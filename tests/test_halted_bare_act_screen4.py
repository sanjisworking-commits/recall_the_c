"""Halted cohort desktop NDPS Bare Act Screen 04 (CTA map halted/04-screen).

Authorized: ChatGPT. Authenticated multiuser GET /laws/ndps after a real
Plus subscription is halted with NDPS retained in the roster. Reading stays
available. Retained presentation is already_active; the primary CTA is the
Halted recovery action from gate_view(BLOCK_PAYMENT_HALTED), not Continue.
Guest, Free, Plus, Expired, paused, pending, Pro/Max, phone, Plus 01–11,
Expired 01–11, and Halted 01–03 stay unchanged. No new route.

M2: the Bare Act page is one generated head (`section.ActHead`, both widths)
for every Act and every viewer; the per-surface desktop/phone twins and the
NDPS fixture are gone. The halted state is unchanged — retained law →
"Already in Playground" chip with Sections + the halted recovery CTA, no Add,
no learn hrefs — only the markup these tests read changed.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.entitlements.models import (
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
)
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.urls import add_path, home_path, law_path, sections_path
from constitution_memorizer.playground.view import PLAYGROUND_BILLING_PATH, gate_view
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act

NDPS = get_bare_act("ndps")
assert NDPS is not None
NDPS_TITLE = NDPS.title
NDPS_META = NDPS.head_meta_label
NDPS_KICKER = "Bare Act · India Code"

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "data" / "output" / "learning_units.json"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
APP = ROOT / "src/constitution_memorizer/web/app.py"
BARE_PAGE = ROOT / "src/constitution_memorizer/web/bare_act_page.py"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
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
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_HALTED_GATE = gate_view(reason=BLOCK_PAYMENT_HALTED)
LIVE_HALTED_STATUS = LIVE_HALTED_GATE.title
LIVE_HALTED_CTA = LIVE_HALTED_GATE.cta_label
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


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _head(html: str) -> str:
    """The one generated Act head (M2): `section.ActHead` through its list."""
    return html.split('class="panel ActHead', 1)[1].split("</section>", 1)[0]


def _band(html: str) -> str:
    """The head band only: back link, kicker, title, meta, CTA, About."""
    return _head(html).split("data-bareact-accordion", 1)[0]


def _flat(markup: str) -> str:
    """Collapse the template's multi-line tags so attribute runs match."""
    return re.sub(r"\s+", " ", markup).replace(" >", ">")


def _chapter_rows(head: str) -> list[str]:
    return head.split('<summary class="bareact-chapter-row"')[1:]


def _chapter_names(head: str) -> list[str]:
    return [
        row.split('<span class="bareact-chapter-name">', 1)[1].split("</span>", 1)[0]
        for row in _chapter_rows(head)
    ]


def _facts(client: TestClient) -> dict:
    snap = client.app.state.entitlement_service.resolve(USER)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    cap = roster.peek_capacity(USER, snap)
    eng = client.app.state.engine.for_user(USER)
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    history = tuple(
        sorted(
            (row.id, row.status, row.tier, row.is_current)
            for row in client.app.state.subscriptions.list_subscription_history(USER)
        )
    )
    service = getattr(client.app.state, "device_service", None)
    if service is None:
        devices = ()
    else:
        devices = tuple(
            sorted((d.id, d.revoked_at, d.device_key_hash) for d in service.list_devices(USER))
        )
    return {
        "active": tuple(sorted(i.law_id for i in roster.active_roster_items(USER))),
        "removed": tuple(sorted(i.law_id for i in roster.removed_roster_items(USER))),
        "used": cap.used,
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        ),
        "selection": tuple(
            sorted(s.source_locator for s in overlay.list_selection(USER, "ndps"))
        ),
        "progress": tuple(
            sorted(
                (p.source_locator, p.status, p.times_completed, p.next_revision)
                for p in overlay.list_progress(USER, "ndps")
            )
        ),
        "constitution": tuple(
            sorted(
                (
                    row.learning_unit_id,
                    row.status,
                    row.times_completed,
                    str(row.next_revision),
                    row.interval_days,
                )
                for row in eng.repo.list_all_progress(USER)
            )
        ),
        "claimed": tuple(sorted(eng.claimed_articles())),
        "subscription": None
        if stored is None
        else (
            stored.id,
            stored.status,
            stored.tier,
            stored.is_current,
            stored.billing_period_end,
        ),
        "history": history,
        "devices": devices,
        "entitlement": (
            snap.subscription_status,
            snap.playground_block_reason,
            snap.can_open_playground,
        ),
    }


