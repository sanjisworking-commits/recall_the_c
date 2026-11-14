# M6 — test changes (branch `pg-m6-calendar`, PR #244)

Every assertion changed by M6, with the decision it follows. No assertion was weakened: each re-pinned line still checks the same element for the decided value, the three `or` forms that could match any `/playground` link were replaced by plain assertions, and the mechanical pins only track the asset versions. Source commits `7716faa` and `ac8ff53`; tests commits `81e2fa5`, `72b8e2d` (the last `or` branch removed) and `eaec5e3` (F02 / F11 follow the visible legend).

## A. Mechanical asset re-pins (commit `81e2fa5`)

| Pin | Was | Now | Modules |
|---|---|---|---|
| `styles.css?v=` | `main93` | `main94` | 31 |
| `mobile.css?v=` | `mob112` | `mob113` | 30 |
| `playground.css?v=` | `pg56` | `pg57` | 55 |
| `calendar-signed.js?v=` | `cal2` | `cal3` | (with the pg57 modules) |

Each bump corresponds to a source edit in the same milestone: `styles.css` (the `.calendar-chip.is-overdue` rule), `mobile.css` (the generic phone block keyed on the paid marker), `playground.css` (the paid-marker re-keying, the halted phone block, the upgrade sheet), `calendar-signed.js` (the sheet handler).

## B. "Continue today's Recall →" targets Today (Q5) — 16 assertions + 3 `or` forms

| File | Lines | Was | Now |
|---|---|---|---|
| `test_signed_in_calendar_screen9.py` | 152, 242 | `href="/playground"` after `data-cal-continue-recall` / in the template | `href="/dashboard"` |
| `test_plus_calendar_screen9.py` | 244, 366 | same | same |
| `test_expired_calendar_screen9.py` | 428, 489, 734 | same | same |
| `test_halted_calendar_screen9.py` | 422, 486, 681, 784 | same | same |
| `test_phone_expired_calendar_screen5.py` | 437, 708 | same | same |
| `test_phone_expired_calendar_screen5.py` | 582 | `'data-cal-continue-recall href="/playground"' in html or ('href="/playground"' in …)` | `'data-cal-continue-recall href="/dashboard"' in html` (the `or` branch removed in `72b8e2d`) |
| `test_phone_plus_calendar_screen5.py` | 351, 586 | same as the first row | `href="/dashboard"` |
| `test_phone_expired_calendar_screen5.py`, `test_phone_plus_calendar_screen5.py` | 390, 311 | `'data-cal-continue-recall href="/playground"' in desk or ('href="/playground"' in desk and "data-cal-continue-recall" in desk)` — the second branch matched any Playground link in the section | `'data-cal-continue-recall href="/dashboard"' in desk` |

The phone today card already pointed at `/dashboard` (`cal-m-today-continue`); those assertions are unchanged.

## C. The Plus Calendar rules key on the shared paid marker (Q3) — 11 assertions

| File | Lines | Was | Now |
|---|---|---|---|
| `test_plus_calendar_screen9.py` | 391, 396, 398 | `data-plus-calendar="desktop"` in `playground.css`; `[data-plus-calendar="desktop"]:not(.is-week) .cal-si-desk` / `.calendar-grid` | `data-paid-calendar="desktop"`; `[data-paid-calendar="desktop"]:not(.is-week) …` |
| `test_plus_calendar_screen9.py`, `test_signed_in_calendar_screen9.py`, `test_phone_signed_in_calendar_screen5.py`, `test_phone_plus_calendar_screen5.py` | 429, 267, 365 (+ 59 selector constant), 572 | `:not([data-plus-calendar])` in the generic phone block | `:not([data-paid-calendar])` |
| `test_phone_plus_calendar_screen5.py` | 542 | `[data-plus-calendar="desktop"]` in the Plus phone block | `[data-paid-calendar="desktop"]` |
| `test_expired_calendar_screen9.py`, `test_halted_calendar_screen9.py` | 765, 826 | `data-plus-calendar="desktop"` in `playground.css` | `data-paid-calendar="desktop"` |

