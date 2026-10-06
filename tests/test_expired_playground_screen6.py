"""Expired cohort desktop Playground-home Screen 06 (CTA map expired/06-screen).

Authorized: ChatGPT. Authenticated multiuser GET /playground after a real
Plus subscription, real NDPS add/selection/progress, and paid period end.
Presentation of the existing read-only home (require_playground_home,
build_home_view, read_only=True). Hero/actions from gate_view
(BLOCK_PAID_PERIOD_ENDED). Saved-progress tiles from live home counts.
Guest, Free, Plus, halted, paused, phone, Plus 01–11, and Expired 01–05
stay unchanged. No new route. No roster mutation.
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
from constitution_memorizer.entitlements.models import BLOCK_PAID_PERIOD_ENDED
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
from constitution_memorizer.playground.urls import add_path, home_path, sections_path
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
LIVE_GATE = gate_view(reason=BLOCK_PAID_PERIOD_ENDED)
LIVE_HEADING = LIVE_GATE.title
LIVE_COPY = LIVE_GATE.lines
LOCATOR = "ndps:section:8:clause:a"
MONTH = playground_month_name(playground_month_bounds(PLAYGROUND_TEST_NOW)[0])
INVENTED = (
    "Your plan expired",
    "Resume subscription",
    "Premium",
    "Unlimited",
    "Unlock all",
    "Free plan",
    "All 3 slots",
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


def _seed_ndps_progress_then_expire(client: TestClient) -> None:
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
    _expire(client)


def _facts(client: TestClient) -> dict:
    snap = client.app.state.entitlement_service.resolve(USER, now=PLAYGROUND_TEST_NOW)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    cap = roster.peek_capacity(USER, snap)
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
    return html.split("data-expired-pg-desktop", 1)[1].split(
        "data-expired-pg-phone", 1
    )[0]


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _expired_client(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_progress_then_expire(client)
    return client


def test_expired_home_is_readonly_gate_view_not_hard_gate(tmp_path: Path) -> None:
    client = _expired_client(tmp_path)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert snap.can_open_playground is False
    home = _home_view(client)
    assert home.read_only is True
    assert home.due_today >= 1
    assert home.sections_learned > 0
    page = client.get("/playground")
    assert page.status_code == 200
    html = unescape(page.text)
    assert 'data-expired-playground="desktop"' in html
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
    assert f">{LIVE_GATE.cta_label}<" in desk
    assert f'href="{LIVE_GATE.cta_href}"' in desk
    assert LIVE_GATE.cta_href == PLAYGROUND_BILLING_PATH
    assert LIVE_GATE.cta_label == "View Playground plans"
    assert f">{LIVE_GATE.secondary_label}<" in desk
    assert f'href="{LIVE_GATE.secondary_href}"' in desk
    assert LIVE_GATE.secondary_href == CONSTITUTION_HOME_PATH
    assert CONSTITUTION_HOME_PATH == "/dashboard"
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
    assert "method=\"post\"" not in desk.lower()
    for phrase in INVENTED:
        assert phrase not in desk, phrase


def test_expired_home_mutation_safety(tmp_path: Path) -> None:
    client = _expired_client(tmp_path)
    before = _facts(client)
    assert "ndps" in before["active"]
    assert before["selection"]
    page = client.get("/playground")
    assert page.status_code == 200
    after = _facts(client)
    assert after == before
    again = client.get(home_path())
    assert again.status_code == 200
    assert _facts(client) == before


def test_guest_free_plus_halted_paused_stay_separate(tmp_path: Path) -> None:
    guest_html = TestClient(_mu_app(tmp_path / "guest")).get("/playground").text
    assert "data-guest-pg-intro" in guest_html
    assert 'data-expired-playground="desktop"' not in guest_html
    assert LIVE_HEADING not in guest_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/playground").text
    assert "data-signed-in-pg-gate" in free_html
    assert 'data-expired-playground="desktop"' not in free_html
    assert LIVE_HEADING not in free_html
    assert "Free account" in _header(free_html) or "Unlock Playground" in free_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = unescape(plus.get("/playground").text)
    assert 'data-plus-playground="desktop"' in plus_html
    assert 'data-expired-playground="desktop"' not in plus_html
    assert "RecallC Plus" in _header(plus_html)
    assert LIVE_HEADING not in plus_html
    assert f">{MONTH}<" in plus_html or MONTH in plus_html
    assert "Browse laws" in plus_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    _confirm_add(halted, "ndps")
    stored = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )
    halted_html = halted.get("/playground").text
    assert 'data-expired-playground="desktop"' not in halted_html
    assert LIVE_HEADING not in halted_html
    assert "Payment retries have stopped" in halted_html
    assert "Resume Playground" in halted_html
    halted_snap = halted.app.state.entitlement_service.resolve(USER)
    assert halted_snap.playground_block_reason != BLOCK_PAID_PERIOD_ENDED

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused)
    stored_p = paused.app.state.subscriptions.get_current_subscription(USER)
    paused.app.state.subscriptions.update_subscription_state(
        USER, stored_p.id, status="paused"
    )
    paused_html = paused.get("/playground").text
    assert 'data-expired-playground="desktop"' not in paused_html
    assert LIVE_HEADING not in paused_html
    assert "Playground subscription paused" in paused_html or "Resume Playground" in paused_html


def test_expired_playground_uses_shared_predicate_and_gate_view() -> None:
    home = HOME.read_text(encoding="utf-8")
    assert "expired_playground" in home
    assert 'data-expired-playground="desktop"' in home
    assert "data-expired-pg-desktop" in home
    assert "expired_gate.title" in home
    assert "expired_gate.cta_href" in home
    assert "expired_gate.secondary_href" in home
    assert "home.due_today" in home
    assert "home.overdue" in home
    assert "home.sections_learned" in home
    assert 'data-plus-playground="desktop"' in home
    assert "Your Playground is paused" not in home
    assert ">4<" not in home.split("expired-pg-tiles", 1)[-1][:400]
    routes = ROUTES.read_text(encoding="utf-8")
    home_fn = routes.split("async def playground_home", 1)[1].split(
        "async def playground_roster", 1
    )[0]
    assert "request_is_expired_subscriber" in home_fn
    assert "request_is_active_plus" in home_fn
    assert '"plus_playground": request_is_active_plus(request)' in home_fn
    assert "gate_view" in home_fn
    assert "expired_gate" in home_fn
    assert "require_playground_home" in home_fn
    assert "build_home_view" in home_fn
    assert "hard_gate\": False" in home_fn or '"hard_gate": False' in home_fn
    deps = DEPS.read_text(encoding="utf-8")
    assert "def request_is_expired_subscriber" in deps
    view = VIEW.read_text(encoding="utf-8")
    assert 'title="Your Playground is paused"' in view
    assert 'cta_label="View Playground plans"' in view
    assert 'secondary_label="Back to Constitution"' in view
    assert 'cta_label="Resume Playground"' in view
    assert 'kind="halted"' in view
    assert 'kind="expired"' in view
    assert 'kind="paused"' in view
    base = BASE.read_text(encoding="utf-8")
    assert "expired_playground" in base
    assert "expired_header_status" in base
    css = PG_CSS.read_text(encoding="utf-8")
    assert "[data-expired-pg-desktop]" in css
    assert "[data-expired-playground=\"desktop\"]" in css
    assert 'data-plus-playground="desktop"' in css
    styles = STYLES.read_text(encoding="utf-8")
    assert ":has([data-expired-playground])" in styles
    assert ":has([data-plus-playground])" in styles


def test_plus_screens_and_expired_01_05_untouched() -> None:
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
    assert 'data-plus-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-plus-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-plus-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    for path in (LANDING, BROWSE, LAWS, BARE, ADD, MANAGE, DASH, CAL, PROFILE, SETTINGS):
        text = path.read_text(encoding="utf-8")
        assert "data-expired-playground" not in text
    assert "data-expired-playground" not in GATE.read_text(encoding="utf-8")
    assert "data-expired-playground" not in MOBILE.read_text(encoding="utf-8")
    assert "def request_is_active_plus" in DEPS.read_text(encoding="utf-8")
    assert 'snapshot.tier == "plus"' in DEPS.read_text(encoding="utf-8")
    add = ADD.read_text(encoding="utf-8")
    assert 'kind == "resume"' in add
    assert 'kind == "expired"' not in add


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


def test_expired_phone_playground_keeps_readonly_home(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_progress_then_expire(client)
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
              const desk = document.querySelector('[data-expired-pg-desktop]');
              const phone = document.querySelector('[data-expired-pg-phone]');
              const grid = document.querySelector('[data-expired-playground="desktop"]');
              return {
                marker: Boolean(grid),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                plus: Boolean(document.querySelector('[data-plus-playground="desktop"]')),
              };
            }"""
        )
        browser.close()
    assert geo["marker"] is True
    assert geo["deskDisplay"] == "none"
    assert geo["phoneDisplay"] != "none"
    assert geo["plus"] is False


