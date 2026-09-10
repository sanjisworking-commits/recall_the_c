# Playground (this branch)

**Guest = explore. Account = complete Constitution. Subscription = Playground. Tier = monthly roster capacity only** (plus 10 / pro 30 / max unlimited distinct laws **active this Playground month**). Overlay item/selection/progress is **persistent learning**, not that quota. **Playground also requires a registered device** (`PLAYGROUND_DEVICE_LIMIT = 2`, same for every tier). Constitution Learn and law reading never use this gate.

RecallC Playground is the paid learning overlay on verbatim Bare Act JSON. Tiers do not change modes, ladders, quality, or device cap. Same-month remove + re-add does not consume an extra roster slot; next month’s laws are carry-forward candidates (Keep uses a new-period slot). **Neither payment, the roster, nor device revocation may delete progress.**

| Document | Status |
|----------|--------|
| [PLAYGROUND_DELIVERY_TRACKER.md](PLAYGROUND_DELIVERY_TRACKER.md) | **Programme scoreboard.** Stage 1 = **5 / 100** (build). Stage 2 optimize is `NOT STARTED` until Stage 1 is `DONE` (100/100). Cloze/overlay proof does **not** inflate either stage. |
| [PLAYGROUND_TWO_LAW_AUDIT.md](PLAYGROUND_TWO_LAW_AUDIT.md) | Overlay design. Cloze = architectural proof, not the finished mode set. NDPS/BNS = **historical validation corpus**, not a production allowlist. Item/selection/progress = persistent learning, not monthly quota and not the device registry. |
| [PAYMENT_ENTITLEMENT_AUDIT.md](PAYMENT_ENTITLEMENT_AUDIT.md) | User-type + **device registry** + **monthly roster** (`Asia/Kolkata` period clock). **Not implemented.** See §21 for prices / Razorpay states / refunds / replacement-churn integers. |
| [law-loading.md](law-loading.md) | Lazy hydration contract Playground inherits. Sitemap inventory is a **build-time manifest**, never request-time Act hydration. |

**On this branch (proof):** Add to Playground, section selection, Cloze, revision rows, guest → sign-in. Routes live in `app.py` as `/playground/{law_id}` — **proof architecture, not production routing.** Locator allowlist is still `{ndps, bns}`. No subscription gate. No monthly roster. No device cookie. Cloze currently starts Day 1 (prototype). Request-time whole-file hashing in `source.py` is a proof artifact to remove.

**Finished train** is scored in [PLAYGROUND_DELIVERY_TRACKER.md](PLAYGROUND_DELIVERY_TRACKER.md): **Stage 1** is the 100-point build (milestones 0–11); **Stage 2** is an unweighted optimize checklist that starts only after Stage 1 is `DONE` (100/100) and proven. Cloze, the NDPS/BNS overlay, and proof revision rows do **not** make Stage 1 look finished and do **not** tick Stage 2. Next implementation batches follow Stage 1 on that tracker, not a second product model.

```text
This contract
    ↓
Generic eligibility helper + locator removal of two-law allowlist
    ↓
Dedicated Playground APIRouter + final URLs
    ↓
Runtime identity/hash cleanup (BareActSpec, no request-time read_bytes)
    ↓
Roster + batched dashboard repository
    ↓
noindex / X-Robots-Tag enforcement
    ↓
learning/workspace routes (all modes)
    ↓
sitemap manifest work separately (law-loading, not Playground)
```

Also still in-scope: user-type resolver, device registry, Razorpay lifecycle, admin override. Open §21 cells block charging live; they do not restore article entitlements or lifetime unlocks.

---

## SEO, routing and performance contract

Product model is unchanged. These rules keep Playground survivable at 30 active laws per user and hundreds of Bare Acts.

### Public SEO vs private Playground

The public Bare Act reader is the search-indexable law surface.

**Indexable:**

- `/laws`
- `/laws/{law_id}` for full Bare Acts
- `/laws/{law_id}/section/{number}`
- public schedule pages

`/laws` has a unique title, unique description, and canonical `https://recall-the-c.in/laws`. Filter/search variants (`/laws?q=bail`, `/laws?subject=criminal`) canonicalize to `/laws` unless a future subject page is deliberately created as an indexable landing page. Bare Act landing, section, and schedule pages get their own canonical/title/description.

Reuse [`web/seo.py`](../src/constitution_memorizer/web/seo.py) (`build_provision_seo` and related helpers). That module is law-generic and does no corpus I/O. **Do not** create a Playground SEO engine.

**Private / personalized — never in any sitemap:**

- `/playground*`
- Playground Learn / progress / revision
- monthly roster management
- device management (`/profile/security/devices`)
- account / subscription lifecycle surfaces

HTML private pages:

```html
<meta name="robots" content="noindex, nofollow">
```

Any future **non-HTML** private resource (export, download, JSON, PDF) must send `X-Robots-Tag` rather than relying on HTML metadata.

### Playground eligibility

NDPS and BNS were the proof corpus, not a permanent production allowlist.

A production law is Playground-eligible only when it is a registered **full Bare Act**:

```text
catalogue primary_content == "full_act"
AND
BareActSpec exists
```

