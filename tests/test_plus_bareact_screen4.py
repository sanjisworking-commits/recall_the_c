"""Plus cohort desktop NDPS Bare Act head Screen 04 (CTA map plus/04-screen).

Authorized: ChatGPT. Authenticated multiuser GET /laws/ndps with a real
active Plus EntitlementSnapshot. M2: one generated Act head serves every
Bare Act and every viewer; the Playground action switches on the live
``playground_state.kind`` only. The "Already in Playground" chip links
Continue / Start learning to the state's own ``primary_href`` (M2-F04).
RecallC Plus header is Screen 04 NDPS only — not a /laws/{id} leak.
"""

from __future__ import annotations

import re
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
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.playground.roster.period import playground_month_bounds
from constitution_memorizer.playground.urls import add_path, law_path, sections_path
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
BARE = ROOT / "src/constitution_memorizer/web/templates/bare_act.html"
BASE = ROOT / "src/constitution_memorizer/web/templates/base.html"
APP = ROOT / "src/constitution_memorizer/web/app.py"
PAGE = ROOT / "src/constitution_memorizer/web/bare_act_page.py"
DEPS = ROOT / "src/constitution_memorizer/entitlements/dependencies.py"
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


def _head_attrs(html: str) -> str:
    """The opening tag of the one generated Act head, whitespace-folded."""
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


def _assert_generated_head(html: str, slug: str = "ndps") -> None:
    """Kicker/title/meta read off the Act model; the list counts match it."""
    act = get_bare_act(slug)
    assert act is not None
    band = _band(html)
    assert f'data-act-head="{slug}"' in _head_attrs(html)
    assert 'class="ActHead-back" href="/laws"' in band
    assert "← Laws" in band
    assert f'<p class="ActHead-kicker">{KICKER}' in band
    assert f'<h1 class="ActHead-title">{act.title}</h1>' in band
    assert f'<p class="ActHead-meta">{act.head_meta_label}</p>' in band
    assert 'class="bareact-info-toggle ActHead-about"' in band
    assert 'aria-expanded="false"' in band
    assert "data-bareact-info hidden" in band
    # The band holds the action, never the reader links.
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
    assert "data-bareact-tabs" not in html
    assert "This Act has no Schedules." not in html


