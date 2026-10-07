"""Signed-in desktop Today Screen 08 (CTA map signedIn/08-screen).

Authorized: ChatGPT. Authenticated multiuser GET /dashboard desktop only.
Phone Today, Gate, and accepted screens 01–06 stay unchanged. Copy, routes,
and dashboard state stay existing. Playground path rows are not fabricated
for a non-subscriber.
"""

from __future__ import annotations

import socket
import threading
import time
from datetime import date, timedelta
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
from constitution_memorizer.progress.scheduler import ReminderEngine
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
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
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


def _engine(client: TestClient) -> ReminderEngine:
    engine = client.app.state.engine
    store = getattr(client.app.state, "session_store", None)
    sessions = getattr(store, "_sessions", None) if store is not None else None
    if sessions:
        newest = sorted(sessions.values(), key=lambda s: s.created_at)[-1]
        return engine.for_user(newest.user.id)
    return engine


def _make_due(client: TestClient, unit_ids: list[str]) -> None:
    eng = _engine(client)
    today = date.today()
    for offset, unit_id in enumerate(unit_ids):
        eng.repo.upsert_progress(
            eng.user_id,
            unit_id=unit_id,
            status="review",
            times_completed=1,
            last_completed=today - timedelta(days=1),
            next_revision=today - timedelta(days=len(unit_ids) - offset),
            interval_days=1,
        )
    eng._invalidate_progress_cache()


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _path_card(html: str) -> str:
    if "data-today-path-card" not in html:
        return ""
    return html.split("data-today-path-card", 1)[1].split("</div>", 1)[0]


