"""Signed-in desktop Landing (CTA map signedIn/01-screen).

Authorized: ChatGPT. Authenticated multiuser GET / serves the same dark
landing.html as guests. Phone `.rc-launch` is unchanged. Destinations are
navigation, not auth. No Sign in CTA, header, or account affordance.
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
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


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


def _mu_app(tmp_path: Path):
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=UUID("11111111-1111-4111-8111-111111111111"),
        email="a@example.com",
        display_name="User A",
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


def _desk(html: str) -> str:
    return html.split('data-guest-landing="desktop"', 1)[1].split("</section>", 1)[0]


def _launch(html: str) -> str:
    return html.split('<section class="rc-launch">', 1)[1].split("</section>", 1)[0]


def test_signed_in_root_serves_landing_not_dashboard(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    root = client.get("/", follow_redirects=False)
    assert root.status_code == 200
    assert root.headers.get("location") is None
    html = root.text
    assert "The Constitution, remembered." in html
    assert ">Recall the C</h1>" in html
    assert 'data-guest-landing="desktop"' in html
    assert "Today" not in _desk(html)
    dash = client.get("/dashboard", follow_redirects=False)
    assert dash.status_code == 200
    assert dash.text != html


def test_signed_in_landing_has_no_header_or_signin_cta(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/", follow_redirects=False).text
    assert "<header" not in html
    assert "<nav" not in html
    assert 'class="nav-link"' not in html
    assert 'href="/login"' not in html
    assert "Sign in" not in html
    assert 'href="/profile"' not in html
    assert 'href="/dashboard"' not in html
    assert "Start learning" not in html
    assert "Explore as guest" not in html


def test_signed_in_landing_ctas_are_browse_and_laws(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/", follow_redirects=False).text
    desk = _desk(html)
    assert 'href="/browse">Explore the Constitution</a>' in desk
    assert 'href="/laws">Explore Laws</a>' in desk
    assert desk.count("href=") == 2
    browse = client.get("/browse")
    assert browse.status_code == 200
    assert "Browse the Constitution" in browse.text
    laws = client.get("/laws")
    assert laws.status_code == 200
    assert "data-laws-index" in laws.text or "laws-index-title" in laws.text


def test_landing_ctas_are_viewer_invariant(tmp_path: Path) -> None:
    app = _mu_app(tmp_path)
    guest = TestClient(app)
    authed = TestClient(app)
    _sign_in(authed)
    guest_html = guest.get("/", follow_redirects=False).text
    authed_html = authed.get("/", follow_redirects=False).text
    assert guest_html == authed_html
    assert _desk(guest_html) == _desk(authed_html)
    assert _launch(guest_html) == _launch(authed_html)
    assert 'href="/browse">Explore the Constitution' in _desk(authed_html)
    assert 'href="/laws">Explore Laws' in _desk(authed_html)


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


def test_signed_in_landing_1280_matches_desktop_shot(tmp_path: Path) -> None:
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
    shot_path = artifact_dir / "signed_in_landing_1280.png"
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
        page.goto(f"{origin}/", wait_until="networkidle")
        assert page.url.rstrip("/") == origin
        geo = page.evaluate(
            """() => {
              const primary = document.querySelector('.rc-desk-cta:not(.is-ghost)');
              const ghost = document.querySelector('.rc-desk-cta.is-ghost');
              const launch = document.querySelector('.rc-launch');
              const header = document.querySelector('header');
              const pr = primary.getBoundingClientRect();
              const gr = ghost.getBoundingClientRect();
              const mark = document.querySelector('.rc-desk-mark');
              const name = document.querySelector('.rc-desk-name');
              const tag = document.querySelector('.rc-desk-tag');
              const bg = getComputedStyle(document.querySelector('.rc-desk')).backgroundColor;
              return {
                deskDisplay: getComputedStyle(document.querySelector('.rc-desk')).display,
                launchDisplay: launch ? getComputedStyle(launch).display : null,
                hasHeader: !!header,
                loginCount: document.querySelectorAll('a[href*="/login"]').length,
                profileCount: document.querySelectorAll('a[href*="/profile"]').length,
                dashCount: document.querySelectorAll('a[href*="/dashboard"]').length,
                signInVisible: /Sign in/.test(document.body.innerText),
                mark: mark && mark.textContent.trim(),
                name: name && name.textContent.trim(),
                tag: tag && tag.textContent.trim(),
                primaryText: primary.textContent.trim(),
                ghostText: ghost.textContent.trim(),
                primaryHref: primary.getAttribute('href'),
                ghostHref: ghost.getAttribute('href'),
                primaryW: pr.width, ghostW: gr.width,
                primaryH: pr.height, ghostH: gr.height,
                primaryX: pr.x, ghostX: gr.x, primaryY: pr.y, ghostY: gr.y,
                bg,
              };
            }"""
        )
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator(".rc-desk-cta:not(.is-ghost)").click()
        page.wait_for_url("**/browse**", timeout=8000)
        browse_url = page.url
        page.goto(f"{origin}/", wait_until="networkidle")
        page.locator(".rc-desk-cta.is-ghost").click()
        page.wait_for_url("**/laws**", timeout=8000)
        laws_url = page.url
        browser.close()

    assert geo["deskDisplay"] == "flex"
    assert geo["launchDisplay"] == "none"
    assert geo["hasHeader"] is False
    assert geo["loginCount"] == 0
    assert geo["profileCount"] == 0
    assert geo["dashCount"] == 0
    assert geo["signInVisible"] is False
    assert geo["mark"] == "C"
    assert geo["name"] == "Recall the C"
    assert geo["tag"] == "The Constitution, remembered."
    assert geo["primaryText"] == "Explore the Constitution"
    assert geo["ghostText"] == "Explore Laws"
    assert geo["primaryHref"] == "/browse"
    assert geo["ghostHref"] == "/laws"
    assert abs(geo["primaryY"] - geo["ghostY"]) <= 2
    assert geo["primaryX"] < geo["ghostX"]
    assert abs(geo["primaryW"] - geo["ghostW"]) <= 1
    assert geo["primaryW"] > 160
    assert abs(geo["primaryH"] - geo["ghostH"]) <= 1
    assert browse_url.rstrip("/").endswith("/browse")
    assert "/laws" in laws_url
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
