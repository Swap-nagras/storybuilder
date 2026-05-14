"""FastAPI server. Serves the chat frontend and streams pipeline progress over SSE."""

import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from orchestrator import run as orchestrate
from schemas import StorySpec


app = FastAPI(title="Bedtime Story Studio")

WEB_DIR = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(WEB_DIR / "index.html"))


class StoryRequest(BaseModel):
    user_input: str
    prior_spec: Optional[StorySpec] = None
    revision_note: Optional[str] = None


async def _sse_stream(req: StoryRequest) -> AsyncGenerator[str, None]:
    """Run the synchronous orchestrator in a thread, forward events as SSE frames.

    SSE frames look like:
        data: {"type":"...","agent":"...","payload":{...}}\\n\\n
    """
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
        except Exception as e:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "error", "agent": "orchestrator", "payload": {"message": str(e)}},
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
    return StreamingResponse(
        _sse_stream(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering if any
        },
    )
