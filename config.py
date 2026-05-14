"""Central configuration. Single source of truth for tunable knobs."""

MODEL = "gpt-3.5-turbo"

MAX_ITERATIONS = 3
ACCEPT_SCORE = 8.5
SAFETY_FLOOR = 9.0
NO_IMPROVEMENT_EPSILON = 0.1

TEMP_SAFETY = 0.0
TEMP_PROMPT_ENGINEER = 0.3
TEMP_STORYTELLER = 0.8
TEMP_EVALUATOR = 0.1

MIN_WORDS = 300
MAX_WORDS = 500

REFUSAL_PREFIX = (
    "I can't write that story, because it would not be safe for a 5-10 year old. "
)
