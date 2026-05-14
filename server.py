"""FastAPI server. Serves the chat frontend and streams pipeline progress over SSE.

Security posture (see README.md for full notes):
- Inputs are length-capped (MAX_INPUT_CHARS / MAX_REVISION_CHARS) and stripped.
- Request body is size-capped before JSON parsing to prevent DoS.
- The orchestrator hardens any client-supplied StorySpec.must_avoid (see
  orchestrator._harden_spec), so a tampered client cannot bypass safety constraints.
- Baseline security headers are added via middleware.
- Internal exceptions are not leaked to the client.
- Server is intended for local use; bind to 127.0.0.1 only.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from config import MAX_INPUT_CHARS, MAX_REVISION_CHARS
from orchestrator import run as orchestrate
from schemas import StorySpec


log = logging.getLogger("story-server")

app = FastAPI(title="Bedtime Story Studio", docs_url=None, redoc_url=None, openapi_url=None)

WEB_DIR = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

# Cap the request body so a single client can't OOM us or stuff our context.
# Generous over the field caps so legitimate JSON (with prior_spec) fits.
MAX_BODY_BYTES = 8 * 1024  # 8 KB

_SEC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "style-src 'self'; "
        "script-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    """Add baseline security headers + body-size guard."""
    # Reject oversized bodies early.
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > MAX_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "request body too large"},
                )
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "bad content-length"})

    response = await call_next(request)
    for k, v in _SEC_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


@app.get("/")
def index():
    return FileResponse(str(WEB_DIR / "index.html"))


class StoryRequest(BaseModel):
    user_input: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)
    prior_spec: Optional[StorySpec] = None
    revision_note: Optional[str] = Field(default=None, max_length=MAX_REVISION_CHARS)

    @field_validator("user_input", "revision_note", mode="before")
    @classmethod
    def _strip_and_check(cls, v):
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("must be a string")
        v = v.strip()
        # Reject control characters except whitespace (\t, \n, \r already stripped).
        if any(0 <= ord(c) < 32 and c not in "\t\n\r" for c in v):
            raise ValueError("control characters not allowed")
        return v


async def _sse_stream(req: StoryRequest) -> AsyncGenerator[str, None]:
    """Run the synchronous orchestrator in a thread, forward events as SSE frames."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def producer() -> None:
        try:
            for ev in orchestrate(
                req.user_input,
                prior_spec=req.prior_spec,
                revision_note=req.revision_note,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, ev.model_dump())
        except Exception:
            # Log the real exception server-side; send a generic message to the client
            # so we don't leak file paths, OpenAI URLs, or stack info.
            log.exception("orchestrator failed")
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {
                    "type": "error",
                    "agent": "orchestrator",
                    "payload": {"message": "Something went wrong on our side. Please try again."},
                },
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

    asyncio.create_task(asyncio.to_thread(producer))

    while True:
        item = await queue.get()
        if item is None:
            break
        yield f"data: {json.dumps(item)}\n\n"


@app.post("/story")
async def story(req: StoryRequest):
    # Pydantic has already enforced length, type, and control-char rules.
    # If revision_note is set, prior_spec must be too (and vice-versa shouldn't matter,
    # but ill-formed combos confuse the orchestrator).
    if req.revision_note is not None and req.prior_spec is None:
        raise HTTPException(status_code=400, detail="revision_note requires prior_spec")
    return StreamingResponse(
        _sse_stream(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
