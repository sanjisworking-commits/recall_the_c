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

**Root sitemap/index and sitemap discovery must never hydrate runtime/canonical JSON. At scale, sitemap URL enumeration must come from a lightweight build-time manifest, not request-time Act hydration.**

Today’s static [`src/constitution_memorizer/web/sitemap.xml`](../src/constitution_memorizer/web/sitemap.xml) is fine at current size. It is served as a file; do not replace that by parsing every law JSON on `GET /sitemap.xml`.

When URL count requires it (hundreds of Acts × sections), produce a **manifest during ingestion/build**:

```text
slug
source_version
section identifiers
public schedule slugs
optional trustworthy last_modified
```

Then serve a sitemap index (constitution + chunked law sitemaps). The manifest is **not** scraped from the Act during a web request.

Playground, roster, Learn, device, account, and other personalized URLs **never** enter a sitemap. See [PLAYGROUND.md](PLAYGROUND.md).

## Later stages (not this batch)

| Stage | When |
|---|---|
| Per-law indexes + chapter/section chunks | ~10–30+ larger Acts |
| DB/object-store corpus + precomputed search index | hundreds of laws or cross-law querying |

BNSS and further Acts land only after this contract is enforced by tests.
