"""Halted cohort desktop Playground-home Screen 06 (CTA map halted/06-screen).

Authorized: ChatGPT. Authenticated multiuser GET /playground after a real
Plus subscription is halted. Presentation of the existing read-only home
(require_playground_home, build_home_view, read_only=True). Hero/actions
from gate_view(BLOCK_PAYMENT_HALTED) even when the paid period elapsed.
Saved-progress tiles from live home counts. Guest, Free, Plus, Expired,
paused, pending, Pro/Max, phone, Plus 01–11, Expired 01–11, and Halted
01–05 stay unchanged. No new route. No roster mutation. No Halted 07.
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
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.entitlements.models import (
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
)
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.access import PlaygroundAccess
from constitution_memorizer.playground.roster.period import (
    playground_month_bounds,
    playground_month_name,
    playground_today,
)
from constitution_memorizer.playground.urls import add_path, home_path, law_path, sections_path
from constitution_memorizer.playground.view import (
    CONSTITUTION_HOME_PATH,
    PLAYGROUND_BILLING_PATH,
    build_home_view,
    gate_view,
)
from constitution_memorizer.web.app import create_app
from tests.conftest import PLAYGROUND_TEST_NOW
from tests.test_playground_m8 import _seed_progress

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
ROUTES = ROOT / "src/constitution_memorizer/playground/routes.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
APP = ROOT / "src/constitution_memorizer/web/app.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_GATE = gate_view(reason=BLOCK_PAYMENT_HALTED)
LIVE_HEADING = LIVE_GATE.title
LIVE_COPY = LIVE_GATE.lines
LIVE_CTA = LIVE_GATE.cta_label
LIVE_EXPIRED_STATUS = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
LOCATOR = "ndps:section:8:clause:a"
MONTH = playground_month_name(playground_month_bounds(PLAYGROUND_TEST_NOW)[0])
INVENTED = (
    "Your subscription expired",
    "Resume subscription",
    "Your payment failed",
    "Fix your payment",
    "Subscription halted",
    "Playground unavailable",
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


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("rtc_csrf") or ""
    return {"csrf_token": token} if token else {}


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


def _seed_ndps_progress_then_halt(client: TestClient) -> None:
    _subscribe(client)
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    selected = client.post(
        sections_path("ndps"),
        data={**_csrf(client), "unit": LOCATOR, "section": "8"},
        follow_redirects=False,
    )
    assert selected.status_code in {200, 303}
    overlay = client.app.state.playground
    locators = [s.source_locator for s in overlay.list_selection(USER, "ndps")]
    assert locators, "section selection did not persist"
    seed_locator = LOCATOR if LOCATOR in locators else locators[0]
    day = playground_today()
    _seed_progress(
        client.app.state.playground,
        USER,
        "ndps",
        seed_locator,
        status="review",
        interval_days=1,
        next_revision=day.isoformat(),
        times_completed=1,
        learned_at=day.isoformat(),
    )
    _halt(client)


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
        "subscription": None
        if stored is None
        else (stored.id, stored.status, stored.tier, stored.is_current),
        "entitlement": (
            snap.subscription_status,
            snap.playground_block_reason,
            snap.can_open_playground,
        ),
    }


def _home_view(client: TestClient):
    snap = client.app.state.entitlement_service.resolve(USER)
    access = PlaygroundAccess(
        user_id=USER,
        snapshot=snap,
        can_open=snap.can_open_playground,
        can_consume_new_law=snap.can_consume_new_playground_law,
        local_owner=False,
        can_view_home=True,
    )
    return build_home_view(
        access=access,
        roster=client.app.state.roster,
        overlay=client.app.state.playground,
    )


def _desk(html: str) -> str:
    return html.split("data-halted-pg-desktop", 1)[1].split(
        "data-halted-pg-phone", 1
    )[0]


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _halted_client(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_progress_then_halt(client)
    return client


def test_halted_home_is_readonly_gate_view_not_hard_gate(tmp_path: Path) -> None:
    client = _halted_client(tmp_path)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.subscription_status == "halted"
    assert snap.playground_block_reason == BLOCK_PAYMENT_HALTED
    assert snap.can_open_playground is False
    home = _home_view(client)
    assert home.read_only is True
    assert home.due_today >= 1
    assert home.sections_learned > 0
    page = client.get("/playground")
    assert page.status_code == 200
    html = unescape(page.text)
    assert 'data-halted-playground="desktop"' in html
    assert 'data-expired-playground="desktop"' not in html
    assert 'data-plus-playground="desktop"' not in html
    assert "data-signed-in-pg-gate" not in html
    assert "data-guest-pg-intro" not in html
    assert 'data-hard-gate="true"' not in html
    assert "is-readonly" in html
    header = _header(html)
    desk = _desk(html)
    assert LIVE_HEADING in header
    assert "RecallC Plus" not in header
    assert "Free account" not in header
    assert 'href="/playground"' in header
    assert "is-active" in header.split('href="/playground"', 1)[1].split("</a>", 1)[0]
    assert f">{LIVE_HEADING}<" in desk
    for line in LIVE_COPY:
        assert line in desk
    assert f">{LIVE_CTA}<" in desk
    assert f'href="{LIVE_GATE.cta_href}"' in desk
    assert LIVE_GATE.cta_href == PLAYGROUND_BILLING_PATH
    assert LIVE_CTA == "Manage subscription"
    assert f">{LIVE_GATE.secondary_label}<" in desk
    assert f'href="{LIVE_GATE.secondary_href}"' in desk
    assert LIVE_GATE.secondary_href == CONSTITUTION_HOME_PATH
    assert CONSTITUTION_HOME_PATH == "/dashboard"
    assert ">Resume Playground<" not in desk
    assert LIVE_EXPIRED_STATUS not in desk
    assert f">{home.due_today}<" in desk
    assert f">{home.overdue}<" in desk
    assert f">{home.sections_learned}<" in desk
    assert "Due today" in desk
    assert "Overdue" in desk
    assert "Sections learned" in desk
    assert ">Browse laws<" not in desk
    assert "Manage " + MONTH not in desk
    assert "Plan next month" not in desk
    assert "Add a law" not in desk
    assert "In Playground this month" not in desk
    assert "LawCard" not in desk
    assert "RosterCapacity" not in desk
    assert "Start learning" not in desk
    assert ">Continue<" not in desk
    assert "Verbatim" not in desk
    assert 'method="post"' not in desk.lower()
    for phrase in INVENTED:
        assert phrase not in desk, phrase
    workspace = client.get(law_path("ndps"))
    assert workspace.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAYMENT_HALTED}"' in workspace.text
    assert 'data-pg-learn-panel="cloze"' not in workspace.text
    sections = client.get(sections_path("ndps"))
    assert sections.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAYMENT_HALTED}"' in sections.text
    assert "data-pg-picker" not in sections.text


def test_halted_elapsed_period_stays_halted_on_home(tmp_path: Path) -> None:
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
    html = unescape(client.get("/playground").text)
    assert 'data-halted-playground="desktop"' in html
    assert 'data-expired-playground="desktop"' not in html
    assert 'data-plus-playground="desktop"' not in html
    desk = _desk(html)
    assert f">{LIVE_HEADING}<" in desk
    assert LIVE_EXPIRED_STATUS not in desk
    assert f">{LIVE_CTA}<" in desk
    assert ">Resume Playground<" not in desk
    assert LIVE_HEADING in _header(html)


def test_halted_home_mutation_safety(tmp_path: Path) -> None:
    client = _halted_client(tmp_path)
    before = _facts(client)
    assert "ndps" in before["active"]
    assert before["selection"]
    page = client.get("/playground")
    assert page.status_code == 200
    after = _facts(client)
    assert after == before
    again = client.get(home_path())
    assert again.status_code == 200
    slash = client.get("/playground/")
    assert slash.status_code == 200
    assert _facts(client) == before
    assert 'data-halted-playground="desktop"' in unescape(again.text)
    assert 'data-halted-playground="desktop"' in unescape(slash.text)


def test_guest_free_plus_expired_paused_pending_pro_max_are_not_halted_home(
    tmp_path: Path,
) -> None:
    guest_html = TestClient(_mu_app(tmp_path / "guest")).get("/playground").text
    assert "data-guest-pg-intro" in guest_html
    assert 'data-halted-playground="desktop"' not in guest_html
    assert LIVE_HEADING not in guest_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/playground").text
    assert "data-signed-in-pg-gate" in free_html
    assert 'data-halted-playground="desktop"' not in free_html
    assert LIVE_HEADING not in free_html
    assert "Free account" in _header(free_html) or "Unlock Playground" in free_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = unescape(plus.get("/playground").text)
    assert 'data-plus-playground="desktop"' in plus_html
    assert 'data-halted-playground="desktop"' not in plus_html
    assert "RecallC Plus" in _header(plus_html)
    assert LIVE_HEADING not in plus_html
    assert f">{MONTH}<" in plus_html or MONTH in plus_html
    assert "Browse laws" in plus_html

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(expired)
    _confirm_add(expired, "ndps")
    stored = expired.app.state.subscriptions.get_current_subscription(USER)
    expired.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        status="expired",
        billing_period_start=EXPIRED_START,
        billing_period_end=EXPIRED_END,
    )
    expired_html = unescape(expired.get("/playground").text)
    assert 'data-expired-playground="desktop"' in expired_html
    assert 'data-halted-playground="desktop"' not in expired_html
    assert f">{LIVE_EXPIRED_STATUS}<" in expired_html
    assert LIVE_HEADING not in expired_html
    assert ">View Playground plans<" in expired_html

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused, status="paused")
    paused_html = paused.get("/playground").text
    assert 'data-halted-playground="desktop"' not in paused_html
    assert LIVE_HEADING not in paused_html
    assert "Playground subscription paused" in paused_html or "Resume Playground" in paused_html

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    pending_html = pending.get("/playground").text
    assert 'data-halted-playground="desktop"' not in pending_html
    assert LIVE_HEADING not in pending_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/playground").text
    assert 'data-halted-playground="desktop"' not in pro_html
    assert LIVE_HEADING not in _header(pro_html)

    mx = TestClient(_mu_app(tmp_path / "max"))
    _sign_in(mx)
    _subscribe(mx, tier="max")
    mx_html = mx.get("/playground").text
    assert 'data-halted-playground="desktop"' not in mx_html
    assert LIVE_HEADING not in _header(mx_html)


def test_halted_playground_uses_shared_predicate_and_gate_view() -> None:
    home = HOME.read_text(encoding="utf-8")
    assert "halted_playground" in home
    assert 'data-halted-playground="desktop"' in home
    assert "data-halted-pg-desktop" in home
    assert "data-halted-pg-phone" in home
    assert "halted_gate.title" in home
    assert "halted_gate.cta_href" in home
    assert "halted_gate.secondary_href" in home
    assert "home.due_today" in home
    assert "home.overdue" in home
    assert "home.sections_learned" in home
    assert 'data-plus-playground="desktop"' in home
    assert 'data-expired-playground="desktop"' in home
    assert LIVE_HEADING not in home
    assert "Playground learning is paused" not in home
    assert "Manage subscription" not in home
    assert "Back to Constitution" not in home
    assert ">4<" not in home.split("data-halted-pg-desktop", 1)[-1][:500]
    halted_branch = home.split("{% if halted_pg and halted_gate %}", 1)[1].split(
        "{% elif expired_pg and expired_gate %}", 1
    )[0]
    assert "expired_gate.title" not in halted_branch
    assert "Payment retries have stopped" not in halted_branch
    routes = ROUTES.read_text(encoding="utf-8")
    home_fn = routes.split("async def playground_home", 1)[1].split(
        "async def playground_roster", 1
    )[0]
    assert "request_is_halted_subscriber" in home_fn
    assert "request_is_expired_subscriber" in home_fn
    assert "request_is_active_plus" in home_fn
    assert '"plus_playground": request_is_active_plus(request)' in home_fn
    assert '"halted_playground": halted_playground' in home_fn
    assert "BLOCK_PAYMENT_HALTED" in home_fn
    assert "gate_view" in home_fn
    assert "halted_gate" in home_fn
    assert "halted_header_status" in home_fn
    assert "require_playground_home" in home_fn
    assert "build_home_view" in home_fn
    assert "hard_gate\": False" in home_fn or '"hard_gate": False' in home_fn
    assert "@router.get(\"/halted" not in routes
    assert "prefix=\"/halted\"" not in routes
    deps = DEPS.read_text(encoding="utf-8")
    assert "def request_is_halted_subscriber" in deps
    view = VIEW.read_text(encoding="utf-8")
    assert 'title="Payment retries have stopped"' in view
    assert 'cta_label="Manage subscription"' in view
    assert 'secondary_label="Back to Constitution"' in view
    assert 'kind="halted"' in view
    base = BASE.read_text(encoding="utf-8")
    assert "halted_playground" in base
    assert "halted_header_status" in base
    css = PG_CSS.read_text(encoding="utf-8")
    assert "[data-halted-pg-desktop]" in css
    assert "[data-halted-pg-phone]" in css
    assert '[data-halted-playground="desktop"]' in css
    assert '[data-expired-playground="desktop"]' in css
    assert ".halted-pg-desk" not in css
    assert ".halted-pg-title" not in css
    styles = STYLES.read_text(encoding="utf-8")
    assert ":has([data-halted-playground])" in styles
    assert ":has([data-expired-playground])" in styles
    assert "playground.css?v=pg28" in base
    assert "data-halted-playground" not in MOBILE.read_text(encoding="utf-8")
    assert "data-halted-playground" not in GATE.read_text(encoding="utf-8")


def test_plus_expired_and_halted_01_05_untouched() -> None:
    assert 'data-halted-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-halted-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-halted-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-halted-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-halted-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-plus-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-expired-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-plus-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-plus-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-plus-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    for path in (LANDING, BROWSE, LAWS, BARE, ADD, GATE, MANAGE, DASH, CAL, PROFILE, SETTINGS):
        text = path.read_text(encoding="utf-8")
        assert "data-halted-playground" not in text
        assert "halted_playground" not in text
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


def test_halted_phone_playground_keeps_readonly_home(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_progress_then_halt(client)
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
        page.goto(f"{origin}/playground", wait_until="networkidle")
        geo = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-halted-pg-desktop]');
              const phone = document.querySelector('[data-halted-pg-phone]');
              const grid = document.querySelector('[data-halted-playground="desktop"]');
              return {
                marker: Boolean(grid),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                plus: Boolean(document.querySelector('[data-plus-playground="desktop"]')),
                expired: Boolean(document.querySelector('[data-expired-playground="desktop"]')),
              };
            }"""
        )
        browser.close()
    assert geo["marker"] is True
    assert geo["deskDisplay"] == "none"
    assert geo["phoneDisplay"] != "none"
    assert geo["plus"] is False
    assert geo["expired"] is False


