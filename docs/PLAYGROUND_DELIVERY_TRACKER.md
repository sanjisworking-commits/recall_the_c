# RecallC Playground — Delivery Tracker

**Scoreboard, not an audit.** Product rules live in [PLAYGROUND.md](PLAYGROUND.md), [PAYMENT_ENTITLEMENT_AUDIT.md](PAYMENT_ENTITLEMENT_AUDIT.md), [PLAYGROUND_TWO_LAW_AUDIT.md](PLAYGROUND_TWO_LAW_AUDIT.md), and [law-loading.md](law-loading.md).

**Snapshot (this file’s date of write):** architecture/product definition is **locked in docs**. Production Playground implementation is **early**. The NDPS/BNS overlay + Cloze + proof revision rows **do not** count as milestones 6–8 (or as production milestone 1 routing/eligibility).

| | |
|--|--|
| **Overall** | **3.5 / 100** |
| Milestone 0 | `IN PROGRESS` — 7/10 items × 5 = **3.5** |
| Milestones 1–11 | `NOT STARTED` except §21 commercial cells in milestone 2 (`BLOCKED`) |

Do not read Cloze on this branch as ~20% complete. Payments, roster, devices, six Learn modes, and Learned → revision are the actual product weight.

---

## Tracking rule

Playground completion is measured out of **100 points**.

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

**§21 BLOCKED (do not invent):** public tier `display_name`, INR prices, GST treatment, monthly vs annual as MVP, Razorpay state → access matrix, `past_due` grace, refund / partial / chargeback access, `DEVICE_REPLACEMENT_*` integers. See [PAYMENT_ENTITLEMENT_AUDIT.md](PAYMENT_ENTITLEMENT_AUDIT.md) §21. Internal codes `plus` / `pro` / `max` are already locked.

---

# 0. Architecture lock + branch baseline — 5 points

**Status: `IN PROGRESS`** (7/10 × 5 = 3.5)

### Scope

* [x] Playground product philosophy locked
* [x] Verbatim law JSON remains canonical
* [x] Constitution model stays independent
* [x] User-type entitlement locked
* [x] Device policy locked
* [x] Monthly roster policy locked
* [x] SEO/routing/loading contracts documented
* [ ] Rebase `cursor/playground-220d` onto **latest** `main`
* [ ] Resolve law-loader / BNSS / SEO / sitemap integration with current `main`
* [ ] Full baseline test suite green after that rebase