def test_plus_bareact_add_path_for_eligible_law_not_in_playground(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    html = client.get("/laws/ndps").text
    attrs = _head_attrs(html)
    assert "data-plus-bareact" in attrs
    assert 'data-pg-kind="eligible_to_add"' in attrs
    assert "data-expired-bareact" not in attrs
    assert "data-halted-bareact" not in attrs
    _assert_generated_head(html)
    band = _band(html)
    header = _header(html)
    assert 'data-pg-kind="eligible_to_add"' in band
    assert 'class="ActHead-cta LawPlaygroundCta" data-law-id="ndps"' in band
    assert "+ Add to Playground" in band
    assert f'href="{add_path("ndps")}"' in band
    assert "data-pg-sheet" in band
    assert "ActHead-btn--ghost" not in band
    assert "Already in Playground" not in band
    assert ">Sections<" not in _cta(html)
    assert "ActHead-inpg" not in band
    assert "Subscribe to use Playground" not in band
    assert "Sign in to use Playground" not in band
    assert "RecallC Plus" in header
    assert "Free account" not in header
    for phrase in INVENTED:
        assert phrase not in band, phrase
    # The sheet is not served on the Act page; it opens from the CTA.
    assert "<dialog" not in html
    assert "data-pg-add" not in html
    preview = client.post(add_path("ndps"), data=_csrf(client), follow_redirects=False)
    assert preview.status_code in {200, 303}


def test_plus_bareact_already_active_uses_real_membership(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    added = _confirm_add(client, "ndps", scope="entire")
    assert added.status_code in {200, 303}
    html = client.get("/laws/ndps").text
    attrs = _head_attrs(html)
    assert "data-plus-bareact" in attrs
    assert 'data-pg-kind="already_active"' in attrs
    assert 'data-membership="in_playground"' in attrs
    _assert_generated_head(html)
    band = _band(html)
    assert "Already in Playground" in band
    assert 'class="LawStatusBadge" data-status="in_playground"' in band
    assert 'class="ActHead-inpg"' in band
    assert 'data-pg-kind="already_active"' in band
    assert f'class="ActHead-inpg-sections" href="{sections_path("ndps")}">Sections<' in band
    # M2-F04: Continue goes to the live state's primary_href — the law's
    # Playground page once the Entire Act is selected — not a fixed /playground.
    assert f'class="ActHead-inpg-continue" href="{law_path("ndps")}">Continue<' in band
    assert 'href="/playground"' not in band
    assert "+ Add to Playground" not in band
    assert "Subscribe to use Playground" not in band
    assert "RecallC Plus" in _header(html)


def test_plus_bareact_roster_membership_is_not_free_spoof(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    _seed_ndps_roster(client)
    html = client.get("/laws/ndps").text
    band = _band(html)
    assert "Already in Playground" in band
    assert 'data-pg-kind="already_active"' in _head_attrs(html)
    assert 'data-pg-kind="already_active"' in band
    assert "Subscribe to use Playground" not in band
    assert 'data-pg-kind="subscribe"' not in band
    # Seeded roster, nothing selected yet: the live state says Start
    # learning and sends the reader to the section picker (M2-F04).
    assert f'class="ActHead-inpg-sections" href="{sections_path("ndps")}">Sections<' in band
    assert f'class="ActHead-inpg-continue" href="{sections_path("ndps")}">Start learning<' in band
    assert ">Continue<" not in _cta(html)
    assert 'href="/playground"' not in band


def test_free_and_guest_bareact_unchanged(tmp_path: Path) -> None:
    free = TestClient(_mu_app(tmp_path / "free"))
    _sign_in(free)
    _seed_ndps_roster(free)
    free_html = free.get("/laws/ndps").text
    free_attrs = _head_attrs(free_html)
    assert "data-plus-bareact" not in free_attrs
    assert 'data-pg-kind="subscribe"' in free_attrs
    _assert_generated_head(free_html)
    free_band = _band(free_html)
    assert "Subscribe to use Playground" in free_band
    assert f'href="{add_path("ndps")}"' in free_band
    assert "Already in Playground" not in free_band
    assert "Free account" in _header(free_html)
    assert "RecallC Plus" not in _header(free_html)

    guest_html = TestClient(_mu_app(tmp_path / "guest")).get("/laws/ndps").text
    guest_attrs = _head_attrs(guest_html)
    assert "data-plus-bareact" not in guest_attrs
    assert 'data-pg-kind="guest"' in guest_attrs
    _assert_generated_head(guest_html)
    assert "Sign in to use Playground" in _band(guest_html)
    assert "RecallC Plus" not in guest_html
    # One template, no per-cohort twins.
    for marker in (
        "data-guest-bareact-desktop",
        "data-signed-in-bareact-desktop",
        "data-bareact-phone",
        "guest-bareact-",
        "signed-bareact-",
    ):
        assert marker not in guest_html, marker
        assert marker not in free_html, marker


def test_halted_expired_and_pro_are_not_plus_screen_04(tmp_path: Path) -> None:
    halted = TestClient(_mu_app(tmp_path / "halted"))
    _sign_in(halted)
    _subscribe(halted, status="halted")
    halted_html = halted.get("/laws/ndps").text
    halted_attrs = _head_attrs(halted_html)
    assert "data-plus-bareact" not in halted_attrs
    assert "data-halted-bareact" in halted_attrs
    assert 'data-pg-kind="resume"' in halted_attrs
    _assert_generated_head(halted_html)
    assert "RecallC Plus" not in _header(halted_html)

    expired = TestClient(_mu_app(tmp_path / "expired"))
    _sign_in(expired)
    _subscribe(expired, status="expired")
    expired_html = expired.get("/laws/ndps").text
    assert "data-plus-bareact" not in _head_attrs(expired_html)
    _assert_generated_head(expired_html)
    assert "RecallC Plus" not in _header(expired_html)

    pro = TestClient(_mu_app(tmp_path / "pro"))
    _sign_in(pro)
    _subscribe(pro, tier="pro")
    pro_html = pro.get("/laws/ndps").text
    pro_attrs = _head_attrs(pro_html)
    assert "data-plus-bareact" not in pro_attrs
    assert 'data-pg-kind="eligible_to_add"' in pro_attrs
    _assert_generated_head(pro_html)
    assert "+ Add to Playground" in _band(pro_html)
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
    # The same generated head serves BNS, carrying the viewer's Plus state;
    # only the Screen 04 header status is NDPS-specific.
    bns_attrs = _head_attrs(bns.text)
    assert 'data-act-head="bns"' in bns_attrs
    assert "data-plus-bareact" in bns_attrs
    _assert_generated_head(bns.text, "bns")
    laws = client.get("/laws")
    assert "RecallC Plus" in _header(laws.text)
    assert 'data-plus-laws="desktop"' in laws.text
    playground = client.get("/playground")
    assert "RecallC Plus" in _header(playground.text)
    assert 'data-plus-playground="desktop"' in playground.text


def test_plus_bareact_marker_uses_shared_predicate() -> None:
    bare = BARE.read_text(encoding="utf-8")
    assert "plus_bareact" in bare
    assert "data-plus-bareact" in bare
    assert 'data-plus-bareact="desktop"' not in bare
    assert "data-signed-in-bareact-desktop" not in bare
    assert "data-guest-bareact-desktop" not in bare
    assert "data-bareact-phone" not in bare
    assert 'href="/laws"' in bare
    # Labels and destinations come off the live state, never the template.
    assert "+ Add to Playground" not in bare
    assert "Already in Playground" not in bare
    assert 'href="/playground"' not in bare
    assert "pg.primary_href" in bare
    assert "pg.secondary_href" in bare
    assert "act.head_meta_label" in bare
    base = BASE.read_text(encoding="utf-8")
    assert "plus_bareact" in base
    assert "path == '/laws/ndps'" in base
    assert "path.startswith('/laws')" in base
    deps = DEPS.read_text(encoding="utf-8")
    assert "def request_is_active_plus" in deps
    page_src = PAGE.read_text(encoding="utf-8")
    assert "request_is_active_plus" in page_src
    assert '"plus_bareact": request_is_active_plus(request)' in page_src
    app_src = APP.read_text(encoding="utf-8")
    assert "bare_act_page_context" in app_src
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
    added = _confirm_add(client, "ndps", scope="entire")
    assert added.status_code in {200, 303}
    session = client.cookies.get(SESSION_COOKIE_NAME)
    assert session
    act = get_bare_act("ndps")
    assert act is not None

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
              const head = document.querySelector('.ActHead[data-act-head="ndps"]');
              const band = head.querySelector('.ActHead-band');
              const brand = document.querySelector('.brand');
              const mark = document.querySelector('.brand-mark');
              const back = band.querySelector('.ActHead-back');
              const add = band.querySelector('.ActHead-btn');
              const cluster = band.querySelector('.ActHead-inpg');
              const sections = band.querySelector('.ActHead-inpg-sections');
              const cont = band.querySelector('.ActHead-inpg-continue');
              const rows = [...head.querySelectorAll('summary.bareact-chapter-row')];
              const bandLinks = band.querySelectorAll(
                'a:not(.ActHead-back):not(.ActHead-btn):not(.ActHead-inpg-sections):not(.ActHead-inpg-continue)'
              );
              const panelText = band.innerText;
              return {
                present: head.hasAttribute('data-plus-bareact'),
                headDisplay: getComputedStyle(head).display,
                twins: document.querySelectorAll(
                  '[data-guest-bareact-desktop], [data-signed-in-bareact-desktop], [data-bareact-phone], [data-plus-bareact-phone]'
                ).length,
                brandHref: brand.getAttribute('href'),
                markFilter: getComputedStyle(mark).filter,
                backHref: back.getAttribute('href'),
                kicker: band.querySelector('.ActHead-kicker').textContent.trim(),
                title: band.querySelector('.ActHead-title').textContent.trim(),
                meta: band.querySelector('.ActHead-meta').textContent.trim(),
                already: panelText.includes('Already in Playground'),
                addText: add && add.textContent.trim(),
                clusterPresent: !!cluster,
                clusterW: cluster ? cluster.getBoundingClientRect().width : 0,
                sectionsHref: sections && sections.getAttribute('href'),
                sectionsText: sections && sections.textContent.trim(),
                continueHref: cont && cont.getAttribute('href'),
                continueText: cont && cont.textContent.trim(),
                subscribe: panelText.includes('Subscribe to use Playground'),
                signIn: panelText.includes('Sign in to use Playground'),
                rowCount: rows.length,
                rowTitles: rows.map((el) =>
                  el.querySelector('.bareact-chapter-name').textContent.trim()
                ),
                extraBandLinks: bandLinks.length,
                details: head.querySelectorAll('details').length,
                openDetails: head.querySelectorAll('details[open]').length,
                schedules: head.querySelectorAll('.bareact-schedule-row').length,
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

        page.locator(".ActHead[data-plus-bareact] .ActHead-back").click()
        page.wait_for_function("() => location.pathname === '/laws'", timeout=8000)
        laws_path = page.evaluate("() => location.pathname")
        laws_plus = page.evaluate(
            """() => !!document.querySelector('[data-plus-laws="desktop"]')"""
        )
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        page.locator(".ActHead[data-plus-bareact] .ActHead-inpg-continue").click()
        page.wait_for_url("**/playground/laws/ndps**", timeout=8000)
        playground_url = page.url
        playground_gate = "data-signed-in-pg-gate" in page.content()

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{origin}/laws/ndps", wait_until="networkidle")
        phone_geo = page.evaluate(
            """() => {
              const head = document.querySelector('.ActHead[data-act-head="ndps"]');
              const cta = head && head.querySelector('.ActHead-cta');
              return {
                plusPresent: !!(head && head.hasAttribute('data-plus-bareact')),
                headDisplay: head ? getComputedStyle(head).display : null,
                ctaW: cta ? cta.getBoundingClientRect().width : 0,
                headW: head ? head.getBoundingClientRect().width : 0,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                details: head ? head.querySelectorAll('details').length : 0,
              };
            }"""
        )
        browser.close()

    assert geo["present"] is True
    assert geo["headDisplay"] != "none"
    assert geo["twins"] == 0
    assert geo["brandHref"] == "/dashboard"
    assert "invert" in geo["markFilter"]
    assert geo["backHref"] == "/laws"
    assert geo["kicker"] == KICKER
    assert geo["title"] == act.title
    assert geo["meta"] == act.head_meta_label
    assert geo["already"] is True
    assert geo["addText"] is None
    assert geo["clusterPresent"] is True
    assert geo["clusterW"] == pytest.approx(380, abs=8)
    assert geo["sectionsText"] == "Sections"
    assert geo["sectionsHref"] == sections_path("ndps")
    assert geo["continueText"] == "Continue"
    assert geo["continueHref"] == law_path("ndps")
    assert geo["subscribe"] is False
    assert geo["signIn"] is False
    assert geo["rowCount"] == act.chapter_count
    assert geo["rowTitles"] == [chapter.title for chapter in act.chapters]
    assert geo["extraBandLinks"] == 0
    assert geo["details"] == act.chapter_count
    assert geo["openDetails"] == 0
    assert geo["schedules"] == len(act.schedules)
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
    assert law_path("ndps") in playground_url
    assert playground_gate is False
    assert phone_geo["plusPresent"] is True
    assert phone_geo["headDisplay"] != "none"
    assert phone_geo["ctaW"] > 0
    assert phone_geo["ctaW"] <= phone_geo["headW"]
    assert phone_geo["overflow"] is False
    assert phone_geo["details"] == act.chapter_count
    assert shot_path.is_file()
    assert shot_path.stat().st_size > 1000