def test_halted_retained_ndps_uses_lifecycle_cta_not_continue(tmp_path: Path) -> None:
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
    assert LIVE_HALTED_STATUS == "Payment retries have stopped"
    assert LIVE_HALTED_CTA == "Manage subscription"
    assert PLAYGROUND_BILLING_PATH == "/billing/subscriptions"
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps")

    before = _facts(client)
    page = client.get("/laws/ndps")
    assert page.status_code == 200
    html = page.text
    header = _header(html)
    desk = _head(html)
    band = _band(html)
    # One head, both widths (M2 §2.1): the halted marker is a bare attribute
    # on the single `section.ActHead`; no twins, no other cohort marker.
    assert html.count('class="panel ActHead') == 1
    assert html.count('data-act-head="ndps"') == 1
    assert "data-halted-bareact" in desk
    assert "data-plus-bareact" not in html
    assert "data-expired-bareact" not in html
    assert "data-bareact-phone" not in html
    assert "data-signed-in-bareact-desktop" not in html
    assert "data-guest-bareact-desktop" not in html
    assert 'data-pg-kind="guest"' not in html
    assert f">{NDPS_KICKER}<" in band
    assert f'<h1 class="ActHead-title">{NDPS_TITLE}</h1>' in band
    assert f'<p class="ActHead-meta">{NDPS_META}</p>' in band
    assert 'class="ActHead-back" href="/laws"' in band
    assert "Already in Playground" in band
    assert 'data-pg-kind="already_active"' in band
    assert 'data-membership="in_playground"' in band
    assert 'class="ActHead-inpg"' in band
    assert ">Sections<" in band
    assert f'class="ActHead-inpg-sections" href="{sections_path("ndps")}"' in band
    assert f'class="ActHead-inpg-continue" href="{PLAYGROUND_BILLING_PATH}"' in band
    assert f">{LIVE_HALTED_CTA}<" in band
    assert f'class="ActHead-inpg-continue" href="{home_path()}"' not in band
    assert 'href="/playground">Continue</a>' not in band
    assert ">Continue<" not in band
    assert ">Start learning<" not in band
    assert ">Resume Playground<" not in band
    assert "+ Add to Playground" not in desk
    assert "Add to this month" not in desk
    assert "Add back" not in desk
    assert "Subscribe to use Playground" not in desk
    assert "Sign in to use Playground" not in desk
    assert 'data-pg-kind="eligible_to_add"' not in desk
    assert 'class="ActHead-btn' not in desk
    assert add_path("ndps") not in desk
    assert "/playground/laws/ndps/learn" not in desk
    assert "/learn" not in desk
    assert "data-pg-sheet" not in desk
    assert "<dialog" not in html
    assert LIVE_HALTED_STATUS in header
    assert LIVE_EXPIRED_STATUS not in header
    assert "Free account" not in header
    assert "RecallC Plus" not in header
    assert "Sanjay" in header
    assert 'href="/browse"' in header
    assert "is-active" in header
    for phrase in INVENTED:
        assert phrase not in desk, phrase
    # The list is generated from the live Act model (M2 §4 Q1): eight NDPS
    # chapter rows, every one a closed <summary>, plus its Schedule row.
    rows = _chapter_rows(desk)
    assert len(rows) == NDPS.chapter_count == 8
    assert _chapter_names(desk) == [c.title for c in NDPS.chapters]
    assert all('aria-expanded="false"' in row for row in rows)
    assert "<details class=\"bareact-chapter\" open" not in desk
    assert desk.count('<div class="bareact-schedule-row') == len(NDPS.schedules) == 1
    assert "data-bareact-tabs" not in desk
    assert "This Act has no Schedules." not in desk
    # Chapter rows expand into their section links (M2 §4 Q3): every section
    # href is a reader link, none is a Playground learn link.
    section_hrefs = [
        chunk.split('"', 1)[0]
        for chunk in desk.split('<a class="bareact-section-row" href="')[1:]
    ]
    assert section_hrefs
    assert all(h.startswith("/laws/ndps/section/") for h in section_hrefs)
    workspace = client.get(law_path("ndps"))
    assert workspace.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAYMENT_HALTED}"' in workspace.text
    assert 'data-pg-learn-panel="cloze"' not in workspace.text
    assert f">{LIVE_HALTED_CTA}<" in workspace.text
    sections = client.get(sections_path("ndps"))
    assert sections.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAYMENT_HALTED}"' in sections.text
    assert "data-pg-picker" not in sections.text
    assert 'data-pg-learn-panel="cloze"' not in sections.text
    chapter = client.get("/laws/ndps/section/8")
    assert chapter.status_code == 200
    assert _facts(client) == before
    again = client.get("/laws/ndps")
    assert again.status_code == 200
    assert _facts(client) == before
    bns = client.get("/laws/bns")
    assert bns.status_code == 200
    assert _facts(client) == before


