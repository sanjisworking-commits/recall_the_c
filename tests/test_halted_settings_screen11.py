"""Halted cohort desktop /settings Screen 11 (CTA map halted/11-screen).

Authorized: ChatGPT. Authenticated multiuser GET /settings after a real Plus
subscription is halted. Overlay on the live Settings model:
request_is_halted_subscriber selects the cohort; header/account status come
from live gate_view(BLOCK_PAYMENT_HALTED); Auto Plan follows can_use_auto_plan;
locked copy stays the existing /pricing unlock row. Guest, Free, Plus
Screen 11, Expired Screen 11, Pro/Max, paused, pending, phone, Plus 01–11,
Expired 01–11, and Halted 01–10 stay unchanged. No new route. No /resume.
"""

from __future__ import annotations

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
    SESSION_COOKIE_NAME,
    InMemorySessionStore,
)
from constitution_memorizer.calendar_sync.sync import calendar_prefs
from constitution_memorizer.entitlements.models import (
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
)
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
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
APP = ROOT / "src/constitution_memorizer/web/app.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
CAL_SYNC = ROOT / "src/constitution_memorizer/calendar_sync"
PLANNER = ROOT / "src/constitution_memorizer/planner"
AUTH_PY = ROOT / "src/constitution_memorizer/auth"
BILLING_PY = ROOT / "src/constitution_memorizer/subscriptions"
USER = UUID("11111111-1111-4111-8111-111111111111")
TOKEN_KEY = Fernet.generate_key().decode()
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_GATE = gate_view(reason=BLOCK_PAYMENT_HALTED)
LIVE_HEADING = LIVE_GATE.title
LIVE_EXPIRED = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
LOCKED_COPY = (
    "Part of unlocking every Article — your saved history is never deleted."
)
INVENTED = (
    "Plan ended 31 August",
    "Resume Playground",
    "Resume your Playground",
    "Your Playground is paused",
    "Playground paused",
    "This paid period has ended",
    "Automatic retries have stopped",
    "Subscription paused",
    "Premium",
    "Unlock all",
    "No plan yet",
    "See plans",
    "8/10",
)
INVENTED_MARKUP = INVENTED + (
    "RecallC Plus",
    "Payment retries have stopped",
    "Manage subscription",
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


def _halt(client: TestClient) -> None:
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None
    client.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )


def _engine(client: TestClient) -> ReminderEngine:
    return client.app.state.engine.for_user(USER)


def _plus_then_halt(client: TestClient) -> None:
    _subscribe(client)
    _halt(client)


def _halted_client(tmp_path: Path, **kwargs) -> TestClient:
    client = TestClient(
        _mu_app(tmp_path, entitlements=True, pricing=True, **kwargs)
    )
    _sign_in(client)
    _plus_then_halt(client)
    return client


def _header(html: str) -> str:
    return html.split("<header", 1)[-1].split("</header>", 1)[0]


def _account_row(html: str) -> str:
    return html.split("settings-account-row", 1)[1].split("</a>", 1)[0]


def _study(html: str) -> str:
    return html.split('data-settings-group="study"', 1)[1]


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
    plan = eng.get_learning_plan()
    planned = tuple(
        sorted(
            (
                day.plan_date.isoformat(),
                tuple((item.learning_unit_id, item.position) for item in day.items),
            )
            for day in eng.list_auto_plan_window(date(2026, 1, 1), date(2026, 12, 31))
        )
    )
    store = getattr(client.app.state, "calendar_store", None)
    if store is None:
        connection = None
    else:
        conn = store.get_connection(USER)
        connection = None if conn is None else (
            conn.google_calendar_id,
            conn.is_active,
            conn.sync_pending,
            conn.sync_status,
        )
    prefs = calendar_prefs(eng)
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
        "plan": None
        if plan is None
        else (
            plan.mode,
            plan.daily_target,
            plan.activated_at,
            plan.target_effective_on,
            plan.prompt_dismissed_on,
            plan.last_anchor_theme,
        ),
        "auto_plan": planned,
        "frequency": eng.get_notification_frequency(),
        "connection": connection,
        "prefs": (
            prefs["timezone"],
            prefs["revision_time"],
            prefs["session_minutes"],
            prefs["reminder_cadence"],
            prefs["cadence_chosen"],
        ),
        "can_open": snap.can_open_playground,
        "reason": snap.playground_block_reason,
        "status": snap.subscription_status,
    }


