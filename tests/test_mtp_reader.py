"""The Medical Termination of Pregnancy Act, 1971 — the first chapterless Act.

Nine sections, no chapters, no schedules. Every earlier Act stored its sections
under `chapters[]`, and the loader, the chapter list and the section page's
eyebrow all assumed that shape. MTP's export keeps its sections at the top
level beside an empty `chapters`, because that is what the statute prints.

What is new to the reader:

* the loader reads top-level `sections` with empty chapter fields rather than
  inventing a "Chapter I";
* the Act's own description is "Sections 1–8", never "0 Chapters · …";
* the reader lists the sections flat, the tab is called "Sections", and the
  section page draws no "Chapter · " eyebrow over nothing;
* the bracket validator walks unchaptered sections too.

The parser-side facts are pinned here as well: the source's own oddities are
preserved rather than repaired and recorded in the canonical's `_validation`
block so they cannot be mistaken for extraction faults, and the runtime is the
archival copy minus the parse's line-by-line record.

Footnotes, stated precisely: MTP's twelve notes hydrate, but no reference is
anchored to a character span, so the reader shows no marker and a user has no
way to reach them yet. NDPS anchors its notes and renders them; MTP does not.
That gap is pinned here as the current behaviour, not claimed as a feature.
"""

from __future__ import annotations

import json
import re
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
ARCHIVAL = REPO / "data" / "reference" / "mtp_canonical_v2.json"
RUNTIME = REPO / "src" / "constitution_memorizer" / "web" / "mtp_runtime_v1.json"

SECTION_IDS = ["1", "2", "3", "4", "5", "5A", "6", "7", "8"]
CHAPTERED = ("ndps", "bns", "bnss", "pota", "uapa", "pss")


def _client(tmp_path: Path) -> tuple[TestClient, ReminderEngine]:
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    return TestClient(create_app(units_path=MINI_UNITS, db_path=db)), engine


def _rows(number: str):
    return get_bare_act("mtp").section(number).rows


def _all_rows():
    return [r for s in get_bare_act("mtp").section_order for r in s.rows]


def _labels(nodes) -> list[str]:
    return [n.get("label") or "" for n in nodes]


def _walk(nodes):
    for node in nodes:
        yield node
        yield from _walk(node.get("children") or [])


def _validation() -> dict:
    return json.loads(ARCHIVAL.read_text(encoding="utf-8"))["_validation"]


# ── The Act ───────────────────────────────────────────────────────────────


def test_the_whole_act_is_present():
    act = get_bare_act("mtp")
    assert act.title == "The Medical Termination of Pregnancy Act, 1971"
    assert act.short_name == "The MTP Act, 1971"
    assert act.act_number == "34 of 1971"
    assert act.enactment_date == "10th August, 1971"
    assert len(act.section_order) == 9
    assert act.render_profile == "bns"


def test_section_order_is_the_canonical_order():
    """5A sits between 5 and 6, as printed — not after 8 by a lexical sort."""
    assert [s.number for s in get_bare_act("mtp").section_order] == SECTION_IDS


def test_the_lettered_section_resolves_and_serves(tmp_path: Path):
    assert get_bare_act("mtp").section("5A") is not None
    client, _ = _client(tmp_path)
    assert client.get("/laws/mtp/section/5A").status_code == 200


def test_the_act_has_no_schedules():
    act = get_bare_act("mtp")
    assert act.schedules == ()
    assert act.public_schedule_slugs == ()


def test_every_node_kind_is_already_in_the_bns_profile():
    kinds = {r.kind for r in _all_rows()}
    assert kinds == {"subsection", "clause", "paragraph", "proviso", "explanation"}


# ── No chapters ───────────────────────────────────────────────────────────


def test_the_act_has_no_chapters_and_its_sections_know_it():
    act = get_bare_act("mtp")
    assert act.chapters == ()
    assert act.chapter_count == 0
    assert [s.number for s in act.unchaptered_sections] == SECTION_IDS
    for section in act.section_order:
        assert not section.has_chapter
        assert section.chapter_number == ""
        assert section.chapter_title == ""
        assert not section.starts_division


def test_the_meta_label_describes_sections_only():
    """Never "0 Chapters · Sections 1–8": that reports a structure the statute
    does not have as if it were a count of zero."""
    assert get_bare_act("mtp").meta_label == "Sections 1–8"
    assert get_bare_act("mtp").section_range == "1–8"


