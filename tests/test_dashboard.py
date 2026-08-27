"""Dashboard view-model helpers (Multi-User Experience layout)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.dashboard import (
    build_dashboard_context,
    day_streak,
    due_article_chips,
    due_minutes,
    first_name,
    progress_strip,
    relative_time,
)


def _unit(
    unit_id: str,
    *,
    article_number: str | None = "20",
    display_title: str | None = None,
    estimated_learning_time: int = 90,
    revision_order: int = 1,
) -> LearningUnit:
    return LearningUnit(
        id=unit_id,
        type=LearningUnitType.CLAUSE,
        article_number=article_number,
        display_title=display_title or f"Article {article_number}",
        text=f"Text for {unit_id}",
        estimated_learning_time=estimated_learning_time,
        revision_order=revision_order,
    )


@pytest.fixture
def engine(tmp_path: Path) -> ReminderEngine:
    units = [
        _unit("u1", article_number="20", revision_order=1),
        _unit("u2", article_number="21", revision_order=2),
        _unit("u3", article_number="20", revision_order=3),
    ]
    return ReminderEngine.from_units(tmp_path / "progress.db", units)


def test_first_name_takes_first_token():
    assert first_name("Ada Lovelace") == "Ada"
    assert first_name("  User A  ") == "User"
    assert first_name("") == "Learner"


def test_relative_time_buckets():
    now = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    assert relative_time(now.isoformat(), now=now) == "Just now"
    assert (
        relative_time((now - timedelta(minutes=12)).isoformat(), now=now) == "12m ago"
    )
    assert relative_time((now - timedelta(hours=2)).isoformat(), now=now) == "2h ago"
    assert (
        relative_time((now - timedelta(days=1)).isoformat(), now=now) == "Yesterday"
    )
    assert (
        relative_time((now - timedelta(days=3)).isoformat(), now=now) == "3 days ago"
    )


def test_due_minutes_and_chips():
    units = [
        _unit("a", article_number="20", estimated_learning_time=30),
        _unit("b", article_number="20", estimated_learning_time=45),
        _unit("c", article_number="21", estimated_learning_time=60),
        _unit("d", article_number="22", estimated_learning_time=60),
        _unit("e", article_number="23", estimated_learning_time=60),
    ]
    assert due_minutes(units) == 5  # 255s → ceil → 5
    assert due_minutes([]) == 0
    chips, more = due_article_chips(units, limit=3)
    assert chips == ["Article 20", "Article 21", "Article 22"]
    assert more == 1


def test_day_streak_consecutive_days(engine: ReminderEngine):
    today = date(2026, 8, 3)
    assert day_streak(engine, as_of=today) == 0

    engine.mark_all_modes_seen("u1")
    engine.mark_done("u1", as_of=today - timedelta(days=2))
    engine.mark_all_modes_seen("u2")
    engine.mark_done("u2", as_of=today - timedelta(days=1))
    # Nothing today → streak ends yesterday = 2
    assert day_streak(engine, as_of=today) == 2

    engine.mark_all_modes_seen("u3")
    engine.mark_done("u3", as_of=today)
    assert day_streak(engine, as_of=today) == 3


def test_progress_strip_and_new_user_context(engine: ReminderEngine):
    today = date(2026, 8, 3)
    strip = progress_strip(engine, as_of=today)
    assert strip == {
        "articles_started": 0,
        "units_completed": 0,
        "units_mastered": 0,
        "day_streak": 0,
        "revisions_done": 0,
    }
    ctx = build_dashboard_context(
        engine,
        display_label="Priya Sharma",
        as_of=today,
        now=datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc),
    )
    assert ctx["greeting"] == "Welcome, Priya."
    assert ctx["nothing_due"] is True
    assert ctx["strip"]["revisions_done"] == 0
    assert ctx["recent"] == []

    engine.mark_all_modes_seen("u1")
    engine.mark_done("u1", as_of=today)
    strip2 = progress_strip(engine, as_of=today)
    assert strip2["units_completed"] >= 1
    assert strip2["revisions_done"] >= 1
    assert strip2["day_streak"] >= 1
    ctx2 = build_dashboard_context(
        engine,
        display_label="Priya Sharma",
        as_of=today,
        now=datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc),
    )
    assert ctx2["greeting"] == "Good morning, Priya."
    assert ctx2["recent"]
    assert ctx2["recent"][0]["unit_id"] == "u1"
