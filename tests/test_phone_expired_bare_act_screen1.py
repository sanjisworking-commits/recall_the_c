"""Phone Expired Bare Act head Screen 01 (CTA map expired/01-screen).

Authorized: ChatGPT. Authenticated expired GET /laws/ndps at 390x844.
Desktop Expired Screen 04 is the functional contract. Compact head reuses
[data-expired-bareact="desktop"] at ≤560; production accordion stays in the
DOM but is hidden. Primary is Resume Playground → billing, never Continue.
Map Continue is composition-only. Guest/Free/Plus/Halted/Pro and other laws
stay as they are. Expired 02 is not this screen.
"""

from __future__ import annotations

import re
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
from constitution_memorizer.entitlements.models import BLOCK_PAID_PERIOD_ENDED
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
    ndps_guest_head,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
APP = ROOT / "src/constitution_memorizer/web/app.py"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_EXPIRED_STATUS = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
INVENTED = (
    "Your plan expired",
    "Resume subscription",
    "Premium",
    "Unlimited",
    "Unlock all",
    "Free plan",
    "All 3 slots",
)
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
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


def _seed_ndps_then_expire(client: TestClient) -> None:
    _subscribe(client)
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps")
    _expire(client)


def _expired_enrolled(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_then_expire(client)
    return client


def _expired_never_enrolled(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    _expire(client)
    return client


def _desk(html: str) -> str:
    return html.split("data-signed-in-bareact-desktop", 1)[1].split(
        "data-bareact-phone", 1
    )[0]


def _tabs(html: str) -> str:
    return html.split("data-expired-bareact-phone-tabs", 1)[1].split("</nav>", 1)[0]


def _facts(client: TestClient) -> dict:
    snap = client.app.state.entitlement_service.resolve(USER)
    history = tuple(
        sorted(
            (row.id, row.status, row.tier, row.is_current)
            for row in client.app.state.subscriptions.list_subscription_history(USER)
        )
    )
    roster = getattr(client.app.state, "roster", None)
    overlay = getattr(client.app.state, "playground", None)
    devices = getattr(client.app.state, "device_service", None)
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    return {
        "session": client.cookies.get(SESSION_COOKIE_NAME),
        "subscription": None
        if stored is None
        else (stored.id, stored.status, stored.tier, stored.is_current),
        "history": history,
        "active": tuple(sorted(i.law_id for i in roster.active_roster_items(USER)))
        if roster is not None
        else (),
        "overlay": tuple(
            sorted((item.law_id, item.status) for item in overlay.list_items(USER))
        )
        if overlay is not None
        else (),
        "devices": tuple(
            sorted(str(getattr(item, "id", item)) for item in devices.list_devices(USER))
        )
        if devices is not None and hasattr(devices, "list_devices")
        else (),
        "entitlement": (
            snap.subscription_status,
            snap.playground_block_reason,
            snap.can_open_playground,
            snap.can_consume_new_playground_law,
        ),
    }


def test_phone_expired_enrolled_uses_resume_not_continue(tmp_path: Path) -> None:
    client = _expired_enrolled(tmp_path)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert snap.subscription_status == "expired"
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    before = _facts(client)
    page = client.get("/laws/ndps")
    assert page.status_code == 200
    html = unescape(page.text)
    assert 'data-expired-bareact="desktop"' in html
    assert "data-plus-bareact-phone" not in html
    assert "data-expired-bareact-phone>" not in html
    assert "data-expired-bareact-phone=" not in html
    assert "data-signed-in-bareact-phone" not in html
    assert "data-guest-bareact-phone" not in html
    assert "data-expired-bareact-phone-tabs" in html
    assert "data-plus-bareact-phone-tabs" not in html
    desk = _desk(html)
    live = ndps_guest_head()
    assert f">{live.title}<" in desk
    assert NDPS_GUEST_KICKER in desk
    assert NDPS_GUEST_META in desk
    assert "6 Chapters" in desk
    assert "8 Chapters" not in desk
    assert 'class="guest-bareact-back" href="/laws"' in desk
    assert 'data-pg-kind="already_active"' in desk
    assert "Already in Playground" in desk
    assert ">Sections<" in desk
    assert f'href="{sections_path("ndps")}"' in desk
    assert f'class="signed-bareact-continue" href="{PLAYGROUND_BILLING_PATH}"' in desk
    assert ">Resume Playground<" in desk
    assert f'class="signed-bareact-continue" href="{home_path()}"' not in desk
    assert ">Continue<" not in desk
    assert "+ Add to Playground" not in desk
    assert 'data-pg-kind="eligible_to_add"' not in desk
    assert "Subscribe to use Playground" not in desk
    assert "Sign in to use Playground" not in desk
    assert 'href="/laws/ndps/section/' not in desk
    assert 'href="/laws/ndps/schedule/' not in desk
    for row in NDPS_GUEST_ROWS:
        assert row.tag in desk
        assert row.title in desk
        assert row.range_label in desk
    for phrase in INVENTED:
        assert phrase not in desk, phrase
    prod = html.split("data-bareact-phone", 1)[1]
    assert "<details" in prod
    assert "Resume Playground" in prod
    chapter = client.get("/laws/ndps/section/8")
    assert chapter.status_code == 200
    workspace = client.get(law_path("ndps"))
    assert workspace.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAID_PERIOD_ENDED}"' in workspace.text
    assert 'data-pg-learn-panel="cloze"' not in workspace.text
    sections = client.get(sections_path("ndps"))
    assert sections.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAID_PERIOD_ENDED}"' in sections.text
    home = client.get("/playground")
    assert home.status_code == 200
    assert (
        "is-readonly" in home.text
        or "read_only" in home.text
        or LIVE_EXPIRED_STATUS in home.text
    )
    assert 'data-hard-gate="true"' not in home.text
    assert _facts(client) == before
    assert client.get("/laws/ndps").status_code == 200
    assert _facts(client) == before


