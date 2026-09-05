"""The Bharatiya Nyaya Sanhita, 2023 — the second Bare Act.

The pathway was built so a second Act cost a JSON file and a registry entry.
That held for loading; it did not hold for rendering, because BNS brings node
types NDPS has no concept of (`exception`, `illustrations`, `illustration`) and
a structural level between chapter and section (divisions).

The load-bearing tests here are the strip invariant, the empty-text inventory,
the division boundaries, and NDPS's appearance staying exactly where it was.
"""

from __future__ import annotations

import collections
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web import bare_acts
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act

REPO = Path(__file__).resolve().parents[1]
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ARCHIVAL = REPO / "data" / "reference" / "bns_canonical_v1.json"
RUNTIME = REPO / "src" / "constitution_memorizer" / "web" / "bns_runtime_v1.json"

# Divisions occur in 7 of 20 chapters. The other 13 have none.
DIVISIONS_BY_CHAPTER = {
    "III": 1, "IV": 3, "V": 5, "VI": 5, "XVII": 10, "XVIII": 1, "XIX": 1,
}
# Chapters that open with ungrouped sections before their first division.
UNGROUPED_PREFIX = {"III": ("14", "33"), "XVIII": ("335", "344"), "XIX": ("351", "355")}


def _client(tmp_path: Path) -> tuple[TestClient, ReminderEngine]:
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    return TestClient(create_app(units_path=MINI_UNITS, db_path=db)), engine


def _strip(value: Any, key: str = "source_x") -> Any:
    if isinstance(value, dict):
        return {k: _strip(v, key) for k, v in value.items() if k != key}
    if isinstance(value, list):
        return [_strip(v, key) for v in value]
    return value


def _walk(nodes):
    for node in nodes or []:
        yield node
        yield from _walk(node.get("children") or [])


def _all_nodes(doc):
    for chapter in doc["chapters"]:
        for section in chapter["sections"]:
            yield from _walk(section.get("body") or [])


# ── The strip invariant ───────────────────────────────────────────────────


def test_runtime_is_the_archival_file_minus_source_x():
    """One deep equality, not a sampled comparison.

    Comparing text values alone would let a bad script drop a label, a type, a
    child relationship or node order and still pass. Section 8's "(6)" and
    Section 2's "Explanation" are exactly the information such a check misses.
    """
    archival = json.loads(ARCHIVAL.read_text(encoding="utf-8"))
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    assert runtime == _strip(archival)


def test_no_source_x_survives_and_provenance_does():
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    assert "source_x" not in RUNTIME.read_text(encoding="utf-8")
    # source_pages says where the text came from. That is provenance, not debris.
    assert all("source_pages" in n for n in _all_nodes(runtime))
    assert runtime["source_file"]["sha256"]
    assert runtime["long_title"] and runtime["enacting_formula"]


def test_structure_is_untouched_by_the_strip():
    archival = json.loads(ARCHIVAL.read_text(encoding="utf-8"))
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    for doc in (archival, runtime):
        assert len(doc["chapters"]) == 20
        assert sum(len(c["sections"]) for c in doc["chapters"]) == 358
        assert sum(len(c.get("divisions") or []) for c in doc["chapters"]) == 26
        assert len(list(_all_nodes(doc))) == 1434
    for a_ch, r_ch in zip(archival["chapters"], runtime["chapters"]):
        assert a_ch["title"] == r_ch["title"]
        for a_s, r_s in zip(a_ch["sections"], r_ch["sections"]):
            assert (a_s["number"], a_s["title"]) == (r_s["number"], r_s["title"])
            assert a_s.get("division_id") == r_s.get("division_id")
            assert a_s.get("division_title") == r_s.get("division_title")
    a_nodes = [(n["type"], n.get("label"), n.get("text")) for n in _all_nodes(archival)]
    r_nodes = [(n["type"], n.get("label"), n.get("text")) for n in _all_nodes(runtime)]
    assert a_nodes == r_nodes


def test_the_script_regenerates_the_committed_runtime_file():
    before = RUNTIME.read_bytes()
    subprocess.run(
        [sys.executable, str(REPO / "scripts" / "strip_bare_act_debug.py")],
        check=True, capture_output=True, cwd=REPO,
    )
    assert RUNTIME.read_bytes() == before


