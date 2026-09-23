"""The Motor Vehicles Act, 1988 — the seventh Bare Act.

The largest Act so far: 14 chapters, 257 section records spanning printed
numbers 1 to 217A, 309 amendment notes, and a 52-page First Schedule of road
signs that exists only as images. It reuses the BNS render profile, the flat
`source_x` strip, the unsupported-schedule row and the NDPS footnote card.

What the parser had to learn from this source, and what is pinned here so a
regeneration cannot quietly undo it:

* Indentation is not a fixed band table. The definitions in s.2 shift from
  the 108 band to the 90 band after clause (8); s.93(2) prints its first three
  clauses at the sub-section's own band; s.150(2) uses a 100/115/129 scheme of
  its own. Parentage is relative geometry plus marker sequence — "(9)"
  continues "(8)" — never wording.
* Six STATE AMENDMENT blocks are printed inline, two of them in 10pt, and the
  principal sections that follow (104, 105) stay in 10pt. They are preserved
  under `source_state_amendments` and never enter a section.
* Footnote anchors are kept as annotations, so this Act's notes reach the
  reader's card. A span that runs over a page break keeps its note number
  from the page that printed the note (p.67 -> p.66 note 3).
* Omission runs ("* * * * *") stand in the list they interrupt; a chapter
  (X) and seven sections are printed as omitted; s.193's amended marker is
  printed "[1]" and is kept exactly so; s.105 prints a two-column list and a
  displayed fraction, both kept in reading order rather than reflowed.

v3 answers the independent audit of v2 (2026-09-23), and its findings are
pinned in the "Independent audit" block below: marker chains on one line
("(a) (i) ..."), Explanations owned by their printed scope, four reviewed
ownership overrides recorded with page and reason, notes that target a
bracketed label, and the formula transcribed from the page as (Y × A) / R.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import BARE_ACTS, get_bare_act

REPO = Path(__file__).resolve().parents[1]
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ARCHIVAL = REPO / "data" / "reference" / "mva_canonical_v3.json"
RUNTIME = REPO / "src" / "constitution_memorizer" / "web" / "mva_runtime_v1.json"

CHAPTERS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV"]
OMITTED = ["140", "141", "142", "143", "144", "191", "195"]
# Printed "2[2A. E-cart ..." — an anchor, an amendment bracket, then the number.
AMENDED_OPENERS = ["2A", "26", "43", "44", "63", "129", "217A"]
# Every inserted section prints this way — 28 in all — and each anchor resolves.
AMENDED_OPENER_COUNT = 28
STATE_AMENDMENTS = [
    (31, "Rajasthan", "41"),
    (46, "Haryana", "65"),
    (52, "Kerala", "71"),
    (71, "Karnataka", "103"),
    (71, "Haryana", "103"),
    (105, "Rajasthan", "192"),
    (113, "Rajasthan", "207"),
]
KINDS = ["subsection", "clause", "subclause", "item", "subitem", "paragraph",
         "proviso", "explanation", "omission", "formula"]


def _client(tmp_path: Path) -> tuple[TestClient, ReminderEngine]:
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    return TestClient(create_app(units_path=MINI_UNITS, db_path=db)), engine


def _rows(number: str):
    return get_bare_act("mva").section(number).rows


def _all_rows():
    return [r for s in get_bare_act("mva").section_order for r in s.rows]


@lru_cache(maxsize=1)
def _archival() -> dict:
    return json.loads(ARCHIVAL.read_text(encoding="utf-8"))


def _canonical_section(number: str) -> dict:
    for chapter in _archival()["chapters"]:
        for section in chapter["sections"]:
            if section["number"] == number:
                return section
    raise KeyError(number)


def _walk(nodes):
    for node in nodes:
        yield node
        yield from _walk(node.get("children") or [])


def _labels(rows, depth: int):
    return [r.label for r in rows if r.depth == depth]


# ── The Act ───────────────────────────────────────────────────────────────


def test_the_whole_act_is_present():
    act = get_bare_act("mva")
    assert act is not None
    assert [c.number for c in act.chapters] == CHAPTERS
    assert len(act.section_order) == 257
    assert act.section_order[0].number == "1"
    assert act.section_order[-1].number == "217A"
    assert act.meta_label == "14 Chapters · Sections 1–217A"


def test_section_order_is_the_arrangement_of_sections():
    """The body's sequence equals the inventory printed on pages 3-9 — a
    reading of the source that the tree did not produce."""
    validation = _archival()["_validation"]
    ids = [s.number for s in get_bare_act("mva").section_order]
    assert ids == validation["arrangement_section_ids"]
    assert ids == validation["section_ids"]


@pytest.mark.parametrize("number", ["2A", "2B", "105", "215D", "217A"])
def test_lettered_and_late_sections_resolve_and_serve(tmp_path: Path, number: str):
    assert get_bare_act("mva").section(number) is not None
    client, _ = _client(tmp_path)
    assert client.get(f"/laws/mva/section/{number}").status_code == 200


def test_chapters_are_contiguous_and_cover_every_section():
    act = get_bare_act("mva")
    seen = []
    for chapter in act.chapters:
        assert chapter.sections, chapter.number
        for section in chapter.sections:
            assert section.chapter_number == chapter.number
            seen.append(section.number)
    assert seen == [s.number for s in act.section_order]
    ranges = {c.number: c.range_label for c in act.chapters}
    assert ranges["I"] == "1–2B"
    assert ranges["X"] == "140–144"
    assert ranges["XIV"].endswith("–217A")


# ── Omissions ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("number", OMITTED)
def test_omitted_sections_keep_their_printed_statement(tmp_path: Path, number: str):
    section = get_bare_act("mva").section(number)
    assert section.is_omitted
    assert section.body == ()
    assert section.rows == ()
    assert section.list_title == "Omitted"
    # UAPA's convention: the whole statement — former heading and amending
    # Act — is the canonical title; there is no separate note to stack.
    assert section.former_title is None
    assert section.omission_note is None
    assert section.omission_heading.startswith("[")
    assert "Omitted by" in section.omission_heading
    client, _ = _client(tmp_path)
    html = client.get(f"/laws/mva/section/{number}").text
    assert "Omitted by" in html
    assert 'class="bareact-omission-note"' not in html


def test_every_other_section_is_active_with_a_body():
    for section in get_bare_act("mva").section_order:
        if section.number not in OMITTED:
            assert not section.is_omitted, section.number
            assert section.rows, section.number


def test_chapter_x_is_printed_omitted_and_keeps_its_five_sections(tmp_path: Path):
    raw = next(c for c in _archival()["chapters"] if c["number"] == "X")
    assert raw["status"] == "omitted"
    assert raw["title"] == "LIABILITY WITHOUT FAULT IN CERTAIN CASES"
    assert raw["omission_note"] == (
        "Omitted by the Motor Vehicles (Amendment) Act, 2019 (32 of 2019) s. 50 (w.e.f. 1-4-2022)."
    )
    chapter = next(c for c in get_bare_act("mva").chapters if c.number == "X")
    assert [s.number for s in chapter.sections] == ["140", "141", "142", "143", "144"]
    assert all(s.is_omitted for s in chapter.sections)
    client, _ = _client(tmp_path)
    assert "Liability Without Fault in Certain Cases" in client.get("/laws/mva").text


def test_omission_runs_stand_in_their_lists_and_render_as_omitted(tmp_path: Path):
    runs = [r for r in _all_rows() if r.is_omission]
    assert len(runs) == 25
    assert all(r.kind == "omission" for r in runs)
    # s.2(8)'s first sub-clause is omitted; s.2(18) is omitted between (17) and (19).
    rows = _rows("2")
    eight = next(i for i, r in enumerate(rows) if r.label == "(8)")
    assert rows[eight + 1].is_omission and rows[eight + 1].depth == 2
    assert rows[eight + 2].label == "(b)"
    depth1 = [(r.label, r.kind) for r in rows if r.depth == 1]
    i17 = depth1.index(("(17)", "clause"))
    assert depth1[i17 + 1] == ("", "omission")
    assert depth1[i17 + 2] == ("(19)", "clause")
    client, _ = _client(tmp_path)
    assert "is-omission" in client.get("/laws/mva/section/2").text


# ── Amendment brackets ────────────────────────────────────────────────────


def test_chapter_xi_carries_the_amendment_bracket(tmp_path: Path):
    act = get_bare_act("mva")
    assert {c.number: c.leading_brackets for c in act.chapters if c.leading_brackets} == {"XI": 1}
    assert act.unbalanced_brackets() == ()
    html = client_html = _client(tmp_path)[0].get("/laws/mva").text
    assert '<span class="bareact-amendment-open">[</span>Chapter XI' in client_html


@pytest.mark.parametrize("number", AMENDED_OPENERS)
def test_amended_openers_keep_their_bracket_and_their_note(number: str):
    section = get_bare_act("mva").section(number)
    assert section.leading_brackets == 1
    annotations = _canonical_section(number)["title_annotations"]
    assert annotations and annotations[0]["note_id"]
    assert annotations[0]["note_id"] in get_bare_act("mva").footnotes


def test_every_inserted_section_carries_its_bracket_and_nothing_else_does():
    act = get_bare_act("mva")
    lb = {s.number for s in act.section_order if s.leading_brackets}
    assert set(AMENDED_OPENERS) <= lb
    assert len(lb) == AMENDED_OPENER_COUNT
    for number in lb:
        annotations = _canonical_section(number)["title_annotations"]
        assert annotations and annotations[0]["note_id"] in act.footnotes, number
    for number in ("1", "2", "66", "105", "194"):
        assert act.section(number).leading_brackets == 0


def test_the_bracket_stream_is_balanced_across_the_whole_act():
    validation = _archival()["_validation"]
    assert validation["bracket_open_count"] == validation["bracket_close_count"] == 325
    assert validation["bracket_problems"] == []


# ── Structures corrected during the parse ─────────────────────────────────


def test_section_2_is_one_definitions_list_under_its_lead():
    rows = _rows("2")
    assert rows[0].kind == "paragraph" and rows[0].depth == 0
    assert rows[0].text == "In this Act, unless context otherwise requires,—"
    assert all(r.depth >= 1 for r in rows[1:])
    depth1 = _labels(rows, 1)
    assert depth1[:8] == ["(1)", "(1A)", "(1B)", "(2)", "(3)", "(4)", "(4A)", "(5)"]
    assert depth1[-3:] == ["(47)", "(48)", "(49)"]
    # (9) is where the source shifts the list from the 108 band to the 90
    # band; it is still the next definition, not a new level.
    assert "(9)" in depth1 and "(9A)" in depth1 and "(42A)" in depth1
    labelled = [r for r in rows if r.depth == 1 and r.label]
    assert len(labelled) == 56
    assert all(r.kind == "clause" for r in labelled)


def test_section_2_7_owns_its_concluding_words_and_their_items():
    """"in either case" refers to (a) and (b) of the contract-carriage
    definition, and the maxicab/motor-cab items belong to it. The page sets
    these at the section band; a reviewed override (p.11) places them."""
    rows = _rows("2")
    seven = next(i for i, r in enumerate(rows) if r.label == "(7)")
    assert [(r.label, r.depth) for r in rows[seven + 1: seven + 3]] == [("(a)", 2), ("(b)", 2)]
    tail = rows[seven + 3]
    assert tail.kind == "paragraph" and tail.depth == 2
    assert tail.text.startswith("and in either case, without stopping")
    assert tail.text.endswith("and includes—")
    assert [(r.label, r.depth) for r in rows[seven + 4: seven + 6]] == [("(i)", 3), ("(ii)", 3)]
    assert rows[seven + 4].text == "a maxicab; and"
    assert (rows[seven + 6].label, rows[seven + 6].depth) == ("(8)", 1)
    node = next(c for c in _canonical_section("2")["body"][0]["children"] if c["label"] == "(7)")
    assert [c.get("label") or c["type"] for c in node["children"]] == ["(a)", "(b)", "paragraph"]


def test_section_8_6_has_three_sibling_provisos():
    rows = _rows("8")
    six = next(i for i, r in enumerate(rows) if r.label == "(6)")
    provisos = rows[six + 1: six + 4]
    assert [r.kind for r in provisos] == ["proviso"] * 3
    assert {r.depth for r in provisos} == {1}
    assert provisos[1].leading_brackets == 1
    assert provisos[1].text.startswith("Provided further that")
    assert provisos[2].text.endswith("prescribed by the Central Government.]")
    assert rows[six + 4].label == "(7)"


def test_section_66_1_has_four_provisos_and_the_span_closes_in_the_last():
    rows = _rows("66")
    one = rows[0]
    assert one.label == "(1)"
    provisos = [r for r in rows[1:6] if r.kind == "proviso"]
    assert len(provisos) == 4 and {r.depth for r in provisos} == {1}
    assert [r.leading_brackets for r in provisos] == [0, 0, 0, 1]
    assert provisos[3].text.endswith("at the discretion of the vehicle owner.]")


def test_section_93_2_clauses_printed_at_the_subsection_band_are_its_clauses():
    rows = _rows("93")
    two = next(i for i, r in enumerate(rows) if r.label == "(2)")
    clauses = [r for r in rows[two + 1:] if r.depth == 1 and r.kind == "clause"]
    assert [r.label for r in clauses[:6]] == ["(a)", "(b)", "(c)", "(d)", "(e)", "(f)"]
    c = next(r for r in rows if r.label == "(c)")
    assert [r.label for r in rows[rows.index(c) + 1: rows.index(c) + 3]] == ["(i)", "(ii)"]
    assert rows[rows.index(c) + 1].depth == 2


def test_section_96_2_lists_thirty_five_items_including_the_inserted_ones():
    rows = _rows("96")
    two = next(i for i, r in enumerate(rows) if r.label == "(2)")
    items = [r.label for r in rows[two + 1:] if r.depth == 1 and r.label]
    assert len(items) == 34
    # The 35th member is an omitted item, printed as an asterisk run.
    assert sum(1 for r in rows[two + 1:] if r.depth == 1 and r.is_omission) == 1
    assert items[:3] == ["(i)", "(ii)", "(iii)"]
    assert items[-6:] == ["(xxx)", "(xxxi)", "(xxxii)", "(xxxiia)", "(xxxiib)", "(xxxiii)"]
    thirty = next(r for r in rows if r.label == "(xxx)")
    assert "(xxxi)" not in thirty.text


def test_section_105_4_keeps_its_two_column_amounts_in_reading_order():
    rows = _rows("105")
    a = next(r for r in rows if r.label == "(a)")
    b = next(r for r in rows if r.label == "(b)")
    assert a.text.endswith("of the unexpired period of the permit Two hundred rupees;")
    assert b.text.endswith("period of the permit One hundred rupees:")


def test_section_105_5_formula_is_a_node_not_prose():
    rows = _rows("105")
    five = next(r for r in rows if r.label == "(5)")
    assert "Y A" not in five.text
    formula = next(r for r in rows if r.kind == "formula")
    assert formula.text == "(Y × A) / R"
    node = next(n for n in _walk(_canonical_section("105")["body"]) if n["type"] == "formula")
    # The × and the rule are drawn, not typed: the text layer is kept beside
    # the transcription, which names the page it was read from.
    assert node["formula_lines"] == ["Y A", "R"]
    assert node["drawings"], "the drawn fraction rule is recorded"
    assert node["transcription"]["expression"] == "(Y × A) / R"
    assert node["transcription"]["page"] == 72
    assert node["transcription"]["text_layer_lines"] == ["Y A", "R"]


def test_section_150_2_irregular_bands_nest_by_relative_geometry():
    rows = _rows("150")
    two = next(i for i, r in enumerate(rows) if r.label == "(2)")
    seq = [(r.label, r.depth, r.kind) for r in rows[two + 1: two + 8] if r.label]
    assert seq[:4] == [
        ("(a)", 1, "clause"), ("(i)", 2, "subclause"), ("(A)", 3, "item"), ("(B)", 3, "item"),
    ]
    labels = [r.label for r in rows[two + 1:] if r.label]
    assert labels.index("(ii)") > labels.index("(D)")
    assert labels.index("(b)") > labels.index("(iii)")


def test_section_193_keeps_its_printed_bracketed_marker():
    """The amendment that numbered s.193 as sub-section (1) is printed
    ``3[1]`` — no parentheses. The label is kept exactly as printed."""
    rows = _rows("193")
    assert (rows[0].label, rows[0].kind, rows[0].depth) == ("[1]", "subsection", 0)
    assert rows[0].text.startswith("Whoever engages himself as an agent or canvasser")
    assert [(r.label, r.leading_brackets) for r in rows[1:3]] == [("(2)", 1), ("(3)", 0)]


def test_section_194_1_owns_only_its_own_text():
    rows = _rows("194")
    one, proviso, one_a = rows[0], rows[1], rows[2]
    assert one.label == "(1)" and one.leading_brackets == 1
    assert one.text.endswith("charges for off-loading of the excess load.]")
    assert proviso.kind == "proviso" and proviso.leading_brackets == 1 and proviso.depth == 1
    assert proviso.text.endswith("in control of such motor vehicle.]")
    assert one_a.label == "(1A)" and one_a.leading_brackets == 1


def test_the_reviewed_ownership_overrides_are_recorded_and_applied():
    """Where geometry cannot decide, the owner is a reviewed decision with a
    page and a reason, not a logged anomaly."""
    overrides = _archival()["_validation"]["ownership_overrides"]
    assert [(o["section"], o["owner_label"], o["page"]) for o in overrides] == [
        ("2", "(7)", 11), ("47", "(ii)", 33), ("50", "(B)", 35), ("105", "(4)", 72),
    ]
    assert all(o["applied"] and o["reason"] for o in overrides)
    # s.47: "together with a declaration" accompanies (a) or (b) — sub-clause (ii)'s words.
    rows = _rows("47")
    i = next(k for k, r in enumerate(rows) if r.text.startswith("together with a declaration"))
    assert rows[i].kind == "paragraph"
    assert rows[i - 1].label == "(b)" and rows[i - 1].depth == rows[i].depth
    assert next(r for r in reversed(rows[:i]) if r.label == "(ii)").depth == rows[i].depth - 1
    # s.50: the same words under item (B).
    rows = _rows("50")
    i = next(k for k, r in enumerate(rows) if r.text.startswith("together with a declaration"))
    assert next(r for r in reversed(rows[:i]) if r.label == "(B)").depth == rows[i].depth - 1
    assert _archival()["_validation"]["reading_order_violations"] == 0


# ── Footnotes ─────────────────────────────────────────────────────────────


def test_every_footnote_is_loaded_and_every_anchor_resolves():
    act = get_bare_act("mva")
    assert len(act.footnotes) == 309
    validation = _archival()["_validation"]
    assert validation["source_footnotes"] == 309
    assert validation["footnote_anchors_source"] == validation["footnote_anchors_attached"] == 355
    assert validation["footnote_anchors_unlinked"] == 0
    assert validation["footnote_notes_unlinked"] == 0
    via_rows = {sg.note_id for r in _all_rows() for sg in r.segments if sg.note_id}
    assert via_rows <= set(act.footnotes)
    # Rows see body anchors only; titles, chapter headings, omission runs and
    # schedule headings carry the rest. Together they reach every note.
    everywhere = set()
    for chapter in _archival()["chapters"]:
        everywhere |= {a["note_id"] for a in chapter.get("title_annotations") or []}
        for section in chapter["sections"]:
            everywhere |= {a["note_id"] for a in section.get("title_annotations") or []}
            for node in _walk(section["body"]):
                everywhere |= {a["note_id"] for a in node.get("annotations") or []}
                everywhere |= {a["note_id"] for a in node.get("label_annotations") or []}
    for schedule in _archival()["schedules"]:
        everywhere |= {a["note_id"] for a in schedule.get("heading_annotations") or []}
    assert everywhere == set(act.footnotes)


def test_section_1_3_anchors_the_word_date():
    act = get_bare_act("mva")
    row = next(r for r in _rows("1") if r.label == "(3)")
    assert [(sg.text, sg.note_id) for sg in row.segments][1] == ("date", "footnote_p10_1")
    assert act.footnotes["footnote_p10_1"].text.startswith("1. 1st July, 1989, vide Notifn.")
    assert act.section("1").note_ids == ("footnote_p10_1",)


def test_a_span_crossing_a_page_keeps_the_note_from_the_page_that_printed_it():
    validation = _archival()["_validation"]
    assert validation["footnote_anchors_linked_to_previous_page"] == [
        {"page": 67, "marker": "3", "note_id": "footnote_p66_3"}
    ]
    carried = [
        a
        for chapter in _archival()["chapters"]
        for section in chapter["sections"]
        for node in _walk(section["body"])
        for a in node.get("annotations") or []
        if a.get("note_on_previous_page")
    ]
    assert len(carried) == 1
    assert carried[0]["anchor_text"] == "[or licence issued under any scheme]"


def test_the_footnote_card_is_wired_on_a_section_page(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/mva/section/1").text
    assert 'data-bareact-fn="footnote_p10_1"' in html
    assert 'aria-describedby="fn-footnote_p10_1"' in html
    assert '<p id="fn-footnote_p10_1">' in html
    assert "data-bareact-fn-card" in html


# ── Independent audit of v2 (2026-09-23): the twelve failed assertions ────


@pytest.mark.parametrize("number, parent, children", [
    ("71", "(3)", ["(a)", "(b)", "(c)", "(d)"]),
    ("74", "(3)", ["(a)", "(b)"]),
    ("88", "(14)", ["(a)", "(b)"]),
    ("116", "(1)", ["(a)", "(b)"]),
])
def test_a_marker_chain_on_one_line_keeps_its_level(number: str, parent: str, children: list[str]):
    """"(3) (a) The State Government ..." is two markers. v2 left (a) in
    (3)'s text and filed (b) beside (3); every clause belongs to (3)."""
    node = next(n for n in _canonical_section(number)["body"] if n.get("label") == parent)
    assert node["text"] == ""
    assert [c["label"] for c in node["children"] if c.get("label")][: len(children)] == children
    assert not any(n.get("label") in children[1:] for n in _canonical_section(number)["body"])
    rows = _rows(number)
    p = next(i for i, r in enumerate(rows) if r.label == parent)
    assert [r.label for r in rows[p + 1: p + 1 + len(children)]] == children
    assert {r.depth for r in rows[p + 1: p + 1 + len(children)]} == {rows[p].depth + 1}


