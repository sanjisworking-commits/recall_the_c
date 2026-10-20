"""Phone Guest Add sheet Screen 02 (CTA map guest/02-screen, 390x844).

M2: one Add sheet per state (§2.1), drawn over the generated Act head and
raised as a bottom sheet at phone width by CSS alone; the phone twin with its
inert buttons is gone, so Sign in / Create an account are real links to the
login gate on both widths. Guest GET /playground/laws/ndps/add is checked
here. Signed-in Unlock, Plus confirm, Expired/Halted recovery, and Guest 03
stay unchanged.
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
from constitution_memorizer.playground.eligibility import playground_bare_act_spec
from constitution_memorizer.playground.urls import add_path
from constitution_memorizer.playground.view import KIND_GUEST
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
PANEL = ROOT / "src/constitution_memorizer/web/templates/partials/playground_add_panel.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
PG_JS = ROOT / "src/constitution_memorizer/web/static/playground.js"
USER = UUID("11111111-1111-4111-8111-111111111111")
LOGIN_NEXT = f"/login?next={add_path('ndps')}"
NDPS = get_bare_act("ndps")
GUEST_ADD_TITLE = "Add to Playground"
READING_NAME = playground_bare_act_spec("ndps").short_name
GUEST_LEDE = (
    f"Playground needs an account. Reading {READING_NAME} "
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


def _sheet(html: str) -> str:
    """The one Add panel: `<section class="pg-sheet-panel" data-pg-add …>`."""
    return html.split('class="pg-sheet-panel"', 1)[1].split("</section>", 1)[0]


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
    sheet_page = client.get(add_path("ndps"))
    assert sheet_page.status_code == 200
    html = unescape(sheet_page.text)
    assert 'data-pg-kind="guest"' in html
    assert KIND_GUEST == "guest"
    assert "data-pg-add" in html
    assert html.count('class="pg-sheet-panel"') == 1  # M2: one sheet, both widths
    assert "data-guest-add-phone" not in html
    assert "data-guest-add-desktop" not in html
    sheet = _sheet(html)
    assert f'<h1 id="pg-add-title" class="pg-add-title">{GUEST_ADD_TITLE}</h1>' in sheet
    assert sheet.count(GUEST_ADD_TITLE) == 1
    assert READING_NAME == "The NDPS Act, 1985"
    assert READING_NAME == NDPS.short_name
    assert GUEST_LEDE in sheet
    assert f'<p class="pg-add-lede">{GUEST_LEDE}</p>' in sheet
    assert MAP_LEDE_LOWER_THE not in sheet
    assert ">Sign in<" in sheet
    assert "Create an account" in sheet
    assert ">Cancel<" not in sheet
    assert "data-pg-sheet-close" not in sheet
    assert "Sign in to use Playground" not in sheet
    # Both gates are real links to the login gate (the phone twin's inert
    # buttons are gone) and nothing on the sheet can write.
    assert sheet.count("data-guest-add-gate") == 2
    assert sheet.count(f'href="{LOGIN_NEXT}"') == 2
    assert f'<a class="pg-add-primary" href="{LOGIN_NEXT}" data-guest-add-gate>Sign in</a>' in sheet
    assert (
        f'<a class="pg-add-secondary" href="{LOGIN_NEXT}" data-guest-add-gate>Create an account</a>'
    ) in sheet
    assert sheet.count("<a ") == 2
    assert "<form" not in sheet
    assert "<button" not in sheet
    assert 'type="button"' not in sheet
    for phrase in SUBSCRIBER_CONTROLS:
        assert phrase not in sheet, phrase
    assert _facts(client) == before
    # The in-page fetch (X-Requested-With: pg-sheet) returns the same panel
    # on its own for playground.js to lift into the live dialog.
    fetched = unescape(
        client.get(add_path("ndps"), headers={"X-Requested-With": "pg-sheet"}).text
    )
    assert fetched.count('class="pg-sheet-panel"') == 1
    assert "<dialog" not in fetched
    assert "ActHead" not in fetched
    fetched_sheet = _sheet(fetched)
    assert 'data-pg-kind="guest"' in fetched_sheet
    assert f'<p class="pg-add-lede">{GUEST_LEDE}</p>' in fetched_sheet
    assert fetched_sheet.count(f'href="{LOGIN_NEXT}"') == 2
    assert fetched_sheet.count("data-guest-add-gate") == 2
    assert "<form" not in fetched_sheet
    assert _facts(client) == before


def test_guest_add_sheet_source_is_one_block_with_real_links() -> None:
    src = ADD.read_text(encoding="utf-8")
    assert (
        '{% extends "bare_act.html" if act is defined and act else "playground_base.html" %}'
        in src
    )
    assert "{% block act_dialog %}" in src
    assert "data-pg-sheet-direct" in src
    assert 'data-pg-sheet-return="{{ cancel_href }}"' in src
    assert src.count('{% include "partials/playground_add_panel.html" %}') == 2
    panel = PANEL.read_text(encoding="utf-8")
    assert panel.lstrip("{#").lstrip().startswith("The Add sheet panel")
    for gone in (
        "data-guest-add-phone",
        "data-guest-add-desktop",
        "guest-add-signin",
        "guest-add-create",
        "guest-add-title",
        'type="button"',
    ):
        assert gone not in src, gone
        assert gone not in panel, gone
    guest = panel.split('{% if kind == "guest" %}', 1)[1].split("{% elif", 1)[0]
    assert 'class="pg-add-title">Add to Playground<' in guest
    assert "reading_name|default(short_title)" in guest
    assert guest.count("login_href") == 2
    assert guest.count("data-guest-add-gate") == 2
    assert '<a class="pg-add-primary" href="{{ login_href }}" data-guest-add-gate>Sign in</a>' in guest
    assert (
        '<a class="pg-add-secondary" href="{{ login_href }}" data-guest-add-gate>Create an account</a>'
    ) in guest
    assert "cancel_href" not in guest
    assert "data-pg-sheet-close" not in guest
    assert "<form" not in guest
    assert "<button" not in guest
    js = PG_JS.read_text(encoding="utf-8")
    assert "guest-add-signin" not in js
    assert "guest-add-create" not in js
    assert "data-guest-add-phone" not in js
    assert "event.target === dialog" in js
    # M2 Q4: a server-opened dialog is re-opened as a modal and closes back
    # onto the Act's own address.
    assert 'dialog.hasAttribute("data-pg-sheet-direct")' in js
    assert 'dialog.getAttribute("data-pg-sheet-return")' in js
    assert "window.history.replaceState(null, \"\", back)" in js


def test_guest_add_css_is_one_block_with_phone_overrides() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    for gone in (
        "guest/02-screen:",
        "data-guest-add-phone",
        "data-guest-add-desktop",
        ".guest-add-signin",
        ".guest-add-create",
    ):
        assert gone not in css, gone
    assert "Add sheet (M2)" in css
    m2 = css.split("Add sheet (M2)", 1)[1]
    primary = m2.split(".pg-add-primary {", 1)[1].split("}", 1)[0]
    assert "width: 100%" in primary
    assert "min-height: 50px" in primary
    secondary = m2.split(".pg-add-secondary {", 1)[1].split("}", 1)[0]
    assert "width: 100%" in secondary
    phone_block = m2.split("@media (max-width: 560px) {", 1)[1].split("\n}\n", 1)[0]
    assert ".pg-sheet-panel[data-pg-add] {" in phone_block
    assert ".pg-add-title {" in phone_block
    assert ".pg-add-lede {" in phone_block
    # The dialog itself is still the shared bottom sheet at phone width.
    generic = css.split("@media (max-width: 560px)", 1)[1].split(
        "/* R2 section/clause picker */", 1
    )[0]
    assert "width: calc(100% - (2 * var(--pg-shell-pad)))" in generic
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg51" in base
    assert "playground.js?v=pg10" in base
    assert "playground.css?v=pg49" not in base
    assert "playground.css?v=pg31" not in base
    assert "playground.css?v=pg30" not in base


def test_signed_in_plus_expired_halted_add_sheets_stay_separate(
    tmp_path: Path,
) -> None:
    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get(add_path("ndps")).text
    assert free_html.count('class="pg-sheet-panel"') == 1
    free_sheet = _sheet(free_html)
    assert 'data-pg-kind="subscribe"' in free_sheet
    assert "Unlock Playground" in free_sheet
    assert '<a class="pg-add-primary" href="/playground">Unlock Playground</a>' in free_sheet
    assert "Create an account" not in free_html
    assert "data-guest-add-gate" not in free_html
    assert "data-expired-add" not in free_sheet
    assert "data-halted-add" not in free_sheet

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get(add_path("ndps")).text
    assert plus_html.count('class="pg-sheet-panel"') == 1
    plus_sheet = _sheet(plus_html)
    assert 'data-pg-kind="eligible_to_add"' in plus_sheet
    assert "data-pg-add-confirm" in plus_sheet
    assert f'action="{add_path("ndps")}"' in plus_sheet
    assert 'name="csrf_token"' in plus_sheet
    assert "Create an account" not in plus_html
    assert "data-guest-add-gate" not in plus_html
    assert "Unlock Playground" not in plus_sheet

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
    expired_sheet = _sheet(expired_html)
    assert "data-expired-add" in expired_sheet
    assert 'data-pg-kind="resume"' in expired_sheet
    assert "Resume Playground" in expired_sheet
    assert "Create an account" not in expired_html
    assert "data-guest-add-gate" not in expired_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get(add_path("ndps")).text
    halted_sheet = _sheet(halted_html)
    assert "data-halted-add" in halted_sheet
    assert "Payment retries have stopped" in halted_sheet
    assert "Manage subscription" in halted_sheet
    assert "Create an account" not in halted_html
    assert "data-guest-add-gate" not in halted_html


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
              const head = document.querySelector('.ActHead');
              return {
                title: head && head.querySelector('.ActHead-title').textContent.trim(),
                tabs: Boolean(document.querySelector('[data-guest-phone-tabs]')),
              };
            }"""
        )
        page.locator(".ActHead .ActHead-btn").click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='guest']", timeout=8000)
        page.wait_for_timeout(400)
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const signin = panel.querySelector('.pg-add-primary');
              const create = panel.querySelector('.pg-add-secondary');
              const tabs = document.querySelector('[data-guest-phone-tabs]');
              const d = dialog.getBoundingClientRect();
              const p = panel.getBoundingClientRect();
              return {
                open: Boolean(dialog && dialog.open),
                kind: panel.getAttribute('data-pg-kind'),
                url: location.pathname,
                panels: document.querySelectorAll('.pg-sheet-panel').length,
                panelDisplay: getComputedStyle(panel).display,
                title: panel.querySelector('.pg-add-title').textContent.trim(),
                lede: panel.querySelector('.pg-add-lede').textContent.trim(),
                signin: {
                  tag: signin.tagName,
                  href: signin.getAttribute('href'),
                  text: signin.textContent.trim(),
                  gate: signin.hasAttribute('data-guest-add-gate'),
                  form: Boolean(signin.closest('form')),
                  width: signin.getBoundingClientRect().width,
                },
                create: {
                  tag: create.tagName,
                  href: create.getAttribute('href'),
                  text: create.textContent.trim(),
                  gate: create.hasAttribute('data-guest-add-gate'),
                  form: Boolean(create.closest('form')),
                  width: create.getBoundingClientRect().width,
                },
                cancel: [...panel.querySelectorAll('a, button')].some((a) => a.textContent.trim() === 'Cancel'),
                dialog: { top: d.top, left: d.left, width: d.width, height: d.height },
                panel: { top: p.top, left: p.left, width: p.width, bottom: p.bottom },
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                backgroundTitle: document.querySelector('.ActHead .ActHead-title')
                  && document.querySelector('.ActHead .ActHead-title').textContent.trim(),
                confirm: Boolean(panel.querySelector('[data-pg-add-confirm]')),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        n_before_click = len(requests)
        page.locator("[data-pg-add] .pg-add-primary").click()
        page.wait_for_url("**/login**", timeout=8000)
        signin_url = page.url
        extra = requests[n_before_click:]

        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.locator(".ActHead .ActHead-btn").click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='guest']", timeout=8000)
        page.locator("[data-pg-add] .pg-add-secondary").click()
        page.wait_for_url("**/login**", timeout=8000)
        create_url = page.url

        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.locator(".ActHead .ActHead-btn").click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='guest']", timeout=8000)
        page.wait_for_timeout(250)
        panel_top = page.evaluate(
            "() => document.querySelector('[data-pg-add]').getBoundingClientRect().top"
        )
        page.mouse.click(195, max(20, panel_top - 40))
        page.wait_for_timeout(250)
        closed = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              return {
                open: Boolean(dialog && dialog.open),
                url: location.pathname,
                title: document.querySelector('.ActHead .ActHead-title')
                  && document.querySelector('.ActHead .ActHead-title').textContent.trim(),
                scroll: window.scrollY,
              };
            }"""
        )

        page.locator(".ActHead .ActHead-btn").click()
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

    assert background["title"] == NDPS.title
    assert background["tabs"] is True
    assert geo["open"] is True
    assert geo["kind"] == KIND_GUEST
    assert geo["url"] == "/laws/ndps"
    assert geo["panels"] == 1
    assert geo["panelDisplay"] != "none"
    assert geo["title"] == GUEST_ADD_TITLE
    assert geo["lede"] == GUEST_LEDE
    assert geo["signin"]["tag"] == "A"
    assert geo["signin"]["href"] == LOGIN_NEXT
    assert geo["signin"]["text"] == "Sign in"
    assert geo["signin"]["gate"] is True
    assert geo["signin"]["form"] is False
    assert geo["signin"]["width"] >= 300
    assert geo["create"]["tag"] == "A"
    assert geo["create"]["href"] == LOGIN_NEXT
    assert geo["create"]["text"] == "Create an account"
    assert geo["create"]["gate"] is True
    assert geo["create"]["form"] is False
    assert geo["create"]["width"] >= 300
    assert geo["cancel"] is False
    assert geo["dialog"]["width"] >= 300
    assert geo["panel"]["width"] >= 300
    assert geo["panel"]["bottom"] >= 840
    assert geo["panel"]["top"] > 400
    assert geo["overflow"] is False
    assert geo["backgroundTitle"] == NDPS.title
    assert geo["confirm"] is False
    assert "/login" in signin_url
    assert add_path("ndps") in signin_url
    assert "/login" in create_url
    assert add_path("ndps") in create_url
    assert not any(item.startswith("POST ") for item in extra)
    assert closed["open"] is False
    assert closed["url"] == "/laws/ndps"
    assert closed["title"] == NDPS.title
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
        page.locator(".ActHead .ActHead-btn").click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='guest']", timeout=8000)
        page.wait_for_timeout(300)
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const gates = [...panel.querySelectorAll('[data-guest-add-gate]')];
              const d = dialog.getBoundingClientRect();
              const closeBtn = panel.querySelector('.pg-sheet-close');
              return {
                open: Boolean(dialog && dialog.open),
                panels: document.querySelectorAll('.pg-sheet-panel').length,
                panelDisplay: getComputedStyle(panel).display,
                title: panel.querySelector('.pg-add-title').textContent.trim(),
                lede: panel.querySelector('.pg-add-lede').textContent.trim(),
                labels: gates.map((el) => el.textContent.trim()),
                tags: gates.map((el) => el.tagName),
                hrefs: gates.map((el) => el.getAttribute('href')),
                closeDisplay: closeBtn ? getComputedStyle(closeBtn).display : 'missing',
                dialogWidth: d.width,
                notFullBleed: d.width < 800 && d.left > 100,
                centered: Math.abs((d.top + d.bottom) / 2 - 400) < 120,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["open"] is True
    assert geo["panels"] == 1
    assert geo["panelDisplay"] != "none"
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
