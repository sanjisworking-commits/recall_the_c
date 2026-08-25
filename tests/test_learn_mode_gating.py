"""Gated learn-mode completion: partition invariants, /seen vs /quiz, stale cycles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.progress.repository import (
    AUTO_SEEN_MODES_SET,
    GATED_MODES_SET,
    LEARN_MODES_SET,
    ProgressRepository,
)
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID
from constitution_memorizer.web import entitlements as ent
from constitution_memorizer.web.app import create_app

from tests.quiz_helpers import (
    complete_all_modes,
    correct_quiz_answers,
    submit_quiz,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
UID = str(LOCAL_USER_ID)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    return TestClient(app)


@pytest.fixture
def repo(tmp_path: Path) -> ProgressRepository:
    return ProgressRepository(open_progress_db(tmp_path / "progress.db"))


# --------------------------------------------------------------------------- #
# Partition invariants                                                         #
# --------------------------------------------------------------------------- #
def test_mode_partition_is_exhaustive_and_disjoint():
    assert AUTO_SEEN_MODES_SET | GATED_MODES_SET == LEARN_MODES_SET
    assert AUTO_SEEN_MODES_SET & GATED_MODES_SET == set()
    assert AUTO_SEEN_MODES_SET == {"read"}
    assert GATED_MODES_SET == {"cloze", "letters", "type", "recite", "test"}
    assert set(ent.OPEN_MODES) | set(ent.SUBSCRIBER_ONLY_MODES) == LEARN_MODES_SET
    assert set(ent.ALL_MODES) == LEARN_MODES_SET


def test_js_contracts_letters_speech_and_quiz_only_test():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "constitution_memorizer"
        / "web"
        / "static"
        / "app.js"
    ).read_text(encoding="utf-8")
    assert 'AUTO_SEEN_MODES = new Set(["read"])' in source
    assert 'markModeAttempted("letters")' in source
    assert 'markModeAttempted("test")' not in source
    assert "webkitSpeechRecognition" not in source
    assert "SpeechRecognition" not in source
    assert "RecallSpeech" in source
    assert 'mode: "recite"' in source
    assert "[data-recite-toggle]" in source
    assert "[data-recite-peek]" in source
    assert "[data-recite-fallback]" in source
    assert "recite.reset()" in source
    assert "abortForServiceFailure" in source
    # Renamed and hoisted: Type skips clause markers using the same rule.
    assert "isStructuralToken" in source


def test_test_visit_does_not_mark_without_quiz(
    client: TestClient, repo: ProgressRepository
):
    client.get("/learn/clause-1?mode=test")
    assert "test" not in repo.modes_seen(UID, "clause-1")
    client.get("/learn/clause-1")  # read
    client.get("/learn/clause-1?mode=letters")
    for mode in ("cloze", "letters", "type", "recite"):
        client.post("/learn/clause-1/seen", data={"mode": mode})
    submit_quiz(client, MINI_UNITS, "clause-1")
    resp = client.post("/learn/clause-1/done", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/learn/")
    progress = repo.get_progress(UID, "clause-1")
    assert progress is not None and progress.times_completed == 1


def test_gated_mode_gets_mark_nothing(client: TestClient, repo: ProgressRepository):
    for mode in ("cloze", "letters", "type", "recite", "test"):
        client.get(f"/learn/clause-1?mode={mode}")
    assert repo.modes_seen(UID, "clause-1") == set()
    client.get("/learn/clause-1?mode=read")
    assert repo.modes_seen(UID, "clause-1") == {"read"}


# --------------------------------------------------------------------------- #
# /seen contract                                                               #
# --------------------------------------------------------------------------- #
def test_seen_accepts_client_trusted_modes(client: TestClient):
    for mode in ("cloze", "letters", "type", "recite"):
        resp = client.post("/learn/clause-1/seen", data={"mode": mode})
        assert resp.status_code == 200
        assert mode in resp.json()["seen"]


def test_seen_rejects_test_with_quiz_required(client: TestClient, repo: ProgressRepository):
    resp = client.post("/learn/clause-1/seen", data={"mode": "test"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "quiz_required"
    assert "test" not in repo.modes_seen(UID, "clause-1")


def test_seen_rejects_legacy_card(client: TestClient, repo: ProgressRepository):
    resp = client.post("/learn/clause-1/seen", data={"mode": "card"})
    assert resp.status_code == 400
    assert repo.modes_seen(UID, "clause-1") == set()


# --------------------------------------------------------------------------- #
# /quiz contract                                                               #
# --------------------------------------------------------------------------- #
def test_quiz_grades_marks_and_returns_done_payload(client: TestClient):
    for mode in ("read", "cloze", "letters", "type", "recite"):
        client.post("/learn/clause-1/seen", data={"mode": mode})
    resp = submit_quiz(client, MINI_UNITS, "clause-1")
    data = resp.json()
    assert data["ok"] is True
    assert data["persisted"] is True
    assert data["score"]["correct"] == data["score"]["total"]
    assert all(r["correct"] for r in data["results"])
    assert "test" in data["seen"]
    assert data["done"]["unlocked"] is True


def test_all_wrong_quiz_still_marks_seen(client: TestClient, repo: ProgressRepository):
    answers = correct_quiz_answers(MINI_UNITS, "clause-1", cycle=0)
    wrong = [
        (0 if a != 0 else 1) if isinstance(a, int) else "definitelywrongword"
        for a in answers
    ]
    resp = client.post(
        "/learn/clause-1/quiz", json={"cycle": 0, "answers": wrong}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["score"]["correct"] == 0
    assert "test" in repo.modes_seen(UID, "clause-1")
    assert data["results"][0]["expected"]  # correct answers are revealed


def test_partial_answers_rejected(client: TestClient, repo: ProgressRepository):
    answers = correct_quiz_answers(MINI_UNITS, "clause-1", cycle=0)
    resp = client.post(
        "/learn/clause-1/quiz",
        json={"cycle": 0, "answers": answers[:-1] + [None]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "answers_incomplete"
    resp = client.post(
        "/learn/clause-1/quiz", json={"cycle": 0, "answers": answers[:-1]}
    )
    assert resp.status_code == 400
    assert repo.modes_seen(UID, "clause-1") == set()


def test_malformed_answer_shapes_rejected(
    client: TestClient, repo: ProgressRepository
):
    answers = correct_quiz_answers(MINI_UNITS, "clause-1", cycle=0)
    mcq_index = next(i for i, a in enumerate(answers) if isinstance(a, int))
    fill_index = next(i for i, a in enumerate(answers) if isinstance(a, str))

    for bad_mcq in (-1, 999999, True, "zero", {}):
        mutated = list(answers)
        mutated[mcq_index] = bad_mcq
        resp = client.post(
            "/learn/clause-1/quiz", json={"cycle": 0, "answers": mutated}
        )
        assert resp.status_code == 400, bad_mcq

    mutated = list(answers)
    mutated[fill_index] = 42
    resp = client.post(
        "/learn/clause-1/quiz", json={"cycle": 0, "answers": mutated}
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "answers_invalid"

    resp = client.post("/learn/clause-1/quiz", json={"answers": answers})
    assert resp.status_code == 400  # missing cycle → invalid payload
    assert repo.modes_seen(UID, "clause-1") == set()


def test_duplicate_submission_is_idempotent(client: TestClient):
    first = submit_quiz(client, MINI_UNITS, "clause-1", cycle=0)
    second = submit_quiz(client, MINI_UNITS, "clause-1", cycle=0)
    assert first.status_code == second.status_code == 200
    assert second.json()["seen"].count("test") == 1


def test_stale_cycle_submission_rejected(
    client: TestClient, repo: ProgressRepository
):
    # Complete cycle 0 end-to-end.
    complete_all_modes(client, MINI_UNITS, "clause-1")
    resp = client.post("/learn/clause-1/done", follow_redirects=False)
    assert resp.status_code == 303
    # Done cleared the mode rows and advanced times_completed to 1.
    assert repo.modes_seen(UID, "clause-1") == set()

    # A stale tab submits the cycle-0 quiz — refused, nothing marked.
    resp = client.post(
        "/learn/clause-1/quiz",
        json={"cycle": 0, "answers": correct_quiz_answers(MINI_UNITS, "clause-1", 0)},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "stale_quiz"
    assert body["current_cycle"] == 1
    assert "test" not in repo.modes_seen(UID, "clause-1")

    # The new cycle serves a different quiz and accepts its own answers.
    assert correct_quiz_answers(MINI_UNITS, "clause-1", 0) != correct_quiz_answers(
        MINI_UNITS, "clause-1", 1
    )
    resp = submit_quiz(client, MINI_UNITS, "clause-1", cycle=1)
    assert resp.status_code == 200
    assert "test" in repo.modes_seen(UID, "clause-1")


# --------------------------------------------------------------------------- #
# Impossible modes are omitted from requirements, never fake-completed         #
# --------------------------------------------------------------------------- #
def _degenerate_client(tmp_path: Path) -> TestClient:
    """One unit whose text can produce neither quiz nor cloze blanks."""
    doc = {
        "schema_version": "1.0.0",
        "source_document": "fixture",
        "unit_count": 1,
        "units": [
            {
                "id": "tiny-1",
                "type": "PART_OVERVIEW",
                "display_title": "Part I",
                "text": "a of it",
                "estimated_learning_time": 30,
                "revision_order": 0,
            }
        ],
    }
    units_path = tmp_path / "degenerate_units.json"
    units_path.write_text(json.dumps(doc), encoding="utf-8")
    return TestClient(
        create_app(units_path=units_path, db_path=tmp_path / "progress.db")
    )


def test_impossible_quiz_and_cloze_omitted_from_required(tmp_path: Path):
    client = _degenerate_client(tmp_path)
    repo = ProgressRepository(open_progress_db(tmp_path / "progress.db"))

    page = client.get("/learn/tiny-1?mode=test").text
    assert "Nothing to quiz here yet" in page
    assert "data-quiz-form" not in page
    assert 'data-required-modes="read,letters,type,recite"' in page
    # Visiting Test no longer checks it; it is omitted from required, so Done
    # does not need a quiz.
    assert repo.modes_seen(UID, "tiny-1") == set()
    client.get("/learn/tiny-1?mode=cloze")
    assert repo.modes_seen(UID, "tiny-1") == set()
    cloze_page = client.get("/learn/tiny-1?mode=cloze").text
    assert "No cloze exercise available for this text." in cloze_page

    # /quiz refuses to grade what cannot be generated.
    resp = client.post("/learn/tiny-1/quiz", json={"cycle": 0, "answers": []})
    assert resp.status_code == 400
    assert resp.json()["error"] == "no_quiz"

    # Done stays reachable with the remaining modes.
    client.get("/learn/tiny-1?mode=read")
    for mode in ("letters", "type", "recite"):
        client.post("/learn/tiny-1/seen", data={"mode": mode})
    resp = client.post("/learn/tiny-1/done", follow_redirects=False)
    assert resp.status_code == 303
    progress = repo.get_progress(UID, "tiny-1")
    assert progress is not None and progress.times_completed == 1


# --------------------------------------------------------------------------- #
# Guest Done gating                                                            #
# --------------------------------------------------------------------------- #
def _guest_client(tmp_path: Path) -> TestClient:
    from constitution_memorizer.auth.fake_provider import FakeAuthProvider
    from constitution_memorizer.auth.sessions import InMemorySessionStore
    from constitution_memorizer.multiuser.settings import (
        MultiUserSettings,
        clear_settings_cache,
    )

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


def test_guest_done_starts_locked(tmp_path: Path):
    client = _guest_client(tmp_path)
    html = client.get("/learn/clause-1").text
    assert "btn-done-locked" in html
    assert "methods left" in html
    assert 'aria-disabled="true"' in html
    assert 'data-done-unlocked="false"' in html
    # Guest Done POST still routes to sign-in, unchanged.
    resp = client.post("/learn/clause-1/done", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")


def test_guest_quiz_grades_without_persisting(tmp_path: Path):
    client = _guest_client(tmp_path)
    resp = submit_quiz(client, MINI_UNITS, "clause-1", cycle=0)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["persisted"] is False
    assert "seen" not in data
