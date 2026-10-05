"""Signed-in desktop Settings Screen 11 (CTA map signedIn/11-screen).

Authorized: ChatGPT. Authenticated multiuser GET /settings desktop only.
Phone Settings, Gate, and accepted screens 01–06 / 08 / 09 / 10 stay unchanged.
Learning-plan and revision-calendar state stay existing product truth.
Mock Free-account copy and fabricated connected-calendar state are not shipped.
"""

from __future__ import annotations

import socket
import threading
import time
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

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
USER = UUID("11111111-1111-4111-8111-111111111111")
TOKEN_KEY = Fernet.generate_key().decode()

MOCK_SCREEN_COPY = (
    "Free account",
    "No plan yet",
    "See plans",
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


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def test_signed_in_settings_desktop_surface(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    page = client.get("/settings")
    assert page.status_code == 200
    html = page.text
    assert "data-signed-in-settings" in html
    guest = TestClient(client.app).get("/settings")
    assert guest.status_code == 200
    assert "data-signed-in-settings" not in guest.text
    header = _header(html)
    top_nav = header.split("PrimaryTabs--top", 1)[1].split("</nav>", 1)[0]
    assert "Settings" not in top_nav
    assert "nav-link is-active" not in top_nav
    assert 'href="/dashboard"' in html
    assert "← Today" in html
    assert "Sanjay" in html
    assert "Signed in with Google" in html
    for phrase in MOCK_SCREEN_COPY:
        assert phrase not in html, phrase
    assert "Appearance, your learning plan, and your revision calendar." in html
    assert 'data-settings-group="study"' in html
    assert "Learning plan" in html
    assert "Self-paced" in html
    assert "Auto Plan" in html
    assert 'action="/settings/learning-plan"' in html
    assert "Save learning plan" in html
    assert 'data-settings-group="calendar"' in html
    assert "Revision calendar" in html
    assert "Connect Google Calendar" in html
    assert 'href="/calendar/google/connect"' in html
    assert 'href="/privacy#google-calendar"' in html
    assert "Recall the C — Revision Schedule" in html
    assert "Last synced" not in html
    assert 'href="/profile"' in html
    assert "/pricing" not in html
    gate = client.get("/playground", follow_redirects=False)
    assert gate.status_code == 200
    assert 'data-playground-gate="not_subscribed"' in gate.text


def test_signed_in_settings_real_plan_and_calendar_destinations(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path, display_name="Priya"))
    _sign_in(client)
    html = client.get("/settings").text
    assert "Priya" in html
    assert 'href="/profile"' in html.split("settings-account-row", 1)[1][:200]
    csrf = client.cookies.get(CSRF_COOKIE_NAME) or ""
    saved = client.post(
        "/settings/learning-plan",
        data={"csrf_token": csrf, "mode": "auto", "daily_target": "5"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert saved.headers["location"].startswith("/settings")
    after = client.get("/settings").text
    assert "Settings saved." in after or 'name="mode" value="auto"' in after
    assert 'id="pace-auto"' in after
    connect = client.get("/calendar/google/connect", follow_redirects=False)
    assert connect.status_code == 303
    assert "accounts.google.com" in connect.headers["location"]
    src = SETTINGS.read_text(encoding="utf-8")
    for phrase in MOCK_SCREEN_COPY:
        assert phrase not in src, phrase
    assert 'action="/settings/learning-plan"' in src
    assert 'href="/calendar/google/connect"' in src
    assert 'action="/calendar/google/preferences"' in src
    assert 'action="/calendar/google/disconnect"' in src
    assert 'href="/privacy#google-calendar"' in src


def test_signed_in_settings_does_not_touch_accepted_screens() -> None:
    settings = SETTINGS.read_text(encoding="utf-8")
    assert "data-signed-in-settings" in settings
    assert 'data-settings-group="study"' in settings
    assert 'data-settings-group="calendar"' in settings
    assert 'class="settings-group settings-phone-only" data-settings-group="account"' in settings
    assert "data-plan-autosubmit" in settings
    assert "data-gcal-reminder-modal" in settings

    assert "data-signed-in-settings" not in DASH.read_text(encoding="utf-8")
    assert "data-signed-in-today" in DASH.read_text(encoding="utf-8")
    assert "data-signed-in-settings" not in CAL.read_text(encoding="utf-8")
    assert "data-signed-in-calendar" in CAL.read_text(encoding="utf-8")
    assert "data-signed-in-settings" not in PROFILE.read_text(encoding="utf-8")
    assert "data-signed-in-profile" in PROFILE.read_text(encoding="utf-8")
    assert "data-signed-in-settings" not in ADD.read_text(encoding="utf-8")
    assert "data-signed-in-settings" not in HOME.read_text(encoding="utf-8")
    assert "data-signed-in-settings" not in GATE.read_text(encoding="utf-8")
    assert "data-signed-in-pg-gate" in GATE.read_text(encoding="utf-8")
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-guest-landing="desktop"' in landing
    assert "data-signed-in-browse-strip" in BROWSE.read_text(encoding="utf-8")
    assert "data-signed-in-laws-desktop" in LAWS.read_text(encoding="utf-8")
    assert "data-signed-in-bareact-desktop" in BARE.read_text(encoding="utf-8")

    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-signed-in-settings" not in mobile
    phone_desk = mobile.split(
        'body[data-mscreen="settings"] .settings-desk-copy {', 1
    )[1].split("}", 1)[0]
    assert "display: none" in phone_desk

    pg_css = PG_CSS.read_text(encoding="utf-8")
    signed_gate_title = pg_css.split(
        ".PlaygroundShell .EntitlementGate[data-signed-in-pg-gate] h1 {", 1
    )[1].split("}", 1)[0]
    assert "font-size: 28px" in signed_gate_title

    css = STYLES.read_text(encoding="utf-8")
    r1 = css.split("/* R1 desktop shell", 1)[1].split(
        "/* Signed-in desktop Today", 1
    )[0]
    assert "position: absolute" not in r1
    assert "left: 50%" not in r1
    today = css.split("/* Signed-in desktop Today", 1)[1].split(
        "/* Signed-in desktop Calendar", 1
    )[0]
    assert "minmax(260px, 380px)" in today
    profile = css.split("/* Signed-in desktop Profile", 1)[1].split(
        "/* Signed-in desktop Settings", 1
    )[0]
    assert "minmax(0, 1fr) minmax(0, 1fr)" in profile
    signed = css.split("/* Signed-in desktop Settings", 1)[1].split(
        "/* R7 closeout", 1
    )[0]
    assert "position: absolute" not in signed
    assert "left: 50%" not in signed
    assert "max-width: 720px" in signed
    assert "font-size: 30px" in signed
    assert "data-signed-in-settings" in signed


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


def test_signed_in_settings_1280_and_phone(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "signed_in_settings_screen11_1280.png"
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
              const panel = document.querySelector('[data-signed-in-settings]');
              const nav = document.querySelector('.PrimaryTabs--top');
              const active = nav && [...nav.querySelectorAll('.nav-link.is-active')].map(
                (el) => (el.textContent || '').trim()
              );
              const back = panel && panel.querySelector('.mobile-back');
              const heading = panel && panel.querySelector(':scope > .display');
              const ident = panel && panel.querySelector('.settings-account-row');
              const study = panel && panel.querySelector('[data-settings-group="study"]');
              const cal = panel && panel.querySelector('[data-settings-group="calendar"]');
              const save = study && study.querySelector('button[type="submit"]');
              const connect = cal && cal.querySelector('[data-gcal-connect]');
              const selfPace = study && study.querySelector('#pace-self-paced');
              const autoPace = study && study.querySelector('#pace-auto');
              const identBox = ident && ident.getBoundingClientRect();
              const studyBox = study && study.getBoundingClientRect();
              const calBox = cal && cal.getBoundingClientRect();
              const identCs = ident ? getComputedStyle(ident) : null;
              const backCs = back ? getComputedStyle(back) : null;
              const status = ident && ident.querySelector('.settings-account-status');
              return {
                present: Boolean(panel),
                activeNav: active || [],
                backText: back && (back.textContent || '').replace(/\\s+/g, ' ').trim(),
                backHref: back && back.getAttribute('href'),
                backDisplay: backCs && backCs.display,
                headingSize: heading ? getComputedStyle(heading).fontSize : null,
                identDisplay: identCs && identCs.display,
                identHref: ident && ident.getAttribute('href'),
                name: ident && (ident.innerText || ''),
                status: status && (status.textContent || '').trim(),
                studyBelow: Boolean(
                  identBox && studyBox && studyBox.top > identBox.bottom - 8
                ),
                calBelow: Boolean(
                  studyBox && calBox && calBox.top > studyBox.bottom - 8
                ),
                selfChecked: Boolean(selfPace && selfPace.checked),
                autoDisabled: Boolean(autoPace && autoPace.disabled),
                saveText: save && (save.textContent || '').replace(/\\s+/g, ' ').trim(),
                connectHref: connect && connect.getAttribute('href'),
                connectText: connect && (connect.textContent || '').replace(/\\s+/g, ' ').trim(),
                hasFreeAccount: /Free account/.test(panel ? panel.innerText : ''),
                hasSynced: /Last synced/.test(cal ? cal.innerText : ''),
                hasSettingsPill: (active || []).includes('Settings'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator(".settings-account-row").click()
        page.wait_for_url("**/profile**", timeout=8000)
        profile_path = page.evaluate("() => location.pathname")

        page.goto(f"{origin}/settings", wait_until="networkidle")
        page.locator(".mobile-back").click()
        page.wait_for_url("**/dashboard**", timeout=8000)
        today_path = page.evaluate("() => location.pathname")

        page.goto(f"{origin}/settings", wait_until="networkidle")
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/settings", wait_until="networkidle")
        phone_geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-signed-in-settings]');
              const back = panel && panel.querySelector('.mobile-back');
              const ident = panel && panel.querySelector('.settings-account-row');
              const deskCopy = panel && panel.querySelector('.settings-desk-copy');
              const connect = panel && panel.querySelector('[data-gcal-connect]');
              return {
                present: Boolean(panel),
                backDisplay: back ? getComputedStyle(back).display : null,
                identDisplay: ident ? getComputedStyle(ident).display : null,
                deskCopyDisplay: deskCopy ? getComputedStyle(deskCopy).display : null,
                connectDisplay: connect ? getComputedStyle(connect).display : null,
              };
            }"""
        )
        browser.close()

    assert geo["present"] is True
    assert geo["hasSettingsPill"] is False
    assert "Settings" not in geo["activeNav"]
    assert geo["backText"] == "← Today"
    assert geo["backHref"] == "/dashboard"
    assert geo["backDisplay"] not in (None, "none")
    assert geo["headingSize"] == "30px"
    assert geo["identDisplay"] == "flex"
    assert geo["identHref"] == "/profile"
    assert "Sanjay" in (geo["name"] or "")
    assert geo["status"] == "Signed in with Google"
    assert geo["studyBelow"] is True
    assert geo["calBelow"] is True
    assert geo["selfChecked"] is True
    assert geo["autoDisabled"] is False
    assert geo["saveText"] == "Save learning plan"
    assert geo["connectHref"] == "/calendar/google/connect"
    assert geo["connectText"] == "Connect Google Calendar"
    assert geo["hasFreeAccount"] is False
    assert geo["hasSynced"] is False
    assert profile_path.rstrip("/") == "/profile"
    assert today_path.rstrip("/") == "/dashboard"
    assert phone_geo["present"] is True
    assert phone_geo["deskCopyDisplay"] == "none"
    assert phone_geo["connectDisplay"] == "none"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
