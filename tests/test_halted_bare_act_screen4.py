"""Halted cohort desktop NDPS Bare Act Screen 04 (CTA map halted/04-screen).

Authorized: ChatGPT. Authenticated multiuser GET /laws/ndps after a real
Plus subscription is halted with NDPS retained in the roster. Reading stays
available. Retained presentation is already_active; the primary CTA is the
Halted recovery action from gate_view(BLOCK_PAYMENT_HALTED), not Continue.
Guest, Free, Plus, Expired, paused, pending, Pro/Max, phone, Plus 01–11,
Expired 01–11, and Halted 01–03 stay unchanged. No new route.
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
from constitution_memorizer.entitlements.models import (
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
)
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.urls import add_path, home_path, law_path, sections_path
from constitution_memorizer.playground.view import PLAYGROUND_BILLING_PATH, gate_view
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.guest_bareact_head import (
    NDPS_GUEST_KICKER,
    NDPS_GUEST_META,
    NDPS_GUEST_ROWS,
    NDPS_GUEST_TITLE,
)

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
LIVE_HALTED_GATE = gate_view(reason=BLOCK_PAYMENT_HALTED)
LIVE_HALTED_STATUS = LIVE_HALTED_GATE.title
LIVE_HALTED_CTA = LIVE_HALTED_GATE.cta_label
LIVE_EXPIRED_STATUS = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
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


def _seed_ndps_then_halt(client: TestClient) -> None:
    _subscribe(client, status="active")
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps")
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None
    client.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _desk(html: str) -> str:
    return html.split("data-signed-in-bareact-desktop", 1)[1].split(
        "data-bareact-phone", 1
    )[0]


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


def test_halted_retained_ndps_uses_lifecycle_cta_not_continue(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_then_halt(client)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.is_authenticated is True
    assert snap.tier == "plus"
    assert snap.subscription_status == "halted"
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    assert snap.playground_block_reason == BLOCK_PAYMENT_HALTED
    assert LIVE_HALTED_STATUS == "Payment retries have stopped"
    assert LIVE_HALTED_CTA == "Manage subscription"
    assert PLAYGROUND_BILLING_PATH == "/billing/subscriptions"
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps")

    before = _facts(client)
    page = client.get("/laws/ndps")
    assert page.status_code == 200
    html = page.text
    header = _header(html)
    desk = _desk(html)
    assert 'data-halted-bareact="desktop"' in html
    assert 'data-plus-bareact="desktop"' not in html
    assert 'data-expired-bareact="desktop"' not in html
    assert "data-signed-in-bareact-desktop" in html
    assert "data-guest-bareact-desktop" not in html
    assert NDPS_GUEST_KICKER in desk
    assert f">{NDPS_GUEST_TITLE}<" in desk
    assert NDPS_GUEST_META in desk
    assert 'class="guest-bareact-back" href="/laws"' in desk
    assert "Already in Playground" in desk
    assert 'data-pg-kind="already_active"' in desk
    assert 'class="signed-bareact-in-pg"' in desk
    assert ">Sections<" in desk
    assert f'href="{sections_path("ndps")}"' in desk
    assert f'class="signed-bareact-continue" href="{PLAYGROUND_BILLING_PATH}"' in desk
    assert f">{LIVE_HALTED_CTA}<" in desk
    assert f'class="signed-bareact-continue" href="{home_path()}"' not in desk
    assert ">Continue<" not in desk
    assert ">Resume Playground<" not in desk
    assert "+ Add to Playground" not in desk
    assert "Add to this month" not in desk
    assert "Add back" not in desk
    assert "Subscribe to use Playground" not in desk
    assert "Sign in to use Playground" not in desk
    assert 'data-pg-kind="eligible_to_add"' not in desk
    assert add_path("ndps") not in desk
    assert "/playground/laws/ndps/learn" not in desk
    assert "data-pg-sheet" not in desk
    assert LIVE_HALTED_STATUS in header
    assert LIVE_EXPIRED_STATUS not in header
    assert "Free account" not in header
    assert "RecallC Plus" not in header
    assert "Sanjay" in header
    assert 'href="/browse"' in header
    assert "is-active" in header
    for phrase in INVENTED:
        assert phrase not in desk, phrase
    for row in NDPS_GUEST_ROWS:
        assert row.title in desk
    assert 'href="/laws/ndps/section/' not in desk
    workspace = client.get(law_path("ndps"))
    assert workspace.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAYMENT_HALTED}"' in workspace.text
    assert 'data-pg-learn-panel="cloze"' not in workspace.text
    assert f">{LIVE_HALTED_CTA}<" in workspace.text
    sections = client.get(sections_path("ndps"))
    assert sections.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAYMENT_HALTED}"' in sections.text
    assert "data-pg-picker" not in sections.text
    assert 'data-pg-learn-panel="cloze"' not in sections.text
    chapter = client.get("/laws/ndps/section/8")
    assert chapter.status_code == 200
    assert _facts(client) == before
    again = client.get("/laws/ndps")
    assert again.status_code == 200
    assert _facts(client) == before
    bns = client.get("/laws/bns")
    assert bns.status_code == 200
    assert _facts(client) == before


def test_halted_elapsed_period_stays_halted_on_bareact(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_then_halt(client)
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    assert stored is not None
    client.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        billing_period_start=EXPIRED_START,
        billing_period_end=EXPIRED_END,
    )
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.subscription_status == "halted"
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps")
    html = client.get("/laws/ndps").text
    header = _header(html)
    desk = _desk(html)
    assert 'data-halted-bareact="desktop"' in html
    assert 'data-expired-bareact="desktop"' not in html
    assert 'data-plus-bareact="desktop"' not in html
    assert LIVE_HALTED_STATUS in header
    assert LIVE_EXPIRED_STATUS not in header
    assert "Free account" not in header
    assert "Already in Playground" in desk
    assert f">{LIVE_HALTED_CTA}<" in desk
    assert ">Continue<" not in desk
    assert ">Resume Playground<" not in desk


def test_never_added_halted_law_has_recovery_not_retained_cluster(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_then_halt(client)
    bns = client.get("/laws/bns").text
    assert 'data-halted-bareact="desktop"' not in bns
    assert "data-signed-in-bareact-desktop" not in bns
    assert "Already in Playground" not in bns
    assert 'data-pg-kind="already_active"' not in bns
    assert 'class="signed-bareact-continue"' not in bns
    assert "+ Add to Playground" not in bns
    assert 'data-pg-kind="eligible_to_add"' not in bns
    assert 'data-pg-kind="resume"' in bns
    assert LIVE_HALTED_CTA in bns
    assert add_path("bns") not in bns

    fresh = TestClient(_mu_app(tmp_path / "none"))
    _sign_in(fresh)
    _subscribe(fresh, status="halted")
    ndps = fresh.get("/laws/ndps").text
    desk = _desk(ndps)
    assert 'data-halted-bareact="desktop"' in ndps
    assert "Already in Playground" not in desk
    assert 'class="signed-bareact-in-pg"' not in desk
    assert 'class="signed-bareact-continue"' not in desk
    assert ">Continue<" not in desk
    assert "+ Add to Playground" not in desk
    assert 'data-pg-kind="already_active"' not in desk
    assert 'data-pg-kind="eligible_to_add"' not in desk
    assert "Subscribe to use Playground" not in desk
    assert 'data-pg-kind="resume"' in desk
    assert LIVE_HALTED_CTA in desk
    assert PLAYGROUND_BILLING_PATH in desk
    assert "data-pg-sheet" not in desk


def test_guest_free_plus_expired_paused_pending_pro_max_are_not_halted_bareact(
    tmp_path: Path,
) -> None:
    guest_html = TestClient(_mu_app(tmp_path / "guest")).get("/laws/ndps").text
    assert 'data-halted-bareact="desktop"' not in guest_html
    assert "data-guest-bareact-desktop" in guest_html
    assert "Sign in to use Playground" in guest_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/laws/ndps").text
    assert 'data-halted-bareact="desktop"' not in free_html
    free_desk = _desk(free_html)
    assert "Subscribe to use Playground" in free_desk
    assert "Free account" in _header(free_html)
    assert LIVE_HALTED_STATUS not in _header(free_html)

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus, status="active")
    added = _confirm_add(plus, "ndps")
    assert added.status_code in {200, 303}
    plus_html = plus.get("/laws/ndps").text
    assert 'data-plus-bareact="desktop"' in plus_html
    assert 'data-halted-bareact="desktop"' not in plus_html
    plus_desk = _desk(plus_html)
    assert "Already in Playground" in plus_desk
    assert f'class="signed-bareact-continue" href="{home_path()}"' in plus_desk
    assert ">Continue<" in plus_desk
    assert "RecallC Plus" in _header(plus_html)
    assert LIVE_HALTED_STATUS not in _header(plus_html)

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(expired, status="active")
    added = _confirm_add(expired, "ndps")
    assert added.status_code in {200, 303}
    stored = expired.app.state.subscriptions.get_current_subscription(USER)
    expired.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        status="expired",
        billing_period_start=EXPIRED_START,
        billing_period_end=EXPIRED_END,
    )
    expired_html = expired.get("/laws/ndps").text
    assert 'data-expired-bareact="desktop"' in expired_html
    assert 'data-halted-bareact="desktop"' not in expired_html
    expired_desk = _desk(expired_html)
    assert "Already in Playground" in expired_desk
    assert ">Resume Playground<" in expired_desk
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in expired_desk
    assert LIVE_EXPIRED_STATUS in _header(expired_html)
    assert LIVE_HALTED_STATUS not in _header(expired_html)

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused, status="paused")
    assert 'data-halted-bareact="desktop"' not in paused.get("/laws/ndps").text

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    assert 'data-halted-bareact="desktop"' not in pending.get("/laws/ndps").text

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro", status="active")
    assert 'data-halted-bareact="desktop"' not in pro.get("/laws/ndps").text

    mx = TestClient(_mu_app(tmp_path / "max"))
    _sign_in(mx)
    _subscribe(mx, tier="max", status="active")
    assert 'data-halted-bareact="desktop"' not in mx.get("/laws/ndps").text


def test_halted_bareact_uses_shared_predicate() -> None:
    bare = BARE.read_text(encoding="utf-8")
    assert "plus_bareact" in bare
    assert "expired_bareact" in bare
    assert "halted_bareact" in bare
    assert 'data-halted-bareact="desktop"' in bare
    assert "pg.kind == 'already_active'" in bare
    assert "pg.primary_label" in bare
    assert "pg.primary_href" in bare
    assert 'href="/playground">Continue</a>' in bare
    assert LIVE_HALTED_STATUS not in bare
    assert LIVE_HALTED_CTA not in bare
    assert "Payment retries have stopped" not in bare
    assert "Manage subscription" not in bare
    for phrase in INVENTED:
        assert phrase not in bare, phrase
    base = BASE.read_text(encoding="utf-8")
    assert "halted_bareact" in base
    assert "halted_header_status" in base
    assert "path == '/laws/ndps'" in base
    assert LIVE_HALTED_STATUS not in base
    app = APP.read_text(encoding="utf-8")
    page = app.split("async def law_detail_page", 1)[1].split(
        "async def bare_act_section_page", 1
    )[0]
    assert "request_is_halted_subscriber" in page
    assert "request_is_expired_subscriber" in page
    assert "request_is_active_plus" in page
    assert '"halted_bareact": halted_bareact' in page
    assert '"halted_header_status": halted_header_status' in page
    assert "_halted_law_presentation" in page
    assert "BLOCK_PAYMENT_HALTED" in page
    assert "gate_view" in page
    assert "def snapshot_is_halted_subscriber" not in page
    assert "def _halted_law_presentation" in app
    assert "def _halted_laws_index_states" in app
    assert "data-halted-bareact" not in PG_CSS.read_text(encoding="utf-8")
    assert "data-halted-bareact" not in STYLES.read_text(encoding="utf-8")
    assert "data-halted-bareact" not in MOBILE.read_text(encoding="utf-8")
    assert "playground.css?v=pg28" in BASE.read_text(encoding="utf-8")
    assert "def request_is_halted_subscriber" in DEPS.read_text(encoding="utf-8")


def test_plus_expired_and_halted_01_02_03_untouched() -> None:
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-halted-landing="desktop"' in landing
    assert "data-halted-bareact" not in landing
    browse = BROWSE.read_text(encoding="utf-8")
    assert 'data-halted-browse="desktop"' in browse
    assert "data-halted-bareact" not in browse
    laws = LAWS.read_text(encoding="utf-8")
    assert 'data-halted-laws="desktop"' in laws
    assert "data-halted-bareact" not in laws
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
    for path in (ADD, HOME, GATE, MANAGE, DASH, CAL, PROFILE, SETTINGS):
        text = path.read_text(encoding="utf-8")
        assert "data-halted-bareact" not in text
        assert "halted_bareact" not in text


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


def test_halted_phone_bareact_unchanged(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_then_halt(client)
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
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        phone = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-signed-in-bareact-desktop]');
              const halted = document.querySelector('[data-halted-bareact="desktop"]');
              const prod = document.querySelector('[data-bareact-phone]');
              return {
                haltedPresent: Boolean(halted),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                prodDisplay: prod ? getComputedStyle(prod).display : null,
                details: prod ? prod.querySelectorAll('details').length : 0,
              };
            }"""
        )
        browser.close()
    assert phone["haltedPresent"] is True
    assert phone["deskDisplay"] == "none"
    assert phone["prodDisplay"] != "none"
    assert phone["details"] > 0