def test_every_chaptered_act_still_reads_exactly_as_before():
    for slug in CHAPTERED:
        act = get_bare_act(slug)
        assert act.chapters, slug
        assert act.unchaptered_sections == (), slug
        assert all(s.has_chapter for s in act.section_order), slug
        assert act.meta_label.startswith(f"{act.chapter_count} Chapters · Sections "), slug
        # Every section reachable through a chapter is in the order, once.
        via_chapters = [s.number for c in act.chapters for s in c.sections]
        assert via_chapters == [s.number for s in act.section_order], slug


def test_the_reader_lists_the_sections_flat(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/mtp").text
    assert '<details class="bareact-chapter"' not in html
    assert "Chapter I" not in html
    panel = html.split('data-bareact-panel="chapters"', 1)[1].split(
        'data-bareact-panel="schedules"', 1
    )[0]
    assert '<div class="bareact-section-list">' in panel
    for number in SECTION_IDS:
        assert f'href="/laws/mtp/section/{number}"' in panel
    assert panel.count('class="bareact-section-row"') == len(SECTION_IDS)
    # The chapter rows' own clothes, nothing new to style.
    assert 'class="bareact-chapters"' in html
    assert "This Act has no Schedules." in html


def test_the_first_tab_is_called_sections_here_and_chapters_elsewhere(tmp_path: Path):
    client, _ = _client(tmp_path)
    mtp = client.get("/laws/mtp").text
    assert 'data-bareact-tab="chapters"\n      >Sections</button>' in mtp
    assert ">Chapters</button>" not in mtp
    for slug in CHAPTERED:
        html = client.get(f"/laws/{slug}").text
        assert 'data-bareact-tab="chapters"\n      >Chapters</button>' in html, slug
        assert '<details class="bareact-chapter"' in html, slug
    # The controller's panel key is unchanged, so the tab JS needs no branch.
    assert mtp.count('data-bareact-panel="') == 2


def test_the_section_page_draws_no_eyebrow_over_nothing(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/mtp/section/3").text
    assert "bareact-reader-eyebrow" not in html
    assert "Chapter  ·" not in html
    assert "<h1 class=\"bareact-reader-title\">Section 3</h1>" in html
    # A chaptered Act keeps its eyebrow exactly as it was.
    pss = client.get("/laws/pss/section/3").text
    assert '<p class="bareact-reader-eyebrow">Chapter II · ' in pss


def test_the_section_description_mentions_no_chapter(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/mtp/section/8").text
    description = re.search(
        r'<meta name="description" content="([^"]*)"', html
    ).group(1)
    assert "Chapter" not in description
    assert description.startswith("Section 8 of the Medical Termination")
    index = client.get("/laws/mtp").text
    index_description = re.search(
        r'<meta name="description" content="([^"]*)"', index
    ).group(1)
    assert "Sections 1–8." in index_description
    assert "0 Chapters" not in index_description


# ── Structure the parser had to get right ─────────────────────────────────


def test_section_2_is_one_definitions_paragraph_with_lettered_clauses():
    body = get_bare_act("mtp").section("2").body
    assert len(body) == 1
    assert body[0]["type"] == "paragraph"
    assert body[0]["text"] == "In this Act, unless the context otherwise requires,—"
    assert _labels(body[0]["children"]) == ["(a)", "(aa)", "(b)", "(c)", "(d)", "(e)"]
    assert all(c["type"] == "clause" for c in body[0]["children"])


def test_section_3_subsection_hierarchy():
    body = get_bare_act("mtp").section("3").body
    assert _labels(body) == ["(1)", "(2)", "(2A)", "(2B)", "(2C)", "(2D)", "(3)", "(4)"]
    assert all(n["type"] == "subsection" for n in body)


def test_section_3_2_shares_its_grounds_between_the_two_alternatives():
    """(a) and (b) each end mid-sentence; "of the opinion, formed in good
    faith, that—" then leads into (i) and (ii), which both alternatives share.
    Nesting the grounds under (b) alone would misstate the law for (a)."""
    sub = get_bare_act("mtp").section("3").body[1]
    assert sub["text"] == (
        "Subject to the provisions of sub-section (4), a pregnancy may be "
        "terminated by a registered medical practitioner,—"
    )
    kinds = [(c["type"], c.get("label") or "") for c in sub["children"]]
    assert kinds == [
        ("clause", "(a)"),
        ("clause", "(b)"),
        ("paragraph", ""),
        ("clause", "(i)"),
        ("clause", "(ii)"),
        ("explanation", "Explanation 1"),
        ("explanation", "Explanation 2"),
    ]
    assert sub["children"][0]["text"].endswith("if such medical practitioner is, or")
    assert sub["children"][1]["text"].endswith(
        "if not less than two registered medical practitioners are,"
    )
    assert sub["children"][2]["text"] == "of the opinion, formed in good faith, that—"


def test_section_3_4_is_a_bare_subsection_number_over_two_clauses():
    """Like BNS s.8(6): no text of its own, but "(4)" is part of how the
    provision is cited, so the row stays on the page."""
    sub = get_bare_act("mtp").section("3").body[-1]
    assert sub["label"] == "(4)"
    assert sub["text"] == ""
    assert _labels(sub["children"]) == ["(a)", "(b)"]
    rows = _rows("3")
    four = next(r for r in rows if r.label == "(4)")
    assert four.depth == 0 and four.text == ""
    assert [r.label for r in rows if r.depth == 1 and r.label in ("(a)", "(b)")][-2:] == [
        "(a)", "(b)",
    ]


def test_section_3_2d_lists_the_medical_board():
    sub = next(n for n in get_bare_act("mtp").section("3").body if n["label"] == "(2D)")
    assert sub["text"] == "The Medical Board shall consist of the following, namely:—"
    assert _labels(sub["children"]) == ["(a)", "(b)", "(c)", "(d)"]


def test_section_4_is_a_lead_two_clauses_and_a_proviso():
    body = get_bare_act("mtp").section("4").body
    assert [(n["type"], n.get("label") or "") for n in body] == [
        ("paragraph", ""), ("proviso", ""),
    ]
    assert _labels(body[0]["children"]) == ["(a)", "(b)"]
    assert body[0]["children"][1]["text"].endswith("Chairperson of the said Committee:")
    assert body[1]["text"].startswith("Provided that the District Level Committee")


def test_section_5_explanations_are_top_level_block_breaks():
    body = get_bare_act("mtp").section("5").body
    assert _labels(body) == ["(1)", "(2)", "(3)", "(4)", "Explanation 1", "Explanation 2"]
    explanations = [r for r in _rows("5") if r.kind == "explanation"]
    assert [r.display_label for r in explanations] == ["Explanation 1.—", "Explanation 2.—"]
    assert all(r.depth == 0 and r.is_block_break for r in explanations)


def test_section_6_2_keeps_the_inserted_clauses_in_printed_order():
    """(a), then the 2021 insertions (aa)/(ab)/(ac), then the original (b)."""
    sub = get_bare_act("mtp").section("6").body[1]
    assert _labels(sub["children"]) == ["(a)", "(aa)", "(ab)", "(ac)", "(b)"]


def test_section_6_3_survives_its_page_break_as_one_sentence():
    sub = get_bare_act("mtp").section("6").body[2]
    assert sub["label"] == "(3)"
    assert sub["children"] == []
    assert sorted(sub["source_pages"]) == [6, 7]
    assert "both Houses agree in making any modification in the rule" in sub["text"]
    assert sub["text"].endswith("previously done under that rule.")


def test_section_7_subsections():
    body = get_bare_act("mtp").section("7").body
    assert _labels(body) == ["(1)", "(2)", "(2A)", "(3)"]
    assert _labels(body[0]["children"]) == ["(a)", "(b)", "(c)"]


def test_section_8_is_a_single_paragraph():
    body = get_bare_act("mtp").section("8").body
    assert len(body) == 1 and body[0]["type"] == "paragraph"
    assert body[0]["text"].startswith("No suit or other legal proceeding")


# ── Reading text ──────────────────────────────────────────────────────────


def test_reading_text_carries_no_editorial_marks():
    """The parser removes brackets, deletion asterisks and superscripts from
    the reading text and keeps them in the archival source_lines. So unlike
    every earlier Act there is nothing for the bracket validator to pair."""
    for row in _all_rows():
        assert "[" not in row.text and "]" not in row.text, row.text
        assert "*" not in row.text, row.text
        assert "  " not in row.text
        assert not re.search(r"\s[,;.](?!\.)", row.text)
    act = get_bare_act("mtp")
    assert "[" not in act.long_title
    assert act.bracket_stream() == ()
    assert act.unbalanced_brackets() == ()
    assert all(r.leading_brackets == 0 for r in _all_rows())


def test_the_omitted_jammu_and_kashmir_words_are_gone_from_the_reading_text():
    """s.1(2) printed "the whole of India 1***." — the deletion run is the
    footnote's business, not the provision's."""
    assert _rows("1")[1].text == "It extends to the whole of India."


@pytest.mark.parametrize(
    "number,fragment",
    [
        # "mentally ill person" replaced "lunatic" in 2002; the bracketed
        # substitution prints as plain text.
        ("2", "“guardian” means a person having the care of the person of a minor or a mentally ill person;"),
        # The 2021 Act's own words, preserved exactly, "gestational age" and all.
        ("3", "at different gestational age shall be such as may be prescribed"),
        # The Indian Medical Council Act citation is left as printed, not modernised.
        ("2", "clause (h) of section 2 of the Indian Medical Council Act, 1956 (102 of 1956)"),
    ],
)
def test_source_wording_is_preserved(number: str, fragment: str):
    assert any(fragment in r.text for r in _rows(number))


# ── Footnotes ─────────────────────────────────────────────────────────────


def test_the_twelve_footnotes_load_by_page_scoped_id():
    """MTP states its notes as {id, marker, text}, the shape the loader keys
    on, so — unlike PSS — they hydrate. Page-scoped ids keep the three
    different notes numbered "1" apart."""
    notes = get_bare_act("mtp").footnotes
    assert len(notes) == 12
    assert {n.split("_")[1] for n in notes} == {"p4", "p5", "p6", "p7"}
    assert notes["footnote_p4_2"].text.startswith("1st April, 1972, vide notification")
    assert notes["footnote_p4_1"].marker == "1"
    assert notes["footnote_p5_1"].marker == "1"


def test_footnotes_are_loaded_but_not_anchored_in_the_text():
    """The references are recorded at section level (`annotations` with a
    source line and the printed text), not as `{start, end}` offsets on
    nodes, so no row carries a note id. NDPS does carry offsets and renders
    its markers; MTP's notes are therefore loaded but unreachable from any
    page until the parser emits node-level anchors. The line ids and printed
    text it does record are enough to derive them later."""
    act = get_bare_act("mtp")
    assert all(section.note_ids == () for section in act.section_order)
    assert all(
        not node.get("annotations") and not node.get("label_annotations")
        for section in act.raw["sections"]
        for node in _walk(section["body"])
    )
    archival = json.loads(ARCHIVAL.read_text(encoding="utf-8"))
    anchors = [a for s in archival["sections"] for a in s["annotations"]]
    assert len(anchors) == 13
    assert {a["note_id"] for a in anchors} <= set(act.footnotes)
    assert {a["section_id"] for a in anchors} == {
        "section_1", "section_2", "section_3", "section_4",
        "section_5", "section_5A", "section_6", "section_7",
    }


def test_no_page_shows_a_footnote_marker_or_note(tmp_path: Path):
    """The user-visible consequence of the test above, pinned so that the
    day anchors land this fails and gets rewritten as a positive check."""
    client, _ = _client(tmp_path)
    ndps = client.get("/laws/ndps/section/1").text
    assert 'id="fn-' in ndps  # the apparatus exists and NDPS uses it
    for number in SECTION_IDS:
        html = client.get(f"/laws/mtp/section/{number}").text
        assert 'id="fn-' not in html, number
        assert "bareact-fn" not in html, number


def test_the_misprinted_footnote_is_kept_as_printed_and_recorded():
    """p.6 n.3 reads "Ins. by Act s. 5, ibid." — the Act number is missing in
    the source. Left uncorrected in the note, and named in the canonical's
    `source_anomalies` so it reads as a printing fault, not a dropped token."""
    assert get_bare_act("mtp").footnotes["footnote_p6_3"].text == (
        "Ins. by Act s. 5, ibid. (w.e.f. 24-9-2021)."
    )
    anomaly = next(
        a for a in _validation()["source_anomalies"]
        if a["kind"] == "footnote_missing_act_number"
    )
    assert anomaly["footnote_id"] == "footnote_p6_3"
    assert anomaly["printed"] == "Ins. by Act s. 5, ibid. (w.e.f. 24-9-2021)."
    assert "Act 8 of 2021" in anomaly["note"]


def test_the_orphan_closing_bracket_is_recorded_not_repaired():
    """s.3(4)(a) prints "...her guardian.]" with no opener anywhere in the
    Act: 11 "[" against 12 "]" over the operative lines. The reading text
    drops it with every other editorial bracket, and the raw line keeps it."""
    validation = _validation()
    assert (validation["bracket_open_count"], validation["bracket_close_count"]) == (11, 12)
    [problem] = validation["bracket_problems"]
    assert problem["kind"] == "unmatched_close"
    assert problem["line_id"] == "p5_l32"
    anomaly = next(
        a for a in validation["source_anomalies"]
        if a["kind"] == "unmatched_editorial_bracket"
    )
    assert anomaly["section"] == "3" and anomaly["source_line_id"] == "p5_l32"
    assert anomaly["printed"] == "consent in writing of her guardian.]"
    archival = json.loads(ARCHIVAL.read_text(encoding="utf-8"))
    raw = next(l for l in archival["source_lines"] if l["id"] == "p5_l32")
    assert raw["raw_text"].endswith("guardian.]")
    clause_a = get_bare_act("mtp").section("3").body[-1]["children"][0]
    assert clause_a["text"].endswith("consent in writing of her guardian.")


def test_the_anomaly_set_is_exactly_these_two():
    """A regeneration that finds a different set is a different source or a
    different parser, and must be looked at rather than absorbed."""
    kinds = [(a["kind"], a.get("source_line_id") or a.get("footnote_id"))
             for a in _validation()["source_anomalies"]]
    assert kinds == [
        ("unmatched_editorial_bracket", "p5_l32"),
        ("footnote_missing_act_number", "footnote_p6_3"),
    ]
    assert _validation()["status"] == "passed"
    assert _validation()["blocking_errors"] == []


# ── Catalogue ─────────────────────────────────────────────────────────────


def test_mtp_is_catalogued_under_the_new_health_subject():
    from constitution_memorizer.web.law_catalog import load_catalog

    catalog = load_catalog()
    law = catalog.by_full_act("mtp")
    assert law is not None
    assert law.id == "mtp"
    assert law.primary_subject == "health"
    assert law.subjects == ("health",)
    assert law.href == "/laws/mtp"
    assert law.primary_content == "full_act"
    assert law.key_provisions_ref is None
    assert "health" in {s.id for s in catalog.visible_subjects}


def test_mtp_is_a_current_act_and_pota_is_still_the_only_badged_one():
    from constitution_memorizer.web.law_catalog import load_catalog

    catalog = load_catalog()
    assert catalog.by_full_act("mtp").is_current
    assert catalog.by_full_act("mtp").status_label == ""
    assert {law.id for law in catalog.laws if law.status_label} == {"pota"}


def test_the_catalogue_entry_is_derived_from_the_act():
    from constitution_memorizer.web.law_catalog import load_catalog

    law = load_catalog().by_full_act("mtp")
    act = get_bare_act("mtp")
    assert law.scope_label == act.meta_label
    assert law.title == act.title


def test_the_act_info_card_holds_only_what_the_source_supports():
    """Commencement comes from the Act's own footnote (1st April 1972, GSR
    285); jurisdiction from s.1(2). No ministry or department row is claimed,
    because neither is in the PDF."""
    from constitution_memorizer.web.act_info import build_act_info
    from constitution_memorizer.web.law_catalog import load_catalog

    panel = build_act_info(get_bare_act("mtp"), load_catalog().by_full_act("mtp"))
    assert panel.meta == "Act No. 34 of 1971"
    assert {row.key: row.value for row in panel.rows} == {
        "Enacted": "10-08-1971",
        "In force": "01-04-1972",
        "Jurisdiction": "Central",
        "Sections": "1–8",
    }
    assert panel.long_title.startswith("An Act to provide for the termination")


@pytest.mark.parametrize(
    "query", ["mtp", "medical termination of pregnancy act", "abortion"]
)
def test_mtp_is_searchable(query: str):
    from constitution_memorizer.web.law_catalog import load_catalog

    assert query in load_catalog().by_full_act("mtp").search_blob


def test_the_health_chip_appears_on_the_catalogue(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws").text
    assert 'data-laws-chip="health"' in html
    assert 'data-law-id="mtp"' in html
    assert 'href="/laws/mtp"' in html


def test_mtp_is_free_to_read_and_records_nothing(tmp_path: Path):
    client, engine = _client(tmp_path)
    before = engine.stats()
    for path in ("/laws", "/laws/mtp", "/laws/mtp/section/1", "/laws/mtp/section/5A", "/laws/mtp/section/8"):
        assert client.get(path).status_code == 200, path
    assert engine.stats() == before
    assert engine.due_today() == []


# ── Data invariants ───────────────────────────────────────────────────────


def _strip(value):
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k != "source_x"}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def test_runtime_is_the_canonical_minus_the_x_coordinate_and_the_line_record():
    archival = json.loads(ARCHIVAL.read_text(encoding="utf-8"))
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    expected = _strip(archival)
    expected.pop("source_lines")
    assert runtime == expected
    assert "source_lines" not in runtime


def test_the_archival_line_record_is_what_the_ids_point_into():
    archival = json.loads(ARCHIVAL.read_text(encoding="utf-8"))
    line_ids = {line["id"] for line in archival["source_lines"]}
    assert len(line_ids) == len(archival["source_lines"]) == 271
    referenced = set()
    for section in archival["sections"]:
        referenced.update(section["source_line_ids"])
        referenced.update(a["source_line_id"] for a in section["annotations"])
    for note in archival["footnotes"]:
        referenced.update(note["source_line_ids"])
    assert referenced <= line_ids


def test_the_runtime_keeps_every_block_the_reader_may_later_need():
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    assert len(runtime["footnotes"]) == 12
    assert len(runtime["sections"]) == 9
    assert runtime["chapters"] == []
    for key in (
        "source_front_matter", "source_back_matter", "long_title",
        "enacting_formula", "editorial_policy", "_validation",
    ):
        assert runtime[key], key
    assert runtime["source_back_matter"][0]["type"] == "statement_of_objects_and_reasons"
    for section in runtime["sections"]:
        assert section["source_pages"]
        assert section["source_line_ids"]


def test_the_archival_canonical_is_the_reviewed_parse():
    archival = json.loads(ARCHIVAL.read_text(encoding="utf-8"))
    assert archival["schema_version"] == "1.2"
    assert archival["document"]["source_file"]["sha256"] == (
        "6e091b4327fa5c2829724ff9bf0f645ad545bb64ed3afd278fe50998b53980ac"
    )
    assert archival["document"]["source_as_on"] == "27th July, 2025"
    assert archival["document"]["parser"].endswith("(MTP v2)")
    checks = archival["_validation"]["section_checks"]
    assert [c["section"] for c in checks] == SECTION_IDS
    assert all(c["text_reconstruction_match"] for c in checks)
    assert archival["_validation"]["unparsed_lines"] == 0
    assert archival["document"]["hierarchy_note"] == (
        "No chapters in source; sections are stored at top level."
    )


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
    assert '"web/mtp_runtime_v1.json"' in (REPO / "pyproject.toml").read_text(
        encoding="utf-8"
    )


def test_the_registry_entry_matches_the_shipped_artifact():
    spec = BARE_ACTS["mtp"]
    assert spec.filename == RUNTIME.name
    assert spec.render_profile == "bns"
    assert spec.short_title == "MTP"
    assert spec.patch_filenames == ()
    assert spec.source_version == "1"


def test_the_sitemap_inventory_has_every_section_and_no_schedule():
    manifest = json.loads(
        (REPO / "src" / "constitution_memorizer" / "web" / "law_sitemap_manifest.json")
        .read_text(encoding="utf-8")
    )
    entry = manifest["laws"]["mtp"]
    assert entry["sections"] == SECTION_IDS
    assert entry["schedules"] == []
    assert entry["runtime_identity"] == "mtp:1:mtp_runtime_v1.json"


def test_the_act_and_its_sections_are_in_the_served_sitemap(tmp_path: Path):
    client, _ = _client(tmp_path)
    assert "sitemap-laws-mtp.xml" in client.get("/sitemap.xml").text
    xml = client.get("/sitemap-laws-mtp.xml").text
    assert xml.count("<loc>") == 1 + len(SECTION_IDS)
    assert "/laws/mtp</loc>" in xml
    assert "/laws/mtp/section/5A</loc>" in xml
    assert "/schedule/" not in xml
