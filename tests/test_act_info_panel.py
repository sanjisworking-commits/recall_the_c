"""The "About this act" card and the Chapters/Schedules tabs.

Both are generic: one template serves all six Acts, and what a given Act
shows follows from what its own sources hold. The risk this file guards is
that the card becomes a third place where facts about an Act are typed —
so the tests pin where each row comes from, not just that it renders.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.act_info import build_act_info, format_act_date
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import BARE_ACTS, get_bare_act
from constitution_memorizer.web.laws_data import MAPPED_LAW_IDS
from constitution_memorizer.web.law_catalog import (
    ACT_INFO_FIELDS,
    CatalogError,
    load_catalog,
    parse_catalog,
)

REPO = Path(__file__).resolve().parents[1]
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
SEED = REPO / "data" / "reference" / "law_catalog.seed.json"


def _client(tmp_path: Path) -> TestClient:
    db = tmp_path / "progress.db"
    ReminderEngine.from_paths(db, MINI_UNITS)
    return TestClient(create_app(units_path=MINI_UNITS, db_path=db))


def _panel(slug: str):
    return build_act_info(get_bare_act(slug), load_catalog().by_full_act(slug))


def _rows(slug: str) -> dict[str, str]:
    return {row.key: row.value for row in _panel(slug).rows}


# ── Dates ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("16th September, 1985", "16-09-1985"),
        ("25th December, 2023", "25-12-2023"),
        ("1st January, 2000", "01-01-2000"),
        ("2nd March, 1999", "02-03-1999"),
        ("3rd April, 1999", "03-04-1999"),
        # India Code prints the day and month unpadded about half the time.
        ("1-7-2024", "01-07-2024"),
        ("01-07-2024", "01-07-2024"),
        ("", ""),
    ],
)
def test_dates_normalise_to_one_format(raw, expected):
    assert format_act_date(raw) == expected


def test_an_unrecognised_date_is_passed_through_not_dropped():
    # Losing a real fact is worse than an inconsistently formatted one.
    assert format_act_date("Chaitra 1, 1907 Saka") == "Chaitra 1, 1907 Saka"
    assert format_act_date("16th Smarch, 1985") == "16th Smarch, 1985"


# ── Where each row comes from ─────────────────────────────────────────────


def test_statutory_rows_are_read_off_the_act_not_the_catalogue():
    act = get_bare_act("ndps")
    panel = _panel("ndps")
    assert panel.meta == f"Act No. {act.act_number}"
    assert panel.long_title == act.long_title
    assert _rows("ndps")["Enacted"] == format_act_date(act.enactment_date)


def test_editorial_rows_are_read_off_the_catalogue_not_the_act():
    law = load_catalog().by_full_act("ndps")
    rows = _rows("ndps")
    assert rows["In force"] == format_act_date(law.act_info.in_force)
    assert rows["Ministry"] == law.act_info.ministry
    assert rows["Department"] == law.act_info.department
    assert rows["Jurisdiction"] == law.act_info.jurisdiction
    assert rows["Last modified"] == format_act_date(law.act_info.last_modified)


def test_no_editorial_field_is_also_present_in_any_canonical_document():
    # The two halves must not overlap: one fact, one owner. If a canonical
    # ever starts carrying a ministry, the card should read it from there.
    for slug in BARE_ACTS:
        document = get_bare_act(slug).raw.get("document") or {}
        assert not set(document) & set(ACT_INFO_FIELDS), slug


def test_the_section_row_is_the_acts_span_not_a_count():
    # NDPS holds 129 section records because 7A, 27A and 68A-68Z are
    # insertions. Printing "129" under a heading every register gives as 83
    # would be the card inventing a fact.
    act = get_bare_act("ndps")
    assert len(act.section_order) == 129
    assert _rows("ndps")["Sections"] == "1–83" == act.section_range


def test_rows_keep_the_designed_order():
    assert [row.key for row in _panel("ndps").rows] == [
        "Enacted",
        "In force",
        "Ministry",
        "Department",
        "Jurisdiction",
        "Sections",
        "Last modified",
    ]


# ── Acts we hold less about ───────────────────────────────────────────────


def test_a_row_we_do_not_hold_is_absent_rather_than_blank():
    # POTA's source prints no enactment date, and no editorial block has been
    # supplied for it. It gets the rows we can stand behind and no others.
    rows = _rows("pota")
    assert rows == {"Sections": "1–64"}
    assert _panel("pota").long_title.startswith("An Act to make provisions")
    assert all(row.value for row in _panel("pota").rows)


def test_every_act_gets_a_card_with_something_true_in_it():
    for slug in BARE_ACTS:
        panel = _panel(slug)
        assert panel.has_content, slug
        assert panel.meta, slug
        assert panel.long_title, slug


def test_pss_has_its_statutory_rows_without_an_editorial_block():
    assert load_catalog().by_full_act("pss").act_info is None
    assert _rows("pss") == {"Enacted": "20-12-2007", "Sections": "1–38"}


# ── The catalogue seed ────────────────────────────────────────────────────


def _seed_with(act_info) -> dict:
    data = json.loads(SEED.read_text())
    for law in data["laws"]:
        if law["id"] == "pss":
            law["act_info"] = act_info
    return data


def _parse(data):
    return parse_catalog(
        data, bare_act_ids=BARE_ACTS, mapped_law_ids=MAPPED_LAW_IDS
    )


def test_a_misspelt_act_info_field_is_an_error_not_a_missing_row():
    # A typo and an absent field look identical on screen, so the seed has to
    # be the thing that complains.
    with pytest.raises(CatalogError, match="unknown act_info field"):
        _parse(_seed_with({"ministry_name": "Ministry of Finance"}))


def test_an_empty_act_info_block_is_an_error():
    with pytest.raises(CatalogError, match="act_info is present but empty"):
        _parse(_seed_with({"ministry": "  "}))


def test_act_info_must_be_an_object():
    with pytest.raises(CatalogError, match="act_info must be an object"):
        _parse(_seed_with(["Ministry of Finance"]))


def test_the_shipped_seed_still_parses():
    assert load_catalog().by_full_act("bnss").act_info.jurisdiction == "Central"


# ── The page ──────────────────────────────────────────────────────────────


def test_the_card_ships_collapsed_and_the_tab_row_ships_hidden(tmp_path):
    # Without JS the page is what it was before either existed: chapters,
    # then schedules, and no tab row pretending to be a control.
    html = _client(tmp_path).get("/laws/ndps").text
    assert 'aria-expanded="false"' in html
    assert 'data-bareact-info hidden' in html
    assert 'data-bareact-tabs hidden' in html
    assert html.count('data-bareact-panel="') == 2
    # Neither panel is hidden in the markup, so both are readable and the
    # schedule link is still in the document for a crawler.
    assert 'data-bareact-panel="schedules"\n  >' in html


def test_the_card_renders_its_rows_on_the_page(tmp_path):
    html = _client(tmp_path).get("/laws/ndps").text
    assert "About this act" in html
    assert "<dt>Ministry</dt>" in html
    assert "Department of Revenue" in html
    assert "ACT NO." not in html  # uppercased by CSS, not typed into markup
    assert "Act No. 61 OF 1985" in html


def test_the_schedule_row_moved_into_the_schedules_panel(tmp_path):
    html = _client(tmp_path).get("/laws/ndps").text
    panel = html.split('data-bareact-panel="schedules"', 1)[1]
    assert "/laws/ndps/schedule/" in panel
    # and is no longer in the chapters panel
    chapters = html.split('data-bareact-panel="chapters"', 1)[1].split(
        'data-bareact-panel="schedules"', 1
    )[0]
    assert "/laws/ndps/schedule/" not in chapters


def test_an_act_with_no_schedules_says_so(tmp_path):
    client = _client(tmp_path)
    assert "This Act has no Schedules." in client.get("/laws/bns").text
    assert "This Act has no Schedules." in client.get("/laws/pss").text
    assert "This Act has no Schedules." not in client.get("/laws/uapa").text


def test_uapa_shows_all_four_schedules_and_bnss_only_the_navigable_one(tmp_path):
    client = _client(tmp_path)
    assert client.get("/laws/uapa").text.count("/laws/uapa/schedule/") == 4
    # BNSS's Second Schedule is 58 positioned-text forms: preserved in the
    # data, still unrenderable, so still not linked.
    assert client.get("/laws/bnss").text.count("/laws/bnss/schedule/") == 1


def test_the_long_title_is_printed_verbatim_brackets_and_all(tmp_path):
    html = _client(tmp_path).get("/laws/uapa").text
    assert "[, and for dealing with terrorist activities,]" in html


def test_the_long_title_joins_the_act_wide_bracket_stream():
    # Rendering a bracket the validator never examines is exactly how the
    # lone "]" on the section header got through the first time.
    act = get_bare_act("uapa")
    assert ("[", "long title") in act.bracket_stream()
    assert ("]", "long title") in act.bracket_stream()
    assert act.unbalanced_brackets() == ()


def test_no_act_gains_a_bracket_orphan_from_its_long_title():
    orphans = {slug: get_bare_act(slug).unbalanced_brackets() for slug in BARE_ACTS}
    # NDPS's one orphan is entry 105E's chemical name "[4,3,-a) (1,4}", a
    # typo in the source register, pinned as a known exception.
    assert {s: len(o) for s, o in orphans.items()} == {
        "ndps": 1, "bns": 0, "bnss": 0, "pota": 0, "uapa": 0, "pss": 0
    }


def test_reading_an_act_page_still_records_nothing(tmp_path):
    client = _client(tmp_path)
    before = client.get("/progress").text
    client.get("/laws/ndps")
    assert client.get("/progress").text == before
