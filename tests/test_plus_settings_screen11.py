"""Plus cohort desktop /settings Screen 11 (CTA map plus/11-screen).

Authorized: ChatGPT. Authenticated multiuser GET /settings with a real
active Plus EntitlementSnapshot. Live current_user, access, learning_plan,
can_auto_plan, next_learning_day, saved, gcal.*, and CSRF. Guest, Free, Pro,
phone, and Plus Screens 01–10 stay on their own wrappers. Calendar OAuth/sync
and the learning-plan engine are not touched.
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
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    InMemorySessionStore,
)
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.web.app import create_app
from tests.test_roster_m5a import _csrf

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
APP = ROOT / "src/constitution_memorizer/web/app.py"
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
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
CAL_SYNC = ROOT / "src/constitution_memorizer/calendar_sync"
PLANNER = ROOT / "src/constitution_memorizer/planner"
AUTH_PY = ROOT / "src/constitution_memorizer/auth"
USER = UUID("11111111-1111-4111-8111-111111111111")
TOKEN_KEY = Fernet.generate_key().decode()
INVENTED = (
    "Premium",
    "Unlock all",
    "No plan yet",
    "See plans",
    "8/10",
    "renews 1 October",
)


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _settings(*, gcal: bool = True) -> MultiUserSettings:
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
        GCAL_CLIENT_ID="gcal-cid" if gcal else "",
        GCAL_CLIENT_SECRET="gcal-secret" if gcal else "",
        GCAL_TOKEN_KEY=TOKEN_KEY if gcal else "",
    )


def _mu_app(tmp_path: Path, *, display_name: str = "Sanjay", gcal: bool = True):
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
        multiuser_settings=_settings(gcal=gcal),
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


def _plus_client(tmp_path: Path, *, gcal: bool = True) -> TestClient:
    client = TestClient(_mu_app(tmp_path, gcal=gcal))
    _sign_in(client)
    _subscribe(client)
    return client


def _header(html: str) -> str:
    return html.split("<header", 1)[-1].split("</header>", 1)[0]


def _account_row(html: str) -> str:
    return html.split("settings-account-row", 1)[1].split("</a>", 1)[0]


def test_plus_settings_reaches_settings_without_nav_pill(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    page = client.get("/settings")
    assert page.status_code == 200
    html = unescape(page.text)
    assert 'data-plus-settings="desktop"' in html
    assert "data-signed-in-settings" in html
    header = _header(html)
    top_nav = header.split("PrimaryTabs--top", 1)[1].split("</nav>", 1)[0]
    assert "Settings" not in top_nav
    assert 'href="/settings"' not in top_nav
    assert 'class="nav-link is-active"' not in top_nav or "Settings" not in top_nav
    assert "RecallC Plus" in header
    assert "Free account" not in header
    assert 'href="/dashboard"' in html
    assert "← Today" in html
    assert 'class="settings-account-row" href="/profile"' in html
    row = _account_row(html)
    assert "Sanjay" in row
    assert "Appearance, your learning plan, and your revision calendar." in html
    for phrase in INVENTED:
        assert phrase not in html, phrase


def test_plus_settings_learning_plan_uses_live_state_and_post(
    tmp_path: Path,
) -> None:
    client = _plus_client(tmp_path)
    html = unescape(client.get("/settings").text)
    assert 'data-settings-group="study"' in html
    assert "Learning plan" in html
    assert "Self-paced" in html
    assert "Auto Plan" in html
    assert 'id="pace-self-paced"' in html
    assert "checked" in html.split('id="pace-self-paced"', 1)[1].split(">", 1)[0]
    assert "disabled" not in html.split('id="pace-auto"', 1)[1].split(">", 1)[0]
    assert "Steady · 3" in html
    assert "Balanced · 5" in html
    assert "Intensive · 7" in html
    assert "checked" in html.split('id="target-5"', 1)[1].split(">", 1)[0]
    assert 'action="/settings/learning-plan"' in html
    assert "Save learning plan" in html
    assert client.cookies.get(CSRF_COOKIE_NAME)
    saved = client.post(
        "/settings/learning-plan",
        data={**_csrf(client), "mode": "auto", "daily_target": "3"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert saved.headers["location"].startswith("/settings")
    after = unescape(client.get("/settings?saved=1").text)
    assert "Settings saved." in after
    assert "checked" in after.split('id="pace-auto"', 1)[1].split(">", 1)[0]
    assert "checked" in after.split('id="target-3"', 1)[1].split(">", 1)[0]
    assert "checked" not in after.split('id="target-5"', 1)[1].split(">", 1)[0]


def test_plus_settings_calendar_uses_live_gcal(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    html = unescape(client.get("/settings").text)
    assert 'data-settings-group="calendar"' in html
    assert "Revision calendar" in html
    assert "Connect Google Calendar" in html
    assert 'href="/calendar/google/connect"' in html
    assert 'href="/privacy#google-calendar"' in html
    assert "Recall the C — Revision Schedule" in html
    assert "Last synced" not in html
    src = SETTINGS.read_text(encoding="utf-8")
    assert "gcal.connected" in src
    assert "gcal.connection" in src
    assert "gcal.prefs" in src
    assert "gcal.status_param" in src
    assert 'action="/calendar/google/preferences"' in src
    assert 'action="/calendar/google/disconnect"' in src


def test_plus_settings_marker_only_for_active_plus(tmp_path: Path) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest")).get("/settings").text
    assert 'data-plus-settings="desktop"' not in guest
    assert "data-signed-in-settings" not in guest
    assert "RecallC Plus" not in _header(guest)

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/settings").text
    assert 'data-plus-settings="desktop"' not in free_html
    assert "data-signed-in-settings" in free_html
    assert "RecallC Plus" not in _header(free_html)

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    pending_html = pending.get("/settings").text
    assert 'data-plus-settings="desktop"' not in pending_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/settings").text
    assert 'data-plus-settings="desktop"' not in pro_html
    assert "RecallC Plus" not in _header(pro_html)


def test_plus_settings_marker_uses_shared_predicate() -> None:
    settings = SETTINGS.read_text(encoding="utf-8")
    assert "plus_settings" in settings
    assert 'data-plus-settings="desktop"' in settings
    assert "data-signed-in-settings" in settings
    assert "can_auto_plan|default(false)" in settings
    assert 'action="/settings/learning-plan"' in settings
    assert 'href="/calendar/google/connect"' in settings
    assert 'href="/privacy#google-calendar"' in settings
    assert 'href="/dashboard"' in settings
    assert "{{ access.status_line }}" in settings
    assert "RecallC Plus" not in settings
    assert "8/10" not in settings
    app = APP.read_text(encoding="utf-8")
    page = app.split("async def settings_page", 1)[1].split(
        "async def settings_save", 1
    )[0]
    assert "request_is_active_plus" in page
    assert '"plus_settings": plus_settings' in page
    plan_post = app.split("async def settings_learning_plan", 1)[1].split(
        "async def choose_get", 1
    )[0]
    assert "plus_settings" not in plan_post
    assert "request_is_active_plus" not in plan_post
    assert "def request_is_active_plus" in DEPS.read_text(encoding="utf-8")
    assert 'snapshot.tier == "plus"' in DEPS.read_text(encoding="utf-8")
    base = BASE.read_text(encoding="utf-8")
    assert "plus_settings_chrome" in base
    assert "RecallC Plus" in base
    assert "playground.css?v=pg28" in base
    css = PG_CSS.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in css
    plus_css = css.split("plus/11-screen", 1)[-1]
    assert "var(--ink)" in plus_css
    assert "#0e7569" not in plus_css
    assert "#3a3a38" not in plus_css
    for phrase in INVENTED:
        assert phrase not in settings, phrase


def test_plus_settings_does_not_touch_accepted_screens_or_engines() -> None:
    assert "data-plus-settings" not in LANDING.read_text(encoding="utf-8")
    assert "data-plus-settings" not in BROWSE.read_text(encoding="utf-8")
    assert "data-plus-settings" not in LAWS.read_text(encoding="utf-8")
    assert "data-plus-settings" not in BARE.read_text(encoding="utf-8")
    assert "data-plus-settings" not in ADD.read_text(encoding="utf-8")
    assert "data-plus-settings" not in HOME.read_text(encoding="utf-8")
    assert "data-plus-settings" not in GATE.read_text(encoding="utf-8")
    assert "data-plus-settings" not in MANAGE.read_text(encoding="utf-8")
    assert "data-plus-settings" not in DASH.read_text(encoding="utf-8")
    assert "data-plus-settings" not in CAL.read_text(encoding="utf-8")
    assert "data-plus-settings" not in PROFILE.read_text(encoding="utf-8")
    assert 'data-plus-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-plus-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-plus-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-plus-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-plus-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-plus-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-plus-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-plus-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-plus-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-plus-settings" not in mobile
    phone_desk = mobile.split(
        'body[data-mscreen="settings"] .settings-desk-copy {', 1
    )[1].split("}", 1)[0]
    assert "display: none" in phone_desk
    settings = SETTINGS.read_text(encoding="utf-8")
    assert "settings-phone-only" in settings
    assert "data-gcal-toggle" in settings
    for path in CAL_SYNC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "plus_settings" not in text
        assert "data-plus-settings" not in text
    for path in PLANNER.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "plus_settings" not in text
        assert "data-plus-settings" not in text
    for path in AUTH_PY.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "plus_settings" not in text
        assert "data-plus-settings" not in text


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


def test_plus_settings_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
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
    shot_path = artifact_dir / "plus_settings_screen11_1280.png"
    free_path = artifact_dir / "plus_settings_screen11_free_1280.png"
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
        page.goto(f"{origin}/settings", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-settings="desktop"]');
              const nav = document.querySelector('.PrimaryTabs--top');
              const active = nav && [...nav.querySelectorAll('.nav-link.is-active')].map(
                (el) => (el.textContent || '').replace(/\\s+/g, ' ').trim()
              );
              const back = plus && plus.querySelector('.si-settings-desk-back a');
              const heading = plus && plus.querySelector(':scope > .display');
              const ident = plus && plus.querySelector('.settings-account-row');
              const study = plus && plus.querySelector('[data-settings-group="study"]');
              const cal = plus && plus.querySelector('[data-settings-group="calendar"]');
              const save = study && study.querySelector('button[type="submit"]');
              const connect = cal && cal.querySelector('[data-gcal-connect]');
              const privacy = cal && cal.querySelector('a[href="/privacy#google-calendar"]');
              const selfPace = study && study.querySelector('#pace-self-paced');
              const autoPace = study && study.querySelector('#pace-auto');
              const selfLabel = study && study.querySelector('label[for="pace-self-paced"]');
              const autoLabel = study && study.querySelector('label[for="pace-auto"]');
              const targetChecked = study && study.querySelector(
                'input[name="daily_target"]:checked'
              );
              const targetLabel = targetChecked && study.querySelector(
                'label[for="' + targetChecked.id + '"]'
              );
              const form = study && study.querySelector('form.settings-plan-form');
              const selfCs = selfLabel ? getComputedStyle(selfLabel) : null;
              const autoCs = autoLabel ? getComputedStyle(autoLabel) : null;
              const identBox = ident && ident.getBoundingClientRect();
              const studyBox = study && study.getBoundingClientRect();
              const calBox = cal && cal.getBoundingClientRect();
              const status = document.querySelector('.account-menu-btn-status');
              const identStatus = ident && ident.querySelector('.settings-account-status');
              return {
                present: Boolean(plus),
                heading: heading && (heading.textContent || '').trim(),
                activeNav: active || [],
                backText: back && (back.textContent || '').replace(/\\s+/g, ' ').trim(),
                backHref: back && back.getAttribute('href'),
                backDisplay: back ? getComputedStyle(back).display : 'none',
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
                autoDisabled: Boolean(autoPace && autoPace.disabled),
                selfBg: selfCs && selfCs.backgroundColor,
                selfColor: selfCs && selfCs.color,
                autoBg: autoCs && autoCs.backgroundColor,
                targetId: targetChecked && targetChecked.id,
                targetText: targetLabel && (targetLabel.textContent || '').replace(/\\s+/g, ' ').trim(),
                formAction: form && form.getAttribute('action'),
                saveText: save && (save.textContent || '').replace(/\\s+/g, ' ').trim(),
                connectHref: connect && connect.getAttribute('href'),
                connectText: connect && (connect.textContent || '').replace(/\\s+/g, ' ').trim(),
                privacyHref: privacy && privacy.getAttribute('href'),
                status: status && (status.textContent || '').trim(),
                statusDisplay: status ? getComputedStyle(status).display : 'none',
                hasSynced: /Last synced/.test(cal ? cal.innerText : ''),
                hasSettingsPill: (active || []).some((t) => t.includes('Settings')),
              };
            }"""
        )
        page.evaluate(
            "() => document.activeElement && document.activeElement.blur()"
        )
        page.screenshot(path=str(shot_path), full_page=False)

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/settings", wait_until="networkidle")
        phone = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-settings="desktop"]');
              const deskCopy = plus && plus.querySelector('.settings-desk-copy');
              const deskBack = plus && plus.querySelector('.si-settings-desk-back');
              const toggle = plus && plus.querySelector('[data-gcal-toggle]');
              return {
                present: Boolean(plus),
                deskCopyDisplay: deskCopy ? getComputedStyle(deskCopy).display : null,
                deskBackDisplay: deskBack ? getComputedStyle(deskBack).display : null,
                toggleDisplay: toggle ? getComputedStyle(toggle.closest('.settings-phone-only') || toggle).display : null,
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
        free_page.goto(f"{free_origin}/settings", wait_until="networkidle")
        free_page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        free_geo = free_page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-settings="desktop"]');
              const signed = document.querySelector('[data-signed-in-settings]');
              const status = document.querySelector('.account-menu-btn-status');
              const autoPace = document.querySelector('#pace-auto');
              return {
                plus: Boolean(plus),
                signed: Boolean(signed),
                status: status && (status.textContent || '').trim(),
                autoDisabled: Boolean(autoPace && autoPace.disabled),
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
    assert geo["heading"] == "Settings"
    assert geo["hasSettingsPill"] is False
    assert "Settings" not in (geo["activeNav"] or [])
    assert geo["backText"] == "← Today"
    assert geo["backHref"] == "/dashboard"
    assert geo["backDisplay"] not in (None, "none")
    assert geo["identHref"] == "/profile"
    assert "Sanjay" in (geo["name"] or "")
    assert geo["studyBelow"] is True
    assert geo["calBelow"] is True
    assert geo["selfChecked"] is True
    assert geo["autoDisabled"] is False
    assert geo["selfBg"] == "rgb(20, 20, 20)"
    assert geo["selfColor"] == "rgb(255, 255, 255)"
    assert geo["autoBg"] != "rgb(20, 20, 20)"
    assert geo["targetId"] == "target-5"
    assert "Balanced" in (geo["targetText"] or "")
    assert geo["formAction"] == "/settings/learning-plan"
    assert geo["saveText"] == "Save learning plan"
    assert geo["connectHref"].startswith("/calendar/google/connect")
    assert geo["connectText"] == "Connect Google Calendar"
    assert geo["privacyHref"] == "/privacy#google-calendar"
    assert geo["status"] == "RecallC Plus"
    assert geo["statusDisplay"] != "none"
    assert geo["hasSynced"] is False
    assert phone["present"] is True
    assert phone["deskCopyDisplay"] == "none"
    assert phone["deskBackDisplay"] == "none"
    assert free_geo["plus"] is False
    assert free_geo["signed"] is True
    assert free_geo["status"] != "RecallC Plus"
    assert shot_path.exists() and shot_path.stat().st_size > 1000
    assert free_path.exists() and free_path.stat().st_size > 1000