def test_halted_playground_screen06_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_progress_then_halt(client)
    home = _home_view(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_playground_screen06_1280.png"
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
        page.goto(f"{origin}/playground", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-halted-pg-desktop]');
              const phone = document.querySelector('[data-halted-pg-phone]');
              const grid = document.querySelector('[data-halted-playground="desktop"]');
              const plus = document.querySelector('[data-plus-playground="desktop"]');
              const expired = document.querySelector('[data-expired-playground="desktop"]');
              const title = desk && desk.querySelector('.expired-pg-title');
              const lede = desk && desk.querySelector('.expired-pg-lede');
              const primary = desk && desk.querySelector('.expired-pg-primary');
              const secondary = desk && desk.querySelector('.expired-pg-secondary');
              const tiles = desk ? [...desk.querySelectorAll('.ProgressSummary-cell')] : [];
              const pgNav = [...document.querySelectorAll('.site-header .nav-link')].find(
                (a) => a.getAttribute('href') === '/playground'
              );
              const lawGrid = document.querySelector('.pg-law-grid');
              const aside = document.querySelector('.pg-aside');
              return {
                marker: Boolean(grid),
                plus: Boolean(plus),
                expired: Boolean(expired),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                title: title && title.textContent.trim(),
                lede: lede && lede.textContent.trim(),
                primaryText: primary && primary.textContent.trim(),
                primaryHref: primary && primary.getAttribute('href'),
                secondaryText: secondary && secondary.textContent.trim(),
                secondaryHref: secondary && secondary.getAttribute('href'),
                tileValues: tiles.map((el) => el.querySelector('.ProgressSummary-value').textContent.trim()),
                tileLabels: tiles.map((el) => el.querySelector('.ProgressSummary-label').textContent.trim()),
                header: document.querySelector('.account-menu-btn-status') &&
                  document.querySelector('.account-menu-btn-status').textContent.trim(),
                navActive: pgNav && pgNav.classList.contains('is-active'),
                lawGridVisible: Boolean(lawGrid && lawGrid.getBoundingClientRect().height > 1),
                asideVisible: Boolean(aside && aside.getBoundingClientRect().height > 1),
                browse: desk && /Browse laws/.test(desk.innerText),
                planNext: desk && /Plan next month/.test(desk.innerText),
                quota: desk && /of 10/.test(desk.innerText),
                resume: desk && /Resume Playground/.test(desk.innerText),
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
    assert geo["phoneDisplay"] == "none"
    assert geo["title"] == LIVE_HEADING
    assert geo["lede"] == LIVE_COPY[0]
    assert geo["primaryText"] == "Manage subscription"
    assert geo["primaryHref"] == PLAYGROUND_BILLING_PATH
    assert geo["secondaryText"] == "Back to Constitution"
    assert geo["secondaryHref"] == CONSTITUTION_HOME_PATH
    assert geo["tileLabels"] == ["Due today", "Overdue", "Sections learned"]
    assert geo["tileValues"] == [
        str(home.due_today),
        str(home.overdue),
        str(home.sections_learned),
    ]
    assert int(geo["tileValues"][0]) >= 1
    assert int(geo["tileValues"][2]) > 0
    assert geo["header"] == LIVE_HEADING
    assert geo["navActive"] is True
    assert geo["lawGridVisible"] is False
    assert geo["asideVisible"] is False
    assert geo["browse"] is False
    assert geo["planNext"] is False
    assert geo["quota"] is False
    assert geo["resume"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_halted_playground_plus_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    roster = client.app.state.roster
    start, end = playground_month_bounds()
    roster._repo.ensure_period(
        USER,
        period_start=start,
        period_end=end,
        tier_snapshot="plus",
        law_limit=10,
    )
    for law_id in ("ndps", "bns", "bnss", "mtp"):
        result = roster._repo.consume_law(
            USER,
            period_start=start,
            law_id=law_id,
            law_limit=10,
            allow_new=True,
        )
        assert result.ok, result.status
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_playground_screen06_plus_regression_1280.png"
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
        page.goto(f"{origin}/playground", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-playground="desktop"]');
              const halted = document.querySelector('[data-halted-playground="desktop"]');
              const expired = document.querySelector('[data-expired-playground="desktop"]');
              const month = document.querySelector('h1.plus-pg-month');
              const aside = document.querySelector('.pg-aside');
              return {
                plus: Boolean(plus),
                halted: Boolean(halted),
                expired: Boolean(expired),
                month: month && month.textContent.trim(),
                asideDisplay: aside ? getComputedStyle(aside).display : null,
                browse: plus && /Browse laws/.test(plus.innerText),
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
    assert geo["month"] == MONTH
    assert geo["asideDisplay"] != "none"
    assert geo["browse"] is True
    assert geo["header"] == "RecallC Plus"
    assert geo["haltedCopy"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
