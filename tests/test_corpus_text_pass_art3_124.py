"""Article 3 / 124 corpus text-pass corrections."""

from __future__ import annotations

from constitution_memorizer.corrections.apply_corrections import (
    ArticleCorrection,
    CorrectionsFile,
    apply_corrections,
)
from constitution_memorizer.learning.learning_unit_generator import generate_learning_units
from constitution_memorizer.learning.schemas import LearningUnitType
from constitution_memorizer.schemas import (
    Article,
    ArticleStatus,
    ConstitutionDocument,
    DocumentMetadata,
    ExtractionSummary,
    Part,
)
from constitution_memorizer.web.text_annotations import (
    TextAnnotation,
    annotate_plain_text,
    load_text_annotations,
)


def _sample_doc() -> ConstitutionDocument:
    return ConstitutionDocument(
        document=DocumentMetadata(title="test", schema_version="1.0.0"),
        parts=[
            Part(
                id="part-i",
                part_number="I",
                title="THE UNION AND ITS TERRITORY",
                articles=[
                    Article(
                        id="article-3",
                        article_number="3",
                        numeric_component=3,
                        title="Formation of new States…",
                        part_number="I",
                        status=ArticleStatus.ACTIVE,
                        opening_text="",
                        body_text=(
                            "Parliament may by law-\n"
                            "(a) form a new State;\n"
                            "(b) increase the area of any State;\n"
                            "(e) alter the name of any State:"
                        ),
                    ),
                    Article(
                        id="article-124",
                        article_number="124",
                        numeric_component=124,
                        title="Establishment and constitution of the Supreme Court",
                        part_number="V",
                        status=ArticleStatus.ACTIVE,
                        body_text=(
                            "(1) … of not more than seven other Judges.\n"
                            "(2) Every Judge … seal on the recommendation of the "
                            "National Judicial Appointments Commission referred to in "
                            "article 124A and shall hold office until he attains the "
                            "age of sixty-five years:\n"
                            "Provided that—\n"
                            "(a) resign;\n"
                            "(b) removed."
                        ),
                    ),
                ],
            )
        ],
        extraction_summary=ExtractionSummary(),
    )


def test_article_3_prefer_article_unit_skips_explanations():
    art3_body = (
        "Parliament may by law—\n"
        "(a) form a new State by separation of territory from any State or by "
        "uniting two or more States or parts of States or by uniting any territory "
        "to a part of any State;\n"
        "(b) increase the area of any State;\n"
        "(c) diminish the area of any State;\n"
        "(d) alter the boundaries of any State;\n"
        "(e) alter the name of any State:\n\n"
        "Provided that no Bill for the purpose shall be introduced in either House "
        "of Parliament except on the recommendation of the President and unless, "
        "where the proposal contained in the Bill affects the area, boundaries or "
        "name of any of the States, the Bill has been referred by the President to "
        "the Legislature of that State for expressing its views thereon within such "
        "period as may be specified in the reference or within such further period "
        "as the President may allow and the period so specified or allowed has "
        "expired."
    )
    corrections = CorrectionsFile(
        articles={
            "article-3": ArticleCorrection(
                title=(
                    "Formation of new States and alteration of areas, boundaries "
                    "or names of existing States"
                ),
                opening_text="",
                body_text=art3_body,
                prefer_article_unit=True,
            )
        }
    )
    reviewed, _ = apply_corrections(_sample_doc(), corrections)
    art = next(a for p in reviewed.parts for a in p.articles if a.id == "article-3")
    assert art.prefer_article_unit is True
    assert art.body_text.startswith("Parliament may by law—")
    assert "(c) diminish" in art.body_text
    assert "Explanation" not in art.body_text
    assert art.clauses == []

    units = generate_learning_units(reviewed).units
    art3_units = [u for u in units if u.article_number == "3"]
    assert len(art3_units) == 1
    unit = art3_units[0]
    assert unit.id == "article-3"
    assert unit.type == LearningUnitType.ARTICLE
    assert unit.display_title == "Article 3"
    assert unit.text.startswith("Parliament may by law—")
    assert "(c) diminish the area of any State;" in unit.text
    assert "Explanation" not in unit.text


