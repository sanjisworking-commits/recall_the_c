"""T29 / D122–D124 — desktop Calendar week view."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.calendar_view import (
    WEEK_STATE_LABELS,
    build_calendar_week,
    sunday_week_bounds,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "src/constitution_memorizer/web/templates"
STATIC = ROOT / "src/constitution_memorizer/web/static"


def _engine(tmp_path: Path) -> ReminderEngine:
    return ReminderEngine.from_paths(tmp_path / "progress.db", MINI_UNITS)


def _complete(engine: ReminderEngine, unit_id: str, on: date) -> None:
    engine.mark_all_modes_seen(unit_id)
    engine.mark_done(unit_id, as_of=on)


def test_sunday_week_crosses_month_boundary() -> None:
    start, end = sunday_week_bounds(date(2026, 10, 1))
    assert start == date(2026, 9, 27)
    assert end == date(2026, 10, 3)
    assert start.month != end.month


def test_week_model_seven_days_and_empty_today_ring(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    today = date(2026, 10, 1)
    week = build_calendar_week(engine, week_of=today, today=today)
    assert len(week.days) == 7
    assert week.start == date(2026, 9, 27)
    assert week.end == date(2026, 10, 3)
    assert "September" in week.title
    assert "October" in week.title or "Oct" in week.title
    assert week.days[0].iso == "2026-09-27"
    assert week.days[-1].iso == "2026-10-03"
    thursday = week.days[4]
    assert thursday.is_today is True
    assert thursday.iso == "2026-10-01"
    for day in week.days:
        assert day.week_events == []


def test_week_cards_name_six_states(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    _complete(engine, "clause-1", date(2026, 8, 18))
    today = date(2026, 8, 19)
    week = build_calendar_week(engine, week_of=today, today=today)
    states = {card.state for day in week.days for card in day.week_events}
    assert states
    assert states <= set(WEEK_STATE_LABELS)
    labels = {card.state_label for day in week.days for card in day.week_events}
    assert labels <= set(WEEK_STATE_LABELS.values())
    due_day = next(day for day in week.days if day.iso == today.isoformat())
    assert due_day.week_events
    assert any(card.state_label == "Review due" for card in due_day.week_events)
    assert any(card.href for card in due_day.week_events)


def test_week_route_and_invalid_date(tmp_path: Path) -> None:
    client = TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    )
    ok = client.get("/calendar?view=week&date=2026-10-01")
    assert ok.status_code == 200
    assert "data-calendar-week" in ok.text
    assert 'role="radiogroup"' in ok.text
    assert "view=week" in ok.text
    assert "Nothing due" in ok.text
    assert "Memorized" in ok.text
    assert "Review due" in ok.text
    assert "Overdue" in ok.text
    bad = client.get("/calendar?view=week&date=2026-13-40")
    assert bad.status_code == 400
    garbage = client.get("/calendar?view=week&date=not-a-date")
    assert garbage.status_code == 400
    month = client.get("/calendar?year=2026&month=10")
    assert month.status_code == 200
    assert "data-calendar-week" not in month.text


def test_week_markup_and_phone_footnote_contract() -> None:
    calendar = (TEMPLATES / "calendar.html").read_text(encoding="utf-8")
    assert "view=week" in calendar
    assert "data-calendar-week" in calendar
    assert "data-calendar-gcal-footnote" in calendar
    assert "pending rung" in calendar
    assert "Nothing due" in calendar
    mobile = (STATIC / "mobile.css").read_text(encoding="utf-8")
    assert "calendar-week" in mobile
    assert "calendar-view-switch" in mobile
    styles = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert ".calendar-week-card.is-overdue" in styles
    assert ".calendar-view-switch" in styles
