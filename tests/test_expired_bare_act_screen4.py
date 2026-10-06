"""Expired cohort desktop NDPS Bare Act Screen 04 (CTA map expired/04-screen).

Authorized: ChatGPT. Authenticated multiuser GET /laws/ndps with a real
expired subscription whose paid period has ended, after NDPS was added
through the real roster/add flow. The Act stays readable. Retained
presentation follows pg.kind == already_active, not pg.subscribed.
Workspace Continue is not hard-coded: live primary is the paid-period-ended
lifecycle CTA because /playground/laws/ndps is not allowed. Guest, Free,
Plus, halted, phone, Plus 01–11, and Expired 01–03 stay unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import socket
import threading
import time
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
from constitution_memorizer.playground.urls import add_path, home_path, law_path, sections_path
from constitution_memorizer.playground.view import PLAYGROUND_BILLING_PATH, gate_view
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.guest_bareact_head import (
    NDPS_GUEST_KICKER,
    NDPS_GUEST_META,
    NDPS_GUEST_ROWS,
    NDPS_GUEST_TITLE,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "data" / "output" / "learning_units.json"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
APP = ROOT / "src/constitution_memorizer/web/app.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
MANAGE = ROOT / "src/constitution_memorizer/web/templates/subscription_manage.html"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_EXPIRED_STATUS = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
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


def _seed_ndps_then_expire(client: TestClient) -> None:
    _subscribe(client)
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps")
    _expire(client)


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _desk(html: str) -> str:
    return html.split("data-signed-in-bareact-desktop", 1)[1].split(
        "data-bareact-phone", 1
    )[0]


def test_expired_retained_ndps_uses_live_already_active_not_subscribed(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_then_expire(client)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert snap.subscription_status == "expired"
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    html = client.get("/laws/ndps").text
    header = _header(html)
    desk = _desk(html)
    assert 'data-expired-bareact="desktop"' in html
    assert 'data-plus-bareact="desktop"' not in html
    assert "data-signed-in-bareact-desktop" in html
    assert "data-guest-bareact-desktop" not in html
    assert NDPS_GUEST_KICKER in desk
    assert f">{NDPS_GUEST_TITLE}<" in desk
    assert NDPS_GUEST_META in desk
    assert 'class="guest-bareact-back" href="/laws"' in desk
    assert "Already in Playground" in desk
    assert 'data-pg-kind="already_active"' in desk
    assert 'class="signed-bareact-in-pg"' in desk
    assert ">Sections<" in desk
    assert f'href="{sections_path("ndps")}"' in desk
    assert f'class="signed-bareact-continue" href="{PLAYGROUND_BILLING_PATH}"' in desk
    assert ">Resume Playground<" in desk
    assert f'class="signed-bareact-continue" href="{home_path()}"' not in desk
    assert ">Continue<" not in desk
    assert "+ Add to Playground" not in desk
    assert 'data-pg-kind="eligible_to_add"' not in desk
    assert "Subscribe to use Playground" not in desk
    assert "Sign in to use Playground" not in desk
    assert LIVE_EXPIRED_STATUS in header
    assert "Free account" not in header
    assert "RecallC Plus" not in header
    assert "Sanjay" in header
    for phrase in INVENTED:
        assert phrase not in desk, phrase
    for row in NDPS_GUEST_ROWS:
        assert row.title in desk
    assert 'href="/laws/ndps/section/' not in desk
    workspace = client.get(law_path("ndps"))
    assert workspace.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAID_PERIOD_ENDED}"' in workspace.text
    assert 'data-pg-learn-panel="cloze"' not in workspace.text
    sections = client.get(sections_path("ndps"))
    assert sections.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAID_PERIOD_ENDED}"' in sections.text
    home = client.get("/playground")
    assert home.status_code == 200
    assert "is-readonly" in home.text or "read_only" in home.text or LIVE_EXPIRED_STATUS in home.text
    assert 'data-hard-gate="true"' not in home.text
    chapter = client.get("/laws/ndps/section/8")
    assert chapter.status_code == 200


def test_never_added_law_does_not_get_retained_treatment(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_then_expire(client)
    bns = client.get("/laws/bns").text
    assert 'data-expired-bareact="desktop"' not in bns
    assert "data-signed-in-bareact-desktop" not in bns
    assert "Already in Playground" not in bns
    assert 'data-pg-kind="already_active"' not in bns
    assert 'class="signed-bareact-continue"' not in bns
    assert "+ Add to Playground" not in bns
    assert 'data-pg-kind="eligible_to_add"' not in bns
    assert 'data-pg-kind="resume"' in bns

    fresh = TestClient(_mu_app(tmp_path / "none"))
    _sign_in(fresh)
    _subscribe(fresh)
    _expire(fresh)
    ndps = fresh.get("/laws/ndps").text
    desk = _desk(ndps)
    assert 'data-expired-bareact="desktop"' in ndps
    assert "Already in Playground" not in desk
    assert 'class="signed-bareact-in-pg"' not in desk
    assert 'class="signed-bareact-continue"' not in desk
    assert ">Continue<" not in desk
    assert "+ Add to Playground" not in desk
    assert 'data-pg-kind="resume"' in desk
    assert "Resume Playground" in desk


def test_free_plus_guest_halted_stay_separate_from_expired(tmp_path: Path) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest"))
    guest_html = guest.get("/laws/ndps").text
    assert 'data-expired-bareact="desktop"' not in guest_html
    assert "data-guest-bareact-desktop" in guest_html
    assert "data-signed-in-bareact-desktop" not in guest_html
    assert "Sign in to use Playground" in guest_html
    assert "RecallC Plus" not in guest_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/laws/ndps").text
    assert 'data-expired-bareact="desktop"' not in free_html
    assert 'data-plus-bareact="desktop"' not in free_html
    free_desk = _desk(free_html)
    assert "Subscribe to use Playground" in free_desk
    assert "Already in Playground" not in free_desk
    assert "Free account" in _header(free_html)
    assert LIVE_EXPIRED_STATUS not in _header(free_html)

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    added = _confirm_add(plus, "ndps")
    assert added.status_code in {200, 303}
    plus_html = plus.get("/laws/ndps").text
    assert 'data-plus-bareact="desktop"' in plus_html
    assert 'data-expired-bareact="desktop"' not in plus_html
    plus_desk = _desk(plus_html)
    assert "Already in Playground" in plus_desk
    assert f'class="signed-bareact-continue" href="{home_path()}"' in plus_desk
    assert ">Continue<" in plus_desk
    assert "RecallC Plus" in _header(plus_html)
    assert LIVE_EXPIRED_STATUS not in _header(plus_html)

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    added = _confirm_add(halted, "ndps")
    assert added.status_code in {200, 303}
    stored = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )
    halted_html = halted.get("/laws/ndps").text
    assert 'data-expired-bareact="desktop"' not in halted_html
    assert 'data-plus-bareact="desktop"' not in halted_html
    assert LIVE_EXPIRED_STATUS not in _header(halted_html)
    halted_snap = halted.app.state.entitlement_service.resolve(USER)
    assert halted_snap.subscription_status == "halted"
    assert halted_snap.playground_block_reason != BLOCK_PAID_PERIOD_ENDED
    halted_desk = _desk(halted_html)
    assert "Already in Playground" not in halted_desk
    assert 'data-pg-kind="already_active"' not in halted_desk
    assert 'class="signed-bareact-in-pg"' not in halted_desk
    assert ">Continue<" not in halted_desk
    assert "Subscribe to use Playground" in halted_desk


def test_expired_bareact_uses_shared_predicate_not_subscribed_gate() -> None:
    bare = BARE.read_text(encoding="utf-8")
    assert "expired_bareact" in bare
    assert 'data-expired-bareact="desktop"' in bare
    assert "plus_bareact" in bare
    assert 'data-plus-bareact="desktop"' in bare
    assert "data-signed-in-bareact-desktop" in bare
    assert "data-guest-bareact-desktop" in bare
    assert "pg.kind == 'already_active'" in bare
    assert "pg_subscribed and pg.kind" not in bare
    assert 'href="/playground">Continue</a>' in bare
    assert "pg_subscribed" in bare
    assert "Your Playground is paused" not in bare
    assert "Playground paused" not in bare
    assert LIVE_EXPIRED_STATUS not in bare
    base = BASE.read_text(encoding="utf-8")
    assert "expired_bareact" in base
    assert "expired_header_status" in base
    assert "path == '/laws/ndps'" in base
    assert "Playground paused" not in base
    app = APP.read_text(encoding="utf-8")
    page = app.split("async def law_detail_page", 1)[1].split(
        "async def bare_act_section_page", 1
    )[0]
    assert "request_is_expired_subscriber" in page
    assert "request_is_active_plus" in page
    assert '"plus_bareact": request_is_active_plus(request)' in page
    assert '"expired_bareact": expired_bareact' in page
    assert "def snapshot_is_expired_subscriber" not in page
    deps = DEPS.read_text(encoding="utf-8")
    assert "def request_is_expired_subscriber" in deps
    assert "BLOCK_PAID_PERIOD_ENDED" in deps
    view = VIEW.read_text(encoding="utf-8")
    assert 'badge_label="Already in Playground"' in view
    assert 'primary_label="Resume Playground"' in view


def test_plus_screens_and_expired_01_02_03_untouched() -> None:
    assert 'data-plus-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-expired-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-plus-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-expired-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-plus-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-expired-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-plus-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-plus-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-plus-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-plus-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-plus-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-plus-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    landing = LANDING.read_text(encoding="utf-8")
    assert "data-expired-bareact" not in landing
    browse = BROWSE.read_text(encoding="utf-8")
    assert "data-expired-bareact" not in browse
    laws = LAWS.read_text(encoding="utf-8")
    assert "data-expired-bareact" not in laws
    for path in (ADD, HOME, MANAGE, DASH, CAL, PROFILE, SETTINGS):
        text = path.read_text(encoding="utf-8")
        assert "data-expired-bareact" not in text
        assert "expired_bareact" not in text
        assert "data-expired-landing" not in text
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-expired-bareact" not in mobile
    assert "def request_is_active_plus" in DEPS.read_text(encoding="utf-8")
    assert 'snapshot.tier == "plus"' in DEPS.read_text(encoding="utf-8")


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


def test_expired_phone_bareact_unchanged(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_then_expire(client)
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
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        phone = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-signed-in-bareact-desktop]');
              const expired = document.querySelector('[data-expired-bareact="desktop"]');
              const prod = document.querySelector('[data-bareact-phone]');
              return {
                expiredPresent: Boolean(expired),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                prodDisplay: prod ? getComputedStyle(prod).display : null,
                details: prod ? prod.querySelectorAll('details').length : 0,
              };
            }"""
        )
        browser.close()
    assert phone["expiredPresent"] is True
    assert phone["deskDisplay"] == "none"
    assert phone["prodDisplay"] != "none"
    assert phone["details"] > 0