def test_phone_expired_never_enrolled_is_resume_only(tmp_path: Path) -> None:
    client = _expired_never_enrolled(tmp_path)
    before = _facts(client)
    html = unescape(client.get("/laws/ndps").text)
    desk = _desk(html)
    assert 'data-expired-bareact="desktop"' in html
    assert 'data-pg-kind="resume"' in desk
    assert "Resume Playground" in desk
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in desk
    assert "Already in Playground" not in desk
    assert 'class="signed-bareact-in-pg"' not in desk
    assert ">Sections<" not in desk
    assert 'class="signed-bareact-continue"' not in desk
    assert ">Continue<" not in desk
    assert "+ Add to Playground" not in desk
    assert 'data-pg-kind="eligible_to_add"' not in desk
    assert "Subscribe to use Playground" not in desk
    assert "Sign in to use Playground" not in desk
    assert _facts(client) == before


def test_phone_expired_five_tabs_browse_active_only(tmp_path: Path) -> None:
    html = _expired_enrolled(tmp_path).get("/laws/ndps").text
    assert "data-expired-bareact-phone-tabs" in html
    assert "data-plus-bareact-phone-tabs" not in html
    assert "data-signed-in-bareact-phone-tabs" not in html
    assert html.count('class="mobile-tabbar') == 1
    tabs = _tabs(html)
    for label, href in TAB_HREFS:
        assert f'href="{href}"' in tabs
        assert label in tabs
    browse = tabs.split('href="/browse"', 1)[1].split("</a>", 1)[0]
    assert "is-active" in browse
    assert 'aria-current="page"' in browse
    assert tabs.count("is-active") == 1
    assert tabs.count('aria-current="page"') == 1
    for href in ("/dashboard", "/playground", "/calendar", "/profile"):
        chunk = tabs.split(f'href="{href}"', 1)[1].split("</a>", 1)[0]
        assert "is-active" not in chunk
        assert "aria-current" not in chunk
    dash = _expired_enrolled(tmp_path / "dash").get("/dashboard").text
    assert "data-expired-bareact-phone-tabs" not in dash


