"""R6 — Today path merge, Calendar Playground chips, Google pending rung, T32.

Closes U6 D115–D124 and T28–T32. Alembic head remains 20260927_0027.
Does not start R7 or reopen R5.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from alembic.config import Config
from alembic.script import ScriptDirectory

from constitution_memorizer.calendar_sync.projection import (
    DayItem,
    MAX_DESCRIPTION_ITEMS,
    build_event_content,
    build_projection,
)
from constitution_memorizer.calendar_sync.sync import _prepare_reconciliation
from constitution_memorizer.playground.schedule import (
    merge_today_path,
    playground_projection_extra,
)
from constitution_memorizer.web.dashboard import TodayUnit
from constitution_memorizer.web.service import _is_missing_optional_schema
from tests.test_playground_m8 import TODAY, _seed_progress
from tests.test_roster_m5a import USER, _authed_client, _confirm_add, _csrf, _subscribe

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "20260927_0027"
TEMPLATES = ROOT / "src/constitution_memorizer/web/templates"
STATIC = ROOT / "src/constitution_memorizer/web/static"
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


def _unit(**overrides) -> TodayUnit:
    base = dict(
        unit_id="u1",
        title="Article 14",
        article_label="Article 14",
        kind="review",
        status="upcoming",
        href="/learn/u1",
        position=1,
        subtitle="",
        day_label="Day 3 revision",
        source="constitution",
        eyebrow="",
        cta_label="Start revision →",
    )
    base.update(overrides)
    return TodayUnit(**base)


def test_r6_alembic_head_unchanged() -> None:
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    assert set(script.get_heads()) == {EXPECTED_HEAD}


def test_d118_gear_opens_settings() -> None:
    html = (TEMPLATES / "dashboard.html").read_text(encoding="utf-8")
    assert 'href="/settings"' in html
    assert "dash-greeting-settings" in html


def test_t28_merge_dues_then_one_new_excludes_new_from_goal() -> None:
    constitution = [
        _unit(unit_id="a19", title="Article 19", status="done"),
        _unit(unit_id="a21", title="Article 21", status="upcoming", kind="review"),
    ]
    due = _unit(
        unit_id="ndps:section:8",
        title="Section 8 — NDPS Act",
        kind="review",
        source="playground",
        eyebrow="Day 1 → 3 · Playground",
        cta_label="Start revision →",
    )
    new = _unit(
        unit_id="ndps:section:1",
        title="Section 1 — NDPS Act",
        kind="new",
        source="playground",
        eyebrow="New · Playground",
        cta_label="Learn →",
    )
    merged = merge_today_path(constitution, [due], new)
    assert [row.unit_id for row in merged] == [
        "a19",
        "ndps:section:8",
        "a21",
        "ndps:section:1",
    ]
    assert merged[1].status == "current"
    assert merged[1].source == "playground"
    assert merged[1].eyebrow == "Day 1 → 3 · Playground"
    assert merged[3].kind == "new"
    assert merged[3].status == "upcoming"
    goal = [
        row
        for row in merged
        if not (row.source == "playground" and row.kind == "new")
    ]
    assert len(goal) == 3


def test_t28_d115_d117_http_path_merge_and_due_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "constitution_memorizer.playground.roster.period.playground_today",
        lambda now=None: TODAY,
    )
    monkeypatch.setattr(
        "constitution_memorizer.playground.schedule.playground_today",
        lambda now=None: TODAY,
    )
    client = _authed_client(tmp_path)
    _subscribe(client)
    assert _confirm_add(client, "ndps").status_code == 303
    client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "section": ["1", "8"]},
        follow_redirects=False,
    )
    repo = client.app.state.playground
    _seed_progress(
        repo,
        USER,
        "ndps",
        "ndps:section:8",
        status="review",
        interval_days=1,
        next_revision=TODAY.isoformat(),
        times_completed=1,
        learned_at=TODAY.isoformat(),
    )
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "Law revisions" not in page.text
    assert "data-today-source=\"playground\"" in page.text
    assert "Day 1 → 3 · Playground" in page.text
    assert "New · Playground" in page.text
    assert "Section 8" in page.text
    assert "Section 1" in page.text
    html = page.text
    assert html.find("Day 1 → 3 · Playground") < html.find("New · Playground")
    assert "data-today-path-card" in html
    due_nodes = html.count("data-today-kind=\"review\"")
    new_nodes = html.count("data-today-kind=\"new\"")
    assert due_nodes >= 1
    assert new_nodes == 1


def test_t28_paused_lists_nothing_playground(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "constitution_memorizer.playground.roster.period.playground_today",
        lambda now=None: TODAY,
    )
    client = _authed_client(tmp_path)
    sub = _subscribe(client)
    assert _confirm_add(client, "ndps").status_code == 303
    client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "section": "8"},
        follow_redirects=False,
    )
    _seed_progress(
        client.app.state.playground,
        USER,
        "ndps",
        "ndps:section:8",
        status="review",
        interval_days=1,
        next_revision=TODAY.isoformat(),
        times_completed=1,
    )
    client.app.state.subscriptions.update_subscription_state(
        USER, sub.id, status="paused"
    )
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "data-today-source=\"playground\"" not in page.text
    assert "Day 1 → 3 · Playground" not in page.text


def test_t30_clause_citation_and_playground_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "constitution_memorizer.playground.roster.period.playground_today",
        lambda now=None: TODAY,
    )
    client = _authed_client(tmp_path)
    _subscribe(client)
    assert _confirm_add(client, "ndps").status_code == 303
    client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "unit": "ndps:section:8:clause:a"},
        follow_redirects=False,
    )
    future = TODAY + timedelta(days=5)
    _seed_progress(
        client.app.state.playground,
        USER,
        "ndps",
        "ndps:section:8:clause:a",
        status="review",
        interval_days=7,
        next_revision=future.isoformat(),
        times_completed=3,
    )
    page = client.get(f"/calendar?year={future.year}&month={future.month}")
    assert page.status_code == 200
    assert "§8(a)" in page.text
    assert "· Playground" in page.text


def test_t31_pending_rung_only_and_paused_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "constitution_memorizer.playground.roster.period.playground_today",
        lambda now=None: TODAY,
    )
    client = _authed_client(tmp_path)
    _subscribe(client)
    assert _confirm_add(client, "ndps").status_code == 303
    client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "section": "8"},
        follow_redirects=False,
    )
    overlay = client.app.state.playground
    roster = client.app.state.roster
    _seed_progress(
        overlay,
        USER,
        "ndps",
        "ndps:section:8",
        status="review",
        interval_days=1,
        next_revision=TODAY.isoformat(),
        times_completed=1,
    )
    extra = playground_projection_extra(
        overlay,
        roster,
        USER,
        today=TODAY,
        horizon_days=120,
        entitled=True,
    )
    assert TODAY in extra
    labels = [item.label for items in extra.values() for item in items]
    assert any("Playground" in label and "Day 1" in label for label in labels)
    assert not any("Day 3" in label or "Day 7" in label for label in labels)
    empty = playground_projection_extra(
        overlay,
        roster,
        USER,
        today=TODAY,
        horizon_days=120,
        entitled=False,
    )
    assert empty == {}


def test_t31_extra_merges_and_keeps_description_cap(tmp_path: Path) -> None:
    from constitution_memorizer.progress.scheduler import ReminderEngine

    engine = ReminderEngine.from_paths(tmp_path / "progress.db", MINI_UNITS)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 8, 18))
    today = date(2026, 8, 18)
    extra_items = [
        DayItem(unit_id=f"pg-{i}", label=f"NDPS · §{i} — Day 1 · Playground")
        for i in range(20)
    ]
    projection = build_projection(
        engine, today=today, extra={date(2026, 8, 19): extra_items}
    )
    day = projection[date(2026, 8, 19)]
    assert day.count >= 20
    assert any("Playground" in item.label for item in day.items)
    content = build_event_content(
        day,
        revision_time="20:00",
        session_minutes=30,
        timezone="Asia/Kolkata",
        dashboard_url="https://recall-the-c.in/dashboard",
    )
    assert f"+ {day.count - MAX_DESCRIPTION_ITEMS} more" in content.description


def test_t31_playground_failure_does_not_fail_constitution(tmp_path: Path) -> None:
    from constitution_memorizer.calendar_sync.store import SqliteCalendarStore
    from constitution_memorizer.progress.db import open_progress_db
    from constitution_memorizer.progress.repository import ProgressRepository
    from constitution_memorizer.progress.scheduler import ReminderEngine

    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    engine = ReminderEngine.from_repository(
        repo,
        {
            u.id: u
            for u in __import__(
                "constitution_memorizer.learning.schemas",
                fromlist=["LearningUnitsDocument"],
            ).LearningUnitsDocument.model_validate(
                __import__(
                    "constitution_memorizer.utils.json_io", fromlist=["read_json"]
                ).read_json(MINI_UNITS)
            ).units
        },
        user_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    )
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=date(2026, 8, 18))
    store = SqliteCalendarStore(conn)

    def boom(_engine, _today):
        raise RuntimeError("playground exploded")

    snapshot = _prepare_reconciliation(
        engine, store, date(2026, 8, 18), extra_loader=boom
    )
    assert snapshot.projection
    assert date(2026, 8, 19) in snapshot.projection


def test_t31_mutations_schedule_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list = []

    def fake_sync(request, user_id):
        called.append(user_id)

    monkeypatch.setattr(
        "constitution_memorizer.calendar_sync.routes.schedule_sync", fake_sync
    )
    client = _authed_client(tmp_path)
    _subscribe(client)
    assert _confirm_add(client, "ndps").status_code == 303
    assert called
    called.clear()
    client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "section": "8"},
        follow_redirects=False,
    )
    assert called
    called.clear()
    client.post(
        "/playground/roster/ndps/remove",
        data=_csrf(client),
        follow_redirects=False,
    )
    assert called


def test_t32_missing_schema_does_not_fail_today_or_calendar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _authed_client(tmp_path)
    _subscribe(client)

    def missing(*_a, **_k):
        raise Exception("no such table: user_playground_progress")

    monkeypatch.setattr(client.app.state.playground, "list_due_revisions", missing)
    monkeypatch.setattr(client.app.state.playground, "list_revision_schedule", missing)
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    cal = client.get("/calendar")
    assert cal.status_code == 200
    assert _is_missing_optional_schema(
        Exception("no such table: user_playground_progress")
    )


def test_t32_other_sql_errors_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _authed_client(tmp_path)
    _subscribe(client)

    def boom(*_a, **_k):
        raise Exception("UNIQUE constraint failed")

    monkeypatch.setattr(client.app.state.playground, "list_due_revisions", boom)
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert 'dashboard_state' in page.text or "couldn’t load" in page.text.lower() or "couldn&#39;t load" in page.text.lower() or "We couldn’t load" in page.text or "We couldn't load" in page.text


def test_t33_r6_asset_pins() -> None:
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "styles.css?v=main75" in base
    assert "mobile.css?v=mob96" in base
    assert "playground.css?v=pg17" in base
    assert "playground.js?v=pg8" in base
    dash = (TEMPLATES / "dashboard.html").read_text(encoding="utf-8")
    assert "data-today-source" in dash
    assert "dash-path-card" in dash
    assert "Law revisions" not in dash
    styles = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert "minmax(280px, 380px)" in styles
    assert ".calendar-week-card" in styles
