"""Phone signed-in Free Add sheet Screen 02 (CTA map signedIn/02-screen).

Authorized: ChatGPT. Authenticated Free overlay on signedIn 01 /laws/ndps.
Unlock Playground navigates to GET /playground (existing not_subscribed
Gate). Guest 02, desktop Add 05, Plus confirm/scope, Expired/Halted, and
signedIn 01 head stay unchanged. Gate restyle is signedIn 03.
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
from constitution_memorizer.playground.urls import add_path, home_path
from constitution_memorizer.playground.view import KIND_SUBSCRIBE, catalogue_from_price
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.guest_bareact_head import NDPS_GUEST_TITLE

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
PG_JS = ROOT / "src/constitution_memorizer/web/static/playground.js"
USER = UUID("11111111-1111-4111-8111-111111111111")
TITLE = "Unlock Playground"
LEDE = (
    "Turning NDPS Act into a learning experience needs a plan. "
    "Reading it stays free."
)
MAP_LEDE_FULL = (
    "Turning The NDPS Act, 1985 into a learning experience needs a plan."
)
NOTE = "from ₹199 / month. Constitution learning stays included with your account."
GATE_TITLE = "Your RecallC account already includes the complete Constitution."
FORBIDDEN = (
    "Already in Playground",
    ">Sections<",
    ">Continue<",
    "Sign in to use Playground",
    "Create an account",
    "Resume Playground",
    "Entire Act",
    "Choose sections",
    "Core",
    "Deep",
    "Infinite",
    "₹149",
    "₹299",
    "₹499",
    ">Cancel<",
    "/billing/subscriptions",
    "/playground?stage=plans",
    "/billing/subscriptions/checkout",
    "/billing/subscriptions/create",
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


def _guest_app(tmp_path: Path):
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=FakeAuthProvider(),
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


def _free_client(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    return client


def _desk(html: str) -> str:
    return html.split("data-signed-in-add-desktop", 1)[1].split(
        "data-signed-in-add-phone", 1
    )[0]


def _phone(html: str) -> str:
    return html.split("data-signed-in-add-phone", 1)[1].split("</div>", 1)[0]


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


def test_phone_signed_in_add_sheet_unlocks_via_playground(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    before = _facts(client)
    sheet = client.get(add_path("ndps"))
    assert sheet.status_code == 200
    html = unescape(sheet.text)
    assert 'data-pg-kind="subscribe"' in html
    assert KIND_SUBSCRIBE == "subscribe"
    assert "data-pg-add" in html
    assert "data-signed-in-add-phone" in html
    phone = _phone(html)
    assert TITLE in phone
    assert phone.count(TITLE) == 2
    assert LEDE in phone
    assert MAP_LEDE_FULL not in phone
    assert NOTE in phone
    assert catalogue_from_price() == "from ₹199"
    assert f'href="{home_path()}"' in phone
    assert 'class="signed-add-unlock"' in phone
    assert 'href="/billing/subscriptions"' not in phone
    assert 'href="/playground?stage=plans"' not in phone
    assert ">Cancel<" not in phone
    assert "cancel_href" not in phone
    assert "<form" not in phone
    assert "data-pg-add-confirm" not in phone
    assert "data-guest-add-phone" not in html
    for phrase in FORBIDDEN:
        assert phrase not in phone, phrase
    desk = _desk(html)
    assert f'href="{home_path()}"' in desk
    assert 'href="/billing/subscriptions"' not in desk
    assert _facts(client) == before


def test_phone_signed_in_add_source_has_no_billing_or_cancel() -> None:
    src = ADD.read_text(encoding="utf-8")
    phone = src.split("data-signed-in-add-phone", 1)[1].split("</div>", 1)[0]
    assert 'class="signed-add-title">Unlock Playground<' in phone
    assert "short_title" in phone
    assert 'class="signed-add-unlock" href="/playground">Unlock Playground<' in phone
    assert "billing" not in phone
    assert "cancel_href" not in phone
    assert ">Cancel<" not in phone
    assert "<form" not in phone
    desk = src.split("data-signed-in-add-desktop", 1)[1].split(
        "data-signed-in-add-phone", 1
    )[0]
    assert 'href="/playground">Unlock Playground</a>' in desk
    assert "signed-add-cancel" in desk
    js = PG_JS.read_text(encoding="utf-8")
    assert "signed-add-unlock" not in js
    assert "data-signed-in-add-phone" not in js
    assert "event.target === dialog" in js


def test_phone_signed_in_add_css_is_breakpoint_scoped() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    phone_block = css.split("is signedIn/02-screen:", 1)[1].split(
        "@media (min-width: 561px)", 1
    )[0]
    assert "@media (max-width: 560px)" in phone_block
    assert ":has([data-signed-in-add-phone])" in phone_block
    assert "width: 100%" in phone_block
    assert "justify-content: flex-end" in phone_block
    assert "max-height: min(92dvh, 100%)" in phone_block
    assert "overflow-y: auto" in phone_block
    assert "overflow-x: hidden" in phone_block
    assert "safe-area-inset-bottom" in phone_block
    assert "[data-signed-in-add-phone] .signed-add-unlock" in phone_block
    assert ":has([data-guest-add-phone])" not in phone_block
    assert ":has([data-plus-add-phone])" not in phone_block
    generic = css.split("@media (max-width: 560px)", 1)[1].split(
        "/* R2 section/clause picker */", 1
    )[0]
    assert "width: calc(100% - (2 * var(--pg-shell-pad)))" in generic
    desk_unlock = css.split(
        "[data-signed-in-add-desktop] .signed-add-unlock {", 1
    )[1].split("}", 1)[0]
    assert "height: 44px" in desk_unlock
    assert "playground.css?v=pg41" in BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg32" not in BASE.read_text(encoding="utf-8")
    assert "styles.css?v=main86" in BASE.read_text(encoding="utf-8")
    assert "mobile.css?v=mob105" in BASE.read_text(encoding="utf-8")


def test_guest_plus_expired_halted_add_sheets_stay_separate(tmp_path: Path) -> None:
    guest = TestClient(_guest_app(tmp_path / "guest"))
    guest_html = guest.get(add_path("ndps")).text
    assert "data-guest-add-phone" in guest_html
    assert "data-signed-in-add-phone" not in guest_html
    assert "Sign in" in guest_html.split("data-guest-add-phone", 1)[1]

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get(add_path("ndps")).text
    assert "data-signed-in-add-phone" not in plus_html
    assert "data-plus-add-phone" in plus_html
    assert "data-pg-add-confirm" in plus_html
    assert "Unlock Playground" not in plus_html.split("data-plus-add-phone", 1)[1]
    assert "Entire Act" in plus_html
    assert "Choose sections" in plus_html

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
    assert "data-signed-in-add-phone" not in expired_html
    assert "data-expired-add-phone" in expired_html
    assert "Unlock Playground" not in expired_html.split("data-expired-add-phone", 1)[1]

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get(add_path("ndps")).text
    assert "data-signed-in-add-phone" not in halted_html
    assert "data-halted-add-phone" in halted_html
    assert "Payment retries have stopped" in halted_html
    assert "Manage subscription" in halted_html


def test_phone_signed_in_add_gets_are_mutation_free(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    before = _facts(client)
    assert before["session"] is not None
    assert before["subscription"] is None
    assert before["active"] == ()
    for url in ("/laws/ndps", add_path("ndps"), home_path(), "/laws"):
        page = client.get(url)
        assert page.status_code == 200
        assert _facts(client) == before
    gate = client.get(home_path())
    assert 'data-playground-gate="not_subscribed"' in gate.text
    assert GATE_TITLE in unescape(gate.text)
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


def test_phone_signed_in_add_screen02_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_signed_in_add_screen02_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
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
        requests: list[str] = []
        page.on(
            "request",
            lambda req: requests.append(f"{req.method} {req.url}"),
        )

        def open_sheet():
            page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
            page.evaluate(
                """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
            )
            page.locator("[data-signed-in-bareact-phone] .guest-bareact-cta").click()
            page.wait_for_selector(
                "[data-pg-add][data-pg-kind='subscribe']", timeout=8000
            )
            page.wait_for_timeout(400)

        open_sheet()
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const desk = panel.querySelector('[data-signed-in-add-desktop]');
              const phoneBlock = panel.querySelector('[data-signed-in-add-phone]');
              const unlock = phoneBlock && phoneBlock.querySelector('.signed-add-unlock');
              const cancel = phoneBlock && [...phoneBlock.querySelectorAll('a, button')].find(
                (el) => el.textContent.trim() === 'Cancel'
              );
              const closeBtn = panel.querySelector('.pg-sheet-close');
              const tabs = document.querySelector('[data-signed-in-bareact-phone-tabs]');
              const handle = getComputedStyle(panel, '::before');
              const d = dialog.getBoundingClientRect();
              const p = panel.getBoundingClientRect();
              const head = document.querySelector('[data-signed-in-bareact-phone]');
              const cta = head && head.querySelector('.guest-bareact-cta');
              return {
                open: Boolean(dialog && dialog.open),
                kind: panel.getAttribute('data-pg-kind'),
                url: location.pathname,
                deskDisplay: getComputedStyle(desk).display,
                phoneDisplay: getComputedStyle(phoneBlock).display,
                title: phoneBlock.querySelector('.signed-add-title').textContent.trim(),
                lede: phoneBlock.querySelector('.signed-add-lede').textContent.trim(),
                note: phoneBlock.querySelector('.signed-add-note') &&
                  phoneBlock.querySelector('.signed-add-note').textContent.trim(),
                unlock: {
                  tag: unlock && unlock.tagName,
                  href: unlock && unlock.getAttribute('href'),
                  text: unlock && unlock.textContent.trim(),
                  width: unlock && unlock.getBoundingClientRect().width,
                  height: unlock && unlock.getBoundingClientRect().height,
                },
                cancel: Boolean(cancel),
                closeDisplay: closeBtn ? getComputedStyle(closeBtn).display : 'missing',
                handleDisplay: handle.display,
                handleHeight: handle.height,
                dialog: { top: d.top, left: d.left, width: d.width, height: d.height },
                panel: { top: p.top, left: p.left, width: p.width, bottom: p.bottom },
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                overflowY: getComputedStyle(panel).overflowY,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                tabFocused: tabs && tabs.contains(document.activeElement),
                backgroundTitle: head && head.querySelector('.guest-bareact-title')
                  && head.querySelector('.guest-bareact-title').textContent.trim(),
                subscribe: cta && cta.textContent.trim(),
                already: head && head.innerText.includes('Already in Playground'),
                guestAdd: Boolean(panel.querySelector('[data-guest-add-phone]')),
                billing: !!(phoneBlock && phoneBlock.querySelector('a[href="/billing/subscriptions"]')),
                plans: !!(phoneBlock && phoneBlock.querySelector('a[href*="stage=plans"]')),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.set_viewport_size({"width": 390, "height": 560})
        short = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const unlock = panel.querySelector('[data-signed-in-add-phone] .signed-add-unlock');
              const box = unlock.getBoundingClientRect();
              return {
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                unlockW: box.width,
                unlockH: box.height,
                inPanel: panel.contains(unlock),
                overflowY: getComputedStyle(panel).overflowY,
              };
            }"""
        )
        page.set_viewport_size({"width": 390, "height": 844})

        panel_top = geo["panel"]["top"]
        page.mouse.click(195, max(20, panel_top - 40))
        page.wait_for_timeout(250)
        closed = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const cta = document.querySelector('[data-signed-in-bareact-phone] .guest-bareact-cta');
              return {
                open: Boolean(dialog && dialog.open),
                url: location.pathname,
                focused: document.activeElement === cta,
                title: document.querySelector('[data-signed-in-bareact-phone] .guest-bareact-title')
                  && document.querySelector('[data-signed-in-bareact-phone] .guest-bareact-title').textContent.trim(),
              };
            }"""
        )

        page.locator("[data-signed-in-bareact-phone] .guest-bareact-cta").click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='subscribe']", timeout=8000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        escaped = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const cta = document.querySelector('[data-signed-in-bareact-phone] .guest-bareact-cta');
              return {
                open: Boolean(dialog && dialog.open),
                url: location.pathname,
                focused: document.activeElement === cta,
              };
            }"""
        )

        n_before = len(requests)
        page.locator("[data-signed-in-bareact-phone] .guest-bareact-cta").click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='subscribe']", timeout=8000)
        page.locator("[data-signed-in-add-phone] .signed-add-unlock").click()
        page.wait_for_url("**/playground", timeout=8000)
        extra = requests[n_before:]
        gate = page.evaluate(
            """() => {
              const gate = document.querySelector('.EntitlementGate');
              return {
                path: location.pathname,
                search: location.search,
                present: Boolean(gate),
                reason: gate && gate.getAttribute('data-playground-gate'),
                title: gate && gate.querySelector('h1') && gate.querySelector('h1').textContent.trim(),
              };
            }"""
        )
        browser.close()

    assert geo["open"] is True
    assert geo["kind"] == KIND_SUBSCRIBE
    assert geo["url"] == "/laws/ndps"
    assert geo["deskDisplay"] == "none"
    assert geo["phoneDisplay"] != "none"
    assert geo["title"] == TITLE
    assert geo["lede"] == LEDE
    assert geo["note"] == NOTE
    assert geo["unlock"]["tag"] == "A"
    assert geo["unlock"]["href"] == home_path()
    assert geo["unlock"]["text"] == TITLE
    assert geo["unlock"]["width"] >= 300
    assert geo["unlock"]["height"] >= 44
    assert geo["cancel"] is False
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
    assert geo["overflowY"] in ("auto", "scroll")
    assert geo["backgroundTitle"] == NDPS_GUEST_TITLE
    assert geo["subscribe"] == "Subscribe to use Playground"
    assert geo["already"] is False
    assert geo["guestAdd"] is False
    assert geo["billing"] is False
    assert geo["plans"] is False
    assert geo["tabFocused"] is False
    assert short["overflow"] is False
    assert short["unlockW"] >= 300
    assert short["unlockH"] >= 44
    assert short["inPanel"] is True
    assert closed["open"] is False
    assert closed["url"] == "/laws/ndps"
    assert closed["focused"] is True
    assert closed["title"] == NDPS_GUEST_TITLE
    assert escaped["open"] is False
    assert escaped["url"] == "/laws/ndps"
    assert escaped["focused"] is True
    assert gate["path"] == home_path()
    assert gate["search"] in ("",)
    assert gate["present"] is True
    assert gate["reason"] == "not_subscribed"
    assert gate["title"] == GATE_TITLE
    assert not any("/billing/subscriptions" in item for item in extra)
    assert not any("stage=plans" in item for item in extra)
    assert not any(item.startswith("POST ") for item in extra)
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_signed_in_add_screen02_desktop_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_signed_in_add_screen02_desktop_regression_1280.png"
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
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        page.locator("[data-signed-in-bareact-desktop] .guest-bareact-cta").click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='subscribe']", timeout=8000)
        page.wait_for_timeout(300)
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const desk = panel.querySelector('[data-signed-in-add-desktop]');
              const phoneBlock = panel.querySelector('[data-signed-in-add-phone]');
              const unlock = desk.querySelector('.signed-add-unlock');
              const cancel = desk.querySelector('.signed-add-cancel');
              const closeBtn = panel.querySelector('.pg-sheet-close');
              const d = dialog.getBoundingClientRect();
              return {
                open: Boolean(dialog && dialog.open),
                deskDisplay: getComputedStyle(desk).display,
                phoneDisplay: phoneBlock ? getComputedStyle(phoneBlock).display : null,
                title: desk.querySelector('.signed-add-title').textContent.trim(),
                lede: desk.querySelector('.signed-add-lede').textContent.trim(),
                unlockHref: unlock.getAttribute('href'),
                unlockText: unlock.textContent.trim(),
                cancelDisplay: cancel ? getComputedStyle(cancel).display : null,
                closeDisplay: closeBtn ? getComputedStyle(closeBtn).display : 'missing',
                dialogWidth: d.width,
                notFullBleed: d.width < 800 && d.left > 100,
                billing: !!(desk.querySelector('a[href="/billing/subscriptions"]')),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["open"] is True
    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["title"] == TITLE
    assert geo["lede"] == LEDE
    assert geo["unlockHref"] == home_path()
    assert geo["unlockText"] == TITLE
    assert geo["cancelDisplay"] == "none"
    assert geo["closeDisplay"] != "none"
    assert geo["notFullBleed"] is True
    assert geo["billing"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
