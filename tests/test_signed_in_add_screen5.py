"""Signed-in subscribe Add sheet (CTA map signedIn/05-screen).

Authorized: ChatGPT. Authenticated multiuser non-subscriber GET
/playground/laws/ndps/add. Since M2 there is ONE sheet per state (no
desktop/phone twins): title "Add to Playground", lede, primary "Unlock
Playground" → the existing /playground Gate, and the tiers/price footnote.
No Cancel in the Free sheet — the ✕ / Escape / scrim close it. The direct
URL returns the full Act page with the sheet inside an open <dialog>
(M2 Q4). Guest Add, Bare Act head, Landing, Browse, and Laws stay unchanged.
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
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
ADD_PANEL = ROOT / "src/constitution_memorizer/web/templates/partials/playground_add_panel.html"
USER = UUID("11111111-1111-4111-8111-111111111111")
TITLE = "Add to Playground"
PRIMARY = "Unlock Playground"
LEDE = (
    "Turning The NDPS Act, 1985 into a learning experience needs a plan. "
    "Reading it stays free."
)
NOTE = "Plus · Pro · Max — from ₹199 / month. Constitution learning stays free."
OLD_MARKERS = (
    "data-signed-in-add-desktop",
    "data-signed-in-add-phone",
    "data-guest-add-desktop",
    "data-guest-add-phone",
    "data-plus-add-desktop",
    "data-plus-add-phone",
    'data-plus-add="desktop"',
    'data-expired-add="desktop"',
    'data-halted-add="desktop"',
    'class="guest-add-',
    "guest-add-title",
    "guest-add-lede",
    "guest-add-signin",
    "signed-add-",
    "plus-add-",
    "expired-add-",
    "halted-add-",
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


def _sheet(html: str) -> str:
    """The one `.pg-sheet-panel` (the Add sheet) in the page."""
    return html.split('class="pg-sheet-panel"', 1)[1].split("</section>", 1)[0]


def _band(html: str, slug: str = "ndps") -> str:
    return html.split(f'data-act-head="{slug}"', 1)[1].split("data-act-list", 1)[0]


def _assert_no_old_markers(text: str) -> None:
    for marker in OLD_MARKERS:
        assert marker not in text, marker


def test_signed_in_add_sheet_is_subscribe_only(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get(add_path("ndps")).text
    _assert_no_old_markers(html)
    assert html.count('class="pg-sheet-panel"') == 1
    sheet = _sheet(html)
    assert 'data-pg-kind="subscribe"' in sheet
    assert "data-pg-add\n" in sheet
    assert 'data-roster-confirm="ndps"' in sheet
    assert 'role="dialog"' in sheet
    assert 'aria-labelledby="pg-add-title"' in sheet
    assert "data-expired-add" not in sheet
    assert "data-halted-add" not in sheet
    assert f'<h1 id="pg-add-title" class="pg-add-title">{TITLE}</h1>' in sheet
    assert f'<p class="pg-add-lede">{LEDE}</p>' in sheet
    assert f'<a class="pg-add-primary" href="{home_path()}">{PRIMARY}</a>' in sheet
    assert sheet.count(PRIMARY) == 1
    assert f'<p class="pg-add-note">{NOTE}</p>' in sheet
    # No Cancel in the Free sheet: ✕ / Escape / scrim close it.
    assert "data-pg-sheet-close" not in sheet
    assert ">Cancel<" not in sheet
    assert "pg-add-secondary" not in sheet
    assert "/billing/subscriptions" not in sheet
    assert "stage=plans" not in sheet
    assert "<form" not in sheet
    assert "data-pg-add-confirm" not in sheet
    assert "data-guest-add-gate" not in sheet
    assert "Sign in to use Playground" not in sheet
    assert "Create an account" not in sheet
    assert "Resume Playground" not in sheet
    assert "Playground full this month" not in sheet
    assert "temporarily unavailable" not in sheet
    assert "Device limit" not in sheet
    assert "Entire Act" not in sheet
    assert "Choose sections" not in sheet
    assert "Already in Playground" not in sheet
    assert ">Sections<" not in sheet
    assert ">Continue<" not in sheet
    assert "included with your account" not in sheet


def test_signed_in_add_direct_url_is_act_page_with_open_dialog(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    page = client.get(add_path("ndps"))
    assert page.status_code == 200
    html = page.text
    # M2 Q4: the direct URL is the Act page with the sheet in an open
    # <dialog>; closing returns to /laws/ndps. The same one panel serves
    # both widths — there is no second copy for the phone.
    assert (
        '<dialog class="pg-sheet" data-pg-sheet-host data-pg-sheet-direct '
        'data-pg-sheet-return="/laws/ndps" aria-modal="true" '
        'aria-labelledby="pg-add-title" open>' in html
    )
    assert html.count("<dialog") == 1
    assert html.count('class="pg-sheet-panel"') == 1
    assert 'data-mscreen="bareact"' in html
    assert "PlaygroundShell" not in html
    assert "data-hard-gate" not in html
    assert html.count('data-act-head="ndps"') == 1
    band = _band(html)
    assert "Subscribe to use Playground" in band
    assert f'href="{add_path("ndps")}"' in band
    assert "data-act-list" in html
    assert '<details class="bareact-chapter">' in html
    sheet = _sheet(html)
    assert f'href="{home_path()}"' in sheet
    assert 'href="/billing/subscriptions"' not in sheet
    assert 'href="/laws/ndps"' not in sheet
    assert ">Cancel<" not in sheet
    assert "data-pg-sheet-close" not in sheet


def test_signed_in_add_in_page_fetch_returns_bare_panel(tmp_path: Path) -> None:
    """playground.js fetches the URL with X-Requested-With: pg-sheet and lifts
    `.pg-sheet-panel` into the live dialog: the same subscribe panel, no Act
    head and no server-rendered dialog around it."""
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    page = client.get(add_path("ndps"), headers={"X-Requested-With": "pg-sheet"})
    assert page.status_code == 200
    html = page.text
    _assert_no_old_markers(html)
    assert html.count('class="pg-sheet-panel"') == 1
    assert "<dialog" not in html
    assert "data-pg-sheet-direct" not in html
    assert "data-act-head" not in html
    assert 'data-mscreen="playground"' in html
    sheet = _sheet(html)
    assert 'data-pg-kind="subscribe"' in sheet
    assert f'<h1 id="pg-add-title" class="pg-add-title">{TITLE}</h1>' in sheet
    assert f'<p class="pg-add-lede">{LEDE}</p>' in sheet
    assert f'<a class="pg-add-primary" href="{home_path()}">{PRIMARY}</a>' in sheet
    assert f'<p class="pg-add-note">{NOTE}</p>' in sheet
    assert ">Cancel<" not in sheet
    assert "data-pg-sheet-close" not in sheet
    assert "/billing/subscriptions" not in sheet
    assert "data-guest-add-gate" not in sheet
    assert sheet == _sheet(client.get(add_path("ndps")).text)


def test_signed_in_add_unlock_opens_existing_gate(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    sheet = _sheet(client.get(add_path("ndps")).text)
    assert f'<a class="pg-add-primary" href="{home_path()}">{PRIMARY}</a>' in sheet
    gate = client.get(home_path(), follow_redirects=False)
    assert gate.status_code == 200
    assert 'class="EntitlementGate"' in gate.text
    assert 'data-playground-gate="not_subscribed"' in gate.text
    assert "Your RecallC account already includes the complete Constitution." in gate.text


def test_signed_in_add_does_not_touch_accepted_screens() -> None:
    bare = BARE.read_text(encoding="utf-8")
    _assert_no_old_markers(bare)
    assert 'data-act-head="{{ act.slug }}"' in bare
    assert "{% block act_dialog %}{% endblock %}" in bare
    add = ADD.read_text(encoding="utf-8")
    _assert_no_old_markers(add)
    # Over the Act when the Act context is present; the plain Playground
    # shell for the in-page fetch (X-Requested-With: pg-sheet) and POSTs.
    assert (
        '{% extends "bare_act.html" if act is defined and act else "playground_base.html" %}'
        in add
    )
    assert "{% block act_dialog %}" in add
    assert "{% block playground %}" in add
    assert add.count('{% include "partials/playground_add_panel.html" %}') == 2
    panel_src = ADD_PANEL.read_text(encoding="utf-8")
    _assert_no_old_markers(panel_src)
    assert panel_src.count('class="pg-sheet-panel"') == 1
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-guest-landing="desktop"' in landing
    browse = BROWSE.read_text(encoding="utf-8")
    assert "data-signed-in-browse-strip" in browse
    laws = LAWS.read_text(encoding="utf-8")
    assert "data-signed-in-laws-desktop" in laws
    css = STYLES.read_text(encoding="utf-8")
    band = css.split("Bare Act head (M2)", 1)[1].split(".ActHead-band {", 1)[1].split("}", 1)[0]
    assert "padding: 16px 40px 22px" in band
    mobile = MOBILE.read_text(encoding="utf-8")
    _assert_no_old_markers(mobile)
    pg_css = PG_CSS.read_text(encoding="utf-8")
    _assert_no_old_markers(pg_css)
    m2 = pg_css.split("Add sheet (M2)", 1)[1]
    title = m2.split(".pg-add-title {", 1)[1].split("}", 1)[0]
    assert "font-size: 22px" in title
    assert "font-weight: 500" in title
    lede = m2.split(".pg-add-lede {", 1)[1].split("}", 1)[0]
    assert "margin: 0 0 18px" in lede
    primary = m2.split(".pg-add-primary {", 1)[1].split("}", 1)[0]
    assert "min-height: 50px" in primary
    assert "width: 100%" in primary
    note = m2.split(".pg-add-note {", 1)[1].split("}", 1)[0]
    assert "text-align: center" in note
    assert "margin: 12px 0 0" in note
    panel = m2.split(".pg-sheet-panel[data-pg-add] {", 1)[1].split("}", 1)[0]
    assert "padding: 26px 28px 26px" in panel
    dialog = pg_css.split("dialog.pg-sheet {", 1)[1].split("}", 1)[0]
    assert "max-width: 460px" in dialog
    close = pg_css.split(".pg-sheet-close {", 1)[1].split("}", 1)[0]
    assert "top: 14px" in close
    assert "right: 14px" in close


def test_signed_in_add_does_not_change_guest_or_other_kinds(tmp_path: Path) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest"))
    guest_html = guest.get(add_path("ndps")).text
    _assert_no_old_markers(guest_html)
    guest_sheet = _sheet(guest_html)
    assert 'data-pg-kind="guest"' in guest_sheet
    assert f'<h1 id="pg-add-title" class="pg-add-title">{TITLE}</h1>' in guest_sheet
    assert "Playground needs an account. Reading The NDPS Act, 1985 stays free" in guest_sheet
    assert 'class="pg-add-primary" href="/login?next=' in guest_sheet
    assert "data-guest-add-gate>Sign in</a>" in guest_sheet
    assert "data-guest-add-gate>Create an account</a>" in guest_sheet
    assert PRIMARY not in guest_sheet
    assert NOTE not in guest_sheet
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    bns = client.get(add_path("bns")).text
    _assert_no_old_markers(bns)
    bns_sheet = _sheet(bns)
    assert 'data-pg-kind="subscribe"' in bns_sheet
    assert 'data-roster-confirm="bns"' in bns_sheet
    assert (
        '<p class="pg-add-lede">Turning The BNS, 2023 into a learning experience '
        "needs a plan. Reading it stays free.</p>" in bns_sheet
    )
    assert f'<a class="pg-add-primary" href="{home_path()}">{PRIMARY}</a>' in bns_sheet
    assert 'data-pg-sheet-return="/laws/bns"' in bns
    assert 'data-act-head="bns"' in bns
    ndps_sheet = _sheet(client.get(add_path("ndps")).text)
    assert "Resume Playground" not in ndps_sheet
    assert "Manage subscription" not in ndps_sheet
    assert "data-guest-add-gate" not in ndps_sheet


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
            page.locator('[data-act-head="ndps"] .ActHead-btn').click()
            page.wait_for_selector("[data-pg-add][data-pg-kind='subscribe']", timeout=8000)

        open_dialog()
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const unlock = panel.querySelector('.pg-add-primary');
              const cancel = panel.querySelector('.pg-add-secondary');
              const closeBtn = panel.querySelector('[data-pg-sheet-close].pg-sheet-close');
              const head = document.querySelector('[data-act-head="ndps"]');
              const box = panel.getBoundingClientRect();
              const note = panel.querySelector('.pg-add-note');
              const titleEl = panel.querySelector('#pg-add-title');
              const ledeEl = panel.querySelector('.pg-add-lede');
              const closeStyle = closeBtn && getComputedStyle(closeBtn);
              const panelStyle = getComputedStyle(panel);
              const backdrop = getComputedStyle(dialog, '::backdrop');
              return {
                open: dialog && dialog.open,
                kind: panel.getAttribute('data-pg-kind'),
                panels: document.querySelectorAll('.pg-sheet-panel').length,
                eyebrow: Boolean(panel.querySelector('.pg-eyebrow')),
                title: titleEl.textContent.trim(),
                titleSize: getComputedStyle(titleEl).fontSize,
                titleWeight: getComputedStyle(titleEl).fontWeight,
                lede: ledeEl.textContent.trim(),
                ledeMarginBottom: getComputedStyle(ledeEl).marginBottom,
                unlockText: unlock.textContent.trim(),
                unlockHref: unlock.getAttribute('href'),
                unlockH: unlock.getBoundingClientRect().height,
                note: note && note.textContent.trim(),
                noteAlign: note && getComputedStyle(note).textAlign,
                noteMarginTop: note && getComputedStyle(note).marginTop,
                cancel: Boolean(cancel),
                hasClose: Boolean(closeBtn),
                closeLabel: closeBtn && closeBtn.getAttribute('aria-label'),
                closeTop: closeStyle && closeStyle.top,
                closeRight: closeStyle && closeStyle.right,
                panelW: box.width,
                panelH: box.height,
                panelPad: panelStyle.padding,
                scrim: backdrop.backgroundColor,
                guestGate: Boolean(panel.querySelector('[data-guest-add-gate]')),
                leaked: {
                  already: panel.innerText.includes('Already in Playground'),
                  resume: panel.innerText.includes('Resume Playground'),
                  full: panel.innerText.includes('Playground full'),
                  pending: panel.innerText.includes('temporarily unavailable'),
                  entire: panel.innerText.includes('Entire Act'),
                  signin: panel.innerText.includes('Create an account'),
                  cancel: panel.innerText.includes('Cancel'),
                },
                background: Boolean(head),
                subscribeCta: head && head.querySelector('.ActHead-btn') &&
                  head.querySelector('.ActHead-btn').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator("[data-pg-add] .pg-add-primary").click()
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
                head: Boolean(document.querySelector('[data-act-head="ndps"]')),
                focused: document.activeElement &&
                  document.activeElement.classList.contains('ActHead-btn'),
              };
            }"""
        )

        open_dialog()
        page.keyboard.press("Escape")
        closed_esc = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              return {
                open: Boolean(dialog && dialog.open),
                path: location.pathname,
              };
            }"""
        )

        page.goto(f"{origin}{add_path('ndps')}", wait_until="networkidle")
        direct = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet[data-pg-sheet-direct]');
              const panel = document.querySelector('[data-pg-add]');
              return {
                open: Boolean(dialog && dialog.open),
                kind: panel && panel.getAttribute('data-pg-kind'),
                head: Boolean(document.querySelector('[data-act-head="ndps"]')),
                path: location.pathname,
              };
            }"""
        )
        page.keyboard.press("Escape")
        page.wait_for_function("() => location.pathname === '/laws/ndps'", timeout=8000)
        direct_closed = page.evaluate("() => location.pathname")

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.locator('[data-act-head="ndps"] [data-pg-sheet]').first.click()
        page.wait_for_selector("[data-pg-add]", timeout=8000)
        phone_geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const unlock = panel.querySelector('.pg-add-primary');
              const cancel = panel.querySelector('.pg-add-secondary');
              return {
                panels: document.querySelectorAll('.pg-sheet-panel').length,
                title: panel.querySelector('#pg-add-title').textContent.trim(),
                titleSize: getComputedStyle(panel.querySelector('#pg-add-title')).fontSize,
                unlockHref: unlock && unlock.getAttribute('href'),
                unlockW: unlock && unlock.getBoundingClientRect().width,
                cancel: Boolean(cancel),
              };
            }"""
        )
        browser.close()

    assert geo["open"] is True
    assert geo["kind"] == "subscribe"
    assert geo["panels"] == 1
    assert geo["eyebrow"] is False
    assert geo["title"] == TITLE
    assert geo["titleSize"] == "22px"
    assert geo["titleWeight"] in ("500",)
    assert geo["lede"] == LEDE
    assert geo["ledeMarginBottom"] == "18px"
    assert geo["unlockText"] == PRIMARY
    assert geo["unlockHref"] == home_path()
    assert geo["unlockH"] == pytest.approx(50, abs=2)
    assert geo["note"] == NOTE
    assert geo["noteAlign"] == "center"
    assert geo["noteMarginTop"] == "12px"
    assert geo["cancel"] is False
    assert geo["hasClose"] is True
    assert geo["closeLabel"] == "Close"
    assert geo["closeTop"] == "14px"
    assert geo["closeRight"] == "14px"
    assert geo["panelW"] == pytest.approx(460, abs=8)
    assert "26px" in geo["panelPad"]
    assert "28px" in geo["panelPad"]
    assert geo["scrim"] not in ("", "rgba(0, 0, 0, 0)")
    assert geo["guestGate"] is False
    assert geo["leaked"]["already"] is False
    assert geo["leaked"]["resume"] is False
    assert geo["leaked"]["full"] is False
    assert geo["leaked"]["pending"] is False
    assert geo["leaked"]["entire"] is False
    assert geo["leaked"]["signin"] is False
    assert geo["leaked"]["cancel"] is False
    assert geo["background"] is True
    assert geo["subscribeCta"] == "Subscribe to use Playground"
    assert gate["path"] == home_path()
    assert gate["present"] is True
    assert gate["reason"] == "not_subscribed"
    assert gate["title"] == "Your RecallC account already includes the complete Constitution."
    assert closed_x["open"] is False
    assert closed_x["path"] == "/laws/ndps"
    assert closed_x["head"] is True
    assert closed_x["focused"] is True
    assert closed_esc["open"] is False
    assert closed_esc["path"] == "/laws/ndps"
    assert direct["open"] is True
    assert direct["kind"] == "subscribe"
    assert direct["head"] is True
    assert direct["path"] == add_path("ndps")
    assert direct_closed == "/laws/ndps"
    assert phone_geo["panels"] == 1
    assert phone_geo["title"] == TITLE
    assert phone_geo["titleSize"] == "19px"
    assert phone_geo["unlockHref"] == home_path()
    assert phone_geo["unlockW"] >= 300
    assert phone_geo["cancel"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
