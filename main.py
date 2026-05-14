"""CLI entry. Same orchestrator that powers the web UI.

What I would have built in 2 more hours:
- A "story memory" so revisions can mention earlier characters/places by reference.
- Read-aloud TTS that streams the story sentence-by-sentence to the speaker.
- A fine-tuned safety classifier on labelled examples instead of a zero-shot prompt
  (cheaper, faster, more consistent than calling gpt-3.5 for the L1/L4 checks).
- A small offline test suite of ~30 stored requests with expected pass/refuse
  outcomes, run on CI to catch prompt regressions.
"""

import sys
from typing import Optional

from schemas import StorySpec


def _print_event(event) -> None:
    """Render a ProgressEvent for the verbose CLI view."""
    t = event.type
    p = event.payload
    if t == "safety_in":
        if p.get("status") == "running":
            print("[L1] safety check: input ...", flush=True)
        else:
            print(f"[L1] safety check: {'ALLOWED' if p['allow'] else 'REFUSED'} — {p['reason']}",
                  flush=True)
    elif t == "spec":
        if p.get("status") == "running":
            print("[promptengineer] planning ...", flush=True)
        elif p.get("status") == "reused":
            print(f"[promptengineer] reusing spec with revision note: {p.get('note', '')}",
                  flush=True)
        else:
            s = p["spec"]
            print(f"[promptengineer] category={s['category']} arc={s['arc']} "
                  f"vocab={s['vocab_band']} target_words={s['target_words']}",
                  flush=True)
    elif t == "storyteller":
        if p.get("status") == "running":
            print(f"[storyteller] iter {p['iteration']}/{p['max']} writing ...", flush=True)
        else:
            print(f"[storyteller] iter {p['iteration']} wrote {p['words']} words", flush=True)
    elif t == "evaluator":
        if p.get("status") == "running":
            print(f"[evaluator] iter {p['iteration']} judging ...", flush=True)
        else:
            print(
                f"[evaluator] iter {p['iteration']} score={p['score']} "
                f"safety={p['safety']} age={p['age_fit']} arc={p['arc_quality']} "
                f"engage={p['engagement']} vocab={p['vocab_fit']} len={p['length_fit']} "
                f"{'PASS' if p['passed'] else 'retry'}",
                flush=True,
            )
            if p.get("issues"):
                for i in p["issues"]:
                    print(f"           issue: {i}", flush=True)
    elif t == "safety_out":
        if p.get("status") == "running":
            print("[L4] final safety recheck ...", flush=True)
        else:
            print(f"[L4] final safety recheck: {'OK' if p['allow'] else 'BLOCKED'} — {p['reason']}",
                  flush=True)
    elif t == "refusal":
        print(f"\n[refused] {p['reason']}\n", flush=True)
    elif t == "story":
        print("\n" + "=" * 60, flush=True)
        print(p["text"], flush=True)
        print("=" * 60, flush=True)
        print(f"(final score: {p['final_score']})", flush=True)
    elif t == "error":
        print(f"[error] {event.agent}: {p.get('message', '?')}", flush=True)


def run_once(
    user_input: str,
    prior_spec: Optional[StorySpec] = None,
    revision_note: Optional[str] = None,
):
    """Run the pipeline once and return the (last_story, last_spec) for revision flow.

    Imported lazily so this module loads cheaply when tested with --help.
    """
    from orchestrator import run as orchestrate

    last_story = None
    last_spec_dump = None
    refused = False
    for ev in orchestrate(user_input, prior_spec=prior_spec, revision_note=revision_note):
        _print_event(ev)
        if ev.type == "story":
            last_story = ev.payload["text"]
            last_spec_dump = ev.payload["spec"]
        elif ev.type == "refusal":
            refused = True
    return last_story, (StorySpec.model_validate(last_spec_dump) if last_spec_dump else None), refused


def main() -> int:
    print("Bedtime Story Studio (for ages 5-10). Ctrl-C to quit.\n")
    try:
        user_input = input("What kind of story do you want to hear? ").strip()
    except (EOFError, KeyboardInterrupt):
        return 0
    if not user_input:
        print("(no input) goodbye.")
        return 0

    story, spec, refused = run_once(user_input)
    if refused or not story:
        return 0

    while True:
        try:
            note = input("\nWant any changes? (e.g. shorter, more dragons, or 'n' to finish): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not note or note.lower() in {"n", "no", "done", "quit", "exit"}:
            print("\nGoodnight!")
            return 0
        story, spec, refused = run_once(user_input, prior_spec=spec, revision_note=note)
        if refused:
            # On refusal of a revision, keep the previous spec so user can try again.
            continue


if __name__ == "__main__":
    sys.exit(main())
