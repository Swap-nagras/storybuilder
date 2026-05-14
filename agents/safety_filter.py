"""L1 input gate and L4 final recheck. Both are safety classifiers."""

from config import TEMP_SAFETY
from llm import call_json
from prompts import SAFETY_IN_SYSTEM, SAFETY_OUT_SYSTEM
from schemas import SafetyDecision


def check_input(user_input: str) -> SafetyDecision:
    """L1: should we even try to write a story for this request?"""
    return call_json(
        user_prompt=f"User request:\n{user_input}",
        system_prompt=SAFETY_IN_SYSTEM,
        schema=SafetyDecision,
        temperature=TEMP_SAFETY,
        max_tokens=200,
    )


def check_output(story: str) -> SafetyDecision:
    """L4: independent re-read of the final draft before showing it to the user."""
    return call_json(
        user_prompt=f"Story to audit:\n\n{story}",
        system_prompt=SAFETY_OUT_SYSTEM,
        schema=SafetyDecision,
        temperature=TEMP_SAFETY,
        max_tokens=200,
    )