Mapped / key-provision entries are **not** eligible until the product deliberately supports that shape.

Production Playground eligibility must ultimately be exposed through **one lightweight shared helper**, conceptually:

```python
is_playground_eligible_law(law_id)
list_playground_eligible_laws()
```

Routes, roster, locators, entitlement, and UI must **not** independently reconstruct eligibility rules. That is how `{ndps, bns}` would reappear in five forms.

Canonical locator remains `{law_id}:section:{number}`. Parse a safe generic law slug, then validate through the helper against the lightweight full-Bare-Act registry. Do not hardcode slugs in routing or locators.

### Route architecture

Do not continue adding Playground HTTP handlers directly to [`web/app.py`](../src/constitution_memorizer/web/app.py).

Create a dedicated FastAPI `APIRouter(prefix="/playground")` (for example `playground/routes.py`) and include it additively from the app factory. **Do not** refactor Constitution routing while doing this.

**`/playground/{law_id}` is proof architecture, not production routing.** Prefer `/playground/laws/{law_id}` so static Playground paths never compete with a law slug.

Locked production namespace:

| Method | Path | Role |
|--------|------|------|
| GET | `/playground` | Personal Playground home (zero Bare Act hydration) |
| GET | `/playground/roster` | Current month’s roster (zero hydration) |
| GET/POST | `/playground/roster/next` | Next-month Keep/Remove |
| GET | `/playground/laws/{law_id}` | Law learning workspace |
| GET/POST | `/playground/laws/{law_id}/sections` | Selection |
| GET | `/playground/laws/{law_id}/sections/{number}/learn/{mode}` | Learn mode |
| — | same law/section tree | completion / revision actions |

Example: `/playground/laws/ndps/sections/8/learn/cloze`.

Device management belongs under account/profile security (`/profile/security/devices`), not under a Playground law route. Payment/subscription routes remain in the billing domain.

### Authorization dependencies

Centralize server-side guards rather than duplicating them across Learn-mode handlers:

```text
authenticated
    → Playground subscription
    → registered device
    → law active in current monthly roster
```

Learning modes consume the resulting authorized Playground context. They do not contain provider, payment, or device logic themselves.

### Law-loading contract

Playground inherits [law-loading.md](law-loading.md):

1. `/playground` and `/playground/roster` must **not** hydrate Bare Act JSON.
2. Use catalogue/registry metadata for Playground cards (title, year, short title, scope).
3. Hydrate only the Act whose workspace/section has been opened.
4. Reuse the process-local `BareAct` cache.
5. Never open/stat/hash every runtime law file from a request path.
6. Runtime law identity comes from `BareActSpec.source_version` / `source_hash`.
7. Exact section hashing occurs only after the relevant Act is loaded.
8. Do not introduce cross-law search by hydrating all Acts.

A content hash required for runtime identity must be computed during ingestion/build and stored in lightweight registry metadata, **not** recomputed by `read_bytes()` on a request. The proof `law_file_hash` in `playground/source.py` must not ship as production design.

Two-level amendment check: if law `source_version` / `source_hash` is unchanged, skip section revalidation. If it changed, hydrate **that** law and compare affected section hashes. Most Playground page loads must never inspect statutory bodies.

### Playground dashboard query contract

`GET /playground` must not perform per-law selection/progress queries.

Provide a batched/aggregate repository read such as `list_playground_summaries(user_id, period)` returning card-level state:

- `law_id`
- `active_this_period`
- selected / learning / Learned / due / mastered counts
- last activity
- lightweight source-update status

Do not resolve every section or recompute every live section hash merely to render Playground home.

Authenticated page chrome reuses the existing request-scoped bootstrap ([`request_context.py`](../src/constitution_memorizer/web/request_context.py)). Do not independently re-query theme, due count, onboarding, or identity in every Playground route.

### Mutation efficiency

Entire-Act selection and monthly roster rollover must use batched writes inside a single transaction (`executemany` / VALUES / COPY-equivalent). Avoid one query cycle per Section. Monthly capacity check + roster consumption remains atomic.

### Monthly-period clock

One authoritative timezone for Playground month boundaries: configured RecallC timezone **`Asia/Kolkata`**. Not UTC. Not per-account `user_timezone` unless account-local timezone is deliberately introduced later. Billing-period timezone and Playground-period timezone are independent (see [PAYMENT_ENTITLEMENT_AUDIT.md](PAYMENT_ENTITLEMENT_AUDIT.md) §14).

### Performance / SEO tests (document now; pytest in later batches)

- `GET /playground` performs **zero** Bare Act hydrations.
- `GET /playground/roster` performs **zero** Bare Act hydrations.
- Opening one Playground law hydrates **at most** that law.
- Opening one law Section/Learn mode never hydrates another Act.
- Dashboard retrieval is batched rather than N+1 by active-law count.
- Request-time law identity never reads/hashes every runtime JSON.
- Root sitemap/index and sitemap discovery never hydrate the Bare Act corpus.
- Personalized Playground URLs are not indexable (HTML `noindex,nofollow`; non-HTML `X-Robots-Tag`) and are absent from sitemap.
