"""Guest NDPS Bare Act head Screen 4 (desktop CTA map guest/04-screen).

Authorized: ChatGPT plan. Guest `/laws/ndps` desktop only. Phone Bare Act,
Landing, Browse, Laws index, and subscriber heads stay unchanged.
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
from constitution_memorizer.web.guest_bareact_head import (
    NDPS_GUEST_KICKER,
    NDPS_GUEST_META,
    NDPS_GUEST_ROWS,
    NDPS_GUEST_TITLE,
    ndps_guest_head,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
FIXTURE = Path(__file__).parent / "fixtures" / "guest_bareact" / "04-screen.jpg"
ROOT = Path(__file__).resolve().parents[1]


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


def _guest_desk(html: str) -> str:
    return html.split("data-guest-bareact-desktop", 1)[1].split(
        "data-bareact-phone", 1
    )[0]


def _phone_index(html: str) -> str:
    return html.split("data-bareact-phone", 1)[1]


def test_screen4_guest_ndps_uses_screen2_header(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/laws/ndps").text
    header = _header(html)
    nav = _primary_nav(html)
    assert "data-guest-bareact-desktop" in html
    assert "<span class=\"brand\"" in header
    assert 'class="brand" href=' not in header
    assert 'src="/static/main_logo.png"' in header
    assert "Recall the C" in header
    assert "data-guest-account-menu" in header
    assert 'account-menu-btn-name">Guest<' in header
    assert "Not signed in" in header
    assert "nav-signin" not in header
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
    guest_mark = css.split(
        'body.is-guest[data-mscreen="bareact"]:has([data-guest-bareact-desktop]) .brand-mark {',
        1,
    )[1].split("}", 1)[0]
    assert "invert(1)" in guest_mark


def test_screen4_back_returns_to_laws(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    desk = _guest_desk(client.get("/laws/ndps").text)
    assert 'class="guest-bareact-back" href="/laws"' in desk
    laws = client.get("/laws", follow_redirects=False)
    assert laws.status_code == 200
    assert "data-guest-laws-desktop" in laws.text


def test_screen4_copy_and_single_playground_cta(tmp_path: Path) -> None:
    desk = _guest_desk(_guest_client(tmp_path).get("/laws/ndps").text)
    assert NDPS_GUEST_KICKER in desk
    assert f">{NDPS_GUEST_TITLE}<" in desk
    assert NDPS_GUEST_META in desk
    assert "Sign in to use Playground" in desk
    assert desk.count("Sign in to use Playground") == 1
    assert f'href="{add_path("ndps")}"' in desk
    assert "data-pg-sheet" in desk
    assert "Already in Playground" not in desk
    assert ">Sections<" not in desk
    assert ">Continue<" not in desk
    assert "LawPlaygroundCta" not in desk
    assert "About this act" not in desk
    assert "data-bareact-tabs" not in desk


def test_screen4_visible_rows_match_the_prototype(tmp_path: Path) -> None:
    desk = _guest_desk(_guest_client(tmp_path).get("/laws/ndps").text)
    for row in NDPS_GUEST_ROWS:
        assert row.tag in desk
        assert row.title in desk
        assert row.range_label in desk
    assert "CHAPTER IIA" not in desk
    assert "NATIONAL FUND" not in desk.upper()
    assert 'href="/laws/ndps/section/' not in desk
    assert 'href="/laws/ndps/schedule/' not in desk
    assert "<details" not in desk
    assert 'role="button"' not in desk
    assert ndps_guest_head().rows == NDPS_GUEST_ROWS


def test_screen4_does_not_change_phone_or_other_screens(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    html = client.get("/laws/ndps").text
    phone = _phone_index(html)
    assert "<details" in phone
    assert 'href="/laws/ndps/section/' in phone
    assert 'href="/laws/ndps/schedule/' in phone
    assert "LawPlaygroundCta" in phone
    landing = client.get("/").text
    assert 'data-guest-landing="desktop"' in landing
    browse = client.get("/browse").text
    assert "Browse the Constitution" in browse
    laws = client.get("/laws").text
    assert "data-guest-laws-desktop" in laws
    assert "data-guest-bareact-desktop" not in laws
    bns = client.get("/laws/bns").text
    assert "data-guest-bareact-desktop" not in bns
    section = client.get("/laws/ndps/section/1").text
    assert "data-guest-bareact-desktop" not in section
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
    assert html.count("<details") == 8
    assert 'href="/laws/ndps/section/' in html


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


def test_screen4_1280_cta_opens_add_dialog_and_rows_are_inert(tmp_path: Path) -> None:
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
              const desk = document.querySelector('[data-guest-bareact-desktop]');
              const phone = document.querySelector('[data-bareact-phone]');
              const brand = document.querySelector('.brand');
              const mark = document.querySelector('.brand-mark');
              const back = desk.querySelector('.guest-bareact-back');
              const cta = desk.querySelector('.guest-bareact-cta');
              const rows = [...desk.querySelectorAll('.guest-bareact-row')];
              const rowLinks = desk.querySelectorAll('a:not(.guest-bareact-back):not(.guest-bareact-cta)');
              return {
                brandTag: brand.tagName,
                markFilter: getComputedStyle(mark).filter,
                deskDisplay: getComputedStyle(desk).display,
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                backHref: back.getAttribute('href'),
                kicker: desk.querySelector('.guest-bareact-kicker').textContent.trim(),
                title: desk.querySelector('.guest-bareact-title').textContent.trim(),
                meta: desk.querySelector('.guest-bareact-meta').textContent.trim(),
                ctaText: cta.textContent.trim(),
                ctaHref: cta.getAttribute('href'),
                ctaSheet: cta.hasAttribute('data-pg-sheet'),
                rowCount: rows.length,
                rowTitles: rows.map((el) => el.querySelector('.guest-bareact-row-title').textContent.trim()),
                rowTags: rows.map((el) => el.querySelector('.guest-bareact-row-tag').textContent.trim()),
                extraLinks: rowLinks.length,
                navLabels: [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                  (el) => el.textContent.replace(/\\s+/g, ' ').trim()
                ),
                browseActive: document.querySelector('.PrimaryTabs--top .nav-link.is-active').textContent.replace(/\\s+/g, ' ').trim(),
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
        page.locator("[data-guest-bareact-desktop] .guest-bareact-cta").click()
        page.wait_for_selector("[data-pg-add]", timeout=8000)
        dialog = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              return {
                kind: panel && panel.getAttribute('data-pg-kind'),
                title: panel && panel.querySelector('h1') && panel.querySelector('h1').textContent.trim(),
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
              const desk = document.querySelector('[data-guest-bareact-desktop]');
              const prod = document.querySelector('[data-bareact-phone]');
              return {
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                prodDisplay: prod ? getComputedStyle(prod).display : null,
                details: prod ? prod.querySelectorAll('details').length : 0,
              };
            }"""
        )
        browser.close()

    assert geo["brandTag"] == "SPAN"
    assert "invert" in geo["markFilter"]
    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["backHref"] == "/laws"
    assert geo["kicker"] == NDPS_GUEST_KICKER
    assert geo["title"] == NDPS_GUEST_TITLE
    assert geo["meta"] == NDPS_GUEST_META
    assert geo["ctaText"] == "Sign in to use Playground"
    assert geo["ctaHref"] == add_path("ndps")
    assert geo["ctaSheet"] is True
    assert geo["rowCount"] == 4
    assert geo["rowTags"] == [row.tag for row in NDPS_GUEST_ROWS]
    assert geo["rowTitles"] == [row.title for row in NDPS_GUEST_ROWS]
    assert geo["extraLinks"] == 0
    assert geo["navLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["browseActive"] == "Browse"
    assert dialog["kind"] == "guest"
    assert dialog["title"] == "Sign in to use Playground"
    assert still_on_ndps is True
    assert phone_geo["deskDisplay"] == "none"
    assert phone_geo["prodDisplay"] != "none"
    assert phone_geo["details"] == 8
    assert FIXTURE.is_file(), "guest/04-screen.jpg fixture missing"
    assert diff is not None
    assert diff["w"] == 1280
    assert diff["rms"] < 32
