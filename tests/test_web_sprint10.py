"""Sprint 10 Learn Read anatomy tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.service import kind_badge_label, unit_crumb

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
    )
    return TestClient(app)


def test_kind_badge_and_crumb_helpers():
    clause = LearningUnit(
        id="c1",
        type=LearningUnitType.CLAUSE,
        display_title="Article 15(1)",
        title="Prohibition of discrimination",
        text="(1) The State shall not discriminate.",
        article_number="15",
        tags=["Part III"],
        estimated_learning_time=30,
    )
    assert kind_badge_label(clause) == "Clause"
    crumb = unit_crumb(clause)
    assert crumb == "Part III · Article 15"
    assert "Prohibition of discrimination" not in crumb


def test_learn_read_anatomy(client: TestClient):
    response = client.get("/learn/clause-1")
    assert response.status_code == 200
    assert "Session" in response.text
    assert "session-track" in response.text
    assert "0 of " in response.text
    assert "kind-badge" in response.text
    assert "Clause" in response.text
    assert "mode-tab is-active" in response.text
    assert "Read" in response.text
    assert "5 methods left" in response.text
    assert "btn-done-locked" in response.text
    assert "Reset unit" in response.text
    assert "Bare Act wording, verbatim" in response.text
    assert "LearningUnitType" not in response.text
    assert "btn-green" not in response.text
    assert "Again tomorrow" in response.text
    assert 'action="/learn/clause-1/again"' in response.text
    assert "learn-actions" in response.text
    assert "label-short" not in response.text
