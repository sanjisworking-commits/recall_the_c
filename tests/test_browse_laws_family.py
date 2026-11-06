"""M3 — Browse and Laws catalogue by tier (docs/design/milestones/M3.md as
corrected; owner decisions of 2026-11-06).

One Browse body for both widths with collapsible Part headers (F01, F02); the
banner slot by viewer — guest strip with one Google action, the Free summary
for RecallC Free accounts only, nothing for subscribers (F03); one data-driven
Laws catalogue for every viewer with no per-card Playground CTA (F04, F05,
F07); Laws card meta equal to the Act head's own label (F06). Gate 1: a Free
account saves a fourth distinct Constitution Article through the real
Learn → Done flow with no claim prompt, under both tier models.

Permission and entitlement behaviour is asserted for every tier here; the
screenshots in the evidence record cover only the viewers whose page differs.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.entitlements.dependencies import (
    snapshot_is_free_account,
    snapshot_is_halted_subscriber,
)
from constitution_memorizer.entitlements.models import BLOCK_PAYMENT_HALTED
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.playground.view import gate_view
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import BARE_ACTS, get_bare_act
from constitution_memorizer.web.browse import browse_parts_sections
from constitution_memorizer.web.law_catalog import card_meta_label, load_catalog
from constitution_memorizer.web.shell import FREE_LABEL, account_status_for_snapshot
from tests.quiz_helpers import complete_all_modes

ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "data" / "output" / "learning_units.json"
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
BROWSE = ROOT / "src/constitution_memorizer/web/templates/browse_index.html"
LAWS = ROOT / "src/constitution_memorizer/web/templates/laws.html"
PARTIAL = ROOT / "src/constitution_memorizer/web/templates/partials/playground.html"
APP_PY = ROOT / "src/constitution_memorizer/web/app.py"
APP_JS = ROOT / "src/constitution_memorizer/web/static/app.js"
MOBILE_JS = ROOT / "src/constitution_memorizer/web/static/mobile.js"
MANIFEST = ROOT / "src/constitution_memorizer/web/law_sitemap_manifest.json"
USER = UUID("11111111-1111-4111-8111-111111111111")
JSON = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}

GUEST_STRIP = "Reading as a guest. Sign in to save your progress."
GUEST_GOOGLE = "/auth/google/start?next=%2Fbrowse"
FREE_SUMMARY = "Free plan — every Article, progress saved."
FREE_LINK = '<a class="browse-access-unlock" href="/playground">View Playground</a>'
# Copy that must never appear on either page for any viewer (D19, 5-1, §4.5.5).
FORBIDDEN = ("3 Articles", "pick any", "Unlock all", "law choices", "₹", "Subscribe to use Playground", "Unlock Playground", "Add to Playground", "Create an account")
# A live subscription window around today and one that ended months ago.
_TODAY = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
ACTIVE = (_TODAY - timedelta(days=20), _TODAY + timedelta(days=10))
EXPIRED = (_TODAY - timedelta(days=110), _TODAY - timedelta(days=80))

# state → subscription row (None = guest; {} = signed-in Free)
STATES: dict[str, dict | None] = {
    "guest": None,
    "free": {},
    "plus": {"tier": "plus", "status": "active"},
    "pro": {"tier": "pro", "status": "active"},
    "max": {"tier": "max", "status": "active"},
    "paused": {"tier": "plus", "status": "paused"},
    "pending": {"tier": "plus", "status": "pending"},
    "expired": {"tier": "plus", "status": "expired", "period": EXPIRED},
    "halted": {"tier": "plus", "status": "halted"},
}
SUBSCRIBERS = ("plus", "pro", "max")
# The shell labels these RecallC Free (a pending row counts as its tier, so it
# is a subscriber here, exactly as the account slot prints it).
FREE_LIKE = ("free", "paused")


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def _settings(tier_model: str = "monthly") -> MultiUserSettings:
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
        PLAYGROUND_TIER_MODEL=tier_model,
    )


def _app(tmp_path: Path, *, units: Path = MINI_UNITS, tier_model: str = "monthly", repo=None):
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="a@example.com", display_name="Sanjay", avatar_url=None)
    tmp_path.mkdir(parents=True, exist_ok=True)
    kwargs = {"progress_repo": repo} if repo is not None else {}
    return create_app(
        units_path=units,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(tier_model),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        **kwargs,
    )


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    assert client.cookies.get(SESSION_COOKIE_NAME)


def _subscribe(client: TestClient, spec: dict) -> None:
    start, end = spec.get("period", ACTIVE)
    client.app.state.subscriptions.create_subscription_record(
        USER, tier=spec["tier"], status=spec["status"], billing_period_start=start,
        billing_period_end=end, is_current=True,
    )


def _client(tmp_path: Path, state: str, **kw) -> TestClient:
    client = TestClient(_app(tmp_path / state, **kw))
    spec = STATES[state]
    if spec is not None:
        _sign_in(client)
        if spec:
            _subscribe(client, spec)
    return client


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _panel(html: str) -> str:
    return html.split('<section class="panel browse"', 1)[1].split("</main>", 1)[0]


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("rtc_csrf") or ""
    return {"csrf_token": token} if token else {}


# --------------------------------------------------------------------------- #
# F01 / F02 — one Browse body, collapsible Parts                                #
# --------------------------------------------------------------------------- #


def test_f01_browse_is_one_body_with_a_grid_per_part(tmp_path: Path) -> None:
    for state in ("guest", "free"):
        client = _client(tmp_path, state, units=UNITS)
        html = client.get("/browse").text
        sections = browse_parts_sections(client.app.state.engine, None)
        assert html.count('<section class="panel browse"') == 1
        parts = re.findall(r'<section class="browse-part" aria-label="Part ([^"]+)" data-browse-part="([^"]+)">(.*?)\n  </section>', html, re.S)
        assert [p[0] for p in parts] == [s.part_number for s in sections], state
        for (_, _, body), section in zip(parts, sections):
            expected = len(section.cards) + sum(len(ch.cards) for ch in section.chapters)
            assert body.count('class="browse-article-card') == expected, (state, section.part_number)
        for gone in ("browse-part-rail", 'class="part-card', "browse-rail-note", 'id="marks-sheet"', "data-sheet-open", "data-marks-filter", "browse-signin-chip", 'class="mobile-screen-title"'):
            assert gone not in html, (state, gone)
        assert '<p class="browse-constitution-label">The Constitution</p>' in html
        assert 'href="/search" aria-label="Search"' in html
        # Q1: the Part pages stay reachable by URL and from the article reader.
        part = client.get("/browse/part/iii")
        assert part.status_code == 200 and "All Parts" in part.text
        assert "/browse/part/iii" in client.get("/browse/article/20").text


def test_f02_part_headers_are_buttons_that_toggle_their_own_grid(tmp_path: Path) -> None:
    client = _client(tmp_path, "guest", units=UNITS)
    html = client.get("/browse").text
    toggles = re.findall(r'<button type="button" class="browse-part-toggle" data-browse-part-heading data-browse-part-toggle aria-expanded="true" aria-controls="([^"]+)">(.*?)</button>', html, re.S)
    assert toggles and len(toggles) == html.count('data-browse-part="')
    for target, inner in toggles:
        assert html.count(f'id="{target}"') == 1
        assert f'<div class="browse-part-body" id="{target}">' in html
        assert "<a " not in inner and "href=" not in inner
        assert "browse-part-roman" in inner and "browse-part-name" in inner and "browse-part-range" in inner
        assert 'class="browse-part-chevron"' in inner and 'aria-hidden="true"' in inner
    # main's Schedules section keeps its plain header: not a toggle.
    assert '<span class="browse-part-roman">Schedules</span>' in html
    assert "browse-part-toggle" not in html.split('id="schedules"', 1)[1]
    # The script flips aria-expanded and hides only the controlled body.
    js = APP_JS.read_text(encoding="utf-8")
    handler = js.split("[data-browse-part-toggle]", 1)[1]
    assert 'getAttribute("aria-expanded") === "true"' in handler
    assert 'setAttribute("aria-expanded", expanded ? "false" : "true")' in handler
    assert 'getElementById(toggle.getAttribute("aria-controls")' in handler and "body.hidden = expanded" in handler
    # Q2: the legend keeps icons with text labels, pressable with aria-pressed.
    legend = html.split('class="browse-legend"', 1)[1].split("</div>", 1)[0]
    items = re.findall(r'<button type="button"\s+class="browse-legend-item browse-mark-(\w+)"\s+data-browse-filter="\w+"\s+aria-pressed="false">(.*?)</button>', legend, re.S)
    assert items
    for key, inner in items:
        assert "<svg" in inner and re.search(r"<span>[^<]+</span>", inner), key


# --------------------------------------------------------------------------- #
# F03 — banner slot by viewer                                                   #
# --------------------------------------------------------------------------- #


def _snapshot(client: TestClient):
    return client.app.state.entitlement_service.resolve(USER)


def test_f03_banner_slot_by_viewer(tmp_path: Path) -> None:
    for state in STATES:
        client = _client(tmp_path, state)
        html = client.get("/browse").text
        panel = _panel(html)
        for phrase in FORBIDDEN:
            assert phrase not in panel, (state, phrase)
        if state == "guest":
            strip = panel.split("data-guest-strip", 1)[1].split("</div>", 1)[0]
            assert GUEST_STRIP in strip
            assert strip.count('href="') == 1 and f'href="{GUEST_GOOGLE}"' in strip
            assert 'data-guest-gate-google>Continue with Google</a>' in strip
            assert "/login" not in strip and "data-guest-gate>" not in strip
            assert "data-signed-in-browse-strip" not in panel
            continue
        assert "data-guest-strip" not in panel
        if state in FREE_LIKE:
            assert "data-signed-in-browse-strip" in panel, state
            summary = panel.split("data-signed-in-browse-strip", 1)[1].split("</div>", 1)[0]
            assert FREE_SUMMARY in summary and FREE_LINK in summary, state
            assert "Free plan" not in panel.split("data-signed-in-browse-strip", 1)[0]
            gate = client.get("/playground")
            assert gate.status_code == 200
        else:
            assert "data-signed-in-browse-strip" not in panel, state
            assert "Free plan" not in panel, state
        if state in ("expired", "halted"):
            snap = _snapshot(client)
            if state == "halted":
                expected = gate_view(reason=BLOCK_PAYMENT_HALTED).title
            else:
                expected = gate_view(reason=str(snap.playground_block_reason or "")).title
            assert expected in _header(html), state


def test_f03_free_predicate_matches_the_shell_label(tmp_path: Path) -> None:
    for state, spec in STATES.items():
        if spec is None:
            continue
        client = _client(tmp_path, state)
        snap = _snapshot(client)
        assert snapshot_is_free_account(snap) == (account_status_for_snapshot(snap) == FREE_LABEL), state
        if state in SUBSCRIBERS:
            assert not snapshot_is_free_account(snap)
        if state == "halted":
            assert snapshot_is_halted_subscriber(snap) and not snapshot_is_free_account(snap)


def test_f03_browse_handler_uses_the_snapshot_not_the_plus_flag() -> None:
    src = APP_PY.read_text(encoding="utf-8")
    handler = src.split("async def browse_index", 1)[1].split("async def browse_part", 1)[0]
    assert "request_is_free_account(request)" in handler and '"free_browse": free_browse' in handler
    assert "part_cards" not in handler
    template = BROWSE.read_text(encoding="utf-8")
    assert "{% elif free_browse|default(false) %}" in template
    assert "not plus_browse" not in template
    assert "{% if access and access.enabled and access.is_free %}" not in template
    assert '<span class="browse-access-label">Preview only</span>' not in template


# --------------------------------------------------------------------------- #
# Gate 1 — the Free Article promise through the real Learn → Done flow          #
# --------------------------------------------------------------------------- #

FOUR_ARTICLES = ("article-1-clause-1", "article-2", "article-3", "article-4-clause-1")


@pytest.mark.parametrize("tier_model", ["monthly", "choices"])
def test_gate1_free_account_saves_a_fourth_article_without_a_claim_prompt(tmp_path: Path, tier_model: str) -> None:
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    app = _app(tmp_path / "app", units=UNITS, tier_model=tier_model, repo=repo)
    client = TestClient(app)
    _sign_in(client)
    assert FREE_SUMMARY in client.get("/browse").text
    for unit_id in FOUR_ARTICLES:
        page = client.get(f"/learn/{unit_id}")
        assert page.status_code == 200, unit_id
        assert "claim=1" not in str(page.url) and "Add Article" not in page.text
        complete_all_modes(client, UNITS, unit_id)
        for mode in ("cloze", "letters", "type", "recite"):
            seen = client.post(f"/learn/{unit_id}/seen", data={"mode": mode}, headers=JSON)
            assert seen.status_code == 200 and seen.json().get("error") != "mode_locked", (unit_id, mode)
        done = client.post(f"/learn/{unit_id}/done", headers=JSON)
        assert done.status_code == 200, (unit_id, done.status_code, done.text[:200])
        body = done.json()
        assert body.get("ok") is True and body.get("error") != "claim_required", (unit_id, body)
        assert "claim_required" not in done.text and "slots_remaining" not in done.text
    records = {u: repo.get_progress(USER, u) for u in FOUR_ARTICLES}
    assert all(r is not None and r.times_completed == 1 for r in records.values()), records
    assert all(r.next_revision is not None for r in records.values()), records
    # A fresh session: new cookies, same account — progress and schedule survive.
    fresh = TestClient(app)
    _sign_in(fresh)
    for unit_id, rec in records.items():
        again = repo.get_progress(USER, unit_id)
        assert again is not None and again.times_completed == 1 and again.next_revision == rec.next_revision
        learn = fresh.get(f"/learn/{unit_id}")
        assert learn.status_code == 200 and "claim=1" not in str(learn.url)
        due = rec.next_revision
        cal = fresh.get(f"/calendar?year={due.year}&month={due.month}")
        assert cal.status_code == 200
    assert repo.claimed_articles(USER) == set()  # nothing was "claimed": Free is every Article


# --------------------------------------------------------------------------- #
# F04 / F05 / F06 / F07 — one Laws catalogue                                    #
# --------------------------------------------------------------------------- #


def _add_entire(client: TestClient, law_id: str) -> None:
    client.get(f"/laws/{law_id}")  # sets the CSRF cookie
    payload = dict(_csrf(client))
    payload.update({"confirm": "add", "scope": "entire"})
    resp = client.post(f"/playground/laws/{law_id}/add", data=payload, follow_redirects=False)
    assert resp.status_code == 303, (resp.status_code, resp.text[:200])


def test_f04_no_card_carries_a_playground_cta_on_any_tier(tmp_path: Path) -> None:
    catalog = load_catalog()
    for state in STATES:
        client = _client(tmp_path, state)
        html = client.get("/laws").text
        assert html.count("data-laws-index") == 1, state
        for gone in ("pg-btn", "pg-lede", "pg-actions", "data-pg-sheet", "data-laws-search-toggle", "data-guest-laws-desktop", "data-laws-phone", "mobile-back", "laws-index-head\""):
            assert gone not in html, (state, gone)
        for phrase in FORBIDDEN:
            assert phrase not in html.split('class="panel laws"', 1)[1], (state, phrase)
        # Card ids only (the badge wrapper repeats data-law-id for its own law).
        ids = re.findall(r'class="laws-index-card"\s+(?:href="[^"]*"\s+)?role="listitem"\s+data-law-id="([^"]+)"', html)
        assert ids == [law.id for law in catalog.laws], state
        for law in catalog.laws:
            assert f'href="{law.href}"' in html, (state, law.id)
    # A Plus account with NDPS in its Playground: exactly one status badge, still no button.
    plus = _client(tmp_path / "with-ndps", "plus")
    _add_entire(plus, "ndps")
    html = plus.get("/laws").text
    assert html.count('class="LawStatusBadge" data-status="in_playground"') == 1
    assert html.count("LawPlaygroundCta--badge") >= 1 and "pg-btn" not in html
    badge_card = html.split('data-law-id="ndps"', 1)[1].split("</article>", 1)[0]
    assert 'data-pg-kind="already_active"' in badge_card and "Already in Playground" in badge_card


def test_f05_search_field_and_chips_follow_the_catalogue(tmp_path: Path) -> None:
    catalog = load_catalog()
    expected_chips = ["All", *[s.label for s in catalog.visible_subjects]] + (["Repealed"] if catalog.repealed_laws else [])
    assert "Health" in expected_chips and "Commercial" not in expected_chips
    for state in ("guest", "free"):
        client = _client(tmp_path, state)
        html = client.get("/laws").text
        assert '<label class="visually-hidden" for="laws-q">Search laws</label>' in html
        search = html.split('<div class="laws-search" data-laws-search>', 1)[1].split("</div>", 1)[0]
        assert '<input' in search and 'id="laws-q"' in search and 'type="search"' in search and 'placeholder="Search laws"' in search
        assert "data-laws-search hidden" not in html
        chips = re.findall(r'data-laws-(?:chip|status)="[^"]*" aria-pressed="(?:true|false)">([^<]+)</button>', html)
        assert chips == expected_chips, state
        assert '<p class="laws-empty" data-laws-empty hidden>No laws found</p>' in html
        q = client.get("/laws?q=ndps&subject=criminal").text
        assert 'data-initial-q="ndps"' in q and 'data-initial-subject="criminal"' in q and 'data-initial-status=""' in q
        r = client.get("/laws?status=repealed").text
        assert 'data-initial-status="repealed"' in r and 'data-initial-subject=""' in r
    js = MOBILE_JS.read_text(encoding="utf-8")
    assert "setExpanded" not in js and "data-laws-search-toggle" not in js
    assert 'document.querySelector("[data-laws-index]")' in js


def test_f06_card_meta_is_the_act_heads_own_label(tmp_path: Path) -> None:
    import json

    catalog = load_catalog()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 3
    for slug in BARE_ACTS:
        assert manifest["laws"][slug]["head_meta_label"], slug
    full_acts = 0
    for law in catalog.laws:
        if law.primary_content == "full_act" and law.full_act_ref:
            full_acts += 1
            act = get_bare_act(law.full_act_ref)
            assert act is not None, law.id
            assert card_meta_label(law) == act.head_meta_label == law.card_meta_label, law.id
        else:
            assert card_meta_label(law) == law.scope_label, law.id
    assert full_acts >= 5
    expected = {
        "ndps": "8 Chapters · Sections 1–83 · Schedule",
        "uapa-1967": "7 Chapters · Sections 1–53 · Schedules",
        "bnss": "39 Chapters · Sections 1–531 · Schedules",
        "mtp": "Sections 1–8",
    }
    by_id = {law.id: law for law in catalog.laws}
    for law_id, label in expected.items():
        assert by_id[law_id].card_meta_label == label, law_id
    html = _client(tmp_path, "guest").get("/laws").text
    for law in catalog.laws:
        assert f'<span class="laws-index-meta">{law.card_meta_label}</span>' in html, law.id
    # The seed's own scope_label is untouched (no seed content change).
    assert by_id["ndps"].scope_label == "8 Chapters · Sections 1–83"
    assert by_id["citizenship-1955"].scope_label == by_id["citizenship-1955"].card_meta_label


def test_f07_the_guest_fixture_is_gone(tmp_path: Path) -> None:
    assert not (ROOT / "src/constitution_memorizer/web/guest_laws_index.py").exists()
    src = APP_PY.read_text(encoding="utf-8")
    assert "guest_laws_index" not in src and "GUEST_LAWS" not in src and "guest_screen3" not in src
    template = LAWS.read_text(encoding="utf-8")
    for gone in ("guest_laws_index", "guest_screen3", "data-guest-laws-desktop", "laws-q-guest", "data-laws-search-toggle", 'class="laws-index-head"', "mobile-back", "playground_cta("):
        assert gone not in template, gone
    assert template.count("<section") == 1 and "playground_status_badge" in template
    partial = PARTIAL.read_text(encoding="utf-8")
    macro = partial.split("{% macro playground_status_badge(state) %}", 1)[1].split("{% endmacro %}", 1)[0]
    assert "pg-btn" not in macro and "data-pg-sheet" not in macro and "status_badge(state.badge, state.badge_label)" in macro
    for state in ("guest", "free"):
        html = _client(tmp_path, state).get("/laws").text
        assert html.count('class="panel laws"') == 1 and html.count("data-laws-body") == 1
