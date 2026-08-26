"""Corpus artefact scrub + stolen-article restorations."""

from __future__ import annotations

from constitution_memorizer.corrections.apply_corrections import (
    ArticleCorrection,
    CorrectionsFile,
    apply_corrections,
)
from constitution_memorizer.corrections.artefact_scrub import (
    canonical_part_title,
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


def test_insertion_brackets_are_stripped_but_their_words_kept():
    """The other half of the footnote convention: "N [ ... ]" marks words
    INSERTED by an amendment. Part XXII carries them because the 58th
    Amendment (1987) added "AUTHORITATIVE TEXT IN HINDI". Unlike an omission,
    the bracketed text IS part of the current heading."""
    raw = "SHORT TITLE, COMMENCEMENT, 1 [AUTHORITATIVE TEXT IN HINDI] AND REPEALS"
    assert (
        strip_heading_omission_marker(raw)
        == "SHORT TITLE, COMMENCEMENT, AUTHORITATIVE TEXT IN HINDI AND REPEALS"
    )
    # Omission markers still behave as before.
    assert strip_heading_omission_marker("THE STATES 1 ***") == "THE STATES"
    # Untouched headings stay byte-identical.
    assert strip_heading_omission_marker("ELECTIONS") == "ELECTIONS"


def test_truncated_part_title_is_restored():
    """Part XXI's heading was cut off after "AND" — no regex can recover
    words that are not in the source, so the canonical text is supplied."""
    cut = strip_heading_omission_marker("1 [TEMPORARY, TRANSITIONAL AND")
    assert cut == "TEMPORARY, TRANSITIONAL AND"
    assert (
        canonical_part_title("XXI", cut)
        == "TEMPORARY, TRANSITIONAL AND SPECIAL PROVISIONS"
    )


def test_canonical_title_defers_to_a_clean_extraction():
    """Only a prefix is restored, so a fixed upstream extraction wins and the
    table quietly stops mattering rather than overwriting it."""
    full = "TEMPORARY, TRANSITIONAL AND SPECIAL PROVISIONS"
    assert canonical_part_title("XXI", full) == full
    # Something genuinely different is never replaced.
    assert canonical_part_title("XXI", "SOMETHING ELSE") == "SOMETHING ELSE"
    # Parts with no entry pass straight through.
    assert canonical_part_title("XXII", "SHORT TITLE") == "SHORT TITLE"


def test_scrub_document_fixes_both_part_headings():
    doc = ConstitutionDocument(
        document=DocumentMetadata(title="t", schema_version="1.0.0"),
        parts=[
            Part(id="part-xxi", part_number="XXI", title="1 [TEMPORARY, TRANSITIONAL AND"),
            Part(
                id="part-xxii",
                part_number="XXII",
                title="SHORT TITLE, COMMENCEMENT, 1 [AUTHORITATIVE TEXT IN HINDI] AND REPEALS",
            ),
        ],
        extraction_summary=ExtractionSummary(),
    )
    scrub_document(doc)
    assert doc.parts[0].title == "TEMPORARY, TRANSITIONAL AND SPECIAL PROVISIONS"
    assert (
        doc.parts[1].title
        == "SHORT TITLE, COMMENCEMENT, AUTHORITATIVE TEXT IN HINDI AND REPEALS"
    )


def test_shipped_part_titles_carry_no_footnote_markers():
    """Guards the committed dataset, not just the scrub: its upstream source
    is not in the repo, so a regression would ship silently."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    doc = json.loads((root / "data" / "output" / "learning_units.json").read_text())
    for unit in doc["units"]:
        if unit.get("type") != "PART_OVERVIEW":
            continue
        title = unit.get("title") or ""
        assert not any(ch in title for ch in "*[]"), unit["id"]
        # A heading ending in a conjunction is the shape of a truncation.
        assert not title.strip().endswith((" AND", " OF", " THE", ",")), unit["id"]
