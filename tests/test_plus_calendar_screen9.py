"""Plus cohort desktop /calendar month-view Screen 09 (CTA map plus/09-screen).

Authorized: ChatGPT. Authenticated multiuser GET /calendar with a real
active Plus EntitlementSnapshot. Live calendar.days, study_by_day, and
study_overdue. Guest, Free, Pro, phone, week view, and Plus Screens 01–08
stay on their own wrappers. Google Calendar sync is not touched.
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
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.service import user_today
from tests.test_playground_m8 import _seed_progress
from tests.test_roster_m5a import _confirm_add, _csrf

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
APP = ROOT / "src/constitution_memorizer/web/app.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
MANAGE = ROOT / "src/constitution_memorizer/web/templates/subscription_manage.html"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
SYNC = ROOT / "src/constitution_memorizer/calendar_sync"
USER = UUID("11111111-1111-4111-8111-111111111111")
INVENTED = (
    "Study archive",
    "calDesign",
    "Premium",
    "Unlock all",
    "Bhagavad Gita",
)
INVENTED_MARKUP = INVENTED + ("September 2026", "2 overdue")


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
) -> None:
    client.app.state.subscriptions.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        billing_period_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 10, 15, tzinfo=timezone.utc),
        is_current=True,
    )


def _plus_client(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    return client


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


def _seed_playground_due(client: TestClient, *, day: date) -> None:
    assert _confirm_add(client, "ndps").status_code == 303
    locator = "ndps:section:8:clause:a"
    posted = client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "unit": locator},
        follow_redirects=False,
    )
    assert posted.status_code in {200, 303}
    _seed_progress(
        client.app.state.playground,
        USER,
        "ndps",
        locator,
        status="review",
        interval_days=1,
        next_revision=day.isoformat(),
        times_completed=1,
        learned_at=day.isoformat(),
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


def _header(html: str) -> str:
    return html.split("<header", 1)[-1].split("</header>", 1)[0]


def _grid(html: str) -> str:
    return html.split('class="calendar-grid"', 1)[-1].split("cal-si-panel", 1)[0]


def test_plus_calendar_reaches_month_with_calendar_selected(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    page = client.get("/calendar")
    assert page.status_code == 200
    html = page.text
    header = _header(html)
    assert 'data-plus-calendar="desktop"' in html
    assert "data-signed-in-calendar" in html
    assert 'href="/calendar" class="nav-link is-active"' in header
    assert ">Calendar<" in header
    assert "RecallC Plus" in header
    assert "Free account" not in header
    today = date.today()
    assert today.strftime("%B %Y") in html
    assert 'role="radiogroup"' in html
    assert 'role="radio"' in html
    assert 'aria-checked="true"' in html
    assert 'href="/calendar?year=' in html
    assert 'href="/calendar?view=week' in html
    assert 'href="/calendar">Today<' in html or 'href="/calendar">Today</a>' in html
    assert ">All<" in html
    assert ">Constitution<" in html
    assert ">Playground<" in html
    assert ">My material<" in html
    assert "Add task" in html
    assert 'data-study-token="' in html
    assert 'href="/playground"' in html.split("data-cal-continue-recall", 1)[1][:80]
    assert "Continue today’s Recall" in html or "Continue today's Recall" in html
    for phrase in INVENTED:
        assert phrase not in html, phrase


def test_plus_calendar_canonical_month_uses_live_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _plus_client(tmp_path)
    day = user_today(_engine(client))
    _pin_playground_today(monkeypatch, day)
    _make_due(client, ["clause-1"], as_of=day)
    _seed_playground_due(client, day=day)
    _seed_study(client, title="Handwritten notes", studied_on=day - timedelta(days=3))
    _seed_study(client, title="Older notes", studied_on=day - timedelta(days=10))
    html = unescape(client.get("/calendar").text)
    assert 'data-plus-calendar="desktop"' in html
    assert f"{day.strftime('%B')} {day.year}" in html
    assert "study" in html.lower() and "of yours" in html
    grid = _grid(html)
    assert f'data-date="{day.isoformat()}"' in grid
    assert "is-today" in grid
    assert 'data-cal-source="constitution"' in grid
    assert 'data-cal-source="playground"' in grid
    assert 'data-cal-source="my"' in grid
    assert "Handwritten notes" in html
    assert "Older notes" in html
    assert "data-cal-overdue" in html
    assert "overdue revision" in html
    assert "{{ study_overdue|length }}" in CAL.read_text(encoding="utf-8")
    assert "Mark revised" in html
    assert "Undo" in html or "data-study-undo" in html
    assert 'data-cal-source="playground"' in html
    playground_href = re.search(
        r'<a[^>]*href="([^"]+)"[^>]*data-cal-source="playground"',
        html,
    ) or re.search(
        r'data-cal-source="playground"[^>]*href="([^"]+)"',
        html,
    )
    assert playground_href
    assert "/playground/" in unescape(playground_href.group(1))
    constitution_href = re.search(
        r'<a[^>]*href="([^"]+)"[^>]*data-cal-source="constitution"',
        html,
    ) or re.search(
        r'data-cal-source="constitution"[^>]*href="([^"]+)"',
        html,
    )
    assert constitution_href
    assert "/playground/" not in unescape(constitution_href.group(1))
    assert "/learn/" in unescape(constitution_href.group(1))
    panel = html.split('data-cal-panel', 1)[1]
    today_panel = re.search(
        rf'data-cal-panel-day="{day.isoformat()}"[^>]*>.*?</div>',
        panel,
        re.S,
    )
    assert today_panel
    assert "item" in today_panel.group(0).lower()
    week = client.get("/calendar?view=week")
    assert week.status_code == 200
    week_html = week.text
    assert "data-calendar-week" in week_html
    assert 'data-plus-calendar="desktop"' in week_html
    assert 'class="calendar is-week"' in week_html or " is-week" in week_html
    assert 'href="/calendar?view=week&amp;date=' in week_html
    assert 'aria-label="Previous week"' in week_html
    assert 'aria-label="Next week"' in week_html


def test_guest_free_pro_calendar_are_not_plus_screen_09(tmp_path: Path) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest")).get("/calendar").text
    assert 'data-plus-calendar="desktop"' not in guest
    assert "RecallC Plus" not in _header(guest)
    assert "data-signed-in-calendar" not in guest
    assert "Add task" not in guest

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/calendar").text
    assert 'data-plus-calendar="desktop"' not in free_html
    assert "data-signed-in-calendar" in free_html
    assert "RecallC Plus" not in _header(free_html)

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/calendar").text
    assert 'data-plus-calendar="desktop"' not in pro_html
    assert "RecallC Plus" not in _header(pro_html)


def test_plus_calendar_markup_preserves_routes_and_study_gates() -> None:
    cal = CAL.read_text(encoding="utf-8")
    assert "plus_calendar" in cal
    assert 'data-plus-calendar="desktop"' in cal
    assert "data-signed-in-calendar" in cal
    assert 'role="radio"' in cal
    assert "aria-checked" in cal
    assert 'href="/calendar?view=week' in cal
    assert 'href="/calendar">Today</a>' in cal or 'href="/calendar">Today<' in cal
    assert 'href="/calendar?year={{ calendar.prev_year }}' in cal
    assert ">All<" in cal
    assert ">Constitution<" in cal
    assert ">Playground<" in cal
    assert ">My material<" in cal
    assert "{% if study_token|default('') %}" in cal
    assert "Add task" in cal
    assert 'href="/playground"' in cal
    assert "Continue today’s Recall" in cal or "Continue today's Recall" in cal
    assert "Mark revised" in cal
    assert "data-study-undo" in cal
    assert "study_overdue" in cal
    assert "study_by_day" in cal
    assert "{{ calendar.title }}" in cal
    assert "{{ calendar.summary }}" in cal
    for phrase in INVENTED_MARKUP:
        assert phrase not in cal, phrase
    app = APP.read_text(encoding="utf-8")
    assert "request_is_active_plus" in app
    assert '"plus_calendar": plus_calendar' in app
    assert "def request_is_active_plus" in DEPS.read_text(encoding="utf-8")
    assert 'snapshot.tier == "plus"' in DEPS.read_text(encoding="utf-8")
    base = BASE.read_text(encoding="utf-8")
    assert "plus_calendar_chrome" in base
    assert "RecallC Plus" in base
    assert "playground.css?v=pg27" in base
    css = PG_CSS.read_text(encoding="utf-8")
    assert 'data-plus-calendar="desktop"' in css
    plus_css = css.split("plus/09-screen", 1)[-1]
    assert "var(--pg-teal)" in plus_css
    assert "#0e7569" not in plus_css
    assert "#3a3a38" not in plus_css
    assert '[data-plus-calendar="desktop"]:not(.is-week) .cal-si-desk' in plus_css
    assert "minmax(0, 1fr) 380px" in plus_css
    assert '[data-plus-calendar="desktop"]:not(.is-week) .calendar-grid' in plus_css
    assert "repeat(7, minmax(0, 1fr))" in plus_css
    js = (ROOT / "src/constitution_memorizer/web/static/calendar-signed.js").read_text(
        encoding="utf-8"
    )
    assert "is-selected" in js
    assert "data-cal-panel-day" in js


def test_plus_calendar_does_not_touch_accepted_screens_or_sync() -> None:
    assert "data-plus-calendar" not in LANDING.read_text(encoding="utf-8")
    assert "data-plus-calendar" not in BROWSE.read_text(encoding="utf-8")
    assert "data-plus-calendar" not in LAWS.read_text(encoding="utf-8")
    assert "data-plus-calendar" not in BARE.read_text(encoding="utf-8")
    assert "data-plus-calendar" not in ADD.read_text(encoding="utf-8")
    assert "data-plus-calendar" not in HOME.read_text(encoding="utf-8")
    assert "data-plus-calendar" not in GATE.read_text(encoding="utf-8")
    assert "data-plus-calendar" not in MANAGE.read_text(encoding="utf-8")
    assert "data-plus-calendar" not in DASH.read_text(encoding="utf-8")
    assert 'data-plus-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-plus-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-plus-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-plus-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-plus-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-plus-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-plus-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in DASH.read_text(encoding="utf-8")
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-plus-calendar" not in mobile
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
        assert "plus_calendar" not in text
        assert "data-plus-calendar" not in text


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


def test_plus_calendar_1280(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    day = user_today(_engine(client))
    _pin_playground_today(monkeypatch, day)
    _make_due(client, ["clause-1"], as_of=day)
    _seed_playground_due(client, day=day)
    _seed_study(client, title="Handwritten notes", studied_on=day - timedelta(days=3))
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "plus_calendar_screen09_1280.png"
    week_path = artifact_dir / "plus_calendar_screen09_week_1280.png"
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
              const cells = [...document.querySelectorAll('.calendar-grid .calendar-cell')];
              const satCells = cells.filter((_, i) => i % 7 === 6);
              const satChips = satCells.flatMap((cell) => [...cell.querySelectorAll('.calendar-chip')]);
              const satRights = [
                dows[6] && dows[6].getBoundingClientRect().right,
                ...satCells.map((cell) => cell.getBoundingClientRect().right),
                ...satChips.map((chip) => chip.getBoundingClientRect().right),
              ].filter((n) => typeof n === 'number');
              const chipRights = [...document.querySelectorAll('.calendar-grid .calendar-chip')]
                .map((chip) => chip.getBoundingClientRect().right);
              const dowWidths = dows.map((el) => el.getBoundingClientRect().width);
              const navActive = document.querySelector('.PrimaryTabs--top .nav-link.is-active');
              const panelVisible = panel && getComputedStyle(panel).display !== 'none';
              const satMaxRight = satRights.length ? Math.max(...satRights) : 0;
              const chipMaxRight = chipRights.length ? Math.max(...chipRights) : 0;
              return {
                present: Boolean(plus),
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
                satClear: Boolean(panelBox && panelVisible && satMaxRight <= panelBox.left + 1),
                chipsClear: Boolean(panelBox && panelVisible && chipMaxRight <= panelBox.left + 1),
                addPresent: Boolean(add) && getComputedStyle(add).display !== 'none',
                sources,
                status: status && status.textContent.trim(),
                statusDisplay: status && getComputedStyle(status).display,
                navActive: navActive && navActive.textContent.replace(/\\s+/g, ' ').trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        assert geo["present"] is True
        assert geo["title"]
        assert date.today().strftime("%B") in (geo["title"] or "")
        assert geo["summary"]
        assert geo["monthChecked"] == "true"
        assert geo["weekChecked"] == "false"
        assert "/calendar?view=week" in (geo["weekHref"] or "")
        assert geo["filterOptions"] == ["all", "constitution", "playground", "my"]
        assert geo["todayIso"] == date.today().isoformat()
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
        assert geo["satClear"] is True
        assert geo["chipsClear"] is True
        assert geo["addPresent"] is True
        assert "constitution" in (geo["sources"] or [])
        assert "playground" in (geo["sources"] or [])
        assert "my" in (geo["sources"] or [])
        assert geo["status"] == "RecallC Plus"
        assert geo["statusDisplay"] != "none"
        assert "Calendar" in (geo["navActive"] or "")
        assert shot_path.exists() and shot_path.stat().st_size > 1000

        page.set_viewport_size({"width": 390, "height": 844})
        phone = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-calendar="desktop"]');
              const grid = document.querySelector('.calendar-grid');
              const mobile = document.querySelector('.revisions-mobile .cal-m-grid');
              return {
                plusDisplay: plus && getComputedStyle(plus).display,
                gridDisplay: grid && getComputedStyle(grid).display,
                mobileGrid: Boolean(mobile) && getComputedStyle(mobile).display !== 'none',
                screen: document.body.getAttribute('data-mscreen'),
              };
            }"""
        )
        assert phone["plusDisplay"] != "none"
        assert phone["gridDisplay"] == "none"
        assert phone["mobileGrid"] is True
        assert phone["screen"] == "revisions"

        page.set_viewport_size({"width": 1280, "height": 800})
        page.goto(f"{origin}/calendar?view=week", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        week_geo = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-calendar="desktop"]');
              const week = document.querySelector('[data-calendar-week]');
              const monthGrid = document.querySelector('.calendar-grid');
              const panel = document.querySelector('[data-cal-panel]');
              const prev = document.querySelector('[aria-label="Previous week"]');
              const nxt = document.querySelector('[aria-label="Next week"]');
              const on = [...document.querySelectorAll('.calendar-view-btn')].find(
                (el) => (el.textContent || '').trim() === 'Week'
              );
              return {
                present: Boolean(plus),
                week: Boolean(week) && getComputedStyle(week).display !== 'none',
                monthHidden: !monthGrid || getComputedStyle(monthGrid).display === 'none',
                panelHidden: !panel || getComputedStyle(panel).display === 'none',
                prevHref: prev && prev.getAttribute('href'),
                nextHref: nxt && nxt.getAttribute('href'),
                weekOn: on && on.getAttribute('aria-checked'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(week_path), full_page=False)
        assert week_geo["present"] is True
        assert week_geo["week"] is True
        assert week_geo["monthHidden"] is True
        assert week_geo["panelHidden"] is True
        assert "/calendar?view=week" in (week_geo["prevHref"] or "")
        assert "/calendar?view=week" in (week_geo["nextHref"] or "")
        assert week_geo["weekOn"] == "true"
        assert week_path.exists() and week_path.stat().st_size > 1000
        context.close()
        browser.close()
