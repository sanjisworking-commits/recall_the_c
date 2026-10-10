"""Phone signed-in Free Settings Screen 07 (CTA map signedIn/07-screen).

Authorized: ChatGPT. Authenticated Free GET /settings at 390x844. Desktop
signed-in Settings Screen 11 is the functional contract. Live identity,
plan eligibility, and calendar state win over the map. Guest phone 07 is
chrome only. Tabbar stays hidden. No S2-1.
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
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
USER = UUID("11111111-1111-4111-8111-111111111111")
TOKEN_KEY = Fernet.generate_key().decode()
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
)
MOCK_SCREEN_COPY = (
    "Free account",
    "No plan yet",
    "See plans",
)
LEGAL_HREFS = ("/terms", "/privacy", "/grievance")
FREE_SEL = (
    "[data-signed-in-settings]:not([data-plus-settings])"
    ":not([data-expired-settings]):not([data-halted-settings])"
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
        APP_BASE_URL="https://recall-the-c.in",
        MULTIUSER_ENABLED="true",
        AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true",
        SESSION_SECRET="test-secret",
        SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon",
        DATABASE_URL="",
        COOKIE_SECURE="false",
        GCAL_CLIENT_ID="gcal-cid",
        GCAL_CLIENT_SECRET="gcal-secret",
        GCAL_TOKEN_KEY=TOKEN_KEY,
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
        study_materials_dir=tmp_path / "study-materials",
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


def _free_client(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    return client


def _panel(html: str) -> str:
    return html.split("data-signed-in-settings", 1)[1].split("</section>", 1)[0]


def _facts(client: TestClient) -> dict:
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    svc = getattr(client.app.state, "device_service", None)
    device_ids = ()
    if svc is not None:
        device_ids = tuple(sorted(str(row.id) for row in svc.list_devices(USER)))
    return {
        "subscription": None
        if stored is None
        else (stored.id, stored.status, stored.tier, stored.is_current),
        "roster": tuple(sorted(i.law_id for i in roster.active_roster_items(USER))),
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        ),
        "devices": device_ids,
    }


def _watch_ensure(client: TestClient) -> list[str]:
    calls: list[str] = []
    svc = getattr(client.app.state, "device_service", None)
    if svc is None:
        return calls
    orig = svc.ensure_current_device

    def wrapped(*args, **kwargs):
        calls.append("ensure_current_device")
        return orig(*args, **kwargs)

    svc.ensure_current_device = wrapped  # type: ignore[method-assign]
    return calls


def test_phone_free_settings_is_live_screen11_contract(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    before = _facts(client)
    ensure_calls = _watch_ensure(client)
    page = client.get("/settings")
    assert page.status_code == 200
    assert _facts(client) == before
    assert ensure_calls == []
    html = unescape(page.text)
    assert "data-signed-in-settings" in html
    assert "data-plus-settings" not in html
    assert "data-expired-settings" not in html
    assert "data-halted-settings" not in html
    assert 'data-mscreen="settings"' in html
    assert 'data-phone-settings="guest"' not in html
    panel = _panel(html)
    assert "Sanjay" in panel
    assert "Signed in with Google" in panel
    assert "Free account" not in panel
    ident = panel.split("settings-account-row", 1)[1][:400]
    assert 'href="/profile"' in ident
    assert "Appearance, your learning plan, and your revision calendar." in panel
    assert 'data-settings-group="study"' in panel
    assert 'data-settings-group="calendar"' in panel
    assert 'data-settings-group="app"' in panel
    assert 'data-settings-group="account"' in panel
    assert 'action="/settings/learning-plan"' in panel
    assert "data-plan-autosubmit" in panel
    assert "Self-paced" in panel
    assert "Auto Plan" in panel
    assert 'id="pace-self-paced"' in panel
    assert 'id="pace-auto"' in panel
    assert "data-gcal-toggle" in panel
    assert 'data-gcal-on="/calendar/google/connect"' in panel
    assert 'data-gcal-off-form="gcal-disconnect-form"' in panel
    assert 'href="/calendar/google/connect"' in panel
    src = SETTINGS.read_text(encoding="utf-8")
    assert 'action="/calendar/google/disconnect"' in src
    assert 'action="/calendar/google/preferences"' in src
    assert "Last synced" not in panel
    assert 'data-theme-set="auto"' in panel
    assert 'data-theme-set="light"' in panel
    assert 'data-theme-set="dark"' in panel
    assert "data-text-size-step" in panel
    assert "data-motion-toggle" in panel
    assert 'data-report-open data-report-section="Settings"' in panel
    assert 'action="/logout"' in panel
    logout = panel.split('action="/logout"', 1)[1].split("</form>", 1)[0]
    assert "confirm(" not in logout
    assert "data-open-signout" not in panel
    assert "id=\"signout-modal\"" not in html or "settings-signout-form" in panel
    for href in LEGAL_HREFS:
        assert f'href="{href}"' in panel
        assert client.get(href).status_code == 200
    assert "Bare Act text verbatim · Day 1 · 3 · 7 · 15 · 30 · 60" in panel
    for phrase in MOCK_SCREEN_COPY:
        assert phrase not in html, phrase
    assert "/pricing" not in html
    assert "Guest · Reading only" not in panel
    assert "data-guest-settings-signin" not in panel
    assert "data-guest-settings-report" not in panel
    tabs = html.split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 1
    )
    if len(tabs) > 1:
        bar = tabs[1].split("</nav>", 1)[0]
        for label_text, href in TAB_HREFS:
            assert f'href="{href}"' in bar
            assert label_text in bar
    csrf = client.cookies.get(CSRF_COOKIE_NAME) or ""
    saved = client.post(
        "/settings/learning-plan",
        data={"csrf_token": csrf, "mode": "self_paced"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert saved.headers["location"].startswith("/settings")
    after_save = unescape(client.get("/settings?saved=1").text)
    assert "Settings saved." in after_save
    connect = client.get("/calendar/google/connect", follow_redirects=False)
    assert connect.status_code == 303
    assert "accounts.google.com" in connect.headers["location"]
    gate = client.get("/playground", follow_redirects=False)
    assert gate.status_code == 200
    assert 'data-playground-gate="not_subscribed"' in gate.text
    profile = client.get("/profile", follow_redirects=False)
    assert profile.status_code == 200
    assert 'href="/settings"' in profile.text
    today = client.get("/dashboard", follow_redirects=False)
    assert today.status_code == 200
    assert _facts(client) == before
    assert ensure_calls == []


def test_phone_free_settings_css_is_breakpoint_scoped() -> None:
    mobile = MOBILE.read_text(encoding="utf-8")
    generic, _, rest = mobile.partition("is signedIn/07-screen:")
    assert "data-signed-in-settings" not in generic
    phone_block = rest.split("/* R1 — Playground phone shell", 1)[0]
    assert "@media (max-width: 560px)" in phone_block
    assert "@media (min-width: 561px)" not in phone_block
    assert FREE_SEL in phone_block.replace("\n", "").replace(" ", "")
    assert ":not([data-plus-settings])" in phone_block
    assert ":not([data-expired-settings])" in phone_block
    assert ":not([data-halted-settings])" in phone_block
    assert "safe-area-inset-bottom" in phone_block
    assert "overflow-x: hidden" in phone_block
    assert ".mobile-tabbar" in phone_block
    assert "display: none" in phone_block.split(".mobile-tabbar", 1)[1].split("}", 1)[0]
    assert "grid-template-columns: repeat(5, 1fr)" not in phone_block
    assert ".lede" in phone_block
    assert "settings-saved" in phone_block
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", phone_block) is None
    assert "display: contents" not in phone_block
    assert "sun" not in phone_block.lower()
    assert 'data-plus-settings="desktop"] {' not in phone_block
    phone_title = mobile.split(
        'body[data-mscreen="settings"] .settings > .display {', 1
    )[1].split("}", 1)[0]
    assert "font-size: 23px" in phone_title
    desk = STYLES.read_text(encoding="utf-8").split(
        "/* Signed-in desktop Settings", 1
    )[1]
    assert "@media (min-width: 561px)" in desk
    assert "max-width: 720px" in desk
    assert "font-size: 30px" in desk
    assert "playground.css?v=pg45" in BASE.read_text(encoding="utf-8")
    assert "styles.css?v=main86" in BASE.read_text(encoding="utf-8")
    assert "mobile.css?v=mob105" in BASE.read_text(encoding="utf-8")
    assert "mobile.css?v=mob104" not in BASE.read_text(encoding="utf-8")
    src = SETTINGS.read_text(encoding="utf-8")
    for phrase in MOCK_SCREEN_COPY:
        assert phrase not in src, phrase
    assert 'action="/settings/learning-plan"' in src
    assert 'href="/calendar/google/connect"' in src
    assert 'action="/calendar/google/disconnect"' in src
    assert "data-signed-in-pg-gate" in GATE.read_text(encoding="utf-8")
    guest_css = PG_CSS.read_text(encoding="utf-8")
    assert "Guest phone Settings (CTA map guest/07-screen)" in guest_css
    guest_chunk = BASE.read_text(encoding="utf-8").split(
        "{% elif guest_settings %}", 1
    )[1].split("{% elif", 1)[0]
    assert "mobile-tabbar" not in guest_chunk


def test_guest_plus_expired_halted_settings_stay_separate(tmp_path: Path) -> None:
    guest = TestClient(_guest_app(tmp_path / "guest")).get("/settings")
    assert guest.status_code == 200
    guest_html = guest.text
    assert 'data-phone-settings="guest"' in guest_html
    assert "data-signed-in-settings" not in guest_html
    assert "data-guest-settings-signin" in guest_html
    assert "data-guest-settings-report" in guest_html
    assert 'data-settings-group="study"' not in guest_html
    assert 'data-settings-group="calendar"' not in guest_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get("/settings").text
    assert "data-signed-in-settings" in plus_html
    assert 'data-plus-settings="desktop"' in plus_html
    assert "data-expired-settings" not in plus_html
    assert "data-halted-settings" not in plus_html

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
    assert 'data-expired-settings="desktop"' in expired_html
    assert "data-plus-settings" not in expired_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/settings").text
    assert 'data-halted-settings="desktop"' in halted_html
    assert "data-plus-settings" not in halted_html


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


def _cookie(session: str, origin: str) -> list[dict]:
    return [
        {
            "name": SESSION_COOKIE_NAME,
            "value": session,
            "url": origin,
            "httpOnly": True,
            "secure": False,
            "sameSite": "Lax",
        }
    ]


def test_phone_signed_in_settings_screen07_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    before = _facts(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_signed_in_settings_screen07_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        context.add_cookies(_cookie(session, origin))
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
              const header = document.querySelector('.site-header');
              const topbar = panel && panel.querySelector(':scope > .mobile-topbar');
              const back = panel && panel.querySelector('.mobile-back');
              const tabs = document.querySelector('.mobile-tabbar');
              const ident = panel && panel.querySelector('.settings-account-row');
              const lede = panel && panel.querySelector(':scope > .lede');
              const study = panel && panel.querySelector('[data-settings-group="study"]');
              const cal = panel && panel.querySelector('[data-settings-group="calendar"]');
              const app = panel && panel.querySelector('[data-settings-group="app"]');
              const account = panel && panel.querySelector('[data-settings-group="account"]');
              const legal = panel && panel.querySelector(':scope > .section-title');
              const selfPace = study && study.querySelector('#pace-self-paced');
              const autoPace = study && study.querySelector('#pace-auto');
              const selfLabel = study && study.querySelector('label[for="pace-self-paced"]');
              const toggle = cal && cal.querySelector('[data-gcal-toggle]');
              const deskCopy = panel && panel.querySelector('.settings-desk-copy');
              const connectRow = panel && panel.querySelector('.gcal-connect-row');
              const autoBtn = panel && panel.querySelector('[data-theme-set="auto"]');
              const motion = panel && panel.querySelector('[data-motion-toggle]');
              const size = panel && panel.querySelector('[data-text-size-row]');
              const report = account && account.querySelector('[data-report-open]');
              const signoutForm = account && account.querySelector('.settings-signout-form');
              const signoutBtn = signoutForm && signoutForm.querySelector('button[type="submit"]');
              const identBox = ident && ident.getBoundingClientRect();
              const studyBox = study && study.getBoundingClientRect();
              const calBox = cal && cal.getBoundingClientRect();
              const appBox = app && app.getBoundingClientRect();
              const accountBox = account && account.getBoundingClientRect();
              const legalBox = legal && legal.getBoundingClientRect();
              const selfCs = selfLabel ? getComputedStyle(selfLabel) : null;
              const autoCs = autoBtn ? getComputedStyle(autoBtn) : null;
              const focusable = [...(panel ? panel.querySelectorAll(
                'a[href], button:not([disabled]), input:not([disabled]), select, textarea'
              ) : [])].filter((el) => {
                const cs = getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden') return false;
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              });
              const owner = (el) => {
                if (el.closest('.settings-account-row')) return 'identity';
                if (el.closest('[data-settings-group="study"]')) return 'study';
                if (el.closest('[data-settings-group="calendar"]')) return 'calendar';
                if (el.closest('[data-settings-group="app"]')) return 'app';
                if (el.closest('[data-settings-group="account"]')) return 'account';
                return 'other';
              };
              const visual = [
                { name: 'identity', top: identBox && identBox.top },
                { name: 'study', top: studyBox && studyBox.top },
                { name: 'calendar', top: calBox && calBox.top },
                { name: 'app', top: appBox && appBox.top },
                { name: 'account', top: accountBox && accountBox.top },
                { name: 'legal', top: legalBox && legalBox.top },
              ].sort((a, b) => (a.top || 0) - (b.top || 0)).map((row) => row.name);
              const focusBlocks = [];
              for (const el of focusable) {
                const name = owner(el);
                if (name === 'other') continue;
                if (focusBlocks[focusBlocks.length - 1] !== name) focusBlocks.push(name);
              }
              const legalLinks = [...(panel ? panel.querySelectorAll('.settings-note a') : [])];
              return {
                present: Boolean(panel),
                plus: Boolean(document.querySelector('[data-plus-settings]')),
                headerDisplay: header ? getComputedStyle(header).display : null,
                topbarDisplay: topbar ? getComputedStyle(topbar).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                backText: back && (back.textContent || '').replace(/\\s+/g, ' ').trim(),
                backHref: back && back.getAttribute('href'),
                identHref: ident && ident.getAttribute('href'),
                name: ident && (ident.innerText || ''),
                ledeDisplay: lede ? getComputedStyle(lede).display : null,
                ledeText: lede && (lede.textContent || '').trim(),
                selfChecked: Boolean(selfPace && selfPace.checked),
                autoDisabled: Boolean(autoPace && autoPace.disabled),
                selfBg: selfCs && selfCs.backgroundColor,
                selfColor: selfCs && selfCs.color,
                autoThemeBg: autoCs && autoCs.backgroundColor,
                autoThemeColor: autoCs && autoCs.color,
                gcalChecked: toggle && toggle.getAttribute('aria-checked'),
                gcalDisplay: toggle ? getComputedStyle(toggle).display : null,
                deskCopyDisplay: deskCopy ? getComputedStyle(deskCopy).display : null,
                connectRowDisplay: connectRow ? getComputedStyle(connectRow).display : null,
                motionChecked: motion && motion.getAttribute('aria-checked'),
                sizeDisplay: size ? getComputedStyle(size).display : null,
                reportDisplay: report ? getComputedStyle(report).display : null,
                signoutDisplay: signoutBtn ? getComputedStyle(signoutBtn).display : null,
                signoutAction: signoutForm && signoutForm.getAttribute('action'),
                visual,
                focusBlocks,
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                hasFreeAccount: /Free account/.test(panel ? panel.innerText : ''),
                hasSynced: /Last synced/.test(cal ? cal.innerText : ''),
                legalHrefs: legalLinks.map((el) => el.getAttribute('href')),
                headingSize: panel && getComputedStyle(panel.querySelector(':scope > .display')).fontSize,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator('[data-settings-group="account"] [data-report-open]').click()
        report_open = page.evaluate(
            """() => {
              const overlay = document.querySelector('[data-report-overlay]');
              return Boolean(overlay && !overlay.hasAttribute('hidden'));
            }"""
        )
        page.locator("[data-rc-close]").click()

        auto_disabled = page.evaluate(
            """() => {
              const autoPace = document.querySelector('#pace-auto');
              return Boolean(autoPace && autoPace.disabled);
            }"""
        )
        if not auto_disabled:
            page.locator('label[for="pace-auto"]').click()
            page.wait_for_url(re.compile(r".*/settings\?saved=1"), timeout=8000)
        else:
            page.goto(f"{origin}/settings?saved=1", wait_until="networkidle")
        saved_geo = page.evaluate(
            """() => {
              const banner = document.querySelector('.settings-saved');
              return {
                text: banner && (banner.textContent || '').trim(),
                display: banner ? getComputedStyle(banner).display : null,
              };
            }"""
        )

        page.goto(f"{origin}/settings", wait_until="networkidle")
        page.locator(".settings-account-row").click()
        page.wait_for_url("**/profile**", timeout=8000)
        profile_path = page.evaluate("() => location.pathname")
        page.locator('[data-profile-account] a[href="/settings"]').click()
        page.wait_for_url("**/settings**", timeout=8000)
        settings_path = page.evaluate("() => location.pathname")
        page.locator(".mobile-back").click()
        page.wait_for_url("**/dashboard**", timeout=8000)
        today_path = page.evaluate("() => location.pathname")

        page.goto(f"{origin}/settings", wait_until="networkidle")
        page.set_viewport_size({"width": 390, "height": 700})
        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(80)
        short = page.evaluate(
            """() => {
              const account = document.querySelector('[data-settings-group="account"]');
              const report = account && account.querySelector('[data-report-open]');
              const signout = account && account.querySelector('.settings-signout-form button');
              const legal = document.querySelector('.settings-note a[href="/terms"]');
              const ladder = document.querySelector('.settings-verbatim');
              const tabs = document.querySelector('.mobile-tabbar');
              const rb = report && report.getBoundingClientRect();
              const sb = signout && signout.getBoundingClientRect();
              const lb = legal && legal.getBoundingClientRect();
              return {
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                reportReachable: Boolean(report && rb && rb.width > 0 && rb.height > 0),
                signoutReachable: Boolean(signout && sb && sb.width > 0 && sb.height > 0),
                legalReachable: Boolean(legal && lb && lb.width > 0 && lb.height > 0),
                ladderDisplay: ladder ? getComputedStyle(ladder).display : null,
                reportMin: report ? Math.min(
                  report.getBoundingClientRect().height, report.offsetHeight
                ) : 0,
                signoutMin: signout ? Math.min(
                  signout.getBoundingClientRect().height, signout.offsetHeight
                ) : 0,
              };
            }"""
        )
        browser.close()

    assert geo["present"] is True
    assert geo["plus"] is False
    assert geo["headerDisplay"] == "none"
    assert geo["topbarDisplay"] not in {None, "none"}
    assert geo["tabsDisplay"] in {None, "none"}
    assert geo["backText"] == "← Today"
    assert geo["backHref"] == "/dashboard"
    assert geo["identHref"] == "/profile"
    assert "Sanjay" in (geo["name"] or "")
    assert "Signed in with Google" in (geo["name"] or "")
    assert geo["ledeDisplay"] not in {None, "none"}
    assert "Appearance, your learning plan, and your revision calendar." in (
        geo["ledeText"] or ""
    )
    assert geo["selfChecked"] is True
    assert geo["selfBg"] == "rgb(20, 20, 20)"
    assert geo["selfColor"] == "rgb(255, 255, 255)"
    assert geo["autoThemeBg"] == "rgb(20, 20, 20)"
    assert geo["autoThemeColor"] == "rgb(255, 255, 255)"
    assert geo["gcalChecked"] == "false"
    assert geo["gcalDisplay"] not in {None, "none"}
    assert geo["deskCopyDisplay"] == "none"
    assert geo["connectRowDisplay"] == "none"
    assert geo["motionChecked"] == "true"
    assert geo["sizeDisplay"] not in {None, "none"}
    assert geo["reportDisplay"] not in {None, "none"}
    assert geo["signoutDisplay"] not in {None, "none"}
    assert geo["signoutAction"] == "/logout"
    assert geo["visual"] == [
        "identity",
        "study",
        "calendar",
        "app",
        "account",
        "legal",
    ]
    assert geo["focusBlocks"] == [
        "identity",
        "study",
        "calendar",
        "app",
        "account",
    ]
    assert geo["overflow"] is False
    assert geo["hasFreeAccount"] is False
    assert geo["hasSynced"] is False
    assert geo["legalHrefs"] == list(LEGAL_HREFS)
    assert geo["headingSize"] == "26px"
    assert report_open is True
    assert saved_geo["text"] == "Settings saved."
    assert saved_geo["display"] not in {None, "none"}
    assert profile_path.rstrip("/") == "/profile"
    assert settings_path.rstrip("/") == "/settings"
    assert today_path.rstrip("/") == "/dashboard"
    assert short["tabsDisplay"] in {None, "none"}
    assert short["overflow"] is False
    assert short["reportReachable"] is True
    assert short["signoutReachable"] is True
    assert short["legalReachable"] is True
    assert short["ladderDisplay"] not in {None, "none"}
    assert short["reportMin"] >= 44
    assert short["signoutMin"] >= 44
    assert _facts(client) == before
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_signed_in_settings_screen07_desktop_regression_1280(
    tmp_path: Path,
) -> None:
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
    shot_path = artifact_dir / "phone_signed_in_settings_screen07_desktop_regression_1280.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
        context.add_cookies(_cookie(session, origin))
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
              const heading = panel && panel.querySelector(':scope > .display');
              const ident = panel && panel.querySelector('.settings-account-row');
              const study = panel && panel.querySelector('[data-settings-group="study"]');
              const cal = panel && panel.querySelector('[data-settings-group="calendar"]');
              const account = panel && panel.querySelector('[data-settings-group="account"]');
              const toggle = panel && panel.querySelector('[data-gcal-toggle]');
              const connect = cal && cal.querySelector('[data-gcal-connect]');
              const selfPace = study && study.querySelector('#pace-self-paced');
              const selfLabel = study && study.querySelector('label[for="pace-self-paced"]');
              const nav = document.querySelector('.PrimaryTabs--top');
              const active = nav && [...nav.querySelectorAll('.nav-link.is-active')].map(
                (el) => (el.textContent || '').trim()
              );
              const phone = document.querySelector('.mobile-tabbar');
              const selfCs = selfLabel ? getComputedStyle(selfLabel) : null;
              return {
                present: Boolean(panel),
                headingSize: heading ? getComputedStyle(heading).fontSize : null,
                identHref: ident && ident.getAttribute('href'),
                name: ident && (ident.innerText || ''),
                selfChecked: Boolean(selfPace && selfPace.checked),
                selfBg: selfCs && selfCs.backgroundColor,
                connectHref: connect && connect.getAttribute('href'),
                connectText: connect && (connect.textContent || '').replace(/\\s+/g, ' ').trim(),
                connectDisplay: connect ? getComputedStyle(connect).display : null,
                togglePhoneDisplay: toggle ? getComputedStyle(
                  toggle.closest('.settings-phone-only') || toggle
                ).display : null,
                tabsDisplay: phone ? getComputedStyle(phone).display : null,
                hasSettingsPill: (active || []).includes('Settings'),
                hasFreeAccount: /Free account/.test(panel ? panel.innerText : ''),
                hasSynced: /Last synced/.test(cal ? cal.innerText : ''),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["present"] is True
    assert geo["headingSize"] == "30px"
    assert geo["identHref"] == "/profile"
    assert "Sanjay" in (geo["name"] or "")
    assert "Signed in with Google" in (geo["name"] or "")
    assert geo["selfChecked"] is True
    assert geo["selfBg"] == "rgb(20, 20, 20)"
    assert geo["connectHref"] and geo["connectHref"].startswith("/calendar/google/connect")
    assert geo["connectText"] == "Connect Google Calendar"
    assert geo["connectDisplay"] not in {None, "none"}
    assert geo["togglePhoneDisplay"] == "none"
    assert geo["tabsDisplay"] == "none"
    assert geo["hasSettingsPill"] is False
    assert geo["hasFreeAccount"] is False
    assert geo["hasSynced"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
