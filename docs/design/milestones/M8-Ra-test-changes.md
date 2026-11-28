# M8-Ra — test changes

Every existing assertion that changed is listed with what it pinned before, what it pins now and the decision behind it. No assertion was removed without a replacement, and none was loosened beyond the value that changed. Authority for all of them: the M8-R plan as approved by the owner on 2026-11-27 (decisions Q4–Q8 with their boundaries).

## 1. New module

`tests/test_edge_state_family.py` — 100 tests. Every period and due date is measured from the suite's pinned clock (`tests/conftest.py::PLAYGROUND_TEST_NOW`), never from the day the suite runs.

| ID | Pins |
|---|---|
| E01 | plans stage for a subscriber: title, the "You’re on RecallC {Plan}." line, no timing words, the same change form and route; the Free title and create form unchanged; Max shown as the current plan with no price; a pending account sees no form and a Manage link, and a direct change request is refused as before with stored values unchanged |
| E02 | `?stage=plans` → 303 to billing for paused, paused-elapsed, halted, halted-elapsed, fixture-expired and ended-active accounts under both models; the Calendar's locked entry under `choices`; Free and `monthly` unchanged |
| E03 | `is_add_sheet_href`; over every state and both models, no link marked as a sheet opener leads anywhere but an Act's Add dialog; Resume links are plain links; Add and "Add back" still open the sheet |
| E04 | paused header (open and elapsed period); other headers unchanged; the paused Add sheet; paused Today and Calendar show the Playground item only as a Resume link, with no Learn link, opener or Playground form |
| E05 | **direct requests as a paused account** — Learn pages, completion, sections save, Add, Remove — are refused, and a full dump of the account's stored rows (progress, selections, overlay items, roster periods and items, the choice ledger, devices, device sessions, replacements, the subscription) is identical before and after each; the same for page views; and a guard test showing the dump does detect a modified row |
| E06 | Profile card and billing wording per model; `monthly` strings unchanged; the same billing forms under both models |
| E07 | device-limit gate, Act-head note and Add sheet state the configured limit (tested with limits 1 and 2); the revoked gate's lines, actions and absence of any promise; the Devices lede against the registration predicate (a device row is created exactly for the accounts that read the paid lede: active and pending); the count line; the replacement-limit gate is reachable and unchanged |
| K | `test_known_defect_h1_…`, `…_h2_…`, `…_h3_…`, `…_h7_…` — see §3 |

## 2. Re-pinned

