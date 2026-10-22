"""Phone signed-in Free Bare Act head Screen 01 (CTA map signedIn/01-screen).

Authorized: ChatGPT. Authenticated Free GET /laws/ndps at 390x844. Since M2
the head is ONE generated `.ActHead` for every Act and every viewer (same
markup on both widths; the phone layout is CSS under `@media (max-width:
560px)`). Map enrolled cluster is composition-only; CTA is Subscribe to use
Playground. Guest, desktop, and Plus/Expired/Halted stay separate by
`data-pg-kind` and the lifecycle attributes. Add-sheet Screen 02 is not this
screen.
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
from constitution_memorizer.playground.urls import add_path, home_path
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
ADD_PANEL = ROOT / "src/constitution_memorizer/web/templates/partials/playground_add_panel.html"
USER = UUID("11111111-1111-4111-8111-111111111111")
NDPS = get_bare_act("ndps")
KICKER = "Bare Act · India Code"
TITLE = NDPS.title
META = NDPS.head_meta_label
PRIMARY = "Subscribe to use Playground"
GUEST_PRIMARY = "Sign in to use Playground"
GUEST_NOTE = "Sign in to add this law to Playground."
# The state's explanatory line under the Free button: the plan price.
FREE_NOTE = "Unlock Playground · from ₹199 / month."
FORBIDDEN = (
    "Already in Playground",
    ">Sections</a>",
    ">Continue</a>",
    ">Manage<",
    "Resume Playground",
    "Add to Playground",
    ">Unlock Playground</a>",
    "Start learning",
    "LawStatusBadge",
    GUEST_PRIMARY,
    GUEST_NOTE,
)
OLD_MARKERS = (
    "data-signed-in-bareact-desktop",
    "data-guest-bareact-desktop",
    "data-guest-bareact-phone",
    "data-bareact-phone",
    "guest-bareact-",
    "signed-bareact-",
    "data-bareact-tabs",
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


def _free_client(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    return client


def _head(html: str, slug: str = "ndps") -> str:
    """The whole generated `.ActHead` section: band + list."""
    return html.split(f'data-act-head="{slug}"', 1)[1].split("</section>", 1)[0]


def _head_attrs(html: str, slug: str = "ndps") -> str:
    return html.split(f'data-act-head="{slug}"', 1)[1].split(">", 1)[0]


def _band(html: str, slug: str = "ndps") -> str:
    return _head(html, slug).split("data-act-list", 1)[0]


def _tabs(html: str) -> str:
    return html.split("data-signed-in-bareact-phone-tabs", 1)[1].split("</nav>", 1)[0]


def _sheet(html: str) -> str:
    return html.split('class="pg-sheet-panel"', 1)[1].split("</section>", 1)[0]


def _assert_no_old_markers(html: str) -> None:
    scrubbed = html.replace("data-signed-in-bareact-phone-tabs", "")
    assert "data-signed-in-bareact-phone" not in scrubbed
    for marker in OLD_MARKERS:
        assert marker not in scrubbed, marker


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


def test_phone_signed_in_free_ndps_uses_subscribe_head(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    page = client.get("/laws/ndps")
    assert page.status_code == 200
    html = unescape(page.text)
    assert html.count('data-act-head="ndps"') == 1
    _assert_no_old_markers(html)
    attrs = _head_attrs(html)
    assert 'data-pg-kind="subscribe"' in attrs
    assert "data-plus-bareact" not in attrs
    assert "data-expired-bareact" not in attrs
    assert "data-halted-bareact" not in attrs
    head = _head(html)
    band = _band(html)
    assert f'<h1 class="ActHead-title">{TITLE}</h1>' in band
    assert KICKER in band
    assert f'<p class="ActHead-meta">{META}</p>' in band
    assert META == "8 Chapters · Sections 1–83 · Schedule"
    assert '<a class="ActHead-back" href="/laws">← Laws</a>' in band
    assert PRIMARY in band
    assert head.count(PRIMARY) == 1
    assert f'href="{add_path("ndps")}"' in band
    assert "data-pg-sheet" in band
    assert 'class="ActHead-btn"' in band
    assert "ActHead-btn--ghost" not in band
    assert 'data-pg-kind="subscribe"\n        >' + PRIMARY + "</a>" in band
    assert 'href="/billing/subscriptions"' not in head
    assert 'href="/playground"' not in head
    assert 'href="/login"' not in head
    assert 'class="ActHead-cta LawPlaygroundCta" data-law-id="ndps" data-pg-kind="subscribe"' in band
    assert f'<p class="ActHead-note">{FREE_NOTE}</p>' in band
    assert band.count("ActHead-note") == 1
    assert band.index("ActHead-btn") < band.index("ActHead-note")
    assert "ActHead-link" not in head
    for phrase in FORBIDDEN:
        assert phrase not in head, phrase
    # About-this-act is kept, collapsed, below the action row (M2 Q2).
    assert "About this act" in band
    assert 'data-bareact-info-toggle\n      aria-expanded="false"' in band
    assert 'data-bareact-info hidden' in band
    assert band.index("ActHead-cta") < band.index("ActHead-about")
    assert "data-bareact-tabs" not in head
    # The list is generated from the Act (M2 §4 Q1): eight chapter rows, each
    # a closed <details> expanding into its section links (Q3), then the
    # schedule row opening its reader.
    rows = head.split("data-act-list", 1)[1]
    assert rows.count('<details class="bareact-chapter">') == NDPS.chapter_count == 8
    assert "<details open" not in rows and '<details class="bareact-chapter" open' not in rows
    assert (
        rows.count('<summary class="bareact-chapter-row" aria-expanded="false">')
        == NDPS.chapter_count
    )
    for chapter in NDPS.chapters:
        assert f'<span class="bareact-chapter-tag">Chapter {chapter.number}</span>' in rows
        assert f'<span class="bareact-chapter-name">{chapter.title}</span>' in rows
        assert (
            '<span class="bareact-chapter-range"><span class="ActHead-range-word">'
            f"Sections </span>{chapter.range_label}</span>"
        ) in rows
    assert rows.count('class="bareact-section-row" href="/laws/ndps/section/') == sum(
        len(chapter.sections) for chapter in NDPS.chapters
    )
    assert rows.count('<div class="bareact-schedule-row') == len(NDPS.schedules) == 1
    assert f'href="/laws/ndps/schedule/{NDPS.schedules[0].slug}"' in rows
    assert "This Act has no Schedules." not in head
    assert client.app.state.subscriptions.get_current_subscription(USER) is None
    assert _facts(client)["active"] == ()


def test_phone_signed_in_five_tabs_browse_active(tmp_path: Path) -> None:
    html = _free_client(tmp_path).get("/laws/ndps").text
    assert "data-signed-in-bareact-phone-tabs" in html
    assert "data-guest-bareact-phone-tabs" not in html
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
    dash = _free_client(tmp_path / "dash").get("/dashboard").text
    assert "data-signed-in-bareact-phone-tabs" not in dash


def test_phone_signed_in_add_sheet_is_existing_subscribe_kind(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    before = _facts(client)
    sheet = client.get(add_path("ndps"))
    assert sheet.status_code == 200
    html = sheet.text
    assert "data-pg-add" in html
    assert html.count('class="pg-sheet-panel"') == 1
    panel = _sheet(html)
    assert 'data-pg-kind="subscribe"' in panel
    assert "data-expired-add" not in panel
    assert "data-halted-add" not in panel
    assert f'<a class="pg-add-primary" href="{home_path()}">Unlock Playground</a>' in panel
    assert 'href="/billing/subscriptions"' not in panel
    assert "data-pg-sheet-close" not in panel
    assert ">Cancel<" not in panel
    # M2 Q4: the direct Add URL is the Act page with the sheet open inside a
    # <dialog>; closing it returns to the Act.
    assert (
        '<dialog class="pg-sheet" data-pg-sheet-host data-pg-sheet-direct '
        'data-pg-sheet-return="/laws/ndps"' in html
    )
    assert 'aria-labelledby="pg-add-title" open>' in html
    assert 'data-act-head="ndps"' in html
    assert PRIMARY in _band(html)
    assert 'data-mscreen="bareact"' in html
    assert "PlaygroundShell" not in html
    assert "data-hard-gate" not in html
    assert _facts(client) == before


def test_phone_signed_in_gets_are_mutation_free(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    before = _facts(client)
    assert before["session"] is not None
    assert before["subscription"] is None
    assert before["active"] == ()
    for url in ("/laws/ndps", add_path("ndps"), "/laws"):
        page = client.get(url)
        assert page.status_code == 200
        assert _facts(client) == before


def test_desktop_guest_plus_expired_halted_stay_separate(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    html = client.get("/laws/ndps").text
    # One head on both widths: the desktop copy is this same section.
    assert html.count('data-act-head="ndps"') == 1
    band = _band(html)
    assert PRIMARY in band
    assert "← Laws" in band
    assert '<a class="ActHead-back" href="/laws">← Laws</a>' in band
    bns = client.get("/laws/bns").text
    assert 'data-act-head="bns"' in bns
    assert 'data-act-head="ndps"' not in bns
    assert PRIMARY in _band(bns, "bns")
    section = client.get("/laws/ndps/section/1").text
    assert "data-act-head" not in section
    assert PRIMARY not in section

    guest = TestClient(_guest_app(tmp_path / "guest"))
    guest_html = guest.get("/laws/ndps").text
    _assert_no_old_markers(guest_html)
    assert 'data-pg-kind="guest"' in _head_attrs(guest_html)
    guest_band = _band(guest_html)
    assert GUEST_PRIMARY in guest_band
    assert f'<p class="ActHead-note">{GUEST_NOTE}</p>' in guest_band
    assert PRIMARY not in guest_band
    assert FREE_NOTE not in guest_band
    assert "data-plus-bareact" not in guest_html

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get("/laws/ndps").text
    _assert_no_old_markers(plus_html)
    plus_attrs = _head_attrs(plus_html)
    assert "data-plus-bareact" in plus_attrs
    assert 'data-pg-kind="eligible_to_add"' in plus_attrs
    plus_band = _band(plus_html)
    assert 'class="ActHead-cta LawPlaygroundCta"' in plus_band
    assert "+ Add to Playground" in plus_band
    assert PRIMARY not in plus_band
    assert FREE_NOTE not in plus_band
    assert GUEST_PRIMARY not in plus_band

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
    expired_attrs = _head_attrs(expired_html)
    assert "data-expired-bareact" in expired_attrs
    assert "data-plus-bareact" not in expired_attrs
    expired_band = _band(expired_html)
    assert "Resume Playground" in expired_band
    assert PRIMARY not in expired_band
    assert FREE_NOTE not in expired_band

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/laws/ndps").text
    halted_attrs = _head_attrs(halted_html)
    assert "data-halted-bareact" in halted_attrs
    assert "data-plus-bareact" not in halted_attrs
    halted_band = _band(halted_html)
    assert 'class="ActHead-cta LawPlaygroundCta"' in halted_band
    assert GUEST_PRIMARY not in halted_band
    assert PRIMARY not in halted_band
    assert FREE_NOTE not in halted_band


def test_phone_signed_in_markers_and_pins() -> None:
    bare = BARE.read_text(encoding="utf-8")
    assert 'data-act-head="{{ act.slug }}"' in bare
    assert "← Laws" in bare
    assert 'class="ActHead-btn' in bare
    assert "data-pg-sheet" in bare
    assert "{{ pg.primary_label }}" in bare
    assert "{{ pg.secondary_copy }}" in bare
    assert 'class="ActHead-cta LawPlaygroundCta"' in bare
    for marker in OLD_MARKERS:
        assert marker not in bare, marker
    assert "data-signed-in-bareact-phone" not in bare
    assert "guest_screen4" not in bare
    base = BASE.read_text(encoding="utf-8")
    assert "data-signed-in-bareact-phone-tabs" in base
    assert "styles.css?v=main88" in base
    assert "mobile.css?v=mob107" in base
    assert "mobile.css?v=mob106" not in base
    assert "styles.css?v=main87" not in base
    styles = STYLES.read_text(encoding="utf-8")
    assert "[data-signed-in-bareact-phone]" not in styles
    assert "[data-signed-in-bareact-desktop]" not in styles
    m2 = styles.split("Bare Act head (M2)", 1)[1]
    phone = m2.split("@media (max-width: 560px) {", 1)[1].split("\n}\n", 1)[0]
    cta = phone.split(".ActHead-cta,\n  .ActHead-cta.LawPlaygroundCta {", 1)[1].split("}", 1)[0]
    assert "width: 100%" in cta
    desk_cta = m2.split(".ActHead-cta,\n.ActHead-cta.LawPlaygroundCta {", 1)[1].split("}", 1)[0]
    assert "width: 380px" in desk_cta
    assert "flex: none" in cta
    title = phone.split(".ActHead-title {", 1)[1].split("}", 1)[0]
    assert "font-size: 19px" in title
    assert ".ActHead-range-word" in phone
    row = phone.split(".ActHead-row {", 1)[1].split("}", 1)[0]
    assert "flex-direction: column" in row
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-signed-in-bareact-phone" not in mobile
    assert 'body[data-mscreen="bareact"] .bareact-chapter-row' in mobile
    assert 'body[data-mscreen="bareact"] .bareact-section-row' in mobile
    add = ADD.read_text(encoding="utf-8")
    assert "data-signed-in-add-phone" not in add
    assert "data-signed-in-add-desktop" not in add
    assert '{% include "partials/playground_add_panel.html" %}' in add
    panel = ADD_PANEL.read_text(encoding="utf-8")
    assert "data-signed-in-add-phone" not in panel
    assert "data-signed-in-add-desktop" not in panel
    subscribe = panel.split('{% elif kind == "subscribe" %}', 1)[1].split(
        '{% elif kind == "resume" %}', 1
    )[0]
    assert '<a class="pg-add-primary" href="/playground">Unlock Playground</a>' in subscribe
    assert 'href="/billing/subscriptions"' not in subscribe
    assert "Cancel" not in subscribe


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


def test_phone_signed_in_bareact_screen01_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_signed_in_bareact_screen01_390x844.png"
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
              const head = document.querySelector('[data-act-head="ndps"]');
              const header = document.querySelector('.site-header');
              const tabs = document.querySelector('[data-signed-in-bareact-phone-tabs]');
              const cta = head && head.querySelector('.ActHead-btn');
              const back = head && head.querySelector('.ActHead-back');
              const chapters = head ? [...head.querySelectorAll('details.bareact-chapter')] : [];
              const schedules = head ? [...head.querySelectorAll('.bareact-schedule-row')] : [];
              const active = tabs && tabs.querySelector('.mobile-tab.is-active');
              const tabLinks = tabs ? [...tabs.querySelectorAll('a.mobile-tab')] : [];
              return {
                headCount: document.querySelectorAll('[data-act-head]').length,
                headDisplay: head ? getComputedStyle(head).display : null,
                pgKind: head && head.getAttribute('data-pg-kind'),
                plus: head && head.hasAttribute('data-plus-bareact'),
                headerDisplay: header ? getComputedStyle(header).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                title: head && head.querySelector('.ActHead-title').textContent.trim(),
                kicker: head && head.querySelector('.ActHead-kicker').textContent.trim(),
                meta: head && head.querySelector('.ActHead-meta').textContent.trim(),
                backText: back && back.textContent.replace(/\\s+/g, ' ').trim(),
                backHref: back && back.getAttribute('href'),
                ctaText: cta && cta.textContent.trim(),
                ctaHref: cta && cta.getAttribute('href'),
                ctaSheet: cta && cta.hasAttribute('data-pg-sheet'),
                ctaKind: cta && cta.getAttribute('data-pg-kind'),
                ctaWidth: cta ? cta.getBoundingClientRect().width : 0,
                ctaHeight: cta ? cta.getBoundingClientRect().height : 0,
                chapterCount: chapters.length,
                openChapters: chapters.filter((el) => el.open).length,
                chapterNames: chapters.map((el) => el.querySelector('.bareact-chapter-name').textContent.trim()),
                scheduleCount: schedules.length,
                rangeWord: head && getComputedStyle(head.querySelector('.ActHead-range-word')).display,
                aboutBelowCta: head && head.querySelector('.ActHead-cta').getBoundingClientRect().bottom <=
                  head.querySelector('.ActHead-about').getBoundingClientRect().top,
                tabLabels: tabLinks.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabLinks.map((el) => el.getAttribute('href')),
                browseActive: active && active.textContent.replace(/\\s+/g, ' ').trim(),
                already: head && head.innerText.includes('Already in Playground'),
                inpg: !!(head && head.querySelector('.ActHead-inpg')),
                note: head && head.querySelector('.ActHead-note') &&
                  head.querySelector('.ActHead-note').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        page.locator('[data-act-head="ndps"] .ActHead-btn').click()
        page.wait_for_selector("[data-pg-add]", timeout=8000)
        dialog = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const unlock = panel && panel.querySelector('.pg-add-primary');
              return {
                kind: panel && panel.getAttribute('data-pg-kind'),
                url: location.pathname,
                title: panel && panel.querySelector('#pg-add-title').textContent.trim(),
                unlockText: unlock && unlock.textContent.trim(),
                unlockHref: unlock && unlock.getAttribute('href'),
                billing: !!(panel && panel.querySelector('a[href="/billing/subscriptions"]')),
                cancel: !!(panel && panel.querySelector('[data-pg-sheet-close].pg-add-secondary')),
              };
            }"""
        )
        page.keyboard.press("Escape")
        still = page.evaluate("() => location.pathname")
        browser.close()

    assert geo["headCount"] == 1
    assert geo["headDisplay"] != "none"
    assert geo["pgKind"] == "subscribe"
    assert geo["plus"] is False
    assert geo["headerDisplay"] == "none"
    assert geo["tabsDisplay"] != "none"
    assert geo["overflow"] is False
    assert geo["title"] == TITLE
    assert geo["kicker"] == KICKER
    assert geo["meta"] == META
    assert geo["backText"] == "← Laws"
    assert geo["backHref"] == "/laws"
    assert geo["ctaText"] == PRIMARY
    assert geo["ctaHref"] == add_path("ndps")
    assert geo["ctaSheet"] is True
    assert geo["ctaKind"] == "subscribe"
    assert geo["ctaWidth"] >= 300
    assert geo["ctaHeight"] >= 44
    assert geo["chapterCount"] == NDPS.chapter_count == 8
    assert geo["openChapters"] == 0
    assert geo["chapterNames"] == [c.title for c in NDPS.chapters]
    assert geo["scheduleCount"] == len(NDPS.schedules) == 1
    assert geo["rangeWord"] == "none"
    assert geo["aboutBelowCta"] is True
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
    assert geo["inpg"] is False
    assert geo["note"] == FREE_NOTE
    assert dialog["kind"] == "subscribe"
    assert dialog["title"] == "Add to Playground"
    assert still.endswith("/laws/ndps")
    assert dialog["unlockText"] == "Unlock Playground"
    assert dialog["unlockHref"] == "/playground"
    assert dialog["billing"] is False
    assert dialog["cancel"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_signed_in_bareact_screen01_desktop_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_signed_in_bareact_screen01_desktop_regression_1280.png"
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
              const head = document.querySelector('[data-act-head="ndps"]');
              const tabs = document.querySelector('[data-signed-in-bareact-phone-tabs]');
              const header = document.querySelector('.site-header');
              const cta = head && head.querySelector('.ActHead-btn');
              const nav = [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                (el) => el.textContent.replace(/\\s+/g, ' ').trim()
              );
              return {
                headCount: document.querySelectorAll('[data-act-head]').length,
                headDisplay: head ? getComputedStyle(head).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                ctaText: cta && cta.textContent.trim(),
                ctaHref: cta && cta.getAttribute('href'),
                ctaKind: cta && cta.getAttribute('data-pg-kind'),
                ctaWidth: cta ? cta.getBoundingClientRect().width : 0,
                rangeWord: head && getComputedStyle(head.querySelector('.ActHead-range-word')).display,
                navLabels: nav,
                title: head && head.querySelector('.ActHead-title').textContent.trim(),
                account: document.querySelector('.account-menu-btn-name')
                  && document.querySelector('.account-menu-btn-name').textContent.trim(),
                status: document.querySelector('.account-menu-btn-status')
                  && document.querySelector('.account-menu-btn-status').textContent.trim(),
                already: head && head.innerText.includes('Already in Playground'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["headCount"] == 1
    assert geo["headDisplay"] != "none"
    assert geo["tabsDisplay"] == "none"
    assert geo["headerDisplay"] != "none"
    assert geo["ctaText"] == PRIMARY
    assert geo["ctaHref"] == add_path("ndps")
    assert geo["ctaKind"] == "subscribe"
    assert geo["ctaWidth"] == pytest.approx(380, abs=4)
    assert geo["rangeWord"] != "none"
    assert geo["navLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["title"] == TITLE
    assert geo["account"] == "Sanjay"
    assert geo["status"] == "Free account"
    assert geo["already"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
