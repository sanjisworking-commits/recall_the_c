"""Halted cohort desktop Landing Screen 01 (CTA map halted/01-screen).

Authorized: ChatGPT. Authenticated multiuser GET / after a real Plus
subscription is halted. Same accepted Screen 01 landing as guest/Plus/Expired:
dark stack, Explore the Constitution → /browse, Explore Laws → /laws, no
header. Halted is marked from EntitlementSnapshot via
request_is_halted_subscriber only. Elapsed paid period stays Halted, not
Expired. No payment copy or billing actions. Guest, Free, Plus, Expired,
paused, pending, Pro/Max, phone, Plus 01–11, and Expired 01–11 stay
unchanged. No new route.
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
from constitution_memorizer.entitlements.dependencies import snapshot_is_halted_subscriber
from constitution_memorizer.entitlements.models import (
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
    CONSTITUTION_ACCESS_FULL,
    EntitlementSnapshot,
)
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
INVENTED = (
    "Payment failed",
    "Payment retries stopped",
    "Your Playground is on hold",
    "Resume Playground",
    "Manage payment",
    "Subscription halted",
    "RecallC Plus",
    "ON HOLD",
    "Free account",
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


def _snap(**overrides) -> EntitlementSnapshot:
    fields = dict(
        is_authenticated=True,
        subscription_status="halted",
        tier="plus",
        is_subscribed=False,
        admin_override=False,
        can_use_constitution_learn=True,
        constitution_access=CONSTITUTION_ACCESS_FULL,
        can_read_laws=True,
        can_open_playground=False,
        can_consume_new_playground_law=False,
        playground_law_limit=10,
        playground_block_reason=BLOCK_PAYMENT_HALTED,
        billing_period_start=ACTIVE_START,
        billing_period_end=ACTIVE_END,
        legacy_status=None,
    )
    fields.update(overrides)
    return EntitlementSnapshot(**fields)


def _desk(html: str) -> str:
    return html.split('data-guest-landing="desktop"', 1)[1].split("</section>", 1)[0]


def _launch(html: str) -> str:
    return html.split('<section class="rc-launch">', 1)[1].split("</section>", 1)[0]


def _facts(client: TestClient) -> dict:
    snap = client.app.state.entitlement_service.resolve(USER)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    cap = roster.peek_capacity(USER, snap)
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


def test_snapshot_is_halted_subscriber_matches_plan_fields() -> None:
    open_period = _snap()
    assert snapshot_is_halted_subscriber(open_period) is True
    elapsed = _snap(
        playground_block_reason=BLOCK_PAID_PERIOD_ENDED,
        billing_period_start=EXPIRED_START,
        billing_period_end=EXPIRED_END,
    )
    assert snapshot_is_halted_subscriber(elapsed) is True
    assert snapshot_is_halted_subscriber(_snap(is_authenticated=False)) is False
    assert snapshot_is_halted_subscriber(
        _snap(subscription_status=None, tier=None, playground_block_reason="not_subscribed")
    ) is False
    assert snapshot_is_halted_subscriber(
        _snap(
            subscription_status="active",
            is_subscribed=True,
            can_open_playground=True,
            can_consume_new_playground_law=True,
            playground_block_reason=None,
        )
    ) is False
    assert snapshot_is_halted_subscriber(
        _snap(
            subscription_status="expired",
            playground_block_reason=BLOCK_PAID_PERIOD_ENDED,
            billing_period_start=EXPIRED_START,
            billing_period_end=EXPIRED_END,
        )
    ) is False
    assert snapshot_is_halted_subscriber(_snap(subscription_status="paused")) is False
    assert snapshot_is_halted_subscriber(_snap(subscription_status="pending")) is False
    assert snapshot_is_halted_subscriber(_snap(subscription_status="cancelled")) is False
    assert snapshot_is_halted_subscriber(_snap(subscription_status="completed")) is False
    assert snapshot_is_halted_subscriber(
        _snap(
            admin_override=True,
            tier=None,
            can_open_playground=True,
            can_consume_new_playground_law=True,
            playground_block_reason=None,
        )
    ) is False


def test_halted_open_period_landing_from_real_subscription(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert stored is not None
    assert stored.status == "halted"
    assert stored.tier == "plus"
    assert stored.billing_period_end == ACTIVE_END
    assert snap.is_authenticated is True
    assert snap.subscription_status == "halted"
    assert snap.tier == "plus"
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    assert snap.playground_block_reason == BLOCK_PAYMENT_HALTED
    assert snapshot_is_halted_subscriber(snap) is True

    root = client.get("/", follow_redirects=False)
    assert root.status_code == 200
    assert root.headers.get("location") is None
    html = root.text
    assert 'data-halted-landing="desktop"' in html
    assert 'data-guest-landing="desktop"' in html
    assert 'data-plus-landing="desktop"' not in html
    assert 'data-expired-landing="desktop"' not in html
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
    assert "data-halted-landing" not in _launch(html)
    browse = client.get("/browse")
    assert browse.status_code == 200
    laws = client.get("/laws")
    assert laws.status_code == 200


def test_halted_elapsed_period_is_halted_not_expired(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(
        client,
        status="halted",
        period_start=EXPIRED_START,
        period_end=EXPIRED_END,
    )
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.subscription_status == "halted"
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snapshot_is_halted_subscriber(snap) is True
    html = client.get("/", follow_redirects=False).text
    assert 'data-halted-landing="desktop"' in html
    assert 'data-expired-landing="desktop"' not in html
    assert 'data-plus-landing="desktop"' not in html


def test_guest_free_plus_expired_paused_pending_pro_max_are_not_halted(
    tmp_path: Path,
) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest")).get("/", follow_redirects=False).text
    assert 'data-halted-landing="desktop"' not in guest
    assert 'data-guest-landing="desktop"' in guest

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/", follow_redirects=False).text
    assert 'data-halted-landing="desktop"' not in free_html
    assert 'data-plus-landing="desktop"' not in free_html
    assert snapshot_is_halted_subscriber(
        free.app.state.entitlement_service.resolve(USER)
    ) is False

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus, status="active")
    plus_html = plus.get("/", follow_redirects=False).text
    assert 'data-plus-landing="desktop"' in plus_html
    assert 'data-halted-landing="desktop"' not in plus_html
    assert 'data-expired-landing="desktop"' not in plus_html

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(
        expired,
        status="expired",
        period_start=EXPIRED_START,
        period_end=EXPIRED_END,
    )
    expired_html = expired.get("/", follow_redirects=False).text
    assert 'data-expired-landing="desktop"' in expired_html
    assert 'data-halted-landing="desktop"' not in expired_html
    assert 'data-plus-landing="desktop"' not in expired_html

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused, status="paused")
    paused_html = paused.get("/", follow_redirects=False).text
    assert 'data-halted-landing="desktop"' not in paused_html

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    pending_html = pending.get("/", follow_redirects=False).text
    assert 'data-halted-landing="desktop"' not in pending_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro", status="active")
    assert 'data-halted-landing="desktop"' not in pro.get("/", follow_redirects=False).text

    mx = TestClient(_mu_app(tmp_path / "max"))
    _sign_in(mx)
    _subscribe(mx, tier="max", status="active")
    assert 'data-halted-landing="desktop"' not in mx.get("/", follow_redirects=False).text

    cancelled = TestClient(_mu_app(tmp_path / "cancelled"))
    _sign_in(cancelled)
    _subscribe(cancelled, status="cancelled")
    assert 'data-halted-landing="desktop"' not in cancelled.get(
        "/", follow_redirects=False
    ).text

    completed = TestClient(_mu_app(tmp_path / "completed"))
    _sign_in(completed)
    _subscribe(completed, status="completed")
    assert 'data-halted-landing="desktop"' not in completed.get(
        "/", follow_redirects=False
    ).text


def test_halted_landing_get_is_mutation_free(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    before = _facts(client)
    assert before["subscription"] is not None
    assert before["entitlement"][1] == "halted"
    page = client.get("/")
    assert page.status_code == 200
    after = _facts(client)
    assert after == before
    again = client.get("/")
    assert again.status_code == 200
    assert _facts(client) == before


def test_halted_landing_marker_uses_shared_predicate() -> None:
    src = LANDING.read_text(encoding="utf-8")
    assert 'data-guest-landing="desktop"' in src
    assert "plus_landing" in src
    assert 'data-plus-landing="desktop"' in src
    assert "expired_landing" in src
    assert 'data-expired-landing="desktop"' in src
    assert "halted_landing" in src
    assert 'data-halted-landing="desktop"' in src
    desk_line = [
        line for line in src.splitlines() if 'data-guest-landing="desktop"' in line
    ][0]
    assert "halted_landing" in desk_line
    assert "plus_landing" in desk_line
    assert "expired_landing" in desk_line
    launch = src.split('<section class="rc-launch">', 1)[1].split("</section>", 1)[0]
    assert "halted_landing" not in launch
    assert "data-halted-landing" not in launch
    assert "Explore the Constitution" in src
    assert 'href="/browse"' in src
    assert 'href="/laws"' in src
    assert 'href="/billing' not in src
    for phrase in INVENTED:
        assert phrase not in src, phrase
    app = APP.read_text(encoding="utf-8")
    home = app.split("async def home", 1)[1].split("eng = _engine()", 1)[0]
    assert "request_is_halted_subscriber" in home
    assert "request_is_expired_subscriber" in home
    assert "request_is_active_plus" in home
    assert '"halted_landing": halted_landing' in home
    assert "def snapshot_is_halted_subscriber" not in home
    deps = DEPS.read_text(encoding="utf-8")
    assert "def snapshot_is_halted_subscriber" in deps
    assert "def request_is_halted_subscriber" in deps
    halted_fn = deps.split("def snapshot_is_halted_subscriber", 1)[1].split(
        "def request_is_halted_subscriber", 1
    )[0]
    assert 'subscription_status == "halted"' in halted_fn
    assert "BLOCK_PAYMENT_HALTED" not in halted_fn
    assert "BLOCK_PAID_PERIOD_ENDED" not in halted_fn
    assert '"pending", "halted", "paused"' in deps or (
        "pending" in deps and "halted" in deps and "paused" in deps
    )
    assert "playground.css?v=pg28" not in src
    assert 'data-halted-landing="desktop"' not in PG_CSS.read_text(encoding="utf-8")
    assert "data-halted-landing" not in STYLES.read_text(encoding="utf-8")
    assert "data-halted-landing" not in MOBILE.read_text(encoding="utf-8")


def test_plus_01_11_and_expired_01_11_untouched() -> None:
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
    assert 'data-expired-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-plus-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-expired-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    assert 'data-expired-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    for path in (
        BROWSE,
        LAWS,
        BARE,
        ADD,
        HOME,
        GATE,
        MANAGE,
        DASH,
        CAL,
        PROFILE,
        SETTINGS,
    ):
        text = path.read_text(encoding="utf-8")
        assert "data-halted-landing" not in text
        assert "halted_landing" not in text


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


def test_halted_phone_launch_unchanged(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    html = client.get("/", follow_redirects=False).text
    assert "data-halted-landing" not in _launch(html)

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
              const primary = launch && launch.querySelector('.rc-launch-cta:not(.is-ghost)');
              const ghost = launch && launch.querySelector('.rc-launch-cta.is-ghost');
              return {
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                launchDisplay: launch ? getComputedStyle(launch).display : null,
                launchHasHalted: !!(launch && launch.hasAttribute('data-halted-landing')),
                launchName: (document.querySelector('.rc-launch-name') || {}).textContent,
                launchTag: (document.querySelector('.rc-launch-tag') || {}).textContent,
                launchMark: (document.querySelector('.rc-launch-mark') || {}).textContent,
                primaryText: primary && primary.textContent.trim(),
                ghostText: ghost && ghost.textContent.trim(),
                primaryHref: primary && primary.getAttribute('href'),
                ghostHref: ghost && ghost.getAttribute('href'),
              };
            }"""
        )
        browser.close()
    assert geo["deskDisplay"] == "none"
    assert geo["launchDisplay"] == "block"
    assert geo["launchHasHalted"] is False
    assert (geo["launchMark"] or "").strip() == "C"
    assert (geo["launchName"] or "").strip() == "Recall the C"
    assert (geo["launchTag"] or "").strip() == "The Constitution, remembered."
    assert geo["primaryText"] == "Explore the Constitution"
    assert geo["ghostText"] == "Explore Laws"
    assert geo["primaryHref"] == "/browse"
    assert geo["ghostHref"] == "/laws"


