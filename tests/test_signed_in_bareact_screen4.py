"""Signed-in desktop NDPS Bare Act head (CTA map signedIn/04-screen).

Authorized: ChatGPT. Authenticated multiuser GET /laws/ndps keeps production
phone Bare Act (accordion, section links, Playground CTA). Desktop head is
reconciled to signedIn/04. Guest Screen 4, signed-in Landing, Browse, and
Laws index stay unchanged. Chapter and schedule rows have no handler.
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
from constitution_memorizer.playground.urls import add_path, home_path, sections_path
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.guest_bareact_head import (
    NDPS_GUEST_KICKER,
    NDPS_GUEST_META,
    NDPS_GUEST_ROWS,
    NDPS_GUEST_TITLE,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
USER = UUID("11111111-1111-4111-8111-111111111111")


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


def _desk(html: str) -> str:
    return html.split("data-signed-in-bareact-desktop", 1)[1].split(
        "data-bareact-phone", 1
    )[0]


def _phone(html: str) -> str:
    return html.split("data-bareact-phone", 1)[1]


def test_signed_in_non_subscriber_shows_subscribe_not_already_in_playground(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_stale_ndps_roster(client)
    html = client.get("/laws/ndps").text
    assert "data-signed-in-bareact-desktop" in html
    assert "data-guest-bareact-desktop" not in html
    desk = _desk(html)
    assert NDPS_GUEST_KICKER in desk
    assert f">{NDPS_GUEST_TITLE}<" in desk
    assert NDPS_GUEST_META in desk
    assert "Subscribe to use Playground" in desk
    assert desk.count("Subscribe to use Playground") == 1
    assert f'href="{add_path("ndps")}"' in desk
    assert "data-pg-sheet" in desk
    assert 'data-pg-kind="subscribe"' in desk
    assert "Already in Playground" not in desk
    assert ">Sections<" not in desk
    assert ">Continue<" not in desk
    assert "LawPlaygroundCta" not in desk
    assert "Sign in to use Playground" not in desk
    assert "+ Add to Playground" not in desk


def test_signed_in_subscriber_not_in_playground_keeps_add_flow(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    desk = _desk(client.get("/laws/ndps").text)
    assert 'data-pg-kind="eligible_to_add"' in desk
    assert "+ Add to Playground" in desk
    assert "LawPlaygroundCta" in desk
    assert "data-pg-sheet" in desk
    assert f'href="{add_path("ndps")}"' in desk
    assert "Already in Playground" not in desk
    assert ">Sections<" not in desk
    assert 'class="signed-bareact-continue"' not in desk
    assert "Subscribe to use Playground" not in desk


def test_signed_in_subscriber_in_playground_shows_cluster(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    desk = _desk(client.get("/laws/ndps").text)
    assert "Already in Playground" in desk
    assert 'data-pg-kind="already_active"' in desk
    assert ">Sections<" in desk
    assert f'href="{sections_path("ndps")}"' in desk
    assert f'class="signed-bareact-continue" href="{home_path()}"' in desk
    assert ">Continue<" in desk
    assert "Subscribe to use Playground" not in desk
    assert "+ Add to Playground" not in desk


def test_signed_in_bareact_back_goes_to_laws_index(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    desk = _desk(client.get("/laws/ndps").text)
    assert 'class="guest-bareact-back" href="/laws"' in desk
    laws = client.get("/laws", follow_redirects=False)
    assert laws.status_code == 200
    assert "data-signed-in-laws-desktop" in laws.text
    assert "data-guest-laws-desktop" not in laws.text


def test_signed_in_bareact_rows_are_inert(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    desk = _desk(client.get("/laws/ndps").text)
    for row in NDPS_GUEST_ROWS:
        assert row.tag in desk
        assert row.title in desk
        assert row.range_label in desk
    assert "CHAPTER IIA" not in desk
    assert 'href="/laws/ndps/section/' not in desk
    assert 'href="/laws/ndps/schedule/' not in desk
    assert "<details" not in desk
    assert 'role="button"' not in desk
    assert "About this act" not in desk
    assert "data-bareact-tabs" not in desk


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
    authed_mark = css.split(
        'body.is-authed[data-mscreen="bareact"]:has([data-signed-in-bareact-desktop]) .brand-mark {',
        1,
    )[1].split("}", 1)[0]
    assert "invert(1)" in authed_mark
    phone_hide = css.split("[data-signed-in-bareact-desktop] {", 1)[1].split("}", 1)[0]
    assert "display: none" in phone_hide
    prod_hide = css.split(
        'body.is-authed[data-mscreen="bareact"] [data-bareact-phone] {', 1
    )[1].split("}", 1)[0]
    assert "display: none" in prod_hide
    shell = css.split("/* R1 desktop shell", 1)[1]
    assert "position: absolute" not in shell
    assert "left: 50%" not in shell
    guest_mark = css.split(
        'body.is-guest[data-mscreen="bareact"]:has([data-guest-bareact-desktop]) .brand-mark {',
        1,
    )[1].split("}", 1)[0]
    assert "invert(1)" in guest_mark
    laws_title = css.split(
        'body.is-authed[data-mscreen="laws"] .laws-index-copy .laws-index-title {',
        1,
    )[1].split("}", 1)[0]
    assert "30px" in laws_title


def test_signed_in_bareact_does_not_touch_phone_or_accepted_screens(
    tmp_path: Path,
) -> None:
    mobile = MOBILE.read_text(encoding="utf-8")
    assert 'data-signed-in-bareact-desktop' not in mobile
    assert 'body[data-mscreen="bareact"] .bareact-chapter' in mobile or "bareact" in mobile
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-guest-landing="desktop"' in landing
    assert "Explore the Constitution" in landing
    browse = BROWSE.read_text(encoding="utf-8")
    assert "data-signed-in-browse-strip" in browse
    assert "Unlock all" in browse
    laws = LAWS.read_text(encoding="utf-8")
    assert "data-signed-in-laws-desktop" in laws
    assert "data-signed-in-bareact-desktop" not in laws

    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/laws/ndps").text
    phone = _phone(html)
    assert "<details" in phone
    assert 'href="/laws/ndps/section/' in phone
    assert "LawPlaygroundCta" in phone
    landing_html = client.get("/").text
    assert 'data-guest-landing="desktop"' in landing_html
    browse_html = client.get("/browse").text
    assert "Browse the Constitution" in browse_html
    assert "data-signed-in-browse-strip" in browse_html
    laws_html = client.get("/laws").text
    assert "data-signed-in-laws-desktop" in laws_html
    assert "data-signed-in-bareact-desktop" not in laws_html
    bns = client.get("/laws/bns").text
    assert "data-signed-in-bareact-desktop" not in bns
    assert "data-bareact-phone" not in bns
    assert "<details" in bns
    guest = TestClient(_mu_app(tmp_path / "guest"))
    guest_ndps = guest.get("/laws/ndps").text
    assert "data-guest-bareact-desktop" in guest_ndps
    assert "data-signed-in-bareact-desktop" not in guest_ndps
    assert "Sign in to use Playground" in guest_ndps


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


def test_signed_in_bareact_1280_non_subscriber_cta_and_inert_rows(
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
              const desk = document.querySelector('[data-signed-in-bareact-desktop]');
              const guest = document.querySelector('[data-guest-bareact-desktop]');
              const phone = document.querySelector('[data-bareact-phone]');
              const brand = document.querySelector('.brand');
              const mark = document.querySelector('.brand-mark');
              const back = desk.querySelector('.guest-bareact-back');
              const cta = desk.querySelector('.guest-bareact-cta');
              const rows = [...desk.querySelectorAll('.guest-bareact-row')];
              const rowLinks = desk.querySelectorAll(
                'a:not(.guest-bareact-back):not(.guest-bareact-cta):not(.signed-bareact-sections):not(.signed-bareact-continue)'
              );
              const details = desk.querySelectorAll('details');
              return {
                brandTag: brand.tagName,
                brandHref: brand.getAttribute('href'),
                markFilter: getComputedStyle(mark).filter,
                deskDisplay: getComputedStyle(desk).display,
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                guestPresent: !!guest,
                backHref: back.getAttribute('href'),
                kicker: desk.querySelector('.guest-bareact-kicker').textContent.trim(),
                title: desk.querySelector('.guest-bareact-title').textContent.trim(),
                meta: desk.querySelector('.guest-bareact-meta').textContent.trim(),
                ctaText: cta && cta.textContent.trim(),
                ctaHref: cta && cta.getAttribute('href'),
                ctaSheet: cta && cta.hasAttribute('data-pg-sheet'),
                ctaKind: cta && cta.getAttribute('data-pg-kind'),
                already: desk.textContent.includes('Already in Playground'),
                sections: !!desk.querySelector('.signed-bareact-sections'),
                continueHref: desk.querySelector('.signed-bareact-continue') &&
                  desk.querySelector('.signed-bareact-continue').getAttribute('href'),
                rowCount: rows.length,
                rowTitles: rows.map((el) =>
                  el.querySelector('.guest-bareact-row-title').textContent.trim()
                ),
                rowTags: rows.map((el) =>
                  el.querySelector('.guest-bareact-row-tag').textContent.trim()
                ),
                extraLinks: rowLinks.length,
                details: details.length,
                accountName: document.querySelector('.account-menu-btn-name').textContent.trim(),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                navLabels: [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                  (el) => el.textContent.replace(/\\s+/g, ' ').trim()
                ),
                browseActive: document.querySelector('.PrimaryTabs--top .nav-link.is-active')
                  .textContent.replace(/\\s+/g, ' ').trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator("[data-signed-in-bareact-desktop] .guest-bareact-cta").click()
        page.wait_for_selector("[data-pg-add]", timeout=8000)
        dialog = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              const titleEl = panel && panel.querySelector('#pg-add-title');
              return {
                kind: panel && panel.getAttribute('data-pg-kind'),
                title: titleEl && titleEl.textContent.trim(),
              };
            }"""
        )
        page.keyboard.press("Escape")
        still_on_ndps = page.url.rstrip("/").endswith("/laws/ndps")

        page.locator("[data-signed-in-bareact-desktop] .guest-bareact-back").click()
        page.wait_for_function("() => location.pathname === '/laws'", timeout=8000)
        laws_path = page.evaluate("() => location.pathname")
        laws_desk = page.evaluate(
            """() => !!document.querySelector('[data-signed-in-laws-desktop]')"""
        )

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        phone_geo = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-signed-in-bareact-desktop]');
              const prod = document.querySelector('[data-bareact-phone]');
              return {
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                prodDisplay: prod ? getComputedStyle(prod).display : null,
                details: prod ? prod.querySelectorAll('details').length : 0,
                sectionLinks: prod
                  ? prod.querySelectorAll('a[href*="/laws/ndps/section/"]').length
                  : 0,
              };
            }"""
        )
        browser.close()

    assert geo["brandTag"] == "A"
    assert geo["brandHref"] == "/dashboard"
    assert "invert" in geo["markFilter"]
    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["guestPresent"] is False
    assert geo["backHref"] == "/laws"
    assert geo["kicker"] == NDPS_GUEST_KICKER
    assert geo["title"] == NDPS_GUEST_TITLE
    assert geo["meta"] == NDPS_GUEST_META
    assert geo["ctaText"] == "Subscribe to use Playground"
    assert geo["ctaHref"] == add_path("ndps")
    assert geo["ctaSheet"] is True
    assert geo["ctaKind"] == "subscribe"
    assert geo["already"] is False
    assert geo["sections"] is False
    assert geo["continueHref"] is None
    assert geo["rowCount"] == 4
    assert geo["rowTags"] == [row.tag for row in NDPS_GUEST_ROWS]
    assert geo["rowTitles"] == [row.title for row in NDPS_GUEST_ROWS]
    assert geo["extraLinks"] == 0
    assert geo["details"] == 0
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
    assert dialog["kind"] == "subscribe"
    assert dialog["title"] == "Unlock Playground"
    assert still_on_ndps is True
    assert laws_path == "/laws"
    assert laws_desk is True
    assert phone_geo["deskDisplay"] == "none"
    assert phone_geo["prodDisplay"] != "none"
    assert phone_geo["details"] == 8
    assert phone_geo["sectionLinks"] > 0
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
