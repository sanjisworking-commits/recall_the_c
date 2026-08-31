"""Automatic NEW preserves sibling order; revisions and manual Learn do not."""

from __future__ import annotations

import inspect
import random
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.planner.eligibility import (
    eligible_units,
    genuinely_completed,
    sequential_prerequisites_satisfied,
    visible_learning_path,
)
from constitution_memorizer.planner.relationships import candidates_from_units
from constitution_memorizer.planner.roadmap import reconcile_auto_roadmap, roadmap_horizon
from constitution_memorizer.planner.selector import LearningMixSelector
from constitution_memorizer.progress.repository import ProgressRecord
from constitution_memorizer.progress.scheduler import INTERVAL_LADDER, ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.service import due_checklist, select_today_mix

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


def _clause(
    unit_id: str,
    article: str,
    order: int,
    **kwargs,
) -> LearningUnit:
    return LearningUnit(
        id=unit_id,
        type=LearningUnitType.CLAUSE,
        article_number=article,
        display_title=f"Article {article}",
        text=f"Text for {unit_id}",
        estimated_learning_time=60,
        revision_order=order,
        tags=["Part III"],
        **kwargs,
    )


def _subclause(
    unit_id: str,
    article: str,
    parent_id: str,
    *,
    next_id: str | None = None,
    prev_id: str | None = None,
) -> LearningUnit:
    return LearningUnit(
        id=unit_id,
        type=LearningUnitType.SUBCLAUSE,
        article_number=article,
        display_title=unit_id,
        text=f"Text for {unit_id}",
        estimated_learning_time=30,
        revision_order=0,
        tags=["Part III"],
        parent_id=parent_id,
        parent_clause_id=parent_id,
        letter_sequence_next=next_id,
        letter_sequence_prev=prev_id,
    )


def _progress(
    unit_id: str,
    *,
    times_completed: int = 0,
    status: str = "new",
) -> ProgressRecord:
    return ProgressRecord(
        learning_unit_id=unit_id,
        status=status,
        times_completed=times_completed,
        last_completed=None,
        next_revision=None,
        interval_days=0,
        ease_factor=2.5,
        created_at="",
        updated_at="",
    )


def _sibling_catalog(*, fillers: int = 24) -> list[LearningUnit]:
    siblings = [
        _clause("315-1", "315", 1),
        _clause("315-2", "315", 2),
        _clause("315-3", "315", 3),
    ]
    extra = [_clause(f"u{i}", str(400 + i), 20 + i) for i in range(1, fillers + 1)]
    return siblings + extra


def _split_sibling_catalog(*, fillers: int = 24) -> list[LearningUnit]:
    parent = _clause(
        "315-1",
        "315",
        1,
        allows_letter_split=True,
        child_unit_ids=["315-1a", "315-1b"],
    )
    children = [
        _subclause("315-1a", "315", "315-1", next_id="315-1b"),
        _subclause("315-1b", "315", "315-1", prev_id="315-1a"),
    ]
    extra = [_clause(f"u{i}", str(400 + i), 20 + i) for i in range(1, fillers + 1)]
    return [parent, *children, _clause("315-2", "315", 2), *extra]


def _engine(tmp_path: Path, units: list[LearningUnit] | None = None) -> ReminderEngine:
    return ReminderEngine.from_units(
        tmp_path / "progress.db", units or _sibling_catalog()
    )


def _complete(engine: ReminderEngine, unit_id: str, *, as_of: date) -> None:
    engine.mark_all_modes_seen(unit_id)
    engine.mark_done(unit_id, as_of=as_of, require_all_modes=True)


def _reconcile(engine: ReminderEngine, as_of: date, *, target: int = 3) -> None:
    plan = engine.get_learning_plan()
    if not plan.is_auto:
        engine.upsert_learning_plan(mode="auto", daily_target=target, as_of=as_of)
        plan = engine.get_learning_plan()
    reconcile_auto_roadmap(
        engine,
        plan,
        as_of=as_of,
        auto_entitled=True,
        claimed=set(),
        remaining_slots=99,
        entitlements_on=False,
    )


