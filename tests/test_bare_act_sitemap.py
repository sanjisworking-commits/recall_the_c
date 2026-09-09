"""Generated sitemap index + per-law child sitemaps for Bare Act discovery.

Contract, not implementation detail: every registered full Bare Act must be
crawl-discoverable through the sitemap index and a manifest-backed child map,
the manifest must stay fresh against its source bytes, sitemap URLs must equal
the page canonicals, and NO sitemap endpoint may hydrate an Act.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

import constitution_memorizer.web.bare_acts as bare_acts
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import (
    BARE_ACTS,
    _data_path,
    runtime_cache_identity,
)
from constitution_memorizer.web.seo import (
    CANONICAL_ORIGIN,
    law_canonical_url,
    provision_canonical_url,
    schedule_canonical_url,
)
from constitution_memorizer.web.sitemaps import (
    MAX_DOCUMENT_BYTES,
    MAX_ENTRIES_PER_DOCUMENT,
    SITEMAP_NS,
    law_sitemap_name,
    load_law_sitemap_manifest,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
SM_NS = f"{{{SITEMAP_NS}}}"


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    load_law_sitemap_manifest.cache_clear()
    app = create_app(
        units_path=MINI_UNITS, db_path=tmp_path / "progress.db", multiuser=False
    )
    yield TestClient(app)
    load_law_sitemap_manifest.cache_clear()


def _locs(xml: str) -> list[str]:
    root = ET.fromstring(xml)
    return [el.text for el in root.iter(f"{SM_NS}loc")]


# --- XML correctness -------------------------------------------------------


def test_index_is_namespaced_sitemapindex(client: TestClient):
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert "application/xml" in resp.headers.get("content-type", "")
    assert resp.text.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    root = ET.fromstring(resp.text)
    assert root.tag == f"{SM_NS}sitemapindex"
    child_locs = _locs(resp.text)
    assert all(loc.startswith(f"{CANONICAL_ORIGIN}/") for loc in child_locs)
    assert len(child_locs) == len(set(child_locs))  # no duplicates


@pytest.mark.parametrize("path", ["/sitemap-laws.xml", "/sitemap-laws-bns.xml"])
def test_urlsets_are_namespaced(client: TestClient, path: str):
    resp = client.get(path)
    assert resp.status_code == 200
    assert "application/xml" in resp.headers.get("content-type", "")
    assert resp.text.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    root = ET.fromstring(resp.text)
    assert root.tag == f"{SM_NS}urlset"
    locs = _locs(resp.text)
    assert locs and all(loc.startswith("https://recall-the-c.in/") for loc in locs)
    assert len(locs) == len(set(locs))


def test_document_guards_reject_oversized(client: TestClient):
    from constitution_memorizer.web import sitemaps

    with pytest.raises(ValueError):
        sitemaps._guard_document("<x/>", MAX_ENTRIES_PER_DOCUMENT + 1)
    with pytest.raises(ValueError):
        sitemaps._guard_document("x" * (MAX_DOCUMENT_BYTES + 1), 1)


# --- Generalized contract over every registered Act ------------------------


def test_every_registered_act_is_discoverable(client: TestClient):
    manifest = load_law_sitemap_manifest()["laws"]
    index_locs = _locs(client.get("/sitemap.xml").text)
    index_children = {loc.rsplit("/", 1)[-1] for loc in index_locs}

    for slug in BARE_ACTS:
        assert slug in manifest, f"{slug} missing from manifest"
        assert law_sitemap_name(slug) in index_children

        resp = client.get(f"/sitemap-laws-{slug}.xml")
        assert resp.status_code == 200
        locs = _locs(resp.text)
        # Law landing + every section; schedules as present.
        assert law_canonical_url(slug) in locs
        entry = manifest[slug]
        assert entry["sections"], f"{slug} has no sections"
        assert len(locs) == 1 + len(entry["sections"]) + len(entry["schedules"])


def test_index_lists_exactly_the_registered_children(client: TestClient):
    index_children = {
        loc.rsplit("/", 1)[-1] for loc in _locs(client.get("/sitemap.xml").text)
    }
    expected = {"sitemap-core.xml", "sitemap-laws.xml"} | {
        law_sitemap_name(slug) for slug in BARE_ACTS
    }
    assert index_children == expected


# --- Interesting NDPS cases ------------------------------------------------


def test_ndps_alphanumeric_and_omitted_and_schedule(client: TestClient):
    locs = _locs(client.get("/sitemap-laws-ndps.xml").text)
    assert f"{CANONICAL_ORIGIN}/laws/ndps/section/27A" in locs  # amended id verbatim
    assert f"{CANONICAL_ORIGIN}/laws/ndps/section/65" in locs  # omitted, still indexed
    assert (
        f"{CANONICAL_ORIGIN}/laws/ndps/schedule/psychotropic-substances" in locs
    )


# --- Canonical parity ------------------------------------------------------


def test_manifest_urls_equal_canonical_helpers(client: TestClient):
    """Exhaustive + cheap: every sitemap loc equals its canonical helper output."""
    manifest = load_law_sitemap_manifest()["laws"]
    for slug, entry in manifest.items():
        locs = set(_locs(client.get(f"/sitemap-laws-{slug}.xml").text))
        assert law_canonical_url(slug) in locs
        for section_id in entry["sections"]:
            assert provision_canonical_url(slug, "section", section_id) in locs
        for schedule_slug in entry["schedules"]:
            assert schedule_canonical_url(slug, schedule_slug) in locs
        assert not any("?" in loc for loc in locs)  # no query variants


@pytest.mark.parametrize(
    "page_path, expected",
    [
        ("/laws/bns/section/103", "https://recall-the-c.in/laws/bns/section/103"),
        ("/laws/ndps/section/27A", "https://recall-the-c.in/laws/ndps/section/27A"),
        ("/laws/ndps/section/65", "https://recall-the-c.in/laws/ndps/section/65"),
        (
            "/laws/ndps/schedule/psychotropic-substances",
            "https://recall-the-c.in/laws/ndps/schedule/psychotropic-substances",
        ),
    ],
)
def test_page_canonical_matches_sitemap_loc(
    client: TestClient, page_path: str, expected: str
):
    html = client.get(page_path).text
    match = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    assert match and match.group(1) == expected


# --- Zero hydration --------------------------------------------------------


def test_no_sitemap_endpoint_hydrates_an_act(client: TestClient, monkeypatch):
    """Primary proof: the loader chokepoint and the Act JSON reader are untouched."""
    calls = {"load": 0, "read": 0}
    real_load = bare_acts._load_cached
    real_read = bare_acts.read_json

    def spy_load(slug, identity):
        calls["load"] += 1
        return real_load(slug, identity)

    def spy_read(path):
        calls["read"] += 1
        return real_read(path)

    monkeypatch.setattr(bare_acts, "_load_cached", spy_load)
    monkeypatch.setattr(bare_acts, "read_json", spy_read)
    real_load.cache_clear()

    endpoints = ["/sitemap.xml", "/sitemap-core.xml", "/sitemap-laws.xml"] + [
        f"/sitemap-laws-{slug}.xml" for slug in BARE_ACTS
    ]
    for path in endpoints:
        assert client.get(path).status_code == 200

    assert calls["load"] == 0, "a sitemap endpoint hydrated an Act"
    assert calls["read"] == 0, "a sitemap endpoint read Act JSON"
    # Secondary check (not sole proof): the loader cache stayed empty.
    assert real_load.cache_info().currsize == 0


# --- Manifest freshness (CI guard, no hydration) ---------------------------


def test_manifest_is_fresh_against_source_bytes():
    """Fails loudly if a runtime file/patch changed without regenerating.

    Byte-hash only — never parses an Act into the model.
    """
    manifest = load_law_sitemap_manifest()["laws"]
    assert set(manifest) == set(BARE_ACTS)
    for slug, spec in BARE_ACTS.items():
        entry = manifest[slug]
        assert entry["runtime_identity"] == runtime_cache_identity(spec)
        recorded = {s["filename"]: s["sha256"] for s in entry["sources"]}
        assert list(recorded) == [spec.filename, *spec.patch_filenames]
        for filename, digest in recorded.items():
            actual = hashlib.sha256(_data_path(filename).read_bytes()).hexdigest()
            assert actual == digest, f"stale digest for {slug}:{filename}"


# --- Robots ----------------------------------------------------------------


def test_robots_declares_sitemap_and_allows_laws(client: TestClient):
    body = client.get("/robots.txt").text
    assert "Sitemap: https://recall-the-c.in/sitemap.xml" in body
    assert "Disallow: /laws" not in body
