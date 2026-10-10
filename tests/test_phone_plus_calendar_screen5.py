"""Phone Plus Calendar Screen 05 (CTA map plus/05-screen).

Authorized: ChatGPT. Authenticated active Plus GET /calendar at 390x844.
Desktop Plus Screen 09 is the functional contract. Live month, Constitution
today-card, Playground chips on selected-day lists only, Continue split
(phone /dashboard, desktop /playground). Empty is a real architecture.
Guest, Free signedIn 05, Expired, Halted, Pro, and desktop 09 stay unchanged.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from datetime import date, datetime, timedelta, timezone
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
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.service import user_today
from tests.test_playground_m8 import _seed_progress
from tests.test_roster_m5a import _confirm_add, _csrf

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
APP = ROOT / "src/constitution_memorizer/web/app.py"
SYNC = ROOT / "src/constitution_memorizer/calendar_sync"
USER = UUID("11111111-1111-4111-8111-111111111111")
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
)
RENDER_INVENTED = (
    "Premium",
    "Unlock all",
    "Study archive",
    "Sunday 6 September",
    "September 2026",
    "Article 19(1)(a)",
    "Article 21",
    "1 UNITS",
    "first revision · Playground",
    "ladder 7 → 15",
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
        study_materials_dir=tmp_path / "study-materials",
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


def _upsert_constitution(
    client: TestClient,
    unit_id: str,
    *,
    as_of: date,
    interval_days: int,
    next_revision: date,
    last_completed: date | None = None,
    times_completed: int = 1,
) -> None:
    eng = _engine(client)
    eng.repo.upsert_progress(
        eng.user_id,
        unit_id=unit_id,
        status="review",
        times_completed=times_completed,
        last_completed=last_completed if last_completed is not None else as_of - timedelta(days=1),
        next_revision=next_revision,
        interval_days=interval_days,
    )
    eng._invalidate_progress_cache()


def _seed_playground_due(client: TestClient, *, day: date) -> None:
    assert _confirm_add(client, "ndps").status_code == 303
    locator = "ndps:section:8:clause:a"
    posted = client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "unit": locator},
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


def _seed_mixed_due_today(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> date:
    day = user_today(_engine(client))
    _pin_playground_today(monkeypatch, day)
    _upsert_constitution(
        client, "clause-1", as_of=day, interval_days=15, next_revision=day
    )
    _upsert_constitution(
        client, "clause-2", as_of=day, interval_days=1, next_revision=day
    )
    _seed_playground_due(client, day=day)
    return day


def _phone(html: str) -> str:
    return html.split("revisions-mobile", 1)[1].split("calendar-header", 1)[0]


def _today_card(phone: str) -> str:
    return phone.split("data-today-list", 1)[1].split(
        "data-calendar-gcal-footnote", 1
    )[0]


def _tabs(html: str) -> str:
    return html.split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 1
    )[1].split("</nav>", 1)[0]


def _write_facts(client: TestClient) -> dict:
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    return {
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
        if phrase == "September 2026" and today.year == 2026 and today.month == 9:
            continue
        assert phrase not in text, phrase


def _assert_plus_calendar_chrome(html: str, *, today: date) -> None:
    assert 'data-plus-calendar="desktop"' in html
    assert "data-signed-in-calendar" in html
    assert "data-expired-calendar" not in html
    assert "data-halted-calendar" not in html
    assert 'data-mscreen="revisions"' in html
    phone = _phone(html)
    assert "Calendar" in phone
    assert today.strftime("%B %Y") in phone
    assert "data-cal-filter" not in phone
    assert "Add task" not in phone
    assert "view=week" not in phone
    assert "data-cal-source" not in phone
    tabs = _tabs(html)
    for label_text, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        assert label_text in tabs
    assert 'aria-current="page"' in tabs
    assert ">Calendar<" in tabs
    assert "data-plus-calendar-phone-tabs" not in html
    _assert_no_invented(phone)


def test_phone_plus_calendar_empty_has_no_invented_chips(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    before = _write_facts(client)
    page = client.get("/calendar")
    assert page.status_code == 200
    assert _write_facts(client) == before
    html = unescape(page.text)
    today = user_today(_engine(client))
    _assert_plus_calendar_chrome(html, today=today)
    phone = _phone(html)
    assert "Nothing due today" in phone
    assert "cal-m-today-continue" not in phone
    assert "/playground/" not in phone
    assert "NDPS" not in phone
    assert "Section 8" not in phone
    assert "Article 20" not in phone
    assert "1 → 3 → 7 → 15 → 30 → 60" in phone
    desk = html.split("calendar-header", 1)[1]
    assert 'data-cal-continue-recall href="/playground"' in desk or (
        'href="/playground"' in desk and "data-cal-continue-recall" in desk
    )


def test_phone_plus_calendar_mixed_due_today_keeps_constitution_today_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _plus_client(tmp_path)
    day = _seed_mixed_due_today(client, monkeypatch)
    before = _write_facts(client)
    html = unescape(client.get("/calendar").text)
    assert _write_facts(client) == before
    _assert_plus_calendar_chrome(html, today=day)
    phone = _phone(html)
    card = _today_card(phone)
    assert "Today · 2 units" in card
    assert "Article 20(1)" in card
    assert "Due today · Day 15" in card
    assert "Article 20(3)" in card
    assert "Due today · Day 1" in card
    assert "NDPS" not in card
    assert "Playground" not in card
    assert 'class="cal-m-today-continue" href="/dashboard"' in card
    assert "cal-m-today-continue" not in phone.split("data-today-list", 1)[0]
    assert 'href="/learn/clause-1"' in card
    assert 'href="/learn/clause-2"' in card
    marker = f'data-day-list="{day.isoformat()}"'
    idx = phone.find(marker)
    assert idx != -1
    day_html = phone[idx : idx + 3500]
    assert "NDPS Act · §8(a) · Playground" in day_html
    playground_href = re.search(r'href="([^"]*playground[^"]*)"', day_html)
    assert playground_href
    href = unescape(playground_href.group(1))
    assert "/playground/" in href
    assert "revision=1" in href
    assert "cal-m-today-continue" not in day_html
    assert 'href="/learn/clause-1"' in day_html
    desk = html.split("calendar-header", 1)[1]
    assert "/playground" in desk.split("data-cal-continue-recall", 1)[1][:80]
    assert 'data-cal-source="playground"' in desk
    assert 'data-cal-source="constitution"' in desk


def test_phone_plus_calendar_day15_constitution_without_playground(
    tmp_path: Path,
) -> None:
    client = _plus_client(tmp_path)
    day = user_today(_engine(client))
    _upsert_constitution(
        client, "clause-1", as_of=day, interval_days=15, next_revision=day
    )
    _upsert_constitution(
        client, "clause-2", as_of=day, interval_days=1, next_revision=day
    )
    html = unescape(client.get("/calendar").text)
    phone = _phone(html)
    card = _today_card(phone)
    assert "Day 15" in card
    assert "ladder 7 → 15" not in card
    assert "Day 15 → 30" not in card
    assert 'href="/dashboard"' in card
    assert "/playground/" not in phone
    assert "NDPS" not in phone
    _assert_no_invented(html)


def test_phone_plus_calendar_enrolled_without_sections_has_no_chip(
    tmp_path: Path,
) -> None:
    client = _plus_client(tmp_path)
    assert _confirm_add(client, "ndps").status_code == 303
    before = _write_facts(client)
    html = unescape(client.get("/calendar").text)
    assert _write_facts(client) == before
    phone = _phone(html)
    assert "NDPS" not in phone
    assert "/playground/" not in phone
    assert 'data-cal-source="playground"' not in html
    assert "Nothing due today" in phone
    assert "cal-m-today-continue" not in phone


def test_phone_plus_calendar_selected_unstarted_has_no_chip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _plus_client(tmp_path)
    day = user_today(_engine(client))
    _pin_playground_today(monkeypatch, day)
    assert _confirm_add(client, "ndps").status_code == 303
    posted = client.post(
        "/playground/laws/ndps/sections",
        data={**_csrf(client), "unit": "ndps:section:8:clause:a"},
        follow_redirects=False,
    )
    assert posted.status_code in {200, 303}
    html = unescape(client.get("/calendar").text)
    phone = _phone(html)
    assert "NDPS" not in phone
    assert "/playground/" not in phone
    assert 'data-cal-source="playground"' not in html
    assert "Nothing due today" in phone


def test_phone_plus_calendar_overdue_done_and_future_constitution(
    tmp_path: Path,
) -> None:
    client = _plus_client(tmp_path)
    day = user_today(_engine(client))
    _upsert_constitution(
        client,
        "clause-1",
        as_of=day,
        interval_days=15,
        next_revision=day - timedelta(days=2),
    )
    html = unescape(client.get("/calendar").text)
    phone = _phone(html)
    card = _today_card(phone)
    assert "Overdue" in card
    assert "Article 20(1)" in card
    assert "Day 15" in card
    assert 'href="/dashboard"' in card

    client_done = _plus_client(tmp_path / "done")
    day_done = user_today(_engine(client_done))
    _upsert_constitution(
        client_done,
        "clause-1",
        as_of=day_done,
        interval_days=3,
        next_revision=day_done + timedelta(days=3),
        last_completed=day_done,
        times_completed=2,
    )
    done_html = unescape(client_done.get("/calendar").text)
    done_card = _today_card(_phone(done_html))
    assert "Done · Day 3" in done_card
    assert "Article 20(1)" in done_card

    client_future = _plus_client(tmp_path / "future")
    day_future = user_today(_engine(client_future))
    _upsert_constitution(
        client_future,
        "clause-1",
        as_of=day_future,
        interval_days=15,
        next_revision=day_future + timedelta(days=7),
    )
    future_html = unescape(client_future.get("/calendar").text)
    future_phone = _phone(future_html)
    assert "Nothing due today" in future_phone
    assert "cal-m-today-continue" not in future_phone
    assert "15-day review" in future_phone
    assert 'data-cal-source="constitution"' in future_html


def test_phone_plus_calendar_month_nav_is_real_get_links(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    today = user_today(_engine(client))
    phone = _phone(client.get("/calendar").text)
    assert 'aria-label="Previous month"' in phone
    assert 'aria-label="Next month"' in phone
    assert "/calendar?year=" in phone
    assert "view=week" not in phone
    other = today.replace(day=1) - timedelta(days=1)
    jumped = client.get(f"/calendar?year={other.year}&month={other.month}")
    assert jumped.status_code == 200
    jumped_phone = _phone(jumped.text)
    assert other.strftime("%B %Y") in unescape(jumped_phone)
    assert "cal-m-today-continue" not in jumped_phone


def test_guest_free_expired_halted_pro_calendar_are_not_plus_phone_05(
    tmp_path: Path,
) -> None:
    guest_resp = TestClient(_guest_app(tmp_path / "guest")).get(
        "/calendar", follow_redirects=False
    )
    assert guest_resp.status_code in (302, 303)
    assert "/login" in (guest_resp.headers.get("location") or "")
    assert "data-plus-calendar" not in guest_resp.text

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/calendar").text
    assert "data-signed-in-calendar" in free_html
    assert "data-plus-calendar" not in free_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/calendar").text
    assert "data-plus-calendar" not in pro_html

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
    expired_html = expired.get("/calendar").text
    assert 'data-expired-calendar="desktop"' in expired_html
    assert "data-plus-calendar" not in expired_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    stored_h = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored_h.id, status="halted"
    )
    halted_html = halted.get("/calendar").text
    assert 'data-halted-calendar="desktop"' in halted_html
    assert "data-plus-calendar" not in halted_html


def test_phone_plus_calendar_css_scope_pins_and_desktop_09_untouched() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    assert "is plus/05-screen:" in css
    phone_block = css.split("is plus/05-screen:", 1)[1].split(
        "Expired and Halted desktop /calendar", 1
    )[0]
    assert "@media (max-width: 560px)" in phone_block
    assert "@media (min-width: 561px)" not in phone_block
    assert '[data-plus-calendar="desktop"]' in phone_block
    assert "safe-area-inset-bottom" in phone_block
    assert "overflow-x: hidden" in phone_block
    assert "min-width: 44px" in phone_block
    assert "min-height: 44px" in phone_block
    assert "var(--m-tabbar, 60px)" in phone_block
    assert ".mobile-tabbar" in phone_block
    assert "grid-template-columns: repeat(5, 1fr)" in phone_block
    assert "position: fixed" in phone_block
    assert "position: static" in phone_block
    assert ".cal-m-cell.is-selected" in phone_block
    assert ":has(.cal-m-cell.is-selected)" in phone_block.replace("\n", "").replace(
        " ", ""
    ) or (":has(.cal-m-cell.is-selected)" in phone_block)
    assert "href*=\"/playground/\"" in phone_block.replace(" ", "") or (
        'href*="/playground/"' in phone_block
    )
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", phone_block) is None
    assert "sun" not in phone_block.lower()
    desk = css.split("plus/09-screen", 1)[1].split("is plus/05-screen:", 1)[0]
    assert "@media (min-width: 561px)" in desk
    assert "minmax(0, 1fr) 380px" in desk
    assert "var(--pg-teal)" in desk
    assert "[data-plus-calendar-phone]" not in css
    mobile = MOBILE.read_text(encoding="utf-8")
    generic, marker, after_04 = mobile.partition("is signedIn/04-screen:")
    assert marker
    combined = after_04.split("/* R1 — Playground phone shell", 1)[0]
    assert "is plus/05-screen:" not in generic
    assert "is plus/05-screen:" not in combined
    assert ":not([data-plus-calendar])" in combined
    assert 'data-plus-calendar="desktop"] {' not in combined
    assert "sun" not in combined.lower()
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", combined) is None
    assert "is plus/05-screen:" not in STYLES.read_text(encoding="utf-8")
    cal = CAL.read_text(encoding="utf-8")
    phone = cal.split("revisions-mobile", 1)[1].split("calendar-header", 1)[0]
    assert 'href="/dashboard"' in phone
    assert "data-cal-filter" not in phone
    assert "data-cal-source" not in phone
    assert "data-plus-calendar-phone" not in cal
    today_card = phone.split("data-today-list", 1)[1]
    assert "cal-m-today-continue" in today_card
    desk_cal = cal.split("calendar-header", 1)[1]
    assert 'href="/playground"' in desk_cal
    assert "data-cal-continue-recall" in desk_cal
    app = APP.read_text(encoding="utf-8")
    assert "build_revisions_view" in app
    assert "playground_calendar_chips" in app
    for path in SYNC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "plus_calendar" not in text
        assert "data-plus-calendar" not in text
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg43" in base
    assert "playground.css?v=pg37" not in base
    assert "styles.css?v=main86" in base
    assert "mobile.css?v=mob105" in base
    assert "data-plus-calendar-phone-tabs" not in base
    first_bar = base.split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 2
    )[2].split("</nav>", 1)[0]
    assert 'href="/calendar"' in first_bar
    assert "path.startswith('/calendar')" in first_bar
    assert "data-plus-calendar-phone-tabs" not in first_bar


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


def _cookie(session: str, origin: str) -> list[dict]:
    return [
        {
            "name": SESSION_COOKIE_NAME,
            "value": session,
            "url": origin,
            "httpOnly": True,
            "secure": False,
            "sameSite": "Lax",
        }
    ]


def test_phone_plus_calendar_screen05_captures(
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

    mixed_app = _mu_app(tmp_path / "mixed")
    mixed_client = TestClient(mixed_app)
    _sign_in(mixed_client)
    _subscribe(mixed_client)
    day = _seed_mixed_due_today(mixed_client, monkeypatch)
    mixed_session = mixed_client.cookies.get(SESSION_COOKIE_NAME)

    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    empty_path = artifact_dir / "phone_plus_calendar_screen05_empty_390x844.png"
    mixed_path = artifact_dir / "phone_plus_calendar_screen05_390x844.png"
    selected_path = artifact_dir / "phone_plus_calendar_screen05_selected_day_390x844.png"
    desk_path = artifact_dir / "phone_plus_calendar_screen05_desktop_regression_1280.png"

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
        page.goto(f"{empty_origin}/calendar", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        empty_geo = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-calendar="desktop"]');
              const header = document.querySelector('.site-header');
              const tabs = document.querySelector('.mobile-tabbar');
              const tabLinks = tabs ? [...tabs.querySelectorAll('a.mobile-tab')] : [];
              const active = tabs && tabs.querySelector('.mobile-tab.is-active');
              const title = document.querySelector('.revisions-title');
              const month = document.querySelector('.revisions-month');
              const grid = document.querySelector('.calendar-grid');
              const mobile = document.querySelector('.revisions-mobile .cal-m-grid');
              const toolbar = document.querySelector('.cal-si-toolbar');
              const continueEl = document.querySelector('.cal-m-today-continue');
              const empty = document.querySelector('[data-today-list] .revisions-empty');
              const navBtn = document.querySelector('.cal-m-nav-btn');
              const todayCell = document.querySelector('.cal-m-cell.is-today');
              const selected = document.querySelector('.cal-m-cell.is-selected');
              const tabBox = tabs && tabs.getBoundingClientRect();
              const emptyBox = empty && empty.getBoundingClientRect();
              const navBox = navBtn && navBtn.getBoundingClientRect();
              const cellBox = todayCell && todayCell.getBoundingClientRect();
              return {
                present: Boolean(plus),
                plusDisplay: plus && getComputedStyle(plus).display,
                title: title && title.textContent.trim(),
                month: month && month.textContent.trim(),
                headerDisplay: header ? getComputedStyle(header).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                tabsPosition: tabs ? getComputedStyle(tabs).position : null,
                tabLabels: tabLinks.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabLinks.map((el) => el.getAttribute('href')),
                calendarActive: active && active.textContent.replace(/\\s+/g, ' ').trim(),
                dedicatedTabs: Boolean(document.querySelector('[data-plus-calendar-phone-tabs]')),
                gridDisplay: grid && getComputedStyle(grid).display,
                mobileGrid: Boolean(mobile) && getComputedStyle(mobile).display !== 'none',
                toolbarDisplay: toolbar ? getComputedStyle(toolbar).display : null,
                continuePresent: Boolean(continueEl),
                emptyText: empty && empty.textContent.trim(),
                emptyBottom: emptyBox && emptyBox.bottom,
                tabTop: tabBox && tabBox.top,
                navH: navBox && navBox.height,
                navW: navBox && navBox.width,
                cellH: cellBox && cellBox.height,
                selected: Boolean(selected),
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                hasNdps: /NDPS|Section 8|Article 19\\(1\\)\\(a\\)|Article 21/.test(
                  (document.querySelector('.revisions-mobile') || {}).innerText || ''
                ),
                screen: document.body.getAttribute('data-mscreen'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, empty_path)

        page.context.clear_cookies()
        page.context.add_cookies(_cookie(mixed_session, mixed_origin))
        page.goto(f"{mixed_origin}/calendar", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        mixed_geo = page.evaluate(
            """() => {
              const continueEl = document.querySelector('.cal-m-today-continue');
              const todayList = document.querySelector('[data-today-list]');
              const tabs = document.querySelector('.mobile-tabbar');
              const todayCell = document.querySelector('.cal-m-cell.is-today');
              const rows = [...document.querySelectorAll('[data-today-list] .revisions-row')];
              const continueBox = continueEl && continueEl.getBoundingClientRect();
              const tabBox = tabs && tabs.getBoundingClientRect();
              const todayBg = todayCell && getComputedStyle(todayCell).backgroundColor;
              const phone = document.querySelector('.revisions-mobile');
              return {
                continueHref: continueEl && continueEl.getAttribute('href'),
                continueText: continueEl && continueEl.textContent.replace(/\\s+/g, ' ').trim(),
                continueH: continueBox && continueBox.height,
                continueBottom: continueBox && continueBox.bottom,
                tabTop: tabBox && tabBox.top,
                todayListHidden: todayList && todayList.hidden,
                todayFilled: todayBg && todayBg !== 'rgba(0, 0, 0, 0)',
                rowHrefs: rows.map((el) => el.getAttribute('href')),
                rowText: rows.map((el) => el.innerText.replace(/\\s+/g, ' ').trim()),
                cardHasPlayground: /NDPS|Playground/.test(
                  (todayList && todayList.innerText) || ''
                ),
                phoneHasPlayground: Boolean(
                  phone && phone.querySelector('a[href*="/playground/"]')
                ),
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, mixed_path)

        other_iso = page.evaluate(
            """(today) => {
              const cells = [...document.querySelectorAll('.cal-m-cell[data-date]')];
              const hit = cells.find((c) => c.getAttribute('data-date') !== today);
              return hit ? hit.getAttribute('data-date') : today;
            }""",
            day.isoformat(),
        )
        page.locator(f'.cal-m-cell[data-date="{other_iso}"]').first.click()
        page.wait_for_timeout(200)
        selected_geo = page.evaluate(
            """() => {
              const selected = document.querySelector('.cal-m-cell.is-selected');
              const todayCell = document.querySelector('.cal-m-cell.is-today');
              const list = document.querySelector('.cal-m-daylist:not([hidden])');
              const todayList = document.querySelector('[data-today-list]');
              const continueEl = document.querySelector('.cal-m-today-continue');
              const selBg = selected && getComputedStyle(selected).backgroundColor;
              const todayBg = todayCell && getComputedStyle(todayCell).backgroundColor;
              const todayBorder = todayCell && getComputedStyle(todayCell).borderTopWidth;
              return {
                selectedIso: selected && selected.getAttribute('data-date'),
                todayIso: todayCell && todayCell.getAttribute('data-date'),
                selectedFilled: selBg && selBg !== 'rgba(0, 0, 0, 0)',
                todayDifferent: selBg !== todayBg,
                todayBorderPx: todayBorder ? parseFloat(todayBorder) : 0,
                listPosition: list ? getComputedStyle(list).position : null,
                listHidden: list ? list.hidden : null,
                todayHidden: todayList && todayList.hidden,
                continueInList: Boolean(
                  list && list.querySelector('.cal-m-today-continue')
                ),
                continueDisplay: continueEl ? getComputedStyle(continueEl).display : null,
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, selected_path)
        page.locator(f'.cal-m-cell[data-date="{other_iso}"]').first.click()
        page.wait_for_timeout(200)
        cleared = page.evaluate(
            """() => {
              const selected = document.querySelector('.cal-m-cell.is-selected');
              const todayList = document.querySelector('[data-today-list]');
              const list = document.querySelector('.cal-m-daylist:not([hidden])');
              return {
                selected: Boolean(selected),
                todayHidden: todayList && todayList.hidden,
                listOpen: Boolean(list),
              };
            }"""
        )

        page.set_viewport_size({"width": 390, "height": 700})
        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(80)
        short = page.evaluate(
            """() => {
              const continueEl = document.querySelector('.cal-m-today-continue');
              const tabs = document.querySelector('.mobile-tabbar');
              const cb = continueEl.getBoundingClientRect();
              const tb = tabs.getBoundingClientRect();
              return {
                continueBottom: cb.bottom,
                tabTop: tb.top,
                tabsFixed: getComputedStyle(tabs).position === 'fixed',
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
              };
            }"""
        )

        page.set_viewport_size({"width": 1280, "height": 800})
        page.goto(f"{mixed_origin}/calendar", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        desk_geo = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-calendar="desktop"]');
              const title = document.querySelector('.calendar-title');
              const filter = document.querySelector('[data-cal-filter]');
              const grid = document.querySelector('.calendar-grid');
              const panel = document.querySelector('[data-cal-panel]');
              const desk = document.querySelector('.cal-si-desk');
              const add = document.querySelector('[data-study-add]');
              const recall = document.querySelector('[data-cal-continue-recall]');
              const status = document.querySelector('.account-menu-btn-status');
              const tabs = document.querySelector('.mobile-tabbar');
              const header = document.querySelector('.site-header');
              const mobile = document.querySelector('.revisions-mobile');
              const gridBox = grid && grid.getBoundingClientRect();
              const panelBox = panel && panel.getBoundingClientRect();
              const deskStyle = desk && getComputedStyle(desk);
              const parseTracks = (value) => (value || '')
                .split(/\\s+/)
                .map((part) => parseFloat(part))
                .filter((n) => Number.isFinite(n));
              const deskTracks = parseTracks(deskStyle && deskStyle.gridTemplateColumns);
              const sources = [...document.querySelectorAll('.calendar-grid [data-cal-source]')].map(
                (el) => el.getAttribute('data-cal-source')
              );
              const navActive = document.querySelector('.PrimaryTabs--top .nav-link.is-active');
              const panelVisible = panel && getComputedStyle(panel).display !== 'none';
              return {
                present: Boolean(plus),
                title: title && title.textContent.trim(),
                filterOptions: filter && [...filter.options].map((o) => o.value),
                twoCol: Boolean(
                  gridBox && panelBox && panelVisible &&
                  panelBox.left >= gridBox.right - 1
                ),
                deskTrackCount: deskTracks.length,
                deskRail: deskTracks[1] || 0,
                addPresent: Boolean(add) && getComputedStyle(add).display !== 'none',
                continueHref: recall && recall.getAttribute('href'),
                sources,
                status: status && status.textContent.trim(),
                statusDisplay: status && getComputedStyle(status).display,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                mobileDisplay: mobile ? getComputedStyle(mobile).display : null,
                navActive: navActive && navActive.textContent.replace(/\\s+/g, ' ').trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, desk_path)
        context.close()
        browser.close()

    assert empty_geo["present"] is True
    assert empty_geo["plusDisplay"] not in (None, "none")
    assert empty_geo["title"] == "Calendar"
    assert empty_geo["month"] == empty_today.strftime("%B %Y")
    assert empty_geo["headerDisplay"] == "none"
    assert empty_geo["tabsDisplay"] != "none"
    assert empty_geo["tabsPosition"] == "fixed"
    assert empty_geo["tabLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert empty_geo["tabHrefs"] == [href for _, href in TAB_HREFS]
    assert empty_geo["calendarActive"] == "Calendar"
    assert empty_geo["dedicatedTabs"] is False
    assert empty_geo["gridDisplay"] == "none"
    assert empty_geo["mobileGrid"] is True
    assert empty_geo["toolbarDisplay"] == "none"
    assert empty_geo["continuePresent"] is False
    assert "Nothing due today" in (empty_geo["emptyText"] or "")
    assert empty_geo["emptyBottom"] <= empty_geo["tabTop"] + 8
    assert empty_geo["navH"] >= 44
    assert empty_geo["navW"] >= 44
    assert empty_geo["cellH"] >= 44
    assert empty_geo["selected"] is False
    assert empty_geo["overflow"] is False
    assert empty_geo["hasNdps"] is False
    assert empty_geo["screen"] == "revisions"

    assert mixed_geo["continueHref"] == "/dashboard"
    assert "Continue" in (mixed_geo["continueText"] or "")
    assert mixed_geo["continueH"] >= 44
    assert mixed_geo["continueBottom"] <= mixed_geo["tabTop"] + 8
    assert mixed_geo["todayListHidden"] is False
    assert mixed_geo["todayFilled"] is True
    assert any("/learn/" in (href or "") for href in mixed_geo["rowHrefs"])
    assert any("Day 15" in text for text in mixed_geo["rowText"])
    assert any("20(1)" in text or "20" in text for text in mixed_geo["rowText"])
    assert mixed_geo["cardHasPlayground"] is False
    assert mixed_geo["phoneHasPlayground"] is True
    assert mixed_geo["overflow"] is False

    assert selected_geo["selectedIso"] == other_iso
    assert selected_geo["todayIso"] == day.isoformat()
    assert selected_geo["selectedFilled"] is True
    if other_iso != day.isoformat():
        assert selected_geo["todayDifferent"] is True
        assert selected_geo["todayBorderPx"] >= 2
        assert selected_geo["todayHidden"] is True
    assert selected_geo["listPosition"] in ("static", "relative")
    assert selected_geo["listHidden"] is False
    assert selected_geo["continueInList"] is False
    assert selected_geo["overflow"] is False
    assert cleared["selected"] is False
    assert cleared["todayHidden"] is False
    assert cleared["listOpen"] is False

    assert short["tabsFixed"] is True
    assert short["continueBottom"] <= short["tabTop"] + 8
    assert short["overflow"] is False

    assert desk_geo["present"] is True
    assert desk_geo["title"]
    assert day.strftime("%B") in (desk_geo["title"] or "")
    assert desk_geo["filterOptions"] == ["all", "constitution", "playground", "my"]
    assert desk_geo["twoCol"] is True
    assert desk_geo["deskTrackCount"] == 2
    assert abs(desk_geo["deskRail"] - 380) <= 1
    assert desk_geo["addPresent"] is True
    assert desk_geo["continueHref"] == "/playground"
    assert "constitution" in (desk_geo["sources"] or [])
    assert "playground" in (desk_geo["sources"] or [])
    assert desk_geo["status"] == "RecallC Plus"
    assert desk_geo["statusDisplay"] != "none"
    assert desk_geo["tabsDisplay"] == "none"
    assert desk_geo["headerDisplay"] != "none"
    assert desk_geo["mobileDisplay"] == "none"
    assert "Calendar" in (desk_geo["navActive"] or "")

    for path in (empty_path, mixed_path, selected_path, desk_path):
        assert path.is_file() and path.stat().st_size > 1000
