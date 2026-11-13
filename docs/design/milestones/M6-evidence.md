# M6 — Calendar (classic) by tier · evidence record

| Item | Value |
|---|---|
| Branch / PR | `pg-m6-calendar` (worktree `pg-m6`), draft PR #244 against `pg-m5-account` (`4221d53`) |
| Baseline | `ab0be0e` — captures and read-back on `4221d53` (`m6/01-baseline-4221d53/`) |
| Candidate | source `7716faa` (markers, gating, sheet, legend, CTA, footnote, overdue chip state, halted phone) + `ac8ff53` (the roadmap legend applied to the legend signed-in accounts actually see); tests `81e2fa5`, `72b8e2d`, `eaec5e3` |
| Captures | `m6/02-candidate-ac8ff53/` (served from the `eaec5e3` tree, whose source equals `ac8ff53`) |
| Tooling | `m1r/tools/capture_m1r.py` (route probe); `m6/tools/readback_m6.py` (nine states × two models × two flags × month / week through the app's TestClient); `m6/tools/serve_populated_m6.py` (progress rows seeded through the engine's repository; no payment or entitlement change); `m6/tools/capture_sheet_m6.py` (opens the upgrade sheet through CDP and records open / focus / Tab / Esc / exceptions) |
| Flags | `PLAYGROUND_TIER_MODEL` unset (`monthly`) on every dev launcher and populated server except the `-choices` launcher used for the gated rows; `ARTICLE_ENTITLEMENTS_ENABLED` off on the servers, both values in the read-back and the tests |
| Owner instructions in force | plan decisions Q1–Q7 (2026-11-11); verification list (2026-11-13); local acceptance separate from hosted; no merge, deployment or entitlement activation |

## 0. Baseline before edit — `4221d53` (`m6/01-baseline-4221d53/`)

