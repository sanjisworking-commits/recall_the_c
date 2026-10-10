"""Phone signed-in Free Today Screen 04 (CTA map signedIn/04-screen).

Authorized: ChatGPT. Authenticated Free GET /dashboard at 390x844. Desktop
signed-in Today Screen 08 is the functional contract. Live Constitution
progress wins over the map. Guest phone 04 is parked. No S2-1.
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
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
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
    "Sunday 6 September",
)
FREE_SEL = (
    "[data-signed-in-today]:not([data-plus-today])"
    ":not([data-expired-today]):not([data-halted-today])"
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


def _tabs(html: str) -> str:
    return html.split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 1
    )[1].split("</nav>", 1)[0]


def _path_card(html: str) -> str:
    if "data-today-path-card" not in html:
        return ""
    return html.split("data-today-path-card", 1)[1].split("</ol>", 1)[0]


def _greeting(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _dash_facts(client: TestClient) -> dict:
    eng = _engine(client)
    today = user_today(eng)
    sessions = eng.repo.study_sessions_for_day(USER, today)
    serialized = tuple(
        (
            kind,
            None
            if sess is None
            else (
                sess.id,
                sess.status,
                sess.remaining,
                tuple(i.learning_unit_id for i in sess.items),
            ),
        )
        for kind, sess in sorted(sessions.items())
    )
    progress = tuple(
        (
            row.learning_unit_id,
            row.status,
            str(row.next_revision),
            row.interval_days,
        )
        for row in sorted(
            eng.list_all_progress(), key=lambda r: r.learning_unit_id
        )
    )
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    return {
        "sessions": serialized,
        "progress": progress,
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


def test_phone_free_today_firstrun_is_live_constitution_onboarding(
    tmp_path: Path,
) -> None:
    client = _free_client(tmp_path)
    page = client.get("/dashboard")
    assert page.status_code == 200
    html = unescape(page.text)
    assert "data-signed-in-today" in html
    assert "data-plus-today" not in html
    assert "data-expired-today" not in html
    assert "data-halted-today" not in html
    assert 'data-today-mode="firstrun"' in html
    assert "Welcome, Sanjay." in html
    today = user_today(_engine(client))
    label = f"{today.strftime('%A')} {today.day} {today.strftime('%B')}"
    assert label in html
    assert 'data-today-date' in html
    assert "Learn your first Article" in html
    assert 'href="/browse"' in html
    assert "/revision/start" not in html
    assert 'data-today-source="playground"' not in html
    assert 'class="dash-avatar-link" href="/settings"' in html
    assert 'class="mobile-icon-btn dash-greeting-settings" href="/settings"' in html
    _assert_no_invented(html)
    tabs = _tabs(html)
    for label_text, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        assert label_text in tabs
    assert 'aria-current="page"' in tabs
    assert ">Today<" in tabs
    greeting = _greeting(html)
    assert "data-theme-pref" not in greeting
    assert "sun" not in greeting.lower()


def test_phone_free_today_revision_uses_constitution_dues_and_live_cta(
    tmp_path: Path,
) -> None:
    client = _free_client(tmp_path)
    _make_due(
        client,
        ["clause-1", "clause-2"],
        interval_days={"clause-1": 15, "clause-2": 1},
    )
    html = unescape(client.get("/dashboard").text)
    assert 'data-today-mode="revision"' in html
    assert 'action="/revision/start"' in html
    assert "data-revision-start" in html
    assert "Start revision →" in html
    assert "Welcome, Sanjay." not in html
    assert "Good morning, Sanjay." in html
    today = user_today(_engine(client))
    label = f"{today.strftime('%A')} {today.day} {today.strftime('%B')}"
    assert label in html
    path = _path_card(html)
    assert 'data-today-unit="clause-1"' in path
    assert 'data-today-unit="clause-2"' in path
    assert 'data-today-source="constitution"' in path
    assert 'data-today-source="playground"' not in html
    assert "Day 15 revision" in path
    assert "Start revision →" in path
    assert 'href="/learn/' in path
    _assert_no_invented(html)
    assert "revisions due" in html.lower()
    assert ">2</span>" in html or ">2<" in html


def test_phone_free_today_learning_empty_does_not_fabricate_dues(
    tmp_path: Path,
) -> None:
    client = _free_client(tmp_path)
    eng = _engine(client)
    today = user_today(eng)
    eng.repo.upsert_progress(
        USER,
        unit_id="clause-1",
        status="review",
        times_completed=1,
        last_completed=today,
        next_revision=today + timedelta(days=15),
        interval_days=15,
    )
    eng._invalidate_progress_cache()
    html = unescape(client.get("/dashboard").text)
    assert 'data-today-mode="firstrun"' not in html
    assert 'data-today-mode="revision"' not in html
    assert "/revision/start" not in html
    assert 'data-today-source="playground"' not in html
    _assert_no_invented(html)


def test_phone_free_today_destinations_and_get_is_mutation_free(
    tmp_path: Path,
) -> None:
    client = _free_client(tmp_path)
    _make_due(client, ["clause-1"])
    before = _dash_facts(client)
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert _dash_facts(client) == before
    html = page.text
    assert 'action="/revision/start"' in html
    assert 'class="dash-avatar-link" href="/settings"' in html
    tabs = _tabs(html)
    assert 'href="/playground"' in tabs
    assert 'href="/calendar"' in tabs
    assert 'href="/profile"' in tabs
    gate = client.get("/playground", follow_redirects=False)
    assert gate.status_code == 200
    assert 'data-playground-gate="not_subscribed"' in gate.text
    assert "data-signed-in-pg-gate" in gate.text
    settings = client.get("/settings", follow_redirects=False)
    assert settings.status_code == 200
    started = client.post("/revision/start", follow_redirects=False)
    assert started.status_code in (302, 303)
    assert "/learn/" in (started.headers.get("location") or "")
    assert _dash_facts(client) != before


def test_guest_plus_expired_halted_today_stay_separate(tmp_path: Path) -> None:
    guest = TestClient(_guest_app(tmp_path / "guest")).get("/dashboard").text
    assert "data-signed-in-today" not in guest
    assert "Welcome." in guest
    assert "Good morning, Sanjay." not in guest
    assert 'data-today-mode="firstrun"' in guest

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get("/dashboard").text
    assert "data-signed-in-today" in plus_html
    assert 'data-plus-today="desktop"' in plus_html
    assert "data-expired-today" not in plus_html
    assert "data-halted-today" not in plus_html

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
    expired_html = expired.get("/dashboard").text
    assert 'data-expired-today="desktop"' in expired_html
    assert "data-plus-today" not in expired_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    stored_h = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored_h.id, status="halted"
    )
    halted_html = halted.get("/dashboard").text
    assert 'data-halted-today="desktop"' in halted_html
    assert "data-plus-today" not in halted_html


def test_phone_free_today_css_is_breakpoint_scoped() -> None:
    mobile = MOBILE.read_text(encoding="utf-8")
    generic, _, rest = mobile.partition("is signedIn/04-screen:")
    assert "data-signed-in-today" not in generic
    phone_block = rest.split("/* R1 — Playground phone shell", 1)[0]
    assert "@media (max-width: 560px)" in phone_block
    assert "@media (min-width: 561px)" not in phone_block
    assert FREE_SEL in phone_block.replace("\n", "").replace(" ", "")
    assert ":not([data-plus-today])" in phone_block
    assert ":not([data-expired-today])" in phone_block
    assert ":not([data-halted-today])" in phone_block
    assert "safe-area-inset-bottom" in phone_block
    assert "overflow-x: hidden" in phone_block
    assert "var(--m-tabbar, 60px)" in phone_block
    assert ".mobile-tabbar" in phone_block
    assert "grid-template-columns: repeat(5, 1fr)" in phone_block
    assert "position: fixed" in phone_block
    assert ".dash-date" in phone_block
    assert "display: block" in phone_block
    assert ".dash-greeting-settings" in phone_block
    assert "sun" not in phone_block.lower()
    assert "[data-phone-pg-gate" not in phone_block
    assert "data-plus-today=\"desktop\"] {" not in phone_block

    desk = STYLES.read_text(encoding="utf-8").split(
        "/* Signed-in desktop Today", 1
    )[1]
    assert "@media (min-width: 561px)" in desk
    assert "minmax(260px, 380px)" in desk
    assert "playground.css?v=pg34" in BASE.read_text(encoding="utf-8")
    assert "styles.css?v=main86" in BASE.read_text(encoding="utf-8")
    assert "mobile.css?v=mob102" in BASE.read_text(encoding="utf-8")
    assert "mobile.css?v=mob101" not in BASE.read_text(encoding="utf-8")
    assert "action=\"/revision/start\"" in DASH.read_text(encoding="utf-8")
    assert "data-signed-in-today-phone" not in DASH.read_text(encoding="utf-8")
    assert "data-signed-in-today" not in ADD.read_text(encoding="utf-8")
    assert "data-signed-in-pg-gate" in GATE.read_text(encoding="utf-8")
    first_bar = BASE.read_text(encoding="utf-8").split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 1
    )[1].split("</nav>", 1)[0]
    assert 'href="/calendar"' in first_bar
    assert "path.startswith('/dashboard')" in first_bar
    assert "data-signed-in-bareact-phone-tabs" not in first_bar
    pg = PG_CSS.read_text(encoding="utf-8")
    assert "data-signed-in-today" not in pg.split(
        "/* Plus desktop /dashboard Today", 1
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


def test_phone_signed_in_today_screen04_firstrun_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    today = user_today(_engine(client))
    label = f"{today.strftime('%A')} {today.day} {today.strftime('%B')}"
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_signed_in_today_screen04_firstrun_390x844.png"
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
        page.goto(f"{origin}/dashboard", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-signed-in-today]');
              const header = document.querySelector('.site-header');
              const tabs = document.querySelector('.mobile-tabbar');
              const tabLinks = tabs ? [...tabs.querySelectorAll('a.mobile-tab')] : [];
              const active = tabs && tabs.querySelector('.mobile-tab.is-active');
              const dateEl = document.querySelector('[data-today-date]');
              const sub = document.querySelector('.dash-subtext');
              const gear = document.querySelector('.dash-greeting-settings');
              const hello = document.querySelector('.dash-hello');
              const cta = document.querySelector('.dash-firstrun-cta');
              const tabBox = tabs && tabs.getBoundingClientRect();
              const ctaBox = cta && cta.getBoundingClientRect();
              return {
                present: Boolean(panel),
                plus: Boolean(document.querySelector('[data-plus-today]')),
                mode: document.querySelector('[data-today-mode]')
                  && document.querySelector('[data-today-mode]').getAttribute('data-today-mode'),
                hello: hello && hello.textContent.trim(),
                dateText: dateEl && dateEl.textContent.trim(),
                dateDisplay: dateEl ? getComputedStyle(dateEl).display : null,
                subDisplay: sub ? getComputedStyle(sub).display : null,
                gearDisplay: gear ? getComputedStyle(gear).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                tabsPosition: tabs ? getComputedStyle(tabs).position : null,
                tabLabels: tabLinks.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabLinks.map((el) => el.getAttribute('href')),
                todayActive: active && active.textContent.replace(/\\s+/g, ' ').trim(),
                ctaText: cta && cta.textContent.trim(),
                ctaHref: cta && cta.getAttribute('href'),
                ctaBottom: ctaBox && ctaBox.bottom,
                tabTop: tabBox && tabBox.top,
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                playgroundRows: document.querySelectorAll(
                  '[data-today-source="playground"]'
                ).length,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["present"] is True
    assert geo["plus"] is False
    assert geo["mode"] == "firstrun"
    assert geo["hello"] == "Welcome, Sanjay."
    assert geo["dateText"] == label
    assert geo["dateDisplay"] not in (None, "none")
    assert geo["subDisplay"] == "none"
    assert geo["gearDisplay"] == "none"
    assert geo["headerDisplay"] == "none"
    assert geo["tabsDisplay"] != "none"
    assert geo["tabsPosition"] == "fixed"
    assert geo["tabLabels"] == ["Today", "Browse", "Playground", "Calendar", "Profile"]
    assert geo["tabHrefs"] == [href for _, href in TAB_HREFS]
    assert geo["todayActive"] == "Today"
    assert "Learn your first Article" in (geo["ctaText"] or "")
    assert geo["ctaHref"] == "/browse"
    assert geo["ctaBottom"] <= geo["tabTop"] + 8
    assert geo["overflow"] is False
    assert geo["playgroundRows"] == 0
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_signed_in_today_screen04_revision_390x844(tmp_path: Path) -> None:
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
    label = f"{today.strftime('%A')} {today.day} {today.strftime('%B')}"
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_signed_in_today_screen04_revision_390x844.png"
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
        requests: list[str] = []
        page.on("request", lambda req: requests.append(f"{req.method} {req.url}"))
        page.goto(f"{origin}/dashboard", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-signed-in-today]');
              const hero = document.querySelector('.dash-due.is-due');
              const form = hero && hero.querySelector('form.dash-revision-form');
              const cta = hero && hero.querySelector('[data-revision-start]');
              const pathCta = document.querySelector(
                '.rc-path-node.is-current .rc-path-cta'
              );
              const tabs = document.querySelector('.mobile-tabbar');
              const dateEl = document.querySelector('[data-today-date]');
              const sources = [...document.querySelectorAll('[data-today-source]')].map(
                (el) => el.getAttribute('data-today-source')
              );
              const pathText = (document.querySelector('[data-today-path-card]')
                || {innerText: ''}).innerText || '';
              const heroBox = hero && hero.getBoundingClientRect();
              const pathBox = document.querySelector('[data-today-path-card]')
                && document.querySelector('[data-today-path-card]').getBoundingClientRect();
              const tabBox = tabs && tabs.getBoundingClientRect();
              const ctaBox = cta && cta.getBoundingClientRect();
              return {
                present: Boolean(panel),
                mode: hero && hero.getAttribute('data-today-mode'),
                formAction: form && form.getAttribute('action'),
                formMethod: form && (form.getAttribute('method') || '').toLowerCase(),
                ctaText: cta && (cta.textContent || '').replace(/\\s+/g, ' ').trim(),
                ctaH: ctaBox && ctaBox.height,
                heroBottom: ctaBox && ctaBox.bottom,
                tabTop: tabBox && tabBox.top,
                tabsPosition: tabs ? getComputedStyle(tabs).position : null,
                dateText: dateEl && dateEl.textContent.trim(),
                dateDisplay: dateEl ? getComputedStyle(dateEl).display : null,
                pathCtaText: pathCta && pathCta.textContent.trim(),
                pathCtaHref: pathCta && pathCta.getAttribute('href'),
                pathCtaMin: pathCta && getComputedStyle(pathCta).minHeight,
                sources,
                hasNdps: /NDPS|Section 8|Section 9|Article 19\\(1\\)\\(a\\)/.test(pathText),
                stacked: Boolean(
                  heroBox && pathBox && pathBox.top > heroBox.bottom - 8
                ),
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                greeting: document.querySelector('.dash-hello')
                  && document.querySelector('.dash-hello').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(80)
        reach = page.evaluate(
            """() => {
              const cta = document.querySelector(
                '.rc-path-node.is-current .rc-path-cta'
              );
              const tabs = document.querySelector('.mobile-tabbar');
              const cr = cta.getBoundingClientRect();
              const tr = tabs.getBoundingClientRect();
              return { ctaBottom: cr.bottom, tabTop: tr.top };
            }"""
        )
        page.set_viewport_size({"width": 390, "height": 700})
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(80)
        short_hero = page.evaluate(
            """() => {
              const heroCta = document.querySelector('[data-revision-start]');
              const tabs = document.querySelector('.mobile-tabbar');
              const hb = heroCta.getBoundingClientRect();
              const tb = tabs.getBoundingClientRect();
              return {
                heroBottom: hb.bottom,
                tabTopHero: tb.top,
                tabsFixed: getComputedStyle(tabs).position === 'fixed',
              };
            }"""
        )
        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(80)
        short_path = page.evaluate(
            """() => {
              const pathCta = document.querySelector(
                '.rc-path-node.is-current .rc-path-cta'
              );
              const tabs = document.querySelector('.mobile-tabbar');
              const pb = pathCta.getBoundingClientRect();
              const tb = tabs.getBoundingClientRect();
              return { pathBottom: pb.bottom, tabTopPath: tb.top };
            }"""
        )
        n_before = len(requests)
        page.goto(f"{origin}/dashboard", wait_until="networkidle")
        page.locator("[data-revision-start]").click()
        page.wait_for_url("**/learn/**", timeout=8000)
        extra = requests[n_before:]
        learn_path = page.evaluate("() => location.pathname")
        browser.close()

    assert geo["present"] is True
    assert geo["mode"] == "revision"
    assert geo["formAction"] == "/revision/start"
    assert geo["formMethod"] == "post"
    assert geo["ctaText"].startswith("Start revision") or "left" in (geo["ctaText"] or "")
    assert geo["ctaH"] == pytest.approx(48, abs=4)
    assert geo["heroBottom"] <= geo["tabTop"] + 8
    assert geo["tabsPosition"] == "fixed"
    assert geo["dateText"] == label
    assert geo["dateDisplay"] not in (None, "none")
    assert "Start revision" in (geo["pathCtaText"] or "") or "Learn " in (
        geo["pathCtaText"] or ""
    )
    assert "/learn/" in (geo["pathCtaHref"] or "")
    assert float(str(geo["pathCtaMin"] or "0").replace("px", "") or 0) >= 44
    assert geo["sources"]
    assert set(geo["sources"]) == {"constitution"}
    assert geo["hasNdps"] is False
    assert geo["stacked"] is True
    assert geo["overflow"] is False
    assert geo["greeting"] == "Good morning, Sanjay."
    assert reach["ctaBottom"] <= reach["tabTop"] + 8
    assert short_hero["tabsFixed"] is True
    assert short_hero["heroBottom"] <= short_hero["tabTopHero"] + 8
    assert short_path["pathBottom"] <= short_path["tabTopPath"] + 8
    assert "/learn/" in learn_path
    assert any(item.startswith("POST ") and "/revision/start" in item for item in extra)
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_signed_in_today_screen04_desktop_regression_1280(
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
        artifact_dir / "phone_signed_in_today_screen04_desktop_regression_1280.png"
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
        page.goto(f"{origin}/dashboard", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-signed-in-today]');
              const tabs = document.querySelector('.mobile-tabbar');
              const header = document.querySelector('.site-header');
              const hero = document.querySelector('.dash-due.is-due');
              const path = document.querySelector('[data-today-path-card]');
              const cta = hero && hero.querySelector('[data-revision-start]');
              const ring = hero && hero.querySelector('.rc-goal-ring');
              const dateEl = document.querySelector('[data-today-date]');
              const sub = document.querySelector('.dash-subtext');
              const titleBox = hero && hero.getBoundingClientRect();
              const pathBox = path && path.getBoundingClientRect();
              const sources = [...document.querySelectorAll('[data-today-source]')].map(
                (el) => el.getAttribute('data-today-source')
              );
              return {
                present: Boolean(panel),
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                twoCol: Boolean(
                  titleBox && pathBox && pathBox.left > titleBox.right - 8
                ),
                heroW: titleBox && titleBox.width,
                ctaH: cta && cta.getBoundingClientRect().height,
                ringW: ring && ring.getBoundingClientRect().width,
                dateDisplay: dateEl ? getComputedStyle(dateEl).display : null,
                subDisplay: sub ? getComputedStyle(sub).display : null,
                sources,
                mode: hero && hero.getAttribute('data-today-mode'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["present"] is True
    assert geo["tabsDisplay"] == "none"
    assert geo["headerDisplay"] != "none"
    assert geo["twoCol"] is True
    assert geo["heroW"] == pytest.approx(380, abs=24)
    assert geo["ctaH"] == pytest.approx(48, abs=2)
    assert geo["ringW"] == pytest.approx(72, abs=2)
    assert geo["dateDisplay"] not in (None, "none")
    assert geo["subDisplay"] == "none"
    assert set(geo["sources"]) == {"constitution"}
    assert geo["mode"] == "revision"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_free_today_date_visible_other_cohorts_stay_hidden(
    tmp_path: Path,
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    def _shot_date(app, session: str) -> dict:
        port, _server = _serve(app)
        origin = f"http://127.0.0.1:{port}"
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
            context = browser.new_context(
                viewport={"width": 390, "height": 844}, device_scale_factor=1
            )
            context.add_cookies(_cookie(session, origin))
            page = context.new_page()
            page.goto(f"{origin}/dashboard", wait_until="networkidle")
            geo = page.evaluate(
                """() => {
                  const dateEl = document.querySelector('[data-today-date]');
                  return {
                    dateDisplay: dateEl ? getComputedStyle(dateEl).display : null,
                    plus: Boolean(document.querySelector('[data-plus-today]')),
                    expired: Boolean(document.querySelector('[data-expired-today]')),
                    halted: Boolean(document.querySelector('[data-halted-today]')),
                    signed: Boolean(document.querySelector('[data-signed-in-today]')),
                  };
                }"""
            )
            browser.close()
        return geo

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    _make_due(free, ["clause-1"])
    free_geo = _shot_date(free.app, free.cookies.get(SESSION_COOKIE_NAME))
    assert free_geo["signed"] is True
    assert free_geo["plus"] is False
    assert free_geo["dateDisplay"] not in (None, "none")

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_geo = _shot_date(plus.app, plus.cookies.get(SESSION_COOKIE_NAME))
    assert plus_geo["plus"] is True
    assert plus_geo["dateDisplay"] == "none"

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
    expired_geo = _shot_date(expired.app, expired.cookies.get(SESSION_COOKIE_NAME))
    assert expired_geo["expired"] is True
    assert expired_geo["dateDisplay"] == "none"

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    stored_h = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored_h.id, status="halted"
    )
    halted_geo = _shot_date(halted.app, halted.cookies.get(SESSION_COOKIE_NAME))
    assert halted_geo["halted"] is True
    assert halted_geo["dateDisplay"] == "none"
