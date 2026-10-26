"""Expired cohort desktop Playground resume dialog Screen 05 (CTA map expired/05-screen).

Authorized: ChatGPT. Authenticated multiuser GET /playground/laws/ndps/add
after NDPS was added through the real roster flow and the paid period ended.
The existing resume sheet is the interception — no new route, no kind=expired.
Heading/copy come from gate_view; primary comes from live LawPlaygroundState.
Opening, closing, and reopening is read-only. Guest, Free, Plus, halted,
pending, full, device-blocked, phone, Plus 01–11, and Expired 01–04 stay
unchanged. Sections remains require_playground_open (full gate, not modal).

M2: one sheet per state (no desktop/phone twins). A direct GET of the Add
URL is the full Act page with the ``.pg-sheet-panel[data-pg-add]`` inside an
open ``<dialog>`` over the generated Act head (M2 Q4); the in-page fetch
(``X-Requested-With: pg-sheet``) returns the panel on its own for
playground.js to lift into the live dialog.
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
from constitution_memorizer.auth.sessions import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    InMemorySessionStore,
)
from constitution_memorizer.entitlements.models import BLOCK_PAID_PERIOD_ENDED
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.access import PlaygroundAccess
from constitution_memorizer.playground.urls import add_path, home_path, law_path, remove_path, sections_path
from constitution_memorizer.playground.view import PLAYGROUND_BILLING_PATH, gate_view, law_membership
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act
from tests.conftest import PLAYGROUND_TEST_NOW

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "data" / "output" / "learning_units.json"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
ADD_PANEL = ROOT / "src/constitution_memorizer/web/templates/partials/playground_add_panel.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
MANAGE = ROOT / "src/constitution_memorizer/web/templates/subscription_manage.html"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
ROUTES = ROOT / "src/constitution_memorizer/playground/routes.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
APP = ROOT / "src/constitution_memorizer/web/app.py"
BARE_PAGE = ROOT / "src/constitution_memorizer/web/bare_act_page.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
PG_JS = ROOT / "src/constitution_memorizer/web/static/playground.js"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
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
    "kind == \"expired\"",
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


def _mu_app(tmp_path: Path, *, units: Path | None = None, display_name: str = "Sanjay"):
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER,
        email="a@example.com",
        display_name=display_name,
        avatar_url=None,
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    return create_app(
        units_path=units or MINI_UNITS,
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


def _facts(client: TestClient) -> dict:
    snap = client.app.state.entitlement_service.resolve(USER, now=PLAYGROUND_TEST_NOW)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    cap = roster.peek_capacity(USER, snap)
    return {
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


def _sheet(html: str) -> str:
    """The Add sheet (M2): the open <dialog> and its one `.pg-sheet-panel`."""
    return html.split("<dialog", 1)[1].split("</dialog>", 1)[0]


def _head(html: str) -> str:
    """The generated Act head the sheet is drawn over (M2 Q4)."""
    return html.split('class="panel ActHead', 1)[1].split("data-bareact-accordion", 1)[0]


def _expired_client(tmp_path: Path, *, units: Path | None = None) -> TestClient:
    client = TestClient(_mu_app(tmp_path, units=units))
    _sign_in(client)
    _seed_ndps_then_expire(client)
    return client


def test_expired_retained_add_is_existing_resume_not_confirm(tmp_path: Path) -> None:
    client = _expired_client(tmp_path)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert snap.subscription_status == "expired"
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    req_html = client.get(add_path("ndps"))
    assert req_html.status_code == 200
    html = unescape(req_html.text)
    # One sheet inside one open dialog over the one Act head (M2 Q4), no
    # desktop/phone twins, no hard-gate shell.
    assert html.count("<dialog") == 1
    assert html.count('class="pg-sheet-panel"') == 1
    assert html.count('class="panel ActHead') == 1
    assert 'data-mscreen="bareact"' in html
    assert "data-hard-gate" not in html
    assert "PlaygroundShell" not in html
    assert 'data-expired-add="desktop"' not in html
    assert "data-expired-add-desktop" not in html
    assert "data-expired-add-phone" not in html
    assert "expired-add-" not in html
    assert 'data-plus-add="desktop"' not in html
    assert "data-plus-add-desktop" not in html
    assert "data-guest-add-desktop" not in html
    assert "data-signed-in-add-desktop" not in html
    dialog = _sheet(html)
    assert 'class="pg-sheet" data-pg-sheet-host data-pg-sheet-direct' in dialog
    assert 'data-pg-sheet-return="/laws/ndps"' in dialog
    assert " open>" in dialog.split(">", 1)[0] + ">"
    assert 'data-pg-kind="resume"' in dialog
    assert "data-expired-add" in dialog
    assert "data-halted-add" not in dialog
    assert 'data-roster-confirm="ndps"' in dialog
    assert 'data-pg-kind="already_active"' not in dialog
    assert 'data-pg-kind="eligible_to_add"' not in html
    assert 'data-pg-add-confirm' not in html
    assert 'action="/playground/laws/ndps/add"' not in html
    assert 'name="confirm"' not in html
    assert 'name="scope"' not in html
    assert ">Entire Act<" not in html
    assert ">Choose sections<" not in html
    assert f'<h1 id="pg-add-title" class="pg-add-title">{LIVE_HEADING}</h1>' in dialog
    for line in LIVE_COPY:
        assert f'<p class="pg-add-lede">{line}</p>' in dialog
    assert ">Resume Playground<" in dialog
    assert f'class="pg-add-primary" href="{PLAYGROUND_BILLING_PATH}">Resume Playground</a>' in dialog
    assert 'class="pg-add-secondary" href="/laws/ndps" data-pg-sheet-close>Cancel</a>' in dialog
    assert "Add to Playground" not in dialog
    assert "+ Add to Playground" not in dialog
    assert "Unlock Playground" not in dialog
    assert "Sign in" not in dialog
    assert "Create an account" not in dialog
    assert "Already in Playground" not in dialog
    assert "Playground full this month" not in dialog
    assert "temporarily unavailable" not in dialog
    assert "Resume a plan to add" not in dialog
    for phrase in INVENTED:
        assert phrase not in dialog, phrase
    # The Act page underneath is the retained Expired 04 head, unchanged.
    head = _head(html)
    assert "data-expired-bareact" in head
    assert 'data-pg-kind="already_active"' in head
    assert "Already in Playground" in head
    assert (
        f'class="ActHead-inpg-continue" href="{PLAYGROUND_BILLING_PATH}">Resume Playground</a>'
        in head
    )
    assert "data-pg-sheet" not in head
    # The in-page open fetches the same panel on its own (no Act context).
    fetched = client.get(add_path("ndps"), headers=SHEET_FETCH)
    assert fetched.status_code == 200
    fetched_html = unescape(fetched.text)
    assert "<dialog" not in fetched_html
    assert 'class="panel ActHead' not in fetched_html
    assert fetched_html.count('class="pg-sheet-panel"') == 1
    assert 'data-pg-kind="resume"' in fetched_html
    assert "data-expired-add" in fetched_html
    assert f'class="pg-add-primary" href="{PLAYGROUND_BILLING_PATH}">Resume Playground</a>' in fetched_html
    assert 'data-pg-add-confirm' not in fetched_html
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True


def test_expired_add_primary_is_live_state_not_post(tmp_path: Path) -> None:
    client = _expired_client(tmp_path)
    snap = client.app.state.entitlement_service.resolve(USER)
    access = PlaygroundAccess(
        user_id=USER,
        snapshot=snap,
        can_open=snap.can_open_playground,
        can_consume_new_law=snap.can_consume_new_playground_law,
        local_owner=False,
        can_view_home=True,
    )
    state = law_membership(
        law_id="ndps",
        access=access,
        roster=client.app.state.roster,
        overlay=client.app.state.playground,
    )
    live_gate = gate_view(reason=str(snap.playground_block_reason or ""))
    html = unescape(client.get(add_path("ndps")).text)
    dialog = _sheet(html)
    assert state.kind == "already_active"
    assert state.primary_label == "Resume Playground"
    assert state.primary_href == PLAYGROUND_BILLING_PATH
    assert live_gate.title == LIVE_HEADING
    assert f">{live_gate.title}<" in dialog
    for line in live_gate.lines:
        assert line in dialog
    assert f'class="pg-add-primary" href="{state.primary_href}">{state.primary_label}</a>' in dialog
    assert 'action="/playground/laws/ndps/add"' not in html
    posted = client.post(
        add_path("ndps"),
        data={**_csrf(client), "confirm": "add", "scope": "sections"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    assert posted.headers.get("location") == home_path()
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is True


def test_expired_add_mutation_safety_open_close_reopen(tmp_path: Path) -> None:
    client = _expired_client(tmp_path)
    before = _facts(client)
    assert "ndps" in before["active"]
    first = client.get(add_path("ndps"))
    assert first.status_code == 200
    assert 'data-pg-kind="resume"' in _sheet(first.text)
    after_open = _facts(client)
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
    after_reopen = _facts(client)
    fetched = client.get(add_path("ndps"), headers=SHEET_FETCH)
    assert fetched.status_code == 200
    assert 'data-pg-kind="resume"' in fetched.text
    after_fetch = _facts(client)
    assert after_open == before
    assert after_post == before
    assert after_reopen == before
    assert after_fetch == before
    assert client.get("/laws/ndps").status_code == 200
    assert _facts(client) == before


def test_expired_sections_stay_gated_not_picker(tmp_path: Path) -> None:
    client = _expired_client(tmp_path)
    sections = client.get(sections_path("ndps"))
    assert sections.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAID_PERIOD_ENDED}"' in sections.text
    assert 'data-pg-picker' not in sections.text
    assert "Choose what to learn" not in sections.text
    assert 'name="scope"' not in sections.text
    assert "Select sections to add" not in sections.text
    workspace = client.get(law_path("ndps"))
    assert workspace.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAID_PERIOD_ENDED}"' in workspace.text
    assert 'data-pg-learn-panel="cloze"' not in workspace.text


def test_non_retained_expired_law_cannot_add(tmp_path: Path) -> None:
    client = _expired_client(tmp_path)
    html = unescape(client.get(add_path("bns")).text)
    dialog = _sheet(html)
    assert html.count("<dialog") == 1
    assert 'data-act-head="bns"' in _head(html)
    assert 'data-pg-sheet-return="/laws/bns"' in dialog
    assert 'data-pg-kind="resume"' in dialog
    assert "data-expired-add" in dialog
    assert 'data-pg-kind="eligible_to_add"' not in html
    assert 'data-pg-kind="already_active"' not in html
    assert 'data-pg-add-confirm' not in html
    assert 'name="confirm"' not in html
    assert 'name="scope"' not in html
    assert f">{LIVE_HEADING}<" in dialog
    for line in LIVE_COPY:
        assert line in dialog
    assert ">Resume Playground<" in dialog
    assert f'class="pg-add-primary" href="{PLAYGROUND_BILLING_PATH}">Resume Playground</a>' in dialog
    assert 'class="pg-add-secondary" href="/laws/bns" data-pg-sheet-close>Cancel</a>' in dialog
    posted = client.post(
        add_path("bns"),
        data={**_csrf(client), "confirm": "add", "scope": "sections"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    assert posted.headers.get("location") == home_path()
    assert client.app.state.roster.is_law_active_this_period(USER, "bns") is False


def test_guest_free_plus_halted_pending_stay_separate(tmp_path: Path) -> None:
    guest_html = TestClient(_mu_app(tmp_path / "guest")).get(add_path("ndps")).text
    guest_sheet = _sheet(guest_html)
    assert 'data-pg-kind="guest"' in guest_sheet
    assert "data-guest-add-gate" in guest_sheet
    assert ">Sign in<" in guest_sheet
    assert "Create an account" in guest_sheet
    assert "data-expired-add" not in guest_sheet
    assert "data-expired-bareact" not in _head(guest_html)
    assert LIVE_HEADING not in guest_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get(add_path("ndps")).text
    free_sheet = _sheet(free_html)
    assert 'data-pg-kind="subscribe"' in free_sheet
    assert "Unlock Playground" in free_sheet
    assert "data-expired-add" not in free_sheet
    assert "data-expired-bareact" not in _head(free_html)
    assert LIVE_HEADING not in free_html
    assert "Resume Playground" not in free_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get(add_path("ndps")).text
    plus_sheet = _sheet(plus_html)
    assert "data-plus-bareact" in _head(plus_html)
    assert 'data-pg-kind="eligible_to_add"' in plus_sheet
    assert 'data-pg-add-confirm' in plus_sheet
    assert 'data-add-step="confirm"' in plus_sheet
    assert '<button type="submit" class="pg-add-primary">Add to Playground</button>' in plus_sheet
    assert "data-expired-add" not in plus_sheet
    assert "data-expired-bareact" not in _head(plus_html)
    assert LIVE_HEADING not in plus_html
    assert "Resume Playground" not in plus_html
    added = _confirm_add(plus, "ndps")
    assert added.status_code in {200, 303}
    plus.post(remove_path("ndps"), data=_csrf(plus), follow_redirects=False)
    readd = plus.get(add_path("ndps")).text
    readd_sheet = _sheet(readd)
    assert 'data-pg-kind="re_add"' in readd_sheet
    assert "Add back" in readd_sheet
    assert "data-expired-add" not in readd_sheet

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    _confirm_add(halted, "ndps")
    stored = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )
    halted_html = halted.get(add_path("ndps")).text
    halted_sheet = _sheet(halted_html)
    assert 'data-pg-kind="resume"' in halted_sheet
    assert "data-expired-add" not in halted_sheet
    assert "data-halted-add" in halted_sheet
    assert "data-halted-bareact" in _head(halted_html)
    assert "data-expired-bareact" not in _head(halted_html)
    assert LIVE_HEADING not in halted_html
    assert "Resume a plan to add" not in halted_html
    assert ">Resume Playground<" not in halted_html
    halted_snap = halted.app.state.entitlement_service.resolve(USER)
    assert halted_snap.subscription_status == "halted"
    assert halted_snap.playground_block_reason != BLOCK_PAID_PERIOD_ENDED

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    pending_html = pending.get(add_path("ndps")).text
    assert "data-expired-add" not in _sheet(pending_html)
    assert LIVE_HEADING not in pending_html
    assert "temporarily unavailable" in pending_html.lower() or 'data-pg-kind="pending"' in pending_html


def test_expired_add_uses_shared_predicate_existing_resume_route() -> None:
    add_src = ADD.read_text(encoding="utf-8")
    # One sheet over the Act page (M2 Q4): the dialog wraps the shared panel
    # partial; the per-surface twins are gone.
    assert '{% extends "bare_act.html" if act is defined and act else "playground_base.html" %}' in add_src
    assert "{% block act_dialog %}" in add_src
    assert "data-pg-sheet-direct" in add_src
    assert 'data-pg-sheet-return="{{ cancel_href }}"' in add_src
    assert add_src.count('{% include "partials/playground_add_panel.html" %}') == 2
    assert "data-expired-bareact" not in add_src
    for src in (add_src, ADD_PANEL.read_text(encoding="utf-8")):
        assert 'kind == "expired"' not in src
        assert 'data-expired-add="desktop"' not in src
        assert "data-expired-add-desktop" not in src
        assert "data-expired-add-phone" not in src
        assert 'data-plus-add="desktop"' not in src
        assert "data-plus-add-desktop" not in src
        assert "data-guest-add-desktop" not in src
        assert "data-signed-in-add-desktop" not in src
        assert "expired-add-" not in src
        assert "plus-add-" not in src
    panel = ADD_PANEL.read_text(encoding="utf-8")
    assert 'kind == "resume"' in panel
    assert "expired_add" in panel
    assert "data-expired-add" in panel
    assert "halted_add" in panel
    assert "state.primary_href" in panel
    assert "state.primary_label" in panel
    assert 'kind == "device_blocked"' in panel
    assert "blocked_pending or kind == " in panel
    assert "blocked_full or kind == " in panel
    assert 'action="/playground/laws/{{ law_id }}/add"' in panel
    resume_branch = panel.split("{% elif kind == \"resume\" %}", 1)[1].split(
        "{% elif kind == \"device_blocked\" %}", 1
    )[0]
    assert 'method="post"' not in resume_branch
    assert "data-pg-add-confirm" not in resume_branch
    assert "name=\"scope\"" not in resume_branch
    assert (
        '<a class="pg-add-primary" href="{{ state.primary_href }}">{{ state.primary_label }}</a>'
        in resume_branch
    )
    assert (
        '<a class="pg-add-secondary" href="{{ cancel_href }}" data-pg-sheet-close>Cancel</a>'
        in resume_branch
    )
    routes = ROUTES.read_text(encoding="utf-8")
    ctx = routes.split("def _add_page_context", 1)[1].split("def _rollover_ids", 1)[0]
    assert "request_is_expired_subscriber" in ctx
    assert "request_is_active_plus" in ctx
    assert 'kind == "already_active"' in ctx
    assert 'kind = "resume"' in ctx
    assert "gate_view" in ctx
    assert "expired_add" in ctx
    assert 'law_id == "ndps"' in ctx
    assert "plus_add_confirm_copy" in ctx
    assert "bare_act_page_context(request, bare)" in ctx
    assert '"pg-sheet"' in ctx
    add_route = routes.split('"/laws/{law_id}/add"', 1)[1].split(
        "@router.post", 1
    )[0]
    assert "playground_add_confirm" in add_route or "require_eligible_law" in add_route
    assert "/expired/resume" not in routes
    deps = DEPS.read_text(encoding="utf-8")
    assert "def request_is_expired_subscriber" in deps
    assert "BLOCK_PAID_PERIOD_ENDED" in deps
    view = VIEW.read_text(encoding="utf-8")
    assert 'primary_label="Resume Playground"' in view
    assert 'KIND_RESUME = "resume"' in view
    assert "kind == \"expired\"" not in view
    js = PG_JS.read_text(encoding="utf-8")
    assert "function enhanceSheets" in js
    assert "[data-pg-sheet]" in js
    assert "dialog.pg-sheet" in js
    assert "data-pg-sheet-direct" in js
    assert "data-pg-sheet-return" in js
    assert "showModal" in js
    assert "replaceState" in js
    css = PG_CSS.read_text(encoding="utf-8")
    assert "Add sheet (M2)" in css
    assert ".pg-sheet-panel[data-pg-add]" in css
    assert ".pg-add-primary" in css
    assert ".pg-add-secondary" in css
    assert "[data-expired-add" not in css
    assert "[data-plus-add-desktop]" not in css
    assert "[data-guest-add-desktop]" not in css
    assert "[data-signed-in-add-desktop]" not in css


def test_plus_screens_and_expired_01_04_untouched() -> None:
    assert 'data-plus-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-expired-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-plus-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-expired-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-plus-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-expired-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert "data-plus-bareact" in BARE.read_text(encoding="utf-8")
    assert "data-expired-bareact" in BARE.read_text(encoding="utf-8")
    assert 'data-add-step="confirm"' in ADD_PANEL.read_text(encoding="utf-8")
    assert 'data-plus-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-plus-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-plus-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-plus-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    for path in (LANDING, BROWSE, LAWS, BARE, HOME, MANAGE, DASH, CAL, PROFILE, SETTINGS):
        text = path.read_text(encoding="utf-8")
        assert "data-expired-add" not in text
    bare = BARE.read_text(encoding="utf-8")
    assert "pg.kind == 'already_active'" in bare
    assert 'href="/playground">Continue</a>' not in bare
    assert (
        'class="ActHead-inpg-continue" href="{{ pg.primary_href }}">{{ pg.primary_label }}</a>'
        in bare
    )
    app = APP.read_text(encoding="utf-8")
    page = app.split("async def law_detail_page", 1)[1].split(
        "async def bare_act_section_page", 1
    )[0]
    assert "bare_act_page_context(request, bare)" in page
    bare_page = BARE_PAGE.read_text(encoding="utf-8")
    assert "request_is_expired_subscriber" in bare_page
    assert '"plus_bareact": request_is_active_plus(request)' in bare_page
    assert "def request_is_active_plus" in DEPS.read_text(encoding="utf-8")
    assert 'snapshot.tier == "plus"' in DEPS.read_text(encoding="utf-8")
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-expired-add" not in mobile
    view = VIEW.read_text(encoding="utf-8")
    assert 'badge_label="Already in Playground"' in view


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


def test_expired_phone_add_uses_resume_not_confirm(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_then_expire(client)
    html = unescape(client.get(add_path("ndps")).text)
    dialog = _sheet(html)
    assert LIVE_HEADING in dialog
    assert "Resume Playground" in dialog
    assert PLAYGROUND_BILLING_PATH in dialog
    assert 'data-pg-add-confirm' not in dialog
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    port, _server = _serve(app)
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
        page.goto(f"{origin}{add_path('ndps')}", wait_until="networkidle")
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const title = panel && panel.querySelector('.pg-add-title');
              return {
                open: Boolean(dialog && dialog.open),
                panels: document.querySelectorAll('[data-pg-add]').length,
                kind: panel && panel.getAttribute('data-pg-kind'),
                expired: Boolean(panel && panel.hasAttribute('data-expired-add')),
                panelDisplay: panel ? getComputedStyle(panel).display : null,
                title: title && title.textContent.trim(),
                head: Boolean(document.querySelector('.ActHead[data-expired-bareact]')),
              };
            }"""
        )
        browser.close()
    assert geo["open"] is True
    assert geo["panels"] == 1
    assert geo["kind"] == "resume"
    assert geo["expired"] is True
    assert geo["panelDisplay"] != "none"
    assert geo["title"] == LIVE_HEADING
    assert geo["head"] is True


