"""Plus cohort desktop Playground-home Screen 06 (CTA map plus/06-screen).

Authorized: ChatGPT. Authenticated multiuser GET /playground with a real
active Plus EntitlementSnapshot. Same home architecture for empty (0/10)
and populated rosters. Guest intro, signed-in Free Gate, Pro home, phone,
and Plus Screens 01–05 stay on their own wrappers.
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
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.roster.period import (
    playground_month_bounds,
    playground_month_name,
)
from constitution_memorizer.playground.urls import roster_next_path, roster_path
from constitution_memorizer.playground.view import BROWSE_LAWS_PATH, sections_selected_copy
from constitution_memorizer.web.app import create_app
from tests.conftest import PLAYGROUND_TEST_NOW

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
PARTIALS = ROOT / "src/constitution_memorizer/web/templates/partials/playground.html"
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
ROUTES = ROOT / "src/constitution_memorizer/playground/routes.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
USER = UUID("11111111-1111-4111-8111-111111111111")
MONTH = playground_month_name(playground_month_bounds(PLAYGROUND_TEST_NOW)[0])
INVENTED = (
    "Premium",
    "Unlimited",
    "renews",
    "Unlock all",
    "Free plan",
    "device limit",
    "replacement",
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


def _seed_roster(client: TestClient, *law_ids: str) -> None:
    roster = client.app.state.roster
    start, end = playground_month_bounds()
    roster._repo.ensure_period(
        USER,
        period_start=start,
        period_end=end,
        tier_snapshot="plus",
        law_limit=10,
    )
    for law_id in law_ids:
        result = roster._repo.consume_law(
            USER,
            period_start=start,
            law_id=law_id,
            law_limit=10,
            allow_new=True,
        )
        assert result.ok, result.status
        assert roster.is_law_active_this_period(USER, law_id) is True


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _aside(html: str) -> str:
    chunk = html.split('class="pg-aside"', 1)[1]
    return chunk.split("</aside>", 1)[0]


def test_sections_selected_copy_is_roster_counts() -> None:
    assert sections_selected_copy(selected=12, learned=8) == "12 sections selected · 8 learned"
    assert sections_selected_copy(selected=1, learned=0) == "1 section selected · 0 learned"
    assert sections_selected_copy(selected=0, learned=0) == "0 sections selected · 0 learned"


def test_plus_empty_home_uses_month_capacity_and_browse_path(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    html = unescape(client.get("/playground").text)
    assert 'data-plus-playground="desktop"' in html
    assert "data-signed-in-pg-gate" not in html
    assert "data-guest-pg-intro" not in html
    header = _header(html)
    assert "RecallC Plus" in header
    assert "Free account" not in header
    assert f'plus-pg-month plus-pg-desk-only">{MONTH}</h1>' in html
    assert f"Your {MONTH} Playground is empty" in html
    assert "Add laws you want to learn this month." in html
    assert f'href="{BROWSE_LAWS_PATH}"' in html
    assert BROWSE_LAWS_PATH == "/laws"
    assert ">Browse laws<" in html
    assert "0 of 10 laws" in html
    assert "10 spaces available" in html
    assert html.count('class="RosterCapacity"') == 1
    aside = _aside(html)
    assert "0 of 10 laws" in aside
    assert ">Browse laws<" in aside
    assert f">Manage {MONTH}<" in aside
    assert "Verbatim, always." in aside
    assert "LawCard" not in html
    assert "Due today" not in html
    assert "Overdue" not in html
    assert "Unlock Playground" not in html
    assert ">View Playground plans<" not in html
    for phrase in INVENTED:
        assert phrase not in html.split("PlaygroundShell", 1)[-1], phrase


def test_plus_populated_home_uses_same_architecture(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    _seed_roster(client, "ndps", "bns", "bnss", "mtp")
    html = unescape(client.get("/playground").text)
    assert 'data-plus-playground="desktop"' in html
    assert f'plus-pg-month plus-pg-desk-only">{MONTH}</h1>' in html
    assert "My Playground" in html
    assert "4 of 10 laws" in html
    assert "6 spaces available" in html
    assert html.count('class="RosterCapacity"') == 1
    assert f"Your {MONTH} Playground is empty" not in html
    assert "Due today" in html
    assert "Overdue" in html
    assert "Sections learned" in html
    assert "To learn" not in html.split("pg-home-tiles", 1)[-1].split("pg-section-head", 1)[0]
    assert "In Playground this month" in html
    assert 'data-law-id="ndps"' in html
    assert 'data-law-id="bns"' in html
    assert 'data-law-id="bnss"' in html
    assert 'data-law-id="mtp"' in html
    assert "Read Bare Act" in html
    assert ">Manage<" in html
    assert "Start learning" in html or "Continue" in html
    assert "0 sections selected · 0 learned" in html
    aside = _aside(html)
    assert "4 of 10 laws" in aside
    assert f'href="{BROWSE_LAWS_PATH}"' in aside
    assert ">Browse laws<" in aside
    assert f">Manage {MONTH}<" in aside
    assert "Verbatim, always." in aside
    assert "Plan next month" in html
    assert roster_path() in html
    assert roster_next_path() in html
    assert "Removed this month" in HOME.read_text(encoding="utf-8")
    assert "Saved progress" in HOME.read_text(encoding="utf-8")


def test_plus_home_preserves_removed_saved_and_plan_next(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    _seed_roster(client, "ndps", "bns")
    start, _end = playground_month_bounds()
    removed = client.app.state.roster._repo.remove_law(
        USER, period_start=start, law_id="bns"
    )
    assert removed is not None
    assert removed.removed_at is not None
    html = unescape(client.get("/playground").text)
    assert 'data-law-id="ndps"' in html
    assert 'data-law-id="bns"' in html
    assert "Removed this month" in html
    assert "2 of 10 laws" in html
    assert "Plan next month" in html
    assert roster_next_path() in html


def test_halted_expired_pro_free_guest_are_not_plus_screen_06(tmp_path: Path) -> None:
    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/playground").text
    assert 'data-halted-playground="desktop"' in halted_html
    assert 'data-plus-playground="desktop"' not in halted_html
    assert "RecallC Plus" not in _header(halted_html)

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(expired, status="expired")
    expired_html = expired.get("/playground").text
    assert 'data-plus-playground="desktop"' not in expired_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/playground").text
    assert 'data-plus-playground="desktop"' not in pro_html
    assert "RecallC Plus" not in _header(pro_html)
    assert 'class="pg-home-title">Playground</h1>' in pro_html or ">Playground<" in pro_html
    assert "To learn" in pro_html or "Your September Playground is empty" in pro_html
    assert pro_html.count('class="RosterCapacity"') == 2

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/playground").text
    assert 'data-plus-playground="desktop"' not in free_html
    assert "data-signed-in-pg-gate" in free_html
    assert ">Unlock Playground<" in free_html

    guest = TestClient(_mu_app(tmp_path / "guest")).get("/playground").text
    assert 'data-plus-playground="desktop"' not in guest
    assert "data-guest-pg-intro" in guest


def test_plus_playground_marker_uses_shared_predicate() -> None:
    home = HOME.read_text(encoding="utf-8")
    assert "plus_playground" in home
    assert 'data-plus-playground="desktop"' in home
    assert "pg-home-empty" in home
    assert "plus-pg-month" in home
    assert "Overdue" in home
    assert "Sections learned" in home
    assert f'href="{{{{ home.browse_href }}}}"' in home
    assert "Removed this month" in home
    assert "Saved progress" in home
    assert "Plan next month" in home
    partials = PARTIALS.read_text(encoding="utf-8")
    assert "sections_copy" in partials
    assert "plus=false" in partials
    base = BASE.read_text(encoding="utf-8")
    assert "plus_playground" in base
    assert "path.rstrip('/') == '/playground'" in base
    assert "RecallC Plus" in base
    assert "playground.css?v=pg28" in base
    deps = DEPS.read_text(encoding="utf-8")
    assert "def request_is_active_plus" in deps
    assert 'snapshot.tier == "plus"' in deps
    routes = ROUTES.read_text(encoding="utf-8")
    assert "request_is_active_plus" in routes
    assert '"plus_playground": request_is_active_plus(request)' in routes
    view = VIEW.read_text(encoding="utf-8")
    assert "def sections_selected_copy" in view
    assert "overdue" in view
    css = PG_CSS.read_text(encoding="utf-8")
    assert 'data-plus-playground="desktop"' in css
    assert "plus-pg-month" in css
    assert "plus-pg-desk-only" in css
    styles = STYLES.read_text(encoding="utf-8")
    assert ":has([data-plus-playground])" in styles
    assert "data-plus-playground" not in GATE.read_text(encoding="utf-8")
    assert "data-plus-playground" not in ADD.read_text(encoding="utf-8")
    assert "data-plus-playground" not in LANDING.read_text(encoding="utf-8")
    assert "data-plus-playground" not in BROWSE.read_text(encoding="utf-8")
    assert "data-plus-playground" not in LAWS.read_text(encoding="utf-8")
    assert "data-plus-playground" not in BARE.read_text(encoding="utf-8")
    for phrase in ("Premium", "Unlimited", "renews"):
        assert phrase not in home


def test_plus_playground_does_not_touch_accepted_screens() -> None:
    assert 'data-plus-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-plus-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-plus-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert "data-plus-browse" in BROWSE.read_text(encoding="utf-8")
    assert "data-plus-landing" in LANDING.read_text(encoding="utf-8")
    assert "data-signed-in-pg-gate" in GATE.read_text(encoding="utf-8")
    assert "data-guest-pg-intro" not in HOME.read_text(encoding="utf-8")


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


def test_plus_playground_1280_empty_and_populated(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    empty_path = artifact_dir / "plus_playground_screen06_empty_1280.png"
    shot_path = artifact_dir / "plus_playground_screen06_1280.png"
    origin = f"http://127.0.0.1:{port}"

    def _open(path: str, *, height: int = 1100):
        browser_ctx = sync_playwright().start()
        browser = browser_ctx.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 1280, "height": height}, device_scale_factor=1
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
        page.goto(f"{origin}{path}", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        return browser_ctx, browser, context, page

    browser_ctx, browser, context, page = _open("/playground", height=800)
    empty_geo = page.evaluate(
        """() => {
          const desk = document.querySelector('[data-plus-playground="desktop"]');
          const gate = document.querySelector('[data-signed-in-pg-gate]');
          const guest = document.querySelector('[data-guest-pg-intro]');
          const month = document.querySelector('.plus-pg-month');
          const empty = document.querySelector('.pg-home-empty');
          const aside = document.querySelector('.pg-aside');
          const cap = document.querySelector('.RosterCapacity');
          const browse = aside && aside.querySelector('.pg-btn');
          const tiles = document.querySelector('.pg-home-tiles');
          const status = document.querySelector('.account-menu-btn-status');
          const prodTitle = document.querySelector('.pg-home-title.plus-pg-desk-hide');
          const csMonth = month && getComputedStyle(month);
          const csEmpty = empty && getComputedStyle(empty);
          const csProd = prodTitle && getComputedStyle(prodTitle);
          const csTiles = tiles && getComputedStyle(tiles);
          return {
            present: Boolean(desk),
            gate: Boolean(gate),
            guest: Boolean(guest),
            month: month && month.textContent.trim(),
            monthSize: csMonth && csMonth.fontSize,
            monthDisplay: csMonth && csMonth.display,
            prodTitleDisplay: csProd && csProd.display,
            emptyTitle: empty && empty.querySelector('.pg-home-empty-title') &&
              empty.querySelector('.pg-home-empty-title').textContent.trim(),
            emptyDisplay: csEmpty && csEmpty.display,
            browseHref: browse && browse.getAttribute('href'),
            browseText: browse && browse.textContent.trim(),
            used: cap && cap.getAttribute('data-roster-used'),
            limit: cap && cap.getAttribute('data-roster-limit'),
            capacityCount: document.querySelectorAll('.RosterCapacity').length,
            tilesDisplay: csTiles && csTiles.display,
            status: status && status.textContent.trim(),
            statusDisplay: status && getComputedStyle(status).display,
            navActive: document.querySelector('.PrimaryTabs--top .nav-link.is-active')
              && document.querySelector('.PrimaryTabs--top .nav-link.is-active').textContent.replace(/\\s+/g, ' ').trim(),
          };
        }"""
    )
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.screenshot(path=str(empty_path), full_page=False)
    context.close()
    browser.close()
    browser_ctx.stop()

    assert empty_geo["present"] is True
    assert empty_geo["gate"] is False
    assert empty_geo["guest"] is False
    assert empty_geo["month"] == MONTH
    assert empty_geo["monthSize"] == "34px"
    assert empty_geo["monthDisplay"] != "none"
    assert empty_geo["prodTitleDisplay"] == "none"
    assert empty_geo["emptyTitle"] == f"Your {MONTH} Playground is empty"
    assert empty_geo["browseHref"] == "/laws"
    assert empty_geo["browseText"] == "Browse laws"
    assert empty_geo["used"] == "0"
    assert empty_geo["limit"] == "10"
    assert empty_geo["capacityCount"] == 1
    assert empty_geo["status"] == "RecallC Plus"
    assert empty_geo["statusDisplay"] != "none"
    assert "Playground" in (empty_geo["navActive"] or "")
    assert empty_path.exists() and empty_path.stat().st_size > 1000

    _seed_roster(client, "ndps", "bns", "bnss", "mtp")
    browser_ctx, browser, context, page = _open("/playground")
    geo = page.evaluate(
        """() => {
          const desk = document.querySelector('[data-plus-playground="desktop"]');
          const month = document.querySelector('.plus-pg-month');
          const empty = document.querySelector('.pg-home-empty');
          const tiles = [...document.querySelectorAll('.pg-home-tiles .ProgressSummary-label')]
            .map((el) => el.textContent.trim());
          const cards = [...document.querySelectorAll('.pg-law-grid .LawCard')];
          const first = cards[0] && cards[0].getBoundingClientRect();
          const second = cards[1] && cards[1].getBoundingClientRect();
          const aside = document.querySelector('.pg-aside');
          const browse = aside && aside.querySelector('.pg-btn');
          const manage = aside && aside.querySelector('.pg-btn--ghost');
          const cap = document.querySelector('.RosterCapacity');
          const trust = aside && aside.querySelector('.TrustMark');
          const bar = cards[0] && cards[0].querySelector('.LawCard-bar');
          const meta = cards[0] && cards[0].querySelector('.LawCard-meta.plus-pg-desk-only');
          const membership = cards[0] && cards[0].querySelector(
            '.LawStatusBadge[data-status="in_playground"]'
          );
          return {
            present: Boolean(desk),
            month: month && month.textContent.trim(),
            empty: Boolean(empty),
            tiles,
            cardIds: cards.map((el) => el.getAttribute('data-law-id')),
            twoCol: first && second && Math.abs(first.y - second.y) < 12 && second.x > first.x,
            browseHref: browse && browse.getAttribute('href'),
            browseText: browse && browse.textContent.trim(),
            manageText: manage && manage.textContent.trim(),
            used: cap && cap.getAttribute('data-roster-used'),
            limit: cap && cap.getAttribute('data-roster-limit'),
            capacityCount: document.querySelectorAll('.RosterCapacity').length,
            trust: Boolean(trust),
            barDisplay: bar && getComputedStyle(bar).display,
            meta: meta && meta.textContent.replace(/\\s+/g, ' ').trim(),
            membershipDisplay: membership && getComputedStyle(membership).display,
            continue: cards[0] && cards[0].innerText.includes('Start learning'),
            read: cards[0] && cards[0].innerText.includes('Read Bare Act'),
            kicker: document.querySelector('.pg-home-kicker') &&
              document.querySelector('.pg-home-kicker').textContent.trim(),
            section: document.querySelector('.pg-section-head h2') &&
              document.querySelector('.pg-section-head h2').textContent.trim(),
            status: document.querySelector('.account-menu-btn-status') &&
              document.querySelector('.account-menu-btn-status').textContent.trim(),
          };
        }"""
    )
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.screenshot(path=str(shot_path), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    phone_geo = page.evaluate(
        """() => {
          const month = document.querySelector('.plus-pg-month');
          const prod = document.querySelector('.pg-home-title.plus-pg-desk-hide');
          const aside = document.querySelector('.pg-aside');
          return {
            monthDisplay: month && getComputedStyle(month).display,
            prodDisplay: prod && getComputedStyle(prod).display,
            asideDisplay: aside && getComputedStyle(aside).display,
          };
        }"""
    )
    context.close()
    browser.close()
    browser_ctx.stop()

    assert geo["present"] is True
    assert geo["month"] == MONTH
    assert geo["empty"] is False
    assert geo["tiles"] == ["Due today", "Overdue", "Sections learned"]
    assert set(geo["cardIds"]) == {"ndps", "bns", "bnss", "mtp"}
    assert len(geo["cardIds"]) == 4
    assert geo["twoCol"] is True
    assert geo["browseHref"] == "/laws"
    assert geo["browseText"] == "Browse laws"
    assert geo["manageText"] == f"Manage {MONTH}"
    assert geo["used"] == "4"
    assert geo["limit"] == "10"
    assert geo["capacityCount"] == 1
    assert geo["trust"] is True
    assert geo["barDisplay"] == "none"
    assert geo["meta"] == "0 sections selected · 0 learned"
    assert geo["membershipDisplay"] == "none"
    assert geo["continue"] is True
    assert geo["read"] is True
    assert geo["kicker"] == "My Playground"
    assert geo["section"] == "In Playground this month"
    assert geo["status"] == "RecallC Plus"
    assert phone_geo["monthDisplay"] == "none"
    assert phone_geo["prodDisplay"] != "none"
    assert shot_path.exists() and shot_path.stat().st_size > 1000
