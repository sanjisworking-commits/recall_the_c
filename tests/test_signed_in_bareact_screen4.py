"""Signed-in desktop NDPS Bare Act head (CTA map signedIn/04-screen).

Authorized: ChatGPT. Authenticated multiuser GET /laws/ndps. Since M2 the
head is ONE generated `.ActHead` for every Act and every viewer (same markup
on both widths; CSS does the layout) — the signed-in desktop twin and the
production phone block are gone. The Free CTA is "Subscribe to use
Playground" opening the Add sheet; an active subscriber sees "+ Add to
Playground" or the in-Playground chip. Signed-in Landing, Browse, and Laws
index stay unchanged. Chapter rows expand into section links (M2 Q3).
"""

from __future__ import annotations

import socket
import threading
import time
from datetime import datetime, timezone
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
from constitution_memorizer.playground.urls import add_path, sections_path
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
USER = UUID("11111111-1111-4111-8111-111111111111")
NDPS = get_bare_act("ndps")
KICKER = "Bare Act · India Code"
TITLE = NDPS.title
META = NDPS.head_meta_label
OLD_MARKERS = (
    "data-signed-in-bareact-desktop",
    "data-signed-in-bareact-phone",
    "data-guest-bareact-desktop",
    "data-guest-bareact-phone",
    "data-bareact-phone",
    "guest-bareact-",
    "signed-bareact-",
    "data-bareact-tabs",
    "This Act has no Schedules.",
)
FREE_NOTE = "Unlock Playground · from ₹199 / month."


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


def _seed_stale_ndps_roster(client: TestClient) -> None:
    roster = client.app.state.roster
    start, end = playground_month_bounds()
    roster._repo.ensure_period(
        USER,
        period_start=start,
        period_end=end,
        tier_snapshot="plus",
        law_limit=10,
    )
    result = roster._repo.consume_law(
        USER,
        period_start=start,
        law_id="ndps",
        law_limit=10,
        allow_new=True,
    )
    assert result.ok, result.status
    assert roster.is_law_active_this_period(USER, "ndps") is True


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _primary_nav(html: str) -> str:
    return html.split('aria-label="Primary"', 1)[1].split("</nav>", 1)[0]


def _head(html: str, slug: str = "ndps") -> str:
    """The whole generated `.ActHead` section: band + list."""
    return html.split(f'data-act-head="{slug}"', 1)[1].split("</section>", 1)[0]


def _band(html: str, slug: str = "ndps") -> str:
    """The head band only: back link, kicker/title/meta, CTA, About."""
    return _head(html, slug).split("data-act-list", 1)[0]


def _list(html: str, slug: str = "ndps") -> str:
    return _head(html, slug).split("data-act-list", 1)[1]


def _assert_no_old_markers(html: str) -> None:
    # The phone tabbar marker `data-signed-in-bareact-phone-tabs` survives in
    # base.html; only the deleted head twin shares its prefix.
    scrubbed = html.replace("data-signed-in-bareact-phone-tabs", "")
    for marker in OLD_MARKERS:
        assert marker not in scrubbed, marker


