"""M2 — the Bare Act head family.

One generated head for every Bare Act and every viewer (M2-F01), chapter rows
that expand into real section links (F02), schedule rows that open their
readers (F03), CTA destinations identical to the live Playground state
(F04), the Add sheet as a dialog over the Act page (F05, decision Q4), the
About card kept below the action (F06), chapterless Acts listed flat (F07).
Everything is read off the live model; nothing here is a per-law constant.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.playground.eligibility import (
    is_playground_eligible_law,
    playground_bare_act_spec,
)
from constitution_memorizer.playground.urls import add_path, law_path, sections_path
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import BARE_ACTS, get_bare_act

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/constitution_memorizer/web/static"
TEMPLATES = ROOT / "src/constitution_memorizer/web/templates"
USER = UUID("11111111-1111-4111-8111-111111111111")
ELIGIBLE = tuple(slug for slug in BARE_ACTS if is_playground_eligible_law(slug))


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _settings(**overrides: str) -> MultiUserSettings:
    values = dict(
        _env_file=None,
        APP_ENV="test",
        MULTIUSER_ENABLED="true",
        AUTH_GOOGLE_ENABLED="true",
        SESSION_SECRET="test-secret",
        SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon",
        DATABASE_URL="",
        COOKIE_SECURE="false",
    )
    values.update(overrides)
    return MultiUserSettings(**values)


def _app(tmp_path: Path, **overrides: str):
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER, email="a@example.com", display_name="Sanjay", avatar_url=None
    )
    tmp_path.mkdir(parents=True, exist_ok=True)
    return create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(**overrides),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
    )


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    assert client.cookies.get(SESSION_COOKIE_NAME)


def _subscribe(client: TestClient, *, tier: str = "plus", status: str = "active") -> None:
    client.app.state.subscriptions.create_subscription_record(
        USER,
        tier=tier,
        status=status,
        billing_period_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 10, 15, tzinfo=timezone.utc),
        is_current=True,
    )


def _add_entire(client: TestClient, law_id: str) -> None:
    csrf = {"csrf_token": client.cookies.get("rtc_csrf") or ""}
    client.post(add_path(law_id), data=csrf, follow_redirects=False)
    done = client.post(
        add_path(law_id), data={**csrf, "confirm": "add", "scope": "entire"}, follow_redirects=False
    )
    assert done.status_code in {200, 303}


def _head(html: str) -> str:
    return html.split("data-act-head=", 1)[1].split("data-act-list", 1)[0]


def _listing(html: str) -> str:
    return html.split("data-act-list", 1)[1].split("</section>", 1)[0]


def _cta(html: str) -> str:
    assert 'class="ActHead-cta LawPlaygroundCta"' in html
    return html.split('class="ActHead-cta LawPlaygroundCta"', 1)[1].split("</div>\n      </div>", 1)[0]


# ── F01 · one generated head for every Act ──────────────────────────────


@pytest.mark.parametrize("slug", tuple(BARE_ACTS))
def test_every_bare_act_renders_the_generated_head_from_the_model(tmp_path, slug):
    act = get_bare_act(slug)
    html = TestClient(_app(tmp_path)).get(f"/laws/{slug}").text
    assert f'data-act-head="{slug}"' in html
    assert 'data-mscreen="bareact"' in html
    head = _head(html)
    assert f'<h1 class="ActHead-title">{act.title}</h1>' in head
    assert f'<p class="ActHead-meta">{act.head_meta_label}</p>' in head
    assert "Bare Act · India Code" in head
    assert 'class="ActHead-back" href="/laws"' in head
    # Chapter rows and schedule rows are counted off the model, not typed.
    listing = _listing(html)
    assert listing.count('<details class="bareact-chapter">') == act.chapter_count
    assert listing.count('<details class="bareact-chapter" open>') == 0
    assert listing.count('<div class="bareact-schedule-row') == len(act.schedules)
    # The six per-surface variants and the fixture are gone for good.
    for stale in (
        "guest-bareact",
        "signed-bareact",
        "data-guest-bareact",
        "data-signed-in-bareact",
        "data-plus-bareact-phone",
        "data-bareact-phone",
        "data-bareact-tabs",
        "data-bareact-panel",
        "This Act has no Schedules.",
    ):
        assert stale not in html, stale
    if slug == "ndps":
        # The fixture's "6 Chapters" never comes back: NDPS prints eight.
        assert "6 Chapters" not in html
        assert "8 Chapters" in html


def test_the_head_meta_is_derived_from_the_schedules_the_act_prints():
    ndps = get_bare_act("ndps")
    assert ndps.head_meta_label == "8 Chapters · Sections 1–83 · Schedule"
    assert get_bare_act("uapa").head_meta_label == "7 Chapters · Sections 1–53 · Schedules"
    assert get_bare_act("bns").head_meta_label == "20 Chapters · Sections 1–358"
    assert get_bare_act("mtp").head_meta_label == "Sections 1–8"
    for slug in BARE_ACTS:
        act = get_bare_act(slug)
        assert act.head_meta_label.startswith(act.meta_label)
        assert ("Schedule" in act.head_meta_label) == bool(act.schedules)


def test_the_fixture_module_and_its_context_no_longer_exist():
    with pytest.raises(ImportError):
        import constitution_memorizer.web.guest_bareact_head  # noqa: F401
    app_py = (ROOT / "src/constitution_memorizer/web/app.py").read_text(encoding="utf-8")
    assert "guest_screen4" not in app_py
    assert "guest_bareact_head" not in app_py
    bare = (TEMPLATES / "bare_act.html").read_text(encoding="utf-8")
    assert "guest_screen4" not in bare
    assert bare.count('class="ActHead-title"') == 1


# ── F02 · chapter rows are real controls that reach every section ───────


@pytest.mark.parametrize("slug", ELIGIBLE)
def test_chapter_rows_expand_into_every_section_link(tmp_path, slug):
    act = get_bare_act(slug)
    listing = _listing(TestClient(_app(tmp_path)).get(f"/laws/{slug}").text)
    assert listing.count('<summary class="bareact-chapter-row" aria-expanded="false">') == act.chapter_count
    for chapter in act.chapters:
        assert f"Chapter {chapter.number}</span>" in listing
        assert chapter.title in listing
        assert f'<span class="ActHead-range-word">Sections </span>{chapter.range_label}</span>' in listing
    for section in act.section_order:
        assert f'href="/laws/{slug}/section/{section.number}"' in listing, section.number
    # Every section link is inside its chapter's <details>, never loose.
    before_first = listing.split("<details", 1)[0] if act.chapters else listing
    if act.chapters:
        assert "bareact-section-row" not in before_first


# ── F03 · schedule rows open their readers ──────────────────────────────


def test_schedule_rows_link_to_their_readers_and_follow_the_chapters(tmp_path):
    client = TestClient(_app(tmp_path))
    for slug in ("ndps", "uapa", "bnss"):
        act = get_bare_act(slug)
        listing = _listing(client.get(f"/laws/{slug}").text)
        for schedule in act.schedules:
            href = f'href="/laws/{slug}/schedule/{schedule.slug}"'
            assert (href in listing) == schedule.is_navigable, schedule.slug
            assert schedule.display_heading in listing
        if act.chapters:
            assert listing.rindex("</details>") < listing.index('class="bareact-schedule-row')
    bnss = _listing(client.get("/laws/bnss").text)
    assert 'class="bareact-schedule-row is-unavailable"' in bnss
    assert "Not yet browsable in the app" in bnss
    for slug in ("bns", "pss"):
        assert "bareact-schedule-row" not in _listing(client.get(f"/laws/{slug}").text)


# ── F04 · the CTA is the live state, by kind ─────────────────────────────


@pytest.mark.parametrize("slug", ELIGIBLE)
def test_guest_cta_is_sign_in_and_opens_the_sheet(tmp_path, slug):
    cta = _cta(TestClient(_app(tmp_path)).get(f"/laws/{slug}").text)
    assert 'data-pg-kind="guest"' in cta
    assert ">Sign in to use Playground</a>" in cta
    assert f'href="{add_path(slug)}"' in cta
    assert "data-pg-sheet" in cta
    assert "Already in Playground" not in cta


@pytest.mark.parametrize("slug", ELIGIBLE)
def test_free_cta_is_subscribe_and_opens_the_sheet(tmp_path, slug):
    client = TestClient(_app(tmp_path))
    _sign_in(client)
    cta = _cta(client.get(f"/laws/{slug}").text)
    assert 'data-pg-kind="subscribe"' in cta
    assert ">Subscribe to use Playground</a>" in cta
    assert f'href="{add_path(slug)}"' in cta
    assert "data-pg-sheet" in cta


@pytest.mark.parametrize("tier", ("plus", "pro", "max"))
def test_subscriber_cta_is_add_then_the_in_playground_chip_with_live_hrefs(tmp_path, tier):
    client = TestClient(_app(tmp_path))
    _sign_in(client)
    _subscribe(client, tier=tier)
    cta = _cta(client.get("/laws/uapa").text)
    assert 'data-pg-kind="eligible_to_add"' in cta
    assert ">+ Add to Playground</a>" in cta
    assert f'href="{add_path("uapa")}"' in cta
    assert "data-pg-sheet" in cta
    _add_entire(client, "uapa")
    html = client.get("/laws/uapa").text
    cta = _cta(html)
    assert 'data-pg-kind="already_active"' in cta
    assert "Already in Playground" in cta
    assert f'class="ActHead-inpg-sections" href="{sections_path("uapa")}">Sections</a>' in cta
    assert f'class="ActHead-inpg-continue" href="{law_path("uapa")}">Continue</a>' in cta
    assert 'href="/playground">Continue' not in cta
    assert "data-pg-sheet" not in cta
    # The same head, not a tier-specific one: the only tier trace is the
    # Plus marker the shell tests rely on.
    assert ("data-plus-bareact" in html) == (tier == "plus")


def test_expired_and_halted_keep_their_lifecycle_cta_inside_the_head(tmp_path):
    client = TestClient(_app(tmp_path))
    _sign_in(client)
    _subscribe(client, status="active")
    _add_entire(client, "ndps")
    stored = client.app.state.subscriptions.get_current_subscription(USER)
    client.app.state.subscriptions.update_subscription_state(USER, stored.id, status="halted")
    html = client.get("/laws/ndps").text
    assert "data-halted-bareact" in html
    cta = _cta(html)
    assert "Already in Playground" in cta
    assert ">Sections</a>" in cta
    assert "Continue</a>" not in cta
    assert "+ Add to Playground" not in cta
    # Another Act is not addable while halted either.
    other = _cta(client.get("/laws/uapa").text)
    assert "+ Add to Playground" not in other
    assert "data-pg-sheet" not in other


def test_playground_disabled_still_renders_the_head_without_a_cta(tmp_path):
    html = TestClient(_app(tmp_path, PLAYGROUND_ENABLED="false")).get("/laws/ndps").text
    assert 'data-act-head="ndps"' in html
    assert "ActHead-cta" not in html
    assert "Sign in to use Playground" not in html
    assert _listing(html).count('<details class="bareact-chapter">') == 8


# ── F05 · the Add sheet is a dialog over the Act (Q4) ───────────────────


def test_direct_add_url_is_the_act_page_with_the_sheet_open(tmp_path):
    client = TestClient(_app(tmp_path))
    _sign_in(client)
    page = client.get(add_path("uapa"))
    assert page.status_code == 200
    html = page.text
    assert 'data-act-head="uapa"' in html
    assert 'data-mscreen="bareact"' in html
    assert "PlaygroundShell" not in html
    dialog = html.split("<dialog ", 1)[1].split("</dialog>", 1)[0]
    assert "data-pg-sheet-direct" in dialog
    assert 'data-pg-sheet-return="/laws/uapa"' in dialog
    assert " open>" in dialog.split(">", 1)[0] + ">"
    assert 'data-pg-add' in dialog and 'data-pg-kind="subscribe"' in dialog
    assert html.count('class="pg-sheet-panel"') == 1
    assert 'id="pg-add-title" class="pg-add-title">Add to Playground</h1>' in dialog
    assert "Turning The UAPA, 1967 into a learning experience needs a plan." in dialog
    assert 'class="pg-add-primary" href="/playground">Unlock Playground</a>' in dialog
    assert "Plus · Pro · Max — from ₹199 / month. Constitution learning stays free." in dialog


def test_plus_add_sheet_keeps_the_confirm_and_scope_contract(tmp_path):
    client = TestClient(_app(tmp_path))
    _sign_in(client)
    _subscribe(client)
    html = client.get(add_path("uapa")).text
    panel = html.split("data-pg-add", 1)[1].split("</dialog>", 1)[0]
    assert 'data-pg-kind="eligible_to_add"' in panel
    assert 'action="/playground/laws/uapa/add" data-pg-add-confirm' in panel
    assert 'name="csrf_token"' in panel and 'name="confirm"' in panel
    assert 'class="pg-add-primary">Add to Playground</button>' in panel
    assert "The UAPA, 1967 joins" in panel
    assert 'data-add-step="scope"' in panel
    assert 'name="scope" value="entire"' in panel and 'name="scope" value="sections"' in panel
    assert panel.count("data-pg-sheet-close") >= 1
    csrf = {"csrf_token": client.cookies.get("rtc_csrf") or ""}
    first = client.post(add_path("uapa"), data=csrf, follow_redirects=False)
    assert first.status_code in {200, 303}
    done = client.post(
        add_path("uapa"), data={**csrf, "confirm": "add", "scope": "entire"}, follow_redirects=False
    )
    assert done.status_code == 303
    assert client.app.state.roster.is_law_active_this_period(USER, "uapa")
    after = client.get(add_path("uapa"), follow_redirects=False)
    assert after.status_code == 303


def test_reading_names_come_from_the_registry_for_every_act(tmp_path):
    client = TestClient(_app(tmp_path))
    for slug in ELIGIBLE:
        spec = playground_bare_act_spec(slug)
        html = client.get(add_path(slug)).text
        assert f"Reading {spec.short_name} stays free" in html, slug


# ── F06 / F07 · About below the action; MTP flat ─────────────────────────


def test_about_this_act_sits_below_the_cta_inside_the_band(tmp_path):
    html = TestClient(_app(tmp_path)).get("/laws/ndps").text
    band = html.split('class="ActHead-band"', 1)[1].split("data-act-list", 1)[0]
    assert band.index('class="ActHead-cta LawPlaygroundCta"') < band.index("data-bareact-info-toggle")
    assert 'aria-controls="bareact-info"' in band
    assert "<dt>Ministry</dt>" in band
    assert 'data-bareact-info hidden' in band


def test_a_chapterless_act_lists_its_sections_flat(tmp_path):
    act = get_bare_act("mtp")
    html = TestClient(_app(tmp_path)).get("/laws/mtp").text
    assert '<p class="ActHead-meta">Sections 1–8</p>' in html
    listing = _listing(html)
    assert "<details" not in listing
    assert "Chapter" not in listing
    assert listing.count('class="bareact-section-row"') == len(act.unchaptered_sections)
    assert "0 Chapters" not in html


# ── the stylesheet and the pins ─────────────────────────────────────────


def test_head_and_sheet_styles_replaced_the_per_surface_blocks():
    styles = (STATIC / "styles.css").read_text(encoding="utf-8")
    mobile = (STATIC / "mobile.css").read_text(encoding="utf-8")
    playground = (STATIC / "playground.css").read_text(encoding="utf-8")
    assert ".panel.ActHead {" in styles
    assert ".ActHead .bareact-chapter-row {" in styles
    assert ".pg-add-primary {" in playground
    for sheet in (styles, mobile, playground):
        for stale in (
            "guest-bareact",
            "signed-bareact",
            "data-guest-bareact",
            "data-signed-in-bareact",
            "data-plus-bareact-phone",
            "data-bareact-phone",
            "guest-add-",
            "signed-add-",
            "plus-add-",
            "expired-add-desktop",
            "halted-add-desktop",
        ):
            assert stale not in sheet, stale
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    for pin in ("styles.css?v=main88", "mobile.css?v=mob107", "playground.css?v=pg50", "playground.js?v=pg9", "mobile.js?v=mob30"):
        assert pin in base, pin
