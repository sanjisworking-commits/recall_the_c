"""Restore Art 124(2) consultation wording omitted after the NJAC strike-down."""

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
    ConstitutionDocument,
    DocumentMetadata,
    Part,
)

ROOT = Path(__file__).resolve().parents[1]
CORRECTIONS = ROOT / "data" / "corrections" / "corrections.json"
UNITS = ROOT / "data" / "output" / "learning_units.json"

ART124_CLAUSE_2 = (
    "(2) Every Judge of the Supreme Court shall be appointed by the President "
    "by warrant under his hand and seal after consultation with such of the "
    "Judges of the Supreme Court and of the High Courts in the States as the "
    "President may deem necessary for the purpose and shall hold office until "
    "he attains the age of sixty-five years:\n"
    "Provided that in the case of appointment of a Judge other than the Chief "
    "Justice, the Chief Justice of India shall always be consulted:\n"
    "Provided further that—\n"
    "(a) a Judge may, by writing under his hand addressed to the President, "
    "resign his office;\n"
    "(b) a Judge may be removed from his office in the manner provided in "
    "clause (4)."
)


def _njac_doc() -> ConstitutionDocument:
    return ConstitutionDocument(
        document=DocumentMetadata(title="t", schema_version="1.0.0"),
        parts=[
            Part(
                id="part-v",
                part_number="V",
                title="THE UNION",
                articles=[
                    Article(
                        id="article-124",
                        article_number="124",
                        numeric_component=124,
                        title="Establishment and constitution of the Supreme Court",
                        part_number="V",
                        status=ArticleStatus.ACTIVE,
                        body_text=(
                            "(1) There shall be a Supreme Court of India consisting of "
                            "a Chief Justice of India and, until Parliament by law "
                            "prescribes a larger number, of not more than seven other "
                            "Judges.\n"
                            "(2) Every Judge of the Supreme Court shall be appointed by "
                            "the President by warrant under his hand and seal on the "
                            "recommendation of the National Judicial Appointments "
                            "Commission referred to in article 124A and shall hold "
                            "office until he attains the age of sixty-five years:\n"
                            "Provided that—\n"
                            "(a) a Judge may resign;\n"
                            "(b) a Judge may be removed."
                        ),
                    ),
                ],
            ),
        ],
    )


def test_corrections_file_restores_124_clause_2():
    data = json.loads(CORRECTIONS.read_text(encoding="utf-8"))
    body = data["articles"]["article-124"]["body_text"]
    assert ART124_CLAUSE_2 in body
    assert "National Judicial Appointments" not in body
    assert "[Provided that]—" not in body


def test_apply_replaces_njac_with_consultation_wording():
    doc, _ = apply_corrections(_njac_doc(), load_corrections(CORRECTIONS))
    art = doc.parts[0].articles[0]
    assert ART124_CLAUSE_2 in (art.body_text or "")
    assert "National Judicial Appointments" not in (art.body_text or "")
    assert "article 124A" not in (art.body_text or "")


def test_learning_units_from_synthetic_doc():
    doc, _ = apply_corrections(_njac_doc(), load_corrections(CORRECTIONS))
    units = {u.id: u for u in generate_learning_units(doc).units}
    clause2 = units["article-124-clause-2"]
    assert clause2.text == ART124_CLAUSE_2
    assert units["article-124-clause-2-subclause-a"].text.startswith("(a)")
    assert units["article-124-clause-2-subclause-b"].text.startswith("(b)")
    assert "National Judicial Appointments" not in clause2.text


def test_committed_learning_units_include_consultation_wording():
    payload = json.loads(UNITS.read_text(encoding="utf-8"))
    by_id = {u["id"]: u for u in payload["units"]}
    assert by_id["article-124-clause-2"]["text"] == ART124_CLAUSE_2
    assert by_id["article-124-clause-2"]["previous_unit"] == "article-124-clause-1"
    assert by_id["article-124-clause-2"]["next_unit"] == "article-124-clause-2a"
    assert "National Judicial Appointments" not in by_id["article-124-clause-2"]["text"]
    assert by_id["article-124-clause-1"]["next_unit"] == "article-124-clause-2"
