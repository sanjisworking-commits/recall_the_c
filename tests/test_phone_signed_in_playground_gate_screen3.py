"""Phone signed-in Free Playground Gate Screen 03 (CTA map signedIn/03-screen).

Authorized: ChatGPT. Authenticated Free GET /playground at 390x844. Desktop
Free Gate 07 is the functional contract. Guest phone 03 is layout reference
only. Continue stays handlerless. No checkout, billing, or entitlement edits.
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
from constitution_memorizer.devices.token import mint_installation_token
from constitution_memorizer.entitlements.models import BLOCK_NOT_SUBSCRIBED
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.urls import add_path, home_path
from constitution_memorizer.playground.view import (
    FREE_GATE_HOW_STEPS,
    PLAYGROUND_BILLING_PATH,
    PLAYGROUND_PLANS_PATH,
    catalogue_plan_views,
    gate_plan_continue_label,
    gate_selector_plan_views,
    gate_view,
)
from constitution_memorizer.subscriptions.catalog import list_subscription_products
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.guest_playground_intro import GUEST_PG_STEPS

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
ACCESS = ROOT / "src/constitution_memorizer/playground/access.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
PG_JS = ROOT / "src/constitution_memorizer/web/static/playground.js"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
INTRO_TITLE = "Your RecallC account already includes the complete Constitution."
INTRO_BODY = "Playground adds structured learning for laws."
INTRO_CTA = "View Playground plans"
HARD_GATE_HIDE = (
    # M1 (DV-21): the desktop nav is no longer hidden on hard-gated pages;
    # only phone bars hide, and the shared guest bar is exempt.
    'body:has(.PlaygroundShell[data-hard-gate="true"]) '
    ".mobile-tabbar:not([data-guest-phone-tabs]) {\n"
    "  display: none;\n"
    "}"
)
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
)
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
    "Core",
    "Deep",
    "Infinite",
    "₹149",
    "₹299",
    "₹499",
    "Create an account",
    "PLAYGROUND · SUBSCRIPTION",
    "12 Aug",
    "11 Sep",
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


def _guest_app(tmp_path: Path):
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=FakeAuthProvider(),
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


def _tabs(html: str) -> str:
    return html.split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 1
    )[1].split("</nav>", 1)[0]


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
        orig = getattr(svc, name, None)
        if orig is None:
            continue

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


def test_phone_free_gate_intro_is_live_not_subscribed_copy(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.playground_block_reason == BLOCK_NOT_SUBSCRIBED
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
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
    assert "data-phone-pg-gate" not in html
    assert "data-guest-pg-intro" not in html
    assert "data-signed-in-pg-phone-tabs" not in html
    assert "How Playground works" in gate
    for step in GUEST_PG_STEPS:
        assert step in gate
    assert FREE_GATE_HOW_STEPS == GUEST_PG_STEPS
    for phrase in INVENTED:
        assert phrase not in gate, phrase
    tabs = _tabs(html)
    for label, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        assert label in tabs
    playground = tabs.split('href="/playground"', 1)[1].split("</a>", 1)[0]
    assert "is-active" in playground
    assert 'aria-current="page"' in playground


def test_signed_in_01_02_unlock_lands_on_intro(tmp_path: Path) -> None:
    client = _free_client(tmp_path)
    ndps = unescape(client.get("/laws/ndps").text)
    phone_head = ndps.split("data-signed-in-bareact-phone", 1)[1]
    assert f'href="{add_path("ndps")}"' in phone_head
    add = unescape(client.get(add_path("ndps")).text)
    phone_add = add.split("data-signed-in-add-phone", 1)[1]
    assert 'href="/playground">Unlock Playground</a>' in phone_add
    gate = unescape(client.get("/playground").text)
    assert 'data-pg-gate-stage="intro"' in gate
    assert INTRO_TITLE in _gate(gate)
    assert "data-pg-plans" not in _gate(gate)


def test_phone_free_gate_stage_query_isolation(tmp_path: Path) -> None:
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


def test_phone_free_gate_plans_lists_live_catalogue_without_selection(
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
    assert "₹199" in gate
    assert "₹399" in gate
    assert "₹1199" in gate
    assert "Monthly. GST included." in gate
    assert calls == []
    billed = catalogue_plan_views()
    assert all(plan.href == PLAYGROUND_BILLING_PATH for plan in billed)


def test_phone_free_gate_tier_selection_continue_has_no_handler(
    tmp_path: Path,
) -> None:
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
        assert 'type="button"' in gate
        assert "data-pg-plan-continue" in gate
        assert f">{label}<" in gate
        continue_html = gate.split("data-pg-plan-continue", 1)[1].split("</button>", 1)[0]
        assert "href=" not in continue_html
        assert "<form" not in gate
        assert 'action="' not in gate
        assert "/checkout" not in gate
        assert PLAYGROUND_BILLING_PATH not in gate
        assert _facts(client) == before
        assert calls == []


def test_phone_free_gate_invalid_tier_stays_plans_without_cta(tmp_path: Path) -> None:
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


def test_phone_free_gate_gets_are_mutation_free(tmp_path: Path) -> None:
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
        "/playground?stage=checkout",
        "/playground?tier=plus",
        "/playground?stage=plans&tier=gold",
    ):
        page = client.get(url)
        assert page.status_code == 200
        assert _facts(client) == before
    assert calls == []


def test_guest_plus_expired_halted_paused_stay_separate(tmp_path: Path) -> None:
    guest = TestClient(_guest_app(tmp_path / "guest")).get("/playground").text
    assert "data-guest-pg-intro" in guest
    assert 'data-phone-pg-gate="guest"' in guest
    assert "data-signed-in-pg-gate" not in guest
    assert INTRO_TITLE not in guest

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = unescape(plus.get("/playground").text)
    assert 'data-plus-playground="desktop"' in plus_html
    assert "data-signed-in-pg-gate" not in plus_html
    plus_plans = unescape(plus.get("/playground?stage=plans&tier=pro").text)
    assert "data-signed-in-pg-gate" not in plus_plans

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
    assert "data-signed-in-pg-gate" not in expired_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    stored_h = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored_h.id, status="halted"
    )
    halted_html = unescape(halted.get("/playground").text)
    assert 'data-halted-playground="desktop"' in halted_html
    assert "data-signed-in-pg-gate" not in halted_html

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused, status="paused")
    paused_html = paused.get("/playground").text
    assert "data-signed-in-pg-gate" not in paused_html
    assert "data-pg-gate-stage" not in paused_html

    limited = TestClient(_mu_app(tmp_path / "device"))
    _sign_in(limited)
    _subscribe(limited)
    inner = getattr(limited.app.state.device_service, "inner", limited.app.state.device_service)
    for index in range(2):
        access = inner.ensure_current_device(
            USER,
            mint_installation_token(),
            auth_session_id=f"seed-sess-{index}",
            commercially_eligible=True,
        )
        assert access.current_device_registered is True
    limited_html = limited.get("/playground").text
    assert 'data-playground-gate="device_limit"' in limited_html
    assert 'data-hard-gate="true"' in limited_html
    assert "data-signed-in-pg-gate" not in limited_html
    assert "Device limit reached" in limited_html
    assert 'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"' in limited_html


def test_phone_free_gate_css_is_breakpoint_scoped() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    assert HARD_GATE_HIDE in css
    assert css.count(HARD_GATE_HIDE) == 1
    phone_block = css.split("is signedIn/03-screen:", 1)[1].split(
        "@media (min-width: 561px)", 1
    )[0]
    assert "@media (max-width: 560px)" in phone_block
    assert "[data-signed-in-pg-gate]" in phone_block
    assert "safe-area-inset-bottom" in phone_block
    assert "overflow-x: hidden" in phone_block
    assert "var(--m-tabbar, 60px)" in phone_block
    assert ".mobile-tabbar" in phone_block
    assert "grid-template-columns: repeat(5, 1fr)" in phone_block
    assert 'data-pg-gate-stage="plans"' in phone_block
    assert "[data-phone-pg-gate" not in phone_block
    assert "data-guest-pg-phone-tabs" not in phone_block
    assert ":has([data-guest-add-phone])" not in phone_block
    desk = css.split(
        "Signed-in desktop not-subscribed Gate (CTA map signedIn/07-screen intro).",
        1,
    )[1].split("/* Guest phone Profile", 1)[0]
    assert "@media (min-width: 561px)" in desk
    assert "minmax(0, 1fr) 300px" in desk
    assert ".mobile-tabbar" not in desk
    hide = css.split(
        'body:has(.PlaygroundShell[data-hard-gate="true"]) .mobile-tabbar', 1
    )[1].split("}", 1)[0]
    assert ":not([data-guest-phone-tabs])" in hide
    assert "data-signed-in-pg-gate" not in hide
    base = BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg49" in base
    assert "playground.css?v=pg33" not in base
    assert "styles.css?v=main87" in base
    assert "mobile.css?v=mob106" in base
    assert "data-signed-in-pg-gate" not in MOBILE.read_text(encoding="utf-8")
    js = PG_JS.read_text(encoding="utf-8")
    assert "data-pg-plan-continue" not in js
    assert "data-signed-in-pg-gate" not in js
    live = gate_view(reason=BLOCK_NOT_SUBSCRIBED)
    assert live.title == INTRO_TITLE
    assert live.cta_label == INTRO_CTA
    assert live.cta_href == PLAYGROUND_PLANS_PATH
    assert live.show_included is False
    gate_src = GATE.read_text(encoding="utf-8")
    assert gate_src.count("data-signed-in-pg-gate") == 1
    assert 'data-phone-pg-gate="guest"' not in gate_src.split(
        "data-signed-in-pg-gate", 1
    )[1]
    access = ACCESS.read_text(encoding="utf-8")
    assert "signed_in_free_pg_phone" not in access
    add = ADD.read_text(encoding="utf-8")
    assert 'href="/playground">Unlock Playground</a>' in add
    first_bar = BASE.read_text(encoding="utf-8").split(
        'class="mobile-tabbar PrimaryTabs PrimaryTabs--bottom"', 2
    )[2].split("</nav>", 1)[0]
    assert 'href="/calendar"' in first_bar
    assert "path.startswith('/profile')" in first_bar
    assert "data-signed-in-bareact-phone-tabs" not in first_bar
    assert "data-plus-bareact-phone-tabs" not in first_bar
    assert "data-guest-pg-phone-tabs" not in first_bar


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


def _cookie(session: str, origin: str) -> list[dict]:
    return [
        {
            "name": SESSION_COOKIE_NAME,
            "value": session,
            "url": origin,
            "httpOnly": True,
            "secure": False,
            "sameSite": "Lax",
        }
    ]


def test_phone_signed_in_playground_gate_screen03_intro_390x844(
    tmp_path: Path,
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_signed_in_playground_gate_screen03_intro_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        context.add_cookies(_cookie(session, origin))
        page = context.new_page()
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )
        requests: list[str] = []
        page.on("request", lambda req: requests.append(f"{req.method} {req.url}"))
        page.goto(f"{origin}/playground", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const gate = document.querySelector('[data-signed-in-pg-gate]');
              const header = document.querySelector('.site-header');
              const tabs = document.querySelector('.mobile-tabbar');
              const cta = gate && gate.querySelector(':scope > .pg-actions a.pg-btn');
              const how = gate && gate.querySelector('.HowPlaygroundWorks');
              const steps = how
                ? [...how.querySelectorAll('.HowPlaygroundWorks-row strong')]
                : [];
              const tabLinks = tabs ? [...tabs.querySelectorAll('a.mobile-tab')] : [];
              const active = tabs && tabs.querySelector('.mobile-tab.is-active');
              const last = gate && gate.lastElementChild;
              const pad = gate
                ? getComputedStyle(document.querySelector('.PlaygroundShell')).paddingBottom
                : '0';
              return {
                present: Boolean(gate),
                stage: gate && gate.getAttribute('data-pg-gate-stage'),
                title: gate && gate.querySelector('#pg-gate-title')
                  && gate.querySelector('#pg-gate-title').textContent.trim(),
                lede: gate && gate.querySelector(':scope > .pg-lede')
                  && gate.querySelector(':scope > .pg-lede').textContent.trim(),
                ctaText: cta && cta.textContent.trim(),
                ctaHref: cta && cta.getAttribute('href'),
                ctaWidth: cta ? cta.getBoundingClientRect().width : 0,
                ctaHeight: cta ? cta.getBoundingClientRect().height : 0,
                plans: Boolean(gate && gate.querySelector('[data-pg-plans]')),
                continueBtn: Boolean(document.querySelector('[data-pg-plan-continue]')),
                headerDisplay: header ? getComputedStyle(header).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                tabLabels: tabLinks.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabLinks.map((el) => el.getAttribute('href')),
                playgroundActive: active && active.textContent.replace(/\\s+/g, ' ').trim(),
                steps: steps.map((el) => (el.textContent || '').trim()),
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                padBottom: pad,
                guestPhone: Boolean(document.querySelector('[data-phone-pg-gate="guest"]')),
                lastTag: last && last.tagName,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(80)
        reach = page.evaluate(
            """() => {
              const gate = document.querySelector('[data-signed-in-pg-gate]');
              const last = gate && gate.lastElementChild;
              const tabs = document.querySelector('.mobile-tabbar');
              const lr = last.getBoundingClientRect();
              const tr = tabs.getBoundingClientRect();
              return { lastBottom: lr.bottom, tabTop: tr.top };
            }"""
        )
        n_before = len(requests)
        page.locator("[data-signed-in-pg-gate] > .pg-actions a.pg-btn").click()
        page.wait_for_url("**/playground?stage=plans", timeout=8000)
        extra = requests[n_before:]
        after = page.evaluate(
            """() => ({
              path: location.pathname,
              search: location.search,
              stage: document.querySelector('[data-signed-in-pg-gate]')
                && document.querySelector('[data-signed-in-pg-gate]').getAttribute('data-pg-gate-stage'),
              continueBtn: Boolean(document.querySelector('[data-pg-plan-continue]')),
            })"""
        )
        browser.close()

    assert geo["present"] is True
    assert geo["stage"] == "intro"
    assert geo["title"] == INTRO_TITLE
    assert geo["lede"] == INTRO_BODY
    assert geo["ctaText"] == INTRO_CTA
    assert geo["ctaHref"] == PLAYGROUND_PLANS_PATH
    assert geo["ctaWidth"] >= 300
    assert geo["ctaHeight"] >= 44
    assert geo["plans"] is False
    assert geo["continueBtn"] is False
    assert geo["headerDisplay"] == "none"
    assert geo["tabsDisplay"] != "none"
    assert geo["tabLabels"] == ["Today", "Browse", "Playground", "Calendar", "Profile"]
    assert geo["tabHrefs"] == [
        "/dashboard",
        "/browse",
        "/playground",
        "/calendar",
        "/profile",
    ]
    assert geo["playgroundActive"] == "Playground"
    assert geo["steps"] == list(GUEST_PG_STEPS)
    assert geo["overflow"] is False
    assert geo["guestPhone"] is False
    assert "60px" in geo["padBottom"] or "88px" in geo["padBottom"]
    assert reach["lastBottom"] <= reach["tabTop"] + 8
    assert after["path"] == home_path()
    assert after["search"] == "?stage=plans"
    assert after["stage"] == "plans"
    assert after["continueBtn"] is False
    assert not any("/billing/subscriptions" in item for item in extra)
    assert not any(item.startswith("POST ") for item in extra)
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_signed_in_playground_gate_screen03_plans_390x844(
    tmp_path: Path,
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_signed_in_playground_gate_screen03_plans_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        context.add_cookies(_cookie(session, origin))
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
              const tabs = document.querySelector('.mobile-tabbar');
              const note = gate && gate.querySelector('.pg-note');
              return {
                stage: gate && gate.getAttribute('data-pg-gate-stage'),
                tiers: cards.map((el) => el.getAttribute('data-tier')),
                names: cards.map((el) =>
                  (el.querySelector('.pg-plan-name') || {}).textContent
                ),
                prices: cards.map((el) =>
                  ((el.querySelector('.pg-plan-price') || {}).textContent || '')
                    .replace(/\\s+/g, ' ').trim()
                ),
                selected: Boolean(document.querySelector('[data-pg-plan-selected]')),
                continue: Boolean(document.querySelector('[data-pg-plan-continue]')),
                introCta: Boolean(gate && gate.querySelector(':scope > .pg-actions a.pg-btn')),
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
                note: note && note.textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(80)
        reach = page.evaluate(
            """() => {
              const note = document.querySelector('[data-signed-in-pg-gate] .pg-note');
              const last = note || document.querySelector('[data-signed-in-pg-gate]').lastElementChild;
              const tabs = document.querySelector('.mobile-tabbar');
              const lr = last.getBoundingClientRect();
              const tr = tabs.getBoundingClientRect();
              return { lastBottom: lr.bottom, tabTop: tr.top, note: Boolean(note) };
            }"""
        )
        page.locator('[data-pg-plans] [data-tier="plus"]').click()
        page.wait_for_url("**/playground?stage=plans&tier=plus", timeout=8000)
        selected = page.evaluate(
            """() => ({
              search: location.search,
              continueText: document.querySelector('[data-pg-plan-continue]')
                && document.querySelector('[data-pg-plan-continue]').textContent.trim(),
            })"""
        )
        browser.close()

    assert geo["stage"] == "plans"
    assert geo["tiers"] == ["plus", "pro", "max"]
    assert [name.strip() for name in geo["names"]] == ["Plus", "Pro", "Max"]
    assert any("₹199" in price for price in geo["prices"])
    assert any("₹399" in price for price in geo["prices"])
    assert any("₹1199" in price for price in geo["prices"])
    assert geo["selected"] is False
    assert geo["continue"] is False
    assert geo["introCta"] is False
    assert geo["tabsDisplay"] != "none"
    assert geo["overflow"] is False
    assert geo["note"] and "GST" in geo["note"]
    assert "₹199" in geo["note"]
    assert reach["note"] is True
    assert reach["lastBottom"] <= reach["tabTop"] + 8
    assert selected["search"] == "?stage=plans&tier=plus"
    assert selected["continueText"] == "Continue with Plus"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_signed_in_playground_gate_screen03_plus_selected_390x844(
    tmp_path: Path,
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = (
        artifact_dir / "phone_signed_in_playground_gate_screen03_plus_selected_390x844.png"
    )
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        context.add_cookies(_cookie(session, origin))
        page = context.new_page()
        page.emulate_media(color_scheme="light")
        page.add_init_script(
            """() => { try { localStorage.setItem('cm-theme', 'light'); } catch (e) {} }"""
        )
        requests: list[str] = []
        page.on("request", lambda req: requests.append(f"{req.method} {req.url}"))
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
              const tabs = document.querySelector('.mobile-tabbar');
              const href = cont && (cont.getAttribute('href')
                || cont.closest('a') || cont.closest('form'));
              return {
                tier: selected && selected.getAttribute('data-tier'),
                pressed: selected && selected.getAttribute('aria-pressed'),
                continueText: cont && (cont.textContent || '').trim(),
                continueType: cont && cont.getAttribute('type'),
                continueTag: cont && cont.tagName,
                continueHref: cont && cont.getAttribute('href'),
                wrapped: Boolean(href),
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                overflow: document.documentElement.scrollWidth
                  > document.documentElement.clientWidth,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(80)
        reach = page.evaluate(
            """() => {
              const cont = document.querySelector('[data-pg-plan-continue]');
              const tabs = document.querySelector('.mobile-tabbar');
              const lr = cont.getBoundingClientRect();
              const tr = tabs.getBoundingClientRect();
              return { lastBottom: lr.bottom, tabTop: tr.top };
            }"""
        )
        n_before = len(requests)
        page.locator("[data-pg-plan-continue]").click()
        page.wait_for_timeout(250)
        page.locator("[data-pg-plan-continue]").focus()
        page.keyboard.press("Enter")
        page.wait_for_timeout(250)
        extra = requests[n_before:]
        stayed = page.evaluate(
            """() => ({ path: location.pathname, search: location.search })"""
        )
        browser.close()

    assert geo["tier"] == "plus"
    assert geo["pressed"] == "true"
    assert geo["continueText"] == "Continue with Plus"
    assert geo["continueType"] == "button"
    assert geo["continueTag"] == "BUTTON"
    assert geo["continueHref"] is None
    assert geo["wrapped"] is False
    assert geo["tabsDisplay"] != "none"
    assert geo["overflow"] is False
    assert reach["lastBottom"] <= reach["tabTop"] + 8
    assert stayed["path"] == home_path()
    assert stayed["search"] == "?stage=plans&tier=plus"
    assert not any(item.startswith("POST ") for item in extra)
    assert not any("/billing" in item for item in extra)
    assert not any("/checkout" in item for item in extra)
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_signed_in_playground_gate_screen03_desktop_regression_1280(
    tmp_path: Path,
) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = (
        artifact_dir
        / "phone_signed_in_playground_gate_screen03_desktop_regression_1280.png"
    )
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
        context.add_cookies(_cookie(session, origin))
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
              const tabs = document.querySelector('.mobile-tabbar');
              const header = document.querySelector('.site-header');
              const cta = gate && gate.querySelector(':scope > .pg-actions .pg-btn');
              const style = gate ? getComputedStyle(gate) : null;
              const status = document.querySelector('.account-menu-btn-status');
              return {
                present: Boolean(gate),
                stage: gate && gate.getAttribute('data-pg-gate-stage'),
                title: gate && gate.querySelector('#pg-gate-title')
                  && gate.querySelector('#pg-gate-title').textContent.trim(),
                ctaText: cta && cta.textContent.trim(),
                ctaHref: cta && cta.getAttribute('href'),
                display: style && style.display,
                columns: style && style.gridTemplateColumns,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                status: status && status.textContent.trim(),
                continueBtn: Boolean(document.querySelector('[data-pg-plan-continue]')),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["present"] is True
    assert geo["stage"] == "intro"
    assert geo["title"] == INTRO_TITLE
    assert geo["ctaText"] == INTRO_CTA
    assert geo["ctaHref"] == PLAYGROUND_PLANS_PATH
    assert geo["display"] == "grid"
    assert geo["columns"] and "300px" in geo["columns"]
    assert geo["tabsDisplay"] == "none"
    assert geo["headerDisplay"] != "none"
    assert geo["status"] == "Free account"
    assert geo["continueBtn"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_device_limit_hard_gate_keeps_tabbar_hidden(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    inner = getattr(app.state.device_service, "inner", app.state.device_service)
    for index in range(2):
        access = inner.ensure_current_device(
            USER,
            mint_installation_token(),
            auth_session_id=f"seed-sess-{index}",
            commercially_eligible=True,
        )
        assert access.current_device_registered is True
    session = client.cookies.get(SESSION_COOKIE_NAME)
    port, _server = _serve(app)
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
        context.add_cookies(_cookie(session, origin))
        page = context.new_page()
        page.goto(f"{origin}/playground", wait_until="networkidle")
        geo = page.evaluate(
            """() => {
              const tabs = document.querySelector('.mobile-tabbar');
              const gate = document.querySelector('[data-signed-in-pg-gate]');
              const shell = document.querySelector('.PlaygroundShell');
              return {
                signedIn: Boolean(gate),
                reason: shell && shell.getAttribute('data-playground-gate'),
                hard: shell && shell.getAttribute('data-hard-gate'),
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
              };
            }"""
        )
        browser.close()

    assert geo["signedIn"] is False
    assert geo["reason"] == "device_limit"
    assert geo["hard"] == "true"
    assert geo["tabsDisplay"] == "none"
