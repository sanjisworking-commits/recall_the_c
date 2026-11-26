# M7b — Act progress, section picker, Learn, completion pages · milestone and evidence record

| Item | Value |
|---|---|
| Branch / PR | `pg-m7b-playground-learn` (worktree `pg-m7b`), cut from the accepted M7a head `0810bc2`; draft PR #246 against `pg-m7a-playground-home` |
| Authority | M7 plan approved 2026-11-16 (`M7.md` §4: Q1 two batches, Q8 picker behaviour); owner's direct answer of 2026-11-16 "Accept M7a, start M7b"; owner-forwarded review of the first candidate with recommendations for this batch (§6) — recorded as recommendations, acted on, **not an acceptance** |
| Baseline | `0810bc2` — `m7b/01-baseline-0810bc2/` |
| First candidate | source `3aff371` (picker, Q8) + `9895a3a` (three layout defects); tests `1526c25` — `m7b/02-candidate-9895a3a/` |
| Design batch | source `c6a6297` + `0274a22`; tests `2528bf0` + `bd40c14` — `m7b/03-design-0274a22/` |
| Tooling | `m1r/tools/capture_m1r.py`; `m7/tools/probe_page_m7.py`; `m7/tools/serve_populated_m7.py --scenario learn`; `m7b/tools/trace_picker_m7b.py`; `m7b/tools/check_learn_m7b.py`; `tests/js/picker_harness.js` |
| Flags | `PLAYGROUND_TIER_MODEL` `monthly`; `ARTICLE_ENTITLEMENTS_ENABLED` off. These pages carry no tier or model branch |

**Status: accepted (local) on 2026-11-26 by the owner's direct answer (§8) — the decided picker change, three layout defects, and the design batch the review recommended. Hosted acceptance pending.** No merge, deployment or `choices` activation.

## 1. Scope

`/playground/laws/{id}` (Act progress), `/playground/laws/{id}/sections` (picker), Learn `read · cloze · letters · type · recite · test`, `…/sections/{n}/learned`, `…/mastered`. One Plus account; tier-independent. Out: the Learn engines, scoring, the ladder, the speech endpoint, marks ("In the news", "Important" — no such feature in the application), source review.

## 2. Baseline — `0810bc2`

Plus, `monthly`, scenario `learn`: NDPS added as an entire Act; BNS sections 1–3 — section 1 with Read and Cloze completed through the Learn completion endpoint, section 2 taken up the ladder and section 3 learned through the repository's completion methods. 11 routes × 390 and 1280 × light and dark = 44 frames with shell and page probes; picker trace. Prototype references (Plus-viewer screens `progress`, `picker`, `learn`, `complete`, `milestone`) were rendered from the prototype export held for this programme and are not committed.

| # | Finding | Kind |
|---|---|---|
| B1 | **Picker (Q8).** Tick a section → no clause box is ticked; click clause 2 to untick it → clause 2 is the only thing selected; click it again → nothing is selected. | decided defect |
| B2 | **Act progress ring.** The fraction label and the ring's paper disc were stacked as two grid rows; the disc hung below the ring's centre. | layout defect |
| B3 | **"On the ladder".** Every bar had zero height. | layout defect |
| B4 | **Learn, desktop.** The six-card mode deck stretched to the height of the text panel. | layout defect (superseded: the deck is now removed) |
| B5–B11 | Differences from the prototype that are design choices | §6 |

## 3. What changed