def test_halted_settings_reaches_settings_with_live_header(tmp_path: Path) -> None:
    client = _halted_client(tmp_path)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.subscription_status == "halted"
    assert snap.playground_block_reason == BLOCK_PAYMENT_HALTED
    assert snap.can_open_playground is False
    page = client.get("/settings")
    assert page.status_code == 200
    html = unescape(page.text)
    header = _header(html)
    assert 'data-halted-settings="desktop"' in html
    assert 'data-plus-settings="desktop"' not in html
    assert 'data-expired-settings="desktop"' not in html
    assert "data-signed-in-settings" in html
    top_nav = header.split("PrimaryTabs--top", 1)[1].split("</nav>", 1)[0]
    assert "Settings" not in top_nav
    assert LIVE_HEADING in header
    assert LIVE_EXPIRED not in header
    assert "RecallC Plus" not in header
    assert "Free account" not in header
    assert 'href="/dashboard"' in html
    assert "← Today" in html
    assert 'class="settings-account-row" href="/profile"' in html
    row = _account_row(html)
    assert "Sanjay" in row
    assert LIVE_HEADING in row
    assert LIVE_EXPIRED not in row
    assert "Playground paused" not in row
    assert "Recall active" not in row
    assert "Appearance, your learning plan, and your revision calendar." in html
    assert "/resume" not in html
    assert "Resume Playground" not in html
    for phrase in INVENTED:
        assert phrase not in html, phrase


