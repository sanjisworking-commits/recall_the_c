"""Plus cohort desktop Browse Screen 02 (CTA map plus/02-screen).

Authorized: ChatGPT. Authenticated multiuser GET /browse with a real active
Plus subscription. Same accepted Browse visual system as Free signed-in
Screen 02; Free 3-Article strip and Unlock all are omitted. Header status
uses the existing RecallC Plus product string from EntitlementSnapshot.
No invented Plus copy, routes, or Browse redesign.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import socket
import threading
import time
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
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
USER = UUID("11111111-1111-4111-8111-111111111111")
INVENTED = (
    "Premium",
    "Unlimited",
    "renews",
    "Unlock all",
    "Free plan",
    "All 3 slots",
    "Start learning",
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


def _mu_app(tmp_path: Path, *, units: Path | None = None, display_name: str = "Sanjay"):
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER,
        email="a@example.com",
        display_name=display_name,
        avatar_url=None,
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
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


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _browse_panel(html: str) -> str:
    return html.split('<section class="panel browse"', 1)[1].split(
        "mobile-sheet", 1
    )[0]


def test_plus_browse_omits_free_strip_from_real_subscription(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    html = client.get("/browse").text
    panel = _browse_panel(html)
    header = _header(html)
    assert 'data-plus-browse="desktop"' in html
    assert "data-signed-in-browse-strip" not in html
    assert "browse-access-unlock" not in html
    assert "data-guest-strip" not in html
    assert ">Browse the Constitution<" in panel
    assert (
        "The Constitution, Part by Part. Open an Article, then learn any clause from inside it."
        in panel
    )
    assert 'href="/laws"' in panel
    assert 'href="/tables"' in panel
    assert '<span class="browse-resource-name">Laws</span>' in panel
    assert '<span class="browse-resource-name">Tables</span>' in panel
    assert "RecallC Plus" in header
    assert "Free account" not in header
    for phrase in INVENTED:
        assert phrase not in panel, phrase
    assert "Unlock all" not in panel
    assert "Free plan" not in panel
    playground = client.get("/playground")
    assert "data-signed-in-pg-gate" not in playground.text
    assert "My Playground" in playground.text
    laws = client.get("/laws")
    assert laws.status_code == 200


def test_free_signed_in_browse_keeps_allowance_and_unlock(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/browse").text
    assert 'data-plus-browse="desktop"' not in html
    strip = html.split("data-signed-in-browse-strip", 1)[1].split("</div>", 1)[0]
    assert "Free plan \u2014 pick any 3 Articles to learn." in strip
    assert "All 3 slots free." in strip
    assert 'class="browse-access-unlock" href="/playground">Unlock all</a>' in strip
    header = _header(html)
    assert "Free account" in header
    assert "RecallC Plus" not in header


def test_guest_browse_is_unchanged(tmp_path: Path) -> None:
    html = TestClient(_mu_app(tmp_path)).get("/browse").text
    assert 'data-plus-browse="desktop"' not in html
    assert "data-guest-strip" in html
    assert "data-signed-in-browse-strip" not in html
    assert "Unlock all" not in html
    assert "RecallC Plus" not in html


def test_halted_and_pro_are_not_plus_screen_02(tmp_path: Path) -> None:
    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/browse").text
    assert 'data-plus-browse="desktop"' not in halted_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/browse").text
    assert 'data-plus-browse="desktop"' not in pro_html
    assert "data-signed-in-browse-strip" in pro_html


def test_plus_browse_marker_is_conditional_in_templates() -> None:
    browse = BROWSE.read_text(encoding="utf-8")
    assert "plus_browse" in browse
    assert 'data-plus-browse="desktop"' in browse
    assert "Unlock all" in browse
    assert 'href="/laws"' in browse
    assert 'href="/tables"' in browse
    base = BASE.read_text(encoding="utf-8")
    assert "plus_browse" in base
    assert "RecallC Plus" in base
    assert "Free account" in base
    for phrase in ("Premium", "Unlimited", "renews"):
        assert phrase not in browse


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


def test_plus_browse_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "plus_browse_screen02_1280.png"
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
              const plus = document.querySelector('[data-plus-browse="desktop"]');
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
              const mr = mark.getBoundingClientRect();
              const grid = document.querySelector('.browse-resource-grid');
              const lr = laws.getBoundingClientRect();
              const tr = tables.getBoundingClientRect();
              const gr = grid.getBoundingClientRect();
              const fr = fallback.getBoundingClientRect();
              const pageBg = getComputedStyle(document.querySelector('.sheet')).backgroundColor;
              const headerBg = getComputedStyle(header).backgroundColor;
              const browseBg = getComputedStyle(browse).backgroundColor;
              const panelText = document.querySelector('section.browse').innerText;
              return {
                present: Boolean(plus),
                headerH: hr.height,
                brandHref: brand.getAttribute('href'),
                brandSrc: mark.getAttribute('src'),
                markFilter: getComputedStyle(mark).filter,
                markW: mr.width,
                markH: mr.height,
                browseText: browse.textContent.replace(/\\s+/g, ' ').trim(),
                browseBg,
                pageBg,
                headerBg,
                headingText: heading.textContent.trim(),
                headingSize: getComputedStyle(heading).fontSize,
                ledeSize: getComputedStyle(lede).fontSize,
                headingY: heading.getBoundingClientRect().y,
                gridY: gr.y,
                hasStrip: !!strip,
                hasUnlock: !!unlock,
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
                partTag: partHead && partHead.tagName,
                partParent: partHead && partHead.parentElement && partHead.parentElement.tagName,
                partRailDisplay: partRail ? getComputedStyle(partRail).display : null,
                mobileHeadDisplay: mobileHead ? getComputedStyle(mobileHead).display : null,
                accountName: document.querySelector('.account-menu-btn-name').textContent.trim(),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                fallbackW: fr.width,
                fallbackH: fr.height,
                legendCaption: legend ? legend.querySelector('.browse-legend-caption').textContent.trim() : null,
                newsLabel: news ? news.innerText.replace(/\\s+/g, ' ').trim() : null,
                navLabels: [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                  (el) => el.textContent.replace(/\\s+/g, ' ').trim()
                ),
                plusCopy: /Premium|Unlimited|Free plan|Unlock all|All 3 slots/.test(panelText),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

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
        page.locator('.PrimaryTabs--top a[href="/playground"]').click()
        page.wait_for_url("**/playground**", timeout=8000)
        playground_html = page.content()
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/browse", wait_until="networkidle")
        phone = page.evaluate(
            """() => {
              const strip = document.querySelector('[data-signed-in-browse-strip]');
              const plus = document.querySelector('[data-plus-browse="desktop"]');
              const display = document.querySelector('.browse > .display');
              const legend = document.querySelector('.browse-legend');
              const part = document.querySelector('.browse-part');
              const rail = document.querySelector('.browse-part-rail');
              const head = document.querySelector('.mobile-screen-head');
              const vis = (el) => el && getComputedStyle(el).display !== 'none';
              return {
                hasStrip: !!strip,
                plusPresent: Boolean(plus),
                displayShown: vis(display),
                legendShown: vis(legend),
                partShown: vis(part),
                railShown: vis(rail),
                headShown: vis(head),
              };
            }"""
        )
        browser.close()

    assert geo["present"] is True
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
    assert geo["accountStatus"] == "RecallC Plus"
    assert geo["headingText"] == "Browse the Constitution"
    assert geo["headingSize"] == "30px"
    assert geo["ledeSize"] == "14.5px"
    assert geo["headingY"] > geo["headerH"]
    assert geo["gridY"] > geo["headingY"]
    assert geo["hasStrip"] is False
    assert geo["hasUnlock"] is False
    assert geo["plusCopy"] is False
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
    assert "/laws" in laws_url
    assert tables_href == "/tables"
    assert article_href and article_href.startswith("/browse/article/")
    assert "data-signed-in-pg-gate" not in playground_html
    assert phone["hasStrip"] is False
    assert phone["plusPresent"] is True
    assert phone["displayShown"] is False
    assert phone["legendShown"] is False
    assert phone["partShown"] is False
    assert phone["railShown"] is True
    assert phone["headShown"] is True
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
