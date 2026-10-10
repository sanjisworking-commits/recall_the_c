"""Halted cohort desktop /dashboard Today Screen 08 (CTA map halted/08-screen).

Authorized: ChatGPT. Authenticated multiuser GET /dashboard after a real Plus
subscription is halted. Overlay on the live Today model: Constitution keeps
POST /revision/start; retained Playground rows stay in live merge order with
Manage subscription from gate_view(BLOCK_PAYMENT_HALTED) even when elapsed.
Guest, Free, Plus Screen 08, Expired Screen 08, paused, pending, Pro/Max,
phone, Plus 01–11, Expired 01–11, and Halted 01–07 stay unchanged. No new
route. No /resume. No Halted 09.
"""

from __future__ import annotations

import re
import socket
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from html import unescape
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
from constitution_memorizer.playground.urls import sections_path
from constitution_memorizer.playground.view import PLAYGROUND_BILLING_PATH, gate_view
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.service import REVISION_KIND, user_today
from tests.test_playground_m8 import _seed_progress
from tests.test_roster_m5a import _confirm_add, _csrf

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
MANAGE = ROOT / "src/constitution_memorizer/web/templates/subscription_manage.html"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
AUTH = ROOT / "src/constitution_memorizer/auth/routes.py"
SCHEDULE = ROOT / "src/constitution_memorizer/playground/schedule.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_GATE = gate_view(reason=BLOCK_PAYMENT_HALTED)
LIVE_HEADING = LIVE_GATE.title
LIVE_CTA = LIVE_GATE.cta_label
LIVE_EXPIRED = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
LOCATOR = "ndps:section:8:clause:a"
INVENTED = (
    "Your plan expired",
    "Resume subscription",
    "Resume Playground",
    "Your Playground is paused",
    "View Playground plans",
    "Premium",
    "Unlock all",
    "Locked",
    "Subscription required",
    "4-day streak",
    "Good morning.",
    "Reviewed this morning",
    "Steady plan",
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


def _halt(client: TestClient) -> None:
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None
    client.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )


def _engine(client: TestClient) -> ReminderEngine:
    return client.app.state.engine.for_user(USER)


def _pin_playground_today(monkeypatch: pytest.MonkeyPatch, day: date) -> None:
    monkeypatch.setattr(
        "constitution_memorizer.playground.roster.period.playground_today",
        lambda now=None: day,
    )
    monkeypatch.setattr(
        "constitution_memorizer.playground.schedule.playground_today",
        lambda now=None: day,
    )


def _make_due(client: TestClient, unit_ids: list[str], *, as_of: date | None = None) -> None:
    eng = _engine(client)
    today = as_of or user_today(eng)
    for offset, unit_id in enumerate(unit_ids):
        eng.repo.upsert_progress(
            eng.user_id,
            unit_id=unit_id,
            status="review",
            times_completed=1,
            last_completed=today - timedelta(days=1),
            next_revision=today - timedelta(days=len(unit_ids) - offset),
            interval_days=1,
        )
    eng._invalidate_progress_cache()


def _seed_ndps_mixed(client: TestClient, *, day: date) -> None:
    assert _confirm_add(client, "ndps").status_code == 303
    posted = client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "unit": LOCATOR, "section": "1"},
        follow_redirects=False,
    )
    assert posted.status_code in {200, 303}
    _seed_progress(
        client.app.state.playground,
        USER,
        "ndps",
        LOCATOR,
        status="review",
        interval_days=1,
        next_revision=day.isoformat(),
        times_completed=1,
        learned_at=day.isoformat(),
    )


def _seed_canonical(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    streak_days: int = 3,
) -> date:
    eng = _engine(client)
    day = user_today(eng)
    _pin_playground_today(monkeypatch, day)
    _make_due(client, ["clause-1", "clause-2"], as_of=day)
    session = eng.create_study_session(
        session_id=uuid.uuid4().hex,
        kind=REVISION_KIND,
        plan_date=day,
        unit_ids=["clause-1", "clause-2"],
    )
    eng.set_study_item_status(
        session_id=session.id, unit_id="clause-1", status="completed"
    )
    for offset in range(streak_days):
        eng.record_daily_goal_met(day - timedelta(days=offset))
    _seed_ndps_mixed(client, day=day)
    return day


