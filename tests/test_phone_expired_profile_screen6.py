"""Phone Expired Profile Screen 06 (CTA map expired/06-screen).

Authorized: ChatGPT. Authenticated expired GET /profile at 390x844.
Desktop Expired Screen 10 is the functional contract. Live identity,
playground_subscription_card paid-period-ended copy, and Resume
Playground /billing/subscriptions win over the map. Guest, Free
signedIn 06, Plus 06, Halted, Pro, and desktop 10 stay on their own
wrappers. No S2-1.
"""

from __future__ import annotations

import re
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
from constitution_memorizer.entitlements.models import (
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
)
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.view import (
    PLAYGROUND_BILLING_PATH,
    gate_view,
    playground_subscription_card,
)
from constitution_memorizer.web.app import create_app
from tests.test_playground_m8 import _seed_progress
from tests.test_roster_m5a import _confirm_add, _csrf

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
AUTH = ROOT / "src/constitution_memorizer/auth/routes.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_HEADING = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
ENDED_BODY = "This paid period has ended. Playground stays saved until you resume."
LOCATOR = "ndps:section:8:clause:a"
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
)
RENDER_INVENTED = (
    "Plan ended 31 August",
    "Plan ended 12 August",
    "Resume your Playground",
    "Resume anytime; nothing resets",
    "saved exactly as you left it",
    "Premium",
    "Unlock all",
    "8/10",
    "2 of 3",
    "See plans",
    "No plan yet",
    "/billing/manage",
    "uses this Playground month",
    "RecallC Core",
)
INVENTED_MARKUP = RENDER_INVENTED + ("September 2026", "new spaces open")


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


def _seed_ndps(client: TestClient) -> None:
    assert _confirm_add(client, "ndps").status_code == 303
    posted = client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "unit": LOCATOR, "section": "1"},
        follow_redirects=False,
    )
    assert posted.status_code in {200, 303}
    _seed_progress(
        client.app.state.playground,
        USER,
        "ndps",
        LOCATOR,
        status="review",
        interval_days=1,
        next_revision="2026-09-16",
        times_completed=1,
        learned_at="2026-09-16",
    )


def _plus_then_expire(client: TestClient) -> None:
    _subscribe(client)
    _seed_ndps(client)
    _expire(client)


def _expired_client(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_expire(client)
    return client


def _tabs(html: str) -> str:
    return html.split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 1
    )[1].split("</nav>", 1)[0]


def _account_list(html: str) -> str:
    return html.split("data-profile-account", 1)[1].split("</div>", 1)[0]


def _identity(html: str) -> str:
    return html.split("data-profile-identity", 1)[1].split("</article>", 1)[0]


def _subscription(html: str) -> str:
    return html.split("data-profile-subscription", 1)[1]


def _live_card(client: TestClient):
    snap = client.app.state.entitlement_service.resolve(USER)
    return playground_subscription_card(snap)


def _facts(client: TestClient) -> dict:
    snap = client.app.state.entitlement_service.resolve(USER)
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    svc = getattr(client.app.state, "device_service", None)
    device_ids = ()
    if svc is not None:
        device_ids = tuple(sorted(str(row.id) for row in svc.list_devices(USER)))
    return {
        "subscription": None
        if stored is None
        else (stored.id, stored.status, stored.tier, stored.is_current),
        "roster": tuple(sorted(i.law_id for i in roster.active_roster_items(USER))),
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        ),
        "selection": tuple(
            sorted(s.source_locator for s in overlay.list_selection(USER, "ndps"))
        ),
        "devices": device_ids,
        "can_open": snap.can_open_playground,
        "reason": snap.playground_block_reason,
    }


def _watch_ensure(client: TestClient) -> list[str]:
    calls: list[str] = []
    svc = getattr(client.app.state, "device_service", None)
    if svc is None:
        return calls
    orig = svc.ensure_current_device

    def wrapped(*args, **kwargs):
        calls.append("ensure_current_device")
        return orig(*args, **kwargs)

    svc.ensure_current_device = wrapped  # type: ignore[method-assign]
    return calls


def _assert_no_invented(html: str) -> None:
    text = unescape(html)
    for phrase in RENDER_INVENTED:
        assert phrase not in text, phrase
    assert ">Subscribe<" not in text
    assert "Change plan" not in text


