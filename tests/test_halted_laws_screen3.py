"""Halted cohort desktop Laws Screen 03 (CTA map halted/03-screen).

Authorized: ChatGPT. Authenticated multiuser GET /laws after a real Plus
subscription is halted. Catalogue, filters, search, and live IN PLAYGROUND
tags stay. Header status comes from gate_view(BLOCK_PAYMENT_HALTED).title
even when the paid period has elapsed. No Playground /learn hrefs.
Guest, Free, Plus, Expired, paused, pending, Pro/Max, phone, Plus 01–11,
Expired 01–11, and Halted 01–02 stay unchanged. No new route.
"""

from __future__ import annotations

import re
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
from constitution_memorizer.entitlements.models import (
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
)
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
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
MANAGE = ROOT / "src/constitution_memorizer/web/templates/subscription_manage.html"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_HALTED_STATUS = gate_view(reason=BLOCK_PAYMENT_HALTED).title
LIVE_EXPIRED_STATUS = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
RETAINED = ("bns", "bnss", "ndps")
INVENTED = (
    "Your subscription expired",
    "Resume subscription",
    "Your payment failed",
    "Fix your payment",
    "Subscription halted",
    "Playground unavailable",
    "Free plan",
    "Unlock all",
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
    status: str = "halted",
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


def _seed_roster_then_halt(
    client: TestClient, law_ids: tuple[str, ...] = RETAINED
) -> None:
    _subscribe(client, status="active")
    for law_id in law_ids:
        added = _confirm_add(client, law_id)
        assert added.status_code in {200, 303}, (law_id, added.status_code)
        assert client.app.state.roster.is_law_active_this_period(USER, law_id)
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None
    client.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )


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


def _facts(client: TestClient) -> dict:
    snap = client.app.state.entitlement_service.resolve(USER)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    cap = roster.peek_capacity(USER, snap)
    eng = client.app.state.engine.for_user(USER)
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    history = tuple(
        sorted(
            (row.id, row.status, row.tier, row.is_current)
            for row in client.app.state.subscriptions.list_subscription_history(USER)
        )
    )
    service = getattr(client.app.state, "device_service", None)
    if service is None:
        devices = ()
    else:
        devices = tuple(
            sorted((d.id, d.revoked_at, d.device_key_hash) for d in service.list_devices(USER))
        )
    return {
        "active": tuple(sorted(i.law_id for i in roster.active_roster_items(USER))),
        "removed": tuple(sorted(i.law_id for i in roster.removed_roster_items(USER))),
        "used": cap.used,
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        ),
        "selection": tuple(
            sorted(s.source_locator for s in overlay.list_selection(USER, "ndps"))
        ),
        "progress": tuple(
            sorted(
                (p.source_locator, p.status, p.times_completed, p.next_revision)
                for p in overlay.list_progress(USER, "ndps")
            )
        ),
        "constitution": tuple(
            sorted(
                (
                    row.learning_unit_id,
                    row.status,
                    row.times_completed,
                    str(row.next_revision),
                    row.interval_days,
                )
                for row in eng.repo.list_all_progress(USER)
            )
        ),
        "claimed": tuple(sorted(eng.claimed_articles())),
        "subscription": None
        if stored is None
        else (
            stored.id,
            stored.status,
            stored.tier,
            stored.is_current,
            stored.billing_period_end,
        ),
        "history": history,
        "devices": devices,
        "entitlement": (
            snap.subscription_status,
            snap.playground_block_reason,
            snap.can_open_playground,
        ),
    }


