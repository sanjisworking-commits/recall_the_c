# M7a — test changes (branch `pg-m7a-playground-home`, PR #245)

Every assertion changed by M7a, with the decision it follows. No assertion was weakened: each re-pinned line still checks the same thing for the decided value, and where a check moved it gained a companion assertion. Source commits `4bc0fd4`, `60a6f37`, `0829d45`, `ea47eab`, `773492f`; tests commits `fe554c5`, `18e9f02`, `fa05a2c`, `8066ef7`, `09bc48d`, `c89dd05`.

## A. Mechanical asset re-pin (`fe554c5`)

| Pin | Was | Now | Modules |
|---|---|---|---|
| `playground.css?v=` | `pg57` | `pg58` | 56 |

The bump follows the stylesheet edit in the same milestone: the home rules re-keyed to the shared marker, the M7a block, the capacity-cell rule. No other asset changed.

## B. The home rules key on the shared open-Playground marker (Q7) — 6 assertions

| File | Was | Now |
|---|---|---|
| `test_expired_playground_screen6.py` | `'data-plus-playground="desktop"' in css` | `'data-open-playground="desktop"' in css` |
| `test_phone_plus_playground_screen3.py` | `"[data-plus-playground-phone]" in phone_block` | `"[data-open-playground-phone]" in phone_block`, plus `"[data-plus-playground-phone]" not in phone_block` |
| `test_phone_plus_playground_screen3.py` | two rule look-ups by `.pg-home-grid[data-plus-playground="desktop"] h1.plus-pg-month {` and `… .pg-month-strip {` | the same two look-ups by `[data-open-playground="desktop"]`; the property checks (`font-size: 34px`, `display: none`) unchanged |
| `test_phone_shared_section_picker_screen1.py` | `"[data-plus-playground-phone]" in plus_home` | `"[data-open-playground-phone]" in plus_home` |
| `test_plus_playground_screen6.py` | `'data-plus-playground="desktop"' in css` | `'data-open-playground="desktop"' in css`, plus `'[data-plus-playground' not in css` |

Unchanged: every assertion that active Plus **renders** `data-plus-playground="desktop"` / `data-plus-playground-phone`, and that halted, expired, Pro, Free and guest pages do not. The Playwright-gated tests still locate the Plus home by its own marker.

## C. Section headings are view fields (Q3 / Q4) — 2 assertions

| File | Was | Now |
|---|---|---|
| `test_plus_playground_screen6.py` (two tests) | `"Removed this month" in` the template source | the template prints `{{ home.removed_heading }}`; `PlaygroundHomeView`'s default for it is `"Removed this month"` (and `"In Playground this month"` for the active heading); one of the two tests also asserts the rendered page contains "In Playground this month" |

The string left the template so that the `choices` branch can print "Previously chosen — add again anytime"; under `monthly` the rendered text is the same, which `test_f02_monthly_pages_keep_the_month_model` pins on the rendered page.

## D. Pro shares the open-Playground home (Q7) — 1 test row

`test_plus_playground_screen6.py::test_halted_expired_pro_free_guest_are_not_plus_screen_06`, Pro section.

| Was | Now |
|---|---|
| `'class="pg-home-title">Playground</h1>' in pro_html or ">Playground<" in pro_html`; `"To learn" in pro_html or "Your September Playground is empty" in pro_html`; `pro_html.count('class="RosterCapacity"') == 2` | Pro carries `data-open-playground="desktop"` and `data-open-playground-phone`; never `data-plus-playground-phone`; "Your September Playground is empty"; exactly one capacity block; `data-roster-limit="30"`; halted and expired pages carry no open marker |

The two `or` forms are gone (each now asserts one thing). The assertions that Pro does **not** carry the Plus marker and does not read "RecallC Plus" are unchanged.

## E. New module

`tests/test_playground_family.py` — 58 tests.

