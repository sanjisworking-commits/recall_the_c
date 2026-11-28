# Entitlement decisions — excerpts and where each stands (record of 2026-11-27)

**What this file is.** A transcription, made so that the decisions the Playground tier-revision work relies on are readable inside the repository. Until now the approvals of 2026-11-02 and the proposals of 2026-11-03 existed only in a review package held outside it. This file changes nothing: it records, it does not decide.

**How it was made.** Every excerpt below was copied line for line from its source file by a script, not retyped, and each carries the source's line numbers. Nothing is quoted from memory or from a summary. The commentary sections (§1, §7 and §8) are analysis written for the M8-R plan and are marked as such.

**What it does not establish.** The review package *reports* the owner's approvals; it is not the owner's own message. If any entry here differs from what was decided, the owner's correction governs and this file is amended.

| Source | Identity | SHA-256 | Read |
|---|---|---|---|
| Tier-revision review package | v3.9, dated 2026-11-03 in its status line; file `enchanted-inventing-chipmunk.md`, held outside the repository | `f6946b20fbd6dcd12a60f019fee49f47bb63f9c7d778e08e924241a5ac2d73a6` | 2026-11-27 |
| Design handover, Coverage Pack | `handover-tier-revision/COVERAGE.md`, dated 28 October 2026 in its opening lines; inside the handover archive `Playground (2).zip` (archive SHA-256 `b432f05e848af1d5b7512cc01713b70d8dd755eba2420b3f811e722fcff95643`), held outside the repository | `0254bea9f248cd0f0e56d00b412f12fd2efd00b088267ebdf794bce25d91fc00` | 2026-11-27 |
| Repository records | the files named in §5, at the commit that adds this file | — | — |

## 1. Status at a glance (analysis; the excerpts in §2–§6 are the authority)

| Decision | Status | Excerpt |
|---|---|---|
| 5-4 paid→Free | approved 2026-11-02 | §2 |
| 5-6a existing personal material | approved 2026-11-02 | §2 |
| 5-6b existing Free holders at create / edit activation | deferred 2026-11-02 — blocks full activation | §2 |
| 5-9a ledger storage; 5-19 consume timing; 5-21 mapping; 5-22 activation flag | approved 2026-11-02 | §2 |
| 5-23 month boundary under `choices` | approved 2026-11-02 | §2 |
| 5-20 transition table | unresolved; a proposal exists (§3) | §2, §3 |
| 5-13 rollback window and triggers | unresolved | §2 |
| 5-1 prices | unresolved; one part decided 2026-11-06 and 2026-11-07 | §4, §5 |
| 5-2 upgrade timing; 5-3 cancellation, downgrade, grace | register recommendations only | §4 |
| 5-7 Max access policy; 5-10 Free device policy; 5-12; 5-14; 5-15 | register recommendations only; applied parts are in §5 | §4, §5 |
| 5-24 partial refunds and open disputes | gap; interim behaviour stated | §4 |

## 2. Review package §5.4 — decision table after the approvals of 2026-11-02

Verbatim, package lines 607–624.

### 5.4 Decision table — status after the owner's approvals of 2026-11-02

Approvals below are the owner's recorded planning decisions. They authorise planning updates only — not implementation, deployment, migration execution, resets, subscription changes or grants. "Blocks" names what cannot be specified until the choice is made. Everything not listed stays exactly as today per §4.6.

