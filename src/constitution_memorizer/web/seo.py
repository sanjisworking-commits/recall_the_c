"""Server-rendered SEO metadata helpers for legal provisions.

Law-generic: the same engine serves the Constitution's Articles and any Bare
Act's Sections/Rules. Callers supply data already loaded by their own view
model, so there is no I/O, corpus read, or DB lookup here. Routing stays
independent of SEO — the caller passes the canonical URL it knows best.
"""

from __future__ import annotations

import json
import re

CANONICAL_ORIGIN = "https://recall-the-c.in"

DEFAULT_SEO_TITLE = "Recall the C"

DEFAULT_SEO_DESCRIPTION = (
    "Learn and memorise Indian law with Recall the C "
    "using structured learning and spaced revision."
)

# Brand account for Twitter/X card attribution. No creator handle: this is the
# brand, not an individual content author.
TWITTER_HANDLE = "@recallthec"

# Minimum length of a cleaned excerpt before it is considered a usable snippet.
# Below this, the description falls back to the heading rather than a thin
# fragment (e.g. a provision whose text is only a short sub-clause).
_MIN_EXCERPT_LEN = 40

# A leading clause / sub-clause marker such as "(1)", "(a)", "(iv)".
_LEADING_MARKER_RE = re.compile(r"^\s*\([0-9A-Za-z]{1,3}\)\s*")


def article_canonical_url(article_number: str) -> str:
    """Canonical URL for a Constitution Article's Browse page."""
    return f"{CANONICAL_ORIGIN}/browse/article/{article_number}"


def provision_canonical_url(
    law_slug: str, provision_type: str, provision_number: str
) -> str:
    """Canonical URL for a Bare Act provision (the production ``/laws`` route).

    ``provision_number`` is kept verbatim as a string: amended Acts carry
    identifiers such as ``27A`` or ``52A``.
    """
    return (
        f"{CANONICAL_ORIGIN}/laws/{law_slug}/{provision_type}/{provision_number}"
    )


def laws_hub_canonical_url() -> str:
    """Canonical URL for the ``/laws`` hub (the Bare Act breadcrumb root).

    Single source for the breadcrumb root so its URL stays byte-identical to
    the hub's sitemap ``loc`` in :func:`sitemaps.build_laws_hub_sitemap`.
    """
    return f"{CANONICAL_ORIGIN}/laws"


def law_canonical_url(law_slug: str) -> str:
    """Canonical URL for a Bare Act's landing page."""
    return f"{CANONICAL_ORIGIN}/laws/{law_slug}"


def schedule_canonical_url(law_slug: str, schedule_slug: str) -> str:
    """Canonical URL for a Bare Act schedule page."""
    return f"{CANONICAL_ORIGIN}/laws/{law_slug}/schedule/{schedule_slug}"


def _with_the(law_name: str) -> str:
    """Prefix ``the`` for prose (``of the Constitution of India``).

    Used only mid-sentence (``... of {the_law}: ...``), so a name that already
    carries a leading article is normalised to a lowercase ``the`` rather than
    left capitalised — otherwise a registry short name like ``The BNS, 2023``
    would render as ``of The BNS, 2023`` mid-sentence.
    """
    name = (law_name or "").strip()
    if not name:
        return name
    if name[:4].lower() == "the ":
        return f"the {name[4:]}"
    return f"the {name}"


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


def build_provision_seo(
    *,
    law_name: str,
    provision_label: str,
    provision_number: str,
    heading: str | None,
    full_text: str | None,
    seo_law_name: str | None = None,
    parent_label: str | None = None,
    parent_number: str | None = None,
    parent_title: str | None = None,
    include_law_in_title: bool = True,
    include_law_in_description: bool = True,
) -> tuple[str, str]:
    """Build a unique ``(seo_title, seo_description)`` for a legal provision.

    ``provision_label``/``provision_number`` are e.g. ``"Article"``/``"21"`` or
    ``"Section"``/``"7"``. ``parent_*`` is the enclosing Part or Chapter.
    ``seo_law_name`` is a short label (``"IBC"``) used in the title when the
    full ``law_name`` is long. The ``include_law_in_*`` flags let callers whose
    URL/query already implies the law (the Constitution) drop the law name from
    the text-led forms; the disambiguating "of the {law}" forms always keep it.
    """
    number = str(provision_number).strip()
    label = (provision_label or "").strip()
    heading = (heading or "").strip()
    short_law = (seo_law_name or "").strip() or (law_name or "").strip()
    the_law = _with_the(law_name)

    if heading:
        base = f"{label} {number} \u2013 {heading}"
        if include_law_in_title:
            seo_title = f"{base} | {short_law} | Recall the C"
        else:
            seo_title = f"{base} | Recall the C"
    else:
        seo_title = f"{label} {number} of {the_law} | Recall the C"

    excerpt = _clean_excerpt(full_text)
    if excerpt and len(excerpt) >= _MIN_EXCERPT_LEN:
        if include_law_in_description:
            lead = f"{label} {number} of {the_law}: {excerpt}"
        else:
            lead = f"{label} {number}: {excerpt}"
    elif heading:
        lead = f"{label} {number} of {the_law} covers {heading}."
    else:
        lead = f"{label} {number} of {the_law}."

    parts = [_ensure_period(lead)]

    if (
        parent_label
        and parent_number
        and str(parent_number).strip().upper() != "UNKNOWN"
    ):
        parent_num = str(parent_number).strip()
        parent_name = (parent_title or "").strip()
        if parent_name:
            parts.append(f"{parent_label} {parent_num}, {parent_name}.")
        else:
            parts.append(f"{parent_label} {parent_num}.")

    parts.append("Learn and revise with Recall the C.")

    seo_description = " ".join(parts)
    return seo_title, seo_description


