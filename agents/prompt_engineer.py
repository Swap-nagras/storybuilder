"""Prompt engineer: classifies the request and emits a tailored StorySpec."""

from config import TEMP_PROMPT_ENGINEER
from llm import call_json
from prompts import PROMPT_ENGINEER_FEWSHOT, PROMPT_ENGINEER_SYSTEM
from schemas import StorySpec


def build_spec(user_input: str) -> StorySpec:
    return call_json(
        user_prompt=f"User request:\n{user_input}",
        system_prompt=PROMPT_ENGINEER_SYSTEM,
        schema=StorySpec,
        temperature=TEMP_PROMPT_ENGINEER,
        max_tokens=600,
        few_shot=PROMPT_ENGINEER_FEWSHOT,
    )
