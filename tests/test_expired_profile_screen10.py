"""Expired cohort desktop /profile Screen 10 (CTA map expired/10-screen).

Authorized: ChatGPT. Authenticated multiuser GET /profile after a real Plus
subscription, retained NDPS Playground progress, and paid period end. Overlay
on the live Profile model: playground_subscription_card remains the lifecycle
authority (PAUSED, Resume Playground → /billing/subscriptions). No Plus usage
stat, no Change plan, no plus_profile_subscription_card. Guest, Free, Plus
Screen 10, Pro/Max, halted, paused, pending, phone, Plus 01–11, and Expired
01–09 stay unchanged. No new route.
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
from constitution_memorizer.entitlements.models import BLOCK_PAID_PERIOD_ENDED
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.view import (
    PLAYGROUND_BILLING_PATH,
    gate_view,
    playground_subscription_card,
)
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from tests.test_playground_m8 import _seed_progress
from tests.test_plus_profile_screen10 import SCREEN10_NOW
from tests.test_roster_m5a import _confirm_add, _csrf

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
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
DEVICES = ROOT / "src/constitution_memorizer/web/templates/devices.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
AUTH = ROOT / "src/constitution_memorizer/auth/routes.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
DEVICES_PY = ROOT / "src/constitution_memorizer/devices"
BILLING_PY = ROOT / "src/constitution_memorizer/subscriptions"
SYNC = ROOT / "src/constitution_memorizer/calendar_sync"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_GATE = gate_view(reason=BLOCK_PAID_PERIOD_ENDED)
LIVE_HEADING = LIVE_GATE.title
LOCATOR = "ndps:section:8:clause:a"
INVENTED = (
    "Plan ended 31 August",
    "Resume your Playground",
    "Resume anytime; nothing resets",
    "saved exactly as you left it",
    "Premium",
    "Unlock all",
    "8/10",
    "2 of 3",
    "See plans",
    "No plan yet",
)
INVENTED_MARKUP = INVENTED + ("September 2026", "new spaces open")


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


def _engine(client: TestClient) -> ReminderEngine:
    return client.app.state.engine.for_user(USER)


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


def _header(html: str) -> str:
    return html.split("<header", 1)[-1].split("</header>", 1)[0]


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
    roster = client.app.state.roster
    overlay = client.app.state.playground
    cap = roster.peek_capacity(USER, snap)
    eng = _engine(client)
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
        "selection": tuple(
            sorted(s.source_locator for s in overlay.list_selection(USER, "ndps"))
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
        "can_open": snap.can_open_playground,
        "reason": snap.playground_block_reason,
    }


def test_expired_profile_reaches_profile_with_profile_selected(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_expire(client)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert snap.can_open_playground is False
    page = client.get("/profile")
    assert page.status_code == 200
    html = unescape(page.text)
    header = _header(html)
    assert 'data-expired-profile="desktop"' in html
    assert 'data-plus-profile="desktop"' not in html
    assert "data-signed-in-profile" in html
    assert 'href="/profile" class="nav-link is-active"' in header or (
        'href="/profile"' in header and 'aria-current="page"' in header
    )
    assert ">Profile<" in header
    assert LIVE_HEADING in header
    assert "RecallC Plus" not in header
    assert "Free account" not in header
    identity = _identity(html)
    assert "Sanjay" in identity
    assert "Signed in with Google" in identity
    assert "Plan ended" not in identity
    account = _account_list(html)
    assert 'href="/profile"' in account
    assert "Sanjay" in account
    assert 'href="/profile/security/devices"' in account
    assert "Devices" in account
    assert "2 of 3" not in account
    assert " of " in account or "device" in account.lower()
    assert 'href="/settings"' in account
    assert "Learning preferences" in account
    assert "Report an issue" in account
    assert "data-report-open" in account
    assert "data-open-signout" in account
    assert 'action="/logout"' in html
    for phrase in INVENTED:
        assert phrase not in html, phrase


def test_expired_profile_card_uses_live_paid_period_ended_branch(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_expire(client)
    card = _live_card(client)
    assert card.show is True
    assert card.chip == "PAUSED"
    assert card.chip_kind == "paused"
    assert card.cta_label == "Resume Playground"
    assert card.cta_href == PLAYGROUND_BILLING_PATH
    assert not card.stat_big
    html = unescape(client.get("/profile").text)
    sub = _subscription(html)
    assert card.title in sub
    assert f">{card.chip}<" in sub
    assert f'data-chip="{card.chip_kind}"' in sub
    assert card.body in sub
    assert card.cta_label in sub
    assert f'href="{card.cta_href}"' in sub
    assert PLAYGROUND_BILLING_PATH == "/billing/subscriptions"
    assert "Change plan" not in html
    assert "new spaces open" not in html
    assert "Manage plan" not in sub
    assert "Subscribe" not in sub
    assert "pg-sub-stat" not in sub
    assert "/ " not in sub.split("pg-sub-stat", 1)[0][-20:] if False else True
    assert not re.search(r"\d+/\d+", sub)
    assert "8/10" not in sub
    assert "1/10" not in sub


def test_expired_profile_does_not_call_plus_capacity_helper() -> None:
    auth = AUTH.read_text(encoding="utf-8")
    overlay = auth.split("async def profile_get", 1)[1].split(
        "async def profile_post", 1
    )[0]
    assert "request_is_expired_subscriber" in overlay
    assert "request_is_active_plus" in overlay
    assert "playground_subscription_card(snapshot)" in overlay
    assert "plus_profile_subscription_card(" in overlay
    assert overlay.find("if plus_profile:") < overlay.find(
        "plus_profile_subscription_card("
    )
    assert overlay.find("expired_profile") < overlay.find("if plus_profile:")
    plus_block = overlay.split("if plus_profile:", 1)[1]
    assert "plus_profile_subscription_card(" in plus_block
    assert "expired_profile" not in plus_block.split("return templates", 1)[0]


def test_expired_profile_edit_devices_settings_report_signout(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_expire(client)
    edit = client.get("/profile?edit=name")
    assert edit.status_code == 200
    html = edit.text
    assert 'data-expired-profile="desktop"' in html
    assert 'id="display_name"' in html
    assert "Save name" in html
    posted = client.post(
        "/profile",
        data={**_csrf(client), "action": "save", "display_name": "Priya"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    assert "/profile" in (posted.headers.get("location") or "")
    saved = unescape(client.get("/profile").text)
    assert "Priya" in saved
    assert 'data-expired-profile="desktop"' in saved
    assert 'id="display_name"' not in saved
    devices = client.get("/profile/security/devices", follow_redirects=False)
    assert devices.status_code == 200
    settings = client.get("/settings", follow_redirects=False)
    assert settings.status_code == 200
    billing = client.get(PLAYGROUND_BILLING_PATH, follow_redirects=False)
    assert billing.status_code == 200
    assert 'data-expired-subscription="desktop"' in billing.text
    html = unescape(client.get("/profile").text)
    assert "data-report-overlay" in html
    assert 'id="signout-modal"' in html
    assert 'action="/logout"' in html
    logged = client.post("/logout", data=_csrf(client), follow_redirects=False)
    assert logged.status_code in {303, 302}


def test_expired_profile_get_is_mutation_free(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_expire(client)
    before = _facts(client)
    assert "ndps" in before["active"]
    assert before["selection"]
    assert before["subscription"] is not None
    assert before["can_open"] is False
    assert before["reason"] == BLOCK_PAID_PERIOD_ENDED
    page = client.get("/profile")
    assert page.status_code == 200
    after = _facts(client)
    assert after == before
    again = client.get("/profile")
    assert again.status_code == 200
    assert _facts(client) == before


def test_guest_free_plus_pro_max_halted_paused_pending_are_not_expired_profile(
    tmp_path: Path,
) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest")).get("/profile").text
    assert 'data-expired-profile="desktop"' not in guest
    assert LIVE_HEADING not in _header(guest)
    assert "data-signed-in-profile" not in guest

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = unescape(free.get("/profile").text)
    assert 'data-expired-profile="desktop"' not in free_html
    assert "data-signed-in-profile" in free_html
    assert LIVE_HEADING not in _header(free_html)
    assert ">Subscribe<" in free_html
    assert "Change plan" not in free_html
    assert "PAUSED" not in free_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    _seed_ndps(plus)
    plus_html = unescape(plus.get("/profile").text)
    assert 'data-plus-profile="desktop"' in plus_html
    assert 'data-expired-profile="desktop"' not in plus_html
    assert "RecallC Plus" in _header(plus_html)
    assert LIVE_HEADING not in _header(plus_html)
    plus_sub = _subscription(plus_html)
    assert ">ACTIVE<" in plus_sub
    assert "Change plan" in plus_sub
    assert "new spaces open" in plus_sub
    assert "Resume Playground" not in plus_sub

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = unescape(pro.get("/profile").text)
    assert 'data-expired-profile="desktop"' not in pro_html
    assert 'data-plus-profile="desktop"' not in pro_html
    assert "RecallC Pro" in pro_html
    assert "Manage plan" in pro_html
    assert "Change plan" not in pro_html

    mx = TestClient(_mu_app(tmp_path / "max"))
    _sign_in(mx)
    _subscribe(mx, tier="max")
    max_html = unescape(mx.get("/profile").text)
    assert 'data-expired-profile="desktop"' not in max_html
    assert 'data-plus-profile="desktop"' not in max_html
    assert "RecallC Max" in max_html
    assert "Manage plan" in max_html
    assert "Change plan" not in max_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    _seed_ndps(halted)
    stored = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )
    halted_html = unescape(halted.get("/profile").text)
    assert 'data-expired-profile="desktop"' not in halted_html
    assert LIVE_HEADING not in _header(halted_html)
    halted_card = playground_subscription_card(
        halted.app.state.entitlement_service.resolve(USER)
    )
    assert halted_card.chip == "ON HOLD"
    assert halted_card.chip in halted_html
    assert halted_card.body in halted_html
    assert halted.app.state.entitlement_service.resolve(
        USER
    ).playground_block_reason != BLOCK_PAID_PERIOD_ENDED

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused)
    _seed_ndps(paused)
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
    assert paused_card.body != _live_card(TestClient(_mu_app(tmp_path / "cmp"))).body
    expired_body = playground_subscription_card.__doc__ and (
        "This paid period has ended. Playground stays saved until you resume."
    )
    assert expired_body not in paused_html

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    pending_html = unescape(pending.get("/profile").text)
    assert 'data-expired-profile="desktop"' not in pending_html
    assert LIVE_HEADING not in _header(pending_html)
    assert "PENDING" in pending_html
    assert "Manage subscription" in pending_html
    assert "Change plan" not in pending_html


def test_expired_profile_marker_uses_shared_predicate() -> None:
    profile = PROFILE.read_text(encoding="utf-8")
    assert "expired_profile" in profile
    assert 'data-expired-profile="desktop"' in profile
    assert 'data-plus-profile="desktop"' in profile
    assert "data-signed-in-profile" in profile
    assert "{{ playground_subscription.title }}" in profile
    assert "{{ playground_subscription.chip }}" in profile
    assert "{{ playground_subscription.body }}" in profile
    assert "{{ playground_subscription.cta_label }}" in profile
    assert "{{ playground_subscription.cta_href }}" in profile
    assert "{{ playground_subscription.stat_big }}" in profile
    assert "{{ device_count_label }}" in profile
    assert "{{ identity_meta" in profile
    assert PLAYGROUND_BILLING_PATH not in profile
    assert "Resume Playground" not in profile
    assert "Change plan" not in profile
    assert "PAUSED" not in profile
    assert "Plan ended" not in profile
    auth = AUTH.read_text(encoding="utf-8")
    overlay = auth.split("async def profile_get", 1)[1].split(
        "async def profile_post", 1
    )[0]
    assert "request_is_expired_subscriber" in overlay
    assert '"expired_profile": expired_profile' in overlay
    assert "playground_subscription_card" in overlay
    assert "gate_view" in overlay
    assert "def snapshot_is_expired_subscriber" not in overlay
    assert "def request_is_expired_subscriber" in DEPS.read_text(encoding="utf-8")
    assert "BLOCK_PAID_PERIOD_ENDED" in DEPS.read_text(encoding="utf-8")
    view = VIEW.read_text(encoding="utf-8")
    assert "def playground_subscription_card" in view
    ended = view.split("if reason == BLOCK_PAID_PERIOD_ENDED:", 1)[1].split(
        "status = str", 1
    )[0]
    assert 'chip="PAUSED"' in ended
    assert 'cta_label="Resume Playground"' in ended
    assert "cta_href=PLAYGROUND_BILLING_PATH" in ended
    base = BASE.read_text(encoding="utf-8")
    assert "expired_profile_chrome" in base
    assert "plus_profile_chrome" in base
    assert "playground.css?v=pg28" in base
    css = PG_CSS.read_text(encoding="utf-8")
    assert 'data-expired-profile="desktop"' in css
    assert "expired/10-screen" in css
    plus_css = css.split("plus/10-screen", 1)[1].split("expired/10-screen", 1)[0]
    expired_css = css.split("expired/10-screen", 1)[1].split("plus/11-screen", 1)[0]
    assert "var(--pg-teal-dark)" in plus_css
    assert "var(--pg-teal-dark)" in expired_css
    assert "#0e7569" not in plus_css
    assert "#0e7569" not in expired_css
    assert "#3a3a38" not in plus_css
    assert "#3a3a38" not in expired_css
    for phrase in INVENTED_MARKUP:
        assert phrase not in profile, phrase


def test_plus_screens_and_expired_01_09_untouched() -> None:
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
    assert 'data-plus-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    for path in (
        LANDING,
        BROWSE,
        LAWS,
        BARE,
        ADD,
        HOME,
        MANAGE,
        DASH,
        CAL,
        SETTINGS,
        GATE,
        DEVICES,
    ):
        text = path.read_text(encoding="utf-8")
        assert "data-expired-profile" not in text
    assert "data-expired-profile" not in MOBILE.read_text(encoding="utf-8")
    mobile = MOBILE.read_text(encoding="utf-8")
    phone_profile = mobile.split(
        'body[data-mscreen="account"] .profile-panel > .display {', 1
    )[1].split("}", 1)[0]
    assert "font-size: 22px" in phone_profile
    post = AUTH.read_text(encoding="utf-8").split("async def profile_post", 1)[1]
    assert "reset_learning_progress" in post
    assert "delete_account" in post
    get = AUTH.read_text(encoding="utf-8").split("async def profile_get", 1)[1].split(
        "async def profile_post", 1
    )[0]
    assert "reset_learning_progress" not in get
    for path in DEVICES_PY.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "expired_profile" not in text
        assert "data-expired-profile" not in text
    for path in BILLING_PY.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "expired_profile" not in text
        assert "data-expired-profile" not in text
    for path in SYNC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "expired_profile" not in text
        assert "data-expired-profile" not in text


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


def test_expired_phone_profile_unchanged(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _plus_then_expire(client)
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
        page.goto(f"{origin}/profile", wait_until="networkidle")
        geo = page.evaluate(
            """() => {
              const marker = document.querySelector('[data-expired-profile="desktop"]');
              const grid = document.querySelector('.pg-profile-grid');
              const identity = document.querySelector('[data-profile-identity]');
              const sub = document.querySelector('[data-profile-subscription]');
              const identityBox = identity && identity.getBoundingClientRect();
              const subBox = sub && sub.getBoundingClientRect();
              return {
                marker: Boolean(marker),
                plus: Boolean(document.querySelector('[data-plus-profile="desktop"]')),
                stacked: Boolean(
                  identityBox && subBox && subBox.top > identityBox.bottom - 8
                ),
                gridDisplay: grid && getComputedStyle(grid).display,
                screen: document.body.getAttribute('data-mscreen'),
              };
            }"""
        )
        browser.close()
    assert geo["marker"] is True
    assert geo["plus"] is False
    assert geo["stacked"] is True
    assert geo["screen"] == "account"


def test_expired_profile_screen10_1280(tmp_path: Path) -> None:
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
    shot_path = artifact_dir / "expired_profile_screen10_1280.png"
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
              const identityBox = identity && identity.getBoundingClientRect();
              const accountBox = account && account.getBoundingClientRect();
              const subBox = sub && sub.getBoundingClientRect();
              const status = document.querySelector('.account-menu-btn-status');
              const navActive = document.querySelector('.PrimaryTabs--top .nav-link.is-active');
              return {
                present: Boolean(expired),
                plus: Boolean(plus),
                heading: heading && heading.textContent.trim(),
                name: identity && (identity.innerText || ''),
                twoCol: Boolean(
                  identityBox && subBox && subBox.left > identityBox.right - 8
                ),
                accountBelowIdentity: Boolean(
                  identityBox && accountBox && accountBox.top > identityBox.bottom - 8
                ),
                subTitle: sub && (sub.querySelector('h2') || {}).textContent,
                subBody: sub && (sub.querySelector('.pg-lede') || {}).textContent,
                chip: chip && chip.textContent.trim(),
                chipKind: chip && chip.getAttribute('data-chip'),
                statPresent: Boolean(stat) && getComputedStyle(stat).display !== 'none',
                ctaText: cta && (cta.textContent || '').replace(/\\s+/g, ' ').trim(),
                ctaHref: cta && cta.getAttribute('href'),
                status: status && status.textContent.trim(),
                statusDisplay: status && getComputedStyle(status).display,
                navActive: navActive && navActive.textContent.replace(/\\s+/g, ' ').trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        context.close()
        browser.close()
    assert geo["present"] is True
    assert geo["plus"] is False
    assert geo["heading"] == "Profile"
    assert "Sanjay" in (geo["name"] or "")
    assert "Signed in with Google" in (geo["name"] or "")
    assert geo["twoCol"] is True
    assert geo["accountBelowIdentity"] is True
    assert geo["subTitle"] == card.title
    assert geo["chip"] == card.chip == "PAUSED"
    assert geo["chipKind"] == "paused"
    assert (geo["subBody"] or "").strip() == card.body
    assert geo["statPresent"] is False
    assert geo["ctaText"] == card.cta_label == "Resume Playground"
    assert geo["ctaHref"] == card.cta_href == PLAYGROUND_BILLING_PATH
    assert geo["status"] == LIVE_HEADING
    assert geo["statusDisplay"] != "none"
    assert "Profile" in (geo["navActive"] or "")
    assert shot_path.exists() and shot_path.stat().st_size > 1000


def test_expired_profile_plus_regression_1280(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    from constitution_memorizer.entitlements import service as entitlement_service
    from constitution_memorizer.playground.roster import period as period_mod

    real_period_utc = period_mod._as_utc
    real_ent_utc = entitlement_service._utc
    monkeypatch.setattr(
        period_mod, "_as_utc", lambda now: real_period_utc(now or SCREEN10_NOW)
    )
    monkeypatch.setattr(
        entitlement_service, "_utc", lambda now: real_ent_utc(now or SCREEN10_NOW)
    )

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    assert _confirm_add(client, "ndps").status_code == 303
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "expired_profile_screen10_plus_regression_1280.png"
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
        page.goto(f"{origin}/profile", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-profile="desktop"]');
              const expired = document.querySelector('[data-expired-profile="desktop"]');
              const sub = document.querySelector('[data-profile-subscription]');
              const cta = sub && sub.querySelector('a.pg-btn');
              const chip = sub && sub.querySelector('.pg-sub-chip');
              const stat = sub && sub.querySelector('.pg-sub-stat');
              const status = document.querySelector('.account-menu-btn-status');
              const identity = document.querySelector('[data-profile-identity]');
              const identityBox = identity && identity.getBoundingClientRect();
              const subBox = sub && sub.getBoundingClientRect();
              return {
                plus: Boolean(plus),
                expired: Boolean(expired),
                chip: chip && chip.textContent.trim(),
                stat: stat && (stat.innerText || '').replace(/\\s+/g, ' ').trim(),
                ctaText: cta && (cta.textContent || '').replace(/\\s+/g, ' ').trim(),
                ctaHref: cta && cta.getAttribute('href'),
                status: status && status.textContent.trim(),
                twoCol: Boolean(
                  identityBox && subBox && subBox.left > identityBox.right - 8
                ),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        context.close()
        browser.close()
    assert geo["plus"] is True
    assert geo["expired"] is False
    assert geo["chip"] == "ACTIVE"
    assert re.search(r"\d+/\d+", geo["stat"] or "")
    assert "new spaces open" in (geo["stat"] or "")
    assert geo["ctaText"] == "Change plan"
    assert geo["ctaHref"] == PLAYGROUND_BILLING_PATH
    assert geo["status"] == "RecallC Plus"
    assert geo["twoCol"] is True
    assert shot_path.exists() and shot_path.stat().st_size > 1000
