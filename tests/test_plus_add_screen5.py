"""Plus cohort desktop NDPS Add-dialog Screen 05 (CTA map plus/05-screen).

Authorized: ChatGPT. Authenticated multiuser GET /playground/laws/ndps/add
with a real active Plus EntitlementSnapshot. Overlay from accepted Screen 04
Add CTA. Guest and signed-in Free Screen 05 stay on their own wrappers.
Choose sections continues to the existing playground_select route.
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
from constitution_memorizer.auth.sessions import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.roster.period import (
    playground_month_bounds,
    playground_month_name,
)
from constitution_memorizer.playground.urls import add_path, law_path, remove_path, sections_path
from constitution_memorizer.playground.view import plus_add_confirm_copy
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.guest_bareact_head import NDPS_GUEST_READING_NAME
from tests.conftest import PLAYGROUND_TEST_NOW

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
ADD_TPL = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
SELECT_TPL = ROOT / "src/constitution_memorizer/web/templates/playground_select.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
ROUTES = ROOT / "src/constitution_memorizer/playground/routes.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
MONTH = playground_month_name(playground_month_bounds(PLAYGROUND_TEST_NOW)[0])
LEDE = (
    f"{NDPS_GUEST_READING_NAME} joins this month's Playground — learnable, verbatim. "
    "The reader itself never changes."
)
SPACE = f"This will use 1 of your 10 law spaces in {MONTH}. 9 will remain."
FOOTER = "Already yours this month — reopening it never uses another space."
INVENTED = (
    "Premium",
    "Unlimited",
    "renews",
    "Unlock all",
    "Free plan",
    "device limit",
    "replacement",
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


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("rtc_csrf") or ""
    return {"csrf_token": token} if token else {}


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


def _plus_client(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    return client


def _desk(html: str) -> str:
    return html.split("data-plus-add-desktop", 1)[1].split(
        "data-plus-add-phone", 1
    )[0]


def _phone(html: str) -> str:
    return html.split("data-plus-add-phone", 1)[1].split(
        'data-add-step="scope"', 1
    )[0]


def _scope(html: str) -> str:
    return html.split('data-add-step="scope"', 1)[1]


def test_plus_add_confirm_copy_uses_roster_remaining() -> None:
    title, lede, space, footer = plus_add_confirm_copy(
        reading_name=NDPS_GUEST_READING_NAME,
        month_name=MONTH,
        law_limit=10,
        remaining_after=9,
    )
    assert title == "Add to Playground"
    assert lede == LEDE
    assert space == SPACE
    assert footer == ""
    _title, _lede, _space, reopen_footer = plus_add_confirm_copy(
        reading_name=NDPS_GUEST_READING_NAME,
        month_name=MONTH,
        law_limit=10,
        remaining_after=9,
        reopen=True,
    )
    assert reopen_footer == FOOTER


def test_plus_add_desktop_is_subscriber_confirm_only(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    html = client.get(add_path("ndps")).text
    assert 'data-plus-add="desktop"' in html
    assert 'data-pg-kind="eligible_to_add"' in html
    assert "data-plus-add-desktop" in html
    assert "data-plus-add-phone" in html
    assert "data-guest-add-desktop" not in html
    assert "data-signed-in-add-desktop" not in html
    desk = unescape(_desk(html))
    assert ">Add to Playground<" in desk
    assert desk.count("Add to Playground") == 2
    assert LEDE in desk
    assert SPACE in desk
    assert FOOTER not in desk
    assert "plus-add-footer" not in desk
    assert "reopening it never uses another space" not in desk
    assert 'name="csrf_token"' in desk
    assert 'name="confirm" value="add"' in desk
    assert 'data-pg-add-confirm' in desk
    assert 'class="plus-add-submit"' in desk
    assert 'data-pg-sheet-close' in desk
    assert ">Cancel<" in desk
    assert "Sign in" not in desk
    assert "Create an account" not in desk
    assert "Unlock Playground" not in desk
    assert "Resume Playground" not in desk
    assert "Playground full this month" not in desk
    assert "temporarily unavailable" not in desk
    assert "Device limit" not in desk
    assert "Subscribe to use Playground" not in desk
    assert "Already in Playground" not in desk
    for phrase in INVENTED:
        assert phrase not in desk, phrase
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False
    assert client.app.state.playground.get_item(USER, "ndps") is None


def test_plus_re_add_keeps_no_extra_space_copy(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    payload["scope"] = "entire"
    added = client.post(add_path("ndps"), data=payload, follow_redirects=False)
    assert added.status_code == 303
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    removed = client.post(remove_path("ndps"), data=_csrf(client), follow_redirects=False)
    assert removed.status_code == 303
    html = unescape(client.get(add_path("ndps")).text)
    assert 'data-pg-kind="re_add"' in html
    assert "data-plus-add-desktop" not in html
    assert "No extra space used." in html
    assert "Your progress will be saved." in html
    assert "Add back" in html
    assert SPACE not in html
    assert "joins this month" not in html
    assert plus_add_confirm_copy(
        reading_name=NDPS_GUEST_READING_NAME,
        month_name=MONTH,
        law_limit=10,
        remaining_after=9,
        reopen=True,
    )[3] == FOOTER


def test_plus_add_phone_keeps_existing_subscriber_confirm(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    phone = unescape(_phone(client.get(add_path("ndps")).text))
    assert f"Add NDPS Act to {MONTH}?" in phone
    assert f"This will use 1 of your 10 law spaces for {MONTH}." in phone
    assert "You'll have 9 spaces remaining." in phone
    assert ">Cancel<" in phone
    assert f'href="/laws/ndps"' in phone
    assert 'data-pg-sheet-close' not in phone
    assert FOOTER not in phone
    assert "joins this month" not in phone
    assert "Unlock Playground" not in phone
    assert "Create an account" not in phone


def test_plus_add_scope_choice_is_existing_machine(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    html = client.get(add_path("ndps")).text
    scope = unescape(_scope(html))
    assert "Add NDPS Act" in scope
    assert "Choose how much of NDPS Act enters your recall schedule." in scope
    assert ">Entire Act<" in scope
    assert ">Choose sections<" in scope
    assert "Pick sections — or open one and pick single clauses" in scope
    assert "Nothing is scheduled yet — provisions activate the first time you learn them." in scope
    assert 'name="scope" value="entire"' in scope
    assert 'name="scope" value="sections"' in scope
    assert 'name="csrf_token"' in scope
    assert 'name="confirm" value="add"' in scope
    assert ">Cancel<" in scope
    assert "Unlock Playground" not in scope
    assert "Create an account" not in scope


def test_plus_add_confirm_post_then_choose_sections(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    missing = client.post(
        add_path("ndps"),
        data={"confirm": "add", "scope": "sections"},
        follow_redirects=False,
    )
    assert missing.status_code == 403

    unconfirmed = client.post(
        add_path("ndps"), data=_csrf(client), follow_redirects=False
    )
    assert unconfirmed.status_code == 303
    assert "/playground/roster" in (unconfirmed.headers.get("location") or "")
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False

    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    scope_page = client.post(add_path("ndps"), data=payload, follow_redirects=False)
    assert scope_page.status_code == 200
    assert 'data-add-step="scope"' in scope_page.text
    assert ">Entire Act<" in scope_page.text
    assert "learnable" in unescape(scope_page.text)
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False

    payload["scope"] = "sections"
    added = client.post(add_path("ndps"), data=payload, follow_redirects=False)
    assert added.status_code == 303
    assert added.headers.get("location") == sections_path("ndps")
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    select = client.get(sections_path("ndps"))
    assert select.status_code == 200
    assert "Choose what to learn" in select.text
    assert 'data-pg-picker' in select.text
    assert 'name="csrf_token"' in select.text
    assert "data-plus-add-desktop" not in select.text
    empty = client.post(
        sections_path("ndps"), data=_csrf(client), follow_redirects=False
    )
    assert empty.status_code in {303, 400}
    if empty.status_code == 400:
        assert empty.json().get("detail") == "invalid_selection"


def test_plus_add_entire_act_uses_existing_endpoint(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    payload["scope"] = "entire"
    added = client.post(add_path("ndps"), data=payload, follow_redirects=False)
    assert added.status_code == 303
    assert added.headers.get("location") == law_path("ndps")
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    again = client.get(add_path("ndps"), follow_redirects=False)
    assert again.status_code == 303


def test_plus_add_does_not_open_from_bare_act_without_sheet_cta(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    html = client.get("/laws/ndps").text
    assert 'data-plus-bareact="desktop"' in html
    assert "+ Add to Playground" in html
    assert f'href="{add_path("ndps")}"' in html
    assert "data-pg-sheet" in html
    assert 'data-pg-kind="eligible_to_add"' in html
    assert "Already in Playground" not in html.split(
        "data-signed-in-bareact-desktop", 1
    )[1].split("data-bareact-phone", 1)[0]


def test_halted_expired_pro_free_guest_are_not_plus_add(tmp_path: Path) -> None:
    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get(add_path("ndps")).text
    assert "data-plus-add-desktop" not in halted_html
    assert 'data-plus-add="desktop"' not in halted_html

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(expired, status="expired")
    expired_html = expired.get(add_path("ndps")).text
    assert "data-plus-add-desktop" not in expired_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get(add_path("ndps")).text
    assert "data-plus-add-desktop" not in pro_html
    assert 'data-pg-kind="eligible_to_add"' in pro_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get(add_path("ndps")).text
    assert "data-plus-add-desktop" not in free_html
    assert "data-signed-in-add-desktop" in free_html
    assert 'data-pg-kind="subscribe"' in free_html
    assert "Unlock Playground" in free_html

    guest_html = TestClient(_mu_app(tmp_path / "guest")).get(add_path("ndps")).text
    assert "data-plus-add-desktop" not in guest_html
    assert "data-guest-add-desktop" in guest_html
    assert "Create an account" in guest_html


def test_plus_add_is_ndps_tied_not_other_laws(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    bns = client.get(add_path("bns")).text
    assert "data-plus-add-desktop" not in bns
    assert 'data-plus-add="desktop"' not in bns
    assert 'data-pg-kind="eligible_to_add"' in bns
    assert f"Add BNS to {MONTH}?" in bns or "Add Bharatiya" in bns
    assert "joins this month" not in bns


def test_plus_add_marker_uses_shared_predicate() -> None:
    add_src = ADD_TPL.read_text(encoding="utf-8")
    assert "plus_add" in add_src
    assert "data-plus-add-desktop" in add_src
    assert 'data-plus-add="desktop"' in add_src
    assert "data-pg-add-confirm" in add_src
    assert ">Entire Act<" in add_src
    assert ">Choose sections<" in add_src
    assert "Pick sections — or open one and pick single clauses" in add_src
    assert "provisions activate the first time you learn them." in add_src
    assert "Unlock Playground" not in add_src.split("{% else %}", 1)[-1]
    select = SELECT_TPL.read_text(encoding="utf-8")
    assert "data-pg-picker" in select
    assert "Choose what to learn" in select
    assert "data-plus-add-desktop" not in select
    routes = ROUTES.read_text(encoding="utf-8")
    assert "request_is_active_plus" in routes
    assert "plus_add_confirm_copy" in routes
    assert 'law_id == "ndps"' in routes
    view = VIEW.read_text(encoding="utf-8")
    assert "def plus_add_confirm_copy" in view
    assert "PLUS_ADD_REOPEN_NOTE" in view
    assert "reopen=False" in routes
    assert "def request_is_active_plus" in DEPS.read_text(encoding="utf-8")
    css = PG_CSS.read_text(encoding="utf-8")
    assert "[data-plus-add-desktop]" in css
    assert "plus-add-submit" in css
    assert "playground.css?v=pg28" in BASE.read_text(encoding="utf-8")
    bare = BARE.read_text(encoding="utf-8")
    assert "data-plus-add-desktop" not in bare
    assert 'data-plus-bareact="desktop"' in bare
    for phrase in ("Premium", "Unlimited", "renews"):
        assert phrase not in add_src


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


def test_plus_add_1280_dialog_scope_and_select(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "plus_add_screen5_1280.png"
    select_path = artifact_dir / "plus_add_screen5_select_1280.png"
    origin = f"http://127.0.0.1:{port}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        cookies = [
            {
                "name": SESSION_COOKIE_NAME,
                "value": session,
                "url": origin,
                "httpOnly": True,
                "secure": False,
                "sameSite": "Lax",
            }
        ]
        if csrf:
            cookies.append(
                {
                    "name": CSRF_COOKIE_NAME,
                    "value": csrf,
                    "url": origin,
                    "httpOnly": True,
                    "secure": False,
                    "sameSite": "Lax",
                }
            )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
        context.add_cookies(cookies)
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
            page.locator('[data-plus-bareact="desktop"] [data-pg-sheet]').click()
            page.wait_for_selector("[data-plus-add-desktop]", timeout=8000)

        open_dialog()
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const desk = panel.querySelector('[data-plus-add-desktop]');
              const phone = panel.querySelector('[data-plus-add-phone]');
              const submit = desk.querySelector('.plus-add-submit');
              const cancel = desk.querySelector('.plus-add-cancel');
              const closeBtn = panel.querySelector('[data-pg-sheet-close].pg-sheet-close');
              const head = document.querySelector('[data-plus-bareact="desktop"]');
              const box = panel.getBoundingClientRect();
              const titleEl = desk.querySelector('.plus-add-title');
              const ledeEl = desk.querySelector('.plus-add-lede');
              const spaceEl = desk.querySelector('.plus-add-space');
              const footerEl = desk.querySelector('.plus-add-footer');
              const closeStyle = closeBtn && getComputedStyle(closeBtn);
              const panelStyle = getComputedStyle(panel);
              const backdrop = getComputedStyle(dialog, '::backdrop');
              const confirmStep = panel.querySelector("[data-add-step='confirm']");
              const scopeStep = panel.querySelector("[data-add-step='scope']");
              return {
                open: dialog && dialog.open,
                kind: panel.getAttribute('data-pg-kind'),
                plus: panel.getAttribute('data-plus-add'),
                deskDisplay: getComputedStyle(desk).display,
                phoneDisplay: getComputedStyle(phone).display,
                eyebrowDisplay: getComputedStyle(panel.querySelector('.pg-eyebrow')).display,
                title: titleEl.textContent.trim(),
                titleSize: getComputedStyle(titleEl).fontSize,
                titleWeight: getComputedStyle(titleEl).fontWeight,
                lede: ledeEl.textContent.trim(),
                space: spaceEl && spaceEl.textContent.trim(),
                footer: footerEl && footerEl.textContent.trim(),
                submitText: submit.textContent.trim(),
                submitH: submit.getBoundingClientRect().height,
                cancelDisplay: cancel ? getComputedStyle(cancel).display : null,
                cancelCloses: cancel && cancel.hasAttribute('data-pg-sheet-close'),
                hasClose: Boolean(closeBtn),
                closeLabel: closeBtn && closeBtn.getAttribute('aria-label'),
                closeTop: closeStyle && closeStyle.top,
                closeRight: closeStyle && closeStyle.right,
                panelW: box.width,
                panelRadius: panelStyle.borderRadius,
                panelPad: panelStyle.padding,
                scrim: backdrop.backgroundColor,
                guestAdd: Boolean(panel.querySelector('[data-guest-add-desktop]')),
                signedAdd: Boolean(panel.querySelector('[data-signed-in-add-desktop]')),
                confirmHidden: Boolean(confirmStep && confirmStep.hidden),
                scopeHidden: Boolean(scopeStep && scopeStep.hidden),
                leaked: {
                  already: desk.innerText.includes('Already in Playground'),
                  resume: desk.innerText.includes('Resume Playground'),
                  full: desk.innerText.includes('Playground full'),
                  pending: desk.innerText.includes('temporarily unavailable'),
                  signin: desk.innerText.includes('Create an account'),
                  unlock: desk.innerText.includes('Unlock Playground'),
                  reopen: desk.innerText.includes('reopening it never uses another space'),
                },
                background: Boolean(head),
                addCta: head && head.querySelector('[data-pg-sheet]') &&
                  head.querySelector('[data-pg-sheet]').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator("[data-plus-add-desktop] .plus-add-submit").click()
        scope_geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const confirmStep = panel.querySelector("[data-add-step='confirm']");
              const scopeStep = panel.querySelector("[data-add-step='scope']");
              const entire = [...scopeStep.querySelectorAll('button')].find(
                (b) => (b.getAttribute('name') === 'scope' && b.getAttribute('value') === 'entire')
              );
              const sections = [...scopeStep.querySelectorAll('button')].find(
                (b) => (b.getAttribute('name') === 'scope' && b.getAttribute('value') === 'sections')
              );
              return {
                path: location.pathname,
                confirmHidden: Boolean(confirmStep && confirmStep.hidden),
                scopeHidden: Boolean(scopeStep && scopeStep.hidden),
                title: scopeStep.querySelector('h1') && scopeStep.querySelector('h1').textContent.trim(),
                entire: entire && entire.innerText,
                sections: sections && sections.innerText,
                note: scopeStep.querySelector('.pg-note') &&
                  scopeStep.querySelector('.pg-note').textContent.trim(),
              };
            }"""
        )
        page.locator(".pg-sheet-close").click()

        open_dialog()
        page.locator(".pg-sheet-close").click()
        closed_x = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              return {
                open: Boolean(dialog && dialog.open),
                path: location.pathname,
                head: Boolean(document.querySelector('[data-plus-bareact="desktop"]')),
                focused: document.activeElement &&
                  document.activeElement.hasAttribute('data-pg-sheet'),
              };
            }"""
        )

        open_dialog()
        page.evaluate(
            """() => document.querySelector('[data-plus-add-desktop] .plus-add-cancel').click()"""
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
              const desk = panel.querySelector('[data-plus-add-desktop]');
              const phoneBlock = panel.querySelector('[data-plus-add-phone]');
              const title = phoneBlock && phoneBlock.querySelector('h1');
              const cancel = phoneBlock && [...phoneBlock.querySelectorAll('a')].find(
                (a) => a.textContent.trim() === 'Cancel'
              );
              return {
                kind: panel.getAttribute('data-pg-kind'),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                phoneDisplay: phoneBlock ? getComputedStyle(phoneBlock).display : null,
                title: title && title.textContent.trim(),
                cancelHref: cancel && cancel.getAttribute('href'),
                plusChrome: Boolean(phoneBlock && phoneBlock.querySelector('.plus-add-title')),
              };
            }"""
        )

        page.set_viewport_size({"width": 1280, "height": 800})
        open_dialog()
        page.locator("[data-plus-add-desktop] .plus-add-submit").click()
        page.locator('button[name="scope"][value="sections"]').click()
        page.wait_for_url("**/playground/laws/ndps/sections", timeout=8000)
        select_geo = page.evaluate(
            """() => {
              const picker = document.querySelector('[data-pg-picker]');
              const submit = document.querySelector('[data-pg-submit]');
              return {
                path: location.pathname,
                present: Boolean(picker),
                title: document.querySelector('h1') && document.querySelector('h1').textContent.trim(),
                submitDisabled: submit ? submit.disabled : null,
                submitText: submit && submit.textContent.trim(),
                plusDialog: Boolean(document.querySelector('[data-plus-add-desktop]')),
              };
            }"""
        )
        page.screenshot(path=str(select_path), full_page=False)
        browser.close()

    assert geo["open"] is True
    assert geo["kind"] == "eligible_to_add"
    assert geo["plus"] == "desktop"
    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["eyebrowDisplay"] == "none"
    assert geo["title"] == "Add to Playground"
    assert geo["titleSize"] == "22px"
    assert geo["titleWeight"] in ("500", "bold")
    assert geo["lede"] == LEDE
    assert geo["space"] == SPACE
    assert geo["footer"] in (None, "")
    assert geo["submitText"] == "Add to Playground"
    assert geo["submitH"] == pytest.approx(50, abs=2)
    assert geo["cancelDisplay"] == "none"
    assert geo["cancelCloses"] is True
    assert geo["hasClose"] is True
    assert geo["closeLabel"] == "Close"
    assert geo["closeTop"] == "14px"
    assert geo["closeRight"] == "14px"
    assert geo["panelW"] == pytest.approx(460, abs=8)
    assert "16px" in geo["panelRadius"]
    assert "26px" in geo["panelPad"]
    assert "28px" in geo["panelPad"]
    assert "0.35" in (geo["scrim"] or "") or "rgba(20, 20, 20, 0.35)" in (geo["scrim"] or "")
    assert geo["guestAdd"] is False
    assert geo["signedAdd"] is False
    assert geo["confirmHidden"] is False
    assert geo["scopeHidden"] is True
    assert geo["leaked"]["already"] is False
    assert geo["leaked"]["resume"] is False
    assert geo["leaked"]["full"] is False
    assert geo["leaked"]["pending"] is False
    assert geo["leaked"]["signin"] is False
    assert geo["leaked"]["unlock"] is False
    assert geo["leaked"]["reopen"] is False
    assert geo["background"] is True
    assert geo["addCta"] == "+ Add to Playground"
    assert scope_geo["path"] == "/laws/ndps"
    assert scope_geo["confirmHidden"] is True
    assert scope_geo["scopeHidden"] is False
    assert scope_geo["title"] == "Add NDPS Act"
    assert scope_geo["entire"] and "Entire Act" in scope_geo["entire"]
    assert scope_geo["sections"] and "Choose sections" in scope_geo["sections"]
    assert "provisions activate the first time you learn them" in (scope_geo["note"] or "")
    assert select_geo["path"] == sections_path("ndps")
    assert select_geo["present"] is True
    assert select_geo["title"] == "Choose what to learn"
    assert select_geo["submitDisabled"] is True
    assert select_geo["submitText"] == "Select sections to add"
    assert select_geo["plusDialog"] is False
    assert closed_x["open"] is False
    assert closed_x["path"] == "/laws/ndps"
    assert closed_x["head"] is True
    assert closed_x["focused"] is True
    assert closed_cancel["open"] is False
    assert closed_cancel["path"] == "/laws/ndps"
    assert closed_esc is False
    assert phone_geo["kind"] == "eligible_to_add"
    assert phone_geo["deskDisplay"] == "none"
    assert phone_geo["phoneDisplay"] != "none"
    assert phone_geo["title"] == f"Add NDPS Act to {MONTH}?"
    assert phone_geo["cancelHref"] == "/laws/ndps"
    assert phone_geo["plusChrome"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
    assert select_path.is_file()
    assert select_path.stat().st_size > 1000
