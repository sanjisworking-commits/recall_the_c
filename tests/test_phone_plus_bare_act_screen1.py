"""Phone Plus Bare Act head Screen 01 (CTA map plus/01-screen).

Authorized: ChatGPT. Authenticated active Plus GET /laws/ndps at 390x844.
Desktop Plus Screen 04 is the functional contract. M2: one generated head
serves both widths (CSS does the layout) and uses live playground_state
(already_active / eligible_to_add / roster_full / re_add). The
already_active chip links Continue / Start learning to the state's own
primary_href (M2-F04); empty roster is Add, not enrolled.
Free/Guest/Expired/Halted/Pro and other laws get the same head with their
own state. Plus 02 is not this screen.
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
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.roster.period import playground_month_bounds
from constitution_memorizer.playground.urls import add_path, law_path, remove_path, sections_path
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
STYLES = ROOT / "src/constitution_memorizer/web/static/styles.css"
MOBILE = ROOT / "src/constitution_memorizer/web/static/mobile.css"
PG_CSS = ROOT / "src/constitution_memorizer/web/static/playground.css"
MOBILE_JS = ROOT / "src/constitution_memorizer/web/static/mobile.js"
USER = UUID("11111111-1111-4111-8111-111111111111")
KICKER = "Bare Act · India Code"
INVENTED = (
    "Premium",
    "Unlimited",
    "renews",
    "Unlock all",
    "Free plan",
    "device limit",
    "replacement",
)
TAB_HREFS = (
    ("Today", "/dashboard"),
    ("Browse", "/browse"),
    ("Playground", "/playground"),
    ("Calendar", "/calendar"),
    ("Profile", "/profile"),
)
FULL_LAWS = (
    "bns",
    "bnss",
    "uapa",
    "pss",
    "mtp",
    "ipc",
    "crpc",
    "cpc",
    "iea",
    "ida",
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


def _plus_client(tmp_path: Path) -> TestClient:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    return client


def _confirm_add(client: TestClient, law_id: str, *, scope: str = "sections"):
    payload = dict(_csrf(client))
    payload["confirm"] = "add"
    payload["scope"] = scope
    preview = client.post(add_path(law_id), data=_csrf(client), follow_redirects=False)
    if preview.status_code == 303 and "/playground/roster" in (
        preview.headers.get("location") or ""
    ):
        return client.post(add_path(law_id), data=payload, follow_redirects=False)
    if preview.status_code == 200:
        return client.post(add_path(law_id), data=payload, follow_redirects=False)
    return preview


def _seed_roster(client: TestClient, *law_ids: str) -> None:
    roster = client.app.state.roster
    start, end = playground_month_bounds()
    roster._repo.ensure_period(
        USER,
        period_start=start,
        period_end=end,
        tier_snapshot="plus",
        law_limit=10,
    )
    for law_id in law_ids:
        result = roster._repo.consume_law(
            USER,
            period_start=start,
            law_id=law_id,
            law_limit=10,
            allow_new=True,
        )
        assert result.ok, result.status
        assert roster.is_law_active_this_period(USER, law_id) is True


def _head_attrs(html: str) -> str:
    match = re.search(r'<section\s+class="panel ActHead[^>]*>', html, re.S)
    assert match, "no generated Act head on the page"
    return re.sub(r"\s+", " ", match.group(0))


def _band(html: str) -> str:
    """Back link, kicker, title, meta, Playground action, About — no list."""
    return unescape(
        html.split('class="panel ActHead', 1)[1].split(
            '<div class="bareact-chapters"', 1
        )[0]
    )


def _cta(html: str) -> str:
    """The Playground action block alone (the About card lists a Sections row)."""
    band = _band(html)
    assert 'class="ActHead-cta LawPlaygroundCta"' in band, "no Playground action in the head"
    return band.split('class="ActHead-cta LawPlaygroundCta"', 1)[1].split("<button", 1)[0]


def _list(html: str) -> str:
    return unescape(
        html.split('<div class="bareact-chapters"', 1)[1].split("</section>", 1)[0]
    )


def _assert_no_phone_twins(html: str) -> None:
    """No per-surface head twins; the Screen 01 tab bar marker is not one."""
    for marker in (
        "data-plus-bareact-phone",
        "data-signed-in-bareact-phone",
        "data-guest-bareact-phone",
        "data-bareact-phone",
    ):
        assert re.search(marker + r"(?!-tabs)", html) is None, marker


def _tabs(html: str) -> str:
    return html.split("data-plus-bareact-phone-tabs", 1)[1].split("</nav>", 1)[0]


def _facts(client: TestClient) -> dict:
    history = tuple(
        sorted(
            (row.id, row.status, row.tier, row.is_current)
            for row in client.app.state.subscriptions.list_subscription_history(USER)
        )
    )
    roster = getattr(client.app.state, "roster", None)
    overlay = getattr(client.app.state, "playground", None)
    devices = getattr(client.app.state, "device_service", None)
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
        "devices": tuple(
            sorted(str(getattr(item, "id", item)) for item in devices.list_devices(USER))
        )
        if devices is not None and hasattr(devices, "list_devices")
        else (),
    }


def _assert_generated_head(html: str, slug: str = "ndps") -> None:
    """Kicker/title/meta read off the Act model; the list counts match it."""
    act = get_bare_act(slug)
    assert act is not None
    band = _band(html)
    assert f'data-act-head="{slug}"' in _head_attrs(html)
    assert "← Laws" in band
    assert 'class="ActHead-back" href="/laws"' in band
    assert f'<p class="ActHead-kicker">{KICKER}' in band
    assert f'<h1 class="ActHead-title">{act.title}</h1>' in band
    assert f'<p class="ActHead-meta">{act.head_meta_label}</p>' in band
    assert f'href="/laws/{slug}/section/' not in band
    assert f'href="/laws/{slug}/schedule/' not in band
    assert "<details" not in band
    listing = _list(html)
    assert listing.count('<summary class="bareact-chapter-row" aria-expanded="false">') == act.chapter_count
    assert listing.count("<details") == act.chapter_count
    assert re.search(r"<details[^>]*\sopen", listing) is None
    assert listing.count('<div class="bareact-schedule-row') == len(act.schedules)
    assert listing.count(f'class="bareact-section-row" href="/laws/{slug}/section/') == len(
        act.section_order
    )
    for chapter in act.chapters:
        assert f"Chapter {chapter.number}</span>" in listing
        assert f'<span class="bareact-chapter-name">{chapter.title}</span>' in listing
        assert (
            f'<span class="bareact-chapter-range"><span class="ActHead-range-word">Sections </span>{chapter.range_label}</span>'
            in listing
        )
    assert "data-bareact-tabs" not in html
    assert "This Act has no Schedules." not in html


def test_phone_plus_already_active_uses_live_membership(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    added = _confirm_add(client, "ndps")
    assert added.status_code in {200, 303}
    page = client.get("/laws/ndps")
    assert page.status_code == 200
    html = unescape(page.text)
    attrs = _head_attrs(html)
    assert "data-plus-bareact" in attrs
    assert 'data-pg-kind="already_active"' in attrs
    assert 'data-membership="in_playground"' in attrs
    _assert_no_phone_twins(html)
    _assert_generated_head(html)
    act = get_bare_act("ndps")
    assert act is not None
    band = _band(html)
    assert "8 Chapters" in band
    assert "6 Chapters" not in band
    cta = _cta(html)
    assert 'data-pg-kind="already_active"' in cta
    assert "Already in Playground" in cta
    assert 'class="LawStatusBadge" data-status="in_playground"' in cta
    assert f'class="ActHead-inpg-sections" href="{sections_path("ndps")}">Sections<' in cta
    # Sections scope with nothing picked yet: the live state's primary is
    # Start learning → the section picker (M2-F04), never a fixed /playground.
    assert f'class="ActHead-inpg-continue" href="{sections_path("ndps")}">Start learning<' in cta
    assert ">Continue<" not in cta
    assert 'href="/playground"' not in band
    assert "+ Add to Playground" not in cta
    assert "Subscribe to use Playground" not in cta
    assert "Sign in to use Playground" not in cta
    assert 'data-pg-kind="subscribe"' not in cta
    assert 'href="/billing/subscriptions"' not in band
    for phrase in INVENTED:
        assert phrase not in band, phrase
    client.get("/laws/ndps")
    before = _facts(client)
    assert before["active"] == ("ndps",)
    assert client.get("/laws/ndps").status_code == 200
    assert _facts(client) == before

    # Entire Act selected: the same chip says Continue and opens the law's
    # own Playground page.
    entire = _plus_client(tmp_path / "entire")
    assert _confirm_add(entire, "ndps", scope="entire").status_code in {200, 303}
    entire_cta = _cta(unescape(entire.get("/laws/ndps").text))
    assert f'class="ActHead-inpg-continue" href="{law_path("ndps")}">Continue<' in entire_cta
    assert f'class="ActHead-inpg-sections" href="{sections_path("ndps")}">Sections<' in entire_cta


def test_phone_plus_eligible_to_add_keeps_add_sheet_trigger(tmp_path: Path) -> None:
    client = _plus_client(tmp_path)
    html = unescape(client.get("/laws/ndps").text)
    assert 'data-pg-kind="eligible_to_add"' in _head_attrs(html)
    _assert_generated_head(html)
    cta = _cta(html)
    assert 'data-pg-kind="eligible_to_add"' in cta
    assert 'class="ActHead-btn"' in cta
    assert "+ Add to Playground" in cta
    assert f'href="{add_path("ndps")}"' in cta
    assert "data-pg-sheet" in cta
    assert "Already in Playground" not in cta
    assert ">Sections<" not in cta
    assert "ActHead-inpg" not in cta
    assert "Subscribe to use Playground" not in cta
    assert "Sign in to use Playground" not in cta
    assert client.app.state.roster.is_law_active_this_period(USER, "ndps") is False
    preview = client.post(add_path("ndps"), data=_csrf(client), follow_redirects=False)
    assert preview.status_code in {200, 303}


def test_phone_plus_roster_full_and_re_add_keep_live_kinds(tmp_path: Path) -> None:
    full = _plus_client(tmp_path / "full")
    _seed_roster(full, *FULL_LAWS)
    full_html = unescape(full.get("/laws/ndps").text)
    assert 'data-pg-kind="roster_full"' in _head_attrs(full_html)
    full_cta = _cta(full_html)
    assert 'data-pg-kind="roster_full"' in full_cta
    assert 'class="ActHead-btn ActHead-btn--ghost"' in full_cta
    assert "Playground full this month" in full_cta
    assert 'class="ActHead-link" href="/playground/roster/next">Plan next month<' in full_cta
    assert "Already in Playground" not in full_cta
    assert "Subscribe to use Playground" not in full_cta
    assert full.app.state.roster.is_law_active_this_period(USER, "ndps") is False

    readd = _plus_client(tmp_path / "readd")
    added = _confirm_add(readd, "ndps")
    assert added.status_code in {200, 303}
    removed = readd.post(remove_path("ndps"), data=_csrf(readd), follow_redirects=False)
    assert removed.status_code in {200, 303}
    readd_html = unescape(readd.get("/laws/ndps").text)
    assert 'data-pg-kind="re_add"' in _head_attrs(readd_html)
    readd_cta = _cta(readd_html)
    assert 'data-pg-kind="re_add"' in readd_cta
    assert ">Add back<" in readd_cta
    assert f'href="{add_path("ndps")}"' in readd_cta
    assert "data-pg-sheet" in readd_cta
    assert 'class="ActHead-note">No extra space used.<' in readd_cta
    assert "Subscribe to use Playground" not in readd_cta
    assert readd.app.state.roster.is_law_active_this_period(USER, "ndps") is False


def test_phone_plus_five_tabs_browse_active_only(tmp_path: Path) -> None:
    html = _plus_client(tmp_path).get("/laws/ndps").text
    assert "data-plus-bareact-phone-tabs" in html
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
    dash = _plus_client(tmp_path / "dash").get("/dashboard").text
    assert "data-plus-bareact-phone-tabs" not in dash


def test_phone_plus_css_scope_pins_and_desktop_04_untouched() -> None:
    styles = STYLES.read_text(encoding="utf-8")
    assert "Bare Act head (M2)" in styles
    m2 = styles.split("Bare Act head (M2)", 1)[1].split(
        "Guest Playground intro (CTA map guest/06-screen)", 1
    )[0]
    # One head, both widths: the desktop rules first, the phone layout in
    # one @media block, nothing per cohort.
    assert ".ActHead-back {" in m2
    assert "min-height: 44px" in m2.split(".ActHead-back {", 1)[1].split("}", 1)[0]
    cta = m2.split(".ActHead-cta.LawPlaygroundCta {", 1)[1].split("}", 1)[0]
    assert "width: 380px" in cta
    assert m2.count("@media (max-width: 560px)") == 1
    phone_block = m2.split("@media (max-width: 560px)", 1)[1]
    assert ".ActHead-inpg-sections,\n  .ActHead-inpg-continue {" in phone_block
    assert "min-height: 44px" in phone_block.split(".ActHead-inpg-continue {", 1)[1].split("}", 1)[0]
    assert ".ActHead-range-word" in phone_block
    assert "display: none" in phone_block.split(".ActHead-range-word {", 1)[1].split("}", 1)[0]
    assert "var(--m-gutter, 18px)" in phone_block
    assert re.search(r"(^|[^A-Za-z0-9_-])order\s*:", m2) is None
    assert "sun" not in m2.lower()
    for legacy in (
        "[data-plus-bareact-phone]",
        "[data-signed-in-bareact-desktop]",
        "[data-guest-bareact-desktop]",
        "[data-bareact-phone]",
        'data-plus-bareact="desktop"',
        "guest-bareact-",
        "signed-bareact-",
    ):
        assert legacy not in styles, legacy
    mobile = MOBILE.read_text(encoding="utf-8")
    for legacy in (
        "is plus/01-screen:",
        "[data-plus-bareact-phone]",
        "guest-bareact-",
        "signed-bareact-",
    ):
        assert legacy not in mobile, legacy
    # The legacy phone row rules stay for the shared .bareact-* classes.
    assert 'body[data-mscreen="bareact"] .bareact-chapter-row {' in mobile
    assert 'body[data-mscreen="bareact"] .bareact-section-row {' in mobile
    pg_css = PG_CSS.read_text(encoding="utf-8")
    assert "data-plus-bareact" not in pg_css
    base = BASE.read_text(encoding="utf-8")
    assert "data-plus-bareact-phone-tabs" in base
    assert "signed_in_plus_bareact_phone" in base
    assert "styles.css?v=main88" in base
    assert "styles.css?v=main87" not in base
    assert "mobile.css?v=mob107" in base
    assert "mobile.css?v=mob106" not in base
    assert "playground.css?v=pg50" in base
    assert "mobile.js?v=mob30" in base
    bare = BARE.read_text(encoding="utf-8")
    assert "data-plus-bareact" in bare
    _assert_no_phone_twins(bare)
    assert 'class="ActHead-cta LawPlaygroundCta"' in bare
    assert 'href="/playground"' not in bare
    assert "Already in Playground" not in bare
    assert "+ Add to Playground" not in bare
    assert "pg.primary_href" in bare
    assert 'class="bareact-chapter-row" aria-expanded="false"' in bare
    mobile_js = MOBILE_JS.read_text(encoding="utf-8")
    accordion = mobile_js.split("[data-bareact-accordion]", 1)[1].split("function initActInfo", 1)[0]
    assert 'setAttribute("aria-expanded"' in accordion


def test_phone_plus_cohorts_and_other_laws_stay_separate(tmp_path: Path) -> None:
    plus = _plus_client(tmp_path / "plus")
    plus_html = plus.get("/laws/ndps").text
    assert "data-plus-bareact" in _head_attrs(plus_html)
    _assert_no_phone_twins(plus_html)
    bns = plus.get("/laws/bns").text
    # The same head serves BNS with the viewer's Plus state; the Screen 01
    # tab bar and header status stay NDPS-only.
    bns_attrs = _head_attrs(bns)
    assert 'data-act-head="bns"' in bns_attrs
    assert "data-plus-bareact" in bns_attrs
    _assert_generated_head(bns, "bns")
    assert "data-plus-bareact-phone-tabs" not in bns
    assert "RecallC Plus" not in bns.split("<header", 1)[1].split("</header>", 1)[0]

    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    free_html = free.get("/laws/ndps").text
    free_attrs = _head_attrs(free_html)
    assert "data-plus-bareact" not in free_attrs
    assert 'data-pg-kind="subscribe"' in free_attrs
    assert "data-plus-bareact-phone-tabs" not in free_html
    assert "data-signed-in-bareact-phone-tabs" in free_html
    _assert_generated_head(free_html)
    assert "Subscribe to use Playground" in _cta(free_html)

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
    guest_attrs = _head_attrs(guest_html)
    assert "data-plus-bareact" not in guest_attrs
    assert 'data-pg-kind="guest"' in guest_attrs
    _assert_generated_head(guest_html)
    assert "Sign in to use Playground" in _cta(guest_html)

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
    expired_html = expired.get("/laws/ndps").text
    expired_attrs = _head_attrs(expired_html)
    assert "data-plus-bareact" not in expired_attrs
    assert "data-expired-bareact" in expired_attrs
    _assert_generated_head(expired_html)
    assert "Resume Playground" in _cta(expired_html)

    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/laws/ndps").text
    halted_attrs = _head_attrs(halted_html)
    assert "data-plus-bareact" not in halted_attrs
    assert "data-halted-bareact" in halted_attrs
    _assert_generated_head(halted_html)
    assert 'data-pg-kind="resume"' in _cta(halted_html)

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/laws/ndps").text
    pro_attrs = _head_attrs(pro_html)
    assert "data-plus-bareact" not in pro_attrs
    assert 'data-pg-kind="eligible_to_add"' in pro_attrs
    _assert_generated_head(pro_html)
    assert "+ Add to Playground" in _cta(pro_html)


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
        added = _confirm_add(client, "ndps", scope="entire")
        assert added.status_code in {200, 303}
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    return session, client


def test_phone_plus_bareact_screen01_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    session, _client = _playwright_session(app, tmp_path, enrolled=True)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_plus_bare_act_screen01_390x844.png"
    origin = f"http://127.0.0.1:{port}"
    act = get_bare_act("ndps")
    assert act is not None

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
              const head = document.querySelector('.ActHead[data-act-head="ndps"]');
              const band = head && head.querySelector('.ActHead-band');
              const header = document.querySelector('.site-header');
              const tabs = document.querySelector('[data-plus-bareact-phone-tabs]');
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
              const back = band && band.querySelector('.ActHead-back');
              const sections = band && band.querySelector('.ActHead-inpg-sections');
              const cont = band && band.querySelector('.ActHead-inpg-continue');
              const rows = head ? [...head.querySelectorAll('summary.bareact-chapter-row')] : [];
              const bandLinks = band
                ? band.querySelectorAll(
                    'a:not(.ActHead-back):not(.ActHead-inpg-sections):not(.ActHead-inpg-continue)'
                  )
                : [];
              const tabLinks = tabs ? [...tabs.querySelectorAll('a.mobile-tab')] : [];
              return {
                plusPresent: !!(head && head.hasAttribute('data-plus-bareact')),
                headDisplay: head ? getComputedStyle(head).display : null,
                twins: document.querySelectorAll(
                  '[data-plus-bareact-phone], [data-signed-in-bareact-desktop], [data-bareact-phone]'
                ).length,
                headerDisplay: header ? getComputedStyle(header).display : null,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                barCount: bars.length,
                visibleBarCount: visibleBars.length,
                visibleActiveCount: visibleActive.length,
                visibleAriaCount: visibleAria.length,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                title: band && band.querySelector('.ActHead-title').textContent.trim(),
                kicker: band && band.querySelector('.ActHead-kicker').textContent.trim(),
                meta: band && band.querySelector('.ActHead-meta').textContent.trim(),
                backText: back && back.textContent.replace(/\\s+/g, ' ').trim(),
                backHref: back && back.getAttribute('href'),
                backH: back ? back.getBoundingClientRect().height : 0,
                already: band && band.innerText.includes('Already in Playground'),
                sectionsText: sections && sections.textContent.trim(),
                sectionsHref: sections && sections.getAttribute('href'),
                sectionsH: sections ? sections.getBoundingClientRect().height : 0,
                continueText: cont && cont.textContent.trim(),
                continueHref: cont && cont.getAttribute('href'),
                continueH: cont ? cont.getBoundingClientRect().height : 0,
                subscribe: band && band.innerText.includes('Subscribe to use Playground'),
                rowCount: rows.length,
                rowTitles: rows.map((el) =>
                  el.querySelector('.bareact-chapter-name').textContent.trim()
                ),
                rangeWordDisplay: head && head.querySelector('.ActHead-range-word')
                  && getComputedStyle(head.querySelector('.ActHead-range-word')).display,
                extraBandLinks: bandLinks.length,
                tabLabels: tabLinks.map((el) => el.textContent.replace(/\\s+/g, ' ').trim()),
                tabHrefs: tabLinks.map((el) => el.getAttribute('href')),
                browseActive: visibleActive[0] && visibleActive[0].textContent.replace(/\\s+/g, ' ').trim(),
                details: head ? head.querySelectorAll('details').length : 0,
                openDetails: head ? head.querySelectorAll('details[open]').length : 0,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)
        page.locator(".ActHead[data-plus-bareact] .ActHead-back").click()
        page.wait_for_function("() => location.pathname === '/laws'", timeout=8000)
        laws_path = page.evaluate("() => location.pathname")
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.locator(".ActHead[data-plus-bareact] .ActHead-inpg-sections").click()
        page.wait_for_url("**/playground/laws/ndps/sections**", timeout=8000)
        sections_url = page.url
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.locator(".ActHead[data-plus-bareact] .ActHead-inpg-continue").click()
        page.wait_for_url("**/playground/laws/ndps**", timeout=8000)
        playground_url = page.url
        playground_gate = "data-signed-in-pg-gate" in page.content()
        page.set_viewport_size({"width": 390, "height": 700})
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        short_overflow = page.evaluate(
            "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        browser.close()

    assert geo["plusPresent"] is True
    assert geo["headDisplay"] != "none"
    assert geo["twins"] == 0
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
    assert geo["backText"] == "← Laws"
    assert geo["backHref"] == "/laws"
    assert geo["backH"] >= 44
    assert geo["already"] is True
    assert geo["sectionsText"] == "Sections"
    assert geo["sectionsHref"] == sections_path("ndps")
    assert geo["sectionsH"] >= 44
    assert geo["continueText"] == "Continue"
    assert geo["continueHref"] == law_path("ndps")
    assert geo["continueH"] >= 44
    assert geo["subscribe"] is False
    assert geo["rowCount"] == act.chapter_count
    assert geo["rowTitles"] == [chapter.title for chapter in act.chapters]
    assert geo["rangeWordDisplay"] == "none"
    assert geo["extraBandLinks"] == 0
    assert geo["tabLabels"] == [label for label, _href in TAB_HREFS]
    assert geo["tabHrefs"] == [href for _label, href in TAB_HREFS]
    assert geo["browseActive"] == "Browse"
    assert geo["details"] == act.chapter_count
    assert geo["openDetails"] == 0
    assert laws_path == "/laws"
    assert "/playground/laws/ndps/sections" in sections_url
    assert law_path("ndps") in playground_url
    assert playground_gate is False
    assert short_overflow is False
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_plus_bareact_screen01_eligible_390x844(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    session, _client = _playwright_session(app, tmp_path, enrolled=False)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_plus_bare_act_screen01_eligible_390x844.png"
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
              const head = document.querySelector('.ActHead[data-plus-bareact]');
              const cta = head && head.querySelector('.ActHead-cta');
              const add = head && head.querySelector('.ActHead-btn[data-pg-sheet]');
              const box = add && add.getBoundingClientRect();
              return {
                kind: cta && cta.getAttribute('data-pg-kind'),
                href: add && add.getAttribute('href'),
                text: add && add.textContent.replace(/\\s+/g, ' ').trim(),
                addH: box ? box.height : 0,
                already: head && head.innerText.includes('Already in Playground'),
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
              };
            }"""
        )
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _screenshot(page, shot_path)
        page.locator(".ActHead[data-plus-bareact] [data-pg-sheet]").click()
        page.wait_for_selector("[data-pg-add]", timeout=8000)
        dialog = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-pg-add]');
              return {
                kind: panel && panel.getAttribute('data-pg-kind'),
                panels: document.querySelectorAll('[data-pg-add]').length,
                twins: panel ? panel.querySelectorAll('[data-plus-add-desktop], [data-plus-add-phone]').length : -1,
                title: panel && panel.querySelector('[data-add-step="confirm"] .pg-add-title')
                  && panel.querySelector('[data-add-step="confirm"] .pg-add-title').textContent.trim(),
                unlock: !!(panel && panel.innerText.includes('Unlock Playground')),
                url: location.pathname,
              };
            }"""
        )
        page.keyboard.press("Escape")
        still = page.evaluate("() => location.pathname")
        browser.close()

    assert geo["kind"] == "eligible_to_add"
    assert geo["href"] == add_path("ndps")
    assert geo["text"] == "+ Add to Playground"
    assert geo["addH"] >= 44
    assert geo["already"] is False
    assert geo["overflow"] is False
    assert dialog["kind"] == "eligible_to_add"
    assert dialog["panels"] == 1
    assert dialog["twins"] == 0
    assert dialog["title"] == "Add to Playground"
    assert dialog["unlock"] is False
    assert dialog["url"].endswith("/laws/ndps")
    assert still.endswith("/laws/ndps")
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000


def test_phone_plus_bareact_screen01_desktop_regression_1280(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    app = _mu_app(tmp_path)
    session, _client = _playwright_session(app, tmp_path, enrolled=True)
    port, _server = _serve(app)
    artifact_dir = Path("/opt/cursor/artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shot_path = artifact_dir / "phone_plus_bare_act_screen01_desktop_regression_1280.png"
    origin = f"http://127.0.0.1:{port}"
    act = get_bare_act("ndps")
    assert act is not None

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
              const head = document.querySelector('.ActHead[data-plus-bareact]');
              const tabs = document.querySelector('[data-plus-bareact-phone-tabs]');
              const header = document.querySelector('.site-header');
              const cluster = head && head.querySelector('.ActHead-cta');
              const box = cluster && cluster.getBoundingClientRect();
              const nav = [...document.querySelectorAll('.PrimaryTabs--top .nav-link')].map(
                (el) => el.textContent.replace(/\\s+/g, ' ').trim()
              );
              const cont = head && head.querySelector('.ActHead-inpg-continue');
              const sections = head && head.querySelector('.ActHead-inpg-sections');
              return {
                headDisplay: head ? getComputedStyle(head).display : null,
                twins: document.querySelectorAll(
                  '[data-plus-bareact-phone], [data-signed-in-bareact-desktop], [data-bareact-phone]'
                ).length,
                tabsDisplay: tabs ? getComputedStyle(tabs).display : null,
                headerDisplay: header ? getComputedStyle(header).display : null,
                clusterW: box ? box.width : 0,
                rangeWordDisplay: head && head.querySelector('.ActHead-range-word')
                  && getComputedStyle(head.querySelector('.ActHead-range-word')).display,
                already: head && head.innerText.includes('Already in Playground'),
                continueHref: cont && cont.getAttribute('href'),
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

    assert geo["headDisplay"] != "none"
    assert geo["twins"] == 0
    assert geo["tabsDisplay"] == "none"
    assert geo["headerDisplay"] != "none"
    assert geo["clusterW"] == pytest.approx(380, abs=8)
    assert geo["rangeWordDisplay"] != "none"
    assert geo["already"] is True
    assert geo["continueHref"] == law_path("ndps")
    assert geo["sectionsHref"] == sections_path("ndps")
    assert geo["navLabels"] == [label for label, _href in TAB_HREFS]
    assert geo["title"] == act.title
    assert geo["account"] == "Sanjay"
    assert geo["status"] == "RecallC Plus"
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
