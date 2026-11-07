"""M4 — Today (`/dashboard`) by tier (owner decisions of 2026-11-07).

F01 guest Today: prototype greeting and date line, "Nothing due yet.", the hero
    CTA opening Browse, one Google action, no superseded "3 Articles" copy.
F02 signed-in first run: identical bodies across Free, Plus, Pro, Max, paused
    and pending; expired / halted keep their header status; no Free chip or
    plan row (dead branches removed).
F03 desktop first-run layout hooks and the phone rules left untouched.
F04 no superseded copy for nine states × two tier models × first run / after
    one real Learn → Done; the lapse banner carries the all-Articles wording.
F06 "n of m reviewed" on the path header only when a goal exists.
F07 permissions: guest posts are refused; both tier models render the same
    Today.
F08 gate: a Free account's fourth distinct Article reaches Today's path on its
    due date with no claim prompt, under `monthly` and `choices`.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.web.dashboard import build_dashboard_context
from tests.quiz_helpers import complete_all_modes
from tests.test_browse_laws_family import JSON, STATES, UNITS, USER, _client
from tests.test_signed_in_today_screen8 import _make_due, _mu_app
from tests.test_signed_in_today_screen8 import _sign_in as _sign_in_08

ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "src" / "constitution_memorizer" / "web" / "static" / "styles.css"
MOBILE = ROOT / "src" / "constitution_memorizer" / "web" / "static" / "mobile.css"
TEMPLATE = ROOT / "src" / "constitution_memorizer" / "web" / "templates" / "dashboard.html"

GOOGLE = 'href="/auth/google/start?next=%2Fdashboard"'
LEGACY = ("3 Articles", "save 3", "pick any", "Unlock all", "Unlock every Article", "3 slots", "/login", "₹", "Free Articles")
SIGNED_IN = [s for s in STATES if s != "guest"]
SAME_BODY = ["free", "pro", "max", "paused", "pending"]
FOUR_ARTICLES = ["article-1-clause-1", "article-2", "article-3", "article-4-clause-1"]


def _main(html: str) -> str:
    return html.split("<main", 1)[1].split("</main>", 1)[0]


def _header(html: str) -> str:
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _today_label(today: date | None = None) -> str:
    today = today or date.today()
    return f"{today.strftime('%A')} {today.day} {today.strftime('%B')}"


# --------------------------------------------------------------------------- #
# F01 — guest Today                                                            #
# --------------------------------------------------------------------------- #
def test_f01_guest_today_is_the_prototype_greeting_with_one_google_action(tmp_path: Path) -> None:
    client = _client(tmp_path, "guest", units=UNITS)
    html = client.get("/dashboard").text
    main = _main(html)
    assert 'data-guest-today="desktop"' in main
    assert "data-signed-in-today" not in main
    assert "Good morning." in main and "Welcome." not in main
    assert f"{_today_label()} · Reading as a guest" in main
    assert 'class="dash-avatar dash-avatar-guest"' in main and ">?</span>" not in main
    assert "rc-streak" not in main
    assert 'data-today-mode="firstrun"' in main
    assert "Nothing due yet." in main and "Nothing due today" not in main
    assert '<a class="dash-firstrun-cta" href="/browse">Learn your first Article →</a>' in main
    assert "you’ll be asked to sign in so your progress is saved" in main
    card = main.split("data-guest-today-signin", 1)[1].split("</div>", 1)[0]
    assert "Sign in to save your progress. Your daily revisions, streak and path will show here." in card
    assert card.count(GOOGLE) == 1 and "data-guest-gate-google" in card
    assert main.count(GOOGLE) == 1
    assert main.count('class="dash-firstrun-item"') >= 1  # Q1: starter rows stay for guests
    assert "Set a learning plan" not in main and "Take the two-minute tour" not in main
    for phrase in LEGACY:
        assert phrase not in main, phrase
    # The Google start honours the same-origin next path.
    start = client.get("/auth/google/start?next=%2Fdashboard", follow_redirects=False)
    assert start.status_code == 303
    assert (start.cookies.get("rtc_auth_next") or "").strip('"') == "/dashboard"


# --------------------------------------------------------------------------- #
# F02 — signed-in first run across tiers                                       #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("state", SIGNED_IN)
def test_f02_signed_in_first_run_per_tier(tmp_path: Path, state: str) -> None:
    client = _client(tmp_path, state, units=UNITS)
    html = client.get("/dashboard").text
    main = _main(html)
    assert "data-signed-in-today" in main
    assert 'data-today-mode="firstrun"' in main
    assert "Welcome, Sanjay." in main  # Q2 (owner): brand-new accounts keep Welcome
    assert "Your account is ready." in main
    assert f'data-today-date>{_today_label()}</p>' in main
    assert "Reading as a guest" not in main
    assert "rc-streak" in main
    assert "dash-access-chip" not in main
    assert "You’re on the Free plan" not in main and "dash-firstrun-plan" not in main
    assert "data-guest-today" not in main and GOOGLE not in main
    assert '<a class="dash-firstrun-cta" href="/browse">' in main
    assert "Set a learning plan" in main and "Take the two-minute tour" in main
    for phrase in LEGACY:
        assert phrase not in main, phrase
    header = _header(html)
    if state == "expired":
        assert "Your Playground is paused" in header and 'data-expired-today="desktop"' in main
    elif state == "halted":
        assert "Payment retries have stopped" in header and 'data-halted-today="desktop"' in main
    elif state == "plus":
        assert 'data-plus-today="desktop"' in main


def test_f02_free_paid_and_pending_first_run_bodies_are_identical(tmp_path: Path) -> None:
    bodies = {}
    for state in SAME_BODY:
        html = _client(tmp_path, state, units=UNITS).get("/dashboard").text
        bodies[state] = re.sub(r"\s+", " ", _main(html))
    assert len(set(bodies.values())) == 1, {k: len(v) for k, v in bodies.items()}


# --------------------------------------------------------------------------- #
# F03 — desktop first-run layout hooks; phone rules untouched                  #
# --------------------------------------------------------------------------- #
def test_f03_desktop_first_run_is_laid_out_and_phone_rules_stay() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    assert template.count('<div class="dash-firstrun-side">') == 1
    assert "access.is_free" not in template
    styles = STYLES.read_text(encoding="utf-8")
    m4 = styles.split("M4 · Today", 1)[1]
    assert "@media (min-width: 561px)" in m4 and "@media (min-width: 900px)" in m4
    grid = m4.split("@media (min-width: 900px)", 1)[1]
    assert ".dash-firstrun {" in grid and "grid-template-columns: minmax(280px, 380px) minmax(0, 1fr)" in grid
    for selector in (".dash-firstrun-hero {", ".dash-firstrun-item {", ".dash-firstrun-signin-btn {", ".dash-avatar-guest {",
                     "[data-guest-today].dashboard-panel {", ".rc-path-count {"):
        assert selector in m4, selector
    assert "min-height: 44px" in m4 and "min-height: 48px" in m4
    mobile = MOBILE.read_text(encoding="utf-8")
    assert 'body[data-mscreen="today"] .dash-firstrun-hero {' in mobile  # phone rules untouched
    m4_phone = mobile.split("M4 · Today phone additions", 1)[1]
    assert "@media (max-width: 560px)" in m4_phone
    assert 'body[data-mscreen="today"] .dash-avatar-guest {' in m4_phone
    assert 'body.is-guest[data-mscreen="today"] .dash-date {' in m4_phone
    assert 'body[data-mscreen="today"] .rc-path-count {' in m4_phone


# --------------------------------------------------------------------------- #
# F04 — superseded copy gone for every state, model and phase                  #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tier_model", ["monthly", "choices"])
@pytest.mark.parametrize("state", list(STATES))
def test_f04_no_superseded_copy_on_today(tmp_path: Path, state: str, tier_model: str) -> None:
    client = _client(tmp_path / tier_model, state, units=UNITS, tier_model=tier_model)
    pages = [client.get("/dashboard").text]
    if state != "guest":
        complete_all_modes(client, UNITS, FOUR_ARTICLES[0])
        done = client.post(f"/learn/{FOUR_ARTICLES[0]}/done", headers=JSON)
        assert done.status_code == 200, done.text[:200]
        pages.append(client.get("/dashboard").text)
        assert 'data-today-mode="firstrun"' not in pages[-1]
    for html in pages:
        main = _main(html)
        for phrase in LEGACY:
            assert phrase not in main, (state, tier_model, phrase)


def test_f04_lapse_banner_states_the_all_articles_rule() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    banner = template.split('class="lapse-banner"', 1)[1].split("</div>", 1)[0]
    assert "Every Article, your progress and your revision schedule stay yours." in banner
    assert "Playground revisions are paused, not deleted — they resume where they were." in banner
    assert "Free Articles" not in banner and "other Articles" not in banner


# --------------------------------------------------------------------------- #
# F06 — the path counter                                                       #
# --------------------------------------------------------------------------- #
def test_f06_path_header_counts_reviewed_only_when_a_goal_exists(tmp_path: Path) -> None:
    client = TestClient(_mu_app(tmp_path))
    _sign_in_08(client)
    first = client.get("/dashboard").text
    assert "data-today-path-count" not in first
    _make_due(client, ["clause-1", "clause-2"])
    html = client.get("/dashboard").text
    assert 'data-today-path-card' in html
    count = re.search(r'data-today-path-count>([^<]+)<', html)
    assert count and count.group(1) == "0 of 2 reviewed", html.count("data-today-path-count")
    assert html.count("data-today-path-count") == 1


# --------------------------------------------------------------------------- #
# F07 — permissions and tier-model parity                                      #
# --------------------------------------------------------------------------- #
def test_f07_guest_cannot_start_sessions_and_get_is_mutation_free(tmp_path: Path) -> None:
    client = _client(tmp_path, "guest", units=UNITS)
    before = client.get("/dashboard").text
    for path in ("/revision/start", "/learning/start", "/learning/plan-my-day"):
        resp = client.post(path, follow_redirects=False)
        assert resp.status_code in (303, 401, 403, 422), (path, resp.status_code)
        assert resp.status_code != 200
    assert client.get("/dashboard").text == before


@pytest.mark.parametrize("state", ["guest", "free", "plus", "expired", "halted"])
def test_f07_today_is_identical_under_both_tier_models(tmp_path: Path, state: str) -> None:
    pages = {}
    for model in ("monthly", "choices"):
        html = _client(tmp_path / model, state, units=UNITS, tier_model=model).get("/dashboard").text
        pages[model] = re.sub(r"\s+", " ", _main(html))
    assert pages["monthly"] == pages["choices"]


# --------------------------------------------------------------------------- #
# F08 — gate: the Free promise reaches Today                                   #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tier_model", ["monthly", "choices"])
def test_f08_free_fourth_article_reaches_today_path_on_its_due_date(tmp_path: Path, tier_model: str) -> None:
    client = _client(tmp_path / tier_model, "free", units=UNITS, tier_model=tier_model)
    for unit_id in FOUR_ARTICLES:
        complete_all_modes(client, UNITS, unit_id)
        done = client.post(f"/learn/{unit_id}/done", headers=JSON)
        assert done.status_code == 200, (unit_id, done.status_code, done.text[:200])
        assert "claim_required" not in done.text and "claim=1" not in done.headers.get("location", "")
    eng = client.app.state.engine.for_user(USER)
    rows = {r.learning_unit_id: r for r in eng.list_all_progress() if r.learning_unit_id in FOUR_ARTICLES}
    assert set(rows) == set(FOUR_ARTICLES)
    fourth = rows[FOUR_ARTICLES[-1]]
    assert fourth.times_completed >= 1 and fourth.next_revision is not None
    # The same engine, read as of the fourth Article's due date: it is on the path.
    ctx = build_dashboard_context(eng, display_label="Sanjay", as_of=fourth.next_revision)
    assert ctx["show_first_run"] is False
    assert ctx["due_count"] >= 1
    assert any(u.unit_id == FOUR_ARTICLES[-1] and u.kind == "review" for u in ctx["today_units"]), [
        (u.unit_id, u.kind) for u in ctx["today_units"]
    ]
    assert "3 Articles" not in client.get("/dashboard").text.split("<main", 1)[1]
    # A fresh sign-in sees the progress on Today's strip.
    again = TestClient(client.app)
    from tests.test_browse_laws_family import _sign_in as _sign_in_family

    _sign_in_family(again)
    html = again.get("/dashboard").text
    strip = html.split('class="dash-strip"', 1)[1].split("</section>", 1)[0]
    started = int(re.search(r'class="dash-strip-num">(\d+)</p>\s*<p class="dash-strip-label">Articles started', strip).group(1))
    assert started >= 4