def _plus_then_halt(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, *, streak_days: int = 3
) -> date:
    _subscribe(client)
    day = _seed_canonical(client, monkeypatch, streak_days=streak_days)
    _halt(client)
    return day


def _header(html: str) -> str:
    return html.split("<header", 1)[-1].split("</header>", 1)[0]


def _path_nodes(html: str) -> list[str]:
    return re.findall(
        r'<li class="rc-path-node[^"]*"[^>]*>.*?</li>',
        html,
        re.S,
    )


def _current_node(html: str) -> str:
    match = re.search(
        r'<li class="rc-path-node is-current"[^>]*>.*?</li>',
        html,
        re.S,
    )
    assert match, "no current path node"
    return match.group(0)


def _hero(html: str) -> str:
    return html.split('data-today-mode="revision"', 1)[1].split("dash-path-card", 1)[0]


def _assert_noncurrent_playground_new_meta_once(html: str) -> None:
    found = False
    for node in _path_nodes(html):
        open_tag = node.split(">", 1)[0]
        if 'data-today-source="playground"' not in open_tag:
            continue
        if "is-current" in open_tag:
            continue
        if "New · Playground" not in node:
            continue
        found = True
        assert node.count("New · Playground") == 1, node
        meta = re.search(r'<span class="rc-path-meta">([^<]*)</span>', node)
        assert meta, node
        assert meta.group(1).strip() == "New · Playground"
        sub = re.search(r'<span class="rc-path-sub">([^<]*)</span>', node)
        assert sub is None or sub.group(1).strip() != "New · Playground"
        assert "rc-path-cta" not in node
        assert "/playground/laws" not in node
        assert "/learn/" not in node
    assert found, "no non-current Playground New row"


def _facts(client: TestClient) -> dict:
    snap = client.app.state.entitlement_service.resolve(USER)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    cap = roster.peek_capacity(USER, snap)
    eng = _engine(client)
    stored = client.app.state.subscriptions.get_current_subscription(USER)
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
        "subscription": None
        if stored is None
        else (
            stored.id,
            stored.status,
            stored.tier,
            stored.is_current,
            stored.billing_period_end,
        ),
    }


def test_halted_today_reaches_dashboard_with_today_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_halt(client, monkeypatch)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.subscription_status == "halted"
    assert snap.playground_block_reason == BLOCK_PAYMENT_HALTED
    page = client.get("/dashboard")
    assert page.status_code == 200
    html = unescape(page.text)
    header = _header(html)
    assert 'data-halted-today="desktop"' in html
    assert 'data-plus-today="desktop"' not in html
    assert 'data-expired-today="desktop"' not in html
    assert "data-signed-in-today" in html
    assert 'href="/dashboard" class="nav-link is-active"' in header
    assert ">Today<" in header
    assert LIVE_HEADING in header
    assert LIVE_EXPIRED not in header
    assert "RecallC Plus" not in header
    assert "Free account" not in header
    assert "Welcome, Sanjay." in html or "Good morning, Sanjay." in html


