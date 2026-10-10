"""Phone signed-in Free Profile Screen 06 (CTA map signedIn/06-screen).

Authorized: ChatGPT. Authenticated Free GET /profile at 390x844. Desktop
signed-in Profile Screen 10 is the functional contract. Live identity,
subscription, and device copy win over the map. Guest phone 06 is a visual
reference only. No S2-1.
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
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
USER = UUID("11111111-1111-4111-8111-111111111111")
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
)
MOCK_SCREEN_COPY = (
    "No plan yet",
    "See plans",
    "2 of 3",
    "Free account · Constitution learning included",
)
FREE_SEL = (
    "[data-signed-in-profile]:not([data-plus-profile])"
    ":not([data-expired-profile]):not([data-halted-profile])"
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


def _tabs(html: str) -> str:
    return html.split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 1
    )[1].split("</nav>", 1)[0]


def _panel(html: str) -> str:
    return html.split("data-signed-in-profile", 1)[1].split("</section>", 1)[0]


def _account_list(html: str) -> str:
    return html.split("data-profile-account", 1)[1].split("</div>", 1)[0]


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


def test_phone_free_profile_is_live_screen10_contract(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    before = _facts(client)
    ensure_calls = _watch_ensure(client)
    page = client.get("/profile")
    assert page.status_code == 200
    assert _facts(client) == before
    assert ensure_calls == []
    html = unescape(page.text)
    assert "data-signed-in-profile" in html
    assert "data-plus-profile" not in html
    assert "data-expired-profile" not in html
    assert "data-halted-profile" not in html
    assert 'data-mscreen="account"' in html
    assert 'data-phone-profile="guest"' not in html
    panel = _panel(html)
    assert "Sanjay" in panel
    assert "Signed in with Google" in panel
    assert 'href="/profile?edit=name"' in panel
    assert "Edit name" in panel
    assert "data-profile-identity" in panel
    assert "data-profile-account" in panel
    assert "data-profile-subscription" in panel
    assert "Playground" in panel
    assert "Subscribe to add Bare Acts to a monthly Playground." in panel
    assert ">Subscribe<" in panel
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in panel
    assert PLAYGROUND_BILLING_PATH == "/billing/subscriptions"
    account = _account_list(html)
    assert 'href="/profile"' in account
    assert 'href="/profile/security/devices"' in account
    assert "Devices" in account
    assert "2 of 3" not in account
    assert " of " in account or "device" in account.lower()
    assert 'href="/settings"' in account
    assert "Learning preferences" in account
    assert "data-report-open" in account
    assert 'data-report-section="Profile"' in account
    assert "data-open-signout" in account
    assert 'id="signout-modal"' in html
    assert 'action="/logout"' in html
    assert 'value="reset_progress"' in html
    assert 'value="delete_account"' in html
    for phrase in MOCK_SCREEN_COPY:
        assert phrase not in html, phrase
    assert "/pricing" not in html
    assert "Read mode." not in panel
    assert "/laws/ndps" not in panel
    tabs = _tabs(html)
    for label_text, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        assert label_text in tabs
    profile_tab = tabs.split('href="/profile"', 1)[1].split("</a>", 1)[0]
    assert "is-active" in profile_tab
    assert 'aria-current="page"' in profile_tab
    gate = client.get("/playground", follow_redirects=False)
    assert gate.status_code == 200
    assert 'data-playground-gate="not_subscribed"' in gate.text
    devices = client.get("/profile/security/devices", follow_redirects=False)
    assert devices.status_code == 200
    settings = client.get("/settings", follow_redirects=False)
    assert settings.status_code == 200
    billing = client.get(PLAYGROUND_BILLING_PATH, follow_redirects=False)
    assert billing.status_code in {200, 303}
    assert _facts(client) == before


def test_phone_free_profile_css_is_breakpoint_scoped() -> None:
    mobile = MOBILE.read_text(encoding="utf-8")
    generic, _, rest = mobile.partition("is signedIn/06-screen:")
    assert "data-signed-in-profile" not in generic
    phone_block = rest.split("/* R1 — Playground phone shell", 1)[0]
    assert "@media (max-width: 560px)" in phone_block
    assert "@media (min-width: 561px)" not in phone_block
    assert FREE_SEL in phone_block.replace("\n", "").replace(" ", "")
    assert ":not([data-plus-profile])" in phone_block
    assert ":not([data-expired-profile])" in phone_block
    assert ":not([data-halted-profile])" in phone_block
    assert "safe-area-inset-bottom" in phone_block
    assert "overflow-x: hidden" in phone_block
    assert "var(--m-tabbar, 60px)" in phone_block
    assert ".mobile-tabbar" in phone_block
    assert "grid-template-columns: repeat(5, 1fr)" in phone_block
    assert "position: fixed" in phone_block
    assert "si-profile-desk-only" in phone_block
    assert "display: flex !important" in phone_block
    assert ".link-btn" in phone_block
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", phone_block) is None
    assert "sun" not in phone_block.lower()
    assert 'data-plus-profile="desktop"] {' not in phone_block
    phone_profile = mobile.split(
        'body[data-mscreen="account"] .profile-panel > .display {', 1
    )[1].split("}", 1)[0]
    assert "font-size: 22px" in phone_profile
    desk = STYLES.read_text(encoding="utf-8").split(
        "/* Signed-in desktop Profile", 1
    )[1]
    assert "@media (min-width: 561px)" in desk
    assert "minmax(0, 1fr) minmax(0, 1fr)" in desk
    assert "font-size: 28px" in desk
    assert "playground.css?v=pg43" in BASE.read_text(encoding="utf-8")
    assert "styles.css?v=main86" in BASE.read_text(encoding="utf-8")
    assert "mobile.css?v=mob105" in BASE.read_text(encoding="utf-8")
    assert "mobile.css?v=mob104" not in BASE.read_text(encoding="utf-8")
    src = PROFILE.read_text(encoding="utf-8")
    for phrase in MOCK_SCREEN_COPY:
        assert phrase not in src, phrase
    assert "{{ playground_subscription.cta_href }}" in src
    assert 'href="/profile?edit=name"' in src
    assert "data-signed-in-pg-gate" in GATE.read_text(encoding="utf-8")
    guest_css = PG_CSS.read_text(encoding="utf-8")
    assert "Guest phone Profile (CTA map guest/06-screen)" in guest_css
    first_bar = BASE.read_text(encoding="utf-8").split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 2
    )[2].split("</nav>", 1)[0]
    assert 'href="/profile"' in first_bar
    assert "path.startswith('/profile')" in first_bar
    assert "data-plus-bareact-phone-tabs" not in first_bar


def test_guest_plus_expired_halted_profiles_stay_separate(tmp_path: Path) -> None:
    guest = TestClient(_guest_app(tmp_path / "guest")).get("/profile")
    assert guest.status_code == 200
    guest_html = guest.text
    assert 'data-phone-profile="guest"' in guest_html
    assert "data-signed-in-profile" not in guest_html
    assert "data-guest-profile-phone-tabs" in guest_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get("/profile").text
    assert "data-signed-in-profile" in plus_html
    assert 'data-plus-profile="desktop"' in plus_html
    assert "data-expired-profile" not in plus_html
    assert "data-halted-profile" not in plus_html

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
    expired_html = expired.get("/profile").text
    assert 'data-expired-profile="desktop"' in expired_html
    assert "data-plus-profile" not in expired_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/profile").text
    assert 'data-halted-profile="desktop"' in halted_html
    assert "data-plus-profile" not in halted_html


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


def test_phone_signed_in_profile_screen06_390x844(tmp_path: Path) -> None:
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
    shot_path = artifact_dir / "phone_signed_in_profile_screen06_390x844.png"
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
        page.goto(f"{origin}/profile", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-signed-in-profile]');
              const header = document.querySelector('.site-header');
              const topbar = panel && panel.querySelector(':scope > .mobile-topbar');
              const tabs = document.querySelector('.mobile-tabbar');
              const tabLinks = tabs ? [...tabs.querySelectorAll('a.mobile-tab')] : [];
              const active = tabs && tabs.querySelector('.mobile-tab.is-active');
              const identity = document.querySelector('[data-profile-identity]');
              const account = document.querySelector('[data-profile-account]');
              const sub = document.querySelector('[data-profile-subscription]');
              const edit = identity && identity.querySelector('a[href="/profile?edit=name"]');
              const cta = sub && sub.querySelector('a.pg-btn');
              const report = account && account.querySelector('[data-report-open]');
              const cardSignout = account && account.querySelector('[data-open-signout]');
              const lowerSignout = document.querySelector(
                '.account-actions > li:has([data-open-signout])'
              );
              const reset = document.querySelector('[data-open-reset]');
              const remove = document.querySelector('[data-open-delete]');
              const devices = account && account.querySelector(
                'a[href="/profile/security/devices"]'
              );
              const prefs = account && account.querySelector('a[href="/settings"]');
              const identityBox = identity && identity.getBoundingClientRect();
              const accountBox = account && account.getBoundingClientRect();
              const subBox = sub && sub.getBoundingClientRect();
              const focusable = [...(panel ? panel.querySelectorAll(
                'a[href], button:not([disabled]), input, select, textarea'
              ) : [])].filter((el) => {
                const cs = getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden') return false;
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              });
              const owner = (el) => {
                if (el.closest('[data-profile-identity]')) return 'identity';
                if (el.closest('[data-profile-account]')) return 'account';
                if (el.closest('[data-profile-subscription]')) return 'subscription';
                return 'other';
              };
              const visual = [
                { name: 'identity', top: identityBox && identityBox.top },
                { name: 'account', top: accountBox && accountBox.top },
                { name: 'subscription', top: subBox && subBox.top },
              ].sort((a, b) => (a.top || 0) - (b.top || 0)).map((row) => row.name);
              const focusBlocks = [];
              for (const el of focusable) {
                const name = owner(el);
                if (name === 'other') continue;
                if (focusBlocks[focusBlocks.length - 1] !== name) focusBlocks.push(name);
              }
              return {
                present: Boolean(panel),
                plus: Boolean(document.querySelector('[data-plus-profile]')),
                headerDisplay: header ? getComputedStyle(header).display : null,
                topbarDisplay: topbar ? getComputedStyle(topbar).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                tabsPosition: tabs ? getComputedStyle(tabs).position : null,
                tabLabels: tabLinks.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabLinks.map((el) => el.getAttribute('href')),
                profileActive: active && active.textContent.replace(/\\s+/g, ' ').trim(),
                name: identity && (identity.innerText || ''),
                editDisplay: edit ? getComputedStyle(edit).display : null,
                editHref: edit && edit.getAttribute('href'),
                ctaText: cta && (cta.textContent || '').replace(/\\s+/g, ' ').trim(),
                ctaHref: cta && cta.getAttribute('href'),
                subTitle: sub && (sub.querySelector('h2') || {}).textContent,
                reportDisplay: report ? getComputedStyle(report).display : null,
                cardSignoutDisplay: cardSignout
                  ? getComputedStyle(cardSignout).display
                  : null,
                lowerSignoutDisplay: lowerSignout
                  ? getComputedStyle(lowerSignout).display
                  : null,
                resetDisplay: reset ? getComputedStyle(reset).display : null,
                deleteDisplay: remove ? getComputedStyle(remove).display : null,
                devicesHref: devices && devices.getAttribute('href'),
                prefsHref: prefs && prefs.getAttribute('href'),
                visual,
                focusBlocks,
                identityTop: identityBox && identityBox.top,
                accountTop: accountBox && accountBox.top,
                subTop: subBox && subBox.top,
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                mockFree: /Free account · Constitution learning included/.test(
                  panel ? panel.innerText : ''
                ),
                mockPlan: /No plan yet|See plans/.test(panel ? panel.innerText : ''),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

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

        page.locator('[data-profile-account] [data-report-open]').click()
        report_open = page.evaluate(
            """() => {
              const overlay = document.querySelector('[data-report-overlay]');
              return Boolean(overlay && !overlay.hasAttribute('hidden'));
            }"""
        )
        page.locator("[data-rc-close]").click()

        page.locator("[data-open-reset]").click()
        reset_open = page.evaluate(
            """() => {
              const modal = document.querySelector('#reset-modal');
              return Boolean(modal && modal.open);
            }"""
        )
        if reset_open:
            page.locator("#reset-modal [data-close-dialog]").click()
        page.locator("[data-open-delete]").click()
        delete_open = page.evaluate(
            """() => {
              const modal = document.querySelector('#delete-modal');
              return Boolean(modal && modal.open);
            }"""
        )
        if delete_open:
            page.locator("#delete-modal [data-close-dialog]").click()

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
        page.set_viewport_size({"width": 390, "height": 700})
        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(80)
        short = page.evaluate(
            """() => {
              const tabs = document.querySelector('.mobile-tabbar');
              const reset = document.querySelector('[data-open-reset]');
              const tb = tabs.getBoundingClientRect();
              const rb = reset && reset.getBoundingClientRect();
              return {
                tabsFixed: getComputedStyle(tabs).position === 'fixed',
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                resetReachable: Boolean(reset && rb && rb.width > 0 && rb.height > 0),
                tabTop: tb.top,
              };
            }"""
        )
        browser.close()

    assert geo["present"] is True
    assert geo["plus"] is False
    assert geo["headerDisplay"] == "none"
    assert geo["topbarDisplay"] == "none"
    assert geo["tabsDisplay"] != "none"
    assert geo["tabsPosition"] == "fixed"
    assert geo["tabLabels"] == ["Today", "Browse", "Playground", "Calendar", "Profile"]
    assert geo["tabHrefs"] == [href for _, href in TAB_HREFS]
    assert geo["profileActive"] == "Profile"
    assert "Sanjay" in (geo["name"] or "")
    assert "Signed in with Google" in (geo["name"] or "")
    assert geo["editDisplay"] not in {None, "none"}
    assert geo["editHref"] == "/profile?edit=name"
    assert geo["ctaText"] == "Subscribe"
    assert geo["ctaHref"] == PLAYGROUND_BILLING_PATH
    assert geo["subTitle"] == "Playground"
    assert geo["reportDisplay"] == "flex"
    assert geo["cardSignoutDisplay"] == "flex"
    assert geo["lowerSignoutDisplay"] == "none"
    assert geo["resetDisplay"] not in {None, "none"}
    assert geo["deleteDisplay"] not in {None, "none"}
    assert geo["devicesHref"] == "/profile/security/devices"
    assert geo["prefsHref"] == "/settings"
    assert geo["visual"] == ["identity", "account", "subscription"]
    assert geo["focusBlocks"] == ["identity", "account", "subscription"]
    assert geo["identityTop"] <= geo["accountTop"]
    assert geo["accountTop"] <= geo["subTop"]
    assert geo["overflow"] is False
    assert geo["mockFree"] is False
    assert geo["mockPlan"] is False
    assert signout_open is True
    assert logout_action == "/logout"
    assert report_open is True
    assert reset_open is True
    assert delete_open is True
    assert devices_path.rstrip("/") == "/profile/security/devices"
    assert settings_path.rstrip("/") == "/settings"
    assert billing_path.rstrip("/") == "/billing/subscriptions"
    assert short["tabsFixed"] is True
    assert short["overflow"] is False
    assert short["resetReachable"] is True
    assert _facts(client) == before
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_signed_in_profile_screen06_desktop_regression_1280(
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
    shot_path = artifact_dir / "phone_signed_in_profile_screen06_desktop_regression_1280.png"
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
        page.goto(f"{origin}/profile", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-signed-in-profile]');
              const identity = document.querySelector('[data-profile-identity]');
              const account = document.querySelector('[data-profile-account]');
              const sub = document.querySelector('[data-profile-subscription]');
              const heading = panel && panel.querySelector(':scope > .display');
              const cta = sub && sub.querySelector('a.pg-btn');
              const report = account && account.querySelector('[data-report-open]');
              const signout = account && account.querySelector('[data-open-signout]');
              const identityBox = identity && identity.getBoundingClientRect();
              const accountBox = account && account.getBoundingClientRect();
              const subBox = sub && sub.getBoundingClientRect();
              const phone = document.querySelector('.mobile-tabbar');
              return {
                present: Boolean(panel),
                headingSize: heading ? getComputedStyle(heading).fontSize : null,
                ctaText: cta && (cta.textContent || '').replace(/\\s+/g, ' ').trim(),
                ctaHref: cta && cta.getAttribute('href'),
                twoCol: Boolean(
                  identityBox && subBox && subBox.left > identityBox.right - 8
                ),
                accountBelowIdentity: Boolean(
                  identityBox && accountBox && accountBox.top > identityBox.bottom - 8
                ),
                reportDisplay: report ? getComputedStyle(report).display : null,
                signoutDisplay: signout ? getComputedStyle(signout).display : null,
                tabsDisplay: phone ? getComputedStyle(phone).display : null,
                mockPlan: /No plan yet|See plans/.test(panel ? panel.innerText : ''),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["present"] is True
    assert geo["headingSize"] == "28px"
    assert geo["ctaText"] == "Subscribe"
    assert geo["ctaHref"] == PLAYGROUND_BILLING_PATH
    assert geo["twoCol"] is True
    assert geo["accountBelowIdentity"] is True
    assert geo["reportDisplay"] == "flex"
    assert geo["signoutDisplay"] == "flex"
    assert geo["tabsDisplay"] == "none"
    assert geo["mockPlan"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
