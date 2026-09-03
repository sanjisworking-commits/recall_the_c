"""Client-side Learn mode switching: href fallback, JS intercept, /seen persist."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.progress.repository import LEARN_MODES
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "src" / "constitution_memorizer" / "web" / "static" / "app.js"


def _sqlite_client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
        )
    )


def _guest_client(tmp_path: Path) -> TestClient:
    clear_settings_cache()
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=MultiUserSettings(
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
        ),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
    )
    return TestClient(app)


def test_all_six_mode_tabs_keep_fallback_hrefs(tmp_path: Path):
    html = _sqlite_client(tmp_path).get("/learn/clause-1").text
    for mode in LEARN_MODES:
        assert f'data-learn-mode="{mode}"' in html
        assert f'href="/learn/clause-1?mode={mode}"' in html
        assert 'role="tab"' in html
    assert 'data-modes-seen="' in html
    assert "app.js?v=main57" in html


def test_direct_get_mode_query_still_server_renders(tmp_path: Path):
    client = _sqlite_client(tmp_path)
    for mode in LEARN_MODES:
        html = client.get(f"/learn/clause-1?mode={mode}").text
        assert f'data-mode="{mode}"' in html
        assert f'data-learn-mode="{mode}"' in html
        assert 'aria-selected="true"' in html


def test_seen_post_returns_tracker_and_done_payload(tmp_path: Path):
    client = _sqlite_client(tmp_path)
    resp = client.post("/learn/clause-1/seen", data={"mode": "cloze"})
    assert resp.status_code == 200
    payload = resp.json()
    assert "cloze" in payload["seen"]
    assert "tracker" in payload
    assert "count" in payload
    assert "done" in payload
    assert "unlocked" in payload["done"]
    assert "label" in payload["done"]


def test_guest_learn_marks_guest_and_does_not_require_post(tmp_path: Path):
    html = _guest_client(tmp_path).get("/learn/clause-1").text
    assert "data-guest-learn" in html
    assert 'data-learn-mode="read"' in html
    assert 'href="/learn/clause-1?mode=test"' in html


def test_app_js_intercepts_mode_tabs_and_updates_url():
    source = APP_JS.read_text(encoding="utf-8")
    assert "function initLearn()" in source
    assert "event.preventDefault()" in source
    assert "history.replaceState" in source
    assert 'closest("[data-learn-mode]")' in source
    assert "aria-selected" in source
    assert "learn.dataset.mode" in source
    learn_src = source.split("function initLearn()", 1)[1].split(
        "function initBrowseArticle()", 1
    )[0]
    assert "pushState" not in learn_src


def test_app_js_posts_seen_with_formdata_append():
    source = APP_JS.read_text(encoding="utf-8")
    learn_src = source.split("function initLearn()", 1)[1].split(
        "function initBrowseArticle()", 1
    )[0]
    assert 'body.append("mode", mode)' in learn_src
    assert "FormData({mode})" not in learn_src
    assert "new FormData({mode})" not in learn_src
    assert "/seen" in learn_src
    assert 'method: "POST"' in learn_src
    assert "data-guest-learn" in learn_src
    assert "confirmedModes.has(mode)" in learn_src
    assert "inFlight.has(mode)" in learn_src


def test_app_js_merges_seen_and_keeps_done_server_authoritative():
    source = APP_JS.read_text(encoding="utf-8")
    learn_src = source.split("function initLearn()", 1)[1].split(
        "function initBrowseArticle()", 1
    )[0]
    assert "confirmedModes.add(item)" in learn_src
    assert "confirmedModes =" not in learn_src.replace(
        "const confirmedModes = parseModes", ""
    )
    assert "serverDoneUnlocked" in learn_src
    assert "dataset.doneUnlocked" in learn_src
    assert "payload.done.unlocked === true" in learn_src
    assert "confirmedModes.size >= 6" not in learn_src
    assert "guestVisitedModes" in learn_src
    assert "ignore stale unlocked:false" in learn_src
    assert "inFlight.delete(mode)" in learn_src
    # Tab marks render the union of server-confirmed and provisional visits
    # (provisional = unclaimed-Article mode visits, R2 persistence matrix).
    assert "applyTabMarks(visitedUnion())" in learn_src
    assert "provisionalModes" in learn_src
    switch = learn_src.split("function switchModeLocal", 1)[1].split(
        "function persistSeen", 1
    )[0]
    assert "applyTabMarks" not in switch
    assert "nextMode === current" in learn_src
    assert "persistSeen(nextMode)" in learn_src


def _locked_methods_left_label(confirmed_count: int) -> str | None:
    """Mirror of app.js lockedMethodsLeftLabel — remaining count is monotonic."""
    remaining = 6 - confirmed_count
    if remaining <= 0:
        return None
    if remaining == 1:
        return "1 method left"
    return f"{remaining} methods left"


def test_locked_done_label_progresses_and_ignores_stale():
    source = APP_JS.read_text(encoding="utf-8")
    learn_src = source.split("function initLearn()", 1)[1].split(
        "function initBrowseArticle()", 1
    )[0]
    assert "function lockedMethodsLeftLabel" in learn_src
    assert "function applyLockedDoneLabel" in learn_src
    # Label counts required visits across the local set: guests use
    # guestVisitedModes, everyone else confirmed + provisional marks
    # (entitlement-aware required set; unclaimed Articles track provisionally).
    assert "lockedMethodsLeftLabel(requiredVisitedCount(localVisited()))" in learn_src
    assert "if (!doneBtn || serverDoneUnlocked)" in learn_src
    # Guest + provisional Done both unlock via the shared local gate.
    assert "function maybeUnlockLocalDone" in learn_src
    assert "maybeUnlockProvisionalDone" not in learn_src
    assert "applyLockedDoneLabel()" in learn_src
    assert "payload.done.unlocked === true" in learn_src
    assert "confirmedModes.size >= 6" not in learn_src

    labels = [_locked_methods_left_label(n) for n in range(1, 6)]
    assert labels == [
        "5 methods left",
        "4 methods left",
        "3 methods left",
        "2 methods left",
        "1 method left",
    ]
    assert _locked_methods_left_label(6) is None
    assert _locked_methods_left_label(0) == "6 methods left"

    confirmed = {"read", "cloze", "letters", "type"}
    stale_seen = {"read", "cloze"}
    merged = confirmed | stale_seen
    assert _locked_methods_left_label(len(merged)) == "2 methods left"
    naive_stale = _locked_methods_left_label(len(stale_seen))
    assert naive_stale == "4 methods left"
    assert _locked_methods_left_label(len(merged)) != naive_stale


def test_app_js_resets_destination_and_stops_recite():
    source = APP_JS.read_text(encoding="utf-8")
    learn_src = source.split("function initLearn()", 1)[1].split(
        "function initBrowseArticle()", 1
    )[0]
    assert 'prevMode === "recite"' in learn_src
    assert "recite.reset()" in learn_src
    assert "cloze.reset()" in learn_src
    assert "letters.reset()" in learn_src
    assert "typeMode.reset()" in learn_src
    assert "testMode.reset()" in learn_src
    assert "setFlipped" not in learn_src
    assert "Saving…" not in learn_src
    assert "spinner" not in learn_src.lower()


def test_app_js_gates_modes_on_completed_attempts():
    source = APP_JS.read_text(encoding="utf-8")
    # Canonical partition mirror: only Read marks on tab visit.
    assert 'AUTO_SEEN_MODES = new Set(["read"])' in source
    learn_src = source.split("function initLearn()", 1)[1].split(
        "function initBrowseArticle()", 1
    )[0]
    assert "function markModeAttempted" in learn_src
    assert "AUTO_SEEN_MODES.has(nextMode)" in learn_src
    assert "function applyQuizPayload" in learn_src
    assert "function applySeenPayload" in learn_src
    # Cloze counts individually tapped blanks; Reveal all never completes.
    cloze_src = source.split("function initCloze", 1)[1].split(
        "function initLetters", 1
    )[0]
    assert "tapRevealed" in cloze_src
    # The two reveal buttons merged into one toggle. That is a LABEL merge:
    # revealing everything must still grant no completion credit, or the mode
    # becomes skippable with a single tap.
    toggle_src = cloze_src.split('"toggle-all"', 1)[1].split("setDensity(density)", 1)[0]
    assert "tapRevealed" not in toggle_src
    assert "onComplete" not in toggle_src
    assert "checkTapComplete" not in toggle_src
