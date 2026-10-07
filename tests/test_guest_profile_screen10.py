"""Guest desktop Profile Screen 10 (CTA map guest/10-screen).

Authorized: ChatGPT. Guest GET `/profile` desktop only. Phone guest Profile,
subscriber Profile, Landing, Browse, Laws, Bare Act, Playground, Today, and
Calendar stay unchanged. Sign in uses the existing `/login?next=/profile` path.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
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


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _guest_app(tmp_path: Path):
    settings = MultiUserSettings(
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
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=settings,
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
    )


def _guest_client(tmp_path: Path) -> TestClient:
    return TestClient(_guest_app(tmp_path))


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _desktop(html: str) -> str:
    return html.split("data-guest-profile-desktop", 1)[1].split(
        "data-guest-profile-phone", 1
    )[0]


def _phone(html: str) -> str:
    return html.split("data-guest-profile-phone>", 1)[1]


def test_screen10_header_is_profile_selected_guest_chrome(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/profile").text
    header = _header(html)
    assert "data-guest-profile-desktop" in html
    assert "data-guest-profile-brand" in header
    assert "<span class=\"brand\"" in header
    assert 'src="/static/main_logo.png"' in header
    assert "Recall the C" in header
    assert "data-guest-profile-account" in header
    assert 'account-menu-btn-name">Guest<' in header
    assert "Not signed in" in header
    assert "data-guest-profile-nav" in header
    assert ">Today<" in header
    assert ">Browse<" in header
    assert ">Playground<" in header
    assert ">Calendar<" in header
    assert ">Profile<" in header
    assert 'data-guest-profile-nav aria-current="page"' in header
    assert 'href="/playground"' in header
    assert "data-guest-profile-phone-nav" in header
    assert ">Home<" in header
    assert ">Search<" in header
    assert ">Learn<" in header
    assert "nav-signin" in header
    css = (ROOT / "src/constitution_memorizer/web/static/styles.css").read_text(
        encoding="utf-8"
    )
    guest_mark = css.split(
        'body.is-guest[data-mscreen="account"]:has([data-guest-profile-desktop]) .brand-mark {',
        1,
    )[1].split("}", 1)[0]
    assert "invert(1)" in guest_mark
    assert "position: absolute" not in css.split("/* R1 desktop shell", 1)[1]


def test_screen10_identity_info_report_and_existing_auth_path(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/profile").text
    desk = _desktop(html)
    assert GUEST_PROFILE_NAME in desk
    assert GUEST_PROFILE_META in desk
    assert GUEST_PROFILE_LEDE in desk
    assert GUEST_PROFILE_BARE_ACTS_LABEL in desk
    assert f'href="{GUEST_PROFILE_BARE_ACTS_HREF}"' in desk
    assert GUEST_PROFILE_BARE_ACTS_HREF == "/laws/ndps"
    assert ">Sign in<" in desk
    assert desk.count("guest-profile-signin") == 1
    assert f'href="{GUEST_PROFILE_SIGNIN_HREF}"' in desk
    assert GUEST_PROFILE_SIGNIN_HREF == "/login?next=/profile"
    assert GUEST_PROFILE_REPORT in desk
    assert "guest-profile-report" in desk
    assert 'href=' not in desk.split("guest-profile-report", 1)[1].split("</div>", 1)[0]
    assert "See plans" not in desk
    assert "Change plan" not in desk
    assert "Manage subscription" not in desk
    assert "/billing/subscriptions" not in desk
    assert "/profile/security/devices" not in desk
    assert "Learning preferences" not in desk
    assert "data-profile-subscription" not in desk


def test_screen10_phone_keeps_production_guest_card(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/profile").text
    phone = _phone(html)
    assert "Guest · Reading only" in phone
    assert 'href="/laws"' in phone
    assert 'href="/laws/ndps"' not in phone
    assert "data-guest-profile" in phone
    assert "Read mode." not in phone
    assert "guest-profile-report" not in phone
    assert f'href="{GUEST_PROFILE_SIGNIN_HREF}"' in phone


def test_screen10_does_not_change_other_screens(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    landing = client.get("/").text
    assert 'data-guest-landing="desktop"' in landing
    browse = client.get("/browse").text
    assert "Browse the Constitution" in browse
    laws = client.get("/laws").text
    assert "data-guest-laws-desktop" in laws
    ndps = client.get("/laws/ndps").text
    assert "data-guest-bareact-desktop" in ndps
    playground = client.get("/playground").text
    assert "data-guest-pg-intro" in playground
    assert "data-guest-profile-desktop" not in playground
    css = (ROOT / "src/constitution_memorizer/web/static/styles.css").read_text(
        encoding="utf-8"
    )
    guest_grid = css.split(
        'body.is-guest[data-mscreen="browse"] .browse-resource-grid {', 1
    )[1].split("}", 1)[0]
    assert "calc(200% / 3)" in guest_grid


def test_single_user_profile_is_not_the_guest_desktop(tmp_path: Path) -> None:
    html = TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    ).get("/profile").text
    assert "data-guest-profile-desktop" not in html


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


def test_screen10_1280_signin_ndps_report_and_phone(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "guest_profile_screen10_1280.png"
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
              const phone = document.querySelector('[data-guest-profile-phone]');
              const brand = document.querySelector('[data-guest-profile-brand]');
              const phoneBrand = document.querySelector('[data-guest-profile-phone-brand]');
              const deskNav = [...document.querySelectorAll('[data-guest-profile-nav]')];
              const phoneNav = [...document.querySelectorAll('[data-guest-profile-phone-nav]')];
              const visibleDesk = deskNav.filter(
                (el) => getComputedStyle(el).display !== 'none' && el.offsetParent !== null
              ).map((el) => el.textContent.replace(/\\s+/g, ' ').trim());
              const visiblePhone = phoneNav.filter(
                (el) => getComputedStyle(el).display !== 'none' && el.offsetParent !== null
              ).map((el) => el.textContent.replace(/\\s+/g, ' ').trim());
              const active = deskNav.find((el) => el.classList.contains('is-active'));
              const signin = desk.querySelector('.guest-profile-signin');
              const bare = desk.querySelector('.guest-profile-bareacts');
              const report = desk.querySelector('.guest-profile-report');
              const playground = deskNav.find((el) => el.textContent.includes('Playground'));
              return {
                deskDisplay: getComputedStyle(desk).display,
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                brandTag: brand && brand.tagName,
                brandDisplay: brand ? getComputedStyle(brand).display : null,
                phoneBrandDisplay: phoneBrand ? getComputedStyle(phoneBrand).display : null,
                visibleDesk,
                visiblePhone,
                activeText: active && active.textContent.replace(/\\s+/g, ' ').trim(),
                name: desk.querySelector('.guest-profile-name').textContent.trim(),
                meta: desk.querySelector('.guest-profile-meta').textContent.trim(),
                lede: desk.querySelector('.guest-profile-lede').textContent.trim(),
                signinText: signin.textContent.trim(),
                signinHref: signin.getAttribute('href'),
                bareText: bare.textContent.trim(),
                bareHref: bare.getAttribute('href'),
                reportText: report.textContent.replace(/\\s+/g, ' ').trim(),
                reportTag: report.tagName,
                reportHref: report.getAttribute('href'),
                playgroundHref: playground && playground.getAttribute('href'),
                guestName: document.querySelector('[data-guest-profile-account] .account-menu-btn-name').textContent.trim(),
                guestStatus: document.querySelector('[data-guest-profile-account] .account-menu-btn-status').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        before_report = page.url
        page.locator("[data-guest-profile-desktop] .guest-profile-report").click()
        page.wait_for_timeout(400)
        after_report = page.url

        page.locator("[data-guest-profile-desktop] .guest-profile-signin").click()
        page.wait_for_url("**/login**", timeout=8000)
        signin_url = page.url
        signin_html = page.content()

        page.goto(f"{origin}/profile", wait_until="networkidle")
        page.locator("[data-guest-profile-desktop] .guest-profile-bareacts").click()
        page.wait_for_url("**/laws/ndps**", timeout=8000)
        ndps_url = page.url
        ndps_html = page.content()

        page.goto(f"{origin}/profile", wait_until="networkidle")
        page.locator("[data-guest-profile-nav][href='/playground']").click()
        page.wait_for_url("**/playground**", timeout=8000)
        playground_html = page.content()

        phone = browser.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        phone.goto(f"{origin}/profile", wait_until="networkidle")
        phone_geo = phone.evaluate(
            """() => {
              const desk = document.querySelector('[data-guest-profile-desktop]');
              const prod = document.querySelector('[data-guest-profile-phone]');
              const bare = prod && prod.querySelector('[data-guest-profile] a');
              return {
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                prodDisplay: prod ? getComputedStyle(prod).display : null,
                meta: prod && prod.querySelector('.muted') && prod.querySelector('.muted').textContent.trim(),
                bareHref: bare && bare.getAttribute('href'),
              };
            }"""
        )
        browser.close()

    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["brandTag"] == "SPAN"
    assert geo["brandDisplay"] != "none"
    assert geo["phoneBrandDisplay"] == "none"
    assert geo["visibleDesk"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["visiblePhone"] == []
    assert geo["activeText"] == "Profile"
    assert geo["name"] == GUEST_PROFILE_NAME
    assert geo["meta"] == GUEST_PROFILE_META
    assert geo["lede"] == GUEST_PROFILE_LEDE
    assert geo["signinText"] == "Sign in"
    assert geo["signinHref"] == GUEST_PROFILE_SIGNIN_HREF
    assert geo["bareText"] == GUEST_PROFILE_BARE_ACTS_LABEL
    assert geo["bareHref"] == GUEST_PROFILE_BARE_ACTS_HREF
    assert geo["reportText"].startswith(GUEST_PROFILE_REPORT)
    assert geo["reportTag"] == "DIV"
    assert geo["reportHref"] is None
    assert geo["playgroundHref"] == "/playground"
    assert geo["guestName"] == "Guest"
    assert geo["guestStatus"] == "Not signed in"
    assert after_report == before_report
    assert "/login" in signin_url
    assert "next=/profile" in signin_url
    assert "data-auth-grid" in signin_html
    assert "/laws/ndps" in ndps_url
    assert "data-guest-bareact-desktop" in ndps_html
    assert "data-guest-pg-intro" in playground_html
    assert phone_geo["deskDisplay"] == "none"
    assert phone_geo["prodDisplay"] != "none"
    assert phone_geo["meta"] == "Guest · Reading only"
    assert phone_geo["bareHref"] == "/laws"
    assert shot_path.is_file()
