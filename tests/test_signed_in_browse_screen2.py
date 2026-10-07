"""Signed-in desktop Browse (CTA map signedIn/02-screen).

Authorized: ChatGPT. Authenticated multiuser GET /browse keeps the same
browse_index.html as guests, with the existing free-plan strip, Unlock all
→ Gate, Laws → /laws, and legend chips as filters. Phone Browse (part-card
rail, mobile head) is unchanged. Article cards and Tables keep existing
hrefs. Signed-in Landing is not reopened.
"""

from __future__ import annotations

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

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "data" / "output" / "learning_units.json"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"


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


def _browse_panel(html: str) -> str:
    return html.split('<section class="panel browse"', 1)[1].split(
        "mobile-sheet", 1
    )[0]


def _strip(html: str) -> str:
    return html.split("data-signed-in-browse-strip", 1)[1].split("</div>", 1)[0]


def test_signed_in_browse_strip_uses_existing_copy_and_unlocks_gate(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/browse").text
    panel = _browse_panel(html)
    heading = panel.find(">Browse the Constitution<")
    strip_at = panel.find("data-signed-in-browse-strip")
    assert heading != -1
    assert strip_at != -1
    assert heading < strip_at
    assert "data-guest-strip" not in html
    strip = _strip(html)
    assert "Free plan \u2014 pick any 3 Articles to learn." in strip
    assert "All 3 slots free." in strip
    assert 'class="browse-access-unlock" href="/playground">Unlock all</a>' in strip
    assert 'href="/pricing"' not in strip
    gate = client.get("/playground", follow_redirects=False)
    assert gate.status_code == 200
    assert 'class="EntitlementGate"' in gate.text
    assert 'data-playground-gate="not_subscribed"' in gate.text
    assert "Unlock Playground" in gate.text


def test_signed_in_browse_laws_and_tables_keep_existing_hrefs(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/browse").text
    row = html.split('class="browse-resource-grid"', 1)[1].split(
        "browse-constitution-label", 1
    )[0]
    assert '<span class="browse-resource-name">Laws</span>' in row
    assert "Bare Acts &amp; statutes" in row
    assert '<span class="browse-resource-name">Tables</span>' in row
    assert "Schedules, Parts, writs" in row
    assert 'href="/laws"' in row
    assert 'href="/tables"' in row
    laws = client.get("/laws")
    assert laws.status_code == 200
    assert "data-laws-index" in laws.text or "laws-index-title" in laws.text
    tables = client.get("/tables")
    assert tables.status_code == 200
    css = STYLES.read_text(encoding="utf-8")
    authed_grid = css.split(
        'body.is-authed[data-mscreen="browse"] .browse-resource-grid {', 1
    )[1].split("}", 1)[0]
    assert "760px" in authed_grid
    guest_grid = css.split(
        'body.is-guest[data-mscreen="browse"] .browse-resource-grid {', 1
    )[1].split("}", 1)[0]
    assert "calc(200% / 3)" in guest_grid


def test_signed_in_browse_legend_uses_in_news_and_filters_only(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS))
    _sign_in(client)
    html = client.get("/browse").text
    assert 'class="browse-legend"' in html
    assert 'data-browse-filter="news"' in html
    assert 'data-browse-filter="visualise"' in html
    legend = html.split('class="browse-legend"', 1)[1].split(
        "browse-constitution-label", 1
    )[0]
    assert "In news" in legend
    assert ">News<" not in legend
    assert "Visualise" in legend
    assert 'href=' not in legend.split("<button", 1)[0]
    assert 'aria-pressed="false"' in legend


def test_signed_in_browse_part_rows_have_no_handler(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/browse").text
    assert "data-browse-part-heading" in html
    chunks = html.split("data-browse-part-heading")[1:]
    assert chunks
    for chunk in chunks[:4]:
        block = chunk.split("</div>", 1)[0]
        assert "<a " not in block
        assert "href=" not in block
        assert "browse-part-roman" in block
        assert "browse-part-name" in block
        assert "browse-part-range" in block


def test_signed_in_browse_article_cards_keep_existing_hrefs(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/browse").text
    panel = _browse_panel(html)
    assert 'href="/browse/article/' in panel
    assert "The Constitution, Part by Part. Open an Article, then learn any clause from inside it." in panel


def test_signed_in_browse_desktop_chrome(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/browse").text
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
    css = STYLES.read_text(encoding="utf-8")
    authed_mark = css.split(
        'body.is-authed[data-mscreen="browse"] .brand-mark {', 1
    )[1].split("}", 1)[0]
    assert "invert(1)" in authed_mark
    display = css.split(
        'body.is-authed[data-mscreen="browse"] .browse > .display {', 1
    )[1].split("}", 1)[0]
    assert "30px" in display
    assert "font-weight: 600" in display
    lede = css.split(
        'body.is-authed[data-mscreen="browse"] .browse > .lede {', 1
    )[1].split("}", 1)[0]
    assert "margin: 0 0 10px" in lede
    cards = css.split(
        'body.is-authed[data-mscreen="browse"] .browse-article-card {', 1
    )[1].split("}", 1)[0]
    assert "min-height: 48px" in cards
    assert "padding: 8px 10px 10px" in cards
    roman = css.split(
        'body.is-authed[data-mscreen="browse"] .browse-part-roman {', 1
    )[1].split("}", 1)[0]
    assert "17px" in roman
    assert (
        "body.is-authed[data-mscreen=\"browse\"] .account-avatar-fallback {\n"
        "    background: var(--ink);\n"
        "    color: var(--on-accent);"
    ) in css
    phone_hide = css.split(
        "body.is-authed[data-mscreen=\"browse\"] .browse-access-summary {", 1
    )[1].split("}", 1)[0]
    assert "display: none" in phone_hide
    shell = css.split("/* R1 desktop shell", 1)[1]
    assert "position: absolute" not in shell
    assert "left: 50%" not in shell


def test_signed_in_browse_does_not_touch_phone_or_landing() -> None:
    mobile = MOBILE.read_text(encoding="utf-8")
    assert 'body[data-mscreen="browse"] .browse > .display' in mobile
    assert 'body[data-mscreen="browse"] .browse-part' in mobile
    assert ".part-card-track" in mobile
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-guest-landing="desktop"' in landing
    assert "Explore the Constitution" in landing


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


def test_signed_in_browse_1280_matches_desktop_shot(tmp_path: Path) -> None:
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
    shot_path = artifact_dir / "signed_in_browse_1280.png"
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
        page.goto(f"{origin}/browse", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const brand = document.querySelector('.brand');
              const mark = document.querySelector('.brand-mark');
              const header = document.querySelector('.site-header');
              const browse = document.querySelector('.nav-link.is-active');
              const strip = document.querySelector('[data-signed-in-browse-strip]');
              const unlock = document.querySelector('.browse-access-unlock');
              const laws = document.querySelector('.browse-resource-card[href="/laws"]');
              const tables = document.querySelector('.browse-resource-card[href="/tables"]');
              const heading = document.querySelector('.browse > .display');
              const lede = document.querySelector('.browse > .lede');
              const partHead = document.querySelector('[data-browse-part-heading]');
              const partRail = document.querySelector('.browse-part-rail');
              const article = document.querySelector('.browse-article-card[href], .browse-card-link');
              const fallback = document.querySelector('.account-avatar-fallback');
              const mobileHead = document.querySelector('.mobile-screen-head');
              const legend = document.querySelector('.browse-legend');
              const news = document.querySelector('.browse-legend-item[data-browse-filter="news"]');
              const hr = header.getBoundingClientRect();
              const br = brand.getBoundingClientRect();
              const mr = mark.getBoundingClientRect();
              const sr = strip.getBoundingClientRect();
              const grid = document.querySelector('.browse-resource-grid');
              const lr = laws.getBoundingClientRect();
              const tr = tables.getBoundingClientRect();
              const gr = grid.getBoundingClientRect();
              const fr = fallback.getBoundingClientRect();
              const pageBg = getComputedStyle(document.querySelector('.sheet')).backgroundColor;
              const headerBg = getComputedStyle(header).backgroundColor;
              const browseBg = getComputedStyle(browse).backgroundColor;
              const headingSize = getComputedStyle(heading).fontSize;
              const ledeSize = getComputedStyle(lede).fontSize;
              return {
                headerH: hr.height,
                brandTag: brand.tagName,
                brandHref: brand.getAttribute('href'),
                brandSrc: mark.getAttribute('src'),
                brandX: br.x,
                markFilter: getComputedStyle(mark).filter,
                markW: mr.width,
                markH: mr.height,
                browseText: browse.textContent.replace(/\\s+/g, ' ').trim(),
                browseBg,
                pageBg,
                headerBg,
                headingText: heading.textContent.trim(),
                headingSize,
                ledeSize,
                stripY: sr.y,
                headingY: heading.getBoundingClientRect().y,
                stripText: strip.innerText.replace(/\\s+/g, ' ').trim(),
                unlockHref: unlock.getAttribute('href'),
                unlockText: unlock.textContent.trim(),
                lawsHref: laws.getAttribute('href'),
                tablesHref: tables.getAttribute('href'),
                lawsX: lr.x,
                tablesX: tr.x,
                lawsY: lr.y,
                tablesY: tr.y,
                lawsW: lr.width,
                tablesW: tr.width,
                gridW: gr.width,
                articleHref: article && article.getAttribute('href'),
                partTag: partHead.tagName,
                partParent: partHead.parentElement && partHead.parentElement.tagName,
                partRailDisplay: partRail ? getComputedStyle(partRail).display : null,
                mobileHeadDisplay: mobileHead ? getComputedStyle(mobileHead).display : null,
                accountName: document.querySelector('.account-menu-btn-name').textContent.trim(),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                fallbackW: fr.width,
                fallbackH: fr.height,
                fallbackRadius: getComputedStyle(fallback).borderRadius,
                fallbackBg: getComputedStyle(fallback).backgroundColor,
                legendCaption: legend.querySelector('.browse-legend-caption').textContent.trim(),
                newsLabel: news ? news.innerText.replace(/\\s+/g, ' ').trim() : null,
                navLabels: [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                  (el) => el.textContent.replace(/\\s+/g, ' ').trim()
                ),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator(".browse-access-unlock").click()
        page.wait_for_url("**/playground**", timeout=8000)
        gate_url = page.url
        gate_html = page.content()
        page.goto(f"{origin}/browse", wait_until="networkidle")
        page.locator('.browse-resource-card[href="/laws"]').click()
        page.wait_for_url("**/laws**", timeout=8000)
        laws_url = page.url
        page.goto(f"{origin}/browse", wait_until="networkidle")
        tables_href = page.locator(
            '.browse-resource-card[href="/tables"]'
        ).get_attribute("href")
        article_href = page.locator(
            ".browse-article-card[href], .browse-card-link"
        ).first.get_attribute("href")
        if page.locator(".browse-legend-item").count() >= 2:
            news = page.locator('.browse-legend-item[data-browse-filter="news"]')
            vis = page.locator('.browse-legend-item[data-browse-filter="visualise"]')
            news.click()
            pressed = page.evaluate(
                """() => ({
                  news: document.querySelector('.browse-legend-item[data-browse-filter="news"]').getAttribute('aria-pressed'),
                  vis: document.querySelector('.browse-legend-item[data-browse-filter="visualise"]').getAttribute('aria-pressed'),
                  filter: document.querySelector('section.browse').getAttribute('data-mark-filter'),
                  hidden: document.querySelectorAll('.browse-article-card.is-mark-hidden').length,
                  total: document.querySelectorAll('.browse-article-card').length,
                })"""
            )
            vis.click()
            swapped = page.evaluate(
                """() => ({
                  news: document.querySelector('.browse-legend-item[data-browse-filter="news"]').getAttribute('aria-pressed'),
                  vis: document.querySelector('.browse-legend-item[data-browse-filter="visualise"]').getAttribute('aria-pressed'),
                  filter: document.querySelector('section.browse').getAttribute('data-mark-filter'),
                })"""
            )
            vis.click()
            cleared = page.evaluate(
                """() => document.querySelector('section.browse').getAttribute('data-mark-filter')"""
            )
        else:
            pressed = swapped = cleared = None

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/browse", wait_until="networkidle")
        phone = page.evaluate(
            """() => {
              const strip = document.querySelector('[data-signed-in-browse-strip]');
              const display = document.querySelector('.browse > .display');
              const legend = document.querySelector('.browse-legend');
              const part = document.querySelector('.browse-part');
              const rail = document.querySelector('.browse-part-rail');
              const head = document.querySelector('.mobile-screen-head');
              const laws = document.querySelector('.browse-resource-card[href="/laws"]');
              const tables = document.querySelector('.browse-resource-card[href="/tables"]');
              const vis = (el) => el && getComputedStyle(el).display !== 'none';
              return {
                stripDisplay: strip ? getComputedStyle(strip).display : null,
                displayShown: vis(display),
                legendShown: vis(legend),
                partShown: vis(part),
                railShown: vis(rail),
                headShown: vis(head),
                lawsHref: laws && laws.getAttribute('href'),
                tablesHref: tables && tables.getAttribute('href'),
              };
            }"""
        )
        browser.close()

    assert geo["brandTag"] == "A"
    assert geo["brandHref"] == "/dashboard"
    assert geo["brandSrc"] == "/static/main_logo.png"
    assert "invert" in geo["markFilter"]
    assert geo["markW"] == pytest.approx(30, abs=1)
    assert geo["markH"] == pytest.approx(30, abs=1)
    assert geo["headerH"] == pytest.approx(60, abs=2)
    assert geo["browseText"] == "Browse"
    assert geo["navLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["accountName"] == "Sanjay"
    assert geo["accountStatus"] == "Free account"
    assert geo["headingText"] == "Browse the Constitution"
    assert geo["headingSize"] == "30px"
    assert geo["ledeSize"] == "14.5px"
    assert geo["headingY"] > geo["headerH"]
    assert geo["stripY"] > geo["headingY"]
    assert "Free plan" in geo["stripText"]
    assert "Unlock all" in geo["stripText"]
    assert geo["unlockHref"] == "/playground"
    assert geo["unlockText"] == "Unlock all"
    assert geo["lawsHref"] == "/laws"
    assert geo["tablesHref"] == "/tables"
    assert geo["lawsX"] < geo["tablesX"]
    assert abs(geo["lawsY"] - geo["tablesY"]) <= 2
    assert abs(geo["lawsW"] - geo["tablesW"]) <= 2
    assert geo["gridW"] == pytest.approx(760, abs=8)
    assert geo["articleHref"] and geo["articleHref"].startswith("/browse/article/")
    assert geo["partTag"] == "DIV"
    assert geo["partParent"] != "A"
    assert geo["partRailDisplay"] == "none"
    assert geo["mobileHeadDisplay"] == "none"
    assert geo["fallbackW"] == pytest.approx(36, abs=1)
    assert geo["fallbackH"] == pytest.approx(36, abs=1)
    assert geo["legendCaption"] == "Marks"
    assert geo["newsLabel"] and "In news" in geo["newsLabel"]
    assert "rgb(20, 20, 20)" in geo["browseBg"] or "rgb(0, 0, 0)" in geo["browseBg"]
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
    assert "/playground" in gate_url
    assert 'data-playground-gate="not_subscribed"' in gate_html
    assert "Unlock Playground" in gate_html
    assert "/laws" in laws_url
    assert tables_href == "/tables"
    assert article_href and article_href.startswith("/browse/article/")
    if pressed is not None:
        assert pressed["news"] == "true"
        assert pressed["vis"] == "false"
        assert pressed["filter"] == "news"
        assert pressed["hidden"] > 0
        assert pressed["hidden"] < pressed["total"]
        assert swapped["news"] == "false"
        assert swapped["vis"] == "true"
        assert swapped["filter"] == "visualise"
        assert cleared is None
    assert phone["stripDisplay"] == "none"
    assert phone["displayShown"] is False
    assert phone["legendShown"] is False
    assert phone["partShown"] is False
    assert phone["railShown"] is True
    assert phone["headShown"] is True
    assert phone["lawsHref"] == "/laws"
    assert phone["tablesHref"] == "/tables"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