Free month and week at 390 / 1280, light + dark; read-back of the nine states under both models and flags. Findings W1–W8 of `M6.md` §1 verified on the baseline rows: the base legend ended with "Review"; create entry points rendered for every signed-in account including Free under `choices` (the API's 403 reached only inside the form); Pro and Max carried no Calendar marker; the halted phone Calendar used the generic panel; the desktop CTA pointed at `/playground`; the footnote stated one ladder.

## 1. What changed (scope diff)

| Area | Change |
|---|---|
| `web/app.py::calendar_page` | `paid_calendar` (subscribed, tier in plus / pro / max, Playground open, not halted or expired) and `can_add_material` (the snapshot's `can_add_personal_calendar_tasks`) in the template context, both False for guests |
| `web/calendar_view.py` | `CalendarMonth.has_review_capacity` (default False) derived from the existing chip kinds |
| `templates/calendar.html` | `data-paid-calendar="desktop"` on the section; the signed-in toolbar legend lists My material · Due today · Memorized · Review done · Review due · Scheduled · New · Overdue (+ "Review" only with a review-capacity chip) and the hidden base legend carries the six roadmap items (+ "Review" the same way); the create entry points ("Add task", day-cell "+", "+ Add study material for this day") and the editor render only with the capability, otherwise one gated entry (`data-cal-upgrade`, `aria-haspopup="dialog"`, `aria-controls="cal-si-upgrade"`) at the toolbar and the day panel; the upgrade sheet `<dialog id="cal-si-upgrade">` with the decided copy and one action; the viewer, the toast and the script stay for every signed-in account (5-6a) and the viewer's Edit control follows the capability; a Constitution review whose day has passed carries `is-overdue`; "Continue today's Recall →" → `/dashboard`; the footnote states both ladders |
| `static/calendar-signed.js` (`cal3`) | `[data-cal-upgrade]` opens the sheet with `showModal()`; focus returns to the entry on close; the delegated handler ignores the gated entries; editor-only elements stay behind the existing guards |
| `static/playground.css` (`pg57`) | the Plus desktop and phone Calendar blocks key on `[data-paid-calendar="desktop"]` (53 selectors); the halted phone Calendar block = the expired phone block with the marker substituted (40 selectors); `.cal-si-upgrade*` styles |
| `static/mobile.css` (`mob113`) | the generic Free phone block excludes `[data-paid-calendar]` instead of `[data-plus-calendar]` (34 selectors) |
| `static/styles.css` (`main94`) | `.calendar-chip.is-overdue` (amber, like the week card and the legend swatch) |
| `templates/base.html` | pins main94 / mob113 / pg57 |
| Untouched | `web/study_archive.py` (the server gate, B1-F11, stays authoritative); the week builder; the Playground chip reconciliation; Google Calendar connect / disconnect / preferences; entitlements, billing, roster, migrations |

## 2. Tests

| Run | SHA | Result |
|---|---|---|
| Calendar cohort (`test_calendar_family`, `test_phone_halted_calendar_screen5`, `test_*calendar_screen*`, `test_calendar_week`, `test_playground_r6`, `test_mobile_screens`, `test_free_law_choices`, `test_account_family`) | `72b8e2d` | 340 passed / 15 skipped / 0 failed (97.6 s) |
| Calendar cohort without `test_free_law_choices` / `test_account_family` | `eaec5e3` | 240 passed / 15 skipped / 0 failed (58.2 s) |
| Full suite, local (`pytest tests`) | `81e2fa5` | **4229 passed / 177 skipped / 0 failed** (14 min 47 s; started 2026-11-13 16:45 UTC). Code-identical to `72b8e2d` except one test assertion; superseded by the run below for the legend change |
| Full suite, local (`pytest tests`) | `eaec5e3` | **4229 passed / 177 skipped / 0 failed** (13 min 16 s; started 2026-11-13 17:01 UTC; log `fullsuite-eaec5e3.log` in the session scratchpad) |
| CI (`workflow_dispatch`, pytest executed) | `81e2fa5` | run 43467013779 — **cancelled** before a result (conclusion `cancelled`; superseded by the dispatch on `eaec5e3`) |
| CI (`workflow_dispatch`, pytest executed) | `eaec5e3` | run 43468411439 — https://github.com/sanjisworking-commits/recall_the_c/actions/runs/43468411439 — pytest **executed** (`Decision: run=true (commit count 924 % 3 == 0)`), job *Unit tests* **success**: **4228 passed / 164 skipped / 14 deselected / 0 failed** (13 min 07 s). Consistent with the local run: CI deselects the 14 integration-marked tests, of which one (the docling smoke test) passes locally and thirteen (the Postgres suites) skip locally |
| CI (`pull_request`, automatic) | `eaec5e3` | run 43468419394 — in progress at the time of this record (its unit step follows the workflow's own rule; the dispatched run above is the executed record) |

New modules: `tests/test_calendar_family.py` (63 tests, F01–F12) and `tests/test_phone_halted_calendar_screen5.py` (6 tests, one Playwright-gated and skipped locally). Every changed assertion is listed in `M6-test-changes.md`; none was weakened.

## 3. Gates

| Gate | Check | Result |
|---|---|---|
| G1 guest gate | `/calendar` and the week route answer 303 to `/login?next=%2Fcalendar` | PASS on `eaec5e3` (F01; read-back guest rows) |
| G2 legends | signed-in desktop month toolbar legend = My material · Due today · Memorized · Review done · Review due · Scheduled · New · Overdue, + "Review" exactly when the grid draws a review-capacity chip; the base legend keeps the six and is hidden for signed-in month views; week legend six items; phone legend Today · Overdue · Scheduled · Done · New | PASS on `eaec5e3` (F02, F11; read-back `base_legend` / `toolbar_legend` / `week_legend` / `phone_legend` columns; `free-populated` 1280 frame shows the nine-item row) |
| G3 markers | paid marker on Plus / Pro / Max / pending under both models; Plus keeps `data-plus-calendar`; expired and halted markers; Free and paused none | PASS on `eaec5e3` (F03 16 rows; read-back `markers` column, 72 rows) |
| G4 create entry points and the sheet | entry points + editor iff `can_add_personal_calendar_tasks` (monthly: every signed-in state; choices: Plus / Pro / Max / pending); otherwise two gated entries, the sheet with the decided title, body, one "See plans ›" → `/playground?stage=plans`, no price; the viewer and script present regardless | PASS on `eaec5e3` (F04 32 rows; read-back `add_task` / `cell_add_count` / `day_add` / `editor_dialog` / `upgrade_entry` / `upgrade_sheet`; `free-choices` frames) |
| G4a API gate | create without the capability → 403 "Personal tasks are part of Plus."; GET `/calendar` changes nothing; Plus create → 200 | PASS on `eaec5e3` (F04 API test) |
| G5 CTA | `data-cal-continue-recall href="/dashboard"` desktop; `cal-m-today-continue href="/dashboard"` phone | PASS on `eaec5e3` (F05; read-back `continue_hrefs`; screen tests re-pinned) |
| G6 footnote | both ladders, Playground pending rung | PASS on `eaec5e3` (F06; read-back `footnote`) |
| G7 week and Playground chips | week view unchanged (six states, 400 on a bad date); Playground chip hrefs reconciled for expired / halted | PASS on `eaec5e3` (F07; `test_calendar_week`, `test_playground_r6`, `test_*calendar_screen9` / `screen5` seeded chip tests all green in the cohort) |
| G8 halted phone | the M6 block mirrors the expired phone block with the marker substituted, ≤ 560 px only; halted phone renders the restyled grid, bars and today card | PASS on `eaec5e3` (F08; `test_phone_halted_calendar_screen5`; `halted/` 390 light + dark frames) |
| G9 5-6a for a gated account (owner item 1) | material saved as Plus, subscription halted under `choices`: the entry and its PNG attachment still read 200 (inline, `image/png`), the first rung can be marked revised; create 403, edit 403 and the entry unchanged; the viewer's Edit control withheld (offered to Pro) | PASS on `eaec5e3` (F09) |
| G10 cross-account (owner item 2) | a second account gets 404 for the entry, the attachment, an edit and a completion of the first account's material; a tokenless write 403; a signed-out request 401; the owner's entry untouched | PASS on `eaec5e3` (F10) |
| G11 viewer outside the editor conditional (owner item 3) | every editor-only element is read behind a guard; in the browser pane and in the headless capture the gated Free `choices` page loads, opens and closes the sheet with **no console error and no exception** | PASS on `eaec5e3` (F12; pane `read_console_messages` empty before and after; `manifest-sheet.json` `exceptions: []` both themes) |
| G12 Overdue legend vs grid (owner item 4) | a Constitution review whose day has passed renders `is-due is-overdue` (amber) in the month grid, today's review `is-due` only; the legend's Overdue swatch and the CSS rule exist; the week card and the phone bar name the same day Overdue | PASS on `eaec5e3` (F11; `free-populated` frames: "Art 32(1)" amber on the 10th, "Art 21" accent on the 13th; `halted` phone: amber bar on the 10th, "Overdue by 3 days") |
| G13 changed assertions (owner item 5) | the 16 CTA assertions and the 11 keying assertions still pin the same elements for the decided values; the three `or` forms are plain assertions | PASS (`M6-test-changes.md` §B, §C, §E) |

## 4. Route matrix (candidate; captures in `m6/02-candidate-ac8ff53/`)

| Row | Server | Widths × themes | Observed |
|---|---|---|---|
| Free month, empty | dev launcher `playground-m6-free` | 390 / 1280 × light / dark | toolbar legend eight items, "Add task", day "+" on days ≤ today, panel "Nothing falls on this day." + Continue → `/dashboard`; phone grid, five-item legend, "Nothing due today" |
| Free week | same | 390 / 1280 × light / dark | six-state week legend on desktop; the phone shows the month grid (week is ≥ 900 px by design) |
| Free month, populated | `serve_populated_m6.py --tier free` (8925) | 390 / 1280 × light / dark | memorized chips (Art 1(1), 32(1), 14, 21), overdue "Art 32(1)" amber on the 10th, "Art 21" due on the 13th, scheduled rungs dashed, Auto Plan "REVIEW · n" chips and the "Review" legend item appended; day panel "2 revisions on this day" + "Article 21 — 1-day review due" |
| Free month under `choices` | dev launcher `playground-m6-free-choices` | 390 / 1280 × light; sheet 1280 × light / dark | "Add task" and "+ Add study material for this day" are the gated entries; no "+" in the cells; the sheet opens as a modal (close control focused), Esc closes it, focus returns to "Add task"; no price; `exceptions: []` |
| Plus month, populated | `serve_populated_m6.py --tier plus` (8926) | 390 / 1280 × light | `data-plus-calendar` + `data-paid-calendar`; same chip states as Free populated; RecallC Plus in the shell |
| Plus (dev launcher account) | `playground-m6-plus` | 1280 × light, `/playground` then `/calendar` | both markers; **no Playground chip** — the account has no due or scheduled Playground work, so the chip row is carried by `test_plus_calendar_screen9` (seeded due + scheduled chips with pinned hrefs) and the read-back `playground_chip_hrefs` column |
| Halted phone, populated | `serve_populated_m6.py --tier halted` (8927) | 390 × light / dark | `data-halted-calendar`; restyled grid; amber overdue bar on the 10th; today card "Article 32(1) · Overdue by 3 days", "Article 21 · Due today"; "Continue today's Recall →"; shell status "Payment retries have stopped" |
| Read-back | TestClient | nine states × 2 models × 2 flags × month / week = 72 rows | markers, legends, toolbar, entry points, sheet, CTA, footnote and chip hrefs as decided for every row; `legacy_copy` empty everywhere |

Probe facts on every captured row (`manifest.json`): one navigation surface; one phone bar at 390 and none at 1280; `hScroll` false; 0 targets under 44 px; 0 low-contrast texts (minimum composited ratio 5.28:1 phone light, 5.96:1 phone dark, 5.33:1 desktop light, 5.93:1 desktop dark); visible focus on every Tab-trail stop (14/14 phone, 8/8 or 9/9 desktop) and on the phone bar's tabs (8/8).

## 5. Visual and accessibility

- Prototype (18 Oct export, `viewer=plus&seed=1&calDesign=classic`): desktop legend under the title *Memorized / Review done / Review due / Scheduled / New / Overdue*; chips black-filled (memorized), grey with ✓ (review done), accent outline (review due), dashed (scheduled), amber outline (overdue); a "DESIGN Current | Study archive" switch (parked). Candidate: the same six states in the same order and the same treatments inside the signed-in toolbar legend, preceded by the two personal-material items and followed by the data-driven "Review" item; the Auto Plan "REVIEW · n" capacity chips have no prototype counterpart (pre-existing). The phone prototype's personal-material rows (filter chips, "Add task", overdue banner, "Mark revised") belong to the parked Study-material design and are not in the app; the app's phone Calendar has no create entry, so the gating is desktop-only.
- Upgrade sheet: native `<dialog>` opened with `showModal()` — outside content inert, focus lands on the close control, Tab stays inside (browser pane: close → "See plans ›" → close), Esc closes, focus returns to the entry. In the headless dark capture the second Tab reported `document.activeElement` = `BODY` (a headless-Chrome artifact: focus left the page to the browser UI; the page outside the dialog stays inert); the light headless row and the pane kept focus inside. CTA 109 × 44 px; close control 33 × 36 px (an icon button inside a dialog; its 44 px hit area is the dialog header row — recorded, not changed).
- No console error or exception on any verified page (pane, both servers; headless both themes).
- NOT RUN: automated accessibility scan; screen reader; real 200 % zoom; hosted.

## 6. Decisions and boundaries (owner, 2026-11-11 and 2026-11-13)

Q1–Q7 as recorded in `M6.md` §4. During implementation two findings were resolved within those decisions and are recorded for review: (W9) the month grid's missed Constitution review now wears the legend's Overdue state (`ac8ff53` ancestor `7716faa`); (W10) the viewer, toast and script were inside the editor's conditional — moved out so 5-6a holds (`7716faa`); and the roadmap legend had first been applied to the base legend that `styles.css` hides for signed-in month views — applied to the visible toolbar legend in `ac8ff53`. `study_archive.py` untouched; `PLAYGROUND_TIER_MODEL` stays `monthly`; no grant, purchase, billing or migration change; the `choices` rows were produced on the `-choices` dev launcher and in tests only.

## 7. Not run and open points

- Hosted S6 (populated Calendar on staging): NOT RUN — staging database availability and A5 container access remain BLOCKED (`M5-staging-prep.md`); separate from local acceptance.
- Automated accessibility scan, screen reader, real zoom: NOT RUN (as in M3–M5).
- Google Calendar connect / disconnect beyond its unit tests: NOT RUN (no credentials locally).
- A Plus account with a live Playground chip on the dev launcher: NOT CAPTURED (no due work); carried by the seeded screen tests.
- The "Review done" chip state was not produced by the populated seed (the builder infers review-done from the row's completion history, not from `times_completed` alone); the legend item is pinned by F02 and the chip class by the existing builder tests.
- Open points carried: 5-6b (gated existing material) and 5-17 (date rules) stay deferred; `review_capacity` chips are drawn for Free accounts although Auto Plan is paid (pre-existing, outside M6 — flagged for the owner); the base legend `.calendar-legend` is dead markup for signed-in month views (kept for the single-user mode; could be retired); the sheet's close control is 33 × 36 px.
- The pull-request CI run on `eaec5e3` (43468419394) runs the unit step only when its own rule says so; the dispatched run is the executed one.

## 8. Owner sign-off

None recorded. Owner sign-off is recorded only against an explicit acceptance instruction; this record is local evidence. "270 passing cohort tests is a useful checkpoint, not yet M6 acceptance" (owner, 2026-11-13) — the gates above, the full suite and the executed CI run are the checkpoint offered for that decision.
