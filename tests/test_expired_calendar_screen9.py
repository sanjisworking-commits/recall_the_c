"""Expired cohort desktop /calendar Screen 09 (CTA map expired/09-screen).

Authorized: ChatGPT. Authenticated multiuser GET /calendar and week view after
a real Plus subscription, Constitution calendar activity, retained NDPS
Playground schedule, optional study archive, and paid period end. Overlay on
the live Calendar: retained Playground chips stay visible when can_open is
False; due/revision Playground hrefs reconcile through
expired_playground_today_action; scheduled Bare Act hrefs stay. Guest, Free,
Plus Screen 09, halted, pending, paused, phone, Plus 01–11, and Expired 01–08
stay unchanged. No new route. Google Calendar sync is not touched.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.entitlements.models import BLOCK_PAID_PERIOD_ENDED
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.urls import law_path
from constitution_memorizer.playground.view import (
    PLAYGROUND_BILLING_PATH,
    gate_view,
    playground_subscription_card,
)
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.calendar_view import sunday_week_bounds
from constitution_memorizer.web.service import user_today
from constitution_memorizer.web.study_archive import StudyArchive
from tests.test_playground_m8 import _seed_progress
from tests.test_roster_m5a import _confirm_add, _csrf

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
MANAGE = ROOT / "src/constitution_memorizer/web/templates/subscription_manage.html"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
APP = ROOT / "src/constitution_memorizer/web/app.py"
SCHEDULE = ROOT / "src/constitution_memorizer/playground/schedule.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
SYNC = ROOT / "src/constitution_memorizer/calendar_sync"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_GATE = gate_view(reason=BLOCK_PAID_PERIOD_ENDED)
LIVE_HEADING = LIVE_GATE.title
DUE_LOCATOR = "ndps:section:8:clause:a"
SCHEDULED_LOCATOR = "ndps:section:1"
INVENTED = (
    "Study archive",
    "calDesign",
    "Premium",
    "Unlock all",
    "Bhagavad Gita",
    "Resume required",
    "Locked",
    "Your plan expired",
    "Subscription required",
)
INVENTED_MARKUP = INVENTED + ("September 2026", "2 overdue")
PLAYGROUND_CHIP_RE = re.compile(
    r'<a\s+class="calendar-chip ([^"]+)"\s+href="([^"]+)"\s+'
    r'title="([^"]*)"\s+data-cal-source="playground"\s*>([^<]*)</a>',
    re.S,
)
PANEL_PLAYGROUND_RE = re.compile(
    r'<a class="cal-si-unit-row" href="([^"]+)" data-cal-source="playground">'
    r'\s*<span class="cal-si-unit-title">([^<]*)</span>',
    re.S,
)
WEEK_CARD_RE = re.compile(
    r'<a class="calendar-week-card ([^"]*)" href="([^"]+)"[^>]*>\s*'
    r'<span class="calendar-week-card-title">([^<]*)</span>',
    re.S,
)


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _settings() -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None,
        APP_ENV="test",
        MULTIUSER_ENABLED="true",
        AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true",
        SESSION_SECRET="test-secret",
        SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon",
        DATABASE_URL="",
        COOKIE_SECURE="false",
    )


def _mu_app(tmp_path: Path, *, display_name: str = "Sanjay"):
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER,
        email="a@example.com",
        display_name=display_name,
        avatar_url=None,
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        study_materials_dir=tmp_path / "study-materials",
    )


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    assert client.cookies.get(SESSION_COOKIE_NAME)


def _subscribe(
    client: TestClient,
    *,
    tier: str = "plus",
    status: str = "active",
    period_start: datetime = ACTIVE_START,
    period_end: datetime = ACTIVE_END,
) -> None:
    client.app.state.subscriptions.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        billing_period_start=period_start,
        billing_period_end=period_end,
        is_current=True,
    )


def _expire(client: TestClient) -> None:
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None
    client.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        status="expired",
        billing_period_start=EXPIRED_START,
        billing_period_end=EXPIRED_END,
    )


def _engine(client: TestClient) -> ReminderEngine:
    return client.app.state.engine.for_user(USER)


def _pin_playground_today(monkeypatch: pytest.MonkeyPatch, day: date) -> None:
    monkeypatch.setattr(
        "constitution_memorizer.playground.roster.period.playground_today",
        lambda now=None: day,
    )
    monkeypatch.setattr(
        "constitution_memorizer.playground.schedule.playground_today",
        lambda now=None: day,
    )


def _make_due(client: TestClient, unit_ids: list[str], *, as_of: date | None = None) -> None:
    eng = _engine(client)
    today = as_of or user_today(eng)
    for offset, unit_id in enumerate(unit_ids):
        eng.repo.upsert_progress(
            eng.user_id,
            unit_id=unit_id,
            status="review",
            times_completed=1,
            last_completed=today - timedelta(days=1),
            next_revision=today - timedelta(days=len(unit_ids) - offset),
            interval_days=1,
        )
    eng._invalidate_progress_cache()


def _scheduled_on(day: date) -> date:
    _start, end = sunday_week_bounds(day)
    nxt = day + timedelta(days=1)
    if nxt <= end:
        return nxt
    return day + timedelta(days=1)


def _seed_playground(client: TestClient, *, due_on: date, scheduled_on: date) -> None:
    assert _confirm_add(client, "ndps").status_code == 303
    posted = client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "unit": DUE_LOCATOR, "section": "1"},
        follow_redirects=False,
    )
    assert posted.status_code in {200, 303}
    overlay = client.app.state.playground
    _seed_progress(
        overlay,
        USER,
        "ndps",
        DUE_LOCATOR,
        status="review",
        interval_days=1,
        next_revision=due_on.isoformat(),
        times_completed=1,
        learned_at=due_on.isoformat(),
    )
    _seed_progress(
        overlay,
        USER,
        "ndps",
        SCHEDULED_LOCATOR,
        status="review",
        interval_days=7,
        next_revision=scheduled_on.isoformat(),
        times_completed=1,
        learned_at=due_on.isoformat(),
    )


def _seed_study(client: TestClient, *, title: str, studied_on: date) -> dict:
    html = client.get("/calendar").text
    token = html.split('data-study-token="', 1)[1].split('"', 1)[0]
    created = client.post(
        "/api/study-materials",
        data={
            "title": title,
            "studied_on": studied_on.isoformat(),
            "activity": "Studied",
            "notes": "Live notes",
        },
        headers={"X-Study-Token": token},
    )
    assert created.status_code == 200, created.text
    return created.json()


def _seed_canonical(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> tuple[date, date]:
    eng = _engine(client)
    day = user_today(eng)
    _pin_playground_today(monkeypatch, day)
    _make_due(client, ["clause-1"], as_of=day)
    scheduled = _scheduled_on(day)
    _seed_playground(client, due_on=day, scheduled_on=scheduled)
    _seed_study(client, title="Handwritten notes", studied_on=day - timedelta(days=3))
    return day, scheduled


def _plus_then_expire(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> tuple[date, date]:
    _subscribe(client)
    day, scheduled = _seed_canonical(client, monkeypatch)
    _expire(client)
    return day, scheduled


def _header(html: str) -> str:
    return html.split("<header", 1)[-1].split("</header>", 1)[0]


def _grid(html: str) -> str:
    return html.split('class="calendar-grid"', 1)[-1].split("cal-si-panel", 1)[0]


def _live_playground_action(client: TestClient) -> tuple[str, str]:
    snap = client.app.state.entitlement_service.resolve(USER)
    card = playground_subscription_card(snap)
    gate = gate_view(reason=str(snap.playground_block_reason or BLOCK_PAID_PERIOD_ENDED))
    label = (card.cta_label if card.show else "") or gate.cta_label
    href = (card.cta_href if card.show else "") or gate.cta_href
    return label, href


def _playground_chips(html: str) -> list[tuple[str, str, str, str]]:
    grid = _grid(html)
    return [
        (m.group(1), unescape(m.group(2)), unescape(m.group(3)), unescape(m.group(4)))
        for m in PLAYGROUND_CHIP_RE.finditer(grid)
    ]


def _facts(client: TestClient) -> dict:
    snap = client.app.state.entitlement_service.resolve(USER)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    cap = roster.peek_capacity(USER, snap)
    eng = _engine(client)
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    root = getattr(client.app.state, "study_archive_root", None)
    if root is None:
        study = ()
    else:
        archive = StudyArchive(Path(root) / str(USER))
        study = tuple(
            sorted(
                (e["id"], e["title"], e["studied_on"], e["notes"], e["activity"])
                for e in archive.list_all()
            )
        )
    store = getattr(client.app.state, "calendar_store", None)
    if store is None:
        google = None
    else:
        conn = store.get_connection(USER)
        maps = store.list_event_mappings(USER)
        google = (
            None
            if conn is None
            else (
                conn.google_calendar_id,
                conn.sync_status,
                conn.sync_pending,
                conn.refresh_token_sealed,
                conn.last_error,
            ),
            tuple(sorted((m.local_date, m.google_event_id, m.content_hash) for m in maps)),
        )
    return {
        "active": tuple(sorted(i.law_id for i in roster.active_roster_items(USER))),
        "removed": tuple(sorted(i.law_id for i in roster.removed_roster_items(USER))),
        "used": cap.used,
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        ),
        "selection": tuple(
            sorted(s.source_locator for s in overlay.list_selection(USER, "ndps"))
        ),
        "progress": tuple(
            sorted(
                (p.source_locator, p.status, p.times_completed, p.next_revision)
                for p in overlay.list_progress(USER, "ndps")
            )
        ),
        "constitution": tuple(
            sorted(
                (
                    row.learning_unit_id,
                    row.status,
                    row.times_completed,
                    str(row.next_revision),
                    row.interval_days,
                )
                for row in eng.repo.list_all_progress(USER)
            )
        ),
        "subscription": None
        if stored is None
        else (
            stored.id,
            stored.status,
            stored.tier,
            stored.is_current,
            stored.billing_period_end,
        ),
        "study": study,
        "google": google,
        "can_open": snap.can_open_playground,
    }


def test_expired_calendar_reaches_month_with_calendar_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_expire(client, monkeypatch)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert snap.can_open_playground is False
    page = client.get("/calendar")
    assert page.status_code == 200
    html = unescape(page.text)
    header = _header(html)
    assert 'data-expired-calendar="desktop"' in html
    assert 'data-plus-calendar="desktop"' not in html
    assert "data-signed-in-calendar" in html
    assert 'href="/calendar" class="nav-link is-active"' in header
    assert ">Calendar<" in header
    assert LIVE_HEADING in header
    assert "RecallC Plus" not in header
    assert "Free account" not in header
    day = user_today(_engine(client))
    assert f"{day.strftime('%B')} {day.year}" in html
    assert 'role="radiogroup"' in html
    assert 'href="/calendar?view=week' in html
    assert ">Playground<" in html
    assert 'href="/playground"' in html.split("data-cal-continue-recall", 1)[1][:80]


def test_expired_calendar_canonical_month_uses_live_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    day, scheduled = _plus_then_expire(client, monkeypatch)
    _label, recovery = _live_playground_action(client)
    html = unescape(client.get("/calendar").text)
    assert 'data-expired-calendar="desktop"' in html
    assert f"{day.strftime('%B')} {day.year}" in html
    assert "study" in html.lower() and "of yours" in html
    grid = _grid(html)
    assert f'data-date="{day.isoformat()}"' in grid
    assert "is-today" in grid
    assert 'data-cal-source="constitution"' in grid
    assert 'data-cal-source="playground"' in grid
    assert 'data-cal-source="my"' in grid
    assert "Handwritten notes" in html
    assert "Mark revised" in html
    chips = _playground_chips(html)
    assert chips
    kinds = {cls for cls, _href, _title, _label in chips}
    hrefs = {href for _cls, href, _title, _label in chips}
    assert any("is-due" in cls for cls in kinds)
    assert any("is-scheduled" in cls for cls in kinds) or scheduled.month != day.month
    assert recovery in hrefs
    assert law_path("ndps") in hrefs
    for cls, href, title, label in chips:
        assert "Playground" in label or "Playground" in title
        if "is-due" in cls:
            assert href == recovery == PLAYGROUND_BILLING_PATH
            assert "/learn/" not in href
        if "is-scheduled" in cls:
            assert href == law_path("ndps")
            assert "/learn/" not in href
            assert "revision=" not in href
    constitution_href = re.search(
        r'<a[^>]*href="([^"]+)"[^>]*data-cal-source="constitution"',
        html,
    ) or re.search(
        r'data-cal-source="constitution"[^>]*href="([^"]+)"',
        html,
    )
    assert constitution_href
    constitution = unescape(constitution_href.group(1))
    assert "/learn/" in constitution
    assert PLAYGROUND_BILLING_PATH not in constitution
    panel = html.split("data-cal-panel", 1)[1]
    today_marker = f'data-cal-panel-day="{day.isoformat()}"'
    assert today_marker in panel
    today_chunk = panel.split(today_marker, 1)[1].split("data-cal-panel-day=", 1)[0]
    assert recovery in today_chunk
    assert 'data-cal-source="playground"' in today_chunk
    panel_hrefs = [unescape(m.group(1)) for m in PANEL_PLAYGROUND_RE.finditer(panel)]
    assert recovery in panel_hrefs
    assert law_path("ndps") in panel_hrefs
    assert all("/learn/" not in href for href in panel_hrefs)
    continue_chunk = html.split("data-cal-continue-recall", 1)[1][:80]
    assert 'href="/playground"' in continue_chunk
    for phrase in INVENTED:
        assert phrase not in html, phrase


def test_expired_calendar_week_retains_reconciled_playground(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    day, scheduled = _plus_then_expire(client, monkeypatch)
    _label, recovery = _live_playground_action(client)
    week = client.get(f"/calendar?view=week&date={day.isoformat()}")
    assert week.status_code == 200
    week_text = week.text
    html = unescape(week_text)
    assert 'data-expired-calendar="desktop"' in html
    assert "data-calendar-week" in html
    assert 'class="calendar is-week"' in html or " is-week" in html
    assert 'href="/calendar?view=week&amp;date=' in week_text or 'href="/calendar?view=week&date=' in html
    assert 'aria-label="Previous week"' in html
    week_cards = [
        (cls, unescape(href), title)
        for cls, href, title in WEEK_CARD_RE.findall(
            html.split("data-calendar-week", 1)[1]
        )
        if "Playground" in title
    ]
    assert week_cards
    due_cards = [card for card in week_cards if "is-due" in card[0]]
    assert due_cards
    assert all(href == recovery for _cls, href, _title in due_cards)
    scheduled_week = client.get(f"/calendar?view=week&date={scheduled.isoformat()}")
    assert scheduled_week.status_code == 200
    scheduled_html = unescape(scheduled_week.text)
    assert 'data-expired-calendar="desktop"' in scheduled_html
    scheduled_cards = [
        unescape(href)
        for _cls, href, title in WEEK_CARD_RE.findall(
            scheduled_html.split("data-calendar-week", 1)[1]
        )
        if "Playground" in title
    ]
    assert law_path("ndps") in scheduled_cards
    assert all("/learn/" not in href for href in scheduled_cards)


def test_expired_calendar_due_chip_cannot_reach_learning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_expire(client, monkeypatch)
    html = unescape(client.get("/calendar").text)
    _label, recovery = _live_playground_action(client)
    due = [
        href
        for cls, href, _title, _label in _playground_chips(html)
        if "is-due" in cls
    ]
    assert due
    assert set(due) == {recovery}
    billing = client.get(recovery, follow_redirects=False)
    assert billing.status_code == 200
    assert 'data-expired-subscription="desktop"' in billing.text
    learn = client.get(
        "/playground/laws/ndps/sections/8/u/clause:a/learn/read?revision=1",
        follow_redirects=False,
    )
    assert learn.status_code in {200, 303, 403}
    if learn.status_code == 200:
        body = unescape(learn.text)
        assert "data-pg-workspace" not in learn.text
        assert (
            'data-playground-gate="' in learn.text
            or LIVE_HEADING in body
            or "Resume Playground" in body
        )


def test_expired_calendar_interactions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    day, _scheduled = _plus_then_expire(client, monkeypatch)
    html = unescape(client.get("/calendar").text)
    constitution_href = re.search(
        r'<a[^>]*href="([^"]+)"[^>]*data-cal-source="constitution"',
        html,
    ) or re.search(
        r'data-cal-source="constitution"[^>]*href="([^"]+)"',
        html,
    )
    assert constitution_href
    constitution = unescape(constitution_href.group(1))
    opened = client.get(constitution, follow_redirects=False)
    assert opened.status_code in {200, 303}
    location = opened.headers.get("location") or constitution
    assert "/learn/" in location or opened.status_code == 200
    assert PLAYGROUND_BILLING_PATH not in location
    _label, recovery = _live_playground_action(client)
    billing = client.get(recovery)
    assert billing.status_code == 200
    assert 'data-expired-subscription="desktop"' in billing.text
    bare = client.get(law_path("ndps"), follow_redirects=False)
    assert bare.status_code in {200, 303, 403}
    if bare.status_code == 200:
        assert "data-pg-workspace" not in bare.text
        assert "data-pg-picker" not in bare.text
    home = client.get("/playground")
    assert home.status_code == 200
    assert 'data-expired-playground="desktop"' in home.text
    token = html.split('data-study-token="', 1)[1].split('"', 1)[0]
    study_id = re.search(r'data-study-id="([^"]+)"', html)
    assert study_id
    marked = client.post(
        f"/api/study-materials/{study_id.group(1)}/reviews/3",
        data={"done": "true"},
        headers={"X-Study-Token": token},
    )
    assert marked.status_code == 200
    week = client.get(f"/calendar?view=week&date={day.isoformat()}")
    assert week.status_code == 200
    assert "Playground" in week.text
    month = client.get("/calendar")
    assert "Playground" in month.text
    assert 'data-expired-calendar="desktop"' in month.text


def test_expired_calendar_get_is_mutation_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    day, scheduled = _plus_then_expire(client, monkeypatch)
    before = _facts(client)
    assert "ndps" in before["active"]
    assert before["selection"]
    assert before["constitution"]
    assert before["subscription"] is not None
    assert before["study"]
    assert before["can_open"] is False
    page = client.get("/calendar")
    assert page.status_code == 200
    after = _facts(client)
    assert after == before
    week = client.get(f"/calendar?view=week&date={day.isoformat()}")
    assert week.status_code == 200
    assert _facts(client) == before
    again = client.get(f"/calendar?view=week&date={scheduled.isoformat()}")
    assert again.status_code == 200
    assert _facts(client) == before


def test_guest_free_plus_halted_paused_pending_are_not_expired_calendar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest")).get("/calendar").text
    assert 'data-expired-calendar="desktop"' not in guest
    assert LIVE_HEADING not in _header(guest)
    assert "data-signed-in-calendar" not in guest
    assert 'data-cal-source="playground"' not in guest

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/calendar").text
    assert 'data-expired-calendar="desktop"' not in free_html
    assert "data-signed-in-calendar" in free_html
    assert LIVE_HEADING not in _header(free_html)
    assert 'data-cal-source="playground"' not in free_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    _seed_canonical(plus, monkeypatch)
    plus_html = unescape(plus.get("/calendar").text)
    assert 'data-plus-calendar="desktop"' in plus_html
    assert 'data-expired-calendar="desktop"' not in plus_html
    assert "RecallC Plus" in _header(plus_html)
    assert LIVE_HEADING not in _header(plus_html)
    plus_chips = _playground_chips(plus_html)
    assert plus_chips
    plus_hrefs = {href for _cls, href, _title, _label in plus_chips}
    assert any("/playground/" in href for href in plus_hrefs)
    assert PLAYGROUND_BILLING_PATH not in plus_hrefs
    due_plus = [href for cls, href, _title, _label in plus_chips if "is-due" in cls]
    assert due_plus
    assert all("/learn/" in href or "revision=" in href for href in due_plus)

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    _seed_canonical(halted, monkeypatch)
    stored = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )
    halted_html = halted.get("/calendar").text
    assert 'data-expired-calendar="desktop"' not in halted_html
    assert LIVE_HEADING not in _header(halted_html)
    assert 'data-cal-source="playground"' not in halted_html
    halted_snap = halted.app.state.entitlement_service.resolve(USER)
    assert halted_snap.playground_block_reason != BLOCK_PAID_PERIOD_ENDED

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused)
    _seed_canonical(paused, monkeypatch)
    stored_p = paused.app.state.subscriptions.get_current_subscription(USER)
    paused.app.state.subscriptions.update_subscription_state(
        USER, stored_p.id, status="paused"
    )
    paused_html = paused.get("/calendar").text
    assert 'data-expired-calendar="desktop"' not in paused_html
    assert 'data-cal-source="playground"' not in paused_html

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    pending_html = pending.get("/calendar").text
    assert 'data-expired-calendar="desktop"' not in pending_html
    assert LIVE_HEADING not in _header(pending_html)


def test_expired_calendar_marker_uses_shared_predicate() -> None:
    cal = CAL.read_text(encoding="utf-8")
    assert "expired_calendar" in cal
    assert 'data-expired-calendar="desktop"' in cal
    assert 'data-plus-calendar="desktop"' in cal
    assert "data-signed-in-calendar" in cal
    assert PLAYGROUND_BILLING_PATH not in cal
    assert "Resume Playground" not in cal
    assert "View Playground plans" not in cal
    assert "{{ chip.href }}" in cal
    assert 'href="/playground"' in cal
    app = APP.read_text(encoding="utf-8")
    page = app.split("async def calendar_page", 1)[1].split("async def progress_page", 1)[0]
    assert "request_is_expired_subscriber" in page
    assert "request_is_active_plus" in page
    assert '"expired_calendar": expired_calendar' in page
    assert '"plus_calendar": plus_calendar' in page
    assert "reconcile_expired_playground_calendar_chips" in page
    assert "access.can_open or expired_calendar" in page
    assert "def snapshot_is_expired_subscriber" not in page
    assert "def request_is_expired_subscriber" in DEPS.read_text(encoding="utf-8")
    assert "BLOCK_PAID_PERIOD_ENDED" in DEPS.read_text(encoding="utf-8")
    schedule = SCHEDULE.read_text(encoding="utf-8")
    assert "def reconcile_expired_playground_calendar_chips" in schedule
    assert "expired_playground_today_action" in schedule.split(
        "def reconcile_expired_playground_calendar_chips", 1
    )[1]
    assert "gate_view" in schedule
    assert "playground_subscription_card" in schedule
    google = schedule.split("def playground_google_extra", 1)[1]
    assert "if not access.can_open or access.user_id is None" in google
    assert "expired_calendar" not in google
    base = BASE.read_text(encoding="utf-8")
    assert "expired_calendar_chrome" in base
    assert "plus_calendar_chrome" in base
    assert "playground.css?v=pg28" in base
    css = PG_CSS.read_text(encoding="utf-8")
    assert 'data-expired-calendar="desktop"' in css
    assert "expired/09-screen" in css
    assert 'data-plus-calendar="desktop"' in css
    plus_css = css.split("plus/09-screen", 1)[1].split("expired/09-screen", 1)[0]
    expired_css = css.split("expired/09-screen", 1)[1].split("plus/10-screen", 1)[0]
    assert "var(--pg-teal)" in plus_css
    assert "var(--pg-teal)" in expired_css
    assert "#0e7569" not in plus_css
    assert "#0e7569" not in expired_css
    assert "#3a3a38" not in plus_css
    assert "#3a3a38" not in expired_css
    assert '[data-expired-calendar="desktop"]:not(.is-week) .cal-si-desk' in expired_css
    assert "minmax(0, 1fr) 380px" in expired_css
    assert "repeat(7, minmax(0, 1fr))" in expired_css
    for phrase in INVENTED_MARKUP:
        assert phrase not in cal, phrase


def test_plus_screens_and_expired_01_08_untouched() -> None:
    assert 'data-plus-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-expired-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-plus-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-expired-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-plus-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-expired-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-plus-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-expired-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-plus-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-expired-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-plus-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-expired-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-plus-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-expired-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-expired-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-plus-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-plus-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    for path in (
        LANDING,
        BROWSE,
        LAWS,
        BARE,
        ADD,
        HOME,
        MANAGE,
        DASH,
        PROFILE,
        SETTINGS,
        GATE,
    ):
        text = path.read_text(encoding="utf-8")
        assert "data-expired-calendar" not in text
    assert "data-expired-calendar" not in MOBILE.read_text(encoding="utf-8")
    mobile = MOBILE.read_text(encoding="utf-8")
    phone = CAL.read_text(encoding="utf-8").split("revisions-mobile", 1)[1].split(
        "calendar-header", 1
    )[0]
    assert "data-cal-filter" not in phone
    assert "Add task" not in phone
    assert "cal-m-grid" in phone
    phone_cal = mobile.split(
        'body[data-mscreen="revisions"] .calendar-grid,', 1
    )[1].split("}", 1)[0]
    assert "display: none" in phone_cal
    for path in SYNC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "expired_calendar" not in text
        assert "data-expired-calendar" not in text
        assert "reconcile_expired_playground_calendar_chips" not in text


def _serve(app, host: str = "127.0.0.1") -> tuple[int, object]:
    import uvicorn

    sock = socket.socket()
    sock.bind((host, 0))
    port = sock.getsockname()[1]
    sock.close()
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(80):
        probe = socket.socket()
        probe.settimeout(0.1)
        ready = probe.connect_ex((host, port)) == 0
        probe.close()
        if ready:
            break
        time.sleep(0.05)
    else:
        pytest.fail("server did not bind")
    return port, server


def test_expired_phone_calendar_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _plus_then_expire(client, monkeypatch)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    port, _server = _serve(app)
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        context.add_cookies(
            [
                {
                    "name": SESSION_COOKIE_NAME,
                    "value": session,
                    "url": origin,
                    "httpOnly": True,
                    "secure": False,
                    "sameSite": "Lax",
                }
            ]
        )
        page = context.new_page()
        page.goto(f"{origin}/calendar", wait_until="networkidle")
        geo = page.evaluate(
            """() => {
              const marker = document.querySelector('[data-expired-calendar="desktop"]');
              const grid = document.querySelector('.calendar-grid');
              const mobile = document.querySelector('.revisions-mobile .cal-m-grid');
              const filter = document.querySelector('[data-cal-filter]');
              return {
                marker: Boolean(marker),
                gridDisplay: grid && getComputedStyle(grid).display,
                mobileGrid: Boolean(mobile) && getComputedStyle(mobile).display !== 'none',
                filterDisplay: filter && getComputedStyle(filter).display,
                screen: document.body.getAttribute('data-mscreen'),
                plus: Boolean(document.querySelector('[data-plus-calendar="desktop"]')),
              };
            }"""
        )
        browser.close()
    assert geo["marker"] is True
    assert geo["plus"] is False
    assert geo["gridDisplay"] == "none"
    assert geo["mobileGrid"] is True
    assert geo["screen"] == "revisions"


def test_expired_calendar_screen09_1280(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    day, _scheduled = _plus_then_expire(client, monkeypatch)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    _label, recovery = _live_playground_action(client)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "expired_calendar_screen09_1280.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
        context.add_cookies(
            [
                {
                    "name": SESSION_COOKIE_NAME,
                    "value": session,
                    "url": origin,
                    "httpOnly": True,
                    "secure": False,
                    "sameSite": "Lax",
                }
            ]
        )
        page = context.new_page()
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )
        page.goto(f"{origin}/calendar", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const expired = document.querySelector('[data-expired-calendar="desktop"]');
              const plus = document.querySelector('[data-plus-calendar="desktop"]');
              const title = document.querySelector('.calendar-title');
              const summary = document.querySelector('.calendar-summary');
              const month = [...document.querySelectorAll('.calendar-view-btn')].find(
                (el) => (el.textContent || '').trim() === 'Month'
              );
              const week = [...document.querySelectorAll('.calendar-view-btn')].find(
                (el) => (el.textContent || '').trim() === 'Week'
              );
              const filter = document.querySelector('[data-cal-filter]');
              const grid = document.querySelector('.calendar-grid');
              const today = document.querySelector('.calendar-grid .calendar-cell.is-today');
              const selected = document.querySelector('.calendar-grid .calendar-cell.is-selected');
              const panel = document.querySelector('[data-cal-panel]');
              const shown = document.querySelector('[data-cal-panel-day]:not([hidden])');
              const add = document.querySelector('[data-study-add]');
              const status = document.querySelector('.account-menu-btn-status');
              const sources = [...document.querySelectorAll('.calendar-grid [data-cal-source]')].map(
                (el) => el.getAttribute('data-cal-source')
              );
              const dueHref = (document.querySelector(
                '.calendar-grid a.calendar-chip.is-due[data-cal-source="playground"]'
              ) || {}).href || '';
              const scheduledHref = (document.querySelector(
                '.calendar-grid a.calendar-chip.is-scheduled[data-cal-source="playground"]'
              ) || {}).href || '';
              const continueHref = (document.querySelector('[data-cal-continue-recall]') || {}).href || '';
              const desk = document.querySelector('.cal-si-desk');
              const gridBox = grid && grid.getBoundingClientRect();
              const panelBox = panel && panel.getBoundingClientRect();
              const deskStyle = desk && getComputedStyle(desk);
              const gridStyle = grid && getComputedStyle(grid);
              const parseTracks = (value) => (value || '')
                .split(/\\s+/)
                .map((part) => parseFloat(part))
                .filter((n) => Number.isFinite(n));
              const deskTracks = parseTracks(deskStyle && deskStyle.gridTemplateColumns);
              const gridTracks = parseTracks(gridStyle && gridStyle.gridTemplateColumns);
              const dows = [...document.querySelectorAll('.calendar-grid .calendar-dow')];
              const dowWidths = dows.map((el) => el.getBoundingClientRect().width);
              const navActive = document.querySelector('.PrimaryTabs--top .nav-link.is-active');
              const panelVisible = panel && getComputedStyle(panel).display !== 'none';
              return {
                present: Boolean(expired),
                plus: Boolean(plus),
                title: title && title.textContent.trim(),
                summary: summary && summary.textContent.trim(),
                monthChecked: month && month.getAttribute('aria-checked'),
                weekChecked: week && week.getAttribute('aria-checked'),
                weekHref: week && week.getAttribute('href'),
                filterOptions: filter && [...filter.options].map((o) => o.value),
                todayIso: today && today.getAttribute('data-date'),
                selectedIso: selected && selected.getAttribute('data-date'),
                panelIso: shown && shown.getAttribute('data-cal-panel-day'),
                twoCol: Boolean(
                  gridBox && panelBox && panelVisible &&
                  panelBox.left >= gridBox.right - 1
                ),
                deskDisplay: deskStyle && deskStyle.display,
                deskTrackCount: deskTracks.length,
                deskRail: deskTracks[1] || 0,
                gridTrackCount: gridTracks.length,
                gridTrackSpread: gridTracks.length
                  ? Math.max(...gridTracks) - Math.min(...gridTracks)
                  : 99,
                dowCount: dows.length,
                dowSpread: dowWidths.length
                  ? Math.max(...dowWidths) - Math.min(...dowWidths)
                  : 99,
                addPresent: Boolean(add) && getComputedStyle(add).display !== 'none',
                sources,
                dueHref,
                scheduledHref,
                continueHref,
                status: status && status.textContent.trim(),
                statusDisplay: status && getComputedStyle(status).display,
                navActive: navActive && navActive.textContent.replace(/\\s+/g, ' ').trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        context.close()
        browser.close()
    assert geo["present"] is True
    assert geo["plus"] is False
    assert geo["title"]
    assert day.strftime("%B") in (geo["title"] or "")
    assert geo["summary"]
    assert geo["monthChecked"] == "true"
    assert geo["weekChecked"] == "false"
    assert "/calendar?view=week" in (geo["weekHref"] or "")
    assert geo["filterOptions"] == ["all", "constitution", "playground", "my"]
    assert geo["todayIso"] == day.isoformat()
    assert geo["selectedIso"] == geo["todayIso"]
    assert geo["panelIso"] == geo["todayIso"]
    assert geo["twoCol"] is True
    assert geo["deskDisplay"] == "grid"
    assert geo["deskTrackCount"] == 2
    assert abs(geo["deskRail"] - 380) <= 1
    assert geo["gridTrackCount"] == 7
    assert geo["gridTrackSpread"] <= 2
    assert geo["dowCount"] == 7
    assert geo["dowSpread"] <= 2
    assert geo["addPresent"] is True
    assert "constitution" in (geo["sources"] or [])
    assert "playground" in (geo["sources"] or [])
    assert "my" in (geo["sources"] or [])
    assert recovery in (geo["dueHref"] or "")
    assert "/learn/" not in (geo["dueHref"] or "")
    if geo["scheduledHref"]:
        assert law_path("ndps") in (geo["scheduledHref"] or "")
    assert "/playground" in (geo["continueHref"] or "")
    assert geo["status"] == LIVE_HEADING
    assert geo["statusDisplay"] != "none"
    assert "Calendar" in (geo["navActive"] or "")
    assert shot_path.exists() and shot_path.stat().st_size > 1000


def test_expired_calendar_plus_regression_1280(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    day, _scheduled = _seed_canonical(client, monkeypatch)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "expired_calendar_screen09_plus_regression_1280.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
        context.add_cookies(
            [
                {
                    "name": SESSION_COOKIE_NAME,
                    "value": session,
                    "url": origin,
                    "httpOnly": True,
                    "secure": False,
                    "sameSite": "Lax",
                }
            ]
        )
        page = context.new_page()
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )
        page.goto(f"{origin}/calendar", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-calendar="desktop"]');
              const expired = document.querySelector('[data-expired-calendar="desktop"]');
              const status = document.querySelector('.account-menu-btn-status');
              const due = document.querySelector(
                '.calendar-grid a.calendar-chip.is-due[data-cal-source="playground"]'
              );
              const desk = document.querySelector('.cal-si-desk');
              const grid = document.querySelector('.calendar-grid');
              const panel = document.querySelector('[data-cal-panel]');
              const deskStyle = desk && getComputedStyle(desk);
              const gridStyle = grid && getComputedStyle(grid);
              const parseTracks = (value) => (value || '')
                .split(/\\s+/)
                .map((part) => parseFloat(part))
                .filter((n) => Number.isFinite(n));
              const deskTracks = parseTracks(deskStyle && deskStyle.gridTemplateColumns);
              const gridTracks = parseTracks(gridStyle && gridStyle.gridTemplateColumns);
              const gridBox = grid && grid.getBoundingClientRect();
              const panelBox = panel && panel.getBoundingClientRect();
              const panelVisible = panel && getComputedStyle(panel).display !== 'none';
              return {
                plus: Boolean(plus),
                expired: Boolean(expired),
                status: status && status.textContent.trim(),
                dueHref: (due && due.getAttribute('href')) || '',
                deskTrackCount: deskTracks.length,
                deskRail: deskTracks[1] || 0,
                gridTrackCount: gridTracks.length,
                gridTrackSpread: gridTracks.length
                  ? Math.max(...gridTracks) - Math.min(...gridTracks)
                  : 99,
                twoCol: Boolean(
                  gridBox && panelBox && panelVisible &&
                  panelBox.left >= gridBox.right - 1
                ),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        context.close()
        browser.close()
    assert geo["plus"] is True
    assert geo["expired"] is False
    assert geo["status"] == "RecallC Plus"
    assert "/playground/" in (geo["dueHref"] or "")
    assert PLAYGROUND_BILLING_PATH not in (geo["dueHref"] or "")
    assert geo["twoCol"] is True
    assert geo["deskTrackCount"] == 2
    assert abs(geo["deskRail"] - 380) <= 1
    assert geo["gridTrackCount"] == 7
    assert geo["gridTrackSpread"] <= 2
    assert shot_path.exists() and shot_path.stat().st_size > 1000
    assert day.isoformat()
