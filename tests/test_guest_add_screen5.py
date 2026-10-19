"""Guest desktop Add dialog Screen 5 (CTA map guest/05-screen).

M2: one Add sheet per state (§2.1), drawn over the generated Act head; the
desktop and phone twins are gone and CSS lays the same panel out as a modal
at 1280 and a bottom sheet at 390. Guest `/playground/laws/ndps/add` is
checked here. Bare Act readers, Landing, Browse, Laws index, and subscriber
sheets stay on their own states.
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
from constitution_memorizer.playground.eligibility import playground_bare_act_spec
from constitution_memorizer.playground.urls import add_path
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
LOGIN_NEXT = f"/login?next={add_path('ndps')}"
NDPS = get_bare_act("ndps")
GUEST_ADD_TITLE = "Add to Playground"
READING_NAME = playground_bare_act_spec("ndps").short_name
PRIMARY = "Sign in to use Playground"


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


def _sheet(html: str) -> str:
    """The one Add panel: `<section class="pg-sheet-panel" data-pg-add …>`."""
    return html.split('class="pg-sheet-panel"', 1)[1].split("</section>", 1)[0]


def _head(html: str) -> str:
    return html.split('class="panel ActHead', 1)[1].split("</section>", 1)[0]


def _band(html: str) -> str:
    return _head(html).split("data-act-list", 1)[0]


def test_screen5_sheet_copy_and_gate_actions(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get(add_path("ndps")).text
    sheet = _sheet(html)
    assert f'<h1 id="pg-add-title" class="pg-add-title">{GUEST_ADD_TITLE}</h1>' in sheet
    assert READING_NAME == "The NDPS Act, 1985"
    assert READING_NAME == NDPS.short_name
    assert (
        '<p class="pg-add-lede">Playground needs an account. Reading '
        f"{READING_NAME} stays free — sign in and you’ll come right back here.</p>"
    ) in sheet
    assert "Playground needs an account" in sheet
    assert "stays free" in sheet
    assert "come right back here" in sheet
    assert sheet.count("data-guest-add-gate") == 2
    assert sheet.count(f'href="{LOGIN_NEXT}"') == 2
    assert f'<a class="pg-add-primary" href="{LOGIN_NEXT}" data-guest-add-gate>Sign in</a>' in sheet
    assert (
        f'<a class="pg-add-secondary" href="{LOGIN_NEXT}" data-guest-add-gate>Create an account</a>'
    ) in sheet
    assert ">Cancel<" not in sheet
    assert "data-pg-sheet-close" not in sheet
    assert 'type="button"' not in sheet  # the phone twin's inert buttons are gone
    assert "<form" not in sheet
    assert "Already in Playground" not in sheet
    assert ">Sections<" not in sheet
    assert ">Continue<" not in sheet
    assert 'data-pg-kind="guest"' in sheet


def test_screen5_one_sheet_for_both_widths_over_the_act_page(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get(add_path("ndps")).text
    # M2 §2.1: one panel, one dialog; no desktop/phone twins.
    assert html.count('class="pg-sheet-panel"') == 1
    assert html.count("<dialog") == 1
    for gone in (
        "data-guest-add-desktop",
        "data-guest-add-phone",
        "guest-add-title",
        "guest-add-lede",
        "guest-add-signin",
        "guest-add-create",
        "PlaygroundShell",
        "data-hard-gate",
    ):
        assert gone not in html, gone
    dialog = html.split("<dialog", 1)[1].split(">", 1)[0]
    assert 'class="pg-sheet"' in dialog
    assert "data-pg-sheet-host" in dialog
    assert "data-pg-sheet-direct" in dialog
    assert 'data-pg-sheet-return="/laws/ndps"' in dialog
    assert 'aria-labelledby="pg-add-title"' in dialog
    assert dialog.rstrip().endswith("open")
    # M2 Q4: the direct URL is the Act page with the sheet open.
    assert 'data-mscreen="bareact"' in html
    assert 'data-act-head="ndps"' in html
    assert html.count('class="panel ActHead') == 1
    assert f'<h1 class="ActHead-title">{NDPS.title}</h1>' in html
    assert html.count('<details class="bareact-chapter">') == NDPS.chapter_count
    assert html.count(PRIMARY) == 1
    css = (ROOT / "src/constitution_memorizer/web/static/playground.css").read_text(
        encoding="utf-8"
    )
    assert "Add sheet (M2)" in css
    m2 = css.split("Add sheet (M2)", 1)[1]
    primary = m2.split(".pg-add-primary {", 1)[1].split("}", 1)[0]
    assert "width: 100%" in primary
    assert "min-height: 50px" in primary
    phone = m2.split("@media (max-width: 560px) {", 1)[1].split("\n}\n", 1)[0]
    assert ".pg-add-title {" in phone


def test_screen5_in_page_fetch_returns_the_panel_alone(tmp_path: Path) -> None:
    # playground.js fetches the same URL with X-Requested-With: pg-sheet and
    # lifts `.pg-sheet-panel` into the live dialog: no Act head, no dialog,
    # the same guest gate links.
    html = _guest_client(tmp_path).get(
        add_path("ndps"), headers={"X-Requested-With": "pg-sheet"}
    ).text
    assert html.count('class="pg-sheet-panel"') == 1
    assert "<dialog" not in html
    assert "data-pg-sheet-direct" not in html
    assert "ActHead" not in html
    assert "data-act-list" not in html
    assert "PlaygroundShell" in html
    assert "data-hard-gate" in html
    sheet = _sheet(html)
    assert 'data-pg-kind="guest"' in sheet
    assert f'<h1 id="pg-add-title" class="pg-add-title">{GUEST_ADD_TITLE}</h1>' in sheet
    assert sheet.count("data-guest-add-gate") == 2
    assert sheet.count(f'href="{LOGIN_NEXT}"') == 2
    assert ">Cancel<" not in sheet
    assert "<form" not in sheet


def test_screen5_does_not_restore_subscriber_ctas_on_ndps_head(tmp_path: Path) -> None:
    band = _band(_guest_client(tmp_path).get("/laws/ndps").text)
    assert PRIMARY in band
    assert "Already in Playground" not in band
    assert ">Sections</a>" not in band  # the About card's <dt> is not a link
    assert ">Continue</a>" not in band
    assert "ActHead-inpg" not in band
    assert NDPS.title in band


def test_screen5_does_not_change_other_screens(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    landing = client.get("/").text
    assert 'data-guest-landing="desktop"' in landing
    browse = client.get("/browse").text
    assert "Browse the Constitution" in browse
    laws = client.get("/laws").text
    assert "data-guest-laws-desktop" in laws
    assert "pg-sheet-panel" not in laws
    bns = client.get("/laws/bns").text
    assert 'data-act-head="bns"' in bns
    assert "pg-sheet-panel" not in bns
    section = client.get("/laws/ndps/section/1").text
    assert "ActHead" not in section
    assert "pg-sheet-panel" not in section
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
    assert "data-guest-add-gate" not in html
    assert "Create an account" not in html
    assert "data-pg-add-confirm" in html
    assert 'data-pg-kind="eligible_to_add"' in html
    assert f'action="{add_path("ndps")}"' in html
    assert 'name="csrf_token"' in html


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
            page.locator(".ActHead .ActHead-btn").click()
            page.wait_for_selector("[data-pg-add][data-pg-kind='guest']", timeout=8000)

        open_dialog()
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const gates = [...panel.querySelectorAll('[data-guest-add-gate]')];
              const head = document.querySelector('.ActHead');
              return {
                open: dialog && dialog.open,
                panels: document.querySelectorAll('.pg-sheet-panel').length,
                panelDisplay: getComputedStyle(panel).display,
                eyebrow: Boolean(panel.querySelector('.pg-eyebrow')),
                title: panel.querySelector('.pg-add-title').textContent.trim(),
                lede: panel.querySelector('.pg-add-lede').textContent.trim(),
                labels: gates.map((el) => el.textContent.trim()),
                tags: gates.map((el) => el.tagName),
                hrefs: gates.map((el) => el.getAttribute('href')),
                classes: gates.map((el) => el.className),
                hasClose: Boolean(panel.querySelector('[data-pg-sheet-close]')),
                cancel: [...panel.querySelectorAll('a, button')].some((a) => a.textContent.trim() === 'Cancel'),
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

        page.locator("[data-pg-add] .pg-add-primary").click()
        page.wait_for_url("**/login**", timeout=8000)
        signin_url = page.url
        signin_html = page.content()
        page.screenshot(path=str(signin_path), full_page=False)

        open_dialog()
        page.locator("[data-pg-add] .pg-add-secondary").click()
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
                head: Boolean(document.querySelector('.ActHead[data-act-head="ndps"]')),
              };
            }"""
        )
        page.screenshot(path=str(close_path), full_page=False)

        phone = browser.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        phone.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        phone.locator(".ActHead .ActHead-btn").click()
        phone.wait_for_selector("[data-pg-add]", timeout=8000)
        phone_geo = phone.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const signin = panel.querySelector('.pg-add-primary');
              const create = panel.querySelector('.pg-add-secondary');
              const p = panel.getBoundingClientRect();
              return {
                panels: document.querySelectorAll('.pg-sheet-panel').length,
                panelDisplay: getComputedStyle(panel).display,
                title: panel.querySelector('h1').textContent.trim(),
                hasCancel: [...panel.querySelectorAll('a, button')].some((a) => a.textContent.trim() === 'Cancel'),
                createVisible: create.offsetParent !== null && create.textContent.trim() === 'Create an account',
                signinTag: signin.tagName,
                signinHref: signin.getAttribute('href'),
                createTag: create.tagName,
                createHref: create.getAttribute('href'),
                bottomSheet: p.bottom >= 840 && p.width >= 300,
              };
            }"""
        )
        browser.close()

    assert geo["open"] is True
    assert geo["panels"] == 1
    assert geo["panelDisplay"] != "none"
    assert geo["eyebrow"] is False
    assert geo["title"] == GUEST_ADD_TITLE
    assert READING_NAME in geo["lede"]
    assert geo["labels"] == ["Sign in", "Create an account"]
    assert geo["tags"] == ["A", "A"]
    assert geo["hrefs"] == [LOGIN_NEXT, LOGIN_NEXT]
    assert geo["classes"] == ["pg-add-primary", "pg-add-secondary"]
    assert geo["hasClose"] is True  # the ✕ playground.js injects
    assert geo["cancel"] is False
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
    assert phone_geo["panels"] == 1
    assert phone_geo["panelDisplay"] != "none"
    assert phone_geo["title"] == GUEST_ADD_TITLE
    assert phone_geo["hasCancel"] is False
    assert phone_geo["createVisible"] is True
    assert phone_geo["signinTag"] == "A"
    assert phone_geo["signinHref"] == LOGIN_NEXT
    assert phone_geo["createTag"] == "A"
    assert phone_geo["createHref"] == LOGIN_NEXT
    assert phone_geo["bottomSheet"] is True
    assert shot_path.is_file()
