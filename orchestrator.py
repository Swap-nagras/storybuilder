"""Pipeline orchestration. Yields ProgressEvents so CLI and web share the same engine.

Flow:
  L1 safety -> prompt engineer -> [storyteller <-> evaluator] loop -> L4 safety -> story.

Revision path (user gave feedback on a prior story):
  reuse prior spec, attach revision_note, skip L1 (topic already cleared),
  rerun the storyteller<->evaluator loop, still run L4 on the new draft.
"""

from typing import Generator, Optional

from config import (
    ACCEPT_SCORE,
    MAX_ITERATIONS,
    NO_IMPROVEMENT_EPSILON,
    REFUSAL_PREFIX,
    SAFETY_FLOOR,
)
from agents.safety_filter import check_input, check_output
from agents.prompt_engineer import build_spec
from agents.storyteller import write_story
from agents.evaluator import judge
from schemas import ProgressEvent, StorySpec, Verdict


def _event(type_: str, agent: str, **payload) -> ProgressEvent:
    return ProgressEvent(type=type_, agent=agent, payload=payload)


def run(
    user_input: str,
    prior_spec: Optional[StorySpec] = None,
    revision_note: Optional[str] = None,
) -> Generator[ProgressEvent, None, None]:
    """Run the full pipeline, streaming progress.

    The final event is either type='story' (with text + spec) or type='refusal' (with reason).
    """
    is_revision = prior_spec is not None and revision_note is not None

    if not is_revision:
        # L1: input safety gate
        yield _event("safety_in", "safety_filter", status="running")
        decision = check_input(user_input)
        yield _event("safety_in", "safety_filter",
                     status="done", allow=decision.allow, reason=decision.reason)
        if not decision.allow:
            yield _event("refusal", "safety_filter",
                         reason=REFUSAL_PREFIX + decision.reason)
            return

        # Prompt engineer
        yield _event("spec", "prompt_engineer", status="running")
        try:
            spec = build_spec(user_input)
        except Exception as e:
            yield _event("error", "prompt_engineer", message=str(e))
            yield _event("refusal", "prompt_engineer",
                         reason="Sorry, I couldn't plan a story for that. Please try a different request.")
            return
        yield _event("spec", "prompt_engineer",
                     status="done", spec=spec.model_dump())
    else:
        # Revision: reuse spec, attach the new instruction.
        spec = prior_spec.model_copy(update={"user_revision_note": revision_note})
        yield _event("spec", "prompt_engineer",
                     status="reused", spec=spec.model_dump(),
                     note=f"Revision: {revision_note}")

    # Storyteller <-> Evaluator loop
    best: Optional[tuple[str, Verdict]] = None
    prior_issues: list[str] = []
    prior_suggestions: list[str] = []

    for iteration in range(1, MAX_ITERATIONS + 1):
        yield _event("storyteller", "storyteller",
                     status="running", iteration=iteration, max=MAX_ITERATIONS)
        story = write_story(spec, prior_issues, prior_suggestions)
        yield _event("storyteller", "storyteller",
                     status="done", iteration=iteration, words=len(story.split()))

        yield _event("evaluator", "evaluator", status="running", iteration=iteration)
        verdict = judge(spec, story)
        yield _event(
            "evaluator", "evaluator",
            status="done", iteration=iteration,
            score=verdict.score,
            safety=verdict.safety, age_fit=verdict.age_fit,
            arc_quality=verdict.arc_quality, engagement=verdict.engagement,
            vocab_fit=verdict.vocab_fit, length_fit=verdict.length_fit,
            passed=verdict.passed,
            issues=verdict.issues, suggestions=verdict.suggestions,
        )

        if verdict.safety < SAFETY_FLOOR:
            # Unsafe draft - never let it win, even if other dimensions are high.
            prior_issues = verdict.issues + [
                "Previous draft had a safety problem; remove ALL unsafe content."
            ]
            prior_suggestions = verdict.suggestions
            continue

        if best is None or verdict.score > best[1].score + NO_IMPROVEMENT_EPSILON:
            best = (story, verdict)
        else:
            # Not improving meaningfully - stop spending API calls.
            break

        if verdict.passed and verdict.score >= ACCEPT_SCORE:
            break

        prior_issues = verdict.issues
        prior_suggestions = verdict.suggestions

    if best is None:
        yield _event("refusal", "evaluator",
                     reason=REFUSAL_PREFIX + "I couldn't write a draft that met the safety bar.")
        return

    final_story, final_verdict = best

    # L4: independent final safety recheck
    yield _event("safety_out", "safety_filter", status="running")
    final_check = check_output(final_story)
    yield _event("safety_out", "safety_filter",
                 status="done", allow=final_check.allow, reason=final_check.reason)
    if not final_check.allow:
        yield _event("refusal", "safety_filter",
                     reason=REFUSAL_PREFIX + final_check.reason)
        return

    yield _event(
        "story", "orchestrator",
        text=final_story,
        spec=spec.model_dump(),
        final_score=final_verdict.score,
    )
