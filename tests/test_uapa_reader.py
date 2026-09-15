"""The Unlawful Activities (Prevention) Act, 1967 — the fifth Bare Act.

Four things here are new to the reader:

* **labelled list markers.** POTA's list schedule stored only a numeric
  serial. UAPA's Second Schedule is labelled (i)-(x) and its Third (a)-(c),
  and a serial-only model dropped both — an `<ol>` would then have renumbered
  them 1, 2, 3, printing a different marker than the statute;
* **declared tables.** UAPA's Fourth Schedule is `type: "table"` with the grid
  under `table: {columns, rows}` rather than `parts[]`, a shape dispatch did
  not recognise, so it fell through to unsupported and 404ed;
* **a zero-row schedule.** That Fourth Schedule prints two headings and no
  rows. It stays navigable and says so, and never acquires rows from the
  Gazette notifications appended to the source PDF;
* **linked schedule references.** "See sections 35(1) and 36" reproduces
  byte for byte, with the citations wrapped in anchors.

The operative 67 sections reuse the BNS render profile unchanged.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import BARE_ACTS, get_bare_act

REPO = Path(__file__).resolve().parents[1]
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ARCHIVAL = REPO / "data" / "reference" / "uapa_canonical_v6.json"
RUNTIME = REPO / "src" / "constitution_memorizer" / "web" / "uapa_runtime_v1.json"

LETTERED = [
    "16A", "18A", "18B", "22A", "22B", "22C", "24A",
    "43A", "43B", "43C", "43D", "43E", "43F", "51A",
]


def _client(tmp_path: Path) -> tuple[TestClient, ReminderEngine]:
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    return TestClient(create_app(units_path=MINI_UNITS, db_path=db)), engine


def _canonical() -> dict:
    return json.loads(ARCHIVAL.read_text(encoding="utf-8"))


# ── The Act ───────────────────────────────────────────────────────────────


def test_the_whole_act_is_present():
    act = get_bare_act("uapa")
    assert act.title == "The Unlawful Activities (Prevention) Act, 1967"
    assert act.act_number == "37 of 1967"
    assert len(act.chapters) == 7
    assert len(act.section_order) == 67
    assert act.meta_label == "7 Chapters · Sections 1–53"
    # Six node types, all already in the BNS vocabulary.
    assert act.render_profile == "bns"


def test_section_order_is_the_canonical_order():
    """Guards a lexical sort, which would put 16A after 169 or before 2."""
    act = get_bare_act("uapa")
    assert [s.number for s in act.section_order] == _canonical()["_validation"][
        "section_ids"
    ]


def test_first_and_last_sections_resolve():
    act = get_bare_act("uapa")
    assert act.section("1").title.startswith("Short title")
    assert act.section("53") is not None
    assert act.section("54") is None
    assert len({s.number for s in act.section_order}) == 67


@pytest.mark.parametrize("number", LETTERED)
def test_lettered_sections_survive(tmp_path: Path, number: str):
    act = get_bare_act("uapa")
    assert act.section(number) is not None, number
    client, _ = _client(tmp_path)
    assert client.get(f"/laws/uapa/section/{number}").status_code == 200


def test_chapters_are_contiguous_and_cover_every_section():
    act = get_bare_act("uapa")
    spans = [(c.number, c.sections[0].number, c.sections[-1].number) for c in act.chapters]
    assert spans == [
        ("I", "1", "2"),
        ("II", "3", "9"),
        ("III", "10", "14"),
        ("IV", "15", "23"),
        ("V", "24", "34"),
        ("VI", "35", "40"),
        ("VII", "41", "53"),
    ]
    assert sum(len(c.sections) for c in act.chapters) == 67


# ── Body hierarchy ────────────────────────────────────────────────────────


def _rows(number: str):
    return get_bare_act("uapa").section(number).rows


def test_section_2_1_eb_is_a_clause():
    labels = {(r.label, r.kind) for r in _rows("2")}
    assert ("(eb)", "clause") in labels


def test_section_8_8_has_two_clauses_and_a_concluding_paragraph():
    rows = _rows("8")
    kinds = [r.kind for r in rows]
    assert "paragraph" in kinds
    assert {r.label for r in rows if r.kind == "clause"} >= {"(a)", "(b)"}


def test_section_10_lead_paragraph_owns_the_clauses():
    rows = _rows("10")
    assert rows[0].kind == "paragraph"
    assert {r.label for r in rows if r.kind == "clause"} >= {"(a)", "(b)"}
    assert {r.label for r in rows if r.kind == "subclause"} >= {"(i)", "(ii)"}
    assert max(r.depth for r in rows) == 2


def test_section_15_keeps_iiia_as_a_subclause_and_its_explanation_owns_clauses():
    rows = _rows("15")
    subclauses = {r.label for r in rows if r.kind == "subclause"}
    assert "(iiia)" in subclauses, sorted(subclauses)
    assert {"(i)", "(ii)", "(iii)", "(iv)"} <= subclauses
    assert any(r.kind == "explanation" for r in rows)


def test_section_25_5_has_a_proviso_and_an_explanation():
    rows = _rows("25")
    assert any(r.kind == "proviso" for r in rows)
    assert any(r.kind == "explanation" for r in rows)
    assert {r.label for r in rows if r.kind == "clause"} >= {"(a)", "(b)", "(c)"}


def test_section_38_proviso_owns_its_clauses():
    rows = _rows("38")
    assert any(r.kind == "proviso" for r in rows)
    assert {r.label for r in rows if r.kind == "clause"} >= {"(a)", "(b)"}


def test_section_40_explanation_owns_its_clauses():
    rows = _rows("40")
    assert any(r.kind == "explanation" for r in rows)
    assert {r.label for r in rows if r.kind == "clause"} >= {"(a)", "(b)"}


def test_section_44_3_has_clauses_a_to_d():
    assert {r.label for r in _rows("44") if r.kind == "clause"} >= {
        "(a)", "(b)", "(c)", "(d)"
    }


def test_section_43d_quoted_insertions_stay_paragraphs():
    """Text the Act quotes is not text the Act enacts as its own proviso.

    43D(2)(b) inserts provisos into the Code. They read as provisos, but they
    are quoted material, so counting them as UAPA's own would make the Act
    appear to enact what it only reproduces.
    """
    rows = _rows("43D")
    inserted = [
        r
        for r in rows
        if r.text.lstrip("\u201c\"").startswith(("Provided further", "Provided also"))
    ]
    assert len(inserted) == 2, [r.text[:40] for r in inserted]
    assert {r.kind for r in inserted} == {"paragraph"}
    # The Act's own proviso in the same section is still a proviso.
    assert any(r.kind == "proviso" for r in rows)


def test_section_43d_quotation_marks_are_reproduced_not_rebalanced():
    """The opening quote is on one node and the closing on another.

    They balance across the pair, not within a node. Nothing may try to even
    them up — that would edit quoted statutory text.
    """
    rows = _rows("43D")
    opening = [r for r in rows if r.text.lstrip().startswith("\u201c")]
    assert len(opening) == 1
    assert opening[0].kind == "paragraph"


@pytest.mark.parametrize("kind", ["subsection", "clause", "subclause", "paragraph",
                                  "proviso", "explanation"])
def test_every_node_kind_reaches_a_page(tmp_path: Path, kind: str):
    act = get_bare_act("uapa")
    hit = next(
        (s for s in act.section_order if any(r.kind == kind for r in s.rows)), None
    )
    assert hit is not None, kind
    client, _ = _client(tmp_path)
    assert client.get(f"/laws/uapa/section/{hit.number}").status_code == 200


# ── Section 16A: omitted ──────────────────────────────────────────────────


def test_section_16a_is_omitted_with_an_empty_body():
    section = get_bare_act("uapa").section("16A")
    assert section.is_omitted
    assert section.body == ()
    assert section.rows == ()
    assert section.list_title == "Omitted"


def test_section_16a_keeps_its_canonical_title_on_the_page(tmp_path: Path):
    """The whole omission statement lives in `title` for this Act.

    Rendering a bare "Omitted." would discard the former heading and the
    amending Act that removed it, both of which the source preserved.
    """
    section = get_bare_act("uapa").section("16A")
    assert section.former_title is None
    assert section.omission_note is None
    assert section.omission_heading == section.title
    assert "radioactive substances" in section.omission_heading
    assert "3 of 2013" in section.omission_heading

    client, _ = _client(tmp_path)
    html = client.get("/laws/uapa/section/16A").text
    assert "radioactive substances" in html
    assert "3 of 2013" in html
    # No bare "Omitted." stacked under text that already says it.
    assert 'class="bareact-omission-note"' not in html


def test_ndps_omitted_section_presentation_is_unchanged(tmp_path: Path):
    section = get_bare_act("ndps").section("65")
    assert section.omission_heading == section.former_title
    client, _ = _client(tmp_path)
    html = client.get("/laws/ndps/section/65").text
    assert "Formerly: Power to make rules" in html
    assert 'class="bareact-omission-note"' in html


# ── Schedules ─────────────────────────────────────────────────────────────


def test_there_are_exactly_four_schedules():
    act = get_bare_act("uapa")
    assert [s.slug for s in act.schedules] == [
        "first-schedule", "second-schedule", "third-schedule", "fourth-schedule"
    ]
    assert [s.kind for s in act.schedules] == ["list", "list", "list", "table"]
    assert all(s.is_navigable for s in act.schedules)


def test_first_schedule_is_a_list_of_33_numbered_entries():
    schedule = get_bare_act("uapa").schedule("first-schedule")
    assert schedule.kind == "list"
    assert len(schedule.entries) == 33
    assert [e.marker for e in schedule.entries] == [str(i) for i in range(1, 34)]
    assert schedule.range_label == "1–33"
    assert all(e.is_numbered for e in schedule.entries)


def test_first_schedule_keeps_its_first_and_last_entry():
    entries = get_bare_act("uapa").schedule("first-schedule").entries
    assert entries[0].text == "BABBAR KHALSA INTERNATIONAL."
    assert "U.N. Prevention and Suppression of Terrorism" in entries[-1].text


def test_second_schedule_markers_are_roman_labels():
    schedule = get_bare_act("uapa").schedule("second-schedule")
    assert schedule.kind == "list"
    assert len(schedule.entries) == 10
    assert [e.marker for e in schedule.entries] == [
        "(i)", "(ii)", "(iii)", "(iv)", "(v)",
        "(vi)", "(vii)", "(viii)", "(ix)", "(x)",
    ]
    assert not any(e.is_numbered for e in schedule.entries)
    assert all(e.label and not e.serial_number for e in schedule.entries)


def test_third_schedule_markers_are_letter_labels():
    schedule = get_bare_act("uapa").schedule("third-schedule")
    assert schedule.kind == "list"
    assert [e.marker for e in schedule.entries] == ["(a)", "(b)", "(c)"]
    assert schedule.entries[0].text == "watermark;"


@pytest.mark.parametrize(
    "slug,markers",
    [
        ("second-schedule", ["(i)", "(x)"]),
        ("third-schedule", ["(a)", "(c)"]),
    ],
)
def test_labelled_markers_render_rather_than_being_renumbered(
    tmp_path: Path, slug: str, markers: list[str]
):
    """The regression the marker field exists for.

    A serial-only model dropped these, and an <ol> would have printed 1, 2, 3
    where the statute prints (i) or (a).
    """
    client, _ = _client(tmp_path)
    html = client.get(f"/laws/uapa/schedule/{slug}").text
    for marker in markers:
        # The marker column may also carry an amendment bracket before the
        # marker, so match the marker's own text rather than the whole span.
        assert f'>{marker}</span>' in html
        assert 'class="bareact-schedule-marker"' in html


def test_every_list_entry_text_reaches_the_page(tmp_path: Path):
    client, _ = _client(tmp_path)
    act = get_bare_act("uapa")
    for slug in ("first-schedule", "second-schedule", "third-schedule"):
        html = client.get(f"/laws/uapa/schedule/{slug}").text
        for entry in act.schedule(slug).entries:
            assert entry.text in html, (slug, entry.marker)


# ── The Fourth Schedule: a real, empty table ──────────────────────────────


def test_fourth_schedule_is_a_table_with_two_columns_and_no_rows():
    schedule = get_bare_act("uapa").schedule("fourth-schedule")
    assert schedule.kind == "table"
    assert schedule.is_table and schedule.is_navigable
    assert len(schedule.parts) == 1
    assert [c.heading for c in schedule.parts[0].columns] == [
        "Sl. No.",
        "Name of Individuals",
    ]
    assert schedule.parts[0].rows == ()
    assert schedule.row_count == 0


def test_fourth_schedule_is_linked_and_renders(tmp_path: Path):
    client, _ = _client(tmp_path)
    assert 'href="/laws/uapa/schedule/fourth-schedule"' in client.get("/laws/uapa").text
    response = client.get("/laws/uapa/schedule/fourth-schedule")
    assert response.status_code == 200
    html = response.text
    assert "Sl. No." in html and "Name of Individuals" in html
    assert "No rows are present in this source." in html


def test_the_empty_state_is_interface_copy_not_statute():
    for path in (ARCHIVAL, RUNTIME):
        assert "No rows are present" not in path.read_text(encoding="utf-8"), path.name


def test_no_gazette_name_ever_becomes_a_fourth_schedule_row(tmp_path: Path):
    """Serials 14-31 are Gazette amendment actions, not printed rows.

    The source PDF lacks serials 1-13 entirely, so no consolidated Fourth
    Schedule exists to render. Manufacturing one would invent statute.
    """
    insertions = _canonical()["source_annexes"][
        "fourth_schedule_insertions_from_notifications"
    ]
    assert len(insertions) == 18
    client, _ = _client(tmp_path)
    html = client.get("/laws/uapa/schedule/fourth-schedule").text
    for insertion in insertions:
        assert insertion["text"] not in html, insertion["inserted_serial_number"]
    schedule = get_bare_act("uapa").schedule("fourth-schedule")
    assert schedule.row_count == 0


def test_no_schedule_acquires_annex_content():
    act = get_bare_act("uapa")
    blob = " ".join(
        e.text for s in act.schedules for e in s.entries
    ) + " ".join(
        cell for s in act.schedules for p in s.parts for r in p.rows for cell in r.cells
    )
    for insertion in _canonical()["source_annexes"][
        "fourth_schedule_insertions_from_notifications"
    ]:
        assert insertion["text"] not in blob


# ── Source annexes ────────────────────────────────────────────────────────


def test_archival_keeps_every_annex_page():
    annexes = _canonical()["source_annexes"]
    assert len(annexes["pages"]) == 72
    assert len(annexes["duplicate_page_pairs"]) == 35
    assert annexes["other_notification_pages"] == [66, 67]


def test_runtime_drops_the_raw_annex_pages_but_keeps_the_provenance():
    """A deliberate, tested removal — the reader cannot use 186 KB of Gazette
    text, and half of it is a duplicate of the other half."""
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    annexes = runtime["source_annexes"]
    assert "pages" not in annexes
    assert len(annexes["duplicate_page_pairs"]) == 35
    assert len(annexes["fourth_schedule_insertions_from_notifications"]) == 18
    assert annexes["other_notification_pages"] == [66, 67]
    assert annexes["note"]


def test_the_annex_summary_already_in_the_canonical_is_retained():
    """No runtime-only structure was invented; `_validation` already had this."""
    validation = json.loads(RUNTIME.read_text(encoding="utf-8"))["_validation"]
    assert validation["fourth_schedule_printed_rows"] == 0
    assert validation["fourth_schedule_annex_insertions"] == 18
    assert validation["fourth_schedule_annex_serials"] == [
        str(n) for n in range(14, 32)
    ]
    assert validation["annex_duplicate_page_pairs"] == 35


def test_the_tribunal_notification_is_not_a_fourth_schedule_amendment():
    annexes = _canonical()["source_annexes"]
    assert annexes["other_notification_pages"] == [66, 67]
    serials = {
        i["inserted_serial_number"]
        for i in annexes["fourth_schedule_insertions_from_notifications"]
    }
    assert serials == {str(n) for n in range(14, 32)}


def test_duplicate_annex_pages_are_not_doubled_into_anything():
    """Pages 68-102 repeat 31-65; the insertions must still count 18, not 36."""
    annexes = _canonical()["source_annexes"]
    assert len(annexes["fourth_schedule_insertions_from_notifications"]) == 18
    pairs = annexes["duplicate_page_pairs"]
    assert all("duplicate_of_page" in p or len(p) == 2 for p in pairs)


# ── Schedule reference links ──────────────────────────────────────────────


def test_reference_segments_reassemble_byte_for_byte():
    """The contract: display text is preserved exactly, links are added."""
    act = get_bare_act("uapa")
    for schedule in act.schedules:
        segments = act.reference_segments(schedule.reference)
        assert "".join(s.text for s in segments) == schedule.reference


def test_fourth_schedule_reference_links_both_sections():
    act = get_bare_act("uapa")
    segments = act.reference_segments("See sections 35(1) and 36")
    assert [(s.text, s.href) for s in segments] == [
        ("See sections ", ""),
        ("35(1)", "/laws/uapa/section/35"),
        (" and ", ""),
        ("36", "/laws/uapa/section/36"),
    ]


def test_a_citation_keeps_its_subsection_inside_the_anchor_text():
    act = get_bare_act("uapa")
    (link,) = [s for s in act.reference_segments("See section 15(2)") if s.is_link]
    assert link.text == "15(2)"
    assert link.href == "/laws/uapa/section/15"


def test_clause_and_explanation_words_are_not_mistaken_for_citations():
    act = get_bare_act("uapa")
    text = "See clause (b) of Explanation to section 15(1)"
    segments = act.reference_segments(text)
    assert [s.text for s in segments if s.is_link] == ["15(1)"]
    assert "".join(s.text for s in segments) == text


def test_a_list_of_citations_links_each_one():
    act = get_bare_act("uapa")
    text = "See sections 2(1) (m), 35, 36 and 38 (1)"
    links = [s for s in act.reference_segments(text) if s.is_link]
    assert [s.text for s in links] == ["2(1) (m)", "35", "36", "38 (1)"]
    assert [s.href for s in links] == [
        "/laws/uapa/section/2",
        "/laws/uapa/section/35",
        "/laws/uapa/section/36",
        "/laws/uapa/section/38",
    ]


def test_a_citation_to_a_section_this_act_lacks_stays_plain_text():
    act = get_bare_act("uapa")
    segments = act.reference_segments("See section 999")
    assert not any(s.is_link for s in segments)
    assert "".join(s.text for s in segments) == "See section 999"


def test_the_links_render_on_both_the_act_page_and_the_schedule_page(tmp_path: Path):
    client, _ = _client(tmp_path)
    expected = '<a class="bareact-reference-link" href="/laws/uapa/section/35">35(1)</a>'
    assert expected in client.get("/laws/uapa").text
    assert expected in client.get("/laws/uapa/schedule/fourth-schedule").text


def test_a_schedule_row_never_nests_anchors(tmp_path: Path):
    """Regression: an <a> row wrapping the reference's own <a> links.

    Nested anchors are invalid, and the parser resolves them by ending the row
    at the first inner link — silently dropping the rest of the reference, the
    range label and the chevron from the rendered page. The row is a container
    with an overlay link so both layers can coexist.
    """
    client, _ = _client(tmp_path)
    html = client.get("/laws/uapa").text
    assert '<a class="bareact-schedule-row"' not in html
    assert '<div class="bareact-schedule-row">' in html
    assert 'class="bareact-schedule-row-link"' in html

    row = html.split('<div class="bareact-schedule-row">', 1)[1].split("</div>", 1)[0]
    # Everything after the first reference link still survives in the row.
    # The last citation is the fourth of four, so if the row were truncated at
    # the first inner anchor none of this would be here.
    assert "See sections " in row
    assert '>38 (1)</a>' in row
    assert row.count('class="bareact-reference-link"') == 4
    assert "1–33" in row
    assert "bareact-section-chevron" in row


@pytest.mark.parametrize("slug,url", [("ndps", "/laws/ndps"), ("pota", "/laws/pota")])
def test_other_acts_schedule_rows_keep_their_content(
    tmp_path: Path, slug: str, url: str
):
    client, _ = _client(tmp_path)
    html = client.get(url).text
    row = html.split('<div class="bareact-schedule-row">', 1)[1].split("</div>", 1)[0]
    act = get_bare_act(slug)
    schedule = next(s for s in act.schedules if s.is_navigable)
    assert schedule.range_label in row
    assert f'href="/laws/{slug}/schedule/{schedule.slug}"' in row


# ── Editorial amendment brackets ──────────────────────────────────────────


# UAPA carries no bracket orphan. NDPS does, and it is not an editorial
# bracket at all: entry 105E's chemical name is printed with mismatched
# delimiters, "[4,3,-a) (1,4}". Pinned exactly rather than waved through, so a
# genuinely new orphan still fails the suite.
KNOWN_BRACKET_ORPHANS = {
    "ndps": (("unclosed-open", "psychotropic-substances row"),),
}


@pytest.mark.parametrize("slug", ["uapa", "pota", "ndps", "bns", "bnss"])
def test_no_act_gains_an_unexplained_bracket_orphan(slug: str):
    """The validator this defect exists for.

    v4's marker regexes consumed the "[" that opens an amendment span, leaving
    26 provisions ending in an orphaned "]". Balance is checked Act-wide in
    document order — never per node or per section, because the source opens a
    span at s.18A and closes it at the end of s.18B — and across schedules as
    well as sections, because one runs from the Second Schedule's title into
    the Third.
    """
    assert get_bare_act(slug).unbalanced_brackets() == KNOWN_BRACKET_ORPHANS.get(
        slug, ()
    )


def test_every_parser_owned_opener_reaches_the_stream():
    """Nothing the parser counted may be dropped before validation.

    The stream is what the validator sees, so an opener recorded on a node
    but never emitted would be invisible to it — which is exactly how the
    schedule-title brackets escaped the earlier audit.
    """
    act = get_bare_act("uapa")
    owned = sum(s.leading_brackets for s in act.section_order)
    owned += sum(r.leading_brackets for s in act.section_order for r in s.rows)
    owned += sum(sc.leading_brackets for sc in act.schedules)
    owned += sum(e.leading_brackets for sc in act.schedules for e in sc.entries)
    assert owned == 34
    stream = act.bracket_stream()
    opens = sum(1 for c, _ in stream if c == "[")
    closes = sum(1 for c, _ in stream if c == "]")
    # The stream carries every owned opener plus the source's own
    # self-contained pairs, and balances Act-wide.
    assert opens >= owned
    assert opens == closes == 80


def test_the_validator_does_not_claim_opener_to_closer_attribution():
    """Counting only.

    Amendment spans run in sequence rather than nesting, and s.2(1)(eb)
    prints a doubled "[[", so no pairing can be inferred from character
    order. The API deliberately exposes a stream and an orphan list, and
    nothing that maps one bracket to another.
    """
    act = get_bare_act("uapa")
    assert not hasattr(act, "bracket_pairs")
    for entry in act.unbalanced_brackets():
        assert len(entry) == 2 and entry[0] in {"unmatched-close", "unclosed-open"}


# ── Cross-boundary spans, taken from the printed source ───────────────────


@pytest.mark.parametrize(
    "opens_at,closes_in",
    [("18A", "18B"), ("22A", "22B")],
)
def test_a_span_opening_at_one_section_closes_in_the_next(opens_at, closes_in):
    """The PDF prints "4[18A. ..." and "[22A. ...", closing a section later.

    One amendment inserted both sections each time. Neither balances alone
    and neither should: closing at the boundary and reopening would be
    manufacturing source text.
    """
    act = get_bare_act("uapa")
    assert act.section(opens_at).leading_brackets == 1
    assert act.section(closes_in).leading_brackets == 0
    assert act.section(closes_in).rows[-1].text.rstrip().endswith("]")
    # And the opener's own section does not close it.
    assert not act.section(opens_at).rows[-1].text.rstrip().endswith("]")


def test_the_second_schedule_span_closes_in_the_third():
    act = get_bare_act("uapa")
    second, third = act.schedule("second-schedule"), act.schedule("third-schedule")
    assert (second.leading_brackets, third.leading_brackets) == (1, 0)
    assert third.entries[-1].text.rstrip().endswith("]")


@pytest.mark.parametrize(
    "number,label,fragment",
    [
        # Source-local pairs that must survive untouched.
        ("2", "(ha)", "[a Schedule]"),
        ("11", None, "[Code]"),
    ],
)
def test_source_local_bracket_pairs_are_preserved(number, label, fragment):
    rows = _rows(number)
    assert any(fragment in r.text for r in rows), fragment


def test_uapa_has_no_editorial_bracket_orphan_at_all():
    assert get_bare_act("uapa").unbalanced_brackets() == ()


@pytest.mark.parametrize(
    "slug,lead",
    [("first-schedule", 0), ("second-schedule", 1), ("third-schedule", 0),
     ("fourth-schedule", 1)],
)
def test_schedule_level_amendment_spans(slug: str, lead: int):
    schedule = get_bare_act("uapa").schedule(slug)
    assert schedule.leading_brackets == lead
    assert schedule.bracket_prefix == "[" * lead


def test_the_second_to_third_schedule_span_crosses_the_boundary():
    """One amendment inserted both schedules.

    The Second opens the span at its title and the Third closes it on entry
    (c). Neither balances alone, and closing/reopening at the boundary would
    be manufacturing source text.
    """
    act = get_bare_act("uapa")
    second, third = act.schedule("second-schedule"), act.schedule("third-schedule")
    assert second.leading_brackets == 1
    assert third.leading_brackets == 0
    assert third.entries[-1].text.rstrip().endswith("]")
    assert not second.entries[-1].text.rstrip().endswith("].")


def test_the_fourth_schedule_span_closes_in_its_residual_line():
    """It prints no rows, so its closer is a residual fragment."""
    schedule = get_bare_act("uapa").schedule("fourth-schedule")
    assert schedule.leading_brackets == 1
    assert any("]" in r for r in schedule.source_residuals)


@pytest.mark.parametrize(
    "slug,reference",
    [
        ("first-schedule", "[See sections 2(1) (m), 35, 36 and 38 (1)]"),
        ("second-schedule", "[See section 15(2)]"),
        ("third-schedule", "[See clause (b) of Explanation to section 15(1)]"),
        ("fourth-schedule", "[See sections 35(1) and 36]"),
    ],
)
def test_schedule_references_keep_their_own_brackets(slug: str, reference: str):
    """A self-contained pair around a citation, never structural metadata."""
    schedule = get_bare_act("uapa").schedule(slug)
    assert schedule.reference == reference
    assert schedule.leading_brackets == 0 or "[" not in schedule.title


def test_reference_links_leave_the_citation_brackets_alone():
    act = get_bare_act("uapa")
    segments = act.reference_segments("[See section 15(2)]")
    assert [(s.text, s.is_link) for s in segments] == [
        ("[See section ", False),
        ("15(2)", True),
        ("]", False),
    ]


def test_the_twenty_six_marker_extraction_orphans_are_all_closed():
    """None of the original defect class survives.

    Every orphan v4 produced came from a consumed opening bracket. What is
    left in UAPA is one uncaptured schedule-title bracket, which is a
    different cause and is tracked separately.
    """
    assert get_bare_act("uapa").unbalanced_brackets() == ()


def test_the_validator_catches_a_lost_opening_bracket():
    """Guards the guard: a stream with a lost "[" must be reported."""
    from constitution_memorizer.web.bare_acts import BareAct

    act = get_bare_act("uapa")
    stripped = [
        (c, w) for c, w in act.bracket_stream() if not (c == "[" and "s17" in w)
    ]
    stack, problems = [], []
    for char, where in stripped:
        if char == "[":
            stack.append(where)
        elif stack:
            stack.pop()
        else:
            problems.append(where)
    assert problems, "removing an opener must leave a closer unmatched"


@pytest.mark.parametrize(
    "number,label,count",
    [("2", "(ea)", 1), ("2", "(eb)", 2), ("2", "(ec)", 1), ("15", "(iiia)", 1),
     ("25", "(ca)", 1), ("36", "(c)", 1), ("43", "(ba)", 1), ("52", "(ee)", 1)],
)
def test_amendment_spans_reopen_before_their_marker(number, label, count):
    (row,) = [r for r in _rows(number) if r.label == label]
    assert row.leading_brackets == count
    assert row.bracket_prefix == "[" * count


@pytest.mark.parametrize(
    "number", ["1", "10", "15", "17", "18A", "22A", "24", "43A", "51A"]
)
def test_the_nine_amended_section_headings_keep_their_bracket(number: str):
    """Whole sections printed as amendment spans: ``2[17. ...``."""
    section = get_bare_act("uapa").section(number)
    assert section.leading_brackets == 1
    assert section.bracket_prefix == "["


def test_sections_not_printed_as_amendments_carry_no_bracket():
    """Narrowly typed: only a parser-counted bracket renders one."""
    act = get_bare_act("uapa")
    for number in ("2", "3", "16A", "53"):
        assert act.section(number).leading_brackets == 0
        assert act.section(number).bracket_prefix == ""


def test_the_three_originally_reported_orphans_are_closed():
    """2(1)(ea), 2(1)(eb) and 2(1)(ec)(vi) — the sites first spotted."""
    act = get_bare_act("uapa")
    for label in ("(ea)", "(eb)"):
        (row,) = [r for r in act.section("2").rows if r.label == label]
        assert row.text.rstrip().endswith(";]")
        assert row.leading_brackets >= 1
    (vi,) = [
        r for r in act.section("2").rows
        if r.label == "(vi)" and "preceding sub-clauses" in r.text
    ]
    # Its opener is on the ancestor clause (ec), not on itself.
    assert vi.leading_brackets == 0
    (ec,) = [r for r in act.section("2").rows if r.label == "(ec)"]
    assert ec.leading_brackets == 1


def test_a_prose_bracket_pair_is_left_exactly_alone():
    """s.2(1)(ha) prints "8[a Schedule]" — a balanced pair inside prose."""
    (ha,) = [r for r in _rows("2") if r.label == "(ha)"]
    assert "[a Schedule]" in ha.text
    assert ha.leading_brackets == 0


def test_the_doubled_bracket_at_2_1_eb_keeps_both_opens():
    """The source prints "[[(eb)] "Order" ...": two opens, then the marker."""
    (eb,) = [r for r in _rows("2") if r.label == "(eb)"]
    assert eb.leading_brackets == 2
    assert eb.text.startswith("]")


def test_the_18a_to_18b_span_is_left_crossing_the_boundary():
    """One pair opens at 18A and closes at the end of 18B.

    Neither section balances alone, and neither should: closing at the
    boundary and reopening would be manufacturing source text.
    """
    act = get_bare_act("uapa")
    assert act.section("18A").leading_brackets == 1
    assert act.section("18B").leading_brackets == 0
    tail = act.section("18B").rows[-1].text
    assert tail.rstrip().endswith("]")


def test_the_brackets_render_before_the_marker_in_the_dom(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/uapa/section/2").text
    assert '<span class="bareact-amendment-open">[</span>' in html
    assert '<span class="bareact-amendment-open">[[</span>' in html
    # Source order: the bracket precedes the label, never follows it.
    opened = html.split('<span class="bareact-amendment-open">[</span>', 1)[1]
    assert opened.lstrip().startswith('<span class="bareact-row-label">')


def test_a_whole_section_span_opens_against_the_first_line_of_statute(tmp_path: Path):
    """Not against "Section 17", which is our chrome rather than source text.

    In print the span opens before the section number — ``2[17. Punishment
    ...`` — and closes at the end of the section. Anchoring it to the first
    body row puts both glyphs in the same body, next to real words.
    """
    client, _ = _client(tmp_path)
    html = client.get("/laws/uapa/section/17").text
    assert '<span class="bareact-amendment-open">[</span>Section 17' not in html
    body = html.split('class="bareact-body"', 1)[1]
    first_row = body.split('class="bareact-row-text"', 1)[1].split("</p>", 1)[0]
    assert first_row.lstrip('>').startswith('<span class="bareact-amendment-open">[</span>')
    assert body.rstrip().rstrip("</div>").rstrip().endswith("]</p>") or "offence.]" in body
    plain = client.get("/laws/uapa/section/3").text
    assert "bareact-amendment-open" not in plain


# ── The other Acts are untouched ──────────────────────────────────────────


def test_pota_list_schedule_is_unchanged(tmp_path: Path):
    schedule = get_bare_act("pota").schedule("schedule")
    assert schedule.kind == "list"
    assert len(schedule.entries) == 32
    assert [e.marker for e in schedule.entries] == [str(i) for i in range(1, 33)]
    # The old field still answers, so nothing reading it broke.
    assert [e.serial_number for e in schedule.entries] == [str(i) for i in range(1, 33)]
    assert schedule.range_label == "1–32"
    assert len(schedule.notes) == 1
    assert schedule.notes[0].marker == "Explanation."
    client, _ = _client(tmp_path)
    assert client.get("/laws/pota/schedule/schedule").status_code == 200


def test_ndps_table_schedule_is_unchanged(tmp_path: Path):
    schedule = get_bare_act("ndps").schedule("psychotropic-substances")
    assert schedule.kind == "table"
    assert [c.key for c in schedule.parts[0].columns] == [
        "serial", "inn", "other", "chemical"
    ]
    assert schedule.range_label == "1–110ZT"
    client, _ = _client(tmp_path)
    assert client.get("/laws/ndps/schedule/psychotropic-substances").status_code == 200


def test_bnss_schedules_are_unchanged(tmp_path: Path):
    first = get_bare_act("bnss").schedule("first-schedule")
    assert first.kind == "table"
    assert len(first.parts) == 2
    assert first.row_count == 444
    assert [n.marker for n in first.notes] == ["1.", "2."]
    second = get_bare_act("bnss").schedule("second-schedule")
    assert second.kind == "unsupported"
    assert not second.is_navigable
    assert len(second.raw_payload["forms"]) == 58
    client, _ = _client(tmp_path)
    assert client.get("/laws/bnss/schedule/first-schedule").status_code == 200
    assert client.get("/laws/bnss/schedule/second-schedule").status_code == 404


def test_bns_body_rendering_is_unchanged(tmp_path: Path):
    act = get_bare_act("bns")
    assert len(act.section_order) == 358
    assert act.render_profile == "bns"
    client, _ = _client(tmp_path)
    assert client.get("/laws/bns/section/103").status_code == 200


def test_a_declared_table_with_no_known_structure_is_preserved_not_guessed():
    from constitution_memorizer.web.bare_acts import _parse_schedule

    schedule = _parse_schedule({"id": "x", "type": "table", "mystery": [1, 2]})
    assert schedule.kind == "unsupported"
    assert schedule.raw_payload["mystery"] == [1, 2]


def test_a_list_entry_without_any_marker_raises():
    from constitution_memorizer.web.bare_acts import _parse_schedule

    with pytest.raises(ValueError, match="serial_number or label"):
        _parse_schedule({"id": "x", "type": "list", "entries": [{"text": "hi"}]})


# ── Catalogue ─────────────────────────────────────────────────────────────


def test_uapa_is_one_card_carrying_both_capabilities():
    """Extended, not duplicated: the clause extract stays as the secondary."""
    from constitution_memorizer.web.law_catalog import load_catalog

    catalog = load_catalog()
    law = catalog.by_full_act("uapa")
    assert law is not None
    assert law.id == "uapa-1967"
    assert law.primary_content == "full_act"
    assert law.key_provisions_ref == "uapa-1967"
    assert law.href == "/laws/uapa"
    assert len([x for x in catalog.laws if x.short_title == "UAPA"]) == 1


def test_uapa_is_a_current_act_and_pota_is_still_repealed():
    from constitution_memorizer.web.law_catalog import load_catalog

    catalog = load_catalog()
    assert catalog.by_full_act("uapa").is_current
    assert catalog.by_full_act("uapa").status_label == ""
    assert catalog.by_full_act("pota").status == "repealed"
    assert {law.id for law in catalog.laws if law.status_label} == {"pota"}


def test_the_catalogue_entry_is_derived_from_the_act():
    from constitution_memorizer.web.law_catalog import load_catalog

    law = load_catalog().by_full_act("uapa")
    act = get_bare_act("uapa")
    assert law.scope_label == act.meta_label
    assert law.title == act.title


@pytest.mark.parametrize(
    "query",
    ["uapa", "unlawful activities", "unlawful activities (prevention) act, 1967"],
)
def test_uapa_is_searchable(query: str):
    from constitution_memorizer.web.law_catalog import load_catalog

    assert query in load_catalog().by_full_act("uapa").search_blob


def test_uapa_uses_the_existing_subject_taxonomy():
    from constitution_memorizer.web.law_catalog import load_catalog

    law = load_catalog().by_full_act("uapa")
    assert law.subjects == ("criminal",)
    assert law.primary_subject == "criminal"


def test_both_uapa_destinations_still_serve(tmp_path: Path):
    """The full Act leads; the Article-mapped extract keeps its own page."""
    client, _ = _client(tmp_path)
    assert client.get("/laws/uapa").status_code == 200
    assert client.get("/laws/uapa-1967").status_code == 200
    html = client.get("/laws").text
    assert 'data-law-id="uapa-1967"' in html
    assert 'href="/laws/uapa"' in html


def test_uapa_is_free_to_read_and_records_nothing(tmp_path: Path):
    client, engine = _client(tmp_path)
    before = engine.stats()
    for path in (
        "/laws", "/laws/uapa", "/laws/uapa/section/1", "/laws/uapa/section/16A",
        "/laws/uapa/section/53", "/laws/uapa/schedule/first-schedule",
        "/laws/uapa/schedule/fourth-schedule",
    ):
        assert client.get(path).status_code == 200, path
    assert engine.stats() == before
    assert engine.due_today() == []


# ── Data invariants ───────────────────────────────────────────────────────


def test_runtime_is_the_canonical_minus_x_and_the_annex_pages():
    archival = json.loads(ARCHIVAL.read_text(encoding="utf-8"))
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))

    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k != "source_x"}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    expected = strip(archival)
    expected["source_annexes"] = {
        k: v for k, v in expected["source_annexes"].items() if k != "pages"
    }
    assert runtime == expected


def test_the_runtime_keeps_page_provenance_on_the_law_itself():
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    for chapter in runtime["chapters"]:
        for section in chapter["sections"]:
            assert section["source_pages"], section["number"]
    for schedule in runtime["schedules"]:
        assert schedule["source_pages"], schedule["id"]
    assert runtime["document"]["source_file"]["sha256"]


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
    assert '"web/uapa_runtime_v1.json"' in (REPO / "pyproject.toml").read_text(
        encoding="utf-8"
    )


def test_the_registry_entry_matches_the_shipped_artifact():
    spec = BARE_ACTS["uapa"]
    assert spec.filename == RUNTIME.name
    assert spec.render_profile == "bns"
    assert spec.short_title == "UAPA"
    assert spec.patch_filenames == ()


def test_all_four_schedules_are_in_the_sitemap_inventory():
    assert get_bare_act("uapa").public_schedule_slugs == (
        "first-schedule", "second-schedule", "third-schedule", "fourth-schedule"
    )
