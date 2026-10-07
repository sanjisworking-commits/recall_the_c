"""Plus cohort desktop Landing Screen 01 (CTA map plus/01-screen).

Authorized: ChatGPT. Authenticated multiuser GET / with a real active Plus
subscription. Same accepted Screen 01 landing as Free/guest: dark stack,
Explore the Constitution → /browse, Explore Laws → /laws, no header.
Plus is marked from EntitlementSnapshot only. No invented Plus copy.
Free Screen 01, Gate, guest, phone, and later Plus screens stay unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import socket
import threading
import time
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
LANDING = (
    Path(__file__).resolve().parents[1]
    / "src/constitution_memorizer/web/templates/landing.html"
)
USER = UUID("11111111-1111-4111-8111-111111111111")
INVENTED = (
    "Premium",
    "Unlimited",
    "RecallC Plus",
    "Free account",
    "Start learning",
    "Sign in",
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


def _desk(html: str) -> str:
    return html.split('data-guest-landing="desktop"', 1)[1].split("</section>", 1)[0]


def test_plus_root_keeps_accepted_landing_from_real_subscription(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    root = client.get("/", follow_redirects=False)
    assert root.status_code == 200
    assert root.headers.get("location") is None
    html = root.text
    assert 'data-plus-landing="desktop"' in html
    assert 'data-guest-landing="desktop"' in html
    desk = _desk(html)
    assert ">Recall the C</h1>" in html
    assert "The Constitution, remembered." in html
    assert 'href="/browse">Explore the Constitution</a>' in desk
    assert 'href="/laws">Explore Laws</a>' in desk
    assert desk.count("href=") == 2
    for phrase in INVENTED:
        assert phrase not in html, phrase
    assert "<header" not in html
    assert "<nav" not in html
    assert 'href="/login"' not in html
    assert 'href="/dashboard"' not in html
    assert 'href="/playground"' not in html
    assert 'href="/billing/subscriptions"' not in html
    browse = client.get("/browse")
    assert browse.status_code == 200
    laws = client.get("/laws")
    assert laws.status_code == 200
    playground = client.get("/playground")
    assert "data-signed-in-pg-gate" not in playground.text
    assert "My Playground" in playground.text


def test_free_signed_in_landing_is_not_plus(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/", follow_redirects=False).text
    assert 'data-guest-landing="desktop"' in html
    assert 'data-plus-landing="desktop"' not in html
    assert 'href="/browse">Explore the Constitution</a>' in html
    assert 'href="/laws">Explore Laws</a>' in html


def test_guest_landing_is_unchanged(tmp_path: Path) -> None:
    html = TestClient(_mu_app(tmp_path)).get("/", follow_redirects=False).text
    assert 'data-guest-landing="desktop"' in html
    assert 'data-plus-landing="desktop"' not in html
    assert 'href="/browse">Explore the Constitution</a>' in html
    assert "<header" not in html


def test_halted_and_pro_are_not_plus_screen_01(tmp_path: Path) -> None:
    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/", follow_redirects=False).text
    assert 'data-plus-landing="desktop"' not in halted_html
    assert 'data-guest-landing="desktop"' in halted_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/", follow_redirects=False).text
    assert 'data-plus-landing="desktop"' not in pro_html


def test_plus_landing_marker_is_conditional_in_template() -> None:
    src = LANDING.read_text(encoding="utf-8")
    assert 'data-guest-landing="desktop"' in src
    assert "plus_landing" in src
    assert 'data-plus-landing="desktop"' in src
    assert "Explore the Constitution" in src
    assert 'href="/browse"' in src
    assert 'href="/laws"' in src
    for phrase in ("Premium", "Unlimited", "RecallC Plus"):
        assert phrase not in src


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


def test_plus_landing_1280(tmp_path: Path) -> None:
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
    shot_path = artifact_dir / "plus_landing_screen01_1280.png"
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
              const desk = document.querySelector('[data-plus-landing="desktop"]');
              const primary = document.querySelector('.rc-desk-cta:not(.is-ghost)');
              const ghost = document.querySelector('.rc-desk-cta.is-ghost');
              const launch = document.querySelector('.rc-launch');
              const header = document.querySelector('header');
              const pr = primary.getBoundingClientRect();
              const gr = ghost.getBoundingClientRect();
              return {
                present: Boolean(desk),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                launchDisplay: launch ? getComputedStyle(launch).display : null,
                hasHeader: !!header,
                loginCount: document.querySelectorAll('a[href*="/login"]').length,
                plusCopy: /Premium|Unlimited|RecallC Plus|Free account/.test(
                  document.body.innerText
                ),
                mark: (document.querySelector('.rc-desk-mark') || {}).textContent,
                name: (document.querySelector('.rc-desk-name') || {}).textContent,
                tag: (document.querySelector('.rc-desk-tag') || {}).textContent,
                primaryText: primary && primary.textContent.trim(),
                ghostText: ghost && ghost.textContent.trim(),
                primaryHref: primary && primary.getAttribute('href'),
                ghostHref: ghost && ghost.getAttribute('href'),
                primaryW: pr.width, ghostW: gr.width,
                primaryH: pr.height, ghostH: gr.height,
                primaryX: pr.x, ghostX: gr.x,
                bg: desk ? getComputedStyle(desk).backgroundColor : null,
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

    assert geo["present"] is True
    assert geo["deskDisplay"] == "flex"
    assert geo["launchDisplay"] == "none"
    assert geo["hasHeader"] is False
    assert geo["loginCount"] == 0
    assert geo["plusCopy"] is False
    assert (geo["mark"] or "").strip() == "C"
    assert (geo["name"] or "").strip() == "Recall the C"
    assert (geo["tag"] or "").strip() == "The Constitution, remembered."
    assert geo["primaryText"] == "Explore the Constitution"
    assert geo["ghostText"] == "Explore Laws"
    assert geo["primaryHref"] == "/browse"
    assert geo["ghostHref"] == "/laws"
    assert geo["primaryX"] < geo["ghostX"]
    assert abs(geo["primaryW"] - geo["ghostW"]) <= 1
    assert abs(geo["primaryH"] - geo["ghostH"]) <= 1
    assert browse_url.rstrip("/").endswith("/browse")
    assert "/laws" in laws_url
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