A prior rebase landed on `main` at BNSS + lazy loading. `main` has since added Bare Act SEO wiring and a generated sitemap index (PRs #192 / #196). Those commits are **not** on this branch until the next rebase. Overlay `{ndps, bns}` allowlists and `/playground/{law_id}` are **milestone 1**, not a hidden milestone-0 fail.

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

**Status: `NOT STARTED`**

Proof handlers in `app.py`, `{ndps, bns}` locators, and request-time `read_bytes()` hashing **do not** satisfy this milestone.

## Eligibility

* [ ] Add one authoritative `is_playground_eligible_law()`
* [ ] Add `list_playground_eligible_laws()`
* [ ] Eligibility = full Bare Act + valid `BareActSpec`
* [ ] Remove production NDPS/BNS allowlists
* [ ] Locator accepts eligible law slugs generically
* [ ] Mapped/key-provision-only laws remain ineligible

Routes, roster, locators, entitlement, and UI must consume **that same helper**. Do not reconstruct eligibility in five modules.

## Routing

* [ ] Create dedicated Playground `APIRouter`
* [ ] Remove Playground HTTP handlers from `app.py`
* [ ] Lock final URLs:

```text
/playground
/playground/roster
/playground/roster/next
/playground/laws/{law_id}
/playground/laws/{law_id}/sections
/playground/laws/{law_id}/sections/{number}/learn/{mode}
```

Proof `/playground/{law_id}` does **not** count.

## Law-loading compatibility

* [ ] Remove request-time whole-file hashing
* [ ] Use registry `source_version` / `source_hash`
* [ ] `/playground` hydrates zero Acts
* [ ] roster pages hydrate zero Acts
* [ ] one law workspace hydrates only that Act
* [ ] no cross-law corpus load

## Data access

* [ ] Batched Playground dashboard query (`list_playground_summaries`)
* [ ] No N+1 selection/progress queries across 10/30 laws
* [ ] Entire-Act section selection uses batched DB writes

### Done when

Playground has a scalable backend shell independent of the two-law proof.

**Weight: 8**

---

# 2. Payment & subscription foundation — 13 points

**Status: `NOT STARTED`** (commercial name/price/GST/interval/state-matrix/refund items: `BLOCKED` on §21)

## Commercial model

* [ ] Final public tier names — **`BLOCKED` §21**
* [ ] Internal tier codes remain stable (`plus` / `pro` / `max` — **locked**)
* [ ] Final prices — **`BLOCKED` §21**
* [ ] GST display treatment — **`BLOCKED` §21**
* [ ] Monthly billing product configuration — **`BLOCKED` §21** (interval choice)
* [ ] Annual billing configuration where offered — **`BLOCKED` §21** (annual still = monthly Playground periods)

## Subscription persistence

* [ ] `user_subscription` or final equivalent
* [ ] Provider subscription ID
* [ ] status
* [ ] tier
* [ ] billing period start/end
* [ ] cancel-at-period-end
* [ ] provider metadata

## Razorpay subscription lifecycle

* [ ] Create subscription
* [ ] Checkout
* [ ] Renewal
* [ ] Auto-renew
* [ ] Cancel
* [ ] Upgrade
* [ ] Downgrade
* [ ] Expiry
* [ ] Failed payment
* [ ] Past due — grace days **`BLOCKED` §21**
* [ ] Paused/halted
* [ ] Resubscribe
* [ ] Refund handling — access outcome **`BLOCKED` §21**
* [ ] Dispute/chargeback handling — **`BLOCKED` §21**

## Webhooks

* [ ] Raw-body signature verification
* [ ] event-ID idempotency
* [ ] duplicate delivery safe
* [ ] out-of-order delivery safe
* [ ] provider reconciliation/fetch path
* [ ] secret rotation strategy
* [ ] webhook tests

## Legacy

* [ ] Existing N-day buyers recognized as `legacy`
* [ ] No silent Plus/Pro/Max remapping
* [ ] Paid entitlement preserved for already-paid period

### Done when

A subscription can move through its full real lifecycle without manually editing the DB. Cursor must **not** invent the §21 cells to tick this milestone.

**Weight: 13**

---

# 3. User-type entitlement inversion — 7 points

**Status: `NOT STARTED`**

Implement one authoritative entitlement resolver.

## Guest

* [ ] Constitution guest behaviour preserved
* [ ] laws readable
* [ ] Playground → Sign in

## Signed-in / no Playground subscription

* [ ] ALL Constitution Articles available
* [ ] ALL six Constitution Learn modes available
* [ ] no 3-Article access restriction
* [ ] no Type/Recite premium restriction
* [ ] laws readable
* [ ] Playground → Subscribe

## Subscriber

* [ ] Full Constitution
* [ ] Full Playground learning capability
* [ ] tier affects only monthly law capacity

## Legacy logic retirement

Stop consulting for access:

* [ ] article claim count
* [ ] 3-Article slot cap
* [ ] selective premium Learn modes

Do **NOT** delete historical tables yet.

## Central service

Entitlement snapshot includes:

```text
authenticated
subscription_status
tier
can_use_constitution_learn
can_use_playground
block_reason
```

(Plus roster and device fields already locked in the payment audit.)

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

**Status: `NOT STARTED`** (replacement-churn numeric policy: `BLOCKED` on §21)

## Registry

* [ ] `user_device`
* [ ] `user_device_session`
* [ ] 2-device configurable limit
* [ ] same limit for all paid tiers
* [ ] `rtc_device` separate from auth session
* [ ] secure random installation token
* [ ] server stores HMAC, not raw secret

## Behaviour

* [ ] first device registers
* [ ] second device registers
* [ ] third device Playground-blocked
* [ ] third device still gets full Constitution
* [ ] logout does not consume new device slot
* [ ] revoke device
* [ ] replacement registration
* [ ] revoked device immediately loses Playground authorization
* [ ] progress unaffected
* [ ] subscription expiry retains device registry
* [ ] resubscription recognizes existing devices

## Device management

* [ ] Profile → Security → Devices
* [ ] current device identified
* [ ] remove device
* [ ] device-limit gate
* [ ] admin/support reset path
* [ ] replacement-churn policy implemented once §21 values locked — **`BLOCKED` until integers exist**

## Concurrency

* [ ] simultaneous registrations cannot create 3 active devices

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

**Status: `NOT STARTED` on this branch**

Public Bare Act SEO and a generated sitemap index exist on **`main`** (not yet merged here). They do **not** complete this milestone until: this branch includes them, Playground/account URLs are `noindex` / absent from sitemap, and query `/laws` canonicalization is verified. Do not re-invent `seo.py`.

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
| 0. Architecture + branch baseline |      5 | `IN PROGRESS` (3.5 earned) |
| 1. Backend foundation             |      8 | `NOT STARTED` |
| 2. Payment/subscriptions          |     13 | `NOT STARTED` / §21 `BLOCKED` |
| 3. User-type entitlement          |      7 | `NOT STARTED` |
| 4. Device control                 |      8 | `NOT STARTED` |
| 5. Monthly roster                 |     12 | `NOT STARTED` |
| 6. Finished UX                    |      8 | `NOT STARTED` |
| 7. Complete Learn engine          |     15 | `NOT STARTED` |
| 8. Learned/revision/mastery       |      8 | `NOT STARTED` |
| 9. Amendments/source integrity    |      5 | `NOT STARTED` |
| 10. SEO/routing discoverability   |      4 | `NOT STARTED` on this branch |
| 11. Production hardening/release  |      7 | `NOT STARTED` |
| **TOTAL**                         |  **100** | **3.5 / 100** |

---

# PR / batch rule

Each substantive implementation batch should map to one or more tracker milestones.

Recommended order:

```text
Batch 0   Rebase onto latest main + contracts (this milestone 0 remainder)
Batch 1   Eligibility + APIRouter + law-loading/hash cleanup
Batch 2   Payment/subscription foundation
Batch 3   User entitlement inversion
Batch 4   Device registry/control
Batch 5   Monthly roster + rollover
Batch 6   Final Playground UI shell
Batch 7   Complete Learn modes
Batch 8   Learned + revision + Today/Calendar
Batch 9   Amendment handling
Batch 10  SEO + sitemap (rebase/adopt main; Playground noindex)
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
