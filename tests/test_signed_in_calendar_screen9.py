"""Signed-in desktop Calendar Screen 09 (CTA map signedIn/09-screen).

Authorized: ChatGPT. Authenticated multiuser GET /calendar desktop only.
Phone Calendar, Gate, and accepted screens 01–06 / 08 stay unchanged.
Copy, routes, and calendar state stay existing. Playground and study rows
are not fabricated for a non-subscriber.
"""

from __future__ import annotations

import socket
import threading
import time
from datetime import date, timedelta
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

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
USER = UUID("11111111-1111-4111-8111-111111111111")


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
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        study_materials_dir=tmp_path / "study-materials",
    )


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    assert client.cookies.get(SESSION_COOKIE_NAME)


def _engine(client: TestClient) -> ReminderEngine:
    engine = client.app.state.engine
    store = getattr(client.app.state, "session_store", None)
    sessions = getattr(store, "_sessions", None) if store is not None else None
    if sessions:
        newest = sorted(sessions.values(), key=lambda s: s.created_at)[-1]
        return engine.for_user(newest.user.id)
    return engine


def _make_due(client: TestClient, unit_ids: list[str]) -> None:
    eng = _engine(client)
    today = date.today()
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


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def test_signed_in_free_calendar_marks_desktop_surface(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/calendar").text
    assert "data-signed-in-calendar" in html
    header = _header(html)
    assert 'href="/playground"' in header
    assert 'href="/browse"' in header
    assert 'href="/dashboard"' in header
    assert 'href="/profile"' in header
    assert 'class="nav-link is-active"' in header
    assert 'aria-current="page"' in header
    assert ">Calendar<" in header
    assert "Study archive" not in html
    assert "calDesign" not in html
    assert 'aria-label="View"' in html
    assert "Month" in html
    assert "Week" in html
    assert "data-cal-filter" in html
    assert ">All<" in html
    assert ">Constitution<" in html
    assert ">Playground<" in html
    assert ">My material<" in html
    assert "Add task" in html
    assert 'href="/playground"' in html.split("data-cal-continue-recall", 1)[1][:80]
    assert "Continue today’s Recall" in html or "Continue today's Recall" in html
    assert "NDPS" not in html
    assert "Section 8" not in html
    assert "Bhagavad Gita" not in html
    phone = html.split("revisions-mobile", 1)[1].split("calendar-header", 1)[0]
    assert "cal-m-grid" in phone
    assert "data-cal-filter" not in phone
    assert "Add task" not in phone
    gate = client.get("/playground", follow_redirects=False)
    assert gate.status_code == 200
    assert 'data-playground-gate="not_subscribed"' in gate.text


def test_signed_in_free_calendar_filters_and_real_path(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _make_due(client, ["clause-1"])
    html = client.get("/calendar").text
    assert 'data-today-source="playground"' not in html
    assert 'data-cal-source="constitution"' in html
    assert "Article 20" in html or "clause-1" in html or "Art " in html
    week = client.get("/calendar?view=week")
    assert week.status_code == 200
    assert "data-calendar-week" in week.text
    assert 'class="calendar-view-btn is-on"' in week.text
    today = date.today()
    nxt = client.get(f"/calendar?year={today.year}&month={today.month}")
    assert nxt.status_code == 200
    token = html.split('data-study-token="', 1)[1].split('"', 1)[0]
    studied = (date.today() - timedelta(days=3)).isoformat()
    create = client.post(
        "/api/study-materials",
        data={
            "title": "Real notes",
            "studied_on": studied,
            "activity": "Studied",
            "notes": "From the editor",
        },
        headers={"X-Study-Token": token},
    )
    assert create.status_code == 200, create.text
    entry = create.json()
    after = client.get("/calendar").text
    assert "Real notes" in after
    assert "Bhagavad Gita" not in after
    assert "NDPS" not in after
    detail = client.get(f"/api/study-materials/{entry['id']}")
    assert detail.status_code == 200
    assert detail.json()["notes"] == "From the editor"
    due = next(
        r for r in entry["reviews"] if r["due_on"] <= date.today().isoformat()
    )
    mark = client.post(
        f"/api/study-materials/{entry['id']}/reviews/{due['offset']}",
        data={"done": "true"},
        headers={"X-Study-Token": token},
    )
    assert mark.status_code == 200
    marked = next(r for r in mark.json()["reviews"] if r["offset"] == due["offset"])
    assert marked["completed_on"] == date.today().isoformat()
    undo = client.post(
        f"/api/study-materials/{entry['id']}/reviews/{due['offset']}",
        data={"done": "false"},
        headers={"X-Study-Token": token},
    )
    assert undo.status_code == 200
    undone = next(r for r in undo.json()["reviews"] if r["offset"] == due["offset"])
    assert undone["completed_on"] is None
    older = client.post(
        "/api/study-materials",
        data={
            "title": "Older notes",
            "studied_on": (date.today() - timedelta(days=10)).isoformat(),
            "activity": "Studied",
        },
        headers={"X-Study-Token": token},
    )
    assert older.status_code == 200, older.text
    overdue_page = client.get("/calendar").text
    assert "Older notes" in overdue_page
    assert "data-cal-overdue" in overdue_page
    assert "overdue revision" in overdue_page
    assert "Mark revised" in overdue_page


def test_signed_in_calendar_does_not_touch_accepted_screens() -> None:
    cal = CAL.read_text(encoding="utf-8")
    assert "data-signed-in-calendar" in cal
    assert "Study archive" not in cal
    assert 'href="/playground"' in cal
    assert "Add task" in cal
    assert "data-cal-filter" in cal
    assert "NDPS Act" not in cal
    assert "September 2026" not in cal
    phone = cal.split("revisions-mobile", 1)[1].split("calendar-header", 1)[0]
    assert 'href="/dashboard"' in phone
    assert "data-cal-filter" not in phone

    assert "data-signed-in-calendar" not in DASH.read_text(encoding="utf-8")
    assert "data-signed-in-today" in DASH.read_text(encoding="utf-8")
    assert "data-signed-in-calendar" not in ADD.read_text(encoding="utf-8")
    assert "data-signed-in-calendar" not in HOME.read_text(encoding="utf-8")
    assert "data-signed-in-calendar" not in GATE.read_text(encoding="utf-8")
    assert "data-signed-in-pg-gate" in GATE.read_text(encoding="utf-8")
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-guest-landing="desktop"' in landing
    assert "data-signed-in-browse-strip" in BROWSE.read_text(encoding="utf-8")
    assert "data-signed-in-laws-desktop" in LAWS.read_text(encoding="utf-8")
    assert "data-signed-in-bareact-desktop" in BARE.read_text(encoding="utf-8")

    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-signed-in-calendar" not in mobile
    assert "cal-si-toolbar" not in mobile
    phone_cal = mobile.split(
        'body[data-mscreen="revisions"] .calendar-grid,', 1
    )[1].split("}", 1)[0]
    assert "display: none" in phone_cal

    pg_css = PG_CSS.read_text(encoding="utf-8")
    signed_gate_title = pg_css.split(
        ".PlaygroundShell .EntitlementGate[data-signed-in-pg-gate] h1 {", 1
    )[1].split("}", 1)[0]
    assert "font-size: 28px" in signed_gate_title

    css = STYLES.read_text(encoding="utf-8")
    r1 = css.split("/* R1 desktop shell", 1)[1].split(
        "/* Signed-in desktop Today", 1
    )[0]
    assert "position: absolute" not in r1
    signed_cal = css.split("/* Signed-in desktop Calendar", 1)[1]
    assert "position: absolute" not in signed_cal.split("/* R7 closeout", 1)[0]
    assert "grid-template-columns: minmax(0, 1fr) 380px" in signed_cal
    today = css.split("/* Signed-in desktop Today", 1)[1].split(
        "/* Signed-in desktop Calendar", 1
    )[0]
    assert "minmax(260px, 380px)" in today
    assert "height: 48px" in today


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


def test_signed_in_calendar_1280_and_phone(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _make_due(client, ["clause-1", "clause-2"])
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "signed_in_calendar_screen9_1280.png"
    panel_path = artifact_dir / "signed_in_calendar_screen9_day_panel_1280.png"
    viewer_path = artifact_dir / "signed_in_calendar_screen9_viewer_1280.png"
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
        page.goto(f"{origin}/calendar", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-signed-in-calendar]');
              const nav = document.querySelector('.PrimaryTabs--top');
              const calendar = nav && [...nav.querySelectorAll('.nav-link')].find(
                (el) => (el.textContent || '').trim() === 'Calendar'
              );
              const playground = nav && [...nav.querySelectorAll('.nav-link')].find(
                (el) => (el.textContent || '').trim() === 'Playground'
              );
              const month = [...document.querySelectorAll('.calendar-view-btn')].find(
                (el) => (el.textContent || '').trim() === 'Month'
              );
              const week = [...document.querySelectorAll('.calendar-view-btn')].find(
                (el) => (el.textContent || '').trim() === 'Week'
              );
              const filter = document.querySelector('[data-cal-filter]');
              const add = document.querySelector('[data-study-add]');
              const plus = document.querySelector('[data-study-date]');
              const grid = document.querySelector('.calendar-grid');
              const side = document.querySelector('[data-cal-panel]');
              const design = (document.body.innerText || '').includes('Study archive');
              const ndps = /NDPS|Section 8|Bhagavad Gita/.test(document.body.innerText || '');
              const titleBox = grid && grid.getBoundingClientRect();
              const sideBox = side && side.getBoundingClientRect();
              const todayActive = calendar && (
                calendar.classList.contains('is-active') ||
                calendar.getAttribute('aria-current') === 'page'
              );
              return {
                present: Boolean(panel),
                calendarActive: todayActive,
                playgroundHref: playground && playground.getAttribute('href'),
                monthHref: month && month.getAttribute('href'),
                weekHref: week && week.getAttribute('href'),
                filterOptions: filter && [...filter.options].map((o) => o.value),
                addPresent: Boolean(add),
                plusPresent: Boolean(plus),
                twoCol: Boolean(
                  titleBox && sideBox && sideBox.left > titleBox.right - 8
                ),
                designToggle: design,
                hasNdps: ndps,
                continueHref: document.querySelector('[data-cal-continue-recall]')
                  && document.querySelector('[data-cal-continue-recall]').getAttribute('href'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        today_iso = date.today().isoformat()
        other_iso = page.evaluate(
            """(today) => {
              const cells = [...document.querySelectorAll('.calendar-grid .calendar-cell[data-date]')];
              const hit = cells.find((c) => (
                c.getAttribute('data-date') !== today && c.querySelector('[data-cal-source]')
              ));
              return hit ? hit.getAttribute('data-date') : today;
            }""",
            today_iso,
        )
        page.locator(f'.calendar-grid .calendar-cell[data-date="{other_iso}"]').first.click()
        page.wait_for_timeout(200)
        panel_iso = page.evaluate(
            """() => {
              const shown = document.querySelector('[data-cal-panel-day]:not([hidden])');
              const recall = document.querySelector('[data-cal-continue-recall]');
              return {
                iso: shown && shown.getAttribute('data-cal-panel-day'),
                continueDisplay: recall ? getComputedStyle(recall).display : null,
              };
            }"""
        )
        page.screenshot(path=str(panel_path), full_page=False)

        page.locator("[data-cal-filter]").select_option("constitution")
        filter_state = page.evaluate(
            """() => {
              const hiddenVisually = (sel) => [...document.querySelectorAll(sel)].every(
                (el) => getComputedStyle(el).display === 'none'
              );
              return {
                myHidden: hiddenVisually('[data-cal-source="my"]') || !document.querySelector('[data-cal-source="my"]'),
                pgHidden: hiddenVisually('[data-cal-source="playground"]') || !document.querySelector('[data-cal-source="playground"]'),
                constitutionVisible: [...document.querySelectorAll('[data-cal-source="constitution"]')].some(
                  (el) => getComputedStyle(el).display !== 'none'
                ),
              };
            }"""
        )
        page.locator("[data-cal-filter]").select_option("all")

        page.locator("[data-study-add]").click()
        page.wait_for_selector("#cal-si-editor", state="visible", timeout=4000)
        editor_open = page.evaluate(
            """() => {
              const d = document.getElementById('cal-si-editor');
              return Boolean(d && d.open);
            }"""
        )
        page.locator("#cal-si-editor [data-study-close]").first.click()

        plus = page.locator(f'.cal-si-cell-add[data-study-date="{today_iso}"]')
        if plus.count():
            plus.first.click()
            page.wait_for_selector("#cal-si-editor", state="visible", timeout=4000)
            plus_open = page.evaluate(
                """() => {
                  const d = document.getElementById('cal-si-editor');
                  const dateEl = document.querySelector('#cal-si-form [name=studied_on]');
                  return {
                    open: Boolean(d && d.open),
                    date: dateEl && dateEl.value,
                  };
                }"""
            )
            page.locator("#cal-si-editor [data-study-close]").first.click()
        else:
            plus_open = {"open": False, "date": None}

        token = (
            client.get("/calendar").text.split('data-study-token="', 1)[1].split('"', 1)[0]
        )
        created = client.post(
            "/api/study-materials",
            data={
                "title": "Real notes",
                "studied_on": (date.today() - timedelta(days=10)).isoformat(),
                "activity": "Studied",
                "notes": "From the editor",
            },
            headers={"X-Study-Token": token},
        )
        assert created.status_code == 200, created.text
        page.goto(f"{origin}/calendar", wait_until="networkidle")
        overdue = page.locator("[data-cal-overdue]")
        assert overdue.count()
        assert overdue.first.get_attribute("open") is None
        overdue.locator("summary").click()
        page.wait_for_timeout(150)
        overdue_open = page.evaluate(
            "() => Boolean(document.querySelector('[data-cal-overdue]').open)"
        )
        overdue.locator("summary").click()
        page.wait_for_timeout(150)
        overdue_closed = page.evaluate(
            "() => Boolean(document.querySelector('[data-cal-overdue]').open)"
        )

        page.locator(".calendar-chip.is-study", has_text="Real notes").first.click()
        page.wait_for_selector("#cal-si-viewer", state="visible", timeout=4000)
        viewer_open = page.evaluate(
            """() => {
              const d = document.getElementById('cal-si-viewer');
              const title = document.getElementById('cal-si-view-title');
              return {
                open: Boolean(d && d.open),
                title: title && title.textContent,
                notes: (document.getElementById('cal-si-notes') || {}).textContent,
              };
            }"""
        )
        page.screenshot(path=str(viewer_path), full_page=False)
        page.locator("#cal-si-viewer [data-study-close]").first.click()
        page.wait_for_function("() => !document.getElementById('cal-si-viewer')?.open")

        page.locator("[data-cal-overdue] summary").click()
        page.locator("[data-cal-overdue] .cal-si-mark").first.click()
        page.wait_for_selector("#cal-si-toast:not([hidden])", timeout=8000)
        toast_text = page.locator("[data-cal-toast-text]").inner_text()
        page.locator("[data-cal-toast-dismiss]").click()
        toast_dismissed = page.evaluate(
            "() => Boolean(document.getElementById('cal-si-toast').hidden)"
        )

        page.locator(".PrimaryTabs--top .nav-link", has_text="Playground").click()
        page.wait_for_url("**/playground**", timeout=8000)
        playground_html = page.content()
        playground_path = page.evaluate("() => location.pathname")

        page.goto(f"{origin}/calendar", wait_until="networkidle")
        page.locator("[data-cal-continue-recall]").click()
        page.wait_for_url("**/playground**", timeout=8000)
        recall_path = page.evaluate("() => location.pathname")
        recall_html = page.content()

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/calendar", wait_until="networkidle")
        phone_geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-signed-in-calendar]');
              const toolbar = document.querySelector('.cal-si-toolbar');
              const grid = document.querySelector('.calendar-grid');
              const mobile = document.querySelector('.revisions-mobile');
              return {
                present: Boolean(panel),
                toolbarDisplay: toolbar ? getComputedStyle(toolbar).display : null,
                gridDisplay: grid ? getComputedStyle(grid).display : null,
                mobileDisplay: mobile ? getComputedStyle(mobile).display : null,
              };
            }"""
        )
        browser.close()

    assert geo["present"] is True
    assert geo["calendarActive"] is True
    assert geo["playgroundHref"] == "/playground"
    assert geo["weekHref"] and "view=week" in geo["weekHref"]
    assert geo["filterOptions"] == ["all", "constitution", "playground", "my"]
    assert geo["addPresent"] is True
    assert geo["plusPresent"] is True
    assert geo["twoCol"] is True
    assert geo["designToggle"] is False
    assert geo["hasNdps"] is False
    assert geo["continueHref"] == "/playground"
    assert panel_iso["iso"] == other_iso
    if other_iso != today_iso:
        assert panel_iso["continueDisplay"] == "none"
    assert filter_state["myHidden"] is True
    assert filter_state["pgHidden"] is True
    assert overdue_open is True
    assert overdue_closed is False
    assert viewer_open["open"] is True
    assert viewer_open["title"] == "Real notes"
    assert "From the editor" in (viewer_open["notes"] or "")
    assert "Marked revised" in toast_text
    assert toast_dismissed is True
    assert editor_open is True
    assert plus_open["open"] is True
    assert plus_open["date"] == today_iso
    assert playground_path.rstrip("/") == "/playground"
    assert 'data-playground-gate="not_subscribed"' in playground_html
    assert recall_path.rstrip("/") == "/playground"
    assert 'data-playground-gate="not_subscribed"' in recall_html
    assert phone_geo["present"] is True
    assert phone_geo["toolbarDisplay"] == "none"
    assert phone_geo["gridDisplay"] == "none"
    assert phone_geo["mobileDisplay"] != "none"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
    assert panel_path.is_file()
    assert viewer_path.is_file()
    assert viewer_path.stat().st_size > 1000
