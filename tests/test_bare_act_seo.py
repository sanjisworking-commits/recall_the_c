"""SEO wiring for Bare Act pages (sections, law index, schedules).

Integration tests here exercise route -> context -> template wiring only; the
exhaustive value tests for ``build_provision_seo`` live in test_article_seo.py.
Bulk tests assert completeness and canonical uniqueness across every indexable
Bare Act URL class.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act, list_bare_acts
from constitution_memorizer.web.seo import (
    CANONICAL_ORIGIN,
    DEFAULT_SEO_DESCRIPTION,
    TWITTER_HANDLE,
    build_law_seo,
    build_provision_seo,
    build_schedule_seo,
    law_canonical_url,
    laws_hub_canonical_url,
    provision_canonical_url,
    schedule_canonical_url,
)
from constitution_memorizer.web.sitemaps import build_laws_hub_sitemap

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


# ── HTML head extractors ─────────────────────────────────────────────────────


def _meta(html: str, *, prop: str | None = None, name: str | None = None) -> str | None:
    attr, value = ("property", prop) if prop else ("name", name)
    pattern = (
        rf'<meta[^>]*\b{attr}=["\']{re.escape(value)}["\'][^>]*'
        r'\bcontent=["\'](.*?)["\']'
    )
    m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1)
    pattern2 = (
        r'<meta[^>]*\bcontent=["\'](.*?)["\'][^>]*'
        rf'\b{attr}=["\']{re.escape(value)}["\']'
    )
    m2 = re.search(pattern2, html, re.IGNORECASE | re.DOTALL)
    return m2.group(1) if m2 else None


def _title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _canonical(html: str) -> str | None:
    m = re.search(
        r'<link[^>]*\brel=["\']canonical["\'][^>]*\bhref=["\'](.*?)["\']',
        html,
        re.IGNORECASE,
    )
    return m.group(1) if m else None


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db"))


# ── Section pages: route -> context -> template wiring ───────────────────────


@pytest.mark.parametrize(
    ("slug", "number"),
    [("bns", "103"), ("ndps", "20"), ("ndps", "27A"), ("ndps", "65")],
)
def test_section_page_metadata_wired(client: TestClient, slug: str, number: str):
    html = client.get(f"/laws/{slug}/section/{number}").text

    title = _title(html)
    assert f"Section {number}" in title
    assert title != "Recall the C"

    desc = _meta(html, name="description")
    assert desc
    assert desc != DEFAULT_SEO_DESCRIPTION

    expected_canonical = f"{CANONICAL_ORIGIN}/laws/{slug}/section/{number}"
    assert _canonical(html) == expected_canonical
    assert _meta(html, prop="og:url") == expected_canonical

    assert _meta(html, prop="og:title") == title
    assert _meta(html, name="twitter:title") == title
    assert _meta(html, prop="og:description") == desc
    assert _meta(html, name="twitter:description") == desc
    assert _meta(html, name="twitter:site") == TWITTER_HANDLE


def test_omitted_section_states_omitted(client: TestClient):
    # NDPS §65 is omitted: the metadata must say so, not imply a live provision.
    html = client.get("/laws/ndps/section/65").text
    assert "(Omitted)" in _title(html)
    assert "omitted" in (_meta(html, name="description") or "").lower()


def test_section_descriptions_are_distinct(client: TestClient):
    descriptions = {
        (slug, number): _meta(
            client.get(f"/laws/{slug}/section/{number}").text, name="description"
        )
        for slug, number in [("bns", "103"), ("ndps", "20"), ("ndps", "27A")]
    }
    assert len(set(descriptions.values())) == len(descriptions)


# ── Law-index and schedule pages ─────────────────────────────────────────────


@pytest.mark.parametrize("slug", ["bns", "ndps"])
def test_law_index_metadata_wired(client: TestClient, slug: str):
    html = client.get(f"/laws/{slug}").text

    title = _title(html)
    assert title != "Recall the C"
    assert get_bare_act(slug).title in title

    desc = _meta(html, name="description")
    assert desc and desc != DEFAULT_SEO_DESCRIPTION

    expected_canonical = f"{CANONICAL_ORIGIN}/laws/{slug}"
    assert _canonical(html) == expected_canonical
    assert _meta(html, prop="og:url") == expected_canonical


def test_schedule_page_metadata_wired(client: TestClient):
    ndps = get_bare_act("ndps")
    assert ndps.schedules, "expected NDPS to ship at least one schedule"
    schedule_slug = ndps.schedules[0].slug

    html = client.get(f"/laws/ndps/schedule/{schedule_slug}").text

    title = _title(html)
    assert title != "Recall the C"
    desc = _meta(html, name="description")
    assert desc and desc != DEFAULT_SEO_DESCRIPTION

    expected_canonical = f"{CANONICAL_ORIGIN}/laws/ndps/schedule/{schedule_slug}"
    assert _canonical(html) == expected_canonical
    assert _meta(html, prop="og:url") == expected_canonical
    assert _meta(html, name="twitter:site") == TWITTER_HANDLE


# ── Bulk coverage across every indexable Bare Act URL class ──────────────────


def _section_seo(act, section):
    heading = section.title
    body = section.plain_text
    return build_provision_seo(
        law_name=act.title,
        seo_law_name=act.short_title,
        provision_label="Section",
        provision_number=section.number,
        heading=heading,
        full_text=body,
        parent_label="Chapter",
        parent_number=section.chapter_number,
        parent_title=section.chapter_title,
    )


def test_every_indexable_object_produces_metadata():
    acts = list_bare_acts()
    assert acts
    for act in acts:
        law_title, law_desc = build_law_seo(
            law_name=act.title, meta_label=act.meta_label
        )
        assert law_title.strip() and law_desc.strip()

        for section in act.section_order:
            title, desc = _section_seo(act, section)
            assert title.strip(), f"empty title for {act.slug} §{section.number}"
            assert desc.strip(), f"empty desc for {act.slug} §{section.number}"

        for schedule in act.schedules:
            title, desc = build_schedule_seo(
                law_name=act.title,
                seo_law_name=act.short_title,
                schedule_title=schedule.title.title(),
                schedule_heading=schedule.display_heading,
            )
            assert title.strip() and desc.strip()


def test_all_bare_act_canonicals_are_unique():
    canonicals: list[str] = []
    for act in list_bare_acts():
        canonicals.append(law_canonical_url(act.slug))
        for section in act.section_order:
            canonicals.append(
                provision_canonical_url(act.slug, "section", section.number)
            )
        for schedule in act.schedules:
            canonicals.append(schedule_canonical_url(act.slug, schedule.slug))

    assert len(canonicals) == len(set(canonicals))


# ── /laws hub canonical (GSC: "User-declared canonical: None") ────────────────


def test_laws_hub_declares_self_canonical(client: TestClient):
    html = client.get("/laws").text
    assert _canonical(html) == f"{CANONICAL_ORIGIN}/laws"
    assert _canonical(html) == laws_hub_canonical_url()


@pytest.mark.parametrize(
    "query",
    ["?q=ndps", "?subject=criminal-law", "?q=bail&subject=criminal-law"],
)
def test_laws_hub_query_variants_canonicalize_to_bare_hub(
    client: TestClient, query: str
):
    # Filtered views of the hub must all point at the bare /laws URL so GSC
    # folds them into one canonical instead of treating each as its own page.
    html = client.get(f"/laws{query}").text
    assert _canonical(html) == laws_hub_canonical_url()


def test_laws_hub_sitemap_loc_matches_canonical():
    xml = build_laws_hub_sitemap()
    locs = re.findall(r"<loc>(.*?)</loc>", xml)
    assert locs == [laws_hub_canonical_url()]
