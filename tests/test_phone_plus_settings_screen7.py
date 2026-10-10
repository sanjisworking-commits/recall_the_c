"""Phone Plus Settings Screen 07 (CTA map plus/07-screen).

Authorized: ChatGPT. Authenticated active Plus GET /settings at 390x844.
Desktop Plus Screen 11 is the functional contract. Live can_use_auto_plan,
live GCal branches, and the live access-summary identity line win over
the map. Free signedIn 07 is layout only. Tabbar stays hidden. No S2-1.
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
from tests.test_roster_m5a import _csrf

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
APP = ROOT / "src/constitution_memorizer/web/app.py"
APP_JS = ROOT / "src/constitution_memorizer/web/static/app.js"
USER = UUID("11111111-1111-4111-8111-111111111111")
TOKEN_KEY = Fernet.generate_key().decode()
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
)
LEGAL_HREFS = ("/terms", "/privacy", "/grievance")
INVENTED = (
    "Recall access · active",
    "Premium",
    "Unlock all",
    "No plan yet",
    "See plans",
    "8/10",
    "renews 1 October",
    "Free account",
    "Subscribe",
    "Change plan",
)
LOCKED_COPY = (
    "Part of unlocking every Article — your saved history is never deleted."
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


def _plus_client(tmp_path: Path, *, gcal: bool = True) -> TestClient:
    client = TestClient(_mu_app(tmp_path, gcal=gcal))
    _sign_in(client)
    _subscribe(client)
    return client


def _panel(html: str) -> str:
    return html.split("data-plus-settings", 1)[1].split("</section>", 1)[0]


def _study(html: str) -> str:
    return html.split('data-settings-group="study"', 1)[1].split(
        'data-settings-group="', 1
    )[0]


def _identity_status(html: str) -> str:
    chunk = html.split("settings-account-status", 1)[1].split("</span>", 1)[0]
    return unescape(chunk.split(">", 1)[-1]).strip()


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


def _plus_css() -> str:
    css = PG_CSS.read_text(encoding="utf-8")
    return css.split("is plus/07-screen:", 1)[1].split("expired/11-screen", 1)[0]


def test_phone_plus_settings_is_live_screen11_contract(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    before = _facts(client)
    ensure_calls = _watch_ensure(client)
    page = client.get("/settings")
    assert page.status_code == 200
    assert _facts(client) == before
    assert ensure_calls == []
    html = unescape(page.text)
    assert 'data-plus-settings="desktop"' in html
    assert "data-signed-in-settings" in html
    assert "data-expired-settings" not in html
    assert "data-halted-settings" not in html
    assert 'data-mscreen="settings"' in html
    assert 'data-phone-settings="guest"' not in html
    panel = _panel(html)
    assert "Sanjay" in panel
    status = _identity_status(html)
    assert status
    assert status != "Recall access · active"
    # Entitlements-off Google seed: live fallback, not a forced product string.
    assert status == "Signed in with Google"
    src = SETTINGS.read_text(encoding="utf-8")
    ident_src = src.split("settings-account-status", 1)[1].split(
        "settings-account-chevron", 1
    )[0]
    assert "{{ access.status_line }}" in ident_src
    assert "Signed in with Google" in ident_src
    assert "Signed in with phone" in ident_src
    ident = panel.split("settings-account-row", 1)[1][:400]
    assert 'href="/profile"' in ident
    assert "Appearance, your learning plan, and your revision calendar." in panel
    assert 'data-settings-group="study"' in panel
    assert 'data-settings-group="calendar"' in panel
    assert 'data-settings-group="app"' in panel
    assert 'data-settings-group="account"' in panel
    study = _study(html)
    assert 'action="/settings/learning-plan"' in panel
    assert "data-plan-autosubmit" in panel
    assert "Self-paced" in study
    assert "Auto Plan" in study
    assert 'id="pace-self-paced"' in study
    assert "checked" in study.split('id="pace-self-paced"', 1)[1].split(">", 1)[0]
    assert "disabled" not in study.split('id="pace-auto"', 1)[1].split(">", 1)[0]
    assert "Steady · 3" in study
    assert "Balanced · 5" in study
    assert "Intensive · 7" in study
    assert "checked" in study.split('id="target-5"', 1)[1].split(">", 1)[0]
    assert LOCKED_COPY not in study
    assert "can_auto_plan|default(false)" in src
    assert "{% if can_auto_plan|default(false) and not is_guest %}" in src
    assert "plus_settings" not in src.split('data-settings-group="study"', 1)[1].split(
        'data-settings-group="calendar"', 1
    )[0]
    assert "data-gcal-toggle" in panel
    assert 'data-gcal-on="/calendar/google/connect"' in panel
    assert 'data-gcal-off-form="gcal-disconnect-form"' in panel
    assert 'href="/calendar/google/connect"' in panel
    assert 'action="/calendar/google/disconnect"' in src
    assert 'action="/calendar/google/preferences"' in src
    assert "gcal.connected" in src
    assert "gcal.connection" in src
    assert "gcal.prefs" in src
    assert "gcal.status_param" in src
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
    assert 'id="signout-modal"' not in html
    assert "settings-signout-form" in panel
    for href in LEGAL_HREFS:
        assert f'href="{href}"' in panel
        assert client.get(href).status_code == 200
    assert "Bare Act text verbatim · Day 1 · 3 · 7 · 15 · 30 · 60" in panel
    for phrase in INVENTED:
        assert phrase not in html, phrase
    assert "/pricing" not in html
    assert "Guest · Reading only" not in panel
    tabs = html.split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 1
    )
    assert len(tabs) > 1
    bar = tabs[1].split("</nav>", 1)[0]
    assert "Settings" not in bar
    for label_text, href in TAB_HREFS:
        assert f'href="{href}"' in bar
        assert label_text in bar
    saved = client.post(
        "/settings/learning-plan",
        data={**_csrf(client), "mode": "auto", "daily_target": "3"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert saved.headers["location"].startswith("/settings")
    after_save = unescape(client.get("/settings?saved=1").text)
    assert "Settings saved." in after_save
    assert "checked" in after_save.split('id="pace-auto"', 1)[1].split(">", 1)[0]
    assert "checked" in after_save.split('id="target-3"', 1)[1].split(">", 1)[0]
    connect = client.get("/calendar/google/connect", follow_redirects=False)
    assert connect.status_code == 303
    assert "accounts.google.com" in connect.headers["location"]
    profile = client.get("/profile", follow_redirects=False)
    assert profile.status_code == 200
    assert 'data-plus-profile="desktop"' in profile.text
    today = client.get("/dashboard", follow_redirects=False)
    assert today.status_code == 200
    assert _facts(client) == before
    assert ensure_calls == []
    assert client.cookies.get(CSRF_COOKIE_NAME)
    logged = client.post(
        "/logout", data=_csrf(client), follow_redirects=False
    )
    assert logged.status_code == 303
    assert "/signed-out" in logged.headers.get("location", "")


def test_phone_plus_settings_calendar_unconfigured_omits_group(
    tmp_path: Path,
) -> None:
    client = _plus_client(tmp_path, gcal=False)
    html = unescape(client.get("/settings").text)
    assert 'data-plus-settings="desktop"' in html
    assert 'data-settings-group="calendar"' not in html
    assert "Last synced" not in html
    assert "data-gcal-toggle" not in html


def test_phone_plus_settings_css_is_breakpoint_scoped() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    assert "is plus/07-screen:" in css
    phone_block = _plus_css()
    assert "@media (max-width: 560px)" in phone_block
    assert "@media (min-width: 561px)" not in phone_block
    assert '[data-plus-settings="desktop"]' in phone_block
    assert "safe-area-inset-bottom" in phone_block
    assert "overflow-x: hidden" in phone_block
    assert ".mobile-tabbar" in phone_block
    tab_rule = phone_block.split(".mobile-tabbar", 1)[1].split("}", 1)[0]
    assert "display: none" in tab_rule
    assert "grid-template-columns: repeat(5, 1fr)" not in phone_block
    assert "position: fixed" not in phone_block
    assert "> .lede" in phone_block
    assert "settings-saved" in phone_block
    assert "font-size: 26px" in phone_block
    assert "var(--ink)" in phone_block
    assert "min-height: 44px" in phone_block
    assert "#0e7569" not in phone_block
    assert "#3a3a38" not in phone_block
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", phone_block) is None
    assert "display: contents" not in phone_block
    assert "data-plus-settings-phone" not in css
    assert "Recall access · active" not in css
    desk = css.split("plus/11-screen", 1)[1].split("is plus/07-screen:", 1)[0]
    assert "@media (min-width: 561px)" in desk
    assert "var(--ink)" in desk
    mobile = MOBILE.read_text(encoding="utf-8")
    generic, _, rest = mobile.partition("is signedIn/07-screen:")
    assert "data-plus-settings" not in generic
    phone_free = rest.split("/* R1 — Playground phone shell", 1)[0]
    assert ":not([data-plus-settings])" in phone_free
    assert 'data-plus-settings="desktop"] {' not in phone_free
    assert "is plus/07-screen:" not in phone_free
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", phone_free) is None
    phone_title = mobile.split(
        'body[data-mscreen="settings"] .settings > .display {', 1
    )[1].split("}", 1)[0]
    assert "font-size: 23px" in phone_title
    phone_desk = mobile.split(
        'body[data-mscreen="settings"] .settings-desk-copy {', 1
    )[1].split("}", 1)[0]
    assert "display: none" in phone_desk
    assert 'body[data-mscreen="settings"] .mobile-tabbar' in mobile
    assert "is plus/07-screen:" not in STYLES.read_text(encoding="utf-8")
    assert "is plus/07-screen:" not in APP.read_text(encoding="utf-8")
    assert "is plus/07-screen:" not in APP_JS.read_text(encoding="utf-8")
    src = SETTINGS.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in src
    assert "data-plus-settings-phone" not in src
    assert "{{ access.status_line }}" in src
    for phrase in INVENTED:
        assert phrase not in src, phrase
    assert 'action="/settings/learning-plan"' in src
    assert 'href="/calendar/google/connect"' in src
    assert 'action="/calendar/google/disconnect"' in src
    assert 'action="/logout"' in src
    assert "data-plan-autosubmit" in src
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg45" in base
    assert "playground.css?v=pg39" not in base
    assert "styles.css?v=main86" in base
    assert "mobile.css?v=mob105" in base
    assert "data-plus-settings-phone-tabs" not in base
    guest_chunk = base.split("{% elif guest_settings %}", 1)[1].split("{% elif", 1)[0]
    assert "mobile-tabbar" not in guest_chunk


def test_guest_free_expired_halted_pro_settings_stay_separate(
    tmp_path: Path,
) -> None:
    guest = TestClient(_guest_app(tmp_path / "guest")).get("/settings")
    assert guest.status_code == 200
    guest_html = guest.text
    assert 'data-phone-settings="guest"' in guest_html
    assert "data-signed-in-settings" not in guest_html
    assert 'data-plus-settings="desktop"' not in guest_html
    assert 'data-settings-group="study"' not in guest_html
    assert 'data-settings-group="calendar"' not in guest_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/settings").text
    assert "data-signed-in-settings" in free_html
    assert 'data-plus-settings="desktop"' not in free_html
    assert "RecallC Plus" not in free_html.split("<header", 1)[-1].split(
        "</header>", 1
    )[0]

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get("/settings").text
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

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/settings").text
    assert 'data-plus-settings="desktop"' not in pro_html
    assert "RecallC Plus" not in pro_html.split("<header", 1)[-1].split(
        "</header>", 1
    )[0]


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


def _geo_script() -> str:
    return """() => {
              const panel = document.querySelector('[data-plus-settings="desktop"]');
              const header = document.querySelector('.site-header');
              const topbar = panel && panel.querySelector(':scope > .mobile-topbar');
              const back = panel && panel.querySelector('.mobile-back');
              const tabs = document.querySelector('.mobile-tabbar');
              const ident = panel && panel.querySelector('.settings-account-row');
              const identStatus = ident && ident.querySelector('.settings-account-status');
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
              const deskBack = panel && panel.querySelector('.si-settings-desk-back');
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
                if (el.closest('.mobile-topbar') || el.closest('.si-settings-desk-back')) {
                  return 'other';
                }
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
              const legalLinks = [...(panel ? panel.querySelectorAll(
                ':scope > .settings-note a'
              ) : [])];
              return {
                present: Boolean(panel),
                headerDisplay: header ? getComputedStyle(header).display : null,
                topbarDisplay: topbar ? getComputedStyle(topbar).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                backText: back && (back.textContent || '').replace(/\\s+/g, ' ').trim(),
                backHref: back && back.getAttribute('href'),
                identHref: ident && ident.getAttribute('href'),
                name: ident && (ident.innerText || ''),
                identStatus: identStatus && (identStatus.textContent || '').trim(),
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
                deskBackDisplay: deskBack ? getComputedStyle(deskBack).display : null,
                motionChecked: motion && motion.getAttribute('aria-checked'),
                sizeDisplay: size ? getComputedStyle(size).display : null,
                reportDisplay: report ? getComputedStyle(report).display : null,
                signoutDisplay: signoutBtn ? getComputedStyle(signoutBtn).display : null,
                signoutAction: signoutForm && signoutForm.getAttribute('action'),
                visual,
                focusBlocks,
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                hasSynced: /Last synced/.test(cal ? cal.innerText : ''),
                hasSettingsTab: tabs ? /Settings/.test(tabs.innerText || '') : false,
                legalHrefs: legalLinks.map((el) => el.getAttribute('href')),
                headingSize: panel && getComputedStyle(
                  panel.querySelector(':scope > .display')
                ).fontSize,
              };
            }"""


def _reach(page, selector: str) -> dict:
    page.locator(selector).scroll_into_view_if_needed()
    page.wait_for_timeout(40)
    return page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          const cs = el ? getComputedStyle(el) : null;
          const r = el && el.getBoundingClientRect();
          return {
            display: cs && cs.display,
            width: r ? r.width : 0,
            height: r ? r.height : 0,
            visible: Boolean(el && r && r.width > 0 && r.height > 0
              && cs && cs.display !== 'none' && cs.visibility !== 'hidden'),
            min: el ? Math.min(r.height, el.offsetHeight) : 0,
          };
        }""",
        selector,
    )