Assertions that Plus **renders** `data-plus-calendar="desktop"` and that Free / Pro / expired / halted / guest do not are unchanged (Plus keeps its marker; Pro now carries the paid marker only, which those tests never forbade).

## D. New modules

| Module | Tests | Covers |
|---|---|---|
| `tests/test_calendar_family.py` | 63 | F01 guest gate; F02 legends (six roadmap items; the "Review" item only with a review-capacity chip; week and phone unchanged); F03 markers for eight signed-in states × two models; F04 create entry points iff `can_add_personal_calendar_tasks` across eight states × two models × two flags, the sheet's copy / single action / no price / dialog semantics, the viewer and script present for every signed-in account, the API 403 unchanged and GET mutation-free; F05 CTA target on both widths; F06 footnote; F07 week smoke; F08 halted phone block mirrors the expired block and the generic phone block excludes every paid account; **F09** a gated account (Plus → halted under `choices`) still reads its entry and attachment and marks a rung revised while create and edit answer 403 and change nothing, and the viewer's Edit control is withheld; **F10** another account gets 404 for the entry, the attachment, edit and complete, a tokenless write is 403, a signed-out request 401, and the owner's entry is untouched; **F11** a past-day Constitution review renders `is-due is-overdue` in the month grid, today's `is-due` only, the legend swatch and CSS rule exist, the week card and phone bar agree; **F12** every editor-only element in `calendar-signed.js` is read behind a guard. |
| `tests/test_phone_halted_calendar_screen5.py` | 6 (1 Playwright-gated, skipped locally) | halted phone chrome under both models (markers, legend, no invented copy, GET mutation-free), month navigation as GET links, sibling states not halted-05, CSS scope (M6 block ≤ 560 px only; the expired block does not acquire the halted marker; the desktop block untouched), light + dark captures when Playwright is present. |

## D2. Family tests re-pointed after the legend finding (commit `eaec5e3`)

| Test | Was | Now | Why |
|---|---|---|---|
| `test_f02_desktop_month_legend_is_the_roadmap_list_without_capacity_chips` | asserted the six items on `.calendar-legend` only | asserts the visible toolbar legend `.cal-si-legend` = My material · Due today · + the six roadmap items, that `.calendar-legend` keeps the six, and that `styles.css` hides `.calendar-legend` for signed-in month views | `.calendar-legend` is hidden for every signed-in month view, so Q2 had been applied to a hidden element (`ac8ff53`) |
| `test_f02_legend_adds_the_review_capacity_item_only_when_drawn` | one `{% if calendar.has_review_capacity %}` in the template | two (toolbar and base legend) | same |
| `test_f11_overdue_legend_matches_the_month_grid` | read the swatches from `.calendar-legend` | reads them from `.cal-si-legend` and asserts the "Review" item is present exactly when the grid draws a review-capacity chip | same |

## E. Verification of the changed assertions (owner note, 2026-11-13)

- Each row in §B still locates the CTA by `data-cal-continue-recall` (desktop) or by the template chunk and pins its `href`; the value moved from `/playground` to `/dashboard` by decision Q5. The three `or` forms were the only assertions that could pass on an unrelated link; they are now single assertions.
- Each row in §C still asserts the Plus rules exist in the stylesheet and are scoped to the Calendar section; the key moved to the marker that Plus, Pro and Max share by decision Q3. Plus's own marker is still asserted present on Plus pages and absent elsewhere.
- Runs: the Calendar cohort (`test_calendar_family`, `test_phone_halted_calendar_screen5`, `test_*calendar_screen*`, `test_calendar_week`, `test_playground_r6`, `test_mobile_screens`, `test_free_law_choices`, `test_account_family`) 340 passed / 15 skipped on `72b8e2d` and 240 passed / 15 skipped (without `test_free_law_choices` and `test_account_family`) on `eaec5e3`; the full suite and the executed CI run are recorded in `M6-evidence.md` §2 against their SHAs.
