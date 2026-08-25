"""User learning-plan preference (self-paced vs Auto 3/5/7)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

LearningPlanMode = Literal["self_paced", "auto"]
DailyTarget = Literal[3, 5, 7]

VALID_MODES: frozenset[str] = frozenset(("self_paced", "auto"))
VALID_TARGETS: frozenset[int] = frozenset((3, 5, 7))

PACE_LABELS = {3: "Steady", 5: "Balanced", 7: "Intensive"}


@dataclass(frozen=True)
class LearningPlan:
    user_id: str
    mode: LearningPlanMode
    daily_target: DailyTarget | None
    activated_at: date | None
    plan_prompt_dismissed_on: date | None
    updated_at: str

    @property
    def is_auto(self) -> bool:
        return self.mode == "auto" and self.daily_target in VALID_TARGETS

    @property
    def is_anchored(self) -> bool:
        return self.is_auto and self.activated_at is not None

    @property
    def is_unanchored_auto(self) -> bool:
        return self.is_auto and self.activated_at is None

    @property
    def pace_label(self) -> str:
        if self.daily_target in PACE_LABELS:
            return PACE_LABELS[self.daily_target]
        return ""


def default_learning_plan(user_id: str) -> LearningPlan:
    return LearningPlan(
        user_id=str(user_id),
        mode="self_paced",
        daily_target=None,
        activated_at=None,
        plan_prompt_dismissed_on=None,
        updated_at="",
    )


def _as_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value)
    if not text:
        return None
    return date.fromisoformat(text[:10])


def learning_plan_from_row(row: object, user_id: str) -> LearningPlan:
    target_raw = row["daily_target"]  # type: ignore[index]
    target: DailyTarget | None = None
    if target_raw is not None:
        try:
            parsed = int(target_raw)
        except (TypeError, ValueError):
            parsed = 0
        if parsed in VALID_TARGETS:
            target = parsed  # type: ignore[assignment]
    mode_raw = str(row["mode"] or "self_paced")  # type: ignore[index]
    mode: LearningPlanMode = "auto" if mode_raw == "auto" else "self_paced"
    return LearningPlan(
        user_id=str(user_id),
        mode=mode,
        daily_target=target,
        activated_at=_as_date(row["activated_at"]),  # type: ignore[index]
        plan_prompt_dismissed_on=_as_date(row["plan_prompt_dismissed_on"]),  # type: ignore[index]
        updated_at=str(row["updated_at"] or ""),  # type: ignore[index]
    )


def validate_mode(mode: str) -> LearningPlanMode:
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid learning plan mode: {mode}")
    return mode  # type: ignore[return-value]


def validate_target(value: int | None) -> DailyTarget | None:
    if value is None:
        return None
    if int(value) not in VALID_TARGETS:
        raise ValueError(f"Invalid daily target: {value}")
    return int(value)  # type: ignore[return-value]
