# RecallC Playground — Delivery Tracker

**Scoreboard, not an audit.** Product rules live in [PLAYGROUND.md](PLAYGROUND.md), [PAYMENT_ENTITLEMENT_AUDIT.md](PAYMENT_ENTITLEMENT_AUDIT.md), [PLAYGROUND_TWO_LAW_AUDIT.md](PLAYGROUND_TWO_LAW_AUDIT.md), and [law-loading.md](law-loading.md).

**Snapshot:** architecture/product definition is **locked in docs**. **Stage 1** (build) is **39.1 / 100**. Production implementation is **early**. The NDPS/BNS overlay + Cloze + proof revision rows **do not** count as milestones 6–8. Milestone 1 is `DONE`. Milestone 2 is **`DONE` — 37/37**. Milestone 3 is **`DONE` — 15/15** (M3-A Constitution inversion + M3-B Playground commercial gate). Milestone 4 is **`IN PROGRESS` — 19/25** (M4-A core two-device authorization). Owner device-management UI remains M4-B. Replacement-churn rate policy remains `BLOCKED`. Monthly roster enforcement remains Milestone 5. **Do not tick Stage 2 from Cloze or from `main`’s sitemap PRs.** This branch includes main’s Bare Act SEO and generated sitemap index; that is Milestone 0 coexistence, not Milestone 10 (`noindex`) and not Stage 2.

| | |
|--|--|
| **Stage 1 (build)** | **39.1 / 100** |
| Milestone 0 | `DONE` — 10/10 items × 5 = **5** |
| Milestone 1 | `DONE` — 18/18 items × 8 = **8** |
| Milestone 2 | `DONE` — 37/37 × 13 = **13** |
| Milestone 3 | `DONE` — 15/15 × 7 = **7** |
| Milestone 4 | `IN PROGRESS` — 19/25 × 8 = **6.08** (M4-A). Device-management UI is M4-B. Replacement-churn integers remain `BLOCKED`. |
| Milestones 5–11 | `NOT STARTED`; remaining §21 `BLOCKED` cells are device-churn integers / support channel only |
| **Stage 2 (optimize)** | **`NOT STARTED` — start gate: Stage 1 = `DONE` (100/100)** |

Do not read Cloze on this branch as ~20% complete. Payments, roster, devices, six Learn modes, and Learned → revision are the actual Stage 1 product weight. Stage 2 is **outside** the 100.

---

## Tracking rule

Playground **Stage 1** completion is measured out of **100 points**. Stage 2 is unweighted and is not part of that 100.

A milestone counts only when:

1. implementation is complete,
2. migrations are complete where required,
3. tests pass,
4. failure/edge states are handled,
5. existing Constitution behaviour remains unchanged,
6. the feature works on both web and the relevant backend interfaces,
7. documentation is updated.

Prototype code does **not** automatically count as production-complete.

Within each milestone:

```text
milestone completion = completed acceptance items / total acceptance items
overall Playground completion = Σ(milestone completion × milestone weight)
```

Status labels — use **only**:

```text
NOT STARTED | IN PROGRESS | BLOCKED | IN REVIEW | DONE
```

`DONE` means acceptance criteria and tests have passed. Do not use “mostly done.”

**§21 remaining `BLOCKED` (do not invent):** `DEVICE_REPLACEMENT_WINDOW_DAYS`, `DEVICE_REPLACEMENT_LIMIT`, support contact channel for device-churn lockout. See [PAYMENT_ENTITLEMENT_AUDIT.md](PAYMENT_ENTITLEMENT_AUDIT.md) §21.

**§21 locked (do not reopen, do not invent alternatives):** public names Plus / Pro / Max; INR prices ₹199 / ₹399 / ₹1,199 per month; GST-inclusive display; MVP monthly-only (no annual SKUs); provider-status access matrix; `pending` as payment-retry grace with **no** grace-day integer; refund access; dispute/chargeback access. Internal codes `plus` / `pro` / `max` remain locked. Milestone 2 implementation against those locked cells is `DONE` — 37/37.

`BLOCKED` is **only** for unresolved product/provider decisions (remaining §21 device-churn cells). Stage 2 is **sequenced**, not blocked. Locked commercial §21 cells remain product truth for Milestone 3 entitlement composition.

