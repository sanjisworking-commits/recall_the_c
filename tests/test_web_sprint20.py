"""Sprint 20 — Progress mastery map."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.schemas import Article, ConstitutionDocument, Part
from constitution_memorizer.utils.identifiers import article_sort_key, parse_article_number
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


def test_progress_full_corpus_map_is_split_by_part(tmp_path: Path):
    """Phone Profile showed one Part — grid of Articles 1–395. The map must
    follow Browse: a row per Part, never a single dump bucket."""
    full_units = Path(__file__).resolve().parents[1] / "data" / "output" / "learning_units.json"
    if not full_units.exists():
        pytest.skip("full learning_units.json missing")
    client = TestClient(
        create_app(
            units_path=full_units,
            db_path=tmp_path / "progress.db",
            reviewed_path=tmp_path / "missing-reviewed.json",
        )
    )
    html = client.get("/progress").text
    assert "Part I" in html
    assert "Part III" in html
    assert "Part XXII" in html
    assert "Learning units" not in html
    assert html.count("mastery-row") >= 10
    assert "Part —" not in html
    assert "mastery-row is-extra" in html
    assert "Your map fills in as you learn" in html
    assert "mastery-legend-phone" in html
    assert ">Due</span>" in html
    # Desktop HTML still lists every Part; phone CSS hides .is-extra.
    assert html.count("mastery-row") >= 20


def _dump_reviewed_from_engine(engine: ReminderEngine, part_number: str) -> ConstitutionDocument:
    numbers = sorted(
        {u.article_number for u in engine.units.values() if u.article_number},
        key=article_sort_key,
    )
    articles = []
    for number in numbers:
        parsed = parse_article_number(number)
        articles.append(
            Article(
                id=f"art-{number}",
                article_number=number,
                numeric_component=parsed.numeric_component if parsed else 0,
                suffix=parsed.suffix if parsed else "",
            )
        )
    return ConstitutionDocument(
        parts=[
            Part(
                id="dump",
                part_number=part_number,
                title="Learning units",
                articles=articles,
            )
        ]
    )


def test_progress_parser_dump_reviewed_splits_into_parts(tmp_path: Path):
    """Live Profile showed PART — / Arts 1–395. Both desktop and phone maps
    must still be one row per Part when reviewed JSON is that dump."""
    full_units = Path(__file__).resolve().parents[1] / "data" / "output" / "learning_units.json"
    if not full_units.exists():
        pytest.skip("full learning_units.json missing")
    engine = ReminderEngine.from_paths(tmp_path / "p.db", full_units)
    dump = _dump_reviewed_from_engine(engine, "—")
    dash = progress_dashboard(engine, reviewed=dump, today=date(2026, 8, 31))
    romans = [row.part_number for row in dash["parts_map"]]
    assert "—" not in romans
    assert "I" in romans
    assert "III" in romans
    assert "XXII" in romans
    assert len(romans) >= 10
    assert not any(len(row.cells) > 200 for row in dash["parts_map"])
    part_i = next(row for row in dash["parts_map"] if row.part_number == "I")
    for cell in part_i.cells:
        parsed = parse_article_number(cell.article_number)
        assert parsed is not None
        assert parsed.numeric_component <= 4


def test_progress_named_dump_part_also_splits(tmp_path: Path):
    """A single Part I that actually holds Arts 1–395 is still a dump."""
    full_units = Path(__file__).resolve().parents[1] / "data" / "output" / "learning_units.json"
    if not full_units.exists():
        pytest.skip("full learning_units.json missing")
    engine = ReminderEngine.from_paths(tmp_path / "p.db", full_units)
    dump = _dump_reviewed_from_engine(engine, "I")
    dash = progress_dashboard(engine, reviewed=dump, today=date(2026, 8, 31))
    romans = [row.part_number for row in dash["parts_map"]]
    assert romans.count("I") == 1
    assert "III" in romans
    assert "XXII" in romans
    part_i = next(row for row in dash["parts_map"] if row.part_number == "I")
    assert len(part_i.cells) < 20


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
    assert "rc-profile-stats" in html
    assert "in progress" in html
    assert "day streak" in html
    assert "Part III" in html
    assert "Fundamental Rights" in html
    assert "mastery-cell" in html
    # Fresh progress continues into Art 20 → tooltip is "due"; unstarted is "new".
    assert (
        'title="Article 20 · due"' in html or 'title="Article 20 · new"' in html
    )
    assert "/static/styles.css?" in html


def test_progress_css_mastery_cell_states(client: TestClient):
    css = client.get("/static/styles.css?v=main49")
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
    assert dash["mastered_count"] == 0
    assert dash["daily_goal_streak"] == 0
    assert isinstance(dash["in_progress_count"], int)
    assert isinstance(dash["part_progress"], list)


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
    # Continue pointer is due (not new), so Part III belongs on the phone bars.
    bars = {row.part_number: row for row in dash["part_progress"]}
    assert "III" in bars
    assert bars["III"].total >= 2
    assert 0 < bars["III"].percent <= 100


def test_mastery_map_skips_anonymous_reviewed_part(engine: ReminderEngine):
    """A parser dump bucket titled Part — must not become the Profile map."""
    today = date(2026, 7, 20)
    reviewed = ConstitutionDocument.model_validate(read_json(MINI_REVIEWED))
    junk = reviewed.parts[0].model_copy(
        update={"id": "part-anon", "part_number": "—", "title": "Learning units"}
    )
    reviewed.parts.insert(0, junk)
    dash = progress_dashboard(engine, reviewed=reviewed, today=today)
    romans = [row.part_number for row in dash["parts_map"]]
    assert "—" not in romans
    assert "III" in romans
    assert not any(row.part_title == "Learning units" for row in dash["parts_map"])


def test_mastery_map_anonymous_only_reviewed_uses_seed(engine: ReminderEngine):
    today = date(2026, 7, 20)
    reviewed = ConstitutionDocument.model_validate(read_json(MINI_REVIEWED))
    reviewed.parts[0] = reviewed.parts[0].model_copy(
        update={"part_number": "—", "title": "Learning units"}
    )
    dash = progress_dashboard(engine, reviewed=reviewed, today=today)
    romans = {row.part_number for row in dash["parts_map"]}
    assert "—" not in romans
    assert "III" in romans
    assert not any(row.part_title == "Learning units" for row in dash["parts_map"])


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


def test_phone_compact_map_keeps_starter_parts(engine: ReminderEngine):
    today = date(2026, 7, 20)
    dash = progress_dashboard(engine, reviewed=None, today=today)
    for row in dash["parts_map"]:
        if row.part_number in {"I", "II", "III", "IV"}:
            assert row.compact is True
        elif not row.has_activity:
            assert row.compact is False


def test_recently_mastered_includes_day_and_date_meta(engine: ReminderEngine):
    today = date(2026, 8, 21)
    engine.mark_all_modes_seen("article-end")
    engine.mark_done("article-end", as_of=today)
    engine.mark_all_modes_seen("article-end")
    engine.mark_done("article-end", as_of=today)
    reviewed = ConstitutionDocument.model_validate(read_json(MINI_REVIEWED))
    dash = progress_dashboard(engine, reviewed=reviewed, today=today)
    assert dash["mastered_count"] >= 1
    row = next(r for r in dash["recently_mastered"] if r["article_number"] == "21")
    assert "Day " in row["meta"]
    assert "Aug" in row["meta"]
    assert row["subtitle"].endswith("complete")
    assert row["last_completed"] == today


def test_progress_page_phone_legend_and_gear(client: TestClient):
    html = client.get("/progress").text
    assert "mastery-legend-phone" in html
    assert "M19.4 15" in html
    assert "M10 1.8v2.4" not in html
    assert 'fill="currentColor"' in html
    assert "See all" not in html
    assert "Constitution progress" in html
    assert "rc-part-progress" in html


def test_split_preference_still_affects_required_counts(engine: ReminderEngine):
    engine.set_split_preference("clause-2", "letters")
    required, pending = path_units_for_article(engine, "20")
    assert pending is False
    assert [u.id for u in required] == ["clause-1", "clause-2-a", "clause-2-b"]
