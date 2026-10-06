"""Plus cohort desktop /dashboard Today Screen 08 (CTA map plus/08-screen).

Authorized: ChatGPT. Authenticated multiuser GET /dashboard with a real
active Plus EntitlementSnapshot. Revision-led mixed Constitution + Playground
path from the live dashboard view model. Guest, Free, Pro, phone, and Plus
Screens 01–07 stay on their own wrappers.
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
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
AUTH = ROOT / "src/constitution_memorizer/auth/routes.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
MANAGE = ROOT / "src/constitution_memorizer/web/templates/subscription_manage.html"
USER = UUID("11111111-1111-4111-8111-111111111111")
INVENTED = (
    "Premium",
    "Unlock all",
    "device limit",
    "replacement",
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


def test_plus_today_reaches_dashboard_with_today_selected(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    page = client.get("/dashboard")
    assert page.status_code == 200
    html = page.text
    header = _header(html)
    assert 'data-plus-today="desktop"' in html
    assert "data-signed-in-today" in html
    assert 'href="/dashboard" class="nav-link is-active"' in header
    assert ">Today<" in header
    assert "RecallC Plus" in header
    assert "Free account" not in header
    assert "Welcome, Sanjay." in html or "Good morning, Sanjay." in html


def test_plus_today_canonical_revision_path_uses_live_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _plus_client(tmp_path)
    day = _seed_canonical(client, monkeypatch, streak_days=3)
    html = unescape(client.get("/dashboard").text)
    assert 'data-today-mode="revision"' in html
    assert 'data-daily-goal-streak="3"' in html
    assert re.search(
        r'class="rc-streak-count">3</span>\s*<span class="rc-streak-suffix">-day streak</span>',
        html,
    )
    assert "4-day streak" not in html
    assert f"{day.strftime('%A')} {day.day} {day.strftime('%B')}" in html
    assert "revisions due" in html
    assert "Continue revision" in html or "Start revision" in html
    nodes = _path_nodes(html)
    assert len(nodes) >= 3
    sources = re.findall(r'data-today-source="([^"]+)"', "".join(nodes))
    statuses = re.findall(r'class="rc-path-node is-([^"]+)"', "".join(nodes))
    assert "done" in statuses
    assert "current" in statuses
    assert "upcoming" in statuses
    assert sources.index("playground") == statuses.index("current")
    current = _current_node(html)
    assert 'data-today-source="playground"' in current
    assert "Day 1 → 3 · Playground" in current
    href = re.search(r'<a class="rc-path-cta" href="([^"]+)"', current)
    assert href, current
    assert "/playground/" in unescape(href.group(1))
    assert "Start revision" in current or "Learn" in current
    constitution = [n for n in nodes if 'data-today-source="constitution"' in n]
    assert constitution
    for node in constitution:
        assert "/playground/" not in node
        if 'is-current' not in node:
            assert "rc-path-cta" not in node
    assert html.find("data-today-unit") < html.find('data-today-source="playground"')
    assert "New · Playground" in html
    assert "Section 8" in html
    assert "Article 20(1)" in html


def test_plus_today_left_card_uses_goal_and_revision_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _plus_client(tmp_path)
    _seed_canonical(client, monkeypatch)
    html = unescape(client.get("/dashboard").text)
    assert 'data-today-mode="revision"' in html
    frac = re.search(r'class="rc-goal-frac">(\d+)/(\d+)</span>', html)
    assert frac, html
    done, total = int(frac.group(1)), int(frac.group(2))
    assert done >= 1
    assert total >= done
    count = re.search(r'class="dash-due-count">(\d+)</span>', html)
    assert count
    assert int(count.group(1)) >= 1
    hero = html.split('data-today-mode="revision"', 1)[1].split("dash-path-card", 1)[0]
    if 'data-today-hero-cta' in hero:
        href = re.search(r'href="([^"]+)"[^>]*data-today-hero-cta', hero) or re.search(
            r'data-today-hero-cta[^>]*href="([^"]+)"', hero
        )
        assert href
        assert "/playground/" in unescape(href.group(1))
        assert 'action="/revision/start"' not in hero
    else:
        assert 'action="/revision/start"' in hero


def test_guest_free_pro_today_are_not_plus_screen_08(tmp_path: Path) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest")).get("/dashboard").text
    assert 'data-plus-today="desktop"' not in guest
    assert "RecallC Plus" not in _header(guest)
    assert "data-signed-in-today" not in guest

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/dashboard").text
    assert 'data-plus-today="desktop"' not in free_html
    assert "data-signed-in-today" in free_html
    assert "RecallC Plus" not in _header(free_html)

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/dashboard").text
    assert 'data-plus-today="desktop"' not in pro_html
    assert "RecallC Plus" not in _header(pro_html)


def test_plus_today_first_run_loading_error_markup_unchanged() -> None:
    dash = DASH.read_text(encoding="utf-8")
    assert 'data-today-mode="firstrun"' in dash
    assert 'dashboard_state == \'loading\'' in dash or 'state == \'loading\'' in dash
    assert 'state == \'data-error\'' in dash
    assert 'data-today-mode="learning"' in dash
    assert 'action="/revision/start"' in dash
    assert "dash-firstrun" in dash
    assert "Nothing due today" in dash
    assert "We couldn’t load today’s Recall" in dash or "couldn't load" in dash


def test_plus_today_marker_uses_shared_predicate() -> None:
    dash = DASH.read_text(encoding="utf-8")
    assert "plus_today" in dash
    assert 'data-plus-today="desktop"' in dash
    assert "data-signed-in-today" in dash
    auth = AUTH.read_text(encoding="utf-8")
    assert "request_is_active_plus" in auth
    assert 'ctx["plus_today"] = plus_today' in auth
    assert "def request_is_active_plus" in DEPS.read_text(encoding="utf-8")
    assert 'snapshot.tier == "plus"' in DEPS.read_text(encoding="utf-8")
    base = BASE.read_text(encoding="utf-8")
    assert "plus_today_chrome" in base
    assert "RecallC Plus" in base
    assert "playground.css?v=pg24" in base
    css = PG_CSS.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in css
    plus_css = css.split("plus/08-screen", 1)[-1]
    assert "var(--pg-teal)" in plus_css
    assert "var(--pg-teal-tint)" in plus_css
    assert "#0e7569" not in plus_css
    for phrase in INVENTED:
        assert phrase not in dash, phrase


def test_plus_today_does_not_touch_accepted_screens() -> None:
    assert "data-plus-today" not in LANDING.read_text(encoding="utf-8")
    assert "data-plus-today" not in BROWSE.read_text(encoding="utf-8")
    assert "data-plus-today" not in LAWS.read_text(encoding="utf-8")
    assert "data-plus-today" not in BARE.read_text(encoding="utf-8")
    assert "data-plus-today" not in ADD.read_text(encoding="utf-8")
    assert "data-plus-today" not in HOME.read_text(encoding="utf-8")
    assert "data-plus-today" not in GATE.read_text(encoding="utf-8")
    assert "data-plus-today" not in MANAGE.read_text(encoding="utf-8")
    assert 'data-plus-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-plus-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-plus-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-plus-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-plus-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-plus-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-plus-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-plus-today" not in mobile
    phone_cta = mobile.split(
        "body[data-mscreen=\"today\"] .rc-path-node.is-current .rc-path-cta {", 1
    )[1].split("}", 1)[0]
    assert "width: 100%" in phone_cta
    assert "min-height: 44px" in phone_cta


def test_screen_06_start_learning_with_zero_sections_reaches_picker(
    tmp_path: Path,
) -> None:
    client = _plus_client(tmp_path)
    added = _confirm_add(client, "ndps")
    assert added.status_code == 303
    home = unescape(client.get("/playground").text)
    assert "Start learning" in home
    href = sections_path("ndps")
    assert href in home
    picker = client.get(href)
    assert picker.status_code == 200
    text = unescape(picker.text)
    assert "Choose what to learn" in text
    assert 'data-pg-picker' in picker.text
    assert f'action="{href}"' in picker.text
    learn = client.get("/playground/laws/ndps/sections/8/learn/read", follow_redirects=False)
    assert learn.status_code in {303, 400}
    if learn.status_code == 303:
        assert href in learn.headers["location"]
    today = unescape(client.get("/dashboard").text)
    assert 'data-today-source="playground"' not in today


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


def test_plus_today_1280(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    shot_path = artifact_dir / "plus_today_screen08_1280.png"
    learning_path = artifact_dir / "plus_today_screen08_learning_1280.png"
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
              const greeting = document.querySelector('.dash-hello');
              const streak = document.querySelector('.rc-streak');
              const hero = document.querySelector('[data-today-mode="revision"]');
              const path = document.querySelector('[data-today-path-card]');
              const current = document.querySelector('.rc-path-node.is-current');
              const status = document.querySelector('.account-menu-btn-status');
              const nodes = [...document.querySelectorAll('.rc-path-node')];
              const first = hero && hero.getBoundingClientRect();
              const pathBox = path && path.getBoundingClientRect();
              return {
                present: Boolean(plus),
                greeting: greeting && greeting.textContent.trim(),
                streak: streak && streak.innerText.replace(/\\s+/g, ' ').trim(),
                streakDisplay: streak && getComputedStyle(streak).display,
                revision: Boolean(hero),
                path: Boolean(path),
                twoCol: Boolean(first && pathBox && Math.abs(first.y - pathBox.y) < 80 && pathBox.x > first.x),
                currentSource: current && current.getAttribute('data-today-source'),
                currentHref: current && (current.querySelector('.rc-path-cta') || {}).href || '',
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
        assert geo["present"] is True
        assert geo["greeting"] == "Good morning, Sanjay."
        assert geo["streakDisplay"] != "none"
        assert "streak" in (geo["streak"] or "").lower()
        assert geo["revision"] is True
        assert geo["path"] is True
        assert geo["twoCol"] is True
        assert geo["currentSource"] == "playground"
        assert "/playground/" in (geo["currentHref"] or "")
        assert "playground" in (geo["sources"] or [])
        assert "constitution" in (geo["sources"] or [])
        assert geo["status"] == "RecallC Plus"
        assert geo["statusDisplay"] != "none"
        assert "Today" in (geo["navActive"] or "")
        assert shot_path.exists() and shot_path.stat().st_size > 1000

        page.set_viewport_size({"width": 390, "height": 844})
        phone = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-today="desktop"]');
              const panel = document.querySelector('.dashboard-panel');
              return {
                plusDisplay: plus && getComputedStyle(plus).display,
                panelDisplay: panel && getComputedStyle(panel).display,
                today: document.body.getAttribute('data-mscreen'),
              };
            }"""
        )
        assert phone["plusDisplay"] != "none"
        assert phone["panelDisplay"] != "none"
        assert phone["today"] == "today"

        page.set_viewport_size({"width": 1280, "height": 800})
        learn_app = _mu_app(tmp_path / "learn", display_name="Sanjay")
        learn_client = TestClient(learn_app)
        _sign_in(learn_client)
        _subscribe(learn_client)
        eng = learn_client.app.state.engine.for_user(USER)
        today = user_today(eng)
        eng.repo.upsert_progress(
            USER,
            unit_id="clause-1",
            status="review",
            times_completed=1,
            last_completed=today - timedelta(days=8),
            next_revision=today + timedelta(days=8),
            interval_days=7,
        )
        eng._invalidate_progress_cache()
        learn_session = learn_client.cookies.get(SESSION_COOKIE_NAME)
        learn_port, _learn_server = _serve(learn_app)
        learn_origin = f"http://127.0.0.1:{learn_port}"
        context.clear_cookies()
        context.add_cookies(
            [
                {
                    "name": SESSION_COOKIE_NAME,
                    "value": learn_session,
                    "url": learn_origin,
                    "httpOnly": True,
                    "secure": False,
                    "sameSite": "Lax",
                }
            ]
        )
        page.goto(f"{learn_origin}/dashboard", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        learning = page.evaluate(
            """() => {
              const plus = document.querySelector('[data-plus-today="desktop"]');
              const revision = document.querySelector('[data-today-mode="revision"]');
              const learning = document.querySelector('[data-today-mode="learning"]');
              return {
                present: Boolean(plus),
                revision: Boolean(revision),
                learning: Boolean(learning),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(learning_path), full_page=False)
        assert learning["present"] is True
        assert learning["revision"] is False
        assert learning["learning"] is True
        assert learning_path.exists() and learning_path.stat().st_size > 1000
        context.close()
        browser.close()
