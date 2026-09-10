# SEO Indexation Runbook — Bare Act discovery

Operational runbook for getting the public Bare Act corpus crawled and indexed,
and for monitoring indexation after deploy. This is **operational SEO only**:

- No application SEO code changes are driven from this doc.
- No new schema.org types, no title/description rewrites, no sitemap redesign.
- No `lastmod` in sitemaps (intentional — see [Why no lastmod](#why-no-lastmod)).
- No Search Console API / OAuth integration. All Google Search Console (GSC)
  steps below are **manual**, via the GSC web UI.

---

## 1. Deployment of record

| Field | Value |
| --- | --- |
| Production origin | `https://recall-the-c.in` |
| Deploy SHA | `a5891c46bcf8ae5dd53f18612e0e0ef78d1e7cdf` (`a5891c4`) |
| Deployed | 2026-09-10, live ~17:10 UTC (verified) |
| Merged PRs | #197 (Bare Act BreadcrumbList JSON-LD), #198 (sitemap packaging fix) |
| Host / build | Railway, `railpack.json` → `uvicorn constitution_memorizer.web.asgi:app`; auto-deploy on push to `main` |
| Verified build | `main` push `959f9b6..a5891c4`; production reflected the new build after ~7 min |

### Incident fixed in this deploy (context)

Before `a5891c4`, the deployed wheel omitted the sitemap data files, so
`/sitemap.xml`, `/sitemap-core.xml`, and every `/sitemap-laws-{slug}.xml`
returned **HTTP 500** in production (only the in-memory `/sitemap-laws.xml` hub
survived). Root cause: `law_sitemap_manifest.json` lived outside the package and
`sitemap-core.xml` was not declared `package-data`, so `pip install .` dropped
both. Tests ran from source (where repo paths resolve), so CI never saw it.
PR #198 moved the manifest into the package and added both files to
`package-data`; a regression test now asserts both ship inside the wheel. If
sitemaps 500 again after a future deploy, re-check that guard first
(`tests/test_bare_act_sitemap.py::test_sitemap_data_files_ship_inside_the_package`).

---

## 2. Sitemap topology and expected counts

Sitemap index: **`https://recall-the-c.in/sitemap.xml`** (submit this one to GSC).

| Sitemap URL | Type | Expected URL count | Composition |
| --- | --- | --- | --- |
| `/sitemap.xml` | index | 5 child sitemaps | core + laws hub + one per registered Act |
| `/sitemap-core.xml` | urlset | **500** | Constitution + marketing (byte-preserved) |
| `/sitemap-laws.xml` | urlset | **1** | `/laws` hub page |
| `/sitemap-laws-bns.xml` | urlset | **359** | 1 law + 358 sections + 0 schedules |
| `/sitemap-laws-bnss.xml` | urlset | **533** | 1 law + 531 sections + 1 schedule (`first-schedule`) |
| `/sitemap-laws-ndps.xml` | urlset | **131** | 1 law + 129 sections + 1 schedule (`psychotropic-substances`) |

**Total discoverable URLs via the index: 1,524** (500 + 1 + 359 + 533 + 131).

Counts are protocol-bounded (each document is guarded at 50,000 entries /
50 MB). When a new Act is registered or a runtime file changes, regenerate the
manifest (`python -m scripts.build_law_sitemap_manifest`) and update this table
from a fresh production audit — do **not** hand-edit counts.

### Invariants verified at this deploy (re-check after any deploy)

- Every sitemap URL returns **HTTP 200**.
- Every sitemap `<loc>` is an **HTTPS** production URL and is **byte-identical**
  to that page's `<link rel="canonical">` (0 mismatches sampled across bns/bnss/ndps).
- `robots.txt` returns 200, allows search crawlers (`User-agent: * … Allow: /`),
  declares `Sitemap: https://recall-the-c.in/sitemap.xml`, and does **not**
  `Disallow: /laws`.
- Sitemap routes are public (served to cookieless crawlers; no login redirect).
- `BreadcrumbList` JSON-LD is present on public law/section/schedule pages.
- BNSS `second-schedule` stays unsupported (**404**, no BreadcrumbList).
- No private route emits Bare Act structured data (`/progress`, `/dashboard`,
  etc. carry no `BreadcrumbList`).

### Quick re-audit

Re-run this self-contained check any time (no external script required):

```bash
for p in /robots.txt /sitemap.xml /sitemap-core.xml /sitemap-laws.xml \
         /sitemap-laws-bns.xml /sitemap-laws-bnss.xml /sitemap-laws-ndps.xml \
         /laws /laws/ndps /laws/ndps/section/27A /laws/bnss/schedule/first-schedule; do
  printf '%-45s %s\n' "$p" "$(curl -s -o /dev/null -w '%{http_code}' https://recall-the-c.in$p)"
done
```

For a deeper check (sitemap `loc` == page canonical, breadcrumb presence,
private-route isolation), also confirm the invariants listed above by spot
inspecting a few `/laws/...` pages and one child sitemap.

---

## 3. Representative URL Inspection sample (manual, GSC → URL Inspection)

Inspect this spread after submitting the sitemap. It covers every URL class and
the known edge cases, so "these are Indexed" is strong evidence the whole corpus
is healthy.

| URL | Why it's in the sample |
| --- | --- |
| `https://recall-the-c.in/laws` | Hub page (crawl entry point) |
| `https://recall-the-c.in/laws/ndps` | Law landing (breadcrumb depth 2) |
| `https://recall-the-c.in/laws/ndps/section/27A` | Amended/lettered section id |
| `https://recall-the-c.in/laws/ndps/section/65` | **Omitted** section (indexable, states omission) |
| `https://recall-the-c.in/laws/bns/section/358` | Last section of a large Act |
| `https://recall-the-c.in/laws/bnss/section/531` | Largest Act, last section |
| `https://recall-the-c.in/laws/bnss/schedule/first-schedule` | Supported (table) schedule |
| `https://recall-the-c.in/laws/ndps/schedule/psychotropic-substances` | Supported schedule |
| `https://recall-the-c.in/browse/article/21` | Constitution page (from `sitemap-core.xml`) |

For each, in URL Inspection confirm: **URL is on Google** (or "Crawled/Discovered"
early on), **Coverage**: no `noindex`/`canonical` conflicts, **User-declared
canonical == Google-selected canonical == the HTTPS self URL**, and
**Enhancements → Breadcrumbs**: valid (for the `/laws/...` pages).

Negative control: `https://recall-the-c.in/laws/bnss/schedule/second-schedule`
should report as **not indexable / 404** — that is expected, not a defect.

---

## 4. Search Console baseline (record at D0)

Capture these fields once, immediately after submission, so later reviews are
deltas against a fixed baseline. (Manual UI reads — no API.)

- **Property**: which GSC property covers `https://recall-the-c.in` (domain vs
  URL-prefix); note the verification method.
- **Sitemaps report** (per submitted sitemap = the index and, if GSC expands
  children, each child): Status, Type, **Discovered URLs**, Last read date.
  Baseline expectation: index accepted; ~1,524 URLs discovered once children are read.
- **Pages (Indexing) report**: total **Indexed**, total **Not indexed**, and the
  breakdown of Not-indexed reasons (e.g. *Crawled – currently not indexed*,
  *Discovered – currently not indexed*, *Duplicate without user-selected canonical*).
- **Enhancements → Breadcrumbs**: valid items, warnings, errors (baseline: errors = 0).
- **Performance** (Search results), last 7 days, filtered to `Page contains /laws`:
  Clicks, Impressions, Avg. CTR, Avg. position (baseline is likely ~0 impressions).
- **Crawl stats** (Settings → Crawl stats): total crawl requests, avg response
  time, any host-status errors.

Record the D0 numbers in a tracking note (or extend this file) with the date.

---

## 5. Review cadence (D0 → D28)

Day 0 is the deploy/submission date (2026-09-10). All steps are manual GSC reads
plus a quick production re-audit; **do not** change application code as part of a
review — file an issue and use the remediation rules in §6.

| Day | Focus | Actions |
| --- | --- | --- |
| **D0** | Submit + baseline | Submit `/sitemap.xml` in GSC. Run the production re-audit (§2). Record the baseline (§4). URL-Inspect + **Request Indexing** for the hub and 2–3 representative law pages. |
| **D3** | Discovery | Sitemaps report should show the index **read** and children **discovered** (~1,524 URLs). Confirm no *Couldn't fetch* / parse errors. Spot-check 2 URL Inspections move to *Crawled* or *Indexed*. |
| **D7** | Early indexation | Pages report: Indexed count rising; capture the top Not-indexed reasons. Breadcrumbs enhancement: valid items appearing, errors still 0. Re-audit production (nothing regressed to 500 / canonical drift). |
| **D14** | Coverage depth | Compare Indexed vs 1,524. Investigate any *Discovered – currently not indexed* clusters (see §6). First Performance signal for `/laws` (impressions > 0). |
| **D28** | Steady state | Assess what proportion of the submitted corpus Google has indexed and whether any persistent exclusion pattern requires investigation. Do not treat a fixed indexation percentage as an acceptance threshold. Breadcrumb rich-result eligibility visible. Decide whether any remediation (§6) is warranted; otherwise close the indexation watch. |

At every checkpoint also glance at Crawl stats host status — a spike in 5xx is
the earliest signal of a packaging/deploy regression like the one PR #198 fixed.

---

## 6. Remediation decision rules

Act only on evidence; each rule is **trigger → diagnosis → action**. Prefer the
smallest fix and keep it out of application SEO logic unless a real code bug is
proven.

1. **Sitemap "Couldn't fetch" or any sitemap URL != 200**
   → Re-audit (§2). If 500s: this is the PR #198 class of bug — verify the wheel
   ships `web/law_sitemap_manifest.json` and `web/sitemap-core.xml`
   (`test_sitemap_data_files_ship_inside_the_package`), redeploy. If 404 on a
   child: a registered Act is missing from the manifest — regenerate the manifest
   and redeploy. **Do not** hand-edit sitemap XML.

2. **`Discovered – currently not indexed` for a large share of `/laws/...`**
   → Usually crawl-budget/quality, not a bug. Confirm the pages are 200, unique
   canonical, and internally linked (hub → law → section). Action: leave to
   Google over more days; optionally Request Indexing for a representative subset.
   Escalate only if it persists past D28 for the majority.

3. **`Duplicate without user-selected canonical` / Google picked a different canonical**
   → Compare user-declared canonical (page `<link rel="canonical">`) with the
   sitemap `<loc>` and Google-selected canonical in URL Inspection. If they
   already match (as verified at deploy), it's Google clustering near-identical
   thin pages — no code change. If they diverge, that's a real bug: capture the
   three URLs and file an issue against the SEO engine (do not patch ad hoc here).

4. **`Excluded by 'noindex'` on a page that should be public**
   → A public Bare Act page must not carry `noindex`. Confirm in the page source;
   if present, it's a template/route regression — file an issue with the URL.
   (Expected `noindex` pages: `/login` and other auth surfaces only.)

5. **Breadcrumbs enhancement shows errors**
   → Inspect the failing URL's rendered `application/ld+json`; confirm it parses
   and `item` == canonical == sitemap loc. If malformed, it's a code regression in
   the breadcrumb helper — file an issue (do not edit JSON in templates).

6. **A private/personalized route appears in Coverage/Performance as indexed**
   → Confirm it carries no Bare Act structured data (it must not) and decide on
   `robots`/`noindex` posture. **Out of scope for this runbook** — file a separate
   ticket; do not expand the current SEO work to change auth-route indexability.

7. **Host status 5xx spike in Crawl stats after a deploy**
   → Treat as a deploy regression. Re-audit (§2), check Railway build logs, and if
   sitemaps are down, apply rule 1.

Escalation for anything requiring an application code change: open a scoped PR
(one logical fix), keep it off `main` until reviewed, and re-run the production
smoke audit (§2) after it deploys.

---

## Why no lastmod

The sitemaps deliberately omit `<lastmod>`. Bare Act statutory text is stable and
we have **no trustworthy modification timestamp** to publish (deriving one from
build time, Git commit time, or the manifest generation date would be fabricated
and can *hurt* crawl scheduling). If a genuine, authoritative amendment date
becomes available per Act in the future, revisit `lastmod` then — do not add a
synthetic one now.

## Out of scope (do not do as part of indexation ops)

- New schema.org types (e.g. `Legislation`) — deferred until authoritative
  enactment/commencement dates, publisher, jurisdiction, and status exist.
- Title/description rewrites, sitemap redesign, chapter URLs in the sitemap.
- Search Console API / OAuth automation.
