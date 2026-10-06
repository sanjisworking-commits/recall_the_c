"""Plus cohort desktop /billing/subscriptions Screen 07 (CTA map plus/07-screen).

Authorized: ChatGPT. Authenticated multiuser GET /billing/subscriptions with a
real active Plus EntitlementSnapshot. Catalog-backed cards, existing change
POST, Desktop.dc.html lede/tags/GST/explain. Guest pricing, Free, Pro/Max
current-plan, checkout, phone, and Plus Screens 01–06 stay on their own wrappers.
"""

from __future__ import annotations

from html import unescape
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    InMemorySessionStore,
)
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.subscriptions.catalog import list_subscription_products
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
MANAGE = ROOT / "src/constitution_memorizer/web/templates/subscription_manage.html"
CHECKOUT = ROOT / "src/constitution_memorizer/web/templates/subscription_checkout.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
ROUTES = ROOT / "src/constitution_memorizer/subscriptions/routes.py"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
USER = UUID("11111111-1111-4111-8111-111111111111")
CATALOG = {row.tier: row for row in list_subscription_products()}
INVENTED = (
    "Premium",
    "Unlock all",
    "Free plan",
    "device limit",
    "replacement",
)
PLUS_LEDE = (
    "Upgrades take effect immediately; downgrades apply from the 1st of next "
    "month. Laws already in your Playground keep working."
)
PLUS_GST = (
    "GST inclusive. Renews monthly until you cancel. Your Playground progress "
    "is never deleted."
)
PLUS_EXPLAIN = (
    "The plan only sets how many laws can be active in your Playground each "
    "calendar month. Subscribe on any day and this month's spaces open at once; "
    "a new set opens on the 1st. Laws already in your Playground keep working, "
    "and your progress is never deleted."
)
PLUS_INCLUDED = "Every Article · All six recall methods · Free."
PLUS_TAG = {
    "plus": "A steady pace — enough for one exam’s syllabus of Acts.",
    "pro": "Broad preparation across many Acts at once.",
    "max": "The whole law library, whenever you want it.",
}
CHANGE_PATH = "/billing/subscriptions/change"


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
    cancel_at_period_end: bool = False,
    provider_metadata: dict | None = None,
    billing: bool = True,
):
    kwargs: dict = {
        "tier": tier,
        "status": status,
        "is_current": True,
        "cancel_at_period_end": cancel_at_period_end,
    }
    if billing:
        kwargs["billing_period_start"] = datetime(2026, 9, 15, tzinfo=timezone.utc)
        kwargs["billing_period_end"] = datetime(2026, 10, 15, tzinfo=timezone.utc)
    if provider_metadata is not None:
        kwargs["provider_metadata"] = provider_metadata
    return client.app.state.subscriptions.create_subscription_record(USER, **kwargs)


