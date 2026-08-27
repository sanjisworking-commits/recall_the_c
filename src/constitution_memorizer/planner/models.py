"""Learning-plan preference and rolling NEW-capacity models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from constitution_memorizer.learning.schemas import LearningUnit
from constitution_memorizer.progress.repository import (
    VALID_DAILY_TARGETS,
    UserLearningPlan,
)

DailyTarget = Literal[3, 5, 7]
PlanDayKind = Literal["review", "new", "empty"]

PACE_LABELS: dict[int, str] = {
    3: "Steady",
    5: "Balanced",
    7: "Intensive",
}

TARGET_COMPOSITION: dict[int, tuple[int, int, int]] = {
    # close, related, explore — plus the anchor, which is chosen first
    3: (1, 1, 0),
    5: (2, 1, 1),
    7: (3, 2, 1),
}


def pace_label(target: int | None) -> str:
    if target in PACE_LABELS:
        return PACE_LABELS[target]
    return "Self-paced"


@dataclass(frozen=True)
class PlannedDay:
    day: date
    kind: PlanDayKind
    review_count: int = 0
    new_capacity: int = 0

    @property
    def calendar_marker(self) -> str | None:
        if self.kind == "review" and self.review_count:
            return f"REVIEW · {self.review_count}"
        if self.kind == "new" and self.new_capacity:
            return f"NEW · {self.new_capacity}"
        return None


@dataclass(frozen=True)
class MixCandidate:
    """A unit plus the structural/theme metadata the selector scores against."""

    unit: LearningUnit
    article_number: str | None
    part: str | None
    chapter: str | None
    themes: tuple[str, ...]
    article_numeric: int | None

    @property
    def id(self) -> str:
        return self.unit.id

    @property
    def primary_theme(self) -> str:
        if self.themes:
            return self.themes[0]
        return self.part or "explore"


def normalize_target(value: int | None) -> int | None:
    if value in VALID_DAILY_TARGETS:
        return int(value)
    return None


def auto_is_projectable(plan: UserLearningPlan) -> bool:
    """Future NEW capacity exists only after Auto has been activated by a NEW Done."""
    return plan.is_active_auto
