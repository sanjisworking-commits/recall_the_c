"""Guest desktop Playground intro Screen 6 (CTA map guest/06-screen).

Authorized: ChatGPT. Guest GET `/playground` desktop only. Phone Gate,
subscriber home, Landing, Browse, Laws, and Bare Act heads stay unchanged.
Sign in uses the existing `/login?next=/playground` path.
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
from constitution_memorizer.web.guest_playground_intro import (
    GUEST_PG_LEDE,
    GUEST_PG_NOTE,
    GUEST_PG_SIGNIN_HREF,
    GUEST_PG_STEPS,
    GUEST_PG_TITLE,
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


def _intro(html: str) -> str:
    return html.split("data-guest-pg-intro", 1)[1].split(
        'data-pg-gate-phone>', 1
    )[0]


def _phone_gate(html: str) -> str:
    return html.split('data-pg-gate-phone>', 1)[1]


def test_screen6_header_is_brand_and_guest_chip(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/playground").text
    header = _header(html)
    assert "data-guest-pg-intro" in html
    assert 'data-guest-pg-brand' in header
    assert "<span class=\"brand\"" in header
    assert 'src="/static/main_logo.png"' in header
    assert "Recall the C" in header
    assert "data-guest-pg-account" in header
    assert 'account-menu-btn-name">Guest<' in header
    assert "Not signed in" in header
    nav = header.split('aria-label="Primary"', 1)[1].split("</nav>", 1)[0]
    assert ">Today<" not in nav
    assert ">Playground<" not in nav
    assert ">Calendar<" not in nav
    assert ">Profile<" not in nav
    css = (ROOT / "src/constitution_memorizer/web/static/styles.css").read_text(
        encoding="utf-8"
    )
    guest_mark = css.split(
        'body.is-guest[data-mscreen="playground"]:has([data-guest-pg-intro]) .brand-mark {',
        1,
    )[1].split("}", 1)[0]
    assert "invert(1)" in guest_mark
    assert "position: absolute" not in css.split("/* R1 desktop shell", 1)[1]


def test_screen6_copy_single_signin_and_existing_auth_path(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/playground").text
    intro = _intro(html)
    assert GUEST_PG_TITLE in intro
    assert GUEST_PG_LEDE in intro
    assert "How Playground works" in intro
    for step in GUEST_PG_STEPS:
        assert step in intro
    assert GUEST_PG_NOTE in intro
    assert ">Sign in<" in intro
    assert intro.count("guest-pg-signin") == 1
    assert f'href="{GUEST_PG_SIGNIN_HREF}"' in intro
    assert GUEST_PG_SIGNIN_HREF == "/login?next=/playground"
    assert "Back to Constitution" not in intro
    assert "Already in Playground" not in intro
    assert "LawCard" not in intro
    assert "Create an account" not in intro
    assert "/billing/subscriptions" not in intro


def test_screen6_phone_gate_keeps_production_copy(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/playground").text
    phone = _phone_gate(html)
    assert "Sign in to use Playground" in phone
    assert GUEST_PG_TITLE not in phone
    assert "How Playground works" in phone
    assert f'href="{GUEST_PG_SIGNIN_HREF}"' in phone
    assert "data-hard-gate=\"true\"" in html


def test_screen6_does_not_change_other_screens(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    landing = client.get("/").text
    assert 'data-guest-landing="desktop"' in landing
    browse = client.get("/browse").text
    assert "Browse the Constitution" in browse
    laws = client.get("/laws").text
    assert "data-guest-laws-desktop" in laws
    ndps = client.get("/laws/ndps").text
    assert "data-guest-bareact-desktop" in ndps
    assert "data-guest-pg-intro" not in ndps
    css = (ROOT / "src/constitution_memorizer/web/static/styles.css").read_text(
        encoding="utf-8"
    )
    guest_grid = css.split(
        'body.is-guest[data-mscreen="browse"] .browse-resource-grid {', 1
    )[1].split("}", 1)[0]
    assert "calc(200% / 3)" in guest_grid


def test_single_user_playground_home_is_not_the_guest_intro(tmp_path: Path) -> None:
    html = TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    ).get("/playground").text
    assert "data-guest-pg-intro" not in html


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


def test_screen6_1280_matches_intro_and_signin_reaches_login(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "guest_playground_screen6_1280.png"
    gate_path = artifact_dir / "guest_pg_intro_signin_gate.png"
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
        page.goto(f"{origin}/playground", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const intro = document.querySelector('[data-guest-pg-intro]');
              const phone = document.querySelector('[data-pg-gate-phone]');
              const brand = document.querySelector('[data-guest-pg-brand]');
              const phoneBrand = document.querySelector('[data-pg-gate-phone-brand]');
              const nav = document.querySelector('.PrimaryTabs--top');
              const signin = intro.querySelector('.guest-pg-signin');
              const steps = [...intro.querySelectorAll('.guest-pg-step-t')].map(
                (el) => el.textContent.trim()
              );
              const visibleNav = [...nav.querySelectorAll('.nav-link')].filter(
                (el) => getComputedStyle(el).display !== 'none' && el.offsetParent !== null
              ).map((el) => el.textContent.replace(/\\s+/g, ' ').trim());
              return {
                introDisplay: getComputedStyle(intro).display,
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                brandTag: brand && brand.tagName,
                brandDisplay: brand ? getComputedStyle(brand).display : null,
                phoneBrandDisplay: phoneBrand ? getComputedStyle(phoneBrand).display : null,
                navDisplay: nav ? getComputedStyle(nav).display : null,
                visibleNav,
                kicker: intro.querySelector('.guest-pg-kicker').textContent.trim(),
                title: intro.querySelector('.guest-pg-title').textContent.trim(),
                lede: intro.querySelector('.guest-pg-lede').textContent.trim(),
                how: intro.querySelector('.guest-pg-how').textContent.trim(),
                steps,
                signinText: signin.textContent.trim(),
                signinHref: signin.getAttribute('href'),
                note: intro.querySelector('.guest-pg-note').textContent.trim(),
                guestName: document.querySelector('.account-menu-btn-name').textContent.trim(),
                guestStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                back: intro.innerText.includes('Back to Constitution'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        page.locator("[data-guest-pg-intro] .guest-pg-signin").click()
        page.wait_for_url("**/login**", timeout=8000)
        signin_url = page.url
        signin_html = page.content()
        page.screenshot(path=str(gate_path), full_page=False)

        phone = browser.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        phone.goto(f"{origin}/playground", wait_until="networkidle")
        phone_geo = phone.evaluate(
            """() => {
              const intro = document.querySelector('[data-guest-pg-intro]');
              const prod = document.querySelector('[data-pg-gate-phone]');
              return {
                introDisplay: intro ? getComputedStyle(intro).display : null,
                prodDisplay: prod ? getComputedStyle(prod).display : null,
                title: prod && prod.querySelector('h1') && prod.querySelector('h1').textContent.trim(),
              };
            }"""
        )
        browser.close()

    assert geo["introDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["brandTag"] == "SPAN"
    assert geo["brandDisplay"] != "none"
    assert geo["phoneBrandDisplay"] == "none"
    assert geo["navDisplay"] == "none"
    assert geo["visibleNav"] == []
    assert geo["kicker"] == "Playground"
    assert geo["title"] == GUEST_PG_TITLE
    assert geo["lede"] == GUEST_PG_LEDE
    assert geo["how"] == "How Playground works"
    assert geo["steps"] == list(GUEST_PG_STEPS)
    assert geo["signinText"] == "Sign in"
    assert geo["signinHref"] == GUEST_PG_SIGNIN_HREF
    assert geo["note"] == GUEST_PG_NOTE
    assert geo["guestName"] == "Guest"
    assert geo["guestStatus"] == "Not signed in"
    assert geo["back"] is False
    assert "/login" in signin_url
    assert "next=/playground" in signin_url
    assert "data-auth-grid" in signin_html
    assert phone_geo["introDisplay"] == "none"
    assert phone_geo["prodDisplay"] != "none"
    assert phone_geo["title"] == "Sign in to use Playground"
    assert shot_path.is_file()
    assert gate_path.is_file()
