"""Halted cohort desktop Add interception sheet Screen 05 (CTA map halted/05-screen).

Authorized: ChatGPT. Authenticated multiuser GET /playground/laws/ndps/add
after a real Plus subscription is halted. Existing resume kind stays; copy
comes from gate_view(BLOCK_PAYMENT_HALTED), not generic Resume Playground.
No new route, no kind=halted, no POST form. Guest, Free, Plus, Expired,
paused, pending, device_blocked, roster-full, phone, Plus 01–11, Expired
01–11, and Halted 01–04 stay unchanged. No Halted 06 work.
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
from constitution_memorizer.auth.sessions import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    InMemorySessionStore,
)
from constitution_memorizer.entitlements.models import (
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
)
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.access import PlaygroundAccess
from constitution_memorizer.playground.urls import add_path, home_path, law_path, sections_path
from constitution_memorizer.playground.view import PLAYGROUND_BILLING_PATH, gate_view, law_membership
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.guest_bareact_head import NDPS_GUEST_TITLE
from tests.conftest import PLAYGROUND_TEST_NOW

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "data" / "output" / "learning_units.json"
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
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
ROUTES = ROOT / "src/constitution_memorizer/playground/routes.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
APP = ROOT / "src/constitution_memorizer/web/app.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
PG_JS = ROOT / "src/constitution_memorizer/web/static/playground.js"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_HALTED_GATE = gate_view(reason=BLOCK_PAYMENT_HALTED)
LIVE_HEADING = LIVE_HALTED_GATE.title
LIVE_COPY = LIVE_HALTED_GATE.lines
LIVE_CTA = LIVE_HALTED_GATE.cta_label
LIVE_EXPIRED_STATUS = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
INVENTED = (
    "Your subscription expired",
    "Resume subscription",
    "Your payment failed",
    "Fix your payment",
    "Subscription halted",
    "Playground unavailable",
    "Free plan",
    "Unlock all",
    'kind == "halted"',
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


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("rtc_csrf") or ""
    return {"csrf_token": token} if token else {}


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


def _seed_ndps_then_halt(client: TestClient) -> None:
    _subscribe(client, status="active")
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps")
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None
    client.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )


def _facts(client: TestClient) -> dict:
    snap = client.app.state.entitlement_service.resolve(USER, now=PLAYGROUND_TEST_NOW)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    cap = roster.peek_capacity(USER, snap)
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    return {
        "active": tuple(sorted(i.law_id for i in roster.active_roster_items(USER))),
        "removed": tuple(sorted(i.law_id for i in roster.removed_roster_items(USER))),
        "used": cap.used,
        "remaining": cap.remaining,
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        ),
        "selection": tuple(
            sorted(s.source_locator for s in overlay.list_selection(USER, "ndps"))
        ),
        "progress": tuple(
            sorted(
                (p.source_locator, p.status, p.times_completed, p.cloze_done)
                for p in overlay.list_progress(USER, "ndps")
            )
        ),
        "subscription": None
        if stored is None
        else (stored.id, stored.status, stored.tier, stored.is_current),
        "entitlement": (
            snap.subscription_status,
            snap.playground_block_reason,
            snap.can_open_playground,
        ),
    }


def _desk(html: str) -> str:
    return html.split("data-halted-add-desktop", 1)[1].split(
        "data-halted-add-phone", 1
    )[0]


def test_halted_add_is_existing_resume_not_confirm(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_then_halt(client)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.is_authenticated is True
    assert snap.tier == "plus"
    assert snap.subscription_status == "halted"
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    assert snap.playground_block_reason == BLOCK_PAYMENT_HALTED
    assert LIVE_HEADING == "Payment retries have stopped"
    assert LIVE_CTA == "Manage subscription"
    access = PlaygroundAccess(
        user_id=USER,
        snapshot=snap,
        can_open=snap.can_open_playground,
        can_consume_new_law=snap.can_consume_new_playground_law,
        local_owner=False,
        can_view_home=True,
    )
    raw = law_membership(
        law_id="ndps",
        access=access,
        roster=client.app.state.roster,
        overlay=client.app.state.playground,
    )
    assert raw.kind == "resume"
    assert raw.primary_label == "Resume Playground"

    before = _facts(client)
    page = client.get(add_path("ndps"))
    assert page.status_code == 200
    html = unescape(page.text)
    assert 'data-pg-kind="resume"' in html
    assert 'data-halted-add="desktop"' in html
    assert "data-halted-add-desktop" in html
    assert "data-halted-add-phone" in html
    assert 'data-pg-kind="halted"' not in html
    assert 'data-pg-kind="already_active"' not in html
    assert 'data-pg-kind="eligible_to_add"' not in html
    assert 'data-plus-add="desktop"' not in html
    assert 'data-expired-add="desktop"' not in html
    assert "data-guest-add-desktop" not in html
    assert "data-signed-in-add-desktop" not in html
    assert "data-pg-add-confirm" not in html
    assert 'action="/playground/laws/ndps/add"' not in html
    assert 'name="confirm"' not in html
    assert 'name="scope"' not in html
    assert ">Entire Act<" not in html
    assert ">Choose sections<" not in html
    assert "Add to Playground" not in html
    assert "Add back" not in html
    desk = _desk(html)
    assert f">{LIVE_HEADING}<" in desk
    for line in LIVE_COPY:
        assert line in desk
    assert f">{LIVE_CTA}<" in desk
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in desk
    assert ">Resume Playground<" not in desk
    assert "Resume a plan to add" not in desk
    assert LIVE_EXPIRED_STATUS not in desk
    assert "Unlock Playground" not in desk
    assert "Sign in" not in desk
    assert "data-pg-sheet-close" in desk
    for phrase in INVENTED:
        assert phrase not in desk, phrase
    phone = html.split("data-halted-add-phone", 1)[1]
    assert f'href="/laws/ndps"' in phone
    assert LIVE_CTA in phone
    assert client.get("/laws/ndps").status_code == 200
    assert 'data-halted-bareact="desktop"' in client.get("/laws/ndps").text
    workspace = client.get(law_path("ndps"))
    assert workspace.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAYMENT_HALTED}"' in workspace.text
    assert 'data-pg-learn-panel="cloze"' not in workspace.text
    sections = client.get(sections_path("ndps"))
    assert sections.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAYMENT_HALTED}"' in sections.text
    assert "data-pg-picker" not in sections.text
    posted = client.post(
        add_path("ndps"),
        data={**_csrf(client), "confirm": "add", "scope": "entire"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    assert posted.headers.get("location") == home_path()
    again = client.get(add_path("ndps"))
    assert again.status_code == 200
    assert _facts(client) == before
    bns = client.get(add_path("bns"))
    assert bns.status_code == 200
    assert _facts(client) == before


def test_halted_elapsed_period_stays_halted_on_add(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_then_halt(client)
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
    html = unescape(client.get(add_path("ndps")).text)
    assert 'data-halted-add="desktop"' in html
    assert 'data-expired-add="desktop"' not in html
    assert 'data-plus-add="desktop"' not in html
    assert 'data-pg-kind="resume"' in html
    assert f">{LIVE_HEADING}<" in html
    assert LIVE_EXPIRED_STATUS not in html
    assert f">{LIVE_CTA}<" in html
    assert ">Resume Playground<" not in html


def test_never_added_halted_bns_gets_same_sheet(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_then_halt(client)
    html = unescape(client.get(add_path("bns")).text)
    assert 'data-pg-kind="resume"' in html
    assert 'data-halted-add="desktop"' in html
    assert 'data-pg-kind="eligible_to_add"' not in html
    assert "data-pg-add-confirm" not in html
    assert 'name="confirm"' not in html
    assert 'name="scope"' not in html
    assert f">{LIVE_HEADING}<" in html
    for line in LIVE_COPY:
        assert line in html
    assert f">{LIVE_CTA}<" in html
    assert PLAYGROUND_BILLING_PATH in html
    posted = client.post(
        add_path("bns"),
        data={**_csrf(client), "confirm": "add", "scope": "sections"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    assert posted.headers.get("location") == home_path()
    assert client.app.state.roster.is_law_active_this_period(USER, "bns") is False


def test_guest_free_plus_expired_paused_pending_are_not_halted_add(
    tmp_path: Path,
) -> None:
    guest_html = TestClient(_mu_app(tmp_path / "guest")).get(add_path("ndps")).text
    assert "data-guest-add-desktop" in guest_html
    assert 'data-halted-add="desktop"' not in guest_html
    assert LIVE_HEADING not in guest_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get(add_path("ndps")).text
    assert "data-signed-in-add-desktop" in free_html
    assert "Unlock Playground" in free_html
    assert 'data-halted-add="desktop"' not in free_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus, status="active")
    plus_html = plus.get(add_path("ndps")).text
    assert 'data-plus-add="desktop"' in plus_html
    assert "data-pg-add-confirm" in plus_html
    assert "Add to Playground" in plus_html
    assert 'data-halted-add="desktop"' not in plus_html

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(expired, status="active")
    added = _confirm_add(expired, "ndps")
    assert added.status_code in {200, 303}
    stored = expired.app.state.subscriptions.get_current_subscription(USER)
    expired.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        status="expired",
        billing_period_start=EXPIRED_START,
        billing_period_end=EXPIRED_END,
    )
    expired_html = unescape(expired.get(add_path("ndps")).text)
    assert 'data-expired-add="desktop"' in expired_html
    assert 'data-halted-add="desktop"' not in expired_html
    assert f">{LIVE_EXPIRED_STATUS}<" in expired_html
    assert ">Resume Playground<" in expired_html
    assert LIVE_HEADING not in expired_html

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused, status="paused")
    paused_html = paused.get(add_path("ndps")).text
    assert 'data-halted-add="desktop"' not in paused_html
    assert "Resume Playground" in paused_html
    assert LIVE_HEADING not in paused_html

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    pending_html = pending.get(add_path("ndps")).text
    assert 'data-halted-add="desktop"' not in pending_html
    assert "temporarily unavailable" in pending_html.lower() or 'data-pg-kind="pending"' in pending_html


def test_halted_add_uses_shared_predicate_existing_resume_route() -> None:
    add_src = ADD.read_text(encoding="utf-8")
    assert 'kind == "resume"' in add_src
    assert 'kind == "halted"' not in add_src
    assert "halted_add" in add_src
    assert 'data-halted-add="desktop"' in add_src
    assert "data-halted-add-desktop" in add_src
    assert "data-halted-add-phone" in add_src
    assert "resume_cta_label" in add_src
    assert "resume_cta_href" in add_src
    assert "state.primary_label" not in add_src.split("{% if halted_add|default(false) %}", 1)[1].split(
        "{% elif expired_add|default(false) %}", 1
    )[0]
    assert LIVE_HEADING not in add_src
    halted_branch = add_src.split("{% if halted_add|default(false) %}", 1)[1].split(
        "{% elif expired_add|default(false) %}", 1
    )[0]
    assert LIVE_CTA not in halted_branch
    assert "Payment retries have stopped" not in halted_branch
    assert 'method="post"' not in halted_branch
    assert "data-pg-add-confirm" not in halted_branch
    assert 'name="scope"' not in halted_branch
    assert "data-pg-sheet-close" in halted_branch
    resume_branch = add_src.split('{% elif kind == "resume" %}', 1)[1].split(
        '{% elif kind == "device_blocked" %}', 1
    )[0]
    assert 'method="post"' not in resume_branch
    routes = ROUTES.read_text(encoding="utf-8")
    ctx = routes.split("def _add_page_context", 1)[1].split("def _rollover_ids", 1)[0]
    assert "request_is_halted_subscriber" in ctx
    assert "request_is_expired_subscriber" in ctx
    assert "BLOCK_PAYMENT_HALTED" in ctx
    assert "gate_view" in ctx
    assert "halted_add" in ctx
    assert "resume_cta_label" in ctx
    assert 'kind = "resume"' in ctx
    assert "def law_membership" not in ctx
    assert 'kind == "halted"' not in ctx
    assert "def request_is_halted_subscriber" in DEPS.read_text(encoding="utf-8")
    view = VIEW.read_text(encoding="utf-8")
    assert 'KIND_RESUME = "resume"' in view
    assert 'kind == "halted"' not in view
    js = PG_JS.read_text(encoding="utf-8")
    assert "function enhanceSheets" in js
    assert "[data-pg-sheet]" in js
    css = PG_CSS.read_text(encoding="utf-8")
    assert "[data-halted-add-desktop]" in css
    assert "[data-expired-add-desktop]" in css
    assert "playground.css?v=pg28" in BASE.read_text(encoding="utf-8")
    assert "data-halted-add" not in MOBILE.read_text(encoding="utf-8")


def test_plus_expired_and_halted_01_04_untouched() -> None:
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-halted-landing="desktop"' in landing
    assert "data-halted-add" not in landing
    browse = BROWSE.read_text(encoding="utf-8")
    assert 'data-halted-browse="desktop"' in browse
    assert "data-halted-add" not in browse
    laws = LAWS.read_text(encoding="utf-8")
    assert 'data-halted-laws="desktop"' in laws
    assert "data-halted-add" not in laws
    bare = BARE.read_text(encoding="utf-8")
    assert 'data-halted-bareact="desktop"' in bare
    assert "data-halted-add" not in bare
    assert 'data-plus-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-expired-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-plus-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-expired-playground="desktop"' in HOME.read_text(encoding="utf-8")
    for path in (LANDING, BROWSE, LAWS, BARE, HOME, GATE, MANAGE, DASH, CAL, PROFILE, SETTINGS):
        text = path.read_text(encoding="utf-8")
        assert "data-halted-add" not in text
        assert "halted_add" not in text


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


def test_halted_phone_add_uses_resume_not_confirm(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_then_halt(client)
    html = unescape(client.get(add_path("ndps")).text)
    phone = html.split("data-halted-add-phone", 1)[1]
    assert LIVE_HEADING in phone
    assert LIVE_CTA in phone
    assert PLAYGROUND_BILLING_PATH in phone
    assert 'href="/laws/ndps"' in phone
    assert "data-pg-add-confirm" not in phone
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
        page.goto(f"{origin}{add_path('ndps')}", wait_until="networkidle")
        geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const desk = panel && panel.querySelector('[data-halted-add-desktop]');
              const phoneBlock = panel && panel.querySelector('[data-halted-add-phone]');
              const cancel = phoneBlock && phoneBlock.querySelector('.pg-btn--ghost');
              return {
                kind: panel && panel.getAttribute('data-pg-kind'),
                halted: panel && panel.getAttribute('data-halted-add'),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                phoneDisplay: phoneBlock ? getComputedStyle(phoneBlock).display : null,
                title: phoneBlock && phoneBlock.querySelector('h1') &&
                  phoneBlock.querySelector('h1').textContent.trim(),
                cancelHref: cancel && cancel.getAttribute('href'),
              };
            }"""
        )
        browser.close()
    assert geo["kind"] == "resume"
    assert geo["halted"] == "desktop"
    assert geo["deskDisplay"] == "none"
    assert geo["phoneDisplay"] != "none"
    assert geo["title"] == LIVE_HEADING
    assert geo["cancelHref"] == "/laws/ndps"


