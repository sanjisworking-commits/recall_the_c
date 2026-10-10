"""Phone Guest Bare Act head Screen 01 (CTA map guest/01-screen, 390x844).

Authorized: ChatGPT. Guest GET /laws/ndps phone composition only. Desktop
1280 guest/04-screen and signed-in/Plus/Expired/Halted phone CTAs stay on
production Bare Act. Add-sheet Screen 02 has its own tests.
"""

from __future__ import annotations

import socket
import threading
import time
from datetime import datetime, timezone
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
from constitution_memorizer.playground.urls import add_path
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.guest_bareact_head import (
    NDPS_GUEST_KICKER,
    NDPS_GUEST_META,
    NDPS_GUEST_ROWS,
    NDPS_GUEST_TITLE,
    ndps_guest_head,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
PRIMARY = "Sign in to use Playground"
FORBIDDEN = (
    "Already in Playground",
    ">Sections<",
    ">Continue<",
    ">Manage<",
    "Resume Playground",
    "Add to Playground",
    "Unlock Playground",
    "Subscribe to use Playground",
    "LawPlaygroundCta",
)
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
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


def _guest_app(tmp_path: Path):
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
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


def _guest_client(tmp_path: Path) -> TestClient:
    return TestClient(_guest_app(tmp_path))


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


def _phone_guest(html: str) -> str:
    return html.split("data-guest-bareact-phone", 1)[1].split(
        "data-bareact-phone", 1
    )[0]


def _tabs(html: str) -> str:
    return html.split("data-guest-bareact-phone-tabs", 1)[1].split("</nav>", 1)[0]


def _facts(client: TestClient) -> dict:
    history = tuple(
        sorted(
            (row.id, row.status, row.tier, row.is_current)
            for row in client.app.state.subscriptions.list_subscription_history(USER)
        )
    )
    roster = getattr(client.app.state, "roster", None)
    overlay = getattr(client.app.state, "playground", None)
    return {
        "session": client.cookies.get(SESSION_COOKIE_NAME),
        "subscription": client.app.state.subscriptions.get_current_subscription(USER),
        "history": history,
        "active": tuple(
            sorted(i.law_id for i in roster.active_roster_items(USER))
        )
        if roster is not None
        else (),
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        )
        if overlay is not None
        else (),
    }


