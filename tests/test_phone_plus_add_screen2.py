"""Phone Plus NDPS Add confirm Screen 02 (CTA map plus/02-screen).

Authorized: ChatGPT. Authenticated active Plus overlay from Plus 01
eligible_to_add on /laws/ndps. Screen 05 copy on [data-plus-add-phone],
signedIn 02 full-bleed sheet, existing confirm form and scope step.
re_add / roster_full / already_active stay off Plus chrome. Desktop
Screen 05, Guest 02, Free 02, Expired/Halted, and Plus 01 stay unchanged.
"""

from __future__ import annotations

import re
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
from constitution_memorizer.auth.sessions import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    InMemorySessionStore,
)
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.roster.period import (
    playground_month_bounds,
    playground_month_name,
)
from constitution_memorizer.playground.urls import add_path, law_path, remove_path, sections_path
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.guest_bareact_head import (
    NDPS_GUEST_READING_NAME,
    NDPS_GUEST_TITLE,
)
from tests.conftest import PLAYGROUND_TEST_NOW

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
PG_JS = ROOT / "src/constitution_memorizer/web/static/playground.js"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
MONTH = playground_month_name(playground_month_bounds(PLAYGROUND_TEST_NOW)[0])
TITLE = "Add to Playground"
LEDE = (
    f"{NDPS_GUEST_READING_NAME} joins this month's Playground — learnable, verbatim. "
    "The reader itself never changes."
)
SPACE = f"This will use 1 of your 10 law spaces in {MONTH}. 9 will remain."
FOOTER = "Already yours this month — reopening it never uses another space."
FULL_LAWS = (
    "bns",
    "bnss",
    "uapa",
    "pss",
    "mtp",
    "ipc",
    "crpc",
    "cpc",
    "iea",
    "ida",
)
FORBIDDEN = (
    "Already in Playground",
    "Unlock Playground",
    "Subscribe to use Playground",
    "Sign in",
    "Create an account",
    "Resume Playground",
    "Playground full this month",
    FOOTER,
    "law unlocks",
    "7 will remain",
    "Premium",
    "Unlimited",
    "Free plan",
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


def _confirm_add(client: TestClient, law_id: str, *, scope: str = "sections"):
    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    payload["scope"] = scope
    return client.post(add_path(law_id), data=payload, follow_redirects=False)


def _seed_roster(client: TestClient, *law_ids: str) -> None:
    roster = client.app.state.roster
    start, end = playground_month_bounds()
    roster._repo.ensure_period(
        USER,
        period_start=start,
        period_end=end,
        tier_snapshot="plus",
        law_limit=10,
    )
    for law_id in law_ids:
        result = roster._repo.consume_law(
            USER,
            period_start=start,
            law_id=law_id,
            law_limit=10,
            allow_new=True,
        )
        assert result.ok, result.status


def _phone(html: str) -> str:
    return html.split("data-plus-add-phone", 1)[1].split(
        'data-add-step="scope"', 1
    )[0]


def _desk(html: str) -> str:
    return html.split("data-plus-add-desktop", 1)[1].split(
        "data-plus-add-phone", 1
    )[0]


def _facts(client: TestClient) -> dict:
    history = tuple(
        sorted(
            (row.id, row.status, row.tier, row.is_current)
            for row in client.app.state.subscriptions.list_subscription_history(USER)
        )
    )
    roster = getattr(client.app.state, "roster", None)
    overlay = getattr(client.app.state, "playground", None)
    start, _end = playground_month_bounds()
    consumed = ()
    if roster is not None:
        consumed = tuple(
            sorted(
                item.law_id
                for item in roster._repo.list_items(USER, start)
                if item.consumed_at is not None
            )
        )
    return {
        "session": client.cookies.get(SESSION_COOKIE_NAME),
        "subscription": client.app.state.subscriptions.get_current_subscription(USER),
        "history": history,
        "active": tuple(
            sorted(i.law_id for i in roster.active_roster_items(USER))
        )
        if roster is not None
        else (),
        "consumed": consumed,
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        )
        if overlay is not None
        else (),
    }


