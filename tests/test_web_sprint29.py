"""Sprint 29 — Tables page + Browse Parts + Home articles-first."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.tables_data import list_table_tabs, load_table_tab

ROOT = Path(__file__).resolve().parents[1]
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
MINI_REVIEWED = Path(__file__).parent / "fixtures" / "learning" / "mini_reviewed.json"
REVIEWED = ROOT / "data" / "output" / "constitution.reviewed.json"
UNITS = ROOT / "data" / "output" / "learning_units.json"
AMENDMENTS = ROOT / "data" / "reference" / "amendments.seed.json"


@pytest.fixture
def mini_client(tmp_path: Path) -> TestClient:
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        reviewed_path=MINI_REVIEWED if MINI_REVIEWED.exists() else None,
    )
    return TestClient(app)


@pytest.fixture
def full_client(tmp_path: Path) -> TestClient:
    if not REVIEWED.exists() or not UNITS.exists():
        pytest.skip("full corpus missing")
    app = create_app(
        units_path=UNITS,
        db_path=tmp_path / "progress.db",
        reviewed_path=REVIEWED,
        amendments_path=AMENDMENTS,
    )
    return TestClient(app)


def test_table_tabs_index_has_ten():
    tabs = list_table_tabs()
    assert len(tabs) == 10
    assert tabs[0].id == "parts"
    assert any(t.id == "languages" and t.label == "8th Schedule" for t in tabs)
    payload = load_table_tab("parts")
    assert payload is not None
    assert payload.title == "Parts of the Constitution"
    assert any(row[0] == "VII" for block in payload.tables for row in block.rows)


def test_eighth_schedule_tab_renamed():
    payload = load_table_tab("languages")
    assert payload is not None
    assert payload.label == "8th Schedule"
    assert payload.title == "Eighth Schedule"
    assert any("Assamese" in row for block in payload.tables for row in block.rows)


def test_seventh_schedule_three_lists():
    payload = load_table_tab("seventh")
    assert payload is not None
    assert len(payload.tables) == 3
    labels = [t.label for t in payload.tables]
    assert labels[0] and "Union" in labels[0]
    assert labels[1] and "State" in labels[1]
    assert labels[2] and "Concurrent" in labels[2]
    assert len(payload.tables[0].rows) >= 90
    assert len(payload.tables[1].rows) >= 60
    assert len(payload.tables[2].rows) >= 45
    assert any(row[0] == "97" for row in payload.tables[0].rows)
    assert any(row[0] == "2A" for row in payload.tables[0].rows)


def test_tables_page_default_parts(mini_client: TestClient):
    html = mini_client.get("/tables").text
    assert "Quick-reference tables" in html
    assert "Parts of the Constitution" in html
    assert "tables-tab is-active" in html or 'class="tables-tab is-active"' in html
    assert "Part VII was repealed" in html
    assert "/static/styles.css?" in html
    assert 'href="/tables"' in html


def test_tables_tab_switch(mini_client: TestClient):
    html = mini_client.get("/tables?tab=writs").text
    assert "Habeas corpus" in html
    assert "Writs" in html


def test_tables_frame_keeps_horizontal_scroll():
    css = (
        Path(__file__).resolve().parents[1]
        / "src/constitution_memorizer/web/static/styles.css"
    ).read_text()
    frame = css.split(".tables-frame {", 1)[1].split("}", 1)[0]
    assert "overflow-x: auto" in frame
    assert "min-width: 560px" in css.split(".tables-grid {", 1)[1].split("}", 1)[0]


def test_home_continue_not_overview(mini_client: TestClient):
    html = mini_client.get("/").text
    assert "part-overview" not in html
    assert "/learn/clause-1" in html


def test_browse_parts_structure(full_client: TestClient):
    html = full_client.get("/browse").text
    assert "The Constitution, Part by Part" in html
    assert "browse-part-roman" in html
    assert "Part III" in html or "Part I" in html
    assert "browse-article-card" in html
    assert "Article 14" in html or "Article 1" in html


def test_browse_tracked_after_progress(full_client: TestClient, tmp_path: Path):
    eng: ReminderEngine = full_client.app.state.engine  # type: ignore[attr-defined]
    # Mark a unit under Art 14 if present
    candidates = [
        u for u in eng.units.values() if (u.article_number or "") == "14" and u.revision_order > 0
    ]
    if not candidates:
        pytest.skip("no art 14 units")
    eng.mark_all_modes_seen(candidates[0].id)
    eng.mark_done(candidates[0].id)
    html = full_client.get("/browse").text
    assert "is-tracked" in html
    assert "Article 14" in html
