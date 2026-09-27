# Playground Milestone 10 — End-of-batch report

**Branch:** `cursor/playground-220d`
**PR:** [#188](https://github.com/sanjisworking-commits/recall_the_c/pull/188)
**Closed as:** Milestone 10 = `DONE` — weight **4**
**Stage 1:** **93.0 / 100**
**Stage 2:** `NOT STARTED`

The architectural split this batch protects is **public statutory discovery vs private learning state**. Google may crawl every canonical Act, section, and supported schedule. It must never index a user's Playground, revision schedule, devices, billing, or account.

Scoreboard: [PLAYGROUND_DELIVERY_TRACKER.md](PLAYGROUND_DELIVERY_TRACKER.md). Product rules: [PLAYGROUND.md](PLAYGROUND.md). Sitemap contract: [law-loading.md](law-loading.md).

This was verification plus private-surface hardening, not an SEO rewrite. [`web/seo.py`](../src/constitution_memorizer/web/seo.py) and [`web/sitemaps.py`](../src/constitution_memorizer/web/sitemaps.py) remain the only engines.

---

## Tracker

```text
Milestone 0 = DONE
Milestone 1 = DONE
Milestone 2 = DONE
Milestone 3 = DONE
Milestone 4 = DONE
Milestone 5 = DONE
Milestone 6 = DONE — 37/37
Milestone 7 = DONE — 15
Milestone 8 = DONE — 20/20
Milestone 9 = DONE — 15/15
Milestone 10 = DONE — 16/16

Stage 1 = 93.0 / 100
Stage 2 = NOT STARTED
```

M11 is **not** scored.

```text
Public law SEO
[x] /laws unique metadata
[x] full Act canonical
[x] section canonical
[x] schedule canonical
[x] query/filter variants canonicalized appropriately
[x] existing generic seo.py reused

Private SEO
[x] /playground* → noindex, nofollow
[x] Learn/progress/revision → noindex
[x] roster → noindex
[x] account/device/payment private pages → noindex where applicable
[x] future non-HTML private routes use X-Robots-Tag

Sitemap
[x] Playground absent
[x] root sitemap/index never hydrates Acts
[x] build-time law URL manifest
[x] manifest includes slug/source version/sections/schedules/optional last-modified
[x] scalable sitemap index/chunking
```

---

## Public SEO

`GET /laws` uses `build_laws_hub_seo()` and `laws_hub_canonical_url()`. Title and description are unique (`Laws of India | Recall the C` / statute-hub copy) and do not fall back to `DEFAULT_SEO_TITLE` / `DEFAULT_SEO_DESCRIPTION`. The hub still renders from catalogue metadata — zero Act hydration.

Query/filter variants (`/laws?q=bail`, `/laws?subject=criminal`, combinations) keep the same unique metadata and canonicalize to `https://recall-the-c.in/laws`. They are not indexable as distinct pages.

| Surface | Canonical helper |
|---------|------------------|
| Hub | `laws_hub_canonical_url()` |
| Act | `law_canonical_url(law_id)` — no query string, no alternate-slug duplicate |
| Section | `provision_canonical_url(law_id, "section", number)` — string IDs (`27A`, `68-I`, `68-O`) |
| Schedule | `schedule_canonical_url(law_id, slug)` — `public_schedule_slugs` only |
| Constitution Article | `article_canonical_url` / `build_article_seo` |

Existing BreadcrumbList JSON-LD, canonical URL consistency, and safe `serialize_structured_data()` are unchanged.

---

## Private SEO

Authority is still `NOINDEX_PATH_PREFIXES` + `is_noindex_path()` (prefix match that does not swallow `/laws` via `/learn`). Jinja context sets `robots_noindex`. `base.html` emits:

```html
<meta name="robots" content="noindex, nofollow">
```

Playground templates extend `playground_base.html` → `base.html`, so home, roster, roster/next, workspace, section selection, learn modes, revision, source-review, add/remove, and entitlement gates inherit the meta. Standalone `login.html` carries the same robots content.

Covered HTML includes `/dashboard`, `/calendar`, `/progress`, `/learn`, `/learning`, `/profile`, `/profile/security/devices`, `/settings`, `/billing/subscriptions`, `/admin`, `/welcome`, `/login`, `/signed-out`, `/session-expired`. Public `/`, `/laws*`, `/browse/article/{n}`, `/terms`, `/privacy`, `/grievance` stay indexable. `/pricing` remains indexable when that flag is on; it 404s while disabled.

Non-HTML private responses use one helper:

```python
apply_private_robots_headers(path, response)
```

Middleware applies it after the route. Rule: private path + non-HTML media type → `X-Robots-Tag: noindex, nofollow`. HTML, empty content-type, public paths, and redirects are left alone so directives do not conflict. Guest `/playground` → `/login` is a redirect and is not required to carry canonical metadata; the rendered login page is noindex.

---

## Sitemap

Layout is unchanged except intra-law chunking:

```text
/sitemap.xml
/sitemap-core.xml
/sitemap-laws.xml
/sitemap-laws-{slug}.xml          # small laws
/sitemap-laws-{slug}-{n}.xml      # when URL count > SITEMAP_URL_CHUNK_SIZE
```

Root index lists core + hub + every law chunk from manifest metadata. No NDPS/BNS/BNSS hardcoding. All `<loc>` values use `CANONICAL_ORIGIN` (`https://recall-the-c.in`), never the incoming Host. Sitemap `loc` equals the page `<link rel="canonical">` for hub, Act, section, and schedule. Private prefixes (`/playground`, `/dashboard`, `/calendar`, `/profile`, `/settings`, `/billing`, `/learn`, `/progress`, …) are absent from every generated document.

Protocol guards remain 50,000 entries and 50 MB. Entry-count chunking is the primary path (`SITEMAP_URL_CHUNK_SIZE`, default 50,000; tests monkeypatch to 2). A chunk that somehow exceeds the byte ceiling fails loudly rather than truncating. Unknown law/chunk → 404. Resolver matches registered slugs only; `../` and path separators are rejected. Adding a 701st law is registry + manifest regeneration, not a new route table.

Omitted sections stay in the per-law map when they have a live public reader page.

---

## Manifest

Builder remains [`scripts/build_law_sitemap_manifest.py`](../scripts/build_law_sitemap_manifest.py) (`SCHEMA_VERSION = 2`). FastAPI startup and sitemap requests never regenerate or validate it by hydrating Acts.

Each law entry:

```json
{
  "slug": "ndps",
  "source_version": "1",
  "runtime_identity": "ndps:1:ndps_act_final.json",
  "sources": [{"filename": "...", "sha256": "..."}],
  "sections": ["1", "27A", "..."],
  "schedules": ["psychotropic-substances"]
}
```

`last_modified` is omitted — there is no trustworthy build-time timestamp. Freshness tests fail if a `BARE_ACTS` key is missing, if `runtime_identity` disagrees with `runtime_cache_identity(spec)`, or if source SHA-256 digests are stale. Sections come from build-time `section_order`. Schedules come from `public_schedule_slugs` (table-backed only; BNSS deferred forms are not advertised). The Playground/learning/account URL space is not in this file.

---

## Performance

| Surface | Acts hydrated |
|---------|----------------|
| FastAPI startup | 0 |
| `GET /laws` | 0 |
| `GET /sitemap.xml` | 0 |
| `GET /sitemap-laws.xml` | 0 |
| `GET /sitemap-laws-ndps.xml` | 0 |

Manifest JSON reads are allowed. Runtime Bare Act JSON reads are not. Large-corpus scaling is index + per-law (or per-chunk) urlsets.

---

## Scope protection

* No M11 work (release checklist, legacy table removal, load/stress, backup/restore, monitoring, rollout).
* No Stage 2 scoring.
* No DB migration. Alembic head remains `20260927_0027`.
* Public law pages remain indexable.
* Private state is absent from sitemaps.

---

## Tests

Focused M10 module: [`tests/test_playground_m10.py`](../tests/test_playground_m10.py) — **26** tests (Alembic 0027 freeze, shared `seo.py` reuse, query canonicals, string section IDs, Playground HTML including learn/revision/source-review, private JSON `X-Robots-Tag`, public pages indexable, account/device/billing/admin/auth, sitemap index without private URLs).

Extended: [`tests/test_bare_act_seo.py`](../tests/test_bare_act_seo.py) (unique hub metadata, `?q=bail` / subject canonicals), [`tests/test_bare_act_sitemap.py`](../tests/test_bare_act_sitemap.py) (explicit `slug`/`source_version`, intra-law chunking with size 2, HTTP chunk roundtrip, builder freshness), plus existing private-noindex, sitemap, law-loading, and structured-data suites.

Focused group (SEO/canonical/robots/sitemap/manifest/law-loading/Bare Act public): **168 passed** before the hub-copy tweak; catalog/NDPS reader regressions then re-passed.

Full suite command:

```bash
python3 -m pytest -m "not integration" -q --tb=line
```

Result: **2331 passed**, 9 skipped, 1 deselected, **0 failed** (incoming baseline 2295 passed).

Alembic head after this batch: `20260927_0027`.

---

## Git

| SHA | What |
|-----|------|
| [`3cfd7fa`](https://github.com/sanjisworking-commits/recall_the_c/commit/3cfd7faeb639604ab5a6d85704f97bac5572b043) | Harden public/private SEO, X-Robots-Tag, manifest slug/source_version, intra-law chunking |
| [`91a7515`](https://github.com/sanjisworking-commits/recall_the_c/commit/91a75154d6543cc13e1eec343a74943fdac536e8) | Unique `/laws` copy without restoring catalog “Bare Acts” grouping |
| [`006d079`](https://github.com/sanjisworking-commits/recall_the_c/commit/006d07984a91ae23b20c32083b634143181fd6f3) | Score Milestone 10 as DONE at Stage 1 93.0 |

Implementation SHA: `3cfd7faeb639604ab5a6d85704f97bac5572b043`. Tracker SHA: `006d07984a91ae23b20c32083b634143181fd6f3`.

PR [#188](https://github.com/sanjisworking-commits/recall_the_c/pull/188) is open on this branch.

---

## Out of scope

- Not M11: production hardening, legacy table removal, load/stress, backup/restore, monitoring, rollout.
- Not Stage 2: SEO performance is not an optimize-stage tick.
- Not a second `playground_seo.py` or hardcoded NDPS/BNS metadata.
- Not a nested sitemap index under a child path.
- Not invented `last_modified` timestamps.