def test_section_9_3_first_proviso_clause_a_owns_its_three_subclauses():
    rows = _rows("9")
    a = next(i for i, r in enumerate(rows) if r.label == "(a)" and r.text == "")
    # Under the first proviso to (3), so a sub-clause; its items sit one deeper.
    assert rows[a].kind == "subclause" and rows[a - 1].kind == "proviso"
    assert [(r.label, r.depth) for r in rows[a + 1: a + 4]] == [
        ("(i)", rows[a].depth + 1), ("(ii)", rows[a].depth + 1), ("(iii)", rows[a].depth + 1),
    ]
    assert rows[a + 1].text.startswith("the applicant has previously held a driving licence")
    assert rows[a + 4].label == "(b)" and rows[a + 4].depth == rows[a].depth
    # "Provided further" continues the chain: the next proviso to (3), not to (b).
    further = next(r for r in rows[a + 5:] if r.kind == "proviso")
    assert further.text.startswith("Provided further") and further.depth == rows[a - 1].depth


def test_section_2_42_explanation_belongs_to_the_definition_not_the_last_alternative():
    node = next(c for c in _canonical_section("2")["body"][0]["children"] if c["label"] == "(42)")
    assert [c.get("label") or c["type"] for c in node["children"]] == ["(i)", "(ii)", "(iii)", "(iv)", "Explanation"]
    expl = node["children"][-1]
    assert expl["text"].startswith("For the purposes of this clause")
    assert expl["scope_declared"] == "clause"