| # | Decision | Choices | Status 2026-11-02 | Blocks |
|---|---|---|---|---|
| 5-9a | Ledger storage | confirm the additive `user_playground_choice` table **in principle** / prefer the open-period alternative | **APPROVED**: additive permanent-choice ledger | schema, lookup sites, B1-F03/F04/F18 |
| 5-21 | Migration mapping | **M0** none / M1 consumed items of non-paid accounts / M2 legacy article claims | **APPROVED**: M0 — no historical backfill, deletion or reset of existing choices | authoring the migration, B1-M02 dry-run content |
| 5-19 | "Choose sections" consume timing | **A** POST carrying `scope=sections` / **B′** inside the sections save, atomic | **APPROVED**: consume only on successful server save (Entire Act, or at least one selected section); choice and membership/selection saved atomically | add handler, sections-page access mode, B1-F08 |
| 5-23 | Month boundary under `choices` | **(a)** automatic carry, Keep/decline retired / (b) automatic for Free, housekeeping step for paid / (c) as today | **APPROVED**: automatic continuation; mandatory monthly Keep/decline retired | rollover routes, B1-F19, read-only membership resolution |
| 5-20 | Transition table §5.3 | approve every row / name rows to change; in-row: immediate cancellation **(i)** now or **(ii)** at period end; halted: keep the block until the provider resolves | **UNRESOLVED** — rows presented in plain language in §5.5 for row-by-row decision | `_from_subscription` resolution, cohort suites |
| 5-4 | Paid→Free with k = 0…3 | approve the §5.2 wording as refined in §4.12.3 / amend | **APPROVED**: preserve original Free choices; user explicitly selects any remaining allowance; other laws' saved data preserved; removed laws never re-added automatically | B1-M02, M7-R copy |
| 5-6a | Existing personal material for Free | **unchanged** (read, complete, download, export, delete allowed) / name operations to restrict | **APPROVED**: existing permissions on existing personal material preserved for B1 | B1-F11 tests |
| 5-6b | Existing Free holders at create/edit activation | (i) gate with notice + grace / (ii) keep edit on held material / **(iii)** defer the gate on such environments until a count exists | **DEFERRED** by the owner. With one coordinated flag this is a blocker to full activation of the new model (§4.5 item 6) | activation of the whole model on environments holding such accounts |
| 5-13 | Rollback window and triggers | window lengths, trigger list, who may flip | **UNRESOLVED** — presented in plain language in §5.5 | deploy plan, B1-M03 |
| 5-22 | Activation approach | accept the `PLAYGROUND_TIER_MODEL` flag / alternative | **APPROVED**: one coordinated activation flag | shape of every resolver |

Not required for B1: 5-9b (personal-material persistence; separate programme), 5-7 (needed before the Visualize and Calendar gates activate for Max rows), 5-10, 5-12, 5-1, 5-14, 5-15, 5-16 (copy and UI; current behaviour until decided).

## 3. Review package §5.5.1 — the 5-20 transition table. **PROPOSED; nothing in it is approved**

Section heading, verbatim, package line 628:

> 5.5 The two unresolved decisions — revised 2026-11-03 per the owner's recommendations [PROPOSED; nothing approved; v3.6 approvals untouched]

Table and the decision it asks for, verbatim, package lines 644–666. The "Today" column describes the code at `3719b9f`.

**Proposed table (decision 5-20; approve, amend per row, or reject).** "Paid-through future" in this table means **verified payment coverage (or an authorised staging grant, staging only) covering now and not revoked**; provider period dates alone never qualify.

