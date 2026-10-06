"""Expired cohort desktop Landing Screen 01 (CTA map expired/01-screen).

Authorized: ChatGPT. Authenticated multiuser GET / with a real expired
subscription whose paid period has ended. Same accepted Screen 01 landing
as guest/Free/Plus: dark stack, Explore the Constitution → /browse,
Explore Laws → /laws, no header. Expired is marked from EntitlementSnapshot
only. No invented expired/resume/billing copy. Guest, Free, Plus, halted,
phone, and Plus Screens 01–11 stay unchanged.
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
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
APP = ROOT / "src/constitution_memorizer/web/app.py"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
MANAGE = ROOT / "src/constitution_memorizer/web/templates/subscription_manage.html"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
USER = UUID("11111111-1111-4111-8111-111111111111")
# Ended vs PLAYGROUND_TEST_NOW = 2026-09-16 12:00 UTC.
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
INVENTED = (
    "Your plan expired",
    "Resume subscription",
    "Resume Playground",
    "Premium",
    "Unlimited",
    "RecallC Plus",
    "Free account",
    "Start learning",
    "saved progress",
    "quota",
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


def _expired_snapshot(client: TestClient):
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None
    snap = client.app.state.entitlement_service.resolve(USER)
    return stored, snap


def _desk(html: str) -> str:
    return html.split('data-guest-landing="desktop"', 1)[1].split("</section>", 1)[0]


def _launch(html: str) -> str:
    return html.split('<section class="rc-launch">', 1)[1].split("</section>", 1)[0]


def test_expired_root_keeps_accepted_landing_from_real_subscription(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    stored, snap = _expired_snapshot(client)
    assert stored.status == "expired"
    assert stored.tier == "plus"
    assert stored.billing_period_end == EXPIRED_END
    assert snap.is_authenticated is True
    assert snap.subscription_status == "expired"
    assert snap.tier == "plus"
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert snap.billing_period_end == EXPIRED_END

    root = client.get("/", follow_redirects=False)
    assert root.status_code == 200
    assert root.headers.get("location") is None
    html = root.text
    assert 'data-expired-landing="desktop"' in html
    assert 'data-guest-landing="desktop"' in html
    assert 'data-plus-landing="desktop"' not in html
    desk = _desk(html)
    assert ">Recall the C</h1>" in html
    assert "The Constitution, remembered." in html
    assert 'href="/browse">Explore the Constitution</a>' in desk
    assert 'href="/laws">Explore Laws</a>' in desk
    assert desk.count("href=") == 2
    for phrase in INVENTED:
        assert phrase not in html, phrase
    assert "<header" not in html
    assert "<nav" not in html
    assert 'href="/login"' not in html
    assert 'href="/dashboard"' not in html
    assert 'href="/playground"' not in html
    assert 'href="/billing' not in html
    assert 'href="/billing/subscriptions"' not in html
    assert "data-expired-landing" not in _launch(html)
    browse = client.get("/browse")
    assert browse.status_code == 200
    laws = client.get("/laws")
    assert laws.status_code == 200


def test_guest_free_plus_halted_pending_are_not_expired(tmp_path: Path) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest"))
    guest_html = guest.get("/", follow_redirects=False).text
    assert 'data-guest-landing="desktop"' in guest_html
    assert 'data-expired-landing="desktop"' not in guest_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/", follow_redirects=False).text
    assert 'data-guest-landing="desktop"' in free_html
    assert 'data-expired-landing="desktop"' not in free_html
    assert 'data-plus-landing="desktop"' not in free_html
    free_snap = free.app.state.entitlement_service.resolve(USER)
    assert free_snap.playground_block_reason != BLOCK_PAID_PERIOD_ENDED
    assert free_snap.tier is None

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(
        plus,
        status="active",
        period_start=ACTIVE_START,
        period_end=ACTIVE_END,
    )
    plus_html = plus.get("/", follow_redirects=False).text
    assert 'data-plus-landing="desktop"' in plus_html
    assert 'data-expired-landing="desktop"' not in plus_html
    plus_snap = plus.app.state.entitlement_service.resolve(USER)
    assert plus_snap.is_subscribed is True
    assert plus_snap.subscription_status == "active"

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(
        halted,
        status="halted",
        period_start=ACTIVE_START,
        period_end=ACTIVE_END,
    )
    halted_html = halted.get("/", follow_redirects=False).text
    assert 'data-expired-landing="desktop"' not in halted_html
    halted_snap = halted.app.state.entitlement_service.resolve(USER)
    assert halted_snap.subscription_status == "halted"
    assert halted_snap.playground_block_reason != BLOCK_PAID_PERIOD_ENDED

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(
        pending,
        status="pending",
        period_start=ACTIVE_START,
        period_end=ACTIVE_END,
    )
    pending_html = pending.get("/", follow_redirects=False).text
    assert 'data-expired-landing="desktop"' not in pending_html


def test_halted_and_paused_past_period_are_not_expired_screen_01(
    tmp_path: Path,
) -> None:
    halted = TestClient(_mu_app(tmp_path / "halted-ended"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_snap = halted.app.state.entitlement_service.resolve(USER)
    assert halted_snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert halted_snap.subscription_status == "halted"
    halted_html = halted.get("/", follow_redirects=False).text
    assert 'data-expired-landing="desktop"' not in halted_html
    assert 'data-plus-landing="desktop"' not in halted_html

    paused = TestClient(_mu_app(tmp_path / "paused-ended"))
    _sign_in(paused)
    _subscribe(paused, status="paused")
    paused_snap = paused.app.state.entitlement_service.resolve(USER)
    assert paused_snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert paused_snap.subscription_status == "paused"
    paused_html = paused.get("/", follow_redirects=False).text
    assert 'data-expired-landing="desktop"' not in paused_html


def test_expired_status_with_open_period_is_not_expired_screen_01(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(
        client,
        status="expired",
        period_start=ACTIVE_START,
        period_end=ACTIVE_END,
    )
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.subscription_status == "expired"
    assert snap.playground_block_reason != BLOCK_PAID_PERIOD_ENDED
    html = client.get("/", follow_redirects=False).text
    assert 'data-expired-landing="desktop"' not in html


def test_expired_landing_marker_is_conditional_in_template() -> None:
    src = LANDING.read_text(encoding="utf-8")
    assert 'data-guest-landing="desktop"' in src
    assert "plus_landing" in src
    assert 'data-plus-landing="desktop"' in src
    assert "expired_landing" in src
    assert 'data-expired-landing="desktop"' in src
    desk_line = [
        line for line in src.splitlines() if 'data-guest-landing="desktop"' in line
    ][0]
    assert "expired_landing" in desk_line
    launch = src.split('<section class="rc-launch">', 1)[1].split("</section>", 1)[0]
    assert "expired_landing" not in launch
    assert "data-expired-landing" not in launch
    assert "Explore the Constitution" in src
    assert 'href="/browse"' in src
    assert 'href="/laws"' in src
    assert "Your plan expired" not in src
    assert "Resume subscription" not in src
    for phrase in ("Premium", "Unlimited", "RecallC Plus"):
        assert phrase not in src
    app = APP.read_text(encoding="utf-8")
    home = app.split("async def home", 1)[1].split("eng = _engine()", 1)[0]
    assert "request_is_expired_subscriber" in home
    assert '"expired_landing": expired_landing' in home
    assert "request_is_active_plus" in home
    deps = DEPS.read_text(encoding="utf-8")
    assert "def snapshot_is_expired_subscriber" in deps
    assert "def request_is_expired_subscriber" in deps
    assert "BLOCK_PAID_PERIOD_ENDED" in deps
    assert '"pending", "halted", "paused"' in deps or (
        "pending" in deps and "halted" in deps and "paused" in deps
    )


def test_plus_screens_01_to_11_untouched() -> None:
    assert 'data-plus-landing="desktop"' in LANDING.read_text(encoding="utf-8")
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
    for path in (BROWSE, LAWS, BARE, ADD, HOME, MANAGE, DASH, CAL, PROFILE, SETTINGS):
        text = path.read_text(encoding="utf-8")
        assert "data-expired-landing" not in text
        assert "expired_landing" not in text
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


def test_expired_phone_launch_unchanged(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    html = client.get("/", follow_redirects=False).text
    assert "data-expired-landing" not in _launch(html)

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
        page.goto(f"{origin}/", wait_until="networkidle")
        geo = page.evaluate(
            """() => {
              const desk = document.querySelector('.rc-desk');
              const launch = document.querySelector('.rc-launch');
              return {
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                launchDisplay: launch ? getComputedStyle(launch).display : null,
                launchHasExpired: !!(launch && launch.hasAttribute('data-expired-landing')),
                launchName: (document.querySelector('.rc-launch-name') || {}).textContent,
                launchTag: (document.querySelector('.rc-launch-tag') || {}).textContent,
              };
            }"""
        )
        browser.close()
    assert geo["deskDisplay"] == "none"
    assert geo["launchDisplay"] == "block"
    assert geo["launchHasExpired"] is False
    assert (geo["launchName"] or "").strip() == "Recall the C"
    assert (geo["launchTag"] or "").strip() == "The Constitution, remembered."


def test_expired_landing_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "expired_landing_screen01_1280.png"
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
        page.goto(f"{origin}/", wait_until="networkidle")
        assert page.url.rstrip("/") == origin
        geo = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-expired-landing="desktop"]');
              const plus = document.querySelector('[data-plus-landing="desktop"]');
              const primary = document.querySelector('.rc-desk-cta:not(.is-ghost)');
              const ghost = document.querySelector('.rc-desk-cta.is-ghost');
              const launch = document.querySelector('.rc-launch');
              const header = document.querySelector('header');
              const pr = primary.getBoundingClientRect();
              const gr = ghost.getBoundingClientRect();
              const text = document.body.innerText;
              return {
                present: Boolean(desk),
                plusPresent: Boolean(plus),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                launchDisplay: launch ? getComputedStyle(launch).display : null,
                hasHeader: !!header,
                loginCount: document.querySelectorAll('a[href*="/login"]').length,
                billingCount: document.querySelectorAll('a[href*="/billing"]').length,
                invented: /Your plan expired|Resume subscription|Resume Playground|Premium|Unlimited|RecallC Plus|quota/.test(text),
                mark: (document.querySelector('.rc-desk-mark') || {}).textContent,
                name: (document.querySelector('.rc-desk-name') || {}).textContent,
                tag: (document.querySelector('.rc-desk-tag') || {}).textContent,
                primaryText: primary && primary.textContent.trim(),
                ghostText: ghost && ghost.textContent.trim(),
                primaryHref: primary && primary.getAttribute('href'),
                ghostHref: ghost && ghost.getAttribute('href'),
                primaryW: pr.width, ghostW: gr.width,
                primaryH: pr.height, ghostH: gr.height,
                primaryX: pr.x, ghostX: gr.x,
                bg: desk ? getComputedStyle(desk).backgroundColor : null,
              };
            }"""
        )
        page.screenshot(path=str(shot_path), full_page=False)
        page.locator(".rc-desk-cta:not(.is-ghost)").click()
        page.wait_for_url("**/browse**", timeout=8000)
        browse_url = page.url
        page.goto(f"{origin}/", wait_until="networkidle")
        page.locator(".rc-desk-cta.is-ghost").click()
        page.wait_for_url("**/laws**", timeout=8000)
        laws_url = page.url
        browser.close()

    assert geo["present"] is True
    assert geo["plusPresent"] is False
    assert geo["deskDisplay"] == "flex"
    assert geo["launchDisplay"] == "none"
    assert geo["hasHeader"] is False
    assert geo["loginCount"] == 0
    assert geo["billingCount"] == 0
    assert geo["invented"] is False
    assert (geo["mark"] or "").strip() == "C"
    assert (geo["name"] or "").strip() == "Recall the C"
    assert (geo["tag"] or "").strip() == "The Constitution, remembered."
    assert geo["primaryText"] == "Explore the Constitution"
    assert geo["ghostText"] == "Explore Laws"
    assert geo["primaryHref"] == "/browse"
    assert geo["ghostHref"] == "/laws"
    assert geo["primaryX"] < geo["ghostX"]
    assert abs(geo["primaryW"] - geo["ghostW"]) <= 1
    assert abs(geo["primaryH"] - geo["ghostH"]) <= 1
    assert browse_url.rstrip("/").endswith("/browse")
    assert "/laws" in laws_url
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_plus_landing_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(
        client,
        status="active",
        period_start=ACTIVE_START,
        period_end=ACTIVE_END,
    )
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "expired_landing_screen01_plus_regression_1280.png"
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
        page.goto(f"{origin}/", wait_until="networkidle")
        geo = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-landing="desktop"]');
              const expired = document.querySelector('[data-expired-landing="desktop"]');
              const primary = document.querySelector('.rc-desk-cta:not(.is-ghost)');
              const ghost = document.querySelector('.rc-desk-cta.is-ghost');
              const launch = document.querySelector('.rc-launch');
              return {
                plusPresent: Boolean(plus),
                expiredPresent: Boolean(expired),
                deskDisplay: plus ? getComputedStyle(plus).display : null,
                launchDisplay: launch ? getComputedStyle(launch).display : null,
                name: (document.querySelector('.rc-desk-name') || {}).textContent,
                tag: (document.querySelector('.rc-desk-tag') || {}).textContent,
                primaryText: primary && primary.textContent.trim(),
                ghostText: ghost && ghost.textContent.trim(),
                primaryHref: primary && primary.getAttribute('href'),
                ghostHref: ghost && ghost.getAttribute('href'),
              };
            }"""
        )
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["plusPresent"] is True
    assert geo["expiredPresent"] is False
    assert geo["deskDisplay"] == "flex"
    assert geo["launchDisplay"] == "none"
    assert (geo["name"] or "").strip() == "Recall the C"
    assert (geo["tag"] or "").strip() == "The Constitution, remembered."
    assert geo["primaryText"] == "Explore the Constitution"
    assert geo["ghostText"] == "Explore Laws"
    assert geo["primaryHref"] == "/browse"
    assert geo["ghostHref"] == "/laws"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
