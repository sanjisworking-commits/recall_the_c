"""Guest desktop Add dialog Screen 5 (CTA map guest/05-screen).

Authorized: ChatGPT plan. Guest `/laws/ndps` desktop sheet only. Phone guest
Add sheet, Bare Act readers, Landing, Browse, Laws index, and subscriber
sheets stay unchanged.
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
from constitution_memorizer.playground.urls import add_path
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.guest_bareact_head import (
    GUEST_ADD_TITLE,
    NDPS_GUEST_READING_NAME,
    NDPS_GUEST_TITLE,
    guest_add_reading_name,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
LOGIN_NEXT = f"/login?next={add_path('ndps')}"


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


def _guest_desk_add(html: str) -> str:
    return html.split("data-guest-add-desktop", 1)[1].split(
        "data-guest-add-phone", 1
    )[0]


def _guest_phone_add(html: str) -> str:
    return html.split("data-guest-add-phone", 1)[1]


def test_screen5_desktop_copy_and_gate_actions(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get(add_path("ndps")).text
    desk = _guest_desk_add(html)
    assert GUEST_ADD_TITLE in desk
    assert NDPS_GUEST_READING_NAME in desk
    assert "Playground needs an account" in desk
    assert "stays free" in desk
    assert "come right back here" in desk
    assert desk.count('data-guest-add-gate') == 2
    assert f'href="{LOGIN_NEXT}"' in desk
    assert desk.count(f'href="{LOGIN_NEXT}"') == 2
    assert ">Sign in<" in desk
    assert "Create an account" in desk
    assert ">Cancel<" not in desk
    assert "Already in Playground" not in desk
    assert ">Sections<" not in desk
    assert ">Continue<" not in desk
    assert guest_add_reading_name("ndps", "NDPS Act") == NDPS_GUEST_READING_NAME


def test_screen5_phone_guest_sheet_keeps_sign_in_and_cancel(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get(add_path("ndps")).text
    phone = _guest_phone_add(html)
    assert "Sign in to use Playground" in phone
    assert ">Cancel<" in phone
    assert f'href="{LOGIN_NEXT}"' in phone
    assert f'href="/laws/ndps"' in phone
    assert "Create an account" not in phone
    assert GUEST_ADD_TITLE not in phone


def test_screen5_does_not_restore_subscriber_ctas_on_ndps_head(tmp_path: Path) -> None:
    desk = _guest_client(tmp_path).get("/laws/ndps").text.split(
        "data-guest-bareact-desktop", 1
    )[1].split("data-bareact-phone", 1)[0]
    assert "Sign in to use Playground" in desk
    assert "Already in Playground" not in desk
    assert ">Sections<" not in desk
    assert ">Continue<" not in desk
    assert NDPS_GUEST_TITLE in desk


def test_screen5_does_not_change_other_screens(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    landing = client.get("/").text
    assert 'data-guest-landing="desktop"' in landing
    browse = client.get("/browse").text
    assert "Browse the Constitution" in browse
    laws = client.get("/laws").text
    assert "data-guest-laws-desktop" in laws
    bns = client.get("/laws/bns").text
    assert "data-guest-bareact-desktop" not in bns
    section = client.get("/laws/ndps/section/1").text
    assert "data-guest-bareact-desktop" not in section
    css = (ROOT / "src/constitution_memorizer/web/static/styles.css").read_text(
        encoding="utf-8"
    )
    guest_grid = css.split(
        'body.is-guest[data-mscreen="browse"] .browse-resource-grid {', 1
    )[1].split("}", 1)[0]
    assert "calc(200% / 3)" in guest_grid


def test_single_user_add_sheet_is_unchanged(tmp_path: Path) -> None:
    html = TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    ).get(add_path("ndps")).text
    assert "data-guest-add-desktop" not in html
    assert "Create an account" not in html
    assert "data-pg-add-confirm" in html


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


def test_screen5_1280_dialog_gate_and_close(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "guest_add_screen5_1280.png"
    close_path = artifact_dir / "guest_add_screen5_closed_ndps.png"
    signin_path = artifact_dir / "guest_add_screen5_gate_signin.png"
    create_path = artifact_dir / "guest_add_screen5_gate_create.png"
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

        def open_dialog():
            page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
            page.evaluate(
                """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
            )
            page.locator("[data-guest-bareact-desktop] .guest-bareact-cta").click()
            page.wait_for_selector("[data-pg-add][data-pg-kind='guest']", timeout=8000)

        open_dialog()
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const desk = panel.querySelector('[data-guest-add-desktop]');
              const phone = panel.querySelector('[data-guest-add-phone]');
              const gates = [...desk.querySelectorAll('[data-guest-add-gate]')];
              const head = document.querySelector('[data-guest-bareact-desktop]');
              return {
                open: dialog && dialog.open,
                deskDisplay: getComputedStyle(desk).display,
                phoneDisplay: getComputedStyle(phone).display,
                eyebrowDisplay: getComputedStyle(panel.querySelector('.pg-eyebrow')).display,
                title: desk.querySelector('.guest-add-title').textContent.trim(),
                lede: desk.querySelector('.guest-add-lede').textContent.trim(),
                labels: gates.map((el) => el.textContent.trim()),
                hrefs: gates.map((el) => el.getAttribute('href')),
                hasClose: Boolean(panel.querySelector('[data-pg-sheet-close]')),
                leaked: {
                  already: head.innerText.includes('Already in Playground'),
                  sections: [...head.querySelectorAll('a')].some((a) => a.textContent.trim() === 'Sections'),
                  continue: [...head.querySelectorAll('a')].some((a) => a.textContent.trim() === 'Continue'),
                },
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator("[data-guest-add-desktop] .guest-add-signin").click()
        page.wait_for_url("**/login**", timeout=8000)
        signin_url = page.url
        signin_html = page.content()
        page.screenshot(path=str(signin_path), full_page=False)

        open_dialog()
        page.locator("[data-guest-add-desktop] .guest-add-create").click()
        page.wait_for_url("**/login**", timeout=8000)
        create_url = page.url
        create_html = page.content()
        page.screenshot(path=str(create_path), full_page=False)

        open_dialog()
        page.locator("[data-pg-sheet-close]").click()
        closed = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              return {
                open: Boolean(dialog && dialog.open),
                url: location.pathname,
                head: Boolean(document.querySelector('[data-guest-bareact-desktop]')),
              };
            }"""
        )
        page.screenshot(path=str(close_path), full_page=False)

        phone = browser.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        phone.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        phone.locator("[data-bareact-phone] [data-pg-sheet]").first.click()
        phone.wait_for_selector("[data-pg-add]", timeout=8000)
        phone_geo = phone.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const desk = panel.querySelector('[data-guest-add-desktop]');
              const phoneBlock = panel.querySelector('[data-guest-add-phone]');
              return {
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                phoneDisplay: phoneBlock ? getComputedStyle(phoneBlock).display : null,
                title: phoneBlock && phoneBlock.querySelector('h1') && phoneBlock.querySelector('h1').textContent.trim(),
                hasCancel: Boolean(phoneBlock && [...phoneBlock.querySelectorAll('a')].some((a) => a.textContent.trim() === 'Cancel')),
                createVisible: Boolean(
                  desk && getComputedStyle(desk).display !== 'none'
                  && desk.textContent.includes('Create an account')
                ),
              };
            }"""
        )
        browser.close()

    assert geo["open"] is True
    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["eyebrowDisplay"] == "none"
    assert geo["title"] == GUEST_ADD_TITLE
    assert NDPS_GUEST_READING_NAME in geo["lede"]
    assert geo["labels"] == ["Sign in", "Create an account"]
    assert geo["hrefs"] == [LOGIN_NEXT, LOGIN_NEXT]
    assert geo["hasClose"] is True
    assert geo["leaked"]["already"] is False
    assert geo["leaked"]["sections"] is False
    assert geo["leaked"]["continue"] is False
    assert "/login" in signin_url
    assert add_path("ndps") in signin_url
    assert "data-auth-grid" in signin_html
    assert "/login" in create_url
    assert add_path("ndps") in create_url
    assert "data-auth-grid" in create_html
    assert closed["open"] is False
    assert closed["url"] == "/laws/ndps"
    assert closed["head"] is True
    assert phone_geo["deskDisplay"] == "none"
    assert phone_geo["phoneDisplay"] != "none"
    assert phone_geo["title"] == "Sign in to use Playground"
    assert phone_geo["hasCancel"] is True
    assert phone_geo["createVisible"] is False
    assert shot_path.is_file()