def test_halted_elapsed_period_stays_halted_on_bareact(tmp_path: Path) -> None:
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
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps")
    html = client.get("/laws/ndps").text
    header = _header(html)
    desk = _band(html)
    assert "data-halted-bareact" in _head(html)
    assert "data-expired-bareact" not in html
    assert "data-plus-bareact" not in html
    assert LIVE_HALTED_STATUS in header
    assert LIVE_EXPIRED_STATUS not in header
    assert "Free account" not in header
    assert "Already in Playground" in desk
    assert 'class="ActHead-inpg"' in desk
    assert f'class="ActHead-inpg-continue" href="{PLAYGROUND_BILLING_PATH}"' in desk
    assert f">{LIVE_HALTED_CTA}<" in desk
    assert ">Continue<" not in desk
    assert ">Resume Playground<" not in desk


def test_never_added_halted_law_has_recovery_not_retained_cluster(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_then_halt(client)
    bns_html = client.get("/laws/bns").text
    bns = _band(bns_html)
    # M2: the halted marker is on every Act's head for a halted viewer, not
    # only NDPS; the never-added law still gets the recovery button, not the
    # retained chip.
    assert "data-halted-bareact" in _head(bns_html)
    assert 'data-act-head="bns"' in bns_html
    assert "Already in Playground" not in bns
    assert 'data-pg-kind="already_active"' not in bns
    assert 'class="ActHead-inpg"' not in bns
    assert 'class="ActHead-inpg-continue"' not in bns
    assert "+ Add to Playground" not in bns
    assert 'data-pg-kind="eligible_to_add"' not in bns
    assert 'data-pg-kind="resume"' in bns
    assert (
        f'<a class="ActHead-btn" href="{PLAYGROUND_BILLING_PATH}" data-pg-kind="resume">{LIVE_HALTED_CTA}</a>'
        in _flat(bns)
    )
    assert add_path("bns") not in bns
    assert "data-pg-sheet" not in bns
    assert "/learn" not in bns

    fresh = TestClient(_mu_app(tmp_path / "none"))
    _sign_in(fresh)
    _subscribe(fresh, status="halted")
    ndps = fresh.get("/laws/ndps").text
    desk = _band(ndps)
    assert "data-halted-bareact" in _head(ndps)
    assert "Already in Playground" not in desk
    assert 'class="ActHead-inpg"' not in desk
    assert 'class="ActHead-inpg-continue"' not in desk
    assert ">Continue<" not in desk
    assert "+ Add to Playground" not in desk
    assert 'data-pg-kind="already_active"' not in desk
    assert 'data-pg-kind="eligible_to_add"' not in desk
    assert "Subscribe to use Playground" not in desk
    assert 'data-pg-kind="resume"' in desk
    assert (
        f'<a class="ActHead-btn" href="{PLAYGROUND_BILLING_PATH}" data-pg-kind="resume">{LIVE_HALTED_CTA}</a>'
        in _flat(desk)
    )
    assert "data-pg-sheet" not in desk


def test_guest_free_plus_expired_paused_pending_pro_max_are_not_halted_bareact(
    tmp_path: Path,
) -> None:
    guest_html = TestClient(_mu_app(tmp_path / "guest")).get("/laws/ndps").text
    assert "data-halted-bareact" not in guest_html
    assert 'data-pg-kind="guest"' in _band(guest_html)
    assert "Sign in to use Playground" in _band(guest_html)

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/laws/ndps").text
    assert "data-halted-bareact" not in free_html
    free_desk = _band(free_html)
    assert 'data-pg-kind="subscribe"' in free_desk
    assert "Subscribe to use Playground" in free_desk
    assert "Free account" in _header(free_html)
    assert LIVE_HALTED_STATUS not in _header(free_html)

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus, status="active")
    added = _confirm_add(plus, "ndps")
    assert added.status_code in {200, 303}
    plus_html = plus.get("/laws/ndps").text
    assert "data-plus-bareact" in _head(plus_html)
    assert "data-halted-bareact" not in plus_html
    plus_desk = _band(plus_html)
    assert "Already in Playground" in plus_desk
    assert 'class="ActHead-inpg"' in plus_desk
    # M2-F04: the chip's actions are the live state's own, not a hard-coded
    # "/playground" Continue.
    continue_href = plus_desk.split('class="ActHead-inpg-continue" href="', 1)[1].split('"', 1)[0]
    continue_label = plus_desk.split('class="ActHead-inpg-continue" href="', 1)[1].split(">", 1)[1].split("<", 1)[0]
    assert continue_href.startswith("/playground")
    assert continue_href != PLAYGROUND_BILLING_PATH
    assert continue_label in {"Continue", "Start learning"}
    assert LIVE_HALTED_CTA not in plus_desk
    assert "RecallC Plus" in _header(plus_html)
    assert LIVE_HALTED_STATUS not in _header(plus_html)

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
    expired_html = expired.get("/laws/ndps").text
    assert "data-expired-bareact" in _head(expired_html)
    assert "data-halted-bareact" not in expired_html
    expired_desk = _band(expired_html)
    assert "Already in Playground" in expired_desk
    assert 'class="ActHead-inpg"' in expired_desk
    assert ">Resume Playground<" in expired_desk
    assert f'class="ActHead-inpg-continue" href="{PLAYGROUND_BILLING_PATH}"' in expired_desk
    assert LIVE_HALTED_CTA not in expired_desk
    assert LIVE_EXPIRED_STATUS in _header(expired_html)
    assert LIVE_HALTED_STATUS not in _header(expired_html)

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused, status="paused")
    assert "data-halted-bareact" not in paused.get("/laws/ndps").text

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    assert "data-halted-bareact" not in pending.get("/laws/ndps").text

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro", status="active")
    assert "data-halted-bareact" not in pro.get("/laws/ndps").text

    mx = TestClient(_mu_app(tmp_path / "max"))
    _sign_in(mx)
    _subscribe(mx, tier="max", status="active")
    assert "data-halted-bareact" not in mx.get("/laws/ndps").text


