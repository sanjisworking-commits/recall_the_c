# M8-Rb — Subscription states: decision table (for the owner's decision)

| Item | Value |
|---|---|
| Status | **For decision. Nothing here is built, and nothing here is approved.** Recommendations are the author's (Claude's), not approvals |
| Asked for | 2026-11-28: a state / action table from the existing findings and approved records, settled rules told apart from open decisions, a recommended outcome and the user impact for each open row |
| Sources | `ENTITLEMENT_DECISIONS.md` (verbatim excerpts with provenance; §2 approvals of 2026-11-02, §3 the proposed 5-20 table); `M8-Ra-billing-matrix.md`; the read-back `m8ra/02-candidate-2270d77/readback.json`; `tests/test_edge_state_family.py` (the four `test_known_defect_*` tests); `subscriptions/service.py`, `subscriptions/policy.py`, `entitlements/service.py` at the M8-Ra head |
| Limits | **Provider behaviour: NOT RUN.** Every "today" below is what the application does with a stored row, seen on a throwaway local database and a mocked provider client. Nothing here shows what Razorpay reports, accepts or does. Each recommendation that depends on the provider says so |
| Held | Transition and billing-action changes, merge, deployment, `choices` activation |

"Today" columns: **M** = under `monthly` (the active model), **C** = under `choices` (built, off). Reach: **P** = a stored shape the application's own code can leave, **S** = a synthetic fixture.

## 1. Settled rules (not reopened here)

| Rule | Record |
|---|---|
| Paid → Free: original Free choices preserved; the user explicitly selects any remaining allowance; other laws' saved data preserved; removed laws never re-added automatically | 5-4, approved 2026-11-02 |
| Free: 3 lifetime law choices; removal never restores a choice; a previously chosen law re-adds without consuming one | Coverage Pack "confirmed rules" (28 Oct) |
| A choice is consumed only on a successful save, atomically with the membership | 5-19, approved 2026-11-02 |
| Additive ledger; no historical backfill, deletion or reset | 5-9a, 5-21, approved 2026-11-02 |
| Under `choices`, months continue automatically; monthly Keep / decline retired | 5-23, approved 2026-11-02 |
| One activation flag, off by default | 5-22, approved 2026-11-02 |
| Existing permissions on existing personal material preserved | 5-6a, approved 2026-11-02 |
| Upgrade takes effect now, downgrade at the end of the billing period | audit §15 (locked); matches `subscriptions/service.py` |
| Until 5-20 is decided, each status keeps its current disposition: `active` use and add; `pending` existing laws only; every other status no Playground; an ended period is read-only | audit §21 (locked); tier-revision plan §4.6 |
| Max is recognised for holders and never offered | owner, 2026-11-07 (M5 Q7) |
| Paused, halted and ended accounts get no plans stage; they keep Resume / Manage | owner, 2026-11-07 (M5 Q8) |
| No price is added; catalogue prices stand as configuration, not as approved pricing | owner, 2026-11-06 and 2026-11-07 |
| An elapsed stored period does not establish that the provider subscription has ended; no duplicate-subscription path; cancellation is not hidden on the date alone | owner, 2026-11-27 (M8-R plan, Q7) |
| Devices: limit 2; 3 replacements per rolling 30 days; registration only while a subscription gives Playground access (active or pending) | audit §21; M5 Q6; M8-Ra Q8 |

Still open and **not** part of this table: 5-6b (deferred — blocks activation), 5-13 (rollback window), 5-1 (prices), 5-7 (Max access under the new model), 5-10 (Free device policy).

## 2. The four priority decisions

### D1 — An abandoned checkout blocks an existing Free account (finding H3; 5-20 row 1)

