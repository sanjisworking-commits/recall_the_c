"""Signed-in desktop subscribe Add dialog (CTA map signedIn/05-screen).

Authorized: ChatGPT. Authenticated multiuser non-subscriber GET
/playground/laws/ndps/add desktop overlay only. Phone subscribe sheet,
guest Add, Bare Act head, Landing, Browse, and Laws stay unchanged.
Unlock Playground opens the existing Gate. X / Cancel / Close dismiss only.
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
from constitution_memorizer.playground.urls import add_path, home_path
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
USER = UUID("11111111-1111-4111-8111-111111111111")
LEDE = (
    "Turning NDPS Act into a learning experience needs a plan. "
    "Reading it stays free."
)
NOTE = "from ₹199 / month. Constitution learning stays included with your account."


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
    return html.split("data-signed-in-add-desktop", 1)[1].split(
        "data-signed-in-add-phone", 1
    )[0]


def _phone(html: str) -> str:
    return html.split("data-signed-in-add-phone", 1)[1].split("</div>", 1)[0]


def test_signed_in_add_desktop_is_subscribe_only(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get(add_path("ndps")).text
    assert 'data-pg-kind="subscribe"' in html
    assert "data-signed-in-add-desktop" in html
    assert "data-guest-add-desktop" not in html
    desk = _desk(html)
    assert ">Unlock Playground<" in desk
    assert desk.count("Unlock Playground") == 2
    assert LEDE in desk
    assert NOTE in desk
    assert f'href="{home_path()}"' in desk
    assert 'class="signed-add-unlock"' in desk
    assert 'data-pg-sheet-close' in desk
    assert ">Cancel<" in desk
    assert "/billing/subscriptions" not in desk
    assert "Sign in to use Playground" not in desk
    assert "Create an account" not in desk
    assert "Resume Playground" not in desk
    assert "Playground full this month" not in desk
    assert "temporarily unavailable" not in desk
    assert "Device limit" not in desk
    assert "Entire Act" not in desk
    assert "Choose sections" not in desk
    assert "Already in Playground" not in desk
    assert ">Sections<" not in desk
    assert ">Continue<" not in desk


def test_signed_in_add_phone_keeps_billing_and_cancel_href(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    phone = _phone(client.get(add_path("ndps")).text)
    assert ">Unlock Playground<" in phone
    assert 'href="/billing/subscriptions"' in phone
    assert f'href="/laws/ndps"' in phone
    assert ">Cancel<" in phone
    assert 'data-pg-sheet-close' not in phone
    assert f'href="{home_path()}"' not in phone
    assert "Create an account" not in phone


def test_signed_in_add_unlock_opens_existing_gate(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    desk = _desk(client.get(add_path("ndps")).text)
    assert f'href="{home_path()}"' in desk
    gate = client.get(home_path(), follow_redirects=False)
    assert gate.status_code == 200
    assert 'class="EntitlementGate"' in gate.text
    assert 'data-playground-gate="not_subscribed"' in gate.text
    assert "Unlock Playground" in gate.text


def test_signed_in_add_does_not_touch_accepted_screens() -> None:
    assert "data-signed-in-add-desktop" not in BARE.read_text(encoding="utf-8")
    assert 'data-signed-in-bareact-desktop' in BARE.read_text(encoding="utf-8")
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-guest-landing="desktop"' in landing
    browse = BROWSE.read_text(encoding="utf-8")
    assert "data-signed-in-browse-strip" in browse
    laws = LAWS.read_text(encoding="utf-8")
    assert "data-signed-in-laws-desktop" in laws
    css = STYLES.read_text(encoding="utf-8")
    headband = css.split(
        "[data-signed-in-bareact-desktop] .guest-bareact-headband {", 1
    )[1].split("}", 1)[0]
    assert "12px 40px 14px" in headband
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-signed-in-add-desktop" not in mobile
    pg_css = (
        ROOT / "src/constitution_memorizer/web/static/playground.css"
    ).read_text(encoding="utf-8")
    guest_block = pg_css.split("[data-guest-add-desktop] .guest-add-title {", 1)[1].split(
        "[data-guest-add-desktop] .guest-add-lede {", 1
    )[0]
    assert "font-size: 22px" in guest_block
    assert "font-weight: 500" in guest_block
    guest_btn = pg_css.split("[data-guest-add-desktop] .guest-add-signin {", 1)[1].split(
        ".PlaygroundShell [data-guest-add-desktop] .guest-add-signin {", 1
    )[0]
    assert "height: 50px" in guest_btn
    signed_title = pg_css.split(
        "[data-signed-in-add-desktop] .signed-add-title {", 1
    )[1].split("}", 1)[0]
    assert "font-size: 20px" in signed_title
    assert "font-weight: 400" in signed_title
    assert "font-size: 22px" not in signed_title


def test_signed_in_add_does_not_change_guest_or_other_kinds(tmp_path: Path) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest"))
    guest_html = guest.get(add_path("ndps")).text
    assert "data-guest-add-desktop" in guest_html
    assert "data-signed-in-add-desktop" not in guest_html
    assert "Create an account" in guest_html
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    bns = client.get(add_path("bns")).text
    assert "data-signed-in-add-desktop" in bns
    assert 'data-pg-kind="subscribe"' in bns
    resume = client.get("/playground").text
    assert "Resume Playground" not in _desk(client.get(add_path("ndps")).text)


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


def test_signed_in_add_1280_gate_and_close(tmp_path: Path) -> None:
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
    shot_path = artifact_dir / "signed_in_add_screen5_density_1280.png"
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
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )

        def open_dialog():
            page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
            page.evaluate(
                """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
            )
            page.locator("[data-signed-in-bareact-desktop] .guest-bareact-cta").click()
            page.wait_for_selector("[data-pg-add][data-pg-kind='subscribe']", timeout=8000)

        open_dialog()
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const desk = panel.querySelector('[data-signed-in-add-desktop]');
              const phone = panel.querySelector('[data-signed-in-add-phone]');
              const unlock = desk.querySelector('.signed-add-unlock');
              const cancel = desk.querySelector('.signed-add-cancel');
              const closeBtn = panel.querySelector('[data-pg-sheet-close].pg-sheet-close');
              const head = document.querySelector('[data-signed-in-bareact-desktop]');
              const box = panel.getBoundingClientRect();
              const note = desk.querySelector('.signed-add-note');
              const titleEl = desk.querySelector('.signed-add-title');
              const ledeEl = desk.querySelector('.signed-add-lede');
              const closeStyle = closeBtn && getComputedStyle(closeBtn);
              const panelStyle = getComputedStyle(panel);
              const backdrop = getComputedStyle(dialog, '::backdrop');
              return {
                open: dialog && dialog.open,
                kind: panel.getAttribute('data-pg-kind'),
                deskDisplay: getComputedStyle(desk).display,
                phoneDisplay: getComputedStyle(phone).display,
                eyebrowDisplay: getComputedStyle(panel.querySelector('.pg-eyebrow')).display,
                title: titleEl.textContent.trim(),
                titleSize: getComputedStyle(titleEl).fontSize,
                titleWeight: getComputedStyle(titleEl).fontWeight,
                lede: ledeEl.textContent.trim(),
                ledeMarginBottom: getComputedStyle(ledeEl).marginBottom,
                unlockText: unlock.textContent.trim(),
                unlockHref: unlock.getAttribute('href'),
                unlockH: unlock.getBoundingClientRect().height,
                unlockShadow: getComputedStyle(unlock).boxShadow,
                note: note && note.textContent.trim(),
                noteAlign: note && getComputedStyle(note).textAlign,
                noteMarginTop: note && getComputedStyle(note).marginTop,
                cancelDisplay: cancel ? getComputedStyle(cancel).display : null,
                cancelCloses: cancel && cancel.hasAttribute('data-pg-sheet-close'),
                hasClose: Boolean(closeBtn),
                closeLabel: closeBtn && closeBtn.getAttribute('aria-label'),
                closeTop: closeStyle && closeStyle.top,
                closeRight: closeStyle && closeStyle.right,
                panelW: box.width,
                panelH: box.height,
                panelRadius: panelStyle.borderRadius,
                panelPad: panelStyle.padding,
                scrim: backdrop.backgroundColor,
                guestAdd: Boolean(panel.querySelector('[data-guest-add-desktop]')),
                leaked: {
                  already: panel.innerText.includes('Already in Playground'),
                  resume: panel.innerText.includes('Resume Playground'),
                  full: panel.innerText.includes('Playground full'),
                  pending: panel.innerText.includes('temporarily unavailable'),
                  entire: panel.innerText.includes('Entire Act'),
                  signin: panel.innerText.includes('Create an account'),
                },
                background: Boolean(head),
                subscribeCta: head && head.querySelector('.guest-bareact-cta') &&
                  head.querySelector('.guest-bareact-cta').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator("[data-signed-in-add-desktop] .signed-add-unlock").click()
        page.wait_for_url("**/playground**", timeout=8000)
        gate = page.evaluate(
            """() => {
              const gate = document.querySelector('.EntitlementGate');
              return {
                path: location.pathname,
                present: Boolean(gate),
                reason: gate && gate.getAttribute('data-playground-gate'),
                title: gate && gate.querySelector('h1') && gate.querySelector('h1').textContent.trim(),
              };
            }"""
        )

        open_dialog()
        page.locator(".pg-sheet-close").click()
        closed_x = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              return {
                open: Boolean(dialog && dialog.open),
                path: location.pathname,
                head: Boolean(document.querySelector('[data-signed-in-bareact-desktop]')),
                focused: document.activeElement &&
                  document.activeElement.classList.contains('guest-bareact-cta'),
              };
            }"""
        )

        open_dialog()
        page.evaluate(
            """() => document.querySelector('[data-signed-in-add-desktop] .signed-add-cancel').click()"""
        )
        closed_cancel = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              return {
                open: Boolean(dialog && dialog.open),
                path: location.pathname,
              };
            }"""
        )

        open_dialog()
        page.keyboard.press("Escape")
        closed_esc = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              return Boolean(dialog && dialog.open);
            }"""
        )

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.locator("[data-bareact-phone] [data-pg-sheet]").first.click()
        page.wait_for_selector("[data-pg-add]", timeout=8000)
        phone_geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const desk = panel.querySelector('[data-signed-in-add-desktop]');
              const phoneBlock = panel.querySelector('[data-signed-in-add-phone]');
              const unlock = phoneBlock && phoneBlock.querySelector('a.pg-btn');
              const cancel = phoneBlock && [...phoneBlock.querySelectorAll('a')].find(
                (a) => a.textContent.trim() === 'Cancel'
              );
              return {
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                phoneDisplay: phoneBlock ? getComputedStyle(phoneBlock).display : null,
                title: phoneBlock && phoneBlock.querySelector('h1') &&
                  phoneBlock.querySelector('h1').textContent.trim(),
                unlockHref: unlock && unlock.getAttribute('href'),
                cancelHref: cancel && cancel.getAttribute('href'),
                cancelCloses: cancel && cancel.hasAttribute('data-pg-sheet-close'),
              };
            }"""
        )
        browser.close()

    assert geo["open"] is True
    assert geo["kind"] == "subscribe"
    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["eyebrowDisplay"] == "none"
    assert geo["title"] == "Unlock Playground"
    assert geo["titleSize"] == "20px"
    assert geo["titleWeight"] in ("400", "normal")
    assert geo["lede"] == LEDE
    assert geo["ledeMarginBottom"] == "14px"
    assert geo["unlockText"] == "Unlock Playground"
    assert geo["unlockHref"] == home_path()
    assert geo["unlockH"] == pytest.approx(44, abs=2)
    assert NOTE in (geo["note"] or "")
    assert geo["noteAlign"] == "center"
    assert geo["noteMarginTop"] == "8px"
    assert geo["cancelDisplay"] == "none"
    assert geo["cancelCloses"] is True
    assert geo["hasClose"] is True
    assert geo["closeLabel"] == "Close"
    assert geo["closeTop"] == "14px"
    assert geo["closeRight"] == "14px"
    assert geo["panelW"] == pytest.approx(460, abs=8)
    assert "14px" in geo["panelRadius"]
    assert "16px" not in geo["panelRadius"]
    assert "20px" in geo["panelPad"]
    assert "24px" in geo["panelPad"]
    assert "0.28" in (geo["scrim"] or "") or "rgba(20, 20, 20, 0.28)" in (geo["scrim"] or "")
    assert geo["guestAdd"] is False
    assert geo["leaked"]["already"] is False
    assert geo["leaked"]["resume"] is False
    assert geo["leaked"]["full"] is False
    assert geo["leaked"]["pending"] is False
    assert geo["leaked"]["entire"] is False
    assert geo["leaked"]["signin"] is False
    assert geo["background"] is True
    assert geo["subscribeCta"] == "Subscribe to use Playground"
    assert gate["path"] == home_path()
    assert gate["present"] is True
    assert gate["reason"] == "not_subscribed"
    assert gate["title"] == "Unlock Playground"
    assert closed_x["open"] is False
    assert closed_x["path"] == "/laws/ndps"
    assert closed_x["head"] is True
    assert closed_x["focused"] is True
    assert closed_cancel["open"] is False
    assert closed_cancel["path"] == "/laws/ndps"
    assert closed_esc is False
    assert phone_geo["deskDisplay"] == "none"
    assert phone_geo["phoneDisplay"] != "none"
    assert phone_geo["title"] == "Unlock Playground"
    assert phone_geo["unlockHref"] == "/billing/subscriptions"
    assert phone_geo["cancelHref"] == "/laws/ndps"
    assert phone_geo["cancelCloses"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