def test_phone_guest_ndps_uses_live_head_and_primary(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    page = client.get("/laws/ndps")
    assert page.status_code == 200
    html = unescape(page.text)
    assert "data-guest-bareact-phone" in html
    phone = _phone_guest(html)
    live = ndps_guest_head()
    assert f">{live.title}<" in phone
    assert live.title == NDPS_GUEST_TITLE
    assert NDPS_GUEST_KICKER in phone
    assert NDPS_GUEST_META in phone
    assert f'href="/laws"' in phone
    assert "← Laws" in phone
    assert PRIMARY in phone
    assert phone.count(PRIMARY) == 1
    assert f'href="{add_path("ndps")}"' in phone
    assert "data-pg-sheet" in phone
    assert 'data-pg-kind="guest"' in phone
    assert 'href="/login"' not in phone
    assert "About this act" not in phone
    assert "data-bareact-tabs" not in phone
    for phrase in FORBIDDEN:
        assert phrase not in phone, phrase
    for row in NDPS_GUEST_ROWS:
        assert row.tag in phone
        assert row.title in phone
        assert row.range_label in phone
    assert 'href="/laws/ndps/section/' not in phone
    assert 'href="/laws/ndps/schedule/' not in phone
    assert "<details" not in phone
    assert live.rows == NDPS_GUEST_ROWS


def test_phone_guest_five_tabs_browse_active(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/laws/ndps").text
    assert "data-guest-bareact-phone-tabs" in html
    assert "mobile-tabbar is-guest" not in html
    tabs = _tabs(html)
    labels = []
    for label, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        labels.append(label)
        assert label in tabs
    assert labels == ["Today", "Browse", "Playground", "Calendar", "Profile"]
    browse = tabs.split('href="/browse"', 1)[1].split("</a>", 1)[0]
    assert "is-active" in browse
    assert 'aria-current="page"' in browse
    for href in ("/dashboard", "/playground", "/calendar", "/profile"):
        chunk = tabs.split(f'href="{href}"', 1)[1].split("</a>", 1)[0]
        assert "is-active" not in chunk
    browse_page = _guest_client(tmp_path / "browse").get("/browse").text
    assert "data-guest-bareact-phone-tabs" not in browse_page
    assert "mobile-tabbar is-guest" in browse_page


def test_phone_guest_add_sheet_is_existing_guest_kind(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    before = _facts(client)
    sheet = client.get(add_path("ndps"))
    assert sheet.status_code == 200
    assert 'data-pg-kind="guest"' in sheet.text
    assert "data-pg-add" in sheet.text
    assert _facts(client) == before


def test_phone_guest_gets_are_mutation_free(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    before = _facts(client)
    assert before["session"] is None
    assert before["subscription"] is None
    for url in ("/laws/ndps", add_path("ndps"), "/laws"):
        page = client.get(url)
        assert page.status_code == 200
        assert _facts(client) == before


def test_desktop_and_other_laws_stay_separate(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    html = client.get("/laws/ndps").text
    desk = html.split("data-guest-bareact-desktop", 1)[1].split(
        "data-guest-bareact-phone", 1
    )[0]
    assert PRIMARY in desk
    assert "← Laws" not in desk
    assert 'class="guest-bareact-back" href="/laws"' in desk
    bns = client.get("/laws/bns").text
    assert "data-guest-bareact-phone" not in bns
    assert "data-guest-bareact-desktop" not in bns
    assert "<details" in bns
    section = client.get("/laws/ndps/section/1").text
    assert "data-guest-bareact-phone" not in section
    landing = client.get("/").text
    assert 'data-guest-landing="desktop"' in landing
    laws = client.get("/laws").text
    assert "data-guest-laws-desktop" in laws
    assert "data-guest-bareact-phone" not in laws


def test_signed_in_plus_expired_halted_phone_keep_production_cta(
    tmp_path: Path,
) -> None:
    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/laws/ndps").text
    assert "data-guest-bareact-phone" not in free_html
    assert "data-guest-bareact-phone-tabs" not in free_html
    assert "data-signed-in-bareact-phone" in free_html
    assert "data-signed-in-bareact-phone-tabs" in free_html
    free_phone = free_html.split("data-signed-in-bareact-phone", 1)[1].split(
        "</section>", 1
    )[0]
    assert "Subscribe to use Playground" in free_phone
    assert PRIMARY not in free_phone
    assert 'data-pg-kind="subscribe"' in free_phone
    assert "LawPlaygroundCta" not in free_phone
    assert "<details" not in free_phone

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get("/laws/ndps").text
    assert "data-guest-bareact-phone" not in plus_html
    plus_prod = plus_html.split("data-bareact-phone", 1)[1]
    assert "LawPlaygroundCta" in plus_prod
    assert PRIMARY not in plus_prod
    assert "Add to Playground" in plus_prod

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
    expired_html = expired.get("/laws/ndps").text
    assert "data-guest-bareact-phone" not in expired_html
    assert "Resume Playground" in expired_html.split("data-bareact-phone", 1)[1]

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/laws/ndps").text
    assert "data-guest-bareact-phone" not in halted_html
    halted_prod = halted_html.split("data-bareact-phone", 1)[1]
    assert "LawPlaygroundCta" in halted_prod
    assert PRIMARY not in halted_prod


def test_phone_guest_markers_and_pins() -> None:
    bare = BARE.read_text(encoding="utf-8")
    assert "data-guest-bareact-phone" in bare
    assert "← Laws" in bare
    assert 'data-pg-kind="guest"' in bare
    base = BASE.read_text(encoding="utf-8")
    assert "data-guest-bareact-phone-tabs" in base
    assert "styles.css?v=main86" in base
    assert "mobile.css?v=mob102" in base
    assert "mobile.css?v=mob99" not in base
    styles = STYLES.read_text(encoding="utf-8")
    hide_phone = styles.split("[data-guest-bareact-phone] {", 1)[1].split("}", 1)[0]
    assert "display: none" in hide_phone
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "guest/01-screen" in mobile
    assert "data-guest-bareact-phone" in mobile
    assert "data-signed-in-bareact-desktop" not in mobile


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


def test_phone_guest_bareact_screen01_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_guest_bareact_screen01_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        page = browser.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const phone = document.querySelector('[data-guest-bareact-phone]');
              const desk = document.querySelector('[data-guest-bareact-desktop]');
              const prod = document.querySelector('[data-bareact-phone]');
              const header = document.querySelector('.site-header');
              const tabs = document.querySelector('[data-guest-bareact-phone-tabs]');
              const cta = phone && phone.querySelector('.guest-bareact-cta');
              const back = phone && phone.querySelector('.guest-bareact-back');
              const rows = phone ? [...phone.querySelectorAll('.guest-bareact-row')] : [];
              const rowLinks = phone ? phone.querySelectorAll('a:not(.guest-bareact-back):not(.guest-bareact-cta)') : [];
              const active = tabs && tabs.querySelector('.mobile-tab.is-active');
              const tabLinks = tabs ? [...tabs.querySelectorAll('a.mobile-tab')] : [];
              const headerChip = document.querySelector('[data-guest-account-menu]');
              return {
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                prodDisplay: prod ? getComputedStyle(prod).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                title: phone && phone.querySelector('.guest-bareact-title').textContent.trim(),
                kicker: phone && phone.querySelector('.guest-bareact-kicker').textContent.trim(),
                meta: phone && phone.querySelector('.guest-bareact-meta').textContent.trim(),
                backText: back && back.textContent.replace(/\\s+/g, ' ').trim(),
                backHref: back && back.getAttribute('href'),
                ctaText: cta && cta.textContent.trim(),
                ctaHref: cta && cta.getAttribute('href'),
                ctaSheet: cta && cta.hasAttribute('data-pg-sheet'),
                ctaWidth: cta ? cta.getBoundingClientRect().width : 0,
                rowCount: rows.length,
                rowTitles: rows.map((el) => el.querySelector('.guest-bareact-row-title').textContent.trim()),
                extraLinks: rowLinks.length,
                tabLabels: tabLinks.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabLinks.map((el) => el.getAttribute('href')),
                browseActive: active && active.textContent.replace(/\\s+/g, ' ').trim(),
                chipDisplay: headerChip ? getComputedStyle(headerChip).display : null,
                already: phone && phone.innerText.includes('Already in Playground'),
                subscribe: phone && phone.innerText.includes('Subscribe to use Playground'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        page.locator("[data-guest-bareact-phone] .guest-bareact-cta").click()
        page.wait_for_selector("[data-pg-add]", timeout=8000)
        dialog = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              return {
                kind: panel && panel.getAttribute('data-pg-kind'),
                url: location.pathname,
              };
            }"""
        )
        page.keyboard.press("Escape")
        still = page.evaluate("() => location.pathname")
        browser.close()

    assert geo["phoneDisplay"] != "none"
    assert geo["deskDisplay"] == "none"
    assert geo["prodDisplay"] == "none"
    assert geo["headerDisplay"] == "none"
    assert geo["tabsDisplay"] != "none"
    assert geo["overflow"] is False
    assert geo["title"] == NDPS_GUEST_TITLE
    assert geo["kicker"] == NDPS_GUEST_KICKER
    assert geo["meta"] == NDPS_GUEST_META
    assert geo["backText"] == "← Laws"
    assert geo["backHref"] == "/laws"
    assert geo["ctaText"] == PRIMARY
    assert geo["ctaHref"] == add_path("ndps")
    assert geo["ctaSheet"] is True
    assert geo["ctaWidth"] >= 300
    assert geo["rowCount"] == 4
    assert geo["rowTitles"] == [row.title for row in NDPS_GUEST_ROWS]
    assert geo["extraLinks"] == 0
    assert geo["tabLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["tabHrefs"] == [
        "/dashboard",
        "/browse",
        "/playground",
        "/calendar",
        "/profile",
    ]
    assert geo["browseActive"] == "Browse"
    assert geo["already"] is False
    assert geo["subscribe"] is False
    assert dialog["kind"] == "guest"
    assert still.endswith("/laws/ndps")
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_guest_bareact_screen01_desktop_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_guest_bareact_screen01_desktop_regression_1280.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        page = browser.new_page(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-guest-bareact-desktop]');
              const phone = document.querySelector('[data-guest-bareact-phone]');
              const prod = document.querySelector('[data-bareact-phone]');
              const tabs = document.querySelector('[data-guest-bareact-phone-tabs]');
              const header = document.querySelector('.site-header');
              const cta = desk && desk.querySelector('.guest-bareact-cta');
              const nav = [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                (el) => el.textContent.replace(/\\s+/g, ' ').trim()
              );
              return {
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                prodDisplay: prod ? getComputedStyle(prod).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                ctaText: cta && cta.textContent.trim(),
                ctaHref: cta && cta.getAttribute('href'),
                navLabels: nav,
                title: desk && desk.querySelector('.guest-bareact-title').textContent.trim(),
                account: document.querySelector('.account-menu-btn-name')
                  && document.querySelector('.account-menu-btn-name').textContent.trim(),
              };
            }"""
        )
        plus_app = _mu_app(tmp_path / "plus-phone")
        plus_client = TestClient(plus_app)
        _sign_in(plus_client)
        _subscribe(plus_client)
        plus_port, _plus_server = _serve(plus_app, host="127.0.0.1")
        plus_page = browser.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        plus_origin = f"http://127.0.0.1:{plus_port}"
        session = plus_client.cookies.get(SESSION_COOKIE_NAME)
        plus_page.context.add_cookies(
            [
                {
                    "name": SESSION_COOKIE_NAME,
                    "value": session,
                    "url": plus_origin,
                    "httpOnly": True,
                    "secure": False,
                    "sameSite": "Lax",
                }
            ]
        )
        plus_page.goto(f"{plus_origin}/laws/ndps", wait_until="networkidle")
        plus_geo = plus_page.evaluate(
            """() => {
              const phoneGuest = document.querySelector('[data-guest-bareact-phone]');
              const prod = document.querySelector('[data-bareact-phone]');
              const desk = document.querySelector('[data-signed-in-bareact-desktop]');
              return {
                guestPhone: phoneGuest ? getComputedStyle(phoneGuest).display : null,
                prodDisplay: prod ? getComputedStyle(prod).display : null,
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                details: prod ? prod.querySelectorAll('details').length : 0,
                cta: prod && prod.innerText.includes('Sign in to use Playground'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["prodDisplay"] == "none"
    assert geo["tabsDisplay"] == "none"
    assert geo["headerDisplay"] != "none"
    assert geo["ctaText"] == PRIMARY
    assert geo["ctaHref"] == add_path("ndps")
    assert geo["navLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["title"] == NDPS_GUEST_TITLE
    assert geo["account"] == "Guest"
    assert plus_geo["guestPhone"] is None
    assert plus_geo["prodDisplay"] != "none"
    assert plus_geo["deskDisplay"] == "none"
    assert plus_geo["details"] == 8
    assert plus_geo["cta"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
