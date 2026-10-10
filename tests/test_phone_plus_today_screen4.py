"""Phone Plus Today Screen 04 (CTA map plus/04-screen).

Authorized: ChatGPT. Authenticated active Plus GET /dashboard at 390x844.
Desktop Plus Screen 08 is the functional contract. Live greeting, date,
streak, mixed Constitution + Playground path, live hero/path CTAs.
First-run is a real empty architecture. Guest, Free signedIn 04, Expired,
Halted, Pro, and desktop 08 stay unchanged.
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
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.urls import sections_path
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
USER = UUID("11111111-1111-4111-8111-111111111111")
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
)
TEMPLATE_INVENTED = (
    "Premium",
    "Unlock all",
    "device limit",
    "replacement",
    "4-day streak",
    "Good morning.",
    "Reviewed this morning",
    "Steady plan",
)
RENDER_INVENTED = (
    "Premium",
    "Unlock all",
    "device limit",
    "replacement",
    "4-day streak",
    "6-day streak",
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
    locator = "ndps:section:8:clause:a"
    posted = client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "unit": locator, "section": "1"},
        follow_redirects=False,
    )
    assert posted.status_code in {200, 303}
    _seed_progress(
        client.app.state.playground,
        USER,
        "ndps",
        locator,
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


def _dash_facts(client: TestClient) -> dict:
    eng = _engine(client)
    today = user_today(eng)
    sessions = eng.repo.study_sessions_for_day(USER, today)
    serialized = tuple(
        (
            kind,
            None
            if sess is None
            else (
                sess.id,
                sess.status,
                sess.remaining,
                tuple(i.learning_unit_id for i in sess.items),
            ),
        )
        for kind, sess in sorted(sessions.items())
    )
    progress = tuple(
        (
            row.learning_unit_id,
            row.status,
            str(row.next_revision),
            row.interval_days,
        )
        for row in sorted(
            eng.list_all_progress(), key=lambda r: r.learning_unit_id
        )
    )
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    return {
        "sessions": serialized,
        "progress": progress,
        "subscription": None
        if stored is None
        else (stored.id, stored.status, stored.tier, stored.is_current),
        "roster": tuple(sorted(i.law_id for i in roster.active_roster_items(USER))),
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
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


def test_phone_plus_today_firstrun_has_no_invented_dues(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    before = _dash_facts(client)
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert _dash_facts(client) == before
    html = unescape(page.text)
    assert 'data-plus-today="desktop"' in html
    assert "data-signed-in-today" in html
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
    assert 'class="dash-avatar-link" href="/settings"' in html
    assert 'class="mobile-icon-btn dash-greeting-settings" href="/settings"' in html
    _assert_no_invented(html)
    tabs = _tabs(html)
    for label_text, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        assert label_text in tabs
    assert 'aria-current="page"' in tabs
    assert ">Today<" in tabs
    assert "data-plus-today-phone-tabs" not in html
    assert "data-theme-pref" not in html.split("<header", 1)[1].split("</header>", 1)[0]


def test_phone_plus_today_canonical_mixed_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _plus_client(tmp_path)
    day = _seed_canonical(client, monkeypatch, streak_days=3)
    before = _dash_facts(client)
    html = unescape(client.get("/dashboard").text)
    assert _dash_facts(client) == before
    assert 'data-plus-today="desktop"' in html
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
    assert 'data-today-hero-cta' in hero
    assert 'action="/revision/start"' not in hero
    href = re.search(
        r'<a class="btn dash-btn-full" href="([^"]+)"[^>]*data-today-hero-cta>([^<]+)',
        hero,
    )
    assert href, hero
    assert "/playground/" in unescape(href.group(1))
    assert "revision=1" in unescape(href.group(1))
    assert href.group(2).strip() == "Start revision →"
    assert "Continue revision" not in hero
    nodes = _path_nodes(html)
    assert len(nodes) >= 4
    sources = re.findall(r'data-today-source="([^"]+)"', "".join(nodes))
    statuses = re.findall(r'class="rc-path-node is-([^"]+)"', "".join(nodes))
    kinds = re.findall(r'data-today-kind="([^"]+)"', "".join(nodes))
    titles = re.findall(r'class="rc-path-title">([^<]+)', "".join(nodes))
    assert sources[0] == "constitution"
    assert statuses[0] == "done"
    assert "Article 20(1)" in titles[0]
    assert "Day 1 revision" in nodes[0]
    current = _current_node(html)
    assert 'data-today-source="playground"' in current
    assert 'data-today-kind="review"' in current
    assert "Section 8(a) — NDPS Act" in current
    assert "Day 1 → 3 · Playground" in current
    cta = re.search(r'<a class="rc-path-cta" href="([^"]+)">([^<]+)', current)
    assert cta
    assert "/playground/" in unescape(cta.group(1))
    assert "revision=1" in unescape(cta.group(1))
    assert cta.group(2).strip() == "Start revision →"
    assert "Article 20(3)" in "".join(titles)
    assert "New · Playground" in html
    assert "Section 1 — NDPS Act" in html
    assert "Section 9" not in html
    assert "Article 19(1)(a)" not in html
    assert "Article 21" not in html
    constitution = [n for n in nodes if 'data-today-source="constitution"' in n]
    assert constitution
    for node in constitution:
        assert "/playground/" not in node
        if "is-current" not in node:
            assert "rc-path-cta" not in node
    assert "review" in kinds
    assert "new" in kinds
    _assert_no_invented(html)


def test_phone_plus_today_day15_constitution_stays_post(
    tmp_path: Path,
) -> None:
    client = _plus_client(tmp_path)
    _make_due(
        client,
        ["clause-1", "clause-2"],
        interval_days={"clause-1": 15, "clause-2": 1},
    )
    html = unescape(client.get("/dashboard").text)
    assert 'data-today-mode="revision"' in html
    assert 'action="/revision/start"' in html
    assert "data-revision-start" in html
    assert "Start revision →" in html
    hero = _revision_hero(html)
    assert 'data-today-hero-cta' not in hero
    path = "".join(_path_nodes(html))
    assert "Day 15 revision" in path
    assert "Day 15 → 30" not in path
    assert 'data-today-source="playground"' not in html
    current = _current_node(html)
    assert "Article 20(1)" in current
    cta = re.search(r'<a class="rc-path-cta" href="([^"]+)">([^<]+)', current)
    assert cta
    assert "/learn/" in unescape(cta.group(1))
    assert cta.group(2).strip() == "Start revision →"
    _assert_no_invented(html)


def test_phone_plus_today_enrolled_without_sections_has_no_playground_row(
    tmp_path: Path,
) -> None:
    client = _plus_client(tmp_path)
    added = _confirm_add(client, "ndps")
    assert added.status_code == 303
    html = unescape(client.get("/dashboard").text)
    assert 'data-today-source="playground"' not in html
    assert 'data-today-mode="firstrun"' in html
    assert "Learn your first Article" in html
    home = unescape(client.get("/playground").text)
    assert "Start learning" in home
    assert sections_path("ndps") in home
    _assert_no_invented(html)


def test_phone_plus_today_selected_unstarted_is_new_not_due(
    tmp_path: Path,
) -> None:
    client = _plus_client(tmp_path)
    assert _confirm_add(client, "ndps").status_code == 303
    posted = client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "section": "8"},
        follow_redirects=False,
    )
    assert posted.status_code in {200, 303}
    html = unescape(client.get("/dashboard").text)
    assert 'data-today-mode="firstrun"' not in html
    assert 'data-today-source="playground"' in html
    current = _current_node(html)
    assert 'data-today-kind="new"' in current
    assert "Section 8 — NDPS Act" in current
    assert "New · Playground" in current or "New · Playground" in html
    cta = re.search(r'<a class="rc-path-cta" href="([^"]+)">([^<]+)', current)
    assert cta
    href = unescape(cta.group(1))
    assert "/playground/" in href
    assert "revision=1" not in href
    assert cta.group(2).strip() == "Learn →"
    hero = _revision_hero(html)
    assert hero == ""
    assert "Continue revision" not in html
    _assert_no_invented(html)


def test_phone_plus_today_caught_up_does_not_invent_dues(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
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
    html = unescape(client.get("/dashboard").text)
    assert 'data-today-mode="firstrun"' not in html
    assert 'data-today-mode="revision"' not in html
    assert 'data-today-mode="learning"' in html
    assert "/revision/start" not in html
    assert 'data-today-source="playground"' not in html
    assert "Section 8" not in html
    _assert_no_invented(html)


def test_guest_free_expired_halted_pro_today_are_not_plus_phone_04(
    tmp_path: Path,
) -> None:
    guest = TestClient(_guest_app(tmp_path / "guest")).get("/dashboard").text
    assert 'data-plus-today="desktop"' not in guest
    assert "data-signed-in-today" not in guest
    assert "Welcome." in guest

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/dashboard").text
    assert 'data-plus-today="desktop"' not in free_html
    assert "data-signed-in-today" in free_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/dashboard").text
    assert 'data-plus-today="desktop"' not in pro_html

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
    expired_html = expired.get("/dashboard").text
    assert 'data-expired-today="desktop"' in expired_html
    assert "data-plus-today" not in expired_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    stored_h = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored_h.id, status="halted"
    )
    halted_html = halted.get("/dashboard").text
    assert 'data-halted-today="desktop"' in halted_html
    assert "data-plus-today" not in halted_html


def test_phone_plus_today_css_scope_pins_and_desktop_08_untouched() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    assert "is plus/04-screen:" in css
    phone_block = css.split("is plus/04-screen:", 1)[1].split(
        "Expired and Halted desktop /dashboard Today", 1
    )[0]
    assert "@media (max-width: 560px)" in phone_block
    assert "@media (min-width: 561px)" not in phone_block
    assert '[data-plus-today="desktop"]' in phone_block
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
    desk = css.split("plus/08-screen", 1)[1].split("is plus/04-screen:", 1)[0]
    assert "@media (min-width: 561px)" in desk
    assert "var(--pg-teal-tint)" in desk
    assert "[data-plus-today-phone]" not in css
    mobile = MOBILE.read_text(encoding="utf-8")
    generic, marker, after_04 = mobile.partition("is signedIn/04-screen:")
    assert marker
    combined = after_04.split("/* R1 — Playground phone shell", 1)[0]
    assert "is plus/04-screen:" not in generic
    assert "is plus/04-screen:" not in combined
    assert ":not([data-plus-today])" in combined
    assert 'data-plus-today="desktop"] {' not in combined
    assert "sun" not in combined.lower()
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", combined) is None
    assert "is plus/04-screen:" not in STYLES.read_text(encoding="utf-8")
    dash = DASH.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in dash
    assert "data-plus-today-phone" not in dash
    assert 'action="/revision/start"' in dash
    assert "data-today-hero-cta" in dash
    for phrase in TEMPLATE_INVENTED:
        assert phrase not in dash, phrase
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg37" in base
    assert "playground.css?v=pg36" not in base
    assert "styles.css?v=main86" in base
    assert "mobile.css?v=mob105" in base
    assert "data-plus-today-phone-tabs" not in base
    first_bar = base.split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 2
    )[2].split("</nav>", 1)[0]
    assert 'href="/calendar"' in first_bar
    assert "path.startswith('/dashboard')" in first_bar
    assert "data-plus-today-phone-tabs" not in first_bar


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


def test_phone_plus_today_screen04_captures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    empty_app = _mu_app(tmp_path / "empty")
    empty_client = TestClient(empty_app)
    _sign_in(empty_client)
    _subscribe(empty_client)
    empty_session = empty_client.cookies.get(SESSION_COOKIE_NAME)
    empty_today = user_today(_engine(empty_client))
    empty_label = f"{empty_today.strftime('%A')} {empty_today.day} {empty_today.strftime('%B')}"

    mixed_app = _mu_app(tmp_path / "mixed")
    mixed_client = TestClient(mixed_app)
    _sign_in(mixed_client)
    _subscribe(mixed_client)
    day = _seed_canonical(mixed_client, monkeypatch, streak_days=3)
    mixed_session = mixed_client.cookies.get(SESSION_COOKIE_NAME)
    mixed_label = f"{day.strftime('%A')} {day.day} {day.strftime('%B')}"

    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    firstrun_path = artifact_dir / "phone_plus_today_screen04_firstrun_390x844.png"
    mixed_path = artifact_dir / "phone_plus_today_screen04_390x844.png"
    desk_path = artifact_dir / "phone_plus_today_screen04_desktop_regression_1280.png"

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
              const plus = document.querySelector('[data-plus-today="desktop"]');
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
              const tabBox = tabs && tabs.getBoundingClientRect();
              const ctaBox = cta && cta.getBoundingClientRect();
              return {
                present: Boolean(plus),
                plusDisplay: plus && getComputedStyle(plus).display,
                mode: document.querySelector('[data-today-mode]')
                  && document.querySelector('[data-today-mode]').getAttribute('data-today-mode'),
                hello: hello && hello.textContent.trim(),
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
                dedicatedTabs: Boolean(document.querySelector('[data-plus-today-phone-tabs]')),
                ctaText: cta && cta.textContent.trim(),
                ctaHref: cta && cta.getAttribute('href'),
                ctaH: ctaBox && ctaBox.height,
                ctaBottom: ctaBox && ctaBox.bottom,
                tabTop: tabBox && tabBox.top,
                avatarHref: avatar && avatar.getAttribute('href'),
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                playgroundRows: document.querySelectorAll(
                  '[data-today-source="playground"]'
                ).length,
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
              const plus = document.querySelector('[data-plus-today="desktop"]');
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
              const nodes = [...document.querySelectorAll('.rc-path-node')];
              const heroBox = hero && hero.getBoundingClientRect();
              const pathBox = document.querySelector('[data-today-path-card]')
                && document.querySelector('[data-today-path-card]').getBoundingClientRect();
              const tabBox = tabs && tabs.getBoundingClientRect();
              const ctaBox = heroCta && heroCta.getBoundingClientRect();
              const pathCtaBox = pathCta && pathCta.getBoundingClientRect();
              return {
                present: Boolean(plus),
                plusDisplay: plus && getComputedStyle(plus).display,
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
                heroBottom: ctaBox && ctaBox.bottom,
                tabTop: tabBox && tabBox.top,
                tabsPosition: tabs ? getComputedStyle(tabs).position : null,
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                pathText: (document.querySelector('[data-today-path-card]')
                  || {innerText: ''}).innerText || '',
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
              const plus = document.querySelector('[data-plus-today="desktop"]');
              const greeting = document.querySelector('.dash-hello');
              const streak = document.querySelector('.rc-streak');
              const hero = document.querySelector('[data-today-mode="revision"]');
              const path = document.querySelector('[data-today-path-card]');
              const current = document.querySelector('.rc-path-node.is-current');
              const status = document.querySelector('.account-menu-btn-status');
              const tabs = document.querySelector('.mobile-tabbar');
              const header = document.querySelector('.site-header');
              const first = hero && hero.getBoundingClientRect();
              const pathBox = path && path.getBoundingClientRect();
              const nodes = [...document.querySelectorAll('.rc-path-node')];
              return {
                present: Boolean(plus),
                greeting: greeting && greeting.textContent.trim(),
                streakDisplay: streak && getComputedStyle(streak).display,
                revision: Boolean(hero),
                path: Boolean(path),
                twoCol: Boolean(first && pathBox && Math.abs(first.y - pathBox.y) < 80 && pathBox.x > first.x),
                currentSource: current && current.getAttribute('data-today-source'),
                currentHref: current && (current.querySelector('.rc-path-cta') || {}).href || '',
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
    assert empty_geo["plusDisplay"] not in (None, "none")
    assert empty_geo["mode"] == "firstrun"
    assert empty_geo["hello"] == "Welcome, Sanjay."
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

    assert mixed_geo["present"] is True
    assert mixed_geo["plusDisplay"] not in (None, "none")
    assert mixed_geo["mode"] == "revision"
    assert mixed_geo["greeting"] == "Good morning, Sanjay."
    assert mixed_geo["dateText"] == mixed_label
    assert mixed_geo["dateDisplay"] not in (None, "none")
    assert mixed_geo["gearDisplay"] == "none"
    assert mixed_geo["frac"] == "1/3"
    assert mixed_geo["due"] == "2"
    assert "3" in (mixed_geo["streak"] or "")
    assert "6-day" not in (mixed_geo["streak"] or "")
    assert mixed_geo["heroTag"] == "A"
    assert "/playground/" in (mixed_geo["heroHref"] or "")
    assert "revision=1" in (mixed_geo["heroHref"] or "")
    assert mixed_geo["heroText"] == "Start revision →"
    assert mixed_geo["formAction"] in (None, "")
    assert mixed_geo["pathCtaText"] == "Start revision →"
    assert "/playground/" in (mixed_geo["pathCtaHref"] or "")
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
    assert mixed_geo["tabsPosition"] == "fixed"
    assert mixed_geo["overflow"] is False

    assert short["overflow"] is False
    assert short["height"] >= 44
    assert short["inView"] is True

    assert desk_geo["present"] is True
    assert desk_geo["greeting"] == "Good morning, Sanjay."
    assert desk_geo["streakDisplay"] != "none"
    assert desk_geo["revision"] is True
    assert desk_geo["path"] is True
    assert desk_geo["twoCol"] is True
    assert desk_geo["currentSource"] == "playground"
    assert "/playground/" in (desk_geo["currentHref"] or "")
    assert "playground" in (desk_geo["sources"] or [])
    assert "constitution" in (desk_geo["sources"] or [])
    assert desk_geo["status"] == "RecallC Plus"
    assert desk_geo["statusDisplay"] != "none"
    assert desk_geo["tabsDisplay"] == "none"
    assert desk_geo["headerDisplay"] != "none"
    assert "Today" in (desk_geo["navActive"] or "")

    for path in (firstrun_path, mixed_path, desk_path):
        assert path.is_file() and path.stat().st_size > 1000
