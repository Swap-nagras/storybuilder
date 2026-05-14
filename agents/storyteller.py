"""Storyteller: writes (or rewrites) the story from a StorySpec + optional feedback."""

from typing import List, Optional

from config import TEMP_STORYTELLER
from llm import call_text
from prompts import STORYTELLER_SYSTEM
from schemas import StorySpec


_ARC_BEATS = {
    "classic_5_act": (
        "Beat 1 (setup): introduce the hero and their ordinary world.\n"
        "Beat 2 (inciting incident): something happens that pulls them into the story.\n"
        "Beat 3 (rising action): they try things; the stakes grow gently.\n"
        "Beat 4 (climax): the turning moment, faced with courage or kindness.\n"
        "Beat 5 (resolution): a warm, safe ending."
    ),
    "gentle_3_beat": (
        "Beat 1 (warm opening): cozy scene, lovable character.\n"
        "Beat 2 (small problem): a tiny gentle worry appears.\n"
        "Beat 3 (comforting resolution): the problem is soothed away; sleep beckons."
    ),
    "lesson_arc": (
        "Beat 1 (situation): the character is going about life.\n"
        "Beat 2 (mistake): they do something small and well-meant that backfires.\n"
        "Beat 3 (realization): a friend or moment helps them see it.\n"
        "Beat 4 (growth): they try again, kinder and wiser. Warm ending."
    ),
}


def _format_spec(spec: StorySpec, prior_issues: Optional[List[str]] = None,
                 prior_suggestions: Optional[List[str]] = None) -> str:
    lines = [
        f"Category: {spec.category}",
        f"Arc: {spec.arc}",
        f"Arc beats to hit:\n{_ARC_BEATS.get(spec.arc, '')}",
        f"Title hint: {spec.title_hint}",
        f"Characters: {', '.join(spec.characters) or '(your choice)'}",
        f"Setting: {spec.setting}",
        f"Moral / theme: {spec.moral_or_theme}",
        f"Tone: {spec.tone}",
        f"Vocabulary band: {spec.vocab_band}",
        f"Target words: {spec.target_words}",
        f"Must include: {', '.join(spec.must_include) or '(none)'}",
        f"Must avoid: {', '.join(spec.must_avoid) or '(none)'}",
    ]
    if spec.user_revision_note:
        lines.append(f"User revision note (latest): {spec.user_revision_note}")
    if prior_issues:
        lines.append("Issues from the previous draft to fix:")
        for i in prior_issues:
            lines.append(f"  - {i}")
    if prior_suggestions:
        lines.append("Suggestions from the editor:")
        for s in prior_suggestions:
            lines.append(f"  - {s}")
    return "\n".join(lines)


def write_story(
    spec: StorySpec,
    prior_issues: Optional[List[str]] = None,
    prior_suggestions: Optional[List[str]] = None,
) -> str:
    user_prompt = _format_spec(spec, prior_issues, prior_suggestions)
    return call_text(
        user_prompt=user_prompt,
        system_prompt=STORYTELLER_SYSTEM,
        temperature=TEMP_STORYTELLER,
        max_tokens=1200,
    ).strip()
