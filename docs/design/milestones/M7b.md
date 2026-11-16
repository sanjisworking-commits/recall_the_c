# M7b — Act progress, section picker, Learn, completion pages · milestone and evidence record

| Item | Value |
|---|---|
| Branch / PR | `pg-m7b-playground-learn` (worktree `pg-m7b`), cut from the accepted M7a head `0810bc2`; draft PR against `pg-m7a-playground-home` |
| Authority | M7 plan approved 2026-11-16 (`M7.md` §4: Q1 two batches, Q8 picker behaviour, Q6 defects only where no design decision is needed); owner's direct answer of 2026-11-16 "Accept M7a, start M7b" |
| Baseline | `0810bc2` — `m7b/01-baseline-0810bc2/` |
| Candidate | source `3aff371` (picker, Q8) + `9895a3a` (three layout defects); tests `1526c25` |
| Tooling | `m1r/tools/capture_m1r.py`; `m7/tools/probe_page_m7.py`; `m7/tools/serve_populated_m7.py --scenario learn`; `m7b/tools/trace_picker_m7b.py` |
| Flags | `PLAYGROUND_TIER_MODEL` `monthly`; `ARTICLE_ENTITLEMENTS_ENABLED` off. These pages carry no tier or model branch (the Act badge's month was handled in M7a) |

**Status: first M7b candidate — the decided picker change and three layout defects — with local evidence. Not accepted. The larger fidelity differences against the prototype (§6) need the owner's decisions and are not built.** No merge, deployment or `choices` activation.

## 1. Scope

`/playground/laws/{id}` (Act progress), `/playground/laws/{id}/sections` (picker), Learn `read · cloze · letters · type · recite · test`, `…/sections/{n}/learned`, `…/mastered`. One Plus account; tier-independent. Out: the Learn engines, scoring, the ladder, the speech endpoint, marks ("In the news", "Important" — drawn in the prototype, no such feature in the application), source review.

## 2. Baseline — `0810bc2`

Plus, `monthly`, scenario `learn`: NDPS added as an entire Act; BNS sections 1–3 — section 1 with Read and Cloze completed through the Learn completion endpoint, section 2 taken up the ladder and section 3 learned through the repository's completion methods. 11 routes × 390 and 1280 × light and dark = 44 frames with shell and page probes (`m7b/01-baseline-0810bc2/plus/`); picker trace (`…/picker-trace/`). Prototype references: the Plus-viewer screens `progress`, `picker`, `learn`, `complete`, `milestone` rendered from the prototype export held for this programme (phone 400 × 860, desktop 1640 × 960); they are not committed.

What the baseline showed:

| # | Finding | Kind |
|---|---|---|
| B1 | **Picker (Q8).** Trace on BNS section 4 (six clauses): tick the section → the section is selected and no clause box is ticked; click clause 2 to untick it → clause 2 is the **only** thing selected; click it again → nothing is selected. | decided defect |
| B2 | **Act progress ring.** The fraction label and the ring's paper disc were stacked as two rows of the ring's grid: the label sat on the ring's top edge and the disc hung below the centre, at both widths and in both themes. | layout defect |
| B3 | **"On the ladder".** Every bar had zero height — the chart showed six counts and no bars. | layout defect |
| B4 | **Learn, desktop (≥ 1040 px).** The six-card mode deck stretched to the height of the text panel beside it: tall, empty cards. | layout defect |
| B5–B11 | Differences from the prototype that are design choices, not defects | §6 |

## 3. What changed

| Area | Change |
|---|---|
| `static/playground-select.js` (`pg2`, `3aff371`) | one state per section, derived from its clause boxes: whole (section ticked, every clause ticked), some (section indeterminate), none. Ticking the section ticks every clause; unticking one leaves the rest; ticking the last promotes back; unticking the section clears its clauses. A whole section rendered by the server gets its clauses ticked on load. The server is unchanged: it ignores the clause values of a section submitted whole and promotes a full set of clauses itself |
| `static/playground.css` (`pg59`, `9895a3a`) | M7b block: the ring's label and disc share one grid cell; ladder bars take their height from the rung's share, with a 2 px baseline for an empty rung and a filled colour for a rung with sections on it; the Learn deck keeps its natural height at ≥ 1040 px |
| `templates/playground_law.html` | a rung with sections on it carries `is-filled` |
| `templates/base.html` | pins `pg59`, `playground-select.js?v=pg2` |
| Untouched | every route handler and view model; the Learn templates, scripts and engines; the picker template; the completion pages |

## 4. Tests

New module `tests/test_playground_learn_family.py` — 10 tests:

| Row | Covers |
|---|---|
| P01 (5) | under both models, a section submitted whole together with its clause values is saved as one whole section; every clause without the section box is promoted to the whole section; all but one clause stay as those clauses, and adding the last one back promotes again; a section with nothing ticked is removed while another stays |
| P02 | the picker script: `setSectionBox`; the state is derived from the clause boxes and a whole section never clears them; the section's change handler sets every clause to the same value; a clause change only repaints; a server-rendered whole section gets its clauses ticked on load; pin `pg2` |
| P03 | the picker's markup is unchanged: a whole section is rendered as the section box alone, the details closed, the same clause inputs |
| P04 | the ring's label and disc share one grid cell; the ring is still a centring grid |
| P05 | the ladder rules, and on a rendered Act progress page a learned section gives exactly one filled bar with count 1 and five empty bars |
| P06 | the Learn deck's desktop rule; pin `pg59` |

Mechanical re-pins, no assertion otherwise changed: `playground.css` `pg58` → `pg59` in 57 modules; `playground-select.js` `pg1` → `pg2` in `test_playground_r1.py` and `test_phone_shared_section_picker_screen1.py`.

| Run | SHA | Result |
|---|---|---|
| Modules that read templates, static files or the picker, local, before the full run | `3aff371` tree | 2525 passed / 156 skipped / 0 failed |
| Full suite, local | `1526c25` | **4307 passed / 177 skipped / 0 failed** (919.0 s) — M7a's 4297 plus the 10 new tests |
| CI `workflow_dispatch` 43836421030 | `1526c25` | **success — pytest executed: 4306 passed / 164 skipped / 14 deselected / 0 failed** (1279.9 s) |

Skipped locally: the Playwright-gated screen tests and the Postgres integration tests; counted as skipped, not passed.

## 5. Gates and evidence

| # | Gate | Result |
|---|---|---|
| G1 | Picker (Q8): tick section → all six clauses ticked; untick clause 2 → the other five stay, section indeterminate, the form submits five clause values; tick it again → whole section; untick the section → nothing | PASS on `3aff371` (script unchanged in `9895a3a`) — candidate trace `m7b/02-candidate-9895a3a/picker-trace/` beside the baseline trace; no script exception |
| G2 | What the picker submits is saved as decided, under both models: a whole section with its clause values is one whole section; all clauses alone are promoted; all but one stay as those clauses; an unticked section is removed | PASS — P01 |
| G3 | The picker page's markup and first render are unchanged | PASS — P03; the four picker frames are byte-identical to the baseline |
| G4 | The ring shows its fraction inside the ring | PASS — P04; frames `law`, `law-new` |
| G5 | Ladder bars are drawn; a rung with sections is filled, an empty rung keeps a baseline | PASS — P05; frames `law` |
| G6 | The Learn deck keeps its natural height on desktop | PASS — P06; frames `learn-*` at 1280 |
| G7 | Nothing else moved | PASS — of the 44 candidate frames 26 are byte-identical to the baseline (every phone Learn frame, Learn `type` at 1280, the picker, learned and mastered); the 18 that differ are Act progress at both widths (`law`, `law-new`) and Learn `read`, `cloze`, `letters`, `recite`, `test` at 1280. The page probe's counts are the same on all 44 rows |

Page probe, 44 rows (`m7b/02-candidate-9895a3a/plus/page-probe.json`): no horizontal scroll, no script exception, a focus ring on every Tab stop recorded. **Open, pre-existing and unchanged — not a pass:**

- Light theme: the small grey labels (`--pg-mid`, `--pg-faint`) at 2.38–2.74:1 on Act progress, Learn and the picker (the picker's "SECTION n" eyebrows alone account for 713 of them on BNS) — the same programme-wide style as M7a's W16.
- Targets under 44 px: the desktop back link (78 × 32, and 93 × 32 on the picker — M7a's W17); Learn `cloze` "Reveal all" 86 × 38 (both widths); Learn `letters` "Just read" and "Speak it" 90 × 34 (desktop); the Learn `test` answer radio 13 × 13 (both widths; its label was not measured as part of the target).
- Completion pages: the "Day 3 … Day 60" pills measure 4.49:1.
- Two probe readings are not defects: the cloze blanks' hidden words measure 1.09:1 in the dark theme because they are deliberately the colour of their blank until revealed; "Section 1 · Learning" at 2.78:1 on dark Act progress is visually-hidden text for assistive technology.

## 6. Differences from the prototype that need the owner's decision (not built)

| # | Screen | Prototype | Application today | Recommendation |
|---|---|---|---|---|
| F1 | Act progress, desktop | a grey head band, then a white body in two columns: ring, "8 of 12 · sections in the ladder", chips and stacked actions on the left; "Your sections" squares and the ladder chart on the right | one column on the page grey; the chip, the two labels and the chart sit close together under the ring | Restyle to the two-column body (stylesheet and a small regrouping of the template). No streak chip: the application has no streak. |
| F2 | Act progress head | short title with the "In Playground" chip beside it | full short name as a large title, the chip on its own line | Keep the title; put the chip beside it on desktop. |
| F3 | Learn, desktop | one focused step: stepper, eyebrow, task heading, the text, one action bar at the bottom | adds the six mode tabs, a "n of 6 methods" line and the six-card deck beside the text | The tabs and the deck both move between modes. Keep the tabs; remove the deck at desktop so the text takes the main column. Phone is already the focused step. |
| F4 | Learn action | a fixed bar at the bottom of the stage ("I've read this →") | the action sits at the end of the panel in the right column | Follow the prototype's bar once F3 is decided. |
| F5 | Completion pages | check badge; "Section 8 · NDPS Act" eyebrow; the pill row runs "Learned ✓ · Day 1 … Day 60 · Mastered"; a quotation and "Back to Playground" on the right; the top navigation stays visible | no badge; "Section 3" eyebrow; pills Day 1 … Day 60; the first-revision date; "Continue"; no navigation | Add the badge, the Act name and the two end pills; keep the first-revision line and "Continue" (they are the working next step). Do not add the quotation: it is content the application does not hold. |
| F6 | Picker | chapter headings in the small label style on a white body | chapter headings in large display capitals on the page grey | Small-label chapter headings; the body treatment with F1. The clause-level picking the application has and the prototype omits stays. |
| F7 | Marks | "In the news" and "Important" marks on the picker and Learn | no such feature | Out of scope: a feature, not a restyle. |
| F8 | Targets and contrast (§5) | — | sub-44 px Learn controls; label greys | The Learn controls can be raised to 44 px with F3 / F4; the label greys belong to the shared-style correction already recommended (M7a W16). |

## 7. Not run and limitations

- Hosted comparison: NOT RUN (staging blocked, `M5-staging-prep.md`).
- Live speech (`letters`, `recite`): NOT RUN — no speech provider locally. The typed fallback was rendered, not exercised by this candidate (no change to those modes).
- Automated accessibility scan, screen reader, real zoom: NOT RUN.
- Playwright-gated screen tests: skipped locally (not installed).
- The picker's click behaviour is evidenced by the CDP trace, not by an automated test in the suite: no browser is available to it. The suite pins the script's structure and what the server saves.
- One account (Plus, `monthly`) was captured; these pages have no tier or model branch.
- Sections 2 and 3 of the fixture were given their progress through the repository's completion methods with a placeholder source identity, so Learn frames were taken on section 1, whose two completions went through the endpoint.

## 8. Owner sign-off

None recorded. M7b was authorised to start; this candidate is offered for review. Sign-off is recorded only against the owner's direct answer.
