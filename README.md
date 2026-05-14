# Bedtime Story Studio — Hippocratic AI Takehome

A multi-agent bedtime-story generator for ages 5-10. The original skeleton called
`gpt-3.5-turbo` once and returned whatever it said. This version splits the job
across three cooperating agents with two extra safety gates, runs an evaluator
in a feedback loop with the storyteller, and exposes both a CLI and a small
ChatGPT-style web UI.

The OpenAI model is unchanged (`gpt-3.5-turbo`) per the assignment.

---

## What it does

```
user input
   │
   ▼
[L1] Input safety gate ─── refuse ──► "I can't write that, because …"
   │ allow
   ▼
Prompt engineer         (categorize → pick story arc → emit StorySpec)
   │
   ▼
Storyteller ─── draft ─► Evaluator (6-dimension scorecard + concrete issues/fixes)
   ▲                       │
   └── feedback ◄──────────┘   loop, max 3 iterations
                               exit on PASS, no-improvement, or cap
   ▼
[L4] Final independent safety re-check ─── refuse ──► graceful refusal
   │ allow
   ▼
Story → user
```

A full ASCII block diagram is in [DIAGRAM.md](DIAGRAM.md).

### The three agents (plus two safety gates)

| Module                              | Role                                                                                                                                                        | Temp | Output           |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- | ---------------- |
| `agents/safety_filter.check_input`  | **L1**: refuse unsafe topics _before_ spending tokens on them.                                                                                              | 0.0  | `SafetyDecision` |
| `agents/prompt_engineer.build_spec` | Classify into one of 8 categories, attach a category-tailored story arc, vocabulary band, target length.                                                    | 0.3  | `StorySpec`      |
| `agents/storyteller.write_story`    | Free-form prose generation against the spec. Hard rules in the system prompt.                                                                               | 0.8  | story text       |
| `agents/evaluator.judge`            | LLM judge. Scores safety, age-fit, arc quality, engagement, vocabulary, length; emits concrete `issues` + `suggestions` that feed back into the next draft. | 0.1  | `Verdict`        |
| `agents/safety_filter.check_output` | **L4**: independent re-read of the final draft, defense-in-depth.                                                                                           | 0.0  | `SafetyDecision` |

### Why the safety design has _two_ gates

The evaluator already scores safety, but the evaluator is graded on the same
draft it just read — its job is closer to the storyteller's than to an
adversary's. The L4 gate calls the safety classifier with a fresh context,
seeing only the final story, with the only mission of refusing. If anything
slipped past the evaluator the L4 gate catches it; if not, it's a quick yes.

### Why per-agent temperatures

The original skeleton used 0.1 for everything. Useful tasks have different needs:

- Safety classifiers want **determinism** → `0.0`.
- The prompt engineer is mostly structured choice → `0.3`.
- The storyteller is creative writing → `0.8`.
- The evaluator wants **consistent grading** → `0.1`.

### How the loop avoids running forever (or hallucinating its way to "pass")

The orchestrator (`orchestrator.py`) terminates on any of:

1. **PASS**: `verdict.passed` is true AND `verdict.score ≥ ACCEPT_SCORE` (8.5).
2. **No improvement**: a new draft did not beat the previous best by at least
   `NO_IMPROVEMENT_EPSILON` (0.1). Stops the loop from spinning on flat scores.
3. **Hard cap**: `MAX_ITERATIONS` = 3.
4. **Safety floor veto**: any draft with `safety < SAFETY_FLOOR` (9.0) is
   discarded _regardless of total score_, so the loop can never "trade off"
   safety for engagement.

If the loop exits without a passing draft, the orchestrator returns the best
_safety-floor-clearing_ draft if one exists, or a graceful refusal if not. It
never hangs.

### README's suggestions

The README suggested arcs, user feedback, and per-category strategies. All three are wired in:

- **Story arcs.** The prompt engineer picks one of `classic_5_act`,
  `gentle_3_beat`, or `lesson_arc` per category, and the storyteller receives
  the explicit beats inline (see `agents/storyteller.py:_ARC_BEATS`).
- **User feedback.** The CLI asks "Want any changes?" after each story; the
  web UI's input placeholder flips to a revision prompt. Either way, the
  request becomes `StorySpec.user_revision_note` and the storyteller↔evaluator
  loop reruns. L1 is skipped (topic already cleared) but L4 still runs on
  the new draft.
- **Per-category strategies.** Each of the 8 categories maps to a different
  arc + tone + vocabulary band combination. `bedtime_calm` gets a soft 3-beat
  arc with no climax; `mystery` gets a 5-act with curious-but-safe stakes;
  `silly_humor` gets a loose 5-act with playful tone. See the
  `PROMPT_ENGINEER_SYSTEM` prompt in `prompts.py`.

---

## Setup

```bash
# 1. install deps
pip install -r requirements.txt

# 2. add your OpenAI key
cp .env.example .env
# then edit .env and paste your key

# 3. run either entrypoint
python main.py                       # CLI
uvicorn server:app --reload          # then open http://localhost:8000
```

The `.env` file is gitignored. **Do not commit it.**

## Run the CLI

