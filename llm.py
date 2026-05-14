"""Thin wrapper over the OpenAI chat completions API.

Keeps the model pinned to gpt-3.5-turbo per the assignment. Supports an optional
`response_format` for JSON-mode control-plane agents.
"""

import json
import os
from typing import Optional, Type, TypeVar

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from config import MODEL

load_dotenv()

_client: Optional[OpenAI] = None


def _client_singleton() -> OpenAI:
    global _client
    if _client is None:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _client = OpenAI(api_key=key)
    return _client


def call_text(
    user_prompt: str,
    system_prompt: str,
    temperature: float,
    max_tokens: int = 1200,
) -> str:
    """Free-form text generation (used by the storyteller)."""
    resp = _client_singleton().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


T = TypeVar("T", bound=BaseModel)


def call_json(
    user_prompt: str,
    system_prompt: str,
    schema: Type[T],
    temperature: float,
    max_tokens: int = 800,
    retries: int = 1,
) -> T:
    """JSON-mode generation parsed into a Pydantic model.

    Retries once on parse/validation failure with a corrective nudge.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        resp = _client_singleton().chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        try:
            return schema.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = e
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous reply was not valid JSON for the required schema. "
                        f"Error: {e}. Reply again with ONLY a valid JSON object."
                    ),
                }
            )
    raise RuntimeError(f"Failed to get valid JSON after {retries + 1} attempts: {last_err}")
