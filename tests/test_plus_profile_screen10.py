"""Plus cohort desktop /profile Screen 10 (CTA map plus/10-screen).

Authorized: ChatGPT. Authenticated multiuser GET /profile with a real
active Plus EntitlementSnapshot. Live identity, device_count_label, and
playground_subscription (usage peeked from roster). Guest, Free, Pro,
phone, edit-name, and Plus Screens 01–09 stay on their own wrappers.
Auth, devices, billing actions, and reset/delete logic are not touched.
"""

from __future__ import annotations

import inspect
import re
import socket
import threading
import time
from datetime import date, datetime, timezone
from html import unescape
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.view import (
    PLAYGROUND_BILLING_PATH,
    PlaygroundSubscriptionCard,
    format_plan_end,
    plus_profile_subscription_card,
)
from constitution_memorizer.playground.roster.period import (
    playground_month_bounds,
    playground_month_name,
)
from constitution_memorizer.web.app import create_app
from tests.test_roster_m5a import _confirm_add, _csrf

# Stage 1 HTTP tests freeze playground_today to 16 September 2026. Screen 10
# Profile must follow the live current Playground month (6 October 2026 here)
# so peek_capacity, month_name, and next_open share that October window.
SCREEN10_NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
AUTH = ROOT / "src/constitution_memorizer/auth/routes.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
MANAGE = ROOT / "src/constitution_memorizer/web/templates/subscription_manage.html"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
DEVICES = ROOT / "src/constitution_memorizer/web/templates/devices.html"
DEVICES_PY = ROOT / "src/constitution_memorizer/devices"
BILLING_PY = ROOT / "src/constitution_memorizer/subscriptions"
USER = UUID("11111111-1111-4111-8111-111111111111")
INVENTED = (
    "Premium",
    "Unlock all",
    "8/10",
    "2 of 3",
    "renews 1 October",
    "See plans",
    "No plan yet",
)
INVENTED_MARKUP = INVENTED + ("September 2026",)


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture(autouse=True)
def _playground_test_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    from constitution_memorizer.entitlements import service as entitlement_service
    from constitution_memorizer.playground.roster import period as period_mod

    real_period_utc = period_mod._as_utc
    real_ent_utc = entitlement_service._utc

    def frozen_period_utc(now):
        return real_period_utc(now or SCREEN10_NOW)

    def frozen_ent_utc(now):
        return real_ent_utc(now or SCREEN10_NOW)

    monkeypatch.setattr(period_mod, "_as_utc", frozen_period_utc)
    monkeypatch.setattr(entitlement_service, "_utc", frozen_ent_utc)


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
    status: str = "active",
    cancel_at_period_end: bool = False,
) -> None:
    client.app.state.subscriptions.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        billing_period_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 10, 15, tzinfo=timezone.utc),
        cancel_at_period_end=cancel_at_period_end,
        is_current=True,
    )


