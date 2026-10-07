"""Halted cohort desktop Browse Screen 02 (CTA map halted/02-screen).

Authorized: ChatGPT. Authenticated multiuser GET /browse after a real Plus
subscription is halted. Constitution browsing stays fully available. The
Free-plan strip is omitted. Header status comes from
gate_view(BLOCK_PAYMENT_HALTED).title even when the paid period has elapsed.
Guest, Free, Plus, Expired, paused, pending, Pro/Max, phone, Plus 01–11,
Expired 01–11, and Halted 01 stay unchanged. No new route.
"""

from __future__ import annotations

import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.entitlements.models import (
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
)
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
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
MANAGE = ROOT / "src/constitution_memorizer/web/templates/subscription_manage.html"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_HALTED_STATUS = gate_view(reason=BLOCK_PAYMENT_HALTED).title
LIVE_EXPIRED_STATUS = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
INVENTED = (
    "Your payment failed",
    "Fix your payment",
    "Resume billing",
    "Subscription halted",
    "Playground unavailable",
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
    status: str = "halted",
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


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _browse_panel(html: str) -> str:
    return html.split('<section class="panel browse"', 1)[1].split(
        "mobile-sheet", 1
    )[0]


def _facts(client: TestClient) -> dict:
    snap = client.app.state.entitlement_service.resolve(USER)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    cap = roster.peek_capacity(USER, snap)
    eng = client.app.state.engine.for_user(USER)
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    history = tuple(
        sorted(
            (row.id, row.status, row.tier, row.is_current)
            for row in client.app.state.subscriptions.list_subscription_history(USER)
        )
    )
    service = getattr(client.app.state, "device_service", None)
    if service is None:
        devices = ()
    else:
        devices = tuple(
            sorted((d.id, d.revoked_at, d.device_key_hash) for d in service.list_devices(USER))
        )
    return {
        "active": tuple(sorted(i.law_id for i in roster.active_roster_items(USER))),
        "removed": tuple(sorted(i.law_id for i in roster.removed_roster_items(USER))),
        "used": cap.used,
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
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
        "claimed": tuple(sorted(eng.claimed_articles())),
        "subscription": None
        if stored is None
        else (
            stored.id,
            stored.status,
            stored.tier,
            stored.is_current,
            stored.billing_period_end,
        ),
        "history": history,
        "devices": devices,
        "entitlement": (
            snap.is_authenticated,
            snap.subscription_status,
            snap.tier,
            snap.is_subscribed,
            snap.can_open_playground,
            snap.can_consume_new_playground_law,
            snap.playground_block_reason,
        ),
    }


def test_halted_open_period_browse_omits_free_strip(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.is_authenticated is True
    assert snap.tier == "plus"
    assert snap.subscription_status == "halted"
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    assert snap.playground_block_reason == BLOCK_PAYMENT_HALTED
    assert LIVE_HALTED_STATUS == "Payment retries have stopped"

    page = client.get("/browse")
    assert page.status_code == 200
    html = page.text
    panel = _browse_panel(html)
    header = _header(html)
    assert 'data-halted-browse="desktop"' in html
    assert 'data-plus-browse="desktop"' not in html
    assert 'data-expired-browse="desktop"' not in html
    assert "data-signed-in-browse-strip" not in html
    assert "browse-access-unlock" not in html
    assert "data-guest-strip" not in html
    assert "Free plan" not in panel
    assert "Unlock all" not in panel
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
    assert "is-preview" not in panel
    assert "Preview only" not in panel
    assert "Sanjay" in header
    assert LIVE_HALTED_STATUS in header
    assert LIVE_EXPIRED_STATUS not in header
    assert "Free account" not in header
    assert "RecallC Plus" not in header
    assert 'href="/browse"' in header
    assert "is-active" in header
    assert "mobile-screen-head" in html
    for phrase in INVENTED:
        assert phrase not in panel, phrase
    assert 'href="/billing' not in panel


def test_halted_elapsed_period_stays_halted_on_browse(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(
        client,
        period_start=EXPIRED_START,
        period_end=EXPIRED_END,
    )
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.subscription_status == "halted"
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    html = client.get("/browse").text
    header = _header(html)
    assert 'data-halted-browse="desktop"' in html
    assert 'data-expired-browse="desktop"' not in html
    assert 'data-plus-browse="desktop"' not in html
    assert "data-signed-in-browse-strip" not in html
    assert LIVE_HALTED_STATUS in header
    assert LIVE_EXPIRED_STATUS not in header
    assert "Free account" not in header


def test_guest_free_plus_expired_paused_pending_pro_max_are_not_halted_browse(
    tmp_path: Path,
) -> None:
    guest_html = TestClient(_mu_app(tmp_path / "guest")).get("/browse").text
    assert 'data-halted-browse="desktop"' not in guest_html
    assert "data-guest-strip" in guest_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/browse").text
    assert 'data-halted-browse="desktop"' not in free_html
    strip = free_html.split("data-signed-in-browse-strip", 1)[1].split("</div>", 1)[0]
    assert "Free plan" in strip
    assert "Unlock all" in strip
    assert "Free account" in _header(free_html)

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus, status="active")
    plus_html = plus.get("/browse").text
    assert 'data-plus-browse="desktop"' in plus_html
    assert 'data-halted-browse="desktop"' not in plus_html
    assert "data-signed-in-browse-strip" not in plus_html
    assert "RecallC Plus" in _header(plus_html)
    assert LIVE_HALTED_STATUS not in _header(plus_html)

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(
        expired,
        status="expired",
        period_start=EXPIRED_START,
        period_end=EXPIRED_END,
    )
    expired_html = expired.get("/browse").text
    assert 'data-expired-browse="desktop"' in expired_html
    assert 'data-halted-browse="desktop"' not in expired_html
    assert "data-signed-in-browse-strip" not in expired_html
    assert LIVE_EXPIRED_STATUS in _header(expired_html)
    assert LIVE_HALTED_STATUS not in _header(expired_html)

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused, status="paused")
    assert 'data-halted-browse="desktop"' not in paused.get("/browse").text

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    assert 'data-halted-browse="desktop"' not in pending.get("/browse").text

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro", status="active")
    assert 'data-halted-browse="desktop"' not in pro.get("/browse").text

    mx = TestClient(_mu_app(tmp_path / "max"))
    _sign_in(mx)
    _subscribe(mx, tier="max", status="active")
    assert 'data-halted-browse="desktop"' not in mx.get("/browse").text


def test_halted_browse_get_is_mutation_free(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    before = _facts(client)
    page = client.get("/browse")
    assert page.status_code == 200
    after = _facts(client)
    assert after == before
    again = client.get("/browse")
    assert again.status_code == 200
    assert _facts(client) == before


def test_halted_browse_uses_shared_predicate() -> None:
    src = BROWSE.read_text(encoding="utf-8")
    assert "plus_browse" in src
    assert "expired_browse" in src
    assert "halted_browse" in src
    assert 'data-halted-browse="desktop"' in src
    assert "not halted_browse|default(false)" in src
    desk_line = [
        line for line in src.splitlines() if 'data-plus-browse="desktop"' in line
    ][0]
    assert "halted_browse" in desk_line
    assert "mobile-screen-head" in src
    assert "Unlock all" in src
    assert 'href="/laws"' in src
    assert 'href="/tables"' in src
    for phrase in INVENTED:
        assert phrase not in src, phrase
    assert LIVE_HALTED_STATUS not in src
    base = BASE.read_text(encoding="utf-8")
    assert "halted_browse" in base
    assert "halted_header_status" in base
    assert "expired_header_status" in base
    assert "RecallC Plus" in base
    assert "Free account" in base
    assert LIVE_HALTED_STATUS not in base
    app = APP.read_text(encoding="utf-8")
    page = app.split("async def browse_index", 1)[1].split(
        "async def browse_part", 1
    )[0]
    assert "request_is_halted_subscriber" in page
    assert "request_is_expired_subscriber" in page
    assert "request_is_active_plus" in page
    assert '"halted_browse": halted_browse' in page
    assert "def snapshot_is_halted_subscriber" not in page
    assert "BLOCK_PAYMENT_HALTED" in page
    assert "gate_view" in page
    home = app.split("async def home", 1)[1].split("eng = _engine()", 1)[0]
    assert "request_is_halted_subscriber" in home
    assert '"halted_landing": halted_landing' in home
    assert "data-halted-browse" not in PG_CSS.read_text(encoding="utf-8")
    assert "data-halted-browse" not in STYLES.read_text(encoding="utf-8")
    assert "data-halted-browse" not in MOBILE.read_text(encoding="utf-8")


def test_plus_expired_and_halted_01_untouched() -> None:
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-halted-landing="desktop"' in landing
    assert "data-halted-browse" not in landing
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
    assert 'data-expired-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-plus-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-expired-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    assert 'data-expired-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    for path in (LAWS, BARE, ADD, HOME, GATE, MANAGE, DASH, CAL, PROFILE, SETTINGS):
        text = path.read_text(encoding="utf-8")
        assert "data-halted-browse" not in text
        assert "halted_browse" not in text
    assert "def request_is_halted_subscriber" in DEPS.read_text(encoding="utf-8")


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


def test_halted_browse_1280(tmp_path: Path) -> None:
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
    shot_path = artifact_dir / "halted_browse_screen02_1280.png"
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
              const halted = document.querySelector('[data-halted-browse="desktop"]');
              const plus = document.querySelector('[data-plus-browse="desktop"]');
              const expired = document.querySelector('[data-expired-browse="desktop"]');
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
                present: Boolean(halted),
                plusPresent: Boolean(plus),
                expiredPresent: Boolean(expired),
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
                invented: /Your payment failed|Fix your payment|Resume billing|Subscription halted|Playground unavailable|Unlock all|Free plan/.test(panelText),
                billingCount: document.querySelectorAll('section.browse a[href*="/billing"]').length,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["present"] is True
    assert geo["plusPresent"] is False
    assert geo["expiredPresent"] is False
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
    assert geo["accountStatus"] == LIVE_HALTED_STATUS
    assert geo["mobileHeadDisplay"] == "none"
    assert geo["partRailDisplay"] == "none"
    assert geo["newsLabel"] and "In news" in geo["newsLabel"]
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_halted_browse_plus_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client, status="active")
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_browse_screen02_plus_regression_1280.png"
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
              const plus = document.querySelector('[data-plus-browse="desktop"]');
              const halted = document.querySelector('[data-halted-browse="desktop"]');
              const expired = document.querySelector('[data-expired-browse="desktop"]');
              const strip = document.querySelector('[data-signed-in-browse-strip]');
              return {
                plusPresent: Boolean(plus),
                haltedPresent: Boolean(halted),
                expiredPresent: Boolean(expired),
                hasStrip: !!strip,
                heading: document.querySelector('.browse > .display').textContent.trim(),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["plusPresent"] is True
    assert geo["haltedPresent"] is False
    assert geo["expiredPresent"] is False
    assert geo["hasStrip"] is False
    assert geo["heading"] == "Browse the Constitution"
    assert geo["accountStatus"] == "RecallC Plus"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
