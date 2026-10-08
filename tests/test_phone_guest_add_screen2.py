"""Phone Guest Add sheet Screen 02 (CTA map guest/02-screen, 390x844).

Authorized: ChatGPT. Guest GET /playground/laws/ndps/add overlay on accepted
Guest 01 /laws/ndps. Desktop 1280 guest Add dialog, signed-in Unlock,
Plus confirm, Expired/Halted recovery, and Guest 03 stay unchanged.
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
from constitution_memorizer.playground.urls import add_path
from constitution_memorizer.playground.view import KIND_GUEST
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.guest_bareact_head import (
    GUEST_ADD_TITLE,
    NDPS_GUEST_READING_NAME,
    NDPS_GUEST_TITLE,
    guest_add_reading_name,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
PG_JS = ROOT / "src/constitution_memorizer/web/static/playground.js"
USER = UUID("11111111-1111-4111-8111-111111111111")
LOGIN_NEXT = f"/login?next={add_path('ndps')}"
GUEST_LEDE = (
    f"Playground needs an account. Reading {NDPS_GUEST_READING_NAME} "
    "stays free — sign in and you’ll come right back here."
)
MAP_LEDE_LOWER_THE = (
    "Playground needs an account. Reading the NDPS Act, 1985 stays free"
)
SUBSCRIBER_CONTROLS = (
    "data-pg-add-confirm",
    'name="confirm"',
    'name="scope"',
    "Entire Act",
    "Choose sections",
    "Unlock Playground",
    "Resume Playground",
    "Manage subscription",
    "Payment retries have stopped",
    "/billing/subscriptions",
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


def _desk(html: str) -> str:
    return html.split("data-guest-add-desktop", 1)[1].split(
        "data-guest-add-phone", 1
    )[0]


def _phone(html: str) -> str:
    return html.split("data-guest-add-phone", 1)[1].split("</div>", 1)[0]


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


def test_phone_guest_add_sheet_is_guest_kind_with_source_copy(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    before = _facts(client)
    sheet = client.get(add_path("ndps"))
    assert sheet.status_code == 200
    html = unescape(sheet.text)
    assert 'data-pg-kind="guest"' in html
    assert KIND_GUEST == "guest"
    assert "data-pg-add" in html
    phone = _phone(html)
    assert GUEST_ADD_TITLE in phone
    assert phone.count(GUEST_ADD_TITLE) == 1
    assert NDPS_GUEST_READING_NAME in phone
    assert guest_add_reading_name("ndps", "NDPS Act") == NDPS_GUEST_READING_NAME
    assert GUEST_LEDE in phone
    assert MAP_LEDE_LOWER_THE not in phone
    assert ">Sign in<" in phone
    assert "Create an account" in phone
    assert ">Cancel<" not in phone
    assert "Sign in to use Playground" not in phone
    assert 'data-guest-add-gate' not in phone
    assert LOGIN_NEXT not in phone
    assert 'href="' not in phone
    assert "<form" not in phone
    assert "<a " not in phone
    assert 'type="button"' in phone
    assert phone.count('type="button"') == 2
    assert 'class="guest-add-signin"' in phone
    assert 'class="guest-add-create"' in phone
    for phrase in SUBSCRIBER_CONTROLS:
        assert phrase not in phone, phrase
    desk = _desk(html)
    assert GUEST_ADD_TITLE in desk
    assert GUEST_LEDE in desk
    assert desk.count('data-guest-add-gate') == 2
    assert desk.count(f'href="{LOGIN_NEXT}"') == 2
    assert _facts(client) == before


def test_phone_guest_add_buttons_are_handlerless_in_source() -> None:
    src = ADD.read_text(encoding="utf-8")
    phone = src.split("data-guest-add-phone", 1)[1].split("</div>", 1)[0]
    assert 'class="guest-add-title">Add to Playground<' in phone
    assert "reading_name|default(short_title)" in phone
    assert 'type="button" class="guest-add-signin">Sign in<' in phone
    assert 'type="button" class="guest-add-create">Create an account<' in phone
    assert "login_href" not in phone
    assert "data-guest-add-gate" not in phone
    assert "cancel_href" not in phone
    assert "<form" not in phone
    assert "<a " not in phone
    desk = src.split("data-guest-add-desktop", 1)[1].split(
        "data-guest-add-phone", 1
    )[0]
    assert "data-guest-add-gate" in desk
    assert "login_href" in desk
    js = PG_JS.read_text(encoding="utf-8")
    assert "guest-add-signin" not in js
    assert "guest-add-create" not in js
    assert "data-guest-add-phone" not in js
    assert "event.target === dialog" in js


def test_phone_guest_add_css_is_breakpoint_scoped() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    phone_block = css.split("is guest/02-screen:", 1)[1].split(
        "@media (min-width: 561px)", 1
    )[0]
    assert "@media (max-width: 560px)" in phone_block
    assert ":has([data-guest-add-phone])" in phone_block
    assert "width: 100%" in phone_block
    assert "justify-content: flex-end" in phone_block
    assert "[data-guest-add-phone] .guest-add-signin" in phone_block
    assert "[data-guest-add-phone] .guest-add-create" in phone_block
    generic = css.split("@media (max-width: 560px)", 1)[1].split(
        "/* R2 section/clause picker */", 1
    )[0]
    assert "width: calc(100% - (2 * var(--pg-shell-pad)))" in generic
    guest_signin = css.split("[data-guest-add-desktop] .guest-add-signin {", 1)[1].split(
        "}", 1
    )[0]
    assert "height: 50px" in guest_signin
    assert "playground.css?v=pg29" in BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg28" not in BASE.read_text(encoding="utf-8")


def test_signed_in_plus_expired_halted_add_sheets_stay_separate(
    tmp_path: Path,
) -> None:
    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get(add_path("ndps")).text
    assert "data-guest-add-phone" not in free_html
    assert "data-signed-in-add-phone" in free_html
    assert 'data-pg-kind="subscribe"' in free_html
    assert "Unlock Playground" in free_html
    assert "Create an account" not in free_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get(add_path("ndps")).text
    assert "data-guest-add-phone" not in plus_html
    assert "data-plus-add-phone" in plus_html
    assert "data-pg-add-confirm" in plus_html
    assert "Create an account" not in plus_html
    assert "Unlock Playground" not in plus_html.split("data-plus-add-phone", 1)[1]

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
    expired_html = expired.get(add_path("ndps")).text
    assert "data-guest-add-phone" not in expired_html
    assert "data-expired-add-phone" in expired_html
    assert "Create an account" not in expired_html
    assert "guest-add-signin" not in expired_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get(add_path("ndps")).text
    assert "data-guest-add-phone" not in halted_html
    assert "data-halted-add-phone" in halted_html
    assert "Payment retries have stopped" in halted_html
    assert "Create an account" not in halted_html
    assert "Manage subscription" in halted_html


def test_phone_guest_gets_are_mutation_free(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    before = _facts(client)
    assert before["session"] is None
    assert before["subscription"] is None
    for _ in range(3):
        for url in ("/laws/ndps", add_path("ndps")):
            page = client.get(url)
            assert page.status_code == 200
            assert _facts(client) == before


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


def test_phone_guest_add_screen02_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_guest_add_screen02_390x844.png"
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
        page.on(
            "request",
            lambda req: requests.append(f"{req.method} {req.url}"),
        )
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        background = page.evaluate(
            """() => {
              const phone = document.querySelector('[data-guest-bareact-phone]');
              return {
                title: phone && phone.querySelector('.guest-bareact-title').textContent.trim(),
                tabs: Boolean(document.querySelector('[data-guest-bareact-phone-tabs]')),
              };
            }"""
        )
        page.locator("[data-guest-bareact-phone] .guest-bareact-cta").click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='guest']", timeout=8000)
        page.wait_for_timeout(400)
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const desk = panel.querySelector('[data-guest-add-desktop]');
              const phoneBlock = panel.querySelector('[data-guest-add-phone]');
              const signin = phoneBlock && phoneBlock.querySelector('.guest-add-signin');
              const create = phoneBlock && phoneBlock.querySelector('.guest-add-create');
              const closeBtn = panel.querySelector('.pg-sheet-close');
              const tabs = document.querySelector('[data-guest-bareact-phone-tabs]');
              const handle = getComputedStyle(panel, '::before');
              const d = dialog.getBoundingClientRect();
              const p = panel.getBoundingClientRect();
              return {
                open: Boolean(dialog && dialog.open),
                kind: panel.getAttribute('data-pg-kind'),
                url: location.pathname,
                deskDisplay: getComputedStyle(desk).display,
                phoneDisplay: getComputedStyle(phoneBlock).display,
                title: phoneBlock.querySelector('.guest-add-title').textContent.trim(),
                lede: phoneBlock.querySelector('.guest-add-lede').textContent.trim(),
                signin: {
                  tag: signin.tagName,
                  type: signin.getAttribute('type'),
                  href: signin.getAttribute('href'),
                  text: signin.textContent.trim(),
                  gate: signin.hasAttribute('data-guest-add-gate'),
                  form: Boolean(signin.closest('form')),
                  width: signin.getBoundingClientRect().width,
                  bg: getComputedStyle(signin).backgroundColor,
                },
                create: {
                  tag: create.tagName,
                  type: create.getAttribute('type'),
                  href: create.getAttribute('href'),
                  text: create.textContent.trim(),
                  gate: create.hasAttribute('data-guest-add-gate'),
                  form: Boolean(create.closest('form')),
                  width: create.getBoundingClientRect().width,
                  bg: getComputedStyle(create).backgroundColor,
                  border: getComputedStyle(create).borderTopWidth,
                },
                closeDisplay: closeBtn ? getComputedStyle(closeBtn).display : 'missing',
                handleDisplay: handle.display,
                handleHeight: handle.height,
                dialog: { top: d.top, left: d.left, width: d.width, height: d.height },
                panel: { top: p.top, left: p.left, width: p.width, bottom: p.bottom },
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                backgroundTitle: document.querySelector('[data-guest-bareact-phone] .guest-bareact-title')
                  && document.querySelector('[data-guest-bareact-phone] .guest-bareact-title').textContent.trim(),
                confirm: Boolean(panel.querySelector('[data-pg-add-confirm]')),
                radius: getComputedStyle(panel).borderTopLeftRadius,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        n_before_click = len(requests)
        page.locator("[data-guest-add-phone] .guest-add-signin").click()
        page.wait_for_timeout(250)
        after_signin = page.evaluate(
            "() => ({ url: location.pathname, open: document.querySelector('dialog.pg-sheet').open })"
        )
        page.locator("[data-guest-add-phone] .guest-add-create").click()
        page.wait_for_timeout(250)
        after_create = page.evaluate(
            "() => ({ url: location.pathname, open: document.querySelector('dialog.pg-sheet').open })"
        )
        extra = requests[n_before_click:]

        panel_top = geo["panel"]["top"]
        page.mouse.click(195, max(20, panel_top - 40))
        page.wait_for_timeout(250)
        closed = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              return {
                open: Boolean(dialog && dialog.open),
                url: location.pathname,
                title: document.querySelector('[data-guest-bareact-phone] .guest-bareact-title')
                  && document.querySelector('[data-guest-bareact-phone] .guest-bareact-title').textContent.trim(),
                scroll: window.scrollY,
              };
            }"""
        )

        page.locator("[data-guest-bareact-phone] .guest-bareact-cta").click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='guest']", timeout=8000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        escaped = page.evaluate(
            """() => ({
              open: Boolean(document.querySelector('dialog.pg-sheet') && document.querySelector('dialog.pg-sheet').open),
              url: location.pathname,
            })"""
        )
        browser.close()

    assert background["title"] == NDPS_GUEST_TITLE
    assert background["tabs"] is True
    assert geo["open"] is True
    assert geo["kind"] == KIND_GUEST
    assert geo["url"] == "/laws/ndps"
    assert geo["deskDisplay"] == "none"
    assert geo["phoneDisplay"] != "none"
    assert geo["title"] == GUEST_ADD_TITLE
    assert geo["lede"] == GUEST_LEDE
    assert geo["signin"]["tag"] == "BUTTON"
    assert geo["signin"]["type"] == "button"
    assert geo["signin"]["href"] is None
    assert geo["signin"]["text"] == "Sign in"
    assert geo["signin"]["gate"] is False
    assert geo["signin"]["form"] is False
    assert geo["signin"]["width"] >= 300
    assert geo["create"]["tag"] == "BUTTON"
    assert geo["create"]["type"] == "button"
    assert geo["create"]["href"] is None
    assert geo["create"]["text"] == "Create an account"
    assert geo["create"]["gate"] is False
    assert geo["create"]["form"] is False
    assert geo["create"]["width"] >= 300
    assert geo["closeDisplay"] == "none"
    assert geo["handleDisplay"] == "block"
    assert geo["dialog"]["width"] >= 389
    assert geo["dialog"]["left"] <= 1
    assert geo["dialog"]["top"] <= 1
    assert geo["panel"]["left"] <= 1
    assert geo["panel"]["width"] >= 389
    assert geo["panel"]["bottom"] >= 840
    assert geo["panel"]["top"] > 400
    assert geo["overflow"] is False
    assert geo["backgroundTitle"] == NDPS_GUEST_TITLE
    assert geo["confirm"] is False
    assert after_signin["url"] == "/laws/ndps"
    assert after_signin["open"] is True
    assert after_create["url"] == "/laws/ndps"
    assert after_create["open"] is True
    assert not any("/login" in item for item in extra)
    assert not any(item.startswith("POST ") for item in extra)
    assert closed["open"] is False
    assert closed["url"] == "/laws/ndps"
    assert closed["title"] == NDPS_GUEST_TITLE
    assert escaped["open"] is False
    assert escaped["url"] == "/laws/ndps"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_guest_add_screen02_desktop_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_guest_add_screen02_desktop_regression_1280.png"
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
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        page.locator("[data-guest-bareact-desktop] .guest-bareact-cta").click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='guest']", timeout=8000)
        page.wait_for_timeout(300)
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const desk = panel.querySelector('[data-guest-add-desktop]');
              const phoneBlock = panel.querySelector('[data-guest-add-phone]');
              const gates = [...desk.querySelectorAll('[data-guest-add-gate]')];
              const d = dialog.getBoundingClientRect();
              const p = panel.getBoundingClientRect();
              const closeBtn = panel.querySelector('.pg-sheet-close');
              return {
                open: Boolean(dialog && dialog.open),
                deskDisplay: getComputedStyle(desk).display,
                phoneDisplay: getComputedStyle(phoneBlock).display,
                title: desk.querySelector('.guest-add-title').textContent.trim(),
                lede: desk.querySelector('.guest-add-lede').textContent.trim(),
                labels: gates.map((el) => el.textContent.trim()),
                tags: gates.map((el) => el.tagName),
                hrefs: gates.map((el) => el.getAttribute('href')),
                closeDisplay: closeBtn ? getComputedStyle(closeBtn).display : 'missing',
                dialogWidth: d.width,
                panelBottom: p.bottom,
                panelTop: p.top,
                notFullBleed: d.width < 800 && d.left > 100,
                centered: Math.abs((d.top + d.bottom) / 2 - 400) < 120,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["open"] is True
    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["title"] == GUEST_ADD_TITLE
    assert geo["lede"] == GUEST_LEDE
    assert geo["labels"] == ["Sign in", "Create an account"]
    assert geo["tags"] == ["A", "A"]
    assert geo["hrefs"] == [LOGIN_NEXT, LOGIN_NEXT]
    assert geo["closeDisplay"] != "none"
    assert geo["notFullBleed"] is True
    assert geo["centered"] is True
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