def test_halted_landing_1280(tmp_path: Path) -> None:
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
    shot_path = artifact_dir / "halted_landing_screen01_1280.png"
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
              const desk = document.querySelector('[data-halted-landing="desktop"]');
              const plus = document.querySelector('[data-plus-landing="desktop"]');
              const expired = document.querySelector('[data-expired-landing="desktop"]');
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
                expiredPresent: Boolean(expired),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                launchDisplay: launch ? getComputedStyle(launch).display : null,
                hasHeader: !!header,
                loginCount: document.querySelectorAll('a[href*="/login"]').length,
                billingCount: document.querySelectorAll('a[href*="/billing"]').length,
                invented: /Payment failed|Payment retries stopped|Your Playground is on hold|Resume Playground|Manage payment|Subscription halted|RecallC Plus|ON HOLD/.test(text),
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
    assert geo["expiredPresent"] is False
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


def test_halted_landing_plus_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client, status="active")
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_landing_screen01_plus_regression_1280.png"
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
              const halted = document.querySelector('[data-halted-landing="desktop"]');
              const expired = document.querySelector('[data-expired-landing="desktop"]');
              const primary = document.querySelector('.rc-desk-cta:not(.is-ghost)');
              const ghost = document.querySelector('.rc-desk-cta.is-ghost');
              const launch = document.querySelector('.rc-launch');
              return {
                plusPresent: Boolean(plus),
                haltedPresent: Boolean(halted),
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
    assert geo["haltedPresent"] is False
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
