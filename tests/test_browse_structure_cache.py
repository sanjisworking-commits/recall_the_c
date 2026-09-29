"""Phase 6 (request latency): the immutable Browse structure is process-cached.

The reviewed corpus is deploy-time static, so browse_parts_sections must build
the Part/Chapter/title/range skeleton once and reuse it, while still recomputing
the per-user overlay (due / tracked / news) on every request.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.schemas import Article, Chapter, ConstitutionDocument, Part
from constitution_memorizer.web import browse as browse_mod
from constitution_memorizer.web.browse import (
    browse_parts_sections,
    clear_browse_skeleton_cache,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


def _article(number: str, title: str) -> Article:
    return Article(
        id=f"art-{number}",
        article_number=number,
        numeric_component=int("".join(c for c in number if c.isdigit()) or 0),
        title=title,
    )


def _doc() -> ConstitutionDocument:
    return ConstitutionDocument(
        parts=[
            Part(
                id="part-1",
                part_number="I",
                title="The Union",
                articles=[_article("1", "Name and territory"), _article("2", "Admission")],
            ),
            Part(
                id="part-3",
                part_number="III",
                title="Fundamental Rights",
                chapters=[
                    Chapter(
                        id="ch-1",
                        chapter_number="1",
                        title="General",
                        articles=[_article("12", "Definition"), _article("13", "Laws")],
                    )
                ],
            ),
            # Skipped: UNKNOWN part number.
            Part(id="part-x", part_number="UNKNOWN", articles=[_article("99", "x")]),
        ]
    )


@pytest.fixture()
def engine(tmp_path: Path) -> ReminderEngine:
    return ReminderEngine.from_paths(tmp_path / "p.db", MINI_UNITS)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_browse_skeleton_cache()
    yield
    clear_browse_skeleton_cache()


def test_structure_is_built_and_shaped_correctly(engine: ReminderEngine):
    doc = _doc()
    sections = browse_parts_sections(engine, doc, news_articles=set())

    # UNKNOWN part dropped; the two real parts survive in order.
    assert [s.part_number for s in sections] == ["I", "III"]
    part1, part3 = sections
    assert part1.part_title == "The Union"
    assert [c.article_number for c in part1.cards] == ["1", "2"]
    # Part III groups its articles under a chapter, not loose cards.
    assert part3.cards == []
    assert [c.chapter_number for c in part3.chapters] == ["1"]
    assert [c.article_number for c in part3.chapters[0].cards] == ["12", "13"]
    assert part3.chapters[0].chapter_title == "General"


def test_skeleton_built_once_then_reused(engine: ReminderEngine, monkeypatch):
    doc = _doc()
    calls = {"n": 0}
    real = browse_mod._build_reviewed_skeleton

    def counting(reviewed):
        calls["n"] += 1
        return real(reviewed)

    monkeypatch.setattr(browse_mod, "_build_reviewed_skeleton", counting)

    first = browse_parts_sections(engine, doc, news_articles=set())
    second = browse_parts_sections(engine, doc, news_articles=set())

    assert calls["n"] == 1  # second call is a cache hit
    # Structure is identical across calls.
    assert [s.part_number for s in first] == [s.part_number for s in second]
    assert [c.article_number for c in first[0].cards] == [
        c.article_number for c in second[0].cards
    ]


def test_per_user_overlay_is_recomputed_not_frozen(engine: ReminderEngine, monkeypatch):
    doc = _doc()
    calls = {"n": 0}
    real = browse_mod._build_reviewed_skeleton

    def counting(reviewed):
        calls["n"] += 1
        return real(reviewed)

    monkeypatch.setattr(browse_mod, "_build_reviewed_skeleton", counting)

    plain = browse_parts_sections(engine, doc, news_articles=set())
    flagged = browse_parts_sections(engine, doc, news_articles={"1"})

    # Skeleton cached (built once), but the news overlay reflects each request.
    assert calls["n"] == 1
    assert plain[0].cards[0].in_news is False
    assert flagged[0].cards[0].in_news is True
    assert "news" in flagged[0].cards[0].marks


def test_distinct_documents_get_distinct_skeletons(engine: ReminderEngine):
    doc_a = _doc()
    doc_b = ConstitutionDocument(
        parts=[Part(id="p2", part_number="II", title="Citizenship",
                    articles=[_article("5", "Citizenship")])]
    )
    a = browse_parts_sections(engine, doc_a, news_articles=set())
    b = browse_parts_sections(engine, doc_b, news_articles=set())
    assert [s.part_number for s in a] == ["I", "III"]
    assert [s.part_number for s in b] == ["II"]
