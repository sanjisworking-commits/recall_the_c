"""T29 / D122–D124 — desktop Calendar week view."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.playground.schedule import attach_playground_calendar_chips
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.calendar_view import (
    WEEK_STATE_LABELS,
    CalendarChip,
    build_calendar_week,
    sunday_week_bounds,
)
from tests.test_playground_m8 import _seed_progress
from tests.test_roster_m5a import USER, _authed_client, _confirm_add, _csrf, _subscribe

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
    assert "memorized this month" in month.text
    assert "0 units this week" in ok.text
    assert "this month" not in ok.text.split("calendar-summary", 1)[-1].split("</p>", 1)[0]
    assert ok.text.count("Nothing due") >= 7


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
    assert "week.summary" in calendar
    assert "this month" not in calendar.split("calendar-summary", 1)[-1].split("</p>", 1)[0]


def _playground_chip(iso_href: str = "/playground/ndps") -> CalendarChip:
    return CalendarChip(
        kind="due",
        unit_id="",
        label="NDPS Act · §8(a) · Playground",
        title="NDPS Act · Section 8(a) — Day 1 revision · Playground",
        href=iso_href,
        category="Playground",
    )


def test_d122_week_summary_counts_after_playground_attach(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    today = date(2026, 10, 1)
    week = build_calendar_week(engine, week_of=today, today=today)
    assert week.event_count == 0
    assert week.summary == "0 units this week"
    assert "this month" not in week.summary
    attach_playground_calendar_chips(
        week, {week.days[4].iso: [_playground_chip()]}
    )
    assert week.event_count == 1
    assert week.summary == "1 unit this week"
    assert "this month" not in week.summary
    assert "0 reviews scheduled" not in week.summary


def test_d122_week_aggregates_constitution_and_playground(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    today = date(2026, 10, 1)
    week = build_calendar_week(engine, week_of=today, today=today)
    week.days[1].chips.append(
        CalendarChip(
            kind="due",
            unit_id="clause-1",
            label="Art 20(1)",
            title="Article 20(1) — 1-day review due",
            href="/learn/clause-1",
        )
    )
    assert week.event_count == 1
    attach_playground_calendar_chips(
        week, {week.days[3].iso: [_playground_chip()]}
    )
    assert week.event_count == 2
    assert week.summary == "2 units this week"
    assert "this month" not in week.summary


def test_d122_week_http_playground_only_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    day = date.today()
    monkeypatch.setattr(
        "constitution_memorizer.playground.roster.period.playground_today",
        lambda now=None: day,
    )
    client = _authed_client(tmp_path)
    _subscribe(client)
    assert _confirm_add(client, "ndps").status_code == 303
    client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "unit": "ndps:section:8:clause:a"},
        follow_redirects=False,
    )
    _seed_progress(
        client.app.state.playground,
        USER,
        "ndps",
        "ndps:section:8:clause:a",
        status="review",
        interval_days=1,
        next_revision=day.isoformat(),
        times_completed=1,
    )
    page = client.get(f"/calendar?view=week&date={day.isoformat()}")
    assert page.status_code == 200
    html = page.text
    assert "NDPS Act" in html
    assert "§8(a)" in html
    assert "Playground" in html
    summary = html.split("calendar-summary", 1)[-1].split("</p>", 1)[0]
    assert "1 unit this week" in summary
    assert "this month" not in summary
    assert "0 reviews scheduled" not in summary


def test_d122_month_view_keeps_month_summary(tmp_path: Path) -> None:
    client = TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    )
    month = client.get("/calendar?year=2026&month=10")
    assert month.status_code == 200
    summary = month.text.split("calendar-summary", 1)[-1].split("</p>", 1)[0]
    assert "memorized this month" in summary
    assert "this week" not in summary
