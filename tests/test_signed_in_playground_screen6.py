"""Signed-in desktop Playground home Screen 06 (CTA map signedIn/06-screen).

Authorized: ChatGPT. Authenticated multiuser GET /playground desktop Gate
for a non-subscriber only. Subscriber home, phone Gate, guest intro, and
accepted screens 01–05 stay unchanged. View Playground plans keeps
/billing/subscriptions. Copy is the existing Gate, not the prototype title.
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
from constitution_memorizer.playground.view import PLAYGROUND_BILLING_PATH
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
USER = UUID("11111111-1111-4111-8111-111111111111")
LEDE = "Playground adds structured learning for laws."
HOW_TITLES = (
    "Choose your laws each month",
    "Progress never disappears",
    "Next month, decide what to keep",
    "Read the law, verbatim",
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


def _subscribe(client: TestClient) -> None:
    client.app.state.subscriptions.create_subscription_record(
        USER,
        tier="plus",
        status="active",
        billing_period_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 10, 15, tzinfo=timezone.utc),
        is_current=True,
    )


def _gate(html: str) -> str:
    return html.split('data-signed-in-pg-gate', 1)[1].split("</section>", 1)[0]


def test_signed_in_non_subscriber_reuses_existing_gate(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/playground").text
    assert 'data-playground-gate="not_subscribed"' in html
    assert "data-signed-in-pg-gate" in html
    assert 'class="EntitlementGate"' in html
    assert 'data-hard-gate="true"' in html
    assert "data-guest-pg-intro" not in html
    gate = _gate(html)
    assert ">Unlock Playground<" in gate
    assert LEDE in gate
    assert ">View Playground plans<" in gate
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in gate
    assert PLAYGROUND_BILLING_PATH == "/billing/subscriptions"
    assert "How Playground works" in gate
    for title in HOW_TITLES:
        assert title in gate
    assert "Included with your account" in gate
    assert "complete Constitution" in gate
    assert "Sign in to use Playground" not in gate
    assert "Sign in to build your law-learning Playground." not in gate
    assert "Your Playground is paused" not in gate
    assert "Payment retries have stopped" not in gate
    assert "Resume Playground" not in gate
    assert "Browse laws" not in gate
    assert "LawCard" not in gate
    assert "RosterCapacity" not in gate
    assert ">Add to Playground<" not in gate
    assert 'href="/laws"' not in gate


def test_subscriber_keeps_existing_playground_home(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    html = client.get("/playground").text
    assert "data-signed-in-pg-gate" not in html
    assert 'class="EntitlementGate"' not in html
    assert "pg-home-title" in html
    assert "My Playground" in html
    assert "Browse laws" in html
    assert ">Unlock Playground<" not in html
    assert ">View Playground plans<" not in html
    # Header may include the Free account label in the DOM; Screen 06 CSS
    # hides it on the subscriber home.


def test_guest_playground_intro_is_unchanged(tmp_path: Path) -> None:
    html = TestClient(_mu_app(tmp_path / "guest")).get("/playground").text
    assert "data-guest-pg-intro" in html
    assert "data-signed-in-pg-gate" not in html
    assert "Sign in to build your law-learning Playground." in html


def test_signed_in_pg_gate_does_not_touch_accepted_screens() -> None:
    assert "data-signed-in-pg-gate" not in ADD.read_text(encoding="utf-8")
    assert "data-signed-in-add-desktop" in ADD.read_text(encoding="utf-8")
    assert "data-signed-in-pg-gate" not in HOME.read_text(encoding="utf-8")
    assert "pg-home-title" in HOME.read_text(encoding="utf-8")
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-guest-landing="desktop"' in landing
    browse = BROWSE.read_text(encoding="utf-8")
    assert "data-signed-in-browse-strip" in browse
    laws = LAWS.read_text(encoding="utf-8")
    assert "data-signed-in-laws-desktop" in laws
    bare = BARE.read_text(encoding="utf-8")
    assert "data-signed-in-bareact-desktop" in bare
    css = STYLES.read_text(encoding="utf-8")
    headband = css.split(
        "[data-signed-in-bareact-desktop] .guest-bareact-headband {", 1
    )[1].split("}", 1)[0]
    assert "12px 40px 14px" in headband
    assert "position: absolute" not in css.split("/* R1 desktop shell", 1)[1]
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-signed-in-pg-gate" not in mobile
    pg_css = PG_CSS.read_text(encoding="utf-8")
    signed_title = pg_css.split(
        "[data-signed-in-add-desktop] .signed-add-title {", 1
    )[1].split("}", 1)[0]
    assert "font-size: 20px" in signed_title
    guest_title = pg_css.split(".guest-pg-title {", 1)[1].split("}", 1)[0]
    assert "font-size: 34px" in guest_title
    gate_html = GATE.read_text(encoding="utf-8")
    assert "data-signed-in-pg-gate" in gate_html
    assert "how_it_works()" in gate_html
    assert 'href="/laws"' not in gate_html
    assert "Browse laws" not in gate_html


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


def test_signed_in_pg_gate_1280_and_phone(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "signed_in_playground_screen6_1280.png"
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
              const nav = document.querySelector('.PrimaryTabs--top');
              const actions = gate && gate.querySelector(':scope > .pg-actions');
              const cta = actions && actions.querySelector('.pg-btn');
              const included = gate && gate.querySelector('.pg-included-card');
              const plans = gate && gate.querySelector('.pg-plan-stage');
              const how = gate && gate.querySelector('.HowPlaygroundWorks');
              const steps = how ? [...how.querySelectorAll('.HowPlaygroundWorks-row')] : [];
              const title = gate && gate.querySelector('#pg-gate-title');
              const lede = gate && gate.querySelector('.pg-lede');
              const howLinks = how ? [...how.querySelectorAll('a')] : [];
              const visibleNav = nav ? [...nav.querySelectorAll('.nav-link')].filter(
                (el) => getComputedStyle(el).display !== 'none' && el.offsetParent !== null
              ).map((el) => el.textContent.replace(/\\s+/g, ' ').trim()) : [];
              const titleBox = title && title.getBoundingClientRect();
              const ctaBox = cta && cta.getBoundingClientRect();
              const howBox = how && how.getBoundingClientRect();
              return {
                present: Boolean(gate),
                reason: gate && gate.getAttribute('data-playground-gate'),
                kicker: gate && gate.querySelector('.pg-eyebrow') &&
                  gate.querySelector('.pg-eyebrow').textContent.trim(),
                title: title && title.textContent.trim(),
                titleSize: title && getComputedStyle(title).fontSize,
                titleWeight: title && getComputedStyle(title).fontWeight,
                lede: lede && lede.textContent.trim(),
                ctaText: cta && cta.textContent.trim(),
                ctaHref: cta && cta.getAttribute('href'),
                ctaH: cta && cta.getBoundingClientRect().height,
                includedDisplay: included ? getComputedStyle(included).display : null,
                plansDisplay: plans ? getComputedStyle(plans).display : null,
                howDisplay: how ? getComputedStyle(how).display : null,
                stepCount: steps.length,
                stepTitles: steps.map(
                  (row) => (row.querySelector('strong') || row).textContent.trim().split('\\n')[0]
                ),
                howHasAnchors: howLinks.length > 0,
                navDisplay: nav ? getComputedStyle(nav).display : null,
                visibleNav,
                guestIntro: Boolean(document.querySelector('[data-guest-pg-intro]')),
                homeTitle: Boolean(document.querySelector('.pg-home-title')),
                lawCard: Boolean(document.querySelector('.LawCard')),
                browseLaws: gate && gate.innerText.includes('Browse laws'),
                paused: gate && gate.innerText.includes('Your Playground is paused'),
                halted: gate && gate.innerText.includes('Payment retries have stopped'),
                twoCol: Boolean(
                  titleBox && ctaBox && howBox &&
                  ctaBox.left > titleBox.right - 8 &&
                  howBox.top > titleBox.bottom - 4 &&
                  Math.abs(howBox.left - titleBox.left) < 8
                ),
                name: document.querySelector('.account-menu-btn-name') &&
                  document.querySelector('.account-menu-btn-name').textContent.trim(),
                status: document.querySelector('.account-menu-btn-status') &&
                  document.querySelector('.account-menu-btn-status').textContent.trim(),
                statusDisplay: document.querySelector('.account-menu-btn-status') &&
                  getComputedStyle(document.querySelector('.account-menu-btn-status')).display,
                markFilter: document.querySelector('.brand-mark') &&
                  getComputedStyle(document.querySelector('.brand-mark')).filter,
                avatarBg: document.querySelector('.account-avatar-fallback') &&
                  getComputedStyle(document.querySelector('.account-avatar-fallback')).backgroundColor,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator("[data-signed-in-pg-gate] > .pg-actions > .pg-btn").click()
        page.wait_for_url("**/billing/subscriptions**", timeout=8000)
        billing_path = page.evaluate("() => location.pathname")

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/playground", wait_until="networkidle")
        phone_geo = page.evaluate(
            """() => {
              const gate = document.querySelector('[data-signed-in-pg-gate]');
              const included = gate && gate.querySelector('.pg-included-card');
              const plans = gate && gate.querySelector('.pg-plan-stage');
              const cta = gate && gate.querySelector(':scope > .pg-actions > .pg-btn');
              const navTop = document.querySelector('.PrimaryTabs--top');
              const tabbar = document.querySelector('.PrimaryTabs--bottom');
              return {
                title: gate && gate.querySelector('#pg-gate-title') &&
                  gate.querySelector('#pg-gate-title').textContent.trim(),
                includedDisplay: included ? getComputedStyle(included).display : null,
                plansDisplay: plans ? getComputedStyle(plans).display : null,
                ctaHref: cta && cta.getAttribute('href'),
                navTopDisplay: navTop ? getComputedStyle(navTop).display : null,
                tabbarDisplay: tabbar ? getComputedStyle(tabbar).display : null,
                grid: gate ? getComputedStyle(gate).display : null,
              };
            }"""
        )
        browser.close()

    assert geo["present"] is True
    assert geo["reason"] == "not_subscribed"
    assert geo["kicker"] == "Playground"
    assert geo["title"] == "Unlock Playground"
    assert geo["titleSize"] == "34px"
    assert geo["titleWeight"] in ("500", "normal")
    assert geo["lede"] == LEDE
    assert geo["ctaText"] == "View Playground plans"
    assert geo["ctaHref"] == PLAYGROUND_BILLING_PATH
    assert geo["ctaH"] == pytest.approx(50, abs=2)
    assert geo["includedDisplay"] == "none"
    assert geo["plansDisplay"] == "none"
    assert geo["howDisplay"] != "none"
    assert geo["stepCount"] == 4
    assert geo["stepTitles"] == list(HOW_TITLES)
    assert geo["howHasAnchors"] is False
    assert geo["navDisplay"] == "none"
    assert geo["visibleNav"] == []
    assert geo["guestIntro"] is False
    assert geo["homeTitle"] is False
    assert geo["lawCard"] is False
    assert geo["browseLaws"] is False
    assert geo["paused"] is False
    assert geo["halted"] is False
    assert geo["twoCol"] is True
    assert geo["name"] == "Sanjay"
    assert geo["status"] == "Free account"
    assert geo["statusDisplay"] != "none"
    assert "invert" in (geo["markFilter"] or "")
    assert billing_path == PLAYGROUND_BILLING_PATH
    assert phone_geo["title"] == "Unlock Playground"
    assert phone_geo["includedDisplay"] != "none"
    assert phone_geo["plansDisplay"] != "none"
    assert phone_geo["ctaHref"] == PLAYGROUND_BILLING_PATH
    assert phone_geo["grid"] != "grid"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