def test_halted_today_canonical_mixed_path_uses_live_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    day = _plus_then_halt(client, monkeypatch, streak_days=3)
    html = unescape(client.get("/dashboard").text)
    assert 'data-today-mode="revision"' in html
    assert 'data-daily-goal-streak="3"' in html
    assert re.search(
        r'class="rc-streak-count">3</span>\s*<span class="rc-streak-suffix">-day streak</span>',
        html,
    )
    assert "4-day streak" not in html
    assert f"{day.strftime('%A')} {day.day} {day.strftime('%B')}" in html
    assert "revisions due" in html or "revision due" in html
    nodes = _path_nodes(html)
    assert len(nodes) >= 3
    sources = re.findall(r'data-today-source="([^"]+)"', "".join(nodes))
    statuses = re.findall(r'class="rc-path-node is-([^"]+)"', "".join(nodes))
    assert "done" in statuses
    assert "current" in statuses
    assert "upcoming" in statuses
    assert "playground" in sources
    assert "constitution" in sources
    assert sources == [
        re.search(r'data-today-source="([^"]+)"', node).group(1) for node in nodes
    ]
    assert sources.index("playground") == statuses.index("current")
    current = _current_node(html)
    assert 'data-today-source="playground"' in current
    assert "Day 1 → 3 · Playground" in current
    cta = re.search(r'<a class="rc-path-cta" href="([^"]+)">([^<]+)', current)
    assert cta, current
    assert unescape(cta.group(1)) == PLAYGROUND_BILLING_PATH
    assert cta.group(2).strip() == LIVE_CTA
    assert "/playground/" not in unescape(cta.group(1))
    assert "/learn/" not in unescape(cta.group(1))
    constitution = [n for n in nodes if 'data-today-source="constitution"' in n]
    assert constitution
    for node in constitution:
        assert PLAYGROUND_BILLING_PATH not in node
        assert LIVE_CTA not in node
        if "is-current" not in node:
            assert "rc-path-cta" not in node
    assert html.find("data-today-unit") < html.find('data-today-source="playground"')
    assert "New · Playground" in html
    _assert_noncurrent_playground_new_meta_once(html)
    assert "Section 8" in html
    assert "Article 20(1)" in html
    for phrase in INVENTED:
        assert phrase not in html, phrase


def test_halted_today_noncurrent_playground_metadata_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_halt(client, monkeypatch)
    html = unescape(client.get("/dashboard").text)
    _assert_noncurrent_playground_new_meta_once(html)


def test_halted_today_constitution_hero_keeps_revision_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_halt(client, monkeypatch)
    html = unescape(client.get("/dashboard").text)
    assert 'data-today-mode="revision"' in html
    hero = _hero(html)
    assert 'action="/revision/start"' in hero
    assert "data-today-hero-cta" not in hero
    assert "Continue revision" in hero or "Start revision" in hero
    assert PLAYGROUND_BILLING_PATH not in hero
    frac = re.search(r'class="rc-goal-frac">(\d+)/(\d+)</span>', html)
    assert frac, html
    done, total = int(frac.group(1)), int(frac.group(2))
    assert done >= 1
    assert total >= done
    count = re.search(r'class="dash-due-count">(\d+)</span>', html)
    assert count
    assert int(count.group(1)) >= 1
    remaining = re.search(r"Continue revision · (\d+) left", hero)
    if remaining:
        left = int(remaining.group(1))
        assert left >= 1
        assert left <= int(count.group(1))


def test_halted_today_playground_cta_cannot_reach_learning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_halt(client, monkeypatch)
    html = unescape(client.get("/dashboard").text)
    current = _current_node(html)
    assert 'data-today-source="playground"' in current
    cta = re.search(r'<a class="rc-path-cta" href="([^"]+)">([^<]+)', current)
    assert cta
    assert unescape(cta.group(1)) == PLAYGROUND_BILLING_PATH
    assert cta.group(2).strip() == LIVE_CTA
    assert "/playground/laws" not in current
    billing = client.get(PLAYGROUND_BILLING_PATH, follow_redirects=False)
    assert billing.status_code == 200
    assert 'data-halted-subscription="desktop"' in billing.text
    picker = client.get(sections_path("ndps"), follow_redirects=False)
    assert picker.status_code in {200, 303, 403}
    if picker.status_code == 200:
        text = unescape(picker.text)
        assert "Choose what to learn" not in text
        assert "data-pg-picker" not in picker.text
        assert f'data-playground-gate="{BLOCK_PAYMENT_HALTED}"' in picker.text
    learn = client.get(
        "/playground/laws/ndps/sections/8/u/clause:a/learn/read?revision=1",
        follow_redirects=False,
    )
    assert learn.status_code in {200, 303, 403}
    if learn.status_code == 200:
        body = unescape(learn.text)
        assert "data-pg-workspace" not in learn.text
        assert (
            f'data-playground-gate="{BLOCK_PAYMENT_HALTED}"' in learn.text
            or LIVE_HEADING in body
        )
        assert "Resume Playground" not in body
    elif learn.status_code == 303:
        location = learn.headers.get("location") or ""
        assert "/learn/" not in location
        assert "revision=1" not in location