def _ids_on(engine: ReminderEngine, day: date) -> list[str]:
    planned = engine.list_auto_plan_day(day)
    if planned is None:
        return []
    return [item.learning_unit_id for item in planned.items]


def _window_ids(engine: ReminderEngine, as_of: date) -> list[str]:
    horizon = roadmap_horizon(as_of)
    ids: list[str] = []
    for day in engine.list_auto_plan_window(as_of, horizon):
        ids.extend(item.learning_unit_id for item in day.items)
    return ids


def _eligible_ids(engine: ReminderEngine, as_of: date) -> set[str]:
    return {unit.id for unit in eligible_units(engine, as_of=as_of)}


def test_case1_basic_lock():
    units = {u.id: u for u in _sibling_catalog(fillers=0)}
    progress: dict[str, ProgressRecord] = {}
    splits: dict[str, str] = {}
    assert sequential_prerequisites_satisfied(
        units["315-1"], units=units, progress=progress, splits=splits
    )
    assert not sequential_prerequisites_satisfied(
        units["315-2"], units=units, progress=progress, splits=splits
    )


def test_case2_unlock_after_completion():
    units = {u.id: u for u in _sibling_catalog(fillers=0)}
    progress = {"315-1": _progress("315-1", times_completed=1, status="review")}
    assert sequential_prerequisites_satisfied(
        units["315-2"], units=units, progress=progress, splits={}
    )


def test_case3_third_clause_requires_all_previous():
    units = {u.id: u for u in _sibling_catalog(fillers=0)}
    progress = {"315-1": _progress("315-1", times_completed=1, status="review")}
    assert sequential_prerequisites_satisfied(
        units["315-2"], units=units, progress=progress, splits={}
    )
    assert not sequential_prerequisites_satisfied(
        units["315-3"], units=units, progress=progress, splits={}
    )


def test_case4_gap_blocks_later_sibling():
    units = {u.id: u for u in _sibling_catalog(fillers=0)}
    progress = {
        "315-1": _progress("315-1", times_completed=1, status="review"),
        "315-3": _progress("315-3"),
    }
    assert not sequential_prerequisites_satisfied(
        units["315-3"], units=units, progress=progress, splits={}
    )


def test_article_root_is_not_a_prerequisite_for_clause_one():
    root = LearningUnit(
        id="article-315",
        type=LearningUnitType.ARTICLE,
        article_number="315",
        display_title="Article 315",
        text="Overview",
        estimated_learning_time=30,
        revision_order=1,
        tags=["Part XIV"],
    )
    units = {
        "article-315": root,
        "315-1": _clause("315-1", "315", 2),
        "315-2": _clause("315-2", "315", 3),
    }
    path = visible_learning_path("315", units, {})
    assert "article-315" not in path
    assert path == ["315-1", "315-2"]
    assert sequential_prerequisites_satisfied(
        units["315-1"], units=units, progress={}, splits={}
    )


def test_planned_progress_does_not_count_as_completion():
    units = {u.id: u for u in _sibling_catalog(fillers=0)}
    progress = {"315-1": _progress("315-1", times_completed=0, status="new")}
    assert not genuinely_completed(progress, "315-1")
    assert not sequential_prerequisites_satisfied(
        units["315-2"], units=units, progress=progress, splits={}
    )


