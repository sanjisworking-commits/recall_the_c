"""Phone Expired Today Screen 04 (CTA map expired/04-screen).

Authorized: ChatGPT. Authenticated expired GET /dashboard at 390x844.
Desktop Expired Screen 08 is the functional contract. Constitution keeps
POST /revision/start when Constitution review remains; Playground current
CTA is live Resume Playground → billing. First-run is a real empty
architecture. Map Learn / Sunday 6 September / streak 6 are presentation
losses. Guest, Free signedIn 04, Plus 04, Halted, Pro, Expired 01–03,
and desktop 08 stay unchanged.
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
from constitution_memorizer.playground.urls import sections_path
from constitution_memorizer.playground.view import (
    PLAYGROUND_BILLING_PATH,
    gate_view,
    playground_subscription_card,
)
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.service import REVISION_KIND, user_today
from tests.test_playground_m8 import _seed_progress
from tests.test_roster_m5a import _confirm_add, _csrf

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
AUTH = ROOT / "src/constitution_memorizer/auth/routes.py"
SCHEDULE = ROOT / "src/constitution_memorizer/playground/schedule.py"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_GATE = gate_view(reason=BLOCK_PAID_PERIOD_ENDED)
LIVE_HEADING = LIVE_GATE.title
LOCATOR = "ndps:section:8:clause:a"
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
)
TEMPLATE_INVENTED = (
    "Your plan expired",
    "Resume subscription",
    "Premium",
    "Unlock all",
    "Locked",
    "Subscription required",
    "4-day streak",
    "Good morning.",
    "Reviewed this morning",
    "Steady plan",
    "Resume Playground",
    "View Playground plans",
)
RENDER_INVENTED = (
    "Your plan expired",
    "Resume subscription",
    "Premium",
    "Unlock all",
    "Locked",
    "Subscription required",
    "4-day streak",
    "6-day streak",
    "Good morning.",
    "Reviewed this morning",
    "Steady plan",
    "Sunday 6 September",
    "Article 19(1)(a)",
    "Article 21",
    "You’re on the Free plan",
    "You're on the Free plan",
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


def _expired_client(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    _expire(client)
    return client


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


def _make_due(
    client: TestClient,
    unit_ids: list[str],
    *,
    as_of: date | None = None,
    interval_days: dict[str, int] | None = None,
) -> None:
    eng = _engine(client)
    today = as_of or user_today(eng)
    intervals = interval_days or {}
    for offset, unit_id in enumerate(unit_ids):
        eng.repo.upsert_progress(
            eng.user_id,
            unit_id=unit_id,
            status="review",
            times_completed=1,
            last_completed=today - timedelta(days=1),
            next_revision=today - timedelta(days=len(unit_ids) - offset),
            interval_days=intervals.get(unit_id, 1),
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


def _plus_then_expire(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, *, streak_days: int = 3
) -> date:
    _subscribe(client)
    day = _seed_canonical(client, monkeypatch, streak_days=streak_days)
    _expire(client)
    return day


def _tabs(html: str) -> str:
    return html.split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 1
    )[1].split("</nav>", 1)[0]


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


def _revision_hero(html: str) -> str:
    if 'data-today-mode="revision"' not in html:
        return ""
    return html.split('data-today-mode="revision"', 1)[1].split(
        "dash-path-card", 1
    )[0]


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
    assert found, "no non-current Playground New row"


def _live_playground_action(client: TestClient) -> tuple[str, str]:
    snap = client.app.state.entitlement_service.resolve(USER)
    card = playground_subscription_card(snap)
    gate = gate_view(reason=str(snap.playground_block_reason or BLOCK_PAID_PERIOD_ENDED))
    label = (card.cta_label if card.show else "") or gate.cta_label
    href = (card.cta_href if card.show else "") or gate.cta_href
    return label, href


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


def _assert_no_invented(html: str) -> None:
    text = unescape(html)
    today = date.today()
    for phrase in RENDER_INVENTED:
        if phrase == "Sunday 6 September" and today == date(2026, 9, 6):
            continue
        assert phrase not in text, phrase
    assert "Article 19(1)(a)" not in text
    assert re.search(r"(^|[^A-Za-z0-9])Section 9([^0-9]|$)", text) is None


def _assert_generic_today_tabs(html: str) -> None:
    tabs = _tabs(html)
    for label_text, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        assert label_text in tabs
    assert 'aria-current="page"' in tabs
    assert ">Today<" in tabs
    assert "data-expired-today-phone-tabs" not in html
    assert "data-expired-bareact-phone-tabs" not in html
    assert "data-plus-today-phone-tabs" not in html


def test_phone_expired_today_firstrun_has_no_invented_dues(tmp_path: Path) -> None:
    client = _expired_client(tmp_path)
    before = _facts(client)
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert _facts(client) == before
    html = unescape(page.text)
    assert 'data-expired-today="desktop"' in html
    assert "data-signed-in-today" in html
    assert 'data-plus-today="desktop"' not in html
    assert 'data-today-mode="firstrun"' in html
    assert "Welcome, Sanjay." in html
    today = user_today(_engine(client))
    label = f"{today.strftime('%A')} {today.day} {today.strftime('%B')}"
    assert label in html
    assert "Nothing due today" in html
    assert "Learn your first Article" in html
    assert 'href="/browse"' in html
    assert "/revision/start" not in html
    assert 'data-today-source="playground"' not in html
    assert "Section 8" not in html
    assert "NDPS" not in html
    assert "lapse-banner" not in html
    assert 'class="dash-avatar-link" href="/settings"' in html
    assert ">S</span>" in html
    assert 'class="mobile-icon-btn dash-greeting-settings" href="/settings"' in html
    _assert_no_invented(html)
    _assert_generic_today_tabs(html)
    assert "data-theme-pref" not in html.split("<header", 1)[1].split("</header>", 1)[0]


def test_phone_expired_today_canonical_mixed_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    day = _plus_then_expire(client, monkeypatch, streak_days=3)
    before = _facts(client)
    html = unescape(client.get("/dashboard").text)
    assert _facts(client) == before
    assert 'data-expired-today="desktop"' in html
    assert 'data-today-mode="revision"' in html
    assert "Good morning, Sanjay." in html
    assert f"{day.strftime('%A')} {day.day} {day.strftime('%B')}" in html
    assert 'data-daily-goal-streak="3"' in html
    assert "4-day streak" not in html
    assert "6-day streak" not in html
    frac = re.search(r'class="rc-goal-frac">(\d+)/(\d+)</span>', html)
    assert frac, html
    assert (frac.group(1), frac.group(2)) == ("1", "3")
    count = re.search(r'class="dash-due-count">(\d+)</span>', html)
    assert count and count.group(1) == "2"
    hero = _revision_hero(html)
    assert 'action="/revision/start"' in hero
    assert "data-today-hero-cta" not in hero
    assert "Continue revision" in hero or "Start revision" in hero
    assert PLAYGROUND_BILLING_PATH not in hero
    nodes = _path_nodes(html)
    assert len(nodes) >= 4
    sources = re.findall(r'data-today-source="([^"]+)"', "".join(nodes))
    statuses = re.findall(r'class="rc-path-node is-([^"]+)"', "".join(nodes))
    titles = re.findall(r'class="rc-path-title">([^<]+)', "".join(nodes))
    assert sources[0] == "constitution"
    assert statuses[0] == "done"
    assert "Article 20(1)" in titles[0]
    assert "Day 1 revision" in nodes[0]
    current = _current_node(html)
    assert 'data-today-source="playground"' in current
    assert 'data-today-kind="review"' in current
    assert "Section 8" in current
    assert "Day 1 → 3 · Playground" in current
    label, href = _live_playground_action(client)
    cta = re.search(r'<a class="rc-path-cta" href="([^"]+)">([^<]+)', current)
    assert cta
    assert unescape(cta.group(1)) == href == PLAYGROUND_BILLING_PATH
    assert cta.group(2).strip() == label
    assert "/playground/" not in unescape(cta.group(1))
    assert "Learn" not in cta.group(2)
    assert "Start revision" not in cta.group(2)
    assert "Continue" not in cta.group(2)
    assert "Article 20(3)" in "".join(titles)
    assert "New · Playground" in html
    _assert_noncurrent_playground_new_meta_once(html)
    constitution = [n for n in nodes if 'data-today-source="constitution"' in n]
    assert constitution
    for node in constitution:
        assert "/billing/subscriptions" not in node
        assert label not in node
        if "is-current" not in node:
            assert "rc-path-cta" not in node
    assert "Section 9" not in html
    assert "Article 19(1)(a)" not in html
    assert "Article 21" not in html
    _assert_no_invented(html)
    _assert_generic_today_tabs(html)
    assert ">S</span>" in html
    assert 'class="dash-avatar-link" href="/settings"' in html


def test_phone_expired_today_constitution_only_keeps_revision_start(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    _make_due(
        client,
        ["clause-1", "clause-2"],
        interval_days={"clause-1": 15, "clause-2": 1},
    )
    _expire(client)
    html = unescape(client.get("/dashboard").text)
    assert 'data-today-mode="revision"' in html
    assert 'action="/revision/start"' in html
    assert "data-revision-start" in html
    hero = _revision_hero(html)
    assert "data-today-hero-cta" not in hero
    assert PLAYGROUND_BILLING_PATH not in hero
    assert 'data-today-source="playground"' not in html
    current = _current_node(html)
    assert 'data-today-source="constitution"' in current
    assert "Article 20(1)" in current
    assert "Day 15 revision" in "".join(_path_nodes(html))
    assert "Day 15 → 30" not in html
    cta = re.search(r'<a class="rc-path-cta" href="([^"]+)">([^<]+)', current)
    assert cta
    assert "/learn/" in unescape(cta.group(1))
    assert PLAYGROUND_BILLING_PATH not in unescape(cta.group(1))
    assert cta.group(2).strip() == "Start revision →"
    started = client.post("/revision/start", follow_redirects=False)
    assert started.status_code == 303
    location = started.headers.get("location") or ""
    assert location.startswith("/learn/")
    assert PLAYGROUND_BILLING_PATH not in location
    _assert_no_invented(html)


def test_phone_expired_today_playground_only_hero_is_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    day = user_today(_engine(client))
    _pin_playground_today(monkeypatch, day)
    _seed_ndps_mixed(client, day=day)
    _expire(client)
    html = unescape(client.get("/dashboard").text)
    assert 'data-today-mode="revision"' in html
    assert 'data-today-mode="firstrun"' not in html
    hero = _revision_hero(html)
    label, href = _live_playground_action(client)
    assert "data-today-hero-cta" in hero
    assert 'action="/revision/start"' not in hero
    hero_cta = re.search(
        r'<a class="btn dash-btn-full" href="([^"]+)"[^>]*data-today-hero-cta>([^<]+)',
        hero,
    )
    assert hero_cta, hero
    assert unescape(hero_cta.group(1)) == href == PLAYGROUND_BILLING_PATH
    assert hero_cta.group(2).strip() == label
    current = _current_node(html)
    assert 'data-today-source="playground"' in current
    cta = re.search(r'<a class="rc-path-cta" href="([^"]+)">([^<]+)', current)
    assert cta
    assert unescape(cta.group(1)) == href
    assert cta.group(2).strip() == label
    assert "Learn" not in cta.group(2)
    _assert_no_invented(html)


def test_phone_expired_today_enrolled_without_sections_has_no_playground_row(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    assert _confirm_add(client, "ndps").status_code == 303
    _expire(client)
    html = unescape(client.get("/dashboard").text)
    assert 'data-today-source="playground"' not in html
    assert 'data-today-mode="firstrun"' in html
    assert "Learn your first Article" in html
    assert "Section 8" not in html
    _assert_no_invented(html)


def test_phone_expired_today_selected_unstarted_is_resume_not_learn(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    assert _confirm_add(client, "ndps").status_code == 303
    posted = client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "section": "8"},
        follow_redirects=False,
    )
    assert posted.status_code in {200, 303}
    _expire(client)
    html = unescape(client.get("/dashboard").text)
    assert 'data-today-mode="firstrun"' not in html
    assert 'data-today-source="playground"' in html
    current = _current_node(html)
    assert 'data-today-kind="new"' in current
    assert "Section 8" in current
    label, href = _live_playground_action(client)
    cta = re.search(r'<a class="rc-path-cta" href="([^"]+)">([^<]+)', current)
    assert cta
    assert unescape(cta.group(1)) == href == PLAYGROUND_BILLING_PATH
    assert cta.group(2).strip() == label
    assert "Learn" not in cta.group(2)
    assert "revision=1" not in unescape(cta.group(1))
    assert _revision_hero(html) == ""
    assert "Continue revision" not in html
    _assert_no_invented(html)


def test_phone_expired_today_caught_up_does_not_invent_dues(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    eng = _engine(client)
    today = user_today(eng)
    eng.repo.upsert_progress(
        USER,
        unit_id="clause-1",
        status="review",
        times_completed=1,
        last_completed=today,
        next_revision=today + timedelta(days=15),
        interval_days=15,
    )
    eng._invalidate_progress_cache()
    _expire(client)
    html = unescape(client.get("/dashboard").text)
    assert 'data-today-mode="firstrun"' not in html
    assert 'data-today-mode="revision"' not in html
    assert 'data-today-mode="learning"' in html
    assert "/revision/start" not in html
    assert 'data-today-source="playground"' not in html
    assert "Section 8" not in html
    _assert_no_invented(html)


def test_phone_expired_today_get_is_mutation_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_expire(client, monkeypatch)
    before = _facts(client)
    assert "ndps" in before["active"]
    assert before["selection"]
    assert before["constitution"]
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert _facts(client) == before
    again = client.get("/dashboard")
    assert again.status_code == 200
    assert _facts(client) == before


def test_phone_expired_today_playground_cta_cannot_reach_learning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_expire(client, monkeypatch)
    html = unescape(client.get("/dashboard").text)
    current = _current_node(html)
    label, href = _live_playground_action(client)
    cta = re.search(r'<a class="rc-path-cta" href="([^"]+)">([^<]+)', current)
    assert cta
    assert unescape(cta.group(1)) == href == PLAYGROUND_BILLING_PATH
    assert cta.group(2).strip() == label
    billing = client.get(href, follow_redirects=False)
    assert billing.status_code == 200
    assert 'data-expired-subscription="desktop"' in billing.text
    picker = client.get(sections_path("ndps"), follow_redirects=False)
    assert picker.status_code in {200, 303, 403}
    if picker.status_code == 200:
        text = unescape(picker.text)
        assert "Choose what to learn" not in text
        assert "data-pg-picker" not in picker.text
    learn = client.get(
        "/playground/laws/ndps/sections/8/u/clause:a/learn/read?revision=1",
        follow_redirects=False,
    )
    assert learn.status_code in {200, 303, 403}
    if learn.status_code == 200:
        body = unescape(learn.text)
        assert "data-pg-workspace" not in learn.text
        assert (
            'data-playground-gate="' in learn.text
            or LIVE_HEADING in body
            or "Resume Playground" in body
        )
    elif learn.status_code == 303:
        location = learn.headers.get("location") or ""
        assert "/learn/" not in location


def test_phone_expired_today_interactions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _plus_then_expire(client, monkeypatch)
    html = unescape(client.get("/dashboard").text)
    hero = _revision_hero(html)
    assert 'action="/revision/start"' in hero
    started = client.post("/revision/start", follow_redirects=False)
    assert started.status_code == 303
    location = started.headers.get("location") or ""
    assert location.startswith("/learn/")
    assert PLAYGROUND_BILLING_PATH not in location
    current = _current_node(html)
    cta = re.search(r'<a class="rc-path-cta" href="([^"]+)"', current)
    assert cta
    assert unescape(cta.group(1)) == PLAYGROUND_BILLING_PATH
    billing = client.get(PLAYGROUND_BILLING_PATH)
    assert billing.status_code == 200
    settings = client.get("/settings")
    assert settings.status_code == 200
    profile = client.get("/profile")
    assert profile.status_code == 200


def test_guest_free_plus_halted_pro_today_are_not_expired_phone_04(
    tmp_path: Path,
) -> None:
    guest = TestClient(_guest_app(tmp_path / "guest")).get("/dashboard").text
    assert 'data-expired-today="desktop"' not in guest
    assert "data-signed-in-today" not in guest
    assert "Welcome." in guest

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/dashboard").text
    assert 'data-expired-today="desktop"' not in free_html
    assert "data-signed-in-today" in free_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get("/dashboard").text
    assert 'data-plus-today="desktop"' in plus_html
    assert 'data-expired-today="desktop"' not in plus_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/dashboard").text
    assert 'data-expired-today="desktop"' not in pro_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    stored = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )
    halted_html = halted.get("/dashboard").text
    assert 'data-halted-today="desktop"' in halted_html
    assert 'data-expired-today="desktop"' not in halted_html


def test_phone_expired_today_css_scope_pins_and_desktop_08_untouched() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    assert "is expired/04-screen:" in css
    phone_block = css.split("is expired/04-screen:", 1)[1].split(
        "Plus desktop /calendar month view", 1
    )[0]
    assert "@media (max-width: 560px)" in phone_block
    assert "@media (min-width: 561px)" not in phone_block
    assert '[data-expired-today="desktop"]' in phone_block
    assert "[data-plus-today" not in phone_block
    assert "[data-halted-today" not in phone_block
    assert "safe-area-inset-bottom" in phone_block
    assert "overflow-x: hidden" in phone_block
    assert "min-height: 44px" in phone_block
    assert "var(--m-tabbar, 60px)" in phone_block
    assert ".mobile-tabbar" in phone_block
    assert "grid-template-columns: repeat(5, 1fr)" in phone_block
    assert "position: fixed" in phone_block
    assert ".dash-date" in phone_block
    assert "display: block" in phone_block
    assert ".dash-greeting-settings" in phone_block
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", phone_block) is None
    assert "sun" not in phone_block.lower()
    plus_phone = css.split("is plus/04-screen:", 1)[1].split(
        "Expired and Halted desktop /dashboard Today", 1
    )[0]
    assert "is expired/04-screen" not in plus_phone
    desk = css.split("expired/08-screen", 1)[1].split("is expired/04-screen:", 1)[0]
    assert "@media (min-width: 561px)" in desk
    assert "var(--pg-teal-tint)" in desk
    assert "[data-expired-today-phone]" not in css
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "is expired/04-screen:" not in mobile
    generic, marker, after_04 = mobile.partition("is signedIn/04-screen:")
    assert marker
    combined = after_04.split("/* R1 — Playground phone shell", 1)[0]
    assert ":not([data-expired-today])" in combined
    assert 'data-expired-today="desktop"] {' not in combined
    assert "is expired/04-screen:" not in STYLES.read_text(encoding="utf-8")
    dash = DASH.read_text(encoding="utf-8")
    assert 'data-expired-today="desktop"' in dash
    assert "data-expired-today-phone" not in dash
    assert 'action="/revision/start"' in dash
    for phrase in TEMPLATE_INVENTED:
        assert phrase not in dash, phrase
    assert PLAYGROUND_BILLING_PATH not in dash
    auth = AUTH.read_text(encoding="utf-8")
    dashboard = auth.split("async def dashboard", 1)[1].split(
        "async def profile_get", 1
    )[0]
    assert "reconcile_expired_playground_today" in dashboard
    assert "apply_expired_today_hero" in dashboard
    assert "merge_today_path" in dashboard
    schedule = SCHEDULE.read_text(encoding="utf-8")
    assert "def apply_expired_today_hero" in schedule
    assert "def reconcile_expired_playground_today" in schedule
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg49" in base
    assert "playground.css?v=pg43" not in base
    assert "styles.css?v=main87" in base
    assert "mobile.css?v=mob106" in base
    assert "data-expired-today-phone-tabs" not in base
    first_bar = base.split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 2
    )[2].split("</nav>", 1)[0]
    assert 'href="/calendar"' in first_bar
    assert "path.startswith('/dashboard')" in first_bar
    assert "data-expired-today-phone-tabs" not in first_bar


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


def _cookie(session: str, origin: str, csrf: str | None = None) -> list[dict]:
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
    return cookies


def test_phone_expired_today_screen04_captures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    empty_app = _mu_app(tmp_path / "empty")
    empty_client = TestClient(empty_app)
    _sign_in(empty_client)
    _subscribe(empty_client)
    _expire(empty_client)
    empty_session = empty_client.cookies.get(SESSION_COOKIE_NAME)
    empty_today = user_today(_engine(empty_client))
    empty_label = f"{empty_today.strftime('%A')} {empty_today.day} {empty_today.strftime('%B')}"

    mixed_app = _mu_app(tmp_path / "mixed")
    mixed_client = TestClient(mixed_app)
    _sign_in(mixed_client)
    day = _plus_then_expire(mixed_client, monkeypatch, streak_days=3)
    mixed_session = mixed_client.cookies.get(SESSION_COOKIE_NAME)
    mixed_label = f"{day.strftime('%A')} {day.day} {day.strftime('%B')}"
    live_label, live_href = _live_playground_action(mixed_client)

    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    firstrun_path = artifact_dir / "phone_expired_today_screen04_firstrun_390x844.png"
    mixed_path = artifact_dir / "phone_expired_today_screen04_390x844.png"
    desk_path = artifact_dir / "phone_expired_today_screen04_desktop_regression_1280.png"

    empty_port, _empty_server = _serve(empty_app)
    mixed_port, _mixed_server = _serve(mixed_app)
    empty_origin = f"http://127.0.0.1:{empty_port}"
    mixed_origin = f"http://127.0.0.1:{mixed_port}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        context.add_cookies(_cookie(empty_session, empty_origin))
        page = context.new_page()
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )
        page.goto(f"{empty_origin}/dashboard", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        empty_geo = page.evaluate(
            """() => {
              const expired = document.querySelector('[data-expired-today="desktop"]');
              const header = document.querySelector('.site-header');
              const tabs = document.querySelector('.mobile-tabbar');
              const tabLinks = tabs ? [...tabs.querySelectorAll('a.mobile-tab')] : [];
              const active = tabs && tabs.querySelector('.mobile-tab.is-active');
              const dateEl = document.querySelector('[data-today-date]');
              const sub = document.querySelector('.dash-subtext');
              const gear = document.querySelector('.dash-greeting-settings');
              const hello = document.querySelector('.dash-hello');
              const cta = document.querySelector('.dash-firstrun-cta');
              const avatar = document.querySelector('.dash-avatar-link');
              const initial = document.querySelector('.dash-avatar-fallback');
              const tabBox = tabs && tabs.getBoundingClientRect();
              const ctaBox = cta && cta.getBoundingClientRect();
              const greeting = document.querySelector('.dash-greeting');
              const hero = document.querySelector('[data-today-mode]');
              return {
                present: Boolean(expired),
                expiredDisplay: expired && getComputedStyle(expired).display,
                mode: document.querySelector('[data-today-mode]')
                  && document.querySelector('[data-today-mode]').getAttribute('data-today-mode'),
                hello: hello && hello.textContent.trim(),
                initial: initial && initial.textContent.trim(),
                dateText: dateEl && dateEl.textContent.trim(),
                dateDisplay: dateEl ? getComputedStyle(dateEl).display : null,
                subDisplay: sub ? getComputedStyle(sub).display : null,
                gearDisplay: gear ? getComputedStyle(gear).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                tabsPosition: tabs ? getComputedStyle(tabs).position : null,
                tabLabels: tabLinks.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabLinks.map((el) => el.getAttribute('href')),
                todayActive: active && active.textContent.replace(/\\s+/g, ' ').trim(),
                dedicatedTabs: Boolean(document.querySelector('[data-expired-today-phone-tabs]')),
                ctaText: cta && cta.textContent.trim(),
                ctaHref: cta && cta.getAttribute('href'),
                ctaH: ctaBox && ctaBox.height,
                ctaBottom: ctaBox && ctaBox.bottom,
                tabTop: tabBox && tabBox.top,
                avatarHref: avatar && avatar.getAttribute('href'),
                greetingTop: greeting && greeting.getBoundingClientRect().top,
                heroTop: hero && hero.getBoundingClientRect().top,
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                playgroundRows: document.querySelectorAll(
                  '[data-today-source="playground"]'
                ).length,
                banner: Boolean(document.querySelector('.lapse-banner')),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, firstrun_path)

        context.clear_cookies()
        context.add_cookies(_cookie(mixed_session, mixed_origin))
        page.goto(f"{mixed_origin}/dashboard", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        mixed_geo = page.evaluate(
            """() => {
              const expired = document.querySelector('[data-expired-today="desktop"]');
              const hero = document.querySelector('[data-today-mode="revision"]');
              const heroCta = hero && (hero.querySelector('[data-today-hero-cta]')
                || hero.querySelector('[data-revision-start]'));
              const form = hero && hero.querySelector('form.dash-revision-form');
              const pathCta = document.querySelector(
                '.rc-path-node.is-current .rc-path-cta'
              );
              const current = document.querySelector('.rc-path-node.is-current');
              const tabs = document.querySelector('.mobile-tabbar');
              const dateEl = document.querySelector('[data-today-date]');
              const gear = document.querySelector('.dash-greeting-settings');
              const frac = document.querySelector('.rc-goal-frac');
              const due = document.querySelector('.dash-due-count');
              const streak = document.querySelector('.rc-streak');
              const greeting = document.querySelector('.dash-greeting');
              const nodes = [...document.querySelectorAll('.rc-path-node')];
              const heroBox = hero && hero.getBoundingClientRect();
              const pathBox = document.querySelector('[data-today-path-card]')
                && document.querySelector('[data-today-path-card]').getBoundingClientRect();
              const tabBox = tabs && tabs.getBoundingClientRect();
              const ctaBox = heroCta && heroCta.getBoundingClientRect();
              const pathCtaBox = pathCta && pathCta.getBoundingClientRect();
              const visible = [...document.querySelectorAll('a, button')].filter((el) => {
                const style = getComputedStyle(el);
                const box = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden'
                  && box.width > 0 && box.height > 0;
              });
              return {
                present: Boolean(expired),
                expiredDisplay: expired && getComputedStyle(expired).display,
                mode: hero && hero.getAttribute('data-today-mode'),
                greeting: document.querySelector('.dash-hello')
                  && document.querySelector('.dash-hello').textContent.trim(),
                dateText: dateEl && dateEl.textContent.trim(),
                dateDisplay: dateEl ? getComputedStyle(dateEl).display : null,
                gearDisplay: gear ? getComputedStyle(gear).display : null,
                frac: frac && frac.textContent.trim(),
                due: due && due.textContent.trim(),
                streak: streak && streak.innerText.replace(/\\s+/g, ' ').trim(),
                heroTag: heroCta && heroCta.tagName,
                heroHref: heroCta && heroCta.getAttribute('href'),
                heroText: heroCta && (heroCta.textContent || '').replace(/\\s+/g, ' ').trim(),
                formAction: form && form.getAttribute('action'),
                pathCtaText: pathCta && pathCta.textContent.trim(),
                pathCtaHref: pathCta && pathCta.getAttribute('href'),
                pathCtaMin: pathCta && getComputedStyle(pathCta).minHeight,
                pathCtaH: pathCtaBox && pathCtaBox.height,
                currentSource: current && current.getAttribute('data-today-source'),
                currentKind: current && current.getAttribute('data-today-kind'),
                sources: nodes.map((el) => el.getAttribute('data-today-source')),
                titles: nodes.map((el) => {
                  const t = el.querySelector('.rc-path-title');
                  return t && t.textContent.trim();
                }),
                stacked: Boolean(
                  heroBox && pathBox && pathBox.top > heroBox.bottom - 8
                ),
                greetingTop: greeting && greeting.getBoundingClientRect().top,
                heroTop: heroBox && heroBox.top,
                pathTop: pathBox && pathBox.top,
                heroBottom: ctaBox && ctaBox.bottom,
                tabTop: tabBox && tabBox.top,
                tabsPosition: tabs ? getComputedStyle(tabs).position : null,
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                pathText: (document.querySelector('[data-today-path-card]')
                  || {innerText: ''}).innerText || '',
                firstVisible: visible[0] && (visible[0].getAttribute('href')
                  || visible[0].getAttribute('data-revision-start') || visible[0].tagName),
                tabInVisible: visible.some((el) => el.classList.contains('mobile-tab')),
                gearInVisible: visible.some((el) => el.classList.contains('dash-greeting-settings')),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, mixed_path)

        page.set_viewport_size({"width": 390, "height": 560})
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(80)
        short = page.evaluate(
            """() => {
              const pathCta = document.querySelector(
                '.rc-path-node.is-current .rc-path-cta'
              );
              const tabs = document.querySelector('.mobile-tabbar');
              pathCta.scrollIntoView();
              let box = pathCta.getBoundingClientRect();
              const tabTop = tabs.getBoundingClientRect().top;
              if (box.bottom > tabTop) {
                window.scrollBy(0, box.bottom - tabTop + 12);
                box = pathCta.getBoundingClientRect();
              }
              return {
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                height: box.height,
                top: box.top,
                bottom: box.bottom,
                inView: box.bottom <= tabs.getBoundingClientRect().top + 2 && box.top >= 0,
                tabTop: tabs.getBoundingClientRect().top,
              };
            }"""
        )

        page.set_viewport_size({"width": 1280, "height": 800})
        page.goto(f"{mixed_origin}/dashboard", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        desk_geo = page.evaluate(
            """() => {
              const expired = document.querySelector('[data-expired-today="desktop"]');
              const plus = document.querySelector('[data-plus-today="desktop"]');
              const greeting = document.querySelector('.dash-hello');
              const streak = document.querySelector('.rc-streak');
              const hero = document.querySelector('[data-today-mode="revision"]');
              const form = document.querySelector('[data-today-mode="revision"] form.dash-revision-form');
              const path = document.querySelector('[data-today-path-card]');
              const current = document.querySelector('.rc-path-node.is-current');
              const status = document.querySelector('.account-menu-btn-status');
              const tabs = document.querySelector('.mobile-tabbar');
              const header = document.querySelector('.site-header');
              const first = hero && hero.getBoundingClientRect();
              const pathBox = path && path.getBoundingClientRect();
              const nodes = [...document.querySelectorAll('.rc-path-node')];
              const cta = current && current.querySelector('.rc-path-cta');
              return {
                present: Boolean(expired),
                plus: Boolean(plus),
                greeting: greeting && greeting.textContent.trim(),
                streakDisplay: streak && getComputedStyle(streak).display,
                revision: Boolean(hero),
                formAction: form && form.getAttribute('action'),
                path: Boolean(path),
                twoCol: Boolean(first && pathBox && Math.abs(first.y - pathBox.y) < 80 && pathBox.x > first.x),
                currentSource: current && current.getAttribute('data-today-source'),
                currentHref: (cta && cta.getAttribute('href')) || '',
                currentLabel: (cta && cta.textContent.trim()) || '',
                sources: nodes.map((el) => el.getAttribute('data-today-source')),
                status: status && status.textContent.trim(),
                statusDisplay: status && getComputedStyle(status).display,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                navActive: document.querySelector('.PrimaryTabs--top .nav-link.is-active')
                  && document.querySelector('.PrimaryTabs--top .nav-link.is-active').textContent.replace(/\\s+/g, ' ').trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, desk_path)
        context.close()
        browser.close()

    assert empty_geo["present"] is True
    assert empty_geo["expiredDisplay"] not in (None, "none")
    assert empty_geo["mode"] == "firstrun"
    assert empty_geo["hello"] == "Welcome, Sanjay."
    assert empty_geo["initial"] == "S"
    assert empty_geo["dateText"] == empty_label
    assert empty_geo["dateDisplay"] not in (None, "none")
    assert empty_geo["subDisplay"] == "none"
    assert empty_geo["gearDisplay"] == "none"
    assert empty_geo["headerDisplay"] == "none"
    assert empty_geo["tabsDisplay"] != "none"
    assert empty_geo["tabsPosition"] == "fixed"
    assert empty_geo["tabLabels"] == ["Today", "Browse", "Playground", "Calendar", "Profile"]
    assert empty_geo["tabHrefs"] == [href for _, href in TAB_HREFS]
    assert empty_geo["todayActive"] == "Today"
    assert empty_geo["dedicatedTabs"] is False
    assert "Learn your first Article" in (empty_geo["ctaText"] or "")
    assert empty_geo["ctaHref"] == "/browse"
    assert empty_geo["ctaH"] == pytest.approx(48, abs=6)
    assert empty_geo["ctaBottom"] <= empty_geo["tabTop"] + 8
    assert empty_geo["avatarHref"] == "/settings"
    assert empty_geo["overflow"] is False
    assert empty_geo["playgroundRows"] == 0
    assert empty_geo["banner"] is False
    assert (empty_geo["greetingTop"] or 0) <= (empty_geo["heroTop"] or 0)

    assert mixed_geo["present"] is True
    assert mixed_geo["expiredDisplay"] not in (None, "none")
    assert mixed_geo["mode"] == "revision"
    assert mixed_geo["greeting"] == "Good morning, Sanjay."
    assert mixed_geo["dateText"] == mixed_label
    assert mixed_geo["dateDisplay"] not in (None, "none")
    assert mixed_geo["gearDisplay"] == "none"
    assert mixed_geo["frac"] == "1/3"
    assert mixed_geo["due"] == "2"
    assert "3" in (mixed_geo["streak"] or "")
    assert "6-day" not in (mixed_geo["streak"] or "")
    assert mixed_geo["heroTag"] == "BUTTON"
    assert mixed_geo["formAction"] == "/revision/start"
    assert "Continue revision" in (mixed_geo["heroText"] or "") or "Start revision" in (
        mixed_geo["heroText"] or ""
    )
    assert mixed_geo["pathCtaText"] == live_label
    assert mixed_geo["pathCtaHref"] == live_href
    assert float(str(mixed_geo["pathCtaMin"] or "0").replace("px", "") or 0) >= 44
    assert mixed_geo["pathCtaH"] == pytest.approx(44, abs=4)
    assert mixed_geo["currentSource"] == "playground"
    assert mixed_geo["currentKind"] == "review"
    assert mixed_geo["sources"][0] == "constitution"
    assert "playground" in (mixed_geo["sources"] or [])
    assert "Article 20(1)" in (mixed_geo["titles"] or [])
    assert any("Section 8" in (t or "") for t in (mixed_geo["titles"] or []))
    assert "Article 19(1)(a)" not in (mixed_geo["pathText"] or "")
    assert mixed_geo["stacked"] is True
    assert (mixed_geo["greetingTop"] or 0) <= (mixed_geo["heroTop"] or 0) <= (
        mixed_geo["pathTop"] or 0
    )
    assert mixed_geo["tabsPosition"] == "fixed"
    assert mixed_geo["overflow"] is False
    assert mixed_geo["firstVisible"] == "/settings"
    assert mixed_geo["tabInVisible"] is True
    assert mixed_geo["gearInVisible"] is False

    assert short["overflow"] is False
    assert short["height"] >= 44
    assert short["inView"] is True

    assert desk_geo["present"] is True
    assert desk_geo["plus"] is False
    assert desk_geo["greeting"] == "Good morning, Sanjay."
    assert desk_geo["streakDisplay"] != "none"
    assert desk_geo["revision"] is True
    assert desk_geo["formAction"] == "/revision/start"
    assert desk_geo["path"] is True
    assert desk_geo["twoCol"] is True
    assert desk_geo["currentSource"] == "playground"
    assert desk_geo["currentHref"] == live_href
    assert desk_geo["currentLabel"] == live_label
    assert "playground" in (desk_geo["sources"] or [])
    assert "constitution" in (desk_geo["sources"] or [])
    assert desk_geo["status"] == LIVE_HEADING
    assert desk_geo["statusDisplay"] != "none"
    assert desk_geo["tabsDisplay"] == "none"
    assert desk_geo["headerDisplay"] != "none"
    assert "Today" in (desk_geo["navActive"] or "")

    for path in (firstrun_path, mixed_path, desk_path):
        assert path.is_file() and path.stat().st_size > 1000
