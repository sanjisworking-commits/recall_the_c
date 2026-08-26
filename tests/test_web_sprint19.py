"""Sprint 19 — Calendar month grid."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.progress.repository import ProgressRecord
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.calendar_view import (
    build_calendar_month,
    completed_review_history,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "progress.db"


@pytest.fixture
def engine(db_path: Path) -> ReminderEngine:
    return ReminderEngine.from_paths(db_path, MINI_UNITS)


@pytest.fixture
def client(db_path: Path) -> TestClient:
    app = create_app(units_path=MINI_UNITS, db_path=db_path)
    return TestClient(app)


def test_calendar_page_renders_month_grid(client: TestClient):
    response = client.get("/calendar?year=2026&month=7")
    assert response.status_code == 200
    html = response.text
    assert "July 2026" in html
    assert "calendar-grid" in html
    assert "calendar-legend" in html
    assert "Memorized" in html
    assert "Review done" in html
    assert "Review due" in html
    assert "Scheduled" in html
    assert "Sun" in html and "Sat" in html
    assert 'href="/calendar?year=2026&amp;month=6"' in html
    assert 'href="/calendar?year=2026&amp;month=8"' in html
    assert "/static/styles.css?" in html
    assert "app.js?v=main44" in html


def test_calendar_invalid_month_returns_400(client: TestClient):
    assert client.get("/calendar?year=2026&month=13").status_code == 400
    assert client.get("/calendar?year=2026&month=0").status_code == 400


def test_calendar_css_chip_styles(client: TestClient):
    css = client.get("/static/styles.css?v=main41")
    assert css.status_code == 200
    text = css.text
    assert ".calendar-grid" in text
    assert ".calendar-chip.is-memorized" in text
    assert ".calendar-chip.is-review-done" in text
    assert ".calendar-chip.is-due" in text
    assert ".calendar-chip.is-scheduled" in text
    assert ".calendar-cell.is-today" in text
    assert "border: 1px dashed" in text


def test_build_calendar_memorized_and_scheduled_chips(engine: ReminderEngine):
    today = date(2026, 7, 20)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 7, 5))
    view = build_calendar_month(engine, year=2026, month=7, today=today)

    assert view.title == "July 2026"
    assert view.memorized_count == 1

    day5 = next(d for d in view.days if d.day == 5)
    assert any(c.kind == "memorized" and c.unit_id == "clause-1" for c in day5.chips)
    assert any(c.label.startswith("Art 20(1)") for c in day5.chips)

    # First interval is 1 day → next_revision July 6 (past → due)
    day6 = next(d for d in view.days if d.day == 6)
    assert any(c.kind == "due" and c.unit_id == "clause-1" for c in day6.chips)

    today_cell = next(d for d in view.days if d.day == 20)
    assert today_cell.is_today


def test_build_calendar_future_scheduled_chip(engine: ReminderEngine):
    today = date(2026, 7, 5)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 7, 5))
    view = build_calendar_month(engine, year=2026, month=7, today=today)
    # Full remaining ladder in July after memorize on the 5th:
    # +1 → 6, +3 → 9, +7 → 16, +15 → 31 (30-day and 60-day fall in later months)
    assert view.scheduled_count == 4
    expected = {
        6: "1-day review",
        9: "3-day review",
        16: "7-day review",
        31: "15-day review",
    }
    for day_num, tip_part in expected.items():
        day = next(d for d in view.days if d.day == day_num)
        chips = [c for c in day.chips if c.kind == "scheduled" and c.unit_id == "clause-1"]
        assert len(chips) == 1
        assert tip_part in chips[0].title


def test_remaining_ladder_projects_full_intervals(engine: ReminderEngine):
    from constitution_memorizer.web.calendar_view import remaining_review_schedule

    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 7, 5))
    row = engine.get_progress("clause-1")
    assert row is not None
    schedule = remaining_review_schedule(row)
    assert [rung for _, rung in schedule] == [1, 3, 7, 15, 30, 60]
    assert [d for d, _ in schedule] == [
        date(2026, 7, 6),
        date(2026, 7, 9),
        date(2026, 7, 16),
        date(2026, 7, 31),
        date(2026, 8, 30),
        date(2026, 10, 29),
    ]


def test_ladder_after_review_starts_at_next_rung(engine: ReminderEngine):
    from constitution_memorizer.web.calendar_view import remaining_review_schedule

    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 7, 5))
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 7, 6))  # completed 1-day → next is 3
    row = engine.get_progress("clause-1")
    assert row is not None
    schedule = remaining_review_schedule(row)
    assert [rung for _, rung in schedule] == [3, 7, 15, 30, 60]
    assert schedule[0][0] == date(2026, 7, 9)


def test_completed_review_history_walks_ladder_backwards():
    row = ProgressRecord(
        learning_unit_id="clause-1",
        status="review",
        times_completed=3,
        last_completed=date(2026, 8, 17),
        next_revision=date(2026, 8, 24),
        interval_days=7,
        ease_factor=2.5,
        created_at="2026-08-13T00:00:00+00:00",
        updated_at="2026-08-17T00:00:00+00:00",
    )
    history = completed_review_history(row)
    assert history == [
        (date(2026, 8, 13), "memorized", None),
        (date(2026, 8, 14), "review_done", 1),
        (date(2026, 8, 17), "review_done", 3),
    ]


def test_completed_review_history_first_done_only():
    row = ProgressRecord(
        learning_unit_id="clause-1",
        status="review",
        times_completed=1,
        last_completed=date(2026, 8, 13),
        next_revision=date(2026, 8, 14),
        interval_days=1,
        ease_factor=2.5,
        created_at="2026-08-13T00:00:00+00:00",
        updated_at="2026-08-13T00:00:00+00:00",
    )
    assert completed_review_history(row) == [
        (date(2026, 8, 13), "memorized", None),
    ]


def test_build_calendar_review_done_and_due_chips(engine: ReminderEngine):
    today = date(2026, 7, 20)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 7, 10))
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 7, 11))  # 1-day review done
    view = build_calendar_month(engine, year=2026, month=7, today=today)

    assert view.memorized_count == 1
    assert view.review_done_count == 1

    day10 = next(d for d in view.days if d.day == 10)
    assert any(c.kind == "memorized" and c.unit_id == "clause-1" for c in day10.chips)

    day11 = next(d for d in view.days if d.day == 11)
    assert any(c.kind == "review_done" and "✓" in c.label for c in day11.chips)
    assert any("1-day review done" in c.title for c in day11.chips)

    # After second completion interval is 3 days → due July 14; later rungs past today skipped
    day14 = next(d for d in view.days if d.day == 14)
    assert any(c.kind == "due" and c.unit_id == "clause-1" for c in day14.chips)
    day21 = next(d for d in view.days if d.day == 21)  # 14 + 7 projected, still future
    assert any(
        c.kind == "scheduled" and "7-day" in c.title for c in day21.chips
    )


def test_build_calendar_keeps_first_done_after_next_day_review(engine: ReminderEngine):
    """First Done on 13 Aug must stay visible after the 1-day review on 14 Aug."""
    today = date(2026, 8, 14)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 8, 13))
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 8, 14))
    view = build_calendar_month(engine, year=2026, month=8, today=today)

    assert view.memorized_count == 1
    assert view.review_done_count == 1

    day13 = next(d for d in view.days if d.day == 13)
    assert any(c.kind == "memorized" and c.unit_id == "clause-1" for c in day13.chips)

    day14 = next(d for d in view.days if d.day == 14)
    assert any(c.kind == "review_done" and c.unit_id == "clause-1" for c in day14.chips)

    day17 = next(d for d in view.days if d.day == 17)
    assert any(c.kind == "scheduled" and c.unit_id == "clause-1" for c in day17.chips)


def test_build_calendar_shows_each_completed_review_in_month(engine: ReminderEngine):
    today = date(2026, 8, 18)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 8, 13))
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 8, 14))
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 8, 17))
    view = build_calendar_month(engine, year=2026, month=8, today=today)

    assert view.memorized_count == 1
    assert view.review_done_count == 2
    kinds = {
        13: "memorized",
        14: "review_done",
        17: "review_done",
    }
    for day_num, kind in kinds.items():
        day = next(d for d in view.days if d.day == day_num)
        assert any(c.kind == kind and c.unit_id == "clause-1" for c in day.chips)


def test_build_calendar_first_done_in_prior_month_stays_on_that_month(
    engine: ReminderEngine,
):
    today = date(2026, 8, 1)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 7, 31))
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 8, 1))

    july = build_calendar_month(engine, year=2026, month=7, today=today)
    assert july.memorized_count == 1
    assert july.review_done_count == 0
    day31 = next(d for d in july.days if d.day == 31)
    assert any(c.kind == "memorized" and c.unit_id == "clause-1" for c in day31.chips)

    august = build_calendar_month(engine, year=2026, month=8, today=today)
    assert august.memorized_count == 0
    assert august.review_done_count == 1
    day1 = next(d for d in august.days if d.day == 1)
    assert any(c.kind == "review_done" and c.unit_id == "clause-1" for c in day1.chips)


def test_calendar_page_shows_chips_from_progress(client: TestClient, engine: ReminderEngine):
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 7, 5))
    html = client.get("/calendar?year=2026&month=7").text
    assert "calendar-chip is-memorized" in html
    assert 'href="/learn/clause-1"' in html
    assert "Art 20(1)" in html


def test_calendar_sunday_first_layout(engine: ReminderEngine):
    # July 2026 starts on Wednesday → 3 leading blanks (Sun–Tue)
    view = build_calendar_month(engine, year=2026, month=7, today=date(2026, 7, 20))
    assert view.weekdays[0] == "Sun"
    assert view.days[0].is_blank
    assert view.days[1].is_blank
    assert view.days[2].is_blank
    assert view.days[3].day == 1


def test_calendar_default_query_uses_today(client: TestClient):
    today = date.today()
    response = client.get("/calendar")
    assert response.status_code == 200
    assert today.strftime("%B %Y") in response.text
