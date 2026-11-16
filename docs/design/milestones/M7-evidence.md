# M7a — Playground home, Manage laws, Remove by tier and model · evidence record

| Item | Value |
|---|---|
| Branch / PR | `pg-m7a-playground-home` (worktree `pg-m7a`), draft PR #245 against `pg-m6-calendar`; cut from the M6 head `0f8fb87` with `origin/main` `e34af87` merged (`6d9d4c7`) |
| Baseline | `49c7904` — read-back and captures on the `6d9d4c7` tree (`m7/01-baseline-6d9d4c7/`) |
| Candidate | source `4bc0fd4` (the `choices` branches, the shared home layout) + `60a6f37` (capacity bar, W12) + `0829d45` (Remove template fallback) + `ea47eab` (read-only homes keep the plain capacity line) + `773492f` (the approved `choices` wording: "How it works", the guest line, the paid Add sheet); tests `fe554c5`, `18e9f02`, `fa05a2c`, `8066ef7`, `09bc48d`, `c89dd05` |
| Captures | `m7/02-candidate-60a6f37/` — frames served from `60a6f37` (`plus`, `plus-empty`, `pro`, `pro-choices`) and `4bc0fd4` (`free-choices-*`, `plus-choices`); read-back on `8066ef7`. The two later source commits do not alter a captured page: `0829d45` only supplies defaults when a caller omits `remove_copy`, and `ea47eab` touches the read-only homes of paused, expired and halted accounts under `choices`, which are not captured. `m7/03-copy-773492f/` — the states `773492f` changes: the paid Add sheet (new law and re-add) and the guest gate, both under `choices` |
| Tooling | `m1r/tools/capture_m1r.py` (frames and shell probe); `m7/tools/readback_m7.py` (nine states × two models × the Playground routes through the app's TestClient); `m7/tools/serve_populated_m7.py` (Playground filled through the application's own save points on a throwaway database; no payment or entitlement change); `m7/tools/probe_page_m7.py` (page-level probe over CDP) |
| Flags | `PLAYGROUND_TIER_MODEL` `monthly` on every server except those named `-choices`; `ARTICLE_ENTITLEMENTS_ENABLED` off |
| Instructions in force | plan with Q1–Q11 approved in the session's plan review, 2026-11-16 (`M7.md` §4); owner-forwarded review of 2026-11-16 with recommendations on the pending items (`M7.md` §4.1) — acted on for the two copy changes, not an acceptance; local acceptance separate from hosted; no merge, deployment or `choices` activation |

M7b (Act progress, picker, Learn, completion pages) is not started and has no evidence here.

## 0. Baseline before edit — `6d9d4c7` (`m7/01-baseline-6d9d4c7/`)

Read-back, 210 rows; 76 frames (Plus `monthly` ten routes; Pro `monthly`, Free `choices` at three choices used, Plus `choices` — home, Manage laws, Remove; 390 and 1280; light and dark). Findings W1–W14 of `M7.md` §5 were read off these rows and frames. Under `choices` the baseline printed 280 month phrases and 34 links to the rollover route across the read-back rows.

Full suite on the combined tree before any M7 edit: **4234 passed / 177 skipped / 0 failed** (876.8 s) — `6d9d4c7` source and tests; the docs-only commit `49c7904` landed during the run.

## 1. What changed (scope diff `49c7904` → `773492f`, `src` only: 13 files)

