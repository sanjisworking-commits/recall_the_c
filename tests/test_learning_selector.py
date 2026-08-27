"""LearningMixSelector is a pure function over an injected candidate set."""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.planner.eligibility import article_slot_policy, eligible_candidates
from constitution_memorizer.planner.models import MixCandidate
from constitution_memorizer.planner.selector import LearningMixSelector
from constitution_memorizer.progress.scheduler import ReminderEngine


def _unit(unit_id: str, article: str, order: int, *, part: str = "III") -> LearningUnit:
    return LearningUnit(
        id=unit_id,
        type=LearningUnitType.CLAUSE,
        article_number=article,
        display_title=f"Article {article}",
        text=f"Text for {unit_id}",
        estimated_learning_time=60,
        revision_order=order,
        tags=[f"Part {part}"],
    )


def _candidate(unit: LearningUnit, *themes: str) -> MixCandidate:
    numeric = None
    if unit.article_number and unit.article_number.isdigit():
        numeric = int(unit.article_number)
    return MixCandidate(
        unit=unit,
        article_number=unit.article_number,
        part="III",
        chapter=None,
        themes=themes,
        article_numeric=numeric,
    )


def test_selector_is_seeded_and_fills_the_target():
    units = [_unit(f"u{i}", str(14 + i), i) for i in range(8)]
    candidates = [_candidate(unit, "equality") for unit in units]
    first = LearningMixSelector().select(candidates, 5, rng=random.Random(7))
    second = LearningMixSelector().select(candidates, 5, rng=random.Random(7))
    assert [item.id for item in first] == [item.id for item in second]
    assert len(first) == 5
    other = LearningMixSelector().select(candidates, 5, rng=random.Random(99))
    assert {item.id for item in first} != {item.id for item in other} or first[0].id != other[0].id


def test_free_plan_my_day_respects_remaining_article_claim_slots(tmp_path: Path):
    units = [
        _unit("claimed-a", "14", 1),
        _unit("claimed-b", "14", 2),
        _unit("open-15", "15", 3),
        _unit("open-15b", "15", 4),
        _unit("open-16", "16", 5),
        _unit("open-19", "19", 6),
        _unit("open-21", "21", 7),
    ]
    engine = ReminderEngine.from_units(tmp_path / "progress.db", units)
    today = date(2026, 8, 1)
    candidates = eligible_candidates(
        engine,
        as_of=today,
        claimed={"14"},
        remaining_slots=1,
        entitlements_on=True,
    )
    allow = article_slot_policy(
        claimed={"14"}, remaining_slots=1, entitlements_on=True
    )
    mix = LearningMixSelector().select(candidates, 5, rng=random.Random(3), allow=allow)
    introduced = {
        item.article_number
        for item in mix
        if item.article_number and item.article_number not in {"14"}
    }
    assert len(introduced) <= 1
    assert mix
    at_cap = article_slot_policy(claimed={"14", "15", "16"}, remaining_slots=0, entitlements_on=True)
    capped = LearningMixSelector().select(
        candidates, 5, rng=random.Random(3), allow=at_cap
    )
    assert all(item.article_number == "14" for item in capped)


def test_selector_has_no_request_parameter():
    import inspect

    params = inspect.signature(LearningMixSelector.select).parameters
    assert "request" not in params
    assert "candidates" in params
