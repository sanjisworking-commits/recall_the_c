# M5 local evidence — Account, Devices and Plans

Branch `pg-m5-account` (PR #240); record in `docs/design/milestones/M5-evidence.md`.

| Folder | Content |
|---|---|
| `01-baseline-e9ca1e4/guest/`, `free/` | baseline Profile, Settings, Devices, gate and plans (`?stage=plans&tier=plus`) at 390×844 and 1280×900, light + dark, probe manifests with Tab trails on the light rows |
| `01-baseline-e9ca1e4/readback/` | `readback.md` / `.json`: nine account states × `monthly` / `choices` × five routes on the baseline (regenerated with the corrected CSRF columns) |
| `01-baseline-e9ca1e4/routes.json` | the five-route list passed to `capture_m1r.py --routes` |
| `02-candidate-d2d6436/guest/` | candidate guest Profile, Settings, Devices (redirect), gate and plans at 320 / 390 / 1280, light + dark |
| `02-candidate-d2d6436/free/` | candidate Free, same grid, signed in through the dev launcher |
| `02-candidate-d2d6436/plus/` | candidate Plus at 390 / 1280, light + dark: Playground first (registers the device on the dev server), then Profile, Devices (populated), the change-plan stage (`?stage=plans&tier=pro`) and Settings |
| `02-candidate-d2d6436/halted/` | candidate halted Profile and Settings at 390 / 1280, light (the phone halted rules) |
| `02-candidate-d2d6436/readback/` | the nine-state read-back on the candidate under both tier models |
| `02-candidate-d2d6436/routes*.json` | the route lists used for each cohort |

Tools (run from the repository root with the project venv):

```
PYTHONPATH=.:src .venv/bin/python docs/design/proto-comparison-2026-10-19/m5/tools/readback_m5.py --out <dir>
.venv/bin/python docs/design/proto-comparison-2026-10-19/m1r/tools/capture_m1r.py --base http://127.0.0.1:8922 --out <dir> --label <label> --routes docs/design/proto-comparison-2026-10-19/m5/01-baseline-e9ca1e4/routes.json --widths 390x844,1280x900 --themes light,dark --focus profile,settings,devices,playground,playground-plans --signin --tier <free|plus|halted>
```

The dev launchers `playground-m5-<tier>` (monthly) and `playground-m5-<tier>-choices` serve the worktree on port 8922 (scripts outside the repository; one tier per server start). Prototype references: the M0 frames under `docs/design/proto-comparison-2026-10-18/{phone,phone-signedin,desktop,desktop-signedin}/proto_*_{profile,settings,devices,gate}_*.png` (PR #218); the desktop prototype has no plans stage and no Devices empty state.