| | |
|---|---|
| **Today** | Pressing "Subscribe" creates a subscription row in status `created` and makes it the account's current row. If the user leaves checkout, the row stays current. **C:** the account meets the "not subscribed" gate and cannot use the laws it chose as a Free account (pinned by `test_known_defect_h3_…`). **M:** a Free account has no Playground either way, so nothing visible changes there. On the billing page such an account is offered "Continue checkout" (or nothing at all while the row has no provider id); "Subscribe" returns to the same checkout; choosing the *other* plan is refused ("finish or abandon the current checkout") and the application has no way to abandon it. The row clears only when the provider reports it expired |
| **User impact** | A Free user who taps Subscribe and backs out loses the Playground they already had, with nothing on screen saying why, for as long as the provider keeps the checkout open (how long: not observed). It punishes exactly the users who were considering paying |
| **Settled** | Nothing specific. 5-20 row 1 proposes "Free" for `created` and `authenticated`; unapproved |
| **Decision needed** | (a) Does a checkout that was never paid leave the account exactly as it was (Free)? (b) May the user abandon an open checkout from the billing page (so they can pick the other plan, or simply clear it)? (c) Is `authenticated` — mandate authorised, first charge not yet confirmed — treated the same? |
| **Recommendation** | (a) **Yes: approve row 1 for `created`.** A row that has never carried a verified payment grants nothing and takes nothing away. (b) **Yes, a "Cancel this checkout" action** on the billing page beside "Continue checkout": it cancels the unpaid subscription at the provider and archives the local row. (c) **Free access, but not "abandoned":** show "We're confirming your payment" (the proposal's note e1), keep the row, offer no second Subscribe. A first payment may be in flight |
| **Screens / actions** | Playground home and gate, Act head, Add sheet, Today and Calendar items (C); billing page: Continue checkout, new Cancel-checkout action, the plan cards; `/billing/subscriptions/create` |
| **Depends on the provider** | Whether an unpaid `created` subscription can be cancelled, and when the provider expires one on its own |

### D2 — Paid → Free selection (finding H2; 5-4 approved, its trigger in 5-20)

| | |
|---|---|
| **Today** | Adds made while paying never write the choice ledger. **C:** when a subscription ends (terminal row, no longer current) the account is "RecallC Free" with **0 of 3 choices used, every paid-era law still in the Playground and fully learnable, and three more addable** (pinned by `test_known_defect_h2_…`). **M:** the same account meets the Free gate; its laws and progress stay stored |
| **User impact** | As built, activating `choices` would give every lapsed subscriber the paid product for nothing, permanently — and whatever corrects that later would take laws away from people who have been using them. The approved rule (5-4) exists; the mechanism does not |
| **Settled** | 5-4 (what is preserved and that the user selects); 5-19 (consume on save); 5-21 (no backfill); the Free rules of §1 |
| **Decision needed** | (a) **When** the account becomes Free — 5-20 rows 3, 5 and 6 (at the end of the verified paid-through period). (b) **What is usable before the user selects.** (c) **How selection is offered.** (d) An account that was **never Free** (subscribed first). (e) What Today and Calendar show for the laws left out |
| **Recommendation** | (a) Approve rows 3, 5, 6: paid until the verified paid-through date, then Free. (b) The proposal's note (d): laws the account chose as a Free account (ledger rows) stay fully usable; every other law becomes **read-only with its data kept** — Bare Act readable, progress and schedule stored, no Learn or completion — until chosen. (c) **Not forced, not automatic:** the Playground home lists the paid-era laws first under "Choose up to *n* laws to keep learning"; a choice is spent only on the user's confirmation, with the confirmation stating that it is permanent. No deadline. (d) Three choices, like any Free account (5-21: nothing is backfilled). (e) Items for locked laws stay visible as locked rows that lead to the selection / plans, never into Learn — the pattern already used for ended accounts. On paying again every law is usable at once and the ledger is untouched (row 15) |
| **Screens / actions** | Playground home (new selection state), Manage laws, Act head and Add sheet for a locked law, Learn and completion routes (refusal), Today, Calendar, Profile card, header label; the ledger write on confirmation |
| **Depends on the provider** | Only for "when": the verified paid-through date (D5) |

### D3 — Paused and halted accounts: Resume / Manage lead to no recovery action

| | |
|---|---|
| **Today** | **Halted** (payment retries exhausted) and **paused**: no Playground (read-only home, items on Today / Calendar as links), indefinitely, whatever was paid for. Their "Resume Playground" / "Manage subscription" links open the billing page, which **offers nothing**, and every billing route refuses them: Subscribe → `change_required`, Change → `state`, Cancel → `unpaid_cancel` (`M8-Ra-billing-matrix.md` §2.3). The same is true of **pending** (retry in progress; it keeps its existing laws) and **authenticated**. The application has no pause feature, so a paused row can only come from an action at the provider |
| **User impact** | A user whose card failed is told to "Resume" and lands on a page with no button. They cannot retry, cannot change the payment method, cannot cancel and cannot subscribe again; a mandate may still exist at the provider. The only way out is support or the provider's own emails. This is the state most likely to produce complaints and chargebacks |
| **Settled** | These accounts get no plans stage (M5 Q8). Nothing about recovery or cancellation |
| **Decision needed** | (a) **Access** — 5-20 rows 7–10: paid until the verified paid-through date, then Free, instead of an indefinite block. (b) **Cancel** for halted, paused and pending accounts (matrix Q-C). (c) **Recovery**: retry / update the payment method (halted, pending); resume (paused) (matrix Q-B). (d) What the links are called |
| **Recommendation** | (a) **Approve rows 7–10.** The period was paid for; after it, a former payer should not be worse off than someone who never paid. (b) **Yes — "Cancel subscription" for halted, paused and pending.** It ends the provider subscription, the row becomes terminal, and the account is Free and can subscribe again. This is the one action that guarantees nobody is trapped. (c) **Offer recovery only through a provider-hosted page, and only once verified**; until then the page says plainly what happened and what the user can do (cancel here; payment method through the provider's link or email). **Paused: no self-service resume** — the page says the subscription was paused and gives the support contact, plus Cancel — until it is decided who may pause. (d) Rename "Resume Playground" to "Manage subscription" wherever no resume exists, and reword the ended-period title "Your Playground is paused", which now collides with the real paused state |
| **Screens / actions** | Billing page (new state panels, Cancel for three more statuses, a possible provider link); `/billing/subscriptions/cancel`; Playground home, Act head, Add sheet, Today, Calendar, Profile card (link labels, titles); header label; **Browse's Free-only copy for a paused account** (the open point left by M8-Ra — it follows whatever (a) decides) |
| **Depends on the provider** | Whether cancellation is accepted in `halted`, `paused` and `pending`; whether a hosted "update payment method" page exists and what it does to a halted subscription; the retry schedule. None observed |

### D4 — Stored period elapsed, provider row still `active` (finding H7)

| | |
|---|---|
| **Today** | The Playground treats the account as ended (read-only, "Your Playground is paused"), while the billing page shows what it shows any active subscriber: **Cancel at cycle end** and the plan change. Requested, Cancel asks the provider to cancel at cycle end and Change asks it to change plan now. "Subscribe" is refused (`change_required`) with no provider call. No stored shape lets Subscribe start a second subscription beside a live row (matrix §2.1). The application asks the provider for a row's state on webhook events, at checkout completion, when subscribing again after a terminal row, and on a support-triggered action — never when a page is opened |
| **User impact** | Two possibilities the application cannot tell apart from its own data: the subscription renewed and we missed the event (a paying user is locked out), or it ended and we missed that (the page offers actions on something that no longer exists). Either way the two screens contradict each other |
| **Settled** | Owner, 2026-11-27: the elapsed date alone establishes nothing; no duplicate-subscription path; cancellation is not hidden on the date alone |
| **Decision needed** | (a) Should the application **ask the provider** before choosing what to show (matrix Q-A)? (b) What happens when that lookup fails. (c) Whether the plan change stays available while the state is unconfirmed. (d) Confirm the two safeguards as standing rules |
| **Recommendation** | (a) **Yes.** When a live row's stored period has elapsed, the billing page and the Playground gate first run the existing provider reconciliation (the support action's code path, under its per-subscription lock, rate-limited). The provider's answer then decides: still active → dates corrected, the account is simply active; ended → the row is archived and D2 applies; pending / halted → D3 applies. (b) **A failed lookup changes nothing on the billing page** — Cancel stays — and shows "We couldn't confirm your subscription just now." For access, the proposal's note (e2): access that was verified is kept for a bounded time (proposed 7 days) so an outage on our side never locks out a payer; after that the state's own row applies. (c) **Cancel always available; a plan change only after a successful lookup in the same request** — changing the plan of a subscription whose state we could not confirm risks a charge the user did not expect. (d) Confirm, with tests that pin them: Subscribe is never offered or accepted while a live row is current; Cancel is never hidden because of a date |
| **Screens / actions** | Billing page (lookup before render, the notice, plan change conditional); `/billing/subscriptions/change`, `/cancel`, `/create`; Playground home and gate, header label |
| **Depends on the provider** | Everything in (a): what the provider reports for such a subscription, and how quickly |

## 3. Every subscription state

The "Proposed" column is the 5-20 table (`ENTITLEMENT_DECISIONS.md` §3) — **a proposal, nothing in it approved**. "Paid-through" means verified payment coverage, not the provider's dates.

| # | State (reach) | Today | Proposed (5-20 row) | Decision | Recommendation | Screens / actions |
|---|---|---|---|---|---|---|
| 1 | No subscription row (P) | **M:** Free gate, Subscribe on billing. **C:** Free, 3 choices | — | settled | — | — |
| 2 | `created`, checkout open or reservation (P) | **M:** as Free; billing: Continue checkout or nothing. **C:** hard gate — H3 | Free (row 1) | **D1** | Free; add Cancel-checkout | Playground home / gate, billing |
| 3 | `authenticated` (P) | no Playground; billing offers nothing; all routes refuse | Free (row 1) | **D1(c)** | Free with "confirming your payment"; no second Subscribe | billing, gate |
| 4 | `active`, period open (P) | full use and adds; billing: change plan, Cancel at cycle end | same (row 2) | settled | — | — |
| 5 | `active`, cancel at period end (P) | full use until the date; billing offers the plan change, not Cancel. After the date: read-only while the row stays current | paid until the paid-through date, then Free (row 3) | part of **D2(a)** | approve | home, Profile card, billing |
| 6 | `active`, downgrade scheduled (P) | full use; change applies at cycle end | — | settled (audit §15) | — | — |
| 7 | `active`, stored period elapsed (P) | read-only Playground; billing: Cancel and plan change; Subscribe refused — H7 | — (not a 5-20 row) | **D4** | ask the provider first; safeguards as rules | billing, gate |
| 8 | `pending`, period open (P) | existing laws usable, no adds; billing offers nothing; routes refuse | paid until the paid-through date — adds allowed (row 11) | 5-20 row 11; **D3(b, c)** | approve; add Cancel; recovery through the provider when verified | home, Add sheet, billing |
| 9 | `pending`, period elapsed (P) | read-only; billing offers nothing | Free — stricter than today (row 12) | 5-20 row 12 (the proposal asks for explicit confirmation) | approve: a retry that has not succeeded is not payment | home, billing |
| 10 | `halted`, period open (P) | no Playground, indefinitely; billing offers nothing | paid until the paid-through date, then Free (row 7) | **D3** | approve; Cancel; plain explanation | home, Today, Calendar, billing |
| 11 | `halted`, period elapsed (P) | the same | Free, with a payment-problem notice and retry / resubscribe (row 8) | **D3** | approve | the same |
| 12 | `paused`, period open (P) | no Playground, indefinitely; billing offers nothing; Browse shows the Free-only copy | paid until the paid-through date, then Free; continues on resume (row 9) | **D3** | approve; Cancel; no self-service resume yet | the same, and Browse |
| 13 | `paused`, period elapsed (P) | the same | Free (row 10) | **D3** | approve | the same |
| 14 | `cancelled`, paid-through still ahead (P; only by an action at the provider — the application cancels at cycle end only) | the row is archived at once; **M:** Free gate, **C:** H2 | paid until the paid-through date, then Free (row 4). In-row question: an immediate cancellation takes effect (i) now or (ii) at period end | 5-20 row 4 | approve, with (ii): what was paid for is honoured | home, Profile card, billing |
| 15 | `cancelled`, `expired`, `completed`, nothing paid ahead — a former payer (P) | row archived; **M:** Free gate, laws and progress stored. **C:** 0 of 3 used, every law usable — H2 | Free (rows 5, 6) | **D2** | selection as in D2 | home, Manage laws, Act head, Today, Calendar |
| 16 | Terminal status on a row that is still current (**S**) | read-only "Your Playground is paused" home — the state the eighteen expired-cohort test modules pin; the service never leaves this shape — H1 | — | **D6** below | retire the fixture with D2; keep no page that no real account can reach | the expired cohort's pages and tests |
| 17 | Full refund or lost dispute on a payment (P) | read-only at once, matched against the current period only | only that payment's coverage is revoked; access recomputed, Free as the fallback (row 13) | 5-20 row 13 | approve | home, billing |
| 18 | Partial refund, open dispute (P) | no access change | no change until resolved (row 14); separate treatment is gap 5-24 | 5-24 | approve as the interim rule; decide 5-24 separately | — |
| 19 | Subscribing again after an ended subscription (P) | new row; old row archived; late events for the old row do not touch the new one | same (row 15) | settled in behaviour (B1-B03) | — | — |
| 20 | Legacy Max, `active` (P) | full use; billing: Schedule Plus, Schedule Pro, Cancel | — | 5-7 (not M8-Rb) | — | — |

## 4. Further decisions the table depends on

| # | Decision | Why it matters | Recommendation |
|---|---|---|---|
| **D5** | The provenance rule of 5-20(a): verified payment coverage is the only source of paid access; provider dates are a schedule only; missing-charge behaviour (notes e1, e2) | Rows 5, 8–15 and D4 all turn on "paid-through". Without it the dates the application stores decide access | Approve, with e1 (first payment unconfirmed → Free with a notice) and e2 (verified access kept through a failed lookup, bounded) — subject to verification against the provider before anything ships |
| **D6** | H1: the read-only "expired" state is a fixture shape | If ended subscriptions become Free (D2), that page and its tests describe nothing real | Retire it with D2; until then leave it untouched |
| **D7** | Which model the transitions apply to | Under `monthly`, "Free" means no Playground at all, so rows 10–15 would change what production users see today | **Transitions behind the `choices` flag only; `monthly` keeps today's dispositions.** The billing-page changes of D3 and D4 are the exception: they are model-independent and would reach production on deployment — decide them knowing that |
| **D8** | Notices and checkout outcomes: payment problem, grace, checkout verifying / success / failure / cancelled (Coverage Pack D1–D5, D10: "Proposed" or "Awaiting owner decision"); 5-3; 5-24 | They are the on-screen side of D1, D3 and D4 | Decide the copy with the rows above; build only the notices those rows need. No grace period beyond e2 unless decided |
| **D9** | Paused Browse wording (left open by M8-Ra) | Under rows 12–13 a paused account is paid until its date and Free after | Browse follows the same account predicate as the header; bundled into M8-Rb |

## 5. What M8-Rb would then contain, and what it waits for

1. Decisions D1–D7 recorded against the owner's direct answer; D8 and D9 can follow.
2. Verification against the provider's documentation and recorded test events for every "Depends on the provider" line — **before** implementation of that line. This needs a provider test mode and is not possible on the local fixtures used so far.
3. B1 (PR #230) accepted, since the resolver changes sit on it.
4. Then: an implementation plan for review, the four `test_known_defect_*` tests reversed as each defect is fixed, the expired cohort re-pinned or retired (D6), a new billing matrix, and the read-back across both models.

Activation of `choices` additionally waits for 5-6b, 5-13 and the fixes for H2 (D2) and H3 (D1).