| Area | Change |
|---|---|
| `playground/view.py` | `playground_month_model(snapshot)` — the period model read from the entitlement snapshot's `tier_model`, never from the flag — and `playground_tier_word`. `capacity_view` gains `month_model` and `tier_label`: Free `choices` → "n of 3 law choices used" · "k left · removal never restores a choice" (at three: "All three used · …"), legend "previously chosen · add again anytime · choice still used", "k choices left"; paid `choices` → "n laws" · "Unlimited · {Tier}". `PlaygroundHomeView` gains the heading, empty-state, strip, aside and limit fields, whose defaults are today's monthly strings. `build_home_view` fills them for `choices`: "Laws", "In Playground", "Previously chosen — add again anytime", "Manage laws", no rollover target, the limit paragraph and upgrade action only for a Free account at its limit. `roster_law_cards`, `add_confirm_copy` take `month_model`. New `roster_page_copy` and `remove_page_copy` hold every model-dependent string of those two pages. |
| `playground/routes.py` | the home passes `open_playground` (the account can open the Playground, has a snapshot, is not the single-user owner); Manage laws passes `month_model`, `roster_copy`, `permanent=` to its own Add confirm, and a model-aware re-add notice; Remove passes `remove_copy`; Act progress passes `month_model` |
| `templates/playground.html` | the styled layout applies to `is_plus or open_playground`; markers `data-open-playground="desktop"` / `data-open-playground-phone` (active Plus keeps `data-plus-playground*` as well); month title, "Playground month", "Manage {next} ›" and the two "Plan next month" rows only while `home.month_model`; headings, empty state and aria labels from the view; under `choices` the phone strip label and note, and in the aside the limit paragraph and the upgrade action |
| `templates/partials/playground.html` | `capacity_block` prints the legend for an unlimited account when the view has no month model |
| `templates/playground_roster.html`, `playground_remove.html`, `playground_law.html` | copy from `roster_copy` / `remove_copy` (the Remove template falls back to the monthly strings if a caller omits it); the rollover row only under the month model; badge "In Playground" without the month under `choices` |
| `static/playground.css` (`pg58`) | the Plus home rules (90 selectors) key on the shared marker; M7a block: `.pg-strip-note`, `.pg-limit-note`, `.pg-upgrade-actions`; inside the aside card capacity cells may shrink (W12) |
| `templates/base.html` | pin `pg58` |
| `web/shell.py`, `web/app.py` (`773492f`) | template global `playground_month_model(request)`: a signed-in account's entitlement snapshot; for a guest, whose shared snapshot carries no model, the entitlement service's own model. Templates still never read the flag |
| `templates/playground_gate.html`, `partials/playground.html` (`773492f`) | under `choices` the guest line reads "Add the laws you want to learn to your Playground." and "How it works" steps 1 and 3 read "Choose your laws" · "… They stay in your Playground until you remove them." and "Remove and add back anytime" · "Your saved progress comes back with the law."; under `monthly` unchanged |
| `partials/playground_add_panel.html`, `playground/routes.py` (`773492f`) | the paid Add sheet under `choices`: eyebrow "Playground", "joins your Playground"; the confirm step and everything under `monthly` unchanged |
| Untouched | the roster service, the ledger, entitlements, billing, migrations; the Act head and every other Add-sheet state (M2-R), including the paid re-add wording (W18); the plans stage (M5); the rollover page and route; the picker, Learn and completion pages (M7b) |

## 2. Tests