def test_case5_same_day_planning_does_not_unlock(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    _reconcile(engine, today, target=5)
    today_ids = _ids_on(engine, today)
    chain = {"315-1", "315-2", "315-3"}
    assert not ({"315-1", "315-2"} <= set(today_ids))
    assert len(chain & set(today_ids)) <= 1
    assert "315-2" not in today_ids
    assert "315-3" not in today_ids


def test_case6_recall_mix_stays_random_across_articles(tmp_path: Path):
    catalog = []
    for article, order_base in (("19", 1), ("72", 10), ("315", 20), ("21", 30)):
        catalog.append(_clause(f"{article}-1", article, order_base))
        catalog.append(_clause(f"{article}-2", article, order_base + 1))
    engine = _engine(tmp_path, catalog)
    today = date(2026, 9, 1)
    unlocked = eligible_units(engine, as_of=today)
    assert {unit.id for unit in unlocked} == {"19-1", "72-1", "315-1", "21-1"}
    candidates = candidates_from_units(unlocked)
    orders = {
        tuple(item.article_number for item in LearningMixSelector().select(
            candidates, 3, rng=random.Random(seed)
        ))
        for seed in range(30)
    }
    assert len(orders) > 1
    assert any(order[0] != "19" for order in orders)


def test_case7_future_roadmap_invalidation(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    later = today + timedelta(days=4)
    engine.upsert_learning_plan(mode="auto", daily_target=3, as_of=today)
    engine.replace_auto_plan_day(today, 3, ["315-1", "u1", "u2"])
    engine.replace_auto_plan_day(later, 3, ["315-2", "u3", "u4"])
    assert "315-2" in _ids_on(engine, later)
    _reconcile(engine, today, target=3)
    assert "315-2" not in _window_ids(engine, today)
    assert engine.get_progress("315-1") is None or engine.get_progress("315-1").times_completed == 0


def test_case8_unlocks_after_real_done(tmp_path: Path):
    engine = _engine(tmp_path, _sibling_catalog(fillers=2))
    today = date(2026, 9, 1)
    later = today + timedelta(days=4)
    engine.upsert_learning_plan(mode="auto", daily_target=3, as_of=today)
    engine.replace_auto_plan_day(today, 3, ["315-1", "u1", "u2"])
    engine.replace_auto_plan_day(later, 3, ["315-2", "u1", "u2"])
    _reconcile(engine, today, target=3)
    assert "315-2" not in _window_ids(engine, today)
    assert "315-2" not in _eligible_ids(engine, today)
    _complete(engine, "315-1", as_of=today)
    assert "315-2" in _eligible_ids(engine, today)
    _reconcile(engine, today, target=3)
    assert "315-2" in _window_ids(engine, today)


def test_case9_skip_requeues_first_and_drops_later(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    later = today + timedelta(days=4)
    engine.upsert_learning_plan(mode="auto", daily_target=3, as_of=today)
    engine.replace_auto_plan_day(today, 3, ["315-1", "u1", "u2"])
    engine.replace_auto_plan_day(later, 3, ["315-2", "u3", "u4"])
    engine.create_study_session(
        session_id="skip-315",
        kind="auto_learning",
        plan_date=today,
        unit_ids=["315-1", "u1", "u2"],
    )
    engine.set_study_item_status(
        session_id="skip-315", unit_id="315-1", status="deferred"
    )
    _reconcile(engine, today, target=3)
    progress = engine.get_progress("315-1")
    assert progress is None or progress.times_completed == 0
    session = engine.study_session_for_day(kind="auto_learning", plan_date=today)
    skipped = next(item for item in session.items if item.learning_unit_id == "315-1")
    assert skipped.status == "deferred"
    future_ids = [
        item.learning_unit_id
        for day in engine.list_auto_plan_window(
            today + timedelta(days=1), roadmap_horizon(today)
        )
        for item in day.items
    ]
    assert "315-1" in future_ids
    assert "315-2" not in future_ids
    assert "315-2" not in _ids_on(engine, today)


def test_case10_plan_my_day_uses_same_rule(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    mix = select_today_mix(engine, target=5, as_of=today)
    assert "315-1" in _eligible_ids(engine, today)
    assert "315-2" not in mix
    assert "315-3" not in mix


def test_case11_split_whole_uses_parent_completion(tmp_path: Path):
    engine = _engine(tmp_path, _split_sibling_catalog())
    today = date(2026, 9, 1)
    engine.set_split_preference("315-1", "whole")
    assert "315-2" not in _eligible_ids(engine, today)
    engine.repo.upsert_progress(
        engine.user_id,
        unit_id="315-1a",
        status="review",
        times_completed=1,
        last_completed=today,
        next_revision=today + timedelta(days=1),
        interval_days=1,
    )
    engine.repo.upsert_progress(
        engine.user_id,
        unit_id="315-1b",
        status="review",
        times_completed=1,
        last_completed=today,
        next_revision=today + timedelta(days=1),
        interval_days=1,
    )
    engine._invalidate_progress_cache()
    assert "315-2" not in _eligible_ids(engine, today)
    _complete(engine, "315-1", as_of=today)
    assert "315-2" in _eligible_ids(engine, today)


def test_case12_split_letters_follows_visible_children(tmp_path: Path):
    engine = _engine(tmp_path, _split_sibling_catalog())
    today = date(2026, 9, 1)
    engine.set_split_preference("315-1", "letters")
    assert _eligible_ids(engine, today) >= {"315-1a"}
    assert "315-1" not in _eligible_ids(engine, today)
    assert "315-1b" not in _eligible_ids(engine, today)
    assert "315-2" not in _eligible_ids(engine, today)
    engine.repo.upsert_progress(
        engine.user_id,
        unit_id="315-1",
        status="review",
        times_completed=1,
        last_completed=today,
        next_revision=today + timedelta(days=1),
        interval_days=1,
    )
    engine._invalidate_progress_cache()
    assert "315-2" not in _eligible_ids(engine, today)
    _complete(engine, "315-1a", as_of=today)
    assert "315-1b" in _eligible_ids(engine, today)
    assert "315-2" not in _eligible_ids(engine, today)
    _complete(engine, "315-1b", as_of=today)
    assert "315-2" in _eligible_ids(engine, today)


def test_case13_revision_unaffected(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    engine.repo.upsert_progress(
        engine.user_id,
        unit_id="315-2",
        status="review",
        times_completed=1,
        last_completed=today - timedelta(days=1),
        next_revision=today,
        interval_days=1,
    )
    due = {unit.id for unit in due_checklist(engine, as_of=today)}
    assert "315-2" in due
    assert "315-2" not in _eligible_ids(engine, today)


def test_case14_manual_learn_unrestricted(tmp_path: Path):
    client = TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    )
    resp = client.get("/learn/clause-2", follow_redirects=True)
    assert resp.status_code == 200


def test_case15_no_n_plus_one_db_reads(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date(2026, 9, 1)
    repo = engine.repo
    original_get = repo.get_progress
    original_list = repo.list_all_progress
    original_splits = repo.list_split_preferences
    counts = {"get": 0, "list": 0, "splits": 0}

    def get_progress(*args, **kwargs):
        counts["get"] += 1
        return original_get(*args, **kwargs)

    def list_all_progress(*args, **kwargs):
        counts["list"] += 1
        return original_list(*args, **kwargs)

    def list_split_preferences(*args, **kwargs):
        counts["splits"] += 1
        return original_splits(*args, **kwargs)

    repo.get_progress = get_progress  # type: ignore[method-assign]
    repo.list_all_progress = list_all_progress  # type: ignore[method-assign]
    repo.list_split_preferences = list_split_preferences  # type: ignore[method-assign]

    eligible_units(engine, as_of=today)
    assert counts["get"] == 0
    assert counts["list"] == 1
    assert counts["splits"] == 1


def test_interval_ladder_and_mark_done_untouched():
    assert INTERVAL_LADDER == (1, 3, 7, 15, 30, 60)
    source = inspect.getsource(ReminderEngine.mark_done)
    assert "sequential_prerequisites" not in source
    assert "times_completed" in source