def test_halted_settings_learning_plan_follows_can_auto_plan(
    tmp_path: Path,
) -> None:
    client = _halted_client(tmp_path)
    html = unescape(client.get("/settings").text)
    study = _study(html)
    assert "Learning plan" in study
    assert "Self-paced" in study
    assert "Auto Plan" in study
    assert 'id="pace-self-paced"' in study
    assert "checked" in study.split('id="pace-self-paced"', 1)[1].split(">", 1)[0]
    assert "disabled" not in study.split('id="pace-self-paced"', 1)[1].split(">", 1)[0]
    assert "disabled" in study.split('id="pace-auto"', 1)[1].split(">", 1)[0]
    assert 'class="segmented is-disabled"' in study
    assert LOCKED_COPY in study
    assert 'href="/pricing"' in study
    assert "Unlock every Article →" in study
    assert 'href="/billing/subscriptions"' not in study
    assert "Manage subscription" not in study
    assert 'id="target-5"' not in study
    assert "Steady · 3" not in study
    assert "Balanced · 5" not in study
    assert "Intensive · 7" not in study
    assert 'action="/settings/learning-plan"' in html
    assert "Save learning plan" in html
    assert (
        "Changing the pace rebuilds future days from tomorrow — today's plan holds."
        in html
    )
    before = _facts(client)
    saved = client.post(
        "/settings/learning-plan",
        data={**_csrf(client), "mode": "self_paced"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert saved.headers["location"].startswith("/settings")
    plan = _engine(client).get_learning_plan()
    assert plan.mode == "self_paced"
    after_self = _facts(client)
    assert after_self["subscription"] == before["subscription"]
    assert after_self["history"] == before["history"]
    assert after_self["active"] == before["active"]
    assert after_self["removed"] == before["removed"]
    assert after_self["progress"] == before["progress"]
    assert after_self["constitution"] == before["constitution"]
    assert after_self["connection"] == before["connection"]
    refused = client.post(
        "/settings/learning-plan",
        data={**_csrf(client), "mode": "auto", "daily_target": "7"},
        follow_redirects=False,
    )
    assert refused.status_code == 303
    after = _engine(client).get_learning_plan()
    assert after.mode == "self_paced"
    assert after.daily_target not in (3, 5, 7) or after.mode != "auto"
    refused_facts = _facts(client)
    assert refused_facts["auto_plan"] == after_self["auto_plan"]
    assert refused_facts["subscription"] == after_self["subscription"]
    assert refused_facts["active"] == after_self["active"]
    assert refused_facts["progress"] == after_self["progress"]
    assert refused_facts["constitution"] == after_self["constitution"]


def test_halted_settings_does_not_clear_saved_auto_plan_on_get(
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
    _halt(client)
    page = client.get("/settings")
    assert page.status_code == 200
    html = unescape(page.text)
    assert 'data-halted-settings="desktop"' in html
    after = _engine(client).get_learning_plan()
    assert after.mode == "auto"
    assert after.daily_target == 5
    assert after.activated_at == activated


def test_halted_settings_calendar_routes_and_live_gcal(tmp_path: Path) -> None:
    client = _halted_client(tmp_path)
    html = unescape(client.get("/settings").text)
    assert 'data-settings-group="calendar"' in html
    assert "Revision calendar" in html
    assert "Connect Google Calendar" in html
    assert 'href="/calendar/google/connect"' in html
    assert 'href="/privacy#google-calendar"' in html
    assert "Recall the C — Revision Schedule" in html
    assert "Last synced" not in html
    connect = client.get("/calendar/google/connect", follow_redirects=False)
    assert connect.status_code in {302, 303}
    privacy = client.get("/privacy", follow_redirects=False)
    assert privacy.status_code == 200
    assert "google-calendar" in privacy.text
    src = SETTINGS.read_text(encoding="utf-8")
    assert "gcal.connected" in src
    assert "gcal.connection" in src
    assert "gcal.prefs" in src
    assert "gcal.status_param" in src
    assert 'action="/calendar/google/preferences"' in src
    assert 'action="/calendar/google/disconnect"' in src
    assert 'href="/calendar/google/connect"' in src
    assert 'href="/privacy#google-calendar"' in src


def test_halted_settings_get_is_mutation_free(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path, entitlements=True, pricing=True))
    _sign_in(client)
    _subscribe(client)
    _engine(client).upsert_learning_plan(
        mode="auto", daily_target=3, as_of=date(2026, 9, 16)
    )
    _halt(client)
    before = _facts(client)
    assert before["subscription"] is not None
    assert before["subscription"][1] == "halted"
    assert before["can_open"] is False
    assert before["reason"] == BLOCK_PAYMENT_HALTED
    assert before["status"] == "halted"
    assert before["plan"][0] == "auto"
    assert before["plan"][1] == 3
    page = client.get("/settings")
    assert page.status_code == 200
    after = _facts(client)
    assert after == before
    again = client.get("/settings")
    assert again.status_code == 200
    assert _facts(client) == before


def test_halted_elapsed_period_stays_halted_on_settings(tmp_path: Path) -> None:
    client = _halted_client(tmp_path)
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
    html = unescape(client.get("/settings").text)
    header = _header(html)
    row = _account_row(html)
    study = _study(html)
    assert 'data-halted-settings="desktop"' in html
    assert 'data-expired-settings="desktop"' not in html
    assert 'data-plus-settings="desktop"' not in html
    assert LIVE_HEADING in header
    assert LIVE_EXPIRED not in header
    assert LIVE_HEADING in row
    assert LIVE_EXPIRED not in row
    assert "disabled" in study.split('id="pace-auto"', 1)[1].split(">", 1)[0]
    assert LOCKED_COPY in study
    assert LIVE_EXPIRED not in html
    assert "Resume Playground" not in html
    assert "/resume" not in html


def test_guest_free_plus_expired_paused_pending_are_not_halted_settings(
    tmp_path: Path,
) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest")).get("/settings").text
    assert 'data-halted-settings="desktop"' not in guest
    assert LIVE_HEADING not in _header(guest)
    assert "data-signed-in-settings" not in guest

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = unescape(free.get("/settings").text)
    assert 'data-halted-settings="desktop"' not in free_html
    assert "data-signed-in-settings" in free_html
    assert LIVE_HEADING not in _header(free_html)
    assert "RecallC Plus" not in _header(free_html)

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = unescape(plus.get("/settings").text)
    assert 'data-plus-settings="desktop"' in plus_html
    assert 'data-halted-settings="desktop"' not in plus_html
    assert 'data-expired-settings="desktop"' not in plus_html
    assert "RecallC Plus" in _header(plus_html)
    assert LIVE_HEADING not in _header(plus_html)
    plus_study = _study(plus_html)
    assert "disabled" not in plus_study.split('id="pace-auto"', 1)[1].split(">", 1)[0]
    assert "Steady · 3" in plus_study
    assert LOCKED_COPY not in plus_study
    assert "Change plan" not in plus_html

    expired = TestClient(_mu_app(tmp_path / "expired", entitlements=True, pricing=True))
    _sign_in(expired)
    _subscribe(expired)
    stored_e = expired.app.state.subscriptions.get_current_subscription(USER)
    expired.app.state.subscriptions.update_subscription_state(
        USER,
        stored_e.id,
        status="expired",
        billing_period_start=EXPIRED_START,
        billing_period_end=EXPIRED_END,
    )
    expired_html = unescape(expired.get("/settings").text)
    assert 'data-expired-settings="desktop"' in expired_html
    assert 'data-halted-settings="desktop"' not in expired_html
    assert 'data-plus-settings="desktop"' not in expired_html
    assert LIVE_EXPIRED in _header(expired_html)
    assert LIVE_HEADING not in _header(expired_html)
    expired_study = _study(expired_html)
    assert "disabled" in expired_study.split('id="pace-auto"', 1)[1].split(">", 1)[0]
    assert LOCKED_COPY in expired_study

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused)
    stored_p = paused.app.state.subscriptions.get_current_subscription(USER)
    paused.app.state.subscriptions.update_subscription_state(
        USER, stored_p.id, status="paused"
    )
    paused_html = unescape(paused.get("/settings").text)
    assert 'data-halted-settings="desktop"' not in paused_html
    assert LIVE_HEADING not in _header(paused_html)

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    pending_html = unescape(pending.get("/settings").text)
    assert 'data-halted-settings="desktop"' not in pending_html
    assert LIVE_HEADING not in _header(pending_html)

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = unescape(pro.get("/settings").text)
    assert 'data-halted-settings="desktop"' not in pro_html
    assert 'data-plus-settings="desktop"' not in pro_html
    assert LIVE_HEADING not in _header(pro_html)

    mx = TestClient(_mu_app(tmp_path / "max"))
    _sign_in(mx)
    _subscribe(mx, tier="max")
    max_html = unescape(mx.get("/settings").text)
    assert 'data-halted-settings="desktop"' not in max_html
    assert 'data-plus-settings="desktop"' not in max_html
    assert LIVE_HEADING not in _header(max_html)


def test_halted_settings_marker_uses_shared_predicate() -> None:
    settings = SETTINGS.read_text(encoding="utf-8")
    assert "halted_settings" in settings
    assert 'data-halted-settings="desktop"' in settings
    assert 'data-plus-settings="desktop"' in settings
    assert 'data-expired-settings="desktop"' in settings
    assert "data-signed-in-settings" in settings
    plus_i = settings.find('data-plus-settings="desktop"')
    halted_i = settings.find('data-halted-settings="desktop"')
    expired_i = settings.find('data-expired-settings="desktop"')
    assert plus_i < halted_i < expired_i
    assert "can_auto_plan|default(false)" in settings
    assert "{{ halted_header_status }}" in settings
    assert "{{ expired_header_status }}" in settings
    assert "{{ access.status_line }}" in settings
    assert LOCKED_COPY in settings
    assert 'href="/pricing"' in settings
    assert "Unlock every Article →" in settings
    assert "/billing/subscriptions" not in settings
    assert 'action="/settings/learning-plan"' in settings
    assert 'href="/calendar/google/connect"' in settings
    assert 'href="/privacy#google-calendar"' in settings
    assert 'href="/dashboard"' in settings
    assert 'href="/profile"' in settings
    assert "RecallC Plus" not in settings
    assert "Your Playground is paused" not in settings
    assert "Playground paused" not in settings
    assert "Payment retries have stopped" not in settings
    assert "Resume Playground" not in settings
    assert "Manage subscription" not in settings
    assert "/resume" not in settings
    app = APP.read_text(encoding="utf-8")
    page = app.split("async def settings_page", 1)[1].split(
        "async def settings_save", 1
    )[0]
    assert "request_is_halted_subscriber" in page
    assert "request_is_expired_subscriber" in page
    assert "request_is_active_plus" in page
    assert "BLOCK_PAYMENT_HALTED" in page
    assert '"halted_settings": halted_settings' in page
    assert '"expired_settings": expired_settings' in page
    assert '"plus_settings": plus_settings' in page
    assert '"halted_header_status": halted_header_status' in page
    assert "can_use_auto_plan" in page
    assert '"can_auto_plan": auto_entitled' in page
    assert "can_auto_plan = False" not in page
    assert "gate_view" in page
    assert "upsert_learning_plan" not in page
    assert "def snapshot_is_halted_subscriber" not in page
    plan_post = app.split("async def settings_learning_plan", 1)[1].split(
        "async def choose_get", 1
    )[0]
    assert "halted_settings" not in plan_post
    assert "request_is_halted_subscriber" not in plan_post
    assert "expired_settings" not in plan_post
    assert "can_use_auto_plan" in plan_post
    assert "def request_is_halted_subscriber" in DEPS.read_text(encoding="utf-8")
    assert 'subscription_status == "halted"' in DEPS.read_text(encoding="utf-8")
    base = BASE.read_text(encoding="utf-8")
    assert "halted_settings_chrome" in base
    assert "plus_settings_chrome" in base
    assert "expired_settings_chrome" in base
    assert LIVE_HEADING not in base
    assert "/resume" not in base
    assert "playground.css?v=pg36" in base
    css = PG_CSS.read_text(encoding="utf-8")
    assert 'data-halted-settings="desktop"' in css
    assert "halted/11-screen" in css
    assert 'data-expired-settings="desktop"' in css
    assert "expired/11-screen" in css
    assert 'data-plus-settings="desktop"' in css
    plus_css = css.split("plus/11-screen", 1)[1].split("expired/11-screen", 1)[0]
    halted_css = css.split("halted/11-screen", 1)[1]
    assert "var(--ink)" in plus_css
    assert 'data-halted-settings="desktop"' in halted_css
    assert 'data-expired-settings="desktop"' in halted_css
    assert "#0e7569" not in plus_css
    assert "#0e7569" not in halted_css
    assert "#3a3a38" not in plus_css
    assert "#3a3a38" not in halted_css
    for phrase in INVENTED_MARKUP:
        assert phrase not in settings, phrase


def test_plus_expired_and_halted_01_10_untouched() -> None:
    assert 'data-halted-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-halted-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-halted-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-halted-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-halted-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-halted-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-halted-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-halted-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-halted-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-halted-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    assert 'data-expired-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
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
        PROFILE,
        GATE,
    ):
        text = path.read_text(encoding="utf-8")
        assert "data-halted-settings" not in text
    mobile = MOBILE.read_text(encoding="utf-8")
    generic, _, rest = mobile.partition("is signedIn/07-screen:")
    assert "data-halted-settings" not in generic
    phone_block = rest.split("/* R1 — Playground phone shell", 1)[0]
    assert ":not([data-halted-settings])" in phone_block
    assert 'data-halted-settings="desktop"' not in phone_block
    phone_desk = mobile.split(
        'body[data-mscreen="settings"] .settings-desk-copy {', 1
    )[1].split("}", 1)[0]
    assert "display: none" in phone_desk
    settings = SETTINGS.read_text(encoding="utf-8")
    assert "settings-phone-only" in settings
    assert "data-gcal-toggle" in settings
    for path in CAL_SYNC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "halted_settings" not in text
        assert "data-halted-settings" not in text
    for path in PLANNER.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "halted_settings" not in text
        assert "data-halted-settings" not in text
    for path in AUTH_PY.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "halted_settings" not in text
        assert "data-halted-settings" not in text
    for path in BILLING_PY.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "halted_settings" not in text
        assert "data-halted-settings" not in text
    plan_post = APP.read_text(encoding="utf-8").split(
        "async def settings_learning_plan", 1
    )[1].split("async def choose_get", 1)[0]
    assert "halted_settings" not in plan_post
    get = APP.read_text(encoding="utf-8").split("async def settings_page", 1)[1].split(
        "async def settings_save", 1
    )[0]
    assert "upsert_learning_plan" not in get


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


