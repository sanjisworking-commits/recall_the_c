"""Phone Expired Bare Act head Screen 01 (CTA map expired/01-screen).

Authorized: ChatGPT. Authenticated expired GET /laws/ndps at 390x844.
Desktop Expired Screen 04 is the functional contract. Primary is Resume
Playground → billing, never Continue. Map Continue is composition-only.
Guest/Free/Plus/Halted/Pro and other laws stay as they are. Expired 02 is
not this screen.

M2: one generated ``section.ActHead`` serves both widths (the ≤560 layout
is CSS under "Bare Act head (M2)" in styles.css), so there is no compact
twin and no hidden production accordion any more: the chapter rows are the
accordion, read off the live Act model (eight NDPS chapters, M2 §4 Q1).
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
from constitution_memorizer.playground.access import PlaygroundAccess
from constitution_memorizer.playground.urls import add_path, home_path, law_path, sections_path
from constitution_memorizer.playground.view import (
    PLAYGROUND_BILLING_PATH,
    gate_view,
    law_membership,
)
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
APP = ROOT / "src/constitution_memorizer/web/app.py"
BARE_PAGE = ROOT / "src/constitution_memorizer/web/bare_act_page.py"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
USER = UUID("11111111-1111-4111-8111-111111111111")
EXPIRED_START = datetime(2026, 8, 16, tzinfo=timezone.utc)
EXPIRED_END = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_START = datetime(2026, 9, 15, tzinfo=timezone.utc)
ACTIVE_END = datetime(2026, 10, 15, tzinfo=timezone.utc)
LIVE_EXPIRED_STATUS = gate_view(reason=BLOCK_PAID_PERIOD_ENDED).title
KICKER = "Bare Act · India Code"
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


def _head(html: str) -> str:
    """The generated Act head (M2): the ``section.ActHead`` tag attributes
    and its band (back link, kicker, title, meta, Playground action, About),
    up to the chapter list."""
    return html.split('class="panel ActHead', 1)[1].split("data-bareact-accordion", 1)[0]


def _act_list(html: str) -> str:
    """The one chapter + schedule list under the head."""
    return html.split("data-bareact-accordion", 1)[1].split("</section>", 1)[0]


def _tabs(html: str) -> str:
    return html.split("data-expired-bareact-phone-tabs", 1)[1].split("</nav>", 1)[0]


def _live_state(client: TestClient, law_id: str = "ndps"):
    """The live LawPlaygroundState the head renders from (M2-F04)."""
    snap = client.app.state.entitlement_service.resolve(USER)
    access = PlaygroundAccess(
        user_id=USER,
        snapshot=snap,
        can_open=snap.can_open_playground,
        can_consume_new_law=snap.can_consume_new_playground_law,
        local_owner=False,
        can_view_home=True,
    )
    return law_membership(
        law_id=law_id,
        access=access,
        roster=client.app.state.roster,
        overlay=client.app.state.playground,
    )


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
    act = get_bare_act("ndps")
    assert act is not None
    head = _head(html)
    # One head on both widths, no phone twin and no clone (M2 §2.1).
    assert html.count('class="panel ActHead') == 1
    assert "data-expired-bareact" in head
    assert 'data-expired-bareact="desktop"' not in html
    assert "data-plus-bareact" not in head
    assert "data-expired-bareact-phone>" not in html
    assert "data-expired-bareact-phone=" not in html
    assert "data-signed-in-bareact-phone>" not in html
    assert "data-guest-bareact-phone>" not in html
    assert "data-bareact-phone" not in html
    assert "data-expired-bareact-phone-tabs" in html
    assert "data-plus-bareact-phone-tabs" not in html
    assert f'<h1 class="ActHead-title">{act.title}</h1>' in head
    assert KICKER in head
    assert f'<p class="ActHead-meta">{act.head_meta_label}</p>' in head
    # Eight chapters from the canonical Act (M2 §4 Q1), not the fixture's six.
    assert "8 Chapters" in head
    assert "6 Chapters" not in head
    assert 'class="ActHead-back" href="/laws"' in head
    assert 'data-pg-kind="already_active"' in head
    assert "Already in Playground" in head
    assert 'class="ActHead-cta LawPlaygroundCta"' in head
    assert 'class="ActHead-inpg"' in head
    assert ">Sections</a>" in head
    assert f'class="ActHead-inpg-sections" href="{sections_path("ndps")}">Sections</a>' in head
    assert (
        f'class="ActHead-inpg-continue" href="{PLAYGROUND_BILLING_PATH}">Resume Playground</a>'
        in head
    )
    assert ">Resume Playground<" in head
    assert f'href="{home_path()}"' not in head
    assert ">Continue<" not in head
    assert ">Start learning<" not in head
    assert "+ Add to Playground" not in head
    assert 'data-pg-kind="eligible_to_add"' not in head
    assert "Subscribe to use Playground" not in head
    assert "Sign in to use Playground" not in head
    assert 'href="/laws/ndps/section/' not in head
    assert 'href="/laws/ndps/schedule/' not in head
    for phrase in INVENTED:
        assert phrase not in head, phrase
    # The chapter rows are the accordion (Q3): every chapter a closed
    # <summary> whose section links are in the document; schedules follow.
    listing = _act_list(html)
    assert act.chapter_count == 8
    assert listing.count('<details class="bareact-chapter">') == act.chapter_count
    assert (
        listing.count('<summary class="bareact-chapter-row" aria-expanded="false">')
        == act.chapter_count
    )
    assert '<details class="bareact-chapter" open' not in listing
    for chapter in act.chapters:
        assert f"Chapter {chapter.number}</span>" in listing
        assert f'<span class="bareact-chapter-name">{chapter.title}</span>' in listing
        assert (
            f'<span class="ActHead-range-word">Sections </span>{chapter.range_label}</span>'
            in listing
        )
    assert listing.count('<div class="bareact-schedule-row') == len(act.schedules)
    for schedule in act.schedules:
        assert f"{schedule.label}</span>" in listing
    assert 'href="/laws/ndps/section/' in listing
    assert 'href="/laws/ndps/schedule/' in listing
    assert "data-bareact-tabs" not in html
    assert "This Act has no Schedules." not in html
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
    head = _head(html)
    assert html.count('class="panel ActHead') == 1
    assert "data-expired-bareact" in head
    assert 'data-pg-kind="resume"' in head
    assert 'class="ActHead-btn"' in head
    assert "Resume Playground" in head
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in head
    assert "Already in Playground" not in head
    assert 'class="ActHead-inpg"' not in head
    assert 'class="ActHead-inpg-sections"' not in head
    assert ">Sections</a>" not in head
    assert 'class="ActHead-inpg-continue"' not in head
    assert ">Continue<" not in head
    assert "+ Add to Playground" not in head
    assert 'data-pg-kind="eligible_to_add"' not in head
    assert "Subscribe to use Playground" not in head
    assert "Sign in to use Playground" not in head
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
    # The head's layout lives in one state-agnostic block (M2): no
    # per-cohort selector, no hidden twin, no reordering.
    styles = STYLES.read_text(encoding="utf-8")
    assert "Bare Act head (M2)" in styles
    block = styles.split("Bare Act head (M2)", 1)[1].split(
        "Guest Playground intro (CTA map guest/06-screen)", 1
    )[0]
    assert ".panel.ActHead" in block
    assert ".ActHead-back" in block
    assert ".ActHead-inpg-continue" in block
    assert "min-height: 44px" in block
    assert "@media (max-width: 560px)" in block
    phone = block.split("@media (max-width: 560px)", 1)[1]
    assert ".ActHead-row" in phone
    assert "flex-direction: column" in phone
    assert ".ActHead-inpg-continue" in phone
    assert "min-height: 44px" in phone
    assert ".ActHead-range-word" in phone
    assert "display: none !important" not in block
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", block) is None
    assert "data-expired-bareact" not in styles
    assert "data-signed-in-bareact-desktop" not in styles
    assert "data-bareact-phone" not in styles
    assert "is expired/01-screen" not in styles
    css = PG_CSS.read_text(encoding="utf-8")
    assert "is expired/01-screen" not in css
    assert "data-expired-bareact" not in css
    assert "[data-expired-bareact-phone]" not in css
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-expired-bareact" not in mobile
    assert 'body[data-mscreen="bareact"] .bareact-chapter-row' in mobile
    assert 'body[data-mscreen="bareact"] .bareact-section-row' in mobile
    bare = BARE.read_text(encoding="utf-8")
    assert "data-expired-bareact-phone" not in bare
    assert "data-expired-bareact" in bare
    assert 'data-expired-bareact="desktop"' not in bare
    assert "data-bareact-phone" not in bare
    assert bare.count('class="panel ActHead') == 1
    base = BASE.read_text(encoding="utf-8")
    assert "data-expired-bareact-phone-tabs" in base
    assert "signed_in_expired_bareact_phone" in base
    assert "styles.css?v=main88" in base
    assert "mobile.css?v=mob107" in base
    assert "playground.css?v=pg50" in base
    assert "playground.css?v=pg40" not in base
    assert "playground.css?v=pg49" not in base
    app = APP.read_text(encoding="utf-8")
    assert "request_is_expired_subscriber" in app
    assert "bare_act_page_context" in app
    bare_page = BARE_PAGE.read_text(encoding="utf-8")
    assert "request_is_expired_subscriber" in bare_page
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
    # The expired marker is the viewer's, carried by every Act's head (M2);
    # BNS is not retained, so it gets the resume button, not the chip.
    bns_head = _head(bns)
    assert "data-expired-bareact" in bns_head
    assert 'data-pg-kind="resume"' in bns_head
    assert "Already in Playground" not in bns_head

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    added = _confirm_add(plus, "ndps")
    assert added.status_code in {200, 303}
    plus_html = plus.get("/laws/ndps").text
    assert "data-plus-bareact-phone" in plus_html
    assert "data-expired-bareact-phone-tabs" not in plus_html
    plus_head = _head(plus_html)
    assert "data-plus-bareact" in plus_head
    assert "data-expired-bareact" not in plus_head
    plus_state = _live_state(plus)
    assert plus_state.kind == "already_active"
    assert plus_state.primary_href != PLAYGROUND_BILLING_PATH
    assert plus_state.primary_label in {"Continue", "Start learning"}
    assert (
        f'class="ActHead-inpg-continue" href="{plus_state.primary_href}">{plus_state.primary_label}</a>'
        in plus_head
    )
    assert "Resume Playground" not in plus_head

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/laws/ndps").text
    assert "data-signed-in-bareact-phone-tabs" in free_html
    assert "data-expired-bareact-phone-tabs" not in free_html
    free_head = _head(free_html)
    assert "data-expired-bareact" not in free_head
    assert 'data-pg-kind="subscribe"' in free_head
    assert "Subscribe to use Playground" in free_head

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
    assert "data-expired-bareact-phone-tabs" not in guest_html
    guest_head = _head(guest_html)
    assert "data-expired-bareact" not in guest_head
    assert 'data-pg-kind="guest"' in guest_head
    assert "Sign in to use Playground" in guest_head

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
    halted_head = _head(halted_html)
    assert "data-halted-bareact" in halted_head
    assert "data-expired-bareact-phone-tabs" not in halted_html
    assert "data-expired-bareact" not in halted_head
    assert 'class="ActHead-inpg"' in halted_head
    assert "<details" in _act_list(halted_html)

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/laws/ndps").text
    assert "data-expired-bareact-phone-tabs" not in pro_html
    pro_head = _head(pro_html)
    assert "data-expired-bareact" not in pro_head
    assert "data-plus-bareact" not in pro_head
    assert 'data-pg-kind="eligible_to_add"' in pro_head
    assert "+ Add to Playground" in pro_head


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
    act = get_bare_act("ndps")
    assert act is not None
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
              const head = document.querySelector('.ActHead[data-expired-bareact]');
              const band = head && head.querySelector('.ActHead-band');
              const list = head && head.querySelector('[data-act-list]');
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
              const back = head && head.querySelector('.ActHead-back');
              const sections = head && head.querySelector('.ActHead-inpg-sections');
              const cont = head && head.querySelector('.ActHead-inpg-continue');
              const rows = list ? [...list.querySelectorAll('summary.bareact-chapter-row')] : [];
              const bandLinks = band
                ? band.querySelectorAll(
                    'a:not(.ActHead-back):not(.ActHead-inpg-sections):not(.ActHead-inpg-continue)'
                  )
                : [];
              const tabLinks = tabs ? [...tabs.querySelectorAll('a.mobile-tab')] : [];
              const backBox = back && back.getBoundingClientRect();
              const sectionsBox = sections && sections.getBoundingClientRect();
              const contBox = cont && cont.getBoundingClientRect();
              return {
                expiredPresent: Boolean(head),
                headCount: document.querySelectorAll('.ActHead').length,
                headDisplay: head ? getComputedStyle(head).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                barCount: bars.length,
                visibleBarCount: visibleBars.length,
                visibleActiveCount: visibleActive.length,
                visibleAriaCount: visibleAria.length,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                title: head && head.querySelector('.ActHead-title').textContent.trim(),
                kicker: head && head.querySelector('.ActHead-kicker').textContent.trim(),
                meta: head && head.querySelector('.ActHead-meta').textContent.trim(),
                backHref: back && back.getAttribute('href'),
                backH: backBox ? backBox.height : 0,
                already: band && band.innerText.includes('Already in Playground'),
                sectionsText: sections && sections.textContent.trim(),
                sectionsHref: sections && sections.getAttribute('href'),
                sectionsH: sectionsBox ? sectionsBox.height : 0,
                continueText: cont && cont.textContent.trim(),
                continueHref: cont && cont.getAttribute('href'),
                continueH: contBox ? contBox.height : 0,
                subscribe: band && band.innerText.includes('Subscribe to use Playground'),
                continueLabel: band && /(?:^|\\n)\\s*Continue\\s*(?:\\n|$)/.test(band.innerText),
                rowCount: rows.length,
                rowTitles: rows.map((el) =>
                  el.querySelector('.bareact-chapter-name').textContent.trim()
                ),
                extraLinks: bandLinks.length,
                tabLabels: tabLinks.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabLinks.map((el) => el.getAttribute('href')),
                browseActive: visibleActive[0] && visibleActive[0].textContent.replace(/\\s+/g, ' ').trim(),
                details: list ? list.querySelectorAll('details.bareact-chapter').length : 0,
                openDetails: list ? list.querySelectorAll('details[open]').length : 0,
                clone: Boolean(document.querySelector('[data-expired-bareact-phone]')),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)
        page.locator(".ActHead[data-expired-bareact] .ActHead-back").click()
        page.wait_for_function("() => location.pathname === '/laws'", timeout=8000)
        laws_path = page.evaluate("() => location.pathname")
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.locator(".ActHead[data-expired-bareact] .ActHead-inpg-sections").click()
        page.wait_for_url("**/playground/laws/ndps/sections**", timeout=8000)
        sections_url = page.url
        sections_html = page.content()
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.locator(".ActHead[data-expired-bareact] .ActHead-inpg-continue").click()
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
    assert geo["headCount"] == 1
    assert geo["headDisplay"] != "none"
    assert geo["headerDisplay"] == "none"
    assert geo["tabsDisplay"] != "none"
    assert geo["barCount"] == 1
    assert geo["visibleBarCount"] == 1
    assert geo["visibleActiveCount"] == 1
    assert geo["visibleAriaCount"] == 1
    assert geo["overflow"] is False
    assert geo["title"] == act.title
    assert geo["kicker"] == KICKER
    assert geo["meta"] == act.head_meta_label
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
    assert geo["rowCount"] == act.chapter_count
    assert geo["rowTitles"] == [chapter.title for chapter in act.chapters]
    assert geo["extraLinks"] == 0
    assert geo["tabLabels"] == [label for label, _href in TAB_HREFS]
    assert geo["tabHrefs"] == [href for _label, href in TAB_HREFS]
    assert geo["browseActive"] == "Browse"
    assert geo["details"] == act.chapter_count
    assert geo["openDetails"] == 0
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
              const head = document.querySelector('.ActHead[data-expired-bareact]');
              const cta = head && head.querySelector('.ActHead-cta');
              const btn = cta && cta.querySelector('.ActHead-btn');
              const box = btn && btn.getBoundingClientRect();
              const cluster = head && head.querySelector('.ActHead-inpg');
              const band = head && head.querySelector('.ActHead-band');
              return {
                kind: cta && cta.getAttribute('data-pg-kind'),
                href: btn && btn.getAttribute('href'),
                text: btn && btn.textContent.replace(/\\s+/g, ' ').trim(),
                addH: box ? box.height : 0,
                already: band && band.innerText.includes('Already in Playground'),
                sections: Boolean(head && head.querySelector('.ActHead-inpg-sections')),
                add: band && /Add to Playground/.test(band.innerText),
                subscribe: band && band.innerText.includes('Subscribe to use Playground'),
                cluster: Boolean(cluster),
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                headDisplay: head ? getComputedStyle(head).display : null,
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
    assert geo["headDisplay"] != "none"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_expired_bareact_screen01_desktop_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    session, _client = _playwright_session(app, tmp_path, enrolled=True)
    act = get_bare_act("ndps")
    assert act is not None
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
              const head = document.querySelector('.ActHead[data-expired-bareact]');
              const tabs = document.querySelector('[data-expired-bareact-phone-tabs]');
              const header = document.querySelector('.site-header');
              const cluster = head && head.querySelector('.ActHead-inpg');
              const box = cluster && cluster.getBoundingClientRect();
              const nav = [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                (el) => el.textContent.replace(/\\s+/g, ' ').trim()
              );
              const cont = head && head.querySelector('.ActHead-inpg-continue');
              const sections = head && head.querySelector('.ActHead-inpg-sections');
              return {
                headCount: document.querySelectorAll('.ActHead').length,
                headDisplay: head ? getComputedStyle(head).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                clusterW: box ? box.width : 0,
                already: head && head.innerText.includes('Already in Playground'),
                continueHref: cont && cont.getAttribute('href'),
                continueText: cont && cont.textContent.trim(),
                sectionsHref: sections && sections.getAttribute('href'),
                navLabels: nav,
                title: head && head.querySelector('.ActHead-title').textContent.trim(),
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

    assert geo["headCount"] == 1
    assert geo["headDisplay"] != "none"
    assert geo["tabsDisplay"] == "none"
    assert geo["headerDisplay"] != "none"
    assert geo["clusterW"] == pytest.approx(380, abs=8)
    assert geo["already"] is True
    assert geo["continueHref"] == PLAYGROUND_BILLING_PATH
    assert geo["continueText"] == "Resume Playground"
    assert geo["sectionsHref"] == sections_path("ndps")
    assert geo["navLabels"] == [label for label, _href in TAB_HREFS]
    assert geo["title"] == act.title
    assert geo["account"] == "Sanjay"
    assert geo["status"] == LIVE_EXPIRED_STATUS
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