def test_expired_bareact_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_then_expire(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "expired_bareact_screen04_1280.png"
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
        geo = page.evaluate(
            """() => {
              const expired = document.querySelector('[data-expired-bareact="desktop"]');
              const desk = document.querySelector('[data-signed-in-bareact-desktop]');
              const plus = document.querySelector('[data-plus-bareact="desktop"]');
              const guest = document.querySelector('[data-guest-bareact-desktop]');
              const phone = document.querySelector('[data-bareact-phone]');
              const brand = document.querySelector('.brand');
              const mark = document.querySelector('.brand-mark');
              const back = desk && desk.querySelector('.guest-bareact-back');
              const cluster = desk && desk.querySelector('.signed-bareact-in-pg');
              const sections = desk && desk.querySelector('.signed-bareact-sections');
              const cont = desk && desk.querySelector('.signed-bareact-continue');
              const rows = desk ? [...desk.querySelectorAll('.guest-bareact-row')] : [];
              const panelText = desk ? desk.innerText : '';
              return {
                present: Boolean(expired),
                plusPresent: Boolean(plus),
                deskDisplay: desk && getComputedStyle(desk).display,
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                guestPresent: !!guest,
                brandHref: brand.getAttribute('href'),
                markFilter: getComputedStyle(mark).filter,
                backHref: back && back.getAttribute('href'),
                kicker: desk && desk.querySelector('.guest-bareact-kicker').textContent.trim(),
                title: desk && desk.querySelector('.guest-bareact-title').textContent.trim(),
                meta: desk && desk.querySelector('.guest-bareact-meta').textContent.trim(),
                already: panelText.includes('Already in Playground'),
                clusterPresent: !!cluster,
                sectionsHref: sections && sections.getAttribute('href'),
                sectionsText: sections && sections.textContent.trim(),
                continueHref: cont && cont.getAttribute('href'),
                continueText: cont && cont.textContent.trim(),
                addShown: /Add to Playground/.test(panelText),
                subscribe: panelText.includes('Subscribe to use Playground'),
                signIn: panelText.includes('Sign in to use Playground'),
                invented: /Your plan expired|Resume subscription|Premium|Unlimited|Unlock all|Free plan|All 3 slots/.test(panelText),
                rowCount: rows.length,
                rowTitles: rows.map((el) =>
                  el.querySelector('.guest-bareact-row-title').textContent.trim()
                ),
                accountName: document.querySelector('.account-menu-btn-name').textContent.trim(),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                navLabels: [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                  (el) => el.textContent.replace(/\\s+/g, ' ').trim()
                ),
                browseActive: document.querySelector('.PrimaryTabs--top .nav-link.is-active')
                  .textContent.replace(/\\s+/g, ' ').trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator('[data-expired-bareact="desktop"] .guest-bareact-back').click()
        page.wait_for_function("() => location.pathname === '/laws'", timeout=8000)
        laws_path = page.evaluate("() => location.pathname")
        browser.close()

    assert geo["present"] is True
    assert geo["plusPresent"] is False
    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["guestPresent"] is False
    assert geo["brandHref"] == "/dashboard"
    assert "invert" in geo["markFilter"]
    assert geo["backHref"] == "/laws"
    assert geo["kicker"] == NDPS_GUEST_KICKER
    assert geo["title"] == NDPS_GUEST_TITLE
    assert geo["meta"] == NDPS_GUEST_META
    assert geo["already"] is True
    assert geo["clusterPresent"] is True
    assert geo["sectionsText"] == "Sections"
    assert geo["sectionsHref"] == sections_path("ndps")
    assert geo["continueText"] == "Resume Playground"
    assert geo["continueHref"] == PLAYGROUND_BILLING_PATH
    assert geo["addShown"] is False
    assert geo["subscribe"] is False
    assert geo["signIn"] is False
    assert geo["invented"] is False
    assert geo["rowCount"] == 4
    assert geo["rowTitles"] == [row.title for row in NDPS_GUEST_ROWS]
    assert geo["accountName"] == "Sanjay"
    assert geo["accountStatus"] == LIVE_EXPIRED_STATUS
    assert geo["navLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["browseActive"] == "Browse"
    assert laws_path == "/laws"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_plus_bareact_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "expired_bareact_screen04_plus_regression_1280.png"
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
        geo = page.evaluate(
            """() => {
              const expired = document.querySelector('[data-expired-bareact="desktop"]');
              const plus = document.querySelector('[data-plus-bareact="desktop"]');
              const desk = document.querySelector('[data-signed-in-bareact-desktop]');
              const cluster = desk && desk.querySelector('.signed-bareact-in-pg');
              const sections = desk && desk.querySelector('.signed-bareact-sections');
              const cont = desk && desk.querySelector('.signed-bareact-continue');
              return {
                expiredPresent: Boolean(expired),
                plusPresent: Boolean(plus),
                already: desk && desk.innerText.includes('Already in Playground'),
                clusterPresent: !!cluster,
                sectionsHref: sections && sections.getAttribute('href'),
                continueHref: cont && cont.getAttribute('href'),
                continueText: cont && cont.textContent.trim(),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                title: desk && desk.querySelector('.guest-bareact-title').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["expiredPresent"] is False
    assert geo["plusPresent"] is True
    assert geo["already"] is True
    assert geo["clusterPresent"] is True
    assert geo["sectionsHref"] == sections_path("ndps")
    assert geo["continueHref"] == home_path()
    assert geo["continueText"] == "Continue"
    assert geo["accountStatus"] == "RecallC Plus"
    assert geo["title"] == NDPS_GUEST_TITLE
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