def test_halted_bareact_uses_shared_predicate() -> None:
    bare = BARE.read_text(encoding="utf-8")
    assert "plus_bareact" in bare
    assert "expired_bareact" in bare
    assert "halted_bareact" in bare
    assert "{% if halted_bareact|default(false) %}data-halted-bareact{% endif %}" in bare
    assert 'data-halted-bareact="desktop"' not in bare
    assert "data-signed-in-bareact-desktop" not in bare
    assert "data-bareact-phone" not in bare
    assert "signed-bareact-" not in bare
    assert "guest-bareact-" not in bare
    assert "pg.kind == 'already_active'" in bare
    assert "pg.primary_label" in bare
    assert "pg.primary_href" in bare
    # M2-F04: the chip's Continue is the live state's destination.
    assert 'href="/playground">Continue</a>' not in bare
    assert (
        '<a class="ActHead-inpg-continue" href="{{ pg.primary_href }}">{{ pg.primary_label }}</a>'
        in bare
    )
    assert '<a class="ActHead-inpg-sections" href="{{ pg.secondary_href }}">{{ pg.secondary_label }}</a>' in bare
    assert ">Continue<" not in bare
    assert "Resume Playground" not in bare
    assert LIVE_HALTED_STATUS not in bare
    assert LIVE_HALTED_CTA not in bare
    assert "Payment retries have stopped" not in bare
    assert "Manage subscription" not in bare
    for phrase in INVENTED:
        assert phrase not in bare, phrase
    base = BASE.read_text(encoding="utf-8")
    assert "halted_bareact" in base
    assert "halted_header_status" in base
    assert "path == '/laws/ndps'" in base
    assert LIVE_HALTED_STATUS not in base
    app = APP.read_text(encoding="utf-8")
    page = app.split("async def law_detail_page", 1)[1].split(
        "async def bare_act_section_page", 1
    )[0]
    # M2: the Laws route hands the head context to one shared builder; the
    # halted predicate and presentation live in web/bare_act_page.py.
    assert "bare_act_page_context(request, bare)" in page
    assert "def snapshot_is_halted_subscriber" not in page
    assert "halted_law_presentation" in app
    assert "def _halted_law_presentation" not in app
    assert "def _halted_laws_index_states" in app
    bare_page = BARE_PAGE.read_text(encoding="utf-8")
    assert "def halted_law_presentation" in bare_page
    assert "def bare_act_page_context" in bare_page
    assert "request_is_halted_subscriber" in bare_page
    assert "request_is_expired_subscriber" in bare_page
    assert "request_is_active_plus" in bare_page
    assert '"halted_bareact": halted_bareact' in bare_page
    assert '"halted_header_status": halted_header_status' in bare_page
    assert "halted_law_presentation(" in bare_page.split("def bare_act_page_context", 1)[1]
    assert "BLOCK_PAYMENT_HALTED" in bare_page
    assert "gate_view" in bare_page
    assert "def snapshot_is_halted_subscriber" not in bare_page
    assert LIVE_HALTED_STATUS not in bare_page
    assert LIVE_HALTED_CTA not in bare_page
    assert "data-halted-bareact" not in PG_CSS.read_text(encoding="utf-8")
    assert "data-halted-bareact" not in STYLES.read_text(encoding="utf-8")
    assert "data-halted-bareact" not in MOBILE.read_text(encoding="utf-8")
    assert "Bare Act head (M2)" in STYLES.read_text(encoding="utf-8")
    assert "playground.css?v=pg51" in BASE.read_text(encoding="utf-8")
    assert "styles.css?v=main88" in BASE.read_text(encoding="utf-8")
    assert "def request_is_halted_subscriber" in DEPS.read_text(encoding="utf-8")


