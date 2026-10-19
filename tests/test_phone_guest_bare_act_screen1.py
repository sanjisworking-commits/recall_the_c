"""Phone Guest Bare Act head Screen 01 (CTA map guest/01-screen, 390x844).

M2: one generated Bare Act head for every Act and every viewer (§2.1); the
phone and desktop twins are gone and CSS lays the same markup out at both
widths. Guest GET /laws/ndps is checked here; signed-in, Plus, Expired and
Halted get their own live-state CTA from the same head. Add-sheet Screen 02
has its own tests.
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
from constitution_memorizer.playground.urls import add_path
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
NDPS = get_bare_act("ndps")
KICKER = "Bare Act · India Code"  # uppercased by CSS, printed in title case
TITLE = NDPS.title
META = NDPS.head_meta_label
PRIMARY = "Sign in to use Playground"
FORBIDDEN = (
    "Already in Playground",
    "ActHead-inpg",
    ">Sections</a>",  # the About card's "Sections" <dt> is not a link
    ">Continue</a>",
    ">Manage<",
    "Resume Playground",
    "Add to Playground",
    "Unlock Playground",
    "Subscribe to use Playground",
    "LawStatusBadge",
)
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
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


def _guest_app(tmp_path: Path):
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
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


def _guest_client(tmp_path: Path) -> TestClient:
    return TestClient(_guest_app(tmp_path))


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


def _head(html: str) -> str:
    """The one generated Act head: `<section class="panel ActHead …">`."""
    return html.split('class="panel ActHead', 1)[1].split("</section>", 1)[0]


def _band(html: str) -> str:
    return _head(html).split("data-act-list", 1)[0]


def _cta(html: str) -> str:
    return _band(html).split('<div class="ActHead-cta', 1)[1].split("</div>", 1)[0]


def _tabs(html: str) -> str:
    return html.split("data-guest-phone-tabs", 1)[1].split("</nav>", 1)[0]


def _facts(client: TestClient) -> dict:
    history = tuple(
        sorted(
            (row.id, row.status, row.tier, row.is_current)
            for row in client.app.state.subscriptions.list_subscription_history(USER)
        )
    )
    roster = getattr(client.app.state, "roster", None)
    overlay = getattr(client.app.state, "playground", None)
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
    }


def test_phone_guest_ndps_uses_live_head_and_primary(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    page = client.get("/laws/ndps")
    assert page.status_code == 200
    html = unescape(page.text)
    assert 'data-act-head="ndps"' in html
    assert 'data-pg-kind="guest"' in html
    band = _band(html)
    assert f'<h1 class="ActHead-title">{TITLE}</h1>' in band
    assert f'<p class="ActHead-kicker">{KICKER}</p>' in band
    assert f'<p class="ActHead-meta">{META}</p>' in band
    assert META == "8 Chapters · Sections 1–83 · Schedule"
    assert '<a class="ActHead-back" href="/laws">← Laws</a>' in band
    assert PRIMARY in band
    assert html.count(PRIMARY) == 1
    assert html.count('class="ActHead-cta LawPlaygroundCta"') == 1
    cta = _cta(html)
    assert f'href="{add_path("ndps")}"' in cta
    assert "data-pg-sheet" in cta
    assert 'data-pg-kind="guest"' in cta
    assert 'class="ActHead-btn"' in cta
    assert cta.count("<a") == 1
    assert '<p class="ActHead-note">Sign in to add this law to Playground.</p>' in cta
    assert 'href="/login"' not in band
    assert "data-bareact-tabs" not in html
    for phrase in FORBIDDEN:
        assert phrase not in _head(html), phrase
    # M2 Q2: About this act stays, collapsed, below the CTA.
    assert "About this act" in band
    assert band.index("ActHead-about") > band.index("ActHead-cta")
    # M2 Q1/Q3: eight chapter rows off the model, each a closed <summary>
    # that expands into its section links; the schedule row opens its reader.
    rows = _head(html).split("data-act-list", 1)[1]
    assert rows.count('<details class="bareact-chapter">') == NDPS.chapter_count == 8
    assert rows.count('<summary class="bareact-chapter-row" aria-expanded="false">') == 8
    assert "<details open" not in rows
    for chapter in NDPS.chapters:
        assert f'<span class="bareact-chapter-tag">Chapter {chapter.number}</span>' in rows
        assert f'<span class="bareact-chapter-name">{chapter.title}</span>' in rows
        assert (
            f'<span class="ActHead-range-word">Sections </span>{chapter.range_label}</span>'
        ) in rows
    assert rows.count('<a class="bareact-section-row" href="/laws/ndps/section/') == len(
        NDPS.section_order
    )
    assert rows.count('<div class="bareact-schedule-row') == len(NDPS.schedules) == 1
    assert 'href="/laws/ndps/schedule/' in rows


def test_phone_guest_five_tabs_browse_active(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/laws/ndps").text
    assert "data-guest-phone-tabs" in html  # M1: shared guest bar
    assert "mobile-tabbar is-guest" not in html
    tabs = _tabs(html)
    labels = []
    for label, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        labels.append(label)
        assert label in tabs
    assert labels == ["Today", "Browse", "Playground", "Calendar", "Profile"]
    browse = tabs.split('href="/browse"', 1)[1].split("</a>", 1)[0]
    assert "is-active" in browse
    assert 'aria-current="page"' in browse
    for href in ("/dashboard", "/playground", "/calendar", "/profile"):
        chunk = tabs.split(f'href="{href}"', 1)[1].split("</a>", 1)[0]
        assert "is-active" not in chunk
    browse_page = _guest_client(tmp_path / "browse").get("/browse").text
    assert "data-guest-phone-tabs" in browse_page  # M1: Browse shares the bar
    assert "mobile-tabbar is-guest" not in browse_page


def test_phone_guest_add_sheet_is_existing_guest_kind(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    before = _facts(client)
    sheet = client.get(add_path("ndps"))
    assert sheet.status_code == 200
    assert 'data-pg-kind="guest"' in sheet.text
    assert "data-pg-add" in sheet.text
    # M2 Q4: the direct Add URL is the Act page with the sheet open; closing
    # it returns to the Act.
    assert 'data-act-head="ndps"' in sheet.text
    assert "data-pg-sheet-direct" in sheet.text
    assert 'data-pg-sheet-return="/laws/ndps"' in sheet.text
    assert _facts(client) == before


def test_phone_guest_gets_are_mutation_free(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    before = _facts(client)
    assert before["session"] is None
    assert before["subscription"] is None
    for url in ("/laws/ndps", add_path("ndps"), "/laws"):
        page = client.get(url)
        assert page.status_code == 200
        assert _facts(client) == before


def test_one_head_serves_both_widths_and_other_laws(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    html = client.get("/laws/ndps").text
    # M2 §2.1: one head, no twins; the back link and CTA are the same markup
    # at both widths.
    assert html.count('class="panel ActHead') == 1
    for gone in (
        "data-guest-bareact-desktop",
        "data-guest-bareact-phone",
        "data-bareact-phone",
        "guest-bareact-",
    ):
        assert gone not in html, gone
    band = _band(html)
    assert PRIMARY in band
    assert "← Laws" in band
    assert '<a class="ActHead-back" href="/laws">' in band
    bns = client.get("/laws/bns").text
    bns_act = get_bare_act("bns")
    assert 'data-act-head="bns"' in bns
    assert bns.count('class="panel ActHead') == 1
    assert bns.count('<details class="bareact-chapter">') == bns_act.chapter_count
    assert f'<p class="ActHead-meta">{bns_act.head_meta_label}</p>' in bns
    assert PRIMARY in bns  # the guest head is generated for every Act
    section = client.get("/laws/ndps/section/1").text
    assert "ActHead" not in section
    landing = client.get("/").text
    assert 'data-guest-landing="desktop"' in landing
    laws = client.get("/laws").text
    assert "data-guest-laws-desktop" in laws
    assert "ActHead" not in laws


def test_signed_in_plus_expired_halted_get_their_own_state_cta(
    tmp_path: Path,
) -> None:
    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/laws/ndps").text
    assert "data-guest-phone-tabs" not in free_html
    assert "data-signed-in-bareact-phone-tabs" in free_html
    assert free_html.count('class="panel ActHead') == 1
    assert "data-plus-bareact" not in free_html
    assert "data-expired-bareact" not in free_html
    assert "data-halted-bareact" not in free_html
    free_cta = _cta(free_html)
    assert "Subscribe to use Playground" in free_cta
    assert PRIMARY not in free_html
    assert 'data-pg-kind="subscribe"' in free_cta
    assert f'href="{add_path("ndps")}"' in free_cta
    assert "data-pg-sheet" in free_cta
    assert "Sign in to add this law" not in free_html
    assert free_html.count('class="ActHead-cta LawPlaygroundCta"') == 1
    assert free_html.count('<details class="bareact-chapter">') == NDPS.chapter_count

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get("/laws/ndps").text
    assert "data-guest-phone-tabs" not in plus_html
    assert "data-plus-bareact" in plus_html
    plus_cta = _cta(plus_html)
    assert 'data-pg-kind="eligible_to_add"' in plus_cta
    assert "+ Add to Playground" in plus_cta
    assert f'href="{add_path("ndps")}"' in plus_cta
    assert "data-pg-sheet" in plus_cta
    assert PRIMARY not in plus_html
    assert "Subscribe to use Playground" not in plus_html
    assert plus_html.count('class="ActHead-cta LawPlaygroundCta"') == 1

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
    assert "data-guest-phone-tabs" not in expired_html
    assert "data-expired-bareact" in expired_html
    expired_cta = _cta(expired_html)
    assert "Resume Playground" in expired_cta
    assert 'data-pg-kind="resume"' in expired_cta
    assert 'href="/billing/subscriptions"' in expired_cta  # M2-F04: live destination
    assert PRIMARY not in expired_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/laws/ndps").text
    assert "data-guest-phone-tabs" not in halted_html
    assert "data-halted-bareact" in halted_html
    halted_cta = _cta(halted_html)
    assert "Manage subscription" in halted_cta
    assert 'href="/billing/subscriptions"' in halted_cta  # M2-F04: live destination
    assert PRIMARY not in halted_html
    assert halted_html.count('class="ActHead-cta LawPlaygroundCta"') == 1


def test_phone_guest_markers_and_pins() -> None:
    bare = BARE.read_text(encoding="utf-8")
    assert 'data-act-head="{{ act.slug }}"' in bare
    assert "← Laws" in bare
    assert 'data-pg-kind="{{ pg.kind }}"' in bare
    assert "data-guest-bareact-phone" not in bare
    assert "data-guest-bareact-desktop" not in bare
    assert "data-bareact-phone" not in bare
    assert "data-bareact-tabs" not in bare
    base = BASE.read_text(encoding="utf-8")
    assert "data-guest-phone-tabs" in base
    assert "styles.css?v=main88" in base
    assert "mobile.css?v=mob107" in base
    assert "styles.css?v=main87" not in base
    assert "mobile.css?v=mob106" not in base
    assert "mobile.css?v=mob99" not in base
    styles = STYLES.read_text(encoding="utf-8")
    assert "Bare Act head (M2)" in styles
    assert "data-guest-bareact-phone" not in styles
    assert "data-guest-bareact-desktop" not in styles
    m2 = styles.split("Bare Act head (M2)", 1)[1]
    phone_block = m2.split("@media (max-width: 560px) {", 1)[1].split("\n}\n", 1)[0]
    assert ".ActHead-row {" in phone_block
    assert "flex-direction: column" in phone_block
    range_word = phone_block.split(".ActHead-range-word {", 1)[1].split("}", 1)[0]
    assert "display: none" in range_word
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "guest/01-screen" not in mobile
    assert "data-guest-bareact-phone" not in mobile
    assert "data-signed-in-bareact-desktop" not in mobile
    assert 'body[data-mscreen="bareact"] .bareact-chapter-row {' in mobile
    assert 'body[data-mscreen="bareact"] .bareact-section-row {' in mobile


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


def test_phone_guest_bareact_screen01_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_guest_bareact_screen01_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        page = browser.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
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
              const heads = document.querySelectorAll('.ActHead');
              const head = heads[0];
              const header = document.querySelector('.site-header');
              const tabs = document.querySelector('[data-guest-phone-tabs]');
              const cta = head && head.querySelector('.ActHead-btn');
              const back = head && head.querySelector('.ActHead-back');
              const rows = head ? [...head.querySelectorAll('.bareact-chapter-row')] : [];
              const sectionLinks = head ? [...head.querySelectorAll('a.bareact-section-row')] : [];
              const visibleSectionLinks = sectionLinks.filter((a) => a.offsetParent !== null);
              const active = tabs && tabs.querySelector('.mobile-tab.is-active');
              const tabLinks = tabs ? [...tabs.querySelectorAll('a.mobile-tab')] : [];
              const headerChip = document.querySelector('[data-guest-account-menu]');
              return {
                heads: heads.length,
                headDisplay: head ? getComputedStyle(head).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                title: head && head.querySelector('.ActHead-title').textContent.trim(),
                kicker: head && head.querySelector('.ActHead-kicker').textContent.trim(),
                meta: head && head.querySelector('.ActHead-meta').textContent.trim(),
                rangeWordDisplay: head && getComputedStyle(head.querySelector('.ActHead-range-word')).display,
                backText: back && back.textContent.replace(/\\s+/g, ' ').trim(),
                backHref: back && back.getAttribute('href'),
                ctaText: cta && cta.textContent.trim(),
                ctaHref: cta && cta.getAttribute('href'),
                ctaSheet: cta && cta.hasAttribute('data-pg-sheet'),
                ctaWidth: cta ? cta.getBoundingClientRect().width : 0,
                rowCount: rows.length,
                rowTitles: rows.map((el) => el.querySelector('.bareact-chapter-name').textContent.trim()),
                openChapters: head ? head.querySelectorAll('details.bareact-chapter[open]').length : -1,
                visibleSectionLinks: visibleSectionLinks.length,
                tabLabels: tabLinks.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabLinks.map((el) => el.getAttribute('href')),
                browseActive: active && active.textContent.replace(/\\s+/g, ' ').trim(),
                chipDisplay: headerChip ? getComputedStyle(headerChip).display : null,
                already: head && head.innerText.includes('Already in Playground'),
                subscribe: head && head.innerText.includes('Subscribe to use Playground'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        page.locator(".ActHead .ActHead-btn").click()
        page.wait_for_selector("[data-pg-add]", timeout=8000)
        dialog = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              return {
                kind: panel && panel.getAttribute('data-pg-kind'),
                url: location.pathname,
              };
            }"""
        )
        page.keyboard.press("Escape")
        still = page.evaluate("() => location.pathname")
        browser.close()

    assert geo["heads"] == 1
    assert geo["headDisplay"] != "none"
    assert geo["headerDisplay"] == "none"
    assert geo["tabsDisplay"] != "none"
    assert geo["overflow"] is False
    assert geo["title"] == TITLE
    assert geo["kicker"] == KICKER
    assert geo["meta"] == META
    assert geo["rangeWordDisplay"] == "none"
    assert geo["backText"] == "← Laws"
    assert geo["backHref"] == "/laws"
    assert geo["ctaText"] == PRIMARY
    assert geo["ctaHref"] == add_path("ndps")
    assert geo["ctaSheet"] is True
    assert geo["ctaWidth"] >= 300
    assert geo["rowCount"] == NDPS.chapter_count == 8
    assert geo["rowTitles"] == [c.title for c in NDPS.chapters]
    assert geo["openChapters"] == 0
    assert geo["visibleSectionLinks"] == 0
    assert geo["tabLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["tabHrefs"] == [
        "/dashboard",
        "/browse",
        "/playground",
        "/calendar",
        "/profile",
    ]
    assert geo["browseActive"] == "Browse"
    assert geo["already"] is False
    assert geo["subscribe"] is False
    assert dialog["kind"] == "guest"
    assert still.endswith("/laws/ndps")
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_guest_bareact_screen01_desktop_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_guest_bareact_screen01_desktop_regression_1280.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        page = browser.new_page(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
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
              const heads = document.querySelectorAll('.ActHead');
              const head = heads[0];
              const tabs = document.querySelector('[data-guest-phone-tabs]');
              const header = document.querySelector('.site-header');
              const cta = head && head.querySelector('.ActHead-btn');
              const nav = [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                (el) => el.textContent.replace(/\\s+/g, ' ').trim()
              );
              return {
                heads: heads.length,
                headDisplay: head ? getComputedStyle(head).display : null,
                rangeWordDisplay: head && getComputedStyle(head.querySelector('.ActHead-range-word')).display,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                ctaText: cta && cta.textContent.trim(),
                ctaHref: cta && cta.getAttribute('href'),
                navLabels: nav,
                title: head && head.querySelector('.ActHead-title').textContent.trim(),
                account: document.querySelector('.account-menu-btn-name')
                  && document.querySelector('.account-menu-btn-name').textContent.trim(),
              };
            }"""
        )
        plus_app = _mu_app(tmp_path / "plus-phone")
        plus_client = TestClient(plus_app)
        _sign_in(plus_client)
        _subscribe(plus_client)
        plus_port, _plus_server = _serve(plus_app, host="127.0.0.1")
        plus_page = browser.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        plus_origin = f"http://127.0.0.1:{plus_port}"
        session = plus_client.cookies.get(SESSION_COOKIE_NAME)
        plus_page.context.add_cookies(
            [
                {
                    "name": SESSION_COOKIE_NAME,
                    "value": session,
                    "url": plus_origin,
                    "httpOnly": True,
                    "secure": False,
                    "sameSite": "Lax",
                }
            ]
        )
        plus_page.goto(f"{plus_origin}/laws/ndps", wait_until="networkidle")
        plus_geo = plus_page.evaluate(
            """() => {
              const heads = document.querySelectorAll('.ActHead');
              const head = heads[0];
              const cta = head && head.querySelector('.ActHead-btn');
              return {
                heads: heads.length,
                headDisplay: head ? getComputedStyle(head).display : null,
                plusMarker: head ? head.hasAttribute('data-plus-bareact') : null,
                kind: cta && cta.getAttribute('data-pg-kind'),
                details: head ? head.querySelectorAll('details').length : 0,
                cta: head && head.innerText.includes('Sign in to use Playground'),
                ctaText: cta && cta.textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["heads"] == 1
    assert geo["headDisplay"] != "none"
    assert geo["rangeWordDisplay"] != "none"
    assert geo["tabsDisplay"] == "none"
    assert geo["headerDisplay"] != "none"
    assert geo["ctaText"] == PRIMARY
    assert geo["ctaHref"] == add_path("ndps")
    assert geo["navLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["title"] == TITLE
    assert geo["account"] == "Guest"
    assert plus_geo["heads"] == 1
    assert plus_geo["headDisplay"] != "none"
    assert plus_geo["plusMarker"] is True
    assert plus_geo["kind"] == "eligible_to_add"
    assert plus_geo["details"] == NDPS.chapter_count == 8
    assert plus_geo["cta"] is False
    assert plus_geo["ctaText"] == "+ Add to Playground"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