def test_runtime_copy_is_declared_as_package_data():
    assert '"web/bns_runtime_v1.json"' in (REPO / "pyproject.toml").read_text()


# ── The Act ───────────────────────────────────────────────────────────────


def test_the_whole_act_is_present():
    act = get_bare_act("bns")
    assert act.title == "The Bharatiya Nyaya Sanhita, 2023"
    assert len(act.chapters) == 20
    assert len(act.section_order) == 358
    assert act.meta_label == "20 Chapters · Sections 1–358"
    assert act.render_profile == "bns"


def test_section_numbers_stay_strings_in_the_acts_own_order():
    act = get_bare_act("bns")
    numbers = [s.number for s in act.section_order]
    assert numbers == [str(n) for n in range(1, 359)]
    assert all(isinstance(n, str) for n in numbers)


def test_node_type_counts():
    act = get_bare_act("bns")
    counts = collections.Counter()
    for section in act.section_order:
        for row in section.rows:
            counts[row.kind] += 1
    # Every node is rendered: 1434 total, none silently dropped.
    assert sum(counts.values()) == 1434
    assert counts == {
        "paragraph": 303, "illustration": 271, "clause": 270, "subsection": 264,
        "explanation": 117, "illustrations": 96, "subclause": 47, "proviso": 29,
        "exception": 27, "item": 10,
    }


def test_absent_fields_degrade_as_designed():
    """BNS is schema 1.0; NDPS is 2.5. None of the gaps may raise."""
    act = get_bare_act("bns")
    assert act.footnotes == {}
    assert act.schedules == ()
    assert all(not s.is_omitted for s in act.section_order)
    assert all(not r.note_ids for s in act.section_order for r in s.rows)


# ── Empty-text nodes ──────────────────────────────────────────────────────


def test_the_empty_text_inventory_is_exactly_98_nodes():
    """96 illustration containers, plus two labelled structural parents.

    Any change here wants review: this is the set the label-only rendering
    rule exists for.
    """
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    empty = collections.Counter(
        (n["type"], n.get("label"))
        for n in _all_nodes(runtime)
        if not (n.get("text") or "").strip()
    )
    assert sum(empty.values()) == 98
    assert empty == {
        ("illustrations", None): 96,
        ("explanation", "Explanation"): 1,
        ("subsection", "(6)"): 1,
    }


def test_a_labelled_node_renders_even_with_no_text():
    """A subsection number is part of how the provision is cited."""
    act = get_bare_act("bns")
    eight = [r for r in act.section("8").rows if r.label == "(6)"]
    assert len(eight) == 1
    assert eight[0].text == ""
    two = [
        r for r in act.section("2").rows
        if r.kind == "explanation" and r.label == "Explanation" and not r.text
    ]
    assert len(two) == 1


# ── Divisions ─────────────────────────────────────────────────────────────


def test_division_headings_land_once_per_division():
    act = get_bare_act("bns")
    starts = {
        c.number: sum(1 for s in c.sections if s.starts_division)
        for c in act.chapters
    }
    assert {k: v for k, v in starts.items() if v} == DIVISIONS_BY_CHAPTER
    assert sum(starts.values()) == 26


@pytest.mark.parametrize("chapter_number,span", sorted(UNGROUPED_PREFIX.items()))
def test_sections_before_a_first_division_stay_ungrouped(chapter_number, span):
    """The guard against a later division bleeding upward over earlier sections."""
    act = get_bare_act("bns")
    chapter = next(c for c in act.chapters if c.number == chapter_number)
    first, last = span
    prefix = []
    for section in chapter.sections:
        if section.division_id is not None:
            break
        prefix.append(section)
    assert (prefix[0].number, prefix[-1].number) == (first, last)
    assert all(not s.starts_division for s in prefix)
    assert all(s.division_title is None for s in prefix)