def test_phone_expired_profile_is_live_screen10_contract(tmp_path: Path) -> None:
    client = _expired_client(tmp_path)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert snap.can_open_playground is False
    before = _facts(client)
    ensure_calls = _watch_ensure(client)
    page = client.get("/profile")
    assert page.status_code == 200
    assert _facts(client) == before
    assert ensure_calls == []
    html = unescape(page.text)
    assert 'data-expired-profile="desktop"' in html
    assert "data-signed-in-profile" in html
    assert "data-plus-profile" not in html
    assert "data-halted-profile" not in html
    assert 'data-mscreen="account"' in html
    assert 'data-phone-profile="guest"' not in html
    identity = _identity(html)
    assert "Sanjay" in identity
    assert "Signed in with Google" in identity
    assert "Plan ended" not in identity
    assert 'href="/profile?edit=name"' in identity
    assert "Edit name" in identity
    account = _account_list(html)
    assert 'href="/profile"' in account
    assert "Sanjay" in account
    assert 'href="/profile/security/devices"' in account
    assert "Devices" in account
    assert "2 of 3" not in account
    assert " of " in account or "device" in account.lower()
    assert 'href="/settings"' in account
    assert "Learning preferences" in account
    assert "data-report-open" in account
    assert 'data-report-section="Profile"' in account
    report_btn = account.split("data-report-open", 1)[1].split("</button>", 1)[0]
    assert "href=" not in report_btn
    assert "data-open-signout" in account
    assert ">Sign out<" in account
    card = _live_card(client)
    assert card.show is True
    assert card.chip == "PAUSED"
    assert card.chip_kind == "paused"
    assert card.cta_label == "Resume Playground"
    assert card.cta_href == PLAYGROUND_BILLING_PATH
    assert not card.stat_big
    assert card.body == ENDED_BODY
    sub = _subscription(html)
    assert card.title in sub
    assert "RecallC Plus" in sub
    assert f">{card.chip}<" in sub
    assert f'data-chip="{card.chip_kind}"' in sub
    assert card.body in sub
    assert card.cta_label in sub
    assert f'href="{card.cta_href}"' in sub
    assert PLAYGROUND_BILLING_PATH == "/billing/subscriptions"
    assert "Change plan" not in html
    assert "Manage plan" not in sub
    assert "Subscribe" not in sub
    assert "pg-sub-stat" not in sub
    assert not re.search(r"\d+/\d+", sub)
    assert "8/10" not in sub
    assert "0/10" not in sub
    assert "1/10" not in sub
    assert "new spaces open" not in sub
    assert "Google" in html
    assert "a@example.com" in html
    assert 'value="reset_progress"' in html
    assert 'value="delete_account"' in html
    assert 'id="signout-modal"' in html
    assert 'action="/logout"' in html
    assert "data-report-overlay" in html
    tabs = _tabs(html)
    for label_text, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        assert label_text in tabs
    profile_tab = tabs.split('href="/profile"', 1)[1].split("</a>", 1)[0]
    assert "is-active" in profile_tab
    assert 'aria-current="page"' in profile_tab
    assert "data-expired-profile-phone-tabs" not in html
    _assert_no_invented(html)
    assert _facts(client) == before


def test_phone_expired_profile_does_not_call_plus_capacity_helper() -> None:
    auth = AUTH.read_text(encoding="utf-8")
    overlay = auth.split("async def profile_get", 1)[1].split(
        "async def profile_post", 1
    )[0]
    assert "request_is_expired_subscriber" in overlay
    assert "playground_subscription_card(snapshot)" in overlay
    assert overlay.find("expired_profile") < overlay.find("if plus_profile:")
    plus_block = overlay.split("if plus_profile:", 1)[1]
    assert "plus_profile_subscription_card(" in plus_block
    assert "expired_profile" not in plus_block.split("return templates", 1)[0]
    view = VIEW.read_text(encoding="utf-8")
    ended = view.split("if reason == BLOCK_PAID_PERIOD_ENDED:", 1)[1].split(
        "status = str", 1
    )[0]
    assert 'chip="PAUSED"' in ended
    assert 'cta_label="Resume Playground"' in ended
    assert "cta_href=PLAYGROUND_BILLING_PATH" in ended
    assert ENDED_BODY in ended
    helper = view.split("def plus_profile_subscription_card", 1)[1].split(
        "def roster_law_cards", 1
    )[0]
    assert "peek_capacity" in helper
    assert "Change plan" in helper


