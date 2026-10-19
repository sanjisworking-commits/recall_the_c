"""Halted cohort desktop Add interception sheet Screen 05 (CTA map halted/05-screen).

Authorized: ChatGPT. Authenticated multiuser GET /playground/laws/ndps/add
after a real Plus subscription is halted. Existing resume kind stays; copy
comes from gate_view(BLOCK_PAYMENT_HALTED), not generic Resume Playground.
No new route, no kind=halted, no POST form. Guest, Free, Plus, Expired,
paused, pending, device_blocked, roster-full, phone, Plus 01–11, Expired
01–11, and Halted 01–04 stay unchanged. No Halted 06 work.

M2: one Add sheet per state (`.pg-sheet-panel[data-pg-add]`, both widths),
served inside an open <dialog> over the full Act page (M2 Q4); the
desktop/phone twins and the NDPS fixture title are gone. The halted
behaviour is unchanged — resume kind, gate copy, recovery CTA, Cancel back
to the Act, no POST form — only the markup these tests read changed.
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
from constitution_memorizer.entitlements.models import (
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
)
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.access import PlaygroundAccess
from constitution_memorizer.playground.urls import add_path, home_path, law_path, sections_path
from constitution_memorizer.playground.view import PLAYGROUND_BILLING_PATH, gate_view, law_membership
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act
from tests.conftest import PLAYGROUND_TEST_NOW

NDPS = get_bare_act("ndps")
assert NDPS is not None
NDPS_TITLE = NDPS.title

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
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
MANAGE = ROOT / "src/constitution_memorizer/web/templates/subscription_manage.html"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
ROUTES = ROOT / "src/constitution_memorizer/playground/routes.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
APP = ROOT / "src/constitution_memorizer/web/app.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
PG_JS = ROOT / "src/constitution_memorizer/web/static/playground.js"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_HALTED_GATE = gate_view(reason=BLOCK_PAYMENT_HALTED)
LIVE_HEADING = LIVE_HALTED_GATE.title
LIVE_COPY = LIVE_HALTED_GATE.lines
LIVE_CTA = LIVE_HALTED_GATE.cta_label
LIVE_EXPIRED_STATUS = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
INVENTED = (
    "Your subscription expired",
    "Resume subscription",
    "Your payment failed",
    "Fix your payment",
    "Subscription halted",
    "Playground unavailable",
    "Free plan",
    "Unlock all",
    'kind == "halted"',
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
    status: str = "halted",
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


def _seed_ndps_then_halt(client: TestClient) -> None:
    _subscribe(client, status="active")
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps")
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None
    client.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )


def _facts(client: TestClient) -> dict:
    snap = client.app.state.entitlement_service.resolve(USER, now=PLAYGROUND_TEST_NOW)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    cap = roster.peek_capacity(USER, snap)
    stored = client.app.state.subscriptions.get_current_subscription(USER)
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
        "subscription": None
        if stored is None
        else (stored.id, stored.status, stored.tier, stored.is_current),
        "entitlement": (
            snap.subscription_status,
            snap.playground_block_reason,
            snap.can_open_playground,
        ),
    }


def _sheet(html: str) -> str:
    """The one Add sheet (M2): `.pg-sheet-panel[data-pg-add]` to its close."""
    return html.split('class="pg-sheet-panel"', 1)[1].split("</section>", 1)[0]


def _sheet_tag(html: str) -> str:
    """The panel's own attribute run, whitespace collapsed."""
    return re.sub(r"\s+", " ", html.split('class="pg-sheet-panel"', 1)[1].split(">", 1)[0])


def _dialog_tag(html: str) -> str:
    return html.split("<dialog ", 1)[1].split(">", 1)[0]


def _head(html: str) -> str:
    """The Act head the sheet is drawn over (M2 Q4)."""
    return html.split('class="panel ActHead', 1)[1].split("</section>", 1)[0]


def _body(html: str) -> str:
    """Everything after the page <title>, so copy pins ignore the tab name."""
    return html.split("</title>", 1)[1]