def test_section_150_explanation_is_section_wide():
    assert [n.get("label") or n["type"] for n in _canonical_section("150")["body"]] == [
        "(1)", "(2)", "(3)", "(4)", "(5)", "(6)", "Explanation",
    ]
    rows = _rows("150")
    expl = next(r for r in rows if r.kind == "explanation")
    assert expl.depth == 0 and expl.text == "For the purposes of this section,—"


def test_section_71_explanation_is_not_part_of_omitted_material():
    body = _canonical_section("71")["body"]
    assert [n.get("label") or n["type"] for n in body] == ["(1)", "omission", "(2)", "(3)", "Explanation"]
    assert all(not n["children"] for n in body if n["type"] == "omission")
    assert body[-1]["text"].startswith("For the purposes of this section")


def test_section_105_4_minimum_compensation_qualifies_the_subsection():
    four = next(n for n in _canonical_section("105")["body"] if n.get("label") == "(4)")
    assert [c.get("label") or c["type"] for c in four["children"]] == ["(a)", "(b)", "proviso"]
    rows = _rows("105")
    proviso = next(r for r in rows if r.text.startswith("Provided that the amount of compensation shall, in no case"))
    assert proviso.depth == next(r for r in rows if r.label == "(4)").depth + 1


def test_explanations_are_owned_by_their_printed_scope():
    scopes = _archival()["_validation"]["explanation_scopes"]
    assert len(scopes) == 32
    moved = {e["section"] for e in scopes if e["owner_before"] != e["owner_after"]}
    assert moved == {"2", "52", "70", "71", "88", "124", "134", "134A", "136A", "150", "178", "184",
                     "185", "198A", "199", "199A", "201", "203", "204"}
    # s.70's section-wide Explanation is printed between clauses (c) and (d)
    # of sub-section (1); moving it would reorder the statute, so it stays,
    # with its scope recorded.
    partial = [e for e in scopes if "raised as far as reading order allows" in e["basis"]]
    assert [(e["section"], e["scope"], e["owner_after"]) for e in partial] == [("70", "section", "subsection (1)")]
    assert not [e for e in scopes if "kept in place" in e["basis"]]
    one = _canonical_section("70")["body"][0]
    assert [c.get("label") or c["type"] for c in one["children"]] == ["(a)", "(b)", "(c)", "Explanation", "(d)", "(e)", "(f)"]
    assert one["children"][3]["scope_declared"] == "section"
    assert [e["section"] for e in scopes if e["scope"] is None] == ["89", "100", "129", "147", "157", "165", "192"]


