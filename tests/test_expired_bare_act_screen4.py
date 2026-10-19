"""Expired cohort desktop NDPS Bare Act Screen 04 (CTA map expired/04-screen).

Authorized: ChatGPT. Authenticated multiuser GET /laws/ndps with a real
expired subscription whose paid period has ended, after NDPS was added
through the real roster/add flow. The Act stays readable. Retained
presentation follows pg.kind == already_active, not pg.subscribed.
Workspace Continue is not hard-coded: live primary is the paid-period-ended
lifecycle CTA because /playground/laws/ndps is not allowed. Guest, Free,
Plus, halted, phone, Plus 01–11, and Expired 01–03 stay unchanged.

M2: the head is the one generated ``section.ActHead`` for every Act and
every viewer (same markup on both widths; CSS does the layout), so the
assertions read the live Act model (``get_bare_act``) instead of the deleted
NDPS fixture head, and the retained chip's Continue carries the live
``LawPlaygroundState`` destination (M2-F04).
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from pathlib import Path
import socket
import threading
import time
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
UNITS = ROOT / "data" / "output" / "learning_units.json"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
APP = ROOT / "src/constitution_memorizer/web/app.py"
BARE_PAGE = ROOT / "src/constitution_memorizer/web/bare_act_page.py"
VIEW = ROOT / "src/constitution_memorizer/playground/view.py"
LANDING = ROOT / "src/constitution_memorizer/web/templates/landing.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
ADD = ROOT / "src/constitution_memorizer/web/templates/playground_add.html"
ADD_PANEL = ROOT / "src/constitution_memorizer/web/templates/partials/playground_add_panel.html"
HOME = ROOT / "src/constitution_memorizer/web/templates/playground.html"
MANAGE = ROOT / "src/constitution_memorizer/web/templates/subscription_manage.html"
DASH = ROOT / "src/constitution_memorizer/web/templates/dashboard.html"
CAL = ROOT / "src/constitution_memorizer/web/templates/calendar.html"
PROFILE = ROOT / "src/constitution_memorizer/web/templates/profile.html"
SETTINGS = ROOT / "src/constitution_memorizer/web/templates/settings.html"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
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


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _head(html: str) -> str:
    """The generated Act head (M2): the ``section.ActHead`` tag attributes
    and its band (back link, kicker, title, meta, Playground action, About),
    up to the chapter list."""
    return html.split('class="panel ActHead', 1)[1].split("data-bareact-accordion", 1)[0]


def _act_list(html: str) -> str:
    """The one chapter + schedule list under the head."""
    return html.split("data-bareact-accordion", 1)[1].split("</section>", 1)[0]


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


def test_expired_retained_ndps_uses_live_already_active_not_subscribed(
    tmp_path: Path,
) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_then_expire(client)
    snap = client.app.state.entitlement_service.resolve(USER)
    assert snap.playground_block_reason == BLOCK_PAID_PERIOD_ENDED
    assert snap.subscription_status == "expired"
    assert snap.is_subscribed is False
    assert snap.can_open_playground is False
    assert snap.can_consume_new_playground_law is False
    html = unescape(client.get("/laws/ndps").text)
    header = _header(html)
    head = _head(html)
    act = get_bare_act("ndps")
    assert act is not None
    # One generated head, no desktop/phone twins (M2 §2.1).
    assert html.count('class="panel ActHead') == 1
    assert 'data-act-head="ndps"' in head
    assert "data-expired-bareact" in head
    assert "data-plus-bareact" not in head
    assert "data-halted-bareact" not in head
    assert KICKER in head
    assert f'<h1 class="ActHead-title">{act.title}</h1>' in head
    assert f'<p class="ActHead-meta">{act.head_meta_label}</p>' in head
    assert 'class="ActHead-back" href="/laws"' in head
    assert "Already in Playground" in head
    assert 'data-pg-kind="already_active"' in head
    assert 'data-membership="in_playground"' in head
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
    assert "data-pg-sheet" not in head
    assert "Subscribe to use Playground" not in head
    assert "Sign in to use Playground" not in head
    assert LIVE_EXPIRED_STATUS in header
    assert "Free account" not in header
    assert "RecallC Plus" not in header
    assert "Sanjay" in header
    for phrase in INVENTED:
        assert phrase not in head, phrase
    # The list is generated from the canonical Act: eight NDPS chapters
    # (M2 §4 Q1), none open, each a <summary> that expands into its section
    # links (Q3); one schedule row.
    listing = _act_list(html)
    assert act.chapter_count == 8
    assert listing.count('<details class="bareact-chapter">') == act.chapter_count
    assert (
        listing.count('<summary class="bareact-chapter-row" aria-expanded="false">')
        == act.chapter_count
    )
    assert '<details class="bareact-chapter" open' not in listing
    assert listing.count('<div class="bareact-schedule-row') == len(act.schedules) == 1
    for chapter in act.chapters:
        assert f"Chapter {chapter.number}</span>" in listing
        assert f'<span class="bareact-chapter-name">{chapter.title}</span>' in listing
    assert 'href="/laws/ndps/section/' not in head
    assert 'href="/laws/ndps/section/' in listing
    workspace = client.get(law_path("ndps"))
    assert workspace.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAID_PERIOD_ENDED}"' in workspace.text
    assert 'data-pg-learn-panel="cloze"' not in workspace.text
    sections = client.get(sections_path("ndps"))
    assert sections.status_code == 200
    assert f'data-playground-gate="{BLOCK_PAID_PERIOD_ENDED}"' in sections.text
    home = client.get("/playground")
    assert home.status_code == 200
    assert "is-readonly" in home.text or "read_only" in home.text or LIVE_EXPIRED_STATUS in home.text
    assert 'data-hard-gate="true"' not in home.text
    chapter = client.get("/laws/ndps/section/8")
    assert chapter.status_code == 200


def test_never_added_law_does_not_get_retained_treatment(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _seed_ndps_then_expire(client)
    bns = unescape(client.get("/laws/bns").text)
    bns_head = _head(bns)
    bns_act = get_bare_act("bns")
    assert bns_act is not None
    assert bns.count('class="panel ActHead') == 1
    assert 'data-act-head="bns"' in bns_head
    # The expired marker is the viewer's, carried by every Act's head (M2).
    assert "data-expired-bareact" in bns_head
    assert f'<p class="ActHead-meta">{bns_act.head_meta_label}</p>' in bns_head
    assert _act_list(bns).count('<details class="bareact-chapter">') == bns_act.chapter_count
    assert "Already in Playground" not in bns_head
    assert 'data-pg-kind="already_active"' not in bns_head
    assert 'class="ActHead-inpg"' not in bns_head
    assert 'class="ActHead-inpg-continue"' not in bns_head
    assert "+ Add to Playground" not in bns_head
    assert 'data-pg-kind="eligible_to_add"' not in bns_head
    assert 'data-pg-kind="resume"' in bns_head
    assert 'class="ActHead-btn"' in bns_head
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in bns_head
    assert ">Resume Playground<" in bns_head

    fresh = TestClient(_mu_app(tmp_path / "none"))
    _sign_in(fresh)
    _subscribe(fresh)
    _expire(fresh)
    ndps = unescape(fresh.get("/laws/ndps").text)
    head = _head(ndps)
    assert "data-expired-bareact" in head
    assert "Already in Playground" not in head
    assert 'class="ActHead-inpg"' not in head
    assert 'class="ActHead-inpg-continue"' not in head
    assert ">Continue<" not in head
    assert "+ Add to Playground" not in head
    assert 'data-pg-kind="resume"' in head
    assert 'class="ActHead-btn"' in head
    assert f'href="{PLAYGROUND_BILLING_PATH}"' in head
    assert "Resume Playground" in head


def test_free_plus_guest_halted_stay_separate_from_expired(tmp_path: Path) -> None:
    guest = TestClient(_mu_app(tmp_path / "guest"))
    guest_html = guest.get("/laws/ndps").text
    guest_head = _head(guest_html)
    assert "data-expired-bareact" not in guest_head
    assert 'data-pg-kind="guest"' in guest_head
    assert 'class="ActHead-btn"' in guest_head
    assert "Sign in to use Playground" in guest_head
    assert "Already in Playground" not in guest_head
    assert "RecallC Plus" not in guest_html

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/laws/ndps").text
    free_head = _head(free_html)
    assert "data-expired-bareact" not in free_head
    assert "data-plus-bareact" not in free_head
    assert 'data-pg-kind="subscribe"' in free_head
    assert "Subscribe to use Playground" in free_head
    assert "Already in Playground" not in free_head
    assert "Free account" in _header(free_html)
    assert LIVE_EXPIRED_STATUS not in _header(free_html)

    plus = TestClient(_mu_app(tmp_path / "plus"))
    _sign_in(plus)
    _subscribe(plus)
    added = _confirm_add(plus, "ndps")
    assert added.status_code in {200, 303}
    plus_html = plus.get("/laws/ndps").text
    plus_head = _head(plus_html)
    assert "data-plus-bareact" in plus_head
    assert "data-expired-bareact" not in plus_head
    assert "Already in Playground" in plus_head
    assert 'data-pg-kind="already_active"' in plus_head
    # A subscriber's Continue is the live state's own destination, never the
    # expired lifecycle CTA (M2-F04).
    plus_state = _live_state(plus)
    assert plus_state.kind == "already_active"
    assert plus_state.primary_href != PLAYGROUND_BILLING_PATH
    assert plus_state.primary_label != "Resume Playground"
    assert plus_state.primary_label in {"Continue", "Start learning"}
    assert (
        f'class="ActHead-inpg-continue" href="{plus_state.primary_href}">{plus_state.primary_label}</a>'
        in plus_head
    )
    assert f'href="{PLAYGROUND_BILLING_PATH}"' not in plus_head
    assert "Resume Playground" not in plus_head
    assert "RecallC Plus" in _header(plus_html)
    assert LIVE_EXPIRED_STATUS not in _header(plus_html)

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
    assert "data-expired-bareact" not in halted_head
    assert "data-plus-bareact" not in halted_head
    assert "data-halted-bareact" in halted_head
    assert LIVE_EXPIRED_STATUS not in _header(halted_html)
    halted_snap = halted.app.state.entitlement_service.resolve(USER)
    assert halted_snap.subscription_status == "halted"
    assert halted_snap.playground_block_reason != BLOCK_PAID_PERIOD_ENDED
    assert ">Continue<" not in halted_head
    assert ">Resume Playground<" not in halted_head
    assert "Subscribe to use Playground" not in halted_head


def test_expired_bareact_uses_shared_predicate_not_subscribed_gate() -> None:
    bare = BARE.read_text(encoding="utf-8")
    assert "expired_bareact" in bare
    assert "data-expired-bareact" in bare
    assert 'data-expired-bareact="desktop"' not in bare
    assert "plus_bareact" in bare
    assert "data-plus-bareact" in bare
    assert 'data-plus-bareact="desktop"' not in bare
    assert "halted_bareact" in bare
    assert "data-halted-bareact" in bare
    # One head: the per-surface twins and their fixture classes are gone.
    assert "data-signed-in-bareact-desktop" not in bare
    assert "data-guest-bareact-desktop" not in bare
    assert "data-bareact-phone" not in bare
    assert "guest-bareact-" not in bare
    assert "signed-bareact-" not in bare
    assert 'class="panel ActHead' in bare
    assert "pg.kind == 'already_active'" in bare
    assert "pg_subscribed and pg.kind" not in bare
    assert "pg_subscribed" not in bare
    # Continue is the live state's destination, not a hard-coded /playground
    # (M2-F04).
    assert 'href="/playground">Continue</a>' not in bare
    assert (
        'class="ActHead-inpg-continue" href="{{ pg.primary_href }}">{{ pg.primary_label }}</a>'
        in bare
    )
    assert "Your Playground is paused" not in bare
    assert "Playground paused" not in bare
    assert LIVE_EXPIRED_STATUS not in bare
    base = BASE.read_text(encoding="utf-8")
    assert "expired_bareact" in base
    assert "expired_header_status" in base
    assert "path == '/laws/ndps'" in base
    assert "Playground paused" not in base
    app = APP.read_text(encoding="utf-8")
    page = app.split("async def law_detail_page", 1)[1].split(
        "async def bare_act_section_page", 1
    )[0]
    assert "bare_act_page_context(request, bare)" in page
    assert "def snapshot_is_expired_subscriber" not in page
    bare_page = BARE_PAGE.read_text(encoding="utf-8")
    assert "def bare_act_page_context" in bare_page
    assert "request_is_expired_subscriber" in bare_page
    assert "request_is_active_plus" in bare_page
    assert '"plus_bareact": request_is_active_plus(request)' in bare_page
    assert '"expired_bareact": expired_bareact' in bare_page
    assert "def snapshot_is_expired_subscriber" not in bare_page
    deps = DEPS.read_text(encoding="utf-8")
    assert "def request_is_expired_subscriber" in deps
    assert "BLOCK_PAID_PERIOD_ENDED" in deps
    view = VIEW.read_text(encoding="utf-8")
    assert 'badge_label="Already in Playground"' in view
    assert 'primary_label="Resume Playground"' in view


def test_plus_screens_and_expired_01_02_03_untouched() -> None:
    assert 'data-plus-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-expired-landing="desktop"' in LANDING.read_text(encoding="utf-8")
    assert 'data-plus-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-expired-browse="desktop"' in BROWSE.read_text(encoding="utf-8")
    assert 'data-plus-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert 'data-expired-laws="desktop"' in LAWS.read_text(encoding="utf-8")
    assert "data-plus-bareact" in BARE.read_text(encoding="utf-8")
    assert "playground_add_panel.html" in ADD.read_text(encoding="utf-8")
    assert 'data-add-step="confirm"' in ADD_PANEL.read_text(encoding="utf-8")
    assert "data-pg-add-confirm" in ADD_PANEL.read_text(encoding="utf-8")
    assert 'data-plus-playground="desktop"' in HOME.read_text(encoding="utf-8")
    assert 'data-plus-subscription="desktop"' in MANAGE.read_text(encoding="utf-8")
    assert 'data-plus-today="desktop"' in DASH.read_text(encoding="utf-8")
    assert 'data-plus-calendar="desktop"' in CAL.read_text(encoding="utf-8")
    assert 'data-plus-profile="desktop"' in PROFILE.read_text(encoding="utf-8")
    assert 'data-plus-settings="desktop"' in SETTINGS.read_text(encoding="utf-8")
    landing = LANDING.read_text(encoding="utf-8")
    assert "data-expired-bareact" not in landing
    browse = BROWSE.read_text(encoding="utf-8")
    assert "data-expired-bareact" not in browse
    laws = LAWS.read_text(encoding="utf-8")
    assert "data-expired-bareact" not in laws
    for path in (ADD, ADD_PANEL, HOME, MANAGE, DASH, CAL, PROFILE, SETTINGS):
        text = path.read_text(encoding="utf-8")
        assert "data-expired-bareact" not in text
        assert "expired_bareact" not in text
        assert "data-expired-landing" not in text
    mobile = MOBILE.read_text(encoding="utf-8")
    assert "data-expired-bareact" not in mobile
    assert "data-expired-bareact" not in STYLES.read_text(encoding="utf-8")
    assert "def request_is_active_plus" in DEPS.read_text(encoding="utf-8")
    assert 'snapshot.tier == "plus"' in DEPS.read_text(encoding="utf-8")


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


def test_expired_phone_bareact_unchanged(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_then_expire(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    act = get_bare_act("ndps")
    assert act is not None

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
              const head = document.querySelector('.ActHead[data-expired-bareact]');
              const list = head && head.querySelector('[data-act-list]');
              const cont = head && head.querySelector('.ActHead-inpg-continue');
              return {
                expiredPresent: Boolean(head),
                headCount: document.querySelectorAll('.ActHead').length,
                headDisplay: head ? getComputedStyle(head).display : null,
                details: list ? list.querySelectorAll('details.bareact-chapter').length : 0,
                openDetails: list ? list.querySelectorAll('details[open]').length : 0,
                resumeText: cont && cont.textContent.trim(),
                resumeHref: cont && cont.getAttribute('href'),
                continueShown: head ? head.innerText.includes('Continue') : false,
              };
            }"""
        )
        browser.close()
    assert phone["expiredPresent"] is True
    assert phone["headCount"] == 1
    assert phone["headDisplay"] != "none"
    assert phone["details"] == act.chapter_count
    assert phone["openDetails"] == 0
    assert phone["resumeText"] == "Resume Playground"
    assert phone["resumeHref"] == PLAYGROUND_BILLING_PATH
    assert phone["continueShown"] is False