def test_plus_expired_and_halted_01_02_03_untouched() -> None:
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-halted-landing="desktop"' in landing
    assert "data-halted-bareact" not in landing
    browse = BROWSE.read_text(encoding="utf-8")
    assert 'data-halted-browse="desktop"' in browse
    assert "data-halted-bareact" not in browse
    laws = LAWS.read_text(encoding="utf-8")
    assert 'data-halted-laws="desktop"' in laws
    assert "data-halted-bareact" not in laws
    bare = BARE.read_text(encoding="utf-8")
    assert "{% if plus_bareact|default(false) %}data-plus-bareact{% endif %}" in bare
    assert "{% if expired_bareact|default(false) %}data-expired-bareact{% endif %}" in bare
    # The one sheet panel lives in its partial; playground_add.html only
    # wraps it (dialog over the Act, or bare for the in-page fetch).
    add = ADD.read_text(encoding="utf-8")
    panel = ADD_PANEL.read_text(encoding="utf-8")
    assert '{% include "partials/playground_add_panel.html" %}' in add
    assert "{% if expired_add|default(false) %}data-expired-add{% endif %}" in panel
    assert "{% if halted_add|default(false) %}data-halted-add{% endif %}" in panel
    assert "data-pg-add-confirm" in panel
    for text in (add, panel):
        assert 'data-plus-add="desktop"' not in text
        assert 'data-expired-add="desktop"' not in text
        assert "data-halted-bareact" not in text
        assert "halted_bareact" not in text
    assert 'data-plus-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-expired-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-plus-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-expired-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-expired-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-plus-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-expired-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-plus-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-expired-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    assert 'data-expired-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    for path in (ADD, HOME, GATE, MANAGE, DASH, CAL, PROFILE, SETTINGS):
        text = path.read_text(encoding="utf-8")
        assert "data-halted-bareact" not in text
        assert "halted_bareact" not in text


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


