"""Arts 54–67 corpus restore + nested population/2026 tooltip."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.corrections.apply_corrections import (
    ArticleCorrection,
    CorrectionsFile,
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
    ExtractionSummary,
    Part,
)
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.text_annotations import (
    ContentNoteRef,
    ContentText,
    NoteRecord,
    TextAnnotation,
    annotate_plain_text,
    load_text_annotations,
    render_note_body,
)

ROOT = Path(__file__).resolve().parents[1]
CORRECTIONS = ROOT / "data" / "corrections" / "corrections.json"
ANNOTATIONS = ROOT / "data" / "reference" / "text_annotations.json"
UNITS = ROOT / "data" / "output" / "learning_units.json"
MINI_UNITS = ROOT / "tests" / "fixtures" / "mini_learning_units.json"


def _part_v_doc(*articles: Article) -> ConstitutionDocument:
    return ConstitutionDocument(
        document=DocumentMetadata(title="t", schema_version="1.0.0"),
        parts=[
            Part(
                id="part-v",
                part_number="V",
                title="THE UNION",
                chapters=[
                    Chapter(
                        id="part-v-chapter-i",
                        chapter_number="I",
                        title="THE EXECUTIVE",
                        articles=list(articles),
                    )
                ],
            )
        ],
        extraction_summary=ExtractionSummary(),
    )


def test_corrections_json_has_54_55_56_67():
    corr = load_corrections(CORRECTIONS)
    assert corr.articles["article-54"].prefer_article_unit is True
    assert corr.articles["article-54"].enable_letter_split is not True
    assert "Explanation" not in (corr.articles["article-54"].body_text or "")
    assert "(b) if, after taking the said multiples" in (
        corr.articles["article-55"].body_text or ""
    )
    assert "Explanation" not in (corr.articles["article-55"].body_text or "")
    assert "2026" not in (corr.articles["article-55"].body_text or "")
    body56 = corr.articles["article-56"].body_text or ""
    assert "Provided that—" in body56
    assert body56.index("Provided that—") < body56.index("(2)")
    assert corr.articles["article-67"].prefer_article_unit is True
    assert corr.articles["article-67"].enable_letter_split is True


def test_article_54_single_card_without_explanation():
    corr = load_corrections(CORRECTIONS)
    doc = _part_v_doc(
        Article(
            id="article-54",
            article_number="54",
            numeric_component=54,
            title="Election of President",
            part_number="V",
            chapter_number="I",
            status=ArticleStatus.ACTIVE,
            body_text="(a) broken Explanation",
        )
    )
    reviewed, _ = apply_corrections(
        doc, CorrectionsFile(articles={"article-54": corr.articles["article-54"]})
    )
    units = {u.id: u for u in generate_learning_units(reviewed).units}
    assert "article-54" in units
    assert units["article-54"].display_title == "Article 54"
    assert units["article-54"].allows_letter_split is False
    assert "Explanation" not in units["article-54"].text
    assert "electoral college" in units["article-54"].text
    assert not any(uid.startswith("article-54-clause") for uid in units)


def test_article_67_article_card_with_sibling_letter_split():
    corr = load_corrections(CORRECTIONS)
    doc = _part_v_doc(
        Article(
            id="article-67",
            article_number="67",
            numeric_component=67,
            title="Term of office of Vice-President",
            part_number="V",
            chapter_number="I",
            status=ArticleStatus.ACTIVE,
            body_text="(a) broken",
        )
    )
    reviewed, _ = apply_corrections(
        doc, CorrectionsFile(articles={"article-67": corr.articles["article-67"]})
    )
    art = reviewed.parts[0].chapters[0].articles[0]
    assert art.prefer_article_unit is True
    assert art.enable_letter_split is True

    units = {u.id: u for u in generate_learning_units(reviewed).units}
    assert units["article-67"].display_title == "Article 67"
    assert units["article-67"].allows_letter_split is True
    assert units["article-67-subclause-a"].display_title == "Article 67(a)"
    assert units["article-67-subclause-b"].display_title == "Article 67(b)"
    assert units["article-67-subclause-c"].display_title == "Article 67(c)"
    assert "67(a)(b)" not in units["article-67-subclause-b"].display_title
    assert "article-67-clause-a" not in units
    assert units["article-67"].child_unit_ids == [
        "article-67-subclause-a",
        "article-67-subclause-b",
        "article-67-subclause-c",
    ]


def test_article_56_proviso_under_clause_one():
    corr = load_corrections(CORRECTIONS)
    doc = _part_v_doc(
        Article(
            id="article-56",
            article_number="56",
            numeric_component=56,
            title="Term of office of President",
            part_number="V",
            chapter_number="I",
            status=ArticleStatus.ACTIVE,
            body_text="(1) broken",
        )
    )
    reviewed, _ = apply_corrections(
        doc, CorrectionsFile(articles={"article-56": corr.articles["article-56"]})
    )
    units = {u.id: u for u in generate_learning_units(reviewed).units}
    assert "Provided that" in units["article-56-clause-1"].text
    assert "continue to hold office until his successor" in units["article-56-clause-1"].text
    assert "Provided that" not in units["article-56-clause-2"].text
    assert "Speaker of the House of the People" in units["article-56-clause-2"].text


def test_tracked_units_54_55_56_67():
    units = {u["id"]: u for u in json.loads(UNITS.read_text())["units"]}
    assert units["article-54"]["display_title"] == "Article 54"
    assert "Explanation" not in units["article-54"]["text"]
    assert "article-54-clause-a" not in units
    assert "article-55-clause-2-subclause-b" in units
    assert "article-55-clause-2-subclause-c" in units
    assert "population" in units["article-55-clause-2"]["text"]
    assert "Explanation" not in units["article-55-clause-3"]["text"]
    assert "2026" not in units["article-55-clause-3"]["text"]
    assert "1971" not in units["article-55-clause-3"]["text"]
    assert "Provided that" in units["article-56-clause-1"]["text"]
    assert "Provided that" not in units["article-56-clause-2"]["text"]
    assert units["article-67"]["display_title"] == "Article 67"
    assert units["article-67"]["allows_letter_split"] is True
    assert units["article-67-subclause-b"]["display_title"] == "Article 67(b)"
    assert "article-67-clause-a" not in units


def test_legacy_note_annotations_still_load():
    catalog = load_text_annotations(ANNOTATIONS)
    assert catalog.units["article-124-clause-1"][0].target == "seven"
    assert catalog.units["article-326"][0].note.startswith("Subs. by")
    annotated = annotate_plain_text(
        "of not more than seven other Judges.",
        catalog.units["article-124-clause-1"],
        notes=catalog.notes,
        unit_id="article-124-clause-1",
    )
    rendered = str(annotated.html)
    assert 'data-bareact-fn="article-124-clause-1-note-0"' in rendered
    assert ">seven</span>" in rendered
    # A legacy note is one flat note with nothing to descend into.
    assert len(annotated.footnotes) == 1
    assert "thirty-three" in annotated.footnotes[0].text
    assert "bareact-fn" not in annotated.footnotes[0].text


def test_structured_note_ref_and_safe_failures():
    notes = {
        "article-55-2026-amendment": NoteRecord(
            id="article-55-2026-amendment",
            note='Subs. by the Constitution (Eighty-fourth Amendment) Act, 2001, s. 2, for "2000" (w.e.f. 21-2-2002).',
        )
    }
    ann = TextAnnotation(
        target="population",
        content=(
            ContentText(value='means census after '),
            ContentNoteRef(label="2026", note_id="article-55-2026-amendment"),
            ContentText(value="."),
        ),
    )
    annotated = annotate_plain_text(
        "the population as ascertained",
        [ann],
        notes=notes,
        unit_id="article-55-clause-2",
    )
    html = str(annotated.html)
    assert 'data-bareact-fn="article-55-clause-2-note-0"' in html
    assert ">population</span>" in html
    # The cited note is a second note, anchored from inside the first.
    ids = [n.id for n in annotated.footnotes]
    assert ids == ["article-55-clause-2-note-0", "article-55-2026-amendment"]
    outer, inner = annotated.footnotes
    assert 'data-bareact-fn="article-55-2026-amendment"' in outer.text
    assert 'tabindex="-1"' in outer.text
    assert ">2026</span>" in outer.text
    assert "Eighty-fourth Amendment" in inner.text

    missing = TextAnnotation(
        target="population",
        content=(ContentNoteRef(label="2026", note_id="missing-note"),),
    )
    plain, cited = render_note_body(missing, notes)
    assert plain == "2026"
    assert cited == ()
    assert "<span" not in plain

    ignored = _parse_via_load_unknown_type()
    assert ignored  # loads without raising


def _parse_via_load_unknown_type() -> bool:
    import tempfile

    payload = {
        "schema_version": "1.1.0",
        "notes": {},
        "units": {
            "article-x": [
                {
                    "target": "word",
                    "content": [
                        {"type": "text", "value": "ok "},
                        {"type": "script", "value": "<evil>"},
                        {"type": "text", "value": "end"},
                    ],
                }
            ]
        },
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ann.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        catalog = load_text_annotations(path)
        ann = catalog.units["article-x"][0]
        assert len(ann.content) == 2
        annotated = annotate_plain_text("a word here", [ann], notes={}, unit_id="article-x")
        html = str(annotated.html)
        assert "<script" not in html
        # The unsupported node is dropped; the surviving copy is the note's.
        note = annotated.footnotes[0].text
        assert note == "ok end"
        assert "evil" not in note
    return True


def test_annotate_escapes_injection_in_structured_content():
    notes = {"n1": NoteRecord(id="n1", note='<img src=x onerror=alert(1)>')}
    ann = TextAnnotation(
        target="population",
        content=(
            ContentText(value="<b>bold</b> "),
            ContentNoteRef(label="<em>2026</em>", note_id="n1"),
        ),
    )
    annotated = annotate_plain_text("population", [ann], notes=notes, unit_id="u1")
    outer, inner = annotated.footnotes
    assert "&lt;b&gt;bold&lt;/b&gt;" in outer.text
    assert "&lt;em&gt;2026&lt;/em&gt;" in outer.text
    assert "<em>" not in outer.text
    # An escaped note may still contain the word onerror as text; the raw tag
    # must not survive into the page.
    assert "&lt;img src=x onerror=alert(1)&gt;" in inner.text
    assert "<img" not in str(annotated.html) + outer.text + inner.text


def test_article_55_learn_html_has_nested_trigger(tmp_path: Path):
    if not UNITS.exists():
        pytest.skip("learning_units.json missing")
    # Annotate population on clause (2); Explanation is tip-only (not in body).
    full = json.loads(UNITS.read_text())
    unit = next(u for u in full["units"] if u["id"] == "article-55-clause-2")
    assert "Explanation" not in unit["text"]
    mini = {
        "schema_version": "1.0.0",
        "source_document": "test",
        "unit_count": 1,
        "units": [unit],
    }
    units_path = tmp_path / "units.json"
    units_path.write_text(json.dumps(mini), encoding="utf-8")
    db = tmp_path / "progress.db"
    app = create_app(units_path=units_path, db_path=db, text_annotations_path=ANNOTATIONS)
    client = TestClient(app)
    # Clause (2) offers letter-split; choose whole so Read renders the tip.
    choose = client.post(
        "/learn/article-55-clause-2/choose",
        data={"mode": "whole"},
        follow_redirects=True,
    )
    assert choose.status_code == 200
    resp = client.get("/learn/article-55-clause-2?mode=read")
    assert resp.status_code == 200
    assert 'data-bareact-fn="article-55-clause-2-note-0"' in resp.text
    assert 'id="fn-article-55-2026-amendment"' in resp.text
    assert "Eighty-fourth Amendment" in resp.text
    assert "1971 census" in resp.text  # note copy
    assert "Explanation.—" not in resp.text.split("learn-panel-read")[1].split("learn-panel-cloze")[0]
    cloze = client.get("/learn/article-55-clause-2?mode=cloze")
    assert cloze.status_code == 200
    # All mode panels share one page; Cloze itself uses plain unit.text.
    assert 'data-cloze-text="' in cloze.text
    assert "bareact-fn" not in cloze.text.split('data-cloze-text="')[1].split('"')[0]


def test_article_54_learn_states_hover(tmp_path: Path):
    if not UNITS.exists():
        pytest.skip("learning_units.json missing")
    full = json.loads(UNITS.read_text())
    unit = next(u for u in full["units"] if u["id"] == "article-54")
    mini = {
        "schema_version": "1.0.0",
        "source_document": "test",
        "unit_count": 1,
        "units": [unit],
    }
    units_path = tmp_path / "units.json"
    units_path.write_text(json.dumps(mini), encoding="utf-8")
    app = create_app(
        units_path=units_path,
        db_path=tmp_path / "progress.db",
        text_annotations_path=ANNOTATIONS,
    )
    client = TestClient(app)
    resp = client.get("/learn/article-54?mode=read")
    assert resp.status_code == 200
    assert ">States</span>" in resp.text
    assert 'data-bareact-fn="article-54-note-0"' in resp.text
    assert "National Capital Territory of Delhi" in resp.text
    assert "Puducherry" in resp.text
    assert "Explanation" not in unit["text"]


def test_footnote_js_and_css_wiring(client_or_skip=None):
    app = create_app(
        units_path=MINI_UNITS if MINI_UNITS.exists() else UNITS,
        db_path=Path("/tmp/bareact-fn-test.db"),
        text_annotations_path=ANNOTATIONS,
    )
    client = TestClient(app)
    js = client.get("/static/app.js")
    assert js.status_code == 200
    text = js.text
    # One implementation, delegated, with the nesting trail and the same
    # dismiss contract the two readers used to keep separately.
    assert "initBareActFootnotes" in text
    assert "initBareFns" not in text
    assert "data-bareact-fn-back" in text
    assert "Escape" in text
    css = client.get("/static/styles.css")
    assert css.status_code == 200
    assert ".bareact-fn-card" in css.text
    assert "bare-fn" not in css.text


def test_browse_article_55_shows_corpus_and_nested_tooltip(tmp_path: Path):
    if not UNITS.exists():
        pytest.skip("learning_units.json missing")
    app = create_app(
        units_path=UNITS,
        db_path=tmp_path / "progress.db",
        text_annotations_path=ANNOTATIONS,
        reviewed_path=tmp_path / "missing-reviewed.json",
    )
    client = TestClient(app)
    resp = client.get("/browse/article/55")
    assert resp.status_code == 200
    html = resp.text
    assert "remainder is not less than five hundred" in html
    assert "single transferable vote" in html
    body = html.split("browse-article-text")[1].split("Learn")[0]
    assert "Explanation.—" not in body
    assert ">population</span>" in html
    assert 'data-bareact-fn="browse-article-55-note-0"' in html
    assert 'data-bareact-fn="article-55-2026-amendment"' in html
    assert ">2026</span>" in html
    assert "Eighty-fourth Amendment" in html
    assert "1971 census" in html  # note only
    # The card must sit outside the clipped preview, or a long note is cut off.
    preview, _, rest = html.partition("</article>")
    assert "bareact-fn-card" not in preview
    assert "bareact-fn-card" in rest


def test_browse_article_54_states_hover(tmp_path: Path):
    if not UNITS.exists():
        pytest.skip("learning_units.json missing")
    app = create_app(
        units_path=UNITS,
        db_path=tmp_path / "progress.db",
        text_annotations_path=ANNOTATIONS,
        reviewed_path=tmp_path / "missing-reviewed.json",
    )
    client = TestClient(app)
    resp = client.get("/browse/article/54")
    assert resp.status_code == 200
    assert "electoral college" in resp.text
    assert "Explanation" not in resp.text.split("unit-text")[1].split("Learn")[0]
    assert ">States</span>" in resp.text
    assert 'data-bareact-fn="browse-article-54-note-0"' in resp.text
    assert "National Capital Territory of Delhi" in resp.text


def test_both_readers_use_one_footnote_presentation(tmp_path: Path):
    """The Constitution and an Act mark statute the same way.

    They diverged once — an inline tip beside the word there, a card at the foot
    of the column here — and the split did not survive the corpus: 56 of the
    Constitution's 88 annotations are amendment notes, the same genre as every
    one of the Act's 108. This pins the convergence so it cannot quietly come
    apart again.
    """
    if not UNITS.exists():
        pytest.skip("learning_units.json missing")
    app = create_app(
        units_path=UNITS,
        db_path=tmp_path / "progress.db",
        text_annotations_path=ANNOTATIONS,
        reviewed_path=tmp_path / "missing-reviewed.json",
    )
    client = TestClient(app)
    act = client.get("/laws/ndps/section/1")
    article = client.get("/browse/article/55")
    assert act.status_code == 200
    assert article.status_code == 200

    for html in (act.text, article.text):
        assert 'class="bareact-fn"' in html
        assert 'class="bareact-fn-notes visually-hidden"' in html
        assert "data-bareact-fn-card" in html
        # Focusable, and described by a note that is really on the page.
        for note_id in re.findall(r'data-bareact-fn="([^"]+)"', html):
            assert f'aria-describedby="fn-{note_id}"' in html
            assert f'<p id="fn-{note_id}">' in html

    # And nothing is left of the inline tip but the comment saying why.
    js = client.get("/static/app.js").text
    css = client.get("/static/styles.css").text
    for gone in ("initBareFns", "bare-fn-word", "bare-fn-tip", "bare-fn-nested"):
        assert gone not in css
        assert gone not in js.replace("`.bare-fn`", "")

