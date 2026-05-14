"""L1 input gate and L4 final recheck. Both are safety classifiers."""

from config import TEMP_SAFETY
from llm import call_json
from prompts import (
    SAFETY_IN_FEWSHOT,
    SAFETY_IN_SYSTEM,
    SAFETY_OUT_FEWSHOT,
    SAFETY_OUT_SYSTEM,
)
from schemas import SafetyDecision


def check_input(user_input: str) -> SafetyDecision:
    """L1: should we even try to write a story for this request?"""
    return call_json(
        user_prompt=f"User request:\n{user_input}",
        system_prompt=SAFETY_IN_SYSTEM,
        schema=SafetyDecision,
        temperature=TEMP_SAFETY,
        max_tokens=200,
        few_shot=SAFETY_IN_FEWSHOT,
    )


def check_revision(revision_note: str) -> SafetyDecision:
    """L1 (revision flavor): is this change request itself safe to apply?

    The original topic was already cleared, but the user could now ask to add
    something unsafe ("make it bloodier", "have a character die violently").
    Same prompt + few-shot examples as `check_input`; only the framing of the
    user message differs so the classifier evaluates it as a modification to
    an existing children's story rather than as a fresh request.
    """
    return call_json(
        user_prompt=(
            "The following is a revision the user wants applied to an existing "
            "bedtime story for ages 5-10. Decide whether applying this change "
            "would keep the story safe and appropriate.\n\n"
            f"Revision: {revision_note}"
        ),
        system_prompt=SAFETY_IN_SYSTEM,
        schema=SafetyDecision,
        temperature=TEMP_SAFETY,
        max_tokens=200,
        few_shot=SAFETY_IN_FEWSHOT,
    )


def check_output(story: str) -> SafetyDecision:
    """L4: independent re-read of the final draft before showing it to the user."""
    return call_json(
        user_prompt=f"Story to audit:\n\n{story}",
        system_prompt=SAFETY_OUT_SYSTEM,
        schema=SafetyDecision,
        temperature=TEMP_SAFETY,
        max_tokens=200,
        few_shot=SAFETY_OUT_FEWSHOT,
    )
