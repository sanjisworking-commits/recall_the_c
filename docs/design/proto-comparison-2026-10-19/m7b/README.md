# M7b — Act progress, picker, Learn, completion pages · evidence folder

Milestone and evidence record: `docs/design/milestones/M7b.md`.

| Path | What |
|---|---|
| `tools/trace_picker_m7b.py` | Click-by-click trace of the picker over CDP: tick a section, click one clause, click it again, untick the section; after each step the section box, the ticked clauses, the block state, what the form would submit, the counter and the submit label. Screenshot after step 2. The browser profile lives in a temporary directory outside the repository. |
| `01-baseline-0810bc2/` | Before any M7b edit: `plus/` — 11 routes (Act progress for a law in progress and a law not started, picker, the six Learn modes, learned, mastered), 390 and 1280, light and dark, 44 frames with `manifest.json` and `page-probe.json`; `picker-trace/` — the defect trace. Route list `routes-learn.json`. |
| `02-candidate-9895a3a/` | Candidate: `plus/` — the same 44 frames and probe (26 byte-identical to the baseline; the 18 that differ are Act progress and five Learn modes at 1280); `picker-trace/` — the trace after the change (recorded on `3aff371`; the script is unchanged in `9895a3a`). |

| `tools/check_learn_m7b.py` | Browser checks of Learn over CDP: where the action bar sits at four window sizes, whether any focus stop ends up under it (readings taken after the browser's focus scroll settles), the six mode tabs, and the typed fallback exercised for letters and recite. Writes `learn-check.json`. Live speech is not exercised. |
| `03-design-0274a22/` | Design batch: `plus/` — the 44 frames on `0274a22` (16 byte-identical to the first candidate: every phone frame except Learn `test` and the completion pages) with `manifest.json`, and `page-probe.json` measured on `c6a6297` (the later commit adds only a gap on the completion steps); `learn-check/learn-check.json` on `0274a22`. The picker traces of `02-candidate-9895a3a/` still apply: the script has not changed. |

The executed picker interaction test lives in the suite: `tests/test_playground_picker_interaction.py` with `tests/js/picker_harness.js`.

The populated state comes from `m7/tools/serve_populated_m7.py --scenario learn` (the application's own save points and the Learn completion endpoint; progress for the learned and mastered sections through the repository's completion methods). Frames use `m1r/tools/capture_m1r.py`, probes `m7/tools/probe_page_m7.py`. Prototype references are not committed.

All of this is local evidence. Hosted comparison is NOT RUN.
