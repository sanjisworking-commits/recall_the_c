"""Server-rendered SEO metadata helpers for Article pages.

Pure functions with no I/O: the caller supplies data already loaded via the
existing ``ArticleBrowseView`` so there is no second corpus read or DB lookup.
"""

from __future__ import annotations

import re

CANONICAL_ORIGIN = "https://recall-the-c.in"

DEFAULT_SEO_TITLE = "Recall the C"

DEFAULT_SEO_DESCRIPTION = (
    "Recall the C is a study aid for memorising the Constitution of India."
)

# Minimum length of a cleaned excerpt before it is considered a usable snippet.
# Below this, the description falls back to the official heading rather than a
# thin fragment (e.g. Article 368's post-marker text).
_MIN_EXCERPT_LEN = 40

# A leading clause / sub-clause marker such as "(1)", "(a)", "(iv)".
_LEADING_MARKER_RE = re.compile(r"^\s*\([0-9A-Za-z]{1,3}\)\s*")


def article_canonical_url(article_number: str) -> str:
    """Absolute canonical URL for an Article's Browse page."""
    return f"{CANONICAL_ORIGIN}/browse/article/{article_number}"


def _clean_excerpt(text: str | None, limit: int = 120) -> str:
    """Collapse whitespace, drop a leading clause marker, truncate on a word.

    Truncation never splits a word: the text is cut at ``limit`` then rolled
    back to the previous space, trailing punctuation is trimmed, and an
    ellipsis is appended.
    """
    collapsed = " ".join((text or "").split())
    collapsed = _LEADING_MARKER_RE.sub("", collapsed)
    if len(collapsed) <= limit:
        return collapsed
    excerpt = collapsed[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{excerpt}\u2026"


def _ensure_period(text: str) -> str:
    """Return ``text`` terminated by sentence punctuation without doubling it."""
    stripped = text.rstrip()
    if not stripped:
        return stripped
    return stripped if stripped[-1] in ".!?\u2026" else f"{stripped}."


def _has_part(part_number: str | None) -> bool:
    return bool(part_number) and str(part_number).strip().upper() != "UNKNOWN"


def build_article_seo(
    article_number: str,
    heading: str | None,
    full_text: str | None,
    part_number: str | None,
    part_title: str | None,
) -> tuple[str, str]:
    """Build a unique ``(seo_title, seo_description)`` for an Article page."""
    number = str(article_number).strip()
    heading = (heading or "").strip()

    if heading:
        seo_title = f"Article {number} \u2013 {heading} | Recall the C"
    else:
        seo_title = f"Article {number} of the Constitution of India | Recall the C"

    excerpt = _clean_excerpt(full_text)
    if excerpt and len(excerpt) >= _MIN_EXCERPT_LEN:
        lead = f"Article {number}: {excerpt}"
    elif heading:
        lead = f"Article {number} of the Constitution of India covers {heading}."
    else:
        lead = f"Article {number} of the Constitution of India."

    parts = [_ensure_period(lead)]

    if _has_part(part_number):
        roman = str(part_number).strip()
        title = (part_title or "").strip()
        if title:
            parts.append(f"Part {roman}, {title}.")
        else:
            parts.append(f"Part {roman}.")

    parts.append("Learn and revise with Recall the C.")

    seo_description = " ".join(parts)
    return seo_title, seo_description