def _plus_client(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    return client


def _header(html: str) -> str:
    return html.split("<header", 1)[-1].split("</header>", 1)[0]


def _desk(html: str) -> str:
    marker = 'data-plus-subscription="desktop"'
    assert marker in html
    return unescape(html.split(marker, 1)[1].split('class="panel purchase"', 1)[0])


def _card(desk: str, tier: str) -> str:
    marker = f'data-tier="{tier}"'
    chunk = desk.split(marker, 1)[1]
    for other in ("plus", "pro", "max"):
        if other == tier:
            continue
        nxt = f'data-tier="{other}"'
        if nxt in chunk:
            chunk = chunk.split(nxt, 1)[0]
            break
    return chunk.split("</article>", 1)[0]


def test_plus_subscriptions_reaches_manage_and_change_your_plan(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    page = client.get("/billing/subscriptions")
    assert page.status_code == 200
    html = page.text
    desk = _desk(html)
    header = _header(html)
    assert "Change your plan" in desk
    assert "Playground · Your plan" in desk
    assert PLUS_LEDE in desk
    assert PLUS_GST in desk
    assert PLUS_EXPLAIN in desk
    assert PLUS_INCLUDED in desk
    assert PLUS_TAG["plus"] in _card(desk, "plus")
    assert PLUS_TAG["pro"] in _card(desk, "pro")
    assert PLUS_TAG["max"] in _card(desk, "max")
    assert "Upgrade applies immediately." not in desk
    assert "Downgrade takes effect" not in desk
    assert "RecallC Plus" in header
    assert "Free account" not in header
    assert 'href="/playground" class="nav-link is-active"' in header
    assert 'data-plus-sub-current' in _card(desk, "plus")
    assert "Current plan" in _card(desk, "plus")
    assert 'action=' not in _card(desk, "plus")
    assert 'name="tier" value="plus"' not in desk
    assert f"₹{CATALOG['plus'].price_inr}" in desk
    assert f"₹{CATALOG['pro'].price_inr}" in desk
    assert f"₹{CATALOG['max'].price_inr:,}" in desk
    assert f"{CATALOG['plus'].playground_law_limit} laws active per month" in desk
    assert f"{CATALOG['pro'].playground_law_limit} laws active per month" in desk
    assert "Unlimited Playground" in desk
    pro = _card(desk, "pro")
    assert f'action="{CHANGE_PATH}"' in pro
    assert 'name="csrf_token"' in pro
    assert 'name="tier" value="pro"' in pro
    assert "Switch to Pro" in pro
    max_card = _card(desk, "max")
    assert f'action="{CHANGE_PATH}"' in max_card
    assert 'name="tier" value="max"' in max_card
    assert "Switch to Max" in max_card
    assert "Schedule " not in desk
    assert "The complete Constitution" in desk
    assert "Included with your account" in desk
    assert "independent of Playground plans" not in desk
    assert "Monthly. GST included. Cancel at the end of the current paid cycle." not in desk
    assert "Monthly. GST included. Cancel at the end of the current paid cycle." in html
    assert "class=\"panel purchase\"" in html
    assert "Playground plans" in html
    assert "Upgrade to Pro" in html
    for phrase in INVENTED:
        assert phrase not in desk, phrase
        assert phrase not in MANAGE.read_text(encoding="utf-8"), phrase


def test_plus_upgrade_posts_use_existing_change_route_with_csrf(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    client.get("/billing/subscriptions")
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf
    denied = client.post(
        CHANGE_PATH,
        data={"csrf_token": "nope", "tier": "pro"},
        follow_redirects=False,
    )
    assert denied.status_code == 403
    for tier in ("pro", "max"):
        resp = client.post(
            CHANGE_PATH,
            data={"csrf_token": csrf, "tier": tier},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/billing/subscriptions" in resp.headers["location"]


def test_guest_and_free_pricing_are_unchanged(tmp_path: Path) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest")).get("/billing/subscriptions").text
    assert 'data-plus-subscription="desktop"' not in guest
    assert "Change your plan" not in guest
    assert "₹199/month" in guest
    assert "₹399/month" in guest
    assert "₹1,199/month" in guest
    assert "Sign in to subscribe" in guest
    assert "GST included" in guest
    assert "Playground plans" in guest

    free_c = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free_c)
    free = free_c.get("/billing/subscriptions").text
    assert 'data-plus-subscription="desktop"' not in free
    assert "Change your plan" not in free
    assert "Subscribe to Plus" in free
    assert "₹199/month" in free
    assert "RecallC Plus" not in _header(free)


def test_pro_and_max_current_plan_are_not_plus_screen_07(tmp_path: Path) -> None:
    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/billing/subscriptions").text
    assert 'data-plus-subscription="desktop"' not in pro_html
    assert "Change your plan" not in pro_html
    assert "Current plan" in pro_html
    assert "Upgrade to Max" in pro_html
    assert "Switch to" not in pro_html

    max_c = TestClient(_mu_app(tmp_path / "max"))
    _sign_in(max_c)
    _subscribe(max_c, tier="max")
    max_html = max_c.get("/billing/subscriptions").text
    assert 'data-plus-subscription="desktop"' not in max_html
    assert "Change your plan" not in max_html
    assert "Current plan" in max_html
    assert "Upgrade to" not in max_html


def test_halted_expired_pending_are_not_plus_screen_07(tmp_path: Path) -> None:
    for status, needle in (
        ("halted", "Automatic retries have stopped"),
        ("expired", None),
        ("pending", "Payment retry in progress"),
    ):
        client = TestClient(_mu_app(tmp_path / status))
        _sign_in(client)
        _subscribe(client, status=status)
        html = client.get("/billing/subscriptions").text
        assert 'data-plus-subscription="desktop"' not in html
        assert "Change your plan" not in html
        if needle:
            assert needle in html


def test_plus_lifecycle_scheduled_and_cancelled_still_render(tmp_path: Path) -> None:
    cancelled = TestClient(_mu_app(tmp_path / "cancel"))
    _sign_in(cancelled)
    _subscribe(cancelled, cancel_at_period_end=True)
    cancel_html = cancelled.get("/billing/subscriptions").text
    cancel_desk = _desk(cancel_html)
    assert "Ends after the current paid cycle" in cancel_desk
    assert "Current paid period ends" in cancel_desk
    assert "Cancel at cycle end" not in cancel_desk

    scheduled = TestClient(_mu_app(tmp_path / "sched"))
    _sign_in(scheduled)
    _subscribe(scheduled, provider_metadata={"scheduled_tier": "pro"})
    sched_html = scheduled.get("/billing/subscriptions").text
    sched_desk = _desk(sched_html)
    assert "Scheduled change" in sched_desk
    assert "pro at cycle end" in sched_desk
    assert "Change your plan" in sched_desk


def test_plus_subscription_marker_uses_shared_predicate() -> None:
    manage = MANAGE.read_text(encoding="utf-8")
    assert "plus_subscription" in manage
    assert 'data-plus-subscription="desktop"' in manage
    assert "Change your plan" in manage
    assert "Playground plans" in manage
    assert 'action="/billing/subscriptions/change"' in manage
    assert "Switch to {{ product.display_name }}" in manage
    assert "Current plan" in manage
    assert "The complete Constitution" in manage
    routes = ROUTES.read_text(encoding="utf-8")
    assert "request_is_active_plus" in routes
    assert '"plus_subscription": request_is_active_plus(request)' in routes
    assert "def _card_limit_label" in routes
    assert "PLUS_DESK_LEDE" in routes
    assert "def _card_description" in routes
    assert PLUS_LEDE in routes
    assert PLUS_TAG["plus"] in routes
    assert PLUS_TAG["pro"] in routes
    assert PLUS_TAG["max"] in routes
    assert PLUS_GST in routes
    assert PLUS_EXPLAIN in routes
    assert PLUS_INCLUDED in routes
    assert "def request_is_active_plus" in DEPS.read_text(encoding="utf-8")
    assert 'snapshot.tier == "plus"' in DEPS.read_text(encoding="utf-8")
    base = BASE.read_text(encoding="utf-8")
    assert "plus_billing" in base
    assert "plus_subscription" in base
    assert "RecallC Plus" in base
    assert "playground.css?v=pg25" in base
    css = PG_CSS.read_text(encoding="utf-8")
    assert 'data-plus-subscription="desktop"' in css
    assert "plus-sub-card" in css
    assert ".plus-sub-tag" in css
    assert ".plus-sub-explain" in css
    assert "var(--rc-illustration)" in css
    assert "#3a3a38" not in css.split("[data-plus-subscription", 1)[-1]
    assert ".panel.purchase" in css
    checkout = CHECKOUT.read_text(encoding="utf-8")
    assert "data-plus-subscription" not in checkout
    assert "Change your plan" not in checkout
    assert "Opening secure checkout" in checkout
    for phrase in INVENTED:
        assert phrase not in manage, phrase


def test_plus_screen_07_does_not_touch_accepted_screens() -> None:
    assert "data-plus-subscription" not in LANDING.read_text(encoding="utf-8")
    assert "data-plus-subscription" not in BROWSE.read_text(encoding="utf-8")
    assert "data-plus-subscription" not in LAWS.read_text(encoding="utf-8")
    assert "data-plus-subscription" not in BARE.read_text(encoding="utf-8")
    assert "data-plus-subscription" not in ADD.read_text(encoding="utf-8")
    assert "data-plus-subscription" not in HOME.read_text(encoding="utf-8")
    assert "data-plus-subscription" not in GATE.read_text(encoding="utf-8")
    assert 'data-plus-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-plus-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-plus-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-plus-bareact="desktop"' in BARE.read_text(encoding="utf-8")
    assert 'data-plus-add="desktop"' in ADD.read_text(encoding="utf-8")
    assert 'data-plus-playground="desktop"' in HOME.read_text(encoding="utf-8")


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


def test_plus_subscriptions_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    row = _subscribe(client, billing=False)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "plus_subscription_screen07_1280.png"
    life_path = artifact_dir / "plus_subscription_screen07_scheduled_1280.png"
    origin = f"http://127.0.0.1:{port}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        context = browser.new_context(
            viewport={"width": 1280, "height": 900}, device_scale_factor=1
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
        page.goto(f"{origin}/billing/subscriptions", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-plus-subscription="desktop"]');
              const purchase = document.querySelector('.panel.purchase');
              const cards = [...document.querySelectorAll('[data-plus-subscription="desktop"] .plus-sub-card')];
              const current = document.querySelector('[data-plus-sub-current]');
              const title = document.querySelector('.plus-sub-title');
              const status = document.querySelector('.account-menu-btn-status');
              const included = document.querySelector('.plus-sub-included');
              const gstEl = document.querySelector('.plus-sub-gst');
              const lede = document.querySelector('.plus-sub-lede');
              const tags = [...document.querySelectorAll('[data-plus-subscription="desktop"] .plus-sub-tag')];
              const first = cards[0] && cards[0].getBoundingClientRect();
              const third = cards[2] && cards[2].getBoundingClientRect();
              const includedBox = included && included.getBoundingClientRect();
              const gstBox = gstEl && gstEl.getBoundingClientRect();
              const csDesk = desk && getComputedStyle(desk);
              const csPurchase = purchase && getComputedStyle(purchase);
              const csCurrent = current && getComputedStyle(current);
              const plusCta = current && current.querySelector('.plus-sub-cta');
              const body = desk && desk.innerText.replace(/\\s+/g, ' ');
              return {
                present: Boolean(desk),
                title: title && title.textContent.trim(),
                lede: lede && lede.textContent.trim(),
                tags: tags.map((el) => el.textContent.trim()),
                deskDisplay: csDesk && csDesk.display,
                purchaseDisplay: csPurchase && csPurchase.display,
                cardCount: cards.length,
                cardHeight: first && first.height,
                threeCol: first && third && Math.abs(first.y - third.y) < 16 && third.x > first.x,
                currentBorder: csCurrent && csCurrent.borderTopWidth,
                currentText: plusCta && plusCta.textContent.trim(),
                currentDisabled: plusCta && plusCta.disabled,
                plusForm: Boolean(current && current.querySelector('form')),
                switchPro: document.body.innerText.includes('Switch to Pro'),
                switchMax: document.body.innerText.includes('Switch to Max'),
                status: status && status.textContent.trim(),
                statusDisplay: status && getComputedStyle(status).display,
                navActive: document.querySelector('.PrimaryTabs--top .nav-link.is-active')
                  && document.querySelector('.PrimaryTabs--top .nav-link.is-active').textContent.replace(/\\s+/g, ' ').trim(),
                included: included && included.innerText.replace(/\\s+/g, ' ').trim(),
                gst: body && body.includes('GST inclusive'),
                gstBelowCards: Boolean(first && gstBox && gstBox.top >= first.bottom - 1),
                includedBelowGst: Boolean(gstBox && includedBox && includedBox.top >= gstBox.bottom - 1),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        assert geo["present"] is True
        assert geo["title"] == "Change your plan"
        assert geo["lede"] == PLUS_LEDE
        assert geo["tags"] == [PLUS_TAG["plus"], PLUS_TAG["pro"], PLUS_TAG["max"]]
        assert geo["deskDisplay"] != "none"
        assert geo["purchaseDisplay"] == "none"
        assert geo["cardCount"] == 3
        assert geo["threeCol"] is True
        assert geo["cardHeight"] >= 240
        assert geo["gstBelowCards"] is True
        assert geo["includedBelowGst"] is True
        assert geo["currentText"] == "Current plan"
        assert geo["currentDisabled"] is True
        assert geo["plusForm"] is False
        assert geo["switchPro"] is True
        assert geo["switchMax"] is True
        assert geo["status"] == "RecallC Plus"
        assert geo["statusDisplay"] != "none"
        assert "Playground" in (geo["navActive"] or "")
        assert "The complete Constitution" in (geo["included"] or "")
        assert PLUS_INCLUDED in (geo["included"] or "")
        assert geo["gst"] is True
        assert shot_path.exists() and shot_path.stat().st_size > 1000

        page.set_viewport_size({"width": 390, "height": 844})
        phone = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-plus-subscription="desktop"]');
              const purchase = document.querySelector('.panel.purchase');
              return {
                deskDisplay: desk && getComputedStyle(desk).display,
                purchaseDisplay: purchase && getComputedStyle(purchase).display,
                plans: purchase && purchase.innerText.includes('Playground plans'),
              };
            }"""
        )
        assert phone["deskDisplay"] == "none"
        assert phone["purchaseDisplay"] != "none"
        assert phone["plans"] is True

        page.set_viewport_size({"width": 1280, "height": 900})
        client.app.state.subscriptions.update_subscription_state(
            USER,
            row.id,
            provider_metadata={"scheduled_tier": "pro"},
        )
        page.goto(f"{origin}/billing/subscriptions", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        life = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-plus-subscription="desktop"]');
              return {
                present: Boolean(desk),
                scheduled: desk && desk.innerText.includes('Scheduled change'),
                tier: desk && desk.innerText.includes('pro at cycle end'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(life_path), full_page=False)
        assert life["present"] is True
        assert life["scheduled"] is True
        assert life["tier"] is True
        assert life_path.exists() and life_path.stat().st_size > 1000
        context.close()
        browser.close()