---

## Programme stages

```text
PLAYGROUND PROGRAMME

STAGE 1 — BUILD
100-point completion score
Milestones 0–11
        ↓
100/100 + production proof
        ↓
STAGE 2 — OPTIMIZE
Unweighted checklist
Measured optimization only
        ↓
DB tuning
routing/backend profiling
law-loading scale
SEO at scale
performance
resilience
abuse hardening
observability
ops tooling
UX optimization
scale testing
cleanup
```

**Stage 1** is milestones 0–11 below. That score **ends at 100**. Stage 2 stays completely outside it.

**Stage 2 status:** `NOT STARTED` — start gate: Stage 1 = `DONE` (100/100). Do not start Stage 2 during Stage 1. Do not reopen prices, GST, roster math, device cap, URL shape, or Constitution independence in Stage 2.

**Overlap:** Stage 1 **implements** first-time correctness (zero-hydration home/roster, batched dashboard, atomic consume, webhook HMAC/idempotency, `noindex` / `X-Robots-Tag`, first-pass admin diagnostics, concurrency tests, rollout/rollback). Stage 2 **profiles / measures / tunes / automates / scales / retires** after measured production behaviour. Do not re-implement Stage 1 contracts under Stage 2 headings.

**Do not tick Stage 2 from Cloze or from `main`’s sitemap PRs.**

This file is the **only** scoreboard for “how far through the overall Playground programme are we?” Do not duplicate Stage 2 into a new audit.

---

# 0. Architecture lock + branch baseline — 5 points

**Status: `DONE`** (10/10 × 5 = 5)

### Scope

* [x] Playground product philosophy locked
* [x] Verbatim law JSON remains canonical
* [x] Constitution model stays independent
* [x] User-type entitlement locked
* [x] Device policy locked
* [x] Monthly roster policy locked
* [x] SEO/routing/loading contracts documented
* [x] Rebase `cursor/playground-220d` onto **latest** `main`
* [x] Resolve law-loader / BNSS / SEO / sitemap integration with current `main`
* [x] Full baseline test suite green after that rebase