def test_halted_phone_bareact_unchanged(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_then_halt(client)
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
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        phone = page.evaluate(
            """() => {
              const heads = document.querySelectorAll('section.ActHead');
              const head = document.querySelector('section.ActHead[data-halted-bareact]');
              const list = head && head.querySelector('[data-act-list]');
              const cont = head && head.querySelector('.ActHead-inpg-continue');
              return {
                headCount: heads.length,
                haltedPresent: Boolean(head),
                headDisplay: head ? getComputedStyle(head).display : null,
                listDisplay: list ? getComputedStyle(list).display : null,
                details: list ? list.querySelectorAll('details.bareact-chapter').length : 0,
                openDetails: list ? list.querySelectorAll('details.bareact-chapter[open]').length : 0,
                continueText: cont && cont.textContent.trim(),
                continueHref: cont && cont.getAttribute('href'),
              };
            }"""
        )
        browser.close()
    # One head on the phone too (M2 §2.1): no hidden desktop twin, the same
    # halted chip, the generated chapter rows closed (M2 §4 Q1).
    assert phone["headCount"] == 1
    assert phone["haltedPresent"] is True
    assert phone["headDisplay"] != "none"
    assert phone["listDisplay"] != "none"
    assert phone["details"] == NDPS.chapter_count
    assert phone["openDetails"] == 0
    assert phone["continueText"] == LIVE_HALTED_CTA
    assert phone["continueHref"] == PLAYGROUND_BILLING_PATH


def test_halted_bareact_1280(tmp_path: Path) -> None:
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
    shot_path = artifact_dir / "halted_bareact_screen04_1280.png"
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
        geo = page.evaluate(
            """() => {
              const desk = document.querySelector('section.ActHead');
              const halted = document.querySelector('section.ActHead[data-halted-bareact]');
              const plus = document.querySelector('section.ActHead[data-plus-bareact]');
              const expired = document.querySelector('section.ActHead[data-expired-bareact]');
              const guest = document.querySelector('section.ActHead[data-pg-kind="guest"]');
              const brand = document.querySelector('.brand');
              const mark = document.querySelector('.brand-mark');
              const back = desk && desk.querySelector('.ActHead-back');
              const cluster = desk && desk.querySelector('.ActHead-inpg');
              const sections = desk && desk.querySelector('.ActHead-inpg-sections');
              const cont = desk && desk.querySelector('.ActHead-inpg-continue');
              const rows = desk ? [...desk.querySelectorAll('summary.bareact-chapter-row')] : [];
              const schedules = desk ? desk.querySelectorAll('.bareact-schedule-row').length : 0;
              const panelText = desk ? desk.innerText : '';
              return {
                headCount: document.querySelectorAll('section.ActHead').length,
                present: Boolean(halted),
                plusPresent: Boolean(plus),
                expiredPresent: Boolean(expired),
                deskDisplay: desk && getComputedStyle(desk).display,
                guestPresent: !!guest,
                brandHref: brand.getAttribute('href'),
                markFilter: getComputedStyle(mark).filter,
                backHref: back && back.getAttribute('href'),
                kicker: desk && desk.querySelector('.ActHead-kicker').textContent.trim(),
                title: desk && desk.querySelector('.ActHead-title').textContent.trim(),
                meta: desk && desk.querySelector('.ActHead-meta').textContent.trim(),
                already: panelText.includes('Already in Playground'),
                clusterPresent: !!cluster,
                sectionsHref: sections && sections.getAttribute('href'),
                sectionsText: sections && sections.textContent.trim(),
                continueHref: cont && cont.getAttribute('href'),
                continueText: cont && cont.textContent.trim(),
                addShown: /Add to Playground/.test(panelText),
                subscribe: panelText.includes('Subscribe to use Playground'),
                signIn: panelText.includes('Sign in to use Playground'),
                invented: /Your subscription expired|Resume subscription|Your payment failed|Fix your payment|Subscription halted|Playground unavailable|Free plan|Unlock all/.test(panelText),
                rowCount: rows.length,
                rowTitles: rows.map((el) =>
                  el.querySelector('.bareact-chapter-name').textContent.trim()
                ),
                scheduleCount: schedules,
                accountName: document.querySelector('.account-menu-btn-name').textContent.trim(),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                navLabels: [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                  (el) => el.textContent.replace(/\\s+/g, ' ').trim()
                ),
                browseActive: document.querySelector('.PrimaryTabs--top .nav-link.is-active')
                  .textContent.replace(/\\s+/g, ' ').trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["headCount"] == 1
    assert geo["present"] is True
    assert geo["plusPresent"] is False
    assert geo["expiredPresent"] is False
    assert geo["deskDisplay"] != "none"
    assert geo["guestPresent"] is False
    assert geo["brandHref"] == "/dashboard"
    assert "invert" in geo["markFilter"]
    assert geo["backHref"] == "/laws"
    assert geo["kicker"] == NDPS_KICKER
    assert geo["title"] == NDPS_TITLE
    assert geo["meta"] == NDPS_META
    assert geo["already"] is True
    assert geo["clusterPresent"] is True
    assert geo["sectionsText"] == "Sections"
    assert geo["sectionsHref"] == sections_path("ndps")
    assert geo["continueText"] == LIVE_HALTED_CTA
    assert geo["continueHref"] == PLAYGROUND_BILLING_PATH
    assert geo["continueText"] != "Continue"
    assert geo["addShown"] is False
    assert geo["subscribe"] is False
    assert geo["signIn"] is False
    assert geo["invented"] is False
    assert geo["rowCount"] == NDPS.chapter_count == 8
    assert geo["rowTitles"] == [c.title for c in NDPS.chapters]
    assert geo["scheduleCount"] == len(NDPS.schedules) == 1
    assert geo["accountName"] == "Sanjay"
    assert geo["accountStatus"] == LIVE_HALTED_STATUS
    assert geo["navLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["browseActive"] == "Browse"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_halted_bareact_plus_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client, status="active")
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_bareact_screen04_plus_regression_1280.png"
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
        geo = page.evaluate(
            """() => {
              const halted = document.querySelector('section.ActHead[data-halted-bareact]');
              const plus = document.querySelector('section.ActHead[data-plus-bareact]');
              const expired = document.querySelector('section.ActHead[data-expired-bareact]');
              const desk = document.querySelector('section.ActHead');
              const cluster = desk && desk.querySelector('.ActHead-inpg');
              const sections = desk && desk.querySelector('.ActHead-inpg-sections');
              const cont = desk && desk.querySelector('.ActHead-inpg-continue');
              return {
                haltedPresent: Boolean(halted),
                plusPresent: Boolean(plus),
                expiredPresent: Boolean(expired),
                already: desk && desk.innerText.includes('Already in Playground'),
                clusterPresent: !!cluster,
                sectionsHref: sections && sections.getAttribute('href'),
                continueHref: cont && cont.getAttribute('href'),
                continueText: cont && cont.textContent.trim(),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                title: desk && desk.querySelector('.ActHead-title').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["haltedPresent"] is False
    assert geo["plusPresent"] is True
    assert geo["expiredPresent"] is False
    assert geo["already"] is True
    assert geo["clusterPresent"] is True
    assert geo["sectionsHref"] == sections_path("ndps")
    # M2-F04: the live state's destination, never the billing page.
    assert geo["continueHref"].startswith("/playground")
    assert geo["continueHref"] != PLAYGROUND_BILLING_PATH
    assert geo["continueText"] in {"Continue", "Start learning"}
    assert geo["continueText"] != LIVE_HALTED_CTA
    assert geo["accountStatus"] == "RecallC Plus"
    assert geo["title"] == NDPS_TITLE
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