def build_article_seo(
    article_number: str,
    heading: str | None,
    full_text: str | None,
    part_number: str | None,
    part_title: str | None,
) -> tuple[str, str]:
    """Constitution wrapper over :func:`build_provision_seo`.

    Omits the law name from the text-led title/description because a
    ``/browse/article/{n}`` query already reads clearly as the Constitution.
    """
    return build_provision_seo(
        law_name="Constitution of India",
        provision_label="Article",
        provision_number=article_number,
        heading=heading,
        full_text=full_text,
        parent_label="Part",
        parent_number=part_number,
        parent_title=part_title,
        include_law_in_title=False,
        include_law_in_description=False,
    )


def build_law_seo(*, law_name: str, meta_label: str | None = None) -> tuple[str, str]:
    """Build ``(seo_title, seo_description)`` for a Bare Act landing page."""
    seo_title = f"{law_name} | Recall the C"
    seo_description = f"Read {_with_the(law_name)} in full on Recall the C."
    if meta_label:
        seo_description += f" {_ensure_period(meta_label)}"
    return seo_title, seo_description


def build_schedule_seo(
    *,
    law_name: str,
    schedule_title: str,
    schedule_heading: str | None = None,
    seo_law_name: str | None = None,
) -> tuple[str, str]:
    """Build ``(seo_title, seo_description)`` for a Bare Act schedule page."""
    short_law = (seo_law_name or "").strip() or (law_name or "").strip()
    title = (schedule_title or "Schedule").strip()

    seo_title = f"{title} \u2013 {short_law} | Recall the C"

    lead = f"{title} of {_with_the(law_name)}"
    heading = (schedule_heading or "").strip()
    if heading:
        lead += f": {heading}"
    seo_description = (
        f"{_ensure_period(lead)} "
        "Learn and revise with structured learning and spaced revision."
    )
    return seo_title, seo_description


# ── Structured data (JSON-LD) ────────────────────────────────────────────────

# Characters that must never survive verbatim inside an HTML ``<script>`` body.
# ``<`` and ``>`` prevent a ``</script>`` breakout; ``&`` keeps the payload a
# valid HTML text node; U+2028/U+2029 are line terminators that break embedded
# scripts in some parsers. All are represented as their JSON ``\uXXXX`` escapes,
# which decode back to the identical string.
_HTML_SCRIPT_ESCAPES = {
    "<": "\\u003c",
    ">": "\\u003e",
    "&": "\\u0026",
    "\u2028": "\\u2028",
    "\u2029": "\\u2029",
}
_HTML_SCRIPT_ESCAPE_RE = re.compile(r"[<>&\u2028\u2029]")


def build_breadcrumb_schema(items: list[tuple[str, str]]) -> dict:
    """Build a Schema.org ``BreadcrumbList`` from ordered ``(name, url)`` pairs.

    Positions are 1-based and follow list order; the final pair is the current
    page (Google includes the current page as the last crumb). Callers pass
    canonical URLs so each ``item`` equals the page's ``<link rel="canonical">``
    and its sitemap ``loc``.
    """
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "name": name,
                "item": url,
            }
            for position, (name, url) in enumerate(items, start=1)
        ],
    }


def serialize_structured_data(data) -> str:
    """Serialise JSON-LD for safe embedding in an inline ``<script>`` block.

    Produces compact JSON, then escapes the characters that could terminate the
    surrounding ``<script>`` element or break parsing (``<``, ``>``, ``&``,
    U+2028, U+2029) as ``\\uXXXX`` sequences. The result is valid JSON-LD whose
    values decode to the originals, so a statutory string containing literal
    ``</script>`` embeds as ``\\u003c/script\\u003e`` and cannot break out.
    """
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return _HTML_SCRIPT_ESCAPE_RE.sub(lambda m: _HTML_SCRIPT_ESCAPES[m.group(0)], raw)
