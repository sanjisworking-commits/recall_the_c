"""Halted cohort desktop /billing/subscriptions Screen 07.

Authorized: ChatGPT. Authenticated multiuser GET /billing/subscriptions after
a real Plus subscription is halted. This is the management page reached from
Halted Screen 06 "Manage subscription", not a second paused-home screen.
Current-plan card is live catalog data. Lifecycle copy is
LIFECYCLE_MESSAGES["halted"]. Header from gate_view(BLOCK_PAYMENT_HALTED).
No upgrade/downgrade/cancel/checkout/Subscribe chooser. Guest, Free, Plus,
Expired, paused, pending, created/authenticated, terminal, phone, Plus 01–11,
Expired 01–11, and Halted 01–06 stay unchanged. No new route. No /resume.
No Halted 08.
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
from constitution_memorizer.auth.sessions import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.entitlements.models import (
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
)
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.urls import add_path, home_path
from constitution_memorizer.playground.view import PLAYGROUND_BILLING_PATH, gate_view
from constitution_memorizer.subscriptions.catalog import list_subscription_products
from constitution_memorizer.subscriptions.routes import LIFECYCLE_MESSAGES
from constitution_memorizer.subscriptions.service import SubscriptionService
from constitution_memorizer.web.app import create_app
from tests.test_subscription_lifecycle import FakeProvider, KEY_ID, PLAN_IDS

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
CHECKOUT = ROOT / "src/constitution_memorizer/web/templates/subscription_checkout.html"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
ROUTES = ROOT / "src/constitution_memorizer/subscriptions/routes.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_GATE = gate_view(reason=BLOCK_PAYMENT_HALTED)
LIVE_HEADING = LIVE_GATE.title
LIVE_CTA = LIVE_GATE.cta_label
LIVE_EXPIRED = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
CATALOG = {row.tier: row for row in list_subscription_products()}
PLUS_TAG = "A steady pace — enough for one exam’s syllabus of Acts."
HALTED_LIFE = LIFECYCLE_MESSAGES["halted"]
CREATE_PATH = "/billing/subscriptions/create"
CHANGE_PATH = "/billing/subscriptions/change"
CANCEL_PATH = "/billing/subscriptions/cancel"
INVENTED = (
    "Your subscription expired",
    "Resume subscription",
    "Change your plan",
    "Subscribe to Plus",
    "Subscribe to Pro",
    "Subscribe to Max",
    "Switch to Pro",
    "Switch to Max",
    "Cancel at cycle end",
    "Continue checkout",
    "Your payment failed",
    "Fix your payment",
    "Subscription halted",
    "Free plan",
    "Unlock all",
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
        RAZORPAY_KEY_ID=KEY_ID,
        RAZORPAY_KEY_SECRET="dummy-secret-for-tests",
        RAZORPAY_PLAN_ID_PLUS="plan_plus",
        RAZORPAY_PLAN_ID_PRO="plan_pro",
        RAZORPAY_PLAN_ID_MAX="plan_max",
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


def _attach_fake(app) -> FakeProvider:
    fake = FakeProvider()
    app.state.subscription_service = SubscriptionService(
        app.state.subscriptions,
        fake,
        PLAN_IDS,
        public_key_id=KEY_ID,
    )
    return fake


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    assert client.cookies.get(SESSION_COOKIE_NAME)


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get(CSRF_COOKIE_NAME) or ""
    return {"csrf_token": token} if token else {}


def _subscribe(
    client: TestClient,
    *,
    tier: str = "plus",
    status: str = "active",
    period_start: datetime = ACTIVE_START,
    period_end: datetime = ACTIVE_END,
):
    return client.app.state.subscriptions.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        billing_period_start=period_start,
        billing_period_end=period_end,
        is_current=True,
    )


def _confirm_add(client: TestClient, law_id: str):
    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    payload["scope"] = "sections"
    preview = client.post(add_path(law_id), data=_csrf(client), follow_redirects=False)
    if preview.status_code == 303 and "/playground/roster" in (
        preview.headers.get("location") or ""
    ):
        return client.post(add_path(law_id), data=payload, follow_redirects=False)
    if preview.status_code == 200:
        return client.post(add_path(law_id), data=payload, follow_redirects=False)
    return preview


def _halt(client: TestClient) -> None:
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None
    client.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )


def _seed_plus_then_halt(client: TestClient) -> None:
    _subscribe(client)
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    _halt(client)


def _facts(client: TestClient, fake: FakeProvider | None = None) -> dict:
    repo = client.app.state.subscriptions
    current = repo.get_current_subscription(USER)
    history = repo.list_subscription_history(USER)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    return {
        "current": (
            None
            if current is None
            else (
                current.id,
                current.status,
                current.is_current,
                current.tier,
                current.billing_period_start,
                current.billing_period_end,
            )
        ),
        "history": tuple(
            sorted((row.id, row.status, row.is_current, row.tier) for row in history)
        ),
        "creates": tuple(req.plan_id for req in (fake.creates if fake else [])),
        "fetches": tuple(fake.fetches if fake else ()),
        "cancels": tuple(fake.cancels if fake else ()),
        "updates": tuple(fake.updates if fake else ()),
        "active": tuple(sorted(i.law_id for i in roster.active_roster_items(USER))),
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        ),
    }


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _desk(html: str) -> str:
    marker = 'data-halted-subscription="desktop"'
    assert marker in html
    return unescape(html.split(marker, 1)[1].split('class="panel purchase"', 1)[0])


def _halted_client(tmp_path: Path) -> tuple[TestClient, FakeProvider]:
    app = _mu_app(tmp_path)
    fake = _attach_fake(app)
    client = TestClient(app)
    _sign_in(client)
    _seed_plus_then_halt(client)
    return client, fake


def test_halted_billing_is_current_plan_not_paused_home(tmp_path: Path) -> None:
    client, fake = _halted_client(tmp_path)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.subscription_status == "halted"
    assert snap.playground_block_reason == BLOCK_PAYMENT_HALTED
    page = client.get("/billing/subscriptions")
    assert page.status_code == 200
    html = unescape(page.text)
    desk = _desk(html)
    header = _header(html)
    assert 'data-halted-subscription="desktop"' in html
    assert 'data-plus-subscription="desktop"' not in html
    assert 'data-expired-subscription="desktop"' not in html
    assert PLAYGROUND_BILLING_PATH == "/billing/subscriptions"
    assert LIVE_CTA == "Manage subscription"
    assert LIVE_GATE.cta_href == PLAYGROUND_BILLING_PATH
    assert LIVE_HEADING in header
    assert "RecallC Plus" not in header
    assert "Free account" not in header
    assert 'href="/playground"' in header
    assert "is-active" in header.split('href="/playground"', 1)[1].split("</a>", 1)[0]
    assert "Playground · Your plan" in desk
    assert ">Playground plans<" in desk
    assert "Change your plan" not in html
    assert "RecallC Plus" in desk
    assert f"₹{CATALOG['plus'].price_inr}" in desk
    assert f"{CATALOG['plus'].playground_law_limit} laws active per month" in desk
    assert PLUS_TAG in desk
    assert ">Current plan<" in desk
    assert HALTED_LIFE in desk
    assert HALTED_LIFE == "Automatic retries have stopped"
    assert "Current paid period ends" in desk
    assert str(ACTIVE_END.date()) in desk or "2026-10-15" in desk
    assert 'data-halted-sub-current' in desk
    assert 'action="/billing/subscriptions/create"' not in desk
    assert 'action="/billing/subscriptions/change"' not in desk
    assert 'action="/billing/subscriptions/cancel"' not in desk
    assert "Subscribe to Plus" not in desk
    assert "Subscribe to Pro" not in desk
    assert "Subscribe to Max" not in desk
    assert "Switch to" not in desk
    assert "Your Playground is paused" not in desk
    assert LIVE_EXPIRED not in desk
    assert "Back to Constitution" not in desk
    assert "Due today" not in desk
    assert "Sections learned" not in desk
    assert fake.creates == []
    assert fake.fetches == []
    home = client.get(home_path())
    assert home.status_code == 200
    assert 'data-halted-playground="desktop"' in home.text
    for phrase in INVENTED:
        assert phrase not in desk, phrase


def test_halted_elapsed_period_stays_halted_on_billing(tmp_path: Path) -> None:
    client, _fake = _halted_client(tmp_path)
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None
    client.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        billing_period_start=EXPIRED_START,
        billing_period_end=EXPIRED_END,
    )
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.subscription_status == "halted"
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    html = unescape(client.get("/billing/subscriptions").text)
    assert 'data-halted-subscription="desktop"' in html
    assert 'data-expired-subscription="desktop"' not in html
    desk = _desk(html)
    assert HALTED_LIFE in desk
    assert ">Current plan<" in desk
    assert "Subscribe to Plus" not in desk
    assert LIVE_EXPIRED not in desk
    assert LIVE_HEADING in _header(html)


def test_halted_billing_get_is_read_only(tmp_path: Path) -> None:
    client, fake = _halted_client(tmp_path)
    before = _facts(client, fake)
    assert before["current"] is not None
    assert before["current"][1] == "halted"
    assert "ndps" in before["active"]
    page = client.get("/billing/subscriptions")
    assert page.status_code == 200
    after = _facts(client, fake)
    assert after == before
    again = client.get("/billing/subscriptions/")
    assert again.status_code == 200
    assert _facts(client, fake) == before
    assert fake.creates == []
    assert fake.fetches == []
    assert fake.cancels == []
    assert fake.updates == []


def test_halted_posts_do_not_mutate(tmp_path: Path) -> None:
    client, fake = _halted_client(tmp_path)
    before = _facts(client, fake)
    client.get("/billing/subscriptions")
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf
    created = client.post(
        CREATE_PATH,
        data={"csrf_token": csrf, "tier": "plus"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert created.headers.get("location") == "/billing/subscriptions?error=change_required"
    changed = client.post(
        CHANGE_PATH,
        data={"csrf_token": csrf, "tier": "pro"},
        follow_redirects=False,
    )
    assert changed.status_code == 303
    assert "/billing/subscriptions?error=" in (changed.headers.get("location") or "")
    cancelled = client.post(
        CANCEL_PATH,
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert cancelled.status_code == 303
    assert cancelled.headers.get("location") == "/billing/subscriptions?error=unpaid_cancel"
    assert _facts(client, fake) == before
    assert fake.creates == []
    assert fake.fetches == []
    assert fake.cancels == []
    assert fake.updates == []


def test_guest_free_plus_expired_paused_pending_are_not_halted_billing(
    tmp_path: Path,
) -> None:
    guest_html = TestClient(_mu_app(tmp_path / "guest")).get("/billing/subscriptions").text
    assert 'data-halted-subscription="desktop"' not in guest_html
    assert "Sign in to subscribe" in guest_html
    assert LIVE_HEADING not in _header(guest_html)

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/billing/subscriptions").text
    assert 'data-halted-subscription="desktop"' not in free_html
    assert "Subscribe to Plus" in free_html
    assert LIVE_HEADING not in _header(free_html)

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = unescape(plus.get("/billing/subscriptions").text)
    assert 'data-plus-subscription="desktop"' in plus_html
    assert 'data-halted-subscription="desktop"' not in plus_html
    assert "Change your plan" in plus_html
    assert "RecallC Plus" in _header(plus_html)
    assert "Switch to Pro" in plus_html

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(expired)
    stored = expired.app.state.subscriptions.get_current_subscription(USER)
    expired.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        status="expired",
        billing_period_start=EXPIRED_START,
        billing_period_end=EXPIRED_END,
    )
    expired_html = unescape(expired.get("/billing/subscriptions").text)
    assert 'data-expired-subscription="desktop"' in expired_html
    assert 'data-halted-subscription="desktop"' not in expired_html
    assert "Subscribe to Plus" in expired_html
    assert LIVE_HEADING not in expired_html

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused, status="paused")
    paused_html = paused.get("/billing/subscriptions").text
    assert 'data-halted-subscription="desktop"' not in paused_html
    assert "Subscription paused" in paused_html
    assert LIVE_HEADING not in paused_html

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    pending_html = pending.get("/billing/subscriptions").text
    assert 'data-halted-subscription="desktop"' not in pending_html
    assert "Payment retry in progress" in pending_html

    for status in ("created", "authenticated", "cancelled", "completed"):
        client = TestClient(_mu_app(tmp_path / status))
        _sign_in(client)
        _subscribe(client, status=status)
        html = client.get("/billing/subscriptions").text
        assert 'data-halted-subscription="desktop"' not in html
        assert LIVE_HEADING not in html


def test_halted_subscription_uses_shared_predicate_and_existing_routes() -> None:
    manage = MANAGE.read_text(encoding="utf-8")
    assert "halted_subscription" in manage
    assert 'data-halted-subscription="desktop"' in manage
    assert 'data-plus-subscription="desktop"' in manage
    assert 'data-expired-subscription="desktop"' in manage
    assert "Playground plans" in manage
    assert "Change your plan" in manage
    assert "current.lifecycle_message" in manage
    assert "current.billing_period_end" in manage
    assert LIVE_HEADING not in manage
    assert "Automatic retries have stopped" not in manage
    assert "Payment retries have stopped" not in manage
    halted_branch = manage.split("{% if halted_sub %}", 1)[1].split(
        "{% set expired_sub", 1
    )[0]
    assert 'action="/billing/subscriptions/create"' not in halted_branch
    assert 'action="/billing/subscriptions/change"' not in halted_branch
    assert 'action="/billing/subscriptions/cancel"' not in halted_branch
    assert "Subscribe to" not in halted_branch
    assert "Switch to" not in halted_branch
    assert 'action="/billing/subscriptions/create"' in manage
    assert 'action="/billing/subscriptions/change"' in manage
    assert 'action="/billing/subscriptions/cancel"' in manage
    routes = ROUTES.read_text(encoding="utf-8")
    page = routes.split("async def manage_page", 1)[1].split(
        "async def create_subscription", 1
    )[0]
    assert "request_is_halted_subscriber" in page
    assert "request_is_expired_subscriber" in page
    assert "request_is_active_plus" in page
    assert '"halted_subscription": halted_subscription' in page
    assert "BLOCK_PAYMENT_HALTED" in page
    assert "gate_view" in page
    assert "TERMINAL_STATUSES" in page
    assert "/resume" not in routes
    assert 'async def create_subscription' in routes
    assert 'async def change_subscription' in routes
    assert 'async def cancel_subscription' in routes
    deps = DEPS.read_text(encoding="utf-8")
    assert "def request_is_halted_subscriber" in deps
    assert HALTED_LIFE == LIFECYCLE_MESSAGES["halted"]
    css = PG_CSS.read_text(encoding="utf-8")
    assert '[data-halted-subscription="desktop"]' in css
    assert '[data-plus-subscription="desktop"]' in css
    assert '[data-expired-subscription="desktop"]' in css
    assert ".halted-sub-desk" not in css
    base = BASE.read_text(encoding="utf-8")
    assert "halted_billing" in base
    assert "halted_subscription" in base
    assert "halted_header_status" in base
    assert LIVE_HEADING not in base
    assert "playground.css?v=pg28" in base
    checkout = CHECKOUT.read_text(encoding="utf-8")
    assert "data-halted-subscription" not in checkout
    assert "data-halted-subscription" not in MOBILE.read_text(encoding="utf-8")


def test_plus_expired_and_halted_01_06_untouched() -> None:
    assert 'data-halted-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-halted-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-halted-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-halted-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-halted-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-halted-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-plus-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-expired-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in DASH.read_text(encoding="utf-8")
    for path in (LANDING, BROWSE, LAWS, BARE, ADD, HOME, GATE, DASH, CAL, PROFILE, SETTINGS):
        text = path.read_text(encoding="utf-8")
        assert "data-halted-subscription" not in text
        assert "halted_subscription" not in text
    add = ADD.read_text(encoding="utf-8")
    assert 'kind == "resume"' in add
    assert 'kind == "halted"' not in add


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


def test_halted_phone_billing_keeps_purchase_panel(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    _attach_fake(app)
    client = TestClient(app)
    _sign_in(client)
    _seed_plus_then_halt(client)
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
        page.goto(f"{origin}/billing/subscriptions", wait_until="networkidle")
        geo = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-halted-subscription="desktop"]');
              const panel = document.querySelector('.panel.purchase');
              return {
                marker: Boolean(desk),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                panelDisplay: panel ? getComputedStyle(panel).display : null,
                plus: Boolean(document.querySelector('[data-plus-subscription="desktop"]')),
                expired: Boolean(document.querySelector('[data-expired-subscription="desktop"]')),
                current: panel && /Current plan/.test(panel.innerText),
                life: panel && /Automatic retries have stopped/.test(panel.innerText),
                subscribe: /Subscribe to Plus/.test(document.body.innerText),
                switchPlan: /Switch to/.test(document.body.innerText),
              };
            }"""
        )
        browser.close()
    assert geo["marker"] is True
    assert geo["deskDisplay"] == "none"
    assert geo["panelDisplay"] != "none"
    assert geo["plus"] is False
    assert geo["expired"] is False
    assert geo["current"] is True
    assert geo["life"] is True
    assert geo["subscribe"] is False
    assert geo["switchPlan"] is False


