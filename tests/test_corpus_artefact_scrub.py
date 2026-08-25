"""Corpus artefact scrub + stolen-article restorations."""

from __future__ import annotations

from constitution_memorizer.corrections.apply_corrections import (
    ArticleCorrection,
    CorrectionsFile,
    apply_corrections,
)
from constitution_memorizer.corrections.artefact_scrub import (
    scrub_display_text,
    scrub_document,
    should_include_opening,
    strip_heading_omission_marker,
)
from constitution_memorizer.learning.learning_unit_generator import generate_learning_units
from constitution_memorizer.schemas import (
    Article,
    ArticleStatus,
    ConstitutionDocument,
    DocumentMetadata,
    ExtractionSummary,
    Part,
)
from constitution_memorizer.web.browse import _article_full_text


def test_scrub_removes_formula_and_pua():
    raw = "Hello <!-- formula-not-decoded --> world \uf02a [seven]"
    assert scrub_display_text(raw) == "Hello world [seven]"


def test_opening_body_dedupe_and_display(tmp_path=None):
    doc = ConstitutionDocument(
        document=DocumentMetadata(title="t", schema_version="1.0.0"),
        parts=[
            Part(
                id="part-iii",
                part_number="III",
                title="FUNDAMENTAL RIGHTS",
                articles=[
                    Article(
                        id="article-14",
                        article_number="14",
                        numeric_component=14,
                        title="Equality before law",
                        status=ArticleStatus.ACTIVE,
                        opening_text=(
                            "The State shall not deny to any person equality before "
                            "the law or the equal protection of the laws within the "
                            "territory of India."
                        ),
                        body_text=(
                            "The State shall not deny to any person equality before "
                            "the law or the equal protection of the laws within the "
                            "territory of India."
                        ),
                    ),
                    Article(
                        id="article-3",
                        article_number="3",
                        numeric_component=3,
                        title="Formation of new States",
                        status=ArticleStatus.ACTIVE,
                        opening_text="Parliament may by law-",
                        body_text=(
                            "Parliament may by law-\n"
                            "(a) form a new State by separation of territory;"
                        ),
                    ),
                    Article(
                        id="article-92b",
                        article_number="92B",
                        numeric_component=92,
                        title="Taxes on consignments",
                        status=ArticleStatus.ACTIVE,
                        body_text="State trade or commerce.] <!-- formula-not-decoded -->",
                    ),
                ],
            )
        ],
        extraction_summary=ExtractionSummary(),
    )
    corrections = CorrectionsFile(
        articles={"article-92b": ArticleCorrection(exclude=True)}
    )
    reviewed, changes = apply_corrections(doc, corrections)
    assert any("cleared opening" in c for c in changes)
    assert any("excluded" in c for c in changes)

    art14 = next(a for p in reviewed.parts for a in p.articles if a.id == "article-14")
    assert art14.opening_text == ""
    full = _article_full_text(art14)
    assert full.count("The State shall not deny") == 1
    assert "formula-not-decoded" not in full

    art3 = next(a for p in reviewed.parts for a in p.articles if a.id == "article-3")
    assert art3.opening_text == ""
    assert art3.body_text.startswith("Parliament may by law-")

    nums = {a.article_number for p in reviewed.parts for a in p.articles}
    assert "92B" not in nums

    units = {u.id: u for u in generate_learning_units(reviewed).units}
    assert units["article-14"].text.count("The State shall not deny") == 1
    assert "article-92b" not in units


def test_should_include_opening_helper():
    assert should_include_opening("", "body") is False
    assert should_include_opening("same", "same") is False
    assert should_include_opening("stem", "stem\n(a) more") is False
    assert should_include_opening("extra note", "body text") is True


def test_heading_omission_marker_stripped_from_part_titles():
    """"THE STATES 1 ***" is Bare Act typography, not a name.

    The "***" stands for words repealed by an amendment and the leading digit
    is the footnote that names it — for Part VI, the Seventh Amendment (1956)
    dropping "IN PART A OF THE FIRST SCHEDULE". Faithful in print, noise as a
    title here. scrub_document used to walk only articles and schedules, so
    the marker reached the Learn deck verbatim.
    """
    doc = ConstitutionDocument(
        document=DocumentMetadata(title="t", schema_version="1.0.0"),
        parts=[
            Part(id="part-vi", part_number="VI", title="THE STATES 1 ***"),
            Part(id="part-i", part_number="I", title="THE UNION AND ITS TERRITORY"),
        ],
        extraction_summary=ExtractionSummary(),
    )
    scrub_document(doc)
    assert doc.parts[0].title == "THE STATES"
    # Untouched titles stay byte-identical.
    assert doc.parts[1].title == "THE UNION AND ITS TERRITORY"


def test_heading_omission_scrub_leaves_body_omissions_alone():
    """An omission inside article text is real Bare Act wording."""
    body = "(2) The President may, notwithstanding anything in 2 *** the proviso"
    assert scrub_display_text(body) == body
    # And the heading rule never fires mid-string, only at the end.
    assert strip_heading_omission_marker(body) == body


def test_heading_omission_scrub_is_conservative():
    assert strip_heading_omission_marker("THE STATES") == "THE STATES"
    assert strip_heading_omission_marker("") == ""
    assert strip_heading_omission_marker(None) is None
    # Never empties a title that is nothing but the marker.
    assert strip_heading_omission_marker("***") == "***"
