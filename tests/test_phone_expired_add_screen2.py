"""Phone Expired NDPS Add resume sheet Screen 02 (CTA map expired/02-screen).

Authorized: ChatGPT. Authenticated expired GET /playground/laws/ndps/add
as the existing resume branch. Overlay on accepted Expired 01 uses a
test-only synthetic data-pg-sheet opener — no product Add control.
Map Unlock / Add to Playground / ₹149 / Continue are not live. Desktop
Expired Add Screen 05 is the functional contract. Guest / Free / Plus /
Halted / Pro stay on their own sheets. Expired 01 is unchanged.
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
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.entitlements.models import BLOCK_PAID_PERIOD_ENDED
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.urls import add_path, home_path, law_path, sections_path
from constitution_memorizer.playground.view import PLAYGROUND_BILLING_PATH, gate_view
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.guest_bareact_head import NDPS_GUEST_TITLE
from tests.conftest import PLAYGROUND_TEST_NOW

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
PG_JS = ROOT / "src/constitution_memorizer/web/static/playground.js"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
ROUTES = ROOT / "src/constitution_memorizer/playground/routes.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_GATE = gate_view(reason=BLOCK_PAID_PERIOD_ENDED)
LIVE_HEADING = LIVE_GATE.title
LIVE_COPY = LIVE_GATE.lines
INVENTED = (
    "Your plan expired",
    "Resume subscription",
    "Premium",
    "Unlimited",
    "Unlock all",
    "Free plan",
    "All 3 slots",
    'kind == "expired"',
    "Core · Deep · Infinite",
    "₹149",
)
OPEN_SHEET = """() => {
  let opener = document.querySelector('[data-expired-add-test-opener]');
  if (!opener) {
    opener = document.createElement('a');
    opener.href = '/playground/laws/ndps/add';
    opener.setAttribute('data-pg-sheet', '');
    opener.setAttribute('data-expired-add-test-opener', '');
    opener.textContent = 'Open resume sheet';
    opener.style.cssText =
      'position:absolute;left:8px;top:8px;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);';
    document.body.appendChild(opener);
  }
  opener.click();
}"""


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
    period_start: datetime = ACTIVE_START,
    period_end: datetime = ACTIVE_END,
) -> None:
    client.app.state.subscriptions.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        billing_period_start=period_start,
        billing_period_end=period_end,
        is_current=True,
    )


def _confirm_add(client: TestClient, law_id: str):
    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    payload["scope"] = "sections"
    preview = client.post(add_path(law_id), data=_csrf(client), follow_redirects=False)
    if preview.status_code == 303 and "/playground/roster" in (
        preview.headers.get("location") or ""
    ):
        return client.post(add_path(law_id), data=payload, follow_redirects=False)
    if preview.status_code == 200:
        return client.post(add_path(law_id), data=payload, follow_redirects=False)
    return preview


def _expire(client: TestClient) -> None:
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None
    client.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        status="expired",
        billing_period_start=EXPIRED_START,
        billing_period_end=EXPIRED_END,
    )


def _seed_ndps_then_expire(client: TestClient) -> None:
    _subscribe(client)
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps")
    _expire(client)


def _expired_enrolled(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_then_expire(client)
    return client


def _expired_never_enrolled(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    _expire(client)
    return client


def _phone(html: str) -> str:
    return html.split("data-expired-add-phone", 1)[1]


def _desk(html: str) -> str:
    return html.split("data-expired-add-desktop", 1)[1].split(
        "data-expired-add-phone", 1
    )[0]


def _facts(client: TestClient) -> dict:
    snap = client.app.state.entitlement_service.resolve(USER, now=PLAYGROUND_TEST_NOW)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    cap = roster.peek_capacity(USER, snap)
    return {
        "status": snap.subscription_status,
        "subscribed": snap.is_subscribed,
        "can_open": snap.can_open_playground,
        "can_consume": snap.can_consume_new_playground_law,
        "reason": snap.playground_block_reason,
        "active": tuple(sorted(i.law_id for i in roster.active_roster_items(USER))),
        "removed": tuple(sorted(i.law_id for i in roster.removed_roster_items(USER))),
        "used": cap.used,
        "remaining": cap.remaining,
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        ),
        "selection": tuple(
            sorted(s.source_locator for s in overlay.list_selection(USER, "ndps"))
        ),
        "progress": tuple(
            sorted(
                (p.source_locator, p.status, p.times_completed, p.cloze_done)
                for p in overlay.list_progress(USER, "ndps")
            )
        ),
    }


def test_phone_expired_add_enrolled_is_resume_not_confirm(tmp_path: Path) -> None:
    client = _expired_enrolled(tmp_path)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert snap.subscription_status == "expired"
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    before = _facts(client)
    page = client.get(add_path("ndps"))
    assert page.status_code == 200
    html = unescape(page.text)
    assert 'data-mscreen="playground"' in html
    assert 'data-pg-kind="resume"' in html
    assert 'data-expired-add="desktop"' in html
    assert "data-expired-add-phone" in html
    assert 'data-pg-kind="expired"' not in html
    assert 'data-pg-kind="eligible_to_add"' not in html
    assert 'data-pg-kind="already_active"' not in html
    assert "data-plus-add-phone" not in html
    assert "data-signed-in-add-phone" not in html
    assert "data-guest-add-phone" not in html
    assert 'data-pg-add-confirm' not in html
    assert 'action="/playground/laws/ndps/add"' not in html
    assert 'name="confirm"' not in html
    assert 'name="scope"' not in html
    assert ">Entire Act<" not in html
    assert ">Choose sections<" not in html
    phone = _phone(html)
    assert f">{LIVE_HEADING}<" in phone
    for line in LIVE_COPY:
        assert line in phone
    assert ">Resume Playground<" in phone
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in phone
    assert ">Cancel<" in phone
    assert "Unlock Playground" not in phone
    assert "Add to Playground" not in phone
    assert "+ Add to Playground" not in phone
    assert "Subscribe to use Playground" not in phone
    assert PLAYGROUND_BILLING_PATH in phone
    assert f'href="{add_path("ndps")}"' not in phone
    assert "/playground?stage=plans" not in phone
    assert "/billing/subscriptions/checkout" not in phone
    assert "/billing/subscriptions/create" not in phone
    for phrase in INVENTED:
        assert phrase not in phone, phrase
    desk = _desk(html)
    assert f">{LIVE_HEADING}<" in desk
    assert ">Resume Playground<" in desk
    assert "Unlock Playground" not in desk
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True
    workspace = client.get(law_path("ndps"))
    assert workspace.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAID_PERIOD_ENDED}"' in workspace.text
    sections = client.get(sections_path("ndps"))
    assert sections.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAID_PERIOD_ENDED}"' in sections.text
    home = client.get("/playground")
    assert home.status_code == 200
    assert 'data-hard-gate="true"' not in home.text
    assert _facts(client) == before


def test_phone_expired_add_never_enrolled_is_resume_only(tmp_path: Path) -> None:
    client = _expired_never_enrolled(tmp_path)
    before = _facts(client)
    html = unescape(client.get(add_path("ndps")).text)
    phone = _phone(html)
    assert 'data-pg-kind="resume"' in html
    assert "data-expired-add-phone" in html
    assert f">{LIVE_HEADING}<" in phone
    assert ">Resume Playground<" in phone
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in phone
    assert 'data-pg-add-confirm' not in html
    assert "Unlock Playground" not in phone
    assert "Add to Playground" not in phone
    assert "+ Add to Playground" not in phone
    assert "Already in Playground" not in phone
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False
    assert _facts(client) == before


def test_phone_expired_add_non_retained_bns_cannot_enroll(tmp_path: Path) -> None:
    client = _expired_enrolled(tmp_path)
    before = _facts(client)
    html = unescape(client.get(add_path("bns")).text)
    assert 'data-pg-kind="resume"' in html
    assert "data-expired-add-phone" in html
    assert 'data-pg-add-confirm' not in html
    assert ">Resume Playground<" in html
    posted = client.post(
        add_path("bns"),
        data={**_csrf(client), "confirm": "add", "scope": "sections"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    assert posted.headers.get("location") == home_path()
    assert client.app.state.roster.is_law_active_this_period(USER, "bns") is False
    assert _facts(client) == before


def test_phone_expired_add_get_and_denied_post_do_not_mutate(tmp_path: Path) -> None:
    client = _expired_enrolled(tmp_path)
    before = _facts(client)
    first = client.get(add_path("ndps"))
    assert first.status_code == 200
    after_get = _facts(client)
    posted = client.post(
        add_path("ndps"),
        data={**_csrf(client), "confirm": "add", "scope": "entire"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    assert posted.headers.get("location") == home_path()
    after_post = _facts(client)
    second = client.get(add_path("ndps"))
    assert second.status_code == 200
    assert 'data-pg-kind="resume"' in second.text
    assert _facts(client) == before
    assert after_get == before
    assert after_post == before
    assert client.get("/laws/ndps").status_code == 200
    assert _facts(client) == before


def test_phone_expired_01_has_no_product_add_opener(tmp_path: Path) -> None:
    enrolled = unescape(_expired_enrolled(tmp_path).get("/laws/ndps").text)
    desk = enrolled.split("data-expired-bareact=\"desktop\"", 1)[1].split(
        "data-bareact-phone", 1
    )[0]
    assert 'class="signed-bareact-continue"' in desk
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in desk
    assert "data-pg-sheet" not in desk
    assert f'href="{add_path("ndps")}"' not in desk
    assert "+ Add to Playground" not in desk
    never = unescape(
        _expired_never_enrolled(tmp_path / "never").get("/laws/ndps").text
    )
    never_desk = never.split("data-expired-bareact=\"desktop\"", 1)[1].split(
        "data-bareact-phone", 1
    )[0]
    assert ">Resume Playground<" in never_desk
    assert f'href="{add_path("ndps")}"' not in never_desk
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in never_desk


def test_phone_expired_add_css_scope_pins_and_no_clone() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    assert "is expired/02-screen:" in css
    phone_block = css.split("is expired/02-screen:", 1)[1].split(
        "Guest desktop Playground intro", 1
    )[0]
    assert "@media (max-width: 560px)" in phone_block
    assert ":has([data-expired-add-phone])" in phone_block
    assert "justify-content: flex-end" in phone_block
    assert "max-height: min(92dvh, 100%)" in phone_block
    assert "overflow-y: auto" in phone_block
    assert "overflow-x: hidden" in phone_block
    assert "safe-area-inset-bottom" in phone_block
    assert ":focus-visible" in phone_block
    assert ".pg-btn--ghost" in phone_block
    assert ".pg-sheet-close" in phone_block
    assert "display: none !important" in phone_block
    assert ":has([data-plus-add-phone])" not in phone_block
    assert ":has([data-signed-in-add-phone])" not in phone_block
    assert ":has([data-guest-add-phone])" not in phone_block
    assert ":has([data-halted-add-phone])" not in phone_block
    assert "data-plus-add-phone" not in phone_block
    assert "data-halted-add-phone" not in phone_block
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", phone_block) is None
    desk_resume = css.split(
        "[data-expired-add-desktop] .expired-add-resume,", 1
    )[1].split(
        "[data-expired-add-desktop] .expired-add-resume:active", 1
    )[0]
    assert "height: 50px" in desk_resume
    assert "padding: 26px 28px" in css.split(
        '.pg-sheet-panel[data-expired-add="desktop"],', 1
    )[1].split("}", 1)[0]
    assert "data-expired-add-phone" not in MOBILE.read_text(encoding="utf-8")
    assert "data-expired-add" not in MOBILE.read_text(encoding="utf-8")
    assert "is expired/02-screen" not in STYLES.read_text(encoding="utf-8")
    js = PG_JS.read_text(encoding="utf-8")
    assert "data-expired-add-phone" not in js
    assert "function enhanceSheets" in js
    assert "event.target === dialog" in js
    src = ADD.read_text(encoding="utf-8")
    assert 'kind == "resume"' in src
    assert 'kind == "expired"' not in src
    phone_src = src.split("data-expired-add-phone", 1)[1].split("{% else %}", 1)[0]
    assert "state.primary_href" in phone_src
    assert "state.primary_label" in phone_src
    assert ">Cancel<" in phone_src
    assert "cancel_href" in phone_src
    assert "data-pg-add-confirm" not in phone_src
    assert "<form" not in phone_src
    routes = ROUTES.read_text(encoding="utf-8")
    assert "request_is_expired_subscriber" in routes
    view = VIEW.read_text(encoding="utf-8")
    assert 'primary_label="Resume Playground"' in view
    assert "kind == \"expired\"" not in view
    base = BASE.read_text(encoding="utf-8")
    assert "styles.css?v=main86" in base
    assert "mobile.css?v=mob105" in base
    assert "playground.css?v=pg46" in base
    assert "playground.css?v=pg41" not in base


def test_phone_expired_add_cohorts_stay_separate(tmp_path: Path) -> None:
    expired_html = _expired_enrolled(tmp_path / "expired").get(add_path("ndps")).text
    assert "data-expired-add-phone" in expired_html
    assert "data-plus-add-phone" not in expired_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get(add_path("ndps")).text
    assert "data-plus-add-phone" in plus_html
    assert "data-expired-add-phone" not in plus_html
    assert 'data-pg-add-confirm' in plus_html
    assert LIVE_HEADING not in plus_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get(add_path("ndps")).text
    assert "data-signed-in-add-phone" in free_html
    assert "data-expired-add-phone" not in free_html
    assert "Unlock Playground" in free_html
    assert "Resume Playground" not in free_html

    guest = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "guest" / "progress.db",
            multiuser=True,
            multiuser_settings=_settings(),
            auth_provider=FakeAuthProvider(),
            session_store=InMemorySessionStore(),
        )
    )
    guest_html = guest.get(add_path("ndps")).text
    assert "data-guest-add-phone" in guest_html
    assert "data-expired-add-phone" not in guest_html
    assert "Create an account" in guest_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    added = _confirm_add(halted, "ndps")
    assert added.status_code in {200, 303}
    stored = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )
    halted_html = halted.get(add_path("ndps")).text
    assert "data-halted-add-phone" in halted_html
    assert "data-expired-add-phone" not in halted_html
    assert LIVE_HEADING not in halted_html
    assert ">Resume Playground<" not in halted_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get(add_path("ndps")).text
    assert "data-expired-add-phone" not in pro_html
    assert LIVE_HEADING not in pro_html


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


def _playwright_session(app, tmp_path: Path, *, enrolled: bool):
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    if enrolled:
        added = _confirm_add(client, "ndps")
        assert added.status_code in {200, 303}
    _expire(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    return session, client


def test_phone_expired_add_screen02_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    session, client = _playwright_session(app, tmp_path, enrolled=True)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_expired_add_screen02_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    before = _facts(client)

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

        def open_sheet():
            page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
            page.evaluate(
                """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
            )
            page.evaluate(OPEN_SHEET)
            page.wait_for_selector(
                "[data-pg-add][data-pg-kind='resume'] [data-expired-add-phone]",
                timeout=8000,
            )
            page.wait_for_timeout(400)

        open_sheet()
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const desk = panel && panel.querySelector('[data-expired-add-desktop]');
              const phoneBlock = panel && panel.querySelector('[data-expired-add-phone]');
              const resume = phoneBlock && phoneBlock.querySelector(
                'a.pg-btn:not(.pg-btn--ghost)'
              );
              const cancel = phoneBlock && [...phoneBlock.querySelectorAll('a, button')].find(
                (el) => el.textContent.trim() === 'Cancel'
              );
              const closeBtn = panel && panel.querySelector('.pg-sheet-close');
              const handle = panel ? getComputedStyle(panel, '::before') : null;
              const d = dialog && dialog.getBoundingClientRect();
              const p = panel && panel.getBoundingClientRect();
              const box = resume && resume.getBoundingClientRect();
              const head = document.querySelector('[data-expired-bareact="desktop"]');
              const productSheet = [...document.querySelectorAll(
                '[data-expired-bareact="desktop"] [data-pg-sheet]'
              )];
              const opener = document.querySelector('[data-expired-add-test-opener]');
              return {
                open: Boolean(dialog && dialog.open),
                kind: panel && panel.getAttribute('data-pg-kind'),
                expiredAdd: panel && panel.getAttribute('data-expired-add'),
                url: location.pathname,
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                phoneDisplay: phoneBlock ? getComputedStyle(phoneBlock).display : null,
                title: phoneBlock && phoneBlock.querySelector('h1')
                  && phoneBlock.querySelector('h1').textContent.trim(),
                lede: phoneBlock && phoneBlock.querySelector('.pg-lede')
                  && phoneBlock.querySelector('.pg-lede').textContent.trim(),
                resumeText: resume && resume.textContent.trim(),
                resumeHref: resume && resume.getAttribute('href'),
                resumeW: box ? box.width : 0,
                resumeH: box ? box.height : 0,
                cancelPresent: Boolean(cancel),
                cancelDisplay: cancel ? getComputedStyle(cancel).display : null,
                closePresent: Boolean(closeBtn),
                closeDisplay: closeBtn ? getComputedStyle(closeBtn).display : 'missing',
                handleDisplay: handle && handle.display,
                dialog: d && { top: d.top, left: d.left, width: d.width, height: d.height },
                panel: p && { top: p.top, left: p.left, width: p.width, bottom: p.bottom },
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                overflowY: panel ? getComputedStyle(panel).overflowY : null,
                already: Boolean(head && head.innerText.includes('Already in Playground')),
                backgroundTitle: head && head.querySelector('.guest-bareact-title')
                  && head.querySelector('.guest-bareact-title').textContent.trim(),
                backgroundResume: Boolean(head && head.innerText.includes('Resume Playground')),
                continueLabel: Boolean(head && /(?:^|\\n)\\s*Continue\\s*(?:\\n|$)/.test(head.innerText)),
                productOpeners: productSheet.length,
                clone: Boolean(document.querySelector('[data-expired-add-phone-clone]')),
                confirmForm: Boolean(panel && panel.querySelector('[data-pg-add-confirm]')),
                guestAdd: Boolean(panel && panel.querySelector('[data-guest-add-phone]')),
                plusAdd: Boolean(panel && panel.querySelector('[data-plus-add-phone]')),
                signedAdd: Boolean(panel && panel.querySelector('[data-signed-in-add-phone]')),
                openerPresent: Boolean(opener),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)

        page.set_viewport_size({"width": 390, "height": 560})
        short = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const resume = panel.querySelector(
                '[data-expired-add-phone] a.pg-btn:not(.pg-btn--ghost)'
              );
              const box = resume.getBoundingClientRect();
              const p = panel.getBoundingClientRect();
              return {
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                resumeW: box.width,
                resumeH: box.height,
                inPanel: panel.contains(resume),
                overflowY: getComputedStyle(panel).overflowY,
                panelBottom: p.bottom,
                panelTop: p.top,
                reachable: box.height >= 44 && box.width >= 44,
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
              const opener = document.querySelector('[data-expired-add-test-opener]');
              const head = document.querySelector('[data-expired-bareact="desktop"]');
              return {
                open: Boolean(dialog && dialog.open),
                url: location.pathname,
                focused: document.activeElement === opener,
                already: Boolean(head && head.innerText.includes('Already in Playground')),
              };
            }"""
        )

        page.evaluate(OPEN_SHEET)
        page.wait_for_selector(
            "[data-pg-add][data-pg-kind='resume'] [data-expired-add-phone]",
            timeout=8000,
        )
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        escaped = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const opener = document.querySelector('[data-expired-add-test-opener]');
              return {
                open: Boolean(dialog && dialog.open),
                url: location.pathname,
                focused: document.activeElement === opener,
              };
            }"""
        )

        page.evaluate(OPEN_SHEET)
        page.wait_for_selector(
            "[data-pg-add][data-pg-kind='resume'] [data-expired-add-phone]",
            timeout=8000,
        )
        page.locator(
            '[data-expired-add-phone] a.pg-btn:not(.pg-btn--ghost)'
        ).click()
        page.wait_for_url("**/billing/subscriptions**", timeout=8000)
        billing_url = page.url
        browser.close()

    assert geo["open"] is True
    assert geo["kind"] == "resume"
    assert geo["expiredAdd"] == "desktop"
    assert geo["url"] == "/laws/ndps"
    assert geo["deskDisplay"] == "none"
    assert geo["phoneDisplay"] != "none"
    assert geo["title"] == LIVE_HEADING
    assert geo["lede"] == LIVE_COPY[0]
    assert geo["resumeText"] == "Resume Playground"
    assert geo["resumeHref"] == PLAYGROUND_BILLING_PATH
    assert geo["resumeW"] >= 300
    assert geo["resumeH"] >= 44
    assert geo["cancelPresent"] is True
    assert geo["cancelDisplay"] == "none"
    assert geo["closePresent"] is True
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
    assert geo["already"] is True
    assert geo["backgroundTitle"] == NDPS_GUEST_TITLE
    assert geo["backgroundResume"] is True
    assert geo["continueLabel"] is False
    assert geo["productOpeners"] == 0
    assert geo["clone"] is False
    assert geo["confirmForm"] is False
    assert geo["guestAdd"] is False
    assert geo["plusAdd"] is False
    assert geo["signedAdd"] is False
    assert geo["openerPresent"] is True
    assert short["overflow"] is False
    assert short["resumeW"] >= 300
    assert short["resumeH"] >= 44
    assert short["inPanel"] is True
    assert short["overflowY"] in ("auto", "scroll")
    assert short["reachable"] is True
    assert closed["open"] is False
    assert closed["url"] == "/laws/ndps"
    assert closed["focused"] is True
    assert closed["already"] is True
    assert escaped["open"] is False
    assert escaped["url"] == "/laws/ndps"
    assert escaped["focused"] is True
    assert PLAYGROUND_BILLING_PATH in billing_url
    assert _facts(client) == before
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_expired_add_screen02_never_enrolled_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    session, client = _playwright_session(app, tmp_path, enrolled=False)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_expired_add_screen02_never_enrolled_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    before = _facts(client)

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
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        page.evaluate(OPEN_SHEET)
        page.wait_for_selector(
            "[data-pg-add][data-pg-kind='resume'] [data-expired-add-phone]",
            timeout=8000,
        )
        page.wait_for_timeout(400)
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const phoneBlock = panel && panel.querySelector('[data-expired-add-phone]');
              const resume = phoneBlock && phoneBlock.querySelector(
                'a.pg-btn:not(.pg-btn--ghost)'
              );
              const head = document.querySelector('[data-expired-bareact="desktop"]');
              const box = resume && resume.getBoundingClientRect();
              return {
                open: Boolean(dialog && dialog.open),
                kind: panel && panel.getAttribute('data-pg-kind'),
                url: location.pathname,
                title: phoneBlock && phoneBlock.querySelector('h1')
                  && phoneBlock.querySelector('h1').textContent.trim(),
                resumeText: resume && resume.textContent.trim(),
                resumeHref: resume && resume.getAttribute('href'),
                resumeH: box ? box.height : 0,
                already: Boolean(head && head.innerText.includes('Already in Playground')),
                sections: Boolean(head && head.querySelector('.signed-bareact-sections')),
                add: Boolean(head && /Add to Playground/.test(head.innerText)),
                unlock: Boolean(phoneBlock && phoneBlock.innerText.includes('Unlock Playground')),
                confirmForm: Boolean(panel && panel.querySelector('[data-pg-add-confirm]')),
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)
        browser.close()

    assert geo["open"] is True
    assert geo["kind"] == "resume"
    assert geo["url"] == "/laws/ndps"
    assert geo["title"] == LIVE_HEADING
    assert geo["resumeText"] == "Resume Playground"
    assert geo["resumeHref"] == PLAYGROUND_BILLING_PATH
    assert geo["resumeH"] >= 44
    assert geo["already"] is False
    assert geo["sections"] is False
    assert geo["add"] is False
    assert geo["unlock"] is False
    assert geo["confirmForm"] is False
    assert geo["overflow"] is False
    assert _facts(client) == before
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_expired_add_screen02_desktop_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    session, _client = _playwright_session(app, tmp_path, enrolled=True)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_expired_add_screen02_desktop_regression_1280.png"
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
        page.evaluate(OPEN_SHEET)
        page.wait_for_selector("[data-expired-add-desktop]", timeout=8000)
        page.wait_for_timeout(300)
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const desk = panel && panel.querySelector('[data-expired-add-desktop]');
              const phoneBlock = panel && panel.querySelector('[data-expired-add-phone]');
              const resume = desk && desk.querySelector('.expired-add-resume');
              const cancel = desk && desk.querySelector('.expired-add-cancel');
              const closeBtn = panel && panel.querySelector('.pg-sheet-close');
              const d = dialog && dialog.getBoundingClientRect();
              const cluster = document.querySelector('.signed-bareact-in-pg');
              return {
                open: Boolean(dialog && dialog.open),
                kind: panel && panel.getAttribute('data-pg-kind'),
                expiredAdd: panel && panel.getAttribute('data-expired-add'),
                plus: panel && panel.getAttribute('data-plus-add'),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                phoneDisplay: phoneBlock ? getComputedStyle(phoneBlock).display : null,
                title: desk && desk.querySelector('.expired-add-title')
                  && desk.querySelector('.expired-add-title').textContent.trim(),
                lede: desk && desk.querySelector('.expired-add-lede')
                  && desk.querySelector('.expired-add-lede').textContent.trim(),
                resumeText: resume && resume.textContent.trim(),
                resumeHref: resume && resume.getAttribute('href'),
                cancelDisplay: cancel ? getComputedStyle(cancel).display : null,
                closeDisplay: closeBtn ? getComputedStyle(closeBtn).display : 'missing',
                dialogWidth: d && d.width,
                notFullBleed: Boolean(d && d.width < 800 && d.left > 100),
                already: Boolean(cluster && cluster.innerText.includes('Already in Playground')),
                confirmForm: Boolean(panel && panel.querySelector('[data-pg-add-confirm]')),
                path: location.pathname,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)
        browser.close()

    assert geo["open"] is True
    assert geo["kind"] == "resume"
    assert geo["expiredAdd"] == "desktop"
    assert geo["plus"] in (None, "")
    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["title"] == LIVE_HEADING
    assert geo["lede"] == LIVE_COPY[0]
    assert geo["resumeText"] == "Resume Playground"
    assert geo["resumeHref"] == PLAYGROUND_BILLING_PATH
    assert geo["cancelDisplay"] == "none"
    assert geo["closeDisplay"] != "none"
    assert geo["notFullBleed"] is True
    assert geo["already"] is True
    assert geo["confirmForm"] is False
    assert geo["path"] == "/laws/ndps"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