def test_phone_plus_settings_screen07_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    before = _facts(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_plus_settings_screen07_390x844.png"
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
        geo = page.evaluate(_geo_script())
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        below = {
            "motion": _reach(page, '[data-motion-toggle]'),
            "account": _reach(page, '[data-settings-group="account"]'),
            "report": _reach(
                page, '[data-settings-group="account"] [data-report-open]'
            ),
            "signout": _reach(
                page, '[data-settings-group="account"] .settings-signout-form button'
            ),
            "legal": _reach(page, '.settings-note a[href="/terms"]'),
            "ladder": _reach(page, ".settings-verbatim"),
        }

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
        short = {
            "tabs": page.evaluate(
                """() => {
                  const tabs = document.querySelector('.mobile-tabbar');
                  return {
                    display: tabs ? getComputedStyle(tabs).display : null,
                    overflow: document.documentElement.scrollWidth
                      > document.documentElement.clientWidth,
                  };
                }"""
            ),
            "motion": _reach(page, '[data-motion-toggle]'),
            "report": _reach(
                page, '[data-settings-group="account"] [data-report-open]'
            ),
            "signout": _reach(
                page, '[data-settings-group="account"] .settings-signout-form button'
            ),
            "legal": _reach(page, '.settings-note a[href="/terms"]'),
            "ladder": _reach(page, ".settings-verbatim"),
        }
        browser.close()

    assert geo["present"] is True
    assert geo["headerDisplay"] == "none"
    assert geo["topbarDisplay"] not in {None, "none"}
    assert geo["tabsDisplay"] in {None, "none"}
    assert geo["hasSettingsTab"] is False
    assert geo["backText"] == "← Today"
    assert geo["backHref"] == "/dashboard"
    assert geo["identHref"] == "/profile"
    assert "Sanjay" in (geo["name"] or "")
    assert geo["identStatus"]
    assert geo["identStatus"] != "Recall access · active"
    assert geo["identStatus"] == "Signed in with Google"
    assert geo["ledeDisplay"] not in {None, "none"}
    assert "Appearance, your learning plan, and your revision calendar." in (
        geo["ledeText"] or ""
    )
    assert geo["selfChecked"] is True
    assert geo["autoDisabled"] is False
    assert geo["selfBg"] == "rgb(20, 20, 20)"
    assert geo["selfColor"] == "rgb(255, 255, 255)"
    assert geo["autoThemeBg"] == "rgb(20, 20, 20)"
    assert geo["autoThemeColor"] == "rgb(255, 255, 255)"
    assert geo["gcalChecked"] == "false"
    assert geo["gcalDisplay"] not in {None, "none"}
    assert geo["deskCopyDisplay"] == "none"
    assert geo["connectRowDisplay"] == "none"
    assert geo["deskBackDisplay"] == "none"
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
    assert geo["hasSynced"] is False
    assert geo["legalHrefs"] == list(LEGAL_HREFS)
    assert geo["headingSize"] == "26px"
    for name, info in below.items():
        assert info["visible"] is True, name
    assert below["report"]["min"] >= 44
    assert below["signout"]["min"] >= 44
    assert report_open is True
    assert saved_geo["text"] == "Settings saved."
    assert saved_geo["display"] not in {None, "none"}
    assert profile_path.rstrip("/") == "/profile"
    assert settings_path.rstrip("/") == "/settings"
    assert today_path.rstrip("/") == "/dashboard"
    assert short["tabs"]["display"] in {None, "none"}
    assert short["tabs"]["overflow"] is False
    assert short["motion"]["visible"] is True
    assert short["report"]["visible"] is True
    assert short["signout"]["visible"] is True
    assert short["legal"]["visible"] is True
    assert short["ladder"]["visible"] is True
    assert short["report"]["min"] >= 44
    assert short["signout"]["min"] >= 44
    assert _facts(client) == before
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_plus_settings_screen07_desktop_regression_1280(
    tmp_path: Path,
) -> None:
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
    shot_path = artifact_dir / "phone_plus_settings_screen07_desktop_regression_1280.png"
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
              const plus = document.querySelector('[data-plus-settings="desktop"]');
              const heading = plus && plus.querySelector(':scope > .display');
              const ident = plus && plus.querySelector('.settings-account-row');
              const identStatus = ident && ident.querySelector('.settings-account-status');
              const study = plus && plus.querySelector('[data-settings-group="study"]');
              const cal = plus && plus.querySelector('[data-settings-group="calendar"]');
              const account = plus && plus.querySelector('[data-settings-group="account"]');
              const toggle = plus && plus.querySelector('[data-gcal-toggle]');
              const connect = cal && cal.querySelector('[data-gcal-connect]');
              const save = study && study.querySelector('button[type="submit"]');
              const selfPace = study && study.querySelector('#pace-self-paced');
              const autoPace = study && study.querySelector('#pace-auto');
              const selfLabel = study && study.querySelector('label[for="pace-self-paced"]');
              const back = plus && plus.querySelector('.si-settings-desk-back a');
              const nav = document.querySelector('.PrimaryTabs--top');
              const active = nav && [...nav.querySelectorAll('.nav-link.is-active')].map(
                (el) => (el.textContent || '').trim()
              );
              const phone = document.querySelector('.mobile-tabbar');
              const status = document.querySelector('.account-menu-btn-status');
              const selfCs = selfLabel ? getComputedStyle(selfLabel) : null;
              const identBox = ident && ident.getBoundingClientRect();
              const studyBox = study && study.getBoundingClientRect();
              const calBox = cal && cal.getBoundingClientRect();
              return {
                present: Boolean(plus),
                headingSize: heading ? getComputedStyle(heading).fontSize : null,
                identHref: ident && ident.getAttribute('href'),
                name: ident && (ident.innerText || ''),
                identStatus: identStatus && (identStatus.textContent || '').trim(),
                selfChecked: Boolean(selfPace && selfPace.checked),
                autoDisabled: Boolean(autoPace && autoPace.disabled),
                selfBg: selfCs && selfCs.backgroundColor,
                connectHref: connect && connect.getAttribute('href'),
                connectText: connect && (connect.textContent || '').replace(/\\s+/g, ' ').trim(),
                connectDisplay: connect ? getComputedStyle(connect).display : null,
                saveText: save && (save.textContent || '').replace(/\\s+/g, ' ').trim(),
                saveDisplay: save ? getComputedStyle(save).display : null,
                togglePhoneDisplay: toggle ? getComputedStyle(
                  toggle.closest('.settings-phone-only') || toggle
                ).display : null,
                accountDisplay: account ? getComputedStyle(account).display : null,
                tabsDisplay: phone ? getComputedStyle(phone).display : null,
                backText: back && (back.textContent || '').replace(/\\s+/g, ' ').trim(),
                backHref: back && back.getAttribute('href'),
                backDisplay: back ? getComputedStyle(back).display : 'none',
                hasSettingsPill: (active || []).includes('Settings'),
                status: status && (status.textContent || '').trim(),
                hasSynced: /Last synced/.test(cal ? cal.innerText : ''),
                studyBelow: Boolean(
                  identBox && studyBox && studyBox.top > identBox.bottom - 8
                ),
                calBelow: Boolean(
                  studyBox && calBox && calBox.top > studyBox.bottom - 8
                ),
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
    assert geo["identStatus"]
    assert geo["identStatus"] != "Recall access · active"
    assert geo["selfChecked"] is True
    assert geo["autoDisabled"] is False
    assert geo["selfBg"] == "rgb(20, 20, 20)"
    assert geo["connectHref"] and geo["connectHref"].startswith(
        "/calendar/google/connect"
    )
    assert geo["connectText"] == "Connect Google Calendar"
    assert geo["connectDisplay"] not in {None, "none"}
    assert geo["saveText"] == "Save learning plan"
    assert geo["saveDisplay"] not in {None, "none"}
    assert geo["togglePhoneDisplay"] == "none"
    assert geo["tabsDisplay"] == "none"
    assert geo["backText"] == "← Today"
    assert geo["backHref"] == "/dashboard"
    assert geo["backDisplay"] not in {None, "none"}
    assert geo["hasSettingsPill"] is False
    assert geo["status"] == "RecallC Plus"
    assert geo["hasSynced"] is False
    assert geo["studyBelow"] is True
    assert geo["calBelow"] is True
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
