# M8-Ra — Subscription and device edge states, safe presentation · milestone and evidence record

| Item | Value |
|---|---|
| Branch / PR | `pg-m8ra-edge-states` (worktree `pg-m8ra`), stacked on the M8-S head `6668f50` (PR #247); draft PR against `pg-m8s-shared-style` |
| Authority | M8-R plan approved by the owner on 2026-11-27 after two forwarded reviews, with the boundaries of §1. **The approval authorises implementation; it is not an acceptance of this batch** |
| Carried items closed here | the plans-stage title for paid holders (M5); the expired Act head's billing link marked as a sheet opener (M2 B12); the device-blocked Add sheet's heading (M2 observation) |
| Baseline | M8-S head (edge-state source identical to `079257e`) — `m8ra/01-baseline-67c7101/` |
| Candidate | source `2270d77`; tests `97edd4e` — `m8ra/02-candidate-2270d77/` |
| Tooling | `m8/tools/readback_m8.py`, `diff_readback_m8.py`, `serve_states_m8.py`, `billing_matrix_m8.py`, `probe_style_m8s.py`, `click_resume_m8.py` |
| Flags | `PLAYGROUND_TIER_MODEL` `monthly` (default); `choices` exercised without activating it. No provider configured |

**Status: candidate with local evidence. Not accepted.** M8-Rb (transitions) and every billing-action change stay held. No merge, deployment, staging write, payment operation or `choices` activation.

The record, the evidence and the read-back are in this one file (as for M7b); the test changes are in `M8-Ra-test-changes.md`; the billing matrix asked for in place of a billing change is `M8-Ra-billing-matrix.md`.

## 1. Boundaries (owner, 2026-11-27)

- Presentation, copy and GET link targets only. No entitlement, ledger, device-policy or migration change; `entitlements/service.py`, `subscriptions/service.py`, `subscriptions/policy.py`, `devices/service.py` and the roster repository are untouched.
- **Billing-action boundary.** On `/billing/subscriptions` no action is added, removed, hidden or re-targeted and no subscription route changes. One exception, on the plans stage only: a *pending* account is not shown the plan-change form the server refuses; its Manage link stays and the server's rejection is unchanged and tested.
- **H7 held.** With the stored period elapsed and the provider row still `active`, the billing page is left exactly as it is: an elapsed stored date does not establish that the provider subscription has ended.
- Paused items on Today and Calendar are links to the existing Resume flow only; no learning or completion write becomes possible, tested by direct requests with a before / after comparison of stored values.
- Plans-stage copy is neutral: no sentence about when a change takes effect.
- Device copy follows the registration predicate (active *or* pending).
- Every state is tagged **P** (production-reachable stored shape) or **S** (synthetic fixture). Neither proves provider behaviour.
- Under `monthly`, anything not listed in §2 renders byte-for-byte as before.

## 2. What changed

| # | Change | Where |
|---|---|---|
| G1 | **Plans stage for a current subscriber.** Title "Change your Playground plan" and one line "You’re on RecallC {Plan}." instead of the Free gate's "Your RecallC account already includes the complete Constitution." Nothing about timing. A legacy Max holder sees a disabled "Max · Current plan" card with no price. A pending holder sees "Plan changes are not available while a payment retry is in progress." and "Manage subscription" instead of the form. The Free title and the create form are unchanged | `playground/access.py` `_gate_page`; `playground_gate.html` |
| G2 | **One rule for sheet openers.** A link is marked `data-pg-sheet` only when it leads to an Act's Add dialog (`is_add_sheet_href`). "Resume Playground" → billing on the Act head, the Playground partial and read-only home cards is now an ordinary link. Measured in a browser on a paused account's Act head (`resume-click.json`): at baseline the click first fetched `/billing/subscriptions` as a sheet and then navigated; on the candidate it navigates directly, with no such fetch | `playground/urls.py`; `playground/view.py` (`_state`, `LawCardView.opens_sheet`); `partials/playground.html` |
| G3a | **Paused header.** "Playground subscription paused" instead of "RecallC Free" (status-based, also once the stored period has elapsed, as for halted) | `entitlements/dependencies.py` `snapshot_is_paused_subscriber`; `web/shell.py` |
| G3b | **Paused Add sheet.** The gate's title and line ("Playground subscription paused" / "Your laws and learning progress are saved.") instead of "Add {Act} to {Month}?" and a capacity line above a Resume button | `playground/routes.py` `_add_page_context` |
| G3c | **Paused Today and Calendar.** The Playground items a halted or expired account already sees. Today: the expired cohort's binder — each item is a link to `/billing/subscriptions` labelled "Resume Playground". Calendar: **every** Playground chip that points into the Playground is rewritten to that link (`reconcile_paused_playground_calendar_chips`). That is stricter than the halted / expired reconcile, which rewrites due and revision chips and leaves the others on the Act-progress page (itself gated) | `playground/schedule.py`; `auth/routes.py` (Today); `web/app.py` (Calendar) |
| G3d | **Paused Profile identity line.** "Signed in with Google", as for halted and expired, instead of "RecallC Free · Constitution learning included". Settings prints the shell label: "Playground subscription paused · Signed in with Google" | `auth/routes.py` (Profile) |
| G4 | **`?stage=plans` for paused / halted / ended accounts** redirects (303) to `/billing/subscriptions` instead of being silently ignored. Under `choices`, the Calendar's locked entry for these accounts reads "Personal tasks need an active subscription" with the account's own Resume / Manage link, instead of "Personal tasks are part of Plus · See plans ›" | `playground/routes.py`; `web/app.py`; `calendar.html` |
| G6 | **No month wording under `choices`** on the Profile card ("Your Playground is open.", "n laws in your Playground", "Resume to keep learning your laws.") and on the billing page (the explanatory paragraph; "Unlimited Playground laws"). `monthly` strings unchanged | `playground/view.py`; `subscriptions/routes.py` (strings only) |
| G7 | **Device limit.** The gate, the Act-head note and the Add sheet state the configured limit carried by the snapshot (2 today). The device-blocked Add sheet shows the gate's title ("Device limit reached") instead of an add confirmation over a "Manage devices" button | `playground/view.py` `gate_view(device_limit=)`; `playground/access.py`; `playground/routes.py` |
| G8 | **Revoked device gate.** Adds "It was removed from this account’s registered devices." and "Your Constitution access and saved progress are unaffected."; second action "Contact support" when a support address is configured, otherwise "Back to Constitution". No promise that the device can be registered again, no instruction to clear data | `playground/view.py`; `playground/access.py` |
| Q8 | **Devices page lede**, generated from the registration predicate. Subscribed (active or pending): "…registered the first time you use the Playground on it while your subscription gives Playground access, including while a payment is being retried." Otherwise: "A device is registered only when the Playground is used on it while a subscription gives Playground access. This account has no such subscription now, so no device is being registered. Devices registered earlier stay listed here and can be removed." The "n of 2 devices" count is shown only when registration applies or a device is still listed | `devices/routes.py`; `devices.html`; `playground/access.py` `device_registration_applies` |

Proposed copy that is new in this batch, for review (Q12): every quoted string in rows G1, G3b's reuse of the gate copy, G4, G6, G8 and Q8.

### Left as it was, on purpose

- `snapshot_is_free_account` still counts a paused account as Free (Browse's Free-only copy, M3). The header no longer does. Changing it would alter accepted Browse pages; recorded as an open point.
- The billing page and every subscription route.
- The expired, halted and paused read-only pages beyond these defects (no prototype restyle while 5-20 may turn all three into Free).

## 3. Findings recorded, not fixed

**Activation blockers** (each pinned by a `test_known_defect_*` test that documents the defect and must be reversed when it is fixed):

- **H2 — paid → Free selection missing.** Under `choices` a former paid account is RecallC Free with 0 of 3 choices used; every paid-era law stays in the Playground and learnable; more can be added. Contrary to approved 5-4.
- **H3 — an abandoned checkout removes Free access.** Under `choices` a `created` subscription row stays current, so a Free account that starts and leaves checkout meets the hard gate and cannot use the laws it chose, until the provider expires the row.

**Held:**

- **H1.** The read-only "expired" state the expired cohort tests pin is a terminal status on a row that is still current (**S**). The service marks a terminal row not-current; in that shape (**P**) the account meets the Free gate under `monthly`.
- **H7.** Elapsed stored period, provider row still `active`: read-only Playground, ordinary current-plan actions on the billing page. Unchanged. See `M8-Ra-billing-matrix.md`.

**From the billing matrix** (execution against a mocked provider client; `M8-Ra-billing-matrix.md`):

- No stored shape lets "Subscribe" start a second subscription beside a live one: the create route answers `change_required` without calling the provider.
- **Halted, paused, pending and authenticated accounts are offered nothing on the billing page, and every billing route refuses them.** Their "Resume Playground" / "Manage subscription" links — including the ones this batch now sends there instead of dead-ending elsewhere — lead to a page with no action. Whatever recovers such a subscription happens at the provider; it is not offered in the application.

**Other observations:**

- For halted and expired accounts, Calendar chips that are not due or revision chips still link to `/playground/laws/{law}` (Act progress), which serves the gate page. Unchanged here; only the paused account's chips were made Resume links throughout, because that was the condition of its approval.
- The order of law cards on a read-only home is not stable between two renders of the same account (a tie the page does not break); seen as a difference between two baseline runs.
- Body-wide probes of Today, Calendar and the Bare Act reader show the site-wide grey labels under 4.5:1 that `M8-S.md` §5 lists for Profile, Devices and the phone Calendar. Unchanged, outside this batch.
- **A second date-dependence in existing tests.** The family modules share `tests/test_browse_laws_family.py::STATES`, whose "expired" period ends 80 days before the *real* date, while the suite pins the entitlement clock to 2026-09-16 (`tests/conftest.py`). From 2026-12-06 that period no longer lies in the past of the pinned clock, and the tests that rely on that state resolving as "paid period ended" can be expected to fail. Not changed here; flagged for a separate fix together with the Calendar test of `M8-S.md` §3. The new module of this batch measures every period from the pinned clock.

## 4. Tests

New `tests/test_edge_state_family.py` — 100 tests (E01–E07 and the four known-defect tests); the list is in `M8-Ra-test-changes.md` §1. Twelve existing modules were re-pinned, one assertion at a time, none weakened (§2 of that file). One of the re-pins **reverses an older rule**: T28, "a paused account's Today lists nothing from the Playground", replaced by the approved Q5(c); what T28 protected — no way into Learn for a paused account — is still asserted, and the direct-request tests of E05 go further.

| Run | SHA | Result |
|---|---|---|
| Related modules by keyword, local, before the re-pins | working tree | 2735 passed / 168 skipped / 21 failed — 20 assertions of the old behaviour (re-pinned) and the date-dependent test below. The keyword selection missed one affected test, found by the full run |
| Full suite, local | `97edd4e` | **4425 passed / 177 skipped / 1 failed** (991.8 s) |
| Full suite, local, on the pull-request head | `8f555b8` (records and tools only since `97edd4e`) | 4425 passed / 177 skipped / 1 failed (1009.9 s) — the same test |
| CI `workflow_dispatch` | `97edd4e` tree | __CI__ |

The one local failure is `tests/test_phone_plus_calendar_screen5.py::test_phone_plus_calendar_overdue_done_and_future_constitution`, the date-dependent test described in `M8-S.md` §3: it fails on the untouched M7b head too from the 24th of the month. Counting it, this batch adds 100 tests and changes no other result: 4325 passed at M8-S → 4425 passed, the same 1 failing.

Skipped locally: the Playwright-gated screen tests and the Postgres integration tests; counted as skipped, not passed.

## 5. Read-back: baseline against candidate

`m8ra/01-baseline-67c7101/readback.json` and `m8ra/02-candidate-2270d77/readback.json`: 13 subscription states and two device states × two tier models × 13 pages. `readback-diff.json` lists every row whose page body or recorded fields changed. Two renders of the same state are identical after request tokens, generated ids and clock times are removed, except for the card-order tie noted in §3.

**254 of 362 rows are identical; 108 changed.** Every changed row belongs to a change of §2:

| Page | `monthly` — states whose page changed | `choices` — states whose page changed | Because |
|---|---|---|---|
| Devices | all 15 | all 15 | Q8 (the lede; the count line for accounts with neither registration nor a device) |
| Plans stage | Plus, Max, pending, cancel-at-end, scheduled downgrade (title); paused, halted, halted-elapsed, fixture-expired, ended-active (303 to billing) | the same | G1, G4 |
| Playground home | halted, halted-elapsed, fixture-expired, ended-active (cards no longer marked as openers); device-revoked (gate lines); paused | the same | G2, G8, G3 |
| Act head, law outside the roster | fixture-expired, ended-active, device-revoked, paused | the same | G2, G7, G3 |
| Add sheet, law outside the roster | fixture-expired, ended-active (opener), device-limit, device-revoked (title), paused | the same | G2, G7, G3 |
| Act head and Add sheet, law in the roster | paused | paused | G3 |
| Today | paused | paused | G3c |
| Calendar | paused | paused; halted, halted-elapsed, fixture-expired, ended-active (locked entry) | G3c, G4 |
| Profile | paused | paused; Plus, Max, cancel-at-end (card wording) | G3, G6 |
| Billing | paused (header label only) | paused; Plus, cancel-at-end, fixture-expired, former-paid, Free (label strings) | G3, G6 |
| Manage laws, Settings | paused (header label only) | paused | G3 |

**Unchanged under `monthly`, byte for byte:** every page of the Free, former-paid and abandoned-checkout accounts except Devices; every page of Plus, Max, pending, cancel-at-end and scheduled-downgrade except Devices and the plans stage; Today, Calendar, Profile, Settings, billing, Manage laws and the in-roster Act head and Add sheet of halted, fixture-expired and ended-active accounts. **The billing page's forms and links are the same in every row** (`forms` is never among the changed fields); for the paused account the only difference on it is the header label.

A first candidate run showed two further rows (cancel-at-end home and Manage laws under `choices`) differing in the page body only; three re-renders of that account matched the baseline, and the re-run recorded here does not show them — the same render-to-render instability as the card-order tie of §3.

## 6. Verification matrix

**C** capture · **R** read-back row · **T** automated test · **D** direct-request test with stored values compared before and after · **K** characterisation of a known defect · **cf** carried from the accepted SHA. Reach: **P** / **S**.

| State | Reach | Header | Home | Plans stage | Act head | Add sheet | Today / Calendar | Profile | Billing | Devices |
|---|---|---|---|---|---|---|---|---|---|---|
| Active Plus (control) | P | R identical | R identical | **C** T — PASS | R identical | R identical | R identical | R identical (`choices`: **C** T, G6) | R identical (`choices`: labels, **C** T) | R T (lede) |
| Active Max | P | R identical | R identical | **C** T — PASS | R identical | R identical | R identical | R identical | R identical | R (lede) |
| Pending | P | R identical | R identical | **C** T **D** — PASS (no form; direct change refused, stored values identical) | R identical | R identical | R identical | R identical | R identical | R T — registers a device |
| Paused | P | T **C** — PASS | R | T — 303 | **C** T — PASS (plain link) | **C** T — PASS | **C** T **D** — PASS | R T | R — header label only | T — not registered |
| Paused, period elapsed | P | T — PASS | — | T — 303 | — | — | T **D** — PASS | — | — | — |
| Halted, open period | P | R identical | R (cards: no opener) | T — 303 | R identical | R identical | R identical (`choices`: locked entry, T) | R identical | R identical | T — not registered |
| Halted, period elapsed | P | R identical | R (cards: no opener) | T — 303 | R identical | R identical | R identical | R identical | R identical | — |
| Fixture expired (terminal, current) | **S** | R identical | R (cards: no opener), **C** | T — 303 | **C** T — PASS (plain link) | R (plain link) | R identical (`choices`: locked entry, T) | R identical | R identical | T — not registered |
| Ended period, row still `active` | P | R identical | R (cards: no opener) | T — 303 | R (plain link) | R (plain link) | R identical | R identical | **K** — unchanged; matrix in `M8-Ra-billing-matrix.md` | — |
| Former paid, `monthly` | P | **K** | **K** | — | R identical | — | R identical | R identical | R identical | T — not registered |
| Former paid, `choices` — **H2** | P | — | **K** — defect pinned | — | **K** | — | — | — | — | — |
| Abandoned checkout, `choices` — **H3** | P | — | **K** — defect pinned | — | — | — | — | — | — | — |
| Cancel at period end; scheduled downgrade | P | R identical | R identical | R (title) | R identical | R identical | R identical | R identical (`choices`: card wording) | R identical | R (lede) |
| Device limit (third browser) | P | — | **C** T — PASS (configured limit) | — | R T | **C** T — PASS | R identical | — | — | R |
| Device revoked (self-removed) | P | — | **C** T — PASS | — | R | **C** R (title) | R identical | — | — | R T — listed as removed |
| Replacement limit | P | — | T — reached; copy unchanged | — | — | — | — | — | — | — |
| Free, Devices page | P | — | — | — | — | — | — | — | — | **C** T — PASS |

"R identical" means the page body is byte-identical to the baseline in the read-back. Captures are at 390 and 1280 px; light, with dark for the plans stage, the paused Add sheet and paused Today. Two cells of the plan are narrower than planned: the fixture-expired home was captured at 1280 only, and the device-revoked Add sheet is a capture with a read-back row rather than its own test (the title rule it follows is tested for the device-limit sheet).

## 7. Frames

`m8ra/01-baseline-67c7101/frames/` and `m8ra/02-candidate-2270d77/frames/`, named `<state>-<route>-<width>-<theme>.png`.

38 frames in each folder, the same names in both.

| Frames | Shows |
|---|---|
| `plus-monthly-plans-*`, `max-monthly-plans-*`, `pending-monthly-plans-*` (390 light, 1280 light, 1280 dark) | the plans stage: the Free gate's title at baseline; "Change your Playground plan", the Max card, the pending notice on the candidate |
| `paused-monthly-add-sheet-*` (390 light, 1280 light, 1280 dark) | "Add PSS to November? · This will use 1 of your 10 law spaces…" above "Resume Playground" at baseline; the paused gate's title on the candidate |
| `paused-monthly-today-today-*` (390 light, 1280 light, 1280 dark), `paused-monthly-today-calendar-*` (390, 1280 light) | no Playground item and "RecallC Free" at baseline; the due revision as "Resume Playground" and the paused header on the candidate |
| `paused-monthly-head-in-*`, `paused-monthly-home-1280-light` | the paused header; the head's Resume link |
| `expired-fixture-monthly-head-out-*`, `expired-fixture-monthly-home-1280-light` | unchanged to the eye (the opener marker is not visible; verified by markup) |
| `device-limit-home-*`, `device-limit-add-sheet-*` | the gate; "Add PSS to November?" over "Manage devices" at baseline, "Device limit reached" on the candidate |
| `device-revoked-home-*`, `device-revoked-add-sheet-*` | the revoked gate without and with its two lines; the sheet's title |
| `free-monthly-devices-*`, `plus-monthly-devices-devices-*` | the Devices lede and count |
| `paused-choices-calendar-lock-1280-light` | the Calendar's locked entry under `choices` |
| `plus-choices-profile-1280-light`, `plus-choices-billing-1280-light` | Profile card and billing wording under `choices` |

Today and Calendar fade in; a frame taken beyond the viewport restarts the fade and comes out washed. Their frames were therefore taken as ordinary frames of a window given the page's full height (`probe_style_m8s.py --settle`). The `style-probe-*.json` files beside the frames are the probe rows of those captures; body-wide rows for Today, Calendar and the Bare Act reader include the site-wide grey findings of §3.

## 8. Not run and limitations

- **Provider behaviour: NOT RUN.** Every state is a row seeded into a throwaway local database. Nothing here shows what the provider reports, when it applies a plan change or cancellation, or what a real payment retry does. Checkout completion, failure and abandonment were not exercised; the billing matrix uses a mocked client.
- Hosted comparison: NOT RUN (staging blocked, `M5-staging-prep.md`). The roadmap's gate DV-18 stays **U** for every hosted row.
- **Browser zoom: NOT RUN.** Automated accessibility scan, screen reader: NOT RUN.
- Playwright-gated screen tests: skipped locally (not installed).
- Live speech; Google Calendar connect / disconnect: NOT RUN (not touched).
- M2's owed hosted checks for Plus, Max, expired and halted heads: NOT RUN.
- Screenshots of the expired and halted homes after M7a's capacity-line change: still not taken, except the frames listed in §7.
- The prototype's `viewer=expired|halted|paused|deviceLimit|deviceRevoked|replacementLimit` and `notice=…` frames were not compared (Q9: no restyle while 5-20 is open); DV-18 stays **U** locally for those rows too.
- The "sheet opener" fix is verified by markup and tests over every state, and by one browser click on a paused account's Act head at baseline and on the candidate (`resume-click.json`: the sheet fetch before navigation is gone). The script's "Opening…" busy state was not observed in either run by that check, so nothing is claimed about it.
- Device states were produced with separate signed-in sessions of one account on one machine.

## 9. Owner sign-off

None recorded. Sign-off is recorded only against the owner's direct answer.

## 10. Proposed roadmap entry (not applied)

`PLAYGROUND_FIDELITY_ROADMAP.md` lives on the branch of PR #218 and still lists one row, "M8 — Subscription and device edge states · proposed". It is not edited from this branch. Proposed replacement, for the owner to apply or amend there:

| Row | State |
|---|---|
| M8-S — shared style (label contrast, back link, Calendar dialog close) | built, draft PR #247, local evidence, not accepted |
| M8-Ra — edge states, safe presentation (plans-stage title, sheet openers, paused parity, `?stage=plans`, `choices` wording, device copy) | built, draft PR #248, local evidence, not accepted |
| M8-Rb — transitions and billing actions (5-20 table, paid → Free selection, abandoned checkout, checkout outcomes, notices, billing page for halted / paused / pending and for an elapsed period with an active row) | held: 5-20, 5-24, 5-3, review of `M8-Ra-billing-matrix.md`; after B1 acceptance |
| Gate DV-18 | **U** — hosted rows not run; the prototype's edge-state viewers not compared (no restyle while 5-20 is open) |