def test_halted_open_period_laws_keeps_catalogue_and_live_tags(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_roster_then_halt(client)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.is_authenticated is True
    assert snap.tier == "plus"
    assert snap.subscription_status == "halted"
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    assert snap.playground_block_reason == BLOCK_PAYMENT_HALTED
    assert LIVE_HALTED_STATUS == "Payment retries have stopped"

    page = client.get("/laws")
    assert page.status_code == 200
    html = page.text
    header = _header(html)
    desk = _desk(html)
    catalog = load_catalog()
    assert 'data-halted-laws="desktop"' in html
    assert 'data-plus-laws="desktop"' not in html
    assert 'data-expired-laws="desktop"' not in html
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
    assert LIVE_HALTED_STATUS in header
    assert LIVE_EXPIRED_STATUS not in header
    assert "Free account" not in header
    assert "RecallC Plus" not in header
    assert "Sanjay" in header
    assert 'href="/browse"' in header
    assert "is-active" in header
    assert not re.search(r"/playground/laws/[^\"']+/learn", desk)
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
    for phrase in INVENTED:
        assert phrase not in desk, phrase


def test_halted_elapsed_period_stays_halted_on_laws(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(
        client,
        period_start=EXPIRED_START,
        period_end=EXPIRED_END,
    )
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.subscription_status == "halted"
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    html = client.get("/laws").text
    header = _header(html)
    assert 'data-halted-laws="desktop"' in html
    assert 'data-expired-laws="desktop"' not in html
    assert 'data-plus-laws="desktop"' not in html
    assert LIVE_HALTED_STATUS in header
    assert LIVE_EXPIRED_STATUS not in header
    assert "Free account" not in header


def test_guest_free_plus_expired_paused_pending_pro_max_are_not_halted_laws(
    tmp_path: Path,
) -> None:
    guest_html = TestClient(_mu_app(tmp_path / "guest")).get("/laws").text
    assert 'data-halted-laws="desktop"' not in guest_html
    assert "data-guest-laws-desktop" in guest_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/laws").text
    assert 'data-halted-laws="desktop"' not in free_html
    assert "Free account" in _header(free_html)

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus, status="active")
    plus_html = plus.get("/laws").text
    assert 'data-plus-laws="desktop"' in plus_html
    assert 'data-halted-laws="desktop"' not in plus_html
    assert "RecallC Plus" in _header(plus_html)
    assert LIVE_HALTED_STATUS not in _header(plus_html)

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(
        expired,
        status="expired",
        period_start=EXPIRED_START,
        period_end=EXPIRED_END,
    )
    expired_html = expired.get("/laws").text
    assert 'data-expired-laws="desktop"' in expired_html
    assert 'data-halted-laws="desktop"' not in expired_html
    assert LIVE_EXPIRED_STATUS in _header(expired_html)
    assert LIVE_HALTED_STATUS not in _header(expired_html)

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused, status="paused")
    assert 'data-halted-laws="desktop"' not in paused.get("/laws").text

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    assert 'data-halted-laws="desktop"' not in pending.get("/laws").text

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro", status="active")
    assert 'data-halted-laws="desktop"' not in pro.get("/laws").text

    mx = TestClient(_mu_app(tmp_path / "max"))
    _sign_in(mx)
    _subscribe(mx, tier="max", status="active")
    assert 'data-halted-laws="desktop"' not in mx.get("/laws").text


