"""Plus cohort desktop Laws index Screen 03 (CTA map plus/03-screen).

Authorized: ChatGPT. Authenticated multiuser GET /laws with a real active
Plus subscription. Same accepted Laws index as Free signed-in Screen 03.
Header status uses RecallC Plus from EntitlementSnapshot via
request_is_active_plus. No Free strip on this page; no invented Plus copy,
routes, or law-card treatments. Screen 04 Bare Act heads stay unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
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
from constitution_memorizer.web.law_catalog import load_catalog

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "data" / "output" / "learning_units.json"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
APP = ROOT / "src/constitution_memorizer/web/app.py"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
USER = UUID("11111111-1111-4111-8111-111111111111")
INVENTED = (
    "Premium",
    "Unlimited",
    "renews",
    "Unlock all",
    "Free plan",
    "All 3 slots",
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


def _desk(html: str) -> str:
    return html.split("data-signed-in-laws-desktop", 1)[1]


def test_plus_laws_keeps_accepted_index_from_real_subscription(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    html = client.get("/laws").text
    header = _header(html)
    desk = _desk(html)
    catalog = load_catalog()
    assert 'data-plus-laws="desktop"' in html
    assert "data-signed-in-laws-desktop" in html
    assert "data-guest-laws-desktop" not in html
    assert 'class="laws-back-link" href="/browse"' in desk
    assert ">Laws<" in desk
    assert (
        "Bare Acts and statutes. Open a law, then add it or its sections to your Playground."
        in desk
    )
    assert 'placeholder="Search laws"' in desk
    assert 'data-laws-chip="" aria-pressed="true"' in desk
    catalog_html = desk.split("data-laws-catalog", 1)[1].split("data-laws-empty", 1)[0]
    rendered_ids = re.findall(
        r'class="laws-index-card"[^>]*data-law-id="([^"]+)"',
        catalog_html,
        re.S,
    )
    assert rendered_ids == [law.id for law in catalog.laws]
    assert rendered_ids[0] == "bns"
    assert "The Bharatiya Nyaya Sanhita, 2023" in desk
    bns = next(law for law in catalog.laws if law.id == "bns")
    ndps = next(law for law in catalog.laws if law.id == "ndps")
    assert f'href="{bns.href}"' in desk
    assert f'href="{ndps.href}"' in desk
    assert "RecallC Plus" in header
    assert "Free account" not in header
    for phrase in INVENTED:
        assert phrase not in desk, phrase
    browse = client.get("/browse")
    assert browse.status_code == 200
    assert "Browse the Constitution" in browse.text
    playground = client.get("/playground")
    assert "data-signed-in-pg-gate" not in playground.text
    assert "Free account" in _header(playground.text)
    bare = client.get("/laws/bns")
    assert bare.status_code == 200
    assert "Free account" in _header(bare.text)
    assert "RecallC Plus" not in _header(bare.text)


def test_free_signed_in_laws_is_not_plus(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/laws").text
    assert 'data-plus-laws="desktop"' not in html
    assert "data-signed-in-laws-desktop" in html
    header = _header(html)
    assert "Free account" in header
    assert "RecallC Plus" not in header
    desk = _desk(html)
    assert 'class="laws-back-link" href="/browse"' in desk
    assert "The Bharatiya Nyaya Sanhita, 2023" in desk


def test_guest_laws_is_unchanged(tmp_path: Path) -> None:
    html = TestClient(_mu_app(tmp_path)).get("/laws").text
    assert 'data-plus-laws="desktop"' not in html
    assert "data-guest-laws-desktop" in html
    assert "RecallC Plus" not in html
    assert "data-signed-in-laws-desktop" not in html


def test_halted_expired_and_pro_are_not_plus_screen_03(tmp_path: Path) -> None:
    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/laws").text
    assert 'data-plus-laws="desktop"' not in halted_html
    assert "Free account" in _header(halted_html)

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(expired, status="expired")
    expired_html = expired.get("/laws").text
    assert 'data-plus-laws="desktop"' not in expired_html

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/laws").text
    assert 'data-plus-laws="desktop"' not in pro_html
    assert "Free account" in _header(pro_html)


def test_plus_laws_marker_uses_shared_predicate() -> None:
    laws = LAWS.read_text(encoding="utf-8")
    assert "plus_laws" in laws
    assert 'data-plus-laws="desktop"' in laws
    assert "data-signed-in-laws-desktop" in laws
    assert 'href="/browse"' in laws
    base = BASE.read_text(encoding="utf-8")
    assert "plus_laws" in base
    assert "RecallC Plus" in base
    deps = DEPS.read_text(encoding="utf-8")
    assert "def request_is_active_plus" in deps
    assert 'snapshot.tier == "plus"' in deps
    app_src = APP.read_text(encoding="utf-8")
    assert "request_is_active_plus" in app_src
    assert 'and snapshot.tier == "plus"' not in app_src
    for phrase in ("Premium", "Unlimited", "renews"):
        assert phrase not in laws


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


def test_plus_laws_1280(tmp_path: Path) -> None:
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
    shot_path = artifact_dir / "plus_laws_screen03_1280.png"
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
              const desk = document.querySelector('[data-plus-laws="desktop"]');
              const signed = document.querySelector('[data-signed-in-laws-desktop]');
              const guest = document.querySelector('[data-guest-laws-desktop]');
              const brand = document.querySelector('.brand');
              const mark = document.querySelector('.brand-mark');
              const header = document.querySelector('.site-header');
              const back = signed && signed.querySelector('.laws-back-link');
              const phoneHead = signed && signed.querySelector('.laws-index-head');
              const search = signed && signed.querySelector('#laws-q');
              const searchWrap = signed && signed.querySelector('[data-laws-search]');
              const chips = signed ? [...signed.querySelectorAll('.laws-chip')].map((el) => ({
                text: el.textContent.trim(),
                pressed: el.getAttribute('aria-pressed'),
                tag: el.tagName,
                href: el.getAttribute('href'),
              })) : [];
              const visible = signed ? [...signed.querySelectorAll('[data-law-id]')].filter(
                (el) => !el.classList.contains('is-filtered-out')
              ) : [];
              const catalog = signed && signed.querySelector('.laws-catalog');
              const cs = catalog && getComputedStyle(catalog);
              const first = visible[0] && visible[0].getBoundingClientRect();
              const second = visible[1] && visible[1].getBoundingClientRect();
              const heading = signed && signed.querySelector('.laws-index-copy .laws-index-title');
              const searchBox = searchWrap && searchWrap.getBoundingClientRect();
              const copyBox = signed && signed.querySelector('.laws-index-copy').getBoundingClientRect();
              const fallback = document.querySelector('.account-avatar-fallback');
              const fr = fallback.getBoundingClientRect();
              const hr = header.getBoundingClientRect();
              const chipStrip = signed && signed.querySelector('.laws-chip-strip');
              const panelText = signed ? signed.innerText : '';
              return {
                present: Boolean(desk),
                deskPresent: !!signed,
                guestPresent: !!guest,
                brandHref: brand.getAttribute('href'),
                markFilter: getComputedStyle(mark).filter,
                headerH: hr.height,
                backHref: back && back.getAttribute('href'),
                backDisplay: back && getComputedStyle(back).display,
                phoneHeadDisplay: phoneHead && getComputedStyle(phoneHead).display,
                heading: heading && heading.textContent.trim(),
                headingSize: heading && getComputedStyle(heading).fontSize,
                kicker: signed && signed.querySelector('.laws-index-kicker').textContent.trim(),
                lede: signed && signed.querySelector('.laws-index-lede').textContent.trim(),
                searchPlaceholder: search && search.getAttribute('placeholder'),
                searchDisplay: searchWrap && getComputedStyle(searchWrap).display,
                searchX: searchBox && searchBox.x,
                copyX: copyBox && copyBox.x,
                chips,
                visibleIds: visible.map((el) => el.getAttribute('data-law-id')),
                firstTitle: visible[0] && (visible[0].querySelector('.laws-index-name') || {}).textContent,
                cols: cs && cs.gridTemplateColumns.split(' ').length,
                twoCol: first && second && Math.abs(first.y - second.y) < 8 && second.x > first.x,
                catalogY: catalog && catalog.getBoundingClientRect().y,
                chipY: chipStrip && chipStrip.getBoundingClientRect().y,
                headingY: heading && heading.getBoundingClientRect().y,
                accountName: document.querySelector('.account-menu-btn-name').textContent.trim(),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                fallbackW: fr.width,
                fallbackH: fr.height,
                navLabels: [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                  (el) => el.textContent.replace(/\\s+/g, ' ').trim()
                ),
                browseActive: document.querySelector('.PrimaryTabs--top .nav-link.is-active').textContent.replace(/\\s+/g, ' ').trim(),
                plusCopy: /Premium|Unlimited|Free plan|Unlock all|All 3 slots/.test(panelText),
                bnsHref: signed && signed.querySelector('a[href="/laws/bns"]') &&
                  signed.querySelector('a[href="/laws/bns"]').getAttribute('href'),
                ndpsHref: signed && signed.querySelector('a[href="/laws/ndps"]') &&
                  signed.querySelector('a[href="/laws/ndps"]').getAttribute('href'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator('[data-plus-laws="desktop"] .laws-back-link').click()
        page.wait_for_url("**/browse**", timeout=8000)
        browse_url = page.url
        page.goto(f"{origin}/laws", wait_until="networkidle")
        page.locator('a[href="/laws/bns"]').first.click()
        page.wait_for_url("**/laws/bns**", timeout=8000)
        bns_url = page.url
        page.goto(f"{origin}/laws", wait_until="networkidle")
        page.locator('a[href="/laws/ndps"]').first.click()
        page.wait_for_url("**/laws/ndps**", timeout=8000)
        ndps_url = page.url

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/laws", wait_until="networkidle")
        phone = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-signed-in-laws-desktop]');
              const plus = document.querySelector('[data-plus-laws="desktop"]');
              const back = desk.querySelector('.laws-back-link');
              const copy = desk.querySelector('.laws-index-copy');
              const head = desk.querySelector('.laws-index-head');
              const catalog = desk.querySelector('.laws-catalog');
              const vis = (el) => el && getComputedStyle(el).display !== 'none';
              return {
                plusPresent: Boolean(plus),
                backShown: vis(back),
                copyShown: vis(copy),
                headShown: vis(head),
                cols: getComputedStyle(catalog).gridTemplateColumns.split(' ').length,
              };
            }"""
        )
        browser.close()

    assert geo["present"] is True
    assert geo["deskPresent"] is True
    assert geo["guestPresent"] is False
    assert geo["brandHref"] == "/dashboard"
    assert "invert" in geo["markFilter"]
    assert geo["headerH"] == pytest.approx(60, abs=2)
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
    assert geo["chips"][0]["pressed"] == "true"
    assert "Commercial" not in [c["text"] for c in geo["chips"]]
    assert "Health" in [c["text"] for c in geo["chips"]]
    assert all(c["tag"] == "BUTTON" and c["href"] is None for c in geo["chips"])
    assert geo["visibleIds"][0] == "bns"
    assert "The Bharatiya Nyaya Sanhita, 2023" in (geo["firstTitle"] or "")
    assert "bns" in geo["visibleIds"]
    assert "ndps" in geo["visibleIds"]
    assert geo["cols"] == 2
    assert geo["twoCol"] is True
    assert geo["catalogY"] > geo["chipY"] > geo["headingY"]
    assert (geo["catalogY"] - geo["chipY"]) < 80
    assert geo["accountName"] == "Sanjay"
    assert geo["accountStatus"] == "RecallC Plus"
    assert geo["plusCopy"] is False
    assert geo["navLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["browseActive"] == "Browse"
    assert geo["bnsHref"] == "/laws/bns"
    assert geo["ndpsHref"] == "/laws/ndps"
    assert geo["fallbackW"] == pytest.approx(36, abs=1)
    assert geo["fallbackH"] == pytest.approx(36, abs=1)
    assert "/browse" in browse_url
    assert "/laws/bns" in bns_url
    assert "/laws/ndps" in ndps_url
    assert phone["plusPresent"] is True
    assert phone["backShown"] is False
    assert phone["copyShown"] is False
    assert phone["headShown"] is True
    assert phone["cols"] == 1
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