| Module · test | Before | Now | Why |
|---|---|---|---|
| `test_account_family.py` · `test_f01_profile_cards_by_state[paused]` | identity line "RecallC Free · Constitution learning included" | "Signed in with Google", and "RecallC Free" absent from the page | G3: the header names the paused subscription; the identity line follows halted and expired |
| `test_account_family.py` · `test_f03_settings_identity_and_auto_plan_by_tier[paused-*]` | "RecallC Free · Signed in with Google" | "Playground subscription paused · Signed in with Google" | G3: Settings prints the shell label |
| `test_account_family.py` · `test_f05_devices_guest_redirects_and_free_sees_the_designed_empty_state` | "Your plan supports the Playground on up to 2 registered devices." / "while a paid plan is active" / "0 of 2 devices" | the unsubscribed lede; no "Your plan supports"; no count line | Q8 |
| `test_browse_laws_family.py` · `test_f03_free_predicate_matches_the_shell_label` | the Free predicate equals "label is RecallC Free" for every state | the same for every state except paused, which is asserted explicitly: predicate true, label "Playground subscription paused" | G3; Browse's predicate deliberately left as it was (`M8-Ra.md` §2) |
| `test_calendar_family.py` · `test_f04_create_entry_points_follow_the_capability[paused / expired / halted · choices]` | sheet "Personal tasks are part of Plus", link "See plans ›" to `?stage=plans`, no `/billing` | sheet "Personal tasks need an active subscription", link to `/billing/subscriptions` labelled Resume Playground (Manage subscription for halted); Free unchanged; "no ₹, no /pricing" kept for all | G4 |
| `test_devices_m4b.py` · `test_authenticated_users_can_open_devices_regardless_of_billing` | "0 of 2 devices" for an account with no subscription | no count line; "No devices registered yet." | Q8 |
| `test_expired_calendar_screen9.py` · `test_guest_free_plus_halted_paused_pending_are_not_expired_calendar` | paused: no Playground chip | paused: Playground chips present, every one linking to `/billing/subscriptions`; the expired marker still absent | G3 / Q5(c) |
| `test_halted_calendar_screen9.py` · `test_guest_free_plus_expired_paused_pending_are_not_halted_calendar` | the same | the same; the halted marker still absent | G3 / Q5(c) |
| `test_expired_today_screen8.py` · `test_guest_free_plus_halted_paused_pending_are_not_expired_today` | paused: no Playground item | paused: Playground item present, no `/playground/laws/` link on the page, a billing link present; the expired marker still absent | G3 / Q5(c) |
| `test_halted_today_screen8.py` · `test_guest_free_plus_expired_paused_pending_are_not_halted_today` | the same | the same; the halted marker still absent | G3 / Q5(c) |
| `test_playground_r6.py` · `test_t28_paused_lists_nothing_playground` → renamed `test_t28_paused_lists_playground_items_only_as_resume_links` | **T28: a paused account's Today lists nothing from the Playground** | the item is listed, as a "Resume Playground" link to billing; no `/playground/laws/` link; a direct request to the Learn page does not serve Learn | **Q5(c) reverses the earlier T28 rule.** What T28 protected — no way into Learn for a paused account — is still asserted |
| `test_request_perf_breakdown.py` · `test_calendar_paused_has_no_t9` → renamed `test_calendar_paused_reads_the_playground_schedule_like_halted_and_expired` | the Calendar request of a paused account runs no Playground stage and no Playground read | exactly the halted / expired contract: the calendar stage once, 2 reads (1 roster, 1 revision), no write | G3 / Q5(c): the chips are now read |
| `test_request_perf_breakdown.py` · `test_dashboard_paused_has_no_t9` → renamed `test_dashboard_paused_reads_the_playground_today_items_like_halted_and_expired` | the same for Today | exactly the halted / expired contract: the today stage once, 3 reads (2 roster, 1 revision), no write | G3 / Q5(c) |
| `test_halted_browse_screen2.py` · `test_guest_free_plus_expired_paused_pending_pro_max_are_not_halted_browse` | paused header contains "RecallC Free" | paused header contains "Playground subscription paused" and not "RecallC Free"; the Free summary assertion is unchanged | G3 |
| `test_signed_in_playground_gate_screen7.py` · `test_guest_plus_expired_halted_paused_pending_stay_separate` | `?stage=plans` for expired and halted serves the read-only home | 303 to `/billing/subscriptions`; still no signed-in gate stage | G4 |

## 3. Known-defect tests

These pin what happens today so that a later change is visible. **They are not passes of a requirement.** Each docstring names the rule it falls short of and says the assertion must be reversed when the defect is fixed.

| Test | Finding | Status |
|---|---|---|
| `test_known_defect_h1_the_pinned_expired_state_is_a_shape_the_service_does_not_keep` | the fixture shape serves the read-only "paused" home; the shape the service leaves serves the Free gate | held for 5-20 |
| `test_known_defect_h2_former_paid_account_under_choices_keeps_every_law_and_three_fresh_choices` | 0 of 3 choices used, paid-era laws learnable, more can be added | **activation blocker** (5-4 not built) |
| `test_known_defect_h3_an_abandoned_checkout_removes_free_access_under_choices` | a `created` row hard-gates a Free account | **activation blocker** (5-20 row 1) |
| `test_known_defect_h7_billing_page_for_an_elapsed_period_with_an_active_row_is_unchanged` | the billing page offers the ordinary current-plan change for an account the Playground treats as ended | held: no billing change without a reviewed matrix |

## 4. Not weakened

No test was deleted, skipped or marked expected-to-fail. The two request-timing tests were made stricter than a bare "stage present": they hold the paused account to the read counts of the halted and expired accounts, with no write.

## 5. Corrections of 2026-11-28 (not changes of this batch's behaviour)

The date-dependent and stamp-dependent tests found on 2026-11-28 were corrected on the M8-S branch and merged here at `0f36525`; the list, the cause of each and the evidence are in `M8-S.md` §3.1 and `m8/date-sweep/`. Two modules this batch had re-pinned are among those touched — `test_browse_laws_family.py` and `test_account_family.py` — and only in one respect: the shared subscription periods are measured from the suite's pinned clock instead of the real date. No assertion listed in §2 changed. The new module of §1 showed no failure at any simulated date.