New module `tests/test_playground_family.py` (58 tests, F01–F13); re-pins listed in `M7-test-changes.md` (`pg58` in 56 modules; six stylesheet keying assertions; two heading assertions; the Pro row of the Plus screen test; one context-key set; the M2-R paid-sheet sentence; the gate's macro call). No assertion weakened.

| Run | SHA | Result |
|---|---|---|
| Full suite, local, before any M7 edit | `6d9d4c7` tree | **4234 passed / 177 skipped / 0 failed** (876.8 s) |
| Full suite, local | `18e9f02` | **2 failed / 4278 passed / 177 skipped** — `tests/test_request_perf_breakdown.py::test_t8_template_bytes_match_unwrapped_render` (`'remove_copy' is undefined` on a direct render of the Remove template) and `::test_t8_html_omits_stage_names_and_ids` (the pinned home context keys lacked `open_playground`). A targeted cohort run had not included this module. Fixed in `0829d45` (template fallback) and `fa05a2c` (key added to the pinned set). |
| Full suite, local | `fe554c5`, `fa05a2c` | stopped before a result (superseded by later commits); not counted |
| Full suite, local (before the approved wording) | `8066ef7` | **4283 passed / 177 skipped / 0 failed** (908.5 s) — the baseline's 4234 plus the 49 new tests |
| Playground family module | `8066ef7` | 49 passed |
| CI `workflow_dispatch` 43795145206 | `18e9f02` | cancelled (superseded); no result |
| CI `workflow_dispatch` 43796843549 | `fa05a2c` | cancelled (superseded); no result |
| CI `workflow_dispatch` 43797265361 (before the approved wording) | `8066ef7` | **success — pytest executed: 4282 passed / 164 skipped / 14 deselected / 0 failed** (1263.8 s) |
| Full suite, local | `09bc48d` (the approved wording) | **1 failed / 4291 passed / 177 skipped** — `tests/test_signed_in_playground_screen6.py::test_signed_in_pg_gate_does_not_touch_accepted_screens` (a template-source pin on `how_it_works()`); a targeted run had not included this module. Re-pinned in `c89dd05`. |
| CI `workflow_dispatch` 43805603278 | `09bc48d` | **failure — pytest executed: 1 failed / 4290 passed / 164 skipped / 14 deselected** (the same test) |
| Full suite, local, final | `c89dd05` | **4292 passed / 177 skipped / 0 failed** (915.6 s) — the baseline's 4234 plus the 58 new tests |
| CI `workflow_dispatch` 43807943617, final | `c89dd05` | **success — pytest executed: 4291 passed / 164 skipped / 14 deselected / 0 failed** (971.5 s) |
| CI `pull_request` 43796849471, 43797271054, 43805608006, 43807949025 | `fa05a2c`, `8066ef7`, `09bc48d`, `c89dd05` | conclusion success, but pytest **did not run** (`Decision: run=false (commit count not divisible by 3)`); not counted as executed runs |

Skipped locally: the Playwright-gated screen tests (Playwright is not installed) and the Postgres integration tests; they are counted as skipped, not passed.

## 3. Gates

| # | Gate | Result |
|---|---|---|
| G1 | Under `choices`, home (empty and populated), Manage laws, re-add confirm, Remove and Act progress print no month phrase for Free, Plus, Pro, Max | PASS — F01; read-back on `8066ef7`: 280 → 1 month phrase across the `choices` rows; the one left was the guest line, removed in `773492f` (G14) |
| G2 | No link to the rollover route under `choices`; the route still redirects to Manage laws | PASS — F01; read-back `rollover_links` 34 → 0 |
| G3 | `monthly` keeps today's copy and links | PASS — F02; read-back: of the 105 `monthly` rows only eight differ from the baseline — Plus home ×2 (the added marker) and Pro / Max / pending home ×2 each (Q7 layout); all 40 Plus `monthly` frames are byte-identical to the baseline (SHA-256) |
| G4 | RecallC Free counter 0 → 3; upgrade action and limit paragraph only at 3 of 3, to the plans stage, no price | PASS — F03; frames `free-choices-0of3`, `-2of3`, `-3of3` |
| G5 | Removal keeps the choice; the law reads "Previously chosen"; re-add consumes nothing; a fourth law stays refused | PASS — F03 (ledger rows compared before and after) |
| G6 | Plus / Pro / Max under `choices`: "n laws" · "Unlimited · {Tier}" | PASS — F04; frames `plus-choices`, `pro-choices` |
| G7 | Shared layout marker on Plus, Pro, Max, pending (both models) and Free (`choices`); Plus marker on active Plus only; none on paused, expired, halted, Free (`monthly`), guest | PASS — F05 (sixteen state × model rows) |
| G8 | Manage laws and Remove copy per model and tier; the page's own Add and re-add confirms | PASS — F06, F07 |
| G9 | GETs under `choices` write nothing | PASS — F08 (period, roster and ledger tables identical after the walk) |
| G10 | Another account cannot open, learn or remove a law it has not added | PASS — F09, both models |
| G11 | Templates read the view, never the flag | PASS — F10 |
| G12 | Pro's 30-segment bar stays inside the aside card (W12) | PASS — `pro/pro_pro_home_1280x900_light.png` against the baseline frame of the same name; F10 pins the rule |
| G14 | Under `choices` the guest line and "How it works" carry no monthly language, promise no count of choices and no price; under `monthly` unchanged | PASS on `c89dd05` — F12 (guest page under both models; the macro rendered under both; the helper reads a signed-in account's snapshot); frames `03-copy-773492f/guest-choices/` |
| G15 | The paid Add sheet under `choices` names no month ("Playground", "joins your Playground") and keeps its confirmation step; under `monthly` unchanged | PASS on `c89dd05` — F13 (Plus and Pro, new law and re-add, both models) and the re-pinned M2-R test; frames and sheet probe `03-copy-773492f/plus-choices-sheet/` |
| G13 | Ended states keep their read-only home | PASS — F05 (three states) and the read-back: paused, expired, halted rows unchanged under `monthly`; under `choices` their home lost only its month phrases and prints the plain "Unlimited" as today; gates and redirects unchanged |

## 4. Route matrix (candidate; `m7/02-candidate-60a6f37/`)

100 frames, each 390 × 844 and 1280 × 900, light and dark. Every row below: status 200, one navigation surface (none on Learn and the completion pages, by design), `hScroll` false, no shell target under 44 px, no low-contrast shell label.

| Folder | Account / model | Routes | Result |
|---|---|---|---|
| `plus/` | Plus, `monthly`, populated | home, Manage laws, roster Add confirm, Remove, rollover, Act progress, picker, Learn (read), learned, mastered | PASS on `60a6f37` — 40 of 40 PNGs byte-identical to the baseline |
| `plus-empty/` | Plus, `monthly`, empty | home | PASS on `60a6f37` |
| `pro/` | Pro, `monthly`, populated | home, Manage laws, Remove | PASS on `60a6f37` — shared layout; bar inside the card |
| `free-choices-0of3/` | Free, `choices`, nothing added | home | PASS on `4bc0fd4`, carried to `ea47eab` |
| `free-choices-2of3/` | Free, `choices`, one active and one previously chosen | home | PASS on `4bc0fd4`, carried |
| `free-choices-3of3/` | Free, `choices`, two active and one previously chosen | home, Manage laws, re-add confirm, Remove | PASS on `4bc0fd4`, carried |
| `plus-choices/` | Plus, `choices`, populated | home, Manage laws, re-add confirm, Remove | PASS on `4bc0fd4`, carried |
| `pro-choices/` | Pro, `choices`, populated | home | PASS on `60a6f37` |
| read-back | nine states × two models | fourteen routes (210 rows) | PASS on `8066ef7` |

| `03-copy-773492f/guest-choices/` | guest, `choices` | the gate | PASS on `773492f` — 4 frames |
| `03-copy-773492f/plus-choices-sheet/` | Plus, `choices`, populated | Add sheet for a new law and for a re-add, opened by URL | PASS on `773492f` — 8 frames; sheet probe below |

**Not captured — covered by tests and read-back only, no screenshot:** the paused, expired and halted homes, including the `ea47eab` change to their capacity line under `choices` (F05 and the read-back rows are the evidence); Max and pending homes; Pro and Max Manage laws and Remove under `choices`; the Pro Add sheet (F13 covers it); the "How it works" block under `choices` (rendered through the macro in F12; no gate that prints it is reachable in multi-user mode).

## 5. Visual and accessibility

Page-level probe (`page-probe.json` beside the frames; `free-choices-2of3`, `free-choices-3of3`, `plus-choices`, `pro` — 40 rows measured inside `<main>`; `03-copy-773492f/plus-choices-sheet` — 8 rows measured inside the open dialog):

- `hScroll` false on every row; no script exception on any row; every Tab stop shows a focus ring (Tab trails are recorded on the light-theme rows).
- Dark theme: no text under 4.5:1 on any probed page or in the sheet (minimum 4.5:1 on the pages, 5.42:1 in the sheet).
- Light theme, **contrast — open finding W16**. The small grey labels fail 4.5:1: "MY PLAYGROUND", section labels and eyebrows at 2.74:1 on the page grey and 3.24:1 on white, Manage-laws section heads at 2.38:1. The style predates M7a and the stylesheet diff does not touch it, **but text M7a added or changed inherits it and fails with it**: the headings "In Playground", "Previously chosen — add again anytime" and "Active", the aside eyebrows "Law choices · Free" and "Playground", and the paid sheet's new eyebrow "Playground" (3.24:1; the sheet's "✕" glyph measures the same). Of M7a's new text only three items meet 4.5:1: the phone strip note (4.51:1 light, 7.14:1 dark), the limit paragraph and the upgrade action. This is not a pass for the pages.
- **Targets.** No control under 44 × 44 px in the sheet or among the controls M7a added. The desktop back link "← Playground" is 78 × 32 px (W17): under the programme's 44 px design target, R1 style, unchanged; its height alone does not establish a failure of an accessibility standard.
- **Sheet (Plus, `choices`; new law and re-add; 390 and 1280).** Opened by URL as a modal dialog; three controls (the action, Cancel, close); 24 consecutive Tab stops stay inside the dialog; no horizontal scroll; no exception.
- Device limit observed working: a third session on a paid account received "Device limit reached" (the populated server removes its own setup device so the capture and probe sessions are the two allowed).

Fidelity against the handover frames (`desktop-12/13/19`, `phone-11/12/19`):

| Difference | Class | Note |
|---|---|---|
| Manage laws is titled "Manage laws", not "September Playground" | decided (Q5) | the handover's own notes remove the month |
| Phone strip button reads "Manage laws"; the frame reads "Manage" | I | same label as the desktop button; one wording across widths |
| Unlimited accounts draw no capacity bar; the frame draws one cell per law | G | a bar that grows with every law overflows (W12); the legend carries the same three facts |
| A previously chosen law is a card with a dashed outline on the home; the frame draws a compact row | G | the existing removed-law card, relabelled; Manage laws already uses the row form |
| Phone home shows "Previously chosen — add again anytime" as a section heading; the frame shows only active laws | I | the working re-add entry stays available on the phone (§0.2a) |

NOT RUN: hosted comparison (staging blocked), automated accessibility scan, screen reader, real zoom, the Playwright-gated screen tests (Playwright is not installed locally).

## 6. Decisions and boundaries

Q1–Q11 as recorded in `M7.md` §4, and the owner-forwarded review of 2026-11-16 as recorded in `M7.md` §4.1. Within the plan, three things were settled during implementation and are recorded for review: the shared marker is named `data-open-playground` rather than a "paid" marker because Q3 puts RecallC Free (`choices`) on the same layout; pending accounts carry it too (their Playground is open; they cannot add); W12 needed its own stylesheet rule. Built after the review: the Q9d wording and W15, exactly as recommended. Not built: W16, W17, W18 (`M7.md` §5.2). `PLAYGROUND_TIER_MODEL` stays `monthly`; no grant, purchase, billing or migration change; every `choices` row was produced on throwaway databases and in tests.

## 7. Not run and open points

- Hosted comparison: NOT RUN — staging database availability and A5 container access remain BLOCKED (`M5-staging-prep.md`).
- Automated accessibility scan, screen reader, real zoom: NOT RUN.
- Playwright-gated screen tests: skipped locally; counted as skipped.
- Live speech: not in M7a's pages.
- **Screenshots do not exist for the paused, expired and halted homes.** Their `choices` copy change (`ea47eab`) rests on F05 and the read-back rows only.
- W16: light-theme label contrast, including the headings and eyebrows M7a added or changed — open; one shared-style correction recommended for the next appropriate batch.
- W17: desktop back link 78 × 32 px — open against the 44 px design target; not by itself a standard failure.
- W18: paid re-add wording on the Act head and inside the Add sheet under `choices` ("Removed this month", "Add back", "No extra space used.") — not built; it now disagrees with the home and Manage laws.
- W13 (generic phone month strip) no longer has a reachable page: every account that sees a writable home now gets the shared layout; the generic markup remains for single-user mode and the read-only states.
- W14 ("sections selected" on the home card, "provisions" on Manage laws): wording inconsistency, unchanged.
- Carried from earlier milestones: 5-20, 5-13, 5-6b, 5-1, 5-14, 5-12; the plans-stage title for paid holders and the expired head's billing button (→ M8-R).

## 8. Owner sign-off

None recorded. Owner sign-off is recorded only against an explicit acceptance instruction; this record is local evidence for M7a only.
