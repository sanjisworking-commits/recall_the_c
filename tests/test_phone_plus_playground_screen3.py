"""Phone Plus Playground home Screen 03 (CTA map plus/03-screen).

Authorized: ChatGPT. Authenticated active Plus GET /playground at 390x844.
Desktop Plus Screen 06 is the functional contract. Live month name, live
month_count_label from active membership, live Start learning / Continue.
Empty and enrolled are both real. Map "2 laws" / "12 Aug – 11 Sep" / "Learn"
are presentation losses. Free Gate, Guest, Expired, Halted, Pro, Plus 01–02,
and desktop 06 stay unchanged.
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
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.roster.period import (
    next_playground_month_bounds,
    playground_month_bounds,
    playground_month_name,
)
from constitution_memorizer.playground.service import activate_law
from constitution_memorizer.playground.urls import (
    add_path,
    law_path,
    roster_next_path,
    roster_path,
    sections_path,
)
from constitution_memorizer.playground.view import BROWSE_LAWS_PATH
from constitution_memorizer.web.app import create_app
from tests.conftest import PLAYGROUND_TEST_NOW

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
PARTIALS = ROOT / "src/constitution_memorizer/web/templates/partials/playground.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
PG_JS = ROOT / "src/constitution_memorizer/web/static/playground.js"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
ROUTES = ROOT / "src/constitution_memorizer/playground/routes.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
USER = UUID("11111111-1111-4111-8111-111111111111")
MONTH = playground_month_name(playground_month_bounds(PLAYGROUND_TEST_NOW)[0])
NEXT = playground_month_name(next_playground_month_bounds(PLAYGROUND_TEST_NOW)[0])
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
)
FULL_LAWS = (
    "bns",
    "bnss",
    "uapa",
    "pss",
    "mtp",
    "ipc",
    "crpc",
    "cpc",
    "iea",
    "ida",
)
INVENTED = (
    "Premium",
    "Unlimited",
    "renews",
    "Unlock all",
    "Free plan",
    "device limit",
    "replacement",
    "Unlock Playground",
    "View Playground plans",
    "12 Aug",
    "11 Sep",
    "2 laws",
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


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("rtc_csrf") or ""
    return {"csrf_token": token} if token else {}


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


def _confirm_add(client: TestClient, law_id: str, *, scope: str = "entire"):
    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    payload["scope"] = scope
    return client.post(add_path(law_id), data=payload, follow_redirects=False)


def _phone(html: str) -> str:
    return html.split("data-plus-playground-phone", 1)[1].split("<aside", 1)[0]


def _tabs(html: str) -> str:
    start = html.find('class="mobile-tabbar')
    assert start != -1
    return html[start:].split("</nav>", 1)[0]


def _strip(html: str) -> str:
    chunk = html.split('class="pg-month-strip"', 1)[1]
    return chunk.split("</div>", 1)[0]


def _facts(client: TestClient) -> dict:
    history = tuple(
        sorted(
            (row.id, row.status, row.tier, row.is_current)
            for row in client.app.state.subscriptions.list_subscription_history(USER)
        )
    )
    roster = getattr(client.app.state, "roster", None)
    overlay = getattr(client.app.state, "playground", None)
    start, _end = playground_month_bounds()
    consumed = ()
    if roster is not None:
        consumed = tuple(
            sorted(
                item.law_id
                for item in roster._repo.list_items(USER, start)
                if item.consumed_at is not None
            )
        )
    return {
        "session": client.cookies.get(SESSION_COOKIE_NAME),
        "subscription": client.app.state.subscriptions.get_current_subscription(USER),
        "history": history,
        "active": tuple(
            sorted(i.law_id for i in roster.active_roster_items(USER))
        )
        if roster is not None
        else (),
        "consumed": consumed,
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        )
        if overlay is not None
        else (),
    }


def test_phone_plus_empty_home_is_live_capacity_not_gate(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    before = _facts(client)
    page = client.get("/playground")
    assert page.status_code == 200
    html = unescape(page.text)
    assert _facts(client)["active"] == ()
    assert _facts(client)["consumed"] == ()
    assert _facts(client)["subscription"] == before["subscription"]
    assert 'data-plus-playground="desktop"' in html
    assert "data-plus-playground-phone" in html
    assert "data-signed-in-pg-gate" not in html
    assert "data-guest-pg-intro" not in html
    assert 'data-playground-gate="not_subscribed"' not in html
    phone = unescape(_phone(html))
    assert 'class="pg-home-title plus-pg-desk-hide">Playground<' in html
    assert f"0 of 10 · {MONTH}" in phone
    assert f"Your {MONTH} Playground is empty" in phone
    assert "Add laws you want to learn this month." in phone
    assert "LawCard" not in phone
    assert 'data-law-id="' not in phone
    strip = _strip(phone)
    assert f">Manage {MONTH}<" in strip
    assert f'href="{roster_path()}"' in strip
    assert ">Add a law<" in strip
    assert f'href="{BROWSE_LAWS_PATH}"' in strip
    assert BROWSE_LAWS_PATH == "/laws"
    assert f">Manage {NEXT} ›<" in strip
    assert f'href="{roster_next_path()}"' in strip
    assert f"Playground month" in strip
    assert MONTH in strip
    assert "12 Aug" not in strip
    assert "0 of 10 laws" in html
    assert "10 spaces available" in html
    for phrase in INVENTED:
        assert phrase not in phone, phrase
    assert ">Learn<" not in phone
    tabs = _tabs(html)
    assert "data-plus-bareact-phone-tabs" not in html
    assert html.count('class="mobile-tabbar') == 1
    for label, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        assert label in tabs
    playground = tabs.split('href="/playground"', 1)[1].split("</a>", 1)[0]
    assert "is-active" in playground
    assert 'aria-current="page"' in playground
    assert tabs.count("is-active") == 1
    assert _facts(client)["consumed"] == before["consumed"]


def test_phone_plus_enrolled_ndps_bns_uses_live_cards(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    _seed_roster(client, "ndps", "bns")
    html = unescape(client.get("/playground").text)
    phone = unescape(_phone(html))
    assert "data-signed-in-pg-gate" not in html
    assert f"Your {MONTH} Playground is empty" not in phone
    assert f"2 of 10 · {MONTH}" in phone
    assert "2 of 10 laws" in html
    assert "8 spaces available" in html
    assert 'data-law-id="ndps"' in phone
    assert 'data-law-id="bns"' in phone
    assert "NDPS Act" in phone
    assert ">BNS<" in phone or "BNS" in phone
    assert "Start learning" in phone
    assert f'href="{sections_path("ndps")}"' in phone
    assert f'href="{sections_path("bns")}"' in phone
    assert ">Learn<" not in phone
    assert "2 laws" not in phone
    assert "12 Aug" not in html
    ndps = phone.split('data-law-id="ndps"', 1)[1].split("</article>", 1)[0]
    assert "Start learning" in ndps
    assert "Continue" not in ndps.split("pg-card-actions--phone", 1)[1]


def test_phone_plus_active_count_is_not_consumed_remaining(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    _seed_roster(client, "ndps", "bns")
    start, _end = playground_month_bounds()
    removed = client.app.state.roster._repo.remove_law(
        USER, period_start=start, law_id="bns"
    )
    assert removed is not None
    assert removed.removed_at is not None
    html = unescape(client.get("/playground").text)
    phone = unescape(_phone(html))
    assert 'data-law-id="ndps"' in phone
    assert 'data-law-id="bns"' in phone
    assert "Removed this month" in phone
    assert f"1 of 10 · {MONTH}" in phone
    assert "2 of 10 laws" in html
    assert "8 spaces available" in html
    assert "Add back" in phone
    assert f'href="{add_path("bns")}"' in phone
    facts = _facts(client)
    assert facts["active"] == ("ndps",)
    assert facts["consumed"] == ("bns", "ndps")


def test_phone_plus_start_learning_and_continue_destinations(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    client.get("/playground")
    added = _confirm_add(client, "ndps", scope="sections")
    assert added.status_code == 303
    assert added.headers.get("location") == sections_path("ndps")
    html = unescape(client.get("/playground").text)
    phone = unescape(_phone(html))
    ndps = phone.split('data-law-id="ndps"', 1)[1].split("</article>", 1)[0]
    actions = ndps.split("pg-card-actions--phone", 1)[1].split(
        "pg-card-actions--desktop", 1
    )[0]
    assert "Start learning" in actions
    assert f'href="{sections_path("ndps")}"' in actions
    assert "1 of 10 laws" in html
    assert "9 spaces available" in html

    entire = _plus_client(tmp_path / "entire")
    entire.get("/playground")
    done = _confirm_add(entire, "ndps", scope="entire")
    assert done.status_code == 303
    assert done.headers.get("location") == law_path("ndps")
    home = unescape(entire.get("/playground").text)
    card = _phone(home).split('data-law-id="ndps"', 1)[1].split("</article>", 1)[0]
    phone_actions = card.split("pg-card-actions--phone", 1)[1].split(
        "pg-card-actions--desktop", 1
    )[0]
    assert "Continue" in phone_actions
    assert f'href="{law_path("ndps")}"' in phone_actions
    assert "Start learning" not in phone_actions
    assert "data-signed-in-pg-gate" not in home


def test_phone_plus_01_continue_and_saved_and_full(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    _seed_roster(client, "ndps")
    bare = client.get("/laws/ndps").text
    assert 'href="/playground"' in bare
    assert "Continue" in bare
    home = unescape(client.get("/playground").text)
    assert "data-plus-playground-phone" in home
    assert "data-signed-in-pg-gate" not in home
    assert 'data-law-id="ndps"' in home

    saved = _plus_client(tmp_path / "saved")
    activate_law(saved.app.state.playground, USER, "ndps")
    saved_html = unescape(saved.get("/playground").text)
    phone = unescape(_phone(saved_html))
    assert "Saved progress" in phone
    assert "Add to this month" in phone
    assert f'href="{add_path("ndps")}"' in phone
    assert saved.app.state.roster.is_law_active_this_period(USER, "ndps") is False
    assert "0 of 10 laws" in saved_html
    assert "10 spaces available" in saved_html

    full = _plus_client(tmp_path / "full")
    _seed_roster(full, *FULL_LAWS)
    full_html = unescape(full.get("/playground").text)
    assert "10 of 10 laws" in full_html
    assert f"Playground full for {MONTH}" in full_html
    assert 'data-law-id="ndps"' not in full_html
    assert len(_facts(full)["consumed"]) == 10


def test_phone_plus_readd_does_not_use_extra_space(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    _seed_roster(client, "ndps")
    start, _end = playground_month_bounds()
    removed = client.app.state.roster._repo.remove_law(
        USER, period_start=start, law_id="ndps"
    )
    assert removed is not None
    before = _facts(client)
    restored = client.app.state.roster._repo.consume_law(
        USER,
        period_start=start,
        law_id="ndps",
        law_limit=10,
        allow_new=True,
    )
    assert restored.ok
    html = unescape(client.get("/playground").text)
    assert "1 of 10 laws" in html
    assert "9 spaces available" in html
    assert _facts(client)["consumed"] == before["consumed"]
    assert _facts(client)["active"] == ("ndps",)


def test_guest_free_expired_halted_pro_stay_separate(tmp_path: Path) -> None:
    guest = TestClient(_guest_app(tmp_path / "guest")).get("/playground").text
    assert "data-guest-pg-intro" in guest
    assert "data-plus-playground-phone" not in guest
    assert 'data-plus-playground="desktop"' not in guest

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/playground").text
    assert "data-signed-in-pg-gate" in free_html
    assert "data-plus-playground-phone" not in free_html
    assert 'data-plus-playground="desktop"' not in free_html

    plus = _plus_client(tmp_path / "plus")
    plans = unescape(plus.get("/playground?stage=plans&tier=pro").text)
    assert "data-signed-in-pg-gate" not in plans
    assert "data-plus-playground-phone" in plans

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
    expired_html = expired.get("/playground").text
    assert "data-plus-playground-phone" not in expired_html
    assert 'data-expired-playground="desktop"' in expired_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/playground").text
    assert "data-plus-playground-phone" not in halted_html
    assert 'data-halted-playground="desktop"' in halted_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/playground").text
    assert "data-plus-playground-phone" not in pro_html
    assert 'data-plus-playground="desktop"' not in pro_html


def test_phone_plus_css_scope_pins_and_desktop_06_untouched() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    assert "is plus/03-screen:" in css
    phone_block = css.split("is plus/03-screen:", 1)[1].split(
        "Expired and Halted desktop Playground home", 1
    )[0]
    assert "@media (max-width: 560px)" in phone_block
    assert "[data-plus-playground-phone]" in phone_block
    assert "safe-area-inset-bottom" in phone_block
    assert "overflow-x: hidden" in phone_block
    assert "min-height: 44px" in phone_block
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", phone_block) is None
    assert "[data-signed-in-pg-gate]" not in phone_block
    desk = css.split(
        ".pg-home-grid[data-plus-playground=\"desktop\"] h1.plus-pg-month {", 1
    )[1].split("}", 1)[0]
    assert "font-size: 34px" in desk
    hide_strip = css.split(
        ".pg-home-grid[data-plus-playground=\"desktop\"] .pg-month-strip {", 1
    )[1].split("}", 1)[0]
    assert "display: none" in hide_strip
    mobile = MOBILE.read_text(encoding="utf-8")
    before_04, marker, after_04 = mobile.partition("is signedIn/04-screen:")
    assert marker
    combined = after_04.split("/* R1 — Playground phone shell", 1)[0]
    assert "data-plus-playground-phone" not in before_04
    assert "data-plus-playground-phone" not in combined
    assert "sun" not in combined.lower()
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", combined) is None
    assert "data-plus-playground-phone" not in STYLES.read_text(encoding="utf-8")
    assert "data-plus-playground-phone" not in PG_JS.read_text(encoding="utf-8")
    home = HOME.read_text(encoding="utf-8")
    assert "data-plus-playground-phone" in home
    assert "plus-pg-period-label" in home
    assert "home.capacity.month_name" in home
    assert "home.month_count_label" in home
    assert "home.manage_href" in home
    assert "home.add_law_href" in home
    assert "home.plan_next_href" in home
    assert "September" not in home
    assert "12 Aug" not in home
    partials = PARTIALS.read_text(encoding="utf-8")
    assert "data-plus-playground-phone" not in partials
    assert "def build_home_view" in VIEW.read_text(encoding="utf-8")
    routes = ROUTES.read_text(encoding="utf-8")
    assert '"plus_playground": request_is_active_plus(request)' in routes
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg43" in base
    assert "playground.css?v=pg35" not in base
    assert "styles.css?v=main86" in base
    assert "mobile.css?v=mob105" in base
    assert "data-plus-playground-phone-tabs" not in base


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


def test_phone_plus_playground_screen03_captures(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    empty_path = artifact_dir / "phone_plus_playground_screen03_empty_390x844.png"
    enrolled_path = artifact_dir / "phone_plus_playground_screen03_390x844.png"
    desk_path = artifact_dir / "phone_plus_playground_screen03_desktop_regression_1280.png"
    origin = f"http://127.0.0.1:{port}"
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

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        context.add_cookies(cookies)
        page = context.new_page()
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )

        def open_home():
            page.goto(f"{origin}/playground", wait_until="networkidle")
            page.evaluate(
                """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
            )
            page.wait_for_selector("[data-plus-playground-phone]", timeout=8000)
            page.wait_for_timeout(250)

        open_home()
        empty_geo = page.evaluate(
            """() => {
              const phone = document.querySelector('[data-plus-playground-phone]');
              const desk = document.querySelector('[data-plus-playground="desktop"]');
              const gate = document.querySelector('[data-signed-in-pg-gate]');
              const title = document.querySelector('.pg-home-title.plus-pg-desk-hide');
              const month = document.querySelector('.plus-pg-month');
              const count = document.querySelector('.pg-home-month');
              const empty = document.querySelector('.pg-home-empty');
              const strip = phone.querySelector('.pg-month-strip');
              const links = [...strip.querySelectorAll('a')];
              const cards = phone.querySelectorAll('.LawCard');
              const actions = phone.querySelector(':scope > p.pg-actions');
              const plan = phone.querySelector(':scope > .pg-plan-row');
              const tabs = [...document.querySelectorAll('.mobile-tabbar .mobile-tab')];
              const active = document.querySelector('.mobile-tabbar .mobile-tab.is-active');
              return {
                present: Boolean(phone && desk),
                gate: Boolean(gate),
                title: title && title.textContent.trim(),
                titleDisplay: title && getComputedStyle(title).display,
                monthDisplay: month && getComputedStyle(month).display,
                count: count && count.textContent.trim(),
                emptyTitle: empty && empty.querySelector('.pg-home-empty-title')
                  && empty.querySelector('.pg-home-empty-title').textContent.trim(),
                cards: cards.length,
                hrefs: links.map((a) => a.getAttribute('href')),
                labels: links.map((a) => a.textContent.replace(/\\s+/g, ' ').trim()),
                actionsDisplay: actions ? getComputedStyle(actions).display : 'missing',
                planDisplay: plan ? getComputedStyle(plan).display : 'missing',
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                tabLabels: tabs.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabs.map((el) => el.getAttribute('href')),
                activeTab: active && active.textContent.replace(/\\s+/g, ' ').trim(),
                dedicatedTabs: Boolean(document.querySelector('[data-plus-playground-phone-tabs]')),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, empty_path)

        page.set_viewport_size({"width": 1280, "height": 800})
        open_home()
        desk_geo = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-plus-playground="desktop"]');
              const phone = document.querySelector('[data-plus-playground-phone]');
              const month = document.querySelector('.plus-pg-month');
              const prod = document.querySelector('.pg-home-title.plus-pg-desk-hide');
              const empty = document.querySelector('.pg-home-empty');
              const strip = document.querySelector('.pg-month-strip');
              const aside = document.querySelector('.pg-aside');
              const cap = document.querySelector('.RosterCapacity');
              const browse = aside && aside.querySelector('.pg-btn');
              const status = document.querySelector('.account-menu-btn-status');
              const csMonth = month && getComputedStyle(month);
              return {
                present: Boolean(desk && phone),
                gate: Boolean(document.querySelector('[data-signed-in-pg-gate]')),
                month: month && month.textContent.trim(),
                monthSize: csMonth && csMonth.fontSize,
                monthDisplay: csMonth && csMonth.display,
                prodDisplay: prod && getComputedStyle(prod).display,
                emptyTitle: empty && empty.querySelector('.pg-home-empty-title')
                  && empty.querySelector('.pg-home-empty-title').textContent.trim(),
                stripDisplay: strip && getComputedStyle(strip).display,
                asideDisplay: aside && getComputedStyle(aside).display,
                used: cap && cap.getAttribute('data-roster-used'),
                limit: cap && cap.getAttribute('data-roster-limit'),
                browseHref: browse && browse.getAttribute('href'),
                browseText: browse && browse.textContent.trim(),
                status: status && status.textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, desk_path)

        _seed_roster(client, "ndps", "bns")
        page.set_viewport_size({"width": 390, "height": 844})
        open_home()
        enrolled_geo = page.evaluate(
            """() => {
              const phone = document.querySelector('[data-plus-playground-phone]');
              const cards = [...phone.querySelectorAll('.pg-law-grid .LawCard')];
              const primaries = cards.map((card) => {
                const btn = card.querySelector('.pg-card-actions--phone .pg-btn');
                const box = btn && btn.getBoundingClientRect();
                return {
                  id: card.getAttribute('data-law-id'),
                  title: card.querySelector('.LawCard-title')
                    && card.querySelector('.LawCard-title').textContent.trim(),
                  text: btn && btn.textContent.trim(),
                  href: btn && btn.getAttribute('href'),
                  height: box && box.height,
                  width: box && box.width,
                };
              });
              const count = document.querySelector('.pg-home-month');
              const empty = document.querySelector('.pg-home-empty');
              return {
                count: count && count.textContent.trim(),
                empty: Boolean(empty),
                ids: cards.map((el) => el.getAttribute('data-law-id')),
                primaries,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                learnExact: primaries.some((row) => row.text === 'Learn'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, enrolled_path)

        page.set_viewport_size({"width": 390, "height": 560})
        short = page.evaluate(
            """() => {
              const phone = document.querySelector('[data-plus-playground-phone]');
              const btn = [...phone.querySelectorAll('.pg-card-actions--phone .pg-btn')].at(-1);
              btn.scrollIntoView();
              const tabsEl = document.querySelector('.mobile-tabbar');
              let box = btn.getBoundingClientRect();
              const tabTop = tabsEl.getBoundingClientRect().top;
              if (box.bottom > tabTop) {
                window.scrollBy(0, box.bottom - tabTop + 12);
                box = btn.getBoundingClientRect();
              }
              return {
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                height: box.height,
                width: box.width,
                top: box.top,
                bottom: box.bottom,
                inView: box.bottom <= tabsEl.getBoundingClientRect().top + 2 && box.top >= 0,
                tabTop: tabsEl.getBoundingClientRect().top,
              };
            }"""
        )
        browser.close()

    assert empty_geo["present"] is True
    assert empty_geo["gate"] is False
    assert empty_geo["title"] == "Playground"
    assert empty_geo["titleDisplay"] != "none"
    assert empty_geo["monthDisplay"] == "none"
    assert empty_geo["count"] == f"0 of 10 · {MONTH}"
    assert empty_geo["emptyTitle"] == f"Your {MONTH} Playground is empty"
    assert empty_geo["cards"] == 0
    assert empty_geo["hrefs"] == [roster_path(), BROWSE_LAWS_PATH, roster_next_path()]
    assert empty_geo["labels"] == [
        f"Manage {MONTH}",
        "Add a law",
        f"Manage {NEXT} ›",
    ]
    assert empty_geo["actionsDisplay"] == "none"
    assert empty_geo["planDisplay"] == "none"
    assert empty_geo["overflow"] is False
    assert empty_geo["tabLabels"] == ["Today", "Browse", "Playground", "Calendar", "Profile"]
    assert empty_geo["tabHrefs"] == [
        "/dashboard",
        "/browse",
        "/playground",
        "/calendar",
        "/profile",
    ]
    assert empty_geo["activeTab"] == "Playground"
    assert empty_geo["dedicatedTabs"] is False

    assert desk_geo["present"] is True
    assert desk_geo["gate"] is False
    assert desk_geo["month"] == MONTH
    assert desk_geo["monthSize"] == "34px"
    assert desk_geo["monthDisplay"] != "none"
    assert desk_geo["prodDisplay"] == "none"
    assert desk_geo["emptyTitle"] == f"Your {MONTH} Playground is empty"
    assert desk_geo["stripDisplay"] == "none"
    assert desk_geo["asideDisplay"] != "none"
    assert desk_geo["used"] == "0"
    assert desk_geo["limit"] == "10"
    assert desk_geo["browseHref"] == "/laws"
    assert desk_geo["browseText"] == "Browse laws"
    assert desk_geo["status"] == "RecallC Plus"

    assert enrolled_geo["count"] == f"2 of 10 · {MONTH}"
    assert enrolled_geo["empty"] is False
    assert set(enrolled_geo["ids"]) == {"ndps", "bns"}
    by_id = {row["id"]: row for row in enrolled_geo["primaries"]}
    assert by_id["ndps"]["title"] == "NDPS Act"
    assert by_id["bns"]["title"] == "BNS"
    assert by_id["ndps"]["text"] == "Start learning"
    assert by_id["bns"]["text"] == "Start learning"
    assert by_id["ndps"]["href"] == sections_path("ndps")
    assert by_id["bns"]["href"] == sections_path("bns")
    assert by_id["ndps"]["height"] >= 44
    assert enrolled_geo["learnExact"] is False
    assert enrolled_geo["overflow"] is False

    assert short["overflow"] is False
    assert short["height"] >= 44
    assert short["inView"] is True

    for path in (empty_path, enrolled_path, desk_path):
        assert path.is_file() and path.stat().st_size > 1000