def test_halted_phone_settings_unchanged(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, entitlements=True, pricing=True)
    client = TestClient(app)
    _sign_in(client)
    _plus_then_halt(client)
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
        page.goto(f"{origin}/settings", wait_until="networkidle")
        geo = page.evaluate(
            """() => {
              const marker = document.querySelector('[data-halted-settings="desktop"]');
              const deskCopy = marker && marker.querySelector('.settings-desk-copy');
              const deskBack = marker && marker.querySelector('.si-settings-desk-back');
              const toggle = marker && marker.querySelector('[data-gcal-toggle]');
              const autoPace = marker && marker.querySelector('#pace-auto');
              const selfPace = marker && marker.querySelector('#pace-self-paced');
              return {
                marker: Boolean(marker),
                plus: Boolean(document.querySelector('[data-plus-settings="desktop"]')),
                expired: Boolean(
                  document.querySelector('[data-expired-settings="desktop"]')
                ),
                deskCopyDisplay: deskCopy ? getComputedStyle(deskCopy).display : null,
                deskBackDisplay: deskBack ? getComputedStyle(deskBack).display : null,
                toggleDisplay: toggle ? getComputedStyle(
                  toggle.closest('.settings-phone-only') || toggle
                ).display : null,
                autoDisabled: Boolean(autoPace && autoPace.disabled),
                selfDisabled: Boolean(selfPace && selfPace.disabled),
                screen: document.body.getAttribute('data-mscreen'),
              };
            }"""
        )
        browser.close()
    assert geo["marker"] is True
    assert geo["plus"] is False
    assert geo["expired"] is False
    assert geo["deskCopyDisplay"] == "none"
    assert geo["deskBackDisplay"] == "none"
    assert geo["autoDisabled"] is True
    assert geo["selfDisabled"] is False
    assert geo["screen"] == "settings"


