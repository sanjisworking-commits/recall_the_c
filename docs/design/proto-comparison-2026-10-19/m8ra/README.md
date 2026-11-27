# M8-Ra — subscription and device edge states: evidence

Record: `docs/design/milestones/M8-Ra.md`; test changes `M8-Ra-test-changes.md`; billing matrix `M8-Ra-billing-matrix.md`. Local evidence only. **Every account state here is a subscription row seeded into a throwaway local database; no payment provider is configured or called, and nothing in this folder shows what the provider does.**

| Path | What it holds |
|---|---|
| `../m8/tools/readback_m8.py` | Read-back through the application's own test client: 13 subscription states and two device states × both tier models × 13 pages. Per page: status or redirect, header label, headings, the Add sheet's title, the gate reason, every link and form that leads to the Playground, billing or Devices (and whether a link is marked as a sheet opener), the Devices lede, and a hash of the page body with request tokens, generated ids and clock times removed. Each state is tagged P (production-reachable stored shape) or S (synthetic fixture). |
| `../m8/tools/diff_readback_m8.py` | Compares two read-backs row by row: identical, or which recorded fields differ. |
| `../m8/tools/serve_states_m8.py` | Serves one account in one state for browser capture (same seeding as the read-back); `--other-devices N` registers N other browsers first. |
| `../m8/tools/billing_matrix_m8.py` | The billing state / action matrix: what the billing page offers and what each billing route does for 18 stored shapes under both models, against a **mocked** provider client. |
| `../m8/tools/probe_style_m8s.py` | The capture and probe tool of M8-S, with `--pre revoke-own-device` (the session removes its own device and signs in again) and `--settle` (ordinary full-height frames for pages that fade in). |
| `routes-*.json` | The routes captured per state. |
| `01-baseline-67c7101/` | The M8-S head, whose edge-state source is identical to `079257e`: `readback.json` / `.md`; `frames/` (38); `style-probe-*.json`. The read-back ran against the `pg-m8s` worktree at `67c7101`; the frames against the same worktree after its evidence commit `6668f50` (no source change between the two). |
| `02-candidate-2270d77/` | Source `2270d77`, read at tests commit `97edd4e`: `readback.json` / `.md`; `readback-diff.json` (254 rows identical, 108 changed — each accounted for in `M8-Ra.md` §5); `billing-matrix.json` / `.md`; `frames/` (38, same names as the baseline); `style-probe-*.json`. |

Frames are named `<state>-<route>-<width>-<theme>.png`.

Known instability, recorded rather than hidden: the order of law cards on a read-only home, and once the body of an active account's home and Manage laws, differ between two renders of the same account. The comparison treats link order as a set; a row that differs only for that reason shows as a body-only difference.

The `style-probe-*.json` rows for Today, Calendar and the Bare Act reader are body-wide and include text coloured by site-wide tokens under 4.5:1 (`M8-S.md` §5). They are not assessed in this batch.
