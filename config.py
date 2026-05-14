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

REFUSAL_PREFIX_UNSAFE_STORY = (
    "I can't write that story, because it would not be safe for a 5-10 year old. "
)
REFUSAL_PREFIX_UNSAFE_REVISION = (
    "I can't make that change to the story, because it would not be safe for a 5-10 year old. "
)

# Maximum lengths to defend against prompt-stuffing and OpenAI cost abuse.
MAX_INPUT_CHARS = 500
MAX_REVISION_CHARS = 200

# Safety floor fields that the server forces on every StorySpec, so a malicious
# client cannot send `must_avoid: []` to bypass storyteller constraints.
HARD_MUST_AVOID = [
    "violence",
    "weapons used to harm",
    "scary imagery",
    "death without comfort",
    "romantic content",
    "profanity",
    "real-world tragedy",
    "drugs, alcohol, gambling",
    "hate speech, slurs, political or religious conflict",
]
