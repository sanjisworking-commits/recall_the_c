"""Restore Art 70's Bare Act sentence; keep Art 71's four clauses distinct."""

from __future__ import annotations

import json
from pathlib import Path

from constitution_memorizer.corrections.apply_corrections import (
    apply_corrections,
    load_corrections,
)
from constitution_memorizer.learning.learning_unit_generator import generate_learning_units
from constitution_memorizer.schemas import (
    Article,
    ArticleStatus,
    Chapter,
    ConstitutionDocument,
    DocumentMetadata,
    Part,
    ProvisionNode,
)

ROOT = Path(__file__).resolve().parents[1]
CORRECTIONS = ROOT / "data" / "corrections" / "corrections.json"
UNITS = ROOT / "data" / "output" / "learning_units.json"

ART70_BODY = (
    "Parliament may make such provision as it thinks fit for the discharge of "
    "the functions of the President in any contingency not provided for in this "
    "Chapter."
)
ART71_CLAUSE_1 = (
    "(1) All doubts and disputes arising out of or in connection with the "
    "election of a President or Vice-President shall be inquired into and "
    "decided by the Supreme Court whose decision shall be final."
)


def _article_map(doc: ConstitutionDocument) -> dict[str, Article]:
    out: dict[str, Article] = {}
    for part in doc.parts:
        for article in part.articles:
            out[str(article.article_number)] = article
        for chapter in part.chapters:
            for article in chapter.articles:
                out[str(article.article_number)] = article
    return out


def _broken_doc() -> ConstitutionDocument:
    return ConstitutionDocument(
        document=DocumentMetadata(title="t", schema_version="1.0.0"),
        parts=[
            Part(
                id="part-v",
                part_number="V",
                title="THE UNION",
                chapters=[
                    Chapter(
                        id="chapter-i",
                        chapter_number="I",
                        title="THE EXECUTIVE",
                        articles=[
                            Article(
                                id="article-70",
                                article_number="70",
                                numeric_component=70,
                                title="Discharge of President's functions in other contingencies",
                                part_number="V",
                                chapter_number="I",
                                status=ArticleStatus.ACTIVE,
                                body_text=(
                                    "(2) If the election of a person as President…"
                                ),
                                clauses=[
                                    ProvisionNode(
                                        id="article-70-clause-2",
                                        label="(2)",
                                        text=(
                                            "If the election of a person as President "
                                            "or Vice-President is declared void…"
                                        ),
                                    ),
                                    ProvisionNode(
                                        id="article-70-clause-3",
                                        label="(3)",
                                        text=(
                                            "Subject to the provisions of this "
                                            "Constitution, Parliament may by law…"
                                        ),
                                    ),
                                    ProvisionNode(
                                        id="article-70-clause-4",
                                        label="(4)",
                                        text=(
                                            "The election of a person as President or "
                                            "Vice-President shall not be called in "
                                            "question…]"
                                        ),
                                    ),
                                ],
                            ),
                            Article(
                                id="article-71",
                                article_number="71",
                                numeric_component=71,
                                title="Seventh Schedule debris",
                                part_number="V",
                                chapter_number="I",
                                status=ArticleStatus.ACTIVE,
                                body_text="List I entry overwrite",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def test_corrections_file_covers_70_and_71():
    data = json.loads(CORRECTIONS.read_text())
    arts = data["articles"]
    assert arts["article-70"]["body_text"] == ART70_BODY
    assert "(2)" not in arts["article-70"]["body_text"]
    assert ART71_CLAUSE_1 in arts["article-71"]["body_text"]
    assert arts["article-71"]["body_text"].count("(4)") == 1
    assert not arts["article-71"]["body_text"].rstrip().endswith("]")


def test_apply_restores_70_and_clears_misattached_clauses():
    doc, _ = apply_corrections(_broken_doc(), load_corrections(CORRECTIONS))
    arts = _article_map(doc)
    assert arts["70"].body_text == ART70_BODY
    assert arts["70"].clauses == []
    assert arts["70"].title == "Discharge of President's functions in other contingencies"
    assert (arts["71"].body_text or "").startswith("(1) All doubts and disputes")
    assert arts["71"].title.startswith("Matters relating to")


def test_learning_units_from_synthetic_doc():
    doc, _ = apply_corrections(_broken_doc(), load_corrections(CORRECTIONS))
    result = generate_learning_units(doc)
    by_art: dict[str, list] = {}
    for unit in result.units:
        by_art.setdefault(unit.article_number, []).append(unit)

    ids_70 = {u.id for u in by_art["70"]}
    assert ids_70 == {"article-70"}
    assert by_art["70"][0].text == ART70_BODY
    assert "article-70-clause-2" not in ids_70

    ids_71 = {u.id for u in by_art["71"]}
    assert ids_71 == {
        "article-71-clause-1",
        "article-71-clause-2",
        "article-71-clause-3",
        "article-71-clause-4",
    }
    texts_71 = " ".join(u.text for u in by_art["71"])
    assert ART71_CLAUSE_1 in texts_71
    assert ART70_BODY not in texts_71


def test_committed_learning_units_separate_70_and_71():
    payload = json.loads(UNITS.read_text())
    units = payload["units"]
    by_id = {u["id"]: u for u in units}
    ids_70 = {u["id"] for u in units if u.get("article_number") == "70"}
    ids_71 = {u["id"] for u in units if u.get("article_number") == "71"}

    assert ids_70 == {"article-70"}
    assert by_id["article-70"]["text"] == ART70_BODY
    assert by_id["article-69"]["next_unit"] == "article-70"
    assert by_id["article-71-clause-1"]["previous_unit"] == "article-70"
    assert by_id["article-70"]["next_unit"] == "article-71-clause-1"
    assert by_id["article-70"]["previous_unit"] == "article-69"

    assert ids_71 == {
        "article-71-clause-1",
        "article-71-clause-2",
        "article-71-clause-3",
        "article-71-clause-4",
    }
    assert by_id["article-71-clause-1"]["text"] == ART71_CLAUSE_1
    assert not by_id["article-71-clause-4"]["text"].rstrip().endswith("]")
    for uid in (
        "article-70-clause-2",
        "article-70-clause-3",
        "article-70-clause-4",
    ):
        assert uid not in by_id