def test_phone_expired_profile_edit_name_and_destinations(tmp_path: Path) -> None:
    client = _expired_client(tmp_path)
    edit = client.get("/profile?edit=name")
    assert edit.status_code == 200
    html = edit.text
    assert 'data-expired-profile="desktop"' in html
    assert 'id="display_name"' in html
    assert "Save name" in html
    assert 'action="/profile"' in html
    posted = client.post(
        "/profile",
        data={**_csrf(client), "action": "save", "display_name": "Priya"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    assert "/profile" in (posted.headers.get("location") or "")
    saved = unescape(client.get("/profile").text)
    assert "Priya" in saved
    assert "Save name" not in saved
    devices = client.get("/profile/security/devices", follow_redirects=False)
    assert devices.status_code == 200
    settings = client.get("/settings", follow_redirects=False)
    assert settings.status_code == 200
    billing = client.get(PLAYGROUND_BILLING_PATH, follow_redirects=False)
    assert billing.status_code == 200
    assert 'data-expired-subscription="desktop"' in billing.text
    missing = client.get("/billing/manage", follow_redirects=False)
    assert missing.status_code == 404
    out = TestClient(_mu_app(tmp_path / "out"))
    _sign_in(out)
    _plus_then_expire(out)
    logged = out.post(
        "/logout",
        data=_csrf(out),
        follow_redirects=False,
    )
    assert logged.status_code in {303, 302}
    assert out.cookies.get(SESSION_COOKIE_NAME) in {None, ""}


def test_phone_expired_profile_get_does_not_mutate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _expired_client(tmp_path)
    roster = client.app.state.roster
    writes: list[str] = []
    real_ensure = roster.ensure_current_period
    real_capacity = roster.capacity
    ensure_calls = _watch_ensure(client)

    def ensure(*args, **kwargs):
        writes.append("ensure")
        return real_ensure(*args, **kwargs)

    def capacity(*args, **kwargs):
        writes.append("capacity")
        return real_capacity(*args, **kwargs)

    monkeypatch.setattr(roster, "ensure_current_period", ensure)
    monkeypatch.setattr(roster, "capacity", capacity)
    before = _facts(client)
    assert "ndps" in before["roster"]
    assert before["selection"]
    assert before["can_open"] is False
    assert before["reason"] == BLOCK_PAID_PERIOD_ENDED
    html = unescape(client.get("/profile").text)
    assert 'data-expired-profile="desktop"' in html
    assert writes == []
    assert ensure_calls == []
    assert _facts(client) == before


def test_guest_free_plus_halted_pro_paused_pending_stay_separate(
    tmp_path: Path,
) -> None:
    guest = TestClient(_guest_app(tmp_path / "guest")).get("/profile")
    assert guest.status_code == 200
    guest_html = guest.text
    assert 'data-phone-profile="guest"' in guest_html
    assert "data-signed-in-profile" not in guest_html
    assert 'data-expired-profile="desktop"' not in guest_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = unescape(free.get("/profile").text)
    assert "data-signed-in-profile" in free_html
    assert "data-expired-profile" not in free_html
    assert ">Subscribe<" in free_html
    assert "Change plan" not in free_html
    assert "Resume Playground" not in free_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = unescape(plus.get("/profile").text)
    assert 'data-plus-profile="desktop"' in plus_html
    assert "data-expired-profile" not in plus_html
    assert "Change plan" in plus_html
    plus_sub = _subscription(plus_html)
    assert ">ACTIVE<" in plus_sub
    assert "Resume Playground" not in plus_sub

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    stored = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )
    halted_html = unescape(halted.get("/profile").text)
    assert 'data-halted-profile="desktop"' in halted_html
    assert "data-expired-profile" not in halted_html
    assert "data-plus-profile" not in halted_html
    halted_card = playground_subscription_card(
        halted.app.state.entitlement_service.resolve(USER)
    )
    halted_gate = gate_view(reason=BLOCK_PAYMENT_HALTED)
    assert halted_card.chip == "ON HOLD"
    halted_sub = _subscription(halted_html)
    assert "Manage subscription" in halted_sub
    assert halted_gate.cta_label in halted_sub
    assert "Resume Playground" not in halted_html
    assert "Change plan" not in halted_sub

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = unescape(pro.get("/profile").text)
    assert "data-expired-profile" not in pro_html
    assert "data-plus-profile" not in pro_html
    assert "RecallC Pro" in pro_html
    assert "Manage plan" in pro_html
    assert "Change plan" not in pro_html

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused)
    stored_p = paused.app.state.subscriptions.get_current_subscription(USER)
    paused.app.state.subscriptions.update_subscription_state(
        USER, stored_p.id, status="paused"
    )
    paused_html = unescape(paused.get("/profile").text)
    assert 'data-expired-profile="desktop"' not in paused_html
    paused_card = playground_subscription_card(
        paused.app.state.entitlement_service.resolve(USER)
    )
    assert paused_card.chip == "PAUSED"
    assert paused_card.body in paused_html
    assert ENDED_BODY not in paused_html

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    pending_html = unescape(pending.get("/profile").text)
    assert 'data-expired-profile="desktop"' not in pending_html
    assert "PENDING" in pending_html
    assert "Manage subscription" in pending_html
    assert "Change plan" not in pending_html


