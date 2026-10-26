"""Phone signed-in Free Calendar Screen 05 (CTA map signedIn/05-screen).

Authorized: ChatGPT. Authenticated Free GET /calendar at 390x844. Desktop
signed-in Calendar Screen 09 is the functional contract. Live Constitution
chips win over the map. Guest phone 05 is parked. No S2-1.
"""

from __future__ import annotations

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

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/partials/playground_add_panel.html"  # M2: panel partial
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
USER = UUID("11111111-1111-4111-8111-111111111111")
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
)
INVENTED = (
    "NDPS",
    "Section 8",
    "Section 9",
    "Article 19(1)(a)",
    "Article 21",
    "Bhagavad Gita",
    "Sunday 6 September",
)
FREE_SEL = (
    "[data-signed-in-calendar]:not([data-plus-calendar])"
    ":not([data-expired-calendar]):not([data-halted-calendar])"
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


def _guest_app(tmp_path: Path):
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
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


def _free_client(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    return client


def _engine(client: TestClient) -> ReminderEngine:
    return client.app.state.engine.for_user(USER)


def _make_due(
    client: TestClient,
    unit_ids: list[str],
    *,
    interval_days: dict[str, int] | None = None,
) -> None:
    eng = _engine(client)
    today = user_today(eng)
    intervals = interval_days or {}
    for offset, unit_id in enumerate(unit_ids):
        days = intervals.get(unit_id, 1)
        eng.repo.upsert_progress(
            eng.user_id,
            unit_id=unit_id,
            status="review",
            times_completed=1,
            last_completed=today - timedelta(days=1),
            next_revision=today - timedelta(days=len(unit_ids) - offset),
            interval_days=days,
        )
    eng._invalidate_progress_cache()


def _phone(html: str) -> str:
    return html.split("revisions-mobile", 1)[1].split("calendar-header", 1)[0]


def _tabs(html: str) -> str:
    return html.split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 1
    )[1].split("</nav>", 1)[0]


def _write_facts(client: TestClient) -> dict:
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    return {
        "subscription": None
        if stored is None
        else (stored.id, stored.status, stored.tier, stored.is_current),
        "roster": tuple(sorted(i.law_id for i in roster.active_roster_items(USER))),
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        ),
    }


def _assert_no_invented(html: str) -> None:
    text = unescape(html)
    today = date.today()
    for phrase in INVENTED:
        if phrase == "Sunday 6 September" and today == date(2026, 9, 6):
            continue
        assert phrase not in text, phrase


def _assert_free_calendar_contract(html: str, *, today: date) -> None:
    assert "data-signed-in-calendar" in html
    assert "data-plus-calendar" not in html
    assert "data-expired-calendar" not in html
    assert "data-halted-calendar" not in html
    assert 'data-mscreen="revisions"' in html
    phone = _phone(html)
    assert "cal-m-grid" in phone
    assert today.strftime("%B %Y") in phone
    assert "data-cal-filter" not in phone
    assert "Add task" not in phone
    if "cal-m-today-continue" in phone:
        assert 'class="cal-m-today-continue" href="/dashboard"' in phone
    assert "cal-m-today-continue" in phone or "Nothing due today" in phone
    assert 'data-cal-source="playground"' not in html
    assert 'data-cal-source="my"' not in html
    assert 'data-today-source="playground"' not in html
    _assert_no_invented(phone)
    assert "1 → 3 → 7 → 15 → 30 → 60" in unescape(phone) or "1 → 3 → 7 → 15 → 30 → 60" in unescape(html)
    tabs = _tabs(html)
    for label_text, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        assert label_text in tabs
    assert 'aria-current="page"' in tabs
    assert ">Calendar<" in tabs
    assert "view=week" not in phone


