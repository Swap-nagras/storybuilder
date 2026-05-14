"""Pydantic schemas used for structured-output prompting and CLI/web messaging."""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


Category = Literal[
    "adventure",
    "fantasy",
    "friendship",
    "animals",
    "bedtime_calm",
    "mystery",
    "lesson_moral",
    "silly_humor",
]

Arc = Literal["classic_5_act", "gentle_3_beat", "lesson_arc"]


class SafetyDecision(BaseModel):
    """Output of the L1 input gate and the L4 final recheck."""

    allow: bool
    reason: str = Field(
        default="",
        description="One sentence explanation. Shown to the user on refusal.",
    )
    category_hint: Optional[str] = None

    @field_validator("reason", mode="before")
    @classmethod
    def _coerce_none(cls, v):
        return "" if v is None else v


class StorySpec(BaseModel):
    """The prompt engineer's plan that the storyteller writes against."""

    category: Category
    arc: Arc
    title_hint: str
    characters: List[str]
    setting: str
    moral_or_theme: str
    tone: str
    vocab_band: str = Field(description="e.g. 'simple, ages 5-7' or 'richer, ages 8-10'")
    target_words: int = Field(ge=200, le=700)
    must_include: List[str] = Field(default_factory=list)
    must_avoid: List[str] = Field(default_factory=list)
    user_revision_note: Optional[str] = None


class Verdict(BaseModel):
    """Evaluator output. score is the mean of the five dimensions (0-10)."""

    reasoning: str = Field(description="Brief chain-of-thought, not shown to user.")
    safety: float = Field(ge=0, le=10)
    age_fit: float = Field(ge=0, le=10)
    arc_quality: float = Field(ge=0, le=10)
    engagement: float = Field(ge=0, le=10)
    vocab_fit: float = Field(ge=0, le=10)
    length_fit: float = Field(ge=0, le=10)
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    passed: bool

    @property
    def score(self) -> float:
        return round(
            (
                self.safety
                + self.age_fit
                + self.arc_quality
                + self.engagement
                + self.vocab_fit
                + self.length_fit
            )
            / 6,
            2,
        )


class ProgressEvent(BaseModel):
    """Emitted by the orchestrator. Drives the CLI verbose mode and the web SSE stream."""

    type: Literal[
        "safety_in",
        "spec",
        "storyteller",
        "evaluator",
        "safety_out",
        "refusal",
        "story",
        "error",
    ]
    agent: str
    payload: dict