| Area | Change |
|---|---|
| `static/playground-select.js` (`pg2`, `3aff371`) | one state per section, derived from its clause boxes: whole, some, none. Ticking the section ticks every clause; unticking one leaves the rest; ticking the last promotes back; unticking the section clears its clauses. A whole section rendered by the server gets its clauses ticked on load. The server is unchanged |
| `static/playground.css`, first candidate (`9895a3a`) | the ring's label and disc share one grid cell; ladder bars take their height from the rung's share, an empty rung keeps a 2 px baseline, a rung with sections on it is filled |
| `templates/playground_law.html` (`9895a3a`, `c6a6297`) | `is-filled` on a rung with sections; three groups in today's reading order — lead (ring, next step), charts (sections, ladder), actions — which are plain blocks on a phone |
| Act progress, desktop (`c6a6297`) | from 900 px the three groups form two columns on the theme's paper surface (`--pg-paper`, `--pg-hairline`; no hard-coded white), and the "In … Playground" badge sits beside the title where there is room. The phone is one column, byte-identical to before |
| Learn (`c6a6297`) | the six-card deck is removed from the template and the stylesheet; the mode tabs remain — six links with the current and completed marks, 44 px tall. From 1040 px the stage is one reading column (760 px) |
| Learn action bar (`c6a6297`) | each mode's primary action carries `pg-learn-actionbar`. In a window at least 900 px wide **and** 600 px tall it sticks to the bottom of the window on the page's own background; everywhere else it is ordinary flow. A bar whose only button is still hidden is not drawn. `scroll-padding-bottom` keeps focused controls clear of it. On this page the shell wrappers clip instead of hiding horizontal overflow, so the window — not a wrapper — is what scrolls |
| Completion pages (`c6a6297`, `0274a22`) | tick badge; the Act's name beside the citation; the ladder row runs Learned · Day 1 … Day 60 · Mastered. A reached step is filled and ticked, the next one outlined in the accent, later ones a plain outline, and each says "reached", "next" or "to come" in text for assistive technology. The first-revision line and "Continue" are unchanged. No quotation |
| Picker (`c6a6297`) | chapter headings stay `h2` and take the small label style from 561 px (the shell's `h2` rule had been overriding the picker's own) |
| Learn control sizes (`c6a6297`) | "Reveal all", the letters practice-style switch and each test answer's whole label have a 44 px minimum |
| `templates/base.html` | pins `pg60`, `playground-select.js?v=pg2` |
| Untouched | every route handler and view model; the Learn scripts and engines; the picker template; the speech endpoint |

## 4. Tests

`tests/test_playground_learn_family.py` — 16 tests; `tests/test_playground_picker_interaction.py` — 3 tests.

| Row | Covers |
|---|---|
| P01 (5) | what the picker submits is saved as decided under both models: a whole section with its clause values is one whole section; every clause alone is promoted; all but one stay as those clauses and promote again when the last is added; an unticked section is removed |
| P02, P03 | the picker script's structure and pin; the picker's markup is unchanged |
| P04, P05 | the ring rule; on a rendered Act progress page a learned section gives one filled bar and five empty ones |
| P06 | no deck markup or rule; on all six Learn pages the tabs are six links to the six modes, exactly one current, the completed mode marked; the 1040 px single column |
| P07 | the bar's rules — sticky only inside the wide-and-tall query, an opaque theme background, not drawn while its only button is hidden, scroll-padding, wrappers clipped; each mode's panel has exactly one bar holding its action |
| P08 | Act progress groups in the same reading order; the two-column rules use theme colours; nothing styles the groups below 900 px |
| P09 (2) | both completion pages: badge, Act name, Continue, the eight-step row with its three states said in text; the three drawings differ; the to-come step's colours measure at least 4.5:1 on the completion surface, and the surface's tokens are the ones measured |
| P10, P11 | chapter headings are `h2` with the label rule; the 44 px rules, and every test answer's radio sits inside its label |
| **Picker interaction, executed** | the shipped script is run under Node against the picker state the server rendered (`tests/js/picker_harness.js`): **whole → one clause unticked → ticked back → cleared, with the form values saved through the real endpoint and the page reloaded at each step**; clicking an indeterminate section box; and a guard that reconstructs the previous script and shows it fails the same cycle (after a whole-section tick, clicking clause 2 leaves only clause 2) |