Rebased onto `main` at BNSS + lazy loading + Bare Act SEO wiring + generated sitemap index (PRs #192 / #196). BNSS is Playground-eligible through `is_playground_eligible_law()`, not a third hardcoded slug.

### Done when

```text
Playground branch is based on current main
+
all planning documents reflect current repository reality
+
existing application tests pass
```

**Weight: 5**

---

# 1. Playground backend foundation — 8 points

**Status: `DONE`** (18/18 × 8 = 8)

M1-A (eligibility + router + final URLs) and M1-B (registry identity, zero-hydration dashboard/summary path, batched writes) are closed. Proof Cloze still does **not** tick milestones 6–8. There is no `/playground/roster` HTTP page yet; that route belongs to Milestone 5.

## Eligibility

* [x] Add one authoritative `is_playground_eligible_law()`
* [x] Add `list_playground_eligible_laws()`
* [x] Eligibility = full Bare Act + valid `BareActSpec`
* [x] Remove production NDPS/BNS allowlists
* [x] Locator accepts eligible law slugs generically
* [x] Mapped/key-provision-only laws remain ineligible

Routes, roster, locators, entitlement, and UI must consume **that same helper**. Do not reconstruct eligibility in five modules.

## Routing

* [x] Create dedicated Playground `APIRouter`
* [x] Remove Playground HTTP handlers from `app.py`
* [x] Lock final URLs:

```text
/playground
/playground/roster
/playground/roster/next
/playground/laws/{law_id}
/playground/laws/{law_id}/sections
/playground/laws/{law_id}/sections/{number}/learn/{mode}
```

Proof `/playground/{law_id}` is retired (404). `/playground/roster` remains a locked URL for Milestone 5; M1 does not implement that HTTP page.

## Law-loading compatibility

* [x] Remove request-time whole-file hashing
* [x] Use registry `source_version` / `source_hash`
* [x] `/playground` hydrates zero Acts
* [x] Playground dashboard / shared roster-summary data path hydrates zero Acts
* [x] one law workspace hydrates only that Act
* [x] no cross-law corpus load

## Data access

* [x] Batched Playground dashboard query (`list_playground_summaries`)
* [x] No N+1 selection/progress queries across 10/30 laws
* [x] Entire-Act section selection uses batched DB writes

### Done when

Playground has a scalable backend shell independent of the two-law proof.

**Weight: 8**

---

# 2. Payment & subscription foundation — 13 points

**Status: `DONE` — 37/37** (M2-A catalogue + persistence, M2-B create/checkout/cancel/upgrade/downgrade, M2-C webhooks/renewal/auto-renew, and M2-D failure/terminal lifecycle + refunds/disputes + resubscribe + legacy classification). Earned **13**. Do **not** tick Milestone 3 entitlement inversion, Playground route gates, devices, or roster.

## Commercial model

* [x] Final public tier names — **locked §21** (`Plus` / `Pro` / `Max`)
* [x] Internal tier codes remain stable (`plus` / `pro` / `max` — **locked**)
* [x] Final prices — **locked §21** (Plus ₹199 / Pro ₹399 / Max ₹1,199 per month)
* [x] GST display treatment — **locked §21** (displayed prices GST-inclusive)
* [x] Monthly billing product configuration — **locked §21** (MVP monthly only)
* [x] Annual billing configuration — **not in MVP** (locked: do not offer annual; do not invent annual prices; future annual still = monthly Playground periods)

## Subscription persistence

* [x] `user_subscription` or final equivalent
* [x] Provider subscription ID
* [x] status
* [x] tier
* [x] billing period start/end
* [x] cancel-at-period-end
* [x] provider metadata

## Razorpay subscription lifecycle

* [x] Create subscription
* [x] Checkout
* [x] Renewal
* [x] Auto-renew
* [x] Cancel
* [x] Upgrade
* [x] Downgrade
* [x] Expiry
* [x] Failed payment
* [x] Payment-retry (`pending`) — **policy locked §21** (no grace-day integer; current-roster yes / new consumption no)
* [x] Paused/halted — **policy locked §21** (`halted` locks Playground learning)
* [x] Resubscribe
* [x] Refund handling — access outcome **locked §21**
* [x] Dispute/chargeback handling — **locked §21**

## Webhooks

* [x] Raw-body signature verification
* [x] event-ID idempotency
* [x] duplicate delivery safe
* [x] out-of-order delivery safe
* [x] provider reconciliation/fetch path
* [x] secret rotation strategy
* [x] webhook tests

## Legacy

* [x] Existing N-day buyers recognized as `legacy`
* [x] No silent Plus/Pro/Max remapping
* [x] Paid entitlement preserved for already-paid period

### Done when

A subscription can move through its full real lifecycle without manually editing the DB. M2-A shipped the server catalogue and `user_subscription` rows. M2-B shipped create, Checkout HMAC, cycle-end cancel, immediate upgrade, and cycle-end downgrade. M2-C shipped Razorpay subscription webhooks (raw-body HMAC, event-id idempotency, provider GET reconciliation) plus renewal/auto-renew billing-bound sync. M2-D shipped failed-payment/`pending`, paused/halted, expiry/terminalization, resubscribe (new provider subscription), refunds/disputes via `subscription_charge`, and read-only legacy N-day classification. These are commercial facts for Milestone 3; they do **not** authorize `/playground` or invert Constitution entitlement. Cursor must implement Milestone 3 against locked §21 commercial cells and must **not** invent remaining device-churn cells.

**Weight: 13**

---

# 3. User-type entitlement inversion — 7 points

**Status: `DONE` — 15/15** (M3-A Constitution inversion + EntitlementService; M3-B Playground commercial HTTP gate). M4-A overlays device fields onto that snapshot. Monthly roster enforcement remains Milestone 5. Pending existing-item behaviour is transitional until M5 can identify current-period roster membership; overlay items are **not** the current roster.

Implement one authoritative entitlement resolver.

## Guest

* [x] Constitution guest behaviour preserved
* [x] laws readable
* [x] Playground → Sign in

## Signed-in / no Playground subscription

* [x] ALL Constitution Articles available
* [x] ALL six Constitution Learn modes available
* [x] no 3-Article access restriction
* [x] no Type/Recite premium restriction
* [x] laws readable
* [x] Playground → Subscribe

## Subscriber

* [x] Full Constitution
* [x] Full Playground learning capability
* [x] tier affects only monthly law capacity

## Legacy logic retirement

Stop consulting for access:

* [x] article claim count
* [x] 3-Article slot cap
* [x] selective premium Learn modes

Do **NOT** delete historical tables yet.

## Central service

Entitlement snapshot includes:

```text
authenticated
subscription_status
tier
is_subscribed
admin_override
can_use_constitution_learn
constitution_access   # guest_explore | full
can_read_laws
can_open_playground
can_consume_new_playground_law
playground_law_limit
playground_block_reason
billing_period_start / billing_period_end
legacy_status
```

M3-A source of truth: [`src/constitution_memorizer/entitlements/`](../src/constitution_memorizer/entitlements/). [`web/entitlements.py`](../src/constitution_memorizer/web/entitlements.py) is the Constitution adapter. M3-B Playground HTTP uses [`playground/access.py`](../src/constitution_memorizer/playground/access.py) (`get_entitlement_snapshot` once per request). **M3 commercial gate is complete.** **M4-A device authorization is in progress (19/25):** [`devices/`](../src/constitution_memorizer/devices/) registers HMAC-hashed `rtc_device` installations (cap 2, all tiers) on first eligible Playground use. Owner device-management UI remains M4-B. Replacement-churn rate policy remains `BLOCKED`. Monthly roster enforcement remains Milestone 5. Pending users may open existing overlay/progress (transitional commercial bit until M5 `is_law_active_this_period`). Overlay items are not current roster. Roster snapshot fields are not fabricated. `playground_law_limit` is catalogue metadata only; 10/30/unlimited is not counted against overlay rows.

### Done when

All allow/deny decisions follow:

```text
Guest = explore
Account = complete Constitution
Subscription = Playground
```

**Weight: 7**

---

# 4. Device control — 8 points

**Status: `IN PROGRESS` — 19/25** (M4-A core two-device authorization). Owner device-management UI remains M4-B. Replacement-churn numeric policy: `BLOCKED` on §21 (`DEVICE_REPLACEMENT_WINDOW_DAYS`, `DEVICE_REPLACEMENT_LIMIT`, support contact channel).

Core two-device authorization shipped. `PLAYGROUND_DEVICE_LIMIT = 2` for Plus/Pro/Max. Cookie `rtc_device` survives logout. Server stores HMAC, not the raw token. Registration is atomic (SQLite `BEGIN IMMEDIATE` / Postgres `pg_advisory_xact_lock`). Minimal device-limit / revoked Playground copy exists so authorization is understandable; Profile → Security → Your devices is **not** ticked.

## Registry

* [x] `user_device`
* [x] `user_device_session`
* [x] 2-device configurable limit
* [x] same limit for all paid tiers
* [x] `rtc_device` separate from auth session
* [x] secure random installation token
* [x] server stores HMAC, not raw secret

## Behaviour

* [x] first device registers
* [x] second device registers
* [x] third device Playground-blocked
* [x] third device still gets full Constitution
* [x] logout does not consume new device slot
* [x] revoke device
* [x] replacement registration
* [x] revoked device immediately loses Playground authorization
* [x] progress unaffected
* [x] subscription expiry retains device registry
* [x] resubscription recognizes existing devices

## Device management

* [ ] Profile → Security → Devices
* [ ] current device identified
* [ ] remove device
* [ ] device-limit gate
* [ ] admin/support reset path
* [ ] replacement-churn policy implemented once §21 values locked — **`BLOCKED` until integers exist**

## Concurrency

* [x] simultaneous registrations cannot create 3 active devices

### Done when

Paid Playground works on no more than two registered installations while the rest of the account remains usable.

**Weight: 8**

---

# 5. Monthly Playground roster — 12 points

**Status: `NOT STARTED`**

This replaces cumulative/lifetime unlock accounting. Do **not** implement `user_playground_law_entitlement`.

## Period

* [ ] monthly Playground period
* [ ] timezone = `Asia/Kolkata`
* [ ] independent from provider billing interval
* [ ] annual subscribers still receive monthly Playground periods

## Capacity

```text
Plus = 10 active laws
Pro  = 30 active laws
Max  = unlimited
```

* [ ] capacity calculated account-wide
* [ ] both devices share same roster
* [ ] Constitution never counts
* [ ] capacity check atomic

## Period tables

* [ ] `user_playground_period`
* [ ] `user_playground_roster_item`
* [ ] unique user + period + law

## Same-month behaviour

* [ ] law activation consumes one slot
* [ ] same law cannot consume twice
* [ ] remove does not refund current-month slot
* [ ] remove + re-add same month costs no second slot
* [ ] full roster blocks only new laws
* [ ] existing roster laws remain fully usable

## Rollover

* [ ] previous laws become carry-forward candidates
* [ ] Keep consumes new-period slot
* [ ] Remove consumes no new-period slot
* [ ] user may add new laws into free spaces
* [ ] rollover can be prepared before month end
* [ ] annual subscribers behave identically

## Historical laws

* [ ] removed law retains all progress
* [ ] historical law can be added in later month
* [ ] later activation consumes one slot for that new month
* [ ] progress resumes exactly where left

### Done when

10/30 means exactly:

> the maximum number of laws that may participate in the user's Playground during that monthly period.

**Weight: 12**

---

# 6. Finished Playground UX — 8 points

**Status: `NOT STARTED`**

Proof Add/Select/Cloze screens do **not** count. Implement the final Claude Design against real entitlement state.

## Navigation

* [ ] Today
* [ ] Browse
* [ ] Playground
* [ ] Calendar
* [ ] Profile

## Playground home

* [ ] current monthly roster
* [ ] capacity display
* [ ] active laws
* [ ] progress summaries
* [ ] due state
* [ ] Learned/mastered state
* [ ] Manage action

## Law states

* [ ] Add to Playground
* [ ] In Playground
* [ ] Continue
* [ ] Previously learned / progress saved
* [ ] Add to this month
* [ ] Playground full this month

## User gates

* [ ] Guest → Sign in
* [ ] Signed-in free → Subscribe
* [ ] Device limit → Manage devices
* [ ] Expired → Playground visible but learning paused
* [ ] payment failure
* [ ] cancel-at-period-end
* [ ] upgrade
* [ ] downgrade scheduled
* [ ] paused
* [ ] resubscribed

## Rollover UX

* [ ] Your {month} Playground
* [ ] Keep
* [ ] Remove
* [ ] slots remaining
* [ ] Add new laws
* [ ] Manage next month

## Trust

* [ ] “Verbatim, always.”
* [ ] canonical statutory reveal
* [ ] no AI-generated statute presentation

### Done when

Every backend entitlement/roster/payment/device state has an intentional UI state.

**Weight: 8**

---

# 7. Complete Playground learning engine — 15 points

**Status: `NOT STARTED`**

Cloze on this branch is **architecture proof only**. It does **not** tick “Cloze productionized.”

The production Playground must support the complete RecallC learning philosophy independently from Constitution code.

## Learn modes

For every required Playground mode:

* [ ] mode design finalized
* [ ] source read from canonical law JSON
* [ ] no copied canonical statute
* [ ] progress persisted independently
* [ ] source hash/version recorded
* [ ] resume behaviour works
* [ ] completion recorded
* [ ] mobile/web UX complete
* [ ] tests

Complete:

* [ ] Cloze **productionized** (proof Cloze ≠ this box)
* [ ] Type
* [ ] Recite
* [ ] Write
* [ ] remaining RecallC mode 5
* [ ] remaining RecallC mode 6

Use the exact existing RecallC six-mode ideology/design rather than inventing a Constitution refactor.

## Law scope

* [ ] Entire Act selection
* [ ] section selection
* [ ] selected sections can enter any mode
* [ ] omitted/empty statutory nodes excluded correctly
* [ ] generic across every Playground-eligible Bare Act

### Done when

A user can take a selected law provision through the complete law-learning experience, not merely Cloze.

**Weight: 15**

---

# 8. Learned → Revision → Mastery — 8 points

**Status: `NOT STARTED`**

Cloze completion currently starting Day 1 revision on this branch is the **overlay prototype**. It does **not** count.

## Learning completion

* [ ] required-mode completion rule locked
* [ ] provision transitions to `Learned`
* [ ] clear Section Learned UI
* [ ] first revision begins only after Learned

## Revision ladder

Official ladder:

```text
1 → 3 → 7 → 15 → 30 → 60
```

* [ ] Day 1
* [ ] Day 3
* [ ] Day 7
* [ ] Day 15
* [ ] Day 30
* [ ] Day 60
* [ ] Mastered/completed state

## Persistence

* [ ] roster removal does not reset ladder
* [ ] subscription expiry does not reset ladder
* [ ] device revocation does not reset ladder
* [ ] reactivation resumes existing revision state
* [ ] overdue handling defined and tested

## Product integration

* [ ] Today integration
* [ ] Calendar/revision schedule integration
* [ ] progress summaries
* [ ] due-count aggregation

### Done when

The full RecallC memory cycle works for laws independently of the Constitution progress model.

**Weight: 8**

---

# 9. Source integrity & amendment handling — 5 points

**Status: `NOT STARTED`**

Proof `source_hash` on overlay rows is not production amendment UX.

## Source identity

* [ ] canonical locator
* [ ] law source version
* [ ] registry law source hash
* [ ] section source hash

## Amendment detection

* [ ] cheap law-level version/hash comparison
* [ ] no whole-corpus hash work on Playground home
* [ ] changed law triggers targeted section comparison
* [ ] unchanged sections preserve learning state
* [ ] affected sections flagged

## UX

* [ ] “Law updated” state
* [ ] number of affected learned provisions
* [ ] review affected provisions
* [ ] source provenance visible where appropriate

## Commercial behaviour

* [ ] amended version does not create a second law slot
* [ ] same `law_id` remains same roster law

### Done when

A statutory amendment can be detected without destroying or silently rewriting the user's memory history.

**Weight: 5**

---

# 10. SEO & public/private routing — 4 points

**Status: `NOT STARTED`**

Public Bare Act SEO and a generated sitemap index from **`main`** (PRs #192 / #196) are now on this branch. They still do **not** complete this milestone until Playground/account URLs are `noindex` / absent from sitemap, and query `/laws` canonicalization is verified. Do not re-invent `seo.py`. Do not tick Stage 2 from that adoption.

## Public law SEO

* [ ] `/laws` unique metadata
* [ ] full Act canonical
* [ ] section canonical
* [ ] schedule canonical
* [ ] query/filter variants canonicalized appropriately
* [ ] existing generic `seo.py` reused

## Private SEO

All personalized surfaces:

* [ ] `/playground*` → `noindex, nofollow`
* [ ] Learn/progress/revision → noindex
* [ ] roster → noindex
* [ ] account/device/payment private pages → noindex where applicable
* [ ] future non-HTML private routes use `X-Robots-Tag`

## Sitemap

* [ ] Playground absent
* [ ] root sitemap/index never hydrates Acts
* [ ] build-time law URL manifest
* [ ] manifest includes slug/source version/sections/schedules/optional last-modified
* [ ] scalable sitemap index/chunking

### Done when

Google can discover public statutory content efficiently while never indexing personal Playground state.

**Weight: 4**

---

# 11. Production hardening, legacy transition & release — 7 points

**Status: `NOT STARTED`**

## Security

* [ ] authorization guards centralized
* [ ] payment → device → roster → law access ordering
* [ ] no client-only paywalls
* [ ] CSRF/state-changing route protections
* [ ] concurrency tests
* [ ] user isolation tests
* [ ] admin override explicitly audited

## Performance

* [ ] no N+1 Playground home
* [ ] zero Act hydration on home/roster
* [ ] one Act maximum per law workspace request
* [ ] sitemap zero hydration
* [ ] batched selection writes
* [ ] batched rollover writes

## Legacy transition

* [ ] old article entitlement checks inactive
* [ ] legacy data retained safely
* [ ] old N-day purchase UI retired/frozen
* [ ] historical buyers handled correctly
* [ ] obsolete code identified
* [ ] delete only after proven unused

## Operational tooling

* [ ] subscription/admin diagnostics
* [ ] device reset
* [ ] roster diagnostics
* [ ] webhook diagnostics/reconciliation
* [ ] audit logging where appropriate

## Final regression

* [ ] Constitution Learn unchanged except deliberate entitlement removal
* [ ] existing Constitution progress intact
* [ ] public Bare Act reader intact
* [ ] admin intact
* [ ] Android/API auth intact
* [ ] full test suite green
* [ ] migrations tested PostgreSQL
* [ ] SQLite/dev parity where required
* [ ] production rollout checklist
* [ ] rollback path

### Done when

Playground + payment can safely replace the existing commercial entitlement model in production.

**Weight: 7**

---

# Total

| Milestone                         | Weight | Status now |
| --------------------------------- | -----: | ---------- |
| 0. Architecture + branch baseline |      5 | `DONE` (5 earned) |
| 1. Backend foundation             |      8 | `DONE` (8 earned; 18/18) |
| 2. Payment/subscriptions          |     13 | `DONE` — 37/37 × 13 = 13 |
| 3. User-type entitlement          |      7 | `DONE` — 15/15 × 7 = 7 |
| 4. Device control                 |      8 | `IN PROGRESS` — 19/25 × 8 = 6.08 |
| 5. Monthly roster                 |     12 | `NOT STARTED` |
| 6. Finished UX                    |      8 | `NOT STARTED` |
| 7. Complete Learn engine          |     15 | `NOT STARTED` |
| 8. Learned/revision/mastery       |      8 | `NOT STARTED` |
| 9. Amendments/source integrity    |      5 | `NOT STARTED` |
| 10. SEO/routing discoverability   |      4 | `NOT STARTED` |
| 11. Production hardening/release  |      7 | `NOT STARTED` |
| **TOTAL (Stage 1)**               |  **100** | **39.1 / 100** |
| Stage 2 — Optimize                |    — | `NOT STARTED` — start gate: Stage 1 = `DONE` (100/100) |

---

# PR / batch rule

Each substantive implementation batch should map to one or more tracker milestones.

Recommended order:

```text
Batch 0   Rebase onto latest main + contracts — DONE (this milestone 0)
Batch 1A  Eligibility + APIRouter + final `/playground/laws/{id}` URLs — DONE
Batch 1B  Law-loading/hash cleanup + batched dashboard/selection — DONE
Batch 2   Payment/subscription foundation
Batch 3   User entitlement inversion — DONE (M3-A Constitution + M3-B Playground gate)
Batch 4   Device registry/control — IN PROGRESS (M4-A 19/25; M4-B device-management UI next; churn BLOCKED)
Batch 5   Monthly roster + rollover
Batch 6   Final Playground UI shell
Batch 7   Complete Learn modes
Batch 8   Learned + revision + Today/Calendar
Batch 9   Amendment handling
Batch 10  SEO + sitemap (main adopted on this branch; remaining: Playground noindex)
Batch 11  Legacy transition + production hardening
```

Small non-blocking rectifications should be folded into the next substantial batch.

Only blockers, security/data-integrity issues, or prerequisites get standalone correction batches.

---

# Playground completion definition

Playground is **100% complete** only when a subscribed user can:

```text
subscribe
  ↓
register permitted device
  ↓
receive monthly 10 / 30 / unlimited roster
  ↓
choose/continue laws
  ↓
select statutory provisions
  ↓
use the complete RecallC learning experience
  ↓
reach Learned
  ↓
complete 1 → 3 → 7 → 15 → 30 → 60
  ↓
retain progress through roster changes,
device changes and subscription lifecycle
  ↓
receive amendment awareness
```

and the system simultaneously supports:

```text
guest
signed-in free
subscriber
legacy subscriber
cancelled
expired
past-due
resubscribed
device-limited
roster-full
annual subscriber
admin override
```

without changing the canonical statutory source or the Constitution data model.

That definition is **Stage 1 = 100/100**. Stage 2 does not change it.

---

# Stage 2 — Optimize Playground (unweighted)

**Status: `NOT STARTED` — start gate: Stage 1 = `DONE` (100/100)**

Starts only after Stage 1 contracts are implemented, tested, and proven in production-like use. Improve scale, reliability, performance, security, and operations **without reopening the product model**.

Do **not** prematurely optimize speculative bottlenecks during Stage 1. Do **not** tick these boxes from Cloze, from proof overlay code, or from `main`’s sitemap PRs.

Where Stage 1 already owns first-time correctness, Stage 2 verbs are **profile / measure / tune / automate / scale / retire** — not **implement**.

### Done when (Stage 2)

Measured improvements against production behaviour; proven-dead legacy/proof paths **retired** only after unused. Product model unchanged.

## 1. Database optimization

* [ ] Profile query plans for roster, revisions, devices, subscriptions, and progress
* [ ] Tune indexes from those plans
* [ ] Measure and eliminate remaining N+1 (Stage 1 already requires batched dashboard / no-N+1 home)
* [ ] Measure p95 of aggregates/dashboard reads; tune
* [ ] Archival / data-retention strategy after real growth is visible

## 2. Routing / backend optimization

* [ ] Measure Playground route latency
* [ ] Trim unnecessary dependencies/queries found in traces
* [ ] Tune request-scoped entitlement/bootstrap caching
* [ ] Profile authorization guard composition; tune
* [ ] Further batch writes/reads where measurement shows benefit

## 3. Law-loading optimization

* [ ] Verify zero-hydration catalogue / Playground dashboard still holds under load (Stage 1 owns the contract)
* [ ] Profile `BareAct` hydration
* [ ] Measure cache effectiveness
* [ ] Prepare section/chapter chunking **only when corpus size justifies it**
* [ ] Scale precomputed search/index infrastructure as the corpus grows

## 4. SEO at scale

* [ ] Automate sitemap manifest generation (Stage 1: manifest **contract** works)
* [ ] Scale / chunk sitemap index for the actual corpus
* [ ] Large-corpus crawl efficiency
* [ ] Canonical audits
* [ ] Structured data/schema where valuable
* [ ] Search Console / index coverage monitoring
* [ ] Core Web Vitals on law pages

## 5. Performance

* [ ] Page-weight audit
* [ ] Tune JS/CSS delivery
* [ ] Profile template rendering
* [ ] Measure DB latency
* [ ] Cold-start behaviour
* [ ] Caching headers for public immutable/static law assets where appropriate

## 6. Concurrency & resilience

* [ ] Profile roster races beyond Stage 1 atomic-consume tests
* [ ] Profile device-registration races beyond Stage 1 cap tests
* [ ] Concurrent progress/revision writes under load
* [ ] Measure duplicate/out-of-order Razorpay handling (Stage 1 owns HMAC + event-id)
* [ ] Tune retry/idempotency from observed failures
* [ ] Degraded-provider scenarios

## 7. Security & misuse prevention

* [ ] Rate limits (tune from observed abuse)
* [ ] Device-churn detection (numeric policy still §21 for Stage 1)
* [ ] Suspicious subscription/account-sharing signals (non-authoritative)
* [ ] Mutation abuse protection
* [ ] Authorization audits
* [ ] CSRF/session-cookie hardening

## 8. Observability

* [ ] Entitlement denial reasons
* [ ] Device-limit events
* [ ] Roster-full events
* [ ] Webhook failures
* [ ] Payment reconciliation failures
* [ ] Law-load latency
* [ ] Playground route latency / error rate

## 9. Operational tooling

* [ ] Improve admin subscription diagnostics from observed failures (Stage 1: first-pass diagnostics exist)
* [ ] Improve device-reset support UX
* [ ] Improve roster inspection
* [ ] Improve Razorpay reconciliation tooling
* [ ] Amendment/source diagnostics
* [ ] Safer support tooling without raw DB intervention

## 10. UX optimization

* [ ] Funnel analytics: Browse → Add → Learn → Learned → revision
* [ ] Measure rollover completion rates
* [ ] Subscription conversion
* [ ] Abandoned learning sessions
* [ ] Clearer empty/error states from observed confusion
* [ ] Accessibility
* [ ] Mobile/responsive refinements

## 11. Scale testing

* [ ] Realistic 700+ law catalogue
* [ ] Users with 30 active laws
* [ ] Large Acts
* [ ] High progress-row counts
* [ ] Sitemap inventory scale
* [ ] Concurrent subscriber traffic

## 12. Cleanup

* [ ] Retire proven-dead legacy entitlement code (Stage 1: stop reading; delete only after unused)
* [ ] Retire obsolete proof-only paths
* [ ] Simplify compatibility shims
* [ ] Consolidate duplicate helpers after real usage is understood

