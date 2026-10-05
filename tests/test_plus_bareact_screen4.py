"""Plus cohort desktop NDPS Bare Act head Screen 04 (CTA map plus/04-screen).

Authorized: ChatGPT. Authenticated multiuser GET /laws/ndps with a real
active Plus EntitlementSnapshot. Same accepted Bare Act head as Free
Screen 04. CTA cluster is existing Playground membership, not a mock.
RecallC Plus header is Screen 04 NDPS only — not a /laws/{id} leak.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import socket
import threading
import time
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
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
APP = ROOT / "src/constitution_memorizer/web/app.py"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
USER = UUID("11111111-1111-4111-8111-111111111111")
INVENTED = (
    "Premium",
    "Unlimited",
    "renews",
    "Unlock all",
    "Free plan",
    "device limit",
    "replacement",
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


def _seed_ndps_roster(client: TestClient) -> None:
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


def _desk(html: str) -> str:
    return html.split("data-signed-in-bareact-desktop", 1)[1].split(
        "data-bareact-phone", 1
    )[0]


def test_plus_bareact_add_path_for_eligible_law_not_in_playground(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    html = client.get("/laws/ndps").text
    assert 'data-plus-bareact="desktop"' in html
    desk = _desk(html)
    header = _header(html)
    assert NDPS_GUEST_KICKER in desk
    assert f">{NDPS_GUEST_TITLE}<" in desk
    assert NDPS_GUEST_META in desk
    assert 'class="guest-bareact-back" href="/laws"' in desk
    assert 'data-pg-kind="eligible_to_add"' in desk
    assert "+ Add to Playground" in desk
    assert f'href="{add_path("ndps")}"' in desk
    assert "data-pg-sheet" in desk
    assert "Already in Playground" not in desk
    assert ">Sections<" not in desk
    assert 'class="signed-bareact-continue"' not in desk
    assert "Subscribe to use Playground" not in desk
    assert "Sign in to use Playground" not in desk
    assert "RecallC Plus" in header
    assert "Free account" not in header
    for phrase in INVENTED:
        assert phrase not in desk, phrase
    for row in NDPS_GUEST_ROWS:
        assert row.title in desk
    assert 'href="/laws/ndps/section/' not in desk
    preview = client.post(add_path("ndps"), data=_csrf(client), follow_redirects=False)
    assert preview.status_code in {200, 303}


def test_plus_bareact_already_active_uses_real_membership(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    html = client.get("/laws/ndps").text
    desk = _desk(html)
    assert 'data-plus-bareact="desktop"' in html
    assert "Already in Playground" in desk
    assert 'data-pg-kind="already_active"' in desk
    assert ">Sections<" in desk
    assert f'href="{sections_path("ndps")}"' in desk
    assert f'class="signed-bareact-continue" href="{home_path()}"' in desk
    assert ">Continue<" in desk
    assert "+ Add to Playground" not in desk
    assert "Subscribe to use Playground" not in desk
    assert "RecallC Plus" in _header(html)


def test_plus_bareact_roster_membership_is_not_free_spoof(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    _seed_ndps_roster(client)
    desk = _desk(client.get("/laws/ndps").text)
    assert "Already in Playground" in desk
    assert 'data-pg-kind="already_active"' in desk
    assert "Subscribe to use Playground" not in desk
    assert 'data-pg-kind="subscribe"' not in desk
    assert ">Continue<" in desk


def test_free_and_guest_bareact_unchanged(tmp_path: Path) -> None:
    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    _seed_ndps_roster(free)
    free_html = free.get("/laws/ndps").text
    assert 'data-plus-bareact="desktop"' not in free_html
    free_desk = _desk(free_html)
    assert "Subscribe to use Playground" in free_desk
    assert "Already in Playground" not in free_desk
    assert "Free account" in _header(free_html)
    assert "RecallC Plus" not in _header(free_html)

    guest_html = TestClient(_mu_app(tmp_path / "guest")).get("/laws/ndps").text
    assert 'data-plus-bareact="desktop"' not in guest_html
    assert "data-guest-bareact-desktop" in guest_html
    assert "data-signed-in-bareact-desktop" not in guest_html
    assert "Sign in to use Playground" in guest_html
    assert "RecallC Plus" not in guest_html


def test_halted_expired_and_pro_are_not_plus_screen_04(tmp_path: Path) -> None:
    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/laws/ndps").text
    assert 'data-plus-bareact="desktop"' not in halted_html
    assert "RecallC Plus" not in _header(halted_html)

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(expired, status="expired")
    expired_html = expired.get("/laws/ndps").text
    assert 'data-plus-bareact="desktop"' not in expired_html
    assert "RecallC Plus" not in _header(expired_html)

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/laws/ndps").text
    assert 'data-plus-bareact="desktop"' not in pro_html
    assert "RecallC Plus" not in _header(pro_html)
    assert "Free account" in _header(pro_html)


def test_plus_bareact_header_does_not_leak_to_other_law_routes(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    ndps = client.get("/laws/ndps")
    assert "RecallC Plus" in _header(ndps.text)
    bns = client.get("/laws/bns")
    assert "RecallC Plus" not in _header(bns.text)
    assert "Free account" in _header(bns.text)
    assert 'data-plus-bareact="desktop"' not in bns.text
    laws = client.get("/laws")
    assert "RecallC Plus" in _header(laws.text)
    assert 'data-plus-laws="desktop"' in laws.text
    playground = client.get("/playground")
    assert "RecallC Plus" in _header(playground.text)
    assert 'data-plus-playground="desktop"' in playground.text


def test_plus_bareact_marker_uses_shared_predicate() -> None:
    bare = BARE.read_text(encoding="utf-8")
    assert "plus_bareact" in bare
    assert 'data-plus-bareact="desktop"' in bare
    assert "data-signed-in-bareact-desktop" in bare
    assert 'href="/laws"' in bare
    assert "+ Add to Playground" not in bare
    base = BASE.read_text(encoding="utf-8")
    assert "plus_bareact" in base
    assert "path == '/laws/ndps'" in base
    assert "path.startswith('/laws')" in base
    deps = DEPS.read_text(encoding="utf-8")
    assert "def request_is_active_plus" in deps
    app_src = APP.read_text(encoding="utf-8")
    assert "request_is_active_plus" in app_src
    assert '"plus_bareact": request_is_active_plus(request)' in app_src
    for phrase in ("Premium", "Unlimited", "renews"):
        assert phrase not in bare


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


def test_plus_bareact_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "plus_bareact_screen04_1280.png"
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
              const plus = document.querySelector('[data-plus-bareact="desktop"]');
              const desk = document.querySelector('[data-signed-in-bareact-desktop]');
              const guest = document.querySelector('[data-guest-bareact-desktop]');
              const phone = document.querySelector('[data-bareact-phone]');
              const brand = document.querySelector('.brand');
              const mark = document.querySelector('.brand-mark');
              const back = desk.querySelector('.guest-bareact-back');
              const add = desk.querySelector('.guest-bareact-cta, .LawPlaygroundCta .pg-btn');
              const cluster = desk.querySelector('.signed-bareact-in-pg');
              const sections = desk.querySelector('.signed-bareact-sections');
              const cont = desk.querySelector('.signed-bareact-continue');
              const rows = [...desk.querySelectorAll('.guest-bareact-row')];
              const rowLinks = desk.querySelectorAll(
                'a:not(.guest-bareact-back):not(.guest-bareact-cta):not(.signed-bareact-sections):not(.signed-bareact-continue)'
              );
              const panelText = desk.innerText;
              return {
                present: Boolean(plus),
                deskDisplay: getComputedStyle(desk).display,
                phoneDisplay: phone ? getComputedStyle(phone).display : null,
                guestPresent: !!guest,
                brandHref: brand.getAttribute('href'),
                markFilter: getComputedStyle(mark).filter,
                backHref: back.getAttribute('href'),
                kicker: desk.querySelector('.guest-bareact-kicker').textContent.trim(),
                title: desk.querySelector('.guest-bareact-title').textContent.trim(),
                meta: desk.querySelector('.guest-bareact-meta').textContent.trim(),
                already: panelText.includes('Already in Playground'),
                addText: add && add.textContent.trim(),
                clusterPresent: !!cluster,
                sectionsHref: sections && sections.getAttribute('href'),
                sectionsText: sections && sections.textContent.trim(),
                continueHref: cont && cont.getAttribute('href'),
                continueText: cont && cont.textContent.trim(),
                subscribe: panelText.includes('Subscribe to use Playground'),
                signIn: panelText.includes('Sign in to use Playground'),
                rowCount: rows.length,
                rowTitles: rows.map((el) =>
                  el.querySelector('.guest-bareact-row-title').textContent.trim()
                ),
                extraLinks: rowLinks.length,
                details: desk.querySelectorAll('details').length,
                accountName: document.querySelector('.account-menu-btn-name').textContent.trim(),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                navLabels: [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                  (el) => el.textContent.replace(/\\s+/g, ' ').trim()
                ),
                browseActive: document.querySelector('.PrimaryTabs--top .nav-link.is-active')
                  .textContent.replace(/\\s+/g, ' ').trim(),
                plusCopy: /Premium|Unlimited|Free plan|Unlock all/.test(panelText),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)

        page.locator("[data-plus-bareact=\"desktop\"] .guest-bareact-back").click()
        page.wait_for_function("() => location.pathname === '/laws'", timeout=8000)
        laws_path = page.evaluate("() => location.pathname")
        laws_plus = page.evaluate(
            """() => !!document.querySelector('[data-plus-laws="desktop"]')"""
        )
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.locator("[data-plus-bareact=\"desktop\"] .signed-bareact-continue").click()
        page.wait_for_url("**/playground**", timeout=8000)
        playground_url = page.url
        playground_gate = "data-signed-in-pg-gate" in page.content()

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        phone_geo = page.evaluate(
            """() => {
              const desk = document.querySelector('[data-signed-in-bareact-desktop]');
              const plus = document.querySelector('[data-plus-bareact="desktop"]');
              const prod = document.querySelector('[data-bareact-phone]');
              return {
                plusPresent: Boolean(plus),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                prodDisplay: prod ? getComputedStyle(prod).display : null,
                details: prod ? prod.querySelectorAll('details').length : 0,
              };
            }"""
        )
        browser.close()

    assert geo["present"] is True
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
    assert geo["continueText"] == "Continue"
    assert geo["continueHref"] == home_path()
    assert geo["subscribe"] is False
    assert geo["signIn"] is False
    assert geo["rowCount"] == 4
    assert geo["rowTitles"] == [row.title for row in NDPS_GUEST_ROWS]
    assert geo["extraLinks"] == 0
    assert geo["details"] == 0
    assert geo["accountName"] == "Sanjay"
    assert geo["accountStatus"] == "RecallC Plus"
    assert geo["plusCopy"] is False
    assert geo["navLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["browseActive"] == "Browse"
    assert laws_path == "/laws"
    assert laws_plus is True
    assert "/playground" in playground_url
    assert playground_gate is False
    assert phone_geo["plusPresent"] is True
    assert phone_geo["deskDisplay"] == "none"
    assert phone_geo["prodDisplay"] != "none"
    assert phone_geo["details"] == 8
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