@pytest.mark.parametrize("number, label, note_id", [("27", "(aa)", "footnote_p26_2"), ("99", "(1)", "footnote_p69_2")])
def test_a_note_printed_against_a_bracketed_label_targets_the_label(tmp_path: Path, number: str, label: str, note_id: str):
    """"2[(aa)]" — the amendment renumbered the label itself. The note is
    stored against the label, with a non-empty range, and the reader anchors
    the label."""
    node = next(n for n in _walk(_canonical_section(number)["body"]) if n.get("label") == label)
    assert not node.get("annotations")
    assert node["label_annotations"] == [{
        "type": "footnote", "marker": "2", "note_id": note_id, "target": "label",
        "start": 0, "end": len(label), "anchor_text": label, "source_page": int(note_id.split("_p")[1].split("_")[0]),
    }]
    row = next(r for r in _rows(number) if r.label == label)
    assert row.label_note_id == note_id
    client, _ = _client(tmp_path)
    html = client.get(f"/laws/mva/section/{number}").text
    assert f'data-bareact-fn="{note_id}"' in html
    assert f'<p id="fn-{note_id}">' in html


def test_every_body_annotation_covers_a_non_empty_range():
    for section in (s for ch in _archival()["chapters"] for s in ch["sections"]):
        for node in _walk(section["body"]):
            for a in node.get("annotations") or []:
                assert 0 <= a["start"] < a["end"] <= len(node["text"]), (section["number"], node.get("label"), a)
    assert _archival()["_validation"]["label_annotations"] == 2
    assert _archival()["_validation"]["inline_marker_chain_mismatches"] == []