def test_halted_today_interactions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_halt(client, monkeypatch)
    html = unescape(client.get("/dashboard").text)
    hero = _hero(html)
    assert 'action="/revision/start"' in hero
    started = client.post("/revision/start", follow_redirects=False)
    assert started.status_code == 303
    location = started.headers.get("location") or ""
    assert location.startswith("/learn/")
    assert PLAYGROUND_BILLING_PATH not in location
    assert "/playground/" not in location
    current = _current_node(html)
    cta = re.search(r'<a class="rc-path-cta" href="([^"]+)"', current)
    assert cta
    playground_href = unescape(cta.group(1))
    assert playground_href == PLAYGROUND_BILLING_PATH
    billing = client.get(playground_href)
    assert billing.status_code == 200
    assert 'data-halted-subscription="desktop"' in billing.text
    home = client.get("/playground")
    assert home.status_code == 200
    assert 'data-halted-playground="desktop"' in home.text
    settings = client.get("/settings")
    assert settings.status_code == 200
    profile = client.get("/profile")
    assert profile.status_code == 200


def test_halted_today_get_is_mutation_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_halt(client, monkeypatch)
    before = _facts(client)
    assert "ndps" in before["active"]
    assert before["selection"]
    assert before["constitution"]
    assert before["subscription"] is not None
    assert before["subscription"][1] == "halted"
    page = client.get("/dashboard")
    assert page.status_code == 200
    after = _facts(client)
    assert after == before
    again = client.get("/dashboard")
    assert again.status_code == 200
    assert _facts(client) == before


