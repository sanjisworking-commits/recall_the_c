# M6 local evidence — Calendar (classic)

Branch `pg-m6-calendar` (PR #244); record in `docs/design/milestones/M6-evidence.md`.

| Folder | Content |
|---|---|
| `01-baseline-4221d53/free/` | baseline Free month and week at 390×844 and 1280×900, light + dark, probe manifests with Tab trails on the light rows |
| `01-baseline-4221d53/readback/` | `readback.md` / `.json`: nine account states × `monthly` / `choices` × both flags × month / week on the baseline |
| `01-baseline-4221d53/routes.json` | the two-route list passed to `capture_m1r.py --routes` |
| `02-candidate-ac8ff53/free/` | candidate Free month and week (empty), same grid, signed in through the dev launcher (`monthly`) |
| `02-candidate-ac8ff53/free-populated/` | candidate Free month with a memorized unit, a review due today, an overdue review and scheduled reviews, served by `tools/serve_populated_m6.py` (390 / 1280 × light / dark) |
| `02-candidate-ac8ff53/free-choices/` | candidate Free under `choices`: the gated "Add task" entry at 390 / 1280 light, and `free-choices_free_calendar-sheet_1280x900_{light,dark}.png` with the upgrade sheet open (`manifest-sheet.json`: open / focus / Tab / Esc / exceptions, by `tools/capture_sheet_m6.py`) |
| `02-candidate-ac8ff53/plus/` | candidate Plus month, populated, 390 + 1280 light (shared paid marker) |
| `02-candidate-ac8ff53/plus-dev/` | the dev launcher's Plus account: `/playground` then `/calendar` at 1280 light (Playground chip check, see the evidence record) |
| `02-candidate-ac8ff53/halted/` | candidate halted phone month, populated, 390 light + dark |
| `02-candidate-ac8ff53/readback/` | the nine-state read-back on the candidate under both tier models and both flags (72 rows) |
| `02-candidate-ac8ff53/routes*.json` | the route lists used for each cohort |

Tools (run from the repository root with the project venv):

```
PYTHONPATH=.:src .venv/bin/python docs/design/proto-comparison-2026-10-19/m6/tools/readback_m6.py --out <dir>
PYTHONPATH=.:src .venv/bin/python docs/design/proto-comparison-2026-10-19/m6/tools/serve_populated_m6.py --port 8925 [--tier plus|pro|max|expired|halted] [--tier-model choices]
.venv/bin/python docs/design/proto-comparison-2026-10-19/m1r/tools/capture_m1r.py --base http://127.0.0.1:<port> --out <dir> --label <label> --routes <routes.json> --widths 390x844,1280x900 --themes light,dark --focus calendar,calendar-week --signin --tier <free|plus|halted>
.venv/bin/python docs/design/proto-comparison-2026-10-19/m6/tools/capture_sheet_m6.py --base http://127.0.0.1:<choices port> --out <dir> --label <label>
```

The dev launchers `playground-m6-<tier>` (monthly) and `playground-m6-<tier>-choices` serve the worktree on port 8924 (scripts outside the repository; one tier per server start). `serve_populated_m6.py` seeds progress rows through the engine's own repository, never a payment or an entitlement change: the account is Free unless `--tier` names a subscription row. Prototype references: the 18 Oct export's `viewer=plus&seed=1&calDesign=classic` Calendar frames (phone and desktop), generated with the M4 wrapper from `~/Downloads`; the Study-material rows of the prototype are the parked Archive tab and are not compared.
