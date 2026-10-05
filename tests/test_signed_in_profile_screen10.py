"""Signed-in desktop Profile Screen 10 (CTA map signedIn/10-screen).

Authorized: ChatGPT. Authenticated multiuser GET /profile desktop only.
Phone Profile, Gate, and accepted screens 01–06 / 08 / 09 stay unchanged.
Copy, destinations, and subscription/device state stay existing product
truth. Mock Free-account screenshot strings are not shipped.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.view import PLAYGROUND_BILLING_PATH
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
USER = UUID("11111111-1111-4111-8111-111111111111")

MOCK_SCREEN_COPY = (
    "No plan yet",
    "See plans",
    "2 of 3",
    "Free account · Constitution learning included",
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


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _account_list(html: str) -> str:
    return html.split("data-profile-account", 1)[1].split("</div>", 1)[0]


def test_signed_in_free_profile_desktop_surface(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    page = client.get("/profile")
    assert page.status_code == 200
    html = page.text
    assert "data-signed-in-profile" in html
    header = _header(html)
    assert 'href="/playground"' in header
    assert 'href="/browse"' in header
    assert 'href="/dashboard"' in header
    assert 'href="/profile"' in header
    assert 'class="nav-link is-active"' in header
    assert 'aria-current="page"' in header
    assert ">Profile<" in header
    assert "data-profile-identity" in html
    assert "Sanjay" in html
    assert "Signed in with Google" in html
    assert "data-profile-account" in html
    assert "data-profile-subscription" in html
    assert ">Playground<" in html
    assert "Subscribe to add Bare Acts to a monthly Playground." in html
    assert ">Subscribe<" in html
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in html
    assert PLAYGROUND_BILLING_PATH == "/billing/subscriptions"
    for phrase in MOCK_SCREEN_COPY:
        assert phrase not in html, phrase
    assert "/pricing" not in html
    gate = client.get("/playground", follow_redirects=False)
    assert gate.status_code == 200
    assert 'data-playground-gate="not_subscribed"' in gate.text


def test_signed_in_profile_account_destinations_and_real_state(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path, display_name="Priya"))
    _sign_in(client)
    html = client.get("/profile").text
    account = _account_list(html)
    assert 'href="/profile"' in account
    assert "Priya" in account
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

    devices = client.get("/profile/security/devices", follow_redirects=False)
    assert devices.status_code == 200
    settings = client.get("/settings", follow_redirects=False)
    assert settings.status_code == 200
    billing = client.get(PLAYGROUND_BILLING_PATH, follow_redirects=False)
    assert billing.status_code in {200, 303}

    src = PROFILE.read_text(encoding="utf-8")
    for phrase in MOCK_SCREEN_COPY:
        assert phrase not in src, phrase


def test_signed_in_profile_does_not_touch_accepted_screens() -> None:
    profile = PROFILE.read_text(encoding="utf-8")
    assert "data-signed-in-profile" in profile
    assert "data-guest-profile-desktop" in profile
    assert "data-report-open" in profile
    assert "data-open-signout" in profile
    assert 'href="/profile/security/devices"' in profile
    assert 'href="/settings"' in profile
    assert "{{ playground_subscription.cta_href }}" in profile
    assert "{{ playground_subscription.cta_label }}" in profile
    assert "{{ identity_meta" in profile
    assert "{{ device_count_label }}" in profile

    assert "data-signed-in-profile" not in DASH.read_text(encoding="utf-8")
    assert "data-signed-in-today" in DASH.read_text(encoding="utf-8")
    assert "data-signed-in-profile" not in CAL.read_text(encoding="utf-8")
    assert "data-signed-in-calendar" in CAL.read_text(encoding="utf-8")
    assert "data-signed-in-profile" not in ADD.read_text(encoding="utf-8")
    assert "data-signed-in-profile" not in HOME.read_text(encoding="utf-8")
    assert "data-signed-in-profile" not in GATE.read_text(encoding="utf-8")
    assert "data-signed-in-pg-gate" in GATE.read_text(encoding="utf-8")
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-guest-landing="desktop"' in landing
    assert "data-signed-in-browse-strip" in BROWSE.read_text(encoding="utf-8")
    assert "data-signed-in-laws-desktop" in LAWS.read_text(encoding="utf-8")
    assert "data-signed-in-bareact-desktop" in BARE.read_text(encoding="utf-8")

    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-signed-in-profile" not in mobile
    assert "si-profile-desk-only" not in mobile
    phone_profile = mobile.split(
        'body[data-mscreen="account"] .profile-panel > .display {', 1
    )[1].split("}", 1)[0]
    assert "font-size: 22px" in phone_profile

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
    assert "height: 48px" in today
    signed_cal = css.split("/* Signed-in desktop Calendar", 1)[1].split(
        "/* Signed-in desktop Profile", 1
    )[0]
    assert "grid-template-columns: minmax(0, 1fr) 380px" in signed_cal
    signed = css.split("/* Signed-in desktop Profile", 1)[1].split(
        "/* Signed-in desktop Settings", 1
    )[0]
    assert "position: absolute" not in signed
    assert "left: 50%" not in signed
    assert "minmax(0, 1fr) minmax(0, 1fr)" in signed
    assert "font-size: 28px" in signed
    assert "data-signed-in-profile" in signed
    assert (
        'body.is-authed[data-mscreen="account"]:has([data-signed-in-profile]) '
        ".account-avatar-fallback"
    ) in signed
    assert "border-radius: 11px" in signed
    chip = signed.split(".account-avatar-fallback {", 2)[2].split("}", 1)[0]
    assert "background: var(--ink)" in chip
    assert "border-color: var(--ink)" in chip


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


def test_signed_in_profile_1280_and_phone(tmp_path: Path) -> None:
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
    shot_path = artifact_dir / "signed_in_profile_screen10_1280.png"
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
              const panel = document.querySelector('[data-signed-in-profile]');
              const nav = document.querySelector('.PrimaryTabs--top');
              const links = nav ? [...nav.querySelectorAll('.nav-link')] : [];
              const profile = links.find(
                (el) => (el.textContent || '').trim() === 'Profile'
              );
              const playground = links.find(
                (el) => (el.textContent || '').trim() === 'Playground'
              );
              const identity = document.querySelector('[data-profile-identity]');
              const account = document.querySelector('[data-profile-account]');
              const sub = document.querySelector('[data-profile-subscription]');
              const cta = sub && sub.querySelector('a.pg-btn');
              const report = account && account.querySelector('[data-report-open]');
              const signout = account && account.querySelector('[data-open-signout]');
              const devices = account && account.querySelector(
                'a[href="/profile/security/devices"]'
              );
              const prefs = account && account.querySelector('a[href="/settings"]');
              const identityBox = identity && identity.getBoundingClientRect();
              const accountBox = account && account.getBoundingClientRect();
              const subBox = sub && sub.getBoundingClientRect();
              const reportCs = report ? getComputedStyle(report) : null;
              const signoutCs = signout ? getComputedStyle(signout) : null;
              const heading = panel && panel.querySelector(':scope > .display');
              const legal = [...(panel ? panel.querySelectorAll('.section-title') : [])].find(
                (el) => (el.textContent || '').trim() === 'Legal'
              );
              const chip = document.querySelector(
                '.account-menu-btn .account-avatar-fallback, .account-menu-btn .account-avatar'
              );
              const chipCs = chip ? getComputedStyle(chip) : null;
              const chipName = document.querySelector('.account-menu-btn-name');
              const chipStatus = document.querySelector('.account-menu-btn-status');
              return {
                present: Boolean(panel),
                profileActive: Boolean(
                  profile && (
                    profile.classList.contains('is-active') ||
                    profile.getAttribute('aria-current') === 'page'
                  )
                ),
                playgroundHref: playground && playground.getAttribute('href'),
                name: identity && (identity.innerText || ''),
                meta: identity && (identity.querySelector('.muted') || {}).textContent,
                ctaText: cta && (cta.textContent || '').replace(/\\s+/g, ' ').trim(),
                ctaHref: cta && cta.getAttribute('href'),
                subTitle: sub && (sub.querySelector('h2') || {}).textContent,
                subBody: sub && (sub.querySelector('.pg-lede') || {}).textContent,
                twoCol: Boolean(
                  identityBox && subBox && subBox.left > identityBox.right - 8
                ),
                accountBelowIdentity: Boolean(
                  identityBox && accountBox && accountBox.top > identityBox.bottom - 8
                ),
                reportDisplay: reportCs && reportCs.display,
                signoutDisplay: signoutCs && signoutCs.display,
                devicesHref: devices && devices.getAttribute('href'),
                prefsHref: prefs && prefs.getAttribute('href'),
                headingSize: heading ? getComputedStyle(heading).fontSize : null,
                signoutColor: signoutCs && signoutCs.color,
                legalDisplay: legal ? getComputedStyle(legal).display : null,
                chipBg: chipCs && chipCs.backgroundColor,
                chipColor: chipCs && chipCs.color,
                chipRadius: chipCs && chipCs.borderRadius,
                chipW: chip ? chip.getBoundingClientRect().width : null,
                chipName: chipName && (chipName.textContent || '').trim(),
                chipStatusDisplay: chipStatus ? getComputedStyle(chipStatus).display : "none",
                mockFree: /Free account · Constitution learning included/.test(
                  panel ? panel.innerText : ''
                ),
                mockPlan: /No plan yet|See plans/.test(panel ? panel.innerText : ''),
                mockDevices: /2 of 3/.test(account ? account.innerText : ''),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator('[data-profile-account] a[href="/profile/security/devices"]').click()
        page.wait_for_url("**/profile/security/devices**", timeout=8000)
        devices_path = page.evaluate("() => location.pathname")

        page.goto(f"{origin}/profile", wait_until="networkidle")
        page.locator('[data-profile-account] a[href="/settings"]').click()
        page.wait_for_url("**/settings**", timeout=8000)
        settings_path = page.evaluate("() => location.pathname")

        page.goto(f"{origin}/profile", wait_until="networkidle")
        page.locator('[data-profile-subscription] a.pg-btn').click()
        page.wait_for_url("**/billing/subscriptions**", timeout=8000)
        billing_path = page.evaluate("() => location.pathname")

        page.goto(f"{origin}/profile", wait_until="networkidle")
        page.locator('[data-profile-account] [data-report-open]').click()
        report_open = page.evaluate(
            """() => {
              const overlay = document.querySelector('[data-report-overlay]');
              return Boolean(overlay && !overlay.hasAttribute('hidden'));
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
        page.locator('.PrimaryTabs--top .nav-link', has_text="Playground").click()
        page.wait_for_url("**/playground**", timeout=8000)
        playground_html = page.content()
        playground_path = page.evaluate("() => location.pathname")

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/profile", wait_until="networkidle")
        phone_geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-signed-in-profile]');
              const grid = panel && panel.querySelector('.pg-profile-grid');
              const identity = document.querySelector('[data-profile-identity]');
              const sub = document.querySelector('[data-profile-subscription]');
              const report = document.querySelector(
                '[data-profile-account] [data-report-open]'
              );
              const deskSignout = document.querySelector(
                '[data-profile-account] [data-open-signout]'
              );
              const identityBox = identity && identity.getBoundingClientRect();
              const subBox = sub && sub.getBoundingClientRect();
              return {
                present: Boolean(panel),
                gridDisplay: grid ? getComputedStyle(grid).display : null,
                stacked: Boolean(
                  identityBox && subBox && subBox.top > identityBox.bottom - 8
                ),
                reportDisplay: report ? getComputedStyle(report).display : null,
                deskSignoutDisplay: deskSignout
                  ? getComputedStyle(deskSignout).display
                  : null,
              };
            }"""
        )
        browser.close()

    assert geo["present"] is True
    assert geo["profileActive"] is True
    assert geo["playgroundHref"] == "/playground"
    assert "Sanjay" in (geo["name"] or "")
    assert "Signed in with Google" in (geo["meta"] or "")
    assert geo["ctaText"] == "Subscribe"
    assert geo["ctaHref"] == PLAYGROUND_BILLING_PATH
    assert geo["subTitle"] == "Playground"
    assert "Subscribe to add Bare Acts" in (geo["subBody"] or "")
    assert geo["twoCol"] is True
    assert geo["accountBelowIdentity"] is True
    assert geo["reportDisplay"] == "flex"
    assert geo["signoutDisplay"] == "flex"
    assert geo["devicesHref"] == "/profile/security/devices"
    assert geo["prefsHref"] == "/settings"
    assert geo["headingSize"] == "28px"
    assert "180" in (geo["signoutColor"] or "") or "b42318" in (geo["signoutColor"] or "").lower()
    assert geo["legalDisplay"] == "none"
    assert geo["chipW"] == pytest.approx(36, abs=2)
    assert geo["chipRadius"] == "11px"
    assert "20, 20, 20" in (geo["chipBg"] or "") or "rgb(20, 20, 20)" in (geo["chipBg"] or "")
    assert geo["chipName"] == "Sanjay"
    assert geo["chipStatusDisplay"] == "none"
    assert geo["mockFree"] is False
    assert geo["mockPlan"] is False
    assert geo["mockDevices"] is False
    assert devices_path.rstrip("/") == "/profile/security/devices"
    assert settings_path.rstrip("/") == "/settings"
    assert billing_path.rstrip("/") == "/billing/subscriptions"
    assert report_open is True
    assert signout_open is True
    assert logout_action == "/logout"
    assert playground_path.rstrip("/") == "/playground"
    assert 'data-playground-gate="not_subscribed"' in playground_html
    assert phone_geo["present"] is True
    assert phone_geo["gridDisplay"] != "grid"
    assert phone_geo["stacked"] is True
    assert phone_geo["reportDisplay"] == "none"
    assert phone_geo["deskSignoutDisplay"] == "none"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
