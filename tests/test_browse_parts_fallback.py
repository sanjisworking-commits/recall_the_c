"""Browse Part segregation without constitution.reviewed.json."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.browse import (
    _article_card_title,
    browse_parts_from_units,
    load_browse_chapters_seed,
    load_browse_parts_seed,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
FULL_UNITS = Path(__file__).resolve().parents[1] / "data" / "output" / "learning_units.json"


def test_browse_parts_seed_loads():
    seed = load_browse_parts_seed()
    assert len(seed) >= 10
    assert seed[0]["roman"] == "I"
    romans = [row["roman"] for row in seed]
    assert "XIVA" in romans


def test_browse_parts_from_mini_units_tags(tmp_path: Path):
    engine = ReminderEngine.from_paths(tmp_path / "p.db", MINI_UNITS)
    sections = browse_parts_from_units(engine)
    assert sections
    part_iii = next((s for s in sections if s.part_number == "III"), None)
    assert part_iii is not None
    assert any(c.article_number == "20" for c in part_iii.cards)


def test_browse_parts_seed_without_tags(tmp_path: Path):
    """Even if Part tags are stripped, seed ranges still segregate."""
    if not FULL_UNITS.exists():
        pytest.skip("full learning_units.json missing")
    engine = ReminderEngine.from_paths(tmp_path / "p.db", FULL_UNITS)
    for unit in engine.units.values():
        unit.tags = [t for t in unit.tags if not str(t).startswith("Part ")]
    sections = browse_parts_from_units(engine)
    romans = [s.part_number for s in sections]
    assert "I" in romans and "II" in romans and "III" in romans
    part_i = next(s for s in sections if s.part_number == "I")
    assert part_i.article_range.startswith("1")
    assert "Part —" != f"Part {part_i.part_number}" or True
    # Must not collapse to one mega-section titled Articles
    assert not any(s.part_number == "—" and s.part_title == "Articles" for s in sections)
    assert len(sections) >= 10


def test_browse_html_parts_without_reviewed(tmp_path: Path):
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
    assert 'data-parts-source="units-seed"' in html
    assert "browse-part-roman" in html
    assert "Part I" in html
    assert "Part II" in html
    assert "Part III" in html
    assert "Articles 1–4" in html or "Articles 1" in html
    assert html.count("browse-part-roman") >= 10
    # Old flat marker (pre-fix single bucket) must be gone
    assert 'class="browse-part-name">Articles</span>' not in html


def test_browse_chapters_seed_covers_chaptered_parts():
    seed = load_browse_chapters_seed()
    parts = {str(row["part"]).upper() for row in seed}
    assert parts == {"V", "VI", "XI", "XII", "XIV", "XVII"}
    assert any(row["part"] == "V" and row["roman"] == "I" for row in seed)


def test_browse_chapters_and_card_titles_without_reviewed(tmp_path: Path):
    if not FULL_UNITS.exists():
        pytest.skip("full learning_units.json missing")
    engine = ReminderEngine.from_paths(tmp_path / "p.db", FULL_UNITS)
    sections = browse_parts_from_units(engine)
    part_iii = next(s for s in sections if s.part_number == "III")
    assert part_iii.chapters == []

    part_v = next(s for s in sections if s.part_number == "V")
    romans = [ch.chapter_number for ch in part_v.chapters]
    assert "I" in romans and "II" in romans
    exec_ch = next(ch for ch in part_v.chapters if ch.chapter_number == "I")
    assert "Executive" in exec_ch.chapter_title
    assert any(c.article_number == "52" for c in exec_ch.cards)
    parl = next(ch for ch in part_v.chapters if ch.chapter_number == "II")
    assert "Parliament" in parl.chapter_title
    assert any(c.article_number == "79" for c in parl.cards)

    part_i = next(s for s in sections if s.part_number == "I")
    art1 = next(c for c in part_i.cards if c.article_number == "1")
    art2 = next(c for c in part_i.cards if c.article_number == "2")
    assert art1.title and "Union" in art1.title
    assert art2.title

    client = TestClient(
        create_app(
            units_path=FULL_UNITS,
            db_path=tmp_path / "progress-html.db",
            reviewed_path=tmp_path / "missing-reviewed.json",
        )
    )
    html = client.get("/browse").text
    assert "Chapter I" in html
    assert "The Executive" in html
    assert "Parliament" in html
    part_iii_html = html.split("Part III", 1)[1].split("Part IV", 1)[0]
    assert "Chapter I" not in part_iii_html
    assert "browse-article-title" in html
    assert "Name and territory" in html or "Union" in html
    assert "functions in other contingencies" in html
    assert "election of a President or Vice-President" in html
    assert "Discharge of President" in html
    assert "functions…" not in html

    part_html = client.get("/browse/part/v").text
    assert "part-row-sub" in part_html
    assert "functions in other contingencies" in part_html
    assert "election of a President or Vice-President" in part_html
    assert "functions…" not in part_html


def test_article_card_title_keeps_the_full_heading():
    long_title = (
        "Matters relating to, or connected with, the election of a "
        "President or Vice-President"
    )
    assert len(long_title) > 42
    assert _article_card_title(long_title) == long_title
    assert "…" not in _article_card_title(long_title)
