"""Phone Guest Settings Screen 07 (CTA map guest/07-screen, 390x844).

Authorized: ChatGPT. Guest GET /settings phone composition only. Desktop
1280, signedIn/Plus/Expired/Halted Settings stay unchanged. Guest 04/05
remain parked. Both Sign in controls and Report are inert type=button.
Appearance and Motion reuse the existing client preference mechanism.
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
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
APP_JS = ROOT / "src/constitution_memorizer/web/static/app.js"
USER = UUID("11111111-1111-4111-8111-111111111111")

GUEST_SETTINGS_NAME = "Guest"
GUEST_SETTINGS_META = "Guest · Reading only"
GUEST_SETTINGS_LEDE = (
    "Appearance, your learning plan, and your revision calendar."
)
GUEST_SETTINGS_LADDER = "Bare Act text verbatim · Day 1 · 3 · 7 · 15 · 30 · 60"
LEGAL_HREFS = ("/terms", "/privacy", "/grievance")
HIDDEN = (
    "Self-paced",
    "Auto Plan",
    "Daily target",
    "Save learning plan",
    "Connect Google Calendar",
    "Sign out",
    "Devices",
    "data-text-size-step",
    'data-settings-group="study"',
    'data-settings-group="calendar"',
    "data-report-open",
    'data-report-section="Settings"',
    "Subscribe",
    "View plans",
    "Manage subscription",
    "Resume Playground",
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


def _guest_app(tmp_path: Path):
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
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


def _guest_client(tmp_path: Path) -> TestClient:
    return TestClient(_guest_app(tmp_path))


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
) -> None:
    client.app.state.subscriptions.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        billing_period_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 10, 15, tzinfo=timezone.utc),
        is_current=True,
    )


def _phone(html: str) -> str:
    return html.split('data-phone-settings="guest"', 1)[1].split("</section>", 1)[0]


def _identity(src: str) -> str:
    return src.split("data-guest-settings-identity", 1)[1].split("</article>", 1)[0]


def _facts(client: TestClient) -> dict:
    history = tuple(
        sorted(
            (row.id, row.status, row.tier, row.is_current)
            for row in client.app.state.subscriptions.list_subscription_history(USER)
        )
    )
    roster = getattr(client.app.state, "roster", None)
    overlay = getattr(client.app.state, "playground", None)
    theme = client.app.state.engine.repo.get_setting(LOCAL_USER_ID, "theme")
    return {
        "session": client.cookies.get(SESSION_COOKIE_NAME),
        "subscription": client.app.state.subscriptions.get_current_subscription(USER),
        "history": history,
        "active": tuple(
            sorted(i.law_id for i in roster.active_roster_items(USER))
        )
        if roster is not None
        else (),
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        )
        if overlay is not None
        else (),
        "theme": theme,
        "google_users": tuple(
            sorted(getattr(client.app.state.auth_provider, "google_users", {}))
        ),
        "phone_users": tuple(
            sorted(getattr(client.app.state.auth_provider, "phone_users", {}))
        ),
    }


def _watch_provider(client: TestClient) -> list[str]:
    calls: list[str] = []
    svc = getattr(client.app.state, "subscription_service", None)
    if svc is None:
        return calls
    for name in (
        "start_subscription",
        "complete_checkout",
        "cancel_at_cycle_end",
        "change_plan",
        "fetch_provider_subscription",
        "fetch_provider_payment",
        "reconcile_current",
    ):
        orig = getattr(svc, name, None)
        if orig is None:
            continue

        def wrapped(*args, _orig=orig, _name=name, **kwargs):
            calls.append(_name)
            return _orig(*args, **kwargs)

        setattr(svc, name, wrapped)
    return calls


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


def test_phone_guest_settings_copy_and_controls(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    before = _facts(client)
    calls = _watch_provider(client)
    page = client.get("/settings")
    assert page.status_code == 200
    html = unescape(page.text)
    assert 'data-phone-settings="guest"' in html
    assert 'data-mscreen="settings"' in html
    assert "class=\"is-guest\"" in html or " is-guest" in html
    phone = _phone(html)
    assert ">Settings<" in phone
    assert GUEST_SETTINGS_NAME in phone
    assert GUEST_SETTINGS_META in phone
    assert GUEST_SETTINGS_LEDE in phone
    assert "Appearance" in phone
    assert 'data-theme-set="auto"' in phone
    assert 'data-theme-set="light"' in phone
    assert 'data-theme-set="dark"' in phone
    assert "data-motion-toggle" in phone
    assert "Transitions between cards and sessions" in phone
    assert GUEST_SETTINGS_LADDER in phone
    for href in LEGAL_HREFS:
        assert f'href="{href}"' in phone
    assert 'href="/dashboard"' in phone
    assert "← Today" in phone or "&larr; Today" in phone
    assert 'data-guest-settings-identity-signin' in phone
    assert "data-guest-settings-signin" in phone
    assert "data-guest-settings-report" in phone
    assert phone.count('type="button"') >= 3
    assert "/login" not in phone
    assert "<form" not in phone
    assert "data-guest-profile-phone-tabs" not in html
    assert "mobile-tabbar is-guest" not in html
    assert "data-guest-pg-phone-tabs" not in html
    assert "data-guest-bareact-phone-tabs" not in html
    for phrase in HIDDEN:
        assert phrase not in phone, phrase
    assert _facts(client) == before
    assert calls == []


def test_phone_guest_settings_identity_signin_is_handlerless() -> None:
    src = SETTINGS.read_text(encoding="utf-8")
    identity = _identity(src)
    assert 'type="button"' in identity
    assert "data-guest-settings-identity-signin" in identity
    assert ">Sign in<" in identity
    assert "href=" not in identity
    assert "<form" not in identity
    assert "/login" not in identity
    assert "data-report-open" not in identity


def test_phone_guest_settings_account_signin_is_handlerless() -> None:
    src = SETTINGS.read_text(encoding="utf-8")
    account = src.split('data-guest-settings-signin', 1)[1].split("</button>", 1)[0]
    assert 'type="button"' in src.split("data-guest-settings-signin", 1)[0][-80:]
    assert ">Sign in<" in account or "Sign in" in account
    assert "href=" not in account
    assert "<form" not in account
    assert "/login" not in account


def test_phone_guest_settings_report_is_handlerless() -> None:
    src = SETTINGS.read_text(encoding="utf-8")
    guest_report = src.split("data-guest-settings-report", 1)[1].split("</button>", 1)[0]
    assert "Report an issue" in guest_report
    assert "href=" not in guest_report
    assert "mailto:" not in guest_report
    assert "data-report-open" not in guest_report
    assert 'data-report-section="Settings"' not in guest_report
    signed = src.split('data-report-open data-report-section="Settings"', 1)[1]
    assert "Report an issue" in signed.split("</button>", 1)[0]


def test_phone_guest_settings_appearance_and_motion_reuse_existing() -> None:
    settings = SETTINGS.read_text(encoding="utf-8")
    app_js = APP_JS.read_text(encoding="utf-8")
    assert 'data-theme-set="auto"' in settings
    assert 'data-theme-set="light"' in settings
    assert 'data-theme-set="dark"' in settings
    assert "data-motion-toggle" in settings
    assert 'const KEY = "cm-theme"' in app_js
    assert 'const MOTION_KEY = "cm-motion"' in app_js
    assert "function initThemeToggle()" in app_js
    assert 'fetch("/api/theme"' in app_js
    assert 'document.querySelectorAll("[data-theme-set]")' in app_js
    assert 'document.querySelectorAll("[data-motion-toggle]")' in app_js
    assert "guest-theme" not in settings
    assert "guest-motion" not in settings
    assert "cm-guest-theme" not in app_js
    html = BASE.read_text(encoding="utf-8")
    assert 'data-theme-preference="{{ theme_preference|default(\'auto\') }}"' in html


def test_phone_guest_settings_legal_hrefs_are_existing_routes(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    phone = _phone(unescape(client.get("/settings").text))
    note = phone.split("settings-verbatim", 1)[1]
    for href in LEGAL_HREFS:
        assert f'href="{href}"' in note
        assert client.get(href).status_code == 200
    assert "/open-source" not in note
    assert "Open-source" not in note


def test_phone_guest_settings_today_goes_to_dashboard(tmp_path: Path) -> None:
    html = unescape(_guest_client(tmp_path).get("/settings").text)
    phone = _phone(html)
    topbar = phone.split('class="mobile-topbar"', 1)[1].split("</div>", 1)[0]
    assert 'href="/dashboard"' in topbar
    assert "Today" in topbar
    assert ">Home<" not in topbar
    assert 'href="/"' not in topbar.replace('href="/dashboard"', "")


def test_phone_guest_settings_has_no_five_tab_bar() -> None:
    base = BASE.read_text(encoding="utf-8")
    assert "guest_settings" in base
    chunk = base.split("{% elif guest_settings %}", 1)[1].split("{% elif", 1)[0]
    assert "mobile-tabbar" not in chunk
    assert "data-guest-profile-phone-tabs" not in chunk


def test_phone_guest_settings_css_is_breakpoint_scoped() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    phone_block = css.split("Guest phone Settings (CTA map guest/07-screen)", 1)[1].split(
        "/* Plus desktop Playground home", 1
    )[0]
    assert "@media (max-width: 560px)" in phone_block
    assert '[data-phone-settings="guest"]' in phone_block
    assert "settings-account-signin" in phone_block
    assert "var(--ink)" in phone_block
    assert "var(--on-accent)" in phone_block
    assert "@media (min-width: 561px)" not in phone_block
    assert "playground.css?v=pg48" in BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg31" not in BASE.read_text(encoding="utf-8")


def test_signed_in_plus_expired_halted_settings_stay_separate(
    tmp_path: Path,
) -> None:
    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/settings").text
    assert 'data-phone-settings="guest"' not in free_html
    assert "data-guest-settings-signin" not in free_html
    assert "data-guest-settings-report" not in free_html
    assert "data-signed-in-settings" in free_html
    assert 'data-report-open data-report-section="Settings"' in free_html
    assert 'data-settings-group="study"' in free_html
    assert "Sign out" in free_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get("/settings").text
    assert 'data-phone-settings="guest"' not in plus_html
    assert 'data-plus-settings="desktop"' in plus_html
    assert "data-signed-in-settings" in plus_html
    assert 'data-report-section="Settings"' in plus_html

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(expired)
    stored = expired.app.state.subscriptions.get_current_subscription(USER)
    expired.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        status="expired",
        billing_period_start=datetime(2026, 8, 16, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )
    expired_html = expired.get("/settings").text
    assert 'data-phone-settings="guest"' not in expired_html
    assert 'data-expired-settings="desktop"' in expired_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/settings").text
    assert 'data-phone-settings="guest"' not in halted_html
    assert 'data-halted-settings="desktop"' in halted_html


def test_phone_guest_settings_gets_are_mutation_free(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    before = _facts(client)
    calls = _watch_provider(client)
    assert before["session"] is None
    assert before["subscription"] is None
    assert before["google_users"] == ()
    assert before["phone_users"] == ()
    for _ in range(3):
        page = client.get("/settings")
        assert page.status_code == 200
        assert _facts(client) == before
    assert calls == []
    assert client.get("/dashboard").status_code == 200
    assert _facts(client) == before


def test_desktop_guest_settings_keeps_header_auth(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/settings").text
    header = html.split("<header", 1)[1].split("</header>", 1)[0]
    assert 'href="/login"' in header
    assert "nav-signin" in header
    assert 'data-phone-settings="guest"' in html
    assert 'data-theme-set="auto"' in html
    phone = _phone(html)
    assert "/login" not in phone


def test_phone_guest_settings_screen07_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_guest_settings_screen07_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        page = browser.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        page.emulate_media(color_scheme="light")
        requests: list[str] = []
        page.on("request", lambda req: requests.append(f"{req.method} {req.url}"))
        page.goto(f"{origin}/settings", wait_until="networkidle")
        geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-phone-settings="guest"]');
              const header = document.querySelector('.site-header');
              const tabs = document.querySelector('.mobile-tabbar');
              const guestBar = document.querySelector('.mobile-tabbar.is-guest');
              const identity = panel && panel.querySelector('[data-guest-settings-identity]');
              const identSignin = panel && panel.querySelector('[data-guest-settings-identity-signin]');
              const accountSignin = panel && panel.querySelector('[data-guest-settings-signin]');
              const report = panel && panel.querySelector('[data-guest-settings-report]');
              const back = panel && panel.querySelector('.mobile-back');
              const autoBtn = panel && panel.querySelector('[data-theme-set="auto"]');
              const lightBtn = panel && panel.querySelector('[data-theme-set="light"]');
              const darkBtn = panel && panel.querySelector('[data-theme-set="dark"]');
              const motion = panel && panel.querySelector('[data-motion-toggle]');
              const account = panel && panel.querySelector('[data-settings-group="account"]');
              const study = panel && panel.querySelector('[data-settings-group="study"]');
              const calendar = panel && panel.querySelector('[data-settings-group="calendar"]');
              const legal = [...(panel ? panel.querySelectorAll('.settings-note a') : [])];
              return {
                panelDisplay: panel ? getComputedStyle(panel).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                guestBarDisplay: guestBar ? getComputedStyle(guestBar).display : null,
                identityDisplay: identity ? getComputedStyle(identity).display : null,
                accountDisplay: account ? getComputedStyle(account).display : null,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                title: panel && panel.querySelector('h1').textContent.trim(),
                name: identity && identity.querySelector('.settings-account-name').textContent.trim(),
                meta: identity && identity.querySelector('.settings-account-status').textContent.trim(),
                lede: panel && panel.querySelector('.lede').textContent.trim(),
                ledeDisplay: panel && getComputedStyle(panel.querySelector('.lede')).display,
                backText: back && back.textContent.replace(/\\s+/g, ' ').trim(),
                backHref: back && back.getAttribute('href'),
                identSignin: {
                  tag: identSignin && identSignin.tagName,
                  type: identSignin && identSignin.getAttribute('type'),
                  href: identSignin && identSignin.getAttribute('href'),
                  text: identSignin && identSignin.textContent.trim(),
                },
                accountSignin: {
                  tag: accountSignin && accountSignin.tagName,
                  type: accountSignin && accountSignin.getAttribute('type'),
                  href: accountSignin && accountSignin.getAttribute('href'),
                  text: accountSignin && accountSignin.querySelector('.settings-row-label').textContent.trim(),
                },
                report: {
                  tag: report && report.tagName,
                  type: report && report.getAttribute('type'),
                  href: report && report.getAttribute('href'),
                  text: report && report.querySelector('.settings-row-label').textContent.trim(),
                  open: report && report.hasAttribute('data-report-open'),
                },
                autoActive: autoBtn && autoBtn.classList.contains('is-active'),
                lightActive: lightBtn && lightBtn.classList.contains('is-active'),
                darkActive: darkBtn && darkBtn.classList.contains('is-active'),
                motionChecked: motion && motion.getAttribute('aria-checked'),
                motionDisplay: motion ? getComputedStyle(motion).display : null,
                study: Boolean(study),
                calendar: Boolean(calendar),
                legalHrefs: legal.map((el) => el.getAttribute('href')),
                legalLabels: legal.map((el) => el.textContent.trim()),
                signout: panel && panel.innerText.includes('Sign out'),
                selfPaced: panel && panel.innerText.includes('Self-paced'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        n_before = len(requests)
        page.locator("[data-guest-settings-identity-signin]").click()
        page.wait_for_timeout(250)
        after_ident = page.evaluate("() => location.pathname")
        page.locator("[data-guest-settings-signin]").click()
        page.wait_for_timeout(250)
        after_account = page.evaluate("() => location.pathname")
        page.locator("[data-guest-settings-report]").click()
        page.wait_for_timeout(250)
        after_report = page.evaluate("() => location.pathname")
        extra = requests[n_before:]
        browser.close()

    assert geo["panelDisplay"] != "none"
    assert geo["headerDisplay"] == "none"
    assert geo["tabsDisplay"] in (None, "none")
    assert geo["guestBarDisplay"] is None
    assert geo["identityDisplay"] != "none"
    assert geo["accountDisplay"] != "none"
    assert geo["overflow"] is False
    assert geo["title"] == "Settings"
    assert geo["name"] == GUEST_SETTINGS_NAME
    assert geo["meta"] == GUEST_SETTINGS_META
    assert geo["lede"] == GUEST_SETTINGS_LEDE
    assert geo["ledeDisplay"] != "none"
    assert geo["backText"] == "← Today"
    assert geo["backHref"] == "/dashboard"
    assert geo["identSignin"]["tag"] == "BUTTON"
    assert geo["identSignin"]["type"] == "button"
    assert geo["identSignin"]["href"] is None
    assert geo["identSignin"]["text"] == "Sign in"
    assert geo["accountSignin"]["tag"] == "BUTTON"
    assert geo["accountSignin"]["type"] == "button"
    assert geo["accountSignin"]["href"] is None
    assert geo["accountSignin"]["text"] == "Sign in"
    assert geo["report"]["tag"] == "BUTTON"
    assert geo["report"]["type"] == "button"
    assert geo["report"]["href"] is None
    assert geo["report"]["text"] == "Report an issue"
    assert geo["report"]["open"] is False
    assert geo["autoActive"] is True
    assert geo["lightActive"] is False
    assert geo["darkActive"] is False
    assert geo["motionChecked"] == "true"
    assert geo["motionDisplay"] != "none"
    assert geo["study"] is False
    assert geo["calendar"] is False
    assert geo["legalHrefs"] == list(LEGAL_HREFS)
    assert geo["legalLabels"] == [
        "Terms & Conditions",
        "Privacy Policy",
        "Grievance Redressal",
    ]
    assert geo["signout"] is False
    assert geo["selfPaced"] is False
    assert after_ident == "/settings"
    assert after_account == "/settings"
    assert after_report == "/settings"
    assert not any("/login" in item for item in extra)
    assert not any(item.startswith("POST ") for item in extra)
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_guest_settings_prefs_stay_browser_local(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        page = context.new_page()
        page.emulate_media(color_scheme="light")
        page.goto(f"{origin}/settings", wait_until="networkidle")
        page.locator('[data-theme-set="light"]').click()
        page.wait_for_timeout(250)
        page.locator("[data-motion-toggle]").click()
        page.wait_for_timeout(250)
        stored = page.evaluate(
            """() => ({
              theme: localStorage.getItem('cm-theme'),
              motion: localStorage.getItem('cm-motion'),
              path: location.pathname,
              cookies: document.cookie,
            })"""
        )
        cookies = context.cookies()
        browser.close()

    assert stored["theme"] == "light"
    assert stored["motion"] == "off"
    assert stored["path"] == "/settings"
    assert SESSION_COOKIE_NAME not in stored["cookies"]
    assert not any(cookie["name"] == SESSION_COOKIE_NAME for cookie in cookies)
    client = TestClient(app)
    facts = _facts(client)
    assert facts["session"] is None
    assert facts["subscription"] is None
    assert facts["history"] == ()
    assert facts["google_users"] == ()
    assert facts["phone_users"] == ()


def test_phone_guest_settings_screen07_desktop_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_guest_settings_screen07_desktop_regression_1280.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        page = browser.new_page(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
        page.emulate_media(color_scheme="light")
        page.goto(f"{origin}/settings", wait_until="networkidle")
        geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-phone-settings="guest"]');
              const identity = document.querySelector('[data-guest-settings-identity]');
              const account = document.querySelector('[data-settings-group="account"]');
              const tabs = document.querySelector('.mobile-tabbar');
              const header = document.querySelector('.site-header');
              const topbar = document.querySelector('.mobile-topbar');
              const autoBtn = document.querySelector('[data-theme-set="auto"]');
              const reportOpen = document.querySelector('[data-report-open]');
              const headerSignin = header && header.querySelector('.nav-signin');
              return {
                panelDisplay: panel ? getComputedStyle(panel).display : null,
                identityDisplay: identity ? getComputedStyle(identity).display : null,
                accountDisplay: account ? getComputedStyle(account).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                topbarDisplay: topbar ? getComputedStyle(topbar).display : null,
                title: panel && panel.querySelector('h1').textContent.trim(),
                autoTag: autoBtn && autoBtn.tagName,
                autoAttr: autoBtn && autoBtn.getAttribute('data-theme-set'),
                reportOpen: Boolean(reportOpen),
                headerSigninHref: headerSignin && headerSignin.getAttribute('href'),
                headerSigninTag: headerSignin && headerSignin.tagName,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["panelDisplay"] != "none"
    assert geo["identityDisplay"] == "none"
    assert geo["accountDisplay"] == "none"
    assert geo["tabsDisplay"] in (None, "none")
    assert geo["headerDisplay"] != "none"
    assert geo["topbarDisplay"] == "none"
    assert geo["title"] == "Settings"
    assert geo["autoTag"] == "BUTTON"
    assert geo["autoAttr"] == "auto"
    assert geo["reportOpen"] is False
    assert geo["headerSigninTag"] == "A"
    assert geo["headerSigninHref"] == "/login"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
