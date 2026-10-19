"""Phone Expired Settings Screen 07 (CTA map expired/07-screen).

Authorized: ChatGPT. Authenticated expired GET /settings at 390x844.
Desktop Expired Screen 11 is the functional contract. Live
can_use_auto_plan, live GCal branches, and live expired_header_status
win over the map. Plus 07 / signedIn 07 are layout only. Tabbar stays
hidden. No S2-1.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from datetime import date, datetime, timezone
from html import unescape
from pathlib import Path
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    InMemorySessionStore,
)
from constitution_memorizer.entitlements.models import BLOCK_PAID_PERIOD_ENDED
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.view import gate_view
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from tests.test_roster_m5a import _csrf

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
APP = ROOT / "src/constitution_memorizer/web/app.py"
APP_JS = ROOT / "src/constitution_memorizer/web/static/app.js"
USER = UUID("11111111-1111-4111-8111-111111111111")
TOKEN_KEY = Fernet.generate_key().decode()
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_HEADING = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
)
LEGAL_HREFS = ("/terms", "/privacy", "/grievance")
INVENTED = (
    "Plan ended 31 August",
    "Plan ended 12 August",
    "Plan ended",
    "Resume your Playground",
    "Resume Playground",
    "Premium",
    "Unlock all",
    "No plan yet",
    "See plans",
    "8/10",
    "Change plan",
    "Recall access · active",
)
INVENTED_MARKUP = INVENTED + ("Your Playground is paused", "RecallC Plus")
LOCKED_COPY = (
    "Part of unlocking every Article — your saved history is never deleted."
)


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _settings(*, gcal: bool = True, entitlements: bool = False, pricing: bool = False) -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None,
        APP_ENV="test",
        APP_BASE_URL="https://recall-the-c.in",
        MULTIUSER_ENABLED="true",
        AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true",
        SESSION_SECRET="test-secret",
        SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon",
        DATABASE_URL="",
        COOKIE_SECURE="false",
        ARTICLE_ENTITLEMENTS_ENABLED="true" if entitlements else "false",
        PRICING_ENABLED="true" if pricing else "false",
        GCAL_CLIENT_ID="gcal-cid" if gcal else "",
        GCAL_CLIENT_SECRET="gcal-secret" if gcal else "",
        GCAL_TOKEN_KEY=TOKEN_KEY if gcal else "",
    )


def _mu_app(
    tmp_path: Path,
    *,
    display_name: str = "Sanjay",
    gcal: bool = True,
    entitlements: bool = False,
    pricing: bool = False,
):
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
        multiuser_settings=_settings(
            gcal=gcal, entitlements=entitlements, pricing=pricing
        ),
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


def _plus_then_expire(client: TestClient) -> None:
    _subscribe(client)
    _expire(client)


def _expired_client(tmp_path: Path, **kwargs) -> TestClient:
    client = TestClient(
        _mu_app(tmp_path, entitlements=True, pricing=True, **kwargs)
    )
    _sign_in(client)
    _plus_then_expire(client)
    return client


def _engine(client: TestClient) -> ReminderEngine:
    return client.app.state.engine.for_user(USER)


def _panel(html: str) -> str:
    return html.split("data-expired-settings", 1)[1].split("</section>", 1)[0]


def _study(html: str) -> str:
    return html.split('data-settings-group="study"', 1)[1].split(
        'data-settings-group="', 1
    )[0]


def _identity_status(html: str) -> str:
    chunk = html.split("settings-account-status", 1)[1].split("</span>", 1)[0]
    return unescape(chunk.split(">", 1)[-1]).strip()


def _facts(client: TestClient) -> dict:
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    snap = client.app.state.entitlement_service.resolve(USER)
    plan = _engine(client).get_learning_plan()
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
        "devices": device_ids,
        "plan": None
        if plan is None
        else (plan.mode, plan.daily_target, plan.activated_at),
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


def _expired_css() -> str:
    css = PG_CSS.read_text(encoding="utf-8")
    return css.split("is expired/07-screen:", 1)[1].split("expired/01-screen", 1)[0]


def test_phone_expired_settings_is_live_screen11_contract(tmp_path: Path) -> None:
    client = _expired_client(tmp_path)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert snap.can_open_playground is False
    before = _facts(client)
    ensure_calls = _watch_ensure(client)
    page = client.get("/settings")
    assert page.status_code == 200
    assert _facts(client) == before
    assert ensure_calls == []
    html = unescape(page.text)
    assert 'data-expired-settings="desktop"' in html
    assert "data-signed-in-settings" in html
    assert "data-plus-settings" not in html
    assert "data-halted-settings" not in html
    assert 'data-mscreen="settings"' in html
    assert 'data-phone-settings="guest"' not in html
    panel = _panel(html)
    assert "Sanjay" in panel
    assert _identity_status(html) == LIVE_HEADING
    src = SETTINGS.read_text(encoding="utf-8")
    ident_src = src.split("settings-account-status", 1)[1].split(
        "settings-account-chevron", 1
    )[0]
    assert "{{ expired_header_status }}" in ident_src
    assert "Your Playground is paused" not in ident_src
    assert "Plan ended" not in ident_src
    ident = panel.split("settings-account-row", 1)[1][:400]
    assert 'href="/profile"' in ident
    assert "Appearance, your learning plan, and your revision calendar." in panel
    assert 'data-settings-group="study"' in panel
    assert 'data-settings-group="calendar"' in panel
    assert 'data-settings-group="app"' in panel
    assert 'data-settings-group="account"' in panel
    study = _study(html)
    assert 'action="/settings/learning-plan"' in panel
    assert "data-plan-autosubmit" in panel
    plan_form = src.split('action="/settings/learning-plan"', 1)[1].split(
        "</form>", 1
    )[0]
    assert 'name="csrf_token"' not in plan_form
    assert "Self-paced" in study
    assert "Auto Plan" in study
    assert 'id="pace-self-paced"' in study
    assert "checked" in study.split('id="pace-self-paced"', 1)[1].split(">", 1)[0]
    assert "disabled" not in study.split('id="pace-self-paced"', 1)[1].split(">", 1)[0]
    assert "disabled" in study.split('id="pace-auto"', 1)[1].split(">", 1)[0]
    assert 'class="segmented is-disabled"' in study
    assert "Steady · 3" not in study
    assert "Balanced · 5" not in study
    assert "Intensive · 7" not in study
    assert 'id="target-5"' not in study
    assert LOCKED_COPY in study
    assert 'href="/pricing"' in study
    assert "Unlock every Article →" in study
    assert "can_auto_plan|default(false)" in src
    assert "expired_settings" not in src.split('data-settings-group="study"', 1)[1].split(
        'data-settings-group="calendar"', 1
    )[0]
    assert "data-gcal-toggle" in panel
    assert 'data-gcal-on="/calendar/google/connect"' in panel
    assert 'data-gcal-off-form="gcal-disconnect-form"' in panel
    assert 'href="/calendar/google/connect"' in panel
    assert 'action="/calendar/google/disconnect"' in src
    assert 'action="/calendar/google/preferences"' in src
    assert "gcal.connected" in src
    assert "gcal.connection" in src
    assert "gcal.prefs" in src
    assert "gcal.status_param" in src
    assert "Last synced" not in panel
    assert 'data-theme-set="auto"' in panel
    assert 'data-theme-set="light"' in panel
    assert 'data-theme-set="dark"' in panel
    assert "data-text-size-step" in panel
    assert "data-motion-toggle" in panel
    assert 'data-report-open data-report-section="Settings"' in panel
    assert 'action="/logout"' in panel
    logout = panel.split('action="/logout"', 1)[1].split("</form>", 1)[0]
    assert "confirm(" not in logout
    assert "data-open-signout" not in panel
    assert 'id="signout-modal"' not in html
    assert "settings-signout-form" in panel
    assert 'name="csrf_token"' in logout
    for href in LEGAL_HREFS:
        assert f'href="{href}"' in panel
        assert client.get(href).status_code == 200
    assert "Bare Act text verbatim · Day 1 · 3 · 7 · 15 · 30 · 60" in panel
    for phrase in INVENTED:
        assert phrase not in html, phrase
    assert "Resume Playground" not in panel
    tabs = html.split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 1
    )
    assert len(tabs) > 1
    bar = tabs[1].split("</nav>", 1)[0]
    assert "Settings" not in bar
    for label_text, href in TAB_HREFS:
        assert f'href="{href}"' in bar
        assert label_text in bar
    saved = client.post(
        "/settings/learning-plan",
        data={**_csrf(client), "mode": "self_paced"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert saved.headers["location"].startswith("/settings")
    plan = _engine(client).get_learning_plan()
    assert plan.mode == "self_paced"
    refused = client.post(
        "/settings/learning-plan",
        data={**_csrf(client), "mode": "auto", "daily_target": "7"},
        follow_redirects=False,
    )
    assert refused.status_code == 303
    after = _engine(client).get_learning_plan()
    assert after.mode != "auto"
    connect = client.get("/calendar/google/connect", follow_redirects=False)
    assert connect.status_code == 303
    assert "accounts.google.com" in connect.headers["location"]
    profile = client.get("/profile", follow_redirects=False)
    assert profile.status_code == 200
    assert 'data-expired-profile="desktop"' in profile.text
    today = client.get("/dashboard", follow_redirects=False)
    assert today.status_code == 200
    assert before["can_open"] is False
    assert _facts(client)["can_open"] is False
    assert ensure_calls == []
    assert client.cookies.get(CSRF_COOKIE_NAME)
    logged = client.post(
        "/logout", data=_csrf(client), follow_redirects=False
    )
    assert logged.status_code == 303
    assert "/signed-out" in logged.headers.get("location", "")


def test_phone_expired_settings_saved_auto_plan_survives_get(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path, entitlements=True, pricing=True))
    _sign_in(client)
    _subscribe(client)
    _engine(client).upsert_learning_plan(
        mode="auto", daily_target=5, as_of=date(2026, 9, 16)
    )
    before = _engine(client).get_learning_plan()
    assert before.mode == "auto"
    assert before.daily_target == 5
    activated = before.activated_at
    _expire(client)
    facts_before = _facts(client)
    page = client.get("/settings")
    assert page.status_code == 200
    after = _engine(client).get_learning_plan()
    assert after.mode == "auto"
    assert after.daily_target == 5
    assert after.activated_at == activated
    assert _facts(client) == facts_before
    html = unescape(page.text)
    study = _study(html)
    assert "disabled" in study.split('id="pace-auto"', 1)[1].split(">", 1)[0]
    assert 'id="target-5"' not in study


def test_phone_expired_settings_calendar_unconfigured_omits_group(
    tmp_path: Path,
) -> None:
    client = _expired_client(tmp_path, gcal=False)
    html = unescape(client.get("/settings").text)
    assert 'data-expired-settings="desktop"' in html
    assert 'data-settings-group="calendar"' not in html
    assert "Last synced" not in html
    assert "data-gcal-toggle" not in html


def test_phone_expired_settings_css_is_breakpoint_scoped() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    assert "is expired/07-screen:" in css
    phone_block = _expired_css()
    assert "@media (max-width: 560px)" in phone_block
    assert "@media (min-width: 561px)" not in phone_block
    assert '[data-expired-settings="desktop"]' in phone_block
    assert "[data-halted-settings" not in phone_block
    assert "[data-plus-settings" not in phone_block
    assert "safe-area-inset-bottom" in phone_block
    assert "overflow-x: hidden" in phone_block
    assert "overflow-wrap: anywhere" in phone_block
    assert ".mobile-tabbar" in phone_block
    tab_rule = phone_block.split(".mobile-tabbar", 1)[1].split("}", 1)[0]
    assert "display: none" in tab_rule
    assert "grid-template-columns: repeat(5, 1fr)" not in phone_block
    assert "position: fixed" not in phone_block
    assert "> .lede" in phone_block
    assert "settings-saved" in phone_block
    assert "font-size: 26px" in phone_block
    assert "var(--ink)" in phone_block
    assert "min-height: 44px" in phone_block
    assert "#0e7569" not in phone_block
    assert "#3a3a38" not in phone_block
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", phone_block) is None
    assert "display: contents" not in phone_block
    assert "data-expired-settings-phone" not in css
    desk = css.split("expired/11-screen", 1)[1].split("is expired/07-screen:", 1)[0]
    assert "@media (min-width: 561px)" in desk
    assert "@media (max-width: 560px)" not in desk
    plus_phone = css.split("is plus/07-screen:", 1)[1].split("expired/11-screen", 1)[0]
    assert "@media (max-width: 560px)" in plus_phone
    assert "[data-expired-settings" not in plus_phone
    mobile = MOBILE.read_text(encoding="utf-8")
    generic, _, rest = mobile.partition("is signedIn/07-screen:")
    assert "data-expired-settings" not in generic
    phone_free = rest.split("/* R1 — Playground phone shell", 1)[0]
    assert ":not([data-expired-settings])" in phone_free
    assert 'data-expired-settings="desktop"] {' not in phone_free
    assert "is expired/07-screen:" not in phone_free
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", phone_free) is None
    phone_title = mobile.split(
        'body[data-mscreen="settings"] .settings > .display {', 1
    )[1].split("}", 1)[0]
    assert "font-size: 23px" in phone_title
    phone_desk = mobile.split(
        'body[data-mscreen="settings"] .settings-desk-copy {', 1
    )[1].split("}", 1)[0]
    assert "display: none" in phone_desk
    assert 'body[data-mscreen="settings"] .mobile-tabbar' in mobile
    assert "is expired/07-screen:" not in STYLES.read_text(encoding="utf-8")
    assert "is expired/07-screen:" not in APP.read_text(encoding="utf-8")
    assert "is expired/07-screen:" not in APP_JS.read_text(encoding="utf-8")
    src = SETTINGS.read_text(encoding="utf-8")
    assert 'data-expired-settings="desktop"' in src
    assert "data-expired-settings-phone" not in src
    assert "{{ expired_header_status }}" in src
    for phrase in INVENTED_MARKUP:
        assert phrase not in src, phrase
    assert 'action="/settings/learning-plan"' in src
    assert 'href="/calendar/google/connect"' in src
    assert 'action="/calendar/google/disconnect"' in src
    assert 'action="/logout"' in src
    assert "data-plan-autosubmit" in src
    plan_post = APP.read_text(encoding="utf-8").split(
        "async def settings_learning_plan", 1
    )[1].split("async def choose_get", 1)[0]
    assert "expired_settings" not in plan_post
    assert "request_is_expired_subscriber" not in plan_post
    get = APP.read_text(encoding="utf-8").split("async def settings_page", 1)[1].split(
        "async def settings_save", 1
    )[0]
    assert "upsert_learning_plan" not in get
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg50" in base
    assert "playground.css?v=pg46" not in base
    assert "styles.css?v=main88" in base
    assert "mobile.css?v=mob107" in base
    assert "data-expired-settings-phone-tabs" not in base
    # M1: the per-screen guest branches are gone; guests share one bar.
    assert "{% elif guest_settings %}" not in base
    assert "data-guest-phone-tabs" in base


def test_guest_free_plus_halted_pro_settings_stay_separate(
    tmp_path: Path,
) -> None:
    guest = TestClient(_guest_app(tmp_path / "guest")).get("/settings")
    assert guest.status_code == 200
    guest_html = guest.text
    assert 'data-phone-settings="guest"' in guest_html
    assert "data-signed-in-settings" not in guest_html
    assert 'data-expired-settings="desktop"' not in guest_html
    assert 'data-settings-group="study"' not in guest_html
    assert 'data-settings-group="calendar"' not in guest_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/settings").text
    assert "data-signed-in-settings" in free_html
    assert 'data-expired-settings="desktop"' not in free_html
    assert LIVE_HEADING not in free_html.split("<header", 1)[-1].split(
        "</header>", 1
    )[0]

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = unescape(plus.get("/settings").text)
    assert 'data-plus-settings="desktop"' in plus_html
    assert "data-expired-settings" not in plus_html
    assert "data-halted-settings" not in plus_html
    plus_study = _study(plus_html)
    assert "disabled" not in plus_study.split('id="pace-auto"', 1)[1].split(">", 1)[0]
    assert "Steady · 3" in plus_study
    assert LOCKED_COPY not in plus_study

    expired = _expired_client(tmp_path / "expired")
    expired_html = unescape(expired.get("/settings").text)
    assert 'data-expired-settings="desktop"' in expired_html
    assert "data-plus-settings" not in expired_html
    assert "disabled" in expired_html.split('id="pace-auto"', 1)[1].split(">", 1)[0]

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    stored = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )
    halted_html = halted.get("/settings").text
    assert 'data-halted-settings="desktop"' in halted_html
    assert "data-expired-settings" not in halted_html
    assert "data-plus-settings" not in halted_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/settings").text
    assert 'data-expired-settings="desktop"' not in pro_html
    assert 'data-plus-settings="desktop"' not in pro_html
    assert LIVE_HEADING not in pro_html.split("<header", 1)[-1].split(
        "</header>", 1
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


def _geo_script() -> str:
    return """() => {
              const panel = document.querySelector('[data-expired-settings="desktop"]');
              const header = document.querySelector('.site-header');
              const topbar = panel && panel.querySelector(':scope > .mobile-topbar');
              const back = panel && panel.querySelector('.mobile-back');
              const tabs = document.querySelector('.mobile-tabbar');
              const ident = panel && panel.querySelector('.settings-account-row');
              const identStatus = ident && ident.querySelector('.settings-account-status');
              const lede = panel && panel.querySelector(':scope > .lede');
              const study = panel && panel.querySelector('[data-settings-group="study"]');
              const cal = panel && panel.querySelector('[data-settings-group="calendar"]');
              const app = panel && panel.querySelector('[data-settings-group="app"]');
              const account = panel && panel.querySelector('[data-settings-group="account"]');
              const legal = panel && panel.querySelector(':scope > .section-title');
              const selfPace = study && study.querySelector('#pace-self-paced');
              const autoPace = study && study.querySelector('#pace-auto');
              const selfLabel = study && study.querySelector('label[for="pace-self-paced"]');
              const locked = study && study.querySelector('.settings-plan-locked');
              const pricing = locked && locked.querySelector('a[href="/pricing"]');
              const toggle = cal && cal.querySelector('[data-gcal-toggle]');
              const deskCopy = panel && panel.querySelector('.settings-desk-copy');
              const connectRow = panel && panel.querySelector('.gcal-connect-row');
              const deskBack = panel && panel.querySelector('.si-settings-desk-back');
              const autoBtn = panel && panel.querySelector('[data-theme-set="auto"]');
              const motion = panel && panel.querySelector('[data-motion-toggle]');
              const size = panel && panel.querySelector('[data-text-size-row]');
              const report = account && account.querySelector('[data-report-open]');
              const signoutForm = account && account.querySelector('.settings-signout-form');
              const signoutBtn = signoutForm && signoutForm.querySelector('button[type="submit"]');
              const identBox = ident && ident.getBoundingClientRect();
              const studyBox = study && study.getBoundingClientRect();
              const calBox = cal && cal.getBoundingClientRect();
              const appBox = app && app.getBoundingClientRect();
              const accountBox = account && account.getBoundingClientRect();
              const legalBox = legal && legal.getBoundingClientRect();
              const selfCs = selfLabel ? getComputedStyle(selfLabel) : null;
              const autoCs = autoBtn ? getComputedStyle(autoBtn) : null;
              const lockedCs = locked ? getComputedStyle(locked) : null;
              const focusable = [...(panel ? panel.querySelectorAll(
                'a[href], button:not([disabled]), input:not([disabled]), select, textarea'
              ) : [])].filter((el) => {
                const cs = getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden') return false;
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              });
              const owner = (el) => {
                if (el.closest('.mobile-topbar') || el.closest('.si-settings-desk-back')) {
                  return 'other';
                }
                if (el.closest('.settings-account-row')) return 'identity';
                if (el.closest('[data-settings-group="study"]')) return 'study';
                if (el.closest('[data-settings-group="calendar"]')) return 'calendar';
                if (el.closest('[data-settings-group="app"]')) return 'app';
                if (el.closest('[data-settings-group="account"]')) return 'account';
                return 'other';
              };
              const visual = [
                { name: 'identity', top: identBox && identBox.top },
                { name: 'study', top: studyBox && studyBox.top },
                { name: 'calendar', top: calBox && calBox.top },
                { name: 'app', top: appBox && appBox.top },
                { name: 'account', top: accountBox && accountBox.top },
                { name: 'legal', top: legalBox && legalBox.top },
              ].sort((a, b) => (a.top || 0) - (b.top || 0)).map((row) => row.name);
              const focusBlocks = [];
              for (const el of focusable) {
                const name = owner(el);
                if (name === 'other') continue;
                if (focusBlocks[focusBlocks.length - 1] !== name) focusBlocks.push(name);
              }
              const legalLinks = [...(panel ? panel.querySelectorAll(
                ':scope > .settings-note a'
              ) : [])];
              return {
                present: Boolean(panel),
                headerDisplay: header ? getComputedStyle(header).display : null,
                topbarDisplay: topbar ? getComputedStyle(topbar).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                backText: back && (back.textContent || '').replace(/\\s+/g, ' ').trim(),
                backHref: back && back.getAttribute('href'),
                identHref: ident && ident.getAttribute('href'),
                name: ident && (ident.innerText || ''),
                identStatus: identStatus && (identStatus.textContent || '').trim(),
                ledeDisplay: lede ? getComputedStyle(lede).display : null,
                ledeText: lede && (lede.textContent || '').trim(),
                selfChecked: Boolean(selfPace && selfPace.checked),
                selfEnabled: Boolean(selfPace && !selfPace.disabled),
                autoDisabled: Boolean(autoPace && autoPace.disabled),
                hasDailyTarget: Boolean(study && study.querySelector('#target-5')),
                lockedText: locked && (locked.innerText || '').replace(/\\s+/g, ' ').trim(),
                lockedOverflow: Boolean(
                  locked && locked.scrollWidth > locked.clientWidth + 1
                ),
                lockedWrap: lockedCs && lockedCs.overflowWrap,
                pricingHref: pricing && pricing.getAttribute('href'),
                selfBg: selfCs && selfCs.backgroundColor,
                selfColor: selfCs && selfCs.color,
                autoThemeBg: autoCs && autoCs.backgroundColor,
                autoThemeColor: autoCs && autoCs.color,
                gcalChecked: toggle && toggle.getAttribute('aria-checked'),
                gcalDisplay: toggle ? getComputedStyle(toggle).display : null,
                deskCopyDisplay: deskCopy ? getComputedStyle(deskCopy).display : null,
                connectRowDisplay: connectRow ? getComputedStyle(connectRow).display : null,
                deskBackDisplay: deskBack ? getComputedStyle(deskBack).display : null,
                motionChecked: motion && motion.getAttribute('aria-checked'),
                sizeDisplay: size ? getComputedStyle(size).display : null,
                reportDisplay: report ? getComputedStyle(report).display : null,
                signoutDisplay: signoutBtn ? getComputedStyle(signoutBtn).display : null,
                signoutAction: signoutForm && signoutForm.getAttribute('action'),
                signoutOnsubmit: signoutForm && signoutForm.getAttribute('onsubmit'),
                signoutModal: Boolean(document.querySelector('#signout-modal')),
                openSignout: Boolean(document.querySelector('[data-open-signout]')),
                visual,
                focusBlocks,
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                hasSynced: /Last synced/.test(cal ? cal.innerText : ''),
                hasSettingsTab: tabs ? /Settings/.test(tabs.innerText || '') : false,
                hasResume: /Resume Playground/.test(panel ? panel.innerText : ''),
                hasPlanEnded: /Plan ended/.test(panel ? panel.innerText : ''),
                legalHrefs: legalLinks.map((el) => el.getAttribute('href')),
                headingSize: panel && getComputedStyle(
                  panel.querySelector(':scope > .display')
                ).fontSize,
              };
            }"""


def _reach(page, selector: str) -> dict:
    page.locator(selector).scroll_into_view_if_needed()
    page.wait_for_timeout(40)
    return page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          const cs = el ? getComputedStyle(el) : null;
          const r = el && el.getBoundingClientRect();
          return {
            display: cs && cs.display,
            width: r ? r.width : 0,
            height: r ? r.height : 0,
            visible: Boolean(el && r && r.width > 0 && r.height > 0
              && cs && cs.display !== 'none' && cs.visibility !== 'hidden'),
            min: el ? Math.min(r.height, el.offsetHeight) : 0,
          };
        }""",
        selector,
    )