def test_halted_bareact_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_then_halt(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_bareact_screen04_1280.png"
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
              const halted = document.querySelector('[data-halted-bareact="desktop"]');
              const desk = document.querySelector('[data-signed-in-bareact-desktop]');
              const plus = document.querySelector('[data-plus-bareact="desktop"]');
              const expired = document.querySelector('[data-expired-bareact="desktop"]');
              const guest = document.querySelector('[data-guest-bareact-desktop]');
              const phone = document.querySelector('[data-bareact-phone]');
              const brand = document.querySelector('.brand');
              const mark = document.querySelector('.brand-mark');
              const back = desk && desk.querySelector('.guest-bareact-back');
              const cluster = desk && desk.querySelector('.signed-bareact-in-pg');
              const sections = desk && desk.querySelector('.signed-bareact-sections');
              const cont = desk && desk.querySelector('.signed-bareact-continue');
              const rows = desk ? [...desk.querySelectorAll('.guest-bareact-row')] : [];
              const panelText = desk ? desk.innerText : '';
              return {
                present: Boolean(halted),
                plusPresent: Boolean(plus),
                expiredPresent: Boolean(expired),
                deskDisplay: desk && getComputedStyle(desk).display,
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                guestPresent: !!guest,
                brandHref: brand.getAttribute('href'),
                markFilter: getComputedStyle(mark).filter,
                backHref: back && back.getAttribute('href'),
                kicker: desk && desk.querySelector('.guest-bareact-kicker').textContent.trim(),
                title: desk && desk.querySelector('.guest-bareact-title').textContent.trim(),
                meta: desk && desk.querySelector('.guest-bareact-meta').textContent.trim(),
                already: panelText.includes('Already in Playground'),
                clusterPresent: !!cluster,
                sectionsHref: sections && sections.getAttribute('href'),
                sectionsText: sections && sections.textContent.trim(),
                continueHref: cont && cont.getAttribute('href'),
                continueText: cont && cont.textContent.trim(),
                addShown: /Add to Playground/.test(panelText),
                subscribe: panelText.includes('Subscribe to use Playground'),
                signIn: panelText.includes('Sign in to use Playground'),
                invented: /Your subscription expired|Resume subscription|Your payment failed|Fix your payment|Subscription halted|Playground unavailable|Free plan|Unlock all/.test(panelText),
                rowCount: rows.length,
                rowTitles: rows.map((el) =>
                  el.querySelector('.guest-bareact-row-title').textContent.trim()
                ),
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
        browser.close()

    assert geo["present"] is True
    assert geo["plusPresent"] is False
    assert geo["expiredPresent"] is False
    assert geo["deskDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["guestPresent"] is False
    assert geo["brandHref"] == "/dashboard"
    assert "invert" in geo["markFilter"]
    assert geo["backHref"] == "/laws"
    assert geo["kicker"] == NDPS_GUEST_KICKER
    assert geo["title"] == NDPS_GUEST_TITLE
    assert geo["meta"] == NDPS_GUEST_META
    assert geo["already"] is True
    assert geo["clusterPresent"] is True
    assert geo["sectionsText"] == "Sections"
    assert geo["sectionsHref"] == sections_path("ndps")
    assert geo["continueText"] == LIVE_HALTED_CTA
    assert geo["continueHref"] == PLAYGROUND_BILLING_PATH
    assert geo["continueText"] != "Continue"
    assert geo["addShown"] is False
    assert geo["subscribe"] is False
    assert geo["signIn"] is False
    assert geo["invented"] is False
    assert geo["rowCount"] == 4
    assert geo["rowTitles"] == [row.title for row in NDPS_GUEST_ROWS]
    assert geo["accountName"] == "Sanjay"
    assert geo["accountStatus"] == LIVE_HALTED_STATUS
    assert geo["navLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["browseActive"] == "Browse"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_halted_bareact_plus_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client, status="active")
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "halted_bareact_screen04_plus_regression_1280.png"
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
              const halted = document.querySelector('[data-halted-bareact="desktop"]');
              const plus = document.querySelector('[data-plus-bareact="desktop"]');
              const expired = document.querySelector('[data-expired-bareact="desktop"]');
              const desk = document.querySelector('[data-signed-in-bareact-desktop]');
              const cluster = desk && desk.querySelector('.signed-bareact-in-pg');
              const sections = desk && desk.querySelector('.signed-bareact-sections');
              const cont = desk && desk.querySelector('.signed-bareact-continue');
              return {
                haltedPresent: Boolean(halted),
                plusPresent: Boolean(plus),
                expiredPresent: Boolean(expired),
                already: desk && desk.innerText.includes('Already in Playground'),
                clusterPresent: !!cluster,
                sectionsHref: sections && sections.getAttribute('href'),
                continueHref: cont && cont.getAttribute('href'),
                continueText: cont && cont.textContent.trim(),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                title: desk && desk.querySelector('.guest-bareact-title').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["haltedPresent"] is False
    assert geo["plusPresent"] is True
    assert geo["expiredPresent"] is False
    assert geo["already"] is True
    assert geo["clusterPresent"] is True
    assert geo["sectionsHref"] == sections_path("ndps")
    assert geo["continueHref"] == home_path()
    assert geo["continueText"] == "Continue"
    assert geo["accountStatus"] == "RecallC Plus"
    assert geo["title"] == NDPS_GUEST_TITLE
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
