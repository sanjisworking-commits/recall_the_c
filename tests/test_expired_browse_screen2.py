"""Expired cohort desktop Browse Screen 02 (CTA map expired/02-screen).

Authorized: ChatGPT. Authenticated multiuser GET /browse with a real expired
subscription whose paid period has ended. Constitution browsing stays fully
available. The Free-plan strip is omitted because expired is not Free.
Header status comes from the live paid-period-ended gate title. Guest, Free,
Plus, halted, phone, Plus 01–11, and Expired 01 stay unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import socket
import threading
import time
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
from constitution_memorizer.playground.view import gate_view
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "data" / "output" / "learning_units.json"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
APP = ROOT / "src/constitution_memorizer/web/app.py"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
MANAGE = ROOT / "src/constitution_memorizer/web/templates/subscription_manage.html"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_EXPIRED_STATUS = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
INVENTED = (
    "Your plan expired",
    "Resume subscription",
    "Resume Playground",
    "Premium",
    "Unlimited",
    "Unlock all",
    "Free plan",
    "All 3 slots",
    "Start learning",
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


def _mu_app(tmp_path: Path, *, units: Path | None = None, display_name: str = "Sanjay"):
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER,
        email="a@example.com",
        display_name=display_name,
        avatar_url=None,
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    return create_app(
        units_path=units or MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=provider,
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
    status: str = "expired",
    period_start: datetime = EXPIRED_START,
    period_end: datetime = EXPIRED_END,
) -> None:
    client.app.state.subscriptions.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        billing_period_start=period_start,
        billing_period_end=period_end,
        is_current=True,
    )


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _browse_panel(html: str) -> str:
    return html.split('<section class="panel browse"', 1)[1].split(
        "mobile-sheet", 1
    )[0]


def test_expired_browse_keeps_constitution_and_omits_free_strip(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert snap.subscription_status == "expired"
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    html = client.get("/browse").text
    panel = _browse_panel(html)
    header = _header(html)
    assert 'data-expired-browse="desktop"' in html
    assert 'data-plus-browse="desktop"' not in html
    assert "data-signed-in-browse-strip" not in html
    assert "browse-access-unlock" not in html
    assert "data-guest-strip" not in html
    assert ">Browse the Constitution<" in panel
    assert (
        "The Constitution, Part by Part. Open an Article, then learn any clause from inside it."
        in panel
    )
    assert 'href="/laws"' in panel
    assert 'href="/tables"' in panel
    assert '<span class="browse-resource-name">Laws</span>' in panel
    assert '<span class="browse-resource-name">Tables</span>' in panel
    assert "/browse/article/" in panel
    assert "Sanjay" in header
    assert LIVE_EXPIRED_STATUS in header
    assert "Free account" not in header
    assert "RecallC Plus" not in header
    assert 'href="/browse"' in header
    assert "is-active" in header
    for phrase in INVENTED:
        assert phrase not in panel, phrase
    assert 'href="/billing' not in panel
    laws = client.get("/laws")
    assert laws.status_code == 200
    tables = client.get("/tables")
    assert tables.status_code == 200


def test_free_plus_guest_halted_stay_separate_from_expired(tmp_path: Path) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest"))
    guest_html = guest.get("/browse").text
    assert 'data-expired-browse="desktop"' not in guest_html
    assert "data-guest-strip" in guest_html
    assert "data-signed-in-browse-strip" not in guest_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/browse").text
    assert 'data-expired-browse="desktop"' not in free_html
    assert 'data-plus-browse="desktop"' not in free_html
    strip = free_html.split("data-signed-in-browse-strip", 1)[1].split("</div>", 1)[0]
    assert "Free plan \u2014 pick any 3 Articles to learn." in strip
    assert "All 3 slots free." in strip
    assert 'class="browse-access-unlock" href="/playground">Unlock all</a>' in strip
    assert "Free account" in _header(free_html)

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(
        plus,
        status="active",
        period_start=ACTIVE_START,
        period_end=ACTIVE_END,
    )
    plus_html = plus.get("/browse").text
    assert 'data-plus-browse="desktop"' in plus_html
    assert 'data-expired-browse="desktop"' not in plus_html
    assert "data-signed-in-browse-strip" not in plus_html
    assert "RecallC Plus" in _header(plus_html)
    assert LIVE_EXPIRED_STATUS not in _header(plus_html)

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(
        halted,
        status="halted",
        period_start=ACTIVE_START,
        period_end=ACTIVE_END,
    )
    halted_html = halted.get("/browse").text
    assert 'data-expired-browse="desktop"' not in halted_html
    assert "data-signed-in-browse-strip" in halted_html
    halted_snap = halted.app.state.entitlement_service.resolve(USER)
    assert halted_snap.subscription_status == "halted"
    assert halted_snap.playground_block_reason != BLOCK_PAID_PERIOD_ENDED


def test_expired_browse_uses_shared_predicate_not_a_template_flag() -> None:
    browse = BROWSE.read_text(encoding="utf-8")
    assert "expired_browse" in browse
    assert 'data-expired-browse="desktop"' in browse
    assert "plus_browse" in browse
    assert 'data-plus-browse="desktop"' in browse
    assert "not expired_browse|default(false)" in browse
    assert "Unlock all" in browse
    assert 'href="/laws"' in browse
    assert 'href="/tables"' in browse
    assert "Your plan expired" not in browse
    assert "Resume Playground" not in browse
    assert "Playground paused" not in browse
    assert LIVE_EXPIRED_STATUS not in browse
    base = BASE.read_text(encoding="utf-8")
    assert "expired_browse" in base
    assert "expired_header_status" in base
    assert "RecallC Plus" in base
    assert "Free account" in base
    assert "Playground paused" not in base
    app = APP.read_text(encoding="utf-8")
    page = app.split("async def browse_index", 1)[1].split(
        "async def browse_part", 1
    )[0]
    assert "request_is_expired_subscriber" in page
    assert "request_is_active_plus" in page
    assert '"expired_browse": expired_browse' in page
    assert "def snapshot_is_expired_subscriber" not in page
    home = app.split("async def home", 1)[1].split("eng = _engine()", 1)[0]
    assert "request_is_expired_subscriber" in home
    assert '"expired_landing": expired_landing' in home
    deps = DEPS.read_text(encoding="utf-8")
    assert "def request_is_expired_subscriber" in deps
    assert "BLOCK_PAID_PERIOD_ENDED" in deps


def test_plus_screens_and_expired_01_untouched() -> None:
    assert 'data-plus-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-expired-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-plus-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-plus-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-plus-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-plus-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-plus-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-plus-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-plus-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-plus-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    landing = LANDING.read_text(encoding="utf-8")
    assert "data-expired-browse" not in landing
    assert "expired_browse" not in landing
    for path in (LAWS, BARE, ADD, HOME, MANAGE, DASH, CAL, PROFILE, SETTINGS):
        text = path.read_text(encoding="utf-8")
        assert "data-expired-browse" not in text
        assert "expired_browse" not in text
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-expired-browse" not in mobile
    assert "def request_is_active_plus" in DEPS.read_text(encoding="utf-8")
    assert 'snapshot.tier == "plus"' in DEPS.read_text(encoding="utf-8")


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


def test_expired_phone_browse_unchanged(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
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
        page.goto(f"{origin}/browse", wait_until="networkidle")
        phone = page.evaluate(
            """() => {
              const display = document.querySelector('.browse > .display');
              const legend = document.querySelector('.browse-legend');
              const part = document.querySelector('.browse-part');
              const rail = document.querySelector('.browse-part-rail');
              const head = document.querySelector('.mobile-screen-head');
              const strip = document.querySelector('[data-signed-in-browse-strip]');
              const vis = (el) => el && getComputedStyle(el).display !== 'none';
              return {
                hasStrip: !!strip,
                expiredPresent: Boolean(
                  document.querySelector('[data-expired-browse="desktop"]')
                ),
                displayShown: vis(display),
                legendShown: vis(legend),
                partShown: vis(part),
                railShown: vis(rail),
                headShown: vis(head),
              };
            }"""
        )
        browser.close()
    assert phone["hasStrip"] is False
    assert phone["expiredPresent"] is True
    assert phone["displayShown"] is False
    assert phone["legendShown"] is False
    assert phone["partShown"] is False
    assert phone["railShown"] is True
    assert phone["headShown"] is True


def test_expired_browse_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "expired_browse_screen02_1280.png"
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
        page.goto(f"{origin}/browse", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const browse = document.querySelector('.nav-link.is-active');
              const expired = document.querySelector('[data-expired-browse="desktop"]');
              const plus = document.querySelector('[data-plus-browse="desktop"]');
              const strip = document.querySelector('[data-signed-in-browse-strip]');
              const unlock = document.querySelector('.browse-access-unlock');
              const laws = document.querySelector('.browse-resource-card[href="/laws"]');
              const tables = document.querySelector('.browse-resource-card[href="/tables"]');
              const heading = document.querySelector('.browse > .display');
              const article = document.querySelector('.browse-article-card[href], .browse-card-link');
              const mobileHead = document.querySelector('.mobile-screen-head');
              const partRail = document.querySelector('.browse-part-rail');
              const news = document.querySelector('.browse-legend-item[data-browse-filter="news"]');
              const panelText = document.querySelector('section.browse').innerText;
              return {
                present: Boolean(expired),
                plusPresent: Boolean(plus),
                browseText: browse.textContent.replace(/\\s+/g, ' ').trim(),
                headingText: heading.textContent.trim(),
                hasStrip: !!strip,
                hasUnlock: !!unlock,
                lawsHref: laws && laws.getAttribute('href'),
                tablesHref: tables && tables.getAttribute('href'),
                articleHref: article && article.getAttribute('href'),
                accountName: document.querySelector('.account-menu-btn-name').textContent.trim(),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                mobileHeadDisplay: mobileHead ? getComputedStyle(mobileHead).display : null,
                partRailDisplay: partRail ? getComputedStyle(partRail).display : null,
                newsLabel: news ? news.innerText.replace(/\\s+/g, ' ').trim() : null,
                invented: /Your plan expired|Resume subscription|Resume Playground|Premium|Unlimited|Unlock all|Free plan|All 3 slots/.test(panelText),
                billingCount: document.querySelectorAll('a[href*="/billing"]').length,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        page.locator('.browse-resource-card[href="/laws"]').click()
        page.wait_for_url("**/laws**", timeout=8000)
        laws_url = page.url
        page.goto(f"{origin}/browse", wait_until="networkidle")
        tables_href = page.locator(
            '.browse-resource-card[href="/tables"]'
        ).get_attribute("href")
        browser.close()

    assert geo["present"] is True
    assert geo["plusPresent"] is False
    assert geo["browseText"] == "Browse"
    assert geo["headingText"] == "Browse the Constitution"
    assert geo["hasStrip"] is False
    assert geo["hasUnlock"] is False
    assert geo["invented"] is False
    assert geo["billingCount"] == 0
    assert geo["lawsHref"] == "/laws"
    assert geo["tablesHref"] == "/tables"
    assert geo["articleHref"] and geo["articleHref"].startswith("/browse/article/")
    assert geo["accountName"] == "Sanjay"
    assert geo["accountStatus"] == LIVE_EXPIRED_STATUS
    assert geo["mobileHeadDisplay"] == "none"
    assert geo["partRailDisplay"] == "none"
    assert geo["newsLabel"] and "In news" in geo["newsLabel"]
    assert "/laws" in laws_url
    assert tables_href == "/tables"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_free_browse_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "expired_browse_screen02_free_1280.png"
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
        page.goto(f"{origin}/browse", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const expired = document.querySelector('[data-expired-browse="desktop"]');
              const plus = document.querySelector('[data-plus-browse="desktop"]');
              const strip = document.querySelector('[data-signed-in-browse-strip]');
              const unlock = document.querySelector('.browse-access-unlock');
              return {
                expiredPresent: Boolean(expired),
                plusPresent: Boolean(plus),
                hasStrip: !!strip,
                stripText: strip ? strip.innerText.replace(/\\s+/g, ' ').trim() : '',
                unlockHref: unlock && unlock.getAttribute('href'),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["expiredPresent"] is False
    assert geo["plusPresent"] is False
    assert geo["hasStrip"] is True
    assert "Free plan" in geo["stripText"]
    assert "All 3 slots free." in geo["stripText"]
    assert geo["unlockHref"] == "/playground"
    assert geo["accountStatus"] == "Free account"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