def test_phone_expired_profile_css_is_breakpoint_scoped() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    assert "is expired/06-screen:" in css
    desk = css.split("expired/10-screen", 1)[1].split("is expired/06-screen:", 1)[0]
    assert "@media (min-width: 561px)" in desk
    assert "@media (max-width: 560px)" not in desk
    assert "var(--pg-teal-dark)" in desk
    assert "[data-halted-profile" in desk
    phone_block = css.split("is expired/06-screen:", 1)[1].split(
        "plus/11-screen", 1
    )[0]
    assert "@media (max-width: 560px)" in phone_block
    assert "@media (min-width: 561px)" not in phone_block
    assert '[data-expired-profile="desktop"]' in phone_block
    assert "[data-halted-profile" not in phone_block
    assert "[data-plus-profile" not in phone_block
    assert "safe-area-inset-bottom" in phone_block
    assert "overflow-x: hidden" in phone_block
    assert "var(--m-tabbar, 60px)" in phone_block
    assert ".mobile-tabbar" in phone_block
    assert "grid-template-columns: repeat(5, 1fr)" in phone_block
    assert "position: fixed" in phone_block
    assert "si-profile-desk-only" in phone_block
    assert "display: flex !important" in phone_block
    assert ".link-btn" in phone_block
    assert "var(--pg-teal-dark)" in phone_block
    assert "var(--pg-teal-border)" in phone_block
    assert "#0e7569" not in phone_block
    assert "#3a3a38" not in phone_block
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", phone_block) is None
    assert "display: contents" not in phone_block
    assert "[data-expired-profile-phone]" not in css
    plus_phone = css.split("is plus/06-screen:", 1)[1].split(
        "expired/10-screen", 1
    )[0]
    assert "[data-expired-profile" not in plus_phone
    assert "@media (max-width: 560px)" in plus_phone
    mobile = MOBILE.read_text(encoding="utf-8")
    generic, _, rest = mobile.partition("is signedIn/06-screen:")
    assert "is expired/06-screen:" not in generic
    phone_free = rest.split("/* R1 — Playground phone shell", 1)[0]
    assert ":not([data-expired-profile])" in phone_free
    assert 'data-expired-profile="desktop"] {' not in phone_free
    assert "is expired/06-screen:" not in phone_free
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", phone_free) is None
    phone_profile = mobile.split(
        'body[data-mscreen="account"] .profile-panel > .display {', 1
    )[1].split("}", 1)[0]
    assert "font-size: 22px" in phone_profile
    assert "is expired/06-screen:" not in STYLES.read_text(encoding="utf-8")
    src = PROFILE.read_text(encoding="utf-8")
    assert 'data-expired-profile="desktop"' in src
    assert "data-expired-profile-phone" not in src
    for phrase in INVENTED_MARKUP:
        assert phrase not in src, phrase
    assert "{{ playground_subscription.cta_href }}" in src
    assert "{{ playground_subscription.cta_label }}" in src
    assert 'href="/profile?edit=name"' in src
    assert "data-report-open" in src
    assert 'action="/logout"' in src
    assert "Resume Playground" not in src
    assert "Change plan" not in src
    assert "PAUSED" not in src
    assert "Plan ended" not in src
    auth = AUTH.read_text(encoding="utf-8")
    get = auth.split("async def profile_get", 1)[1].split(
        "async def profile_post", 1
    )[0]
    assert "plus_profile_subscription_card" in get
    assert "ensure_current_device" not in get
    post = auth.split("async def profile_post", 1)[1]
    assert "reset_learning_progress" in post
    assert "delete_account" in post
    assert "reset_learning_progress" not in get
    assert "def request_is_expired_subscriber" in DEPS.read_text(encoding="utf-8")
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg50" in base
    assert "playground.css?v=pg45" not in base
    assert "styles.css?v=main88" in base
    assert "mobile.css?v=mob107" in base
    assert "data-expired-profile-phone-tabs" not in base
    first_bar = base.split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 2
    )[2].split("</nav>", 1)[0]
    assert 'href="/profile"' in first_bar
    assert "path.startswith('/profile')" in first_bar
    assert "data-expired-profile-phone-tabs" not in first_bar
    assert "data-expired-bareact-phone-tabs" not in first_bar


