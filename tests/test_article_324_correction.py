"""Restore Article 324 title vs body — clause (1) must not live in the Learn lede."""

from __future__ import annotations

from constitution_memorizer.corrections.apply_corrections import (
    ArticleCorrection,
    CorrectionsFile,
    apply_corrections,
)
from constitution_memorizer.learning.learning_unit_generator import generate_learning_units
from constitution_memorizer.schemas import (
    Article,
    ArticleStatus,
    ConstitutionDocument,
    DocumentMetadata,
    ExtractionSummary,
    Part,
    ProvisionNode,
)
from constitution_memorizer.web.service import unit_crumb

_TITLE = (
    "Superintendence, direction and control of elections to be vested in an "
    "Election Commission"
)

_BODY = (
    "(1) The superintendence, direction and control of the preparation of the "
    "electoral rolls for, and the conduct of, all elections to Parliament and to "
    "the Legislature of every State and of elections to the offices of President "
    "and Vice-President held under this Constitution shall be vested in a "
    "Commission (referred to in this Constitution as the Election Commission).\n"
    "(2) The Election Commission shall consist of the Chief Election Commissioner "
    "and such number of other Election Commissioners, if any, as the President may "
    "from time to time fix and the appointment of the Chief Election Commissioner "
    "and other Election Commissioners shall, subject to the provisions of any law "
    "made in that behalf by Parliament, be made by the President.\n"
    "(3) When any other Election Commissioner is so appointed the Chief Election "
    "Commissioner shall act as the Chairman of the Election Commission.\n"
    "(4) Before each general election to the House of the People and to the "
    "Legislative Assembly of each State, and before the first general election and "
    "thereafter before each biennial election to the Legislative Council of each "
    "State having such Council, the President may also appoint after consultation "
    "with the Election Commission such Regional Commissioners as he may consider "
    "necessary to assist the Election Commission in the performance of the "
    "functions conferred on the Commission by clause (1).\n"
    "(5) Subject to the provisions of any law made by Parliament, the conditions "
    "of service and tenure of office of the Election Commissioners and the "
    "Regional Commissioners shall be such as the President may by rule determine:\n"
    "Provided that the Chief Election Commissioner shall not be removed from his "
    "office except in like manner and on the like grounds as a Judge of the "
    "Supreme Court and the conditions of service of the Chief Election "
    "Commissioner shall not be varied to his disadvantage after his appointment:\n"
    "Provided further that any other Election Commissioner or a Regional "
    "Commissioner shall not be removed from office except on the recommendation of "
    "the Chief Election Commissioner.\n"
    "(6) The President, or the Governor of a State, shall, when so requested by "
    "the Election Commission, make available to the Election Commission or to a "
    "Regional Commissioner such staff as may be necessary for the discharge of the "
    "functions conferred on the Election Commission by clause (1)."
)

_POLLUTED_TITLE = (
    _TITLE
    + ".(1) The superintendence, direction and control of the preparation of the "
    "electoral rolls for, and the conduct of, all elections to Parliament and to "
    "the Legislature of every State and of elections to the offices of President "
    "and Vice"
)


def test_article_324_title_body_split_and_clauses_1_through_6():
    doc = ConstitutionDocument(
        document=DocumentMetadata(title="t", schema_version="1.0.0"),
        parts=[
            Part(
                id="part-xv",
                part_number="XV",
                title="ELECTIONS",
                articles=[
                    Article(
                        id="article-324",
                        article_number="324",
                        numeric_component=324,
                        title=_POLLUTED_TITLE,
                        part_number="XV",
                        status=ArticleStatus.ACTIVE,
                        opening_text="",
                        body_text=(
                            "(2) The Election Commission shall consist of the Chief "
                            "Election Commissioner…"
                        ),
                        clauses=[
                            ProvisionNode(
                                id="article-324-clause-2",
                                label="(2)",
                                label_type="numeric",
                                text="The Election Commission shall consist…",
                            ),
                            ProvisionNode(
                                id="article-324-clause-5",
                                label="(5)",
                                label_type="numeric",
                                text=(
                                    "Subject to the provisions of any law made by "
                                    "Parliament… after his appointment:"
                                ),
                            ),
                        ],
                    )
                ],
            )
        ],
        extraction_summary=ExtractionSummary(),
    )
    reviewed, _ = apply_corrections(
        doc,
        CorrectionsFile(
            articles={
                "article-324": ArticleCorrection(
                    title=_TITLE,
                    part_number="XV",
                    opening_text="",
                    body_text=_BODY,
                )
            }
        ),
    )
    art = next(a for p in reviewed.parts for a in p.articles if a.id == "article-324")
    assert art.title == _TITLE
    assert art.title is not None and ".(1)" not in art.title
    assert art.clauses == []
    assert art.body_text.startswith("(1) The superintendence")
    assert "Provided further that any other Election Commissioner" in art.body_text
    assert art.body_text.rstrip().endswith("by clause (1).")

    units = {u.id: u for u in generate_learning_units(reviewed).units}
    for n in range(1, 7):
        assert f"article-324-clause-{n}" in units
    for n in range(1, 7):
        unit = units[f"article-324-clause-{n}"]
        assert unit.title == _TITLE
        assert ".(1)" not in (unit.title or "")
        assert unit.text.startswith(f"({n})")
        crumb = unit_crumb(unit)
        assert ".(1)" not in crumb
        assert crumb == "Part XV · Article 324"
        assert "electoral rolls" not in crumb

    assert "Vice-President" in units["article-324-clause-1"].text
    assert "recommendation of the Chief Election Commissioner" in units[
        "article-324-clause-5"
    ].text
    assert "make available to the Election Commission" in units[
        "article-324-clause-6"
    ].text