| # | Provider status | Paid-through | Proposed effective access | Today | Changes today? |
|---|---|---|---|---|---|
| 1 | `created`, `authenticated` (checkout not completed) | none | Free | no Playground | yes — Free capability appears |
| 2 | `active` | future | paid tier, full use and adds | same | no |
| 3 | `active` with `cancel_at_period_end` | future → passed | paid until the verified paid-through date, then Free | same timing; then read-only | after the date: Free instead of read-only |
| 4 | `cancelled` | future | **paid until the verified paid-through date** (honoured), then Free | blocked at once | yes — honours the paid period |
| 5 | `cancelled` | passed or none | Free | blocked | yes — Free instead of block |
| 6 | `expired`, `completed` | future (rare) / passed | paid until the date if future; Free when paid access ends | blocked | yes |
| 7 | `halted` | future | **paid until the verified paid-through date** (verified remaining access preserved), then Free | indefinite block, read-only | yes — no indefinite block |
| 8 | `halted` | passed or none | Free (banner: payment problem; offer retry/resubscribe) | indefinite block | yes |
| 9 | `paused` | future | paid until the verified paid-through date, then Free; on resume the row continues | indefinite block, read-only | yes |
| 10 | `paused` | passed or none | Free | indefinite block | yes |
| 11 | `pending` (charge due, retry window open) | future (previous cycle still paid through) | paid until that date — the pending payment itself grants nothing | use existing, no adds | adds allowed while paid through |
| 12 | `pending` | passed or none | Free — **stricter than today**, which lets a pending account keep using existing laws without a verified paid-through date | use existing, no adds | yes — owner to confirm this tightening explicitly |
| 13 | any status, full refund or lost dispute on a payment | that payment's coverage revoked | **only the entitlement attributable to that payment** is revoked (the charge's own period on its own subscription row); a refund for an earlier cycle never revokes a later paid cycle; another valid subscription row is untouched; access is then **recomputed across the remaining valid entitlements** (a later covering charge, a legacy grant, a staging grant on staging) with **Free as the fallback** | read-only at once, by matching the current period only | Free or remaining entitlement instead of read-only |
| 14 | any status, partial refund or open dispute | unchanged | **no access change until resolved** (today's de-facto behaviour: both map to `none`); separate treatment is gap **5-24** | no change | no |
| 15 | resubscription (new row, old row `is_current = false`) | per the new row | the newly purchased tier from the new row's verified dates; choices and saved data preserved; late events for the old row never alter the new row (B1-B03) | same | no |

**Notes for implementation (not decisions).** (a) "Verified" requires the provider GET to have succeeded; a stale `billing_period_end` after a failed GET is treated as unverified only for *granting* paid access, never for *removing* access the user already has, until the next successful GET (B1-B02 serialises the writes). (b) Attribution at the lookup already holds: charges are listed per `user_subscription_id` and matched to their own period dates (`charge_postgres.py:87–95`, `charge_repository.py:94–110`, `281–299`), so a refund on another subscription row or on an earlier cycle does not match the current period — the earlier [GAP] in v3.7 is withdrawn. What B1-B03 must still test: after a revocation, access is recomputed across the remaining valid entitlements instead of today's blanket `BLOCK_PAID_PERIOD_ENDED`, and a later cycle's coverage survives an earlier cycle's refund. (e) Missing or unverifiable payment records — two cases, never conflated [PROPOSED]: **(e1) First payment awaiting verification** (no captured charge has ever been recorded on this subscription row): the account is not granted paid access on dates alone; it sees Free access with a "confirming your payment" banner; reconciliation retries a provider GET on every incoming event for the row and on a schedule (proposed: 5, 15, 60 minutes, then hourly for 24 hours, then the daily B1-B05 run), records the charge when the provider confirms the payment, and flags the row for admin attention if still unconfirmed after 24 hours. **(e2) Previously verified paid access when a lookup fails** (a captured charge was recorded earlier on this row, the provider schedule shows a continuing cycle, and the provider GET for the new cycle fails or times out — an outage, not a provider answer): the account **keeps its last verified access**; a failed lookup never removes access that was verified, so an established paid user is not silently downgraded. The retained access is time-boxed (proposed: 7 days past the end of the last verified coverage), retries follow the (e1) schedule, the row is flagged for admin attention after 24 hours, and the user sees no change until either the provider confirms (coverage recorded) or the box expires (then the state's row applies, with a banner). A **successful** lookup that reports no payment is not an outage: the row's state applies at once. All of (e) is to be verified against provider behaviour before B1 ships. (c) Mapping these rules onto Razorpay's state machine is implementation work that must be verified against provider documentation and recorded test events before B1 ships; nothing here asserts provider behaviour. (d) Between "paid access ends" and the user's own selections: active laws covered by ledger rows stay fully usable; selection is needed only to spend remaining choices; laws without a ledger row keep their data with restricted access (read-only, revisions per 5-5).

**You decide (5-20):** (a) the provenance rule — verified payment coverage as the sole production source of paid access, provider dates as schedule only, staging grants as a distinct staging-only source, and the missing-charge behaviour in note (e); (b) the table — approve, or name rows to amend: rows 4, 7, 9 (honouring covered access on cancel, halt, pause), row 12 (the pending tightening), row 1 (Free for never-completed checkouts), row 13 (per-payment revocation with recompute).

## 4. Review package §5.2 — register rows that bear on subscription and device states