def _above_tab(page, selector: str) -> dict:
    page.locator(selector).scroll_into_view_if_needed()
    page.wait_for_timeout(40)
    return page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          const tabs = document.querySelector('.mobile-tabbar');
          const cs = tabs ? getComputedStyle(tabs) : null;
          const r = el && el.getBoundingClientRect();
          const t = tabs && tabs.getBoundingClientRect();
          return {
            tabsFixed: Boolean(cs && cs.position === 'fixed'),
            overflow: document.documentElement.scrollWidth
              > document.documentElement.clientWidth,
            above: Boolean(el && tabs && r && t && r.bottom <= t.top + 8),
            ctaHref: (
              document.querySelector('[data-profile-subscription] a.pg-btn') || {}
            ).getAttribute && document.querySelector(
              '[data-profile-subscription] a.pg-btn'
            ).getAttribute('href'),
          };
        }""",
        selector,
    )


def _clearance(page) -> dict:
    reset = _above_tab(page, "[data-open-reset]")
    delete = _above_tab(page, "[data-open-delete]")
    return {
        "tabsFixed": reset["tabsFixed"] and delete["tabsFixed"],
        "overflow": reset["overflow"] or delete["overflow"],
        "resetAbove": reset["above"],
        "deleteAbove": delete["above"],
        "ctaHref": delete["ctaHref"],
    }


def _screenshot(page, path: Path, *, attempts: int = 5) -> None:
    last: OSError | None = None
    for index in range(attempts):
        try:
            page.screenshot(path=str(path), full_page=False)
            return
        except OSError as exc:
            last = exc
            time.sleep(0.4 * (index + 1))
    assert last is not None
    raise last


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


_PHONE_GEO = """() => {
  const panel = document.querySelector('[data-expired-profile="desktop"]');
  const header = document.querySelector('.site-header');
  const topbar = panel && panel.querySelector(':scope > .mobile-topbar');
  const tabs = document.querySelector('.mobile-tabbar');
  const tabLinks = tabs ? [...tabs.querySelectorAll('a.mobile-tab')] : [];
  const active = tabs && tabs.querySelector('.mobile-tab.is-active');
  const identity = document.querySelector('[data-profile-identity]');
  const account = document.querySelector('[data-profile-account]');
  const sub = document.querySelector('[data-profile-subscription]');
  const edit = identity && identity.querySelector('a[href="/profile?edit=name"]');
  const cta = sub && sub.querySelector('a.pg-btn');
  const report = account && account.querySelector('[data-report-open]');
  const cardSignout = account && account.querySelector('[data-open-signout]');
  const lowerSignout = document.querySelector(
    '.account-actions > li:has([data-open-signout])'
  );
  const reset = document.querySelector('[data-open-reset]');
  const remove = document.querySelector('[data-open-delete]');
  const devices = account && account.querySelector(
    'a[href="/profile/security/devices"]'
  );
  const prefs = account && account.querySelector('a[href="/settings"]');
  const identityBox = identity && identity.getBoundingClientRect();
  const accountBox = account && account.getBoundingClientRect();
  const subBox = sub && sub.getBoundingClientRect();
  const tabBox = tabs && tabs.getBoundingClientRect();
  const focusable = [...(panel ? panel.querySelectorAll(
    'a[href], button:not([disabled]), input, select, textarea'
  ) : [])].filter((el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  });
  const owner = (el) => {
    if (el.closest('[data-profile-identity]')) return 'identity';
    if (el.closest('[data-profile-account]')) return 'account';
    if (el.closest('[data-profile-subscription]')) return 'subscription';
    return 'other';
  };
  const visual = [
    { name: 'identity', top: identityBox && identityBox.top },
    { name: 'account', top: accountBox && accountBox.top },
    { name: 'subscription', top: subBox && subBox.top },
  ].sort((a, b) => (a.top || 0) - (b.top || 0)).map((row) => row.name);
  const focusBlocks = [];
  for (const el of focusable) {
    const name = owner(el);
    if (name === 'other') continue;
    if (focusBlocks[focusBlocks.length - 1] !== name) focusBlocks.push(name);
  }
  const text = panel ? (panel.innerText || '') : '';
  const stat = sub && sub.querySelector('.pg-sub-stat');
  return {
    present: Boolean(panel),
    plus: Boolean(document.querySelector('[data-plus-profile="desktop"]')),
    halted: Boolean(document.querySelector('[data-halted-profile="desktop"]')),
    headerDisplay: header ? getComputedStyle(header).display : null,
    topbarDisplay: topbar ? getComputedStyle(topbar).display : null,
    tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
    tabsPosition: tabs ? getComputedStyle(tabs).position : null,
    tabLabels: tabLinks.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
    tabHrefs: tabLinks.map((el) => el.getAttribute('href')),
    profileActive: active && active.textContent.replace(/\\s+/g, ' ').trim(),
    dedicatedTabs: Boolean(
      document.querySelector('[data-expired-profile-phone-tabs]')
    ),
    name: identity && (identity.innerText || ''),
    editDisplay: edit ? getComputedStyle(edit).display : null,
    editHref: edit && edit.getAttribute('href'),
    ctaText: cta && (cta.textContent || '').replace(/\\s+/g, ' ').trim(),
    ctaHref: cta && cta.getAttribute('href'),
    subTitle: sub && (sub.querySelector('h2') || {}).textContent,
    chip: sub && (sub.querySelector('.pg-sub-chip') || {}).textContent,
    chipKind: sub && (sub.querySelector('.pg-sub-chip') || {}).getAttribute
      && sub.querySelector('.pg-sub-chip').getAttribute('data-chip'),
    statPresent: Boolean(stat) && getComputedStyle(stat).display !== 'none',
    stat: stat && (stat.innerText || '').replace(/\\s+/g, ' ').trim(),
    body: sub && ((sub.querySelector('.pg-lede') || {}).innerText || ''),
    reportDisplay: report ? getComputedStyle(report).display : null,
    cardSignoutDisplay: cardSignout
      ? getComputedStyle(cardSignout).display
      : null,
    lowerSignoutDisplay: lowerSignout
      ? getComputedStyle(lowerSignout).display
      : null,
    resetDisplay: reset ? getComputedStyle(reset).display : null,
    deleteDisplay: remove ? getComputedStyle(remove).display : null,
    devicesHref: devices && devices.getAttribute('href'),
    prefsHref: prefs && prefs.getAttribute('href'),
    visual,
    focusBlocks,
    identityTop: identityBox && identityBox.top,
    accountTop: accountBox && accountBox.top,
    subTop: subBox && subBox.top,
    overflow: document.documentElement.scrollWidth
      > document.documentElement.clientWidth,
    mockEnded: /Plan ended/.test(text),
    mockResume: /Resume your Playground/.test(text),
    subscribe: />Subscribe<|Subscribe to add Bare Acts/.test(text),
    changePlan: /Change plan/.test(text),
    signinMethod: /Sign-in method/.test(text) && /Google/.test(text),
    tabCount: tabLinks.length,
    tabTop: tabBox && tabBox.top,
  };
}"""


def test_phone_expired_profile_screen06_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _plus_then_expire(client)
    before = _facts(client)
    card = _live_card(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_expired_profile_screen06_390x844.png"
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
        page.goto(f"{origin}/profile", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(_PHONE_GEO)
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)

        page.locator('[data-profile-account] [data-open-signout]').click()
        signout_open = page.evaluate(
            """() => {
              const modal = document.querySelector('#signout-modal');
              return Boolean(modal && modal.open);
            }"""
        )
        logout_action = page.evaluate(
            """() => {
              const form = document.querySelector('#signout-modal form');
              return form && form.getAttribute('action');
            }"""
        )
        if signout_open:
            page.locator("#signout-modal [data-close-dialog]").click()

        page.locator('[data-profile-account] [data-report-open]').click()
        report_open = page.evaluate(
            """() => {
              const overlay = document.querySelector('[data-report-overlay]');
              return Boolean(overlay && !overlay.hasAttribute('hidden'));
            }"""
        )
        report_path = page.evaluate("() => location.pathname")
        page.locator("[data-rc-close]").click()

        page.locator("[data-open-reset]").click()
        reset_open = page.evaluate(
            """() => {
              const modal = document.querySelector('#reset-modal');
              return Boolean(modal && modal.open);
            }"""
        )
        reset_action = page.evaluate(
            """() => {
              const form = document.querySelector('#reset-modal form');
              const action = form && form.querySelector('[name="action"]');
              return {
                href: form && form.getAttribute('action'),
                value: action && action.getAttribute('value'),
              };
            }"""
        )
        if reset_open:
            page.locator("#reset-modal [data-close-dialog]").click()
        page.locator("[data-open-delete]").click()
        delete_open = page.evaluate(
            """() => {
              const modal = document.querySelector('#delete-modal');
              return Boolean(modal && modal.open);
            }"""
        )
        delete_action = page.evaluate(
            """() => {
              const form = document.querySelector('#delete-modal form');
              const action = form && form.querySelector('[name="action"]');
              return {
                href: form && form.getAttribute('action'),
                value: action && action.getAttribute('value'),
              };
            }"""
        )
        if delete_open:
            page.locator("#delete-modal [data-close-dialog]").click()

        page.locator('[data-profile-account] a[href="/profile/security/devices"]').click()
        page.wait_for_url("**/profile/security/devices**", timeout=8000)
        devices_path = page.evaluate("() => location.pathname")
        page.goto(f"{origin}/profile", wait_until="networkidle")
        page.locator('[data-profile-account] a[href="/settings"]').click()
        page.wait_for_url("**/settings**", timeout=8000)
        settings_path = page.evaluate("() => location.pathname")
        page.goto(f"{origin}/profile", wait_until="networkidle")
        page.locator('[data-profile-subscription] a.pg-btn').click()
        page.wait_for_url("**/billing/subscriptions**", timeout=8000)
        billing_path = page.evaluate("() => location.pathname")

        page.goto(f"{origin}/profile", wait_until="networkidle")
        tall = _clearance(page)
        page.set_viewport_size({"width": 390, "height": 700})
        page.wait_for_timeout(80)
        short = _clearance(page)
        browser.close()

    assert geo["present"] is True
    assert geo["plus"] is False
    assert geo["halted"] is False
    assert geo["headerDisplay"] == "none"
    assert geo["topbarDisplay"] == "none"
    assert geo["tabsDisplay"] != "none"
    assert geo["tabsPosition"] == "fixed"
    assert geo["tabLabels"] == ["Today", "Browse", "Playground", "Calendar", "Profile"]
    assert geo["tabHrefs"] == [href for _, href in TAB_HREFS]
    assert geo["profileActive"] == "Profile"
    assert geo["dedicatedTabs"] is False
    assert geo["tabCount"] == 5
    assert "Sanjay" in (geo["name"] or "")
    assert "Signed in with Google" in (geo["name"] or "")
    assert "Plan ended" not in (geo["name"] or "")
    assert geo["editDisplay"] not in {None, "none"}
    assert geo["editHref"] == "/profile?edit=name"
    assert geo["ctaText"] == card.cta_label == "Resume Playground"
    assert geo["ctaHref"] == card.cta_href == PLAYGROUND_BILLING_PATH
    assert geo["subTitle"] == card.title == "RecallC Plus"
    assert (geo["chip"] or "").strip() == "PAUSED"
    assert geo["chipKind"] == "paused"
    assert geo["statPresent"] is False
    assert not re.search(r"\d+/\d+", geo["stat"] or "")
    assert (geo["body"] or "").strip() == ENDED_BODY
    assert geo["reportDisplay"] == "flex"
    assert geo["cardSignoutDisplay"] == "flex"
    assert geo["lowerSignoutDisplay"] == "none"
    assert geo["resetDisplay"] not in {None, "none"}
    assert geo["deleteDisplay"] not in {None, "none"}
    assert geo["devicesHref"] == "/profile/security/devices"
    assert geo["prefsHref"] == "/settings"
    assert geo["visual"] == ["identity", "account", "subscription"]
    assert geo["focusBlocks"] == ["identity", "account", "subscription"]
    assert geo["identityTop"] <= geo["accountTop"]
    assert geo["accountTop"] <= geo["subTop"]
    assert geo["overflow"] is False
    assert geo["mockEnded"] is False
    assert geo["mockResume"] is False
    assert geo["subscribe"] is False
    assert geo["changePlan"] is False
    assert geo["signinMethod"] is True
    assert signout_open is True
    assert logout_action == "/logout"
    assert report_open is True
    assert report_path.rstrip("/") == "/profile"
    assert reset_open is True
    assert reset_action["href"] == "/profile"
    assert reset_action["value"] == "reset_progress"
    assert delete_open is True
    assert delete_action["href"] == "/profile"
    assert delete_action["value"] == "delete_account"
    assert devices_path.rstrip("/") == "/profile/security/devices"
    assert settings_path.rstrip("/") == "/settings"
    assert billing_path.rstrip("/") == "/billing/subscriptions"
    assert tall["tabsFixed"] is True
    assert tall["overflow"] is False
    assert tall["resetAbove"] is True
    assert tall["deleteAbove"] is True
    assert short["tabsFixed"] is True
    assert short["overflow"] is False
    assert short["resetAbove"] is True
    assert short["deleteAbove"] is True
    assert short["ctaHref"] == PLAYGROUND_BILLING_PATH
    assert _facts(client) == before
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_expired_profile_screen06_desktop_regression_1280(
    tmp_path: Path,
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _plus_then_expire(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    card = _live_card(client)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_expired_profile_screen06_desktop_regression_1280.png"
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
        page.goto(f"{origin}/profile", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const expired = document.querySelector('[data-expired-profile="desktop"]');
              const plus = document.querySelector('[data-plus-profile="desktop"]');
              const heading = document.querySelector(
                '[data-expired-profile="desktop"] > .display'
              );
              const identity = document.querySelector('[data-profile-identity]');
              const account = document.querySelector('[data-profile-account]');
              const sub = document.querySelector('[data-profile-subscription]');
              const cta = sub && sub.querySelector('a.pg-btn');
              const chip = sub && sub.querySelector('.pg-sub-chip');
              const stat = sub && sub.querySelector('.pg-sub-stat');
              const report = account && account.querySelector('[data-report-open]');
              const signout = account && account.querySelector('[data-open-signout]');
              const identityBox = identity && identity.getBoundingClientRect();
              const accountBox = account && account.getBoundingClientRect();
              const subBox = sub && sub.getBoundingClientRect();
              const status = document.querySelector('.account-menu-btn-status');
              const navActive = document.querySelector(
                '.PrimaryTabs--top .nav-link.is-active'
              );
              const phone = document.querySelector('.mobile-tabbar');
              return {
                present: Boolean(expired),
                plus: Boolean(plus),
                heading: heading && heading.textContent.trim(),
                headingSize: heading ? getComputedStyle(heading).fontSize : null,
                name: identity && (identity.innerText || ''),
                twoCol: Boolean(
                  identityBox && subBox && subBox.left > identityBox.right - 8
                ),
                accountBelowIdentity: Boolean(
                  identityBox && accountBox && accountBox.top > identityBox.bottom - 8
                ),
                subTitle: sub && (sub.querySelector('h2') || {}).textContent,
                chip: chip && chip.textContent.trim(),
                chipKind: chip && chip.getAttribute('data-chip'),
                statPresent: Boolean(stat) && getComputedStyle(stat).display !== 'none',
                body: sub && ((sub.querySelector('.pg-lede') || {}).innerText || ''),
                ctaText: cta && (cta.textContent || '').replace(/\\s+/g, ' ').trim(),
                ctaHref: cta && cta.getAttribute('href'),
                reportDisplay: report && getComputedStyle(report).display,
                signoutDisplay: signout && getComputedStyle(signout).display,
                status: status && status.textContent.trim(),
                statusDisplay: status && getComputedStyle(status).display,
                navActive: navActive && navActive.textContent.replace(
                  /\\s+/g, ' '
                ).trim(),
                tabsDisplay: phone ? getComputedStyle(phone).display : null,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)
        browser.close()

    assert geo["present"] is True
    assert geo["plus"] is False
    assert geo["heading"] == "Profile"
    assert geo["headingSize"] == "28px"
    assert "Sanjay" in (geo["name"] or "")
    assert "Signed in with Google" in (geo["name"] or "")
    assert "Plan ended" not in (geo["name"] or "")
    assert geo["twoCol"] is True
    assert geo["accountBelowIdentity"] is True
    assert geo["subTitle"] == card.title
    assert geo["chip"] == card.chip == "PAUSED"
    assert geo["chipKind"] == "paused"
    assert geo["statPresent"] is False
    assert (geo["body"] or "").strip() == ENDED_BODY
    assert geo["ctaText"] == card.cta_label == "Resume Playground"
    assert geo["ctaHref"] == card.cta_href == PLAYGROUND_BILLING_PATH
    assert geo["reportDisplay"] == "flex"
    assert geo["signoutDisplay"] == "flex"
    assert geo["status"] == LIVE_HEADING
    assert geo["statusDisplay"] != "none"
    assert "Profile" in (geo["navActive"] or "")
    assert geo["tabsDisplay"] == "none"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