def test_phone_expired_css_scope_pins_and_no_clone() -> None:
    css = PG_CSS.read_text(encoding="utf-8")
    assert "is expired/01-screen" in css
    block = css.split("is expired/01-screen", 1)[1]
    assert "data-expired-bareact" in block
    assert "[data-signed-in-bareact-desktop][data-expired-bareact=\"desktop\"]" in block
    assert "display: block !important" in block
    assert ":has([data-expired-bareact=\"desktop\"])" in block
    assert "[data-bareact-phone]" in block
    assert "display: none !important" in block
    assert "safe-area-inset-bottom" in block
    assert "overflow-x: hidden" in block
    assert "min-height: 44px" in block
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", block) is None
    assert "[data-expired-bareact-phone]" not in block
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-expired-bareact" not in mobile
    styles = STYLES.read_text(encoding="utf-8")
    assert "is expired/01-screen" not in styles
    hide = styles.split("[data-signed-in-bareact-desktop] {", 1)[1].split("}", 1)[0]
    assert "display: none" in hide
    assert "important" in hide
    bare = BARE.read_text(encoding="utf-8")
    assert "data-expired-bareact-phone" not in bare
    assert 'data-expired-bareact="desktop"' in bare
    base = BASE.read_text(encoding="utf-8")
    assert "data-expired-bareact-phone-tabs" in base
    assert "signed_in_expired_bareact_phone" in base
    assert "styles.css?v=main86" in base
    assert "mobile.css?v=mob105" in base
    assert "playground.css?v=pg47" in base
    assert "playground.css?v=pg40" not in base
    app = APP.read_text(encoding="utf-8")
    assert "request_is_expired_subscriber" in app
    deps = DEPS.read_text(encoding="utf-8")
    assert "def request_is_expired_subscriber" in deps
    view = VIEW.read_text(encoding="utf-8")
    assert 'primary_label="Resume Playground"' in view


def test_phone_expired_cohorts_and_other_laws_stay_separate(tmp_path: Path) -> None:
    expired = _expired_enrolled(tmp_path / "expired")
    expired_html = expired.get("/laws/ndps").text
    assert "data-expired-bareact-phone-tabs" in expired_html
    assert "data-plus-bareact-phone" not in expired_html
    bns = expired.get("/laws/bns").text
    assert "data-expired-bareact-phone-tabs" not in bns
    assert 'data-expired-bareact="desktop"' not in bns

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    added = _confirm_add(plus, "ndps")
    assert added.status_code in {200, 303}
    plus_html = plus.get("/laws/ndps").text
    assert "data-plus-bareact-phone" in plus_html
    assert "data-expired-bareact-phone-tabs" not in plus_html
    assert 'data-expired-bareact="desktop"' not in plus_html
    plus_phone = plus_html.split("data-plus-bareact-phone", 1)[1].split("</section>", 1)[0]
    assert ">Continue<" in plus_phone
    assert f'href="{home_path()}"' in plus_phone

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/laws/ndps").text
    assert "data-signed-in-bareact-phone" in free_html
    assert "data-expired-bareact-phone-tabs" not in free_html
    assert 'data-expired-bareact="desktop"' not in free_html
    assert "Subscribe to use Playground" in free_html.split(
        "data-signed-in-bareact-phone", 1
    )[1]

    guest = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "guest" / "progress.db",
            multiuser=True,
            multiuser_settings=_settings(),
            auth_provider=FakeAuthProvider(),
            session_store=InMemorySessionStore(),
        )
    )
    guest_html = guest.get("/laws/ndps").text
    assert "data-guest-bareact-phone" in guest_html
    assert "data-expired-bareact-phone-tabs" not in guest_html
    assert "Sign in to use Playground" in guest_html

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted)
    added = _confirm_add(halted, "ndps")
    assert added.status_code in {200, 303}
    stored = halted.app.state.subscriptions.get_current_subscription(USER)
    halted.app.state.subscriptions.update_subscription_state(
        USER, stored.id, status="halted"
    )
    halted_html = halted.get("/laws/ndps").text
    assert 'data-halted-bareact="desktop"' in halted_html
    assert "data-expired-bareact-phone-tabs" not in halted_html
    assert 'data-expired-bareact="desktop"' not in halted_html
    halted_prod = halted_html.split("data-bareact-phone", 1)[1]
    assert "LawPlaygroundCta" in halted_prod
    assert "<details" in halted_prod

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/laws/ndps").text
    assert "data-expired-bareact-phone-tabs" not in pro_html
    assert 'data-expired-bareact="desktop"' not in pro_html