| Row | Covers |
|---|---|
| F01 | Free, Plus, Pro, Max under `choices`: empty home, populated home, Manage laws, re-add confirm, Remove and Act progress print no month phrase and no link to the rollover route; headings "Laws" / "In Playground" / "Previously chosen — add again anytime"; "Add again"; the rollover route still redirects to Manage laws |
| F02 | Plus, Pro, Max under `monthly`: month title, "Manage {Month}", "Playground month", "In Playground this month", "Removed this month", three rollover links on the home and one on Manage laws, "Add back", today's rule line, "Remove from {Month}", the Act badge, rollover page 200 |
| F03 | RecallC Free counter 0 → 3 with the remaining line and the phone strip; at 3 of 3 the limit paragraph (exact text), one upgrade action → the plans stage, no price; removal keeps the ledger, the legend reads "previously chosen · add again anytime · choice still used"; a fourth law stays refused; re-add confirm copy; re-adding leaves the ledger unchanged; the page's own Add confirm states the permanent choice |
| F04 | Plus / Pro / Max under `choices`: `data-roster-limit="unlimited"`, "3 laws", "Unlimited · {Tier}", phone strip, legend, no choice copy, no upgrade action |
| F05 | markers for eight signed-in states × two models; the guest gate; the read-only homes of paused, expired and halted accounts under `choices` print no month phrase, no tier word and no rollover link, and still offer "Resume Playground" |
| F06 / F07 | Manage laws and Remove under `choices` per tier (titles, rule lines, section labels, badges, buttons, no plan row); the paid re-add confirm and notice; the two copy tables for both models |
| F08 | a GET walk under `choices` (Free and Plus) leaves the period, roster and ledger tables identical |
| F09 | under both models, a second account cannot open, learn or remove a law the first account added; the first account's membership is untouched |
| F10 | stylesheet keyed on the shared marker, no `[data-plus-playground` selector left, the M7a block and the capacity-cell rule; rollover links behind `home.month_model` / `month_model`; templates never read the flag |
| F11 | `capacity_view` strings for the monthly, paid-`choices` and Free-`choices` branches |
| F12 (`09bc48d`) | the guest line under both models (no count of choices, no price, the other three steps unchanged); the "How it works" macro rendered under both models (steps 1 and 3 per model, step 2 unchanged, default argument = monthly); the template global returns the signed-in account's snapshot model under both models; the gate template calls the helper and never reads the flag |
| F13 (`09bc48d`) | Plus and Pro Add sheet under `choices`, for a new law and a re-add: eyebrow "Playground", "joins your Playground", no month, the confirm step and its form still present, no price; under `monthly` the month eyebrow and "joins this month's Playground" unchanged |

The family module derives its month words from the suite's pinned Playground clock (`tests/conftest.py::PLAYGROUND_TEST_NOW`).

## F. Context-key pin (`fa05a2c`)

`tests/test_request_perf_breakdown.py::_T8_HOME_CONTEXT_KEYS` lists the exact keys the home handler passes to its template; `open_playground` was added to the set (Q7). The equality check itself is unchanged.

The same module's `test_t8_template_bytes_match_unwrapped_render` renders `playground_remove.html` with the pre-M7a context (`law_id`, `month_name`, `short_title`). It failed on `18e9f02` with `'remove_copy' is undefined`; the template now falls back to the monthly strings (`0829d45`) and the test is unchanged.

## G. M2-R paid-sheet assertion (`09bc48d`, finding W15)

`tests/test_act_head_m2r.py::test_paid_confirm_step_is_unchanged_under_choices` (Plus and Pro).

| Was | Now |
|---|---|
| `"joins this month's Playground — learnable, verbatim." in panel` | `"joins your Playground — learnable, verbatim." in panel`; `'<p class="pg-eyebrow">Playground</p>' in panel`; `"this month" not in panel` |

The test's purpose — the confirmation step stays for Plus and Pro under `choices` because 5-14 is not approved — is unchanged: `data-pg-kind="eligible_to_add"`, no Free warning, and `data-step="confirm"` are asserted as before. Only the sentence it used to recognise the paid sheet moved to the wording recommended in the owner-forwarded review of 2026-11-16.

## H. Gate template-source pin (`c89dd05`, Q9d)

`tests/test_signed_in_playground_screen6.py::test_signed_in_pg_gate_does_not_touch_accepted_screens`.

| Was | Now |
|---|---|
| `"how_it_works()" in gate_html` | `"{{ how_it_works(pg_month_model) }}" in gate_html` |

The assertion still says the gate calls the macro. That the macro's default argument produces the monthly block is pinned by F12. The test failed on `09bc48d` (locally and in CI run 43805603278); a targeted run had not included this module — the third template-source pin the full suite caught in this milestone, after the two of §F.

## I. Not run locally

Playwright-gated tests in the re-pinned modules skip locally (Playwright is not installed); their selectors still target markers Plus keeps. They are counted as skipped, not passed.