def test_expired_bareact_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _seed_ndps_then_expire(client)
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    act = get_bare_act("ndps")
    assert act is not None

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "expired_bareact_screen04_1280.png"
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
              const plus = document.querySelector('.ActHead[data-plus-bareact]');
              const brand = document.querySelector('.brand');
              const mark = document.querySelector('.brand-mark');
              const band = head && head.querySelector('.ActHead-band');
              const back = head && head.querySelector('.ActHead-back');
              const cluster = head && head.querySelector('.ActHead-inpg');
              const sections = head && head.querySelector('.ActHead-inpg-sections');
              const cont = head && head.querySelector('.ActHead-inpg-continue');
              const rows = head
                ? [...head.querySelectorAll('[data-act-list] summary.bareact-chapter-row')]
                : [];
              const schedules = head
                ? head.querySelectorAll('[data-act-list] .bareact-schedule-row').length
                : 0;
              const panelText = band ? band.innerText : '';
              return {
                present: Boolean(head),
                plusPresent: Boolean(plus),
                headCount: document.querySelectorAll('.ActHead').length,
                headDisplay: head && getComputedStyle(head).display,
                kind: head && head.getAttribute('data-pg-kind'),
                brandHref: brand.getAttribute('href'),
                markFilter: getComputedStyle(mark).filter,
                backHref: back && back.getAttribute('href'),
                kicker: head && head.querySelector('.ActHead-kicker').textContent.trim(),
                title: head && head.querySelector('.ActHead-title').textContent.trim(),
                meta: head && head.querySelector('.ActHead-meta').textContent.trim(),
                already: panelText.includes('Already in Playground'),
                clusterPresent: !!cluster,
                sectionsHref: sections && sections.getAttribute('href'),
                sectionsText: sections && sections.textContent.trim(),
                continueHref: cont && cont.getAttribute('href'),
                continueText: cont && cont.textContent.trim(),
                addShown: /Add to Playground/.test(panelText),
                subscribe: panelText.includes('Subscribe to use Playground'),
                signIn: panelText.includes('Sign in to use Playground'),
                invented: /Your plan expired|Resume subscription|Premium|Unlimited|Unlock all|Free plan|All 3 slots/.test(panelText),
                rowCount: rows.length,
                rowTitles: rows.map((el) =>
                  el.querySelector('.bareact-chapter-name').textContent.trim()
                ),
                scheduleCount: schedules,
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

        page.locator(".ActHead[data-expired-bareact] .ActHead-back").click()
        page.wait_for_function("() => location.pathname === '/laws'", timeout=8000)
        laws_path = page.evaluate("() => location.pathname")
        browser.close()

    assert geo["present"] is True
    assert geo["plusPresent"] is False
    assert geo["headCount"] == 1
    assert geo["headDisplay"] != "none"
    assert geo["kind"] == "already_active"
    assert geo["brandHref"] == "/dashboard"
    assert "invert" in geo["markFilter"]
    assert geo["backHref"] == "/laws"
    assert geo["kicker"] == KICKER
    assert geo["title"] == act.title
    assert geo["meta"] == act.head_meta_label
    assert geo["already"] is True
    assert geo["clusterPresent"] is True
    assert geo["sectionsText"] == "Sections"
    assert geo["sectionsHref"] == sections_path("ndps")
    assert geo["continueText"] == "Resume Playground"
    assert geo["continueHref"] == PLAYGROUND_BILLING_PATH
    assert geo["addShown"] is False
    assert geo["subscribe"] is False
    assert geo["signIn"] is False
    assert geo["invented"] is False
    assert geo["rowCount"] == act.chapter_count
    assert geo["rowTitles"] == [chapter.title for chapter in act.chapters]
    assert geo["scheduleCount"] == len(act.schedules)
    assert geo["accountName"] == "Sanjay"
    assert geo["accountStatus"] == LIVE_EXPIRED_STATUS
    assert geo["navLabels"] == [
        "Today",
        "Browse",
        "Playground",
        "Calendar",
        "Profile",
    ]
    assert geo["browseActive"] == "Browse"
    assert laws_path == "/laws"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_plus_bareact_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path, units=UNITS if UNITS.exists() else MINI_UNITS)
    client = TestClient(app)
    _sign_in(client)
    _subscribe(client)
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    act = get_bare_act("ndps")
    assert act is not None
    state = _live_state(client)
    assert state.kind == "already_active"
    assert state.primary_href != PLAYGROUND_BILLING_PATH

    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "expired_bareact_screen04_plus_regression_1280.png"
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
              const expired = document.querySelector('.ActHead[data-expired-bareact]');
              const plus = document.querySelector('.ActHead[data-plus-bareact]');
              const cluster = plus && plus.querySelector('.ActHead-inpg');
              const sections = plus && plus.querySelector('.ActHead-inpg-sections');
              const cont = plus && plus.querySelector('.ActHead-inpg-continue');
              return {
                expiredPresent: Boolean(expired),
                plusPresent: Boolean(plus),
                already: plus && plus.innerText.includes('Already in Playground'),
                clusterPresent: !!cluster,
                sectionsHref: sections && sections.getAttribute('href'),
                continueHref: cont && cont.getAttribute('href'),
                continueText: cont && cont.textContent.trim(),
                accountStatus: document.querySelector('.account-menu-btn-status').textContent.trim(),
                title: plus && plus.querySelector('.ActHead-title').textContent.trim(),
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.screenshot(path=str(shot_path), full_page=False)
        browser.close()

    assert geo["expiredPresent"] is False
    assert geo["plusPresent"] is True
    assert geo["already"] is True
    assert geo["clusterPresent"] is True
    assert geo["sectionsHref"] == sections_path("ndps")
    assert geo["continueHref"] == state.primary_href
    assert geo["continueText"] == state.primary_label
    assert geo["accountStatus"] == "RecallC Plus"
    assert geo["title"] == act.title
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
