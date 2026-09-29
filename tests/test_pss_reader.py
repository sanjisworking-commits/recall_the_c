"""The Payment and Settlement Systems Act, 2007 — the sixth Bare Act.

Almost all of this Act reuses machinery that already exists: the BNS render
profile covers its six node types, it has no schedules at all, and a flat
`source_x` strip derives its runtime copy.

One thing is new. PSS prints "2[CHAPTER II" — a whole chapter inside an
amendment span, closing at the end of its only section. Sections, provisions,
schedules and list entries already carry `leading_brackets`; chapters did not,
so the opening bracket was dropped at load and its closer was orphaned. The
validator caught it before any integration work, which is what it is for.

The parser-side audit is pinned here too: the structures corrected across
PSS v1 → v3 are asserted against the shipped artifact so a future regeneration
cannot quietly undo them.
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
ARCHIVAL = REPO / "data" / "reference" / "pss_canonical_v3.json"
RUNTIME = REPO / "src" / "constitution_memorizer" / "web" / "pss_runtime_v1.json"

LETTERED = ["10A", "23A", "34A", "34B"]
SECTION_IDS = [
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "10A", "11", "12", "13",
    "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "23A", "24",
    "25", "26", "27", "28", "29", "30", "31", "32", "33", "34", "34A", "34B",
    "35", "36", "37", "38",
]


def _client(tmp_path: Path) -> tuple[TestClient, ReminderEngine]:
    db = tmp_path / "progress.db"
    engine = ReminderEngine.from_paths(db, MINI_UNITS)
    return TestClient(create_app(units_path=MINI_UNITS, db_path=db)), engine


def _rows(number: str):
    return get_bare_act("pss").section(number).rows


def _all_rows():
    return [r for s in get_bare_act("pss").section_order for r in s.rows]


# ── The Act ───────────────────────────────────────────────────────────────


def test_the_whole_act_is_present():
    act = get_bare_act("pss")
    assert act.title == "The Payment and Settlement Systems Act, 2007"
    assert act.short_name == "The PSS Act, 2007"
    assert len(act.chapters) == 8
    assert len(act.section_order) == 42
    # 42 section records spanning printed numbers 1 to 38: the lettered ones
    # sit between, exactly as UAPA's 67 records span 1 to 53.
    assert act.meta_label == "8 Chapters · Sections 1–38"
    assert act.render_profile == "bns"


def test_section_order_is_the_canonical_order():
    """Guards a lexical sort, which would move 10A after 10 but before 2."""
    assert [s.number for s in get_bare_act("pss").section_order] == SECTION_IDS
    assert len(set(SECTION_IDS)) == 42


@pytest.mark.parametrize("number", LETTERED)
def test_lettered_sections_resolve_and_serve(tmp_path: Path, number: str):
    assert get_bare_act("pss").section(number) is not None
    client, _ = _client(tmp_path)
    assert client.get(f"/laws/pss/section/{number}").status_code == 200


def test_chapters_are_contiguous_and_cover_every_section():
    act = get_bare_act("pss")
    spans = [(c.number, c.sections[0].number, c.sections[-1].number) for c in act.chapters]
    assert spans == [
        ("I", "1", "2"),
        ("II", "3", "3"),
        ("III", "4", "9"),
        ("IV", "10", "19"),
        ("V", "20", "23A"),
        ("VI", "24", "25"),
        ("VII", "26", "31"),
        ("VIII", "32", "38"),
    ]
    assert sum(len(c.sections) for c in act.chapters) == 42


def test_the_act_has_no_schedules():
    act = get_bare_act("pss")
    assert act.schedules == ()
    assert act.public_schedule_slugs == ()


def test_every_node_kind_is_already_in_the_bns_profile():
    kinds = {r.kind for r in _all_rows()}
    assert kinds == {
        "subsection", "clause", "subclause", "paragraph", "proviso", "explanation",
    }
    assert get_bare_act("pss").render_profile == "bns"


# ── The chapter-level amendment span ──────────────────────────────────────


def test_chapter_two_carries_the_amendment_bracket():
    """PSS prints "2[CHAPTER II", closing at the end of its only section."""
    act = get_bare_act("pss")
    chapter = next(c for c in act.chapters if c.number == "II")
    assert chapter.leading_brackets == 1
    assert chapter.bracket_prefix == "["
    assert len(chapter.sections) == 1
    assert act.section("3").rows[-1].text.rstrip().endswith("]")


def test_no_other_chapter_of_any_act_carries_one():
    """The shared field is demonstrably inert outside PSS."""
    for slug in ("ndps", "bns", "bnss", "pota", "uapa", "pss"):
        for chapter in get_bare_act(slug).chapters:
            expected = 1 if (slug, chapter.number) == ("pss", "II") else 0
            assert chapter.leading_brackets == expected, (slug, chapter.number)
            assert chapter.bracket_prefix == "[" * expected


def test_pss_has_no_bracket_orphan():
    """Without the chapter field this reported ('unmatched-close', 's3 (4)')."""
    assert get_bare_act("pss").unbalanced_brackets() == ()


def test_the_chapter_bracket_renders_before_the_chapter_tag(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws/pss").text
    assert '<span class="bareact-amendment-open">[</span>Chapter II' in html
    assert html.count('class="bareact-amendment-open"') == 1


def test_other_acts_render_no_chapter_bracket(tmp_path: Path):
    client, _ = _client(tmp_path)
    for slug in ("ndps", "bns", "bnss", "pota", "uapa"):
        html = client.get(f"/laws/{slug}").text
        chapters = html.split('class="bareact-chapter-row"')
        for block in chapters[1:]:
            tag = block.split("</span>", 1)[0]
            assert "bareact-amendment-open" not in tag, slug


# ── Structures corrected across the parser revisions ──────────────────────


def test_section_8_1_does_not_fabricate_a_sentence():
    """v1 produced "If a system provider,— the Reserve Bank may ...".

    The concluding words print after clauses (i)-(iv); folding them into the
    lead invented a sentence the Act does not contain.
    """
    sub = get_bare_act("pss").section("8").body[0]
    assert sub["label"] == "(1)"
    assert sub["text"] == "If a system provider,—"
    kinds = [(c["type"], c.get("label") or "") for c in sub["children"]]
    assert kinds == [
        ("clause", "(i)"), ("clause", "(ii)"), ("clause", "(iii)"),
        ("clause", "(iv)"), ("paragraph", ""), ("proviso", ""),
    ]
    proviso = sub["children"][-1]
    assert [c.get("label") for c in proviso["children"]] == ["(i)", "(ii)"]


def test_section_9_1_is_one_continuous_sentence():
    """v1 split it after "from the date on" because the next line began "which"."""
    sub = get_bare_act("pss").section("9").body[0]
    assert sub["children"] == []
    assert sub["text"].endswith("appeal to the Central Government.")
    assert "from the date on which the order is communicated" in sub["text"]


def test_section_2_1_o_owns_its_conclusion_and_proviso():
    body = get_bare_act("pss").section("2").body[0]
    clause = next(c for c in body["children"] if c.get("label") == "(o)")
    assert [(c["type"], c.get("label") or "") for c in clause["children"]] == [
        ("subclause", "(i)"), ("subclause", "(ii)"), ("paragraph", ""), ("proviso", ""),
    ]
    following = [c.get("label") for c in body["children"]]
    assert following[following.index("(o)") + 1] == "(p)"


def test_section_17_concluding_paragraph_owns_its_own_list():
    body = get_bare_act("pss").section("17").body
    assert len(body) == 1
    lead = body[0]
    assert [c.get("label") for c in lead["children"] if c.get("label")] == ["(a)", "(b)"]
    concluding = lead["children"][-1]
    assert concluding["type"] == "paragraph"
    assert [c.get("label") for c in concluding["children"]] == ["(i)", "(ii)"]


@pytest.mark.parametrize(
    "label,expect_children",
    [("(4)", ["(a)", "(b)", ""]), ("(5)", []), ("(6)", ["(a)", "(b)"])],
)
def test_section_23_subsections(label: str, expect_children: list[str]):
    sub = next(n for n in get_bare_act("pss").section("23").body if n.get("label") == label)
    assert [c.get("label") or "" for c in sub["children"]] == expect_children


def test_section_23_6_b_keeps_its_own_continuation():
    sub = next(n for n in get_bare_act("pss").section("23").body if n.get("label") == "(6)")
    clause_b = next(c for c in sub["children"] if c.get("label") == "(b)")
    assert clause_b["text"].rstrip().endswith(
        "return the collaterals held in excess to the system participants concerned.]"
    )


def test_section_23_explanations():
    body = get_bare_act("pss").section("23").body
    explanations = [n for n in body if n["type"] == "explanation"]
    assert [n["label"] for n in explanations] == ["Explanation 1", "Explanation 2"]
    # "[Explanation 1]" — the closing bracket stays at the head of the text so
    # the pair survives in printed order once the opener is rendered.
    assert explanations[0].get("leading_brackets") == 1
    assert explanations[0]["text"].startswith("]")
    assert explanations[1].get("leading_brackets") == 1
    assert explanations[1]["text"].rstrip().endswith("]")


def test_section_34a_subsection_2_returns_to_top_level():
    """It resumes after a page break, where a stack parser can strand it."""
    body = get_bare_act("pss").section("34A").body
    assert [(n["type"], n.get("label") or "") for n in body] == [
        ("subsection", "(1)"),
        ("subsection", "(2)"),
        ("explanation", "Explanation"),
    ]
    one = body[0]
    clause_b = next(c for c in one["children"] if c.get("label") == "(b)")
    assert [c.get("label") for c in clause_b["children"]] == ["(i)", "(ii)"]


def test_section_34b_continuation_belongs_to_clause_b():
    clause_b = next(
        c for c in get_bare_act("pss").section("34B").body[0]["children"]
        if c.get("label") == "(b)"
    )
    assert "in so far as regulation of financial products" in clause_b["text"]


# ── Source oddities that must never be "repaired" ─────────────────────────


def test_section_38_prints_two_subsections_labelled_2():
    """A real source anomaly, preserved and recorded rather than renumbered."""
    labels = [n.get("label") for n in get_bare_act("pss").section("38").body]
    assert labels == ["(1)", "(2)", "(2)", "(3)"]
    anomalies = json.loads(ARCHIVAL.read_text(encoding="utf-8"))["_validation"][
        "source_anomalies"
    ]
    assert any(a["section"] == "38" and a["label"] == "(2)" for a in anomalies)


@pytest.mark.parametrize(
    "number,fragment",
    [
        ("2", "only a net claim be demanded or a net obligation be owned"),
        ("37", "make such provision is not inconsistent"),
    ],
)
def test_awkward_source_wording_is_preserved(number: str, fragment: str):
    assert any(fragment in r.text for r in _rows(number))


def test_the_page_separator_is_not_statutory_text():
    """v2 pulled "_____________" into s.38(3) by classifying it as body."""
    assert not any("___" in r.text for r in _all_rows())
    last = get_bare_act("pss").section("38").rows[-1]
    assert last.text.rstrip().endswith("under that regulation.")


def test_no_whitespace_damage_from_removed_footnote_anchors():
    for row in _all_rows():
        assert "  " not in row.text
        assert not re.search(r"\s[,;.](?!\.)", row.text)
        assert "￾" not in row.text


# ── Catalogue ─────────────────────────────────────────────────────────────


def test_pss_is_catalogued_under_the_new_financial_subject():
    from constitution_memorizer.web.law_catalog import load_catalog

    catalog = load_catalog()
    law = catalog.by_full_act("pss")
    assert law is not None
    assert law.id == "pss"
    assert law.primary_subject == "financial"
    assert law.subjects == ("financial",)
    assert law.href == "/laws/pss"
    assert law.primary_content == "full_act"
    assert law.key_provisions_ref is None
    assert "financial" in {s.id for s in catalog.visible_subjects}


def test_pss_is_a_current_act_and_pota_is_still_the_only_badged_one():
    from constitution_memorizer.web.law_catalog import load_catalog

    catalog = load_catalog()
    assert catalog.by_full_act("pss").is_current
    assert catalog.by_full_act("pss").status_label == ""
    assert {law.id for law in catalog.laws if law.status_label} == {"pota"}


def test_the_catalogue_entry_is_derived_from_the_act():
    from constitution_memorizer.web.law_catalog import load_catalog

    law = load_catalog().by_full_act("pss")
    act = get_bare_act("pss")
    assert law.scope_label == act.meta_label
    assert law.title == act.title


@pytest.mark.parametrize(
    "query", ["pss", "payment and settlement systems act", "payment systems"]
)
def test_pss_is_searchable(query: str):
    from constitution_memorizer.web.law_catalog import load_catalog

    assert query in load_catalog().by_full_act("pss").search_blob


def test_the_financial_chip_appears_on_the_catalogue(tmp_path: Path):
    client, _ = _client(tmp_path)
    html = client.get("/laws").text
    assert 'data-laws-chip="financial"' in html
    assert 'data-law-id="pss"' in html
    assert 'href="/laws/pss"' in html


def test_pss_is_free_to_read_and_records_nothing(tmp_path: Path):
    client, engine = _client(tmp_path)
    before = engine.stats()
    for path in (
        "/laws", "/laws/pss", "/laws/pss/section/1", "/laws/pss/section/10A",
        "/laws/pss/section/38",
    ):
        assert client.get(path).status_code == 200, path
    assert engine.stats() == before
    assert engine.due_today() == []


# ── Data invariants ───────────────────────────────────────────────────────


def test_runtime_is_the_canonical_minus_the_x_coordinate():
    archival = json.loads(ARCHIVAL.read_text(encoding="utf-8"))
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))

    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k != "source_x"}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    assert runtime == strip(archival)


def test_the_runtime_keeps_every_archival_block_the_reader_may_later_need():
    """Nothing is dropped beyond the debug coordinate.

    The footnotes in particular: no Act renders them today, so PSS ships no
    footnote adapter, but its 20 amendment notes must survive so the feature
    stays possible without a reparse.
    """
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    assert len(runtime["source_footnotes"]) == 20
    for key in (
        "source_front_matter", "source_supplementary_material",
        "long_title", "enacting_formula", "_validation",
    ):
        assert runtime[key], key
    for chapter in runtime["chapters"]:
        for section in chapter["sections"]:
            assert section["source_pages"]


def test_the_archival_canonical_retains_all_twenty_footnotes():
    archival = json.loads(ARCHIVAL.read_text(encoding="utf-8"))
    assert len(archival["source_footnotes"]) == 20
    assert all(n["text"] for n in archival["source_footnotes"])


def test_footnotes_are_preserved_but_not_loaded():
    """PSS states its notes as {page, number, text}; the loader keys on ids.

    Deliberate for this batch: no Act renders footnotes, so adapting them
    would add a code path with no user-visible effect.
    """
    assert get_bare_act("pss").footnotes == {}


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
    assert '"web/pss_runtime_v1.json"' in (REPO / "pyproject.toml").read_text(
        encoding="utf-8"
    )


def test_the_registry_entry_matches_the_shipped_artifact():
    spec = BARE_ACTS["pss"]
    assert spec.filename == RUNTIME.name
    assert spec.render_profile == "bns"
    assert spec.short_title == "PSS"
    assert spec.patch_filenames == ()
    assert spec.source_version == "1"


def test_the_sitemap_inventory_has_every_section_and_no_schedule():
    manifest = json.loads(
        (REPO / "src" / "constitution_memorizer" / "web" / "law_sitemap_manifest.json")
        .read_text(encoding="utf-8")
    )
    entry = manifest["laws"]["pss"]
    assert entry["sections"] == SECTION_IDS
    assert entry["schedules"] == []
    assert entry["runtime_identity"] == "pss:1:pss_runtime_v1.json"


def test_the_act_and_its_sections_are_in_the_served_sitemap(tmp_path: Path):
    client, _ = _client(tmp_path)
    assert "sitemap-laws-pss.xml" in client.get("/sitemap.xml").text
    xml = client.get("/sitemap-laws-pss.xml").text
    assert xml.count("<loc>") == 1 + len(SECTION_IDS)
    assert "/laws/pss</loc>" in xml
    assert "/laws/pss/section/34B</loc>" in xml
    assert "/schedule/" not in xml
