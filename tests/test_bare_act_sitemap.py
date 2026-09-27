"""Generated sitemap index + per-law child sitemaps for Bare Act discovery.

Contract, not implementation detail: every registered full Bare Act must be
crawl-discoverable through the sitemap index and a manifest-backed child map,
the manifest must stay fresh against its source bytes, sitemap URLs must equal
the page canonicals, and NO sitemap endpoint may hydrate an Act.
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

import constitution_memorizer.web.bare_acts as bare_acts
import constitution_memorizer.web.sitemaps as sitemaps
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
        ("/laws", "https://recall-the-c.in/laws"),
        ("/laws/ndps", "https://recall-the-c.in/laws/ndps"),
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
        assert entry["slug"] == slug
        assert entry["source_version"] == spec.source_version
        assert "last_modified" not in entry
        recorded = {s["filename"]: s["sha256"] for s in entry["sources"]}
        assert list(recorded) == [spec.filename, *spec.patch_filenames]
        for filename, digest in recorded.items():
            actual = hashlib.sha256(_data_path(filename).read_bytes()).hexdigest()
            assert actual == digest, f"stale digest for {slug}:{filename}"


# --- Packaging (deployment contract) ---------------------------------------


@pytest.mark.parametrize(
    "filename", ["law_sitemap_manifest.json", "sitemap-core.xml"]
)
def test_sitemap_data_files_ship_inside_the_package(filename: str):
    """The manifest and core sitemap must live in the package AND be declared
    package-data, or the built wheel omits them and every file-reading sitemap
    route 500s in production (only the in-memory hub map survives).

    This guards the exact regression that took the deployed sitemaps down: the
    files existed in the repo but outside the wheel.
    """
    # 1. Physically inside the importable package (what the routes read).
    assert (sitemaps._WEB_DIR / filename).is_file()

    # 2. Declared as package-data so `pip install .` ships it in the wheel.
    pyproject = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    )
    package_data = pyproject["tool"]["setuptools"]["package-data"][
        "constitution_memorizer"
    ]
    assert f"web/{filename}" in package_data


# --- Robots ----------------------------------------------------------------


def test_robots_declares_sitemap_and_allows_laws(client: TestClient):
    body = client.get("/robots.txt").text
    assert "Sitemap: https://recall-the-c.in/sitemap.xml" in body
    assert "Disallow: /laws" not in body


def test_intra_law_chunking_splits_without_loss_or_dupes(monkeypatch):
    load_law_sitemap_manifest.cache_clear()
    monkeypatch.setattr(sitemaps, "SITEMAP_URL_CHUNK_SIZE", 2)
    docs = sitemaps.law_sitemap_documents("ndps")
    assert docs is not None
    assert len(docs) > 1
    combined: list[str] = []
    for name, locs in docs:
        assert name.startswith("sitemap-laws-ndps-")
        assert name.endswith(".xml")
        assert 1 <= len(locs) <= 2
        combined.extend(locs)
    expected = sitemaps.law_url_locs("ndps")
    assert combined == expected
    assert len(combined) == len(set(combined))
    index = sitemaps.build_sitemap_index()
    for name, _chunk_locs in docs:
        assert f"{CANONICAL_ORIGIN}/{name}" in index
    assert f"{CANONICAL_ORIGIN}/sitemap-laws-ndps.xml" not in index
    assert sitemaps.build_law_sitemap("ndps") is None
    assert sitemaps.parse_law_sitemap_ref("ndps") is None
    assert sitemaps.parse_law_sitemap_ref("ndps-1") == ("ndps", 1)
    assert sitemaps.parse_law_sitemap_ref("ndps-99999") is None
    assert sitemaps.parse_law_sitemap_ref("../ndps") is None
    first = sitemaps.build_law_sitemap("ndps", chunk=1)
    assert first is not None
    assert len(_locs(first)) <= 2
    load_law_sitemap_manifest.cache_clear()


def test_chunked_sitemap_http_roundtrip(client: TestClient, monkeypatch):
    monkeypatch.setattr(sitemaps, "SITEMAP_URL_CHUNK_SIZE", 2)
    load_law_sitemap_manifest.cache_clear()
    index = client.get("/sitemap.xml")
    assert index.status_code == 200
    assert f"{CANONICAL_ORIGIN}/sitemap-laws-ndps-1.xml" in index.text
    assert f"{CANONICAL_ORIGIN}/sitemap-laws-ndps.xml" not in index.text
    first = client.get("/sitemap-laws-ndps-1.xml")
    assert first.status_code == 200
    assert len(_locs(first.text)) <= 2
    missing = client.get("/sitemap-laws-ndps.xml")
    assert missing.status_code == 404
    load_law_sitemap_manifest.cache_clear()


def test_unchunked_law_rejects_numbered_child(client: TestClient):
    assert sitemaps.parse_law_sitemap_ref("ndps") == ("ndps", None)
    resp = client.get("/sitemap-laws-ndps-1.xml")
    assert resp.status_code == 404
    unknown = client.get("/sitemap-laws-not-a-registered-law.xml")
    assert unknown.status_code == 404


def _builder_module():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "build_law_sitemap_manifest.py"
    spec = importlib.util.spec_from_file_location("build_law_sitemap_manifest", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_builder_emits_explicit_slug_and_source_version():
    """Offline builder is the only regenerator. Test-time hydration is allowed."""
    from constitution_memorizer.web.bare_acts import get_bare_act

    builder = _builder_module()
    manifest = builder.build_manifest()
    assert manifest["schema_version"] == builder.SCHEMA_VERSION == 2
    assert set(manifest["laws"]) == set(BARE_ACTS)
    for slug, spec in BARE_ACTS.items():
        entry = manifest["laws"][slug]
        act = get_bare_act(slug)
        assert entry["slug"] == slug
        assert entry["source_version"] == spec.source_version
        assert entry["runtime_identity"] == runtime_cache_identity(spec)
        assert entry["sections"] == [section.number for section in act.section_order]
        assert entry["schedules"] == list(act.public_schedule_slugs)
        assert "last_modified" not in entry
        unsupported = [
            sched.slug for sched in act.schedules if not sched.is_table
        ]
        for schedule_slug in unsupported:
            assert schedule_slug not in entry["schedules"]


def test_committed_manifest_matches_builder_output():
    builder = _builder_module()
    assert builder._serialize(builder.build_manifest()) == (
        Path(__file__).resolve().parents[1]
        / "src"
        / "constitution_memorizer"
        / "web"
        / "law_sitemap_manifest.json"
    ).read_text(encoding="utf-8")
