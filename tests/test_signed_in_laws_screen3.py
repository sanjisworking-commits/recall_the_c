"""Signed-in desktop Laws index (CTA map signedIn/03-screen).

Authorized: ChatGPT. Authenticated multiuser GET /laws keeps the shared
laws.html production catalogue, chips, Bare Act-head hrefs, and Playground
state. Desktop layout is reconciled to signedIn/03. Phone /laws, signed-in
Landing, and signed-in Browse are unchanged.
"""

from __future__ import annotations

import re
import socket
import threading
import time
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
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.law_catalog import load_catalog

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "data" / "output" / "learning_units.json"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"


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


def _mu_app(tmp_path: Path, *, units: Path | None = None, display_name: str = "Sanjay"):
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=UUID("11111111-1111-4111-8111-111111111111"),
        email="a@example.com",
        display_name=display_name,
        avatar_url=None,
    )
    return create_app(
        units_path=units or MINI_UNITS,
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


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _primary_nav(html: str) -> str:
    return html.split('aria-label="Primary"', 1)[1].split("</nav>", 1)[0]


def _desk(html: str) -> str:
    return html.split("data-signed-in-laws-desktop", 1)[1]


def test_signed_in_laws_uses_production_catalogue_not_guest_cards(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/laws").text
    assert "data-signed-in-laws-desktop" in html
    assert "data-guest-laws-desktop" not in html
    assert "data-laws-phone" not in html
    desk = _desk(html)
    catalog = load_catalog()
    catalog_html = desk.split("data-laws-catalog", 1)[1].split("data-laws-empty", 1)[0]
    rendered_ids = re.findall(
        r'class="laws-index-card"[^>]*data-law-id="([^"]+)"',
        catalog_html,
        re.S,
    )
    assert rendered_ids == [law.id for law in catalog.laws]
    assert "bns" in rendered_ids
    assert "ndps" in rendered_ids
    assert "The Bharatiya Nyaya Sanhita, 2023" in desk
    assert "The Narcotic Drugs and Psychotropic Substances Act, 1985" in desk
    assert "The Companies Act, 2013" not in desk
    assert "The Bharatiya Sakshya Adhiniyam, 2023" not in desk
    assert "The Bharatiya Nyaya Sanhita, 2025" not in desk


def test_signed_in_laws_back_goes_to_browse_index(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    desk = _desk(client.get("/laws").text)
    assert 'class="laws-back-link" href="/browse"' in desk
    assert 'class="mobile-back" href="/browse">← Browse' in desk
    browse = client.get("/browse", follow_redirects=False)
    assert browse.status_code == 200
    assert "Browse the Constitution" in browse.text
    assert 'data-signed-in-browse-strip' in browse.text


def test_signed_in_laws_chips_and_search_are_in_place_filters(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    desk = _desk(client.get("/laws").text)
    assert ">Laws<" in desk
    assert "Bare Acts and statutes. Open a law, then add it or its sections to your Playground." in desk
    assert 'placeholder="Search laws"' in desk
    labels = re.findall(
        r'<button type="button" class="laws-chip[^"]*"[^>]*>([^<]+)</button>',
        desk,
    )
    catalog = load_catalog()
    expected = ["All"] + [s.label for s in catalog.visible_subjects]
    if catalog.repealed_laws:
        expected.append("Repealed")
    assert labels == expected
    assert "Commercial" not in labels
    assert "Health" in labels
    assert 'data-laws-chip="" aria-pressed="true"' in desk
    chips = desk.split("laws-chip-strip", 1)[1].split("laws-catalog", 1)[0]
    assert "<a " not in chips
    assert "href=" not in chips
    search = desk.split('class="laws-search"', 1)[1].split("</div>", 1)[0]
    assert "<form" not in search
    assert "action=" not in search
    assert 'id="laws-q"' in search


def test_signed_in_laws_cards_keep_existing_bare_act_heads(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    desk = _desk(client.get("/laws").text)
    catalog = load_catalog()
    bns = next(law for law in catalog.laws if law.id == "bns")
    ndps = next(law for law in catalog.laws if law.id == "ndps")
    assert bns.href == "/laws/bns"
    assert ndps.href == "/laws/ndps"
    assert f'href="{bns.href}"' in desk
    assert f'href="{ndps.href}"' in desk
    for href in (bns.href, ndps.href):
        page = client.get(href, follow_redirects=False)
        assert page.status_code == 200, href
        assert "bareact" in page.text or "data-mscreen" in page.text
    assert "LawPlaygroundCta" in desk
    assert "Already in Playground" in Path(
        ROOT / "src/constitution_memorizer/playground/view.py"
    ).read_text(encoding="utf-8")


def test_signed_in_laws_desktop_chrome(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/laws").text
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
    assert 'class="nav-link is-active"' in nav or "is-active" in nav
    css = STYLES.read_text(encoding="utf-8")
    authed_mark = css.split(
        'body.is-authed[data-mscreen="laws"] .brand-mark {', 1
    )[1].split("}", 1)[0]
    assert "invert(1)" in authed_mark
    title = css.split(
        'body.is-authed[data-mscreen="laws"] .laws-index-copy .laws-index-title {',
        1,
    )[1].split("}", 1)[0]
    assert "30px" in title
    assert "font-weight: 600" in title
    search = css.split(
        'body.is-authed[data-mscreen="laws"] .laws-search {', 1
    )[1].split("}", 1)[0]
    assert "300px" in search
    catalog = css.split(
        'body.is-authed[data-mscreen="laws"] .laws-catalog {', 1
    )[1].split("}", 1)[0]
    assert "1fr 1fr" in catalog
    assert "1000px" in catalog
    phone_hide = css.split(
        "body.is-authed[data-mscreen=\"laws\"] .laws-back-link,", 1
    )[1].split("}", 1)[0]
    assert "display: none" in phone_hide
    shell = css.split("/* R1 desktop shell", 1)[1]
    assert "position: absolute" not in shell
    assert "left: 50%" not in shell
    browse_mark = css.split(
        'body.is-authed[data-mscreen="browse"] .brand-mark {', 1
    )[1].split("}", 1)[0]
    assert "invert(1)" in browse_mark
    browse_cards = css.split(
        'body.is-authed[data-mscreen="browse"] .browse-article-card {', 1
    )[1].split("}", 1)[0]
    assert "min-height: 48px" in browse_cards


def test_signed_in_laws_does_not_touch_phone_landing_or_browse() -> None:
    mobile = MOBILE.read_text(encoding="utf-8")
    assert 'body[data-mscreen="laws"] .laws-index-head' in mobile
    assert 'body[data-mscreen="laws"] .laws-index-card' in mobile
    assert 'body[data-mscreen="laws"] .laws-chip-strip' in mobile
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-guest-landing="desktop"' in landing
    assert "Explore the Constitution" in landing
    browse = BROWSE.read_text(encoding="utf-8")
    assert "data-signed-in-browse-strip" in browse
    assert "Unlock all" in browse


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


def test_signed_in_laws_1280_filters_and_keeps_existing_heads(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "signed_in_laws_1280.png"
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
        page.goto(f"{origin}/laws", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-signed-in-laws-desktop]');
              const guest = document.querySelector('[data-guest-laws-desktop]');
              const brand = document.querySelector('.brand');
              const mark = document.querySelector('.brand-mark');
              const header = document.querySelector('.site-header');
              const back = desk.querySelector('.laws-back-link');
              const phoneHead = desk.querySelector('.laws-index-head');
              const search = desk.querySelector('#laws-q');
              const searchWrap = desk.querySelector('[data-laws-search]');
              const chips = [...desk.querySelectorAll('.laws-chip')].map((el) => ({
                text: el.textContent.trim(),
                pressed: el.getAttribute('aria-pressed'),
                subject: el.getAttribute('data-laws-chip'),
                status: el.getAttribute('data-laws-status'),
                tag: el.tagName,
                href: el.getAttribute('href'),
              }));
              const visible = [...desk.querySelectorAll('[data-law-id]')].filter(
                (el) => !el.classList.contains('is-filtered-out')
              );
              const catalog = desk.querySelector('.laws-catalog');
              const cs = getComputedStyle(catalog);
              const first = visible[0] && visible[0].getBoundingClientRect();
              const second = visible[1] && visible[1].getBoundingClientRect();
              const ndps = desk.querySelector('a[href="/laws/ndps"]');
              const bns = desk.querySelector('a[href="/laws/bns"]');
              const fallback = document.querySelector('.account-avatar-fallback');
              const fr = fallback.getBoundingClientRect();
              const hr = header.getBoundingClientRect();
              const pageBg = getComputedStyle(document.querySelector('.sheet')).backgroundColor;
              const headerBg = getComputedStyle(header).backgroundColor;
              const heading = desk.querySelector('.laws-index-copy .laws-index-title');
              const searchBox = searchWrap.getBoundingClientRect();
              const copyBox = desk.querySelector('.laws-index-copy').getBoundingClientRect();
              return {
                brandTag: brand.tagName,
                brandHref: brand.getAttribute('href'),
                markFilter: getComputedStyle(mark).filter,
                headerH: hr.height,
                deskPresent: !!desk,
                guestPresent: !!guest,
                backHref: back.getAttribute('href'),
                backDisplay: getComputedStyle(back).display,
                phoneHeadDisplay: getComputedStyle(phoneHead).display,
                heading: heading.textContent.trim(),
                headingSize: getComputedStyle(heading).fontSize,
                kicker: desk.querySelector('.laws-index-kicker').textContent.trim(),
                lede: desk.querySelector('.laws-index-lede').textContent.trim(),
                searchPlaceholder: search.getAttribute('placeholder'),
                searchHiddenAttr: searchWrap.hasAttribute('hidden'),
                searchDisplay: getComputedStyle(searchWrap).display,
                searchX: searchBox.x,
                copyX: copyBox.x,
                chips,
                visibleIds: visible.map((el) => el.getAttribute('data-law-id')),
                cols: cs.gridTemplateColumns.split(' ').length,
                twoCol: first && second && Math.abs(first.y - second.y) < 8 && second.x > first.x,
                ndpsHref: ndps && ndps.getAttribute('href'),
                bnsHref: bns && bns.getAttribute('href'),
                accountName: document.querySelector('.account-menu-btn-name').textContent.trim(),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                fallbackW: fr.width,
                fallbackH: fr.height,
                navLabels: [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                  (el) => el.textContent.replace(/\\s+/g, ' ').trim()
                ),
                browseActive: document.querySelector('.PrimaryTabs--top .nav-link.is-active').textContent.replace(/\\s+/g, ' ').trim(),
                pageBg,
                headerBg,
                playgroundCtaCount: desk.querySelectorAll('.LawPlaygroundCta').length,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator('[data-signed-in-laws-desktop] .laws-back-link').click()
        page.wait_for_url("**/browse**", timeout=8000)
        browse_url = page.url
        browse_heading = page.locator(".browse > .display").inner_text()
        page.goto(f"{origin}/laws", wait_until="networkidle")

        page.locator(
            '[data-signed-in-laws-desktop] .laws-chip[data-laws-chip="criminal"]'
        ).click()
        criminal = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-signed-in-laws-desktop]');
              const visible = [...desk.querySelectorAll('[data-law-id]')].filter(
                (el) => !el.classList.contains('is-filtered-out')
              );
              return {
                path: location.pathname,
                search: location.search,
                ids: visible.map((el) => el.getAttribute('data-law-id')),
                subjects: visible.map((el) => el.getAttribute('data-subjects')),
                pressed: desk.querySelector('[data-laws-chip="criminal"]').getAttribute('aria-pressed'),
                all: desk.querySelector('[data-laws-chip=""]').getAttribute('aria-pressed'),
              };
            }"""
        )
        page.locator(
            '[data-signed-in-laws-desktop] .laws-chip[data-laws-chip=""]'
        ).click()
        page.fill("#laws-q", "ndps")
        searched = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-signed-in-laws-desktop]');
              const visible = [...desk.querySelectorAll('[data-law-id]')].filter(
                (el) => !el.classList.contains('is-filtered-out')
              );
              return {
                path: location.pathname,
                ids: visible.map((el) => el.getAttribute('data-law-id')),
              };
            }"""
        )
        page.fill("#laws-q", "")
        page.locator(
            '[data-signed-in-laws-desktop] .laws-chip[data-laws-chip=""]'
        ).click()
        restored = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-signed-in-laws-desktop]');
              const visible = [...desk.querySelectorAll('[data-law-id]')].filter(
                (el) => !el.classList.contains('is-filtered-out')
              );
              return {
                ids: visible.map((el) => el.getAttribute('data-law-id')),
                all: desk.querySelector('[data-laws-chip=""]').getAttribute('aria-pressed'),
                q: document.querySelector('#laws-q').value,
              };
            }"""
        )

        page.locator('a[href="/laws/ndps"]').first.click()
        page.wait_for_url("**/laws/ndps**", timeout=8000)
        ndps_url = page.url
        page.goto(f"{origin}/laws", wait_until="networkidle")
        page.locator('a[href="/laws/bns"]').first.click()
        page.wait_for_url("**/laws/bns**", timeout=8000)
        bns_url = page.url

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/laws", wait_until="networkidle")
        phone = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-signed-in-laws-desktop]');
              const back = desk.querySelector('.laws-back-link');
              const copy = desk.querySelector('.laws-index-copy');
              const head = desk.querySelector('.laws-index-head');
              const toggle = desk.querySelector('[data-laws-search-toggle]');
              const search = desk.querySelector('[data-laws-search]');
              const catalog = desk.querySelector('.laws-catalog');
              const vis = (el) => el && getComputedStyle(el).display !== 'none';
              return {
                backShown: vis(back),
                copyShown: vis(copy),
                headShown: vis(head),
                toggleShown: vis(toggle),
                searchHidden: search.hasAttribute('hidden'),
                cols: getComputedStyle(catalog).gridTemplateColumns.split(' ').length,
                ndpsHref: desk.querySelector('a[href="/laws/ndps"]') &&
                  desk.querySelector('a[href="/laws/ndps"]').getAttribute('href'),
                bnsHref: desk.querySelector('a[href="/laws/bns"]') &&
                  desk.querySelector('a[href="/laws/bns"]').getAttribute('href'),
              };
            }"""
        )
        browser.close()

    assert geo["brandTag"] == "A"
    assert geo["brandHref"] == "/dashboard"
    assert "invert" in geo["markFilter"]
    assert geo["headerH"] == pytest.approx(60, abs=2)
    assert geo["deskPresent"] is True
    assert geo["guestPresent"] is False
    assert geo["backHref"] == "/browse"
    assert geo["backDisplay"] != "none"
    assert geo["phoneHeadDisplay"] == "none"
    assert geo["heading"] == "Laws"
    assert geo["headingSize"] == "30px"
    assert geo["kicker"] == "Browse"
    assert "Bare Acts and statutes" in geo["lede"]
    assert geo["searchPlaceholder"] == "Search laws"
    assert geo["searchDisplay"] != "none"
    assert geo["searchX"] > geo["copyX"]
    assert [c["text"] for c in geo["chips"]][0] == "All"
    assert "Commercial" not in [c["text"] for c in geo["chips"]]
    assert "Health" in [c["text"] for c in geo["chips"]]
    assert all(c["tag"] == "BUTTON" and c["href"] is None for c in geo["chips"])
    assert geo["chips"][0]["pressed"] == "true"
    assert "bns" in geo["visibleIds"]
    assert "ndps" in geo["visibleIds"]
    assert "ca" not in geo["visibleIds"]
    assert geo["cols"] == 2
    assert geo["twoCol"] is True
    assert geo["ndpsHref"] == "/laws/ndps"
    assert geo["bnsHref"] == "/laws/bns"
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
    assert geo["playgroundCtaCount"] >= 1
    page_rgb = tuple(
        int(x.strip())
        for x in geo["pageBg"]
        .replace("rgba(", "")
        .replace("rgb(", "")
        .replace(")", "")
        .split(",")[:3]
    )
    header_rgb = tuple(
        int(x.strip())
        for x in geo["headerBg"]
        .replace("rgba(", "")
        .replace("rgb(", "")
        .replace(")", "")
        .split(",")[:3]
    )
    assert page_rgb[0] > 200 and page_rgb[0] < 250
    assert header_rgb[0] > 250
    assert "/browse" in browse_url
    assert "Browse the Constitution" in browse_heading
    assert criminal["path"] == "/laws"
    assert "subject=criminal" in criminal["search"]
    assert criminal["pressed"] == "true"
    assert criminal["all"] == "false"
    assert criminal["ids"]
    assert all("criminal" in sub.split() for sub in criminal["subjects"])
    assert searched["path"] == "/laws"
    assert searched["ids"] == ["ndps"]
    assert restored["all"] == "true"
    assert restored["q"] == ""
    assert "ndps" in restored["ids"]
    assert "bns" in restored["ids"]
    assert len(restored["ids"]) == len(geo["visibleIds"])
    assert "/laws/ndps" in ndps_url
    assert "/laws/bns" in bns_url
    assert phone["backShown"] is False
    assert phone["copyShown"] is False
    assert phone["headShown"] is True
    assert phone["toggleShown"] is True
    assert phone["searchHidden"] is True
    assert phone["cols"] == 1
    assert phone["ndpsHref"] == "/laws/ndps"
    assert phone["bnsHref"] == "/laws/bns"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