def test_signed_in_non_subscriber_shows_subscribe_not_already_in_playground(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_stale_ndps_roster(client)
    html = client.get("/laws/ndps").text
    assert 'data-act-head="ndps"' in html
    _assert_no_old_markers(html)
    head = _head(html)
    band = _band(html)
    assert 'data-pg-kind="subscribe"' in html.split('data-act-head="ndps"', 1)[1].split(">", 1)[0]
    assert "data-plus-bareact" not in head
    assert "data-expired-bareact" not in head
    assert "data-halted-bareact" not in head
    assert KICKER in band
    assert f'<h1 class="ActHead-title">{TITLE}</h1>' in band
    assert f'<p class="ActHead-meta">{META}</p>' in band
    assert "Subscribe to use Playground" in band
    assert head.count("Subscribe to use Playground") == 1
    assert f'href="{add_path("ndps")}"' in band
    assert "data-pg-sheet" in band
    assert (
        'class="ActHead-cta LawPlaygroundCta" data-law-id="ndps" data-pg-kind="subscribe"'
        in band
    )
    assert 'data-pg-kind="subscribe"\n        >Subscribe to use Playground</a>' in band
    # The state's own explanatory line under the button: the plan price.
    assert f'<p class="ActHead-note">{FREE_NOTE}</p>' in band
    assert band.count("ActHead-note") == 1
    assert band.index("ActHead-btn") < band.index("ActHead-note")
    assert "LawStatusBadge" not in band
    assert "Already in Playground" not in head
    assert ">Sections</a>" not in head
    assert ">Continue</a>" not in head
    assert "Start learning" not in head
    assert "ActHead-inpg" not in head
    assert "Sign in to use Playground" not in head
    assert "Sign in to add this law" not in head
    assert "+ Add to Playground" not in head
    assert "Resume Playground" not in head
    assert ">Unlock Playground</a>" not in head
    assert "ActHead-link" not in head


def test_signed_in_subscriber_not_in_playground_keeps_add_flow(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    html = client.get("/laws/ndps").text
    _assert_no_old_markers(html)
    head = _head(html)
    band = _band(html)
    assert "data-plus-bareact" in html.split('data-act-head="ndps"', 1)[1].split(">", 1)[0]
    assert 'data-pg-kind="eligible_to_add"' in band
    assert "+ Add to Playground" in band
    assert (
        'class="ActHead-cta LawPlaygroundCta" data-law-id="ndps" data-pg-kind="eligible_to_add"'
        in band
    )
    assert "ActHead-note" not in band
    assert "LawStatusBadge" not in band
    assert 'class="ActHead-btn"' in band
    assert "ActHead-btn--ghost" not in band
    assert "data-pg-sheet" in band
    assert f'href="{add_path("ndps")}"' in band
    assert "Already in Playground" not in head
    assert ">Sections</a>" not in head
    assert "ActHead-inpg" not in head
    assert "Subscribe to use Playground" not in head


def test_signed_in_subscriber_in_playground_shows_cluster(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    html = client.get("/laws/ndps").text
    _assert_no_old_markers(html)
    head = _head(html)
    band = _band(html)
    assert "Already in Playground" in band
    assert 'data-pg-kind="already_active"' in band
    assert 'class="ActHead-inpg"' in band
    assert 'class="LawStatusBadge" data-status="in_playground"' in band
    assert f'class="ActHead-inpg-sections" href="{sections_path("ndps")}">Sections</a>' in band
    # M2-F04: Continue is the live state's own destination and label — a
    # fresh roster entry starts learning at its Sections page, not at the
    # old hard-coded /playground.
    assert f'class="ActHead-inpg-continue" href="{sections_path("ndps")}"' in band
    assert ">Start learning</a>" in band
    assert 'class="ActHead-inpg-continue" href="/playground"' not in band
    assert "ActHead-btn" not in band
    assert "ActHead-note" not in band
    assert "Subscribe to use Playground" not in head
    assert "+ Add to Playground" not in head


def test_signed_in_bareact_back_goes_to_laws_index(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    band = _band(client.get("/laws/ndps").text)
    assert '<a class="ActHead-back" href="/laws">← Laws</a>' in band
    laws = client.get("/laws", follow_redirects=False)
    assert laws.status_code == 200
    assert "data-signed-in-laws-desktop" in laws.text
    assert "data-guest-laws-desktop" not in laws.text


def test_signed_in_bareact_rows_are_generated_from_the_act(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/laws/ndps").text
    head = _head(html)
    band = _band(html)
    rows = _list(html)
    assert 'class="bareact-chapters" data-bareact-accordion data-act-list' in head
    # Every chapter the Act prints, from the live model (M2 §4 Q1): eight for
    # NDPS, Chapter IIA and VA included. None starts open.
    assert NDPS.chapter_count == 8
    assert rows.count('<details class="bareact-chapter">') == NDPS.chapter_count
    assert "<details open" not in rows
    assert '<details class="bareact-chapter" open' not in rows
    assert (
        rows.count('<summary class="bareact-chapter-row" aria-expanded="false">')
        == NDPS.chapter_count
    )
    assert [c.number for c in NDPS.chapters] == ["I", "II", "IIA", "III", "IV", "V", "VA", "VI"]
    for chapter in NDPS.chapters:
        assert f'<span class="bareact-chapter-tag">Chapter {chapter.number}</span>' in rows
        assert f'<span class="bareact-chapter-name">{chapter.title}</span>' in rows
        assert (
            '<span class="bareact-chapter-range"><span class="ActHead-range-word">'
            f"Sections </span>{chapter.range_label}</span>"
        ) in rows
    assert "Chapter IIA" in rows
    assert "CHAPTER IIA" not in rows
    # Chapter rows expand into section links (M2 Q3) — one per section.
    section_count = sum(len(chapter.sections) for chapter in NDPS.chapters)
    assert section_count > 0
    assert rows.count('class="bareact-section-row" href="/laws/ndps/section/') == section_count
    assert rows.count('class="bareact-section-list"') == NDPS.chapter_count
    # Schedules follow the chapters and open their reader.
    assert len(NDPS.schedules) == 1
    assert rows.count('<div class="bareact-schedule-row') == len(NDPS.schedules)
    assert rows.count('class="bareact-schedule-row-link"') == len(NDPS.schedules)
    schedule = NDPS.schedules[0]
    assert schedule.is_navigable
    assert f'href="/laws/ndps/schedule/{schedule.slug}"' in rows
    assert f'<span class="bareact-chapter-tag">{schedule.label}</span>' in rows
    assert (
        '<span class="bareact-chapter-range"><span class="ActHead-range-word">'
        f"Entries </span>{schedule.range_label}</span>"
    ) in rows
    assert "This Act has no Schedules." not in head
    assert "data-bareact-tabs" not in head
    assert "data-bareact-tab" not in head
    assert "data-bareact-panel" not in head
    assert 'role="button"' not in head
    # About-this-act stays, collapsed, below the title/CTA row (M2 Q2).
    assert (
        'class="bareact-info-toggle ActHead-about"\n      data-bareact-info-toggle\n'
        '      aria-expanded="false"' in band
    )
    assert ">About this act</button>" in band
    assert 'id="bareact-info" data-bareact-info hidden' in band
    assert band.index("ActHead-cta") < band.index("ActHead-about")
    assert band.index("ActHead-title") < band.index("ActHead-cta")


def test_signed_in_bareact_desktop_chrome(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/laws/ndps").text
    header = _header(html)
    nav = _primary_nav(html)
    assert '<a class="brand" href="/dashboard"' in header
    assert 'src="/static/main_logo.png"' in header
    assert "Recall the C" in header
    assert 'account-menu-btn-name">Sanjay<' in header
    assert "Free account" in header
    assert "Not signed in" not in header
    for label in ("Today", "Browse", "Playground", "Calendar", "Profile"):
        assert label in nav
    assert 'href="/dashboard"' in nav
    assert 'href="/browse"' in nav
    assert 'href="/playground"' in nav
    assert 'href="/calendar"' in nav
    assert 'href="/profile"' in nav
    assert ">Home<" not in nav
    assert "nav-signin" not in header
    assert "is-active" in nav
    css = STYLES.read_text(encoding="utf-8")
    for marker in OLD_MARKERS[:5]:
        assert marker not in css, marker
    assert "guest-bareact-" not in css
    assert "signed-bareact-" not in css
    m2 = css.split("Bare Act head (M2)", 1)[1]
    band = m2.split(".ActHead-band {", 1)[1].split("}", 1)[0]
    assert "padding: 16px 40px 22px" in band
    assert "border-bottom: 1px solid var(--hairline)" in band
    row = m2.split(".ActHead-row {", 1)[1].split("}", 1)[0]
    assert "display: flex" in row
    assert "align-items: flex-end" in row
    cta = m2.split(".ActHead-cta,\n.ActHead-cta.LawPlaygroundCta {", 1)[1].split("}", 1)[0]
    assert "width: 380px" in cta
    assert "min-width: 240px" in cta
    assert "flex-direction: column" in cta
    note = m2.split(".ActHead-note {", 1)[1].split("}", 1)[0]
    assert "font-size: 12.5px" in note
    btn = m2.split(".ActHead-btn {", 1)[1].split("}", 1)[0]
    assert "min-height: 48px" in btn
    assert "width: 100%" in btn
    assert "border-radius: 12px" in btn
    back = m2.split(".ActHead-back {", 1)[1].split("}", 1)[0]
    assert "min-height: 44px" in back
    kicker = m2.split(".ActHead-kicker {", 1)[1].split("}", 1)[0]
    assert "text-transform: uppercase" in kicker
    chapters = m2.split(".ActHead .bareact-chapters {", 1)[1].split("}", 1)[0]
    assert "padding: 8px 40px 60px" in chapters
    assert "@media (max-width: 560px)" in m2
    # The R1 shell block proper (logo tile, centred tabs, account menu) — it
    # ends where the Guest Browse section begins. The M2 About toggle's 44 px
    # band is padding pulled back by margins, so the shell positions nothing.
    shell = css.split("/* R1 desktop shell", 1)[1].split("/* Guest Browse index", 1)[0]
    assert "position: absolute" not in shell
    assert "left: 50%" not in shell
    about_tap = m2.split(".ActHead-about {", 1)[1].split("}", 1)[0]
    assert "min-height: 44px" in about_tap
    assert "margin: 0 0 -10px" in about_tap and "padding: 10px 0" in about_tap
    laws_title = css.split(
        'body.is-authed[data-mscreen="laws"] .laws-index-copy .laws-index-title {',
        1,
    )[1].split("}", 1)[0]
    assert "30px" in laws_title


def test_signed_in_bareact_does_not_touch_phone_or_accepted_screens(
    tmp_path: Path,
) -> None:
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-signed-in-bareact-desktop" not in mobile
    assert "data-signed-in-bareact-phone" not in mobile
    assert 'body[data-mscreen="bareact"] .bareact-chapter-row' in mobile
    assert 'body[data-mscreen="bareact"] .bareact-section-row' in mobile
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-guest-landing="desktop"' in landing
    assert "Explore the Constitution" in landing
    browse = BROWSE.read_text(encoding="utf-8")
    assert "data-signed-in-browse-strip" in browse
    assert "Unlock all" in browse
    laws = LAWS.read_text(encoding="utf-8")
    assert "data-signed-in-laws-desktop" in laws
    assert "data-act-head" not in laws
    assert "data-signed-in-bareact-desktop" not in laws

    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/laws/ndps").text
    # One head on both widths: the accordion, the section links and the
    # Playground action all live in the same generated section.
    assert html.count('data-act-head="ndps"') == 1
    head = _head(html)
    assert "<details" in head
    assert 'href="/laws/ndps/section/' in head
    assert 'class="ActHead-cta LawPlaygroundCta"' in head
    assert "data-signed-in-bareact-phone-tabs" in html
    landing_html = client.get("/").text
    assert 'data-guest-landing="desktop"' in landing_html
    browse_html = client.get("/browse").text
    assert "Browse the Constitution" in browse_html
    assert "data-signed-in-browse-strip" in browse_html
    laws_html = client.get("/laws").text
    assert "data-signed-in-laws-desktop" in laws_html
    assert "data-act-head" not in laws_html
    bns = client.get("/laws/bns").text
    _assert_no_old_markers(bns)
    assert 'data-act-head="bns"' in bns
    assert 'data-act-head="ndps"' not in bns
    bns_act = get_bare_act("bns")
    bns_head = _head(bns, "bns")
    assert bns_head.count('<details class="bareact-chapter">') == bns_act.chapter_count
    assert bns_head.count('<div class="bareact-schedule-row') == len(bns_act.schedules) == 0
    assert f'<p class="ActHead-meta">{bns_act.head_meta_label}</p>' in bns_head
    assert "Subscribe to use Playground" in bns_head
    guest = TestClient(_mu_app(tmp_path / "guest"))
    guest_ndps = guest.get("/laws/ndps").text
    _assert_no_old_markers(guest_ndps)
    assert 'data-act-head="ndps"' in guest_ndps
    guest_band = _band(guest_ndps)
    assert 'data-pg-kind="guest"' in guest_band
    assert "Sign in to use Playground" in guest_band
    assert "Subscribe to use Playground" not in guest_band
    assert FREE_NOTE not in guest_band
    assert '<p class="ActHead-note">Sign in to add this law to Playground.</p>' in guest_band
    assert "data-plus-bareact" not in guest_ndps
    assert f'<h1 class="ActHead-title">{TITLE}</h1>' in guest_band


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


def test_signed_in_bareact_1280_non_subscriber_cta_and_rows(
    tmp_path: Path,
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _seed_stale_ndps_roster(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "signed_in_bare_act_1280.png"
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
              const heads = document.querySelectorAll('[data-act-head]');
              const brand = document.querySelector('.brand');
              const back = head.querySelector('.ActHead-back');
              const cta = head.querySelector('.ActHead-btn');
              const band = head.querySelector('.ActHead-band');
              const copy = head.querySelector('.ActHead-copy');
              const chapters = [...head.querySelectorAll('details.bareact-chapter')];
              const schedules = [...head.querySelectorAll('.bareact-schedule-row')];
              const sectionLinks = head.querySelectorAll('a.bareact-section-row[href^="/laws/ndps/section/"]');
              return {
                brandTag: brand.tagName,
                brandHref: brand.getAttribute('href'),
                headCount: heads.length,
                headDisplay: getComputedStyle(head).display,
                pgKind: head.getAttribute('data-pg-kind'),
                plus: head.hasAttribute('data-plus-bareact'),
                backHref: back.getAttribute('href'),
                kicker: head.querySelector('.ActHead-kicker').textContent.trim(),
                kickerTransform: getComputedStyle(head.querySelector('.ActHead-kicker')).textTransform,
                title: head.querySelector('.ActHead-title').textContent.trim(),
                meta: head.querySelector('.ActHead-meta').textContent.trim(),
                ctaText: cta && cta.textContent.trim(),
                ctaHref: cta && cta.getAttribute('href'),
                ctaSheet: cta && cta.hasAttribute('data-pg-sheet'),
                ctaKind: cta && cta.getAttribute('data-pg-kind'),
                already: head.textContent.includes('Already in Playground'),
                inpg: !!head.querySelector('.ActHead-inpg'),
                note: head.querySelector('.ActHead-note') &&
                  head.querySelector('.ActHead-note').textContent.trim(),
                chapterCount: chapters.length,
                openChapters: chapters.filter((el) => el.open).length,
                chapterTags: chapters.map((el) =>
                  el.querySelector('.bareact-chapter-tag').textContent.trim()
                ),
                chapterNames: chapters.map((el) =>
                  el.querySelector('.bareact-chapter-name').textContent.trim()
                ),
                scheduleCount: schedules.length,
                sectionLinks: sectionLinks.length,
                aboutBelowCta: band.querySelector('.ActHead-cta').getBoundingClientRect().bottom <=
                  band.querySelector('.ActHead-about').getBoundingClientRect().top,
                aboutExpanded: band.querySelector('.ActHead-about').getAttribute('aria-expanded'),
                accountName: document.querySelector('.account-menu-btn-name').textContent.trim(),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                navLabels: [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                  (el) => el.textContent.replace(/\\s+/g, ' ').trim()
                ),
                browseActive: document.querySelector('.PrimaryTabs--top .nav-link.is-active')
                  .textContent.replace(/\\s+/g, ' ').trim(),
                bandPadTop: parseFloat(getComputedStyle(band).paddingTop),
                bandPadBottom: parseFloat(getComputedStyle(band).paddingBottom),
                rowAlign: getComputedStyle(head.querySelector('.ActHead-row')).alignItems,
                ctaW: cta.getBoundingClientRect().width,
                ctaH: cta.getBoundingClientRect().height,
                copyH: copy.getBoundingClientRect().height,
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
              const titleEl = panel && panel.querySelector('#pg-add-title');
              const primary = panel && panel.querySelector('.pg-add-primary');
              return {
                kind: panel && panel.getAttribute('data-pg-kind'),
                title: titleEl && titleEl.textContent.trim(),
                primary: primary && primary.textContent.trim(),
                primaryHref: primary && primary.getAttribute('href'),
              };
            }"""
        )
        page.keyboard.press("Escape")
        still_on_ndps = page.url.rstrip("/").endswith("/laws/ndps")

        page.locator('[data-act-head="ndps"] .ActHead-back').click()
        page.wait_for_function("() => location.pathname === '/laws'", timeout=8000)
        laws_path = page.evaluate("() => location.pathname")
        laws_desk = page.evaluate(
            """() => !!document.querySelector('[data-signed-in-laws-desktop]')"""
        )

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        phone_geo = page.evaluate(
            """() => {
              const head = document.querySelector('[data-act-head="ndps"]');
              const cta = head && head.querySelector('.ActHead-btn');
              return {
                headCount: document.querySelectorAll('[data-act-head]').length,
                headDisplay: head ? getComputedStyle(head).display : null,
                ctaText: cta && cta.textContent.trim(),
                ctaW: cta ? cta.getBoundingClientRect().width : 0,
                details: head ? head.querySelectorAll('details.bareact-chapter').length : 0,
                sectionLinks: head
                  ? head.querySelectorAll('a[href*="/laws/ndps/section/"]').length
                  : 0,
                rangeWord: getComputedStyle(head.querySelector('.ActHead-range-word')).display,
              };
            }"""
        )
        browser.close()

    assert geo["brandTag"] == "A"
    assert geo["brandHref"] == "/dashboard"
    assert geo["headCount"] == 1
    assert geo["headDisplay"] != "none"
    assert geo["pgKind"] == "subscribe"
    assert geo["plus"] is False
    assert geo["backHref"] == "/laws"
    assert geo["kicker"] == KICKER
    assert geo["kickerTransform"] == "uppercase"
    assert geo["title"] == TITLE
    assert geo["meta"] == META
    assert geo["ctaText"] == "Subscribe to use Playground"
    assert geo["ctaHref"] == add_path("ndps")
    assert geo["ctaSheet"] is True
    assert geo["ctaKind"] == "subscribe"
    assert geo["already"] is False
    assert geo["inpg"] is False
    assert geo["note"] == FREE_NOTE
    assert geo["chapterCount"] == NDPS.chapter_count == 8
    assert geo["openChapters"] == 0
    assert geo["chapterTags"] == [f"Chapter {c.number}" for c in NDPS.chapters]
    assert geo["chapterNames"] == [c.title for c in NDPS.chapters]
    assert geo["scheduleCount"] == len(NDPS.schedules) == 1
    assert geo["sectionLinks"] == sum(len(c.sections) for c in NDPS.chapters)
    assert geo["aboutBelowCta"] is True
    assert geo["aboutExpanded"] == "false"
    assert geo["accountName"] == "Sanjay"
    assert geo["accountStatus"] == "Free account"
    assert geo["navLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["browseActive"] == "Browse"
    assert geo["bandPadTop"] == pytest.approx(16, abs=1)
    assert geo["bandPadBottom"] == pytest.approx(22, abs=1)
    assert geo["rowAlign"] == "flex-end"
    assert geo["ctaH"] == pytest.approx(48, abs=2)
    assert geo["ctaW"] == pytest.approx(380, abs=4)
    assert abs(geo["ctaH"] - geo["copyH"]) < 60
    assert dialog["kind"] == "subscribe"
    assert dialog["title"] == "Add to Playground"
    assert dialog["primary"] == "Unlock Playground"
    assert dialog["primaryHref"] == "/playground"
    assert still_on_ndps is True
    assert laws_path == "/laws"
    assert laws_desk is True
    assert phone_geo["headCount"] == 1
    assert phone_geo["headDisplay"] != "none"
    assert phone_geo["ctaText"] == "Subscribe to use Playground"
    assert phone_geo["ctaW"] >= 300
    assert phone_geo["details"] == 8
    assert phone_geo["sectionLinks"] > 0
    assert phone_geo["rangeWord"] == "none"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
