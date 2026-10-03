"""Guest Landing Screen 1 (desktop CTA map guest/01-screen).

Authorized: ChatGPT plan + Sanjali. Guest `/` is this dedicated landing only.
Phone `.rc-launch` is unchanged. Destinations are navigation, not auth.
"""

from __future__ import annotations

import socket
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageChops

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
REF_CTA = ROOT / "cta-map" / "cta-map" / "guest" / "01-screen.jpg"
REF_FIXTURE = Path(__file__).parent / "fixtures" / "guest_landing" / "01-screen.jpg"
SCREENSHOT_DIR = Path("/opt/cursor/artifacts")
VIEWPORT = {"width": 1280, "height": 800}


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


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _serve(app, port: int) -> threading.Thread:
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(80):
        probe = socket.socket()
        probe.settimeout(0.1)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            probe.close()
            return thread
        probe.close()
        thread.join(0.05)
    raise RuntimeError(f"server did not bind on {port}")


def _reference_image() -> Path | None:
    for path in (REF_CTA, REF_FIXTURE):
        if path.exists():
            return path
    return None


def _rms(a: Image.Image, b: Image.Image) -> float:
    if a.size != b.size:
        b = b.resize(a.size, Image.Resampling.LANCZOS)
    a = a.convert("RGB")
    b = b.convert("RGB")
    diff = ImageChops.difference(a, b)
    hist = diff.histogram()
    squares = sum(value * (idx % 256) ** 2 for idx, value in enumerate(hist))
    return (squares / (float(a.size[0]) * a.size[1])) ** 0.5


def test_screen1_1280_matches_cta_map_screenshot(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    port = _free_port()
    _serve(_guest_app(tmp_path), port)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    out = SCREENSHOT_DIR / "guest_landing_screen1_1280.png"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
        page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
        page.wait_for_timeout(400)
        geo = page.evaluate(
            """() => {
              const desk = document.querySelector('.rc-desk');
              const launch = document.querySelector('.rc-launch');
              const header = document.querySelector('header');
              const mark = document.querySelector('.rc-desk-mark');
              const name = document.querySelector('.rc-desk-name');
              const tag = document.querySelector('.rc-desk-tag');
              const primary = document.querySelector('.rc-desk-cta:not(.is-ghost)');
              const ghost = document.querySelector('.rc-desk-cta.is-ghost');
              const stack = document.querySelector('.rc-desk-stack');
              const cs = getComputedStyle(document.body);
              const box = (el) => {
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return {x: r.x, y: r.y, w: r.width, h: r.height};
              };
              return {
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                launchDisplay: launch ? getComputedStyle(launch).display : null,
                hasHeader: !!header,
                loginCount: document.querySelectorAll('a[href*="/login"]').length,
                mark: box(mark),
                name: box(name),
                tag: box(tag),
                primary: box(primary),
                ghost: box(ghost),
                stack: box(stack),
                primaryHref: primary && primary.getAttribute('href'),
                ghostHref: ghost && ghost.getAttribute('href'),
                primaryText: primary && primary.textContent.trim(),
                ghostText: ghost && ghost.textContent.trim(),
                pageBg: cs.backgroundColor,
                pageFg: cs.color,
                innerWidth: window.innerWidth,
                innerHeight: window.innerHeight,
              };
            }"""
        )
        page.screenshot(path=str(out), full_page=False)
        browser.close()

    assert geo["innerWidth"] == 1280
    assert geo["deskDisplay"] == "flex"
    assert geo["launchDisplay"] == "none"
    assert geo["hasHeader"] is False
    assert geo["loginCount"] == 0
    assert geo["primaryHref"] == "/browse"
    assert geo["ghostHref"] == "/laws"
    assert geo["primaryText"] == "Explore the Constitution"
    assert geo["ghostText"] == "Explore Laws"
    mark, primary, ghost, stack = geo["mark"], geo["primary"], geo["ghost"], geo["stack"]
    assert mark is not None and primary is not None and ghost is not None
    assert abs(mark["w"] - mark["h"]) <= 1
    assert 56 <= mark["w"] <= 72
    assert abs(primary["y"] - ghost["y"]) <= 2
    assert primary["x"] < ghost["x"]
    assert 36 <= primary["h"] <= 48
    assert primary["w"] > 160
    # Vertically centred stack (CTA map Screen 1).
    mid = stack["y"] + stack["h"] / 2
    assert abs(mid - geo["innerHeight"] / 2) < 80

    captured = Image.open(out)
    ref_path = _reference_image()
    if ref_path is None:
        pytest.fail(
            "CTA map screenshot missing "
            f"(looked for {REF_CTA} and {REF_FIXTURE})"
        )
    rms = _rms(captured, Image.open(ref_path))
    assert rms < 18, f"1280 landing diverges from CTA map Screen 1 (rms={rms:.2f})"
