"""Milestone 7: Playground six-mode law-learning engine.

M7 replaces proof Cloze completion semantics. Completing a mode writes
``user_playground_mode_progress`` only. M8 will add Learned → Day 1.
"""

from __future__ import annotations

import ast
import inspect
import sqlite3
from html import unescape
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from alembic.config import Config
from alembic.script import ScriptDirectory

from constitution_memorizer.playground.db import (
    BACKFILL_CLOZE_SQL,
    SCHEMA_SQL,
    ensure_sqlite_schema,
)
from constitution_memorizer.playground.learning.modes import (
    PLAYGROUND_LEARN_MODES,
    PLAYGROUND_MODE_LABELS,
)
from constitution_memorizer.playground.learning.service import load_learn_provision
from constitution_memorizer.playground.learning.test import (
    build_section_quiz,
    coerce_quiz_answers,
    grade_section_quiz,
)
from constitution_memorizer.playground.locators import section_locator
from constitution_memorizer.playground.postgres import PostgresPlaygroundRepository
from constitution_memorizer.playground.repository import SqlitePlaygroundRepository
from constitution_memorizer.playground.source import (
    canonical_body_text,
    locators_for_act,
    source_hash,
)
from constitution_memorizer.playground.urls import (
    law_path,
    learn_complete_path,
    learn_path,
    learn_quiz_path,
    learn_start_path,
    sections_path,
)
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act
from tests.test_playground import (
    MINI_UNITS,
    _add_and_select,
    _add_law,
    _client,
    _sqlite_repo,
)
from tests.test_roster_m5a import (
    USER,
    _authed_client,
    _confirm_add,
    _csrf,
    _subscribe,
)

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "20260925_0026"
MODES = PLAYGROUND_LEARN_MODES


def _complete(client: TestClient, law_id: str, number: str, mode: str):
    data = _csrf(client) if client.cookies.get("rtc_csrf") else {}
    return client.post(learn_complete_path(law_id, number, mode), data=data)


def _json_post(client: TestClient, url: str, payload: dict):
    token = client.cookies.get("rtc_csrf") or ""
    body = dict(payload)
    if token:
        body["csrf_token"] = token
    return client.post(
        url,
        json=body,
        headers={"X-CSRF-Token": token, "Accept": "application/json"},
    )


def test_mode_registry_is_recallc_six_without_write():
    assert MODES == ("read", "cloze", "letters", "type", "recite", "test")
    assert "write" not in MODES
    assert PLAYGROUND_MODE_LABELS["type"] == "Type"
    tracker = (ROOT / "docs" / "PLAYGROUND_DELIVERY_TRACKER.md").read_text()
    m7 = tracker.split("# 8.")[0]
    assert "* [ ] Write" not in m7
    assert "remaining RecallC mode" not in m7
    assert "* [ ] Read" in m7 or "* [x] Read" in m7
    assert "* [ ] Letters" in m7 or "* [x] Letters" in m7
    assert "* [ ] Test" in m7 or "* [x] Test" in m7


def test_alembic_0025_parent_one_head_rls_and_sqlite_parity():
    cfg = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [EXPECTED_HEAD]
    rev = script.get_revision("20260924_0025")
    assert rev.down_revision == "20260917_0024"
    path = ROOT / "alembic" / "versions" / "20260924_0025_playground_mode_progress.py"
    text = path.read_text(encoding="utf-8")
    ast.parse(text, filename=str(path))
    assert "user_playground_mode_progress" in text
    assert "PRIMARY KEY (user_id, law_id, source_locator, mode)" in text
    assert "read', 'cloze', 'letters', 'type', 'recite', 'test'" in text
    assert "in_progress', 'completed'" in text
    assert "ENABLE ROW LEVEL SECURITY" in text
    assert "cloze_done" in text
    overlay = (
        ROOT / "alembic" / "versions" / "20260906_0017_playground_overlay.py"
    ).read_text()
    assert "user_playground_mode_progress" not in overlay
    roster = (
        ROOT / "alembic" / "versions" / "20260917_0024_playground_roster.py"
    ).read_text()
    assert "user_playground_mode_progress" not in roster
    assert "PRIMARY KEY (user_id, law_id, source_locator, mode)" in SCHEMA_SQL
    assert "CHECK (mode IN ('read', 'cloze', 'letters', 'type', 'recite', 'test'))" in SCHEMA_SQL
    assert "ON CONFLICT (user_id, law_id, source_locator, mode) DO NOTHING" in BACKFILL_CLOZE_SQL