def test_signed_in_free_today_marks_desktop_surface(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    html = client.get("/dashboard").text
    assert "data-signed-in-today" in html
    assert 'data-mscreen="today"' in html or "today" in html
    header = _header(html)
    assert 'href="/playground"' in header
    assert 'href="/browse"' in header
    assert 'href="/calendar"' in header
    assert 'href="/profile"' in header
    assert 'class="nav-link is-active"' in header
    assert 'aria-current="page"' in header
    assert ">Today<" in header
    assert 'href="/settings"' in html
    assert 'class="dash-avatar-link" href="/settings"' in html
    gate = client.get("/playground", follow_redirects=False)
    assert gate.status_code == 200
    assert 'data-playground-gate="not_subscribed"' in gate.text
    assert "data-signed-in-pg-gate" in gate.text


def test_signed_in_free_today_uses_real_state_not_stale_playground(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    first = client.get("/dashboard").text
    assert 'data-today-mode="firstrun"' in first
    assert "NDPS" not in first
    assert "Section 8" not in first
    assert 'data-today-source="playground"' not in first
    assert "/revision/start" not in first

    _make_due(client, ["clause-1", "clause-2"])
    html = client.get("/dashboard").text
    assert 'data-today-mode="revision"' in html
    assert 'action="/revision/start"' in html
    assert "data-revision-start" in html
    assert "revision" in html.lower()
    path = _path_card(html)
    assert 'data-today-unit="clause-1"' in path
    assert 'data-today-unit="clause-2"' in path
    assert 'data-today-source="playground"' not in html
    assert "NDPS" not in html
    assert "Section 8" not in html
    assert "Section 9" not in html
    assert "Article 19(1)(a)" not in html
    today = date.today()
    label = f"{today.strftime('%A')} {today.day} {today.strftime('%B')}"
    assert label in html
    assert "Sunday 6 September" not in html or today == date(2026, 9, 6)
    settings = client.get("/settings", follow_redirects=False)
    assert settings.status_code == 200


def test_signed_in_today_does_not_touch_accepted_screens() -> None:
    dash = DASH.read_text(encoding="utf-8")
    assert "data-signed-in-today" in dash
    assert 'action="/revision/start"' in dash
    assert 'href="/settings"' in dash
    assert "NDPS Act" not in dash
    assert "Good morning." not in dash
    assert "4-day streak" not in dash

    assert "data-signed-in-today" not in ADD.read_text(encoding="utf-8")
    assert "data-signed-in-add-desktop" in ADD.read_text(encoding="utf-8")
    assert "data-signed-in-today" not in HOME.read_text(encoding="utf-8")
    assert "data-signed-in-today" not in GATE.read_text(encoding="utf-8")
    assert "data-signed-in-pg-gate" in GATE.read_text(encoding="utf-8")
    landing = LANDING.read_text(encoding="utf-8")
    assert 'data-guest-landing="desktop"' in landing
    assert "data-signed-in-browse-strip" in BROWSE.read_text(encoding="utf-8")
    assert "data-signed-in-laws-desktop" in LAWS.read_text(encoding="utf-8")
    assert "data-signed-in-bareact-desktop" in BARE.read_text(encoding="utf-8")

    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-signed-in-today" not in mobile
    phone_cta = mobile.split(
        "body[data-mscreen=\"today\"] .rc-path-node.is-current .rc-path-cta {", 1
    )[1].split("}", 1)[0]
    assert "width: 100%" in phone_cta
    assert "min-height: 44px" in phone_cta

    pg_css = PG_CSS.read_text(encoding="utf-8")
    signed_gate_title = pg_css.split(
        ".PlaygroundShell .EntitlementGate[data-signed-in-pg-gate] h1 {", 1
    )[1].split("}", 1)[0]
    assert "font-size: 28px" in signed_gate_title

    css = STYLES.read_text(encoding="utf-8")
    r1 = css.split("/* R1 desktop shell", 1)[1].split(
        "/* Signed-in desktop Today", 1
    )[0]
    assert "position: absolute" not in r1
    signed = css.split("/* Signed-in desktop Today", 1)[1]
    assert "minmax(260px, 380px)" in signed
    assert "height: 48px" in signed
    assert "width: 72px" in signed
    headband = css.split(
        "[data-signed-in-bareact-desktop] .guest-bareact-headband {", 1
    )[1].split("}", 1)[0]
    assert "12px 40px 14px" in headband


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


def test_signed_in_today_1280_and_phone(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _make_due(client, ["clause-1", "clause-2"])
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "signed_in_today_screen8_1280.png"
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
        page.goto(f"{origin}/dashboard", wait_until="networkidle")
        page.evaluate(
            """() => { document.documentElement.setAttribute('data-theme', 'light'); }"""
        )
        geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-signed-in-today]');
              const nav = document.querySelector('.PrimaryTabs--top');
              const today = nav && [...nav.querySelectorAll('.nav-link')].find(
                (el) => (el.textContent || '').trim() === 'Today'
              );
              const playground = nav && [...nav.querySelectorAll('.nav-link')].find(
                (el) => (el.textContent || '').trim() === 'Playground'
              );
              const hero = document.querySelector('.dash-due.is-due');
              const path = document.querySelector('[data-today-path-card]');
              const cta = hero && hero.querySelector('[data-revision-start]');
              const form = hero && hero.querySelector('form.dash-revision-form');
              const ring = hero && hero.querySelector('.rc-goal-ring');
              const frac = hero && hero.querySelector('.rc-goal-frac');
              const dateEl = document.querySelector('[data-today-date]');
              const sub = document.querySelector('.dash-subtext');
              const settings = document.querySelector('.dash-avatar-link');
              const strip = document.querySelector('.dash-strip');
              const sources = [...document.querySelectorAll('[data-today-source]')].map(
                (el) => el.getAttribute('data-today-source')
              );
              const pathText = path ? (path.innerText || '') : '';
              const titleBox = hero && hero.getBoundingClientRect();
              const pathBox = path && path.getBoundingClientRect();
              const ctaBox = cta && cta.getBoundingClientRect();
              const todayActive = today && (
                today.classList.contains('is-active') ||
                today.getAttribute('aria-current') === 'page'
              );
              return {
                present: Boolean(panel),
                todayActive,
                playgroundHref: playground && playground.getAttribute('href'),
                settingsHref: settings && settings.getAttribute('href'),
                mode: hero && hero.getAttribute('data-today-mode'),
                formAction: form && form.getAttribute('action'),
                ctaText: cta && (cta.textContent || '').replace(/\\s+/g, ' ').trim(),
                ctaH: ctaBox && ctaBox.height,
                ringW: ring && ring.getBoundingClientRect().width,
                fracDisplay: frac ? getComputedStyle(frac).display : null,
                dateText: dateEl && dateEl.textContent.trim(),
                dateDisplay: dateEl ? getComputedStyle(dateEl).display : null,
                subDisplay: sub ? getComputedStyle(sub).display : null,
                twoCol: Boolean(
                  titleBox && pathBox && pathBox.left > titleBox.right - 8
                ),
                heroW: titleBox && titleBox.width,
                stripDisplay: strip ? getComputedStyle(strip).display : null,
                sources,
                hasNdps: /NDPS|Section 8|Section 9/.test(pathText),
                navToday: today && (today.textContent || '').trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator('.PrimaryTabs--top .nav-link', has_text="Playground").click()
        page.wait_for_url("**/playground**", timeout=8000)
        playground_html = page.content()
        playground_path = page.evaluate("() => location.pathname")

        page.goto(f"{origin}/dashboard", wait_until="networkidle")
        page.locator(".dash-avatar-link").click()
        page.wait_for_url("**/settings**", timeout=8000)
        settings_path = page.evaluate("() => location.pathname")

        page.goto(f"{origin}/dashboard", wait_until="networkidle")
        page.locator("[data-revision-start]").click()
        page.wait_for_url("**/learn/**", timeout=8000)
        learn_path = page.evaluate("() => location.pathname")

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/dashboard", wait_until="networkidle")
        phone_geo = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-signed-in-today]');
              const top = document.querySelector('.dash-top');
              const hero = document.querySelector('.dash-due.is-due');
              const path = document.querySelector('[data-today-path-card]');
              const dateEl = document.querySelector('[data-today-date]');
              const cta = path && path.querySelector('.rc-path-cta');
              const titleBox = hero && hero.getBoundingClientRect();
              const pathBox = path && path.getBoundingClientRect();
              return {
                present: Boolean(panel),
                topDisplay: top ? getComputedStyle(top).display : null,
                stacked: Boolean(
                  titleBox && pathBox && pathBox.top > titleBox.bottom - 8
                ),
                dateDisplay: dateEl ? getComputedStyle(dateEl).display : null,
                pathCtaWidth: cta ? cta.getBoundingClientRect().width : null,
                heroWidth: titleBox && titleBox.width,
              };
            }"""
        )
        browser.close()

    assert geo["present"] is True
    assert geo["todayActive"] is True
    assert geo["playgroundHref"] == "/playground"
    assert geo["settingsHref"] == "/settings"
    assert geo["mode"] == "revision"
    assert geo["formAction"] == "/revision/start"
    assert geo["ctaText"].startswith("Start revision") or "left" in (geo["ctaText"] or "")
    assert geo["ctaH"] == pytest.approx(48, abs=2)
    assert geo["ringW"] == pytest.approx(72, abs=2)
    assert geo["fracDisplay"] not in (None, "none")
    assert geo["dateDisplay"] not in (None, "none")
    assert geo["subDisplay"] == "none"
    assert geo["twoCol"] is True
    assert geo["heroW"] == pytest.approx(380, abs=24)
    assert geo["stripDisplay"] == "none"
    assert geo["sources"]
    assert set(geo["sources"]) == {"constitution"}
    assert geo["hasNdps"] is False
    assert playground_path.rstrip("/") == "/playground"
    assert 'data-playground-gate="not_subscribed"' in playground_html
    assert settings_path.rstrip("/") == "/settings"
    assert "/learn/" in learn_path
    assert phone_geo["present"] is True
    assert phone_geo["topDisplay"] == "block"
    assert phone_geo["stacked"] is True
    assert phone_geo["dateDisplay"] == "none"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