def test_phone_plus_add_eligible_confirm_uses_screen05_copy(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    before = _facts(client)
    page = client.get(add_path("ndps"))
    assert page.status_code == 200
    html = unescape(page.text)
    assert 'data-pg-kind="eligible_to_add"' in html
    assert "data-plus-add-phone" in html
    assert "data-plus-add-desktop" in html
    phone = unescape(_phone(html))
    assert f'class="plus-add-title">{TITLE}<' in phone
    assert LEDE in phone
    assert SPACE in phone
    assert 'data-pg-add-confirm' in phone
    assert 'name="csrf_token"' in phone
    assert 'name="confirm" value="add"' in phone
    assert f'class="plus-add-submit">{TITLE}<' in phone
    assert ">Cancel<" not in phone
    assert 'href="/laws/ndps"' not in phone
    assert "plus-add-footer" not in phone
    assert FOOTER not in phone
    assert f"Add NDPS Act to {MONTH}?" not in phone
    assert "You'll have 9 spaces remaining." not in phone
    assert "data-signed-in-add-phone" not in html
    assert "data-guest-add-phone" not in html
    for phrase in FORBIDDEN:
        assert phrase not in phone, phrase
    desk = unescape(_desk(html))
    assert LEDE in desk
    assert SPACE in desk
    assert FOOTER not in desk
    assert _facts(client) == before
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False


def test_phone_plus_add_plus01_trigger_stays_eligible_sheet(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    html = client.get("/laws/ndps").text
    phone_head = html.split("data-plus-bareact-phone", 1)[1].split("</section>", 1)[0]
    assert 'data-pg-kind="eligible_to_add"' in phone_head
    assert f'href="{add_path("ndps")}"' in phone_head
    assert "data-pg-sheet" in phone_head
    assert "+ Add to Playground" in phone_head
    assert "Already in Playground" not in phone_head


def test_phone_plus_add_confirm_without_scope_does_not_consume(
    tmp_path: Path,
) -> None:
    client = _plus_client(tmp_path)
    before = _facts(client)
    missing = client.post(
        add_path("ndps"),
        data={"confirm": "add", "scope": "sections"},
        follow_redirects=False,
    )
    assert missing.status_code == 403
    assert _facts(client) == before

    unconfirmed = client.post(
        add_path("ndps"), data=_csrf(client), follow_redirects=False
    )
    assert unconfirmed.status_code == 303
    assert "/playground/roster" in (unconfirmed.headers.get("location") or "")
    assert _facts(client) == before

    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    scope_page = client.post(add_path("ndps"), data=payload, follow_redirects=False)
    assert scope_page.status_code == 200
    assert 'data-add-step="scope"' in scope_page.text
    assert ">Entire Act<" in scope_page.text
    assert ">Choose sections<" in scope_page.text
    assert _facts(client) == before
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False


def test_phone_plus_add_scope_still_consumes_through_existing_handler(
    tmp_path: Path,
) -> None:
    client = _plus_client(tmp_path)
    added = _confirm_add(client, "ndps", scope="entire")
    assert added.status_code == 303
    assert added.headers.get("location") == law_path("ndps")
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    cap = client.app.state.roster.capacity(
        USER, client.app.state.entitlement_service.resolve(USER)
    )
    assert cap.used == 1
    assert cap.remaining == 9


def test_phone_plus_re_add_roster_full_already_active_are_not_plus02(
    tmp_path: Path,
) -> None:
    readd = _plus_client(tmp_path / "readd")
    added = _confirm_add(readd, "ndps", scope="entire")
    assert added.status_code == 303
    used_after_add = readd.app.state.roster.capacity(
        USER, readd.app.state.entitlement_service.resolve(USER)
    ).used
    removed = readd.post(remove_path("ndps"), data=_csrf(readd), follow_redirects=False)
    assert removed.status_code == 303
    html = unescape(readd.get(add_path("ndps")).text)
    assert 'data-pg-kind="re_add"' in html
    assert "data-plus-add-desktop" not in html
    assert "data-plus-add-phone" not in html
    assert "No extra space used." in html
    assert "Add back" in html
    assert LEDE not in html
    assert SPACE not in html
    restored = _confirm_add(readd, "ndps", scope="entire")
    assert restored.status_code == 303
    assert readd.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    assert (
        readd.app.state.roster.capacity(
            USER, readd.app.state.entitlement_service.resolve(USER)
        ).used
        == used_after_add
    )

    full = _plus_client(tmp_path / "full")
    _seed_roster(full, *FULL_LAWS)
    full_html = full.get(add_path("ndps")).text
    assert 'data-pg-kind="roster_full"' in full_html or "Playground full this month" in full_html
    assert "data-plus-add-desktop" not in full_html
    assert "data-plus-add-phone" not in full_html
    assert LEDE not in unescape(full_html)

    active = _plus_client(tmp_path / "active")
    seeded = _confirm_add(active, "ndps", scope="entire")
    assert seeded.status_code == 303
    again = active.get(add_path("ndps"), follow_redirects=False)
    assert again.status_code == 303
    assert "data-plus-add-phone" not in (again.headers.get("location") or "")


def test_phone_plus_add_css_is_breakpoint_scoped() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    phone_block = css.split("is plus/02-screen:", 1)[1].split(
        "@media (min-width: 561px)", 1
    )[0]
    assert "@media (max-width: 560px)" in phone_block
    assert ":has([data-plus-add-phone])" in phone_block
    assert "width: 100%" in phone_block
    assert "justify-content: flex-end" in phone_block
    assert "max-height: min(92dvh, 100%)" in phone_block
    assert "overflow-y: auto" in phone_block
    assert "overflow-x: hidden" in phone_block
    assert "safe-area-inset-bottom" in phone_block
    assert "[data-plus-add-phone] .plus-add-submit" in phone_block
    assert ":has([data-guest-add-phone])" not in phone_block
    assert ":has([data-signed-in-add-phone])" not in phone_block
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", phone_block) is None
    desk_submit = css.split(
        "[data-plus-add-desktop] .plus-add-submit {", 1
    )[1].split("}", 1)[0]
    assert "height: 50px" in desk_submit
    assert "padding: 26px 28px" in css.split(
        ".pg-sheet-panel[data-plus-add=\"desktop\"] {", 1
    )[1].split("}", 1)[0]
    assert "data-plus-add-phone" not in MOBILE.read_text(encoding="utf-8")
    assert "data-plus-add-phone" not in STYLES.read_text(encoding="utf-8")
    js = PG_JS.read_text(encoding="utf-8")
    assert "data-plus-add-phone" not in js
    assert "event.target === dialog" in js
    src = ADD.read_text(encoding="utf-8")
    phone_src = src.split("data-plus-add-phone", 1)[1].split("{% else %}", 1)[0]
    assert "plus_add_title" in phone_src
    assert "plus_add_lede" in phone_src
    assert "data-pg-add-confirm" in phone_src
    assert ">Cancel<" not in phone_src
    assert "cancel_href" not in phone_src
    desk_src = src.split("data-plus-add-desktop", 1)[1].split(
        "data-plus-add-phone", 1
    )[0]
    assert "plus-add-cancel" in desk_src
    assert "data-pg-sheet-close" in desk_src
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg35" in base
    assert "playground.css?v=pg34" not in base
    assert "styles.css?v=main86" in base
    assert "mobile.css?v=mob105" in base


def test_guest_free_expired_halted_pro_other_law_stay_separate(
    tmp_path: Path,
) -> None:
    guest = TestClient(_guest_app(tmp_path / "guest"))
    guest_html = guest.get(add_path("ndps")).text
    assert "data-guest-add-phone" in guest_html
    assert "data-plus-add-phone" not in guest_html
    assert "Sign in" in guest_html.split("data-guest-add-phone", 1)[1]

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get(add_path("ndps")).text
    assert "data-signed-in-add-phone" in free_html
    assert "data-plus-add-phone" not in free_html
    assert "Unlock Playground" in free_html

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
    assert "data-plus-add-phone" not in expired_html
    assert "data-expired-add-phone" in expired_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get(add_path("ndps")).text
    assert "data-plus-add-phone" not in halted_html
    assert "data-halted-add-phone" in halted_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get(add_path("ndps")).text
    assert "data-plus-add-phone" not in pro_html
    assert "data-plus-add-desktop" not in pro_html
    assert 'data-pg-kind="eligible_to_add"' in pro_html

    plus = _plus_client(tmp_path / "plus")
    bns = plus.get(add_path("bns")).text
    assert "data-plus-add-phone" not in bns
    assert "data-plus-add-desktop" not in bns
    assert LEDE not in unescape(bns)


def _screenshot(page, path: Path, *, attempts: int = 5) -> None:
    last: OSError | None = None
    for index in range(attempts):
        try:
            page.screenshot(path=str(path), full_page=False)
            return
        except OSError as exc:
            last = exc
            time.sleep(0.4 * (index + 1))
    assert last is not None
    raise last


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


def test_phone_plus_add_screen02_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_plus_add_screen02_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    before = _facts(client)

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
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        context.add_cookies(cookies)
        page = context.new_page()
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )

        def open_sheet():
            page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
            page.evaluate(
                """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
            )
            page.locator("[data-plus-bareact-phone] [data-pg-sheet]").click()
            page.wait_for_selector(
                "[data-pg-add][data-pg-kind='eligible_to_add']", timeout=8000
            )
            page.wait_for_timeout(400)

        open_sheet()
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const desk = panel.querySelector('[data-plus-add-desktop]');
              const phoneBlock = panel.querySelector('[data-plus-add-phone]');
              const submit = phoneBlock && phoneBlock.querySelector('.plus-add-submit');
              const cancel = phoneBlock && [...phoneBlock.querySelectorAll('a, button')].find(
                (el) => el.textContent.trim() === 'Cancel'
              );
              const closeBtn = panel.querySelector('.pg-sheet-close');
              const handle = getComputedStyle(panel, '::before');
              const d = dialog.getBoundingClientRect();
              const p = panel.getBoundingClientRect();
              const head = document.querySelector('[data-plus-bareact-phone]');
              const cta = head && head.querySelector('[data-pg-sheet]');
              const confirmStep = panel.querySelector("[data-add-step='confirm']");
              const scopeStep = panel.querySelector("[data-add-step='scope']");
              return {
                open: Boolean(dialog && dialog.open),
                kind: panel.getAttribute('data-pg-kind'),
                url: location.pathname,
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                phoneDisplay: phoneBlock ? getComputedStyle(phoneBlock).display : null,
                title: phoneBlock && phoneBlock.querySelector('.plus-add-title')
                  && phoneBlock.querySelector('.plus-add-title').textContent.trim(),
                lede: phoneBlock && phoneBlock.querySelector('.plus-add-lede')
                  && phoneBlock.querySelector('.plus-add-lede').textContent.trim(),
                space: phoneBlock && phoneBlock.querySelector('.plus-add-space')
                  && phoneBlock.querySelector('.plus-add-space').textContent.trim(),
                submit: {
                  tag: submit && submit.tagName,
                  type: submit && submit.getAttribute('type'),
                  text: submit && submit.textContent.trim(),
                  width: submit && submit.getBoundingClientRect().width,
                  height: submit && submit.getBoundingClientRect().height,
                },
                cancel: Boolean(cancel),
                closeDisplay: closeBtn ? getComputedStyle(closeBtn).display : 'missing',
                handleDisplay: handle.display,
                dialog: { top: d.top, left: d.left, width: d.width, height: d.height },
                panel: { top: p.top, left: p.left, width: p.width, bottom: p.bottom },
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                overflowY: getComputedStyle(panel).overflowY,
                tabFocused: Boolean(
                  document.querySelector('[data-plus-bareact-phone-tabs]')
                  && document.querySelector('[data-plus-bareact-phone-tabs]').contains(
                    document.activeElement
                  )
                ),
                backgroundTitle: head && head.querySelector('.guest-bareact-title')
                  && head.querySelector('.guest-bareact-title').textContent.trim(),
                addCta: cta && cta.textContent.replace(/\\s+/g, ' ').trim(),
                already: head && head.innerText.includes('Already in Playground'),
                guestAdd: Boolean(panel.querySelector('[data-guest-add-phone]')),
                signedAdd: Boolean(panel.querySelector('[data-signed-in-add-phone]')),
                confirmHidden: Boolean(confirmStep && confirmStep.hidden),
                scopeHidden: Boolean(scopeStep && scopeStep.hidden),
                footer: phoneBlock && phoneBlock.querySelector('.plus-add-footer')
                  && phoneBlock.querySelector('.plus-add-footer').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)

        page.set_viewport_size({"width": 390, "height": 560})
        short = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const submit = panel.querySelector('[data-plus-add-phone] .plus-add-submit');
              const box = submit.getBoundingClientRect();
              const p = panel.getBoundingClientRect();
              return {
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                submitW: box.width,
                submitH: box.height,
                inPanel: panel.contains(submit),
                overflowY: getComputedStyle(panel).overflowY,
                panelBottom: p.bottom,
                panelTop: p.top,
                dialogH: dialog.getBoundingClientRect().height,
                paddingBottom: getComputedStyle(panel).paddingBottom,
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
              const cta = document.querySelector('[data-plus-bareact-phone] [data-pg-sheet]');
              return {
                open: Boolean(dialog && dialog.open),
                url: location.pathname,
                focused: document.activeElement === cta,
                title: document.querySelector('[data-plus-bareact-phone] .guest-bareact-title')
                  && document.querySelector('[data-plus-bareact-phone] .guest-bareact-title').textContent.trim(),
                already: document.querySelector('[data-plus-bareact-phone]')
                  && document.querySelector('[data-plus-bareact-phone]').innerText.includes(
                    'Already in Playground'
                  ),
              };
            }"""
        )

        page.locator("[data-plus-bareact-phone] [data-pg-sheet]").click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='eligible_to_add']", timeout=8000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        escaped = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const cta = document.querySelector('[data-plus-bareact-phone] [data-pg-sheet]');
              return {
                open: Boolean(dialog && dialog.open),
                url: location.pathname,
                focused: document.activeElement === cta,
              };
            }"""
        )

        page.locator("[data-plus-bareact-phone] [data-pg-sheet]").click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='eligible_to_add']", timeout=8000)
        page.locator("[data-plus-add-phone] .plus-add-submit").click()
        page.wait_for_timeout(250)
        scoped = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const confirmStep = panel.querySelector("[data-add-step='confirm']");
              const scopeStep = panel.querySelector("[data-add-step='scope']");
              return {
                path: location.pathname,
                confirmHidden: Boolean(confirmStep && confirmStep.hidden),
                scopeHidden: Boolean(scopeStep && scopeStep.hidden),
                entire: Boolean(scopeStep && scopeStep.innerText.includes('Entire Act')),
                sections: Boolean(scopeStep && scopeStep.innerText.includes('Choose sections')),
              };
            }"""
        )
        browser.close()

    assert geo["open"] is True
    assert geo["kind"] == "eligible_to_add"
    assert geo["url"] == "/laws/ndps"
    assert geo["deskDisplay"] == "none"
    assert geo["phoneDisplay"] != "none"
    assert geo["title"] == TITLE
    assert geo["lede"] == LEDE
    assert geo["space"] == SPACE
    assert geo["submit"]["tag"] == "BUTTON"
    assert geo["submit"]["type"] == "submit"
    assert geo["submit"]["text"] == TITLE
    assert geo["submit"]["width"] >= 300
    assert geo["submit"]["height"] >= 44
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
    assert geo["addCta"] == "+ Add to Playground"
    assert geo["already"] is False
    assert geo["guestAdd"] is False
    assert geo["signedAdd"] is False
    assert geo["confirmHidden"] is False
    assert geo["scopeHidden"] is True
    assert geo["footer"] in (None, "")
    assert geo["tabFocused"] is False
    assert short["overflow"] is False
    assert short["submitW"] >= 300
    assert short["submitH"] >= 44
    assert short["inPanel"] is True
    assert short["overflowY"] in ("auto", "scroll")
    assert short["panelBottom"] <= 561
    assert short["panelTop"] >= 0
    assert "env(safe-area-inset-bottom" in PG_CSS.read_text(encoding="utf-8").split(
        "is plus/02-screen:", 1
    )[1].split("@media (min-width: 561px)", 1)[0]
    assert closed["open"] is False
    assert closed["url"] == "/laws/ndps"
    assert closed["focused"] is True
    assert closed["title"] == NDPS_GUEST_TITLE
    assert closed["already"] is False
    assert escaped["open"] is False
    assert escaped["url"] == "/laws/ndps"
    assert escaped["focused"] is True
    assert scoped["path"] == "/laws/ndps"
    assert scoped["confirmHidden"] is True
    assert scoped["scopeHidden"] is False
    assert scoped["entire"] is True
    assert scoped["sections"] is True
    assert _facts(client) == before
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_plus_add_screen02_desktop_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_plus_add_screen02_desktop_regression_1280.png"
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
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        page.locator('[data-plus-bareact="desktop"] [data-pg-sheet]').click()
        page.wait_for_selector("[data-plus-add-desktop]", timeout=8000)
        page.wait_for_timeout(300)
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const desk = panel.querySelector('[data-plus-add-desktop]');
              const phoneBlock = panel.querySelector('[data-plus-add-phone]');
              const submit = desk.querySelector('.plus-add-submit');
              const cancel = desk.querySelector('.plus-add-cancel');
              const closeBtn = panel.querySelector('.pg-sheet-close');
              const d = dialog.getBoundingClientRect();
              return {
                open: Boolean(dialog && dialog.open),
                kind: panel.getAttribute('data-pg-kind'),
                deskDisplay: getComputedStyle(desk).display,
                phoneDisplay: phoneBlock ? getComputedStyle(phoneBlock).display : null,
                title: desk.querySelector('.plus-add-title').textContent.trim(),
                lede: desk.querySelector('.plus-add-lede').textContent.trim(),
                space: desk.querySelector('.plus-add-space').textContent.trim(),
                submitText: submit.textContent.trim(),
                submitH: submit.getBoundingClientRect().height,
                cancelDisplay: cancel ? getComputedStyle(cancel).display : null,
                closeDisplay: closeBtn ? getComputedStyle(closeBtn).display : 'missing',
                panelW: panel.getBoundingClientRect().width,
                dialogWidth: d.width,
                notFullBleed: d.width < 800 && d.left > 100,
                footer: desk.querySelector('.plus-add-footer')
                  && desk.querySelector('.plus-add-footer').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)
        browser.close()

    assert geo["open"] is True
    assert geo["kind"] == "eligible_to_add"
    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["title"] == TITLE
    assert geo["lede"] == LEDE
    assert geo["space"] == SPACE
    assert geo["submitText"] == TITLE
    assert geo["submitH"] == pytest.approx(50, abs=2)
    assert geo["cancelDisplay"] == "none"
    assert geo["closeDisplay"] != "none"
    assert geo["panelW"] == pytest.approx(460, abs=8)
    assert geo["notFullBleed"] is True
    assert geo["footer"] in (None, "")
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