def test_sqlite_backfill_cloze_done_without_duplicates(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "m7.db")
    conn.row_factory = sqlite3.Row
    ensure_sqlite_schema(conn)
    uid = str(LOCAL_USER_ID)
    conn.execute(
        """
        INSERT INTO user_playground_progress (
            user_id, law_id, source_locator, status, cloze_done,
            times_completed, last_completed, next_revision, interval_days,
            source_version, source_hash, updated_at
        ) VALUES (?, 'ndps', 'ndps:section:1', 'review', 1, 2, '2026-09-10',
                  '2026-09-11', 1, 'v1', 'hash-a', '2026-09-10T00:00:00+00:00')
        """,
        (uid,),
    )
    conn.commit()
    ensure_sqlite_schema(conn)
    ensure_sqlite_schema(conn)
    rows = conn.execute(
        """
        SELECT mode, status, attempt_count, source_hash, source_version
        FROM user_playground_mode_progress
        WHERE user_id = ? AND source_locator = 'ndps:section:1'
        """,
        (uid,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["mode"] == "cloze"
    assert rows[0]["status"] == "completed"
    assert int(rows[0]["attempt_count"]) == 2
    assert rows[0]["source_hash"] == "hash-a"
    leftover = conn.execute(
        "SELECT status, interval_days FROM user_playground_progress"
    ).fetchone()
    assert leftover["status"] == "review"
    assert int(leftover["interval_days"]) == 1


def test_mode_check_rejects_write(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    with pytest.raises(ValueError):
        repo.complete_mode(
            LOCAL_USER_ID,
            "ndps",
            "ndps:section:1",
            "write",
            source_version="v",
            source_hash="h",
        )
    with pytest.raises(sqlite3.IntegrityError):
        repo.conn.execute(
            """
            INSERT INTO user_playground_mode_progress (
                user_id, law_id, source_locator, mode, status, attempt_count,
                first_started_at, last_attempt_at, completed_at,
                source_version, source_hash, created_at, updated_at
            ) VALUES (?, 'ndps', 'ndps:section:1', 'write', 'completed', 1,
                      't', 't', 't', 'v', 'h', 't', 't')
            """,
            (str(LOCAL_USER_ID),),
        )


@pytest.mark.parametrize("mode", MODES)
def test_repository_start_complete_reload_idempotent(tmp_path: Path, mode: str):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="tok")
    loc = "ndps:section:8"
    started = repo.start_mode(
        LOCAL_USER_ID, "ndps", loc, mode, source_version="v", source_hash="hash-a"
    )
    assert started.status == "in_progress"
    assert started.attempt_count == 0
    first = repo.complete_mode(
        LOCAL_USER_ID, "ndps", loc, mode, source_version="v", source_hash="hash-a"
    )
    assert first.status == "completed"
    assert first.attempt_count == 1
    completed_at = first.completed_at
    second = repo.complete_mode(
        LOCAL_USER_ID, "ndps", loc, mode, source_version="v2", source_hash="hash-b"
    )
    assert second.status == "completed"
    assert second.attempt_count == 2
    assert second.completed_at == completed_at
    assert second.source_hash == "hash-a"
    loaded = repo.get_mode_progress(LOCAL_USER_ID, "ndps", loc, mode)
    assert loaded == second
    other = [row.mode for row in repo.list_mode_progress(LOCAL_USER_ID, "ndps", loc)]
    assert other == [mode]


def test_mode_progress_cross_user_isolation(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    other = UUID("22222222-2222-4222-8222-222222222222")
    loc = "ndps:section:1"
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    repo.add_item(other, "ndps", source_version="v", law_source_hash="t")
    repo.complete_mode(
        LOCAL_USER_ID, "ndps", loc, "read", source_version="v", source_hash="h"
    )
    assert repo.get_mode_progress(other, "ndps", loc, "read") is None
    assert repo.list_mode_progress(other, "ndps") == []


def test_postgres_mode_upsert_uses_on_conflict():
    source = inspect.getsource(PostgresPlaygroundRepository.complete_mode)
    assert "ON CONFLICT (user_id, law_id, source_locator, mode)" in source
    start = inspect.getsource(PostgresPlaygroundRepository.start_mode)
    assert "ON CONFLICT (user_id, law_id, source_locator, mode)" in start
    listed = inspect.getsource(PostgresPlaygroundRepository.list_mode_progress)
    assert "user_id = %s AND law_id = %s" in listed
    sqlite_src = inspect.getsource(SqlitePlaygroundRepository.list_mode_progress)
    assert "user_id = ? AND law_id = ?" in sqlite_src


@pytest.mark.parametrize("mode", MODES)
def test_get_selected_section_is_200(tmp_path: Path, mode: str):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    page = client.get(learn_path("ndps", "1", mode))
    assert page.status_code == 200
    assert PLAYGROUND_MODE_LABELS[mode] in page.text
    assert "data-pg-learn" in page.text
    loc = section_locator("ndps", "1").value
    assert (
        client.app.state.playground.get_mode_progress(
            LOCAL_USER_ID, "ndps", loc, mode
        )
        is None
    )


def test_unknown_mode_is_404(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    assert client.get(learn_path("ndps", "1", "write")).status_code == 404
    assert client.get(learn_path("ndps", "1", "mode5")).status_code == 404
    posted = client.post(learn_complete_path("ndps", "1", "write"))
    assert posted.status_code == 404
    loc = section_locator("ndps", "1").value
    assert client.app.state.playground.list_mode_progress(LOCAL_USER_ID, "ndps", loc) == []


def test_unselected_section_redirects_without_write(tmp_path: Path):
    client = _client(tmp_path)
    _add_law(client, "ndps")
    page = client.get(learn_path("ndps", "1", "read"), follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"] == sections_path("ndps")
    denied = client.post(learn_complete_path("ndps", "1", "read"))
    assert denied.status_code == 400
    loc = section_locator("ndps", "1").value
    assert client.app.state.playground.list_mode_progress(LOCAL_USER_ID, "ndps", loc) == []


def test_read_get_does_not_complete(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    page = client.get(learn_path("ndps", "1", "read"))
    assert page.status_code == 200
    assert "Mark as read" in page.text
    loc = section_locator("ndps", "1").value
    assert (
        client.app.state.playground.get_mode_progress(
            LOCAL_USER_ID, "ndps", loc, "read"
        )
        is None
    )
    done = _complete(client, "ndps", "1", "read")
    assert done.status_code == 200
    assert done.json()["status"] == "completed"
    reload_page = client.get(learn_path("ndps", "1", "read"))
    assert "Done." in reload_page.text


def test_read_complete_control_not_constitution_desktop_hidden():
    html = (
        ROOT / "src/constitution_memorizer/web/templates/playground_learn.html"
    ).read_text(encoding="utf-8")
    css = (
        ROOT / "src/constitution_memorizer/web/static/playground.css"
    ).read_text(encoding="utf-8")
    assert "learn-read-controls" not in html
    assert "pg-learn-actions" in html
    assert "Mark as read" in html
    assert "learn-panel-cloze" not in html
    assert "learn-panel-letters" not in html
    assert "learn-panel-type" not in html
    assert "learn-panel-recite" not in html
    assert "learn-panel-test" not in html
    assert ".pg-learn-actions" in css
    before_desktop = css.split("@media (min-width: 1040px)")[0]
    deck = before_desktop.split(".pg-learn-deck")[1][:160]
    assert "display: none" in deck


@pytest.mark.parametrize("mode", ("read", "cloze", "letters", "type", "recite"))
def test_mode_complete_persists_and_leaves_others(tmp_path: Path, mode: str):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    loc = section_locator("ndps", "1").value
    first = _complete(client, "ndps", "1", mode)
    assert first.status_code == 200
    payload = first.json()
    assert payload["ok"] is True
    assert payload["status"] == "completed"
    assert payload["completed_modes"] == [mode]
    second = _complete(client, "ndps", "1", mode)
    assert second.json()["attempt_count"] == 2
    overlay = client.app.state.playground
    row = overlay.get_mode_progress(LOCAL_USER_ID, "ndps", loc, mode)
    assert row is not None
    assert row.status == "completed"
    for other in MODES:
        if other == mode:
            continue
        assert overlay.get_mode_progress(LOCAL_USER_ID, "ndps", loc, other) is None
    legacy = overlay.get_progress(LOCAL_USER_ID, "ndps", loc)
    assert legacy is None


def test_http_cloze_does_not_schedule_day_1(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    payload = _complete(client, "ndps", "1", "cloze").json()
    assert "interval_days" not in payload
    assert "next_revision" not in payload
    loc = section_locator("ndps", "1").value
    assert client.app.state.playground.get_progress(LOCAL_USER_ID, "ndps", loc) is None


def test_six_modes_generic_across_ndps_bns_bnss(tmp_path: Path):
    client = _client(tmp_path)
    for law_id in ("ndps", "bns", "bnss"):
        _add_and_select(client, law_id, "1")
        act = get_bare_act(law_id)
        section = act.section("1")
        body = canonical_body_text(section)
        loc = section_locator(law_id, "1").value
        for mode in MODES:
            page = client.get(learn_path(law_id, "1", mode))
            assert page.status_code == 200
            html = unescape(page.text)
            assert body[:60] in html
            if mode == "cloze":
                assert "learn-cloze-density" in html
                assert "learn-panel-cloze" not in html
            if mode != "test":
                done = _complete(client, law_id, "1", mode)
                assert done.status_code == 200
                assert done.json()["ok"] is True
            else:
                questions = build_section_quiz(
                    law_id=law_id,
                    source_locator=loc,
                    canonical_body=body,
                    cycle=0,
                    source_hash=source_hash(section),
                )
                answers = [
                    q.answer_index if q.kind == "mcq" else q.answer_text
                    for q in questions
                ]
                quiz = _json_post(
                    client,
                    learn_quiz_path(law_id, "1"),
                    {"cycle": 0, "answers": answers},
                )
                assert quiz.status_code == 200
                assert quiz.json()["status"] == "completed"
        summary = client.app.state.playground.list_mode_progress(
            LOCAL_USER_ID, law_id, loc
        )
        assert {row.mode for row in summary if row.status == "completed"} == set(MODES)


def test_entire_act_opens_modes_at_several_points(tmp_path: Path):
    client = _client(tmp_path)
    _add_law(client, "ndps")
    saved = client.post(
        sections_path("ndps"), data={"entire": "1"}, follow_redirects=False
    )
    assert saved.status_code == 303
    locators = locators_for_act("ndps")
    selected = {
        row.source_locator
        for row in client.app.state.playground.list_selection(LOCAL_USER_ID, "ndps")
    }
    assert {loc.value for loc in locators} == selected
    assert "ndps:section:65" not in selected
    picks = [locators[0], locators[len(locators) // 2], locators[-1]]
    assert len({item.value for item in picks}) == 3
    for loc in picks:
        for mode in MODES:
            page = client.get(learn_path("ndps", loc.number, mode))
            assert page.status_code == 200


def test_omitted_section_is_not_learnable(tmp_path: Path):
    client = _client(tmp_path)
    _add_law(client, "ndps")
    client.post(sections_path("ndps"), data={"entire": "1"}, follow_redirects=False)
    selected = {
        row.source_locator
        for row in client.app.state.playground.list_selection(LOCAL_USER_ID, "ndps")
    }
    assert "ndps:section:65" not in selected
    page = client.get(learn_path("ndps", "65", "read"), follow_redirects=False)
    assert page.status_code in {303, 404}
    posted = client.post(learn_complete_path("ndps", "65", "read"))
    assert posted.status_code in {400, 404}
    assert (
        client.app.state.playground.list_mode_progress(
            LOCAL_USER_ID, "ndps", "ndps:section:65"
        )
        == []
    )


def test_resume_three_modes_after_new_client(tmp_path: Path):
    db = tmp_path / "progress.db"
    client = TestClient(create_app(units_path=MINI_UNITS, db_path=db))
    _add_and_select(client, "ndps", "1")
    for mode in ("read", "cloze", "letters"):
        assert _complete(client, "ndps", "1", mode).status_code == 200
    again = TestClient(create_app(units_path=MINI_UNITS, db_path=db))
    page = again.get(learn_path("ndps", "1", "type"))
    assert page.status_code == 200
    assert "Read ✓" in page.text
    assert "Cloze ✓" in page.text
    assert "Letters ✓" in page.text
    assert "Type ✓" not in page.text
    loc = section_locator("ndps", "1").value
    rows = {
        row.mode
        for row in again.app.state.playground.list_mode_progress(
            LOCAL_USER_ID, "ndps", loc
        )
        if row.status == "completed"
    }
    assert rows == {"read", "cloze", "letters"}


def test_cross_device_same_mode_rows(tmp_path: Path):
    first = _authed_client(tmp_path)
    _subscribe(first)
    _confirm_add(first, "ndps")
    first.post(
        sections_path("ndps"),
        data={**_csrf(first), "section": "1"},
        follow_redirects=False,
    )
    for mode in ("read", "cloze"):
        assert _complete(first, "ndps", "1", mode).status_code == 200
    second = TestClient(first.app)
    start = second.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    second.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    page = second.get(learn_path("ndps", "1", "letters"))
    assert page.status_code == 200
    assert "Read ✓" in page.text
    assert "Cloze ✓" in page.text
    loc = section_locator("ndps", "1").value
    rows = first.app.state.playground.list_mode_progress(USER, "ndps", loc)
    assert {row.mode for row in rows if row.status == "completed"} == {"read", "cloze"}


def test_roster_remove_readd_keeps_modes(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    _confirm_add(client, "ndps")
    client.post(
        sections_path("ndps"),
        data={**_csrf(client), "section": "1"},
        follow_redirects=False,
    )
    for mode in ("read", "cloze", "letters"):
        assert _complete(client, "ndps", "1", mode).status_code == 200
    loc = section_locator("ndps", "1").value
    before = client.app.state.playground.list_mode_progress(USER, "ndps", loc)
    client.post(
        "/playground/roster/ndps/remove",
        data=_csrf(client),
        follow_redirects=False,
    )
    blocked = client.get(learn_path("ndps", "1", "type"))
    assert blocked.status_code == 200
    assert "Progress saved" in blocked.text or "Add to this month" in blocked.text
    assert client.app.state.playground.list_mode_progress(USER, "ndps", loc) == before
    _confirm_add(client, "ndps")
    page = client.get(learn_path("ndps", "1", "type"))
    assert page.status_code == 200
    assert "Read ✓" in page.text
    assert client.app.state.playground.list_mode_progress(USER, "ndps", loc) == before


def test_source_identity_mismatch_does_not_mutate(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    _complete(client, "ndps", "1", "read")
    loc = section_locator("ndps", "1").value
    repo = client.app.state.playground
    repo.conn.execute(
        """
        UPDATE user_playground_mode_progress
        SET source_hash = 'aaaa', source_version = 'old'
        WHERE source_locator = ?
        """,
        (loc,),
    )
    repo.conn.commit()
    page = client.get(learn_path("ndps", "1", "read"))
    assert page.status_code == 200
    assert "Law updated" in page.text
    row = repo.get_mode_progress(LOCAL_USER_ID, "ndps", loc, "read")
    assert row is not None
    assert row.source_hash == "aaaa"
    assert row.source_version == "old"
    assert row.status == "completed"


def test_test_mode_no_answer_leak_and_stale_cycle(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    page = client.get(learn_path("ndps", "1", "test"))
    assert page.status_code == 200
    assert "answer_index" not in page.text
    assert "answer_text" not in page.text
    loc, _act, section, body, live, _version = load_learn_provision("ndps", "1")
    questions = build_section_quiz(
        law_id="ndps",
        source_locator=loc.value,
        canonical_body=body,
        cycle=0,
        source_hash=live,
    )
    assert questions
    malformed = _json_post(
        client, learn_quiz_path("ndps", "1"), {"cycle": 0, "answers": []}
    )
    assert malformed.status_code == 400
    answers = [
        q.answer_index if q.kind == "mcq" else q.answer_text for q in questions
    ]
    first = _json_post(
        client, learn_quiz_path("ndps", "1"), {"cycle": 0, "answers": answers}
    )
    assert first.status_code == 200
    stale = _json_post(
        client, learn_quiz_path("ndps", "1"), {"cycle": 0, "answers": answers}
    )
    assert stale.status_code == 409
    assert coerce_quiz_answers(["x"], 2) is None
    graded = grade_section_quiz(questions, answers)
    assert graded["total"] == len(questions)


def test_test_seed_is_stable():
    section = get_bare_act("ndps").section("1")
    body = canonical_body_text(section)
    loc = section_locator("ndps", "1").value
    digest = source_hash(section)
    first = build_section_quiz(
        law_id="ndps", source_locator=loc, canonical_body=body, cycle=3, source_hash=digest
    )
    second = build_section_quiz(
        law_id="ndps", source_locator=loc, canonical_body=body, cycle=3, source_hash=digest
    )
    assert [q.public_dict() for q in first] == [q.public_dict() for q in second]
    third = build_section_quiz(
        law_id="ndps", source_locator=loc, canonical_body=body, cycle=4, source_hash=digest
    )
    assert [q.prompt for q in first] != [q.prompt for q in third] or first != third


def test_workspace_shows_method_progress_not_learned(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    for mode in ("read", "cloze", "letters", "type"):
        _complete(client, "ndps", "1", mode)
    page = client.get(law_path("ndps"))
    assert "4 of 6 methods" in page.text
    assert "Start learning" in page.text or "Continue" in page.text
    assert "Learn (Cloze)" not in page.text
    _complete(client, "ndps", "1", "recite")
    loc, _act, section, body, live, _v = load_learn_provision("ndps", "1")
    questions = build_section_quiz(
        law_id="ndps",
        source_locator=loc.value,
        canonical_body=body,
        cycle=0,
        source_hash=live,
    )
    answers = [q.answer_index if q.kind == "mcq" else q.answer_text for q in questions]
    _json_post(client, learn_quiz_path("ndps", "1"), {"cycle": 0, "answers": answers})
    done = client.get(law_path("ndps"))
    assert "Learned" in done.text
    assert "First revision" in done.text
    assert "Day 1" in done.text
    assert "product Learned" not in done.text


def test_no_m8_calls_on_production_path():
    routes = (ROOT / "src/constitution_memorizer/playground/routes.py").read_text()
    assert "complete_cloze" not in routes
    assert "next_revision_date" not in routes
    assert "advance_interval" not in routes
    assert "INTERVAL_LADDER" not in routes
    learning = ROOT / "src/constitution_memorizer/playground/learning"
    blob = "\n".join(path.read_text() for path in learning.glob("*.py"))
    assert "from constitution_memorizer.learning" not in blob
    assert "from constitution_memorizer.web.quiz" not in blob
    assert "unit_modes_seen" not in blob
    assert "ReminderEngine" not in blob


def test_one_act_hydration_on_mode_get(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from constitution_memorizer.web import bare_acts
    from constitution_memorizer.web.bare_acts import clear_bare_act_cache

    client = _client(tmp_path)
    _add_and_select(client, "bns", "1")
    hydrated: list[str] = []
    real = bare_acts.get_bare_act

    def wrapped(slug, *args, **kwargs):
        hydrated.append(str(slug))
        return real(slug, *args, **kwargs)

    monkeypatch.setattr(bare_acts, "get_bare_act", wrapped)
    clear_bare_act_cache()
    hydrated.clear()
    page = client.get(learn_path("bns", "1", "type"))
    assert page.status_code == 200
    assert "bns" in hydrated
    assert "ndps" not in hydrated
    assert "bnss" not in hydrated


def test_guest_and_free_still_gated(tmp_path: Path):
    from tests.test_entitlement_m3b import _assert_subscribe_gate, _authed_client, _guest_client

    guest = _guest_client(tmp_path)
    login = guest.get(learn_path("ndps", "1", "type"), follow_redirects=False)
    assert login.status_code == 303
    assert "/login" in login.headers["location"]
    free, _repo = _authed_client(tmp_path)
    gated = free.get(learn_path("ndps", "1", "type"), follow_redirects=False)
    _assert_subscribe_gate(gated)


def test_pending_active_roster_can_use_all_modes(tmp_path: Path):
    client = _authed_client(tmp_path)
    sub = _subscribe(client)
    _confirm_add(client, "ndps")
    client.post(
        sections_path("ndps"),
        data={**_csrf(client), "section": "1"},
        follow_redirects=False,
    )
    client.app.state.subscriptions.update_subscription_state(
        USER, sub.id, status="pending"
    )
    for mode in MODES:
        page = client.get(learn_path("ndps", "1", mode))
        assert page.status_code == 200
    done = _complete(client, "ndps", "1", "type")
    assert done.status_code == 200
    assert done.json()["ok"] is True


def test_start_does_not_increment_attempt(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    started = _json_post(client, learn_start_path("ndps", "1", "type"), {})
    assert started.status_code == 200
    assert started.json()["status"] == "in_progress"
    assert started.json()["attempt_count"] == 0
    loc = section_locator("ndps", "1").value
    row = client.app.state.playground.get_mode_progress(
        LOCAL_USER_ID, "ndps", loc, "type"
    )
    assert row is not None
    assert row.status == "in_progress"
    assert row.attempt_count == 0


def test_constitution_learn_modes_untouched():
    from constitution_memorizer.progress.repository import LEARN_MODES

    assert LEARN_MODES == PLAYGROUND_LEARN_MODES
    playground_quiz = (
        ROOT / "src/constitution_memorizer/playground/learning/test.py"
    ).read_text()
    assert "from constitution_memorizer.learning" not in playground_quiz
    assert "from constitution_memorizer.web.quiz" not in playground_quiz
    assert "def build_quiz" in (
        ROOT / "src/constitution_memorizer/web/quiz.py"
    ).read_text()
