"""Guest NDPS Bare Act head Screen 4 (desktop CTA map guest/04-screen).

M2: one generated Bare Act head for every Act and every viewer (§2.1). The
desktop and phone twins are gone; the same markup is laid out by CSS at both
widths. Guest `/laws/ndps` is checked here at 1280. Landing, Browse, Laws
index, and subscriber heads stay unchanged.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.urls import add_path
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
NDPS = get_bare_act("ndps")
KICKER = "Bare Act · India Code"  # uppercased by CSS, printed in title case
TITLE = NDPS.title
META = NDPS.head_meta_label
PRIMARY = "Sign in to use Playground"


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _guest_app(tmp_path: Path):
    settings = MultiUserSettings(
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
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=settings,
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
    )


def _guest_client(tmp_path: Path) -> TestClient:
    return TestClient(_guest_app(tmp_path))


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _primary_nav(html: str) -> str:
    return html.split('aria-label="Primary"', 1)[1].split("</nav>", 1)[0]


def _head(html: str) -> str:
    """The one generated Act head: `<section class="panel ActHead …">`."""
    return html.split('class="panel ActHead', 1)[1].split("</section>", 1)[0]


def _band(html: str) -> str:
    """Back link, kicker, title, meta, CTA and About — above the list."""
    return _head(html).split("data-act-list", 1)[0]


def _act_list(html: str) -> str:
    return _head(html).split("data-act-list", 1)[1]


def test_screen4_guest_ndps_uses_screen2_header(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/laws/ndps").text
    header = _header(html)
    nav = _primary_nav(html)
    assert 'data-act-head="ndps"' in html
    assert 'data-mscreen="bareact"' in html
    assert '<a class="brand" href="/"' in header  # M1: one brand link
    assert 'src="/static/main_logo.png"' in header
    assert "Recall the C" in header
    assert "data-guest-account-menu" not in header
    assert '<a class="nav-signin" href="/login">Sign in</a>' in header  # M1 shell
    assert ">Home<" not in nav
    assert ">Search<" not in nav
    assert ">Learn<" not in nav
    for label in ("Today", "Browse", "Playground", "Calendar", "Profile"):
        assert label in nav
    assert "is-active" in nav
    assert 'aria-current="page"' in nav
    css = (ROOT / "src/constitution_memorizer/web/static/styles.css").read_text(
        encoding="utf-8"
    )
    # M2: the per-surface guest block is gone; the page wash comes from the
    # one "Bare Act head (M2)" block for every viewer.
    assert "Bare Act head (M2)" in css
    assert "data-guest-bareact-desktop" not in css
    page_wash = css.split(
        'body[data-mscreen="bareact"] .page-wrap,', 1
    )[1].split("}", 1)[0]
    assert "var(--paper)" in page_wash


def test_screen4_back_returns_to_laws(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    band = _band(client.get("/laws/ndps").text)
    assert '<a class="ActHead-back" href="/laws">← Laws</a>' in band
    laws = client.get("/laws", follow_redirects=False)
    assert laws.status_code == 200
    assert "data-guest-laws-desktop" in laws.text


def test_screen4_copy_and_single_playground_cta(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/laws/ndps").text
    band = _band(html)
    assert f'<p class="ActHead-kicker">{KICKER}</p>' in band
    assert f'<h1 class="ActHead-title">{TITLE}</h1>' in band
    assert f'<p class="ActHead-meta">{META}</p>' in band
    assert META == "8 Chapters · Sections 1–83 · Schedule"
    assert PRIMARY in band
    assert html.count(PRIMARY) == 1
    assert html.count('class="ActHead-cta LawPlaygroundCta"') == 1
    cta = band.split('<div class="ActHead-cta', 1)[1].split("</div>", 1)[0]
    assert 'data-law-id="ndps"' in cta
    assert 'data-pg-kind="guest"' in cta
    assert 'class="ActHead-btn"' in cta
    assert "ActHead-btn--ghost" not in cta
    assert f'href="{add_path("ndps")}"' in cta
    assert "data-pg-sheet" in cta
    assert "ActHead-link" not in cta
    assert "LawStatusBadge" not in cta  # a guest has no status chip
    assert '<p class="ActHead-note">Sign in to add this law to Playground.</p>' in cta
    assert cta.count("<a") == 1
    # No in-Playground chip for a guest: no badge, no Sections / Continue
    # links. (The About card's "Sections" <dt> is statutory metadata, not a
    # link, so the check is on anchors and the chip classes.)
    assert "Already in Playground" not in band
    assert "ActHead-inpg" not in band
    assert ">Sections</a>" not in band
    assert ">Continue</a>" not in band
    assert "data-bareact-tabs" not in html
    assert "This Act has no Schedules" not in html
    # M2 Q2: About this act stays, collapsed, BELOW the title/CTA row.
    about = band.index('class="bareact-info-toggle ActHead-about"')
    assert about > band.index('class="ActHead-cta LawPlaygroundCta"')
    assert 'aria-expanded="false"' in band
    assert 'id="bareact-info" data-bareact-info hidden' in band


def test_screen4_rows_are_generated_from_the_act(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/laws/ndps").text
    rows = _act_list(html)
    # M2 §4 Q1: eight NDPS chapters from canonical data, every row a
    # <summary> that expands into its section links (Q3), none open.
    assert NDPS.chapter_count == 8
    assert [c.number for c in NDPS.chapters] == [
        "I", "II", "IIA", "III", "IV", "V", "VA", "VI"
    ]
    assert rows.count('<details class="bareact-chapter">') == NDPS.chapter_count
    assert rows.count('<summary class="bareact-chapter-row" aria-expanded="false">') == (
        NDPS.chapter_count
    )
    assert "<details open" not in rows
    assert "<details class=\"bareact-chapter\" open" not in rows
    for chapter in NDPS.chapters:
        assert f'<span class="bareact-chapter-tag">Chapter {chapter.number}</span>' in rows
        assert f'<span class="bareact-chapter-name">{chapter.title}</span>' in rows
        assert (
            '<span class="bareact-chapter-range">'
            f'<span class="ActHead-range-word">Sections </span>{chapter.range_label}</span>'
        ) in rows
    assert "Chapter IIA" in rows
    section_rows = rows.count('<a class="bareact-section-row" href="/laws/ndps/section/')
    assert section_rows == len(NDPS.section_order)
    assert rows.count('<div class="bareact-schedule-row') == len(NDPS.schedules) == 1
    assert rows.count('href="/laws/ndps/schedule/') == sum(
        1 for schedule in NDPS.schedules if schedule.is_navigable
    )
    assert '<span class="ActHead-range-word">Entries </span>' in rows
    assert 'role="button"' not in rows
    assert "<button" not in rows


def test_screen4_one_head_serves_both_widths_and_other_screens(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    html = client.get("/laws/ndps").text
    # M2 §2.1: one head; no desktop/phone twins and no legacy phone block.
    assert html.count('class="panel ActHead') == 1
    for gone in (
        "data-guest-bareact-desktop",
        "data-guest-bareact-phone",
        "data-bareact-phone",
        "guest-bareact-",
        "signed-bareact-",
    ):
        assert gone not in html, gone
    landing = client.get("/").text
    assert 'data-guest-landing="desktop"' in landing
    browse = client.get("/browse").text
    assert "Browse the Constitution" in browse
    laws = client.get("/laws").text
    assert "data-guest-laws-desktop" in laws
    assert "ActHead" not in laws
    bns = client.get("/laws/bns").text
    bns_act = get_bare_act("bns")
    assert 'data-act-head="bns"' in bns
    assert f'<p class="ActHead-meta">{bns_act.head_meta_label}</p>' in bns
    assert bns.count('<details class="bareact-chapter">') == bns_act.chapter_count == 20
    assert PRIMARY in bns  # the guest CTA is generated for every Act
    section = client.get("/laws/ndps/section/1").text
    assert "ActHead" not in section
    css = (ROOT / "src/constitution_memorizer/web/static/styles.css").read_text(
        encoding="utf-8"
    )
    guest_grid = css.split(
        'body.is-guest[data-mscreen="browse"] .browse-resource-grid {', 1
    )[1].split("}", 1)[0]
    assert "calc(200% / 3)" in guest_grid


def test_single_user_and_authed_ndps_heads_are_unchanged(tmp_path: Path) -> None:
    html = TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    ).get("/laws/ndps").text
    assert "data-guest-bareact-desktop" not in html
    assert "data-bareact-phone" not in html
    assert html.count("<details") == NDPS.chapter_count == 8
    assert 'href="/laws/ndps/section/' in html
    assert PRIMARY not in html
    assert 'data-pg-kind="guest"' not in html
    assert f'<h1 class="ActHead-title">{TITLE}</h1>' in html


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


def test_screen4_1280_cta_opens_add_dialog_and_rows_stay_closed(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "guest_bareact_screen4_1280.png"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        page = browser.new_page(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )
        page.goto(f"http://127.0.0.1:{port}/laws/ndps", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const heads = document.querySelectorAll('.ActHead');
              const head = heads[0];
              const brand = document.querySelector('.brand');
              const back = head.querySelector('.ActHead-back');
              const cta = head.querySelector('.ActHead-btn');
              const rows = [...head.querySelectorAll('.bareact-chapter-row')];
              const openChapters = head.querySelectorAll('details.bareact-chapter[open]');
              const sectionLinks = [...head.querySelectorAll('a.bareact-section-row')];
              const visibleSectionLinks = sectionLinks.filter((a) => a.offsetParent !== null);
              const about = head.querySelector('.ActHead-about');
              return {
                heads: heads.length,
                brandTag: brand.tagName,
                headDisplay: getComputedStyle(head).display,
                rangeWordDisplay: getComputedStyle(head.querySelector('.ActHead-range-word')).display,
                backHref: back.getAttribute('href'),
                kicker: head.querySelector('.ActHead-kicker').textContent.trim(),
                kickerTransform: getComputedStyle(head.querySelector('.ActHead-kicker')).textTransform,
                title: head.querySelector('.ActHead-title').textContent.trim(),
                meta: head.querySelector('.ActHead-meta').textContent.trim(),
                ctaText: cta.textContent.trim(),
                ctaHref: cta.getAttribute('href'),
                ctaSheet: cta.hasAttribute('data-pg-sheet'),
                ctaCount: head.querySelectorAll('.ActHead-btn, .ActHead-inpg').length,
                aboutBelowCta: Boolean(about) && about.getBoundingClientRect().top > cta.getBoundingClientRect().bottom,
                aboutExpanded: about && about.getAttribute('aria-expanded'),
                rowCount: rows.length,
                rowTags: rows.map((el) => el.querySelector('.bareact-chapter-tag').textContent.trim()),
                rowTitles: rows.map((el) => el.querySelector('.bareact-chapter-name').textContent.trim()),
                openChapters: openChapters.length,
                sectionLinks: sectionLinks.length,
                visibleSectionLinks: visibleSectionLinks.length,
                scheduleRows: head.querySelectorAll('.bareact-schedule-row').length,
                navLabels: [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                  (el) => el.textContent.replace(/\\s+/g, ' ').trim()
                ),
                browseActive: document.querySelector('.PrimaryTabs--top .nav-link.is-active').textContent.replace(/\\s+/g, ' ').trim(),
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
              const titleEl = panel && panel.querySelector('.pg-add-title');
              return {
                kind: panel && panel.getAttribute('data-pg-kind'),
                title: titleEl && titleEl.textContent.trim(),
                panels: document.querySelectorAll('.pg-sheet-panel').length,
              };
            }"""
        )
        page.keyboard.press("Escape")
        still_on_ndps = page.url.rstrip("/").endswith("/laws/ndps")
        phone = browser.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        phone.goto(f"http://127.0.0.1:{port}/laws/ndps", wait_until="networkidle")
        phone_geo = phone.evaluate(
            """() => {
              const heads = document.querySelectorAll('.ActHead');
              const head = heads[0];
              const cta = head.querySelector('.ActHead-btn');
              return {
                heads: heads.length,
                headDisplay: getComputedStyle(head).display,
                rangeWordDisplay: getComputedStyle(head.querySelector('.ActHead-range-word')).display,
                ctaText: cta.textContent.trim(),
                ctaWidth: cta.getBoundingClientRect().width,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
              };
            }"""
        )
        browser.close()

    assert geo["heads"] == 1
    assert geo["brandTag"] == "SPAN"
    assert geo["headDisplay"] != "none"
    assert geo["rangeWordDisplay"] != "none"
    assert geo["backHref"] == "/laws"
    assert geo["kicker"] == KICKER
    assert geo["kickerTransform"] == "uppercase"
    assert geo["title"] == TITLE
    assert geo["meta"] == META
    assert geo["ctaText"] == PRIMARY
    assert geo["ctaHref"] == add_path("ndps")
    assert geo["ctaSheet"] is True
    assert geo["ctaCount"] == 1
    assert geo["aboutBelowCta"] is True
    assert geo["aboutExpanded"] == "false"
    assert geo["rowCount"] == NDPS.chapter_count == 8
    assert geo["rowTags"] == [f"Chapter {c.number}" for c in NDPS.chapters]
    assert geo["rowTitles"] == [c.title for c in NDPS.chapters]
    assert geo["openChapters"] == 0
    assert geo["sectionLinks"] == len(NDPS.section_order)
    assert geo["visibleSectionLinks"] == 0
    assert geo["scheduleRows"] == len(NDPS.schedules)
    assert geo["navLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["browseActive"] == "Browse"
    assert dialog["kind"] == "guest"
    assert dialog["title"] == "Add to Playground"
    assert dialog["panels"] == 1
    assert still_on_ndps is True
    assert phone_geo["heads"] == 1
    assert phone_geo["headDisplay"] != "none"
    assert phone_geo["rangeWordDisplay"] == "none"
    assert phone_geo["ctaText"] == PRIMARY
    assert phone_geo["ctaWidth"] >= 300
    assert phone_geo["overflow"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
