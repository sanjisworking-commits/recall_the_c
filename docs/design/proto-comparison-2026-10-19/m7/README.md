# M7 — Playground flows · evidence folder

Milestone record: `docs/design/milestones/M7.md`.

| Path | What |
|---|---|
| `tools/readback_m7.py` | Read-back through the app's TestClient: nine account states × two tier models × the Playground routes (home empty / populated, Manage laws, roster Add and re-add confirm, Remove, rollover, Act progress, picker, Learn, learned, mastered). Records headings, markers, capacity attributes, every month-model phrase, rollover links, law-card memberships and the response of each save point used to populate. |
| `tools/serve_populated_m7.py` | Serves one signed-in account whose Playground was filled through the application's own save points on a throwaway database (`--tier`, `--tier-model`, `--scenario empty|populated|free2`). No payment, no entitlement edit beyond the fixture subscription row. |
| `01-baseline-6d9d4c7/` | Before any M7 edit, on the M6 head with `origin/main` merged: `readback/` (210 rows), `plus/` (ten routes, `monthly`), `pro/` (`monthly`), `free-choices/` (three choices used), `plus-choices/` — 390 and 1280, light and dark, 76 frames with `manifest.json` (SHA-256 and shell probe per frame). Route lists: `routes-flows.json`, `routes-home.json`. |

Captures use `m1r/tools/capture_m1r.py` (headless Chrome over CDP; the dev fake Google sign-in; no cookie or token is written to disk). Design references: the 18 Oct prototype export and the tier-revision handover frames (`desktop-12/13/19`, `phone-11/12/19`); they are not committed here.

All of this is local evidence. Hosted comparison is NOT RUN.