def test_expired_playground_screen06_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_progress_then_expire(client)
    home = _home_view(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "expired_playground_screen06_1280.png"
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
              const desk = document.querySelector('[data-expired-pg-desktop]');
              const phone = document.querySelector('[data-expired-pg-phone]');
              const grid = document.querySelector('[data-expired-playground="desktop"]');
              const plus = document.querySelector('[data-plus-playground="desktop"]');
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
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["marker"] is True
    assert geo["plus"] is False
    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["title"] == LIVE_HEADING
    assert geo["lede"] == LIVE_COPY[0]
    assert geo["primaryText"] == "View Playground plans"
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
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_expired_playground_plus_regression_1280(tmp_path: Path) -> None:
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
    shot_path = artifact_dir / "expired_playground_screen06_plus_regression_1280.png"
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
              const expired = document.querySelector('[data-expired-playground="desktop"]');
              const month = document.querySelector('h1.plus-pg-month');
              const aside = document.querySelector('.pg-aside');
              return {
                plus: Boolean(plus),
                expired: Boolean(expired),
                month: month && month.textContent.trim(),
                asideDisplay: aside ? getComputedStyle(aside).display : null,
                browse: plus && /Browse laws/.test(plus.innerText),
                header: document.querySelector('.account-menu-btn-status') &&
                  document.querySelector('.account-menu-btn-status').textContent.trim(),
                paused: document.body.innerText.includes('Your Playground is paused'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["plus"] is True
    assert geo["expired"] is False
    assert geo["month"] == MONTH
    assert geo["asideDisplay"] != "none"
    assert geo["browse"] is True
    assert geo["header"] == "RecallC Plus"
    assert geo["paused"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