Re-pinned, none weakened: `playground.css` `pg58` → `pg59` → `pg60` (58 modules); `playground-select.js` `pg1` → `pg2` (2 modules); `test_playground_m7.py::test_read_complete_control_not_constitution_desktop_hidden` — the deck's "hidden until 1040 px" check became "no deck markup or rule, tabs present, the 1040 px query remains"; `test_playground_r4.py::test_d87_desktop_deck_panel_layout_is_1040` — the 1040 px deck / panel grid check became the 1040 px single reading column.

| Run | SHA | Result |
|---|---|---|
| Full suite, local, first candidate | `1526c25` | 4307 passed / 177 skipped / 0 failed |
| CI `workflow_dispatch` 43836421030, first candidate | `1526c25` | success — pytest executed: 4306 passed / 164 skipped / 14 deselected |
| Template-, static-, Playground- and Learn-related modules, local, on the design-batch tree before its tests | `c6a6297` tree | 3 failed / 4121 passed / 174 skipped — the three deck pins named above; re-pinned in `2528bf0` |
| Full suite, local | `2528bf0` | stopped before a result (superseded by the gap fix); not counted |
| CI `workflow_dispatch` 44854597850 | `2528bf0` | cancelled (superseded); no result |
| Full suite, local, **final** | `bd40c14` | **4316 passed / 177 skipped / 0 failed** (863.7 s) |
| CI `workflow_dispatch` 44854805695, **final** | `bd40c14` | **success — pytest executed: 4315 passed / 164 skipped / 14 deselected / 0 failed** (1045.1 s). The skipped count is unchanged from the first candidate while nine tests were added, so the three Node-driven picker tests ran in CI |

Skipped locally: the Playwright-gated screen tests and the Postgres integration tests; counted as skipped, not passed.

## 5. Gates and evidence

| # | Gate | Result |
|---|---|---|
| G1 | Picker, in a browser: tick section → all six clauses ticked; untick clause 2 → the other five stay; tick it again → whole; untick the section → nothing | PASS on `3aff371` (script unchanged since) — trace `m7b/02-candidate-9895a3a/picker-trace/` beside the baseline trace |
| G2 | Picker, executed in the suite with save and reload at each step, and failing on the previous script | PASS on `bd40c14`, locally and in CI |
| G3 | The picker's markup and first render are unchanged; chapter headings are small `h2` | PASS — P03, P10; picker phone frames byte-identical to the first candidate |
| G4 | Ring and ladder | PASS — P04, P05; frames `law`, `law-new` |
| G5 | Act progress: two columns from 900 px on theme colours, badge beside the title; the phone is one column | PASS — P08; the phone frames of `law` and `law-new` are byte-identical to the first candidate |
| G6 | Learn: no deck; six modes, current and completed marks, keyboard access | PASS — P06; `learn-check.json` `tabs`: six links, 44 px tall, the current and done marks, 0 deck elements; the Tab trail reaches all six |
| G7 | Action bar does not obscure text, controls or focus at the tested viewports | **Tested viewport and focus checks passed** — P07; `learn-check.json`: sticky and stuck at 1280 × 900; **ordinary flow at 1280 × 500, 640 × 450 (a reduced-viewport reflow check) and 390 × 844**; on the test mode at 1280 × 900, 21 focus stops with the page scrolling to 1290 px — **0 under the bar, 0 off screen**, and the bar's action reached by keyboard; no horizontal scroll in any case. **Browser zoom: NOT RUN** — no page was zoomed, so this gate makes no claim about zoom |
| G8 | Typed fallback after the layout change | PASS — exercised in a browser at 1280 × 900: letters — five opening words typed, "Check typed words" → "Matched 5 words."; recite — the 280-word passage typed, "Check accuracy" → "280 / 280 recalled · 100%", a 280-word accuracy map, and the completion action (hidden before) appears in the bar. **Live speech: NOT RUN** |
| G9 | Completion pages: badge, Act name, end pills, the three states distinct and said in text, first-revision line and Continue kept, no quotation | PASS — P09; frames `learned`, `mastered` |
| G10 | Completion pill contrast | PASS — the to-come step is `#9a9a9a` on `#141414`, 6.5:1 (it was 4.49:1 on its old fill, below 4.5:1); the probe finds no text under 4.5:1 on either completion page (minimum 6.55:1) |
| G11 | Learn controls reach 44 px, the radio measured by its whole label | PASS — P11; the page probe, which now measures a radio or checkbox by its clickable label, reports no Learn control under 44 px at either width |
| G12 | Nothing else moved | PASS — of the 44 design-batch frames, 16 are byte-identical to the first candidate (Act progress, picker and Learn `read`, `cloze`, `letters`, `type`, `recite` on the phone); the 28 that differ are the desktop frames, Learn `test` on the phone (taller answers) and the completion pages |

