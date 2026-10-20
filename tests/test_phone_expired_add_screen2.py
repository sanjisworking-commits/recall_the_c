"""Phone Expired NDPS Add resume sheet Screen 02 (CTA map expired/02-screen).

Authorized: ChatGPT. Authenticated expired GET /playground/laws/ndps/add
as the existing resume branch. Overlay on accepted Expired 01 uses a
test-only synthetic data-pg-sheet opener — no product Add control.
Map Unlock / Add to Playground / ₹149 / Continue are not live. Desktop
Expired Add Screen 05 is the functional contract. Guest / Free / Plus /
Halted / Pro stay on their own sheets. Expired 01 is unchanged.

M2: one sheet per state serves both widths (phone raises it as a bottom
sheet by CSS under "Add sheet (M2)" in playground.css), so there is no phone
twin: the direct Add URL is the Act page with the panel inside an open
<dialog> (M2 Q4), and the in-page fetch lifts the same panel out.
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
from constitution_memorizer.web.bare_acts import get_bare_act
from tests.conftest import PLAYGROUND_TEST_NOW

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
ADD_PANEL = ROOT / "src/constitution_memorizer/web/templates/partials/playground_add_panel.html"
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
SHEET_FETCH = {"X-Requested-With": "pg-sheet"}
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
SHEET_READY = "[data-pg-add][data-pg-kind='resume'][data-expired-add]"


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


def _sheet(html: str) -> str:
    """The Add sheet (M2): the open <dialog> and its one `.pg-sheet-panel`."""
    return html.split("<dialog", 1)[1].split("</dialog>", 1)[0]


def _head(html: str) -> str:
    """The generated Act head the sheet is drawn over (M2 Q4)."""
    return html.split('class="panel ActHead', 1)[1].split("data-bareact-accordion", 1)[0]


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
    # The direct Add URL is the Act page with the sheet open (M2 Q4): one
    # dialog, one panel, one head; no phone twin and no hard-gate shell.
    assert 'data-mscreen="bareact"' in html
    assert html.count("<dialog") == 1
    assert html.count('class="pg-sheet-panel"') == 1
    assert html.count('class="panel ActHead') == 1
    assert "data-hard-gate" not in html
    assert "PlaygroundShell" not in html
    assert 'data-expired-add="desktop"' not in html
    assert "data-expired-add-phone" not in html
    assert "data-expired-add-desktop" not in html
    assert "data-plus-add-phone" not in html
    assert "data-signed-in-add-phone" not in html
    assert "data-guest-add-phone" not in html
    assert "expired-add-" not in html
    assert 'data-pg-kind="expired"' not in html
    assert 'data-pg-kind="eligible_to_add"' not in html
    assert 'data-pg-add-confirm' not in html
    assert 'action="/playground/laws/ndps/add"' not in html
    assert 'name="confirm"' not in html
    assert 'name="scope"' not in html
    assert ">Entire Act<" not in html
    assert ">Choose sections<" not in html
    sheet = _sheet(html)
    assert "data-pg-sheet-direct" in sheet
    assert 'data-pg-sheet-return="/laws/ndps"' in sheet
    assert 'data-pg-kind="resume"' in sheet
    assert "data-expired-add" in sheet
    assert "data-halted-add" not in sheet
    assert 'data-pg-kind="already_active"' not in sheet
    assert f'<h1 id="pg-add-title" class="pg-add-title">{LIVE_HEADING}</h1>' in sheet
    for line in LIVE_COPY:
        assert f'<p class="pg-add-lede">{line}</p>' in sheet
    assert ">Resume Playground<" in sheet
    assert f'class="pg-add-primary" href="{PLAYGROUND_BILLING_PATH}">Resume Playground</a>' in sheet
    assert 'class="pg-add-secondary" href="/laws/ndps" data-pg-sheet-close>Cancel</a>' in sheet
    assert ">Cancel<" in sheet
    assert "Unlock Playground" not in sheet
    assert "Add to Playground" not in sheet
    assert "+ Add to Playground" not in sheet
    assert "Subscribe to use Playground" not in sheet
    assert "Already in Playground" not in sheet
    assert PLAYGROUND_BILLING_PATH in sheet
    assert f'href="{add_path("ndps")}"' not in sheet
    assert "/playground?stage=plans" not in sheet
    assert "/billing/subscriptions/checkout" not in sheet
    assert "/billing/subscriptions/create" not in sheet
    for phrase in INVENTED:
        assert phrase not in sheet, phrase
    # Underneath: the accepted Expired 01 head, retained chip intact.
    head = _head(html)
    assert "data-expired-bareact" in head
    assert 'data-pg-kind="already_active"' in head
    assert "Already in Playground" in head
    assert (
        f'class="ActHead-inpg-continue" href="{PLAYGROUND_BILLING_PATH}">Resume Playground</a>'
        in head
    )
    # The in-page open fetches the same panel on its own.
    fetched = client.get(add_path("ndps"), headers=SHEET_FETCH)
    assert fetched.status_code == 200
    fetched_html = unescape(fetched.text)
    assert "<dialog" not in fetched_html
    assert 'class="panel ActHead' not in fetched_html
    assert fetched_html.count('class="pg-sheet-panel"') == 1
    assert 'data-pg-kind="resume"' in fetched_html
    assert "data-expired-add" in fetched_html
    assert f">{LIVE_HEADING}<" in fetched_html
    assert f'class="pg-add-primary" href="{PLAYGROUND_BILLING_PATH}">Resume Playground</a>' in fetched_html
    assert 'data-pg-add-confirm' not in fetched_html
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
    sheet = _sheet(html)
    assert html.count("<dialog") == 1
    assert 'data-pg-kind="resume"' in sheet
    assert "data-expired-add" in sheet
    assert f">{LIVE_HEADING}<" in sheet
    assert ">Resume Playground<" in sheet
    assert f'class="pg-add-primary" href="{PLAYGROUND_BILLING_PATH}">Resume Playground</a>' in sheet
    assert 'data-pg-add-confirm' not in html
    assert "Unlock Playground" not in sheet
    assert "Add to Playground" not in sheet
    assert "+ Add to Playground" not in sheet
    assert "Already in Playground" not in sheet
    assert "Already in Playground" not in _head(html)
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False
    assert _facts(client) == before


def test_phone_expired_add_non_retained_bns_cannot_enroll(tmp_path: Path) -> None:
    client = _expired_enrolled(tmp_path)
    before = _facts(client)
    html = unescape(client.get(add_path("bns")).text)
    sheet = _sheet(html)
    assert 'data-act-head="bns"' in _head(html)
    assert 'data-pg-sheet-return="/laws/bns"' in sheet
    assert 'data-pg-kind="resume"' in sheet
    assert "data-expired-add" in sheet
    assert 'data-pg-add-confirm' not in html
    assert ">Resume Playground<" in sheet
    assert f'class="pg-add-primary" href="{PLAYGROUND_BILLING_PATH}">Resume Playground</a>' in sheet
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
    fetched = client.get(add_path("ndps"), headers=SHEET_FETCH)
    assert fetched.status_code == 200
    after_fetch = _facts(client)
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
    assert 'data-pg-kind="resume"' in _sheet(second.text)
    assert _facts(client) == before
    assert after_get == before
    assert after_fetch == before
    assert after_post == before
    assert client.get("/laws/ndps").status_code == 200
    assert _facts(client) == before


def test_phone_expired_01_has_no_product_add_opener(tmp_path: Path) -> None:
    enrolled = unescape(_expired_enrolled(tmp_path).get("/laws/ndps").text)
    head = _head(enrolled)
    assert "data-expired-bareact" in head
    assert 'class="ActHead-inpg-continue"' in head
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in head
    assert "data-pg-sheet" not in head
    assert f'href="{add_path("ndps")}"' not in head
    assert "+ Add to Playground" not in head
    assert "<dialog" not in enrolled
    never = unescape(
        _expired_never_enrolled(tmp_path / "never").get("/laws/ndps").text
    )
    never_head = _head(never)
    assert "data-expired-bareact" in never_head
    assert ">Resume Playground<" in never_head
    assert f'href="{add_path("ndps")}"' not in never_head
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in never_head
    assert "+ Add to Playground" not in never_head
    assert "<dialog" not in never


def test_phone_expired_add_css_scope_pins_and_no_clone() -> None:
    # One sheet, both widths (M2): the panel rules are state-agnostic and the
    # phone geometry is the shared bottom-sheet dialog, not a cohort clone.
    css = PG_CSS.read_text(encoding="utf-8")
    assert "Add sheet (M2)" in css
    sheet_block = css.split("Add sheet (M2)", 1)[1].split(
        "Guest desktop Playground intro", 1
    )[0]
    assert ".pg-sheet-panel[data-pg-add]" in sheet_block
    assert "padding: 26px 28px" in sheet_block.split(".pg-sheet-panel[data-pg-add] {", 1)[1].split("}", 1)[0]
    assert ".pg-add-title" in sheet_block
    assert ".pg-add-lede" in sheet_block
    assert ".pg-add-primary" in sheet_block
    assert "min-height: 50px" in sheet_block.split(".pg-add-primary {", 1)[1].split("}", 1)[0]
    assert ".pg-add-secondary" in sheet_block
    assert "@media (max-width: 560px)" in sheet_block
    phone_block = sheet_block.split("@media (max-width: 560px)", 1)[1]
    assert "safe-area-inset-bottom" in phone_block
    assert "display: none !important" not in sheet_block
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", sheet_block) is None
    assert "[data-expired-add" not in css
    assert "[data-plus-add-phone]" not in css
    assert "[data-signed-in-add-phone]" not in css
    assert "[data-guest-add-phone]" not in css
    assert "[data-halted-add-phone]" not in css
    assert "data-plus-add-phone" not in css
    assert "data-halted-add-phone" not in css
    assert "is expired/02-screen" not in css
    dialog_phone = css.split("dialog.pg-sheet[open] {", 1)[1].split("/* R2 section/clause picker */", 1)[0]
    assert "max-height: min(92dvh, 100%)" in dialog_phone
    assert "inset: auto 0 0 0" in dialog_phone
    assert "safe-area-inset-bottom" in dialog_phone
    assert ".pg-sheet-close {\n    display: none;" in dialog_phone
    assert "data-expired-add-phone" not in MOBILE.read_text(encoding="utf-8")
    assert "data-expired-add" not in MOBILE.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")
    assert "is expired/02-screen" not in styles
    assert "data-expired-add" not in styles
    js = PG_JS.read_text(encoding="utf-8")
    assert "data-expired-add-phone" not in js
    assert "function enhanceSheets" in js
    assert "event.target === dialog" in js
    assert "data-pg-sheet-direct" in js
    assert "data-pg-sheet-return" in js
    assert "replaceState" in js
    add_src = ADD.read_text(encoding="utf-8")
    assert "{% block act_dialog %}" in add_src
    assert "data-pg-sheet-direct" in add_src
    assert 'data-pg-sheet-return="{{ cancel_href }}"' in add_src
    assert '{% include "partials/playground_add_panel.html" %}' in add_src
    src = ADD_PANEL.read_text(encoding="utf-8")
    for text in (add_src, src):
        assert 'kind == "expired"' not in text
        assert "data-expired-add-phone" not in text
        assert "data-expired-add-desktop" not in text
        assert "expired-add-" not in text
    assert 'kind == "resume"' in src
    assert "data-expired-add" in src
    resume_branch = src.split('{% elif kind == "resume" %}', 1)[1].split(
        '{% elif kind == "device_blocked" %}', 1
    )[0]
    assert "state.primary_href" in resume_branch
    assert "state.primary_label" in resume_branch
    assert ">Cancel<" in resume_branch
    assert "cancel_href" in resume_branch
    assert "data-pg-sheet-close" in resume_branch
    assert "data-pg-add-confirm" not in resume_branch
    assert "<form" not in resume_branch
    routes = ROUTES.read_text(encoding="utf-8")
    assert "request_is_expired_subscriber" in routes
    assert '"pg-sheet"' in routes
    view = VIEW.read_text(encoding="utf-8")
    assert 'primary_label="Resume Playground"' in view
    assert "kind == \"expired\"" not in view
    base = BASE.read_text(encoding="utf-8")
    assert "styles.css?v=main88" in base
    assert "mobile.css?v=mob107" in base
    assert "playground.css?v=pg51" in base
    assert "playground.js?v=pg11" in base
    assert "playground.css?v=pg41" not in base
    assert "playground.css?v=pg49" not in base


def test_phone_expired_add_cohorts_stay_separate(tmp_path: Path) -> None:
    expired_html = _expired_enrolled(tmp_path / "expired").get(add_path("ndps")).text
    assert "data-expired-add" in _sheet(expired_html)
    assert "data-plus-bareact" not in _head(expired_html)

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get(add_path("ndps")).text
    plus_sheet = _sheet(plus_html)
    assert "data-plus-bareact" in _head(plus_html)
    assert 'data-pg-kind="eligible_to_add"' in plus_sheet
    assert "data-expired-add" not in plus_sheet
    assert 'data-pg-add-confirm' in plus_sheet
    assert LIVE_HEADING not in plus_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get(add_path("ndps")).text
    free_sheet = _sheet(free_html)
    assert 'data-pg-kind="subscribe"' in free_sheet
    assert "data-expired-add" not in free_sheet
    assert "Unlock Playground" in free_sheet
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
    guest_sheet = _sheet(guest_html)
    assert 'data-pg-kind="guest"' in guest_sheet
    assert "data-expired-add" not in guest_sheet
    assert "Create an account" in guest_sheet

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
    halted_sheet = _sheet(halted_html)
    assert "data-halted-add" in halted_sheet
    assert "data-expired-add" not in halted_sheet
    assert LIVE_HEADING not in halted_html
    assert ">Resume Playground<" not in halted_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get(add_path("ndps")).text
    pro_sheet = _sheet(pro_html)
    assert "data-expired-add" not in pro_sheet
    assert 'data-pg-kind="eligible_to_add"' in pro_sheet
    assert "data-plus-bareact" not in _head(pro_html)
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
    act = get_bare_act("ndps")
    assert act is not None
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
            page.wait_for_selector(SHEET_READY, timeout=8000)
            page.wait_for_timeout(400)

        open_sheet()
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const resume = panel && panel.querySelector('a.pg-add-primary');
              const cancel = panel && panel.querySelector('a.pg-add-secondary');
              const closeBtn = panel && panel.querySelector('.pg-sheet-close');
              const handle = panel ? getComputedStyle(panel, '::before') : null;
              const d = dialog && dialog.getBoundingClientRect();
              const p = panel && panel.getBoundingClientRect();
              const box = resume && resume.getBoundingClientRect();
              const head = document.querySelector('.ActHead[data-expired-bareact]');
              const band = head && head.querySelector('.ActHead-band');
              const productSheet = [...document.querySelectorAll(
                '.ActHead[data-expired-bareact] [data-pg-sheet]'
              )];
              const opener = document.querySelector('[data-expired-add-test-opener]');
              return {
                open: Boolean(dialog && dialog.open),
                panels: document.querySelectorAll('[data-pg-add]').length,
                kind: panel && panel.getAttribute('data-pg-kind'),
                expiredAdd: Boolean(panel && panel.hasAttribute('data-expired-add')),
                url: location.pathname,
                panelDisplay: panel ? getComputedStyle(panel).display : null,
                title: panel && panel.querySelector('h1.pg-add-title')
                  && panel.querySelector('h1.pg-add-title').textContent.trim(),
                lede: panel && panel.querySelector('.pg-add-lede')
                  && panel.querySelector('.pg-add-lede').textContent.trim(),
                resumeText: resume && resume.textContent.trim(),
                resumeHref: resume && resume.getAttribute('href'),
                resumeW: box ? box.width : 0,
                resumeH: box ? box.height : 0,
                cancelPresent: Boolean(cancel),
                cancelText: cancel && cancel.textContent.trim(),
                cancelDisplay: cancel ? getComputedStyle(cancel).display : null,
                closePresent: Boolean(closeBtn),
                closeDisplay: closeBtn ? getComputedStyle(closeBtn).display : 'missing',
                handleDisplay: handle && handle.display,
                dialog: d && { top: d.top, left: d.left, width: d.width, height: d.height },
                panel: p && { top: p.top, left: p.left, width: p.width, bottom: p.bottom },
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                overflowY: panel ? getComputedStyle(panel).overflowY : null,
                already: Boolean(band && band.innerText.includes('Already in Playground')),
                backgroundTitle: head && head.querySelector('.ActHead-title')
                  && head.querySelector('.ActHead-title').textContent.trim(),
                backgroundResume: Boolean(band && band.innerText.includes('Resume Playground')),
                continueLabel: Boolean(band && /(?:^|\\n)\\s*Continue\\s*(?:\\n|$)/.test(band.innerText)),
                productOpeners: productSheet.length,
                clone: Boolean(document.querySelector('[data-expired-add-phone], [data-expired-add-desktop]')),
                confirmForm: Boolean(panel && panel.querySelector('[data-pg-add-confirm]')),
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
              const resume = panel.querySelector('a.pg-add-primary');
              const box = resume.getBoundingClientRect();
              const p = panel.getBoundingClientRect();
              return {
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                resumeW: box.width,
                resumeH: box.height,
                inPanel: panel.contains(resume),
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
              const head = document.querySelector('.ActHead[data-expired-bareact]');
              return {
                open: Boolean(dialog && dialog.open),
                url: location.pathname,
                focused: document.activeElement === opener,
                already: Boolean(head && head.innerText.includes('Already in Playground')),
              };
            }"""
        )

        page.evaluate(OPEN_SHEET)
        page.wait_for_selector(SHEET_READY, timeout=8000)
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
        page.wait_for_selector(SHEET_READY, timeout=8000)
        page.locator("[data-pg-add] a.pg-add-primary").click()
        page.wait_for_url("**/billing/subscriptions**", timeout=8000)
        billing_url = page.url
        browser.close()

    assert geo["open"] is True
    assert geo["panels"] == 1
    assert geo["kind"] == "resume"
    assert geo["expiredAdd"] is True
    assert geo["url"] == "/laws/ndps"
    assert geo["panelDisplay"] != "none"
    assert geo["title"] == LIVE_HEADING
    assert geo["lede"] == LIVE_COPY[0]
    assert geo["resumeText"] == "Resume Playground"
    assert geo["resumeHref"] == PLAYGROUND_BILLING_PATH
    assert geo["resumeW"] >= 300
    assert geo["resumeH"] >= 44
    assert geo["cancelPresent"] is True
    assert geo["cancelText"] == "Cancel"
    assert geo["cancelDisplay"] != "none"
    assert geo["closePresent"] is True
    assert geo["closeDisplay"] == "none"
    assert geo["handleDisplay"] == "block"
    assert geo["dialog"]["width"] >= 300
    assert geo["dialog"]["left"] >= 0
    assert geo["panel"]["left"] >= 0
    assert geo["panel"]["width"] >= 300
    assert geo["panel"]["bottom"] >= 840
    assert geo["panel"]["top"] > 400
    assert geo["overflow"] is False
    assert geo["already"] is True
    assert geo["backgroundTitle"] == act.title
    assert geo["backgroundResume"] is True
    assert geo["continueLabel"] is False
    assert geo["productOpeners"] == 0
    assert geo["clone"] is False
    assert geo["confirmForm"] is False
    assert geo["openerPresent"] is True
    assert short["overflow"] is False
    assert short["resumeW"] >= 300
    assert short["resumeH"] >= 44
    assert short["inPanel"] is True
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
        page.wait_for_selector(SHEET_READY, timeout=8000)
        page.wait_for_timeout(400)
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const resume = panel && panel.querySelector('a.pg-add-primary');
              const head = document.querySelector('.ActHead[data-expired-bareact]');
              const band = head && head.querySelector('.ActHead-band');
              const box = resume && resume.getBoundingClientRect();
              return {
                open: Boolean(dialog && dialog.open),
                kind: panel && panel.getAttribute('data-pg-kind'),
                url: location.pathname,
                title: panel && panel.querySelector('h1.pg-add-title')
                  && panel.querySelector('h1.pg-add-title').textContent.trim(),
                resumeText: resume && resume.textContent.trim(),
                resumeHref: resume && resume.getAttribute('href'),
                resumeH: box ? box.height : 0,
                already: Boolean(band && band.innerText.includes('Already in Playground')),
                sections: Boolean(head && head.querySelector('.ActHead-inpg-sections')),
                add: Boolean(band && /Add to Playground/.test(band.innerText)),
                unlock: Boolean(panel && panel.innerText.includes('Unlock Playground')),
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
        page.wait_for_selector(SHEET_READY, timeout=8000)
        page.wait_for_timeout(300)
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const resume = panel && panel.querySelector('a.pg-add-primary');
              const cancel = panel && panel.querySelector('a.pg-add-secondary');
              const closeBtn = panel && panel.querySelector('.pg-sheet-close');
              const d = dialog && dialog.getBoundingClientRect();
              const cluster = document.querySelector('.ActHead-inpg');
              return {
                open: Boolean(dialog && dialog.open),
                panels: document.querySelectorAll('[data-pg-add]').length,
                kind: panel && panel.getAttribute('data-pg-kind'),
                expiredAdd: Boolean(panel && panel.hasAttribute('data-expired-add')),
                panelDisplay: panel ? getComputedStyle(panel).display : null,
                title: panel && panel.querySelector('.pg-add-title')
                  && panel.querySelector('.pg-add-title').textContent.trim(),
                lede: panel && panel.querySelector('.pg-add-lede')
                  && panel.querySelector('.pg-add-lede').textContent.trim(),
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
    assert geo["panels"] == 1
    assert geo["kind"] == "resume"
    assert geo["expiredAdd"] is True
    assert geo["panelDisplay"] != "none"
    assert geo["title"] == LIVE_HEADING
    assert geo["lede"] == LIVE_COPY[0]
    assert geo["resumeText"] == "Resume Playground"
    assert geo["resumeHref"] == PLAYGROUND_BILLING_PATH
    assert geo["cancelDisplay"] != "none"
    assert geo["closeDisplay"] != "none"
    assert geo["notFullBleed"] is True
    assert geo["already"] is True
    assert geo["confirmForm"] is False
    assert geo["path"] == "/laws/ndps"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
