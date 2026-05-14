"""Evaluator: scores the draft on six dimensions and yields structured feedback."""

from config import TEMP_EVALUATOR
from llm import call_json
from prompts import EVALUATOR_SYSTEM
from schemas import StorySpec, Verdict


def judge(spec: StorySpec, story: str) -> Verdict:
    user_prompt = (
        "StorySpec:\n"
        f"  category={spec.category}, arc={spec.arc}, vocab_band={spec.vocab_band}, "
        f"target_words={spec.target_words}\n"
        f"  characters={spec.characters}, setting={spec.setting}, theme={spec.moral_or_theme}\n"
        f"  must_avoid={spec.must_avoid}\n\n"
        "Draft to evaluate:\n"
        f"{story}\n\n"
        f"(Word count: {len(story.split())})"
    )
    return call_json(
        user_prompt=user_prompt,
        system_prompt=EVALUATOR_SYSTEM,
        schema=Verdict,
        temperature=TEMP_EVALUATOR,
        max_tokens=600,
    )
