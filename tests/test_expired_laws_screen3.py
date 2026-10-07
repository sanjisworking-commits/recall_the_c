"""Expired cohort desktop Laws Screen 03 (CTA map expired/03-screen).

Authorized: ChatGPT. Authenticated multiuser GET /laws with a real expired
subscription whose paid period has ended. The catalogue stays fully
browseable. Per-law Playground badges come from playground_states after a
real roster/add seed, then expire. Header status comes from the live
paid-period-ended gate title. Guest, Free, Plus, halted, phone, Plus 01–11,
and Expired 01–02 stay unchanged.
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
from constitution_memorizer.entitlements.models import BLOCK_PAID_PERIOD_ENDED
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.urls import add_path
from constitution_memorizer.playground.view import gate_view
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.law_catalog import load_catalog

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "data" / "output" / "learning_units.json"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
APP = ROOT / "src/constitution_memorizer/web/app.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
MANAGE = ROOT / "src/constitution_memorizer/web/templates/subscription_manage.html"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_EXPIRED_STATUS = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
RETAINED = ("bns", "bnss", "ndps")
INVENTED = (
    "Your plan expired",
    "Resume subscription",
    "Premium",
    "Unlimited",
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


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("rtc_csrf") or ""
    return {"csrf_token": token} if token else {}


def _subscribe(
    client: TestClient,
    *,
    tier: str = "plus",
    status: str = "active",
    period_start: datetime = ACTIVE_START,
    period_end: datetime = ACTIVE_END,
) -> None:
    client.app.state.subscriptions.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        billing_period_start=period_start,
        billing_period_end=period_end,
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


def _expire(client: TestClient) -> None:
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None
    client.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        status="expired",
        billing_period_start=EXPIRED_START,
        billing_period_end=EXPIRED_END,
    )


def _seed_roster_then_expire(
    client: TestClient, law_ids: tuple[str, ...] = RETAINED
) -> None:
    _subscribe(client)
    for law_id in law_ids:
        added = _confirm_add(client, law_id)
        assert added.status_code in {200, 303}, (law_id, added.status_code)
        assert client.app.state.roster.is_law_active_this_period(USER, law_id)
    _expire(client)


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _desk(html: str) -> str:
    return html.split("data-signed-in-laws-desktop", 1)[1]


def _catalog_html(desk: str) -> str:
    return desk.split("data-laws-catalog", 1)[1].split("data-laws-empty", 1)[0]


def _cta_kind(desk: str, law_id: str) -> str | None:
    match = re.search(
        rf'<div class="LawPlaygroundCta"[^>]*data-law-id="{re.escape(law_id)}"[^>]*>',
        desk,
    )
    if match is None:
        return None
    kind = re.search(r'data-pg-kind="([^"]+)"', match.group(0))
    return kind.group(1) if kind else None


def test_expired_laws_keeps_catalogue_and_live_playground_state(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_roster_then_expire(client)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert snap.subscription_status == "expired"
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    html = client.get("/laws").text
    header = _header(html)
    desk = _desk(html)
    catalog = load_catalog()
    assert 'data-expired-laws="desktop"' in html
    assert 'data-plus-laws="desktop"' not in html
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
    catalog_html = _catalog_html(desk)
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
    assert LIVE_EXPIRED_STATUS in header
    assert "Free account" not in header
    assert "RecallC Plus" not in header
    assert "Sanjay" in header
    assert 'href="/browse"' in header
    assert "is-active" in header
    for phrase in INVENTED:
        assert phrase not in desk, phrase
    assert "PaymentStateBanner" not in html
    assert "+ Add to Playground" not in desk
    assert 'data-pg-kind="eligible_to_add"' not in desk
    for law_id in RETAINED:
        assert client.app.state.roster.is_law_active_this_period(USER, law_id)
        assert _cta_kind(desk, law_id) == "already_active"
        assert (
            f'data-law-id="{law_id}" data-pg-kind="already_active" data-membership="in_playground"'
            in desk
        )
    assert desk.count('data-status="in_playground"') == len(RETAINED)
    assert desk.count("Already in Playground") == len(RETAINED)
    assert _cta_kind(desk, "pss") == "resume"
    assert 'data-law-id="pss" data-pg-kind="already_active"' not in desk
    assert 'data-law-id="mtp" data-pg-kind="already_active"' not in desk
    assert "IN PLAYGROUND" not in LAWS.read_text(encoding="utf-8")
    browse = client.get("/browse")
    assert browse.status_code == 200
    bare = client.get("/laws/bns")
    assert bare.status_code == 200
    assert f'href="{bns.href}"' in desk


def test_free_plus_guest_halted_stay_separate_from_expired(tmp_path: Path) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest"))
    guest_html = guest.get("/laws").text
    assert 'data-expired-laws="desktop"' not in guest_html
    assert "data-guest-laws-desktop" in guest_html
    assert "data-signed-in-laws-desktop" not in guest_html
    assert "RecallC Plus" not in guest_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/laws").text
    assert 'data-expired-laws="desktop"' not in free_html
    assert 'data-plus-laws="desktop"' not in free_html
    assert "data-signed-in-laws-desktop" in free_html
    assert "Free account" in _header(free_html)
    assert LIVE_EXPIRED_STATUS not in _header(free_html)
    assert "The Bharatiya Nyaya Sanhita, 2023" in _desk(free_html)

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get("/laws").text
    assert 'data-plus-laws="desktop"' in plus_html
    assert 'data-expired-laws="desktop"' not in plus_html
    assert "RecallC Plus" in _header(plus_html)
    assert LIVE_EXPIRED_STATUS not in _header(plus_html)
    plus_desk = _desk(plus_html)
    assert "+ Add to Playground" in plus_desk
    assert 'data-pg-kind="already_active"' not in plus_desk

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    for law_id in RETAINED:
        added = _confirm_add(halted, law_id)
        assert added.status_code in {200, 303}, law_id
    stored = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )
    halted_html = halted.get("/laws").text
    assert 'data-expired-laws="desktop"' not in halted_html
    assert 'data-plus-laws="desktop"' not in halted_html
    assert LIVE_EXPIRED_STATUS not in _header(halted_html)
    halted_snap = halted.app.state.entitlement_service.resolve(USER)
    assert halted_snap.subscription_status == "halted"
    assert halted_snap.playground_block_reason != BLOCK_PAID_PERIOD_ENDED


def test_expired_laws_uses_shared_predicate_not_a_template_flag() -> None:
    laws = LAWS.read_text(encoding="utf-8")
    assert "expired_laws" in laws
    assert 'data-expired-laws="desktop"' in laws
    assert "plus_laws" in laws
    assert 'data-plus-laws="desktop"' in laws
    assert "data-signed-in-laws-desktop" in laws
    assert "data-guest-laws-desktop" in laws
    assert 'href="/browse"' in laws
    assert "playground_cta(pg_state)" in laws
    assert "IN PLAYGROUND" not in laws
    assert "Your Playground is paused" not in laws
    assert "Playground paused" not in laws
    assert LIVE_EXPIRED_STATUS not in laws
    assert "Your plan expired" not in laws
    base = BASE.read_text(encoding="utf-8")
    assert "expired_laws" in base
    assert "expired_browse" in base
    assert "expired_header_status" in base
    assert "RecallC Plus" in base
    assert "Free account" in base
    assert "Playground paused" not in base
    app = APP.read_text(encoding="utf-8")
    page = app.split("async def laws_page", 1)[1].split(
        "async def law_detail_page", 1
    )[0]
    assert "request_is_expired_subscriber" in page
    assert "request_is_active_plus" in page
    assert '"expired_laws": expired_laws' in page
    assert '"expired_header_status": expired_header_status' in page
    assert "gate_view" in page
    assert "def snapshot_is_expired_subscriber" not in page
    browse = app.split("async def browse_index", 1)[1].split(
        "async def browse_part", 1
    )[0]
    assert "request_is_expired_subscriber" in browse
    assert '"expired_browse": expired_browse' in browse
    deps = DEPS.read_text(encoding="utf-8")
    assert "def request_is_expired_subscriber" in deps
    assert "BLOCK_PAID_PERIOD_ENDED" in deps
    view = VIEW.read_text(encoding="utf-8")
    assert "BLOCK_PAID_PERIOD_ENDED" in view
    assert "KIND_ALREADY_ACTIVE" in view
    assert 'badge_label="Already in Playground"' in view


def test_plus_screens_and_expired_01_02_untouched() -> None:
    assert 'data-plus-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-expired-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-plus-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-expired-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-plus-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-plus-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-plus-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-plus-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-plus-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-plus-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-plus-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    landing = LANDING.read_text(encoding="utf-8")
    assert "data-expired-laws" not in landing
    assert "expired_laws" not in landing
    browse = BROWSE.read_text(encoding="utf-8")
    assert "data-expired-laws" not in browse
    assert "expired_laws" not in browse
    for path in (BARE, ADD, HOME, MANAGE, DASH, CAL, PROFILE, SETTINGS):
        text = path.read_text(encoding="utf-8")
        assert "data-expired-laws" not in text
        assert "expired_laws" not in text
        assert "data-expired-browse" not in text
        assert "data-expired-landing" not in text
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-expired-laws" not in mobile
    assert "def request_is_active_plus" in DEPS.read_text(encoding="utf-8")
    assert 'snapshot.tier == "plus"' in DEPS.read_text(encoding="utf-8")
    assert "def request_is_expired_subscriber" in DEPS.read_text(encoding="utf-8")


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


def test_expired_phone_laws_unchanged(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _seed_roster_then_expire(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
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
        page.goto(f"{origin}/laws", wait_until="networkidle")
        phone = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-signed-in-laws-desktop]');
              const expired = document.querySelector('[data-expired-laws="desktop"]');
              const back = desk && desk.querySelector('.laws-back-link');
              const copy = desk && desk.querySelector('.laws-index-copy');
              const head = desk && desk.querySelector('.laws-index-head');
              const catalog = desk && desk.querySelector('.laws-catalog');
              const vis = (el) => el && getComputedStyle(el).display !== 'none';
              return {
                expiredPresent: Boolean(expired),
                backShown: vis(back),
                copyShown: vis(copy),
                headShown: vis(head),
                cols: catalog
                  ? getComputedStyle(catalog).gridTemplateColumns.split(' ').length
                  : null,
              };
            }"""
        )
        browser.close()
    assert phone["expiredPresent"] is True
    assert phone["backShown"] is False
    assert phone["copyShown"] is False
    assert phone["headShown"] is True
    assert phone["cols"] == 1


