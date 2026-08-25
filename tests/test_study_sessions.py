"""Study sessions: a revision queue that Done and Again both stay inside.

The bug these guard is that ``mark_done`` resolves what comes next from the
static Constitution graph, so finishing a due unit walked to its sequential
neighbour instead of the next *due* unit. Every "follows the queue" assertion
below is only meaningful because the fixture's queue order and its graph order
deliberately disagree.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.completion import next_learn_url, with_params

from tests.quiz_helpers import complete_all_modes

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "src" / "constitution_memorizer" / "web" / "static" / "app.js"
MOBILE_JS = ROOT / "src" / "constitution_memorizer" / "web" / "static" / "mobile.js"


def _client(tmp_path: Path, *, multiuser: bool = False) -> TestClient:
    kwargs: dict = {
        "units_path": MINI_UNITS,
        "db_path": tmp_path / "progress.db",
        "multiuser": multiuser,
    }
    if multiuser:
        clear_settings_cache()
        kwargs["multiuser_settings"] = MultiUserSettings(
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
        kwargs["auth_provider"] = FakeAuthProvider()
        kwargs["session_store"] = InMemorySessionStore()
    return TestClient(create_app(**kwargs))


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)


def _engine(client: TestClient) -> ReminderEngine:
    """The engine the *signed-in* user's requests are bound to.

    In multiuser mode every request rebinds to ``for_user(user.id)``, so
    reading app.state.engine directly would inspect the local-user row and
    every session assertion would silently pass on empty data.
    """
    engine = client.app.state.engine
    store = getattr(client.app.state, "session_store", None)
    sessions = getattr(store, "_sessions", None) if store is not None else None
    if sessions:
        newest = sorted(sessions.values(), key=lambda s: s.created_at)[-1]
        return engine.for_user(newest.user.id)
    return engine


def _make_due(client: TestClient, unit_ids: list[str], *, days_overdue: int = 0) -> None:
    """Seed units as due for review, oldest first in the order given.

    Staggering ``next_revision`` fixes the queue order, since due_today sorts
    on it — otherwise the snapshot would fall back to unit-id order and the
    "not the sequential neighbour" assertions would be luck.
    """
    eng = _engine(client)
    today = date.today()
    for offset, unit_id in enumerate(unit_ids):
        eng.repo.upsert_progress(
            eng.user_id,
            unit_id=unit_id,
            status="review",
            times_completed=1,
            last_completed=today - timedelta(days=1),
            next_revision=today - timedelta(days=days_overdue + len(unit_ids) - offset),
            interval_days=1,
        )
    eng._invalidate_progress_cache()


def _session_and_unit_from_location(location: str) -> tuple[str, str]:
    """Parse a Learn redirect, including `/learn/{id}/choose?session=` hops."""
    parts = urlsplit(location)
    session_id = parse_qs(parts.query).get("session", [""])[0]
    path = parts.path.removesuffix("/choose")
    return session_id, path.rsplit("/", 1)[-1]


def _start_plan_my_day(client: TestClient) -> tuple[str, str]:
    resp = client.post(
        "/study/plan-my-day",
        data={"count": "3"},
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    session_id, unit_id = _session_and_unit_from_location(resp.headers["location"])
    assert session_id and unit_id and unit_id != "choose"
    return session_id, unit_id


def _render_learn(client: TestClient, engine: ReminderEngine, unit_id: str, session_id: str):
    """Open the Learn page for a mix item, resolving letter-split first."""
    unit = engine.get_unit(unit_id)
    if unit is not None and unit.allows_letter_split:
        engine.set_split_preference(unit_id, "whole")
    resp = client.get(f"/learn/{unit_id}?session={session_id}", follow_redirects=False)
    hops = 0
    while resp.status_code in (303, 307) and hops < 4:
        loc = resp.headers["location"]
        session_id, unit_id = _session_and_unit_from_location(loc)
        unit = engine.get_unit(unit_id)
        if unit is not None and unit.allows_letter_split:
            engine.set_split_preference(unit_id, "whole")
        resp = client.get(loc, follow_redirects=False)
        hops += 1
    return resp, unit_id


def _start(client: TestClient) -> tuple[str, str]:
    """POST /revision/start → (session_id, first unit id)."""
    resp = client.post("/revision/start", follow_redirects=False)
    assert resp.status_code == 303, resp.text
    return _session_and_unit_from_location(resp.headers["location"])


def _session_of(location: str) -> str:
    return parse_qs(urlsplit(location).query).get("session", [""])[0]


def _finish(client: TestClient, unit_id: str, session_id: str = "") -> str:
    """Complete every mode, then Done. Returns the redirect Location."""
    complete_all_modes(client, MINI_UNITS, unit_id)
    action = with_params(f"/learn/{unit_id}/done", {"session": session_id})
    resp = client.post(action, follow_redirects=False)
    assert resp.status_code == 303, resp.text
    return resp.headers["location"]


# --------------------------------------------------------------------------- #
# Starting                                                                     #
# --------------------------------------------------------------------------- #


def test_revision_start_is_idempotent(tmp_path: Path):
    client = _client(tmp_path)
    _make_due(client, ["clause-1", "article-end"])
    first_id, first_unit = _start(client)
    second_id, second_unit = _start(client)
    assert first_id and first_id == second_id
    assert first_unit == second_unit == "clause-1"


def test_revision_start_with_nothing_due_goes_home(tmp_path: Path):
    client = _client(tmp_path)
    resp = client.post("/revision/start", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    assert _engine(client).active_study_session(kind="revision") is None


def test_start_snapshots_the_due_order(tmp_path: Path):
    client = _client(tmp_path)
    _make_due(client, ["article-end", "clause-1"])
    session_id, first = _start(client)
    session = _engine(client).get_study_session(session_id)
    assert session is not None
    assert [i.learning_unit_id for i in session.items] == ["article-end", "clause-1"]
    assert first == "article-end"


# --------------------------------------------------------------------------- #
# Walking the queue                                                            #
# --------------------------------------------------------------------------- #


def test_done_follows_the_queue_not_the_graph(tmp_path: Path):
    client = _client(tmp_path)
    # clause-1's sequential neighbour is clause-2; the queue's next is
    # article-end. Without a session the redirect goes to clause-2.
    _make_due(client, ["clause-1", "article-end"])
    session_id, first = _start(client)
    assert first == "clause-1"
    location = _finish(client, "clause-1", session_id)
    assert urlsplit(location).path == "/learn/article-end"
    assert _session_of(location) == session_id


def test_sequential_done_is_unchanged_without_a_session(tmp_path: Path):
    client = _client(tmp_path)
    location = _finish(client, "clause-1")
    # clause-2 is split-capable with no preference stored, so sequential
    # navigation lands on the split chooser — as it always has.
    assert location == "/learn/clause-2/choose?done=clause-1"


def test_ajax_done_payload_follows_the_queue(tmp_path: Path):
    """The JSON path recomputed next_url itself, so the HTML fix alone left
    the phone advancing sequentially."""
    client = _client(tmp_path)
    _make_due(client, ["clause-1", "article-end"])
    session_id, _first = _start(client)
    complete_all_modes(client, MINI_UNITS, "clause-1")
    resp = client.post(
        f"/learn/clause-1/done?session={session_id}",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert urlsplit(payload["next_url"]).path == "/learn/article-end"
    assert _session_of(payload["next_url"]) == session_id
    assert payload["session_id"] == session_id
    assert payload["session_remaining"] == 1


def test_again_defers_the_item_and_stays_in_the_queue(tmp_path: Path):
    client = _client(tmp_path)
    _make_due(client, ["clause-1", "article-end"])
    session_id, _first = _start(client)
    resp = client.post(f"/learn/clause-1/again?session={session_id}", follow_redirects=False)
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert urlsplit(location).path == "/learn/article-end"
    assert _session_of(location) == session_id

    session = _engine(client).get_study_session(session_id)
    assert session is not None
    item = session.item_for("clause-1")
    assert item is not None and item.status == "deferred"
    # A deferred unit is not a completed revision.
    assert session.completed_count == 0


def test_queue_exhaustion_completes_the_session_and_lands_home(tmp_path: Path):
    client = _client(tmp_path)
    _make_due(client, ["clause-1", "article-end"])
    session_id, _first = _start(client)
    _finish(client, "clause-1", session_id)
    location = _finish(client, "article-end", session_id)
    assert urlsplit(location).path == "/"
    assert _session_of(location) == ""

    session = _engine(client).get_study_session(session_id)
    assert session is not None
    assert session.status == "complete"
    assert session.completed_count == 2
    assert _engine(client).active_study_session(kind="revision") is None


def test_refresh_mid_session_resumes_the_same_snapshot(tmp_path: Path):
    """Completing an item pushes its next_revision forward, so the live due
    list shrinks. The snapshot must not."""
    client = _client(tmp_path)
    _make_due(client, ["clause-1", "article-end"])
    session_id, _first = _start(client)
    _finish(client, "clause-1", session_id)

    resumed_id, resumed_unit = _start(client)
    assert resumed_id == session_id
    assert resumed_unit == "article-end"
    session = _engine(client).get_study_session(session_id)
    assert session is not None
    assert [i.learning_unit_id for i in session.items] == ["clause-1", "article-end"]
    assert session.remaining == 1


# --------------------------------------------------------------------------- #
# Membership                                                                   #
# --------------------------------------------------------------------------- #


def test_foreign_unit_with_session_redirects_to_pending(tmp_path: Path):
    """A `?session=` that does not include this unit resumes the queue."""
    client = _client(tmp_path)
    _make_due(client, ["clause-1", "article-end"])
    session_id, first = _start(client)

    resp = client.get(f"/learn/clause-2-a?session={session_id}", follow_redirects=False)
    assert resp.status_code == 303
    loc = resp.headers["location"]
    assert loc.startswith(f"/learn/{first}")
    assert f"session={session_id}" in loc

    html = client.get(f"/learn/{first}?session={session_id}").text
    assert f'data-session-id="{session_id}"' in html
    assert "/learn/clause-2?session=" not in html
    assert 'href="/learn/clause-2"' in html


def test_completed_session_is_not_honoured(tmp_path: Path):
    client = _client(tmp_path)
    _make_due(client, ["clause-1", "article-end"])
    session_id, _first = _start(client)
    _finish(client, "clause-1", session_id)
    _finish(client, "article-end", session_id)

    html = client.get(f"/learn/clause-1?session={session_id}").text
    assert "data-session-id" not in html
    assert "data-revision-exit-modal" not in html


def test_unknown_session_id_renders_sequentially(tmp_path: Path):
    client = _client(tmp_path)
    resp = client.get("/learn/clause-1?session=not-a-real-session")
    assert resp.status_code == 200
    assert "data-session-id" not in resp.text


# --------------------------------------------------------------------------- #
# Carrying the session through every hop                                       #
# --------------------------------------------------------------------------- #


def test_next_learn_url_composes_one_query(tmp_path: Path):
    client = _client(tmp_path)
    url = next_learn_url(
        _engine(client), "clause-1", done_unit_id="article-end", session_id="s-1"
    )
    # The old f-string built `?done=x?session=y`, which reads as one value.
    assert url.count("?") == 1
    query = parse_qs(urlsplit(url).query)
    assert query["done"] == ["article-end"]
    assert query["session"] == ["s-1"]


def test_learn_page_carries_the_session_into_every_in_unit_link(tmp_path: Path):
    client = _client(tmp_path)
    _make_due(client, ["clause-1", "article-end"])
    session_id, _first = _start(client)
    html = client.get(f"/learn/clause-1?session={session_id}").text
    assert f'data-session-id="{session_id}"' in html
    for mode in ("read", "cloze", "letters", "type", "recite", "test"):
        # Jinja escapes the separator in an attribute value.
        assert f'href="/learn/clause-1?mode={mode}&amp;session={session_id}"' in html
    assert f'action="/learn/clause-1/done?session={session_id}"' in html
    assert f'action="/learn/clause-1/again?session={session_id}"' in html


def test_mode_switch_keeps_the_session(tmp_path: Path):
    client = _client(tmp_path)
    _make_due(client, ["clause-1", "article-end"])
    session_id, _first = _start(client)
    html = client.get(f"/learn/clause-1?mode=cloze&session={session_id}").text
    assert f'data-session-id="{session_id}"' in html
    assert 'data-mode="cloze"' in html


def test_split_redirect_keeps_the_session(tmp_path: Path):
    """clause-2 has no split preference, so the Learn GET bounces to /choose."""
    client = _client(tmp_path)
    _make_due(client, ["clause-2", "clause-1"])
    session_id, first = _start(client)
    assert first == "clause-2"
    resp = client.get(f"/learn/clause-2?session={session_id}", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/learn/clause-2/choose?session={session_id}"

    choose = client.get(f"/learn/clause-2/choose?session={session_id}")
    assert f'action="/learn/clause-2/choose?session={session_id}"' in choose.text
    picked = client.post(
        f"/learn/clause-2/choose?session={session_id}",
        data={"mode": "whole"},
        follow_redirects=False,
    )
    assert picked.status_code == 303
    assert _session_of(picked.headers["location"]) == session_id


def test_mobile_deck_roundtrip_preserves_the_query(tmp_path: Path):
    """showDeck used to rewrite to a bare /learn/{id}, destroying the session."""
    source = MOBILE_JS.read_text(encoding="utf-8")
    deck = source.split("function showDeck()", 1)[1].split("\n    }", 1)[0]
    assert "URLSearchParams(window.location.search)" in deck
    assert 'params.delete("mode")' in deck
    assert '"/learn/" + encodeURIComponent(unitId));' not in source


# --------------------------------------------------------------------------- #
# Today                                                                        #
# --------------------------------------------------------------------------- #


def test_today_renders_exactly_one_hero(tmp_path: Path):
    client = _client(tmp_path, multiuser=True)
    _sign_in(client)

    caught_up = client.get("/dashboard").text
    assert caught_up.count("data-today-mode=") == 1
    assert 'data-today-mode="learning"' in caught_up
    assert "/revision/start" not in caught_up

    _make_due(client, ["clause-1", "article-end"])
    due = client.get("/dashboard").text
    assert due.count("data-today-mode=") == 1
    assert 'data-today-mode="revision"' in due
    assert 'action="/revision/start"' in due
    assert "Start revision" in due
    assert "Continue where you stopped" not in due


def test_today_shows_continue_revision_with_the_pending_count(tmp_path: Path):
    client = _client(tmp_path, multiuser=True)
    _sign_in(client)
    _make_due(client, ["clause-1", "article-end"])
    session_id, _first = _start(client)
    _finish(client, "clause-1", session_id)

    html = client.get("/dashboard").text
    assert 'data-today-mode="revision"' in html
    assert "Continue revision · 1 left" in html


def test_guest_revision_start_creates_no_session(tmp_path: Path):
    """A guest engine is bound to LOCAL_USER_ID — an unguarded write would
    land in a row shared by every guest."""
    client = _client(tmp_path, multiuser=True)
    resp = client.post("/revision/start", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")
    assert _engine(client).active_study_session(kind="revision") is None


# --------------------------------------------------------------------------- #
# Dates                                                                        #
# --------------------------------------------------------------------------- #


def test_plan_date_uses_the_users_local_date(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    eng.set_setting("user_timezone", "Pacific/Kiritimati")  # UTC+14
    _make_due(client, ["clause-1", "article-end"])
    session_id, _first = _start(client)
    session = eng.get_study_session(session_id)
    assert session is not None

    from constitution_memorizer.web.service import user_today

    assert session.plan_date == user_today(eng)
    # The stale check reads the same date, so today's queue is found again.
    assert eng.active_study_session(kind="revision", plan_date=session.plan_date) is not None


def test_a_session_from_another_day_is_not_resumed(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    _make_due(client, ["clause-1", "article-end"])
    stale = eng.create_study_session(
        session_id="stale-session",
        kind="revision",
        plan_date=date.today() - timedelta(days=1),
        unit_ids=["clause-1"],
    )
    session_id, _first = _start(client)
    assert session_id != stale.id


# --------------------------------------------------------------------------- #
# Revision position                                                            #
# --------------------------------------------------------------------------- #


def test_learn_shows_the_queue_position_not_lifetime_mastery(tmp_path: Path):
    client = _client(tmp_path)
    _make_due(client, ["clause-1", "article-end"])
    session_id, _first = _start(client)
    html = client.get(f"/learn/article-end?session={session_id}").text
    assert "Revision 2 of 2" in html
    assert "data-revision-badge" in html
    # Without a session there is no queue to be 2-of.
    assert "Revision 2 of 2" not in client.get("/learn/article-end").text


# --------------------------------------------------------------------------- #
# Exit guard                                                                   #
# --------------------------------------------------------------------------- #


def test_exit_modal_renders_only_for_an_unfinished_session(tmp_path: Path):
    client = _client(tmp_path)
    _make_due(client, ["clause-1", "article-end"])
    session_id, _first = _start(client)
    assert "data-revision-exit-modal" in client.get(
        f"/learn/clause-1?session={session_id}"
    ).text
    # No session at all → nothing to guard.
    assert "data-revision-exit-modal" not in client.get("/learn/clause-1").text


def test_exit_modal_copy(tmp_path: Path):
    client = _client(tmp_path)
    _make_due(client, ["clause-1", "article-end"])
    session_id, _first = _start(client)
    html = client.get(f"/learn/clause-1?session={session_id}").text
    assert "Exit revision?" in html
    assert "Your completed revisions are saved." in html
    assert "You can return later to finish the remaining revisions." in html
    assert "Keep revising" in html
    assert "Exit revision<" in html


def test_exit_guard_is_armed_by_history_not_by_confirm():
    source = APP_JS.read_text(encoding="utf-8")
    assert "function initRevisionGuard()" in source
    guard = source.split("function initRevisionGuard()", 1)[1].split(
        "\n  function initLearn()", 1
    )[0]
    assert "window.confirm" not in guard
    assert "history.pushState" in guard
    assert 'addEventListener("popstate"' in guard
    assert "showModal()" in guard
    # Exiting navigates; it never posts, deletes or reseeds anything.
    assert "fetch(" not in guard
    assert "/revision/start" not in guard
    assert 'window.location.assign(pendingHref)' in guard


def test_exit_guard_leaves_in_unit_navigation_alone():
    source = APP_JS.read_text(encoding="utf-8")
    guard = source.split("function initRevisionGuard()", 1)[1].split(
        "\n  function initLearn()", 1
    )[0]
    # Only the deck header's anchor leaves the queue. The phone's deck-back is
    # a <button> that returns to the deck within the same unit, and mode tabs
    # stay inside it.
    assert 'closest("a.mobile-back[href]")' in guard
    # No selector reaches the in-unit controls: the phone's deck-back is a
    # <button data-deck-back> and the mode tabs are [data-learn-mode].
    assert "[data-deck-back]" not in guard
    assert "[data-learn-mode]" not in guard
    assert "querySelectorAll" not in guard


def test_mode_switching_still_cannot_fire_popstate():
    """The sentinel only works because nothing else pushes history."""
    source = APP_JS.read_text(encoding="utf-8")
    learn_src = source.split("function initLearn()", 1)[1].split(
        "function initBrowseArticle()", 1
    )[0]
    assert "pushState" not in learn_src
    assert "history.replaceState" in learn_src
    assert "pushState" not in MOBILE_JS.read_text(encoding="utf-8")


def test_no_route_deletes_a_study_session():
    """Exiting preserves the queue so Today can resume it."""
    app_py = (
        ROOT / "src" / "constitution_memorizer" / "web" / "app.py"
    ).read_text(encoding="utf-8")
    assert "delete_study_session" not in app_py
    repo = (
        ROOT / "src" / "constitution_memorizer" / "progress" / "repository.py"
    ).read_text(encoding="utf-8")
    assert "DELETE FROM study_session" not in repo


def test_exiting_preserves_the_queue_for_later(tmp_path: Path):
    client = _client(tmp_path, multiuser=True)
    _sign_in(client)
    _make_due(client, ["clause-1", "article-end"])
    session_id, _first = _start(client)
    _finish(client, "clause-1", session_id)

    # "Exit revision" is a plain navigation to the dashboard — no endpoint.
    assert client.get("/dashboard").status_code == 200
    session = _engine(client).get_study_session(session_id)
    assert session is not None
    assert session.status == "active"
    assert session.completed_count == 1
    assert session.remaining == 1
    resumed_id, resumed_unit = _start(client)
    assert resumed_id == session_id
    assert resumed_unit == "article-end"


# --------------------------------------------------------------------------- #
# Living ahead of the migration                                                #
# --------------------------------------------------------------------------- #


def _drop_session_tables(client: TestClient) -> None:
    """Reproduce production: new code, older schema.

    Deploys and migrations are separate manual steps here (the start command
    does not run Alembic), so this window is structural, not hypothetical.
    """
    conn = _engine(client).repo.conn
    conn.execute("DROP TABLE IF EXISTS study_session_item")
    conn.execute("DROP TABLE IF EXISTS study_session")
    conn.commit()


def test_today_still_renders_when_the_tables_are_missing(tmp_path: Path):
    client = _client(tmp_path, multiuser=True)
    _sign_in(client)
    _make_due(client, ["clause-1", "article-end"])
    _drop_session_tables(client)

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.text
    # The whole context build used to raise, dropping Today into its
    # data-error state — which is what "cannot view Today" looked like.
    assert 'data-today-mode="revision"' in html
    assert '<span class="dash-due-count">2</span>' in html
    assert "revisions due" in html
    # No session is known, so the CTA is Start, never "Continue · N left".
    assert "Start revision" in html
    assert "Continue revision" not in html


def test_start_revision_falls_back_to_the_due_list_without_the_tables(tmp_path: Path):
    """The hero renders without a session, so its CTA must not dead-end."""
    client = _client(tmp_path, multiuser=True)
    _sign_in(client)
    _make_due(client, ["clause-1", "article-end"])
    _drop_session_tables(client)

    resp = client.post("/revision/start", follow_redirects=False)
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert urlsplit(location).path == "/learn/clause-1"
    assert _session_of(location) == ""


def test_a_real_database_error_is_not_swallowed(tmp_path: Path):
    """The guard is narrow: only "that table is missing" is tolerated."""
    from constitution_memorizer.web.service import _is_missing_study_session_table

    assert _is_missing_study_session_table(
        Exception('relation "study_session" does not exist')
    )
    assert _is_missing_study_session_table(Exception("no such table: study_session"))
    assert not _is_missing_study_session_table(Exception("connection refused"))
    assert not _is_missing_study_session_table(
        Exception('relation "learning_unit_progress" does not exist')
    )


def test_learning_session_skip_does_not_schedule_review(tmp_path: Path):
    db = tmp_path / "progress.db"
    app = create_app(units_path=MINI_UNITS, db_path=db)
    engine = app.state.engine
    client = TestClient(app)
    sid, unit_id = _start_plan_my_day(client)
    page, unit_id = _render_learn(client, engine, unit_id, sid)
    assert page.status_code == 200
    assert "Skip for today" in page.text
    skip = client.post(
        f"/learn/{unit_id}/again?session={sid}",
        follow_redirects=False,
    )
    assert skip.status_code == 303
    row = engine.get_progress(unit_id)
    if row is not None:
        assert not (row.status == "review" and row.times_completed == 0)
    loaded = engine.get_study_session(sid)
    assert loaded is not None
    item = loaded.item_for(unit_id)
    assert item is not None
    assert item.status == "deferred"


def test_plan_my_day_split_clause_still_opens_learn(tmp_path: Path):
    """CI hash-seed can put clause-2 first, which 303s to /choose not 404."""
    db = tmp_path / "progress.db"
    app = create_app(units_path=MINI_UNITS, db_path=db)
    engine = app.state.engine
    client = TestClient(app)
    session = engine.create_study_session(
        session_id="s-choose",
        kind="day_plan",
        plan_date=date.today(),
        unit_ids=["clause-2", "clause-1"],
    )
    loc = next_learn_url(engine, "clause-2", session_id=session.id)
    sid, unit_id = _session_and_unit_from_location(loc)
    assert unit_id == "clause-2"
    page, unit_id = _render_learn(client, engine, unit_id, sid)
    assert page.status_code == 200
    assert "Skip for today" in page.text
    client = _client(tmp_path)
    _make_due(client, ["clause-1", "article-end"])
    session_id, unit_id = _start(client)
    page = client.get(f"/learn/{unit_id}?session={session_id}")
    assert "Again tomorrow" in page.text
    again = client.post(
        f"/learn/{unit_id}/again?session={session_id}",
        follow_redirects=False,
    )
    assert again.status_code == 303
    row = _engine(client).get_progress(unit_id)
    assert row is not None
    assert row.next_revision == date.today() + timedelta(days=1)
    loaded = _engine(client).get_study_session(session_id)
    assert loaded is not None
    item = loaded.item_for(unit_id)
    assert item is not None
    assert item.status == "deferred"


def test_mark_done_with_session_completes_item_atomically(tmp_path: Path):
    from constitution_memorizer.web.service import start_or_resume_revision

    engine = ReminderEngine.from_paths(tmp_path / "progress.db", MINI_UNITS)
    today = date.today()
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today - timedelta(days=1))
    engine.mark_all_modes_seen("clause-1")
    session = start_or_resume_revision(engine, as_of=today)
    assert session is not None
    first = session.items[0].learning_unit_id
    engine.mark_done(first, as_of=today, session_id=session.id)
    loaded = engine.get_study_session(session.id)
    assert loaded is not None
    item = loaded.item_for(first)
    assert item is not None
    assert item.status == "completed"


def test_pending_already_completed_item_is_reconciled_on_get(tmp_path: Path):
    db = tmp_path / "progress.db"
    app = create_app(units_path=MINI_UNITS, db_path=db)
    client = TestClient(app)
    sid, unit_id = _start_plan_my_day(client)
    engine = app.state.engine
    unit = engine.get_unit(unit_id)
    if unit is not None and unit.allows_letter_split:
        engine.set_split_preference(unit_id, "whole")
    today = date.today()
    engine.mark_all_modes_seen(unit_id)
    engine.mark_done(unit_id, as_of=today)
    planted = engine.get_study_session(sid)
    assert planted is not None
    assert planted.item_for(unit_id).status == "pending"
    client.get(f"/learn/{unit_id}?session={sid}", follow_redirects=False)
    reconciled = engine.get_study_session(sid)
    assert reconciled is not None
    assert reconciled.item_for(unit_id).status == "completed"