def test_halted_add_is_existing_resume_not_confirm(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_then_halt(client)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.is_authenticated is True
    assert snap.tier == "plus"
    assert snap.subscription_status == "halted"
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    assert snap.playground_block_reason == BLOCK_PAYMENT_HALTED
    assert LIVE_HEADING == "Payment retries have stopped"
    assert LIVE_CTA == "Manage subscription"
    access = PlaygroundAccess(
        user_id=USER,
        snapshot=snap,
        can_open=snap.can_open_playground,
        can_consume_new_law=snap.can_consume_new_playground_law,
        local_owner=False,
        can_view_home=True,
    )
    raw = law_membership(
        law_id="ndps",
        access=access,
        roster=client.app.state.roster,
        overlay=client.app.state.playground,
    )
    assert raw.kind == "resume"
    assert raw.primary_label == "Resume Playground"

    before = _facts(client)
    page = client.get(add_path("ndps"))
    assert page.status_code == 200
    html = unescape(page.text)
    # One sheet, both widths (M2 §2.1), inside an open <dialog> over the full
    # Act page (M2 Q4): no twins, no other cohort marker.
    assert html.count('class="pg-sheet-panel"') == 1
    tag = _sheet_tag(html)
    assert "data-pg-add " in tag
    assert 'data-pg-kind="resume"' in tag
    assert " data-halted-add " in tag
    assert 'data-roster-confirm="ndps"' in tag
    assert 'role="dialog"' in tag and 'aria-modal="true"' in tag
    assert 'aria-labelledby="pg-add-title"' in tag
    assert "data-expired-add" not in html
    assert "data-halted-add-desktop" not in html
    assert "data-halted-add-phone" not in html
    assert 'data-halted-add="desktop"' not in html
    assert 'data-pg-kind="halted"' not in html
    assert 'data-pg-kind="already_active"' not in _sheet(html)
    assert 'data-pg-kind="eligible_to_add"' not in html
    assert 'data-plus-add="desktop"' not in html
    assert "data-plus-add" not in html
    assert 'data-expired-add="desktop"' not in html
    assert "data-guest-add-desktop" not in html
    assert "data-signed-in-add-desktop" not in html
    assert "data-guest-add-gate" not in html
    assert "data-pg-add-confirm" not in html
    assert 'action="/playground/laws/ndps/add"' not in html
    assert 'name="confirm"' not in html
    assert 'name="scope"' not in html
    assert "<form" not in _sheet(html)
    assert ">Entire Act<" not in html
    assert ">Choose sections<" not in html
    # The tab name is "Add to Playground · {Act}"; no sheet or head copy is.
    assert "Add to Playground" not in _body(html)
    assert "Add back" not in html
    dialog = _dialog_tag(html)
    assert 'class="pg-sheet"' in dialog
    assert "data-pg-sheet-host" in dialog
    assert "data-pg-sheet-direct" in dialog
    assert 'data-pg-sheet-return="/laws/ndps"' in dialog
    assert dialog.rstrip().endswith("open")
    assert 'data-mscreen="bareact"' in html
    assert "PlaygroundShell" not in html
    assert "data-hard-gate" not in html
    desk = _sheet(html)
    assert f'<h1 id="pg-add-title" class="pg-add-title">{LIVE_HEADING}</h1>' in desk
    for line in LIVE_COPY:
        assert f'<p class="pg-add-lede">{line}</p>' in desk
    assert f'<a class="pg-add-primary" href="{PLAYGROUND_BILLING_PATH}">{LIVE_CTA}</a>' in desk
    assert '<a class="pg-add-secondary" href="/laws/ndps" data-pg-sheet-close>Cancel</a>' in desk
    assert ">Resume Playground<" not in desk
    assert "Resume a plan to add" not in desk
    assert LIVE_EXPIRED_STATUS not in desk
    assert "Unlock Playground" not in desk
    assert "Sign in" not in desk
    assert "data-pg-sheet-close" in desk
    assert "pg-eyebrow" not in desk
    for phrase in INVENTED:
        assert phrase not in desk, phrase
    # The Act head underneath is the halted one (M2 Q4), the same chip the
    # Bare Act page shows: Sections + the recovery CTA, not Continue.
    head = _head(html)
    assert "data-halted-bareact" in head
    assert 'data-act-head="ndps"' in head
    assert f'<h1 class="ActHead-title">{NDPS_TITLE}</h1>' in head
    assert "Already in Playground" in head
    assert 'class="ActHead-inpg"' in head
    assert f'class="ActHead-inpg-sections" href="{sections_path("ndps")}"' in head
    assert f'class="ActHead-inpg-continue" href="{PLAYGROUND_BILLING_PATH}"' in head
    assert f">{LIVE_CTA}<" in head
    assert ">Continue<" not in head
    assert "data-pg-sheet" not in head
    # The in-page open (playground.js, X-Requested-With: pg-sheet) gets the
    # same panel on its own — no Act head, no dialog — and lifts it into the
    # live dialog itself; same kind, copy, CTA and Cancel.
    fetched = unescape(
        client.get(add_path("ndps"), headers={"X-Requested-With": "pg-sheet"}).text
    )
    assert fetched.count('class="pg-sheet-panel"') == 1
    assert 'class="panel ActHead' not in fetched
    assert "<dialog" not in fetched
    assert "data-pg-sheet-direct" not in fetched
    fetched_tag = _sheet_tag(fetched)
    assert 'data-pg-kind="resume"' in fetched_tag
    assert " data-halted-add " in fetched_tag
    assert _sheet(fetched) == desk
    assert _facts(client) == before
    assert client.get("/laws/ndps").status_code == 200
    assert "data-halted-bareact" in client.get("/laws/ndps").text
    assert "<dialog" not in client.get("/laws/ndps").text
    workspace = client.get(law_path("ndps"))
    assert workspace.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAYMENT_HALTED}"' in workspace.text
    assert 'data-pg-learn-panel="cloze"' not in workspace.text
    sections = client.get(sections_path("ndps"))
    assert sections.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAYMENT_HALTED}"' in sections.text
    assert "data-pg-picker" not in sections.text
    posted = client.post(
        add_path("ndps"),
        data={**_csrf(client), "confirm": "add", "scope": "entire"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    assert posted.headers.get("location") == home_path()
    again = client.get(add_path("ndps"))
    assert again.status_code == 200
    assert _facts(client) == before
    bns = client.get(add_path("bns"))
    assert bns.status_code == 200
    assert _facts(client) == before


def test_halted_elapsed_period_stays_halted_on_add(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_then_halt(client)
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None
    client.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        billing_period_start=EXPIRED_START,
        billing_period_end=EXPIRED_END,
    )
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.subscription_status == "halted"
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    html = unescape(client.get(add_path("ndps")).text)
    tag = _sheet_tag(html)
    assert " data-halted-add " in tag
    assert "data-expired-add" not in html
    assert "data-plus-add" not in html
    assert 'data-pg-kind="resume"' in tag
    sheet = _sheet(html)
    assert f'<h1 id="pg-add-title" class="pg-add-title">{LIVE_HEADING}</h1>' in sheet
    assert LIVE_EXPIRED_STATUS not in html
    assert f'<a class="pg-add-primary" href="{PLAYGROUND_BILLING_PATH}">{LIVE_CTA}</a>' in sheet
    assert ">Resume Playground<" not in html
    assert "data-halted-bareact" in _head(html)
    assert "data-expired-bareact" not in html


def test_never_added_halted_bns_gets_same_sheet(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_then_halt(client)
    html = unescape(client.get(add_path("bns")).text)
    tag = _sheet_tag(html)
    assert 'data-pg-kind="resume"' in tag
    assert " data-halted-add " in tag
    assert 'data-roster-confirm="bns"' in tag
    assert 'data-pg-kind="eligible_to_add"' not in html
    assert "data-pg-add-confirm" not in html
    assert 'name="confirm"' not in html
    assert 'name="scope"' not in html
    sheet = _sheet(html)
    assert f'<h1 id="pg-add-title" class="pg-add-title">{LIVE_HEADING}</h1>' in sheet
    for line in LIVE_COPY:
        assert f'<p class="pg-add-lede">{line}</p>' in sheet
    assert f'<a class="pg-add-primary" href="{PLAYGROUND_BILLING_PATH}">{LIVE_CTA}</a>' in sheet
    assert '<a class="pg-add-secondary" href="/laws/bns" data-pg-sheet-close>Cancel</a>' in sheet
    assert 'data-pg-sheet-return="/laws/bns"' in _dialog_tag(html)
    assert 'data-act-head="bns"' in _head(html)
    assert "Already in Playground" not in _head(html)
    posted = client.post(
        add_path("bns"),
        data={**_csrf(client), "confirm": "add", "scope": "sections"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    assert posted.headers.get("location") == home_path()
    assert client.app.state.roster.is_law_active_this_period(USER, "bns") is False


def test_guest_free_plus_expired_paused_pending_are_not_halted_add(
    tmp_path: Path,
) -> None:
    guest_html = TestClient(_mu_app(tmp_path / "guest")).get(add_path("ndps")).text
    assert 'data-pg-kind="guest"' in _sheet_tag(guest_html)
    assert "data-guest-add-gate" in _sheet(guest_html)
    assert ">Sign in</a>" in _sheet(guest_html)
    assert "data-halted-add" not in guest_html
    assert "data-halted-bareact" not in guest_html
    assert LIVE_HEADING not in guest_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get(add_path("ndps")).text
    assert 'data-pg-kind="subscribe"' in _sheet_tag(free_html)
    assert '<a class="pg-add-primary" href="/playground">Unlock Playground</a>' in _sheet(free_html)
    assert "data-halted-add" not in free_html
    assert "data-halted-bareact" not in free_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus, status="active")
    plus_html = plus.get(add_path("ndps")).text
    assert 'data-pg-kind="eligible_to_add"' in _sheet_tag(plus_html)
    assert "data-plus-bareact" in _head(plus_html)
    assert "data-pg-add-confirm" in _sheet(plus_html)
    assert '<button type="submit" class="pg-add-primary">Add to Playground</button>' in _sheet(plus_html)
    assert "data-halted-add" not in plus_html
    assert "data-halted-bareact" not in plus_html

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(expired, status="active")
    added = _confirm_add(expired, "ndps")
    assert added.status_code in {200, 303}
    stored = expired.app.state.subscriptions.get_current_subscription(USER)
    expired.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        status="expired",
        billing_period_start=EXPIRED_START,
        billing_period_end=EXPIRED_END,
    )
    expired_html = unescape(expired.get(add_path("ndps")).text)
    assert " data-expired-add " in _sheet_tag(expired_html)
    assert 'data-pg-kind="resume"' in _sheet_tag(expired_html)
    assert "data-halted-add" not in expired_html
    assert "data-expired-bareact" in _head(expired_html)
    assert "data-halted-bareact" not in expired_html
    assert f">{LIVE_EXPIRED_STATUS}<" in _sheet(expired_html)
    assert ">Resume Playground<" in _sheet(expired_html)
    assert LIVE_HEADING not in expired_html

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused, status="paused")
    paused_html = paused.get(add_path("ndps")).text
    assert "data-halted-add" not in paused_html
    assert 'data-pg-kind="resume"' in _sheet_tag(paused_html)
    assert '<a class="pg-add-primary" href="/billing/subscriptions">Resume Playground</a>' in _sheet(paused_html)
    assert LIVE_HEADING not in paused_html

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    pending_html = pending.get(add_path("ndps")).text
    assert "data-halted-add" not in pending_html
    assert "temporarily unavailable" in pending_html.lower() or 'data-pg-kind="pending"' in pending_html


def test_halted_add_uses_shared_predicate_existing_resume_route() -> None:
    # M2: one sheet panel per state in partials/playground_add_panel.html;
    # playground_add.html wraps it — in an open <dialog> over the Act page
    # (direct URL) or bare on playground_base.html (in-page fetch / POST).
    wrapper = ADD.read_text(encoding="utf-8")
    add_src = ADD_PANEL.read_text(encoding="utf-8")
    assert '{% extends "bare_act.html" if act is defined and act else "playground_base.html" %}' in wrapper
    assert "{% block act_dialog %}" in wrapper
    assert "{% block playground %}" in wrapper
    assert wrapper.count('{% include "partials/playground_add_panel.html" %}') == 2
    assert "data-pg-sheet-direct" in wrapper
    assert 'data-pg-sheet-return="{{ cancel_href }}"' in wrapper
    assert "pg-sheet-panel" not in wrapper
    assert 'kind == "resume"' in add_src
    assert 'kind == "halted"' not in add_src
    assert "halted_add" in add_src
    assert "{% if halted_add|default(false) %}data-halted-add{% endif %}" in add_src
    assert "{% if expired_add|default(false) %}data-expired-add{% endif %}" in add_src
    assert add_src.count('class="pg-sheet-panel"') == 1
    for text in (wrapper, add_src):
        assert 'data-halted-add="desktop"' not in text
        assert "data-halted-add-desktop" not in text
        assert "data-halted-add-phone" not in text
        assert "halted-add-" not in text
        assert "plus-add-" not in text
        assert "expired-add-" not in text
        assert 'kind == "halted"' not in text
    assert "resume_cta_label" in add_src
    assert "resume_cta_href" in add_src
    resume_branch = add_src.split('{% elif kind == "resume" %}', 1)[1].split(
        '{% elif kind == "device_blocked" %}', 1
    )[0]
    halted_branch = resume_branch.split("{% if halted_add|default(false) %}", 1)[1].split(
        "{% elif expired_add|default(false) %}", 1
    )[0]
    assert "state.primary_label" not in halted_branch
    assert '<a class="pg-add-primary" href="{{ resume_cta_href }}">{{ resume_cta_label }}</a>' in halted_branch
    assert LIVE_HEADING not in add_src
    assert LIVE_HEADING not in wrapper
    assert LIVE_CTA not in halted_branch
    assert "Payment retries have stopped" not in halted_branch
    assert 'method="post"' not in halted_branch
    assert "data-pg-add-confirm" not in halted_branch
    assert 'name="scope"' not in halted_branch
    assert '<a class="pg-add-secondary" href="{{ cancel_href }}" data-pg-sheet-close>Cancel</a>' in resume_branch
    assert 'method="post"' not in resume_branch
    assert "Resume Playground" in resume_branch.split("{% else %}", 1)[1]
    routes = ROUTES.read_text(encoding="utf-8")
    ctx = routes.split("def _add_page_context", 1)[1].split("def _rollover_ids", 1)[0]
    assert "request_is_halted_subscriber" in ctx
    assert "request_is_expired_subscriber" in ctx
    assert "BLOCK_PAYMENT_HALTED" in ctx
    assert "gate_view" in ctx
    assert "halted_add" in ctx
    assert "resume_cta_label" in ctx
    assert 'kind = "resume"' in ctx
    assert "def law_membership" not in ctx
    assert 'kind == "halted"' not in ctx
    assert "def request_is_halted_subscriber" in DEPS.read_text(encoding="utf-8")
    view = VIEW.read_text(encoding="utf-8")
    assert 'KIND_RESUME = "resume"' in view
    assert 'kind == "halted"' not in view
    js = PG_JS.read_text(encoding="utf-8")
    assert "function enhanceSheets" in js
    assert "[data-pg-sheet]" in js
    assert "data-pg-sheet-direct" in js
    assert "data-pg-sheet-return" in js
    css = PG_CSS.read_text(encoding="utf-8")
    assert "Add sheet (M2)" in css
    assert ".pg-add-primary" in css
    assert ".pg-add-secondary" in css
    assert "[data-halted-add-desktop]" not in css
    assert "[data-expired-add-desktop]" not in css
    assert "data-halted-add" not in css
    assert "playground.css?v=pg50" in BASE.read_text(encoding="utf-8")
    assert "playground.js?v=pg9" in BASE.read_text(encoding="utf-8")
    assert "data-halted-add" not in MOBILE.read_text(encoding="utf-8")


def test_plus_expired_and_halted_01_04_untouched() -> None:
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-halted-landing="desktop"' in landing
    assert "data-halted-add" not in landing
    browse = BROWSE.read_text(encoding="utf-8")
    assert 'data-halted-browse="desktop"' in browse
    assert "data-halted-add" not in browse
    laws = LAWS.read_text(encoding="utf-8")
    assert 'data-halted-laws="desktop"' in laws
    assert "data-halted-add" not in laws
    bare = BARE.read_text(encoding="utf-8")
    assert "{% if halted_bareact|default(false) %}data-halted-bareact{% endif %}" in bare
    assert "data-halted-add" not in bare
    add = ADD.read_text(encoding="utf-8")
    panel = ADD_PANEL.read_text(encoding="utf-8")
    assert '{% include "partials/playground_add_panel.html" %}' in add
    assert "{% if expired_add|default(false) %}data-expired-add{% endif %}" in panel
    assert "data-pg-add-confirm" in panel
    for text in (add, panel):
        assert 'data-plus-add="desktop"' not in text
        assert 'data-expired-add="desktop"' not in text
    assert 'data-plus-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-expired-playground="desktop"' in HOME.read_text(encoding="utf-8")
    for path in (LANDING, BROWSE, LAWS, BARE, HOME, GATE, MANAGE, DASH, CAL, PROFILE, SETTINGS):
        text = path.read_text(encoding="utf-8")
        assert "data-halted-add" not in text
        assert "halted_add" not in text


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


def test_halted_phone_add_uses_resume_not_confirm(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_then_halt(client)
    html = unescape(client.get(add_path("ndps")).text)
    phone = _sheet(html)
    assert LIVE_HEADING in phone
    assert LIVE_CTA in phone
    assert PLAYGROUND_BILLING_PATH in phone
    assert 'href="/laws/ndps"' in phone
    assert "data-pg-add-confirm" not in phone
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
              const panels = document.querySelectorAll('[data-pg-add]');
              const panel = panels[0] || null;
              const cancel = panel && panel.querySelector('.pg-add-secondary[data-pg-sheet-close]');
              const primary = panel && panel.querySelector('.pg-add-primary');
              return {
                open: Boolean(dialog && dialog.open),
                panels: panels.length,
                kind: panel && panel.getAttribute('data-pg-kind'),
                halted: Boolean(panel && panel.hasAttribute('data-halted-add')),
                panelDisplay: panel ? getComputedStyle(panel).display : null,
                title: panel && panel.querySelector('h1') &&
                  panel.querySelector('h1').textContent.trim(),
                primaryText: primary && primary.textContent.trim(),
                primaryHref: primary && primary.getAttribute('href'),
                cancelHref: cancel && cancel.getAttribute('href'),
                confirmForm: Boolean(panel && panel.querySelector('[data-pg-add-confirm]')),
              };
            }"""
        )
        browser.close()
    # One panel on the phone (M2 §2.1), raised as the sheet, same copy and CTA.
    assert geo["open"] is True
    assert geo["panels"] == 1
    assert geo["kind"] == "resume"
    assert geo["halted"] is True
    assert geo["panelDisplay"] != "none"
    assert geo["title"] == LIVE_HEADING
    assert geo["primaryText"] == LIVE_CTA
    assert geo["primaryHref"] == PLAYGROUND_BILLING_PATH
    assert geo["cancelHref"] == "/laws/ndps"
    assert geo["confirmForm"] is False


def test_halted_add_screen05_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_then_halt(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_add_screen05_1280.png"
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
        page.wait_for_selector("[data-pg-add][data-halted-add]", timeout=8000)
        geo = page.evaluate(
            """() => {
              const dialog = document.querySelector('dialog.pg-sheet');
              const panels = document.querySelectorAll('[data-pg-add]');
              const panel = panels[0] || null;
              const resume = panel && panel.querySelector('.pg-add-primary');
              const cancel = panel && panel.querySelector('.pg-add-secondary[data-pg-sheet-close]');
              const closeBtn = panel && panel.querySelector('[data-pg-sheet-close].pg-sheet-close');
              const haltedBare = document.querySelector('section.ActHead[data-halted-bareact]');
              const cluster = document.querySelector('.ActHead-inpg');
              const titleEl = panel && panel.querySelector('.pg-add-title');
              const ledeEl = panel && panel.querySelector('.pg-add-lede');
              const confirmForm = panel && panel.querySelector('[data-pg-add-confirm]');
              const scope = panel && panel.querySelector("[data-add-step='scope']");
              return {
                open: Boolean(dialog && dialog.open),
                panels: panels.length,
                kind: panel && panel.getAttribute('data-pg-kind'),
                haltedAdd: Boolean(panel && panel.hasAttribute('data-halted-add')),
                plus: Boolean(panel && panel.hasAttribute('data-plus-add')),
                expired: Boolean(panel && panel.hasAttribute('data-expired-add')),
                panelDisplay: panel ? getComputedStyle(panel).display : null,
                eyebrow: Boolean(panel && panel.querySelector('.pg-eyebrow')),
                title: titleEl && titleEl.textContent.trim(),
                lede: ledeEl && ledeEl.textContent.trim(),
                resumeText: resume && resume.textContent.trim(),
                resumeHref: resume && resume.getAttribute('href'),
                cancelText: cancel && cancel.textContent.trim(),
                cancelHref: cancel && cancel.getAttribute('href'),
                hasClose: Boolean(closeBtn),
                closeLabel: closeBtn && closeBtn.getAttribute('aria-label'),
                background: Boolean(haltedBare),
                already: Boolean(cluster && cluster.innerText.includes('Already in Playground')),
                header: document.querySelector('.account-menu-btn-status') &&
                  document.querySelector('.account-menu-btn-status').textContent.trim(),
                actTitle: haltedBare && haltedBare.querySelector('.ActHead-title') &&
                  haltedBare.querySelector('.ActHead-title').textContent.trim(),
                confirmForm: Boolean(confirmForm),
                scope: Boolean(scope),
                path: location.pathname,
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
                head: Boolean(document.querySelector('section.ActHead[data-halted-bareact]')),
              };
            }"""
        )
        browser.close()

    assert geo["open"] is True
    assert geo["panels"] == 1
    assert geo["kind"] == "resume"
    assert geo["haltedAdd"] is True
    assert geo["plus"] is False
    assert geo["expired"] is False
    assert geo["panelDisplay"] != "none"
    assert geo["eyebrow"] is False
    assert geo["title"] == LIVE_HEADING
    assert geo["lede"] == LIVE_COPY[0]
    assert geo["resumeText"] == LIVE_CTA
    assert geo["resumeText"] != "Continue"
    assert geo["resumeText"] != "Add to Playground"
    assert geo["resumeHref"] == PLAYGROUND_BILLING_PATH
    # One markup on both widths: Cancel is the sheet's own link back to the Act.
    assert geo["cancelText"] == "Cancel"
    assert geo["cancelHref"] == "/laws/ndps"
    assert geo["hasClose"] is True
    assert geo["closeLabel"] == "Close"
    assert geo["background"] is True
    assert geo["already"] is True
    assert geo["header"] == LIVE_HEADING
    assert geo["actTitle"] == NDPS_TITLE
    assert geo["confirmForm"] is False
    assert geo["scope"] is False
    assert geo["path"] == "/laws/ndps"
    assert closed["open"] is False
    assert closed["path"] == "/laws/ndps"
    assert closed["head"] is True
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_halted_add_plus_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client, status="active")
    session = client.cookies.get(SESSION_COOKIE_NAME)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_add_screen05_plus_regression_1280.png"
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
        page.locator('section.ActHead[data-plus-bareact] [data-pg-sheet]').click()
        page.wait_for_selector("[data-pg-add][data-pg-kind='eligible_to_add']", timeout=8000)
        geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const confirmStep = panel && panel.querySelector("[data-add-step='confirm']");
              const title = confirmStep && confirmStep.querySelector('.pg-add-title');
              const submit = confirmStep && confirmStep.querySelector('[data-pg-add-confirm] .pg-add-primary');
              return {
                kind: panel && panel.getAttribute('data-pg-kind'),
                plusHead: Boolean(document.querySelector('section.ActHead[data-plus-bareact]')),
                haltedAttr: Boolean(panel && panel.hasAttribute('data-halted-add')),
                haltedHead: Boolean(document.querySelector('section.ActHead[data-halted-bareact]')),
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
    assert geo["haltedAttr"] is False
    assert geo["haltedHead"] is False
    assert geo["title"] == "Add to Playground"
    assert geo["submit"] == "Add to Playground"
    assert geo["confirm"] is True
    assert geo["header"] == "RecallC Plus"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