def test_article_124_omits_struck_down_njac_wording():
    body = (
        "(1) There shall be a Supreme Court of India consisting of a Chief Justice "
        "of India and, until Parliament by law prescribes a larger number, of not "
        "more than seven other Judges.\n"
        "(2) Every Judge of the Supreme Court shall be appointed by the President "
        "by warrant under his hand and seal and shall hold office until he attains "
        "the age of sixty-five years:\n"
        "[Provided that]—\n"
        "(a) a Judge may, by writing under his hand addressed to the President, "
        "resign his office;\n"
        "(b) a Judge may be removed from his office in the manner provided in "
        "clause (4)."
    )
    corrections = CorrectionsFile(
        articles={"article-124": ArticleCorrection(opening_text="", body_text=body)}
    )
    reviewed, _ = apply_corrections(_sample_doc(), corrections)
    art = next(a for p in reviewed.parts for a in p.articles if a.id == "article-124")
    assert "National Judicial Appointments" not in art.body_text
    assert "after consultation" not in art.body_text
    assert "[Provided that]—" in art.body_text
    assert (
        "by warrant under his hand and seal and shall hold office until he attains"
        in art.body_text
    )

    units = {u.id: u for u in generate_learning_units(reviewed).units}
    clause1 = units["article-124-clause-1"]
    assert "seven other Judges" in clause1.text
    clause2 = units["article-124-clause-2"]
    assert "National Judicial Appointments" not in clause2.text
    assert "after consultation" not in clause2.text
    assert "seal and shall hold office" in clause2.text
    assert "[Provided that]—" in clause2.text


def test_seven_annotation_anchors_the_word_and_carries_its_note():
    catalog = load_text_annotations()
    anns = catalog["article-124-clause-1"]
    assert anns[0].target == "seven"
    annotated = annotate_plain_text(
        "of not more than seven other Judges.",
        anns,
    )
    rendered = str(annotated.html)
    assert 'class="bareact-fn"' in rendered
    assert ">seven</span>" in rendered
    assert 'aria-describedby="fn-fn-note-0"' in rendered
    # The note travels beside the text, never inside it.
    note = annotated.footnotes[0].text
    assert "thirty-three" in note
    assert "37 of 2019" in note
    assert "thirty-three" not in rendered
    assert "sevenNow" not in rendered
    assert ">seven</span>Now" not in rendered


def test_annotate_escapes_and_skips_missing_targets():
    annotated = annotate_plain_text(
        "alpha <beta> gamma",
        [TextAnnotation(target="missing", note="n")],
    )
    assert "&lt;beta&gt;" in str(annotated.html)
    assert "bareact-fn" not in str(annotated.html)
    assert annotated.footnotes == ()


def test_article_326_title_body_split_and_eighteen_hover():
    title = (
        "Elections to the House of the People and to the Legislative Assemblies "
        "of States to be on the basis of adult suffrage"
    )
    body = (
        "The elections to the House of the People and to the Legislative Assembly of "
        "every State shall be on the basis of adult suffrage; that is to say, every "
        "person who is a citizen of India and who is not less than eighteen years of "
        "age on such date as may be fixed in that behalf by or under any law made by "
        "the appropriate Legislature and is not otherwise disqualified under this "
        "Constitution or any law made by the appropriate Legislature on the ground of "
        "non-residence, unsoundness of mind, crime or corrupt or illegal practice, "
        "shall be entitled to be registered as a voter at any such election."
    )
    doc = ConstitutionDocument(
        document=DocumentMetadata(title="test", schema_version="1.0.0"),
        parts=[
            Part(
                id="part-xv",
                part_number="XV",
                title="ELECTIONS",
                articles=[
                    Article(
                        id="article-326",
                        article_number="326",
                        numeric_component=326,
                        title=title + ".The elections to the House… 2 [eighteen years] … non",
                        status=ArticleStatus.ACTIVE,
                        opening_text="",
                        body_text=(
                            "residence, unsoundness of mind, crime or corrupt or illegal "
                            "practice, shall be entitled to be registered as a voter at "
                            "any such election."
                        ),
                    )
                ],
            )
        ],
        extraction_summary=ExtractionSummary(),
    )
    corrections = CorrectionsFile(
        articles={
            "article-326": ArticleCorrection(
                title=title,
                opening_text="",
                body_text=body,
            )
        }
    )
    reviewed, _ = apply_corrections(doc, corrections)
    art = next(a for p in reviewed.parts for a in p.articles if a.id == "article-326")
    assert art.title == title
    assert art.title is not None and "eighteen" not in art.title
    assert art.body_text.startswith("The elections to the House")
    assert "2 [" not in art.body_text
    assert "[eighteen" not in art.body_text
    assert "eighteen years" in art.body_text

    unit = next(u for u in generate_learning_units(reviewed).units if u.id == "article-326")
    assert unit.display_title == "Article 326"
    assert unit.title == title
    assert "eighteen years" in unit.text
    assert unit.text.startswith("The elections")

    anns = load_text_annotations()["article-326"]
    assert anns[0].target == "eighteen"
    annotated = annotate_plain_text(unit.text, anns)
    rendered = str(annotated.html)
    assert ">eighteen</span>" in rendered
    assert 'class="bareact-fn"' in rendered
    note = annotated.footnotes[0].text
    assert "Sixty-first Amendment" in note
    assert "twenty-one years" in note
    assert "2 [eighteen" not in rendered