# ── State amendments ──────────────────────────────────────────────────────


def test_state_amendments_are_preserved_whole_and_kept_out_of_the_statute():
    blocks = _archival()["source_state_amendments"]
    assert len(blocks) == 6
    entries = [(b["source_pages"][0], e["state"], e["amends_section"]) for b in blocks for e in b["entries"]]
    assert entries == STATE_AMENDMENTS
    assert all(e["vide"].startswith("[Vide") for b in blocks for e in b["entries"])
    assert all(e["text"].startswith("Amendment of") for b in blocks for e in b["entries"])
    for row in _all_rows():
        assert "[Vide" not in row.text
        assert "STATE AMENDMENT" not in row.text
        assert "Karnataka Act" not in row.text
    for section in get_bare_act("mva").section_order:
        assert "Amendment of section" not in section.title


def test_the_ten_point_sections_after_a_state_insert_are_principal_text():
    rows = _rows("104")
    assert rows[0].text.startswith("Where a scheme has been published under sub-section (3) of section 100")
    assert get_bare_act("mva").section("105").rows[0].label == "(1)"


# ── Schedules ─────────────────────────────────────────────────────────────


def test_both_schedules_are_listed_but_not_browsable(tmp_path: Path):
    act = get_bare_act("mva")
    assert [(s.number, s.kind, s.is_navigable) for s in act.schedules] == [
        ("First", "unsupported", False), ("Second", "unsupported", False),
    ]
    client, _ = _client(tmp_path)
    html = client.get("/laws/mva").text
    assert "FIRST SCHEDULE" in html and "SECOND SCHEDULE" in html
    assert "Mandatory Signs" in html and "Schedule for Compensation" in html
    assert html.count("Not yet browsable in the app") == 2
    assert 'href="/laws/mva/schedule/' not in html
    assert "This Act has no Schedules." not in html


