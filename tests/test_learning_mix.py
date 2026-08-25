"""Guided-random learning mix: eligibility, seeding, and fallbacks."""

from __future__ import annotations

import random
from pathlib import Path

from constitution_memorizer.learning.schemas import LearningUnit, LearningUnitType
from constitution_memorizer.progress.mix_selector import (
    eligible_new_units,
    load_relationships,
    select_learning_mix,
)
from constitution_memorizer.progress.scheduler import ReminderEngine


def _clause(n: int, article: str) -> LearningUnit:
    return LearningUnit(
        id=f"u-{n}",
        type=LearningUnitType.CLAUSE,
        article_number=article,
        display_title=f"Article {article}",
        text=f"Clause text {n} " * 8,
        estimated_learning_time=45,
        revision_order=n,
        tags=["Part III"],
    )


def _engine(tmp_path: Path) -> ReminderEngine:
    articles = (
        ["14", "15", "16", "17", "18"] * 2
        + ["19", "20", "21", "22"] * 2
        + ["32", "72", "123"]
    )
    units = [_clause(i + 1, articles[i]) for i in range(len(articles))]
    units.append(
        LearningUnit(
            id="overview",
            type=LearningUnitType.PART_OVERVIEW,
            display_title="Part III overview",
            text="Overview",
            estimated_learning_time=30,
            revision_order=0,
            tags=["Part III"],
        )
    )
    return ReminderEngine.from_units(tmp_path / "progress.db", units)


def test_eligible_excludes_overview_completed_and_review(tmp_path: Path):
    engine = _engine(tmp_path)
    ids = {unit.id for unit in eligible_new_units(engine)}
    assert "overview" not in ids
    engine.mark_all_modes_seen("u-1")
    engine.mark_done("u-1")
    ids_after = {unit.id for unit in eligible_new_units(engine)}
    assert "u-1" not in ids_after
    assert len(ids_after) == len(ids) - 1


def test_select_learning_mix_is_seeded(tmp_path: Path):
    engine = _engine(tmp_path)
    first = [u.id for u in select_learning_mix(engine, 5, rng=random.Random(11))]
    second = [u.id for u in select_learning_mix(engine, 5, rng=random.Random(11))]
    other = [u.id for u in select_learning_mix(engine, 5, rng=random.Random(99))]
    assert first == second
    assert len(first) == 5
    assert len(set(first)) == 5
    assert other != first or len(set(other) | set(first)) >= 5


def test_mix_falls_back_when_a_band_is_thin(tmp_path: Path):
    engine = ReminderEngine.from_units(
        tmp_path / "progress.db",
        [_clause(i, str(400 + i)) for i in range(1, 8)],
    )
    picked = select_learning_mix(engine, 7, rng=random.Random(3))
    assert len(picked) == 7
    assert {u.id for u in picked} == {f"u-{i}" for i in range(1, 8)}


def test_load_relationships_reads_repo_reference():
    data = load_relationships()
    themes = data.get("themes") or []
    pairs = data.get("pairs") or []
    assert themes
    assert pairs
    theme_articles = {
        article
        for theme in themes
        for article in theme.get("article_numbers") or []
    }
    pair_articles = {
        article for pair in pairs for article in pair.get("articles") or []
    }
    assert "32" in theme_articles and "226" in theme_articles
    assert "32" in pair_articles and "226" in pair_articles
    labels = " ".join(
        str(theme.get("id") or "") + " " + str(theme.get("label") or "")
        for theme in themes
    )
    assert "remedies" in labels.lower() or "14" in theme_articles
