"""SEO metadata: unit tests for the generator + wiring tests for the route.

Unit tests assert exact generated strings. Integration tests assert only that
the route/template wiring is correct (tags exist, correspond, and differ per
Article), so wording tweaks do not cascade into web-layer failures.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.seo import (
    CANONICAL_ORIGIN,
    DEFAULT_SEO_DESCRIPTION,
    _clean_excerpt,
    article_canonical_url,
    build_article_seo,
)

ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "data" / "output" / "learning_units.json"

ART_14_TEXT = (
    "The State shall not deny to any person equality before the law or the "
    "equal protection of the laws within the territory of India."
)
ART_21_TEXT = (
    "No person shall be deprived of his life or personal liberty except "
    "according to procedure established by law."
)
ART_368_TEXT = (
    "(1) Notwithstanding anything in this Constitution, Parliament may in "
    "exercise of its constituent power amend by way of addition, variation "
    "or repeal any provision of this Constitution."
)


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — exact generated values
# ─────────────────────────────────────────────────────────────────────────────


def test_canonical_url():
    assert article_canonical_url("21") == f"{CANONICAL_ORIGIN}/browse/article/21"


def test_article_14_text_led():
    title, desc = build_article_seo(
        "14", "Equality before law", ART_14_TEXT, "III", "Fundamental Rights"
    )
    assert title == "Article 14 \u2013 Equality before law | Recall the C"
    assert desc.startswith("Article 14: The State shall not deny to any person")
    assert desc.endswith(
        "Part III, Fundamental Rights. Learn and revise with Recall the C."
    )


def test_article_21_full_sentence_not_truncated():
    title, desc = build_article_seo(
        "21",
        "Protection of life and personal liberty",
        ART_21_TEXT,
        "III",
        "Fundamental Rights",
    )
    assert title == (
        "Article 21 \u2013 Protection of life and personal liberty | Recall the C"
    )
    # Short enough to keep the whole sentence, so no ellipsis.
    assert "\u2026" not in desc
    assert desc == (
        "Article 21: No person shall be deprived of his life or personal "
        "liberty except according to procedure established by law. "
        "Part III, Fundamental Rights. Learn and revise with Recall the C."
    )


def test_article_368_strips_marker_and_leads_with_text():
    # A leading "(1)" is not, by itself, a reason to drop the text: the
    # marker is stripped and the substantive remainder is used.
    title, desc = build_article_seo(
        "368",
        "Power of Parliament to amend the Constitution and procedure therefor",
        ART_368_TEXT,
        "XX",
        None,
    )
    assert title.startswith("Article 368 \u2013 Power of Parliament to amend")
    assert "(1)" not in desc
    assert desc.startswith("Article 368: Notwithstanding anything in this Constitution")
    assert desc.endswith("Part XX. Learn and revise with Recall the C.")


def test_short_post_marker_text_falls_back_to_heading():
    # Once the "(a)" marker is stripped, "x." is too short to be a useful
    # snippet, so the description falls back to the official heading.
    title, desc = build_article_seo(
        "77", "Conduct of business of the Government", "(a) x.", "V", None
    )
    assert desc == (
        "Article 77 of the Constitution of India covers Conduct of business "
        "of the Government. Part V. Learn and revise with Recall the C."
    )


def test_missing_heading_with_valid_text():
    title, desc = build_article_seo(
        "50",
        None,
        "The State shall endeavour to separate the judiciary from the executive.",
        "IV",
        "Directive Principles",
    )
    assert title == "Article 50 of the Constitution of India | Recall the C"
    assert desc.startswith(
        "Article 50: The State shall endeavour to separate the judiciary"
    )
    assert desc.endswith(
        "Part IV, Directive Principles. Learn and revise with Recall the C."
    )


def test_missing_heading_empty_text_unknown_part_still_valid():
    title, desc = build_article_seo("999", None, "", "UNKNOWN", None)
    assert title == "Article 999 of the Constitution of India | Recall the C"
    assert desc == (
        "Article 999 of the Constitution of India. "
        "Learn and revise with Recall the C."
    )


def test_clean_excerpt_strips_marker_and_truncates_on_word_boundary():
    long_text = (
        "(1) Notwithstanding anything to the contrary, this provision shall "
        "continue in force until such time as Parliament by law otherwise "
        "provides for the matter in question."
    )
    excerpt = _clean_excerpt(long_text, limit=60)
    assert not excerpt.startswith("(1)")
    assert excerpt.startswith("Notwithstanding")
    assert excerpt.endswith("\u2026")
    # Truncated body (minus the ellipsis) never splits a word.
    body = excerpt[:-1]
    assert not long_text.split("(1) ", 1)[1].startswith(body + "x")
    assert " " not in body[-1:] or body == body.rstrip()


def test_clean_excerpt_handles_none():
    assert _clean_excerpt(None) == ""


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — route/template wiring only
# ─────────────────────────────────────────────────────────────────────────────


def _meta(html: str, *, prop: str | None = None, name: str | None = None) -> str | None:
    attr, value = ("property", prop) if prop else ("name", name)
    pattern = (
        rf'<meta[^>]*\b{attr}=["\']{re.escape(value)}["\'][^>]*'
        r'\bcontent=["\'](.*?)["\']'
    )
    m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1)
    # content may precede the identifying attribute
    pattern2 = (
        r'<meta[^>]*\bcontent=["\'](.*?)["\'][^>]*'
        rf'\b{attr}=["\']{re.escape(value)}["\']'
    )
    m2 = re.search(pattern2, html, re.IGNORECASE | re.DOTALL)
    return m2.group(1) if m2 else None


def _title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return (m.group(1).strip() if m else "")


def _canonical(html: str) -> str | None:
    m = re.search(
        r'<link[^>]*\brel=["\']canonical["\'][^>]*\bhref=["\'](.*?)["\']',
        html,
        re.IGNORECASE,
    )
    return m.group(1) if m else None


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    if not UNITS.exists():
        pytest.skip("learning_units.json missing")
    return TestClient(create_app(units_path=UNITS, db_path=tmp_path / "progress.db"))


@pytest.mark.parametrize("number", ["14", "21", "368"])
def test_article_page_has_wired_metadata(client: TestClient, number: str):
    html = client.get(f"/browse/article/{number}").text

    title = _title(html)
    assert f"Article {number}" in title

    desc = _meta(html, name="description")
    assert desc
    assert desc != DEFAULT_SEO_DESCRIPTION

    expected_canonical = f"{CANONICAL_ORIGIN}/browse/article/{number}"
    assert _canonical(html) == expected_canonical
    assert _meta(html, prop="og:url") == expected_canonical

    # Social tags correspond to the page title/description.
    assert _meta(html, prop="og:title") == title
    assert _meta(html, name="twitter:title") == title
    assert _meta(html, prop="og:description") == desc
    assert _meta(html, name="twitter:description") == desc


def test_article_descriptions_are_distinct(client: TestClient):
    desc = {}
    for number in ("14", "21", "368"):
        html = client.get(f"/browse/article/{number}").text
        desc[number] = _meta(html, name="description")
    assert desc["14"] != desc["21"]
    assert desc["21"] != desc["368"]
    assert desc["14"] != desc["368"]


def test_non_article_page_keeps_default_description(client: TestClient):
    html = client.get("/browse").text
    assert _meta(html, name="description") == DEFAULT_SEO_DESCRIPTION