def _screenshot(page, path: Path, *, attempts: int = 5) -> None:
    last: OSError | None = None
    for index in range(attempts):
        try:
            page.screenshot(path=str(path), full_page=False)
            return
        except OSError as exc:
            last = exc
            time.sleep(0.4 * (index + 1))
    assert last is not None
    raise last


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


def _playwright_session(app, tmp_path: Path, *, enrolled: bool):
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    if enrolled:
        added = _confirm_add(client, "ndps")
        assert added.status_code in {200, 303}
    _expire(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    return session, client


def test_phone_expired_bareact_screen01_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    session, _client = _playwright_session(app, tmp_path, enrolled=True)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_expired_bare_act_screen01_390x844.png"
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
              const desk = document.querySelector('[data-signed-in-bareact-desktop]');
              const expired = document.querySelector('[data-expired-bareact="desktop"]');
              const prod = document.querySelector('[data-bareact-phone]');
              const header = document.querySelector('.site-header');
              const tabs = document.querySelector('[data-expired-bareact-phone-tabs]');
              const bars = [...document.querySelectorAll('.mobile-tabbar')];
              const visibleBars = bars.filter((el) => getComputedStyle(el).display !== 'none');
              const visibleActive = visibleBars.flatMap((bar) =>
                [...bar.querySelectorAll('.mobile-tab.is-active')].filter(
                  (el) => getComputedStyle(el).display !== 'none'
                )
              );
              const visibleAria = visibleBars.flatMap((bar) =>
                [...bar.querySelectorAll('[aria-current="page"]')].filter(
                  (el) => getComputedStyle(el).display !== 'none'
                )
              );
              const back = expired && expired.querySelector('.guest-bareact-back');
              const sections = expired && expired.querySelector('.signed-bareact-sections');
              const cont = expired && expired.querySelector('.signed-bareact-continue');
              const rows = expired ? [...expired.querySelectorAll('.guest-bareact-row')] : [];
              const rowLinks = expired
                ? expired.querySelectorAll(
                    'a:not(.guest-bareact-back):not(.signed-bareact-sections):not(.signed-bareact-continue)'
                  )
                : [];
              const tabLinks = tabs ? [...tabs.querySelectorAll('a.mobile-tab')] : [];
              const backBox = back && back.getBoundingClientRect();
              const sectionsBox = sections && sections.getBoundingClientRect();
              const contBox = cont && cont.getBoundingClientRect();
              return {
                expiredPresent: Boolean(expired),
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                expiredDisplay: expired ? getComputedStyle(expired).display : null,
                prodDisplay: prod ? getComputedStyle(prod).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                barCount: bars.length,
                visibleBarCount: visibleBars.length,
                visibleActiveCount: visibleActive.length,
                visibleAriaCount: visibleAria.length,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                title: expired && expired.querySelector('.guest-bareact-title').textContent.trim(),
                kicker: expired && expired.querySelector('.guest-bareact-kicker').textContent.trim(),
                meta: expired && expired.querySelector('.guest-bareact-meta').textContent.trim(),
                backHref: back && back.getAttribute('href'),
                backH: backBox ? backBox.height : 0,
                already: expired && expired.innerText.includes('Already in Playground'),
                sectionsText: sections && sections.textContent.trim(),
                sectionsHref: sections && sections.getAttribute('href'),
                sectionsH: sectionsBox ? sectionsBox.height : 0,
                continueText: cont && cont.textContent.trim(),
                continueHref: cont && cont.getAttribute('href'),
                continueH: contBox ? contBox.height : 0,
                subscribe: expired && expired.innerText.includes('Subscribe to use Playground'),
                continueLabel: expired && /(?:^|\\n)\\s*Continue\\s*(?:\\n|$)/.test(expired.innerText),
                rowCount: rows.length,
                rowTitles: rows.map((el) =>
                  el.querySelector('.guest-bareact-row-title').textContent.trim()
                ),
                extraLinks: rowLinks.length,
                tabLabels: tabLinks.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabLinks.map((el) => el.getAttribute('href')),
                browseActive: visibleActive[0] && visibleActive[0].textContent.replace(/\\s+/g, ' ').trim(),
                details: prod ? prod.querySelectorAll('details').length : 0,
                clone: Boolean(document.querySelector('[data-expired-bareact-phone]')),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)
        page.locator('[data-expired-bareact="desktop"] .guest-bareact-back').click()
        page.wait_for_function("() => location.pathname === '/laws'", timeout=8000)
        laws_path = page.evaluate("() => location.pathname")
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.locator('[data-expired-bareact="desktop"] .signed-bareact-sections').click()
        page.wait_for_url("**/playground/laws/ndps/sections**", timeout=8000)
        sections_url = page.url
        sections_html = page.content()
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.locator('[data-expired-bareact="desktop"] .signed-bareact-continue').click()
        page.wait_for_url("**/billing/subscriptions**", timeout=8000)
        billing_url = page.url
        page.goto(f"{origin}/playground", wait_until="networkidle")
        home_html = page.content()
        page.set_viewport_size({"width": 390, "height": 700})
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        short_overflow = page.evaluate(
            "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        browser.close()

    assert geo["expiredPresent"] is True
    assert geo["clone"] is False
    assert geo["deskDisplay"] != "none"
    assert geo["expiredDisplay"] != "none"
    assert geo["prodDisplay"] == "none"
    assert geo["headerDisplay"] == "none"
    assert geo["tabsDisplay"] != "none"
    assert geo["barCount"] == 1
    assert geo["visibleBarCount"] == 1
    assert geo["visibleActiveCount"] == 1
    assert geo["visibleAriaCount"] == 1
    assert geo["overflow"] is False
    assert geo["title"] == NDPS_GUEST_TITLE
    assert geo["kicker"] == NDPS_GUEST_KICKER
    assert geo["meta"] == NDPS_GUEST_META
    assert geo["backHref"] == "/laws"
    assert geo["backH"] >= 44
    assert geo["already"] is True
    assert geo["sectionsText"] == "Sections"
    assert geo["sectionsHref"] == sections_path("ndps")
    assert geo["sectionsH"] >= 44
    assert geo["continueText"] == "Resume Playground"
    assert geo["continueHref"] == PLAYGROUND_BILLING_PATH
    assert geo["continueH"] >= 44
    assert geo["subscribe"] is False
    assert geo["continueLabel"] is False
    assert geo["rowCount"] == 4
    assert geo["rowTitles"] == [row.title for row in NDPS_GUEST_ROWS]
    assert geo["extraLinks"] == 0
    assert geo["tabLabels"] == [label for label, _href in TAB_HREFS]
    assert geo["tabHrefs"] == [href for _label, href in TAB_HREFS]
    assert geo["browseActive"] == "Browse"
    assert geo["details"] > 0
    assert laws_path == "/laws"
    assert "/playground/laws/ndps/sections" in sections_url
    assert f'data-playground-gate="{BLOCK_PAID_PERIOD_ENDED}"' in sections_html
    assert 'data-pg-learn-panel="cloze"' not in sections_html
    assert PLAYGROUND_BILLING_PATH in billing_url
    assert "/playground" not in billing_url.split("://", 1)[-1].split("/", 1)[-1]
    assert (
        "is-readonly" in home_html
        or "read_only" in home_html
        or LIVE_EXPIRED_STATUS in home_html
    )
    assert 'data-hard-gate="true"' not in home_html
    assert short_overflow is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_expired_bareact_screen01_never_enrolled_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    session, _client = _playwright_session(app, tmp_path, enrolled=False)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_expired_bare_act_screen01_never_enrolled_390x844.png"
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
              const expired = document.querySelector('[data-expired-bareact="desktop"]');
              const cta = expired && expired.querySelector('.LawPlaygroundCta');
              const btn = cta && cta.querySelector('.pg-btn');
              const box = btn && btn.getBoundingClientRect();
              const cluster = expired && expired.querySelector('.signed-bareact-in-pg');
              return {
                kind: cta && cta.getAttribute('data-pg-kind'),
                href: btn && btn.getAttribute('href'),
                text: btn && btn.textContent.replace(/\\s+/g, ' ').trim(),
                addH: box ? box.height : 0,
                already: expired && expired.innerText.includes('Already in Playground'),
                sections: Boolean(expired && expired.querySelector('.signed-bareact-sections')),
                add: expired && /Add to Playground/.test(expired.innerText),
                subscribe: expired && expired.innerText.includes('Subscribe to use Playground'),
                cluster: Boolean(cluster),
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                deskDisplay: expired ? getComputedStyle(expired).display : null,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)
        browser.close()

    assert geo["kind"] == "resume"
    assert geo["href"] == PLAYGROUND_BILLING_PATH
    assert geo["text"] == "Resume Playground"
    assert geo["addH"] >= 44
    assert geo["already"] is False
    assert geo["sections"] is False
    assert geo["add"] is False
    assert geo["subscribe"] is False
    assert geo["cluster"] is False
    assert geo["overflow"] is False
    assert geo["deskDisplay"] != "none"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_expired_bareact_screen01_desktop_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    session, _client = _playwright_session(app, tmp_path, enrolled=True)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_expired_bare_act_screen01_desktop_regression_1280.png"
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
              const desk = document.querySelector('[data-signed-in-bareact-desktop]');
              const expired = document.querySelector('[data-expired-bareact="desktop"]');
              const prod = document.querySelector('[data-bareact-phone]');
              const tabs = document.querySelector('[data-expired-bareact-phone-tabs]');
              const header = document.querySelector('.site-header');
              const cluster = desk && desk.querySelector('.signed-bareact-in-pg');
              const box = cluster && cluster.getBoundingClientRect();
              const nav = [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                (el) => el.textContent.replace(/\\s+/g, ' ').trim()
              );
              const cont = desk && desk.querySelector('.signed-bareact-continue');
              const sections = desk && desk.querySelector('.signed-bareact-sections');
              return {
                deskDisplay: desk ? getComputedStyle(desk).display : null,
                expiredDisplay: expired ? getComputedStyle(expired).display : null,
                prodDisplay: prod ? getComputedStyle(prod).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                clusterW: box ? box.width : 0,
                already: desk && desk.innerText.includes('Already in Playground'),
                continueHref: cont && cont.getAttribute('href'),
                continueText: cont && cont.textContent.trim(),
                sectionsHref: sections && sections.getAttribute('href'),
                navLabels: nav,
                title: desk && desk.querySelector('.guest-bareact-title').textContent.trim(),
                account: document.querySelector('.account-menu-btn-name')
                  && document.querySelector('.account-menu-btn-name').textContent.trim(),
                status: document.querySelector('.account-menu-btn-status')
                  && document.querySelector('.account-menu-btn-status').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)
        browser.close()

    assert geo["deskDisplay"] != "none"
    assert geo["expiredDisplay"] != "none"
    assert geo["prodDisplay"] == "none"
    assert geo["tabsDisplay"] == "none"
    assert geo["headerDisplay"] != "none"
    assert geo["clusterW"] == pytest.approx(380, abs=8)
    assert geo["already"] is True
    assert geo["continueHref"] == PLAYGROUND_BILLING_PATH
    assert geo["continueText"] == "Resume Playground"
    assert geo["sectionsHref"] == sections_path("ndps")
    assert geo["navLabels"] == [label for label, _href in TAB_HREFS]
    assert geo["title"] == NDPS_GUEST_TITLE
    assert geo["account"] == "Sanjay"
    assert geo["status"] == LIVE_EXPIRED_STATUS
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