def test_phone_free_calendar_empty_is_live_constitution_month(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    before = _write_facts(client)
    page = client.get("/calendar")
    assert page.status_code == 200
    assert _write_facts(client) == before
    html = unescape(page.text)
    today = user_today(_engine(client))
    _assert_free_calendar_contract(html, today=today)
    phone = _phone(html)
    assert "Calendar" in phone
    assert f'href="/calendar?year={today.year}&amp;month=' in phone or (
        f'href="/calendar?year={today.year}&month=' in phone
    )
    assert "Nothing due today" in phone
    assert "cal-m-today-continue" not in phone
    gate = client.get("/playground", follow_redirects=False)
    assert gate.status_code == 200
    assert 'data-playground-gate="not_subscribed"' in gate.text


def test_phone_free_calendar_due_uses_constitution_chips_and_learn_hrefs(
    tmp_path: Path,
) -> None:
    client = _free_client(tmp_path)
    _make_due(
        client,
        ["clause-1", "clause-2"],
        interval_days={"clause-1": 15, "clause-2": 1},
    )
    before = _write_facts(client)
    page = client.get("/calendar")
    assert page.status_code == 200
    assert _write_facts(client) == before
    html = unescape(page.text)
    today = user_today(_engine(client))
    _assert_free_calendar_contract(html, today=today)
    phone = _phone(html)
    assert "Article 20" in phone or "Art 20" in phone
    assert 'href="/learn/clause-1"' in phone
    assert 'href="/learn/clause-2"' in phone
    assert "Day 15" in phone
    assert "Continue today’s Recall" in phone or "Continue today's Recall" in phone
    assert 'class="cal-m-today-continue" href="/dashboard"' in phone
    today_card = phone.split("data-today-list", 1)[1].split("data-calendar-gcal-footnote", 1)[0]
    assert "cal-m-today-continue" in today_card
    assert "cal-m-today-continue" not in phone.split("data-today-list", 1)[0]
    assert "data-day-list" in phone
    assert "data-day-empty" in phone
    assert "data-today-list" in phone


def test_phone_free_calendar_month_nav_is_real_get_links(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    html = client.get("/calendar").text
    today = user_today(_engine(client))
    phone = _phone(html)
    prev = client.get(
        f"/calendar?year={today.year}&month={today.month}",
        follow_redirects=False,
    )
    assert prev.status_code == 200
    assert 'aria-label="Previous month"' in phone
    assert 'aria-label="Next month"' in phone
    assert "/calendar?year=" in phone
    assert "view=week" not in phone
    other = (today.replace(day=1) - timedelta(days=1))
    jumped = client.get(f"/calendar?year={other.year}&month={other.month}")
    assert jumped.status_code == 200
    jumped_phone = _phone(jumped.text)
    assert other.strftime("%B %Y") in unescape(jumped_phone)
    assert "cal-m-today-continue" not in jumped_phone


def test_guest_plus_expired_halted_calendar_stay_separate(tmp_path: Path) -> None:
    guest_resp = TestClient(_guest_app(tmp_path / "guest")).get(
        "/calendar", follow_redirects=False
    )
    assert guest_resp.status_code in (302, 303)
    assert "/login" in (guest_resp.headers.get("location") or "")
    assert "data-signed-in-calendar" not in guest_resp.text
    assert "data-plus-calendar" not in guest_resp.text

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get("/calendar").text
    assert "data-signed-in-calendar" in plus_html
    assert 'data-plus-calendar="desktop"' in plus_html
    assert "data-expired-calendar" not in plus_html
    assert "data-halted-calendar" not in plus_html

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(expired)
    stored = expired.app.state.subscriptions.get_current_subscription(USER)
    expired.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        status="expired",
        billing_period_start=datetime(2026, 8, 16, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )
    expired_html = expired.get("/calendar").text
    assert 'data-expired-calendar="desktop"' in expired_html
    assert "data-plus-calendar" not in expired_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    stored_h = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored_h.id, status="halted"
    )
    halted_html = halted.get("/calendar").text
    assert 'data-halted-calendar="desktop"' in halted_html
    assert "data-plus-calendar" not in halted_html


def test_phone_free_calendar_css_is_breakpoint_scoped() -> None:
    mobile = MOBILE.read_text(encoding="utf-8")
    generic, _, rest = mobile.partition("is signedIn/05-screen:")
    assert "data-signed-in-calendar" not in generic
    phone_block = rest.split("/* R1 — Playground phone shell", 1)[0]
    assert "@media (max-width: 560px)" in phone_block
    assert "@media (min-width: 561px)" not in phone_block
    assert FREE_SEL in phone_block.replace("\n", "").replace(" ", "")
    assert ":not([data-plus-calendar])" in phone_block
    assert ":not([data-expired-calendar])" in phone_block
    assert ":not([data-halted-calendar])" in phone_block
    assert "safe-area-inset-bottom" in phone_block
    assert "overflow-x: hidden" in phone_block
    assert "var(--m-tabbar, 60px)" in phone_block
    assert ".mobile-tabbar" in phone_block
    assert "grid-template-columns: repeat(5, 1fr)" in phone_block
    assert "position: fixed" in phone_block
    assert "position: static" in phone_block
    assert ".cal-m-daylist:not([hidden])" in phone_block.replace("\n", "").replace(" ", "") or (
        ".cal-m-daylist" in phone_block and "position: static" in phone_block
    )
    assert "min-width: 44px" in phone_block
    assert "min-height: 44px" in phone_block
    assert ".cal-m-cell.is-selected" in phone_block
    assert ":has(.cal-m-cell.is-selected)" in phone_block.replace("\n", "").replace(" ", "") or (
        ":has(.cal-m-cell.is-selected)" in phone_block
    )
    assert "data-plus-calendar=\"desktop\"] {" not in phone_block
    assert "cal-si-toolbar" not in mobile
    phone_cal = mobile.split(
        'body[data-mscreen="revisions"] .calendar-grid,', 1
    )[1].split("}", 1)[0]
    assert "display: none" in phone_cal

    desk = STYLES.read_text(encoding="utf-8").split(
        "/* Signed-in desktop Calendar", 1
    )[1]
    assert "@media (min-width: 561px)" in desk
    assert "grid-template-columns: minmax(0, 1fr) 380px" in desk
    assert "playground.css?v=pg52" in BASE.read_text(encoding="utf-8")
    assert "styles.css?v=main88" in BASE.read_text(encoding="utf-8")
    assert "mobile.css?v=mob107" in BASE.read_text(encoding="utf-8")
    assert "mobile.css?v=mob104" not in BASE.read_text(encoding="utf-8")
    cal = CAL.read_text(encoding="utf-8")
    assert "data-signed-in-calendar" in cal
    phone = cal.split("revisions-mobile", 1)[1].split("calendar-header", 1)[0]
    assert 'href="/dashboard"' in phone
    assert "data-cal-filter" not in phone
    assert "cal-m-today-continue" in phone
    today_card = phone.split("data-today-list", 1)[1]
    assert "cal-m-today-continue" in today_card
    assert "data-signed-in-calendar" not in ADD.read_text(encoding="utf-8")
    assert "data-signed-in-pg-gate" in GATE.read_text(encoding="utf-8")
    assert "data-signed-in-today" in DASH.read_text(encoding="utf-8")
    first_bar = BASE.read_text(encoding="utf-8").split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 2
    )[2].split("</nav>", 1)[0]
    assert 'href="/calendar"' in first_bar
    assert "path.startswith('/calendar')" in first_bar
    assert "data-plus-bareact-phone-tabs" not in first_bar
    pg = PG_CSS.read_text(encoding="utf-8")
    assert "data-signed-in-calendar" not in pg.split(
        "/* Plus desktop /calendar", 1
    )[0]


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


