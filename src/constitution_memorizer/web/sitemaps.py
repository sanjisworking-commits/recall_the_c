"""Generated XML sitemaps for crawler discovery — zero Bare Act hydration.

Every function here is pure and runs on the request path. It consumes only the
lightweight `BARE_ACTS` registry specs, the committed `law_sitemap_manifest.json`
(built offline by `scripts/build_law_sitemap_manifest.py`), and the canonical
URL helpers. It MUST NOT call `get_bare_act()` / `list_bare_acts()` or read any
runtime/canonical statute JSON: a crawler hits every child sitemap, and paying a
statute parse per fetch would turn discovery into a cache-churn workload.

Layout (all root-level, so each map's URLs stay within its own path scope):

    /sitemap.xml            sitemap index
    /sitemap-core.xml       existing static marketing + Constitution urlset
    /sitemap-laws.xml       the /laws hub
    /sitemap-laws-{slug}.xml one urlset per registered full Bare Act
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from constitution_memorizer.utils.json_io import read_json
from constitution_memorizer.web.bare_acts import BARE_ACTS
from constitution_memorizer.web.seo import (
    CANONICAL_ORIGIN,
    law_canonical_url,
    provision_canonical_url,
    schedule_canonical_url,
)

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_XML_DECL = '<?xml version="1.0" encoding="UTF-8"?>'

# Sitemap protocol ceilings, applied to every generated document (index and
# urlsets alike). We are far below both; the guards exist so a future corpus
# shape fails loudly here rather than shipping a spec-violating sitemap.
MAX_ENTRIES_PER_DOCUMENT = 50_000
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024

CORE_SITEMAP_NAME = "sitemap-core.xml"
LAWS_HUB_SITEMAP_NAME = "sitemap-laws.xml"

_WEB_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _WEB_DIR.parents[2]
_MANIFEST_FILENAME = "law_sitemap_manifest.json"


def law_sitemap_name(slug: str) -> str:
    """Child-sitemap filename for a law slug (``sitemap-laws-bns.xml``)."""
    return f"sitemap-laws-{slug}.xml"


def _child_sitemap_url(name: str) -> str:
    return f"{CANONICAL_ORIGIN}/{name}"


def _manifest_path() -> Path:
    """Locate the committed manifest, repo layout first then packaged."""
    candidates = (
        _REPO_ROOT / "data" / "reference" / _MANIFEST_FILENAME,
        _WEB_DIR / _MANIFEST_FILENAME,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"{_MANIFEST_FILENAME} not found at {candidates[0]} or {candidates[1]}. "
        "Run `python -m scripts.build_law_sitemap_manifest`."
    )


@lru_cache(maxsize=1)
def load_law_sitemap_manifest() -> dict:
    """Read + process-cache the committed manifest. No Act is parsed.

    Cached with ``lru_cache``; tests that swap the manifest or a registry entry
    must call ``load_law_sitemap_manifest.cache_clear()`` so ordering never
    decides which manifest a test sees.
    """
    return read_json(_manifest_path())


def _guard_document(xml: str, entry_count: int) -> str:
    """Fail loudly if a document breaks either protocol ceiling."""
    if entry_count > MAX_ENTRIES_PER_DOCUMENT:
        raise ValueError(
            f"sitemap document has {entry_count} entries "
            f"(> {MAX_ENTRIES_PER_DOCUMENT}); introduce chunking"
        )
    byte_len = len(xml.encode("utf-8"))
    if byte_len > MAX_DOCUMENT_BYTES:
        raise ValueError(
            f"sitemap document is {byte_len} bytes "
            f"(> {MAX_DOCUMENT_BYTES}); introduce chunking"
        )
    return xml


def _render_urlset(locs: list[str]) -> str:
    body = "\n".join(f"  <url><loc>{escape(loc)}</loc></url>" for loc in locs)
    xml = (
        f"{_XML_DECL}\n"
        f'<urlset xmlns="{SITEMAP_NS}">\n'
        f"{body}\n"
        "</urlset>\n"
    )
    return _guard_document(xml, len(locs))


def _render_index(child_urls: list[str]) -> str:
    body = "\n".join(
        f"  <sitemap><loc>{escape(url)}</loc></sitemap>" for url in child_urls
    )
    xml = (
        f"{_XML_DECL}\n"
        f'<sitemapindex xmlns="{SITEMAP_NS}">\n'
        f"{body}\n"
        "</sitemapindex>\n"
    )
    return _guard_document(xml, len(child_urls))


def _registered_laws_in_manifest() -> list[str]:
    """Registered slugs that also have a manifest entry, sorted.

    Defensive: never advertise a child map we cannot build. A registered slug
    missing from the manifest is a build error the freshness test catches; here
    we simply omit it rather than emit a 500-ing child `<loc>`.
    """
    manifest_laws = load_law_sitemap_manifest().get("laws", {})
    return sorted(slug for slug in BARE_ACTS if slug in manifest_laws)


def build_sitemap_index() -> str:
    """The `<sitemapindex>`: core + laws hub + one child per registered law.

    Metadata only — iterates `BARE_ACTS` keys and the manifest, never an Act.
    """
    child_urls = [
        _child_sitemap_url(CORE_SITEMAP_NAME),
        _child_sitemap_url(LAWS_HUB_SITEMAP_NAME),
    ]
    child_urls += [
        _child_sitemap_url(law_sitemap_name(slug))
        for slug in _registered_laws_in_manifest()
    ]
    return _render_index(child_urls)


def build_laws_hub_sitemap() -> str:
    """A one-URL urlset for the `/laws` hub page. No hydration."""
    return _render_urlset([f"{CANONICAL_ORIGIN}/laws"])


def build_law_sitemap(slug: str) -> str | None:
    """Per-law urlset from the manifest: law + sections + public schedules.

    Returns ``None`` for an unregistered slug or one absent from the manifest,
    so the route answers 404. Section identifiers are used verbatim (strings
    such as ``27A``); omitted sections stay in (they have live reader pages).
    """
    if slug not in BARE_ACTS:
        return None
    entry = load_law_sitemap_manifest().get("laws", {}).get(slug)
    if entry is None:
        return None

    locs = [law_canonical_url(slug)]
    locs += [
        provision_canonical_url(slug, "section", section_id)
        for section_id in entry.get("sections", [])
    ]
    locs += [
        schedule_canonical_url(slug, schedule_slug)
        for schedule_slug in entry.get("schedules", [])
    ]
    return _render_urlset(locs)