```
$ python main.py
Bedtime Story Studio (for ages 5-10). Ctrl-C to quit.

What kind of story do you want to hear? A story about Alice and her cat Bob

[L1] safety check: input ...
[L1] safety check: ALLOWED — Friendly characters with no unsafe content.
[promptengineer] planning ...
[promptengineer] category=friendship arc=lesson_arc vocab=middle, ages 7-9 target_words=400
[storyteller] iter 1/3 writing ...
[storyteller] iter 1 wrote 412 words
[evaluator] iter 1 judging ...
[evaluator] iter 1 score=9.12 safety=10 age=9 arc=9 engage=9 vocab=9 len=9 PASS
[L4] final safety recheck ...
[L4] final safety recheck: OK — safe

============================================================
Once upon a time, in a sunny little house on Maple Lane …
============================================================
(final score: 9.12)

Want any changes? (e.g. shorter, more dragons, or 'n' to finish):
```

## Run the web UI

```bash
uvicorn server:app --reload
# open http://localhost:8000
```

The page is a single-pane ChatGPT-style chat:

- Type the request → an assistant bubble streams the **live pipeline trace**
  (which agent is running, the per-iteration evaluator scores, the specific
  issues being fixed), then the story renders below.
- After a story is shown, the input placeholder flips to
  "Want any changes? (e.g. shorter, more dragons)". The next message is fed
  back as a revision; the same loop runs, with L1 skipped and L4 still on duty.
- **New story** button (top right) resets the spec so the next message starts
  a brand new topic.
- Refusals (L1 or L4) render as a distinct, friendly red bubble — never a
  blank screen or a stack trace.

### Project layout

```
main.py                  CLI entry
server.py                FastAPI app + SSE stream for the web UI
orchestrator.py          The pipeline. Generator of ProgressEvents shared by CLI and web.
agents/
  safety_filter.py       L1 input gate + L4 final recheck
  prompt_engineer.py     Categorize + emit StorySpec
  storyteller.py         Story generation against a spec
  evaluator.py           Judge with per-dimension scorecard
schemas.py               Pydantic models (StorySpec, Verdict, SafetyDecision, ProgressEvent)
prompts.py               All system prompts (kept in one file for easy iteration)
llm.py                   call_text + call_json wrappers around OpenAI chat completions
config.py                Knobs: thresholds, temperatures, iter cap, word range
web/
  index.html             Chat UI shell
  app.js                 SSE client + DOM rendering
  style.css              Dark theme
DIAGRAM.md               The block diagram
requirements.txt
.env.example             API key template (real .env is gitignored)
```

### Prompting strategies in use

- **Few-shot prompting** on every control-plane agent (safety L1, prompt
  engineer, evaluator, safety L4). Each system prompt is followed by 2-4
  worked examples interleaved as alternating `(user, assistant)` turns —
  `llm._build_messages` assembles them. The example sets live in `prompts.py`
  as `SAFETY_IN_FEWSHOT`, `PROMPT_ENGINEER_FEWSHOT`, `EVALUATOR_FEWSHOT`,
  `SAFETY_OUT_FEWSHOT`. The examples are deliberately mixed: each set covers
  one or more "allow / pass" cases and one or more "refuse / fail" cases,
  including an **adversarial** one (a "kid-friendly vampire" framing for L1,
  a violent draft for the evaluator) so the model has seen the exact failure
  mode it must catch. This is the single biggest reliability lever on
  gpt-3.5-turbo's structured outputs in this pipeline.
- **Role + constraint prompts** with explicit "for ages 5-10" framing on every agent.
- **JSON-mode + Pydantic parsing** on all three control-plane agents (safety,
  prompt engineer, evaluator). The storyteller stays free-form.
- **Chain-of-thought inside the JSON envelope** — the evaluator returns a
  `reasoning` field so it thinks before scoring, but the reasoning is never
  shown to the user (see `schemas.Verdict.reasoning`).
- **Explicit negative constraints** in the storyteller system prompt — at
  gpt-3.5 quality, listing what _not_ to do beats hoping it'll infer.
- **Per-iteration feedback injection** — the evaluator's `issues` and
  `suggestions` are formatted into the _next_ storyteller prompt, so the model
  has concrete targets to fix instead of just "try again".
- **Category-tailored arc beats** are inlined into the storyteller prompt so
  gpt-3.5 doesn't have to invent structure.
- **Safety floor as a hard veto**: a verdict with `safety < 9.0` is discarded
  in code, not just trusted to the evaluator's `passed` flag — defense in depth.

### What I would build with 2 more hours

(Also noted at the top of `main.py`.)

- A small offline test suite of ~30 stored requests with expected pass/refuse
  outcomes, run in CI to catch prompt regressions.
- A fine-tuned safety classifier on labeled examples instead of a zero-shot
  prompt — cheaper, faster, more consistent than gpt-3.5 for L1/L4.
- "Story memory" so a revision can refer to characters from earlier in the
  conversation.
- Sentence-level read-aloud streaming TTS.
- A `--dry-run` mode that traces the full pipeline against canned responses
  for local-only testing without burning API spend.

---

## Original assignment

See `README_ORIGINAL.md` for the unmodified assignment text.