def test_halted_settings_screen11_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, entitlements=True, pricing=True)
    client = TestClient(app)
    _sign_in(client)
    _plus_then_halt(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_settings_screen11_1280.png"
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
        page.goto(f"{origin}/settings", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const halted = document.querySelector('[data-halted-settings="desktop"]');
              const plus = document.querySelector('[data-plus-settings="desktop"]');
              const expired = document.querySelector('[data-expired-settings="desktop"]');
              const heading = halted && halted.querySelector(':scope > .display');
              const ident = halted && halted.querySelector('.settings-account-row');
              const study = halted && halted.querySelector('[data-settings-group="study"]');
              const cal = halted && halted.querySelector('[data-settings-group="calendar"]');
              const save = study && study.querySelector('button[type="submit"]');
              const selfPace = study && study.querySelector('#pace-self-paced');
              const autoPace = study && study.querySelector('#pace-auto');
              const locked = study && study.querySelector('.settings-plan-locked');
              const pricing = locked && locked.querySelector('a[href="/pricing"]');
              const identStatus = ident && ident.querySelector('.settings-account-status');
              const status = document.querySelector('.account-menu-btn-status');
              const back = halted && halted.querySelector('.si-settings-desk-back a');
              const identBox = ident && ident.getBoundingClientRect();
              const studyBox = study && study.getBoundingClientRect();
              const calBox = cal && cal.getBoundingClientRect();
              const nav = document.querySelector('.PrimaryTabs--top');
              const active = nav && [...nav.querySelectorAll('.nav-link.is-active')].map(
                (el) => (el.textContent || '').replace(/\\s+/g, ' ').trim()
              );
              return {
                present: Boolean(halted),
                plus: Boolean(plus),
                expired: Boolean(expired),
                heading: heading && (heading.textContent || '').trim(),
                identHref: ident && ident.getAttribute('href'),
                name: ident && (ident.innerText || ''),
                identStatus: identStatus && (identStatus.textContent || '').trim(),
                studyBelow: Boolean(
                  identBox && studyBox && studyBox.top > identBox.bottom - 8
                ),
                calBelow: Boolean(
                  studyBox && calBox && calBox.top > studyBox.bottom - 8
                ),
                selfChecked: Boolean(selfPace && selfPace.checked),
                selfDisabled: Boolean(selfPace && selfPace.disabled),
                autoDisabled: Boolean(autoPace && autoPace.disabled),
                locked: locked && (locked.innerText || '').replace(/\\s+/g, ' ').trim(),
                pricingHref: pricing && pricing.getAttribute('href'),
                saveText: save && (save.textContent || '').replace(/\\s+/g, ' ').trim(),
                status: status && (status.textContent || '').trim(),
                statusDisplay: status ? getComputedStyle(status).display : 'none',
                backText: back && (back.textContent || '').replace(/\\s+/g, ' ').trim(),
                backHref: back && back.getAttribute('href'),
                hasDailyTarget: Boolean(study && study.querySelector('#target-5')),
                calTitle: cal && (cal.querySelector('h2') || {}).textContent,
                resume: (document.body.innerText || '').includes('Resume Playground'),
                activeNav: active || [],
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        context.close()
        browser.close()
    assert geo["present"] is True
    assert geo["plus"] is False
    assert geo["expired"] is False
    assert geo["heading"] == "Settings"
    assert geo["identHref"] == "/profile"
    assert "Sanjay" in (geo["name"] or "")
    assert geo["identStatus"] == LIVE_HEADING
    assert geo["studyBelow"] is True
    assert geo["calBelow"] is True
    assert geo["selfChecked"] is True
    assert geo["selfDisabled"] is False
    assert geo["autoDisabled"] is True
    assert LOCKED_COPY in (geo["locked"] or "")
    assert geo["pricingHref"] == "/pricing"
    assert geo["saveText"] == "Save learning plan"
    assert geo["status"] == LIVE_HEADING
    assert geo["statusDisplay"] != "none"
    assert geo["backText"] == "← Today"
    assert geo["backHref"] == "/dashboard"
    assert geo["hasDailyTarget"] is False
    assert "Revision calendar" in (geo["calTitle"] or "")
    assert geo["resume"] is False
    assert "Settings" not in (geo["activeNav"] or [])
    assert shot_path.exists() and shot_path.stat().st_size > 1000


def test_halted_settings_plus_regression_1280(tmp_path: Path) -> None:
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
    shot_path = artifact_dir / "halted_settings_screen11_plus_regression_1280.png"
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
        page.goto(f"{origin}/settings", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-settings="desktop"]');
              const halted = document.querySelector('[data-halted-settings="desktop"]');
              const expired = document.querySelector('[data-expired-settings="desktop"]');
              const study = document.querySelector('[data-settings-group="study"]');
              const selfPace = study && study.querySelector('#pace-self-paced');
              const autoPace = study && study.querySelector('#pace-auto');
              const target = study && study.querySelector('#target-5');
              const status = document.querySelector('.account-menu-btn-status');
              const save = study && study.querySelector('button[type="submit"]');
              const selfLabel = study && study.querySelector('label[for="pace-self-paced"]');
              const selfCs = selfLabel ? getComputedStyle(selfLabel) : null;
              return {
                plus: Boolean(plus),
                halted: Boolean(halted),
                expired: Boolean(expired),
                selfChecked: Boolean(selfPace && selfPace.checked),
                autoDisabled: Boolean(autoPace && autoPace.disabled),
                hasDailyTarget: Boolean(target),
                status: status && (status.textContent || '').trim(),
                statusDisplay: status ? getComputedStyle(status).display : 'none',
                saveText: save && (save.textContent || '').replace(/\\s+/g, ' ').trim(),
                selfBg: selfCs && selfCs.backgroundColor,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        context.close()
        browser.close()
    assert geo["plus"] is True
    assert geo["halted"] is False
    assert geo["expired"] is False
    assert geo["selfChecked"] is True
    assert geo["autoDisabled"] is False
    assert geo["hasDailyTarget"] is True
    assert geo["status"] == "RecallC Plus"
    assert geo["statusDisplay"] != "none"
    assert geo["saveText"] == "Save learning plan"
    assert geo["selfBg"] == "rgb(20, 20, 20)"
    assert shot_path.exists() and shot_path.stat().st_size > 1000