def test_phone_expired_settings_screen07_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, entitlements=True, pricing=True)
    client = TestClient(app)
    _sign_in(client)
    _plus_then_expire(client)
    before = _facts(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_expired_settings_screen07_390x844.png"
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
        page.goto(f"{origin}/settings", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(_geo_script())
        page.locator(".mobile-back").focus()
        focus_vis = page.evaluate(
            """() => {
              const el = document.activeElement;
              const cs = el ? getComputedStyle(el) : null;
              const outlineOn = Boolean(
                cs && cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0
              );
              const shadowOn = Boolean(cs && cs.boxShadow && cs.boxShadow !== 'none');
              return {
                isBack: Boolean(el && el.classList.contains('mobile-back')),
                visible: outlineOn || shadowOn,
                outlineStyle: cs && cs.outlineStyle,
                outlineWidth: cs && cs.outlineWidth,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        below = {
            "back": _reach(page, ".mobile-back"),
            "motion": _reach(page, '[data-motion-toggle]'),
            "account": _reach(page, '[data-settings-group="account"]'),
            "report": _reach(
                page, '[data-settings-group="account"] [data-report-open]'
            ),
            "signout": _reach(
                page, '[data-settings-group="account"] .settings-signout-form button'
            ),
            "legal": _reach(page, '.settings-note a[href="/terms"]'),
            "ladder": _reach(page, ".settings-verbatim"),
            "gcal": _reach(page, '[data-gcal-toggle]'),
        }

        page.locator('[data-settings-group="account"] [data-report-open]').click()
        report_open = page.evaluate(
            """() => {
              const overlay = document.querySelector('[data-report-overlay]');
              return Boolean(overlay && !overlay.hasAttribute('hidden'));
            }"""
        )
        page.locator("[data-rc-close]").click()

        page.goto(f"{origin}/settings?saved=1", wait_until="networkidle")
        saved_geo = page.evaluate(
            """() => {
              const banner = document.querySelector('.settings-saved');
              const autoPace = document.querySelector('#pace-auto');
              return {
                text: banner && (banner.textContent || '').trim(),
                display: banner ? getComputedStyle(banner).display : null,
                autoDisabled: Boolean(autoPace && autoPace.disabled),
              };
            }"""
        )

        page.goto(f"{origin}/settings", wait_until="networkidle")
        page.locator(".settings-account-row").click()
        page.wait_for_url("**/profile**", timeout=8000)
        profile_path = page.evaluate("() => location.pathname")
        page.locator('[data-profile-account] a[href="/settings"]').click()
        page.wait_for_url("**/settings**", timeout=8000)
        settings_path = page.evaluate("() => location.pathname")
        page.locator(".mobile-back").click()
        page.wait_for_url("**/dashboard**", timeout=8000)
        today_path = page.evaluate("() => location.pathname")

        page.goto(f"{origin}/settings", wait_until="networkidle")
        page.set_viewport_size({"width": 390, "height": 700})
        short = {
            "tabs": page.evaluate(
                """() => {
                  const tabs = document.querySelector('.mobile-tabbar');
                  return {
                    display: tabs ? getComputedStyle(tabs).display : null,
                    overflow: document.documentElement.scrollWidth
                      > document.documentElement.clientWidth,
                  };
                }"""
            ),
            "motion": _reach(page, '[data-motion-toggle]'),
            "report": _reach(
                page, '[data-settings-group="account"] [data-report-open]'
            ),
            "signout": _reach(
                page, '[data-settings-group="account"] .settings-signout-form button'
            ),
            "legal": _reach(page, '.settings-note a[href="/terms"]'),
            "ladder": _reach(page, ".settings-verbatim"),
        }
        browser.close()

    assert geo["present"] is True
    assert geo["headerDisplay"] == "none"
    assert geo["topbarDisplay"] not in {None, "none"}
    assert geo["tabsDisplay"] in {None, "none"}
    assert geo["hasSettingsTab"] is False
    assert geo["backText"] == "← Today"
    assert geo["backHref"] == "/dashboard"
    assert geo["identHref"] == "/profile"
    assert "Sanjay" in (geo["name"] or "")
    assert geo["identStatus"] == LIVE_HEADING
    assert geo["ledeDisplay"] not in {None, "none"}
    assert "Appearance, your learning plan, and your revision calendar." in (
        geo["ledeText"] or ""
    )
    assert geo["selfChecked"] is True
    assert geo["selfEnabled"] is True
    assert geo["autoDisabled"] is True
    assert geo["hasDailyTarget"] is False
    assert LOCKED_COPY in (geo["lockedText"] or "")
    assert geo["lockedOverflow"] is False
    assert geo["lockedWrap"] in {"anywhere", "break-word"}
    assert geo["pricingHref"] == "/pricing"
    assert geo["selfBg"] == "rgb(20, 20, 20)"
    assert geo["selfColor"] == "rgb(255, 255, 255)"
    assert geo["autoThemeBg"] == "rgb(20, 20, 20)"
    assert geo["autoThemeColor"] == "rgb(255, 255, 255)"
    assert geo["gcalChecked"] == "false"
    assert geo["gcalDisplay"] not in {None, "none"}
    assert geo["deskCopyDisplay"] == "none"
    assert geo["connectRowDisplay"] == "none"
    assert geo["deskBackDisplay"] == "none"
    assert geo["motionChecked"] == "true"
    assert geo["sizeDisplay"] not in {None, "none"}
    assert geo["reportDisplay"] not in {None, "none"}
    assert geo["signoutDisplay"] not in {None, "none"}
    assert geo["signoutAction"] == "/logout"
    assert geo["signoutOnsubmit"] in {None, ""}
    assert geo["signoutModal"] is False
    assert geo["openSignout"] is False
    assert geo["hasResume"] is False
    assert geo["hasPlanEnded"] is False
    assert geo["visual"] == [
        "identity",
        "study",
        "calendar",
        "app",
        "account",
        "legal",
    ]
    assert geo["focusBlocks"] == [
        "identity",
        "study",
        "calendar",
        "app",
        "account",
    ]
    assert geo["overflow"] is False
    assert geo["hasSynced"] is False
    assert geo["legalHrefs"] == list(LEGAL_HREFS)
    assert geo["headingSize"] == "26px"
    assert focus_vis["isBack"] is True
    assert focus_vis["visible"] is True
    for name, info in below.items():
        assert info["visible"] is True, name
    assert below["back"]["min"] >= 44
    assert below["report"]["min"] >= 44
    assert below["signout"]["min"] >= 44
    assert below["gcal"]["min"] >= 44
    assert report_open is True
    assert saved_geo["text"] == "Settings saved."
    assert saved_geo["display"] not in {None, "none"}
    assert saved_geo["autoDisabled"] is True
    assert profile_path.rstrip("/") == "/profile"
    assert settings_path.rstrip("/") == "/settings"
    assert today_path.rstrip("/") == "/dashboard"
    assert short["tabs"]["display"] in {None, "none"}
    assert short["tabs"]["overflow"] is False
    assert short["motion"]["visible"] is True
    assert short["report"]["visible"] is True
    assert short["signout"]["visible"] is True
    assert short["legal"]["visible"] is True
    assert short["ladder"]["visible"] is True
    assert short["report"]["min"] >= 44
    assert short["signout"]["min"] >= 44
    assert _facts(client) == before
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_expired_settings_screen07_desktop_regression_1280(
    tmp_path: Path,
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, entitlements=True, pricing=True)
    client = TestClient(app)
    _sign_in(client)
    _plus_then_expire(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_expired_settings_screen07_desktop_regression_1280.png"
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
        page.goto(f"{origin}/settings", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const expired = document.querySelector('[data-expired-settings="desktop"]');
              const plus = document.querySelector('[data-plus-settings="desktop"]');
              const heading = expired && expired.querySelector(':scope > .display');
              const ident = expired && expired.querySelector('.settings-account-row');
              const identStatus = ident && ident.querySelector('.settings-account-status');
              const study = expired && expired.querySelector('[data-settings-group="study"]');
              const cal = expired && expired.querySelector('[data-settings-group="calendar"]');
              const account = expired && expired.querySelector('[data-settings-group="account"]');
              const toggle = expired && expired.querySelector('[data-gcal-toggle]');
              const connect = cal && cal.querySelector('[data-gcal-connect]');
              const save = study && study.querySelector('button[type="submit"]');
              const selfPace = study && study.querySelector('#pace-self-paced');
              const autoPace = study && study.querySelector('#pace-auto');
              const locked = study && study.querySelector('.settings-plan-locked');
              const pricing = locked && locked.querySelector('a[href="/pricing"]');
              const selfLabel = study && study.querySelector('label[for="pace-self-paced"]');
              const back = expired && expired.querySelector('.si-settings-desk-back a');
              const nav = document.querySelector('.PrimaryTabs--top');
              const active = nav && [...nav.querySelectorAll('.nav-link.is-active')].map(
                (el) => (el.textContent || '').replace(/\\s+/g, ' ').trim()
              );
              const phone = document.querySelector('.mobile-tabbar');
              const status = document.querySelector('.account-menu-btn-status');
              const selfCs = selfLabel ? getComputedStyle(selfLabel) : null;
              const identBox = ident && ident.getBoundingClientRect();
              const studyBox = study && study.getBoundingClientRect();
              const calBox = cal && cal.getBoundingClientRect();
              return {
                present: Boolean(expired),
                plus: Boolean(plus),
                heading: heading && (heading.textContent || '').trim(),
                headingSize: heading ? getComputedStyle(heading).fontSize : null,
                identHref: ident && ident.getAttribute('href'),
                name: ident && (ident.innerText || ''),
                identStatus: identStatus && (identStatus.textContent || '').trim(),
                selfChecked: Boolean(selfPace && selfPace.checked),
                autoDisabled: Boolean(autoPace && autoPace.disabled),
                hasDailyTarget: Boolean(study && study.querySelector('#target-5')),
                locked: locked && (locked.innerText || '').replace(/\\s+/g, ' ').trim(),
                pricingHref: pricing && pricing.getAttribute('href'),
                selfBg: selfCs && selfCs.backgroundColor,
                connectHref: connect && connect.getAttribute('href'),
                connectDisplay: connect ? getComputedStyle(connect).display : null,
                saveText: save && (save.textContent || '').replace(/\\s+/g, ' ').trim(),
                saveDisplay: save ? getComputedStyle(save).display : null,
                togglePhoneDisplay: toggle ? getComputedStyle(
                  toggle.closest('.settings-phone-only') || toggle
                ).display : null,
                accountDisplay: account ? getComputedStyle(account).display : null,
                tabsDisplay: phone ? getComputedStyle(phone).display : null,
                backText: back && (back.textContent || '').replace(/\\s+/g, ' ').trim(),
                backHref: back && back.getAttribute('href'),
                backDisplay: back ? getComputedStyle(back).display : 'none',
                hasSettingsPill: (active || []).includes('Settings'),
                status: status && (status.textContent || '').trim(),
                statusDisplay: status ? getComputedStyle(status).display : 'none',
                hasSynced: /Last synced/.test(cal ? cal.innerText : ''),
                hasResume: /Resume Playground/.test(expired ? expired.innerText : ''),
                studyBelow: Boolean(
                  identBox && studyBox && studyBox.top > identBox.bottom - 8
                ),
                calBelow: Boolean(
                  studyBox && calBox && calBox.top > studyBox.bottom - 8
                ),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["present"] is True
    assert geo["plus"] is False
    assert geo["heading"] == "Settings"
    assert geo["headingSize"] == "30px"
    assert geo["identHref"] == "/profile"
    assert "Sanjay" in (geo["name"] or "")
    assert geo["identStatus"] == LIVE_HEADING
    assert geo["selfChecked"] is True
    assert geo["autoDisabled"] is True
    assert geo["hasDailyTarget"] is False
    assert LOCKED_COPY in (geo["locked"] or "")
    assert geo["pricingHref"] == "/pricing"
    assert geo["selfBg"] == "rgb(20, 20, 20)"
    assert geo["saveText"] == "Save learning plan"
    assert geo["saveDisplay"] not in {None, "none"}
    assert geo["togglePhoneDisplay"] == "none"
    assert geo["tabsDisplay"] == "none"
    assert geo["backText"] == "← Today"
    assert geo["backHref"] == "/dashboard"
    assert geo["backDisplay"] not in {None, "none"}
    assert geo["hasSettingsPill"] is False
    assert geo["status"] == LIVE_HEADING
    assert geo["statusDisplay"] != "none"
    assert geo["hasSynced"] is False
    assert geo["hasResume"] is False
    assert geo["studyBelow"] is True
    assert geo["calBelow"] is True
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
