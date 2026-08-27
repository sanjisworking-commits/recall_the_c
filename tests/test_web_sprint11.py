"""Sprint 11 sibling rails and subclause stem tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.service import (
    chip_label,
    done_button_label,
    sibling_chips,
    subclause_stem_text,
)
from constitution_memorizer.progress.scheduler import ReminderEngine

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
    )
    return TestClient(app)


@pytest.fixture
def engine(tmp_path: Path) -> ReminderEngine:
    return ReminderEngine.from_paths(tmp_path / "progress.db", MINI_UNITS)


def test_chip_label_and_done_label():
    clause = LearningUnit(
        id="c",
        type=LearningUnitType.CLAUSE,
        display_title="Article 15(2)",
        text="(2) stem",
        estimated_learning_time=30,
    )
    letter = LearningUnit(
        id="l",
        type=LearningUnitType.SUBCLAUSE,
        display_title="Article 15(2)(a)",
        text="(a) letter",
        estimated_learning_time=15,
        letter_sequence_next="l2",
    )
    assert chip_label(clause) == "(2)"
    assert chip_label(letter) == "(a)"
    assert done_button_label(clause) == "Done — next unit"
    assert done_button_label(letter) == "Done — next letter"


def test_clause_sibling_rail(client: TestClient):
    response = client.get("/learn/clause-1")
    assert response.status_code == 200
    assert "sibling-rail" in response.text
    assert 'aria-label="Clause siblings"' in response.text
    assert "(1)" in response.text
    assert "(3)" in response.text
    assert 'href="/learn/clause-2"' in response.text
    assert "is-current" in response.text
    assert "learn-stem" not in response.text


def test_letter_rail_and_stem(client: TestClient):
    client.post("/learn/clause-2/choose", data={"mode": "letters"})
    response = client.get("/learn/clause-2-a")
    assert response.status_code == 200
    assert "sibling-rail is-letters" in response.text
    assert 'aria-label="Letter sequence"' in response.text
    assert "(a)" in response.text
    assert "(b)" in response.text
    assert 'href="/learn/clause-2-b"' in response.text
    assert "learn-stem" in response.text
    assert "unless-" in response.text
    assert "(a) the accusation" not in response.text.split("learn-stem")[1].split(
        "</p>"
    )[0]
    assert "Done — next letter" not in response.text
    assert "methods left" in response.text


def test_stem_helper_strips_letters(engine: ReminderEngine):
    unit = engine.get_unit("clause-2-a")
    assert unit is not None
    stem = subclause_stem_text(engine, unit)
    assert stem is not None
    assert stem.startswith("(3)")
    assert "(a)" not in stem
    assert "(b)" not in stem


def test_sibling_chips_helper(engine: ReminderEngine):
    clause = engine.get_unit("clause-1")
    assert clause is not None
    chips = sibling_chips(engine, clause)
    assert [c.label for c in chips] == ["(1)", "(3)"]
    assert chips[0].state == "current"
    assert chips[1].state == "idle"

    letter = engine.get_unit("clause-2-a")
    assert letter is not None
    letter_chips = sibling_chips(engine, letter)
    assert [c.label for c in letter_chips] == ["(a)", "(b)"]
