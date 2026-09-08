"""The Bharatiya Nagarik Suraksha Sanhita, 2023 — the third Bare Act.

Two things here are new to the reader and carry most of the risk:

* the **generic schedule model** — parts, N columns, notes — replacing a model
  hardcoded to NDPS's four drug columns, without touching NDPS's dataset;
* the **Second Schedule**, 58 positioned-text forms with no table
  representation, which must be preserved whole rather than coerced or dropped.

The operative 531 sections reuse the BNS render profile unchanged.
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
ARCHIVAL = REPO / "data" / "reference" / "bnss_canonical_v3.json"
RUNTIME = REPO / "src" / "constitution_memorizer" / "web" / "bnss_runtime_v1.json"

CHAPTERS_WITH_DIVISIONS = {"VI", "VII", "XI", "XVIII", "XX", "XXV", "XXXIV"}


def _client(tmp_path: Path) -> tuple[TestClient, ReminderEngine]:
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    return TestClient(create_app(units_path=MINI_UNITS, db_path=db)), engine


# ── The Act ───────────────────────────────────────────────────────────────


def test_the_whole_act_is_present():
    act = get_bare_act("bnss")
    assert act.title == "The Bharatiya Nagarik Suraksha Sanhita, 2023"
    assert len(act.chapters) == 39
    assert len(act.section_order) == 531
    assert act.meta_label == "39 Chapters · Sections 1–531"
    # Reuses BNS's vocabulary rather than forking a third profile.
    assert act.render_profile == "bns"


def test_first_and_last_sections_resolve():
    act = get_bare_act("bnss")
    numbers = [s.number for s in act.section_order]
    assert numbers == [str(n) for n in range(1, 532)]
    assert all(isinstance(n, str) for n in numbers)
    assert act.section("1") is not None
    assert act.section("531") is not None
    assert [s.number if s else None for s in act.neighbours("1")] == [None, "2"]
    assert [s.number if s else None for s in act.neighbours("531")] == ["530", None]


def test_divisions_group_and_ungrouped_sections_stay_ungrouped():
    act = get_bare_act("bnss")
    with_divisions = {
        c.number for c in act.chapters if any(s.starts_division for s in c.sections)
    }
    assert with_divisions == CHAPTERS_WITH_DIVISIONS
    assert sum(1 for c in act.chapters for s in c.sections if s.starts_division) == 24
    # A section with no division id never opens one, in any chapter.
    for chapter in act.chapters:
        for section in chapter.sections:
            if section.division_id is None:
                assert not section.starts_division, section.number


@pytest.mark.parametrize(
    "number,kind",
    [("9", "proviso"), ("1", "explanation"), ("234", "illustrations"),
     ("234", "illustration"), ("35", "item"), ("2", "subclause")],
)
def test_each_node_kind_renders(tmp_path: Path, number: str, kind: str):
    client, _ = _client(tmp_path)
    html = client.get(f"/laws/bnss/section/{number}").text
    assert f"is-{kind}" in html


def test_deepest_nesting_renders(tmp_path: Path):
    act = get_bare_act("bnss")
    deep = [s.number for s in act.section_order if any(r.depth == 3 for r in s.rows)]
    assert deep == ["35", "129"]
    client, _ = _client(tmp_path)
    html = client.get("/laws/bnss/section/35").text
    assert 'style="--depth: 3"' in html


def test_the_chapter_list(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/bnss").text
    assert html.count("<details") == 39
    assert 'class="bareact-page is-bns"' in html or "bareact-page is-bns" in html
    assert html.count('class="bareact-division"') == 24
    # One schedule row: the First. The Second has no table representation.
    assert html.count('class="bareact-schedule-row"') == 1
    assert 'href="/laws/bnss/schedule/first-schedule"' in html
    assert "second-schedule" not in html


def test_bnss_is_on_the_catalogue(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws").text
    assert 'href="/laws/bnss"' in html
    assert "The Bharatiya Nagarik Suraksha Sanhita, 2023" in html
    assert "39 Chapters · Sections 1–531" in html


# ── First Schedule: the generic model ─────────────────────────────────────


def test_first_schedule_shape():
    schedule = get_bare_act("bnss").schedule("first-schedule")
    assert schedule is not None and schedule.is_table
    # BNSS names by ordinal and titles by subject; NDPS carries both in title.
    assert schedule.number == "First"
    assert schedule.title == "CLASSIFICATION OF OFFENCES"
    assert schedule.label == "FIRST SCHEDULE"
    assert schedule.display_heading == "Classification of Offences"
    assert len(schedule.parts) == 2
    part_i, part_ii = schedule.parts
    assert len(part_i.rows) == 441
    assert len(part_i.columns) == 6
    assert len(part_ii.rows) == 3
    assert len(part_ii.columns) == 4
    assert [c.heading for c in part_i.columns][:2] == ["Section", "Offence"]
    assert schedule.row_count == 444


def test_first_schedule_notes_are_preserved():
    schedule = get_bare_act("bnss").schedule("first-schedule")
    assert len(schedule.notes) == 2
    assert [n.number for n in schedule.notes] == ["1", "2"]
    assert all(n.text for n in schedule.notes)
    # Notes carry their own page provenance; the model must not drop it.
    assert all(n.source_pages for n in schedule.notes)


@pytest.mark.parametrize("section", ["250(a)", "319(2)", "332(a)", "357"])
def test_named_first_schedule_records_render(tmp_path: Path, section: str):
    """Row groups are used exactly as supplied — never re-split or re-paired."""
    schedule = get_bare_act("bnss").schedule("first-schedule")
    rows = [r for r in schedule.parts[0].rows if r.cells[0] == section]
    assert len(rows) == 1, section
    assert rows[0].cells[1], section  # has an offence
    client, _ = _client(tmp_path)
    html = client.get("/laws/bnss/schedule/first-schedule").text
    assert f">{section}</td>" in html


def test_first_schedule_page_renders_both_parts_and_notes(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/bnss/schedule/first-schedule").text
    assert html.count("<table") == 2
    assert html.count("<tbody") == 2
    # Headings come from the schedule's own metadata, not the template.
    assert "Cognizable or non-cognizable" in html
    assert "By what Court triable" in html
    assert 'class="bareact-schedule-notes"' in html
    assert html.count('class="bareact-schedule-note"') == 2
    assert html.count("<tr>") == 444 + 2  # rows + one header row per part


def test_row_provenance_is_normalised():
    """Part I ships `source_pages`; Part II ships the singular `source_page`."""
    part_i, part_ii = get_bare_act("bnss").schedule("first-schedule").parts
    assert all(isinstance(r.source_pages, tuple) for r in part_i.rows)
    assert all(r.source_pages for r in part_i.rows)
    assert all(r.source_pages for r in part_ii.rows)


# ── Second Schedule: preserved, not rendered ──────────────────────────────


def test_second_schedule_is_kept_whole_and_not_coerced():
    act = get_bare_act("bnss")
    assert len(act.schedules) == 2
    second = act.schedules[1]
    assert second.slug == "second-schedule"
    assert not second.is_table
    assert second.kind == "unsupported"
    assert "forms" in second.unsupported_reason
    # Not flattened into a fake table.
    assert second.parts == ()
    assert second.row_count == 0
    # …and not discarded either: every form survives on the payload.
    assert second.raw_payload is not None
    assert len(second.raw_payload["forms"]) == 58


def test_form_fragments_keep_their_coordinates():
    """The strip is path-aware: coordinates are debris in body text, content here.

    Form 1 places "Serial No……." and "Police Station………" at the same
    `source_y` with different `source_x`. That pair *is* a two-column header,
    and a global strip would destroy it.
    """
    forms = json.loads(RUNTIME.read_text(encoding="utf-8"))["schedules"][1]["forms"]
    assert len(forms) == 58
    missing = [
        (f["number"], i)
        for f in forms
        for i, frag in enumerate(f["body"])
        if "source_x" not in frag or "source_y" not in frag
    ]
    assert missing == []
    first, second = forms[0]["body"][0], forms[0]["body"][1]
    assert first["source_y"] == second["source_y"]
    assert first["source_x"] != second["source_x"]


def test_the_second_schedule_has_no_reachable_page(tmp_path: Path):
    client, _ = _client(tmp_path)
    assert client.get("/laws/bnss/schedule/second-schedule").status_code == 404
    assert client.get("/laws/bnss/schedule/nope").status_code == 404


# ── The runtime artifact ──────────────────────────────────────────────────


def test_runtime_is_the_canonical_file_minus_audit_fields():
    """One deep equality, path-aware. Not a global key drop."""
    archival = json.loads(ARCHIVAL.read_text(encoding="utf-8"))
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    body_drop = {"source_x"}
    row_drop = {
        "source_y", "offence_lines", "punishment_lines",
        "cognizable_lines", "bailability_lines", "court_lines",
    }
    arrays = {"source_line_inventory"}

    def strip_body(nodes):
        return [
            {
                **{k: v for k, v in n.items() if k not in body_drop},
                "children": strip_body(n.get("children") or []),
            }
            for n in nodes
        ]

    def strip_schedule(s):
        out = {k: v for k, v in s.items() if k not in arrays}
        if "parts" in out:
            out["parts"] = [
                {
                    **p,
                    "rows": [
                        {k: v for k, v in r.items() if k not in row_drop}
                        for r in p.get("rows") or []
                    ],
                }
                for p in out["parts"]
            ]
        return out

    expected = {k: v for k, v in archival.items() if k not in arrays}
    expected["chapters"] = [
        {
            **c,
            "sections": [
                {**s, "body": strip_body(s.get("body") or [])}
                for s in c.get("sections") or []
            ],
        }
        for c in expected.get("chapters") or []
    ]
    expected["schedules"] = [strip_schedule(s) for s in expected.get("schedules") or []]
    assert runtime == expected


def test_operative_text_loses_only_the_x_coordinate():
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    node = runtime["chapters"][0]["sections"][0]["body"][0]
    assert "source_x" not in node
    assert "source_pages" in node  # provenance stays


def test_the_script_regenerates_the_committed_runtime_file():
    before = RUNTIME.read_bytes()
    subprocess.run(
        [sys.executable, str(REPO / "scripts" / "strip_bare_act_debug.py")],
        check=True, capture_output=True, cwd=REPO,
    )
    assert RUNTIME.read_bytes() == before


def test_runtime_copy_is_declared_as_package_data():
    assert '"web/bnss_runtime_v1.json"' in (REPO / "pyproject.toml").read_text()


def test_the_registry_entry_matches_the_shipped_artifact():
    spec = BARE_ACTS["bnss"]
    assert spec.filename == "bnss_runtime_v1.json"
    assert spec.render_profile == "bns"
    assert spec.patch_filenames == ()


# ── Nothing else moves ────────────────────────────────────────────────────


def test_bnss_is_free_to_read_and_records_nothing(tmp_path: Path):
    client, engine = _client(tmp_path)
    before = engine.stats()
    for path in (
        "/laws", "/laws/bnss", "/laws/bnss/section/1", "/laws/bnss/section/531",
        "/laws/bnss/schedule/first-schedule",
    ):
        assert client.get(path).status_code == 200, path
    assert engine.stats() == before
    assert engine.due_today() == []


def test_identifier_columns_never_wrap(tmp_path: Path):
    """Regression: a 34px fixed serial column wrapped "110ZT" onto two lines.

    Every schedule table now scrolls and sizes columns to content, so an
    identifier stays on one line and prose wraps at a readable measure rather
    than at whatever width is left over.
    """
    client, _ = _client(tmp_path)
    css = client.get("/static/styles.css").text
    ident = css.split(".bareact-schedule-table th.is-serial,", 1)[1].split("}", 1)[0]
    assert "white-space: nowrap" in ident
    prose = css.split(
        ".bareact-schedule-table th:not(.is-serial):not(.is-section),", 1
    )[1].split("}", 1)[0]
    assert "min-width" in prose and "max-width" in prose


def test_ndps_column_typography_survived_the_generic_refactor(tmp_path: Path):
    """Per-column sizing moved to the column key; the appearance did not."""
    client, _ = _client(tmp_path)
    css = client.get("/static/styles.css").text
    for key, size in (("serial", "10.5px"), ("inn", "10.5px"),
                      ("other", "10.5px"), ("chemical", "10px")):
        rule = css.split(f".bareact-schedule-table td.is-{key} {{", 1)[1].split("}", 1)[0]
        assert f"font-size: {size}" in rule, key
    html = client.get("/laws/ndps/schedule/psychotropic-substances").text
    for key in ("serial", "inn", "other", "chemical"):
        assert f'class="is-{key}"' in html, key


def test_ndps_schedule_still_renders_at_its_own_url(tmp_path: Path):
    """Adapted into the generic model, not migrated — URL and page unchanged."""
    client, _ = _client(tmp_path)
    response = client.get("/laws/ndps/schedule/psychotropic-substances")
    assert response.status_code == 200
    html = response.text
    assert html.count("<table") == 1
    assert "N, N-Diethyltryptamine" in html
    assert "Sl. No." in html
    assert html.count("<tr>") == 163  # 162 entries + one header