Heading, verbatim, package line 557: "5.2 Full register (unresolved; recommendations are not approvals)". These rows are recommendations, not approvals. Verbatim, package lines 561, 562, 563, 567, 571, 573, 575, 576, 582.

| # | Decision | Recommendation | Blocks |
|---|---|---|---|
| 5-1 | Plus/Pro prices, period, tax presentation | [PROPOSED] no price printed until decided; "GST included" only beside a real price | Plans, M2-R |
| 5-2 | Upgrade timing / proration | [ENG] keep `SCHEDULE_NOW` up, cycle-end down; no "instant unlock" copy | copy |
| 5-3 | Cancellation, downgrade, payment-failure grace | keep current dispositions | M8-R |
| 5-7 | Existing paid Max subscriptions: access under the new model (Playground unlimited? Visualize? personal tasks?) and migration | [PROPOSED] preserve recognition and current access; grant **no new benefit by assumption**; owner decides Visualize/Calendar for Max before those gates activate; staging Max test rows are fixtures, not policy | Visualize/Calendar gate activation |
| 5-10 | Device policy for Free | [PROPOSED] not applied this release | B1 default |
| 5-12 | Revision dates on re-add | [PROPOSED] restore ladder position; next revision from re-add date; no "exactly as you left them" copy | M2-R |
| 5-14 | Remove paid confirmation step | [PROPOSED] accept | M2-R |
| 5-15 | `/pricing` scope | [PROPOSED] stays disabled; Plans stage is the only tier page; landing/sitemap respect the flag | M5-R |
| 5-24 | Partial refunds and open (unresolved) disputes | [GAP] today both map to `access_effect = none` (`subscriptions/policy.py:62–73` recognises only `refund == full` and `dispute == lost`); no access change until resolved is the de-facto rule; separate treatment to be decided; not a B1 blocker | B1-B05 reconciliation, M8-R |

## 5. Later decisions already recorded in the repository

Verbatim rows from the milestone records, with file and line.

`docs/design/milestones/M2-R-evidence.md:83`

