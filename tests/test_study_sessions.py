"""Study sessions: snapshot, defer, rollover, GET /learn, HTML/JSON nav."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.progress.study_session import (
    close_stale_sessions,
    get_learning_plan,
    mark_item_deferred,
    mark_item_done,
    maybe_activate_auto_plan,
    save_learning_plan,
    start_or_resume_learning,
    start_or_resume_revision,
)
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.completion import (
    done_json_payload,
    resolve_post_action_navigation,
)

from tests.quiz_helpers import complete_all_modes

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


def _engine(tmp_path: Path) -> ReminderEngine:
    return ReminderEngine.from_paths(tmp_path / "progress.db", MINI_UNITS)


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    )


def _session_from_location(location: str) -> tuple[str, str]:
    parsed = urlparse(location)
    unit_id = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    sid = parse_qs(parsed.query).get("session", [""])[0]
    return unit_id, sid


def test_deferred_revision_item_skips_and_completes_session(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date.today()
    for unit_id in ("clause-1", "article-end"):
        engine.mark_all_modes_seen(unit_id)
        engine.mark_done(unit_id, as_of=today - timedelta(days=1))
    session = start_or_resume_revision(engine, today=today)
    assert session is not None
    first = session.items[0]
    second = session.items[1]
    updated = mark_item_deferred(engine, session.id, first.learning_unit_id)
    assert updated is not None
    item = updated.item_for(first.learning_unit_id)
    assert item is not None
    assert item.state == "deferred"
    assert item.deferred_at
    assert item.completed_at is None
    assert updated.pending_count == 1
    assert updated.next_pending().learning_unit_id == second.learning_unit_id
    done = mark_item_done(engine, session.id, second.learning_unit_id)
    assert done is not None
    assert done.status == "completed"
    assert done.pending_count == 0
    assert len(done.completed_items) == 1
    assert first.learning_unit_id not in {
        row.learning_unit_id for row in done.completed_items
    }


def test_date_rollover_abandons_stale_queues(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date.today()
    yesterday = today - timedelta(days=1)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=yesterday - timedelta(days=1))
    stale_rev = engine.repo.insert_study_session(
        engine.user_id,
        session_id="rev-old",
        kind="revision",
        plan_date=yesterday,
        unit_ids=["clause-1"],
    )
    engine.mark_all_modes_seen("article-end")
    engine.mark_done("article-end", as_of=yesterday)
    stale_learn = engine.repo.insert_study_session(
        engine.user_id,
        session_id="learn-old",
        kind="one_day_learning",
        plan_date=yesterday,
        unit_ids=["clause-1", "article-end"],
    )
    engine.repo.set_session_item_state(
        engine.user_id,
        stale_learn.id,
        "article-end",
        "completed",
        completed_at="2026-08-01T00:00:00+00:00",
    )
    close_stale_sessions(engine, today=today)
    assert engine.repo.get_study_session(engine.user_id, stale_rev.id).status == "abandoned"
    assert engine.repo.get_study_session(engine.user_id, stale_learn.id).status == "abandoned"
    fresh = start_or_resume_revision(engine, today=today)
    assert fresh is not None
    assert fresh.id != stale_rev.id
    assert fresh.plan_date == today
    from constitution_memorizer.progress.mix_selector import eligible_new_units

    eligible = {unit.id for unit in eligible_new_units(engine)}
    assert "clause-1" not in eligible  # already learned
    # Unfinished selected units that were never completed stay eligible only
    # if they were never learned — article-end was completed as real progress.
    row = engine.get_progress("article-end")
    assert row is not None and row.times_completed >= 1


def test_unanchored_auto_activates_on_new_not_revision(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date.today()
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today - timedelta(days=1))
    save_learning_plan(engine, mode="auto", daily_target=3)
    assert get_learning_plan(engine).activated_at is None
    engine.mark_all_modes_seen("clause-1")
    revision = engine.mark_done("clause-1", as_of=today)
    maybe_activate_auto_plan(
        engine,
        was_new_unit=revision.progress.times_completed == 1,
        today=today,
    )
    assert get_learning_plan(engine).activated_at is None

    session = start_or_resume_learning(
        engine, kind="auto_learning", count=3, today=today
    )
    assert session is not None
    engine.mark_all_modes_seen("article-end")
    fresh = engine.mark_done("article-end", as_of=today)
    maybe_activate_auto_plan(
        engine,
        was_new_unit=fresh.progress.times_completed == 1,
        today=today,
    )
    assert get_learning_plan(engine).activated_at == today


def test_get_learn_does_not_create_session(tmp_path: Path):
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    today = date.today()
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today - timedelta(days=1))
    client = TestClient(create_app(units_path=MINI_UNITS, db_path=db))
    resp = client.get("/learn", follow_redirects=False)
    assert resp.status_code in (303, 307)
    conn = sqlite3.connect(db)
    try:
        n = conn.execute("SELECT COUNT(*) FROM study_session").fetchone()[0]
    finally:
        conn.close()
    assert n == 0
    start = client.post("/study/revision/start", follow_redirects=False)
    assert start.status_code == 303
    loc = start.headers["location"]
    assert "session=" in loc
    again = client.post("/study/revision/start", follow_redirects=False)
    assert again.headers["location"] == loc
    conn = sqlite3.connect(db)
    try:
        n = conn.execute("SELECT COUNT(*) FROM study_session").fetchone()[0]
    finally:
        conn.close()
    assert n == 1


def test_html_and_json_navigation_match(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date.today()
    for unit_id in ("clause-1", "article-end"):
        engine.mark_all_modes_seen(unit_id)
        engine.mark_done(unit_id, as_of=today - timedelta(days=1))
        engine.mark_all_modes_seen(unit_id)
    session = start_or_resume_revision(engine, today=today)
    assert session is not None
    first = session.items[0]
    unit = engine.get_unit(first.learning_unit_id)
    result = engine.mark_done(first.learning_unit_id, as_of=today)
    mark_item_done(engine, session.id, first.learning_unit_id)
    html_url = resolve_post_action_navigation(
        engine,
        unit_id=first.learning_unit_id,
        sequential_next_id=result.next_unit_id,
        session_id=session.id,
        done_unit_id=first.learning_unit_id,
        multiuser=False,
    )
    payload = done_json_payload(
        eng=engine,
        quotes=[],
        unit=unit,
        result=result,
        request=None,
        multiuser=False,
        session_id=session.id,
    )
    assert payload["next_url"] == html_url
    assert f"session={session.id}" in html_url


def test_html_done_keeps_session_query_on_next_pending(tmp_path: Path):
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    today = date.today()
    for unit_id in ("clause-1", "article-end"):
        engine.mark_all_modes_seen(unit_id)
        engine.mark_done(unit_id, as_of=today - timedelta(days=1))
    client = TestClient(create_app(units_path=MINI_UNITS, db_path=db))
    start = client.post("/study/revision/start", follow_redirects=False)
    first_id, sid = _session_from_location(start.headers["location"])
    complete_all_modes(client, MINI_UNITS, first_id)
    html_done = client.post(
        f"/learn/{first_id}/done",
        data={"session": sid},
        follow_redirects=False,
    )
    assert html_done.status_code == 303
    loc = html_done.headers["location"]
    assert f"session={sid}" in loc
    assert f"done={first_id}" in loc


def test_json_done_next_url_keeps_session(tmp_path: Path):
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    today = date.today()
    for unit_id in ("clause-1", "article-end"):
        engine.mark_all_modes_seen(unit_id)
        engine.mark_done(unit_id, as_of=today - timedelta(days=1))
    client = TestClient(create_app(units_path=MINI_UNITS, db_path=db))
    start = client.post("/study/revision/start", follow_redirects=False)
    first_id, sid = _session_from_location(start.headers["location"])
    complete_all_modes(client, MINI_UNITS, first_id)
    json_done = client.post(
        f"/learn/{first_id}/done",
        data={"session": sid},
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        },
        follow_redirects=False,
    )
    assert json_done.status_code == 200
    next_url = json_done.json()["next_url"]
    assert f"session={sid}" in next_url
    assert f"done={first_id}" in next_url


def test_session_param_survives_learn_page_hops(tmp_path: Path):
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    today = date.today()
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today - timedelta(days=1))
    client = TestClient(create_app(units_path=MINI_UNITS, db_path=db))
    start = client.post("/study/revision/start", follow_redirects=False)
    unit_id, sid = _session_from_location(start.headers["location"])
    page = client.get(f"/learn/{unit_id}?session={sid}")
    assert page.status_code == 200
    html = page.text
    assert f'name="session" value="{sid}"' in html
    assert f"?mode=cloze&amp;session={sid}" in html or f"?mode=cloze&session={sid}" in html
    assert "Exit revision?" in html
    assert 'data-exit-revision="true"' in html
    complete_all_modes(client, MINI_UNITS, unit_id)
    html_done = client.post(
        f"/learn/{unit_id}/done",
        data={"session": sid},
        follow_redirects=False,
    )
    assert html_done.status_code == 303
    loc = html_done.headers["location"]
    assert "done=" in loc
    assert "/learn/clause-2" not in loc
    assert "caught_up=1" in loc or f"session={sid}" in loc


def test_exit_revision_leaves_session_active(tmp_path: Path):
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    today = date.today()
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today - timedelta(days=1))
    client = TestClient(create_app(units_path=MINI_UNITS, db_path=db))
    start = client.post("/study/revision/start", follow_redirects=False)
    _unit_id, sid = _session_from_location(start.headers["location"])
    exit_resp = client.post("/study/revision/exit", follow_redirects=False)
    assert exit_resp.status_code == 303
    loaded = engine.repo.get_study_session(engine.user_id, sid)
    assert loaded is not None
    assert loaded.status == "active"
    assert loaded.pending_count >= 1


def _rewrite_deck_url(href: str, data_session_id: str = "") -> str:
    """Python replica of mobile.js showDeck() query rewrite."""
    parts = urlsplit(href)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.pop("mode", None)
    if data_session_id and "session" not in query:
        query["session"] = data_session_id
    return urlunsplit(("", "", parts.path, urlencode(query), parts.fragment))


def test_showdeck_keeps_session_drops_only_mode(tmp_path: Path):
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    today = date.today()
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today - timedelta(days=1))
    client = TestClient(create_app(units_path=MINI_UNITS, db_path=db))
    start = client.post("/study/revision/start", follow_redirects=False)
    unit_id, sid = _session_from_location(start.headers["location"])
    page = client.get(f"/learn/{unit_id}?session={sid}&mode=read")
    assert page.status_code == 200
    html = page.text
    assert 'data-mobile-view="mode"' in html
    assert f'data-session-id="{sid}"' in html
    assert "data-deck-back" in html
    assert f"session={sid}" in html
    source = Path("src/constitution_memorizer/web/static/mobile.js").read_text(
        encoding="utf-8"
    )
    show = source[source.index("function showDeck") : source.index("function refreshDeckState")]
    assert 'searchParams.delete("mode")' in show
    assert 'history.replaceState({}, "", "/learn/" + encodeURIComponent(unitId))' not in show
    assert _rewrite_deck_url("/learn/u?session=abc&mode=cloze") == "/learn/u?session=abc"


def test_exit_revision_guard_registers_popstate():
    source = Path("src/constitution_memorizer/web/static/app.js").read_text(
        encoding="utf-8"
    )
    guard = source[
        source.index("function initExitRevisionGuard") : source.index(
            "function initPlanMyDayDialog"
        )
    ]
    assert 'addEventListener("popstate"' in guard
    assert "history.pushState" in guard
    assert "window.confirm" not in guard
    assert "[data-deck-back]" in guard
    assert "[data-learn-mode]" in guard


def test_foreign_unit_with_session_redirects_to_pending(tmp_path: Path):
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    today = date.today()
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today - timedelta(days=1))
    client = TestClient(create_app(units_path=MINI_UNITS, db_path=db))
    start = client.post("/study/revision/start", follow_redirects=False)
    unit_id, sid = _session_from_location(start.headers["location"])
    assert unit_id == "clause-1"
    resp = client.get(f"/learn/article-end?session={sid}", follow_redirects=False)
    assert resp.status_code == 303
    loc = resp.headers["location"]
    assert loc.startswith("/learn/clause-1")
    assert f"session={sid}" in loc
    page = client.get(f"/learn/clause-1?session={sid}")
    assert page.status_code == 200
    assert "/learn/clause-2?session=" not in page.text
    assert 'href="/learn/clause-2"' in page.text


def test_learning_session_skip_does_not_schedule_review(tmp_path: Path):
    db = tmp_path / "progress.db"
    app = create_app(units_path=MINI_UNITS, db_path=db)
    engine = app.state.engine
    client = TestClient(app)
    start = client.post(
        "/study/plan-my-day",
        data={"count": "3"},
        follow_redirects=False,
    )
    assert start.status_code == 303
    unit_id, sid = _session_from_location(start.headers["location"])
    page = client.get(f"/learn/{unit_id}?session={sid}", follow_redirects=False)
    assert page.status_code == 200
    assert "Skip for today" in page.text
    skip = client.post(
        f"/learn/{unit_id}/again",
        data={"session": sid},
        follow_redirects=False,
    )
    assert skip.status_code == 303
    row = engine.get_progress(unit_id)
    if row is not None:
        assert not (row.status == "review" and row.times_completed == 0)
    loaded = engine.repo.get_study_session(engine.user_id, sid)
    assert loaded is not None
    item = loaded.item_for(unit_id)
    assert item is not None
    assert item.state == "deferred"
    assert "session=" in skip.headers["location"] or "caught_up=" in skip.headers["location"]


def test_revision_again_still_defers_until_tomorrow(tmp_path: Path):
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    today = date.today()
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today - timedelta(days=1))
    client = TestClient(create_app(units_path=MINI_UNITS, db_path=db))
    start = client.post("/study/revision/start", follow_redirects=False)
    unit_id, sid = _session_from_location(start.headers["location"])
    page = client.get(f"/learn/{unit_id}?session={sid}")
    assert "Again tomorrow" in page.text
    again = client.post(
        f"/learn/{unit_id}/again",
        data={"session": sid},
        follow_redirects=False,
    )
    assert again.status_code == 303
    row = engine.get_progress(unit_id)
    assert row is not None
    assert row.next_revision == today + timedelta(days=1)
    loaded = engine.repo.get_study_session(engine.user_id, sid)
    item = loaded.item_for(unit_id)
    assert item is not None
    assert item.state == "deferred"


def test_mark_done_with_session_completes_item_atomically(tmp_path: Path):
    engine = _engine(tmp_path)
    today = date.today()
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today - timedelta(days=1))
    engine.mark_all_modes_seen("clause-1")
    session = start_or_resume_revision(engine, today=today)
    assert session is not None
    first = session.items[0].learning_unit_id
    engine.mark_done(first, as_of=today, session_id=session.id)
    loaded = engine.repo.get_study_session(engine.user_id, session.id)
    assert loaded is not None
    item = loaded.item_for(first)
    assert item is not None
    assert item.state == "completed"


def test_pending_already_completed_item_is_reconciled_on_get(tmp_path: Path):
    db = tmp_path / "progress.db"
    app = create_app(units_path=MINI_UNITS, db_path=db)
    client = TestClient(app)
    start = client.post(
        "/study/plan-my-day",
        data={"count": "3"},
        follow_redirects=False,
    )
    assert start.status_code == 303
    unit_id, sid = _session_from_location(start.headers["location"])
    engine = app.state.engine
    today = date.today()
    engine.mark_all_modes_seen(unit_id)
    engine.mark_done(unit_id, as_of=today)
    planted = engine.repo.get_study_session(engine.user_id, sid)
    assert planted is not None
    assert planted.item_for(unit_id).state == "pending"
    client.get(f"/learn/{unit_id}?session={sid}", follow_redirects=False)
    reconciled = engine.repo.get_study_session(engine.user_id, sid)
    assert reconciled is not None
    assert reconciled.item_for(unit_id).state == "completed"
