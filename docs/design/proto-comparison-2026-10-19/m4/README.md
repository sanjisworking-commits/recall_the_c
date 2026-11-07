# M4 local evidence — Today (`/dashboard`)

Branch `pg-m4-today`; record in `docs/design/milestones/M4-evidence.md`.

| Folder | Content |
|---|---|
| `01-baseline-6186863/guest/` | guest `/dashboard` at 390×844 and 1280×900, light + dark, probe manifest (`manifest.json`, Tab trail on the light rows) |
| `01-baseline-6186863/free/` | Free first run, same grid, signed in through the dev launcher's fake Google sign-in |
| `01-baseline-6186863/free-populated/` | Free with one completed Article and two clauses due, served by `tools/serve_populated_m4.py` |
| `01-baseline-6186863/readback/` | `readback.md` / `readback.json`: nine account states × `monthly` / `choices` × first run / after one real Learn → Done |
| `01-baseline-6186863/routes.json` | the single-route list passed to `capture_m1r.py --routes` |
| `02-candidate-3e06fb0/guest/` | candidate guest `/dashboard` at 320×568, 390×844, 720×900 and 1280×900, light + dark (the 320 / 390 rows re-captured after the narrow-width greeting fix that follows `3e06fb0`) |
| `02-candidate-3e06fb0/free/` | candidate Free first run, same grid, signed in through the dev launcher |
| `02-candidate-3e06fb0/free-populated/` | candidate Free populated (served by `tools/serve_populated_m4.py`), 390 / 1280 × light / dark — the desktop path header now reads "0 of 1 reviewed" |
| `02-candidate-3e06fb0/readback/` | the nine-state read-back on the candidate (legacy-copy scan limited to `<main>`; the shell's own Sign in link is M1-R's) |

Tools (run from the repository root with the project venv):

```
PYTHONPATH=.:src .venv/bin/python docs/design/proto-comparison-2026-10-19/m4/tools/readback_m4.py --out <dir>
PYTHONPATH=.:src .venv/bin/python docs/design/proto-comparison-2026-10-19/m4/tools/serve_populated_m4.py --port 8921 [--tier plus|pro|max|expired|halted]
.venv/bin/python docs/design/proto-comparison-2026-10-19/m1r/tools/capture_m1r.py --base http://127.0.0.1:8921 --out <dir> --label <label> --routes docs/design/proto-comparison-2026-10-19/m4/01-baseline-6186863/routes.json --widths 390x844,1280x900 --themes light,dark --focus dashboard --signin --tier free
```

The dev launchers `playground-m4-<tier>` (monthly) and `playground-m4-<tier>-choices` serve the worktree on port 8920 (scripts outside the repository). Prototype references: the 18 Oct 2026 export (`Recall the C - Playground[ Desktop].dc.html`, served with `make_wrappers.py` from the M0 captures folder, `screen=today`, `viewer=guest|signedIn|plus`, `seed=1`); the frames M0 committed under `docs/design/proto-comparison-2026-10-18/{phone,phone-signedin,desktop,desktop-signedin}/proto_*_today_*.png` (PR #218). The export committed in `docs/design/` at this SHA is the 29 Sep version and has no guest Today.