> | 5-1 | **Decided 2026-11-06 (owner-forwarded review): omit "from ₹199" from upgrade sheets until pricing is approved.** Applied in `3ad4b82` to the `subscribe` sheet and the Act-head Free note; the `free_limit` sheet already printed none. The Playground gate / Pricing / Billing pages still show plan prices (out of this decision's scope). | Closed for M2-R; pricing approval itself remains open under 5-1. |

`docs/design/milestones/M5.md:38`

> | Q6 | Devices per prototype: "Devices", allowance lede, REGISTERED cards with Remove, designed empty state, desktop layout; same endpoints and confirm step. | The lede promises nothing to Free (registration happens on Playground use while a paid plan is active). |

`docs/design/milestones/M5.md:39`

> | Q7 | Plan cards are a required radio group in one form; Continue posts to `/billing/subscriptions/create`; Max never offered; "from ₹" removed. | Catalogue prices remain **as current configuration, not as approval of the pricing policy**; tests mock the subscription service — no provider call, nothing charged. |

`docs/design/milestones/M5.md:40`

> | Q8 | `?stage=plans` renders the plans stage for accounts that **can open** the Playground. | Never bypasses eligibility: a current subscriber's form posts to `/billing/subscriptions/change`; paused / expired / halted keep today's home and Resume / Manage flows. |

The locked plan-change and status rules that remain in force are in `docs/PAYMENT_ENTITLEMENT_AUDIT.md` §15 ("Upgrade / downgrade (locked)") and §21; they are not copied here because that file is already in the repository.

## 6. Design handover, Coverage Pack — rows that bear on these states

Verbatim, `COVERAGE.md` line 5:

> Confirmed rules (unchanged): Guest read-only, sign-in to save · Free ₹0: all Articles + 3 lifetime law choices, removal never restores a choice, previously chosen laws re-add without consuming one · Plus: unlimited laws + personal Calendar tasks · Pro: + curated Visualize (Article 82 live) · Max removed.

Verbatim rows, `COVERAGE.md` lines 21, 22, 23, 25, 26, 27, 30, 35. The pack's own status key: "**Complete** = designed to the confirmed entitlement rules · **Proposed** = designed, needs owner approval".

| Item | Covered by | Status |
|---|---|---|
| Checkout summary, verifying, success, failure, cancelled | D1–D5 (+ D1p, D3p, D4p) | Proposed (prices separate; monthly billing proposed for first release; tax, receipt, timeout, charge-status placeholder) |
| Active subscription, upgrade review, scheduled cancellation, resubscription | D6, D7, D9, D11 | Proposed (period-end cancellation per decision 3; proration pending) |
| Downgrade: Pro → Plus / paid → Free | D8, D12 | Approved (decision 2): original Free choices return permanently; other laws locked, progress saved, Bare Act readable |
| Free accounts and the existing Playground device limit | F2 | Awaiting owner decision (register item b) |
| Payment problem, grace period | D10 | Awaiting owner decision |
| Prices, proration, grace, refunds | placeholders in D1, D7, D10, D11, Plans | Awaiting owner decision (decided separately; prototype does not decide them) |
| Free accounts already holding personal tasks | E5 | Approved (decision 4b): view / attachments / complete / delete stay; Plus for new, edit, reschedule. Reminders continuing: separate decision |
| Legacy Max accounts and billing records | — | Keep intact until migration is explicitly decided |

## 7. Where the documents differ, one by one (analysis for the M8-R plan)

No document is superseded as a whole. Each row names the later dated record that governs the point.

| # | Difference | What governs, and since when |
|---|---|---|
| C1 | The audit's §21 lists Plus ₹199 / Pro ₹399 / Max ₹1,199 as "Locked" | They remain the configured catalogue. They are not approved pricing for the redesign: 2026-11-06 ("pricing approval itself remains open", §5 above) and 2026-11-07 (M5 Q7, §5 above). 5-1 is open (§4) |
| C2 | The audit's §15 and §21 treat Max as a tier that can be bought | 2026-11-07, M5 Q7: "Max never offered". The Coverage Pack agrees: "Max removed" with legacy Max accounts kept intact (§6) |
| C3 | The audit's monthly roster with Keep / Remove rollover | Stands under `monthly`. Under `choices`, 5-23 as approved 2026-11-02 (§2) |
| C4 | The audit's §21 status → access matrix and §15 plan-change timing | No conflict: in force, and they match the code. The 5-20 table (§3) is a proposal only |
| C5 | Coverage Pack "decision 2": on paid → Free, "other laws locked" (§6) | 5-4 as approved 2026-11-02 (§2) gives the detail: original choices preserved, explicit selection of any remaining allowance, saved data kept |
| C6 | Coverage Pack "decision 4b": Free accounts already holding personal tasks (§6) | 5-6a approved and 5-6b deferred, 2026-11-02 (§2): the create / edit gate for existing holders is not decided |
| C7 | Coverage Pack "period-end cancellation per decision 3" (§6) | Consistent with the audit's §21 and with the service. Only 5-20's sub-question on immediate cancellation is open (§2) |
| C8 | The roadmap's "M8" (prototype viewers, gate DV-18) and the review package's "M8-R" | Both apply. DV-18 stays the gate and stays U wherever a comparison was not made |

## 8. Findings recorded against these decisions

Found by inspection at `079257e`; to be confirmed and characterised by tests in M8-Ra. They are defects or open questions, not decisions.

- **H2 — blocks `choices` activation.** Paid adds never write the choice ledger, so under `choices` a former paid account is RecallC Free with 0 of 3 choices used, every paid-era law carried forward and learnable, and three more addable. This does not follow 5-4 (§2).
- **H3 — blocks `choices` activation.** A checkout that is started and abandoned leaves a `created` subscription row current; under `choices` that account is hard-gated and loses its Free choices until the provider expires the row (5-20 row 1, §3).
- **H1.** The read-only "expired" state pinned by the expired cohort tests is a subscription row that is both terminal and current — a shape the service does not keep (`subscriptions/service.py`, `_persist_provider` marks a terminal row not-current).
- **H7.** With the stored period elapsed and the provider row still `active`, the billing page shows the ordinary current-plan actions. Not changed; a state / action matrix is to be reviewed first.
