"""Guest Browse index Screen 2 (desktop CTA map guest/02-screen).

Authorized: ChatGPT plan + Sanjali. Guest `/browse` is this Constitution
index only. Phone Browse (part-card rail, mobile head) is unchanged.
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
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
FIXTURE = Path(__file__).parent / "fixtures" / "guest_browse" / "02-screen.jpg"
ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "data" / "output" / "learning_units.json"


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _guest_app(tmp_path: Path, *, units: Path | None = None):
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
        units_path=units or MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=settings,
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
    )


def _guest_client(tmp_path: Path, *, units: Path | None = None) -> TestClient:
    return TestClient(_guest_app(tmp_path, units=units))


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _primary_nav(html: str) -> str:
    return html.split('aria-label="Primary"', 1)[1].split("</nav>", 1)[0]


def _guest_strip(html: str) -> str:
    return html.split('data-guest-strip', 1)[1].split("</div>", 1)[0]


def _browse_panel(html: str) -> str:
    return html.split('<section class="panel browse"', 1)[1].split(
        "mobile-sheet", 1
    )[0]


def test_screen2_guest_strip_is_under_the_heading(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/browse").text
    panel = _browse_panel(html)
    heading = panel.find(">Browse the Constitution<")
    strip = panel.find("data-guest-strip")
    assert heading != -1
    assert strip != -1
    assert heading < strip
    body = _guest_strip(html)
    assert "Reading as a guest" in body
    assert "Sign in to save 3 Articles" in body
    assert "guest-strip-dismiss" not in _guest_strip(html)
    assert "data-guest-strip-dismiss" not in html


def test_screen2_strip_signin_routes_to_the_gate(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    html = client.get("/browse").text
    strip = _guest_strip(html)
    assert 'href="/login"' in strip
    assert 'data-guest-gate' in strip
    gate = client.get("/login", follow_redirects=False)
    assert gate.status_code == 200
    assert "<title>Sign in" in gate.text
    assert "Continue as guest" in gate.text


def test_screen2_strip_is_the_only_desktop_signin_entry(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/browse").text
    header = _header(html)
    nav = _primary_nav(html)
    assert "nav-signin" not in header
    assert 'href="/login"' not in nav
    strip = _guest_strip(html)
    assert strip.count('href="/login"') == 1
    assert 'class="guest-strip-signin"' in strip


def test_screen2_laws_card_routes_to_the_laws_index(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
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
    assert 'data-laws-index' in laws.text or "laws-index-title" in laws.text


def test_screen2_legend_filters_marks_and_keeps_pressed_state(tmp_path: Path) -> None:
    html = _guest_client(tmp_path, units=UNITS).get("/browse").text
    assert 'class="browse-legend"' in html
    assert 'data-browse-filter="news"' in html
    assert 'data-browse-filter="visualise"' in html
    legend = html.split('class="browse-legend"', 1)[1].split(
        "browse-constitution-label", 1
    )[0]
    assert ">news<" in legend
    assert "Visualise" in legend
    assert 'aria-pressed="false"' in legend
    js = (
        ROOT / "src/constitution_memorizer/web/static/app.js"
    ).read_text(encoding="utf-8")
    apply = js.split("function applyFilter", 1)[1].split("function wait", 1)[0]
    assert 'aria-pressed"' in apply or "aria-pressed" in apply
    assert "is-mark-hidden" in apply
    assert "data-mark-filter" in apply


def test_screen2_part_heading_rows_are_not_links(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/browse").text
    assert "data-browse-part-heading" in html
    chunks = html.split('data-browse-part-heading')[1:]
    assert chunks
    for chunk in chunks[:4]:
        block = chunk.split("</div>", 1)[0]
        assert "<a " not in block
        assert "href=" not in block
        assert "browse-part-roman" in block
        assert "browse-part-name" in block
        assert "browse-part-range" in block


def test_screen2_desktop_header_and_guest_account_menu(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/browse").text
    header = _header(html)
    nav = _primary_nav(html)
    assert "<span class=\"brand\"" in header
    assert 'class="brand" href=' not in header
    assert "Recall the C" in header
    for label in ("Today", "Browse", "Playground", "Calendar", "Profile"):
        assert label in nav
    assert 'href="/dashboard"' in nav
    assert 'href="/browse"' in nav
    assert 'href="/playground"' in nav
    assert 'href="/calendar"' in nav
    assert 'href="/profile"' in nav
    assert "is-active" in nav
    assert "aria-current=\"page\"" in nav
    assert ">Home<" not in nav
    assert ">Search<" not in nav
    assert ">Learn<" not in nav
    assert "Learning as guest" not in header
    assert "nav-signin" not in header
    assert 'data-guest-account-menu' in header
    assert 'account-menu-btn-name">Guest<' in header
    assert "Not signed in" in header
    menu = header.split("data-account-panel", 1)[1]
    assert 'href="/settings">Settings</a>' in menu
    assert "data-account-close" in menu
    assert ">Sign out<" in menu
    assert 'action="/logout"' not in menu
    assert 'href="/profile"' not in menu
    assert 'href="/learn"' not in menu
    assert 'href="/progress"' not in menu
    assert 'href="/calendar"' not in menu
    assert 'href="/memory"' not in menu
    assert 'href="/admin"' not in menu


def test_screen2_does_not_change_mobile_browse_part_cards(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/browse").text
    assert 'class="browse-part-rail"' in html
    assert "part-card-track" in html
    assert 'class="mobile-screen-head"' in html
    assert 'class="mobile-tabbar is-guest"' in html
    css = (
        ROOT / "src/constitution_memorizer/web/static/mobile.css"
    ).read_text(encoding="utf-8")
    assert (
        'body[data-mscreen="browse"] .browse > .display' in css
    )
    assert ".part-card-track" in css


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


def test_screen2_1280_matches_prototype_screenshot(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "guest_browse_screen2_1280.png"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        page = browser.new_page(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )
        page.goto(f"http://127.0.0.1:{port}/browse", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const brand = document.querySelector('.brand');
              const header = document.querySelector('.site-header');
              const browse = document.querySelector('.nav-link.is-active');
              const strip = document.querySelector('[data-guest-strip]');
              const signin = document.querySelector('.guest-strip-signin');
              const laws = document.querySelector('.browse-resource-card[href="/laws"]');
              const tables = document.querySelector('.browse-resource-card[href="/tables"]');
              const heading = document.querySelector('.browse > .display');
              const partHead = document.querySelector('[data-browse-part-heading]');
              const partRail = document.querySelector('.browse-part-rail');
              const chip = document.querySelector('[data-guest-account-menu] .account-menu-btn');
              const mobileHead = document.querySelector('.mobile-screen-head');
              const visibleLogin = [...document.querySelectorAll('a[href^="/login"]')].filter((el) => {
                const s = getComputedStyle(el);
                return s.display !== 'none' && s.visibility !== 'hidden' && el.offsetParent !== null;
              });
              const hr = header.getBoundingClientRect();
              const br = brand.getBoundingClientRect();
              const sr = strip.getBoundingClientRect();
              const lr = laws.getBoundingClientRect();
              const tr = tables.getBoundingClientRect();
              const pageBg = getComputedStyle(document.querySelector('.sheet')).backgroundColor;
              const headerBg = getComputedStyle(header).backgroundColor;
              const signinBg = getComputedStyle(signin).backgroundColor;
              const browseBg = getComputedStyle(browse).backgroundColor;
              const partTag = partHead.tagName;
              const partParent = partHead.parentElement && partHead.parentElement.tagName;
              return {
                headerH: hr.height,
                headerY: hr.y,
                brandTag: brand.tagName,
                brandHref: brand.getAttribute('href'),
                brandX: br.x,
                browseText: browse.textContent.replace(/\\s+/g, ' ').trim(),
                browseBg,
                pageBg,
                headerBg,
                signinBg,
                signinHref: signin.getAttribute('href'),
                headingText: heading.textContent.trim(),
                stripY: sr.y,
                headingY: heading.getBoundingClientRect().y,
                lawsHref: laws.getAttribute('href'),
                tablesHref: tables.getAttribute('href'),
                lawsX: lr.x,
                tablesX: tr.x,
                lawsY: lr.y,
                tablesY: tr.y,
                partTag,
                partParent,
                partRailDisplay: partRail ? getComputedStyle(partRail).display : null,
                mobileHeadDisplay: mobileHead ? getComputedStyle(mobileHead).display : null,
                visibleLogin: visibleLogin.map((el) => el.getAttribute('href')),
                guestName: document.querySelector('.account-menu-btn-name').textContent.trim(),
                guestStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                chipW: chip.getBoundingClientRect().width,
                navLabels: [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                  (el) => el.textContent.replace(/\\s+/g, ' ').trim()
                ),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        diff = None
        if FIXTURE.is_file():
            import base64

            b64 = base64.b64encode(FIXTURE.read_bytes()).decode("ascii")
            live = base64.b64encode(page.screenshot(type="png")).decode("ascii")
            diff = page.evaluate(
                """async ({ fixture, live }) => {
                  function load(src) {
                    return new Promise((resolve, reject) => {
                      const img = new Image();
                      img.onload = () => resolve(img);
                      img.onerror = reject;
                      img.src = src;
                    });
                  }
                  const a = await load('data:image/jpeg;base64,' + fixture);
                  const b = await load('data:image/png;base64,' + live);
                  const w = Math.min(a.naturalWidth, b.naturalWidth, 1280);
                  const h = Math.min(a.naturalHeight, b.naturalHeight, 800);
                  const ca = document.createElement('canvas');
                  const cb = document.createElement('canvas');
                  ca.width = cb.width = w;
                  ca.height = cb.height = h;
                  const xa = ca.getContext('2d');
                  const xb = cb.getContext('2d');
                  xa.drawImage(a, 0, 0, w, h);
                  xb.drawImage(b, 0, 0, w, h);
                  const pa = xa.getImageData(0, 0, w, h).data;
                  const pb = xb.getImageData(0, 0, w, h).data;
                  let acc = 0;
                  let n = 0;
                  const step = 8;
                  for (let y = 0; y < h; y += step) {
                    for (let x = 0; x < w; x += step) {
                      const i = (y * w + x) * 4;
                      const dr = pa[i] - pb[i];
                      const dg = pa[i + 1] - pb[i + 1];
                      const db = pa[i + 2] - pb[i + 2];
                      acc += dr * dr + dg * dg + db * db;
                      n += 1;
                    }
                  }
                  return { rms: Math.sqrt(acc / (n * 3)), w, h, n };
                }""",
                {"fixture": b64, "live": live},
            )
        page.locator("[data-account-toggle]").click()
        menu = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-guest-account-menu] [data-account-panel]');
              const items = [...panel.querySelectorAll('[role="menuitem"]')].map((el) => ({
                tag: el.tagName,
                href: el.getAttribute('href'),
                text: el.textContent.trim(),
                close: el.hasAttribute('data-account-close'),
                action: el.closest('form') && el.closest('form').getAttribute('action'),
              }));
              return { hidden: panel.hidden, items };
            }"""
        )
        page.locator("[data-account-close]").click()
        closed = page.evaluate(
            """() => document.querySelector('[data-guest-account-menu] [data-account-panel]').hidden"""
        )
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
        browser.close()

    assert geo["brandTag"] == "SPAN"
    assert geo["brandHref"] is None
    assert geo["headerH"] == pytest.approx(60, abs=2)
    assert geo["browseText"] == "Browse"
    assert geo["navLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["guestName"] == "Guest"
    assert geo["guestStatus"] == "Not signed in"
    assert geo["headingText"] == "Browse the Constitution"
    assert geo["headingY"] > geo["headerH"]
    assert geo["stripY"] > geo["headingY"]
    assert geo["signinHref"] == "/login"
    assert geo["lawsHref"] == "/laws"
    assert geo["tablesHref"] == "/tables"
    assert geo["lawsX"] < geo["tablesX"]
    assert abs(geo["lawsY"] - geo["tablesY"]) <= 2
    assert geo["partTag"] == "DIV"
    assert geo["partParent"] != "A"
    assert geo["partRailDisplay"] == "none"
    assert geo["mobileHeadDisplay"] == "none"
    assert geo["visibleLogin"] == ["/login"]
    assert "rgb(20, 20, 20)" in geo["browseBg"] or "rgb(0, 0, 0)" in geo["browseBg"]
    assert "rgb(20, 20, 20)" in geo["signinBg"] or "rgb(0, 0, 0)" in geo["signinBg"]
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
    assert menu["hidden"] is False
    assert [item["text"] for item in menu["items"]] == ["Settings", "Sign out"]
    assert menu["items"][0]["href"] == "/settings"
    assert menu["items"][1]["close"] is True
    assert menu["items"][1]["action"] is None
    assert closed is True
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
    assert FIXTURE.is_file(), "guest/02-screen.jpg fixture missing"
    assert diff is not None
    assert diff["w"] == 1280
    assert diff["rms"] < 32
