"""Guest Landing Screen 1 (desktop CTA map guest/01-screen).

Authorized: ChatGPT plan + Sanjali. Guest `/` is this dedicated landing only.
Phone `.rc-launch` is unchanged. Destinations are navigation, not auth.
"""

from __future__ import annotations

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

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


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


def _desktop_css(html: str) -> str:
    return html.split("@media (min-width:561px){", 1)[1]


def _phone_css(html: str) -> str:
    return html.split("@media (max-width:560px){", 1)[1].split(
        "@media (max-width:560px) and", 1
    )[0]


def test_screen1_destinations_are_browse_and_laws_indexes(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/").text
    desk = html.split('data-guest-landing="desktop"', 1)[1].split("</section>", 1)[0]
    assert 'href="/browse">Explore the Constitution</a>' in desk
    assert 'href="/laws">Explore Laws</a>' in desk
    assert "/login" not in desk
    client = _guest_client(tmp_path)
    browse = client.get("/browse")
    assert browse.status_code == 200
    assert "Browse the Constitution" in browse.text
    laws = client.get("/laws")
    assert laws.status_code == 200
    assert 'data-laws-index' in laws.text or "laws-index-title" in laws.text


def test_screen1_has_no_header_or_signin_control(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/").text
    assert "<header" not in html
    assert 'class="nav-link"' not in html
    assert 'href="/login"' not in html
    assert "Sign in" not in html
    assert "Start learning" not in html
    assert "Start memorizing" not in html
    assert "Explore as guest" not in html
    assert 'href="/profile"' not in html
    assert "<nav" not in html


def test_screen1_desktop_buttons_share_one_width(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/").text
    desktop = _desktop_css(html)
    phone = _phone_css(html)
    assert "grid-auto-columns:1fr" in desktop
    assert ".rc-desk-cta{" in desktop
    assert "width:100%" in desktop.split(".rc-desk-cta{", 1)[1].split("}", 1)[0]
    assert "grid-auto-columns:1fr" not in phone
    assert ".rc-launch-cta{display:flex" in phone
    assert "Explore the Constitution" in html
    assert "Explore Laws" in html


def test_screen1_1280_buttons_are_equal_width(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    import socket
    import threading
    import time

    import uvicorn
    from playwright.sync_api import sync_playwright

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    config = uvicorn.Config(
        _guest_app(tmp_path), host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(80):
        probe = socket.socket()
        probe.settimeout(0.1)
        ready = probe.connect_ex(("127.0.0.1", port)) == 0
        probe.close()
        if ready:
            break
        time.sleep(0.05)
    else:
        pytest.fail("server did not bind")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        page = browser.new_page(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
        page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
        geo = page.evaluate(
            """() => {
              const primary = document.querySelector('.rc-desk-cta:not(.is-ghost)');
              const ghost = document.querySelector('.rc-desk-cta.is-ghost');
              const launch = document.querySelector('.rc-launch');
              const header = document.querySelector('header');
              const pr = primary.getBoundingClientRect();
              const gr = ghost.getBoundingClientRect();
              return {
                deskDisplay: getComputedStyle(document.querySelector('.rc-desk')).display,
                launchDisplay: launch ? getComputedStyle(launch).display : null,
                hasHeader: !!header,
                loginCount: document.querySelectorAll('a[href*="/login"]').length,
                primaryW: pr.width, ghostW: gr.width,
                primaryH: pr.height, ghostH: gr.height,
                primaryX: pr.x, ghostX: gr.x, primaryY: pr.y, ghostY: gr.y,
                primaryHref: primary.getAttribute('href'),
                ghostHref: ghost.getAttribute('href'),
              };
            }"""
        )
        browser.close()

    assert geo["deskDisplay"] == "flex"
    assert geo["launchDisplay"] == "none"
    assert geo["hasHeader"] is False
    assert geo["loginCount"] == 0
    assert geo["primaryHref"] == "/browse"
    assert geo["ghostHref"] == "/laws"
    assert abs(geo["primaryY"] - geo["ghostY"]) <= 2
    assert geo["primaryX"] < geo["ghostX"]
    assert abs(geo["primaryW"] - geo["ghostW"]) <= 1
    assert geo["primaryW"] > 160
    assert abs(geo["primaryH"] - geo["ghostH"]) <= 1
