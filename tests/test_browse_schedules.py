"""Constitution Schedules appear on Browse after Parts I–XXII."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.browse import (
    browse_schedule_cards,
    build_schedule_view,
    load_browse_schedules_seed,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
FULL_UNITS = Path(__file__).resolve().parents[1] / "data" / "output" / "learning_units.json"


def test_browse_schedules_seed_has_all_twelve():
    seed = load_browse_schedules_seed()
    slugs = [row["slug"] for row in seed]
    assert slugs == [
        "first",
        "second",
        "third",
        "fourth",
        "fifth",
        "sixth",
        "seventh",
        "eighth",
        "ninth",
        "tenth",
        "eleventh",
        "twelfth",
    ]
    assert seed[0]["roman"] == "I"
    assert seed[-1]["roman"] == "XII"


def test_browse_schedule_cards_from_full_units(tmp_path: Path):
    if not FULL_UNITS.exists():
        pytest.skip("full learning_units.json missing")
    engine = ReminderEngine.from_paths(tmp_path / "p.db", FULL_UNITS)
    cards = browse_schedule_cards(engine)
    assert len(cards) == 12
    assert cards[0].href == "/browse/schedule/first"
    assert cards[6].slug == "seventh"
    assert cards[6].unit_count >= 1


def test_browse_index_lists_schedules(tmp_path: Path):
    if not FULL_UNITS.exists():
        pytest.skip("full learning_units.json missing")
    client = TestClient(
        create_app(
            units_path=FULL_UNITS,
            db_path=tmp_path / "progress.db",
            reviewed_path=tmp_path / "missing-reviewed.json",
        )
    )
    html = client.get("/browse").text
    assert "The Schedules" in html
    assert "Schedule I" in html
    assert "Schedule XII" in html
    assert 'href="/browse/schedule/first"' in html
    assert 'href="/browse/schedule/twelfth"' in html
    assert "The States and the Union territories" in html


def test_browse_schedule_page_first_and_seventh(tmp_path: Path):
    if not FULL_UNITS.exists():
        pytest.skip("full learning_units.json missing")
    client = TestClient(
        create_app(
            units_path=FULL_UNITS,
            db_path=tmp_path / "progress.db",
            reviewed_path=tmp_path / "missing-reviewed.json",
        )
    )
    first = client.get("/browse/schedule/first")
    assert first.status_code == 200
    assert "Schedule I" in first.text
    assert "Andhra Pradesh" in first.text
    assert 'href="/browse/schedule/second"' in first.text
    css = client.get("/static/mobile.css").text
    hide = css.split(".browse-schedule-page .eyebrow-desktop", 1)[1].split("}", 1)[0]
    assert "display: none" in hide

    seventh = client.get("/browse/schedule/seventh")
    assert seventh.status_code == 200
    assert "Union List" in seventh.text
    assert "Defence of India" in seventh.text


def test_unknown_schedule_is_404(tmp_path: Path):
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
        )
    )
    assert client.get("/browse/schedule/thirteenth").status_code == 404


def test_build_schedule_view_skips_heading_only_units(tmp_path: Path):
    if not FULL_UNITS.exists():
        pytest.skip("full learning_units.json missing")
    engine = ReminderEngine.from_paths(tmp_path / "p.db", FULL_UNITS)
    first = build_schedule_view(engine, "first")
    assert first is not None
    assert first.tables_tab == "states"
    assert first.table_payload is not None
    assert "PART I" not in first.full_text
    tenth = build_schedule_view(engine, "tenth")
    assert tenth is not None
    assert "disqualification" in tenth.full_text.lower()
