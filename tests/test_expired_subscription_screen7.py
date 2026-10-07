"""Expired cohort desktop /billing/subscriptions Screen 07.

Authorized: ChatGPT. Authenticated multiuser GET /billing/subscriptions after
a real Plus period ends. This is the plan/resubscribe page reached from
Expired Screen 06 "View Playground plans", not a second paused-home screen.
Hero copy stays established Playground plans + ended_message. Catalogue and
Subscribe to Plus/Pro/Max POST /billing/subscriptions/create are live.
Guest, Free, Plus Screen 07, halted, pending, paused, phone, Plus 01–11,
and Expired 01–06 stay unchanged. No new route.
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
from constitution_memorizer.entitlements.models import BLOCK_PAID_PERIOD_ENDED
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.urls import add_path
from constitution_memorizer.playground.view import (
    CONSTITUTION_HOME_PATH,
    PLAYGROUND_BILLING_PATH,
    gate_view,
)
from constitution_memorizer.subscriptions.catalog import list_subscription_products
from constitution_memorizer.subscriptions.config import SubscriptionPlanIds
from constitution_memorizer.subscriptions.routes import ENDED_MESSAGE
from constitution_memorizer.subscriptions.service import SubscriptionService
from constitution_memorizer.web.app import create_app
from tests.conftest import PLAYGROUND_TEST_NOW
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
PG_ROUTES = ROOT / "src/constitution_memorizer/playground/routes.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_GATE = gate_view(reason=BLOCK_PAID_PERIOD_ENDED)
LIVE_HEADING = LIVE_GATE.title
CATALOG = {row.tier: row for row in list_subscription_products()}
CREATE_PATH = "/billing/subscriptions/create"
INVENTED = (
    "Your plan expired",
    "Resume subscription",
    "Renew Plus",
    "Your Plus expired",
    "Premium",
    "Unlock all",
    "Free plan",
    "Change your plan",
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
    cancel_at_period_end: bool = False,
):
    return client.app.state.subscriptions.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        billing_period_start=period_start,
        billing_period_end=period_end,
        is_current=True,
        cancel_at_period_end=cancel_at_period_end,
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


def _seed_plus_then_expire(client: TestClient) -> None:
    _subscribe(client)
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    _expire(client)


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
            else (current.id, current.status, current.is_current, current.tier)
        ),
        "history": tuple(
            sorted((row.id, row.status, row.is_current, row.tier) for row in history)
        ),
        "creates": tuple(req.plan_id for req in (fake.creates if fake else [])),
        "fetches": tuple(fake.fetches if fake else ()),
        "active": tuple(sorted(i.law_id for i in roster.active_roster_items(USER))),
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        ),
        "progress": tuple(
            sorted(
                (p.source_locator, p.status)
                for p in overlay.list_progress(USER, "ndps")
            )
        ),
    }


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _desk(html: str) -> str:
    marker = 'data-expired-subscription="desktop"'
    assert marker in html
    return unescape(html.split(marker, 1)[1].split('class="panel purchase"', 1)[0])


def _expired_client(tmp_path: Path) -> tuple[TestClient, FakeProvider]:
    app = _mu_app(tmp_path)
    fake = _attach_fake(app)
    client = TestClient(app)
    _sign_in(client)
    _seed_plus_then_expire(client)
    return client, fake


def test_expired_billing_is_plan_chooser_not_paused_home(tmp_path: Path) -> None:
    client, fake = _expired_client(tmp_path)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    page = client.get("/billing/subscriptions")
    assert page.status_code == 200
    html = unescape(page.text)
    desk = _desk(html)
    header = _header(html)
    assert 'data-expired-subscription="desktop"' in html
    assert 'data-plus-subscription="desktop"' not in html
    assert "Change your plan" not in html
    assert "Current plan" not in html
    assert "data-plus-sub-current" not in html
    assert ">Playground plans<" in desk
    assert ENDED_MESSAGE in desk
    assert LIVE_HEADING in header
    assert "RecallC Plus" not in header
    assert "Free account" not in header
    assert 'href="/playground"' in header
    assert "is-active" in header.split('href="/playground"', 1)[1].split("</a>", 1)[0]
    assert PLAYGROUND_BILLING_PATH == "/billing/subscriptions"
    assert LIVE_GATE.cta_href == PLAYGROUND_BILLING_PATH
    assert f"₹{CATALOG['plus'].price_inr:,}" in desk or f"₹{CATALOG['plus'].price_inr}" in desk
    assert f"₹{CATALOG['pro'].price_inr:,}" in desk or f"₹{CATALOG['pro'].price_inr}" in desk
    assert f"₹{CATALOG['max'].price_inr:,}" in desk
    assert f"{CATALOG['plus'].playground_law_limit} laws active per month" in desk
    assert f"{CATALOG['pro'].playground_law_limit} laws active per month" in desk
    assert "Unlimited Playground" in desk
    assert "Subscribe to Plus" in desk
    assert "Subscribe to Pro" in desk
    assert "Subscribe to Max" in desk
    assert f'action="{CREATE_PATH}"' in desk
    assert 'name="csrf_token"' in desk
    assert 'name="tier" value="plus"' in desk
    assert 'name="tier" value="pro"' in desk
    assert 'name="tier" value="max"' in desk
    assert "/billing/subscriptions/change" not in desk
    assert "/resume" not in desk
    assert "Your Playground is paused" not in desk
    assert "View Playground plans" not in desk
    assert "Back to Constitution" not in desk
    assert CONSTITUTION_HOME_PATH not in desk
    assert fake.creates == []
    assert fake.fetches == []
    for phrase in INVENTED:
        assert phrase not in desk, phrase


def test_expired_billing_get_is_read_only(tmp_path: Path) -> None:
    client, fake = _expired_client(tmp_path)
    before = _facts(client, fake)
    assert before["current"] is not None
    assert before["current"][1] == "expired"
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


def test_expired_resubscribe_posts_create_and_archives_old_row(tmp_path: Path) -> None:
    client, fake = _expired_client(tmp_path)
    before = _facts(client, fake)
    old_id = before["current"][0]
    client.get("/billing/subscriptions")
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf
    denied = client.post(
        CREATE_PATH,
        data={"csrf_token": "nope", "tier": "plus"},
        follow_redirects=False,
    )
    assert denied.status_code == 403
    assert fake.creates == []
    posted = client.post(
        CREATE_PATH,
        data={"csrf_token": csrf, "tier": "plus"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    assert posted.headers.get("location") == "/billing/subscriptions/checkout"
    assert len(fake.creates) == 1
    assert fake.creates[0].plan_id == "plan_plus"
    current = client.app.state.subscriptions.get_current_subscription(USER)
    assert current is not None
    assert current.id != old_id
    assert current.status == "created"
    assert current.is_current is True
    old = client.app.state.subscriptions.get_subscription(USER, old_id)
    assert old is not None
    assert old.is_current is False
    assert old.status == "expired"
    history = client.app.state.subscriptions.list_subscription_history(USER)
    assert {row.id for row in history} == {old_id, current.id}
    roster_ids = {i.law_id for i in client.app.state.roster.active_roster_items(USER)}
    assert "ndps" in roster_ids


def test_guest_free_plus_halted_paused_stay_separate(tmp_path: Path) -> None:
    guest_html = TestClient(_mu_app(tmp_path / "guest")).get("/billing/subscriptions").text
    assert 'data-expired-subscription="desktop"' not in guest_html
    assert "Sign in to subscribe" in guest_html
    assert ENDED_MESSAGE not in guest_html
    assert LIVE_HEADING not in _header(guest_html)

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/billing/subscriptions").text
    assert 'data-expired-subscription="desktop"' not in free_html
    assert "Subscribe to Plus" in free_html
    assert ENDED_MESSAGE not in free_html
    assert LIVE_HEADING not in _header(free_html)

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = unescape(plus.get("/billing/subscriptions").text)
    assert 'data-plus-subscription="desktop"' in plus_html
    assert 'data-expired-subscription="desktop"' not in plus_html
    assert "Change your plan" in plus_html
    assert "RecallC Plus" in _header(plus_html)
    assert "Current plan" in plus_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/billing/subscriptions").text
    assert 'data-halted-subscription="desktop"' in halted_html
    assert 'data-expired-subscription="desktop"' not in halted_html
    assert "Automatic retries have stopped" in halted_html
    assert "Current plan" in halted_html
    assert "Payment retries have stopped" in halted_html
    assert LIVE_HEADING not in halted_html

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused, status="paused")
    paused_html = paused.get("/billing/subscriptions").text
    assert 'data-expired-subscription="desktop"' not in paused_html
    assert "Subscription paused" in paused_html
    assert LIVE_HEADING not in paused_html

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    pending_html = pending.get("/billing/subscriptions").text
    assert 'data-expired-subscription="desktop"' not in pending_html
    assert "Payment retry in progress" in pending_html

    for status in ("created", "authenticated", "cancelled", "completed"):
        client = TestClient(_mu_app(tmp_path / status))
        _sign_in(client)
        _subscribe(client, status=status)
        html = client.get("/billing/subscriptions").text
        assert 'data-expired-subscription="desktop"' not in html
        assert "Change your plan" not in html
        assert LIVE_HEADING not in html

    checkout_expired = TestClient(_mu_app(tmp_path / "co-exp"))
    _sign_in(checkout_expired)
    _subscribe(checkout_expired, status="expired")
    checkout_html = checkout_expired.get("/billing/subscriptions").text
    assert 'data-expired-subscription="desktop"' not in checkout_html
    assert "Subscription checkout expired" in checkout_html
    assert "Change your plan" not in checkout_html

    billed = _expired_client(tmp_path / "co")[0]
    bounced = billed.get("/billing/subscriptions/checkout", follow_redirects=False)
    assert bounced.status_code == 303
    assert bounced.headers.get("location") == "/billing/subscriptions"


def test_cancel_at_period_end_current_plus_is_not_expired_chooser(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    stored = _subscribe(
        client,
        period_start=EXPIRED_START,
        period_end=EXPIRED_END,
        cancel_at_period_end=True,
    )
    assert stored.status == "active"
    assert stored.is_current is True
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    html = unescape(client.get("/billing/subscriptions").text)
    assert 'data-expired-subscription="desktop"' not in html
    assert "Ends after the current paid cycle" in html
    assert "Current plan" in html
    assert "Change your plan" not in html


def test_expired_subscription_uses_shared_predicate_and_existing_create() -> None:
    manage = MANAGE.read_text(encoding="utf-8")
    assert "expired_subscription" in manage
    assert 'data-expired-subscription="desktop"' in manage
    assert 'data-plus-subscription="desktop"' in manage
    assert "Playground plans" in manage
    assert "Change your plan" in manage
    assert 'action="/billing/subscriptions/create"' in manage
    assert 'action="/billing/subscriptions/change"' in manage
    assert "Subscribe to {{ product.display_name }}" in manage
    assert "Your Playground is paused" not in manage
    assert "View Playground plans" not in manage
    routes = ROUTES.read_text(encoding="utf-8")
    page = routes.split("async def manage_page", 1)[1].split(
        "async def create_subscription", 1
    )[0]
    assert "request_is_expired_subscriber" in page
    assert "request_is_active_plus" in page
    assert '"plus_subscription": request_is_active_plus(request)' in page
    assert "TERMINAL_STATUSES" in page
    assert "ENDED_MESSAGE" in page
    assert "gate_view" in page
    assert "/resume" not in routes
    deps = DEPS.read_text(encoding="utf-8")
    assert "def request_is_expired_subscriber" in deps
    home = HOME.read_text(encoding="utf-8")
    assert "expired_gate.cta_href" in home
    view = VIEW.read_text(encoding="utf-8")
    assert 'cta_href=cta_href or PLAYGROUND_BILLING_PATH' in view or "PLAYGROUND_BILLING_PATH" in view
    assert PLAYGROUND_BILLING_PATH == "/billing/subscriptions"
    css = PG_CSS.read_text(encoding="utf-8")
    assert '[data-expired-subscription="desktop"]' in css
    assert 'data-plus-subscription="desktop"' in css
    base = BASE.read_text(encoding="utf-8")
    assert "expired_billing" in base
    assert "expired_header_status" in base
    assert "plus_billing" in base
    checkout = CHECKOUT.read_text(encoding="utf-8")
    assert "data-expired-subscription" not in checkout
    assert SubscriptionPlanIds is not None


def test_plus_screens_and_expired_01_06_untouched() -> None:
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
    assert 'data-plus-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-plus-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-plus-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    for path in (LANDING, BROWSE, LAWS, BARE, ADD, HOME, DASH, CAL, PROFILE, SETTINGS):
        text = path.read_text(encoding="utf-8")
        assert "data-expired-subscription" not in text
    assert "data-expired-subscription" not in GATE.read_text(encoding="utf-8")
    assert "data-expired-subscription" not in MOBILE.read_text(encoding="utf-8")
    assert "data-expired-subscription" not in CHECKOUT.read_text(encoding="utf-8")
    home_fn = PG_ROUTES.read_text(encoding="utf-8").split(
        "async def playground_home", 1
    )[1].split("async def playground_roster", 1)[0]
    assert '"plus_playground": request_is_active_plus(request)' in home_fn
    add = ADD.read_text(encoding="utf-8")
    assert 'kind == "resume"' in add


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


def test_expired_phone_billing_keeps_purchase_panel(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    _attach_fake(app)
    client = TestClient(app)
    _sign_in(client)
    _seed_plus_then_expire(client)
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
              const desk = document.querySelector('[data-expired-subscription="desktop"]');
              const panel = document.querySelector('.panel.purchase');
              return {
                marker: Boolean(desk),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                panelDisplay: panel ? getComputedStyle(panel).display : null,
                plus: Boolean(document.querySelector('[data-plus-subscription="desktop"]')),
                subscribe: /Subscribe to Plus/.test(document.body.innerText),
              };
            }"""
        )
        browser.close()
    assert geo["marker"] is True
    assert geo["deskDisplay"] == "none"
    assert geo["panelDisplay"] != "none"
    assert geo["plus"] is False
    assert geo["subscribe"] is True


