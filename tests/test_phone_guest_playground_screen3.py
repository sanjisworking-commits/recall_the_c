"""Phone Guest Playground tab Screen 03 (CTA map guest/03-screen, 390x844).

Authorized: ChatGPT. Guest GET /playground phone Gate (shared/05). Desktop
guest/06-screen intro, Free Gate 07, Plus/Expired/Halted homes, and Guest
04/05 stay unchanged.
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
from constitution_memorizer.entitlements.models import BLOCK_SIGN_IN_REQUIRED
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.view import PLAYGROUND_PLANS_PATH, gate_view
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.guest_playground_intro import (
    GUEST_GATE_FOOTNOTE,
    GUEST_GATE_VALUES,
    GUEST_PG_NOTE,
    GUEST_PG_SIGNIN_HREF,
    GUEST_PG_TITLE,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "src/constitution_memorizer/web/templates/playground_gate.html"
PARTIAL = ROOT / "src/constitution_memorizer/web/templates/partials/playground.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
USER = UUID("11111111-1111-4111-8111-111111111111")
LIVE = gate_view(reason=BLOCK_SIGN_IN_REQUIRED)
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
)
FREE_FORBIDDEN = (
    "View Playground plans",
    "data-pg-plans",
    "data-signed-in-pg-gate",
    "Your RecallC account already includes",
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


def _guest_app(tmp_path: Path):
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
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


def _guest_client(tmp_path: Path) -> TestClient:
    return TestClient(_guest_app(tmp_path))


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


def _phone(html: str) -> str:
    return html.split('data-phone-pg-gate="guest"', 1)[1].split("</section>", 1)[0]


def _tabs(html: str) -> str:
    return html.split("data-guest-pg-phone-tabs", 1)[1].split("</nav>", 1)[0]


def _facts(client: TestClient) -> dict:
    history = tuple(
        sorted(
            (row.id, row.status, row.tier, row.is_current)
            for row in client.app.state.subscriptions.list_subscription_history(USER)
        )
    )
    roster = getattr(client.app.state, "roster", None)
    overlay = getattr(client.app.state, "playground", None)
    return {
        "session": client.cookies.get(SESSION_COOKIE_NAME),
        "subscription": client.app.state.subscriptions.get_current_subscription(USER),
        "history": history,
        "active": tuple(
            sorted(i.law_id for i in roster.active_roster_items(USER))
        )
        if roster is not None
        else (),
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        )
        if overlay is not None
        else (),
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
    return calls


def test_phone_guest_playground_uses_live_gate_and_shared_values(
    tmp_path: Path,
) -> None:
    client = _guest_client(tmp_path)
    before = _facts(client)
    calls = _watch_provider(client)
    page = client.get("/playground")
    assert page.status_code == 200
    html = unescape(page.text)
    assert 'data-phone-pg-gate="guest"' in html
    assert 'data-playground-gate="sign_in_required"' in html
    assert LIVE.reason == BLOCK_SIGN_IN_REQUIRED
    assert 'data-hard-gate="true"' in html
    phone = _phone(html)
    assert LIVE.eyebrow in phone
    assert LIVE.eyebrow == "Playground"
    assert LIVE.title in phone
    assert LIVE.title == "Sign in to use Playground"
    assert LIVE.lines[0] in phone
    assert GUEST_PG_TITLE not in phone
    assert len(GUEST_GATE_VALUES) == 3
    for item in GUEST_GATE_VALUES:
        assert item.title in phone
        assert item.body in phone
    assert ">Sign in<" in phone
    assert "Create an account" in phone
    assert 'type="button"' in phone
    assert phone.count('type="button"') == 2
    assert 'href="' not in phone
    assert "<form" not in phone
    assert "<a " not in phone
    assert GUEST_PG_SIGNIN_HREF not in phone
    assert GUEST_GATE_FOOTNOTE in phone
    assert GUEST_GATE_FOOTNOTE in GUEST_PG_NOTE
    for phrase in FREE_FORBIDDEN:
        assert phrase not in phone, phrase
    assert "LawCard" not in phone
    assert PLAYGROUND_PLANS_PATH not in phone
    assert _facts(client) == before
    assert calls == []


def test_phone_guest_playground_buttons_are_handlerless_in_source() -> None:
    src = PARTIAL.read_text(encoding="utf-8")
    macro = src.split("guest_phone_gate", 1)[1].split("{% macro how_it_works", 1)[0]
    assert 'data-phone-pg-gate="guest"' in macro
    assert "shared/05" in macro
    assert 'type="button" class="pg-guest-gate-signin">Sign in<' in macro
    assert 'type="button" class="pg-guest-gate-create">Create an account<' in macro
    assert "login_href" not in macro
    assert "/login" not in macro
    assert "<form" not in macro
    assert "<a " not in macro
    gate = GATE.read_text(encoding="utf-8")
    assert "guest_phone_gate(" in gate
    assert "data-guest-pg-intro" in gate
    assert "data-signed-in-pg-gate" in gate


def test_phone_guest_five_tabs_playground_active(tmp_path: Path) -> None:
    html = _guest_client(tmp_path).get("/playground").text
    assert "data-guest-pg-phone-tabs" in html
    assert "mobile-tabbar is-guest" not in html
    tabs = _tabs(html)
    labels = []
    for label, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        labels.append(label)
        assert label in tabs
    assert labels == ["Today", "Browse", "Playground", "Calendar", "Profile"]
    playground = tabs.split('href="/playground"', 1)[1].split("</a>", 1)[0]
    assert "is-active" in playground
    assert 'aria-current="page"' in playground
    for href in ("/dashboard", "/browse", "/calendar", "/profile"):
        chunk = tabs.split(f'href="{href}"', 1)[1].split("</a>", 1)[0]
        assert "is-active" not in chunk
    ndps = _guest_client(tmp_path / "ndps").get("/laws/ndps").text
    assert "data-guest-pg-phone-tabs" not in ndps
    assert "data-guest-bareact-phone-tabs" in ndps


def test_phone_guest_playground_css_is_breakpoint_scoped() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    phone_block = css.split("shared/05 / guest/03-screen.", 1)[1].split(
        "@media (min-width: 561px)", 1
    )[0]
    assert "@media (max-width: 560px)" in phone_block
    assert '[data-phone-pg-gate="guest"]' in phone_block
    assert "pg-guest-gate-signin" in phone_block
    assert "pg-guest-gate-create" in phone_block
    hide = css.split("[data-phone-pg-gate=\"guest\"],", 1)[1].split("}", 1)[0]
    assert "display: none" in hide
    assert "data-guest-pg-phone-tabs" in hide or "data-guest-pg-phone-tabs" in css
    assert "playground.css?v=pg38" in BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg31" not in BASE.read_text(encoding="utf-8")
    assert "playground.css?v=pg30" not in BASE.read_text(encoding="utf-8")
    guest_title = css.split(".guest-pg-title {", 1)[1].split("}", 1)[0]
    assert "font-size: 34px" in guest_title


def test_free_plus_expired_halted_paused_stay_separate(tmp_path: Path) -> None:
    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/playground").text
    assert "data-phone-pg-gate" not in free_html
    assert "data-signed-in-pg-gate" in free_html
    assert "View Playground plans" in free_html
    assert "Create an account" not in free_html
    plans = free.get("/playground?stage=plans").text
    assert 'data-pg-gate-stage="plans"' in plans
    assert "data-pg-plans" in plans
    assert "data-phone-pg-gate" not in plans

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    plus_html = plus.get("/playground").text
    assert "data-phone-pg-gate" not in plus_html
    assert "data-guest-pg-intro" not in plus_html
    assert 'data-plus-playground="desktop"' in plus_html

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
    expired_html = expired.get("/playground").text
    assert "data-phone-pg-gate" not in expired_html
    assert "Create an account" not in expired_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/playground").text
    assert "data-phone-pg-gate" not in halted_html
    assert "Payment retries have stopped" in halted_html

    paused = TestClient(_mu_app(tmp_path / "paused"))
    _sign_in(paused)
    _subscribe(paused, status="paused")
    paused_html = paused.get("/playground").text
    assert "data-phone-pg-gate" not in paused_html
    assert "Create an account" not in paused_html


def test_phone_guest_playground_gets_are_mutation_free(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    before = _facts(client)
    calls = _watch_provider(client)
    assert before["session"] is None
    assert before["subscription"] is None
    for _ in range(3):
        page = client.get("/playground")
        assert page.status_code == 200
        assert _facts(client) == before
    assert calls == []


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


def test_phone_guest_playground_screen03_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_guest_playground_screen03_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        page = browser.new_page(
            viewport={"width": 390, "height": 844}, device_scale_factor=1
        )
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
              const phone = document.querySelector('[data-phone-pg-gate="guest"]');
              const intro = document.querySelector('[data-guest-pg-intro]');
              const header = document.querySelector('.site-header');
              const tabs = document.querySelector('[data-guest-pg-phone-tabs]');
              const signin = phone && phone.querySelector('.pg-guest-gate-signin');
              const create = phone && phone.querySelector('.pg-guest-gate-create');
              const values = phone ? [...phone.querySelectorAll('.pg-guest-gate-value strong')].map(
                (el) => el.textContent.trim()
              ) : [];
              const tabLinks = tabs ? [...tabs.querySelectorAll('a.mobile-tab')] : [];
              const active = tabs && tabs.querySelector('.mobile-tab.is-active');
              return {
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                introDisplay: intro ? getComputedStyle(intro).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                eyebrow: phone && phone.querySelector('.pg-guest-gate-kicker').textContent.trim(),
                title: phone && phone.querySelector('h1').textContent.trim(),
                lede: phone && phone.querySelector('.pg-guest-gate-lede').textContent.trim(),
                values,
                signin: {
                  tag: signin && signin.tagName,
                  type: signin && signin.getAttribute('type'),
                  href: signin && signin.getAttribute('href'),
                  text: signin && signin.textContent.trim(),
                  width: signin ? signin.getBoundingClientRect().width : 0,
                },
                create: {
                  tag: create && create.tagName,
                  type: create && create.getAttribute('type'),
                  href: create && create.getAttribute('href'),
                  text: create && create.textContent.trim(),
                  width: create ? create.getBoundingClientRect().width : 0,
                },
                note: phone && phone.querySelector('.pg-guest-gate-note')
                  && phone.querySelector('.pg-guest-gate-note').textContent.trim(),
                tabLabels: tabLinks.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabLinks.map((el) => el.getAttribute('href')),
                playgroundActive: active && active.textContent.replace(/\\s+/g, ' ').trim(),
                plans: phone && phone.innerText.includes('View Playground plans'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        n_before = len(requests)
        page.locator("[data-phone-pg-gate='guest'] .pg-guest-gate-signin").click()
        page.wait_for_timeout(250)
        after_signin = page.evaluate("() => location.pathname")
        page.locator("[data-phone-pg-gate='guest'] .pg-guest-gate-create").click()
        page.wait_for_timeout(250)
        after_create = page.evaluate("() => location.pathname")
        extra = requests[n_before:]
        browser.close()

    assert geo["phoneDisplay"] != "none"
    assert geo["introDisplay"] == "none"
    assert geo["headerDisplay"] == "none"
    assert geo["tabsDisplay"] != "none"
    assert geo["overflow"] is False
    assert geo["eyebrow"] == LIVE.eyebrow
    assert geo["title"] == LIVE.title
    assert geo["lede"] == LIVE.lines[0]
    assert geo["values"] == [item.title for item in GUEST_GATE_VALUES]
    assert geo["signin"]["tag"] == "BUTTON"
    assert geo["signin"]["type"] == "button"
    assert geo["signin"]["href"] is None
    assert geo["signin"]["text"] == "Sign in"
    assert geo["signin"]["width"] >= 300
    assert geo["create"]["tag"] == "BUTTON"
    assert geo["create"]["type"] == "button"
    assert geo["create"]["href"] is None
    assert geo["create"]["text"] == "Create an account"
    assert geo["create"]["width"] >= 300
    assert geo["note"] == GUEST_GATE_FOOTNOTE
    assert geo["tabLabels"] == ["Today", "Browse", "Playground", "Calendar", "Profile"]
    assert geo["tabHrefs"] == [
        "/dashboard",
        "/browse",
        "/playground",
        "/calendar",
        "/profile",
    ]
    assert geo["playgroundActive"] == "Playground"
    assert geo["plans"] is False
    assert after_signin == "/playground"
    assert after_create == "/playground"
    assert not any("/login" in item for item in extra)
    assert not any(item.startswith("POST ") for item in extra)
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_guest_playground_screen03_desktop_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _guest_app(tmp_path)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_guest_playground_screen03_desktop_regression_1280.png"
    origin = f"http://127.0.0.1:{port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", args=["--disable-lcd-text"])
        page = browser.new_page(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )
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
              const intro = document.querySelector('[data-guest-pg-intro]');
              const phone = document.querySelector('[data-phone-pg-gate="guest"]');
              const tabs = document.querySelector('[data-guest-pg-phone-tabs]');
              const header = document.querySelector('.site-header');
              const signin = intro && intro.querySelector('.guest-pg-signin');
              return {
                introDisplay: intro ? getComputedStyle(intro).display : null,
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                title: intro && intro.querySelector('.guest-pg-title').textContent.trim(),
                signinTag: signin && signin.tagName,
                signinHref: signin && signin.getAttribute('href'),
                createInIntro: intro && intro.innerText.includes('Create an account'),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["introDisplay"] != "none"
    assert geo["phoneDisplay"] == "none"
    assert geo["tabsDisplay"] == "none"
    assert geo["headerDisplay"] != "none"
    assert geo["title"] == GUEST_PG_TITLE
    assert geo["signinTag"] == "A"
    assert geo["signinHref"] == GUEST_PG_SIGNIN_HREF
    assert geo["createInIntro"] is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
