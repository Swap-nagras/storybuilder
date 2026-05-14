# System Block Diagram

```
                          ┌────────────────────────┐
                          │       USER INPUT       │
                          │  "A story about ..."   │
                          └───────────┬────────────┘
                                      │
                                      ▼
                  ┌───────────────────────────────────────┐
                  │  L1 — INPUT SAFETY GATE  (temp=0.0)   │
                  │  agents/safety_filter.check_input     │
                  │  → SafetyDecision{allow, reason}      │
                  └─────┬─────────────────────────┬───────┘
                        │ refuse                  │ allow
                        ▼                         ▼
              ┌──────────────────┐  ┌────────────────────────────────┐
              │ Polite refusal   │  │  PROMPT ENGINEER  (temp=0.3)   │
              │ → user           │  │  agents/prompt_engineer        │
              └──────────────────┘  │  • classify into 1 of 8 cats   │
                                    │  • pick arc (3 styles)         │
                                    │  • set vocab band + length     │
                                    │  → StorySpec                   │
                                    └────────────────┬───────────────┘
                                                     │
                                                     ▼
                  ┌───────────────────────────────────────────────────┐
                  │                                                   │
                  │   ╔═════════════════════════════════════════╗     │
                  │   ║         FEEDBACK LOOP (≤3 iters)        ║     │
                  │   ║                                         ║     │
                  │   ║  ┌─────────────────┐                    ║     │
                  │   ║  │  STORYTELLER    │ ──── draft ──┐     ║     │
                  │   ║  │   (temp=0.8)    │              │     ║     │
                  │   ║  │  + arc beats    │              ▼     ║     │
                  │   ║  │  + must_avoid   │     ┌────────────────┐   │
                  │   ║  └────────▲────────┘     │  EVALUATOR     │   │
                  │   ║           │              │   (temp=0.1)   │   │
                  │   ║           │              │  scores 0-10:  │   │
                  │   ║           │              │  • safety      │   │
                  │   ║           │              │  • age_fit     │   │
                  │   ║   issues +               │  • arc_quality │   │
                  │   ║   suggestions ◄─────────│  • engagement  │   │
                  │   ║                          │  • vocab_fit   │   │
                  │   ║                          │  • length_fit  │   │
                  │   ║                          │  → Verdict     │   │
                  │   ║                          └────────┬───────┘   │
                  │   ║                                   │           │
                  │   ║   exit when:                      │           │
                  │   ║    • passed AND score ≥ 8.5  ─────┤           │
                  │   ║    • score not improving    ─────┤           │
                  │   ║    • iter == 3              ─────┤           │
                  │   ║    (safety<9 ⇒ draft discarded, not chosen) ║│
                  │   ╚═══════════════════════════════════╪═════════╝│
                  │                                       │           │
                  └───────────────────────────────────────┼───────────┘
                                                          ▼
                  ┌────────────────────────────────────────────────────┐
                  │  L4 — FINAL SAFETY RE-CHECK  (temp=0.0)            │
                  │  agents/safety_filter.check_output                 │
                  │  fresh context, only sees the chosen draft         │
                  │  → SafetyDecision{allow, reason}                   │
                  └─────┬─────────────────────────────────┬────────────┘
                        │ block                            │ allow
                        ▼                                  ▼
              ┌──────────────────┐               ┌────────────────────┐
              │ Polite refusal   │               │   STORY → USER     │
              │ → user           │               └─────────┬──────────┘
              └──────────────────┘                         │
                                                           │
                                          ┌────────────────┴────────────────┐
                                          │   user feedback ("shorter",     │
                                          │   "add a moon")                 │
                                          └────────────────┬────────────────┘
                                                           │
                                                  StorySpec.user_revision_note
                                                  reuse spec, skip L1,
                                                  rerun loop, L4 still runs
                                                           │
                                                           └──► back into loop
```

Legend:

- `L1` and `L4` are independent safety classifiers. L1 saves work by refusing
  bad topics before any storytelling happens. L4 reads the *final* draft with
  fresh context and acts as a last-line defense.
- The evaluator's `safety` dimension is one of six scored dimensions; the
  orchestrator additionally enforces a **hard floor** (`safety ≥ 9.0`) in code,
  so the loop can never pick an unsafe draft regardless of overall score.
- The whole pipeline is a generator of `ProgressEvent`s, which is what powers
  both the verbose CLI output and the live trace in the web UI.
