"""The Prevention of Terrorism Act, 2002 — the fourth Bare Act.

Three things here are new to the reader:

* the **list schedule** — POTA's Schedule is 32 numbered organisations, not a
  table. It gets its own kind rather than a one-column fake table;
* **strict schedule dispatch**. The old rule sent anything carrying `entries[]`
  into the NDPS drug adapter, which reads four NDPS-specific fields; POTA's
  entries carry `serial_number` and `text`, so all 32 organisation names came
  out blank under NDPS's drug headings. Dispatch is now declared-type first,
  then complete signatures;
* **catalogue lifecycle metadata**, so a repealed Act reads as historical
  without its statutory text being touched.

The operative 64 sections reuse the BNS render profile unchanged.
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
ARCHIVAL = REPO / "data" / "reference" / "pota_canonical_v1.json"
RUNTIME = REPO / "src" / "constitution_memorizer" / "web" / "pota_runtime_v1.json"

SCHEDULE_URL = "/laws/pota/schedule/schedule"


def _client(tmp_path: Path) -> tuple[TestClient, ReminderEngine]:
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    return TestClient(create_app(units_path=MINI_UNITS, db_path=db)), engine


# ── The Act ───────────────────────────────────────────────────────────────


def test_the_whole_act_is_present():
    act = get_bare_act("pota")
    assert act.title == "The Prevention of Terrorism Act, 2002"
    assert len(act.chapters) == 6
    assert len(act.section_order) == 64
    assert act.meta_label == "6 Chapters · Sections 1–64"
    # Six node types, all of them already in the BNS vocabulary.
    assert act.render_profile == "bns"


def test_section_numbers_run_1_to_64_in_the_acts_own_order():
    act = get_bare_act("pota")
    numbers = [s.number for s in act.section_order]
    assert numbers == [str(n) for n in range(1, 65)]
    assert all(isinstance(n, str) for n in numbers)


def test_first_and_last_sections_resolve():
    act = get_bare_act("pota")
    assert act.section("1").title.startswith("Short title, application")
    assert act.section("64").title == "Repeal and saving"
    assert act.section("65") is None


def test_chapters_are_contiguous_and_cover_every_section():
    act = get_bare_act("pota")
    spans = [(c.number, c.sections[0].number, c.sections[-1].number) for c in act.chapters]
    assert spans == [
        ("I", "1", "2"),
        ("II", "3", "17"),
        ("III", "18", "22"),
        ("IV", "23", "35"),
        ("V", "36", "48"),
        ("VI", "49", "64"),
    ]
    assert sum(len(c.sections) for c in act.chapters) == 64


def test_pota_has_no_divisions():
    """Unlike BNS and BNSS, no chapter of POTA is subdivided."""
    act = get_bare_act("pota")
    assert not any(s.division_id for s in act.section_order)
    assert not any(s.starts_division for s in act.section_order)


@pytest.mark.parametrize(
    "number,kind",
    [("1", "subsection"), ("1", "clause"), ("3", "explanation"), ("3", "proviso")],
)
def test_each_node_kind_renders(tmp_path: Path, number: str, kind: str):
    client, _ = _client(tmp_path)
    response = client.get(f"/laws/pota/section/{number}")
    assert response.status_code == 200
    act = get_bare_act("pota")
    kinds = {row.kind for row in act.section(number).rows}
    assert kind in kinds, (number, kind, kinds)


def test_deepest_nesting_renders(tmp_path: Path):
    """Section 49(3)(a)(i)-(ii): subsection > clause > subclause."""
    act = get_bare_act("pota")
    rows = act.section("49").rows
    subclauses = [r for r in rows if r.kind == "subclause"]
    assert subclauses, [r.kind for r in rows]
    assert max(r.depth for r in rows) == 2
    assert {r.label for r in subclauses} >= {"(i)", "(ii)"}
    client, _ = _client(tmp_path)
    assert client.get("/laws/pota/section/49").status_code == 200


def test_section_49_quoted_insertions_stay_paragraph_text():
    """49(2)(b) inserts provisos into the Code — quoted text, not POTA provisos.

    Counting them as POTA's own provisos would make the Act appear to say
    something it only quotes.
    """
    act = get_bare_act("pota")
    inserted = [
        r
        for r in act.section("49").rows
        if r.text.lstrip('"').startswith(("Provided further", "Provided also"))
    ]
    assert len(inserted) == 2
    assert {r.kind for r in inserted} == {"paragraph"}


def test_provisos_and_explanations_survive():
    act = get_bare_act("pota")
    provisos = sum(1 for s in act.section_order for r in s.rows if r.kind == "proviso")
    explanations = sum(
        1 for s in act.section_order for r in s.rows if r.kind == "explanation"
    )
    # 19 provisos and 6 explanations in the operative text; the Schedule's own
    # Explanation is a schedule note, not a body node.
    assert (provisos, explanations) == (19, 6)


def test_the_chapter_list(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/pota").text
    assert html.count('class="bareact-chapter"') == 6
    assert "Prevention of Terrorism" in html
    assert f'href="{SCHEDULE_URL}"' in html


# ── The Schedule: a list, not a table ─────────────────────────────────────


def test_schedule_is_parsed_as_a_list():
    schedule = get_bare_act("pota").schedule("schedule")
    assert schedule is not None
    assert schedule.kind == "list"
    assert schedule.is_list and schedule.is_navigable
    assert not schedule.is_table
    assert schedule.parts == ()
    assert schedule.label == "THE SCHEDULE"
    assert schedule.reference == "See section 18"
    assert schedule.range_label == "1–32"


def test_schedule_has_all_32_entries_with_contiguous_serials():
    schedule = get_bare_act("pota").schedule("schedule")
    assert len(schedule.entries) == 32
    assert schedule.row_count == 32
    assert [e.serial_number for e in schedule.entries] == [str(i) for i in range(1, 33)]
    assert all(e.source_pages for e in schedule.entries)


def test_every_organisation_name_survives_the_adapter(tmp_path: Path):
    """The regression this whole batch exists for.

    Under the old dispatch every one of these came out as an empty cell,
    because `entries[]` alone routed POTA into the NDPS drug adapter.
    """
    schedule = get_bare_act("pota").schedule("schedule")
    assert all(e.text.strip() for e in schedule.entries)
    client, _ = _client(tmp_path)
    html = client.get(SCHEDULE_URL).text
    for entry in schedule.entries:
        assert entry.text in html, entry.serial_number


@pytest.mark.parametrize(
    "serial,fragment",
    [
        ("1", "Babbar Khalsa International"),
        ("23", "Deendar anjuman"),
        ("26", "Al Badr"),
        ("32", "Akhil Bharat Nepali Ekta Samaj (ABNES)"),
    ],
)
def test_named_schedule_entries(serial: str, fragment: str):
    schedule = get_bare_act("pota").schedule("schedule")
    (entry,) = [e for e in schedule.entries if e.serial_number == serial]
    assert fragment in entry.text


def test_serials_24_and_25_are_the_entries_the_explanation_carves_out():
    """The Explanation and section 1(6) both turn on these two serials.

    If the list were ever renumbered or an entry silently dropped, the
    Explanation would point at the wrong organisations while still reading
    correctly — so the cross-reference is pinned, not just the count.
    """
    schedule = get_bare_act("pota").schedule("schedule")
    by_serial = {e.serial_number: e.text for e in schedule.entries}
    assert "Communist Party of India (Marxist-Leninist)" in by_serial["24"]
    assert "Maoist Communist Centre (MCC)" in by_serial["25"]
    assert "serial numbers 24 and 25" in schedule.notes[0].text


def test_the_schedule_renders_as_a_list_and_never_as_a_table(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get(SCHEDULE_URL).text
    assert 'class="bareact-schedule-list"' in html
    assert "<table" not in html
    assert "<th" not in html
    # NDPS's drug headings must not leak onto an unrelated Act's schedule.
    for heading in ("Sl. No.", "International non-proprietary", "Chemical name"):
        assert heading not in html, heading


def test_serials_come_from_the_statute_not_from_css(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get(SCHEDULE_URL).text
    assert 'value="1"' in html
    assert 'value="32"' in html


# ── The Schedule's Explanation ────────────────────────────────────────────


def test_the_schedule_explanation_is_preserved():
    """Legally material: section 1(6) carves out serial numbers 24 and 25."""
    schedule = get_bare_act("pota").schedule("schedule")
    assert len(schedule.notes) == 1
    note = schedule.notes[0]
    assert note.label == "Explanation"
    assert note.number == ""
    assert note.marker == "Explanation."
    assert "serial numbers 24 and 25" in note.text
    assert note.source_pages == (26,)


def test_the_explanation_renders_under_the_list(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get(SCHEDULE_URL).text
    assert 'class="bareact-schedule-notes"' in html
    assert "Explanation." in html
    assert "serial numbers 24 and 25" in html
    assert "5th December, 2001" in html


def test_note_markers_are_punctuated_by_the_model_not_the_template():
    from constitution_memorizer.web.bare_acts import ScheduleNote

    assert ScheduleNote(number="1").marker == "1."
    assert ScheduleNote(label="Explanation").marker == "Explanation."
    # Already punctuated in the source: not doubled.
    assert ScheduleNote(label="Explanation.").marker == "Explanation."
    assert ScheduleNote().marker == ""


# ── Strict dispatch ───────────────────────────────────────────────────────


def test_a_declared_list_with_broken_entries_raises():
    """Fail loudly rather than render a schedule that looks empty."""
    from constitution_memorizer.web.bare_acts import _parse_schedule

    with pytest.raises(ValueError, match="no entries"):
        _parse_schedule({"id": "schedule", "type": "list", "entries": []})
    with pytest.raises(ValueError, match="no text"):
        _parse_schedule(
            {"id": "schedule", "type": "list", "entries": [{"serial_number": "1"}]}
        )


def test_a_partial_ndps_signature_is_preserved_not_guessed():
    """An unfamiliar `entries[]` shape must never enter the drug adapter."""
    from constitution_memorizer.web.bare_acts import _parse_schedule

    schedule = _parse_schedule(
        {
            "id": "schedule_mystery",
            "title": "SOMETHING NEW",
            # One NDPS field, not the complete signature.
            "entries": [{"serial_number": "1", "substance": "x"}],
        }
    )
    assert schedule.kind == "unsupported"
    assert schedule.raw_payload is not None
    assert schedule.raw_payload["entries"][0]["substance"] == "x"


# ── The other Acts are untouched ──────────────────────────────────────────


def test_ndps_schedule_still_dispatches_to_the_table_adapter(tmp_path: Path):
    schedule = get_bare_act("ndps").schedule("psychotropic-substances")
    assert schedule.kind == "table"
    assert schedule.entries == ()
    assert [c.key for c in schedule.parts[0].columns] == [
        "serial",
        "inn",
        "other",
        "chemical",
    ]
    assert schedule.range_label == "1–110ZT"
    client, _ = _client(tmp_path)
    assert client.get("/laws/ndps/schedule/psychotropic-substances").status_code == 200


def test_bnss_first_schedule_is_unchanged(tmp_path: Path):
    schedule = get_bare_act("bnss").schedule("first-schedule")
    assert schedule.kind == "table"
    assert len(schedule.parts) == 2
    assert schedule.row_count == 444
    assert [n.marker for n in schedule.notes] == ["1.", "2."]
    for part in schedule.parts:
        for row in part.rows:
            assert all(cell.strip() for cell in row.cells)
    client, _ = _client(tmp_path)
    assert client.get("/laws/bnss/schedule/first-schedule").status_code == 200


def test_bnss_second_schedule_is_still_deferred(tmp_path: Path):
    schedule = get_bare_act("bnss").schedule("second-schedule")
    assert schedule.kind == "unsupported"
    assert not schedule.is_navigable
    assert len(schedule.raw_payload["forms"]) == 58
    client, _ = _client(tmp_path)
    assert client.get("/laws/bnss/schedule/second-schedule").status_code == 404


# ── Lifecycle status ──────────────────────────────────────────────────────


def test_the_catalogue_marks_pota_repealed():
    from constitution_memorizer.web.law_catalog import load_catalog

    law = load_catalog().by_full_act("pota")
    assert law is not None
    assert law.status == "repealed"
    assert law.status_label == "Repealed / Historical"
    assert law.status_note == (
        "Repealed by the Prevention of Terrorism (Repeal) Act, 2004"
    )
    assert not law.is_current


def test_no_other_law_carries_a_status_badge():
    from constitution_memorizer.web.law_catalog import load_catalog

    badged = {law.id for law in load_catalog().laws if law.status_label}
    assert badged == {"pota"}


def test_the_status_label_is_derived_not_stored():
    """A law cannot be current and badged 'Repealed' at once."""
    from constitution_memorizer.web.law_catalog import load_catalog

    for law in load_catalog().laws:
        if law.is_current:
            assert law.status_label == ""
            assert law.status_note == ""


def test_an_unknown_status_is_rejected():
    from constitution_memorizer.web.law_catalog import CatalogError, parse_catalog

    from tests.test_law_catalog import SUBJECTS, _law

    with pytest.raises(CatalogError, match="unknown status"):
        parse_catalog(
            {"subjects": SUBJECTS[:1], "laws": [_law(status="lapsed")]},
            bare_act_ids=["ndps"],
            mapped_law_ids=[],
        )


def test_a_current_law_cannot_carry_a_status_note():
    from constitution_memorizer.web.law_catalog import CatalogError, parse_catalog

    from tests.test_law_catalog import SUBJECTS, _law

    with pytest.raises(CatalogError, match="status_note"):
        parse_catalog(
            {"subjects": SUBJECTS[:1], "laws": [_law(status_note="Repealed by X")]},
            bare_act_ids=["ndps"],
            mapped_law_ids=[],
        )


def test_the_status_shows_on_the_catalogue_and_the_act_page(tmp_path: Path):
    client, _ = _client(tmp_path)
    catalogue = client.get("/laws").text
    assert 'class="laws-index-status"' in catalogue
    assert "Repealed / Historical" in catalogue

    page = client.get("/laws/pota").text
    assert 'class="bareact-status"' in page
    assert "Repealed / Historical" in page
    assert "Repealed by the Prevention of Terrorism (Repeal) Act, 2004" in page


def test_current_acts_show_no_badge(tmp_path: Path):
    client, _ = _client(tmp_path)
    for slug in ("ndps", "bns", "bnss"):
        html = client.get(f"/laws/{slug}").text
        assert 'class="bareact-status"' not in html, slug
        assert "Repealed" not in html, slug


def test_the_repeal_sentence_is_not_in_the_statutory_json():
    """Editorial metadata stays out of the canonical text."""
    for path in (ARCHIVAL, RUNTIME):
        assert "Repeal) Act, 2004" not in path.read_text(encoding="utf-8"), path.name


def test_pota_is_still_listed_and_searchable(tmp_path: Path):
    """Historical does not mean hidden."""
    from constitution_memorizer.web.law_catalog import load_catalog

    law = load_catalog().by_full_act("pota")
    assert "repealed" in law.search_blob
    assert "pota" in law.search_blob
    client, _ = _client(tmp_path)
    html = client.get("/laws").text
    assert 'data-law-id="pota"' in html
    assert 'href="/laws/pota"' in html


def test_pota_is_free_to_read_and_records_nothing(tmp_path: Path):
    client, engine = _client(tmp_path)
    before = engine.stats()
    for url in ("/laws", "/laws/pota", "/laws/pota/section/1",
                "/laws/pota/section/64", SCHEDULE_URL):
        assert client.get(url).status_code == 200, url
    assert engine.stats() == before
    assert engine.due_today() == []


# ── Data invariants ───────────────────────────────────────────────────────


def test_runtime_is_the_canonical_file_minus_the_x_coordinate():
    archival = json.loads(ARCHIVAL.read_text(encoding="utf-8"))
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))

    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k != "source_x"}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    assert runtime == strip(archival)


def test_the_runtime_keeps_every_page_reference():
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    seen = 0

    def walk(value):
        nonlocal seen
        if isinstance(value, dict):
            if "source_pages" in value:
                seen += 1
                assert value["source_pages"], value.get("type")
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(runtime)
    assert seen > 300
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
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert '"web/pota_runtime_v1.json"' in pyproject


def test_the_registry_entry_matches_the_shipped_artifact():
    spec = BARE_ACTS["pota"]
    assert spec.filename == RUNTIME.name
    assert spec.render_profile == "bns"
    assert spec.patch_filenames == ()


def test_the_catalogue_scope_label_is_derived_from_the_act():
    from constitution_memorizer.web.law_catalog import load_catalog

    law = load_catalog().by_full_act("pota")
    act = get_bare_act("pota")
    assert law.scope_label == act.meta_label
    assert law.title == act.title