def test_first_schedule_keeps_its_identity_and_explanatory_notes():
    first = _archival()["schedules"][0]
    assert first["content_type"] == "visual_road_signs"
    assert first["title"] == "MANDATORY SIGNS OF SCHEDULE OF THE MOTOR VEHICLES ACT, 1988"
    assert first["heading"] == first["title"]
    assert first["printed_heading"] == "[[THE FIRST SCHEDULE]]"
    assert [a["note_id"] for a in first["heading_annotations"]] == ["footnote_p121_1", "footnote_p121_2"]
    assert [p["page"] for p in first["image_pages"]] == list(range(121, 173))
    assert first["source_pages"] == list(range(121, 174))
    assert first["explanatory_notes_text"].startswith("“Explanatory Notes”")
    assert "Normal size" in first["explanatory_notes_text"]


def test_second_schedule_is_omitted_with_its_printed_statement():
    second = _archival()["schedules"][1]
    assert second["status"] == "omitted"
    assert second["title"] == "Schedule for compensation for third party fatal accidents/injury cases claims"
    assert second["omission_note"].endswith("s. 93 (w.e.f. 1-4-2022).")
    assert second["printed_heading"] == "THE SECOND SCHEDULE"
    assert second["heading"] == second["title"]
    assert second["heading_annotations"][0]["note_id"] == "footnote_p174_1"