def test_expired_add_screen05_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_then_expire(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    act = get_bare_act("ndps")
    assert act is not None

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "expired_add_screen05_1280.png"
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
        page.evaluate(
            """() => {
              const a = document.createElement('a');
              a.href = '/playground/laws/ndps/add';
              a.setAttribute('data-pg-sheet', '');
              a.style.display = 'none';
              document.body.appendChild(a);
              a.click();
            }"""
        )
        page.wait_for_selector("[data-pg-add][data-expired-add]", timeout=8000)
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panel = document.querySelector('[data-pg-add]');
              const resume = panel && panel.querySelector('.pg-add-primary');
              const cancel = panel && panel.querySelector('.pg-add-secondary');
              const closeBtn = panel && panel.querySelector('[data-pg-sheet-close].pg-sheet-close');
              const expiredBare = document.querySelector('.ActHead[data-expired-bareact]');
              const cluster = document.querySelector('.ActHead-inpg');
              const titleEl = panel && panel.querySelector('.pg-add-title');
              const ledeEl = panel && panel.querySelector('.pg-add-lede');
              const backdrop = dialog ? getComputedStyle(dialog, '::backdrop') : null;
              const confirmForm = panel && panel.querySelector('[data-pg-add-confirm]');
              const scope = panel && panel.querySelector("[data-add-step='scope']");
              return {
                open: Boolean(dialog && dialog.open),
                panels: document.querySelectorAll('[data-pg-add]').length,
                kind: panel && panel.getAttribute('data-pg-kind'),
                expiredAdd: Boolean(panel && panel.hasAttribute('data-expired-add')),
                haltedAdd: Boolean(panel && panel.hasAttribute('data-halted-add')),
                panelDisplay: panel ? getComputedStyle(panel).display : null,
                eyebrow: Boolean(panel && panel.querySelector('.pg-eyebrow')),
                title: titleEl && titleEl.textContent.trim(),
                lede: ledeEl && ledeEl.textContent.trim(),
                resumeText: resume && resume.textContent.trim(),
                resumeHref: resume && resume.getAttribute('href'),
                cancelText: cancel && cancel.textContent.trim(),
                cancelHref: cancel && cancel.getAttribute('href'),
                cancelDisplay: cancel ? getComputedStyle(cancel).display : null,
                hasClose: Boolean(closeBtn),
                closeLabel: closeBtn && closeBtn.getAttribute('aria-label'),
                background: Boolean(expiredBare),
                already: Boolean(cluster && cluster.innerText.includes('Already in Playground')),
                header: document.querySelector('.account-menu-btn-status') &&
                  document.querySelector('.account-menu-btn-status').textContent.trim(),
                actTitle: expiredBare && expiredBare.querySelector('.ActHead-title') &&
                  expiredBare.querySelector('.ActHead-title').textContent.trim(),
                confirmForm: Boolean(confirmForm),
                scope: Boolean(scope),
                path: location.pathname,
                scrim: backdrop && backdrop.backgroundColor,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator(".pg-sheet-close").click()
        closed = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              return {
                open: Boolean(dialog && dialog.open),
                path: location.pathname,
                head: Boolean(document.querySelector('.ActHead[data-expired-bareact]')),
              };
            }"""
        )
        browser.close()

    assert geo["open"] is True
    assert geo["panels"] == 1
    assert geo["kind"] == "resume"
    assert geo["expiredAdd"] is True
    assert geo["haltedAdd"] is False
    assert geo["panelDisplay"] != "none"
    assert geo["eyebrow"] is False
    assert geo["title"] == LIVE_HEADING
    assert geo["lede"] == LIVE_COPY[0]
    assert geo["resumeText"] == "Resume Playground"
    assert geo["resumeHref"] == PLAYGROUND_BILLING_PATH
    assert geo["cancelText"] == "Cancel"
    assert geo["cancelHref"] == "/laws/ndps"
    assert geo["cancelDisplay"] != "none"
    assert geo["hasClose"] is True
    assert geo["closeLabel"] == "Close"
    assert geo["background"] is True
    assert geo["already"] is True
    assert geo["header"] == LIVE_HEADING
    assert geo["actTitle"] == act.title
    assert geo["confirmForm"] is False
    assert geo["scope"] is False
    assert geo["path"] == "/laws/ndps"
    assert closed["open"] is False
    assert closed["path"] == "/laws/ndps"
    assert closed["head"] is True
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_expired_add_plus_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "expired_add_screen05_plus_regression_1280.png"
    origin = f"http://127.0.0.1:{port}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
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
                    "httpOnly": False,
                    "secure": False,
                    "sameSite": "Lax",
                }
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
        page.locator(".ActHead[data-plus-bareact] [data-pg-sheet]").click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='eligible_to_add']", timeout=8000)
        geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const title = panel && panel.querySelector("[data-add-step='confirm'] .pg-add-title");
              const submit = panel && panel.querySelector("[data-add-step='confirm'] button.pg-add-primary");
              return {
                kind: panel && panel.getAttribute('data-pg-kind'),
                plusHead: Boolean(document.querySelector('.ActHead[data-plus-bareact]')),
                expiredHead: Boolean(document.querySelector('.ActHead[data-expired-bareact]')),
                expiredAttr: Boolean(panel && panel.hasAttribute('data-expired-add')),
                title: title && title.textContent.trim(),
                submit: submit && submit.textContent.trim(),
                confirm: Boolean(panel && panel.querySelector('[data-pg-add-confirm]')),
                header: document.querySelector('.account-menu-btn-status') &&
                  document.querySelector('.account-menu-btn-status').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["kind"] == "eligible_to_add"
    assert geo["plusHead"] is True
    assert geo["expiredHead"] is False
    assert geo["expiredAttr"] is False
    assert geo["title"] == "Add to Playground"
    assert geo["submit"] == "Add to Playground"
    assert geo["confirm"] is True
    assert geo["header"] == "RecallC Plus"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