def test_halted_add_screen05_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_then_halt(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_add_screen05_1280.png"
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
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        page.evaluate(
            """() => {
              const a = document.createElement('a');
              a.href = '/playground/laws/ndps/add';
              a.setAttribute('data-pg-sheet', '');
              a.style.display = 'none';
              document.body.appendChild(a);
              a.click();
            }"""
        )
        page.wait_for_selector("[data-halted-add-desktop]", timeout=8000)
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const desk = panel && panel.querySelector('[data-halted-add-desktop]');
              const phoneBlock = panel && panel.querySelector('[data-halted-add-phone]');
              const resume = desk && desk.querySelector('.halted-add-resume');
              const cancel = desk && desk.querySelector('.halted-add-cancel');
              const closeBtn = panel && panel.querySelector('[data-pg-sheet-close].pg-sheet-close');
              const haltedBare = document.querySelector('[data-halted-bareact="desktop"]');
              const cluster = document.querySelector('.signed-bareact-in-pg');
              const titleEl = desk && desk.querySelector('.halted-add-title');
              const ledeEl = desk && desk.querySelector('.halted-add-lede');
              const confirmForm = panel && panel.querySelector('[data-pg-add-confirm]');
              const scope = panel && panel.querySelector("[data-add-step='scope']");
              return {
                open: Boolean(dialog && dialog.open),
                kind: panel && panel.getAttribute('data-pg-kind'),
                haltedAdd: panel && panel.getAttribute('data-halted-add'),
                plus: panel && panel.getAttribute('data-plus-add'),
                expired: panel && panel.getAttribute('data-expired-add'),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                phoneDisplay: phoneBlock ? getComputedStyle(phoneBlock).display : null,
                eyebrowDisplay: panel && panel.querySelector('.pg-eyebrow')
                  ? getComputedStyle(panel.querySelector('.pg-eyebrow')).display
                  : null,
                title: titleEl && titleEl.textContent.trim(),
                lede: ledeEl && ledeEl.textContent.trim(),
                resumeText: resume && resume.textContent.trim(),
                resumeHref: resume && resume.getAttribute('href'),
                cancelDisplay: cancel ? getComputedStyle(cancel).display : null,
                hasClose: Boolean(closeBtn),
                closeLabel: closeBtn && closeBtn.getAttribute('aria-label'),
                background: Boolean(haltedBare),
                already: Boolean(cluster && cluster.innerText.includes('Already in Playground')),
                header: document.querySelector('.account-menu-btn-status') &&
                  document.querySelector('.account-menu-btn-status').textContent.trim(),
                actTitle: haltedBare && haltedBare.querySelector('.guest-bareact-title') &&
                  haltedBare.querySelector('.guest-bareact-title').textContent.trim(),
                confirmForm: Boolean(confirmForm),
                scope: Boolean(scope),
                path: location.pathname,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator(".pg-sheet-close").click()
        closed = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              return {
                open: Boolean(dialog && dialog.open),
                path: location.pathname,
                head: Boolean(document.querySelector('[data-halted-bareact="desktop"]')),
              };
            }"""
        )
        browser.close()

    assert geo["open"] is True
    assert geo["kind"] == "resume"
    assert geo["haltedAdd"] == "desktop"
    assert geo["plus"] in (None, "")
    assert geo["expired"] in (None, "")
    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["eyebrowDisplay"] == "none"
    assert geo["title"] == LIVE_HEADING
    assert geo["lede"] == LIVE_COPY[0]
    assert geo["resumeText"] == LIVE_CTA
    assert geo["resumeText"] != "Continue"
    assert geo["resumeText"] != "Add to Playground"
    assert geo["resumeHref"] == PLAYGROUND_BILLING_PATH
    assert geo["cancelDisplay"] == "none"
    assert geo["hasClose"] is True
    assert geo["closeLabel"] == "Close"
    assert geo["background"] is True
    assert geo["already"] is True
    assert geo["header"] == LIVE_HEADING
    assert geo["actTitle"] == NDPS_GUEST_TITLE
    assert geo["confirmForm"] is False
    assert geo["scope"] is False
    assert geo["path"] == "/laws/ndps"
    assert closed["open"] is False
    assert closed["path"] == "/laws/ndps"
    assert closed["head"] is True
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_halted_add_plus_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client, status="active")
    session = client.cookies.get(SESSION_COOKIE_NAME)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_add_screen05_plus_regression_1280.png"
    origin = f"http://127.0.0.1:{port}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
        cookies = [
            {
                "name": SESSION_COOKIE_NAME,
                "value": session,
                "url": origin,
                "httpOnly": True,
                "secure": False,
                "sameSite": "Lax",
            }
        ]
        if csrf:
            cookies.append(
                {
                    "name": CSRF_COOKIE_NAME,
                    "value": csrf,
                    "url": origin,
                    "httpOnly": False,
                    "secure": False,
                    "sameSite": "Lax",
                }
            )
        context.add_cookies(cookies)
        page = context.new_page()
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        page.locator('[data-plus-bareact="desktop"] [data-pg-sheet]').click()
        page.wait_for_selector("[data-plus-add-desktop]", timeout=8000)
        geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const desk = panel && panel.querySelector('[data-plus-add-desktop]');
              const halted = panel && panel.querySelector('[data-halted-add-desktop]');
              const title = desk && desk.querySelector('.plus-add-title');
              const submit = desk && desk.querySelector('.plus-add-submit');
              return {
                kind: panel && panel.getAttribute('data-pg-kind'),
                plus: panel && panel.getAttribute('data-plus-add'),
                haltedAttr: panel && panel.getAttribute('data-halted-add'),
                haltedPresent: Boolean(halted),
                title: title && title.textContent.trim(),
                submit: submit && submit.textContent.trim(),
                confirm: Boolean(panel && panel.querySelector('[data-pg-add-confirm]')),
                header: document.querySelector('.account-menu-btn-status') &&
                  document.querySelector('.account-menu-btn-status').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["kind"] == "eligible_to_add"
    assert geo["plus"] == "desktop"
    assert geo["haltedAttr"] in (None, "")
    assert geo["haltedPresent"] is False
    assert geo["title"] == "Add to Playground"
    assert geo["submit"] == "Add to Playground"
    assert geo["confirm"] is True
    assert geo["header"] == "RecallC Plus"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