# ── Rendering ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("kind", KINDS)
def test_every_node_kind_reaches_a_page(tmp_path: Path, kind: str):
    act = get_bare_act("mva")
    hit = next((s for s in act.section_order if any(r.kind == kind for r in s.rows)), None)
    assert hit is not None, kind
    client, _ = _client(tmp_path)
    assert client.get(f"/laws/mva/section/{hit.number}").status_code == 200


def test_no_whitespace_damage_from_removed_anchors_or_span_joins():
    """One hit is the source's own: s.51(12) prints "registering .authority",
    a stray period in the text layer. It is kept as printed, not repaired."""
    hits = [(s.number, row.text) for s in get_bare_act("mva").section_order
            for row in s.rows if re.search(r"\s[,;.](?!\.)", row.text)]
    assert len(hits) == 1
    assert hits[0][0] == "51" and "registering .authority" in hits[0][1]
    for row in _all_rows():
        assert "\ufffe" not in row.text
        assert "  " not in row.text


def test_the_archived_validation_earned_its_pass():
    v = _archival()["_validation"]
    assert v["status"] == "PASS"
    assert v["pages"] == 176
    assert v["coverage_percent"] == 100.0
    assert v["statutory_blocks_unmatched"] == 0
    assert v["source_blocks_unmatched"] == 0
    assert v["marker_reconciled"] is True
    assert v["deterministic_two_runs"] is True
    assert v["unrecognised_paren_tokens"] == []
    assert v["state_amendment_blocks"] == 6
    assert v["omission_runs"] == 25
    assert v["repairs_by_type"] == {"span_gap_space": v["repairs_total"]}