def test_halted_laws_get_is_mutation_free(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_roster_then_halt(client)
    before = _facts(client)
    page = client.get("/laws")
    assert page.status_code == 200
    after = _facts(client)
    assert after == before
    again = client.get("/laws")
    assert again.status_code == 200
    assert _facts(client) == before


def test_halted_laws_uses_shared_predicate() -> None:
    src = LAWS.read_text(encoding="utf-8")
    assert "plus_laws" in src
    assert "expired_laws" in src
    assert "halted_laws" in src
    assert 'data-halted-laws="desktop"' in src
    assert "playground_cta(pg_state)" in src
    assert "IN PLAYGROUND" not in src
    assert LIVE_HALTED_STATUS not in src
    for phrase in INVENTED:
        assert phrase not in src, phrase
    base = BASE.read_text(encoding="utf-8")
    assert "halted_laws" in base
    assert "halted_header_status" in base
    assert "expired_header_status" in base
    assert "RecallC Plus" in base
    assert "Free account" in base
    assert LIVE_HALTED_STATUS not in base
    app = APP.read_text(encoding="utf-8")
    page = app.split("async def laws_page", 1)[1].split(
        "async def law_detail_page", 1
    )[0]
    assert "request_is_halted_subscriber" in page
    assert "request_is_expired_subscriber" in page
    assert "request_is_active_plus" in page
    assert '"halted_laws": halted_laws' in page
    assert "_halted_laws_index_states" in page
    assert "def snapshot_is_halted_subscriber" not in page
    assert "BLOCK_PAYMENT_HALTED" in page
    assert "gate_view" in page
    assert "def _halted_laws_index_states" in app
    browse = app.split("async def browse_index", 1)[1].split(
        "async def browse_part", 1
    )[0]
    assert "request_is_halted_subscriber" in browse
    assert '"halted_browse": halted_browse' in browse
    assert "data-halted-laws" not in PG_CSS.read_text(encoding="utf-8")
    assert "data-halted-laws" not in STYLES.read_text(encoding="utf-8")
    assert "data-halted-laws" not in MOBILE.read_text(encoding="utf-8")
    assert "playground.css?v=pg28" in BASE.read_text(encoding="utf-8")


def test_plus_expired_and_halted_01_02_untouched() -> None:
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-halted-landing="desktop"' in landing
    assert "data-halted-laws" not in landing
    browse = BROWSE.read_text(encoding="utf-8")
    assert 'data-halted-browse="desktop"' in browse
    assert "data-halted-laws" not in browse
    assert 'data-plus-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-expired-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-plus-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-expired-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-plus-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-expired-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-plus-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-expired-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-plus-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-expired-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-expired-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-plus-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-expired-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-plus-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-expired-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    assert 'data-expired-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    for path in (BARE, ADD, HOME, GATE, MANAGE, DASH, CAL, PROFILE, SETTINGS):
        text = path.read_text(encoding="utf-8")
        assert "data-halted-laws" not in text
        assert "halted_laws" not in text
    assert "def request_is_halted_subscriber" in DEPS.read_text(encoding="utf-8")


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


def test_halted_laws_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _seed_roster_then_halt(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_laws_screen03_1280.png"
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
              const desk = document.querySelector('[data-halted-laws="desktop"]');
              const plus = document.querySelector('[data-plus-laws="desktop"]');
              const expired = document.querySelector('[data-expired-laws="desktop"]');
              const signed = document.querySelector('[data-signed-in-laws-desktop]');
              const browse = document.querySelector('.nav-link.is-active');
              const heading = signed && signed.querySelector('.laws-index-copy .laws-index-title');
              const search = signed && signed.querySelector('#laws-q');
              const back = signed && signed.querySelector('.laws-back-link');
              const chips = signed ? [...signed.querySelectorAll('.laws-chip')].map(
                (el) => el.textContent.trim()
              ) : [];
              const badges = [...(signed ? signed.querySelectorAll('.LawStatusBadge[data-status="in_playground"]') : [])]
                .filter((el) => getComputedStyle(el).display !== 'none')
                .map((el) => {
                  const card = el.closest('[data-law-id]');
                  return card && card.getAttribute('data-law-id');
                });
              const learn = [...signed.querySelectorAll('a[href*="/learn"]')].map(
                (el) => el.getAttribute('href')
              );
              const add = signed && signed.innerText.includes('+ Add to Playground');
              return {
                present: Boolean(desk),
                plusPresent: Boolean(plus),
                expiredPresent: Boolean(expired),
                browseText: browse ? browse.textContent.replace(/\\s+/g, ' ').trim() : '',
                headingText: heading ? heading.textContent.trim() : '',
                searchPlaceholder: search ? search.getAttribute('placeholder') : null,
                backHref: back && back.getAttribute('href'),
                chips,
                badges,
                learn,
                add,
                accountName: document.querySelector('.account-menu-btn-name').textContent.trim(),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["present"] is True
    assert geo["plusPresent"] is False
    assert geo["expiredPresent"] is False
    assert geo["browseText"] == "Browse"
    assert geo["headingText"] == "Laws"
    assert geo["searchPlaceholder"] == "Search laws"
    assert geo["backHref"] == "/browse"
    assert "All" in geo["chips"]
    assert "Criminal" in geo["chips"]
    assert set(RETAINED) <= set(geo["badges"])
    assert geo["learn"] == []
    assert geo["add"] is False
    assert geo["accountName"] == "Sanjay"
    assert geo["accountStatus"] == LIVE_HALTED_STATUS
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_halted_laws_plus_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client, status="active")
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_laws_screen03_plus_regression_1280.png"
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
              const plus = document.querySelector('[data-plus-laws="desktop"]');
              const halted = document.querySelector('[data-halted-laws="desktop"]');
              const expired = document.querySelector('[data-expired-laws="desktop"]');
              const heading = document.querySelector('.laws-index-copy .laws-index-title');
              return {
                plusPresent: Boolean(plus),
                haltedPresent: Boolean(halted),
                expiredPresent: Boolean(expired),
                heading: heading ? heading.textContent.trim() : '',
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["plusPresent"] is True
    assert geo["haltedPresent"] is False
    assert geo["expiredPresent"] is False
    assert geo["heading"] == "Laws"
    assert geo["accountStatus"] == "RecallC Plus"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
