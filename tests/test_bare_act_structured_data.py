"""Structured data (JSON-LD) for public Bare Act pages.

Stage 3 emits a Schema.org ``BreadcrumbList`` on the Bare Act law landing,
section and schedule pages. These tests parse the rendered
``application/ld+json`` as JSON (never string-match the payload), assert the
breadcrumb shape and that every ``item`` URL is byte-identical to the page's
canonical link and its sitemap ``loc``, and prove the markup never leaks onto
Constitution or private routes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import BARE_ACTS, get_bare_act
from constitution_memorizer.web.seo import (
    CANONICAL_ORIGIN,
    build_breadcrumb_schema,
    law_canonical_url,
    laws_hub_canonical_url,
    provision_canonical_url,
    schedule_canonical_url,
    serialize_structured_data,
)
from constitution_memorizer.web.sitemaps import build_law_sitemap

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"

# Every publicly routable (table-only) schedule across every registered Act.
# This tracks the exact public-schedule boundary from Stage 2, so it covers
# BNSS's supported First Schedule and NDPS's schedule while excluding BNSS's
# unrenderable Second Schedule.
PUBLIC_SCHEDULES = [
    (slug, schedule_slug)
    for slug in sorted(BARE_ACTS)
    for schedule_slug in get_bare_act(slug).public_schedule_slugs
]

_LD_JSON_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_CANONICAL_RE = re.compile(
    r'<link[^>]*\brel=["\']canonical["\'][^>]*\bhref=["\'](.*?)["\']',
    re.IGNORECASE,
)


def _ld_json_blocks(html: str) -> list[dict]:
    """Every ``application/ld+json`` payload on the page, parsed as JSON."""
    return [json.loads(m.group(1)) for m in _LD_JSON_RE.finditer(html)]


def _breadcrumb(html: str) -> dict:
    blocks = [b for b in _ld_json_blocks(html) if b.get("@type") == "BreadcrumbList"]
    assert len(blocks) == 1, f"expected exactly one BreadcrumbList, got {len(blocks)}"
    return blocks[0]


def _crumbs(schema: dict) -> list[tuple[int, str, str]]:
    return [
        (el["position"], el["name"], el["item"])
        for el in schema["itemListElement"]
    ]


def _canonical(html: str) -> str | None:
    m = _CANONICAL_RE.search(html)
    return m.group(1) if m else None


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    )


# ── Unit: schema builder ─────────────────────────────────────────────────────


def test_build_breadcrumb_schema_shape_and_positions():
    schema = build_breadcrumb_schema(
        [("Laws", "https://x/laws"), ("BNS", "https://x/laws/bns")]
    )
    assert schema["@context"] == "https://schema.org"
    assert schema["@type"] == "BreadcrumbList"
    assert _crumbs(schema) == [
        (1, "Laws", "https://x/laws"),
        (2, "BNS", "https://x/laws/bns"),
    ]
    assert all(el["@type"] == "ListItem" for el in schema["itemListElement"])


# ── Unit: safe serialisation ─────────────────────────────────────────────────


def test_serialize_round_trips_and_escapes_html_and_line_terminators():
    payload = {"name": "A < B > C & D\u2028E\u2029F"}
    out = serialize_structured_data(payload)

    # None of the HTML-significant characters survive verbatim.
    assert "<" not in out
    assert ">" not in out
    assert "&" not in out
    assert "\u2028" not in out
    assert "\u2029" not in out
    assert "\\u003c" in out and "\\u003e" in out and "\\u0026" in out
    assert "\\u2028" in out and "\\u2029" in out

    # ...but the JSON decodes back to the identical string.
    assert json.loads(out) == payload


def test_serialize_prevents_script_breakout():
    hostile = "</script><script>alert(1)</script>"
    out = serialize_structured_data({"name": hostile})

    # No literal closing tag can terminate the surrounding <script> element.
    assert "</script>" not in out.lower()
    # The value is preserved exactly once decoded.
    assert json.loads(out)["name"] == hostile


def test_serialized_breakout_stays_inert_in_rendered_page(client: TestClient):
    # The real template path must not undo the escaping: a section body is
    # never hostile, but this proves the |safe filter emits escaped bytes.
    html = client.get("/laws/ndps/section/27A").text
    block = _LD_JSON_RE.search(html)
    assert block is not None
    assert "</script>" not in block.group(1).lower()


# ── Integration: law landing page ────────────────────────────────────────────


def test_law_page_breadcrumb(client: TestClient):
    act = get_bare_act("ndps")
    html = client.get("/laws/ndps").text
    schema = _breadcrumb(html)

    assert _crumbs(schema) == [
        (1, "Laws", laws_hub_canonical_url()),
        (2, act.short_title, law_canonical_url("ndps")),
    ]
    # Last crumb == the page's own canonical link.
    assert schema["itemListElement"][-1]["item"] == _canonical(html)
    assert laws_hub_canonical_url() == f"{CANONICAL_ORIGIN}/laws"


# ── Integration: section pages ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("slug", "number"),
    [("ndps", "27A"), ("ndps", "65"), ("bnss", "531")],
)
def test_section_breadcrumb_has_no_chapter_item(
    client: TestClient, slug: str, number: str
):
    act = get_bare_act(slug)
    html = client.get(f"/laws/{slug}/section/{number}").text
    schema = _breadcrumb(html)

    section_url = provision_canonical_url(slug, "section", number)
    assert _crumbs(schema) == [
        (1, "Laws", laws_hub_canonical_url()),
        (2, act.short_title, law_canonical_url(slug)),
        (3, f"Section {number}", section_url),
    ]
    # Exactly three crumbs: Laws -> Act -> Section, never a chapter URL.
    assert len(schema["itemListElement"]) == 3
    chapter_url = provision_canonical_url(slug, "chapter", act.section(number).chapter_number)
    assert all(el["item"] != chapter_url for el in schema["itemListElement"])

    # JSON-LD item URL == HTML canonical == sitemap loc.
    assert section_url == _canonical(html)
    assert section_url in build_law_sitemap(slug)


# ── Integration: schedule page ───────────────────────────────────────────────


@pytest.mark.parametrize(("slug", "schedule_slug"), PUBLIC_SCHEDULES)
def test_schedule_breadcrumb_uses_untransformed_display_heading(
    client: TestClient, slug: str, schedule_slug: str
):
    # Covers every public (table-only) schedule, incl. BNSS's First Schedule.
    act = get_bare_act(slug)
    schedule = act.schedule(schedule_slug)
    resp = client.get(f"/laws/{slug}/schedule/{schedule_slug}")
    assert resp.status_code == 200
    schema = _breadcrumb(resp.text)

    schedule_url = schedule_canonical_url(slug, schedule_slug)
    assert _crumbs(schema) == [
        (1, "Laws", laws_hub_canonical_url()),
        (2, act.short_title, law_canonical_url(slug)),
        (3, schedule.display_heading, schedule_url),
    ]
    # The breadcrumb name is the verbatim reader-page identity, not .title()-cased.
    assert schema["itemListElement"][-1]["name"] == schedule.display_heading
    assert schedule_url == _canonical(resp.text)
    assert schedule_url in build_law_sitemap(slug)


def test_bnss_second_schedule_is_not_a_structured_data_surface(client: TestClient):
    # BNSS's Second Schedule has no table representation (is_table False), so
    # the route 404s and it must never surface a public BreadcrumbList page.
    # This guards the exact table-only boundary established in Stage 2.
    assert not get_bare_act("bnss").schedule("second-schedule").is_table
    resp = client.get("/laws/bnss/schedule/second-schedule")
    assert resp.status_code == 404
    assert "application/ld+json" not in resp.text
    assert all(
        block.get("@type") != "BreadcrumbList" for block in _ld_json_blocks(resp.text)
    )


# ── Isolation: Constitution and private routes ───────────────────────────────


def test_constitution_page_has_no_bare_act_breadcrumb(client: TestClient):
    # A representative Constitution response must not carry the Bare Act
    # BreadcrumbList. This does not forbid unrelated future Constitution JSON-LD.
    html = client.get("/browse/article/21").text
    assert all(
        block.get("@type") != "BreadcrumbList" for block in _ld_json_blocks(html)
    )


@pytest.mark.parametrize("path", ["/progress", "/dashboard", "/settings"])
def test_private_page_has_no_structured_data(client: TestClient, path: str):
    # Single-user mode renders the owner's real private page (200, no login
    # redirect), so this asserts against the actual private body — not a 302.
    resp = client.get(path)
    assert resp.status_code == 200
    assert not resp.history, f"{path} redirected: {resp.history}"
    assert "application/ld+json" not in resp.text
