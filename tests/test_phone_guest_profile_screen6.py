"""Phone Guest Profile Screen 06 (CTA map guest/06-screen, 390x844).

Authorized: ChatGPT. Guest GET /profile phone composition only. Desktop
guest/10-screen, signedIn/Plus/Expired/Halted Profiles stay unchanged.
Guest 04/05 remain parked. Sign in and Report are inert type=button.
Browse the Bare Acts → /laws/ndps.
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
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.guest_profile import (
    GUEST_PROFILE_BARE_ACTS_HREF,
    GUEST_PROFILE_BARE_ACTS_LABEL,
    GUEST_PROFILE_LEDE,
    GUEST_PROFILE_META,
    GUEST_PROFILE_NAME,
    GUEST_PROFILE_REPORT,
    GUEST_PROFILE_SIGNIN_HREF,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
)
SIGNED_IN_ROWS = (
    "Devices",
    "Learning preferences",
    "Sign out",
    "data-profile-subscription",
    "/profile/security/devices",
    "/billing/subscriptions",
)
FORBIDDEN = (
    "Subscribe",
    "View plans",
    "Manage subscription",
    "Resume Playground",
    "See plans",
    "Change plan",
    "Guest · Reading only",
    GUEST_PROFILE_SIGNIN_HREF,
    "data-report-open",
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
    return html.split('data-phone-profile="guest"', 1)[1].split("</section>", 1)[0]


def _tabs(html: str) -> str:
    return html.split("data-guest-profile-phone-tabs", 1)[1].split("</nav>", 1)[0]


def _desk(html: str) -> str:
    return html.split("data-guest-profile-desktop", 1)[1].split(
        "data-phone-profile", 1
    )[0]


def _facts(client: TestClient) -> dict:
    history = tuple(
        sorted(
            (row.id, row.status, row.tier, row.is_current)
            for row in client.app.state.subscriptions.list_subscription_history(USER)
        )
    )
    roster = getattr(client.app.state, "roster", None)
    overlay = getattr(client.app.state, "playground", None)
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


def test_phone_guest_profile_copy_and_controls(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    before = _facts(client)
    calls = _watch_provider(client)
    page = client.get("/profile")
    assert page.status_code == 200
    html = unescape(page.text)
    assert 'data-phone-profile="guest"' in html
    assert "data-guest-profile-desktop" in html
    phone = _phone(html)
    assert ">Profile<" in phone
    assert GUEST_PROFILE_NAME in phone
    assert GUEST_PROFILE_META in phone
    assert GUEST_PROFILE_LEDE in phone
    assert GUEST_PROFILE_BARE_ACTS_LABEL in phone
    assert f'href="{GUEST_PROFILE_BARE_ACTS_HREF}"' in phone
    assert GUEST_PROFILE_BARE_ACTS_HREF == "/laws/ndps"
    assert GUEST_PROFILE_REPORT in phone
    assert ">Sign in<" in phone
    assert phone.count('type="button"') == 2
    assert GUEST_PROFILE_SIGNIN_HREF not in phone
    assert "/login" not in phone
    assert "<form" not in phone
    assert 'href="/browse"' not in phone
    assert 'href="/playground"' not in phone
    assert 'href="/laws"' not in phone.replace(
        f'href="{GUEST_PROFILE_BARE_ACTS_HREF}"', ""
    )
    for phrase in FORBIDDEN + SIGNED_IN_ROWS:
        assert phrase not in phone, phrase
    assert _facts(client) == before
    assert calls == []


def test_phone_guest_profile_buttons_are_handlerless_in_source() -> None:
    src = PROFILE.read_text(encoding="utf-8")
    phone = src.split('data-phone-profile="guest"', 1)[1].split("</section>", 1)[0]
    assert 'type="button" class="guest-profile-signin">Sign in<' in phone
    assert 'type="button" class="guest-profile-report">' in phone
    assert GUEST_PROFILE_REPORT in phone
    assert f'href="{GUEST_PROFILE_BARE_ACTS_HREF}"' in phone
    assert "/login" not in phone
    assert "<form" not in phone
    assert "data-report-open" not in phone
    desk = src.split("data-guest-profile-desktop", 1)[1].split(
        "data-phone-profile", 1
    )[0]
    assert f'href="{GUEST_PROFILE_SIGNIN_HREF}"' in desk
    assert "<a class=\"guest-profile-signin\"" in desk
    assert 'type="button"' not in desk


def test_phone_guest_five_tabs_profile_active(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/profile").text
    assert "data-guest-profile-phone-tabs" in html
    assert "mobile-tabbar is-guest" not in html
    tabs = _tabs(html)
    labels = []
    for label, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        labels.append(label)
        assert label in tabs
    assert labels == ["Today", "Browse", "Playground", "Calendar", "Profile"]
    profile = tabs.split('href="/profile"', 1)[1].split("</a>", 1)[0]
    assert "is-active" in profile
    assert 'aria-current="page"' in profile
    for href in ("/dashboard", "/browse", "/playground", "/calendar"):
        chunk = tabs.split(f'href="{href}"', 1)[1].split("</a>", 1)[0]
        assert "is-active" not in chunk
    ndps = _guest_client(tmp_path / "ndps").get("/laws/ndps").text
    assert "data-guest-profile-phone-tabs" not in ndps
    assert "data-guest-bareact-phone-tabs" in ndps
    playground = _guest_client(tmp_path / "pg").get("/playground").text
    assert "data-guest-profile-phone-tabs" not in playground
    assert "data-guest-pg-phone-tabs" in playground


def test_phone_guest_profile_css_is_breakpoint_scoped() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    phone_block = css.split("Guest phone Profile (CTA map guest/06-screen)", 1)[1].split(
        "/* Guest desktop Profile", 1
    )[0]
    assert "@media (max-width: 560px)" in phone_block
    assert '[data-phone-profile="guest"]' in phone_block
    assert "guest-profile-signin" in phone_block
    assert "guest-profile-report" in phone_block
    assert "guest-profile-bareacts" in phone_block
    hide = css.split('[data-phone-profile="guest"],', 1)[1].split("}", 1)[0]
    assert "display: none" in hide
    assert "data-guest-profile-phone-tabs" in hide
    assert "playground.css?v=pg40" in BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg31" not in BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg30" not in BASE.read_text(encoding="utf-8")
    guest_title = css.split(".guest-profile-title {", 1)[1].split("}", 1)[0]
    assert "font-size: 28px" in guest_title


def test_signed_in_plus_expired_halted_paused_profiles_stay_separate(
    tmp_path: Path,
) -> None:
    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/profile").text
    assert 'data-phone-profile="guest"' not in free_html
    assert "data-guest-profile-phone-tabs" not in free_html
    assert "data-signed-in-profile" in free_html
    assert "Devices" in free_html
    assert "Learning preferences" in free_html
    assert "Sign out" in free_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get("/profile").text
    assert 'data-phone-profile="guest"' not in plus_html
    assert 'data-plus-profile="desktop"' in plus_html
    assert "data-signed-in-profile" in plus_html

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
    assert 'data-phone-profile="guest"' not in expired_html
    assert 'data-expired-profile="desktop"' in expired_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/profile").text
    assert 'data-phone-profile="guest"' not in halted_html
    assert 'data-halted-profile="desktop"' in halted_html

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused, status="paused")
    paused_html = paused.get("/profile").text
    assert 'data-phone-profile="guest"' not in paused_html
    assert "data-guest-profile-desktop" not in paused_html

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    pending_html = pending.get("/profile").text
    assert 'data-phone-profile="guest"' not in pending_html
    assert "data-guest-profile-desktop" not in pending_html


def test_phone_guest_profile_gets_are_mutation_free(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    before = _facts(client)
    calls = _watch_provider(client)
    assert before["session"] is None
    assert before["subscription"] is None
    for _ in range(3):
        page = client.get("/profile")
        assert page.status_code == 200
        assert _facts(client) == before
    assert calls == []
    assert client.get("/laws/ndps").status_code == 200
    assert _facts(client) == before


def test_desktop_guest_profile_signin_still_uses_login(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/profile").text
    desk = _desk(html)
    assert f'href="{GUEST_PROFILE_SIGNIN_HREF}"' in desk
    assert GUEST_PROFILE_META in desk
    assert f'href="{GUEST_PROFILE_BARE_ACTS_HREF}"' in desk
    assert 'type="button"' not in desk


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


def test_phone_guest_profile_screen06_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_guest_profile_screen06_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        page = browser.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )
        requests: list[str] = []
        page.on("request", lambda req: requests.append(f"{req.method} {req.url}"))
        page.goto(f"{origin}/profile", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const phone = document.querySelector('[data-phone-profile="guest"]');
              const desk = document.querySelector('[data-guest-profile-desktop]');
              const prod = document.querySelector('[data-guest-profile-phone]');
              const header = document.querySelector('.site-header');
              const tabs = document.querySelector('[data-guest-profile-phone-tabs]');
              const signin = phone && phone.querySelector('.guest-profile-signin');
              const report = phone && phone.querySelector('.guest-profile-report');
              const bare = phone && phone.querySelector('.guest-profile-bareacts');
              const tabLinks = tabs ? [...tabs.querySelectorAll('a.mobile-tab')] : [];
              const active = tabs && tabs.querySelector('.mobile-tab.is-active');
              const guestBar = document.querySelector('.mobile-tabbar.is-guest');
              return {
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                prodDisplay: prod ? getComputedStyle(prod).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                guestBarDisplay: guestBar ? getComputedStyle(guestBar).display : null,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                title: phone && phone.querySelector('h1').textContent.trim(),
                name: phone && phone.querySelector('.guest-profile-name').textContent.trim(),
                meta: phone && phone.querySelector('.guest-profile-meta').textContent.trim(),
                lede: phone && phone.querySelector('.guest-profile-lede').textContent.trim(),
                signin: {
                  tag: signin && signin.tagName,
                  type: signin && signin.getAttribute('type'),
                  href: signin && signin.getAttribute('href'),
                  text: signin && signin.textContent.trim(),
                },
                report: {
                  tag: report && report.tagName,
                  type: report && report.getAttribute('type'),
                  href: report && report.getAttribute('href'),
                  text: report && report.textContent.replace(/\\s+/g, ' ').trim(),
                  open: report && report.hasAttribute('data-report-open'),
                },
                bareText: bare && bare.textContent.trim(),
                bareHref: bare && bare.getAttribute('href'),
                tabLabels: tabLinks.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabLinks.map((el) => el.getAttribute('href')),
                profileActive: active && active.textContent.replace(/\\s+/g, ' ').trim(),
                devices: phone && phone.innerText.includes('Devices'),
                prefs: phone && phone.innerText.includes('Learning preferences'),
                signout: phone && phone.innerText.includes('Sign out'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        n_before = len(requests)
        page.locator("[data-phone-profile='guest'] .guest-profile-signin").click()
        page.wait_for_timeout(250)
        after_signin = page.evaluate("() => location.pathname")
        page.locator("[data-phone-profile='guest'] .guest-profile-report").click()
        page.wait_for_timeout(250)
        after_report = page.evaluate("() => location.pathname")
        extra = requests[n_before:]
        page.locator("[data-phone-profile='guest'] .guest-profile-bareacts").click()
        page.wait_for_url("**/laws/ndps**", timeout=8000)
        ndps_url = page.url
        ndps_html = page.content()
        browser.close()

    assert geo["phoneDisplay"] != "none"
    assert geo["deskDisplay"] == "none"
    assert geo["prodDisplay"] == "none"
    assert geo["headerDisplay"] == "none"
    assert geo["tabsDisplay"] != "none"
    assert geo["guestBarDisplay"] is None
    assert geo["overflow"] is False
    assert geo["title"] == "Profile"
    assert geo["name"] == GUEST_PROFILE_NAME
    assert geo["meta"] == GUEST_PROFILE_META
    assert geo["lede"] == GUEST_PROFILE_LEDE
    assert geo["signin"]["tag"] == "BUTTON"
    assert geo["signin"]["type"] == "button"
    assert geo["signin"]["href"] is None
    assert geo["signin"]["text"] == "Sign in"
    assert geo["report"]["tag"] == "BUTTON"
    assert geo["report"]["type"] == "button"
    assert geo["report"]["href"] is None
    assert geo["report"]["text"].startswith(GUEST_PROFILE_REPORT)
    assert geo["report"]["open"] is False
    assert geo["bareText"] == GUEST_PROFILE_BARE_ACTS_LABEL
    assert geo["bareHref"] == GUEST_PROFILE_BARE_ACTS_HREF
    assert geo["tabLabels"] == ["Today", "Browse", "Playground", "Calendar", "Profile"]
    assert geo["tabHrefs"] == [
        "/dashboard",
        "/browse",
        "/playground",
        "/calendar",
        "/profile",
    ]
    assert geo["profileActive"] == "Profile"
    assert geo["devices"] is False
    assert geo["prefs"] is False
    assert geo["signout"] is False
    assert after_signin == "/profile"
    assert after_report == "/profile"
    assert not any("/login" in item for item in extra)
    assert not any(item.startswith("POST ") for item in extra)
    assert "/laws/ndps" in ndps_url
    assert "data-guest-bareact-phone" in ndps_html
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_guest_profile_screen06_desktop_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_guest_profile_screen06_desktop_regression_1280.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        page = browser.new_page(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
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
              const desk = document.querySelector('[data-guest-profile-desktop]');
              const phone = document.querySelector('[data-phone-profile="guest"]');
              const tabs = document.querySelector('[data-guest-profile-phone-tabs]');
              const header = document.querySelector('.site-header');
              const signin = desk && desk.querySelector('.guest-profile-signin');
              const report = desk && desk.querySelector('.guest-profile-report');
              return {
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                name: desk && desk.querySelector('.guest-profile-name').textContent.trim(),
                meta: desk && desk.querySelector('.guest-profile-meta').textContent.trim(),
                signinTag: signin && signin.tagName,
                signinHref: signin && signin.getAttribute('href'),
                reportTag: report && report.tagName,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["tabsDisplay"] == "none"
    assert geo["headerDisplay"] != "none"
    assert geo["name"] == GUEST_PROFILE_NAME
    assert geo["meta"] == GUEST_PROFILE_META
    assert geo["signinTag"] == "A"
    assert geo["signinHref"] == GUEST_PROFILE_SIGNIN_HREF
    assert geo["reportTag"] == "DIV"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