def _plus_client(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    return client


def _header(html: str) -> str:
    return html.split("<header", 1)[-1].split("</header>", 1)[0]


def _account_list(html: str) -> str:
    return html.split("data-profile-account", 1)[1].split("</div>", 1)[0]


def _identity(html: str) -> str:
    return html.split("data-profile-identity", 1)[1].split("</article>", 1)[0]


def _usage_parts(*, used: int, limit: int = 10) -> tuple[str, str, str, str]:
    start, end = playground_month_bounds()
    month = playground_month_name(start)
    nxt = format_plan_end(end)
    following = date(
        start.year + (1 if start.month == 12 else 0),
        1 if start.month == 12 else start.month + 1,
        1,
    )
    assert end == following
    assert start == date(SCREEN10_NOW.year, SCREEN10_NOW.month, 1)
    assert month == "October"
    assert nxt == "1 November"
    return f"{used}/{limit}", month, nxt, f"laws in {month} · new spaces open {nxt}"


def test_plus_profile_subscription_card_uses_live_roster_not_magic_quota() -> None:
    card = PlaygroundSubscriptionCard(
        title="RecallC Plus",
        chip="ACTIVE",
        chip_kind="active",
        body="This month’s Playground is open.",
        stat_big="10",
        stat_label="10 laws / month",
        cta_label="Manage plan",
        cta_href=PLAYGROUND_BILLING_PATH,
    )

    def _peek(start: date, end: date | None, *, used: int = 3, limit: int = 10):
        return SimpleNamespace(
            peek_capacity=lambda user_id, snapshot: SimpleNamespace(
                used=used,
                law_limit=limit,
                period_start=start,
                period_end=end,
            )
        )

    september = plus_profile_subscription_card(
        card,
        snapshot=SimpleNamespace(playground_law_limit=10),
        roster=_peek(date(2026, 9, 1), date(2026, 10, 1)),
        user_id="x",
    )
    assert september.stat_big == "3/10"
    assert september.stat_label == "laws in September · new spaces open 1 October"
    assert "1 November" not in september.stat_label
    assert september.cta_label == "Change plan"
    assert september.cta_href == PLAYGROUND_BILLING_PATH
    assert september.chip == "ACTIVE"
    assert september.body == card.body

    october = plus_profile_subscription_card(
        card,
        snapshot=SimpleNamespace(playground_law_limit=10),
        roster=_peek(date(2026, 10, 1), date(2026, 11, 1), used=1),
        user_id="x",
    )
    assert october.stat_big == "1/10"
    assert october.stat_label == "laws in October · new spaces open 1 November"
    assert "September" not in october.stat_label

    # Missing period_end must still follow period_start, not the calendar clock.
    incomplete = plus_profile_subscription_card(
        card,
        snapshot=SimpleNamespace(playground_law_limit=10),
        roster=_peek(date(2026, 9, 1), None),
        user_id="x",
    )
    assert incomplete.stat_label == "laws in September · new spaces open 1 October"

    source = inspect.getsource(plus_profile_subscription_card)
    assert "8/10" not in source
    assert " = 10" not in source
    assert source.count("10") == 0
    assert "next_playground_month_bounds" not in source


def test_plus_profile_reaches_profile_with_profile_selected(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    page = client.get("/profile")
    assert page.status_code == 200
    html = unescape(page.text)
    header = _header(html)
    assert 'data-plus-profile="desktop"' in html
    assert "data-signed-in-profile" in html
    assert 'href="/profile" class="nav-link is-active"' in header or (
        'href="/profile"' in header and 'aria-current="page"' in header
    )
    assert ">Profile<" in header
    assert "RecallC Plus" in header
    assert "Free account" not in header
    identity = _identity(html)
    assert "Sanjay" in identity
    assert "Signed in with Google" in identity
    assert "renews 1 October" not in identity
    account = _account_list(html)
    assert 'href="/profile"' in account
    assert "Sanjay" in account
    assert 'href="/profile/security/devices"' in account
    assert "Devices" in account
    assert "2 of 3" not in account
    assert " of " in account or "device" in account.lower()
    assert 'href="/settings"' in account
    assert "Learning preferences" in account
    assert "Settings ›" in account
    assert "Report an issue" in account
    assert "data-report-open" in account
    assert 'data-report-section="Profile"' in account
    report_btn = account.split("data-report-open", 1)[1].split("</button>", 1)[0]
    assert "href=" not in report_btn
    assert "data-open-signout" in account
    assert ">Sign out<" in account
    assert 'id="signout-modal"' in html
    assert 'action="/logout"' in html
    assert "data-report-overlay" in html
    for phrase in INVENTED:
        assert phrase not in html, phrase


def test_plus_profile_card_uses_live_subscription_and_roster(
    tmp_path: Path,
) -> None:
    client = _plus_client(tmp_path)
    assert _confirm_add(client, "ndps").status_code == 303
    html = unescape(client.get("/profile").text)
    assert 'data-plus-profile="desktop"' in html
    sub = html.split("data-profile-subscription", 1)[1]
    assert "RecallC Plus" in sub
    assert 'data-chip="active"' in sub
    assert ">ACTIVE<" in sub
    assert "1/10" in sub
    stat, month, nxt, line = _usage_parts(used=1)
    assert stat in sub
    assert line in sub
    assert f"laws in {month}" in sub
    assert f"new spaces open {nxt}" in sub
    assert "September" not in sub
    assert "8/10" not in sub
    assert "Change plan" in sub
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in sub
    assert PLAYGROUND_BILLING_PATH == "/billing/subscriptions"
    assert "Subscribe to add Bare Acts" not in sub
    empty = TestClient(_mu_app(tmp_path / "empty"))
    _sign_in(empty)
    _subscribe(empty)
    empty_sub = unescape(empty.get("/profile").text).split(
        "data-profile-subscription", 1
    )[1]
    assert "0/10" in empty_sub
    assert "1/10" not in empty_sub
    _, month, nxt, empty_line = _usage_parts(used=0)
    assert empty_line in empty_sub
    assert f"laws in {month}" in empty_sub
    assert f"new spaces open {nxt}" in empty_sub
    assert "September" not in empty_sub


def test_plus_profile_get_does_not_mutate_roster(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _plus_client(tmp_path)
    roster = client.app.state.roster
    writes: list[str] = []
    real_ensure = roster.ensure_current_period
    real_capacity = roster.capacity

    def ensure(*args, **kwargs):
        writes.append("ensure")
        return real_ensure(*args, **kwargs)

    def capacity(*args, **kwargs):
        writes.append("capacity")
        return real_capacity(*args, **kwargs)

    monkeypatch.setattr(roster, "ensure_current_period", ensure)
    monkeypatch.setattr(roster, "capacity", capacity)
    before = [
        (row.period_start, row.period_end, row.law_limit, row.status)
        for row in roster.list_periods(USER)
    ]
    html = client.get("/profile").text
    assert 'data-plus-profile="desktop"' in html
    _, month, nxt, line = _usage_parts(used=0)
    assert line in unescape(html)
    assert writes == []
    after = [
        (row.period_start, row.period_end, row.law_limit, row.status)
        for row in roster.list_periods(USER)
    ]
    assert after == before == []

    monkeypatch.setattr(roster, "ensure_current_period", real_ensure)
    monkeypatch.setattr(roster, "capacity", real_capacity)
    assert _confirm_add(client, "ndps").status_code == 303
    writes.clear()
    monkeypatch.setattr(roster, "ensure_current_period", ensure)
    monkeypatch.setattr(roster, "capacity", capacity)
    seeded = [
        (row.period_start, row.period_end, row.law_limit, row.status)
        for row in roster.list_periods(USER)
    ]
    start, end = playground_month_bounds()
    assert seeded
    assert seeded[0][0] == start
    assert seeded[0][1] == end
    used = roster.peek_capacity(USER, None).used
    html = unescape(client.get("/profile").text)
    _, month, nxt, line = _usage_parts(used=used)
    assert line in html
    assert writes == []
    assert [
        (row.period_start, row.period_end, row.law_limit, row.status)
        for row in roster.list_periods(USER)
    ] == seeded


def test_plus_profile_lifecycle_keeps_shared_card_semantics(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path / "cancel"))
    _sign_in(client)
    _subscribe(client, cancel_at_period_end=True)
    html = unescape(client.get("/profile").text)
    assert 'data-plus-profile="desktop"' in html
    assert 'data-chip="active"' in html
    assert "Cancels at the end of the current paid period" in html
    assert "Change plan" in html

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    pending_html = pending.get("/profile").text
    assert 'data-plus-profile="desktop"' not in pending_html
    assert "PENDING" in pending_html or "pending" in pending_html.lower()
    assert "Change plan" not in pending_html


def test_guest_free_pro_profile_are_not_plus_screen_10(tmp_path: Path) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest")).get("/profile").text
    assert 'data-plus-profile="desktop"' not in guest
    assert "RecallC Plus" not in _header(guest)
    assert "data-signed-in-profile" not in guest
    assert "Change plan" not in guest.split("data-guest-profile-desktop", 1)[-1][
        :2000
    ]

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/profile").text
    assert 'data-plus-profile="desktop"' not in free_html
    assert "data-signed-in-profile" in free_html
    assert "RecallC Plus" not in _header(free_html)
    assert ">Subscribe<" in free_html
    assert "Change plan" not in free_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = unescape(pro.get("/profile").text)
    assert 'data-plus-profile="desktop"' not in pro_html
    assert "RecallC Plus" not in _header(pro_html)
    assert "RecallC Pro" in pro_html
    assert "Manage plan" in pro_html
    assert "Change plan" not in pro_html


def test_plus_profile_edit_name_and_sign_out_stay_existing(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    edit = client.get("/profile?edit=name")
    assert edit.status_code == 200
    html = edit.text
    assert 'data-plus-profile="desktop"' in html
    assert 'id="display_name"' in html
    assert "Save name" in html
    assert 'href="/profile"' in html
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
    assert 'id="display_name"' not in saved

    devices = client.get("/profile/security/devices", follow_redirects=False)
    assert devices.status_code == 200
    settings = client.get("/settings", follow_redirects=False)
    assert settings.status_code == 200
    billing = client.get(PLAYGROUND_BILLING_PATH, follow_redirects=False)
    assert billing.status_code in {200, 303}

    out = TestClient(_mu_app(tmp_path / "out"))
    _sign_in(out)
    _subscribe(out)
    logged = out.post(
        "/logout",
        data=_csrf(out),
        follow_redirects=False,
    )
    assert logged.status_code in {303, 302}
    assert out.cookies.get(SESSION_COOKIE_NAME) in {None, ""}


def test_plus_profile_marker_uses_shared_predicate() -> None:
    profile = PROFILE.read_text(encoding="utf-8")
    assert "plus_profile" in profile
    assert 'data-plus-profile="desktop"' in profile
    assert "data-signed-in-profile" in profile
    assert "{{ playground_subscription.title }}" in profile
    assert "{{ playground_subscription.chip }}" in profile
    assert "{{ playground_subscription.stat_big }}" in profile
    assert "{{ playground_subscription.stat_label }}" in profile
    assert "{{ playground_subscription.cta_href }}" in profile
    assert "{{ playground_subscription.cta_label }}" in profile
    assert "{{ device_count_label }}" in profile
    assert "{{ identity_meta" in profile
    assert 'href="/profile/security/devices"' in profile
    assert 'href="/settings"' in profile
    assert "data-report-open" in profile
    assert 'action="/logout"' in profile
    assert "8/10" not in profile
    assert "2 of 3" not in profile
    assert "Change plan" not in profile
    auth = AUTH.read_text(encoding="utf-8")
    assert "request_is_active_plus" in auth
    assert "plus_profile_subscription_card" in auth
    assert '"plus_profile": plus_profile' in auth
    assert "def request_is_active_plus" in DEPS.read_text(encoding="utf-8")
    assert 'snapshot.tier == "plus"' in DEPS.read_text(encoding="utf-8")
    view = VIEW.read_text(encoding="utf-8")
    assert "def plus_profile_subscription_card" in view
    assert "peek_capacity" in view.split("def plus_profile_subscription_card", 1)[1].split(
        "def roster_law_cards", 1
    )[0]
    overlay = view.split("def plus_profile_subscription_card", 1)[1].split(
        "def roster_law_cards", 1
    )[0]
    assert "8/10" not in overlay
    assert " = 10" not in overlay
    base = BASE.read_text(encoding="utf-8")
    assert "plus_profile_chrome" in base
    assert "RecallC Plus" in base
    assert "playground.css?v=pg27" in base
    css = PG_CSS.read_text(encoding="utf-8")
    assert 'data-plus-profile="desktop"' in css
    plus_css = css.split("plus/10-screen", 1)[-1]
    assert "var(--pg-teal-dark)" in plus_css
    assert "#0e7569" not in plus_css
    assert "#3a3a38" not in plus_css
    for phrase in INVENTED_MARKUP:
        assert phrase not in profile, phrase


def test_plus_profile_does_not_touch_accepted_screens_or_services() -> None:
    assert "data-plus-profile" not in LANDING.read_text(encoding="utf-8")
    assert "data-plus-profile" not in BROWSE.read_text(encoding="utf-8")
    assert "data-plus-profile" not in LAWS.read_text(encoding="utf-8")
    assert "data-plus-profile" not in BARE.read_text(encoding="utf-8")
    assert "data-plus-profile" not in ADD.read_text(encoding="utf-8")
    assert "data-plus-profile" not in HOME.read_text(encoding="utf-8")
    assert "data-plus-profile" not in GATE.read_text(encoding="utf-8")
    assert "data-plus-profile" not in MANAGE.read_text(encoding="utf-8")
    assert "data-plus-profile" not in DASH.read_text(encoding="utf-8")
    assert "data-plus-profile" not in CAL.read_text(encoding="utf-8")
    assert "data-plus-profile" not in SETTINGS.read_text(encoding="utf-8")
    assert "data-plus-profile" not in DEVICES.read_text(encoding="utf-8")
    assert 'data-plus-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-plus-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-plus-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-plus-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-plus-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-plus-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-plus-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-plus-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-plus-profile" not in mobile
    phone_profile = mobile.split(
        'body[data-mscreen="account"] .profile-panel > .display {', 1
    )[1].split("}", 1)[0]
    assert "font-size: 22px" in phone_profile
    auth = AUTH.read_text(encoding="utf-8")
    post = auth.split("async def profile_post", 1)[1]
    assert "reset_learning_progress" in post
    assert "delete_account" in post
    overlay = auth.split("async def profile_get", 1)[1].split(
        "async def profile_post", 1
    )[0]
    assert "reset_learning_progress" not in overlay
    assert "ensure_current_device" not in overlay
    assert "/billing/subscriptions/change" not in overlay
    for path in DEVICES_PY.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "plus_profile" not in text
        assert "data-plus-profile" not in text
    for path in BILLING_PY.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "plus_profile" not in text
        assert "data-plus-profile" not in text


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


def test_plus_profile_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    assert _confirm_add(client, "ndps").status_code == 303
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    free_app = _mu_app(tmp_path / "free")
    free_client = TestClient(free_app)
    _sign_in(free_client)
    free_session = free_client.cookies.get(SESSION_COOKIE_NAME)
    assert free_session

    port, _server = _serve(app)
    free_port, _free_server = _serve(free_app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "plus_profile_screen10_1280.png"
    free_path = artifact_dir / "plus_profile_screen10_free_1280.png"
    origin = f"http://127.0.0.1:{port}"
    free_origin = f"http://127.0.0.1:{free_port}"

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
        page.goto(f"{origin}/profile", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-profile="desktop"]');
              const heading = document.querySelector('[data-plus-profile="desktop"] > .display');
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
              const navActive = document.querySelector('.PrimaryTabs--top .nav-link.is-active');
              const editWrap = identity && [...identity.querySelectorAll('p')].find(
                (p) => p.querySelector('.link-btn')
              );
              return {
                present: Boolean(plus),
                heading: heading && heading.textContent.trim(),
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
                stat: stat && (stat.innerText || '').replace(/\\s+/g, ' ').trim(),
                ctaText: cta && (cta.textContent || '').replace(/\\s+/g, ' ').trim(),
                ctaHref: cta && cta.getAttribute('href'),
                reportDisplay: report && getComputedStyle(report).display,
                signoutDisplay: signout && getComputedStyle(signout).display,
                status: status && status.textContent.trim(),
                statusDisplay: status && getComputedStyle(status).display,
                navActive: navActive && navActive.textContent.replace(/\\s+/g, ' ').trim(),
                editDisplay: editWrap ? getComputedStyle(editWrap).display : 'none',
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator('[data-profile-account] [data-report-open]').click()
        report_state = page.evaluate(
            """() => {
              const overlay = document.querySelector('[data-report-overlay]');
              return {
                open: Boolean(overlay && !overlay.hasAttribute('hidden')),
                path: location.pathname,
              };
            }"""
        )
        page.locator("[data-rc-close]").click()
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

        page.set_viewport_size({"width": 390, "height": 844})
        phone = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-profile="desktop"]');
              const grid = plus && plus.querySelector('.pg-profile-grid');
              const identity = document.querySelector('[data-profile-identity]');
              const sub = document.querySelector('[data-profile-subscription]');
              const report = document.querySelector(
                '[data-profile-account] [data-report-open]'
              );
              const identityBox = identity && identity.getBoundingClientRect();
              const subBox = sub && sub.getBoundingClientRect();
              return {
                plusDisplay: plus && getComputedStyle(plus).display,
                gridDisplay: grid ? getComputedStyle(grid).display : null,
                stacked: Boolean(
                  identityBox && subBox && subBox.top > identityBox.bottom - 8
                ),
                reportDisplay: report ? getComputedStyle(report).display : null,
                screen: document.body.getAttribute('data-mscreen'),
              };
            }"""
        )

        free_ctx = browser.new_context(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
        free_ctx.add_cookies(
            [
                {
                    "name": SESSION_COOKIE_NAME,
                    "value": free_session,
                    "url": free_origin,
                    "httpOnly": True,
                    "secure": False,
                    "sameSite": "Lax",
                }
            ]
        )
        free_page = free_ctx.new_page()
        free_page.emulate_media(color_scheme="light")
        free_page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )
        free_page.goto(f"{free_origin}/profile", wait_until="networkidle")
        free_page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        free_geo = free_page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-profile="desktop"]');
              const signed = document.querySelector('[data-signed-in-profile]');
              const cta = document.querySelector('[data-profile-subscription] a.pg-btn');
              const status = document.querySelector('.account-menu-btn-status');
              return {
                plus: Boolean(plus),
                signed: Boolean(signed),
                ctaText: cta && (cta.textContent || '').replace(/\\s+/g, ' ').trim(),
                statusDisplay: status ? getComputedStyle(status).display : 'none',
              };
            }"""
        )
        free_page.evaluate(
            "() => document.activeElement && document.activeElement.blur()"
        )
        free_page.screenshot(path=str(free_path), full_page=False)
        free_ctx.close()
        context.close()
        browser.close()

    assert geo["present"] is True
    assert geo["heading"] == "Profile"
    assert "Sanjay" in (geo["name"] or "")
    assert "Signed in with Google" in (geo["name"] or "")
    assert geo["twoCol"] is True
    assert geo["accountBelowIdentity"] is True
    assert geo["subTitle"] == "RecallC Plus"
    assert geo["chip"] == "ACTIVE"
    assert geo["chipKind"] == "active"
    assert re.search(r"\d+/\d+", geo["stat"] or "")
    assert "8/10" not in (geo["stat"] or "")
    _, month, nxt, _line = _usage_parts(used=1)
    assert f"laws in {month}" in (geo["stat"] or "")
    assert f"new spaces open {nxt}" in (geo["stat"] or "")
    assert "September" not in (geo["stat"] or "")
    assert geo["ctaText"] == "Change plan"
    assert geo["ctaHref"] == PLAYGROUND_BILLING_PATH
    assert geo["reportDisplay"] == "flex"
    assert geo["signoutDisplay"] == "flex"
    assert geo["status"] == "RecallC Plus"
    assert geo["statusDisplay"] != "none"
    assert "Profile" in (geo["navActive"] or "")
    assert geo["editDisplay"] == "none"
    assert report_state["open"] is True
    assert report_state["path"].rstrip("/") == "/profile"
    assert signout_open is True
    assert logout_action == "/logout"
    assert phone["plusDisplay"] != "none"
    assert phone["gridDisplay"] != "grid"
    assert phone["stacked"] is True
    assert phone["reportDisplay"] == "none"
    assert phone["screen"] == "account"
    assert free_geo["plus"] is False
    assert free_geo["signed"] is True
    assert free_geo["ctaText"] == "Subscribe"
    assert shot_path.exists() and shot_path.stat().st_size > 1000
    assert free_path.exists() and free_path.stat().st_size > 1000