def test_expired_subscription_screen07_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    _attach_fake(app)
    client = TestClient(app)
    _sign_in(client)
    _seed_plus_then_expire(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "expired_subscription_screen07_1280.png"
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
              const desk = document.querySelector('[data-expired-subscription="desktop"]');
              const plus = document.querySelector('[data-plus-subscription="desktop"]');
              const panel = document.querySelector('.panel.purchase');
              const title = desk && desk.querySelector('.plus-sub-title');
              const lede = desk && desk.querySelector('.plus-sub-lede');
              const ctas = desk ? [...desk.querySelectorAll('.expired-sub-cta')] : [];
              return {
                marker: Boolean(desk),
                plus: Boolean(plus),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                panelDisplay: panel ? getComputedStyle(panel).display : null,
                title: title && title.textContent.trim(),
                lede: lede && lede.textContent.trim(),
                ctaText: ctas.map((el) => el.textContent.trim()),
                header: document.querySelector('.account-menu-btn-status') &&
                  document.querySelector('.account-menu-btn-status').textContent.trim(),
                changePlan: document.body.innerText.includes('Change your plan'),
                currentPlan: desk && /Current plan/.test(desk.innerText),
                pausedHome: desk && /Your Playground is paused/.test(desk.innerText),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()
    assert geo["marker"] is True
    assert geo["plus"] is False
    assert geo["deskDisplay"] != "none"
    assert geo["panelDisplay"] == "none"
    assert geo["title"] == "Playground plans"
    assert geo["lede"] == ENDED_MESSAGE
    assert geo["ctaText"] == ["Subscribe to Plus", "Subscribe to Pro", "Subscribe to Max"]
    assert geo["header"] == LIVE_HEADING
    assert geo["changePlan"] is False
    assert geo["currentPlan"] is False
    assert geo["pausedHome"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_expired_subscription_plus_regression_1280(tmp_path: Path) -> None:
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
    shot_path = artifact_dir / "expired_subscription_screen07_plus_regression_1280.png"
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
              const expired = document.querySelector('[data-expired-subscription="desktop"]');
              const title = plus && plus.querySelector('.plus-sub-title');
              return {
                plus: Boolean(plus),
                expired: Boolean(expired),
                title: title && title.textContent.trim(),
                current: plus && /Current plan/.test(plus.innerText),
                header: document.querySelector('.account-menu-btn-status') &&
                  document.querySelector('.account-menu-btn-status').textContent.trim(),
                ended: document.body.innerText.includes('Previous subscription ended'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()
    assert geo["plus"] is True
    assert geo["expired"] is False
    assert geo["title"] == "Change your plan"
    assert geo["current"] is True
    assert geo["header"] == "RecallC Plus"
    assert geo["ended"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