Page probe, 44 rows (`m7b/03-design-0274a22/plus/page-probe.json`, measured on `c6a6297`; `0274a22` adds only the completion step gap): no horizontal scroll, no script exception, a focus ring on every Tab stop recorded.

**Open, pre-existing and unchanged — not a pass:**

- Light theme: the small grey labels (`--pg-mid`, `--pg-faint`) at 2.38–2.74:1 on Act progress, Learn and the picker — the shared label style of M7a's W16. On the picker the failing text is the "SECTION n" eyebrows and the "Not started" status (2.38:1, 713 readings on BNS); the chapter headings, now in the label style, use `--pg-muted` and pass. On Act progress the labels now sit on the paper surface and measure 3.24:1 instead of 2.74:1 — still failing.
- Dark theme, phone picker: the same "SECTION n" eyebrows and "Not started" status measure 4.1:1 — below 4.5:1, present at baseline, unchanged.
- The desktop back link at 78 × 32 px (93 × 32 on the picker): under the 44 px design target (M7a's W17).
- Two probe readings are not defects: the cloze blanks' hidden words measure 1.09:1 in the dark theme because they are deliberately the colour of their blank until revealed; "Section 1 · Learning" on dark Act progress is visually-hidden text for assistive technology.

## 6. The review's recommendations for this batch and what was done

The review of the first candidate was forwarded without further comment. It is recorded as recommendations; it says itself that it is not an M7b acceptance.

| Area | Recommendation | Done |
|---|---|---|
| Act progress | Two-column desktop layout; preserve the title, badge beside it where space permits, single-column phone; theme colours rather than hard-coded white | Built so (G5) |
| Learn | Keep mode tabs, remove the duplicate desktop deck; preserve all six modes, completion indicators and keyboard access | Built so (G6) |
| Learn action bar | Follow the prototype, but never obscure text, controls or keyboard focus at narrow widths or zoom | Built as a bar that sticks only in a wide and tall window. Narrow and short viewports: tested viewport and focus checks passed (G7). Zoom: NOT RUN (§7) |
| Completion pages | Check badge, Act name, Learned / Mastered end pills; keep the first-revision date and Continue; distinguish reached from future; no invented quotation | Built so (G9) |
| Picker | Smaller chapter headings, preserving heading semantics, clause selection and indeterminate states | Built so (G3) |
| News / Important marks | Out of scope | Not built |
| Control sizes | Enlarge affected Learn controls; measure the radio's whole clickable label | Built; the probe measures the label (G11) |
| Picker verification | An automated interaction test for whole → partial → whole → cleared, including save / reload | Added: the shipped script executed under Node, in the suite and in CI (G2) |
| Learn verification | Exercise the typed fallback after removing the deck and repositioning actions; keep live speech NOT RUN unless tested | Exercised (G8); live speech NOT RUN |
| Contrast | Retain the shared label-contrast finding; correct the 4.49:1 completion pill | Finding retained (§5); pill corrected (G10) |

Still different from the prototype, by the decisions above or because the application has no such content: no quotation and no "Back to Playground" on the completion pages (the working "Continue" stays); the completion pages show no site navigation; no streak chip on Act progress; no marks; the picker keeps clause-level picking.

## 7. Not run and limitations

- Hosted comparison: NOT RUN (staging blocked, `M5-staging-prep.md`).
- **Live speech** (`letters`, `recite`): NOT RUN — no speech provider locally. Only the typed fallback was exercised.
- Automated accessibility scan, screen reader: NOT RUN.
- **Browser zoom: NOT RUN.** No page was zoomed. G7's 640 × 450 case is a reduced-viewport reflow check in an unzoomed browser; it shows how the page lays out in a small window and is not evidence of behaviour under zoom.
- Playwright-gated screen tests: skipped locally (not installed).
- The executed picker test runs the real script against a stand-in DOM that implements only what the script uses; it is not a browser. The browser behaviour is the CDP trace of G1, recorded on `3aff371`.
- The focus check of G7 covers the test mode at one window size; the other modes have fewer controls than it does.
- One account (Plus, `monthly`) was captured; these pages have no tier or model branch.
- Sections 2 and 3 of the fixture received their progress through the repository's completion methods with a placeholder source identity, so Learn frames were taken on section 1.

### 7.1 Wording correction, 2026-11-26

An owner-forwarded review of this record found that G7 and the PR summary overstated zoom verification: the 640 × 450 case had been described as "1280 × 900 at 200 % zoom", and a disclaimer further down did not undo that claim. Corrected here, in `learn-check.json` (the case label only — no measurement changed), in `tools/check_learn_m7b.py` and in the PR description: G7's result is "tested viewport and focus checks passed", 640 × 450 is a reduced-viewport reflow check, and browser zoom is NOT RUN. Documentation and evidence labelling only; no product or test file changed, so the tested SHA stays `bd40c14`.

## 8. Owner sign-off — local, M7b (owner's direct answer, 2026-11-26)

| Item | Record |
|---|---|
| Instruction | An owner-forwarded review of 2026-11-26 recommended acceptance after one wording correction (§7.1) and said that acceptance remained the owner's. The correction was made (`e27b506`), and the owner was then asked directly, with PR #246 at head `e27b506` (tested `bd40c14`): "Do you accept M7b as the reusable local baseline, with its recorded limitations (label contrast and 32 px back link open; browser zoom, live speech and hosted checks not run)?" The owner answered: **"Yes, I accept M7b"** — to the option "record local acceptance in M7b.md and on PR #246 against source `0274a22` / tested `bd40c14` / head `e27b506`. Hosted acceptance, merge, deployment and choices activation stay separate and untouched." |
| Decision | **Accepted (local)** as the reusable local baseline for Act progress, the section picker, Learn (`read · cloze · letters · type · recite · test`) and the learned / mastered completion pages — source `0274a22` (with `3aff371`, `9895a3a`, `c6a6297`), tested `bd40c14` (local 4316 passed / 177 skipped / 0 failed; CI 44854805695 executed, 4315 passed / 164 skipped / 14 deselected / 0 failed); evidence `m7b/01-baseline-0810bc2/`, `02-candidate-9895a3a/`, `03-design-0274a22/`. From `bd40c14` to `e27b506` only records, captures and evidence tooling changed. |
| Scope of the acceptance | What the recorded tests, frames, probes, traces and checks cover (§3–§5). It does not extend to anything listed as NOT RUN or as a limitation in §7. |
| Findings retained, open | Light-theme label contrast 2.38–3.24:1 and the phone picker's dark-theme "SECTION n" / "Not started" text at 4.1:1 (the shared label style, M7a W16) — for the shared-style batch. The desktop back link at 78 × 32 px against the 44 px design target (M7a W17). |
| NOT RUN, retained | Hosted comparison; live speech; **browser zoom**; automated accessibility scan; screen reader; Playwright-gated screen tests. The executed picker test uses a stand-in DOM, not a browser. |
| Not covered by this acceptance | Hosted acceptance; merge; deployment; `choices` activation (blockers 5-6b, 5-20, 5-13 unchanged). |
| Reopening | Local evidence is reopened only where a later change affects these pages. |