# ── Catalogue ─────────────────────────────────────────────────────────────


def test_mva_is_catalogued_under_administrative():
    from constitution_memorizer.web.law_catalog import load_catalog

    catalog = load_catalog()
    law = catalog.by_full_act("mva")
    assert law is not None
    assert law.id == "mva"
    assert law.primary_subject == "administrative"
    assert law.subjects == ("administrative",)
    assert law.href == "/laws/mva"
    assert law.primary_content == "full_act"
    assert law.is_current and law.status_label == ""


def test_the_catalogue_entry_is_derived_from_the_act():
    from constitution_memorizer.web.law_catalog import load_catalog

    law = load_catalog().by_full_act("mva")
    act = get_bare_act("mva")
    assert law.scope_label == act.meta_label
    assert law.title == act.title


@pytest.mark.parametrize("query", ["mva", "mv act", "motor vehicles act 1988", "driving licence", "traffic"])
def test_mva_is_searchable(query: str):
    from constitution_memorizer.web.law_catalog import load_catalog

    assert query in load_catalog().by_full_act("mva").search_blob


def test_mva_appears_on_the_catalogue_page(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws").text
    assert 'data-law-id="mva"' in html
    assert 'href="/laws/mva"' in html


def test_mva_is_free_to_read_and_records_nothing(tmp_path: Path):
    client, engine = _client(tmp_path)
    before = engine.stats()
    for path in (
        "/laws", "/laws/mva", "/laws/mva/section/1", "/laws/mva/section/2",
        "/laws/mva/section/105", "/laws/mva/section/140", "/laws/mva/section/217A",
    ):
        assert client.get(path).status_code == 200, path
    assert engine.stats() == before
    assert engine.due_today() == []


# ── Runtime artifact ──────────────────────────────────────────────────────


def test_runtime_is_the_canonical_minus_the_x_coordinate():
    archival = _archival()
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))

    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k != "source_x"}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    assert runtime == strip(archival)


def test_the_runtime_keeps_what_the_reader_may_later_need():
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    assert len(runtime["footnotes"]) == 309
    assert len(runtime["source_state_amendments"]) == 6
    assert len(runtime["schedules"]) == 2
    for key in ("source_front_matter", "source_supplementary_material", "long_title",
                "enacting_formula", "_validation"):
        assert runtime[key], key
    assert runtime["long_title"] == "An Act to consolidate and amend the law relating to motor vehicles."
    assert runtime["document"]["source_as_on"] == "15th August, 2026"
    assert runtime["document"]["act_number"] == "59 of 1988"


def test_the_script_regenerates_the_committed_runtime_file():
    before = RUNTIME.read_bytes()
    subprocess.run(
        [sys.executable, str(REPO / "scripts" / "strip_bare_act_debug.py")],
        cwd=REPO,
        check=True,
        capture_output=True,
    )
    assert RUNTIME.read_bytes() == before


def test_runtime_copy_is_declared_as_package_data():
    assert '"web/mva_runtime_v1.json"' in (REPO / "pyproject.toml").read_text(encoding="utf-8")


def test_the_registry_entry_matches_the_shipped_artifact():
    spec = BARE_ACTS["mva"]
    assert spec.filename == RUNTIME.name
    assert spec.render_profile == "bns"
    assert spec.short_title == "MVA"
    assert spec.patch_filenames == ()
    assert spec.source_version == "1"


def test_the_sitemap_inventory_has_every_section_and_no_schedule():
    manifest = json.loads(
        (REPO / "src" / "constitution_memorizer" / "web" / "law_sitemap_manifest.json").read_text(encoding="utf-8")
    )
    entry = manifest["laws"]["mva"]
    assert entry["sections"] == [s.number for s in get_bare_act("mva").section_order]
    assert len(entry["sections"]) == 257
    assert entry["schedules"] == []
    assert entry["runtime_identity"] == "mva:1:mva_runtime_v1.json"


def test_the_act_and_its_sections_are_in_the_served_sitemap(tmp_path: Path):
    client, _ = _client(tmp_path)
    assert "sitemap-laws-mva.xml" in client.get("/sitemap.xml").text
    xml = client.get("/sitemap-laws-mva.xml").text
    assert xml.count("<loc>") == 1 + 257
    assert "/laws/mva</loc>" in xml
    assert "/laws/mva/section/217A</loc>" in xml
    assert "/schedule/" not in xml
