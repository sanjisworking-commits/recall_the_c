"""Guest Laws index Screen 3 (desktop CTA map guest/03-screen).

Authorized: ChatGPT plan. Guest `/laws` desktop only. Phone /laws catalogue,
Landing, Browse, and Bare Act readers stay unchanged.
"""

from __future__ import annotations

import re
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
from constitution_memorizer.web.guest_laws_index import (
    EXISTING_LAW_HEADS,
    GUEST_LAWS_CARDS,
    GUEST_LAWS_CHIPS,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
FIXTURE = Path(__file__).parent / "fixtures" / "guest_laws" / "03-screen.jpg"
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
    return html.split("data-guest-laws-desktop", 1)[1].split("data-laws-phone", 1)[0]


def _phone_index(html: str) -> str:
    return html.split("data-laws-phone", 1)[1]


def test_screen3_guest_laws_route_uses_screen2_header(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/laws").text
    header = _header(html)
    nav = _primary_nav(html)
    assert 'data-guest-laws-desktop' in html
    assert "<span class=\"brand\"" in header
    assert 'class="brand" href=' not in header
    assert 'src="/static/main_logo.png"' in header
    assert "Recall the C" in header
    assert 'data-guest-account-menu' in header
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
        'body.is-guest[data-mscreen="laws"] .brand-mark {', 1
    )[1].split("}", 1)[0]
    assert "invert(1)" in guest_mark


def test_screen3_back_returns_to_browse(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    desk = _guest_desk(client.get("/laws").text)
    assert 'class="laws-back-link" href="/browse"' in desk
    browse = client.get("/browse", follow_redirects=False)
    assert browse.status_code == 200
    assert "Browse the Constitution" in browse.text


def test_screen3_copy_search_and_default_filter(tmp_path: Path) -> None:
    desk = _guest_desk(_guest_client(tmp_path).get("/laws").text)
    assert ">Laws<" in desk
    assert "Bare Acts and statutes. Open a law, then add it or its sections to your Playground." in desk
    assert 'placeholder="Search laws"' in desk
    assert "data-laws-search-toggle" not in desk
    labels = re.findall(
        r'<button type="button" class="laws-chip[^"]*"[^>]*>([^<]+)</button>',
        desk,
    )
    assert labels == [
        "All",
        "Criminal",
        "Commercial",
        "Financial",
        "Constitutional",
        "Administrative",
        "Environmental",
        "Repealed",
    ]
    assert 'data-laws-chip="" aria-pressed="true"' in desk
    assert 'data-laws-chip="criminal" aria-pressed="false"' in desk
    assert 'data-laws-status="repealed" aria-pressed="false"' in desk
    assert "LawPlaygroundCta" not in desk
    assert "Health" not in desk


def test_screen3_visible_cards_match_the_prototype(tmp_path: Path) -> None:
    desk = _guest_desk(_guest_client(tmp_path).get("/laws").text)
    ids = []
    for chunk in desk.split("data-law-id=\"")[1:]:
        ids.append(chunk.split("\"", 1)[0])
    assert ids == [law.id for law in GUEST_LAWS_CARDS]
    assert "The Bharatiya Nyaya Sanhita, 2025" in desk
    assert "20 Chapters · Sections 1–358" in desk
    assert "The Bharatiya Nagarik Suraksha Sanhita, 2023" in desk
    assert "The Narcotic Drugs and Psychotropic Substances Act, 1985" in desk
    assert "6 Chapters · Sections 1–83 · Schedule" in desk
    assert "The Unlawful Activities (Prevention) Act, 1967" in desk
    assert "The Bharatiya Sakshya Adhiniyam, 2023" in desk
    assert "12 Chapters · Sections 1–170" in desk
    assert "The Prevention of Money-laundering Act, 2002" in desk
    assert "The Payment and Settlement Systems Act, 2007" in desk
    assert "The Companies Act, 2013" in desk
    assert "29 Chapters · Sections 1–470" in desk
    assert "CRIMINAL · FULL ACT" in desk
    assert "FINANCIAL · FULL ACT" in desk
    assert "COMMERCIAL · FULL ACT" in desk
    assert "The Bharatiya Nyaya Sanhita, 2023" not in desk
    assert "8 Chapters · Sections 1–83<" not in desk


def test_screen3_existing_law_cards_open_bare_act_heads(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    desk = _guest_desk(client.get("/laws").text)
    for law in GUEST_LAWS_CARDS:
        if law.href not in EXISTING_LAW_HEADS:
            continue
        assert f'href="{law.href}"' in desk
        page = client.get(law.href, follow_redirects=False)
        assert page.status_code == 200, law.href
        assert "bareact" in page.text or "data-mscreen" in page.text


def test_screen3_does_not_change_phone_or_other_screens(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    html = client.get("/laws").text
    phone = _phone_index(html)
    assert 'data-laws-search-toggle' in phone
    assert 'data-laws-chip="health"' in phone
    assert "The Medical Termination of Pregnancy Act, 1971" in phone
    assert "The Bharatiya Nyaya Sanhita, 2023" in phone
    landing = client.get("/").text
    assert 'data-guest-landing="desktop"' in landing
    browse = client.get("/browse").text
    assert "Browse the Constitution" in browse
    assert 'class="browse-resource-grid"' in browse
    assert 'href="/laws"' in browse
    css = (ROOT / "src/constitution_memorizer/web/static/styles.css").read_text(
        encoding="utf-8"
    )
    guest_grid = css.split(
        'body.is-guest[data-mscreen="browse"] .browse-resource-grid {', 1
    )[1].split("}", 1)[0]
    assert "calc(200% / 3)" in guest_grid
    mobile = (ROOT / "src/constitution_memorizer/web/static/mobile.css").read_text(
        encoding="utf-8"
    )
    assert 'body[data-mscreen="laws"] .laws-index-card' in mobile


def test_single_user_laws_index_is_unchanged(tmp_path: Path) -> None:
    html = TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    ).get("/laws").text
    assert "data-guest-laws-desktop" not in html
    assert "data-laws-phone" not in html
    assert 'data-laws-chip="health"' in html
    assert "The Bharatiya Nyaya Sanhita, 2025" not in html


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


def test_screen3_1280_filters_search_and_matches_prototype(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "guest_laws_screen3_1280.png"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        page = browser.new_page(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )
        page.goto(f"http://127.0.0.1:{port}/laws", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-guest-laws-desktop]');
              const phone = document.querySelector('[data-laws-phone]');
              const brand = document.querySelector('.brand');
              const mark = document.querySelector('.brand-mark');
              const back = desk.querySelector('.laws-back-link');
              const search = desk.querySelector('#laws-q-guest');
              const chips = [...desk.querySelectorAll('.laws-chip')].map((el) => ({
                text: el.textContent.trim(),
                pressed: el.getAttribute('aria-pressed'),
                subject: el.getAttribute('data-laws-chip'),
                status: el.getAttribute('data-laws-status'),
              }));
              const visible = [...desk.querySelectorAll('[data-law-id]')].filter(
                (el) => !el.classList.contains('is-filtered-out')
              );
              const catalog = desk.querySelector('.laws-catalog');
              const cs = getComputedStyle(catalog);
              const first = visible[0] && visible[0].getBoundingClientRect();
              const second = visible[1] && visible[1].getBoundingClientRect();
              return {
                brandTag: brand.tagName,
                markFilter: getComputedStyle(mark).filter,
                deskDisplay: getComputedStyle(desk).display,
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                backHref: back.getAttribute('href'),
                heading: desk.querySelector('.laws-index-title').textContent.trim(),
                lede: desk.querySelector('.laws-index-lede').textContent.trim(),
                kicker: desk.querySelector('.laws-index-kicker').textContent.trim(),
                searchPlaceholder: search.getAttribute('placeholder'),
                searchHidden: desk.querySelector('[data-laws-search]').hidden,
                chips,
                visibleIds: visible.map((el) => el.getAttribute('data-law-id')),
                firstTitle: visible[0] && visible[0].querySelector('.laws-index-name').textContent.trim(),
                cols: cs.gridTemplateColumns.split(' ').length,
                twoCol: first && second && Math.abs(first.y - second.y) < 4 && second.x > first.x,
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
        page.locator('[data-guest-laws-desktop] .laws-chip[data-laws-chip="criminal"]').click()
        criminal = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-guest-laws-desktop]');
              const visible = [...desk.querySelectorAll('[data-law-id]')].filter(
                (el) => !el.classList.contains('is-filtered-out')
              );
              return {
                ids: visible.map((el) => el.getAttribute('data-law-id')),
                subjects: visible.map((el) => el.getAttribute('data-subjects')),
                pressed: desk.querySelector('[data-laws-chip="criminal"]').getAttribute('aria-pressed'),
                all: desk.querySelector('[data-laws-chip=""]').getAttribute('aria-pressed'),
              };
            }"""
        )
        page.locator('[data-guest-laws-desktop] .laws-chip[data-laws-chip="commercial"]').click()
        commercial = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-guest-laws-desktop]');
              const visible = [...desk.querySelectorAll('[data-law-id]')].filter(
                (el) => !el.classList.contains('is-filtered-out')
              );
              return visible.map((el) => el.getAttribute('data-law-id'));
            }"""
        )
        page.locator('[data-guest-laws-desktop] .laws-chip[data-laws-chip=""]').click()
        page.fill("#laws-q-guest", "ndps")
        searched = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-guest-laws-desktop]');
              const visible = [...desk.querySelectorAll('[data-law-id]')].filter(
                (el) => !el.classList.contains('is-filtered-out')
              );
              return visible.map((el) => el.getAttribute('data-law-id'));
            }"""
        )
        page.fill("#laws-q-guest", "")
        page.locator('[data-guest-laws-desktop] .laws-chip[data-laws-status="repealed"]').click()
        repealed = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-guest-laws-desktop]');
              const visible = [...desk.querySelectorAll('[data-law-id]')].filter(
                (el) => !el.classList.contains('is-filtered-out')
              );
              return visible.map((el) => el.getAttribute('data-law-id'));
            }"""
        )
        browser.close()

    assert geo["brandTag"] == "SPAN"
    assert "invert" in geo["markFilter"]
    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["backHref"] == "/browse"
    assert geo["heading"] == "Laws"
    assert geo["kicker"] == "Browse"
    assert "Bare Acts and statutes" in geo["lede"]
    assert geo["searchPlaceholder"] == "Search laws"
    assert geo["searchHidden"] is False
    assert [c["text"] for c in geo["chips"]] == [chip.label for chip in GUEST_LAWS_CHIPS]
    assert geo["chips"][0]["pressed"] == "true"
    assert geo["visibleIds"][:8] == [
        "bns",
        "bnss",
        "ndps",
        "uapa",
        "bsa",
        "pmla",
        "pss",
        "ca",
    ]
    assert "pota" not in geo["visibleIds"]
    assert geo["firstTitle"] == "The Bharatiya Nyaya Sanhita, 2025"
    assert geo["cols"] == 2
    assert geo["twoCol"] is True
    assert geo["navLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["browseActive"] == "Browse"
    assert criminal["pressed"] == "true"
    assert criminal["all"] == "false"
    assert criminal["ids"]
    assert all(sub == "criminal" for sub in criminal["subjects"])
    assert "pota" not in criminal["ids"]
    assert commercial == ["ca", "ica", "arb", "tpa"]
    assert searched == ["ndps"]
    assert repealed == ["pota"]
    assert FIXTURE.is_file(), "guest/03-screen.jpg fixture missing"
    assert diff is not None
    assert diff["w"] == 1280
    assert diff["rms"] < 32
