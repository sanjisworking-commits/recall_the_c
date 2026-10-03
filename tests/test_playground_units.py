"""R2 — clause locators, units authority, picker POST, selection rules."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from constitution_memorizer.playground.locators import (
    LocatorError,
    SectionLocator,
    UnitLocator,
    parse_locator,
    section_locator,
    unit_locator,
)
from constitution_memorizer.playground.learning.modes import PLAYGROUND_LEARN_MODES
from constitution_memorizer.playground.service import (
    SelectionRejected,
    normalize_selection_locators,
    require_playground_law,
    selection_rows,
)
from constitution_memorizer.playground.source import locators_for_act, source_hash
from constitution_memorizer.playground.units import (
    UnitIdentity,
    citation_label,
    enumerate_selectable_units,
    section_unit_map,
    unit_hash,
    unit_hash_for_locator,
)
from constitution_memorizer.playground.urls import learn_path, learn_path_for_locator, sections_path
from constitution_memorizer.playground.view import picker_cta_copy, picker_status_line, provisions_label
from constitution_memorizer.playground.roster.period import playground_today
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID
from constitution_memorizer.web.bare_acts import ActSection, clear_bare_act_cache, get_bare_act
from tests.test_playground import (
    _add_and_select,
    _add_law,
    _client,
    _hydrate_spy,
    _sqlite_repo,
)
from tests.test_playground_m8 import _seed_progress

TODAY = date(2026, 9, 29)


def _ndps_section(number: str):
    act = get_bare_act("ndps")
    assert act is not None
    section = act.section(number)
    assert section is not None
    return act, section


def _selection_snapshot(repo, law_id: str):
    return tuple(
        (row.source_locator, row.source_version, row.source_hash, row.selected_at)
        for row in repo.list_selection(LOCAL_USER_ID, law_id)
    )


def _item_snapshot(repo, law_id: str):
    return repo.get_item(LOCAL_USER_ID, law_id)


def _assert_picker_rejected(client, *, law_id: str, data: dict) -> None:
    repo = client.app.state.playground
    before_selection = _selection_snapshot(repo, law_id)
    before_item = _item_snapshot(repo, law_id)
    rejected = client.post(
        sections_path(law_id),
        data=data,
        follow_redirects=False,
    )
    assert rejected.status_code == 400
    assert rejected.json() == {"detail": "invalid_selection"}
    assert _selection_snapshot(repo, law_id) == before_selection
    assert _item_snapshot(repo, law_id) == before_item


def _pss_38():
    act = get_bare_act("pss")
    assert act is not None
    section = act.section("38")
    assert section is not None
    return act, section


def test_section_locator_roundtrip():
    loc = section_locator("bns", "103")
    parsed = parse_locator(loc.value)
    assert isinstance(parsed, SectionLocator)
    assert parsed.law_id == "bns"
    assert parsed.section_number == "103"
    assert parsed.value == "bns:section:103"
    assert not hasattr(parsed, "kind")


def test_unit_locator_roundtrip_and_ordinal_default():
    loc = parse_locator("ndps:section:8:clause:a")
    assert isinstance(loc, UnitLocator)
    assert loc.section_number == "8"
    assert loc.kind == "clause"
    assert loc.label == "a"
    assert loc.ordinal == 1
    assert loc.value == "ndps:section:8:clause:a"
    assert loc.display_label == "(a)"
    assert "~" not in loc.display_label
    again = unit_locator("ndps", "8", "clause", "a")
    assert again == loc
    assert parse_locator(again.value) == again


def test_duplicate_ordinal_serialization():
    loc = parse_locator("pss:section:38:subsection:2~2")
    assert isinstance(loc, UnitLocator)
    assert loc.label == "2"
    assert loc.ordinal == 2
    assert loc.value == "pss:section:38:subsection:2~2"
    assert loc.display_label == "(2)"
    assert "2~2" not in loc.display_label
    first = parse_locator("pss:section:38:subsection:2")
    assert first.ordinal == 1
    assert first.value == "pss:section:38:subsection:2"
    assert first != loc


def test_malformed_locator_rejection():
    bad = (
        "ndps:section:8:clause:a:extra",
        "ndps:section:8:paragraph:1",
        "ndps:section:8:clause:",
        "ndps:section:8:clause:a~0",
        "ndps:section:8:clause:a~",
        "ndps:section:8:",
        "ndps:chapter:1",
        "NDPS:section:8:clause:a",
        "ndps:section:8:foo:a",
    )
    for raw in bad:
        with pytest.raises(LocatorError):
            parse_locator(raw)
    # Must not coerce a unit-shaped string into a section locator.
    with pytest.raises(LocatorError):
        parse_locator("ndps:section:8:clause")
    section = parse_locator("ndps:section:8")
    assert isinstance(section, SectionLocator)
    assert section.section_number == "8"


def test_pss_section_38_duplicate_printed_two():
    _act, section = _pss_38()
    units = enumerate_selectable_units(section, law_id="pss")
    twos = [u for u in units if u.label == "2" and u.kind == "subsection"]
    assert len(twos) == 2
    assert twos[0].ordinal == 1
    assert twos[1].ordinal == 2
    assert twos[0].locator.value == "pss:section:38:subsection:2"
    assert twos[1].locator.value == "pss:section:38:subsection:2~2"
    assert twos[0].display_label == twos[1].display_label == "(2)"
    assert "~" not in twos[0].display_label
    assert citation_label(twos[1].locator) == "Section 38(2)"


def test_lead_in_tail_and_descendant_inclusion():
    _act, section = _ndps_section("8")
    mapped = section_unit_map(section)
    units = enumerate_selectable_units(section, law_id="ndps")
    assert [u.display_label for u in units] == ["(a)", "(b)", "(c)"]
    assert mapped.lead_in.startswith("No person shall")
    assert "decorative purposes" in mapped.tail
    last = units[-1]
    assert "cultivate any coca plant" not in last.canonical_text
    assert "produce, manufacture, possess" in last.canonical_text
    assert "decorative purposes" not in last.canonical_text
    assert "Provided further" not in last.canonical_text
    assert last.lead_in == mapped.lead_in
    _act9, s9 = _ndps_section("9")
    units9 = enumerate_selectable_units(s9, law_id="ndps")
    assert [u.display_label for u in units9[:2]] == ["(1)", "(2)"]
    first = units9[0]
    assert "permit and regulate" in first.canonical_text
    assert "(i)" not in first.display_label


def test_section_with_fewer_than_two_units_stays_section_only():
    act = get_bare_act("mtp")
    assert act is not None
    section = act.section("8")
    assert section is not None
    units = enumerate_selectable_units(section, law_id="mtp")
    assert units == ()
    mapped = section_unit_map(section)
    assert mapped.section_only is True
    ndps = get_bare_act("ndps")
    assert ndps is not None
    s11 = ndps.section("11")
    assert s11 is not None
    assert enumerate_selectable_units(s11, law_id="ndps") == ()


def test_whole_section_unit_exclusivity_and_all_unit_promotion():
    act = require_playground_law("ndps")
    a = "ndps:section:8:clause:a"
    b = "ndps:section:8:clause:b"
    c = "ndps:section:8:clause:c"
    mixed = normalize_selection_locators(
        "ndps", ["8"], entire=False, units=[a], act=act
    )
    assert any(isinstance(item, SectionLocator) and item.section_number == "8" for item in mixed)
    assert not any(isinstance(item, UnitLocator) and item.section_number == "8" for item in mixed)
    promoted = normalize_selection_locators(
        "ndps", [], entire=False, units=[a, b, c], act=act
    )
    assert [item.value for item in promoted] == ["ndps:section:8"]
    partial = normalize_selection_locators(
        "ndps", [], entire=False, units=[a, b], act=act
    )
    assert {item.value for item in partial} == {a, b}


def test_all_unit_learning_is_not_whole_section_mastery(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    units = ["ndps:section:8:clause:a", "ndps:section:8:clause:b", "ndps:section:8:clause:c"]
    for loc in units:
        _seed_progress(
            repo,
            LOCAL_USER_ID,
            "ndps",
            loc,
            status="learned",
            interval_days=1,
            next_revision=(TODAY + timedelta(days=1)).isoformat(),
            times_completed=6,
            learned_at=TODAY.isoformat(),
        )
    rows = selection_rows("ndps", [], entire=False, units=units)
    assert [row[0] for row in rows] == ["ndps:section:8"]
    repo.replace_selection(LOCAL_USER_ID, "ndps", rows)
    section_progress = repo.get_progress(LOCAL_USER_ID, "ndps", "ndps:section:8")
    assert section_progress is None or section_progress.status != "learned"
    for loc in units:
        row = repo.get_progress(LOCAL_USER_ID, "ndps", loc)
        assert row is not None
        assert row.status == "learned"


def test_switch_preserves_dormant_progress_and_due_excludes_deselected(tmp_path: Path):
    repo = _sqlite_repo(tmp_path)
    repo.add_item(LOCAL_USER_ID, "ndps", source_version="v", law_source_hash="t")
    section = "ndps:section:8"
    unit = "ndps:section:8:clause:a"
    repo.replace_selection(LOCAL_USER_ID, "ndps", [(section, "v", "h")])
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "ndps",
        section,
        status="review",
        interval_days=3,
        next_revision=TODAY.isoformat(),
        times_completed=2,
    )
    due = repo.list_due_revisions(LOCAL_USER_ID, TODAY, ["ndps"])
    assert [row.source_locator for row in due] == [section]
    repo.replace_selection(LOCAL_USER_ID, "ndps", [(unit, "v", "u")])
    dormant = repo.get_progress(LOCAL_USER_ID, "ndps", section)
    assert dormant is not None
    assert dormant.status == "review"
    due = repo.list_due_revisions(LOCAL_USER_ID, TODAY, ["ndps"])
    assert due == []
    repo.replace_selection(LOCAL_USER_ID, "ndps", [(section, "v", "h")])
    resumed = repo.get_progress(LOCAL_USER_ID, "ndps", section)
    assert resumed is not None
    assert resumed.status == "review"
    assert resumed.times_completed == 2
    due = repo.list_due_revisions(LOCAL_USER_ID, TODAY, ["ndps"])
    assert [row.source_locator for row in due] == [section]


def test_unit_hash_deterministic_and_ignores_presentation():
    _act, section = _ndps_section("8")
    units = enumerate_selectable_units(section, law_id="ndps")
    clause_a = units[0]
    digest = unit_hash(clause_a)
    assert digest == unit_hash(clause_a)
    assert len(digest) == 64
    other = units[1]
    assert unit_hash(other) != digest
    annotated = dict(section.body[1])
    annotated["annotations"] = [{"type": "footnote", "marker": "9", "note_id": "x"}]
    mutated_body = [section.body[0], annotated, *section.body[2:]]
    from dataclasses import replace

    presented = replace(section, body=tuple(mutated_body))
    presented_units = enumerate_selectable_units(presented, law_id="ndps")
    assert unit_hash(presented_units[0]) == digest
    changed_body = list(section.body)
    changed = dict(changed_body[1])
    changed["text"] = str(changed.get("text") or "") + " amended"
    changed_body[1] = changed
    statutory = replace(section, body=tuple(changed_body))
    changed_units = enumerate_selectable_units(statutory, law_id="ndps")
    assert unit_hash(changed_units[0]) != digest
    loc = unit_locator("ndps", "8", "clause", "a")
    assert unit_hash_for_locator(loc, section) == digest


def test_provisions_copy_and_cta_grammar():
    assert provisions_label(1) == "1 provision"
    assert provisions_label(2) == "2 provisions"
    assert picker_cta_copy(section_count=0, partial_unit_count=0) == "Select sections to add"
    assert picker_cta_copy(section_count=1, partial_unit_count=0) == "Add 1 section →"
    assert picker_cta_copy(section_count=2, partial_unit_count=0) == "Add 2 sections →"
    assert (
        picker_cta_copy(section_count=1, partial_unit_count=1)
        == "Add 1 section (1 clause partial) →"
    )
    assert (
        picker_cta_copy(section_count=1, partial_unit_count=2)
        == "Add 1 section (2 clauses partial) →"
    )
    assert picker_status_line("not_started") == "Not started"
    assert picker_status_line("learning", completed=4) == "Learning · 4 of 6 modes"
    assert picker_status_line("due", interval=3) == "Due · Day 3"
    assert picker_status_line("mastered") == "Mastered"
    assert (
        picker_status_line(
            "learned",
            next_revision=(TODAY + timedelta(days=1)).isoformat(),
            as_of=TODAY,
        )
        == "Learned · first revision tomorrow"
    )


def test_learn_path_for_locator_parallel_routes():
    section = section_locator("ndps", "8")
    assert learn_path_for_locator(section, "read") == learn_path("ndps", "8", "read")
    unit = parse_locator("ndps:section:8:clause:a")
    path = learn_path_for_locator(unit, "read")
    assert path == "/playground/laws/ndps/sections/8/u/clause:a/learn/read"
    dup = parse_locator("pss:section:38:subsection:2~2")
    assert "~2" in learn_path_for_locator(dup, "cloze")


def test_nojs_section_and_unit_post_and_omitted_rejection(tmp_path: Path):
    client = _client(tmp_path)
    _add_law(client, "ndps")
    saved = client.post(
        sections_path("ndps"),
        data={"section": "8"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    repo = client.app.state.playground
    selected = {row.source_locator for row in repo.list_selection(LOCAL_USER_ID, "ndps")}
    assert selected == {"ndps:section:8"}
    units = client.post(
        sections_path("ndps"),
        data={
            "unit": [
                "ndps:section:8:clause:a",
                "ndps:section:8:clause:b",
            ]
        },
        follow_redirects=False,
    )
    assert units.status_code == 303
    selected = {row.source_locator for row in repo.list_selection(LOCAL_USER_ID, "ndps")}
    assert selected == {"ndps:section:8:clause:a", "ndps:section:8:clause:b"}
    _assert_picker_rejected(
        client,
        law_id="ndps",
        data={"section": "65", "unit": "ndps:section:8:not-a-unit:1"},
    )
    selected = {row.source_locator for row in repo.list_selection(LOCAL_USER_ID, "ndps")}
    assert selected == {"ndps:section:8:clause:a", "ndps:section:8:clause:b"}


def test_picker_markup_tri_state_chapterless_and_copy(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "8")
    page = client.get(sections_path("ndps"))
    html = page.text
    assert page.status_code == 200
    assert "Choose what to learn" in html
    assert "Whole sections, or open one and pick clauses." in html
    assert "Save selection" not in html
    assert "Entire Act or individual sections" not in html
    assert "Add 1 section" in html
    assert "SECTION 8" in html
    assert "CHAPTER" in html
    assert 'name="section"' in html
    assert 'name="unit"' in html
    assert "ndps:section:8:clause:a" in html
    assert "aria-checked=" in html
    assert "Show clauses" in html
    assert "pg-sticky-cta" in html
    assert "pg-pick-aside" in html
    assert "data-chapterless" not in html
    client.post(
        sections_path("ndps"),
        data={
            "unit": [
                "ndps:section:8:clause:a",
                "ndps:section:8:clause:b",
            ]
        },
        follow_redirects=False,
    )
    mixed = client.get(sections_path("ndps"))
    assert 'aria-checked="mixed"' in mixed.text
    assert "1 provision" not in mixed.text or "2 provisions" in mixed.text
    assert "clauses partial" in mixed.text
    mtp = _client(tmp_path)
    _add_and_select(mtp, "mtp", "1")
    mtp_page = mtp.get(sections_path("mtp"))
    assert "data-chapterless" in mtp_page.text
    assert "Chapter" not in mtp_page.text
    assert "CHAPTER" not in mtp_page.text


def test_picker_status_line_uses_real_progress_including_dormant(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "8")
    repo = client.app.state.playground
    as_of = playground_today()
    digest = source_hash(_ndps_section("8")[1])
    for mode in PLAYGROUND_LEARN_MODES[:4]:
        repo.complete_mode(
            LOCAL_USER_ID,
            "ndps",
            "ndps:section:8",
            mode,
            source_version="v",
            source_hash=digest,
            as_of=as_of,
        )
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "ndps",
        "ndps:section:1",
        status="mastered",
        interval_days=60,
        next_revision=None,
        times_completed=6,
        learned_at="2026-01-01",
        last_completed="2026-09-01",
    )
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "ndps",
        "ndps:section:2",
        status="review",
        interval_days=3,
        next_revision=(as_of - timedelta(days=1)).isoformat(),
        times_completed=1,
        learned_at="2026-09-01",
        last_completed="2026-09-17",
    )
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "ndps",
        "ndps:section:4",
        status="learned",
        interval_days=1,
        next_revision=(as_of + timedelta(days=1)).isoformat(),
        learned_at=as_of.isoformat(),
    )
    learning = client.get(sections_path("ndps"))
    html = learning.text
    assert "Learning · 4 of 6 modes" in html
    assert "Mastered" in html
    assert "Due · Day 3" in html
    assert "Learned · first revision tomorrow" in html
    assert "Not started" in html
    switched = client.post(
        sections_path("ndps"),
        data={"section": "9"},
        follow_redirects=False,
    )
    assert switched.status_code == 303
    dormant = client.get(sections_path("ndps"))
    assert "Learning · 4 of 6 modes" in dormant.text
    assert "Mastered" in dormant.text


def test_unit_learn_route_resolves(tmp_path: Path):
    client = _client(tmp_path)
    _add_law(client, "ndps")
    client.post(
        sections_path("ndps"),
        data={"unit": "ndps:section:8:clause:a"},
        follow_redirects=False,
    )
    path = learn_path_for_locator(parse_locator("ndps:section:8:clause:a"), "read")
    page = client.get(path)
    assert page.status_code == 200
    assert "cultivate any coca plant" in page.text
    assert "decorative purposes" not in page.text
    existing = client.get(learn_path("ndps", "8", "read"), follow_redirects=False)
    assert existing.status_code in {303, 200}


def test_requested_law_only_hydration_on_picker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    clear_bare_act_cache()
    hydrated = _hydrate_spy(monkeypatch)
    client = _client(tmp_path)
    _add_law(client, "ndps")
    hydrated.clear()
    clear_bare_act_cache()
    page = client.get(sections_path("ndps"))
    assert page.status_code == 200
    assert hydrated.count("ndps") >= 1
    assert "bns" not in hydrated
    assert "bnss" not in hydrated
    assert "pss" not in hydrated
    assert "mtp" not in hydrated
    hydrated.clear()
    clear_bare_act_cache()
    client.post(
        sections_path("ndps"),
        data={"unit": "ndps:section:8:clause:a"},
        follow_redirects=False,
    )
    assert "ndps" in hydrated
    assert "bns" not in hydrated


def test_unit_locator_cannot_exist_unbound():
    with pytest.raises(LocatorError):
        UnitLocator(law_id="", section_number="8", kind="clause", label="a")
    with pytest.raises(LocatorError):
        unit_locator("", "8", "clause", "a")
    _act, section = _ndps_section("8")
    mapped = section_unit_map(section)
    assert mapped.units
    for unit in mapped.units:
        assert isinstance(unit.identity, UnitIdentity)
        assert not hasattr(unit, "locator")
        assert not hasattr(unit.identity, "value")
        assert unit.identity.section_number == "8"
    bound = enumerate_selectable_units(section, law_id="ndps")
    assert bound
    for unit in bound:
        assert unit.locator.law_id == "ndps"
        assert parse_locator(unit.locator.value) == unit.locator


def test_normalize_entire_validates_extras_then_ignores_valid_ones():
    act = require_playground_law("ndps")
    entire = locators_for_act("ndps", act=act)
    with pytest.raises(SelectionRejected):
        normalize_selection_locators(
            "ndps",
            ["65"],
            entire=True,
            units=["ndps:section:8:clause:a"],
            act=act,
        )
    with pytest.raises(SelectionRejected):
        normalize_selection_locators(
            "ndps",
            ["8"],
            entire=True,
            units=["ndps:section:8:not-a-unit:1"],
            act=act,
        )
    accepted = normalize_selection_locators(
        "ndps",
        ["8"],
        entire=True,
        units=["ndps:section:8:clause:a"],
        act=act,
    )
    assert [item.value for item in accepted] == [item.value for item in entire]
    assert not any(isinstance(item, UnitLocator) for item in accepted)


def test_unlearnable_non_omitted_rejected_with_synthetic_section():
    act = require_playground_law("ndps")
    synthetic = ActSection(
        number="99Z",
        title="Synthetic empty body",
        status="active",
        former_title=None,
        omission_note=None,
        chapter_number="",
        chapter_title="",
        body=(),
        profile="ndps",
    )
    fake = replace(act, section_order=act.section_order + (synthetic,))
    assert fake.section("99Z") is not None
    assert act.section("99Z") is None
    with pytest.raises(SelectionRejected):
        normalize_selection_locators("ndps", ["99Z"], entire=False, act=fake)


def test_picker_post_rejects_invalid_payloads_without_mutation(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "8")
    payloads = (
        {"unit": "ndps:section:8:not-a-unit:1"},
        {"unit": "bns:section:103:clause:a"},
        {"section": "99999"},
        {"section": "65"},
        {"unit": "ndps:section:8:clause:zzz"},
        {"unit": "ndps:section:8:clause:a~9"},
        {"unit": "pss:section:38:subsection:2~9"},
        {"section": " 8 "},
        {"unit": " ndps:section:8:clause:a "},
        {"unit": "ndps:section:8:clause:a~1"},
    )
    for data in payloads:
        _assert_picker_rejected(client, law_id="ndps", data=data)


def test_picker_post_valid_plus_invalid_applies_neither(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "9")
    _assert_picker_rejected(
        client,
        law_id="ndps",
        data={
            "unit": [
                "ndps:section:8:clause:a",
                "ndps:section:8:not-a-unit:1",
            ]
        },
    )
    selected = {
        row.source_locator
        for row in client.app.state.playground.list_selection(LOCAL_USER_ID, "ndps")
    }
    assert selected == {"ndps:section:9"}
    assert "ndps:section:8:clause:a" not in selected


def test_picker_post_entire_act_valid_and_invalid_extras(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "8")
    _assert_picker_rejected(
        client,
        law_id="ndps",
        data={"entire": "1", "section": "65"},
    )
    selected = {
        row.source_locator
        for row in client.app.state.playground.list_selection(LOCAL_USER_ID, "ndps")
    }
    assert selected == {"ndps:section:8"}
    saved = client.post(
        sections_path("ndps"),
        data={
            "entire": "1",
            "section": "8",
            "unit": "ndps:section:8:clause:a",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    expected = {item.value for item in locators_for_act("ndps")}
    got = {
        row.source_locator
        for row in client.app.state.playground.list_selection(LOCAL_USER_ID, "ndps")
    }
    assert got == expected
    assert "ndps:section:8:clause:a" not in got


def test_picker_post_whitespace_absent_and_empty_clears(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "9")
    mixed = client.post(
        sections_path("ndps"),
        data={"section": ["8", "   ", "\t"], "unit": ["", "  "]},
        follow_redirects=False,
    )
    assert mixed.status_code == 303
    selected = {
        row.source_locator
        for row in client.app.state.playground.list_selection(LOCAL_USER_ID, "ndps")
    }
    assert selected == {"ndps:section:8"}
    cleared = client.post(
        sections_path("ndps"),
        data={},
        follow_redirects=False,
    )
    assert cleared.status_code == 303
    assert client.app.state.playground.list_selection(LOCAL_USER_ID, "ndps") == []
    client.post(
        sections_path("ndps"),
        data={"section": "9"},
        follow_redirects=False,
    )
    whitespace_only = client.post(
        sections_path("ndps"),
        data={"section": "   ", "unit": "\n"},
        follow_redirects=False,
    )
    assert whitespace_only.status_code == 303
    assert client.app.state.playground.list_selection(LOCAL_USER_ID, "ndps") == []
