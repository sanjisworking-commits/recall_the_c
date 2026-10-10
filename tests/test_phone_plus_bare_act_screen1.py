"""Phone Plus Bare Act head Screen 01 (CTA map plus/01-screen).

Authorized: ChatGPT. Authenticated active Plus GET /laws/ndps at 390x844.
Desktop Plus Screen 04 is the functional contract. Compact head uses live
playground_state (already_active / eligible_to_add / roster_full / re_add).
Map already_active cluster is composition; empty roster is Add, not enrolled.
Free/Guest/Expired/Halted/Pro and other laws stay as they are. Plus 02 is not
this screen.
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
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.roster.period import playground_month_bounds
from constitution_memorizer.playground.urls import add_path, home_path, remove_path, sections_path
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.guest_bareact_head import (
    NDPS_GUEST_KICKER,
    NDPS_GUEST_META,
    NDPS_GUEST_ROWS,
    NDPS_GUEST_TITLE,
    ndps_guest_head,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
INVENTED = (
    "Premium",
    "Unlimited",
    "renews",
    "Unlock all",
    "Free plan",
    "device limit",
    "replacement",
)
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


def _phone(html: str) -> str:
    return html.split("data-plus-bareact-phone", 1)[1].split("</section>", 1)[0]


def _tabs(html: str) -> str:
    return html.split("data-plus-bareact-phone-tabs", 1)[1].split("</nav>", 1)[0]


def _facts(client: TestClient) -> dict:
    history = tuple(
        sorted(
            (row.id, row.status, row.tier, row.is_current)
            for row in client.app.state.subscriptions.list_subscription_history(USER)
        )
    )
    roster = getattr(client.app.state, "roster", None)
    overlay = getattr(client.app.state, "playground", None)
    devices = getattr(client.app.state, "device_service", None)
    return {
        "session": client.cookies.get(SESSION_COOKIE_NAME),
        "subscription": client.app.state.subscriptions.get_current_subscription(USER),
        "history": history,
        "active": tuple(
            sorted(i.law_id for i in roster.active_roster_items(USER))
        )
        if roster is not None
        else (),
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        )
        if overlay is not None
        else (),
        "devices": tuple(
            sorted(str(getattr(item, "id", item)) for item in devices.list_devices(USER))
        )
        if devices is not None and hasattr(devices, "list_devices")
        else (),
    }


def test_phone_plus_already_active_uses_live_membership(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    page = client.get("/laws/ndps")
    assert page.status_code == 200
    html = unescape(page.text)
    assert "data-plus-bareact-phone" in html
    assert "data-signed-in-bareact-phone" not in html
    assert "data-guest-bareact-phone" not in html
    phone = _phone(html)
    live = ndps_guest_head()
    assert f">{live.title}<" in phone
    assert NDPS_GUEST_KICKER in phone
    assert NDPS_GUEST_META in phone
    assert "6 Chapters" in phone
    assert "8 Chapters" not in phone
    assert "← Laws" in phone
    assert 'href="/laws"' in phone
    assert 'data-pg-kind="already_active"' in phone
    assert "Already in Playground" in phone
    assert ">Sections<" in phone
    assert f'href="{sections_path("ndps")}"' in phone
    assert f'class="signed-bareact-continue" href="{home_path()}"' in phone
    assert ">Continue<" in phone
    assert "+ Add to Playground" not in phone
    assert "Subscribe to use Playground" not in phone
    assert "Sign in to use Playground" not in phone
    assert 'data-pg-kind="subscribe"' not in phone
    assert 'href="/billing/subscriptions"' not in phone
    assert 'href="/laws/ndps/section/' not in phone
    assert 'href="/laws/ndps/schedule/' not in phone
    assert "<details" not in phone
    for row in NDPS_GUEST_ROWS:
        assert row.tag in phone
        assert row.title in phone
        assert row.range_label in phone
    assert live.rows == NDPS_GUEST_ROWS
    for phrase in INVENTED:
        assert phrase not in phone, phrase
    client.get("/laws/ndps")
    before = _facts(client)
    assert before["active"] == ("ndps",)
    assert client.get("/laws/ndps").status_code == 200
    assert _facts(client) == before


def test_phone_plus_eligible_to_add_keeps_add_sheet_trigger(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    html = unescape(client.get("/laws/ndps").text)
    phone = _phone(html)
    assert 'data-pg-kind="eligible_to_add"' in phone
    assert "+ Add to Playground" in phone
    assert f'href="{add_path("ndps")}"' in phone
    assert "data-pg-sheet" in phone
    assert "Already in Playground" not in phone
    assert ">Sections<" not in phone
    assert 'class="signed-bareact-continue"' not in phone
    assert "Subscribe to use Playground" not in phone
    assert "Sign in to use Playground" not in phone
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False
    preview = client.post(add_path("ndps"), data=_csrf(client), follow_redirects=False)
    assert preview.status_code in {200, 303}


def test_phone_plus_roster_full_and_re_add_keep_live_kinds(tmp_path: Path) -> None:
    full = _plus_client(tmp_path / "full")
    _seed_roster(full, *FULL_LAWS)
    full_phone = unescape(_phone(full.get("/laws/ndps").text))
    assert 'data-pg-kind="roster_full"' in full_phone
    assert "Playground full this month" in full_phone
    assert "Already in Playground" not in full_phone
    assert "Subscribe to use Playground" not in full_phone
    assert full.app.state.roster.is_law_active_this_period(USER, "ndps") is False

    readd = _plus_client(tmp_path / "readd")
    added = _confirm_add(readd, "ndps")
    assert added.status_code in {200, 303}
    removed = readd.post(remove_path("ndps"), data=_csrf(readd), follow_redirects=False)
    assert removed.status_code in {200, 303}
    readd_phone = unescape(_phone(readd.get("/laws/ndps").text))
    assert 'data-pg-kind="re_add"' in readd_phone
    assert "Add back" in readd_phone
    assert f'href="{add_path("ndps")}"' in readd_phone
    assert "data-pg-sheet" in readd_phone
    assert "Subscribe to use Playground" not in readd_phone
    assert readd.app.state.roster.is_law_active_this_period(USER, "ndps") is False


def test_phone_plus_five_tabs_browse_active_only(tmp_path: Path) -> None:
    html = _plus_client(tmp_path).get("/laws/ndps").text
    assert "data-plus-bareact-phone-tabs" in html
    assert "data-signed-in-bareact-phone-tabs" not in html
    assert html.count('class="mobile-tabbar') == 1
    tabs = _tabs(html)
    for label, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        assert label in tabs
    browse = tabs.split('href="/browse"', 1)[1].split("</a>", 1)[0]
    assert "is-active" in browse
    assert 'aria-current="page"' in browse
    assert tabs.count("is-active") == 1
    assert tabs.count('aria-current="page"') == 1
    for href in ("/dashboard", "/playground", "/calendar", "/profile"):
        chunk = tabs.split(f'href="{href}"', 1)[1].split("</a>", 1)[0]
        assert "is-active" not in chunk
        assert "aria-current" not in chunk
    dash = _plus_client(tmp_path / "dash").get("/dashboard").text
    assert "data-plus-bareact-phone-tabs" not in dash


def test_phone_plus_css_scope_pins_and_desktop_04_untouched() -> None:
    mobile = MOBILE.read_text(encoding="utf-8")
    before_04, marker, after_04 = mobile.partition("is signedIn/04-screen:")
    assert marker
    assert "is plus/01-screen:" in before_04
    assert "is plus/01-screen:" not in after_04.split("/* R1 — Playground phone shell", 1)[0]
    plus_block = before_04.split("is plus/01-screen:", 1)[1].split(
        "/* Desktop keeps the deck", 1
    )[0]
    assert "data-plus-bareact-phone" in plus_block
    assert ":has([data-plus-bareact-phone])" in plus_block
    assert "safe-area-inset-bottom" in plus_block
    assert "overflow-x: hidden" in plus_block
    assert "min-height: 44px" in plus_block
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", plus_block) is None
    assert "sun" not in plus_block.lower()
    assert 'data-plus-bareact="desktop"] {' not in plus_block
    desk_hide = mobile.split("/* Desktop keeps the deck", 1)[1].split(
        "is signedIn/04-screen:", 1
    )[0]
    hide_rule = desk_hide.split("[data-plus-bareact-phone] {", 1)[1].split("}", 1)[0]
    assert "display: none" in hide_rule
    styles = STYLES.read_text(encoding="utf-8")
    assert "[data-plus-bareact-phone]" not in styles
    cluster = styles.split(
        "[data-signed-in-bareact-desktop] .signed-bareact-in-pg {", 1
    )[1].split("}", 1)[0]
    assert "flex: 0 0 380px" in cluster
    base = BASE.read_text(encoding="utf-8")
    assert "data-plus-bareact-phone-tabs" in base
    assert "signed_in_plus_bareact_phone" in base
    assert "styles.css?v=main86" in base
    assert "mobile.css?v=mob105" in base
    assert "mobile.css?v=mob104" not in base
    assert "playground.css?v=pg39" in base
    bare = BARE.read_text(encoding="utf-8")
    assert "data-plus-bareact-phone" in bare
    assert 'href="/playground"' in bare
    plus_section = bare.split("data-plus-bareact-phone", 1)[1].split(
        "data-signed-in-bareact-phone", 1
    )[0]
    assert "Already in Playground" not in plus_section
    assert "+ Add to Playground" not in plus_section


def test_phone_plus_cohorts_and_other_laws_stay_separate(tmp_path: Path) -> None:
    plus = _plus_client(tmp_path / "plus")
    plus_html = plus.get("/laws/ndps").text
    assert "data-plus-bareact-phone" in plus_html
    assert "data-signed-in-bareact-phone" not in plus_html
    bns = plus.get("/laws/bns").text
    assert "data-plus-bareact-phone" not in bns
    assert "RecallC Plus" not in bns.split("<header", 1)[1].split("</header>", 1)[0]

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/laws/ndps").text
    assert "data-plus-bareact-phone" not in free_html
    assert "data-plus-bareact-phone-tabs" not in free_html
    assert "data-signed-in-bareact-phone" in free_html
    assert "Subscribe to use Playground" in _phone_free(free_html)

    guest = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "guest" / "progress.db",
            multiuser=True,
            multiuser_settings=_settings(),
            auth_provider=FakeAuthProvider(),
            session_store=InMemorySessionStore(),
        )
    )
    guest_html = guest.get("/laws/ndps").text
    assert "data-plus-bareact-phone" not in guest_html
    assert "data-guest-bareact-phone" in guest_html
    assert "Sign in to use Playground" in guest_html

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
    expired_html = expired.get("/laws/ndps").text
    assert "data-plus-bareact-phone" not in expired_html
    assert "Resume Playground" in expired_html.split("data-bareact-phone", 1)[1]

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/laws/ndps").text
    assert "data-plus-bareact-phone" not in halted_html
    halted_prod = halted_html.split("data-bareact-phone", 1)[1]
    assert "LawPlaygroundCta" in halted_prod

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/laws/ndps").text
    assert "data-plus-bareact-phone" not in pro_html
    assert 'data-plus-bareact="desktop"' not in pro_html


def _phone_free(html: str) -> str:
    return html.split("data-signed-in-bareact-phone", 1)[1].split("</section>", 1)[0]


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


def _playwright_session(app, tmp_path: Path, *, enrolled: bool):
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    if enrolled:
        added = _confirm_add(client, "ndps")
        assert added.status_code in {200, 303}
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    return session, client


def test_phone_plus_bareact_screen01_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    session, _client = _playwright_session(app, tmp_path, enrolled=True)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_plus_bare_act_screen01_390x844.png"
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
              const phone = document.querySelector('[data-plus-bareact-phone]');
              const desk = document.querySelector('[data-signed-in-bareact-desktop]');
              const prod = document.querySelector('[data-bareact-phone]');
              const header = document.querySelector('.site-header');
              const tabs = document.querySelector('[data-plus-bareact-phone-tabs]');
              const bars = [...document.querySelectorAll('.mobile-tabbar')];
              const visibleBars = bars.filter((el) => getComputedStyle(el).display !== 'none');
              const visibleActive = visibleBars.flatMap((bar) =>
                [...bar.querySelectorAll('.mobile-tab.is-active')].filter(
                  (el) => getComputedStyle(el).display !== 'none'
                )
              );
              const visibleAria = visibleBars.flatMap((bar) =>
                [...bar.querySelectorAll('[aria-current="page"]')].filter(
                  (el) => getComputedStyle(el).display !== 'none'
                )
              );
              const back = phone && phone.querySelector('.guest-bareact-back');
              const sections = phone && phone.querySelector('.signed-bareact-sections');
              const cont = phone && phone.querySelector('.signed-bareact-continue');
              const rows = phone ? [...phone.querySelectorAll('.guest-bareact-row')] : [];
              const rowLinks = phone
                ? phone.querySelectorAll(
                    'a:not(.guest-bareact-back):not(.signed-bareact-sections):not(.signed-bareact-continue)'
                  )
                : [];
              const tabLinks = tabs ? [...tabs.querySelectorAll('a.mobile-tab')] : [];
              return {
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                prodDisplay: prod ? getComputedStyle(prod).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                barCount: bars.length,
                visibleBarCount: visibleBars.length,
                visibleActiveCount: visibleActive.length,
                visibleAriaCount: visibleAria.length,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                title: phone && phone.querySelector('.guest-bareact-title').textContent.trim(),
                kicker: phone && phone.querySelector('.guest-bareact-kicker').textContent.trim(),
                meta: phone && phone.querySelector('.guest-bareact-meta').textContent.trim(),
                backText: back && back.textContent.replace(/\\s+/g, ' ').trim(),
                backHref: back && back.getAttribute('href'),
                backH: back ? back.getBoundingClientRect().height : 0,
                already: phone && phone.innerText.includes('Already in Playground'),
                sectionsText: sections && sections.textContent.trim(),
                sectionsHref: sections && sections.getAttribute('href'),
                sectionsH: sections ? sections.getBoundingClientRect().height : 0,
                continueText: cont && cont.textContent.trim(),
                continueHref: cont && cont.getAttribute('href'),
                continueH: cont ? cont.getBoundingClientRect().height : 0,
                subscribe: phone && phone.innerText.includes('Subscribe to use Playground'),
                rowCount: rows.length,
                rowTitles: rows.map((el) =>
                  el.querySelector('.guest-bareact-row-title').textContent.trim()
                ),
                extraLinks: rowLinks.length,
                tabLabels: tabLinks.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabLinks.map((el) => el.getAttribute('href')),
                browseActive: visibleActive[0] && visibleActive[0].textContent.replace(/\\s+/g, ' ').trim(),
                details: prod ? prod.querySelectorAll('details').length : 0,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)
        page.locator("[data-plus-bareact-phone] .guest-bareact-back").click()
        page.wait_for_function("() => location.pathname === '/laws'", timeout=8000)
        laws_path = page.evaluate("() => location.pathname")
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.locator("[data-plus-bareact-phone] .signed-bareact-sections").click()
        page.wait_for_url("**/playground/laws/ndps/sections**", timeout=8000)
        sections_url = page.url
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.locator("[data-plus-bareact-phone] .signed-bareact-continue").click()
        page.wait_for_url("**/playground**", timeout=8000)
        playground_url = page.url
        playground_gate = "data-signed-in-pg-gate" in page.content()
        page.set_viewport_size({"width": 390, "height": 700})
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        short_overflow = page.evaluate(
            "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        browser.close()

    assert geo["phoneDisplay"] != "none"
    assert geo["deskDisplay"] == "none"
    assert geo["prodDisplay"] == "none"
    assert geo["headerDisplay"] == "none"
    assert geo["tabsDisplay"] != "none"
    assert geo["barCount"] == 1
    assert geo["visibleBarCount"] == 1
    assert geo["visibleActiveCount"] == 1
    assert geo["visibleAriaCount"] == 1
    assert geo["overflow"] is False
    assert geo["title"] == NDPS_GUEST_TITLE
    assert geo["kicker"] == NDPS_GUEST_KICKER
    assert geo["meta"] == NDPS_GUEST_META
    assert geo["backText"] == "← Laws"
    assert geo["backHref"] == "/laws"
    assert geo["backH"] >= 44
    assert geo["already"] is True
    assert geo["sectionsText"] == "Sections"
    assert geo["sectionsHref"] == sections_path("ndps")
    assert geo["sectionsH"] >= 44
    assert geo["continueText"] == "Continue"
    assert geo["continueHref"] == home_path()
    assert geo["continueH"] >= 44
    assert geo["subscribe"] is False
    assert geo["rowCount"] == 4
    assert geo["rowTitles"] == [row.title for row in NDPS_GUEST_ROWS]
    assert geo["extraLinks"] == 0
    assert geo["tabLabels"] == [label for label, _href in TAB_HREFS]
    assert geo["tabHrefs"] == [href for _label, href in TAB_HREFS]
    assert geo["browseActive"] == "Browse"
    assert geo["details"] == 8
    assert laws_path == "/laws"
    assert "/playground/laws/ndps/sections" in sections_url
    assert "/playground" in playground_url
    assert playground_gate is False
    assert short_overflow is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_plus_bareact_screen01_eligible_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    session, _client = _playwright_session(app, tmp_path, enrolled=False)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_plus_bare_act_screen01_eligible_390x844.png"
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
              const phone = document.querySelector('[data-plus-bareact-phone]');
              const cta = phone && phone.querySelector('.LawPlaygroundCta');
              const add = phone && phone.querySelector('[data-pg-sheet]');
              const box = add && add.getBoundingClientRect();
              return {
                kind: cta && cta.getAttribute('data-pg-kind'),
                href: add && add.getAttribute('href'),
                text: add && add.textContent.replace(/\\s+/g, ' ').trim(),
                addH: box ? box.height : 0,
                already: phone && phone.innerText.includes('Already in Playground'),
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)
        page.locator("[data-plus-bareact-phone] [data-pg-sheet]").click()
        page.wait_for_selector("[data-pg-add]", timeout=8000)
        dialog = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              return {
                kind: panel && panel.getAttribute('data-pg-kind'),
                plusDesk: !!(panel && panel.querySelector('[data-plus-add-desktop]')),
                plusPhone: !!(panel && panel.querySelector('[data-plus-add-phone]')),
                unlock: !!(panel && panel.innerText.includes('Unlock Playground')),
                url: location.pathname,
              };
            }"""
        )
        page.keyboard.press("Escape")
        still = page.evaluate("() => location.pathname")
        browser.close()

    assert geo["kind"] == "eligible_to_add"
    assert geo["href"] == add_path("ndps")
    assert geo["text"] == "+ Add to Playground"
    assert geo["addH"] >= 44
    assert geo["already"] is False
    assert geo["overflow"] is False
    assert dialog["kind"] == "eligible_to_add"
    assert dialog["plusDesk"] is True
    assert dialog["plusPhone"] is True
    assert dialog["unlock"] is False
    assert still.endswith("/laws/ndps")
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_plus_bareact_screen01_desktop_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    session, _client = _playwright_session(app, tmp_path, enrolled=True)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_plus_bare_act_screen01_desktop_regression_1280.png"
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
              const desk = document.querySelector('[data-signed-in-bareact-desktop]');
              const plusPhone = document.querySelector('[data-plus-bareact-phone]');
              const prod = document.querySelector('[data-bareact-phone]');
              const tabs = document.querySelector('[data-plus-bareact-phone-tabs]');
              const header = document.querySelector('.site-header');
              const cluster = desk && desk.querySelector('.signed-bareact-in-pg');
              const box = cluster && cluster.getBoundingClientRect();
              const nav = [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                (el) => el.textContent.replace(/\\s+/g, ' ').trim()
              );
              const cont = desk && desk.querySelector('.signed-bareact-continue');
              const sections = desk && desk.querySelector('.signed-bareact-sections');
              return {
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                plusPhoneDisplay: plusPhone ? getComputedStyle(plusPhone).display : null,
                prodDisplay: prod ? getComputedStyle(prod).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                clusterW: box ? box.width : 0,
                already: desk && desk.innerText.includes('Already in Playground'),
                continueHref: cont && cont.getAttribute('href'),
                sectionsHref: sections && sections.getAttribute('href'),
                navLabels: nav,
                title: desk && desk.querySelector('.guest-bareact-title').textContent.trim(),
                account: document.querySelector('.account-menu-btn-name')
                  && document.querySelector('.account-menu-btn-name').textContent.trim(),
                status: document.querySelector('.account-menu-btn-status')
                  && document.querySelector('.account-menu-btn-status').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)
        browser.close()

    assert geo["deskDisplay"] != "none"
    assert geo["plusPhoneDisplay"] == "none"
    assert geo["prodDisplay"] == "none"
    assert geo["tabsDisplay"] == "none"
    assert geo["headerDisplay"] != "none"
    assert geo["clusterW"] == pytest.approx(380, abs=8)
    assert geo["already"] is True
    assert geo["continueHref"] == home_path()
    assert geo["sectionsHref"] == sections_path("ndps")
    assert geo["navLabels"] == [label for label, _href in TAB_HREFS]
    assert geo["title"] == NDPS_GUEST_TITLE
    assert geo["account"] == "Sanjay"
    assert geo["status"] == "RecallC Plus"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
