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
    assert "Article 20" in ctx2["recent"][0]["text"]


def test_dashboard_today_mode_revision_first(engine: ReminderEngine):
    today = date(2026, 8, 3)
    engine.mark_all_modes_seen("u1")
    engine.mark_done("u1", as_of=today - timedelta(days=1))
    ctx = build_dashboard_context(
        engine,
        display_label="Priya Sharma",
        as_of=today,
        entitled=True,
    )
    assert ctx["today_mode"] == "start_revision"
    assert ctx["due_count"] == 1

    from constitution_memorizer.progress.study_session import start_or_resume_revision

    session = start_or_resume_revision(engine, today=today)
    assert session is not None
    ctx2 = build_dashboard_context(
        engine,
        display_label="Priya Sharma",
        as_of=today,
        entitled=True,
    )
    assert ctx2["today_mode"] == "continue_revision"
    assert ctx2["revision_left"] == session.pending_count


def test_dashboard_today_mode_self_paced_when_caught_up(engine: ReminderEngine):
    today = date(2026, 8, 3)
    ctx = build_dashboard_context(
        engine,
        display_label="Priya Sharma",
        as_of=today,
        entitled=False,
    )
    assert ctx["today_mode"] in ("self_paced", "caught_up")
    assert ctx["nothing_due"] is True


def test_dashboard_uses_user_local_date_not_utc(engine: ReminderEngine, monkeypatch):
    from zoneinfo import ZoneInfo

    from constitution_memorizer.progress.local_date import USER_TIMEZONE_KEY, user_today

    utc_instant = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    utc_today = utc_instant.date()
    local_today = utc_instant.astimezone(ZoneInfo("Pacific/Kiritimati")).date()
    assert local_today != utc_today

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return utc_instant.replace(tzinfo=None)
            return utc_instant.astimezone(tz)

    monkeypatch.setattr(
        "constitution_memorizer.progress.local_date.datetime", FrozenDateTime
    )
    engine.set_setting(USER_TIMEZONE_KEY, "Pacific/Kiritimati")
    engine.mark_all_modes_seen("u1")
    engine.mark_done("u1", as_of=utc_today)
    assert user_today(engine) == local_today

    ctx_local = build_dashboard_context(
        engine,
        display_label="Priya Sharma",
        entitled=True,
    )
    assert ctx_local["today_mode"] == "start_revision"
    assert ctx_local["due_count"] >= 1

    ctx_utc = build_dashboard_context(
        engine,
        display_label="Priya Sharma",
        as_of=utc_today,
        entitled=True,
    )
    assert ctx_utc["due_count"] == 0
    assert ctx_utc["today_mode"] != "start_revision"


def test_dashboard_today_mode_continue_learning(engine: ReminderEngine):
    today = date(2026, 8, 3)
    from constitution_memorizer.progress.study_session import start_or_resume_learning

    session = start_or_resume_learning(
        engine, kind="one_day_learning", count=3, today=today
    )
    assert session is not None
    ctx = build_dashboard_context(
        engine,
        display_label="Priya Sharma",
        as_of=today,
        entitled=False,
    )
    assert ctx["today_mode"] == "continue_learning"
    assert ctx["learning_count"] == session.pending_count
    assert f"{session.pending_count} left" in ctx["continue_learning_label"]
    assert "today's plan" in ctx["continue_learning_label"]


def test_dashboard_plan_prompt_is_behind_dialog():
    html = Path(
        "src/constitution_memorizer/web/templates/dashboard.html"
    ).read_text(encoding="utf-8")
    assert "Nothing to review today." in html
    assert "Want Recall to plan today's learning?" in html
    assert "Plan my day" in html
    dialog_at = html.index("data-plan-my-day-dialog")
    prompt_at = html.index("Want Recall to plan today's learning?")
    assert prompt_at < dialog_at
    assert 'name="count"' not in html[:dialog_at]
    assert 'name="count" value="{{ n }}"' in html[dialog_at:]
    assert "((3, 'Steady · 3'), (5, 'Balanced · 5'), (7, 'Intensive · 7'))" in html[dialog_at:]
    dash_py = Path("src/constitution_memorizer/web/dashboard.py").read_text(
        encoding="utf-8"
    )
    assert "Continue today's plan" in dash_py
    assert "Continue learning" in dash_py


def test_dashboard_route_passes_user_today():
    source = Path("src/constitution_memorizer/auth/routes.py").read_text(
        encoding="utf-8"
    )
    dash = source[source.index("def dashboard") : source.index("ctx[\"user\"]")]
    assert "as_of=user_today(eng)" in dash