def test_the_ungrouped_prefix_is_absent_from_the_page(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/bns").text
    # Chapter III's heading must appear once, and below section 33's row.
    assert html.count("Of right of private defence") == 1
    assert html.index("/laws/bns/section/33") < html.index("Of right of private defence")
    assert html.index("Of right of private defence") < html.index("/laws/bns/section/34")
    assert html.count('class="bareact-division"') == 26


# ── Rendering: the handoff's QA sections ──────────────────────────────────


@pytest.mark.parametrize(
    "number",
    ["6", "116", "1", "2", "4", "63", "101", "113", "335", "356",
     "111", "178", "294", "358"],
)
def test_qa_sections_render(tmp_path: Path, number: str):
    client, _ = _client(tmp_path)
    response = client.get(f"/laws/bns/section/{number}")
    assert response.status_code == 200
    assert 'class="bareact-row' in response.text


def test_section_1_mixes_subsections_explanation_and_an_illustration(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/bns/section/1").text
    assert "Explanation.—" in html
    assert "is-explanation is-block-break" in html
    assert "is-illustrations" in html
    assert ">Illustration<" in html  # one child, so singular
    assert "is-illustration\"" in html


def test_section_335_names_the_block_in_the_plural(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/bns/section/335").text
    assert ">Illustrations<" in html


def test_exceptions_and_explanations_carry_the_em_dash(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/bns/section/63").text
    assert "Exception 1.—" in html
    assert "is-exception is-block-break" in html


def test_labels_are_not_double_punctuated():
    from constitution_memorizer.web.bare_acts import ProvisionRow

    already = ProvisionRow(
        depth=0, kind="exception", label="Exception 1.", text="x", profile="bns"
    )
    assert already.display_label == "Exception 1."


def test_asides_and_illustrations_carry_no_marker(tmp_path: Path):
    act = get_bare_act("bns")
    for section in act.section_order:
        for row in section.rows:
            if row.kind in {"explanation", "exception", "proviso",
                            "illustration", "illustrations"}:
                assert not row.shows_marker, (section.number, row.kind)
            else:
                assert row.shows_marker, (section.number, row.kind)


def test_the_chapter_list_and_laws_card(tmp_path: Path):
    client, _ = _client(tmp_path)
    chapters = client.get("/laws/bns").text
    assert chapters.count("<details") == 20
    assert "The Bharatiya Nyaya Sanhita, 2023" in chapters
    assert "Of Offences Affecting the Human Body" in chapters  # title-cased
    assert "bareact-schedule-row" not in chapters  # BNS has no schedule
    laws = client.get("/laws").text
    assert 'href="/laws/bns"' in laws
    assert "20 Chapters · Sections 1–358" in laws
    # NDPS is listed first: registry order, and it shipped first.
    assert laws.index('href="/laws/ndps"') < laws.index('href="/laws/bns"')


def test_bns_is_free_to_read_and_records_nothing(tmp_path: Path):
    client, engine = _client(tmp_path)
    before = engine.stats()
    for path in ("/laws/bns", "/laws/bns/section/1", "/laws/bns/section/358"):
        assert client.get(path).status_code == 200
    assert engine.stats() == before
    assert client.get("/laws/bns/section/999").status_code == 404
    assert client.get("/laws/bns/schedule/anything").status_code == 404


# ── NDPS must not move ────────────────────────────────────────────────────


def test_ndps_rendering_is_unchanged(tmp_path: Path):
    """The load-bearing isolation test.

    "Keep NDPS as-is" has to be enforceable, not aspirational: if a BNS rule
    reaches an NDPS proviso or explanation, this fails.
    """
    client, _ = _client(tmp_path)
    html = client.get("/laws/ndps/section/2").text
    assert 'class="bareact-row-kind">Explanation<' in html
    assert "is-aside is-explanation" in html
    assert "is-aside is-proviso" in html
    # None of the BNS vocabulary may appear on an NDPS page.
    for token in ("is-block-break", "is-illustration", "is-exception", ".—"):
        assert token not in html, token
    assert 'class="bareact-page is-ndps"' in html or "bareact-page is-ndps" in html
    # Every NDPS row still carries its marker.
    act = get_bare_act("ndps")
    assert all(r.shows_marker for s in act.section_order for r in s.rows)


def test_bns_css_cannot_reach_ndps(tmp_path: Path):
    client, _ = _client(tmp_path)
    for sheet in ("/static/styles.css", "/static/mobile.css"):
        css = client.get(sheet).text
        for line in css.splitlines():
            stripped = line.strip()
            if "is-bns" in stripped and stripped.startswith("."):
                assert ".bareact-page.is-bns" in stripped, stripped
            if any(
                token in stripped
                for token in (".is-illustration", ".is-exception", ".is-block-break")
            ) and stripped.startswith("."):
                assert "is-bns" in stripped, stripped
