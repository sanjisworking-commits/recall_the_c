"""Sprint 20 — Progress mastery map."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.schemas import ConstitutionDocument
from constitution_memorizer.utils.json_io import read_json
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.progress_stats import (
    article_mastery_state,
    path_units_for_article,
    progress_dashboard,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
MINI_REVIEWED = Path(__file__).parent / "fixtures" / "learning" / "mini_reviewed.json"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "progress.db"


@pytest.fixture
def engine(db_path: Path) -> ReminderEngine:
    return ReminderEngine.from_paths(db_path, MINI_UNITS)


@pytest.fixture
def client(db_path: Path) -> TestClient:
    app = create_app(
        units_path=MINI_UNITS,
        db_path=db_path,
        reviewed_path=MINI_REVIEWED,
    )
    return TestClient(app)


def test_progress_page_without_reviewed_uses_part_seed(tmp_path: Path):
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
            reviewed_path=tmp_path / "missing-reviewed.json",
        )
    )
    html = client.get("/progress").text
    assert "Part III" in html
    assert "Learning units" not in html
    assert "mastery-map" in html


def test_progress_page_has_stat_tiles_and_mastery_map(client: TestClient):
    response = client.get("/progress")
    assert response.status_code == 200
    html = response.text
    assert "Progress" in html
    assert "Mastery map" in html
    assert "Tracked articles" in html
    assert "progress-stat-grid" in html
    assert "Tracked units" in html
    assert "Completed" in html
    assert "Mastered" in html
    assert "Remaining" in html
    assert "mastery-map" in html
    assert "Part III" in html
    assert "Fundamental Rights" in html
    assert "mastery-cell" in html
    # Fresh progress continues into Art 20 → tooltip is "due"; unstarted is "new".
    assert (
        'title="Article 20 · due"' in html or 'title="Article 20 · new"' in html
    )
    assert "/static/styles.css?" in html


def test_progress_css_mastery_cell_states(client: TestClient):
    css = client.get("/static/styles.css?v=main38")
    assert css.status_code == 200
    text = css.text
    assert ".mastery-cell.is-new" in text
    assert ".mastery-cell.is-learning" in text
    assert ".mastery-cell.is-review" in text
    assert ".mastery-cell.is-mastered" in text
    assert ".mastery-cell.is-due" in text
    assert "width: 16px" in text
    assert ".tracked-progress-bar" in text


def test_mastery_map_article_20_is_clickable(client: TestClient):
    html = client.get("/progress").text
    assert 'title="Article 20 · due"' in html or 'title="Article 20 · new"' in html
    assert (
        "mastery-cell is-new is-tracked" in html
        or "mastery-cell is-due is-tracked" in html
    )
    assert 'href="/learn/' in html


def test_partial_completion_is_review_or_due(engine: ReminderEngine):
    today = date(2026, 7, 20)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today)
    # Partial without continue pointer → review
    assert (
        article_mastery_state(engine, "20", today=today, continue_id=None) == "review"
    )
    # Continue pointer in article → due
    assert (
        article_mastery_state(engine, "20", today=today, continue_id="clause-2")
        == "due"
    )


def test_tracked_row_tags_and_bar(client: TestClient, engine: ReminderEngine):
    today = date(2026, 7, 20)
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today)
    reviewed = ConstitutionDocument.model_validate(read_json(MINI_REVIEWED))
    dash = progress_dashboard(engine, reviewed=reviewed, today=today)
    row20 = next(r for r in dash["tracked_rows"] if r.article_number == "20")
    assert row20.completed >= 1
    assert row20.bar_percent > 0
    assert row20.tag in {"", "due", "choice pending", "mastered"}
    assert row20.tag not in {"learning", "review"}

    html = client.get("/progress").text
    assert "tracked-article-row" in html
    assert "tracked-progress-bar" in html
    assert "Article 20" in html


def test_all_complete_on_first_rung_is_learning(engine: ReminderEngine):
    today = date(2026, 7, 20)
    engine.set_split_preference("clause-2", "whole")
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today)
    engine.mark_all_modes_seen("clause-2")
    engine.mark_done("clause-2", as_of=today)
    state = article_mastery_state(engine, "20", today=today, continue_id=None)
    assert state == "learning"


def test_all_complete_past_first_rung_is_mastered(engine: ReminderEngine):
    today = date(2026, 7, 20)
    engine.mark_all_modes_seen("article-end")
    engine.mark_done("article-end", as_of=today)  # interval 1 → learning
    assert (
        article_mastery_state(engine, "21", today=today, continue_id=None) == "learning"
    )
    engine.mark_all_modes_seen("article-end")
    engine.mark_done("article-end", as_of=today)  # advances to interval 3
    assert (
        article_mastery_state(engine, "21", today=today, continue_id=None) == "mastered"
    )


def test_fresh_account_has_no_tracked_article_rows(engine: ReminderEngine):
    """Unset split choice must not list untouched articles as tracked."""
    today = date(2026, 7, 20)
    dash = progress_dashboard(engine, reviewed=None, today=today)
    assert dash["tracked_rows"] == []


def test_mastery_map_uses_seed_parts_when_reviewed_missing(engine: ReminderEngine):
    today = date(2026, 7, 20)
    dash = progress_dashboard(engine, reviewed=None, today=today)
    romans = {row.part_number for row in dash["parts_map"]}
    # Mini fixture only has Articles 20–21 → Part III from the seed.
    assert "—" not in romans
    assert "III" in romans
    part_iii = next(r for r in dash["parts_map"] if r.part_number == "III")
    assert part_iii.part_title
    assert {c.article_number for c in part_iii.cells} >= {"20", "21"}


def test_choice_pending_tag(engine: ReminderEngine):
    today = date(2026, 7, 20)
    # Touch article 20 without choosing split on clause-2
    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1", as_of=today)
    reviewed = ConstitutionDocument.model_validate(read_json(MINI_REVIEWED))
    dash = progress_dashboard(engine, reviewed=reviewed, today=today)
    row20 = next(r for r in dash["tracked_rows"] if r.article_number == "20")
    assert row20.pending_choice is True
    assert row20.tag == "choice pending"


def test_split_preference_still_affects_required_counts(engine: ReminderEngine):
    engine.set_split_preference("clause-2", "letters")
    required, pending = path_units_for_article(engine, "20")
    assert pending is False
    assert [u.id for u in required] == ["clause-1", "clause-2-a", "clause-2-b"]
