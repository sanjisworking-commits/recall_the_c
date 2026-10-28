"""Signed-in Free Playground Gate Screen 07 (CTA map signedIn/07-screen).

Authorized: ChatGPT. Authenticated Free GET /playground intro, then
?stage=plans and &tier= selectors on the existing Gate. Guest intro, Plus
home, Expired 06, Halted 06, paused/pending/device gates, Add dialog copy,
and phone redesign stay unchanged. Continue with X has no handler.
"""

from __future__ import annotations

import socket
import threading
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.entitlements.models import BLOCK_NOT_SUBSCRIBED
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.view import (
    FREE_GATE_HOW_STEPS,
    GATE_STAGE_INTRO,
    GATE_STAGE_PLANS,
    PLAYGROUND_BILLING_PATH,
    PLAYGROUND_PLANS_PATH,
    catalogue_plan_views,
    gate_plan_continue_label,
    gate_selector_plan_views,
    gate_view,
    parse_playground_gate_stage,
)
from constitution_memorizer.subscriptions.catalog import list_subscription_products
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.guest_playground_intro import GUEST_PG_STEPS

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
ACCESS = ROOT / "src/constitution_memorizer/playground/access.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
INTRO_TITLE = "Your RecallC account already includes the complete Constitution."
INTRO_BODY = "Playground adds structured learning for laws."
INTRO_CTA = "View Playground plans"
INVENTED = (
    "Choose a plan",
    "Best value",
    "Recommended",
    "Start free",
    "Buy now",
    "Checkout",
    "Coming soon",
    "Unlock Playground",
    "Subscribe to Plus",
    "Subscribe to Pro",
    "Subscribe to Max",
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
        APP_BASE_URL="https://recall-the-c.in",
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
    tmp_path.mkdir(parents=True, exist_ok=True)
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


def _free_client(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    return client


def _gate(html: str) -> str:
    return html.split("data-signed-in-pg-gate", 1)[1].split("</section>", 1)[0]


def _header(html: str) -> str:
    return html.split("<header", 1)[-1].split("</header>", 1)[0]


def _facts(client: TestClient) -> dict:
    snap = client.app.state.entitlement_service.resolve(USER)
    roster = client.app.state.roster
    overlay = client.app.state.playground
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    history = tuple(
        sorted(
            (row.id, row.status, row.tier, row.is_current)
            for row in client.app.state.subscriptions.list_subscription_history(USER)
        )
    )
    return {
        "active": tuple(sorted(i.law_id for i in roster.active_roster_items(USER))),
        "removed": tuple(sorted(i.law_id for i in roster.removed_roster_items(USER))),
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        ),
        "subscription": None
        if stored is None
        else (stored.id, stored.status, stored.tier, stored.is_current),
        "history": history,
        "can_open": snap.can_open_playground,
        "reason": snap.playground_block_reason,
        "status": snap.subscription_status,
        "subscribed": snap.is_subscribed,
    }


def _watch_provider(client: TestClient) -> list[str]:
    calls: list[str] = []
    svc = getattr(client.app.state, "subscription_service", None)
    if svc is None:
        return calls
    for name in (
        "start_subscription",
        "complete_checkout",
        "cancel_at_cycle_end",
        "change_plan",
        "fetch_provider_subscription",
        "fetch_provider_payment",
        "reconcile_current",
    ):
        orig = getattr(svc, name)

        def wrapped(*args, _orig=orig, _name=name, **kwargs):
            calls.append(_name)
            return _orig(*args, **kwargs)

        setattr(svc, name, wrapped)
    razor = getattr(svc, "_client", None)
    if razor is not None:
        for name in (
            "create_subscription",
            "fetch_subscription",
            "fetch_payment",
            "cancel_subscription",
        ):
            if not hasattr(razor, name):
                continue
            orig = getattr(razor, name)

            def wrapped(*args, _orig=orig, _name=name, **kwargs):
                calls.append(_name)
                return _orig(*args, **kwargs)

            setattr(razor, name, wrapped)
    return calls


def test_free_gate_intro_uses_viewer_table_copy(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.playground_block_reason == BLOCK_NOT_SUBSCRIBED
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    page = client.get("/playground")
    assert page.status_code == 200
    html = unescape(page.text)
    gate = _gate(html)
    assert 'data-playground-gate="not_subscribed"' in html
    assert "data-signed-in-pg-gate" in html
    assert 'data-pg-gate-stage="intro"' in html
    assert 'data-hard-gate="true"' in html
    assert f">{INTRO_TITLE}<" in gate
    assert INTRO_BODY in gate
    assert ">Unlock Playground<" not in gate
    assert INTRO_CTA in gate
    assert f'href="{PLAYGROUND_PLANS_PATH}"' in gate
    assert PLAYGROUND_BILLING_PATH not in gate
    assert "data-pg-plans" not in gate
    assert "data-pg-plan-continue" not in html
    assert "Included with your account" not in html
    assert "Back to Constitution" not in gate
    assert "How Playground works" in gate
    for step in GUEST_PG_STEPS:
        assert step in gate
    assert FREE_GATE_HOW_STEPS == GUEST_PG_STEPS
    assert "Choose your laws each month" not in gate
    assert "data-guest-pg-intro" not in html
    assert "Free account" in _header(html)
    for phrase in INVENTED:
        assert phrase not in gate, phrase


def test_free_gate_stage_query_isolation(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    intro = unescape(client.get("/playground?stage=intro").text)
    assert 'data-pg-gate-stage="intro"' in intro
    assert "data-pg-plans" not in _gate(intro)
    garbage = unescape(client.get("/playground?stage=checkout").text)
    assert 'data-pg-gate-stage="intro"' in garbage
    bare_tier = unescape(client.get("/playground?tier=plus").text)
    assert 'data-pg-gate-stage="intro"' in bare_tier
    assert "data-pg-plan-continue" not in bare_tier
    assert "Continue with Plus" not in bare_tier


def test_free_gate_plans_lists_live_catalogue_without_selection(
    tmp_path: Path,
) -> None:
    client = _free_client(tmp_path)
    calls = _watch_provider(client)
    page = client.get("/playground?stage=plans")
    assert page.status_code == 200
    html = unescape(page.text)
    gate = _gate(html)
    assert 'data-pg-gate-stage="plans"' in html
    assert "data-pg-plans" in gate
    products = list_subscription_products()
    assert [row.tier for row in products] == ["plus", "pro", "max"]
    views = gate_selector_plan_views()
    assert tuple(plan.tier for plan in views) == ("plus", "pro", "max")
    for plan in views:
        assert f'data-tier="{plan.tier}"' in gate
        assert plan.display_name in gate
        assert plan.price_label in gate
        assert plan.limit_label in gate
        assert plan.href in gate
        assert PLAYGROUND_BILLING_PATH not in plan.href
        assert f"stage=plans&tier={plan.tier}" in plan.href
    assert "data-pg-plan-selected" not in gate
    assert "data-pg-plan-continue" not in html
    assert "Continue with" not in html
    assert INTRO_CTA not in gate
    assert PLAYGROUND_BILLING_PATH not in gate
    assert calls == []
    billed = catalogue_plan_views()
    assert all(plan.href == PLAYGROUND_BILLING_PATH for plan in billed)


def test_free_gate_tier_selection_continue_has_no_handler(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    products = {row.tier: row for row in list_subscription_products()}
    for tier in ("plus", "pro", "max"):
        calls = _watch_provider(client)
        before = _facts(client)
        page = client.get(f"/playground?stage=plans&tier={tier}")
        assert page.status_code == 200
        html = unescape(page.text)
        gate = _gate(html)
        name = products[tier].display_name
        label = f"Continue with {name}"
        assert gate_plan_continue_label(selected_tier=tier) == label
        assert 'data-pg-gate-stage="plans"' in html
        selected = gate.split(f'data-tier="{tier}"', 1)[1].split("data-tier=", 1)[0]
        assert "data-pg-plan-selected" in selected
        assert 'aria-current="true"' in selected
        assert 'aria-pressed="true"' in selected
        assert "is-selected" in gate.split(f'data-tier="{tier}"', 1)[0][-80:] + selected[:80]
        assert f'type="button"' in gate
        assert 'data-pg-plan-continue' in gate
        assert f">{label}<" in gate
        continue_html = gate.split("data-pg-plan-continue", 1)[1].split("</button>", 1)[0]
        assert "href=" not in continue_html
        assert "<form" not in gate
        assert 'action="' not in gate
        assert "/checkout" not in gate
        assert PLAYGROUND_BILLING_PATH not in gate
        assert "Coming soon" not in gate
        assert _facts(client) == before
        assert calls == []


def test_free_gate_invalid_tier_stays_plans_without_cta(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    page = client.get("/playground?stage=plans&tier=gold")
    assert page.status_code == 200
    html = unescape(page.text)
    gate = _gate(html)
    assert 'data-pg-gate-stage="plans"' in html
    assert "data-pg-plans" in gate
    assert "data-pg-plan-selected" not in gate
    assert "data-pg-plan-continue" not in html
    assert "Continue with" not in html
    assert "Continue with Plus" not in html


def test_free_gate_gets_are_mutation_free(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    calls = _watch_provider(client)
    before = _facts(client)
    assert before["can_open"] is False
    assert before["reason"] == BLOCK_NOT_SUBSCRIBED
    assert before["subscription"] is None
    for url in (
        "/playground",
        "/playground?stage=plans",
        "/playground?stage=plans&tier=plus",
        "/playground?stage=plans&tier=pro",
        "/playground?stage=plans&tier=max",
    ):
        page = client.get(url)
        assert page.status_code == 200
        assert _facts(client) == before
    assert calls == []


def test_guest_plus_expired_halted_paused_pending_stay_separate(
    tmp_path: Path,
) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest")).get("/playground").text
    assert "data-guest-pg-intro" in guest
    assert "data-signed-in-pg-gate" not in guest
    assert "Sign in to build your law-learning Playground." in guest
    assert INTRO_TITLE not in guest
    guest_plans = TestClient(_mu_app(tmp_path / "guest-plans")).get(
        "/playground?stage=plans"
    ).text
    assert "data-guest-pg-intro" in guest_plans
    assert "data-signed-in-pg-gate" not in guest_plans

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = unescape(plus.get("/playground").text)
    assert 'data-plus-playground="desktop"' in plus_html
    assert "data-signed-in-pg-gate" not in plus_html
    assert "My Playground" in plus_html or "pg-home-title" in plus_html
    plus_plans = unescape(plus.get("/playground?stage=plans&tier=pro").text)
    assert "data-signed-in-pg-gate" not in plus_plans
    assert 'data-plus-playground="desktop"' in plus_plans

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(expired)
    stored = expired.app.state.subscriptions.get_current_subscription(USER)
    expired.app.state.subscriptions.update_subscription_state(
        USER,
        stored.id,
        status="expired",
        billing_period_start=datetime(2026, 8, 16, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )
    expired_html = unescape(expired.get("/playground").text)
    assert 'data-expired-playground="desktop"' in expired_html
    assert "Your Playground is paused" in expired_html
    assert ">View Playground plans<" in expired_html
    assert INTRO_TITLE not in expired_html
    expired_plans = unescape(expired.get("/playground?stage=plans").text)
    assert 'data-expired-playground="desktop"' in expired_plans
    assert "data-signed-in-pg-gate" not in expired_plans

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    stored_h = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored_h.id, status="halted"
    )
    halted_html = unescape(halted.get("/playground").text)
    assert 'data-halted-playground="desktop"' in halted_html
    assert "Payment retries have stopped" in halted_html
    assert "Manage subscription" in halted_html
    assert INTRO_TITLE not in halted_html
    halted_plans = unescape(halted.get("/playground?stage=plans").text)
    assert 'data-halted-playground="desktop"' in halted_plans
    assert "data-signed-in-pg-gate" not in halted_plans

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused, status="paused")
    paused_html = paused.get("/playground").text
    assert "Playground subscription paused" in paused_html or "Resume Playground" in paused_html
    assert "data-pg-gate-stage" not in paused_html

    pending = TestClient(_mu_app(tmp_path / "pending"))
    _sign_in(pending)
    _subscribe(pending, status="pending")
    pending_html = pending.get("/playground").text
    assert "data-signed-in-pg-gate" not in pending_html
    assert INTRO_TITLE not in pending_html


def test_desktop_entry_points_open_playground_gate(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    browse = client.get("/browse").text
    assert 'class="browse-access-unlock" href="/playground">Unlock all</a>' in browse
    header = _header(client.get("/dashboard").text)
    assert 'href="/playground"' in header
    assert ">Playground<" in header
    add = client.get("/playground/laws/ndps/add")
    assert add.status_code == 200
    desk = add.text.split("data-signed-in-add-desktop", 1)[1].split(
        "data-signed-in-add-phone", 1
    )[0]
    assert 'href="/playground">Unlock Playground</a>' in desk
    phone = add.text.split("data-signed-in-add-phone", 1)[1]
    assert 'href="/playground">Unlock Playground</a>' in phone
    gate = client.get("/playground")
    assert 'data-pg-gate-stage="intro"' in gate.text
    assert INTRO_TITLE in unescape(gate.text)


def test_free_gate_marker_and_parser_are_presentation_only() -> None:
    gate = GATE.read_text(encoding="utf-8")
    assert "data-signed-in-pg-gate" in gate
    assert 'data-pg-gate-stage="{{ gate_stage }}"' in gate
    assert "data-pg-plan-continue" in gate
    assert 'type="button"' in gate
    assert "data-pg-plan-selected" in gate
    assert INTRO_TITLE not in gate
    assert "Unlock Playground" not in gate.split("data-signed-in-pg-gate", 1)[1]
    assert "/resume" not in gate
    assert "Coming soon" not in gate
    view = VIEW.read_text(encoding="utf-8")
    not_sub = view.split("if reason == BLOCK_NOT_SUBSCRIBED:", 1)[1].split(
        "if reason == BLOCK_DEVICE_LIMIT:", 1
    )[0]
    assert INTRO_TITLE in not_sub
    assert "Unlock Playground" not in not_sub
    assert "PLAYGROUND_PLANS_PATH" in not_sub
    assert "show_plans=False" in not_sub
    assert "show_included=False" in not_sub
    assert "def catalogue_plan_views" in view
    billed = view.split("def catalogue_plan_views", 1)[1].split(
        "def parse_playground_gate_stage", 1
    )[0]
    assert "PLAYGROUND_BILLING_PATH" in billed
    assert "def gate_selector_plan_views" in view
    assert "def parse_playground_gate_stage" in view
    access = ACCESS.read_text(encoding="utf-8")
    page = access.split("def _gate_page", 1)[1]
    assert "parse_playground_gate_stage_from_request" in page
    assert "PLAYGROUND_PLANS_PATH" in page
    assert "BLOCK_PAID_PERIOD_ENDED" in page
    assert "PLAYGROUND_BILLING_PATH" in page
    live = gate_view(reason=BLOCK_NOT_SUBSCRIBED)
    assert live.title == INTRO_TITLE
    assert live.lines == (INTRO_BODY,)
    assert live.cta_label == INTRO_CTA
    assert live.cta_href == PLAYGROUND_PLANS_PATH
    assert live.show_plans is False
    assert live.show_included is False
    assert parse_playground_gate_stage() == (GATE_STAGE_INTRO, None)
    assert parse_playground_gate_stage("plans") == (GATE_STAGE_PLANS, None)
    assert parse_playground_gate_stage("plans", "plus") == (GATE_STAGE_PLANS, "plus")
    assert parse_playground_gate_stage(None, "plus") == (GATE_STAGE_INTRO, None)
    assert parse_playground_gate_stage("plans", "gold") == (GATE_STAGE_PLANS, None)
    assert FREE_GATE_HOW_STEPS == GUEST_PG_STEPS
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg48" in base
    css = PG_CSS.read_text(encoding="utf-8")
    assert "signedIn/07-screen" in css
    assert 'data-pg-gate-stage="plans"' in css
    assert "data-pg-plan-continue" in css
    assert "data-signed-in-pg-gate" not in MOBILE.read_text(encoding="utf-8")
    assert 'href="/playground">Unlock all</a>' in BROWSE.read_text(encoding="utf-8")
    add = ADD.read_text(encoding="utf-8")
    desk = add.split("data-signed-in-add-desktop", 1)[1].split(
        "data-signed-in-add-phone", 1
    )[0]
    assert 'href="/playground">Unlock Playground</a>' in desk
    phone = add.split("data-signed-in-add-phone", 1)[1]
    assert 'href="/playground">Unlock Playground</a>' in phone
    assert "data-signed-in-pg-gate" not in HOME.read_text(encoding="utf-8")


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


def test_free_gate_screen07_intro_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "free_gate_screen07_intro_1280.png"
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
        page.goto(f"{origin}/playground", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const gate = document.querySelector('[data-signed-in-pg-gate]');
              const title = gate && gate.querySelector('#pg-gate-title');
              const lede = gate && gate.querySelector(':scope > .pg-lede');
              const cta = gate && gate.querySelector(':scope > .pg-actions .pg-btn');
              const plans = gate && gate.querySelector('[data-pg-plans]');
              const how = gate && gate.querySelector('.HowPlaygroundWorks');
              const steps = how ? [...how.querySelectorAll('.HowPlaygroundWorks-row strong')] : [];
              const status = document.querySelector('.account-menu-btn-status');
              return {
                present: Boolean(gate),
                stage: gate && gate.getAttribute('data-pg-gate-stage'),
                title: title && title.textContent.trim(),
                lede: lede && lede.textContent.trim(),
                ctaText: cta && cta.textContent.trim(),
                ctaHref: cta && cta.getAttribute('href'),
                plans: Boolean(plans),
                stepCount: steps.length,
                steps: steps.map((el) => (el.textContent || '').trim()),
                status: status && status.textContent.trim(),
                continueBtn: Boolean(document.querySelector('[data-pg-plan-continue]')),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        context.close()
        browser.close()
    assert geo["present"] is True
    assert geo["stage"] == "intro"
    assert geo["title"] == INTRO_TITLE
    assert geo["lede"] == INTRO_BODY
    assert geo["ctaText"] == INTRO_CTA
    assert geo["ctaHref"] == PLAYGROUND_PLANS_PATH
    assert geo["plans"] is False
    assert geo["stepCount"] == 4
    assert geo["steps"] == list(GUEST_PG_STEPS)
    assert geo["status"] == "Free account"
    assert geo["continueBtn"] is False
    assert shot_path.exists() and shot_path.stat().st_size > 1000


def test_free_gate_screen07_plans_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "free_gate_screen07_plans_1280.png"
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
        page.goto(f"{origin}/playground?stage=plans", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const gate = document.querySelector('[data-signed-in-pg-gate]');
              const cards = [...document.querySelectorAll('[data-pg-plans] [data-tier]')];
              const selected = document.querySelector('[data-pg-plan-selected]');
              const cont = document.querySelector('[data-pg-plan-continue]');
              const introCta = gate && gate.querySelector(':scope > .pg-actions a.pg-btn');
              return {
                stage: gate && gate.getAttribute('data-pg-gate-stage'),
                tiers: cards.map((el) => el.getAttribute('data-tier')),
                names: cards.map((el) => (el.querySelector('.pg-plan-name') || {}).textContent),
                selected: Boolean(selected),
                continue: Boolean(cont),
                introCta: introCta && introCta.textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        context.close()
        browser.close()
    assert geo["stage"] == "plans"
    assert geo["tiers"] == ["plus", "pro", "max"]
    assert [name.strip() for name in geo["names"]] == ["Plus", "Pro", "Max"]
    assert geo["selected"] is False
    assert geo["continue"] is False
    assert geo["introCta"] in (None, False, "")
    assert shot_path.exists() and shot_path.stat().st_size > 1000


def test_free_gate_screen07_plus_selected_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "free_gate_screen07_plus_selected_1280.png"
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
        page.goto(
            f"{origin}/playground?stage=plans&tier=plus", wait_until="networkidle"
        )
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const selected = document.querySelector('[data-pg-plan-selected]');
              const cont = document.querySelector('[data-pg-plan-continue]');
              const href = cont && (cont.getAttribute('href') || cont.closest('a') || cont.closest('form'));
              return {
                tier: selected && selected.getAttribute('data-tier'),
                pressed: selected && selected.getAttribute('aria-pressed'),
                current: selected && selected.getAttribute('aria-current'),
                selectedClass: selected && selected.classList.contains('is-selected'),
                continueText: cont && (cont.textContent || '').trim(),
                continueType: cont && cont.getAttribute('type'),
                continueTag: cont && cont.tagName,
                continueHref: cont && cont.getAttribute('href'),
                wrapped: Boolean(href),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        context.close()
        browser.close()
    assert geo["tier"] == "plus"
    assert geo["pressed"] == "true"
    assert geo["current"] == "true"
    assert geo["selectedClass"] is True
    assert geo["continueText"] == "Continue with Plus"
    assert geo["continueType"] == "button"
    assert geo["continueTag"] == "BUTTON"
    assert geo["continueHref"] is None
    assert geo["wrapped"] is False
    assert shot_path.exists() and shot_path.stat().st_size > 1000
