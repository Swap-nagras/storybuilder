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
    HARD_MUST_AVOID,
    MAX_ITERATIONS,
    NO_IMPROVEMENT_EPSILON,
    REFUSAL_PREFIX_UNSAFE_REVISION,
    REFUSAL_PREFIX_UNSAFE_STORY,
    SAFETY_FLOOR,
)
from agents.safety_filter import check_input, check_output, check_revision
from agents.prompt_engineer import build_spec
from agents.storyteller import write_story
from agents.evaluator import judge
from schemas import ProgressEvent, SafetyDecision, StorySpec, Verdict


def _event(type_: str, agent: str, **payload) -> ProgressEvent:
    return ProgressEvent(type=type_, agent=agent, payload=payload)


_PIVOT_HINTS = {"meta_request", "off_topic", "sensitive_info"}


def _format_refusal(decision: SafetyDecision, *, default_prefix: str) -> str:
    """Pick the right refusal framing.

    - meta/off_topic/sensitive: the classifier already wrote a smart pivot in `reason`.
      Use it verbatim — adding a kid-safety prefix would be wrong for a prompt-injection probe.
    - unsafe_topic / unknown: prepend the kid-safety prefix.
    """
    hint = (decision.category_hint or "").lower().strip()
    reason = (decision.reason or "").strip()
    if hint in _PIVOT_HINTS:
        return reason or (
            "I can't share that, but I'd love to tell you a bedtime story instead."
        )
    return default_prefix + (
        reason or "the request involves content that isn't appropriate."
    )


def _harden_spec(spec: StorySpec) -> StorySpec:
    """Force the safety-critical `must_avoid` list onto a spec.

    Prevents a client-supplied (or model-supplied) spec from omitting safety
    constraints. We dedupe while preserving order.
    """
    merged = list(spec.must_avoid)
    for item in HARD_MUST_AVOID:
        if item not in merged:
            merged.append(item)
    return spec.model_copy(update={"must_avoid": merged})


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
        # L1: input safety gate (also catches meta/off-topic/prompt-injection)
        yield _event("safety_in", "safety_filter", status="running")
        decision = check_input(user_input)
        yield _event(
            "safety_in", "safety_filter",
            status="done", allow=decision.allow, reason=decision.reason,
            category_hint=decision.category_hint,
        )
        if not decision.allow:
            yield _event(
                "refusal", "safety_filter",
                reason=_format_refusal(decision, default_prefix=REFUSAL_PREFIX_UNSAFE_STORY),
                category_hint=decision.category_hint,
            )
            return

        # Prompt engineer
        yield _event("spec", "prompt_engineer", status="running")
        try:
            spec = build_spec(user_input)
        except Exception:
            # Do not leak exception details to the client.
            yield _event("error", "prompt_engineer", message="planning failed")
            yield _event(
                "refusal", "prompt_engineer",
                reason="Sorry, I couldn't plan a story for that. Please try a different request.",
            )
            return
        spec = _harden_spec(spec)
        yield _event("spec", "prompt_engineer",
                     status="done", spec=spec.model_dump())
    else:
        # Revision flow: re-check the change itself (covers meta/off-topic/unsafe),
        # then harden the (possibly client-supplied) prior spec.
        yield _event("safety_in", "safety_filter", status="running", revision=True)
        rev_decision = check_revision(revision_note)
        yield _event(
            "safety_in", "safety_filter",
            status="done", revision=True,
            allow=rev_decision.allow, reason=rev_decision.reason,
            category_hint=rev_decision.category_hint,
        )
        if not rev_decision.allow:
            yield _event(
                "refusal", "safety_filter",
                reason=_format_refusal(rev_decision, default_prefix=REFUSAL_PREFIX_UNSAFE_REVISION),
                category_hint=rev_decision.category_hint,
            )
            return

        spec = _harden_spec(prior_spec).model_copy(
            update={"user_revision_note": revision_note},
        )
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
        yield _event(
            "refusal", "evaluator",
            reason=REFUSAL_PREFIX_UNSAFE_STORY
                   + "I couldn't write a draft that met the safety bar.",
        )
        return

    final_story, final_verdict = best

    # L4: independent final safety recheck
    yield _event("safety_out", "safety_filter", status="running")
    final_check = check_output(final_story)
    yield _event("safety_out", "safety_filter",
                 status="done", allow=final_check.allow, reason=final_check.reason)
    if not final_check.allow:
        yield _event(
            "refusal", "safety_filter",
            reason=REFUSAL_PREFIX_UNSAFE_STORY + (final_check.reason or "the draft was unsafe."),
        )
        return

    yield _event(
        "story", "orchestrator",
        text=final_story,
        spec=spec.model_dump(),
        final_score=final_verdict.score,
    )