def test_halted_subscription_screen07_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    _attach_fake(app)
    client = TestClient(app)
    _sign_in(client)
    _seed_plus_then_halt(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_subscription_screen07_1280.png"
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
        page.goto(f"{origin}/billing/subscriptions", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-halted-subscription="desktop"]');
              const plus = document.querySelector('[data-plus-subscription="desktop"]');
              const expired = document.querySelector('[data-expired-subscription="desktop"]');
              const panel = document.querySelector('.panel.purchase');
              const title = desk && desk.querySelector('.plus-sub-title');
              const name = desk && desk.querySelector('.plus-sub-name');
              const price = desk && desk.querySelector('.plus-sub-price');
              const cta = desk && desk.querySelector('.plus-sub-cta');
              const note = desk && desk.querySelector('.plus-sub-note');
              return {
                marker: Boolean(desk),
                plus: Boolean(plus),
                expired: Boolean(expired),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                panelDisplay: panel ? getComputedStyle(panel).display : null,
                title: title && title.textContent.trim(),
                eyebrow: desk && desk.querySelector('.plus-sub-eyebrow') &&
                  desk.querySelector('.plus-sub-eyebrow').textContent.trim(),
                name: name && name.textContent.trim(),
                price: price && price.textContent.replace(/\\s+/g, ' ').trim(),
                cta: cta && cta.textContent.trim(),
                ctaDisabled: cta && cta.disabled,
                life: note && note.textContent.trim(),
                period: desk && /Current paid period ends/.test(desk.innerText),
                header: document.querySelector('.account-menu-btn-status') &&
                  document.querySelector('.account-menu-btn-status').textContent.trim(),
                subscribe: desk && /Subscribe to/.test(desk.innerText),
                switchPlan: desk && /Switch to/.test(desk.innerText),
                changePlan: /Change your plan/.test(document.body.innerText),
                pausedHome: desk && /Your Playground is paused/.test(desk.innerText),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()
    assert geo["marker"] is True
    assert geo["plus"] is False
    assert geo["expired"] is False
    assert geo["deskDisplay"] != "none"
    assert geo["panelDisplay"] == "none"
    assert geo["title"] == "Playground plans"
    assert geo["eyebrow"] == "Playground · Your plan"
    assert geo["name"] == "RecallC Plus"
    assert geo["price"] and "₹199" in geo["price"]
    assert geo["cta"] == "Current plan"
    assert geo["ctaDisabled"] is True
    assert geo["life"] == HALTED_LIFE
    assert geo["period"] is True
    assert geo["header"] == LIVE_HEADING
    assert geo["subscribe"] is False
    assert geo["switchPlan"] is False
    assert geo["changePlan"] is False
    assert geo["pausedHome"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_halted_subscription_plus_regression_1280(tmp_path: Path) -> None:
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
    shot_path = artifact_dir / "halted_subscription_screen07_plus_regression_1280.png"
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
        page.goto(f"{origin}/billing/subscriptions", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-subscription="desktop"]');
              const halted = document.querySelector('[data-halted-subscription="desktop"]');
              const expired = document.querySelector('[data-expired-subscription="desktop"]');
              const title = plus && plus.querySelector('.plus-sub-title');
              return {
                plus: Boolean(plus),
                halted: Boolean(halted),
                expired: Boolean(expired),
                title: title && title.textContent.trim(),
                current: plus && /Current plan/.test(plus.innerText),
                switchPro: plus && /Switch to Pro/.test(plus.innerText),
                header: document.querySelector('.account-menu-btn-status') &&
                  document.querySelector('.account-menu-btn-status').textContent.trim(),
                haltedCopy: document.body.innerText.includes('Payment retries have stopped'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()
    assert geo["plus"] is True
    assert geo["halted"] is False
    assert geo["expired"] is False
    assert geo["title"] == "Change your plan"
    assert geo["current"] is True
    assert geo["switchPro"] is True
    assert geo["header"] == "RecallC Plus"
    assert geo["haltedCopy"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
