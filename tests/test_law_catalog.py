"""Static /laws catalogue: metadata only, full HTML, no content loaders."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.law_catalog import (
    CatalogError,
    load_catalog,
    normalize_search,
    parse_catalog,
)
from constitution_memorizer.web.laws_data import MAPPED_LAW_IDS, load_laws

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
PRODUCTION_LAW_IDS = (
    "ndps",
    "uapa-1967",
    "citizenship-1955",
    "pcr-1955",
    "rte-2009",
    "rpa-1951",
    "rti-2005",
    "epa-1986",
)

SUBJECTS = [
    {"id": "criminal", "label": "Criminal", "display_order": 10},
    {"id": "constitutional", "label": "Constitutional", "display_order": 20},
    {"id": "unused", "label": "Unused", "display_order": 99},
]


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    )


def _law(**overrides: object) -> dict:
    row: dict = {
        "id": "ndps",
        "title": "The Narcotic Drugs and Psychotropic Substances Act, 1985",
        "short_title": "NDPS Act",
        "year": 1985,
        "aliases": ["NDPS"],
        "subjects": ["criminal"],
        "primary_subject": "criminal",
        "display_order": 10,
        "scope_label": "8 Chapters · Sections 1–83",
        "primary_content": "full_act",
        "content": {"full_act": {"ref": "ndps"}, "key_provisions": None},
    }
    row.update(overrides)
    return row


def test_normalize_search_keeps_punctuation():
    assert normalize_search("  RTI,  2005  ") == "rti, 2005"
    assert normalize_search("NDPS", 1985, ["Narcotics"]) == "ndps 1985 narcotics"


def test_production_catalogue_loads_without_bns():
    catalog = load_catalog()
    ids = [law.id for law in catalog.laws]
    assert ids == list(PRODUCTION_LAW_IDS)
    assert "bns" not in ids
    ndps = catalog.laws[0]
    assert ndps.tag_line == "CRIMINAL · FULL ACT"
    assert ndps.href == "/laws/ndps"
    rti = next(law for law in catalog.laws if law.id == "rti-2005")
    assert rti.tag_line == "ADMINISTRATIVE · KEY PROVISIONS"
    assert rti.href == "/laws/rti-2005"
    assert {s.id for s in catalog.visible_subjects} == {
        "criminal",
        "constitutional",
        "administrative",
        "environmental",
    }


def test_mapped_law_ids_match_laws_seed():
    assert MAPPED_LAW_IDS == {act.id for act in load_laws()}


def test_sort_is_independent_of_json_order():
    catalog = parse_catalog(
        {
            "subjects": SUBJECTS[:2],
            "laws": [
                _law(
                    id="later",
                    display_order=20,
                    content={"full_act": {"ref": "ndps"}, "key_provisions": None},
                ),
                _law(id="earlier", display_order=10),
            ],
        },
        bare_act_ids={"ndps"},
        mapped_law_ids=set(),
    )
    assert [law.id for law in catalog.laws] == ["earlier", "later"]


def test_primary_subject_must_belong_to_subjects():
    with pytest.raises(CatalogError, match="primary_subject"):
        parse_catalog(
            {
                "subjects": SUBJECTS[:2],
                "laws": [_law(primary_subject="constitutional")],
            },
            bare_act_ids={"ndps"},
            mapped_law_ids=set(),
        )


def test_refs_checked_against_override_registries_only():
    with pytest.raises(CatalogError, match="BARE_ACTS"):
        parse_catalog(
            {"subjects": SUBJECTS[:1], "laws": [_law()]},
            bare_act_ids=set(),
            mapped_law_ids=set(),
        )
    with pytest.raises(CatalogError, match="MAPPED_LAW_IDS"):
        parse_catalog(
            {
                "subjects": SUBJECTS[:1],
                "laws": [
                    _law(
                        primary_content="key_provisions",
                        content={
                            "full_act": None,
                            "key_provisions": {"ref": "missing-mapped"},
                        },
                    )
                ],
            },
            bare_act_ids=set(),
            mapped_law_ids={"rti-2005"},
        )


def test_dual_capability_fixture_routes_via_primary_content():
    raw = {
        "subjects": SUBJECTS[:2],
        "laws": [
            {
                "id": "bns",
                "title": "The Bharatiya Nyaya Sanhita, 2023",
                "short_title": "BNS",
                "year": 2023,
                "aliases": ["Bharatiya Nyaya Sanhita"],
                "subjects": ["criminal", "constitutional"],
                "primary_subject": "criminal",
                "display_order": 1,
                "scope_label": "20 Chapters · Sections 1–358",
                "primary_content": "full_act",
                "content": {
                    "full_act": {"ref": "bns"},
                    "key_provisions": {"ref": "bns-mapped"},
                },
            }
        ],
    }
    catalog = parse_catalog(
        raw, bare_act_ids={"bns"}, mapped_law_ids={"bns-mapped"}
    )
    law = catalog.laws[0]
    assert law.href == "/laws/bns"
    assert law.tag_line == "CRIMINAL · FULL ACT"
    assert "constitutional" in law.subjects
    keyed = parse_catalog(
        {
            **raw,
            "laws": [{**raw["laws"][0], "primary_content": "key_provisions"}],
        },
        bare_act_ids={"bns"},
        mapped_law_ids={"bns-mapped"},
    )
    assert keyed.laws[0].href == "/laws/bns-mapped"
    assert keyed.laws[0].tag_line == "CRIMINAL · KEY PROVISIONS"


def test_unused_subjects_are_not_visible():
    catalog = parse_catalog(
        {"subjects": SUBJECTS, "laws": [_law()]},
        bare_act_ids={"ndps"},
        mapped_law_ids=set(),
    )
    assert [s.id for s in catalog.visible_subjects] == ["criminal"]


def test_empty_scope_and_missing_capability_fail():
    with pytest.raises(CatalogError, match="scope_label"):
        parse_catalog(
            {"subjects": SUBJECTS[:1], "laws": [_law(scope_label="")]},
            bare_act_ids={"ndps"},
            mapped_law_ids=set(),
        )
    with pytest.raises(CatalogError, match="capability"):
        parse_catalog(
            {
                "subjects": SUBJECTS[:1],
                "laws": [
                    _law(
                        primary_content="full_act",
                        content={"full_act": None, "key_provisions": None},
                    )
                ],
            },
            bare_act_ids={"ndps"},
            mapped_law_ids=set(),
        )


def test_get_laws_does_not_call_content_loaders(tmp_path: Path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("content loader must not run on GET /laws")

    monkeypatch.setattr(
        "constitution_memorizer.web.bare_acts.list_bare_acts", boom
    )
    monkeypatch.setattr(
        "constitution_memorizer.web.bare_acts.get_bare_act", boom
    )
    monkeypatch.setattr("constitution_memorizer.web.laws_data.get_law", boom)
    monkeypatch.setattr("constitution_memorizer.web.laws_data.load_laws", boom)
    import constitution_memorizer.web.app as webapp

    for name in ("list_bare_acts", "get_bare_act", "get_law", "load_laws"):
        if hasattr(webapp, name):
            monkeypatch.setattr(webapp, name, boom)

    response = _client(tmp_path).get("/laws")
    assert response.status_code == 200


def test_index_html_always_contains_every_production_law(tmp_path: Path):
    client = _client(tmp_path)
    html = client.get("/laws?q=ndps&subject=criminal").text
    assert "data-laws-index" in html
    assert 'data-initial-q="ndps"' in html
    assert 'data-initial-subject="criminal"' in html
    for law_id in PRODUCTION_LAW_IDS:
        assert f'data-law-id="{law_id}"' in html
        href_id = "ndps" if law_id == "ndps" else law_id
        assert f'href="/laws/{href_id}"' in html
    assert "Not started" not in html
    assert "Coming soon" not in html
    assert "law-practice-note" not in html
    assert "Bare Acts" not in html
    assert "Mapped to Articles" not in html
    assert "No laws found" in html
    assert 'href="/laws/bns"' not in html


def test_unknown_subject_initialises_as_all(tmp_path: Path):
    html = _client(tmp_path).get("/laws?subject=no-such").text
    assert 'data-initial-subject="no-such"' in html
    assert 'data-laws-chip="" aria-pressed="true"' in html
    assert 'data-laws-chip="criminal" aria-pressed="false"' in html
    for law_id in PRODUCTION_LAW_IDS:
        assert f'data-law-id="{law_id}"' in html


def test_search_blobs_cover_production_examples(tmp_path: Path):
    html = _client(tmp_path).get("/laws").text
    rti = html.split('data-law-id="rti-2005"', 1)[1].split("</a>", 1)[0]
    assert "rti" in rti
    ndps = html.split('data-law-id="ndps"', 1)[1].split("</a>", 1)[0]
    assert "1985" in ndps
    assert "narcotics" in ndps
    assert 'data-subjects="criminal"' in ndps
    assert "CRIMINAL · FULL ACT" in ndps
    catalog = load_catalog()
    rti_law = next(law for law in catalog.laws if law.id == "rti-2005")
    assert "rti" in rti_law.search_blob
    ndps_law = catalog.laws[0]
    assert "1985" in ndps_law.search_blob
    assert "narcotics" in ndps_law.search_blob
    assert "criminal" in ndps_law.search_blob


def test_chip_css_does_not_wrap():
    css = Path("src/constitution_memorizer/web/static/styles.css").read_text()
    block = css.split(".laws-chip-strip {", 1)[1].split("}", 1)[0]
    assert "overflow-x: auto" in block
    assert "flex-wrap: nowrap" in block


def test_browse_resource_grid_lives_in_base_css():
    css = Path("src/constitution_memorizer/web/static/styles.css").read_text()
    block = css.split(".browse-resource-grid {", 1)[1].split("}", 1)[0]
    assert "display: grid" in block
    assert "1fr 1fr" in block or "repeat(2" in block
