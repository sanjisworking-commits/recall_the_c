"""Phone signed-in Free Add sheet Screen 02 (CTA map signedIn/02-screen).

Authorized: ChatGPT. Authenticated Free overlay on signedIn 01 /laws/ndps.
Since M2 it is ONE sheet per state on both widths (phone raises it as a
bottom sheet by CSS): title "Add to Playground", lede, primary "Unlock
Playground" navigating to GET /playground (existing not_subscribed Gate),
tiers/price footnote, no Cancel. Guest, Plus confirm/scope, Expired/Halted
sheets stay separate by `data-pg-kind` and the lifecycle attributes. Gate
restyle is signedIn 03.
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
from constitution_memorizer.web.bare_acts import get_bare_act

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
ADD_PANEL = ROOT / "src/constitution_memorizer/web/templates/partials/playground_add_panel.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
PG_JS = ROOT / "src/constitution_memorizer/web/static/playground.js"
USER = UUID("11111111-1111-4111-8111-111111111111")
NDPS_TITLE = get_bare_act("ndps").title
TITLE = "Add to Playground"
PRIMARY = "Unlock Playground"
# The lede uses the registry's short name for every Act ("The NDPS Act, 1985"
# for NDPS), which is the CTA map's own wording.
LEDE = (
    "Turning The NDPS Act, 1985 into a learning experience needs a plan. "
    "Reading it stays free."
)
MAP_LEDE_FULL = (
    "Turning The NDPS Act, 1985 into a learning experience needs a plan."
)
NOTE = "Plus · Pro · Max — from ₹199 / month. Constitution learning stays free."
GATE_TITLE = "Your RecallC account already includes the complete Constitution."
FORBIDDEN = (
    "Already in Playground",
    ">Sections<",
    ">Continue<",
    "Sign in to use Playground",
    "Create an account",
    "Resume Playground",
    "Manage subscription",
    "Entire Act",
    "Choose sections",
    "Core",
    "Deep",
    "Infinite",
    "₹149",
    "₹299",
    "₹499",
    ">Cancel<",
    "data-pg-sheet-close",
    "data-guest-add-gate",
    "/billing/subscriptions",
    "/playground?stage=plans",
    "/billing/subscriptions/checkout",
    "/billing/subscriptions/create",
    "included with your account",
)
OLD_MARKERS = (
    "data-signed-in-add-desktop",
    "data-signed-in-add-phone",
    "data-guest-add-desktop",
    "data-guest-add-phone",
    "data-plus-add-desktop",
    "data-plus-add-phone",
    "data-expired-add-phone",
    "data-halted-add-phone",
    'data-plus-add="desktop"',
    'data-expired-add="desktop"',
    'data-halted-add="desktop"',
    'class="guest-add-',
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


def _sheet(html: str) -> str:
    """The one `.pg-sheet-panel` (the Add sheet) in the page."""
    return html.split('class="pg-sheet-panel"', 1)[1].split("</section>", 1)[0]


def _sheet_attrs(html: str) -> str:
    return html.split('class="pg-sheet-panel"', 1)[1].split(">", 1)[0]


def _assert_no_old_markers(text: str) -> None:
    for marker in OLD_MARKERS:
        assert marker not in text, marker


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
    _assert_no_old_markers(html)
    assert KIND_SUBSCRIBE == "subscribe"
    assert "data-pg-add" in html
    assert html.count('class="pg-sheet-panel"') == 1
    attrs = _sheet_attrs(html)
    assert 'data-pg-kind="subscribe"' in attrs
    assert 'data-roster-confirm="ndps"' in attrs
    assert "data-expired-add" not in attrs
    assert "data-halted-add" not in attrs
    panel = _sheet(html)
    assert f'<h1 id="pg-add-title" class="pg-add-title">{TITLE}</h1>' in panel
    assert panel.count(TITLE) == 1
    assert panel.count(PRIMARY) == 1
    assert f'<p class="pg-add-lede">{LEDE}</p>' in panel
    assert MAP_LEDE_FULL in panel
    assert "Turning NDPS Act into" not in panel
    assert f'<p class="pg-add-note">{NOTE}</p>' in panel
    assert catalogue_from_price() == "from ₹199"
    assert catalogue_from_price() in NOTE
    assert f'<a class="pg-add-primary" href="{home_path()}">{PRIMARY}</a>' in panel
    assert 'href="/billing/subscriptions"' not in panel
    assert 'href="/playground?stage=plans"' not in panel
    assert ">Cancel<" not in panel
    assert "pg-add-secondary" not in panel
    assert "cancel_href" not in panel
    assert 'href="/laws/ndps"' not in panel
    assert "<form" not in panel
    assert "data-pg-add-confirm" not in panel
    assert "pg-eyebrow" not in panel
    for phrase in FORBIDDEN:
        assert phrase not in panel, phrase
    # One panel serves both widths; it ships inside an open <dialog> over the
    # Act page and closing it returns to the Act (M2 Q4).
    assert (
        '<dialog class="pg-sheet" data-pg-sheet-host data-pg-sheet-direct '
        'data-pg-sheet-return="/laws/ndps"' in html
    )
    assert 'aria-labelledby="pg-add-title" open>' in html
    assert html.count("<dialog") == 1
    assert 'data-act-head="ndps"' in html
    assert 'data-mscreen="bareact"' in html
    assert "PlaygroundShell" not in html
    assert "data-hard-gate" not in html
    assert _facts(client) == before
    # The in-page open (playground.js, X-Requested-With: pg-sheet) gets the
    # same panel alone, without the Act page or a server-rendered dialog.
    fetched = client.get(add_path("ndps"), headers={"X-Requested-With": "pg-sheet"})
    assert fetched.status_code == 200
    assert fetched.text.count('class="pg-sheet-panel"') == 1
    assert "<dialog" not in fetched.text
    assert "data-act-head" not in fetched.text
    # Alone, the panel is its own dialog; inside the host <dialog> it is not.
    alone = _sheet(unescape(fetched.text))
    assert 'role="dialog" aria-modal="true" aria-labelledby="pg-add-title"' in alone
    assert alone.replace('role="dialog" aria-modal="true" aria-labelledby="pg-add-title"', "") == panel
    assert _facts(client) == before


def test_phone_signed_in_add_source_has_no_billing_or_cancel() -> None:
    page_src = ADD.read_text(encoding="utf-8")
    _assert_no_old_markers(page_src)
    assert (
        '{% extends "bare_act.html" if act is defined and act else "playground_base.html" %}'
        in page_src
    )
    assert page_src.count('{% include "partials/playground_add_panel.html" %}') == 2
    assert "data-pg-sheet-direct" in page_src
    assert 'data-pg-sheet-return="{{ cancel_href }}"' in page_src
    src = ADD_PANEL.read_text(encoding="utf-8")
    _assert_no_old_markers(src)
    assert src.count('class="pg-sheet-panel"') == 1
    subscribe = src.split('{% elif kind == "subscribe" %}', 1)[1].split(
        '{% elif kind == "resume" %}', 1
    )[0]
    assert f'<h1 id="pg-add-title" class="pg-add-title">{TITLE}</h1>' in subscribe
    assert "reading_name" in subscribe
    assert f'<a class="pg-add-primary" href="/playground">{PRIMARY}</a>' in subscribe
    assert "catalogue_plans" in subscribe
    assert "from_price" in subscribe
    assert "Constitution learning stays free." in subscribe
    assert "billing" not in subscribe
    assert "cancel_href" not in subscribe
    assert "Cancel" not in subscribe
    assert "pg-add-secondary" not in subscribe
    assert "<form" not in subscribe
    # Unlock Playground is the subscribe sheet's only use; no other state
    # borrows it.
    assert src.count(PRIMARY) == 1
    js = PG_JS.read_text(encoding="utf-8")
    assert "signed-add-unlock" not in js
    assert "data-signed-in-add-phone" not in js
    assert "event.target === dialog" in js
    assert "data-pg-sheet-direct" in js
    assert "data-pg-sheet-return" in js
    assert "showModal" in js
    assert "replaceState" in js


def test_phone_signed_in_add_css_is_breakpoint_scoped() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    _assert_no_old_markers(css)
    assert "is signedIn/02-screen:" not in css
    # Phone geometry is the shared bottom-sheet rule for every dialog.
    dialog_phone = css.split("@media (max-width: 560px)", 1)[1].split(
        "/* R2 section/clause picker */", 1
    )[0]
    assert "--pg-sheet-anchor: bottom" in dialog_phone
    assert "width: calc(100% - (2 * var(--pg-shell-pad)))" in dialog_phone
    assert "max-width: none" in dialog_phone
    assert "max-height: min(92dvh, 100%)" in dialog_phone
    assert "safe-area-inset-bottom" in dialog_phone
    assert "inset: auto 0 0 0" in dialog_phone
    close_phone = dialog_phone.split(".pg-sheet-close {", 1)[1].split("}", 1)[0]
    assert "display: none" in close_phone
    # The M2 sheet rules: one set of .pg-add-* classes, phone-scoped tweaks.
    m2 = css.split("Add sheet (M2)", 1)[1]
    primary = m2.split(".pg-add-primary {", 1)[1].split("}", 1)[0]
    assert "width: 100%" in primary
    assert "min-height: 50px" in primary
    phone = m2.split("@media (max-width: 560px) {", 1)[1].split("\n}\n", 1)[0]
    panel = phone.split(".pg-sheet-panel[data-pg-add] {", 1)[1].split("}", 1)[0]
    assert "safe-area-inset-bottom" in panel
    title = phone.split(".pg-add-title {", 1)[1].split("}", 1)[0]
    assert "font-size: 19px" in title
    assert "padding-right: 0" in title
    assert ":has([data-signed-in-add-phone])" not in css
    assert ":has([data-guest-add-phone])" not in css
    assert ":has([data-plus-add-phone])" not in css
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg51" in base
    assert "playground.css?v=pg49" not in base
    assert "playground.css?v=pg32" not in base
    assert "styles.css?v=main88" in base
    assert "mobile.css?v=mob107" in base
    assert "playground.js?v=pg10" in base
    assert "mobile.js?v=mob30" in base


def test_guest_plus_expired_halted_add_sheets_stay_separate(tmp_path: Path) -> None:
    guest = TestClient(_guest_app(tmp_path / "guest"))
    guest_html = guest.get(add_path("ndps")).text
    _assert_no_old_markers(guest_html)
    assert 'data-pg-kind="guest"' in _sheet_attrs(guest_html)
    guest_panel = _sheet(guest_html)
    assert "data-guest-add-gate>Sign in</a>" in guest_panel
    assert "data-guest-add-gate>Create an account</a>" in guest_panel
    assert PRIMARY not in guest_panel
    assert NOTE not in guest_panel

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get(add_path("ndps")).text
    _assert_no_old_markers(plus_html)
    plus_attrs = _sheet_attrs(plus_html)
    assert 'data-pg-kind="eligible_to_add"' in plus_attrs
    assert "data-expired-add" not in plus_attrs
    assert "data-halted-add" not in plus_attrs
    plus_panel = _sheet(plus_html)
    assert 'data-add-step="confirm"' in plus_panel
    assert 'data-add-step="scope"' in plus_panel
    assert "data-pg-add-confirm" in plus_panel
    assert f'<form method="post" action="{add_path("ndps")}" data-pg-add-confirm>' in plus_panel
    assert '<input type="hidden" name="csrf_token"' in plus_panel
    assert '<input type="hidden" name="confirm" value="add">' in plus_panel
    assert '<button type="submit" class="pg-add-primary">Add to Playground</button>' in plus_panel
    assert PRIMARY not in plus_panel
    assert NOTE not in plus_panel
    assert "Entire Act" in plus_panel
    assert "Choose sections" in plus_panel
    assert 'data-pg-sheet-close>Cancel</a>' in plus_panel

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
    _assert_no_old_markers(expired_html)
    expired_attrs = _sheet_attrs(expired_html)
    assert 'data-pg-kind="resume"' in expired_attrs
    assert "data-expired-add" in expired_attrs
    assert "data-halted-add" not in expired_attrs
    expired_panel = _sheet(expired_html)
    assert PRIMARY not in expired_panel
    assert NOTE not in expired_panel
    assert ">Resume Playground</a>" in expired_panel
    assert 'href="/laws/ndps" data-pg-sheet-close>Cancel</a>' in expired_panel

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get(add_path("ndps")).text
    _assert_no_old_markers(halted_html)
    halted_attrs = _sheet_attrs(halted_html)
    assert "data-halted-add" in halted_attrs
    assert "data-expired-add" not in halted_attrs
    halted_panel = _sheet(halted_html)
    assert "Payment retries have stopped" in halted_panel
    assert "Manage subscription" in halted_panel
    assert PRIMARY not in halted_panel
    assert NOTE not in halted_panel


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
            page.locator('[data-act-head="ndps"] .ActHead-btn').click()
            page.wait_for_selector(
                "[data-pg-add][data-pg-kind='subscribe']", timeout=8000
            )
            page.wait_for_timeout(400)

        open_sheet()
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const unlock = panel.querySelector('.pg-add-primary');
              const cancel = [...panel.querySelectorAll('a, button')].find(
                (el) => el.textContent.trim() === 'Cancel'
              );
              const closeBtn = panel.querySelector('.pg-sheet-close');
              const tabs = document.querySelector('[data-signed-in-bareact-phone-tabs]');
              const handle = getComputedStyle(panel, '::before');
              const d = dialog.getBoundingClientRect();
              const p = panel.getBoundingClientRect();
              const head = document.querySelector('[data-act-head="ndps"]');
              const cta = head && head.querySelector('.ActHead-btn');
              return {
                open: Boolean(dialog && dialog.open),
                kind: panel.getAttribute('data-pg-kind'),
                url: location.pathname,
                panels: document.querySelectorAll('.pg-sheet-panel').length,
                title: panel.querySelector('#pg-add-title').textContent.trim(),
                titleSize: getComputedStyle(panel.querySelector('#pg-add-title')).fontSize,
                lede: panel.querySelector('.pg-add-lede').textContent.trim(),
                note: panel.querySelector('.pg-add-note') &&
                  panel.querySelector('.pg-add-note').textContent.trim(),
                unlock: {
                  tag: unlock && unlock.tagName,
                  href: unlock && unlock.getAttribute('href'),
                  text: unlock && unlock.textContent.trim(),
                  width: unlock && unlock.getBoundingClientRect().width,
                  height: unlock && unlock.getBoundingClientRect().height,
                },
                cancel: Boolean(cancel),
                secondary: Boolean(panel.querySelector('.pg-add-secondary')),
                closeDisplay: closeBtn ? getComputedStyle(closeBtn).display : 'missing',
                handleDisplay: handle.display,
                handleHeight: handle.height,
                dialog: { top: d.top, left: d.left, width: d.width, height: d.height },
                panel: { top: p.top, left: p.left, width: p.width, bottom: p.bottom },
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                tabFocused: tabs && tabs.contains(document.activeElement),
                backgroundTitle: head && head.querySelector('.ActHead-title')
                  && head.querySelector('.ActHead-title').textContent.trim(),
                subscribe: cta && cta.textContent.trim(),
                already: head && head.innerText.includes('Already in Playground'),
                guestGate: Boolean(panel.querySelector('[data-guest-add-gate]')),
                billing: !!panel.querySelector('a[href="/billing/subscriptions"]'),
                plans: !!panel.querySelector('a[href*="stage=plans"]'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.set_viewport_size({"width": 390, "height": 560})
        short = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const unlock = panel.querySelector('.pg-add-primary');
              const box = unlock.getBoundingClientRect();
              return {
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                unlockW: box.width,
                unlockH: box.height,
                inPanel: panel.contains(unlock),
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
              const cta = document.querySelector('[data-act-head="ndps"] .ActHead-btn');
              return {
                open: Boolean(dialog && dialog.open),
                url: location.pathname,
                focused: document.activeElement === cta,
                title: document.querySelector('[data-act-head="ndps"] .ActHead-title')
                  && document.querySelector('[data-act-head="ndps"] .ActHead-title').textContent.trim(),
              };
            }"""
        )

        page.locator('[data-act-head="ndps"] .ActHead-btn').click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='subscribe']", timeout=8000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        escaped = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const cta = document.querySelector('[data-act-head="ndps"] .ActHead-btn');
              return {
                open: Boolean(dialog && dialog.open),
                url: location.pathname,
                focused: document.activeElement === cta,
              };
            }"""
        )

        n_before = len(requests)
        page.locator('[data-act-head="ndps"] .ActHead-btn').click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='subscribe']", timeout=8000)
        page.locator("[data-pg-add] .pg-add-primary").click()
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
    assert geo["panels"] == 1
    assert geo["title"] == TITLE
    assert geo["titleSize"] == "19px"
    assert geo["lede"] == LEDE
    assert geo["note"] == NOTE
    assert geo["unlock"]["tag"] == "A"
    assert geo["unlock"]["href"] == home_path()
    assert geo["unlock"]["text"] == PRIMARY
    assert geo["unlock"]["width"] >= 300
    assert geo["unlock"]["height"] >= 44
    assert geo["cancel"] is False
    assert geo["secondary"] is False
    assert geo["closeDisplay"] == "none"
    assert geo["handleDisplay"] == "block"
    assert geo["dialog"]["width"] >= 300
    assert geo["dialog"]["top"] > 300
    assert geo["panel"]["width"] >= 300
    assert geo["panel"]["bottom"] >= 840
    assert geo["panel"]["top"] > 400
    assert geo["overflow"] is False
    assert geo["backgroundTitle"] == NDPS_TITLE
    assert geo["subscribe"] == "Subscribe to use Playground"
    assert geo["already"] is False
    assert geo["guestGate"] is False
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
    assert closed["title"] == NDPS_TITLE
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
        page.locator('[data-act-head="ndps"] .ActHead-btn').click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='subscribe']", timeout=8000)
        page.wait_for_timeout(300)
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const unlock = panel.querySelector('.pg-add-primary');
              const closeBtn = panel.querySelector('.pg-sheet-close');
              const d = dialog.getBoundingClientRect();
              return {
                open: Boolean(dialog && dialog.open),
                panels: document.querySelectorAll('.pg-sheet-panel').length,
                title: panel.querySelector('#pg-add-title').textContent.trim(),
                titleSize: getComputedStyle(panel.querySelector('#pg-add-title')).fontSize,
                lede: panel.querySelector('.pg-add-lede').textContent.trim(),
                unlockHref: unlock.getAttribute('href'),
                unlockText: unlock.textContent.trim(),
                cancel: Boolean(panel.querySelector('.pg-add-secondary')),
                closeDisplay: closeBtn ? getComputedStyle(closeBtn).display : 'missing',
                dialogWidth: d.width,
                notFullBleed: d.width < 800 && d.left > 100,
                billing: !!panel.querySelector('a[href="/billing/subscriptions"]'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["open"] is True
    assert geo["panels"] == 1
    assert geo["title"] == TITLE
    assert geo["titleSize"] == "22px"
    assert geo["lede"] == LEDE
    assert geo["unlockHref"] == home_path()
    assert geo["unlockText"] == PRIMARY
    assert geo["cancel"] is False
    assert geo["closeDisplay"] != "none"
    assert geo["dialogWidth"] == pytest.approx(460, abs=8)
    assert geo["notFullBleed"] is True
    assert geo["billing"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