def _cookie(session: str, origin: str) -> list[dict]:
    return [
        {
            "name": SESSION_COOKIE_NAME,
            "value": session,
            "url": origin,
            "httpOnly": True,
            "secure": False,
            "sameSite": "Lax",
        }
    ]


def test_phone_signed_in_calendar_screen05_empty_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    today = user_today(_engine(client))
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_signed_in_calendar_screen05_empty_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        context.add_cookies(_cookie(session, origin))
        page = context.new_page()
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )
        posts: list[str] = []
        page.on(
            "request",
            lambda req: posts.append(req.url)
            if req.method == "POST"
            else None,
        )
        page.goto(f"{origin}/calendar", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-signed-in-calendar]');
              const header = document.querySelector('.site-header');
              const tabs = document.querySelector('.mobile-tabbar');
              const tabLinks = tabs ? [...tabs.querySelectorAll('a.mobile-tab')] : [];
              const active = tabs && tabs.querySelector('.mobile-tab.is-active');
              const title = document.querySelector('.revisions-title');
              const month = document.querySelector('.revisions-month');
              const grid = document.querySelector('.cal-m-grid');
              const desk = document.querySelector('.calendar-grid');
              const toolbar = document.querySelector('.cal-si-toolbar');
              const mobile = document.querySelector('.revisions-mobile');
              const todayCell = document.querySelector('.cal-m-cell.is-today');
              const selected = document.querySelector('.cal-m-cell.is-selected');
              const continueEl = document.querySelector('.cal-m-today-continue');
              const empty = document.querySelector('[data-today-list] .revisions-empty');
              const navBtn = document.querySelector('.cal-m-nav-btn');
              const tabBox = tabs && tabs.getBoundingClientRect();
              const emptyBox = empty && empty.getBoundingClientRect();
              const navBox = navBtn && navBtn.getBoundingClientRect();
              const cellBox = todayCell && todayCell.getBoundingClientRect();
              return {
                present: Boolean(panel),
                plus: Boolean(document.querySelector('[data-plus-calendar]')),
                title: title && title.textContent.trim(),
                month: month && month.textContent.trim(),
                headerDisplay: header ? getComputedStyle(header).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                tabsPosition: tabs ? getComputedStyle(tabs).position : null,
                tabLabels: tabLinks.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabLinks.map((el) => el.getAttribute('href')),
                calendarActive: active && active.textContent.replace(/\\s+/g, ' ').trim(),
                mobileDisplay: mobile ? getComputedStyle(mobile).display : null,
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                toolbarDisplay: toolbar ? getComputedStyle(toolbar).display : null,
                todayFill: todayCell && getComputedStyle(todayCell).backgroundColor,
                selected: Boolean(selected),
                continuePresent: Boolean(continueEl),
                emptyText: empty && empty.textContent.trim(),
                emptyBottom: emptyBox && emptyBox.bottom,
                tabTop: tabBox && tabBox.top,
                navH: navBox && navBox.height,
                navW: navBox && navBox.width,
                cellH: cellBox && cellBox.height,
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                playgroundRows: document.querySelectorAll(
                  '[data-cal-source="playground"]'
                ).length,
                hasNdps: /NDPS|Section 8|Article 19\\(1\\)\\(a\\)|Article 21/.test(
                  (document.querySelector('.revisions-mobile') || {}).innerText || ''
                ),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["present"] is True
    assert geo["plus"] is False
    assert geo["title"] == "Calendar"
    assert geo["month"] == today.strftime("%B %Y")
    assert geo["headerDisplay"] == "none"
    assert geo["tabsDisplay"] != "none"
    assert geo["tabsPosition"] == "fixed"
    assert geo["tabLabels"] == ["Today", "Browse", "Playground", "Calendar", "Profile"]
    assert geo["tabHrefs"] == [href for _, href in TAB_HREFS]
    assert geo["calendarActive"] == "Calendar"
    assert geo["mobileDisplay"] != "none"
    assert geo["deskDisplay"] == "none"
    assert geo["toolbarDisplay"] == "none"
    assert geo["selected"] is False
    assert geo["continuePresent"] is False
    assert "Nothing due today" in (geo["emptyText"] or "")
    assert geo["emptyBottom"] <= geo["tabTop"] + 8
    assert geo["navH"] >= 44
    assert geo["navW"] >= 44
    assert geo["cellH"] >= 44
    assert geo["overflow"] is False
    assert geo["playgroundRows"] == 0
    assert geo["hasNdps"] is False
    assert not any("study-materials" in url or "calendar-sync" in url for url in posts)
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_signed_in_calendar_screen05_due_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _make_due(
        client,
        ["clause-1", "clause-2"],
        interval_days={"clause-1": 15, "clause-2": 1},
    )
    session = client.cookies.get(SESSION_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_signed_in_calendar_screen05_due_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        context.add_cookies(_cookie(session, origin))
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
              const continueEl = document.querySelector('.cal-m-today-continue');
              const todayList = document.querySelector('[data-today-list]');
              const tabs = document.querySelector('.mobile-tabbar');
              const todayCell = document.querySelector('.cal-m-cell.is-today');
              const rows = [...document.querySelectorAll('[data-today-list] .revisions-row')];
              const continueBox = continueEl && continueEl.getBoundingClientRect();
              const tabBox = tabs && tabs.getBoundingClientRect();
              const todayBg = todayCell && getComputedStyle(todayCell).backgroundColor;
              return {
                continueHref: continueEl && continueEl.getAttribute('href'),
                continueText: continueEl && continueEl.textContent.replace(/\\s+/g, ' ').trim(),
                continueH: continueBox && continueBox.height,
                continueBottom: continueBox && continueBox.bottom,
                tabTop: tabBox && tabBox.top,
                todayListHidden: todayList && todayList.hidden,
                todayFilled: todayBg && todayBg !== 'rgba(0, 0, 0, 0)',
                rowHrefs: rows.map((el) => el.getAttribute('href')),
                rowText: rows.map((el) => el.innerText.replace(/\\s+/g, ' ').trim()),
                playground: document.querySelectorAll('[data-cal-source="playground"]').length,
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        page.set_viewport_size({"width": 390, "height": 700})
        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(80)
        short = page.evaluate(
            """() => {
              const continueEl = document.querySelector('.cal-m-today-continue');
              const tabs = document.querySelector('.mobile-tabbar');
              const cb = continueEl.getBoundingClientRect();
              const tb = tabs.getBoundingClientRect();
              return {
                continueBottom: cb.bottom,
                tabTop: tb.top,
                tabsFixed: getComputedStyle(tabs).position === 'fixed',
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
              };
            }"""
        )
        browser.close()

    assert geo["continueHref"] == "/dashboard"
    assert "Continue" in (geo["continueText"] or "")
    assert geo["continueH"] >= 44
    assert geo["continueBottom"] <= geo["tabTop"] + 8
    assert geo["todayListHidden"] is False
    assert geo["todayFilled"] is True
    assert any("/learn/" in (href or "") for href in geo["rowHrefs"])
    assert any("20" in text for text in geo["rowText"])
    assert any("Day 15" in text for text in geo["rowText"])
    assert geo["playground"] == 0
    assert geo["overflow"] is False
    assert short["tabsFixed"] is True
    assert short["continueBottom"] <= short["tabTop"] + 8
    assert short["overflow"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_signed_in_calendar_screen05_selected_day_390x844(
    tmp_path: Path,
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _make_due(
        client,
        ["clause-1", "clause-2"],
        interval_days={"clause-1": 15, "clause-2": 1},
    )
    session = client.cookies.get(SESSION_COOKIE_NAME)
    today = user_today(_engine(client))
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_signed_in_calendar_screen05_selected_day_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        context.add_cookies(_cookie(session, origin))
        page = context.new_page()
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )
        page.goto(f"{origin}/calendar", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        other_iso = page.evaluate(
            """(today) => {
              const cells = [...document.querySelectorAll('.cal-m-cell[data-date]')];
              const hit = cells.find((c) => c.getAttribute('data-date') !== today);
              return hit ? hit.getAttribute('data-date') : today;
            }""",
            today.isoformat(),
        )
        page.locator(f'.cal-m-cell[data-date="{other_iso}"]').first.click()
        page.wait_for_timeout(200)
        geo = page.evaluate(
            """(today) => {
              const selected = document.querySelector('.cal-m-cell.is-selected');
              const todayCell = document.querySelector('.cal-m-cell.is-today');
              const list = document.querySelector('.cal-m-daylist:not([hidden])');
              const todayList = document.querySelector('[data-today-list]');
              const continueEl = document.querySelector('.cal-m-today-continue');
              const selBg = selected && getComputedStyle(selected).backgroundColor;
              const todayBg = todayCell && getComputedStyle(todayCell).backgroundColor;
              const selBorder = selected && getComputedStyle(selected).borderTopWidth;
              const todayBorder = todayCell && getComputedStyle(todayCell).borderTopWidth;
              return {
                selectedIso: selected && selected.getAttribute('data-date'),
                todayIso: todayCell && todayCell.getAttribute('data-date'),
                selectedFilled: selBg && selBg !== 'rgba(0, 0, 0, 0)',
                todayDifferent: selBg !== todayBg,
                todayBorderPx: todayBorder ? parseFloat(todayBorder) : 0,
                selectedBorderPx: selBorder ? parseFloat(selBorder) : 0,
                listPosition: list ? getComputedStyle(list).position : null,
                listHidden: list ? list.hidden : null,
                listKind: list && (list.hasAttribute('data-day-empty')
                  ? 'empty' : list.getAttribute('data-day-list')),
                todayHidden: todayList && todayList.hidden,
                continueDisplay: continueEl ? getComputedStyle(continueEl).display : null,
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
              };
            }""",
            today.isoformat(),
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        page.locator(f'.cal-m-cell[data-date="{other_iso}"]').first.click()
        page.wait_for_timeout(200)
        cleared = page.evaluate(
            """() => {
              const selected = document.querySelector('.cal-m-cell.is-selected');
              const todayCell = document.querySelector('.cal-m-cell.is-today');
              const todayList = document.querySelector('[data-today-list]');
              const list = document.querySelector('.cal-m-daylist:not([hidden])');
              const todayBg = todayCell && getComputedStyle(todayCell).backgroundColor;
              return {
                selected: Boolean(selected),
                todayHidden: todayList && todayList.hidden,
                listOpen: Boolean(list),
                todayFilled: todayBg && todayBg !== 'rgba(0, 0, 0, 0)',
              };
            }"""
        )
        browser.close()

    assert geo["selectedIso"] == other_iso
    assert geo["todayIso"] == today.isoformat()
    assert geo["selectedFilled"] is True
    if other_iso != today.isoformat():
        assert geo["todayDifferent"] is True
        assert geo["todayBorderPx"] >= 2
        assert geo["todayHidden"] is True
    assert geo["listPosition"] in ("static", "relative")
    assert geo["listHidden"] is False
    assert geo["listKind"] in {other_iso, "empty"}
    assert geo["overflow"] is False
    assert cleared["selected"] is False
    assert cleared["todayHidden"] is False
    assert cleared["listOpen"] is False
    assert cleared["todayFilled"] is True
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_signed_in_calendar_screen05_desktop_regression_1280(
    tmp_path: Path,
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _make_due(client, ["clause-1", "clause-2"])
    session = client.cookies.get(SESSION_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = (
        artifact_dir / "phone_signed_in_calendar_screen05_desktop_regression_1280.png"
    )
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
        context.add_cookies(_cookie(session, origin))
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
              const panel = document.querySelector('[data-signed-in-calendar]');
              const tabs = document.querySelector('.mobile-tabbar');
              const header = document.querySelector('.site-header');
              const mobile = document.querySelector('.revisions-mobile');
              const grid = document.querySelector('.calendar-grid');
              const toolbar = document.querySelector('.cal-si-toolbar');
              const side = document.querySelector('[data-cal-panel]');
              const recall = document.querySelector('[data-cal-continue-recall]');
              const week = [...document.querySelectorAll('.calendar-view-btn')].find(
                (el) => (el.textContent || '').trim() === 'Week'
              );
              const titleBox = grid && grid.getBoundingClientRect();
              const sideBox = side && side.getBoundingClientRect();
              return {
                present: Boolean(panel),
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                mobileDisplay: mobile ? getComputedStyle(mobile).display : null,
                gridDisplay: grid ? getComputedStyle(grid).display : null,
                toolbarDisplay: toolbar ? getComputedStyle(toolbar).display : null,
                twoCol: Boolean(
                  titleBox && sideBox && sideBox.left > titleBox.right - 8
                ),
                continueHref: recall && recall.getAttribute('href'),
                weekHref: week && week.getAttribute('href'),
                hasNdps: /NDPS|Section 8|Bhagavad Gita/.test(document.body.innerText || ''),
                playgroundChips: document.querySelectorAll(
                  '[data-cal-source="playground"]'
                ).length,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        page.locator("[data-cal-continue-recall]").click()
        page.wait_for_url("**/playground**", timeout=8000)
        recall_path = page.evaluate("() => location.pathname")
        recall_html = page.content()
        browser.close()

    assert geo["present"] is True
    assert geo["tabsDisplay"] == "none"
    assert geo["headerDisplay"] != "none"
    assert geo["mobileDisplay"] == "none"
    assert geo["gridDisplay"] != "none"
    assert geo["toolbarDisplay"] != "none"
    assert geo["twoCol"] is True
    assert geo["continueHref"] == "/playground"
    assert geo["weekHref"] and "view=week" in geo["weekHref"]
    assert geo["hasNdps"] is False
    assert geo["playgroundChips"] == 0
    assert recall_path.rstrip("/") == "/playground"
    assert 'data-playground-gate="not_subscribed"' in recall_html
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
