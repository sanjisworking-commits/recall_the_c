# Law loading architecture

Adding Bare Acts must not make application startup or the `/laws` catalogue
parse every canonical or runtime JSON file. The number and size of Acts will
grow; hydration cost must stay on the Act that was actually requested.

See also the module notes in `src/constitution_memorizer/web/bare_acts.py`
and `src/constitution_memorizer/web/law_catalog.py`.

## Four distinct concepts

These are not four caches of the same object.

```text
Canonical artifact
    ↓ build/derivation
Runtime artifact
    ↓ lazy hydration
Process-local parsed BareAct

Catalogue metadata
    └── completely separate path
```

### A. Canonical artifact

Archival source-of-truth (for example `data/reference/bns_canonical_v1.json`).
Provenance-rich. Not opened merely to render `/laws` or to start the app.

A SHA-256 stored inside canonical JSON is Gazette/PDF provenance. It is not
the process-cache identity of the reader artifact.

### B. Runtime artifact

Reader-optimised law JSON shipped with the app (for example
`bns_runtime_v1.json`, `ndps_act_final.json`). In Stage 1 this is one file
per Act (plus optional patches). Opened only when a route needs that Act.

### C. Process-local hydrated representation

The parsed `BareAct` object. Cached per worker on:

```text
identity = f"{slug}:{source_version}:{source_hash or filename}"
```

`source_hash` is an optional identity of the **runtime** artifact, taken from
registry metadata. The loader does not open, stat, or hash the JSON file to
compute this key. Deployment / process recycle is the normal invalidation.

### D. Catalogue / registry metadata

Tiny. Safe at startup. Used by `GET /laws`. Includes slug, display names,
scope labels, and `BareActSpec` fields such as `source_version` /
`source_hash`. Must not require runtime or canonical hydration.

Index search uses `search_blob` on this seed. It must not parse every Act.

## Stage 1 rules

1. Startup and `/laws` read catalogue/registry metadata only.
2. A complete law hydrates only when a route needs that law.
3. After a successful parse, reuse the process-local `BareAct` for the same
   identity. Do not introduce Redis (or Postgres) as a store for static Acts.
4. Do not preload every registered Act in FastAPI lifespan. Do not call
   `list_bare_acts()` from catalogue rendering or startup. That helper
   hydrates every Act and exists for debug/tests only.
5. Stage 1 keeps one runtime file per Act. Later chunking (manifest +
   chapter/section files) must be able to sit behind `get_bare_act` without
   changing public routes. Do not implement chunking here.
6. Do not implement cross-law search by loading every Act.

## Sitemap (never hydrate Acts)

**Root sitemap/index and sitemap discovery must never hydrate runtime/canonical JSON. Sitemap URL enumeration comes from a lightweight build-time manifest, not request-time Act hydration.**

Current public layout (generic Bare Act SEO/sitemap from production `main`):

```text
/sitemap.xml              generated sitemap index
/sitemap-core.xml         static Constitution + marketing urlset
/sitemap-laws.xml         the /laws hub
/sitemap-laws-{slug}.xml  one urlset per registered full Bare Act
```

The index and per-law urlsets are built from the lightweight `BARE_ACTS` registry (`BareActSpec`) plus the committed manifest [`data/reference/law_sitemap_manifest.json`](../data/reference/law_sitemap_manifest.json). Request handlers MUST NOT call `get_bare_act()` / `list_bare_acts()` or open runtime/canonical statute JSON. Rebuild the manifest during ingestion/build (`scripts/build_law_sitemap_manifest.py`), never during a web request.

Manifest fields:

```text
slug
source_version
section identifiers
public schedule slugs
optional trustworthy last_modified
```

Playground, roster, Learn, device, account, and other personalized URLs **never** enter a sitemap. See [PLAYGROUND.md](PLAYGROUND.md). Public `/laws*` remains the indexable surface. Do not add a second SEO engine. Playground `noindex` / `X-Robots-Tag` is a later Stage 1 batch.

## Later stages (not this batch)

| Stage | When |
|---|---|
| Per-law indexes + chapter/section chunks | ~10–30+ larger Acts |
| DB/object-store corpus + precomputed search index | hundreds of laws or cross-law querying |

BNSS is already a registered full Bare Act under this loader. Further Acts land only after this contract is enforced by tests.