def test_halted_elapsed_period_stays_halted_on_today(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_halt(client, monkeypatch)
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
    html = unescape(client.get("/dashboard").text)
    header = _header(html)
    assert 'data-halted-today="desktop"' in html
    assert 'data-expired-today="desktop"' not in html
    assert 'data-plus-today="desktop"' not in html
    assert LIVE_HEADING in header
    assert LIVE_EXPIRED not in header
    current = _current_node(html)
    assert 'data-today-source="playground"' in current
    cta = re.search(r'<a class="rc-path-cta" href="([^"]+)">([^<]+)', current)
    assert cta
    assert unescape(cta.group(1)) == PLAYGROUND_BILLING_PATH
    assert cta.group(2).strip() == LIVE_CTA
    assert "Resume Playground" not in current
    assert LIVE_EXPIRED not in html
    assert "Resume Playground" not in html
    hero = _hero(html)
    assert 'action="/revision/start"' in hero


def test_guest_free_plus_expired_paused_pending_are_not_halted_today(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest")).get("/dashboard").text
    assert 'data-halted-today="desktop"' not in guest
    assert LIVE_HEADING not in _header(guest)
    assert "data-signed-in-today" not in guest

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/dashboard").text
    assert 'data-halted-today="desktop"' not in free_html
    assert "data-signed-in-today" in free_html
    assert LIVE_HEADING not in _header(free_html)
    assert 'data-today-source="playground"' not in free_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    _seed_canonical(plus, monkeypatch)
    plus_html = unescape(plus.get("/dashboard").text)
    assert 'data-plus-today="desktop"' in plus_html
    assert 'data-halted-today="desktop"' not in plus_html
    assert 'data-expired-today="desktop"' not in plus_html
    assert "RecallC Plus" in _header(plus_html)
    assert LIVE_HEADING not in _header(plus_html)
    current = _current_node(plus_html)
    assert 'data-today-source="playground"' in current
    href = re.search(r'<a class="rc-path-cta" href="([^"]+)"', current)
    assert href
    assert "/playground/" in unescape(href.group(1))
    hero = _hero(plus_html)
    assert "data-today-hero-cta" in hero
    assert 'action="/revision/start"' not in hero
    assert "New · Playground" in plus_html
    _assert_noncurrent_playground_new_meta_once(plus_html)

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(expired)
    _seed_canonical(expired, monkeypatch)
    stored_e = expired.app.state.subscriptions.get_current_subscription(USER)
    expired.app.state.subscriptions.update_subscription_state(
        USER,
        stored_e.id,
        status="expired",
        billing_period_start=EXPIRED_START,
        billing_period_end=EXPIRED_END,
    )
    expired_html = unescape(expired.get("/dashboard").text)
    assert 'data-expired-today="desktop"' in expired_html
    assert 'data-halted-today="desktop"' not in expired_html
    assert LIVE_EXPIRED in _header(expired_html)
    assert LIVE_HEADING not in _header(expired_html)
    expired_current = _current_node(expired_html)
    expired_cta = re.search(
        r'<a class="rc-path-cta" href="([^"]+)">([^<]+)', expired_current
    )
    assert expired_cta
    assert expired_cta.group(2).strip() != LIVE_CTA
    assert LIVE_HEADING not in expired_current

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused)
    _seed_canonical(paused, monkeypatch)
    stored_p = paused.app.state.subscriptions.get_current_subscription(USER)
    paused.app.state.subscriptions.update_subscription_state(
        USER, stored_p.id, status="paused"
    )
    paused_html = paused.get("/dashboard").text
    assert 'data-halted-today="desktop"' not in paused_html
    assert 'data-today-source="playground"' not in paused_html

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    pending_html = pending.get("/dashboard").text
    assert 'data-halted-today="desktop"' not in pending_html
    assert LIVE_HEADING not in _header(pending_html)

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/dashboard").text
    assert 'data-halted-today="desktop"' not in pro_html
    assert LIVE_HEADING not in _header(pro_html)

    mx = TestClient(_mu_app(tmp_path / "max"))
    _sign_in(mx)
    _subscribe(mx, tier="max")
    mx_html = mx.get("/dashboard").text
    assert 'data-halted-today="desktop"' not in mx_html
    assert LIVE_HEADING not in _header(mx_html)


def test_halted_today_marker_uses_shared_predicate() -> None:
    dash = DASH.read_text(encoding="utf-8")
    assert "halted_today" in dash
    assert 'data-halted-today="desktop"' in dash
    assert 'data-plus-today="desktop"' in dash
    assert 'data-expired-today="desktop"' in dash
    assert "data-signed-in-today" in dash
    assert 'action="/revision/start"' in dash
    assert PLAYGROUND_BILLING_PATH not in dash
    assert "Resume Playground" not in dash
    assert "Manage subscription" not in dash
    assert "Payment retries have stopped" not in dash
    assert "/resume" not in dash
    assert "ndps" not in dash
    auth = AUTH.read_text(encoding="utf-8")
    dashboard = auth.split("async def dashboard", 1)[1].split(
        "async def profile_get", 1
    )[0]
    assert "request_is_halted_subscriber" in dashboard
    assert "request_is_expired_subscriber" in dashboard
    assert "request_is_active_plus" in dashboard
    assert "BLOCK_PAYMENT_HALTED" in dashboard
    assert 'ctx["plus_today"] = plus_today' in dashboard
    assert 'ctx["halted_today"] = halted_today' in dashboard
    assert 'ctx["expired_today"] = expired_today' in dashboard
    assert "reconcile_halted_playground_today" in dashboard
    assert "reconcile_expired_playground_today" in dashboard
    assert "apply_expired_today_hero" in dashboard
    assert "/resume" not in dashboard
    assert "ndps" not in dashboard
    assert "def request_is_halted_subscriber" in DEPS.read_text(encoding="utf-8")
    assert 'snapshot.subscription_status == "halted"' in DEPS.read_text(encoding="utf-8")
    schedule = SCHEDULE.read_text(encoding="utf-8")
    assert "request_is_halted_subscriber" in schedule
    assert "request_is_expired_subscriber" in schedule
    assert "halted_playground_today_action" in schedule
    assert "reconcile_halted_playground_today" in schedule
    halted_action = schedule.split("def halted_playground_today_action", 1)[1].split(
        "def _stamp_playground_today_action", 1
    )[0]
    assert "BLOCK_PAYMENT_HALTED" in halted_action
    assert "playground_subscription_card" not in halted_action
    assert "gate_view" in halted_action
    base = BASE.read_text(encoding="utf-8")
    assert "halted_today_chrome" in base
    assert "plus_today_chrome" in base
    assert "expired_today_chrome" in base
    assert LIVE_HEADING not in base
    assert "playground.css?v=pg43" in base
    css = PG_CSS.read_text(encoding="utf-8")
    assert 'data-halted-today="desktop"' in css
    assert "halted/08-screen" in css
    assert 'data-expired-today="desktop"' in css
    assert "expired/08-screen" in css
    assert 'data-plus-today="desktop"' in css
    halted_css = css.split("halted/08-screen", 1)[1].split("plus/09-screen", 1)[0]
    assert "var(--pg-teal)" in halted_css
    assert "#0e7569" not in halted_css
    for phrase in INVENTED:
        assert phrase not in dash, phrase


def test_plus_expired_and_halted_01_07_untouched() -> None:
    assert 'data-halted-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-halted-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-halted-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-halted-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-halted-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-halted-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-halted-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-expired-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-plus-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-expired-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-plus-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-expired-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    assert 'data-expired-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    for path in (
        LANDING,
        BROWSE,
        LAWS,
        BARE,
        ADD,
        HOME,
        MANAGE,
        CAL,
        PROFILE,
        SETTINGS,
        GATE,
    ):
        text = path.read_text(encoding="utf-8")
        assert "data-halted-today" not in text
        assert "halted_today" not in text
    mobile = MOBILE.read_text(encoding="utf-8")
    generic, _, phone_free = mobile.partition("is signedIn/04-screen:")
    assert "data-halted-today" not in generic
    phone_block = phone_free.split("/* R1 — Playground phone shell", 1)[0]
    assert ":not([data-halted-today])" in phone_block
    assert 'data-halted-today="desktop"' not in phone_block
    phone_cta = generic.split(
        'body[data-mscreen="today"] .rc-path-node.is-current .rc-path-cta {', 1
    )[1].split("}", 1)[0]
    assert "width: 100%" in phone_cta
    assert "min-height: 44px" in phone_cta


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


def test_halted_phone_today_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _plus_then_halt(client, monkeypatch)
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
        page.goto(f"{origin}/dashboard", wait_until="networkidle")
        geo = page.evaluate(
            """() => {
              const marker = document.querySelector('[data-halted-today="desktop"]');
              const panel = document.querySelector('.dashboard-panel');
              const dateEl = document.querySelector('[data-today-date]');
              const cta = document.querySelector('.rc-path-node.is-current .rc-path-cta');
              const ctaStyle = cta && getComputedStyle(cta);
              const ctaBox = cta && cta.getBoundingClientRect();
              return {
                marker: Boolean(marker),
                panelDisplay: panel && getComputedStyle(panel).display,
                today: document.body.getAttribute('data-mscreen'),
                dateDisplay: dateEl && getComputedStyle(dateEl).display,
                ctaWidth: ctaBox && ctaBox.width,
                ctaMinHeight: ctaStyle && ctaStyle.minHeight,
                plus: Boolean(document.querySelector('[data-plus-today="desktop"]')),
                expired: Boolean(document.querySelector('[data-expired-today="desktop"]')),
              };
            }"""
        )
        browser.close()
    assert geo["marker"] is True
    assert geo["panelDisplay"] != "none"
    assert geo["today"] == "today"
    assert geo["plus"] is False
    assert geo["expired"] is False
    assert geo["dateDisplay"] == "none"
    assert (geo["ctaWidth"] or 0) > 0
    assert str(geo["ctaMinHeight"] or "").endswith("px")
    assert float(str(geo["ctaMinHeight"]).replace("px", "") or 0) >= 44


def test_halted_today_screen08_1280(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _plus_then_halt(client, monkeypatch, streak_days=3)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_today_screen08_1280.png"
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
        page.goto(f"{origin}/dashboard", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const halted = document.querySelector('[data-halted-today="desktop"]');
              const plus = document.querySelector('[data-plus-today="desktop"]');
              const expired = document.querySelector('[data-expired-today="desktop"]');
              const greeting = document.querySelector('.dash-hello');
              const streak = document.querySelector('.rc-streak');
              const hero = document.querySelector('[data-today-mode="revision"]');
              const form = document.querySelector('[data-today-mode="revision"] form.dash-revision-form');
              const path = document.querySelector('[data-today-path-card]');
              const current = document.querySelector('.rc-path-node.is-current');
              const status = document.querySelector('.account-menu-btn-status');
              const nodes = [...document.querySelectorAll('.rc-path-node')];
              const first = hero && hero.getBoundingClientRect();
              const pathBox = path && path.getBoundingClientRect();
              const cta = current && current.querySelector('.rc-path-cta');
              return {
                present: Boolean(halted),
                plus: Boolean(plus),
                expired: Boolean(expired),
                greeting: greeting && greeting.textContent.trim(),
                streak: streak && streak.innerText.replace(/\\s+/g, ' ').trim(),
                streakDisplay: streak && getComputedStyle(streak).display,
                revision: Boolean(hero),
                formAction: form && form.getAttribute('action'),
                path: Boolean(path),
                twoCol: Boolean(first && pathBox && Math.abs(first.y - pathBox.y) < 80 && pathBox.x > first.x),
                currentSource: current && current.getAttribute('data-today-source'),
                currentHref: (cta && cta.getAttribute('href')) || '',
                currentLabel: (cta && cta.textContent.trim()) || '',
                sources: nodes.map((el) => el.getAttribute('data-today-source')),
                statuses: nodes.map((el) => [...el.classList].find((c) => c.startsWith('is-'))),
                status: status && status.textContent.trim(),
                statusDisplay: status && getComputedStyle(status).display,
                navActive: document.querySelector('.PrimaryTabs--top .nav-link.is-active')
                  && document.querySelector('.PrimaryTabs--top .nav-link.is-active').textContent.replace(/\\s+/g, ' ').trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        context.close()
        browser.close()
    assert geo["present"] is True
    assert geo["plus"] is False
    assert geo["expired"] is False
    assert geo["greeting"] == "Good morning, Sanjay."
    assert geo["streakDisplay"] != "none"
    assert "streak" in (geo["streak"] or "").lower()
    assert geo["revision"] is True
    assert geo["formAction"] == "/revision/start"
    assert geo["path"] is True
    assert geo["twoCol"] is True
    assert geo["currentSource"] == "playground"
    assert geo["currentHref"] == PLAYGROUND_BILLING_PATH
    assert geo["currentLabel"] == LIVE_CTA
    assert "playground" in (geo["sources"] or [])
    assert "constitution" in (geo["sources"] or [])
    assert geo["status"] == LIVE_HEADING
    assert geo["statusDisplay"] != "none"
    assert "Today" in (geo["navActive"] or "")
    assert shot_path.exists() and shot_path.stat().st_size > 1000


def test_halted_today_plus_regression_1280(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    _seed_canonical(client, monkeypatch, streak_days=3)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_today_screen08_plus_regression_1280.png"
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
        page.goto(f"{origin}/dashboard", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-today="desktop"]');
              const halted = document.querySelector('[data-halted-today="desktop"]');
              const expired = document.querySelector('[data-expired-today="desktop"]');
              const current = document.querySelector('.rc-path-node.is-current');
              const cta = current && current.querySelector('.rc-path-cta');
              const status = document.querySelector('.account-menu-btn-status');
              const heroCta = document.querySelector('[data-today-hero-cta]');
              return {
                plus: Boolean(plus),
                halted: Boolean(halted),
                expired: Boolean(expired),
                currentSource: current && current.getAttribute('data-today-source'),
                currentHref: (cta && (cta.href || cta.getAttribute('href'))) || '',
                status: status && status.textContent.trim(),
                heroHref: (heroCta && (heroCta.href || heroCta.getAttribute('href'))) || '',
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        context.close()
        browser.close()
    assert geo["plus"] is True
    assert geo["halted"] is False
    assert geo["expired"] is False
    assert geo["currentSource"] == "playground"
    assert "/playground/" in (geo["currentHref"] or "")
    assert "/playground/" in (geo["heroHref"] or "")
    assert geo["status"] == "RecallC Plus"
    assert shot_path.exists() and shot_path.stat().st_size > 1000