def test_expired_laws_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _seed_roster_then_expire(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "expired_laws_screen03_1280.png"
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
              const desk = document.querySelector('[data-expired-laws="desktop"]');
              const signed = document.querySelector('[data-signed-in-laws-desktop]');
              const plus = document.querySelector('[data-plus-laws="desktop"]');
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
                (el) => !el.classList.contains('is-filtered-out') &&
                  el.classList.contains('laws-index-card')
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
              const badges = [...signed.querySelectorAll('.LawStatusBadge[data-status="in_playground"]')]
                .filter((el) => getComputedStyle(el).display !== 'none')
                .map((el) => {
                  const card = el.closest('[data-law-id]');
                  return {
                    lawId: card && card.getAttribute('data-law-id'),
                    text: el.textContent.replace(/\\s+/g, ' ').trim(),
                    shown: getComputedStyle(el).display !== 'none',
                  };
                });
              const addShown = [...signed.querySelectorAll('.LawPlaygroundCta .pg-btn')].some(
                (el) => getComputedStyle(el).display !== 'none' &&
                  /Add to Playground/.test(el.textContent)
              );
              return {
                present: Boolean(desk),
                plusPresent: Boolean(plus),
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
                invented: /Your plan expired|Resume subscription|Premium|Unlimited|Unlock all|Free plan|All 3 slots/.test(panelText),
                banner: !!document.querySelector('.PaymentStateBanner'),
                addShown,
                badges,
                bnsHref: signed && signed.querySelector('a[href="/laws/bns"]') &&
                  signed.querySelector('a[href="/laws/bns"]').getAttribute('href'),
                ndpsHref: signed && signed.querySelector('a[href="/laws/ndps"]') &&
                  signed.querySelector('a[href="/laws/ndps"]').getAttribute('href'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator('[data-expired-laws="desktop"] .laws-back-link').click()
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
        browser.close()

    assert geo["present"] is True
    assert geo["plusPresent"] is False
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
    assert geo["accountStatus"] == LIVE_EXPIRED_STATUS
    assert geo["invented"] is False
    assert geo["banner"] is False
    assert geo["addShown"] is False
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
    badge_ids = [b["lawId"] for b in geo["badges"]]
    assert set(badge_ids) == set(RETAINED)
    assert all("Already in Playground" in (b["text"] or "") or
               "IN PLAYGROUND" in (b["text"] or "").upper()
               for b in geo["badges"])
    assert "/browse" in browse_url
    assert "/laws/bns" in bns_url
    assert "/laws/ndps" in ndps_url
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_plus_laws_regression_1280(tmp_path: Path) -> None:
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
    shot_path = artifact_dir / "expired_laws_screen03_plus_regression_1280.png"
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
              const expired = document.querySelector('[data-expired-laws="desktop"]');
              const plus = document.querySelector('[data-plus-laws="desktop"]');
              const signed = document.querySelector('[data-signed-in-laws-desktop]');
              const badges = signed
                ? [...signed.querySelectorAll('.LawStatusBadge[data-status="in_playground"]')]
                : [];
              const catalog = signed && signed.querySelector('.laws-catalog');
              const visible = signed ? [...signed.querySelectorAll('.laws-index-card')].filter(
                (el) => !el.classList.contains('is-filtered-out')
              ) : [];
              const first = visible[0] && visible[0].getBoundingClientRect();
              const second = visible[1] && visible[1].getBoundingClientRect();
              return {
                expiredPresent: Boolean(expired),
                plusPresent: Boolean(plus),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                badgeCount: badges.length,
                heading: signed && signed.querySelector('.laws-index-copy .laws-index-title').textContent.trim(),
                cols: catalog && getComputedStyle(catalog).gridTemplateColumns.split(' ').length,
                twoCol: first && second && Math.abs(first.y - second.y) < 8 && second.x > first.x,
                bnsHref: signed && signed.querySelector('a[href="/laws/bns"]') &&
                  signed.querySelector('a[href="/laws/bns"]').getAttribute('href'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["expiredPresent"] is False
    assert geo["plusPresent"] is True
    assert geo["accountStatus"] == "RecallC Plus"
    assert geo["badgeCount"] == 0
    assert geo["heading"] == "Laws"
    assert geo["cols"] == 2
    assert geo["twoCol"] is True
    assert geo["bnsHref"] == "/laws/bns"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
