"""Guest Laws index Screen 3 (desktop CTA map guest/03-screen).

Authorized: ChatGPT plan. M3 (Q3 / Q5 / F04): guest `/laws` is the one
data-driven catalogue every viewer sees at every width — chips from the
catalogue's visible subjects, card meta from the Act head's own label, a
visible labelled search field, and no per-card Playground CTA. The guest
fixture (web/guest_laws_index.py) and the second phone body are retired.
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
from constitution_memorizer.web.law_catalog import load_catalog

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
FIXTURE = Path(__file__).parent / "fixtures" / "guest_laws" / "03-screen.jpg"
ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"


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


def _index(html: str) -> str:
    # M3 (Q3): one Laws body for every viewer and width.
    assert html.count("data-laws-index") == 1
    return html.split("data-laws-index", 1)[1].split("</section>", 1)[0]


def _chip_labels(index: str) -> list[str]:
    return re.findall(
        r'<button type="button" class="laws-chip[^"]*"[^>]*>([^<]+)</button>',
        index,
    )


def _expected_chips() -> list[str]:
    catalog = load_catalog()
    labels = ["All"] + [s.label for s in catalog.visible_subjects]
    if catalog.repealed_laws:
        labels.append("Repealed")
    return labels


def _assert_guest_has_no_playground_cta(html: str) -> None:
    """M3 (F04): a guest card carries no badge, no button and no full CTA.

    The badge-only wrapper is still printed for the guest state (kind
    "guest") but is empty — nothing to read, nothing to press.
    """
    assert "LawStatusBadge" not in html
    assert "pg-btn" not in html
    assert "pg-lede" not in html
    assert "data-pg-sheet" not in html
    assert html.count('class="LawPlaygroundCta"') == 0
    wrappers = html.count("LawPlaygroundCta--badge")
    empty = re.findall(
        r'<div class="LawPlaygroundCta LawPlaygroundCta--badge"[^>]*data-pg-kind="guest"[^>]*>\s*</div>',
        html,
    )
    assert len(empty) == wrappers


def test_screen3_guest_laws_route_uses_screen2_header(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/laws").text
    header = _header(html)
    nav = _primary_nav(html)
    # M3 (Q3): the guest-only desktop body is gone — one catalogue, no
    # signed-in marker for a guest.
    assert html.count("data-laws-index") == 1
    assert "data-laws-body" in html
    assert "data-guest-laws-desktop" not in html
    assert "data-signed-in-laws-desktop" not in html
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
    css = STYLES.read_text(encoding="utf-8")
    # M3 (Q3): one desktop rule-set for guests and accounts alike.
    assert 'body.is-guest[data-mscreen="laws"]' not in css
    assert 'body.is-authed[data-mscreen="laws"]' not in css
    mark = css.split('body[data-mscreen="laws"] .brand-mark {', 1)[1].split("}", 1)[0]
    assert "invert(1)" in mark


def test_screen3_back_returns_to_browse(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    index = _index(client.get("/laws").text)
    assert 'class="laws-back-link" href="/browse"' in index
    assert index.count('class="laws-back-link"') == 1
    assert "mobile-back" not in index  # M3 (Q5): one back link for both widths
    browse = client.get("/browse", follow_redirects=False)
    assert browse.status_code == 200
    assert "Browse the Constitution" in browse.text


def test_screen3_copy_search_and_default_filter(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/laws").text
    index = _index(html)
    assert '<p class="laws-index-kicker">Browse</p>' in index
    assert '<h1 class="display laws-index-title">Laws</h1>' in index
    assert "Bare Acts and statutes. Open a law, then add it or its sections to your Playground." in index
    # M3 (Q5): the search field is always visible and labelled; the phone
    # toggle and the second input id are gone.
    assert '<div class="laws-search" data-laws-search>' in index
    assert '<label class="visually-hidden" for="laws-q">Search laws</label>' in index
    assert 'id="laws-q"' in index
    assert 'placeholder="Search laws"' in index
    assert "laws-q-guest" not in html
    assert "data-laws-search-toggle" not in html
    assert 'class="laws-index-head"' not in html
    # M3 (Q3): chips come from the catalogue's visible subjects.
    labels = _chip_labels(index)
    assert labels == _expected_chips()
    assert labels == [
        "All",
        "Criminal",
        "Constitutional",
        "Administrative",
        "Environmental",
        "Financial",
        "Health",
        "Repealed",
    ]
    assert "Commercial" not in labels
    assert 'data-laws-chip="" aria-pressed="true"' in index
    assert 'data-laws-chip="criminal" aria-pressed="false"' in index
    assert 'data-laws-chip="health" aria-pressed="false"' in index
    assert 'data-laws-status="repealed" aria-pressed="false"' in index
    chips = index.split("laws-chip-strip", 1)[1].split("laws-catalog", 1)[0]
    assert "<a " not in chips
    assert "href=" not in chips
    # M3 (F04): a guest card never carries a Playground CTA or badge.
    _assert_guest_has_no_playground_cta(html)


def test_screen3_cards_are_the_catalogue(tmp_path: Path) -> None:
    index = _index(_guest_client(tmp_path).get("/laws").text)
    catalog = load_catalog()
    ids = re.findall(r'class="laws-index-card"[^>]*data-law-id="([^"]+)"', index, re.S)
    # M3 (Q3): the guest fixture is gone — the cards are the catalogue, in
    # catalogue order, each linking to its own head.
    assert ids == [law.id for law in catalog.laws]
    for law in catalog.laws:
        card = index.split(f'data-law-id="{law.id}"', 1)[1].split("</a>", 1)[0]
        assert f'href="{law.href}"' in index
        assert f'<span class="laws-index-name">{law.title}</span>' in card
        assert f'<span class="laws-index-meta">{law.card_meta_label}</span>' in card
    # M3 (Q3): a full Act prints its head's own meta line; key-provisions
    # laws keep their seed scope_label.
    assert "The Narcotic Drugs and Psychotropic Substances Act, 1985" in index
    assert "8 Chapters · Sections 1–83 · Schedule" in index
    assert "6 Chapters · Sections 1–83" not in index  # the fixture's stale NDPS line
    assert "The Unlawful Activities (Prevention) Act, 1967" in index
    assert "7 Chapters · Sections 1–53 · Schedules" in index
    assert "The Bharatiya Nagarik Suraksha Sanhita, 2023" in index
    assert "39 Chapters · Sections 1–531 · Schedules" in index
    assert "The Bharatiya Nyaya Sanhita, 2023" in index
    assert "20 Chapters · Sections 1–358" in index
    assert "The Medical Termination of Pregnancy Act, 1971" in index
    assert "<span class=\"laws-index-meta\">Sections 1–8</span>" in index
    assert "CRIMINAL · FULL ACT" in index
    assert "FINANCIAL · FULL ACT" in index
    assert "HEALTH · FULL ACT" in index
    assert "CONSTITUTIONAL · KEY PROVISIONS" in index
    assert "COMMERCIAL" not in index
    assert "The Companies Act, 2013" not in index
    assert "The Bharatiya Sakshya Adhiniyam, 2023" not in index
    assert "The Prevention of Money-laundering Act, 2002" not in index
    assert "The Bharatiya Nyaya Sanhita, 2025" not in index
    repealed = index.split('data-law-id="pota"', 1)[1].split("</a>", 1)[0]
    assert 'data-status="repealed"' in index
    assert '<span class="laws-index-status">' in repealed


def test_screen3_law_cards_open_bare_act_heads(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    index = _index(client.get("/laws").text)
    heads = [law for law in load_catalog().laws if law.full_act_ref]
    assert heads
    for law in heads:
        assert f'href="{law.href}"' in index
        page = client.get(law.href, follow_redirects=False)
        assert page.status_code == 200, law.href
        assert f'data-act-head="{law.full_act_ref}"' in page.text, law.href


def test_screen3_one_body_serves_phone_and_other_screens_unchanged(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    html = client.get("/laws").text
    # M3 (Q3 / Q5): no second phone body, no phone head, no search toggle.
    assert html.count('class="panel laws"') == 1
    assert "data-laws-phone" not in html
    assert "data-laws-search-toggle" not in html
    assert 'class="laws-index-head"' not in html
    assert "mobile-back" not in html
    assert 'data-laws-chip="health"' in html
    assert "The Medical Termination of Pregnancy Act, 1971" in html
    assert "The Bharatiya Nyaya Sanhita, 2023" in html
    landing = client.get("/").text
    assert 'data-guest-landing="desktop"' in landing
    browse = client.get("/browse").text
    assert "Browse the Constitution" in browse
    assert 'class="browse-resource-grid"' in browse
    assert 'href="/laws"' in browse
    css = STYLES.read_text(encoding="utf-8")
    guest_grid = css.split(
        'body.is-guest[data-mscreen="browse"] .browse-resource-grid {', 1
    )[1].split("}", 1)[0]
    assert "calc(200% / 3)" in guest_grid
    mobile = MOBILE.read_text(encoding="utf-8")
    assert 'body[data-mscreen="laws"] .laws-index-card' in mobile
    assert ".laws-index-head" not in mobile
    assert "data-laws-search-toggle" not in mobile
    hero = mobile.split('body[data-mscreen="laws"] .laws-index-hero {', 1)[1].split("}", 1)[0]
    assert "display: block" in hero
    search = mobile.split('body[data-mscreen="laws"] .laws-search {', 1)[1].split("}", 1)[0]
    assert "display: flex" in search
    assert "height: 44px" in search
    back = mobile.split('body[data-mscreen="laws"] .laws-back-link {', 1)[1].split("}", 1)[0]
    assert "min-height: 44px" in back


def test_single_user_laws_index_is_unchanged(tmp_path: Path) -> None:
    html = TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    ).get("/laws").text
    assert html.count("data-laws-index") == 1
    assert "data-guest-laws-desktop" not in html
    assert "data-laws-phone" not in html
    assert 'data-laws-chip="health"' in html
    assert "The Bharatiya Nyaya Sanhita, 2025" not in html
    assert "guest_laws_index" not in LAWS.read_text(encoding="utf-8")


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
    catalog = load_catalog()

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
        # M3 (Q3 / Q5): one [data-laws-index] body; the search input is #laws-q.
        geo = page.evaluate(
            """() => {
              const bodies = document.querySelectorAll('[data-laws-index]');
              const desk = bodies[0];
              const brand = document.querySelector('.brand');
              const mark = document.querySelector('.brand-mark');
              const back = desk.querySelector('.laws-back-link');
              const search = desk.querySelector('#laws-q');
              const legacyHead = desk.querySelector('.laws-index-head, [data-laws-search-toggle], .mobile-back');
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
                bodies: bodies.length,
                brandTag: brand.tagName,
                markFilter: getComputedStyle(mark).filter,
                deskDisplay: getComputedStyle(desk).display,
                legacyHead: !!legacyHead,
                backHref: back.getAttribute('href'),
                backDisplay: getComputedStyle(back).display,
                heading: desk.querySelector('.laws-index-title').textContent.trim(),
                lede: desk.querySelector('.laws-index-lede').textContent.trim(),
                kicker: desk.querySelector('.laws-index-kicker').textContent.trim(),
                searchPlaceholder: search.getAttribute('placeholder'),
                searchHidden: desk.querySelector('[data-laws-search]').hidden,
                searchDisplay: getComputedStyle(desk.querySelector('[data-laws-search]')).display,
                chips,
                visibleIds: visible.map((el) => el.getAttribute('data-law-id')),
                firstTitle: visible[0] && visible[0].querySelector('.laws-index-name').textContent.trim(),
                ctaCount: desk.querySelectorAll('.LawStatusBadge, .pg-btn, .pg-lede, [data-pg-sheet], .LawPlaygroundCta:not(.LawPlaygroundCta--badge)').length,
                emptyWrappers: [...desk.querySelectorAll('.LawPlaygroundCta--badge')].every(
                  (el) => el.children.length === 0 && el.textContent.trim() === ''
                ),
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
        page.locator('[data-laws-index] .laws-chip[data-laws-chip="criminal"]').click()
        criminal = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-laws-index]');
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
        # M3 (Q3): "Commercial" is gone; Health is the catalogue's own chip.
        page.locator('[data-laws-index] .laws-chip[data-laws-chip="health"]').click()
        health = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-laws-index]');
              const visible = [...desk.querySelectorAll('[data-law-id]')].filter(
                (el) => !el.classList.contains('is-filtered-out')
              );
              return visible.map((el) => el.getAttribute('data-law-id'));
            }"""
        )
        page.locator('[data-laws-index] .laws-chip[data-laws-chip=""]').click()
        page.fill("#laws-q", "ndps")
        searched = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-laws-index]');
              const visible = [...desk.querySelectorAll('[data-law-id]')].filter(
                (el) => !el.classList.contains('is-filtered-out')
              );
              return visible.map((el) => el.getAttribute('data-law-id'));
            }"""
        )
        page.fill("#laws-q", "")
        page.locator('[data-laws-index] .laws-chip[data-laws-status="repealed"]').click()
        repealed = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-laws-index]');
              const visible = [...desk.querySelectorAll('[data-law-id]')].filter(
                (el) => !el.classList.contains('is-filtered-out')
              );
              return visible.map((el) => el.getAttribute('data-law-id'));
            }"""
        )
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"http://127.0.0.1:{port}/laws", wait_until="networkidle")
        phone = page.evaluate(
            """() => {
              const bodies = document.querySelectorAll('[data-laws-index]');
              const desk = bodies[0];
              const vis = (el) => el && getComputedStyle(el).display !== 'none';
              return {
                bodies: bodies.length,
                backShown: vis(desk.querySelector('.laws-back-link')),
                copyShown: vis(desk.querySelector('.laws-index-copy')),
                searchShown: vis(desk.querySelector('[data-laws-search]')),
                legacyHead: !!desk.querySelector('.laws-index-head, [data-laws-search-toggle], .mobile-back'),
                cols: getComputedStyle(desk.querySelector('.laws-catalog')).gridTemplateColumns.split(' ').length,
              };
            }"""
        )
        browser.close()

    assert geo["bodies"] == 1
    assert geo["brandTag"] == "SPAN"
    assert "invert" in geo["markFilter"]
    assert geo["deskDisplay"] != "none"
    assert geo["legacyHead"] is False
    assert geo["backHref"] == "/browse"
    assert geo["backDisplay"] != "none"
    assert geo["heading"] == "Laws"
    assert geo["kicker"] == "Browse"
    assert "Bare Acts and statutes" in geo["lede"]
    assert geo["searchPlaceholder"] == "Search laws"
    assert geo["searchHidden"] is False
    assert geo["searchDisplay"] != "none"
    assert [c["text"] for c in geo["chips"]] == _expected_chips()
    assert geo["chips"][0]["pressed"] == "true"
    assert geo["visibleIds"] == [law.id for law in catalog.current_laws]
    assert "pota" not in geo["visibleIds"]
    assert geo["firstTitle"] == "The Bharatiya Nyaya Sanhita, 2023"
    assert geo["ctaCount"] == 0  # M3 (F04): no badge, button or full CTA for a guest
    assert geo["emptyWrappers"] is True
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
    assert all("criminal" in sub.split() for sub in criminal["subjects"])
    assert "pota" not in criminal["ids"]
    assert health == ["mtp"]
    assert searched == ["ndps"]
    assert repealed == ["pota"]
    assert phone["bodies"] == 1
    assert phone["backShown"] is True
    assert phone["copyShown"] is True
    assert phone["searchShown"] is True
    assert phone["legacyHead"] is False
    assert phone["cols"] == 1
    assert FIXTURE.is_file(), "guest/03-screen.jpg fixture missing"
    assert diff is not None
    assert diff["w"] == 1280
    assert diff["rms"] < 32
