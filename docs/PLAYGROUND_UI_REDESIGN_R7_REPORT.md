# Playground UI Redesign — R7 report

Responsive, accessibility, parity, and frozen-domain closeout (U8). Stage 1,
R5, and R6 remain frozen. Stage 2 remains parked. PR 188 stays a draft. Do
not merge.

Work followed the approved order: inventory / V24 → T40 ledger (docs only) →
V15 → responsive → theme → reduced motion → keyboard/focus → semantics →
V11 → **T40 execution** → **V16/V17/V18** → focused + full suite → visual /
CI / Railway → handoff. Frozen-domain regression did not run before the
authorized T40 rewrites.

Authoritative docs:

- [PLAYGROUND_UI_REDESIGN_PLAN.md](PLAYGROUND_UI_REDESIGN_PLAN.md)
- [PLAYGROUND_UI_REDESIGN_TRACKER.md](PLAYGROUND_UI_REDESIGN_TRACKER.md)
- [PLAYGROUND_UI_REDESIGN_R7_LEDGER.md](PLAYGROUND_UI_REDESIGN_R7_LEDGER.md)
- [design/PLAYGROUND_DESIGN_INVENTORY.md](design/PLAYGROUND_DESIGN_INVENTORY.md)
- [design/PLAYGROUND-FINISH-HANDOFF.md](design/PLAYGROUND-FINISH-HANDOFF.md)

```text
Stage 1               = DONE — 100.0 / 100, frozen
UI Redesign Programme = 100.0 / 100
U0                     = 10 / 10
U1                     = 28 / 28
U2                     = 39 / 39
U3                     = 38 / 38
U4                     = 28 / 28
U5                     = 13 / 13  (includes T42)
U6                     = 15 / 15
U7                     = 12 / 12
U8                     = 25 / 25
R5                     = DONE (frozen)
R6                     = DONE (frozen)
R7                     = DONE
Stage 2                = PARKED
```

**Branch:** `cursor/playground-220d`  
**PR:** [#188](https://github.com/sanjisworking-commits/recall_the_c/pull/188) (draft)

Programme score is `90 + 10 × proven_U8 / 25`. U8 is 25/25, so the
programme is **100.0 / 100** by the formula. That is not a forced 100:
rows without evidence stay open, and none were marked DONE to chase the
ceiling.

---

## Acceptance

| | |
|---|---|
| Targeted | U8 T40, V1–V24. |
| Completed | Ledgers, a11y/responsive reconciliation against existing D rows, authorized T40 rewrites, frozen-domain regression, visual matrix, CI, Railway, handoff. |
| Remaining | Merge is not this batch. Stage 2 stays PARKED. |
| Programme score before | 90.0 / 100 |
| Programme score after | **100.0 / 100** |
| Alembic | one head: `20260927_0027`. No R7 migration. |

No new Class-D product decision. No newly discovered B/C denominator rows.
Stop log empty.

---

## Branch state

| | SHA |
|---|---|
| Starting (R6 frozen HEAD) | [`56065c2`](https://github.com/sanjisworking-commits/recall_the_c/commit/56065c2) |
| Implementation | [`fc0ca67`](https://github.com/sanjisworking-commits/recall_the_c/commit/fc0ca67) |
| Closeout docs | [`a2fdde7`](https://github.com/sanjisworking-commits/recall_the_c/commit/a2fdde7) |

| SHA | What |
|-----|------|
| `fc0ca67` | Ledgers; overflow / focus / 44px / reduced-motion / ~1024 collision; T40-4 Today path; T40-5 eligible Act loop; T33 `main76` / `mob97` / `pg18` (`pg8` unchanged) |

Nothing from Stage 1, R5, or R6 was reopened except the T33 asset pin and
the two T40 rewrites the ledger authorized.

---

## Architecture (thin layer)

R7 is CSS + test-contract closeout. It does not add routes, tables, or a
migration.

| Concern | Authority |
|---|---|
| Order | T40 execution before V16/V17/V18 |
| Phone chrome | `mobile.css` `@media (max-width: 560px)` tab bar. ~768 is 561–899 flex header |
| Desktop chrome | ≥900px (D18). V3 is the 900–1039 collision pass |
| Calendar week | `min-width: 900px` only |
| V11 | min-size / padding. Settings **styling** frozen (D113). Constitution Learn not rebuilt |
| V15 `APPROVED DEVIATION` | Classification only. Cannot close V11 |
| Class B | Token / focus / overflow / 44px against D1–D17. New mismatch that needs a new D row = STOP |
| Legal | Class B |
| Admin | Class D, V18 regression only |
| Prototypes | No `.dc.html` edits |

Fair work shipped: `overflow-x: hidden` on shell/main; global
`:focus-visible`; 44px min on applicable phone controls; reduced-motion
collapse of remaining `.panel` motion; 900–1039 `min-width: 0` on week
grid, header, home grid, and Act-head CTA.

---

## T40

| ID | Change | Weakened? |
|---|---|---|
| T40-1..3 | Already executed in R3/R5 | no |
| T40-4 | `test_today_queue_current_roster_only` now pins `data-today-path-card`, `data-today-kind="review"` ≥2, `Day 3 → 7 · Playground`, `Day 1 → 3 · Playground`, `Start revision →`, `"Law revisions"` absent, BNSS absent, BNS before NDPS | no |
| T40-5 | `test_current_acts_show_no_badge` loops `list_playground_eligible_laws()` | no |

V17 includes M8. Running V17 before T40-4 would have treated the obsolete
“Law revisions” heading as a new frozen R6 defect. That is why step 10
precedes step 11.

---

## Visual matrix

Captured with Playwright + system Chrome (`channel="chrome"`). Representative
screenshots only. Every family and listed Class-C state was inspected
(HTTP + template), including surfaces that share a screenshot.

The first 1024 Act-head capture was mid-rise animation (washed-out body,
full-contrast chrome). Recapture under `prefers-reduced-motion` is the
collision proof — CTA column sits beside the title, seven-day week fits
at 1024 with a text legend.

Today 1280 still shows “Nothing to review today” next to a New NDPS path
card. That is frozen T28: New is excluded from `due_count`. Not an R7 fix.

| State | Evidence |
|---|---|
| Home 390/768/1024/1280 | `r7_home_*.png` — 768 is flex header, not 900px 3-column |
| Today | `r7_today_390_light_settled.png`, `r7_today_1280_light.png` |
| Week 1024/1280 | `r7_calendar_week_1024_light.png`, `r7_calendar_week_1280_light.png` |
| Settings 44px + focus | `r7_settings_390_light.png`, `r7_settings_focus_390_light.png` |
| Act-head 1024 | `r7_act_head_1024_reduced.png` |
| Gate / D142 / devices | `r7_gate_guest_390_light.png`, `r7_d142_404_390_light.png`, `r7_devices_390_light.png` |
| Legal / login / landing | `r7_legal_terms_390_dark_view.png`, `r7_auth_login_390_light_view.png`, `r7_landing_390_light.png` |

---

## Tests

| Run | Result |
|---|---|
| `tests/test_playground_r7.py` | ledger order, Class B/C, T40 authorization, V15, V24 `_walk_paths` via `original_router`, CSS contracts, D102 titles, V11 settings, week desktop-only |
| `pytest -m "not integration"` on `fc0ca67` | **2888 passed**, 9 skipped, 1 deselected |
| CI on `fc0ca67` | push [37022804844](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/37022804844) and PR [37022809702](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/37022809702) succeeded |
| Railway on `fc0ca67` | `trustworthy-embrace / recall_the_c-pr-188` success |

V19/V20 closed only after those greens.

---

## Programme score

| | |
|---|---|
| Before | 90.0 / 100 |
| Newly proven | U8 25 |
| U8 | 25 / 25 → **10.0** |
| After | **100.0 / 100** |

Rows closed this batch: T40, V1–V24.

---

## Remaining

R7-targeted rows: **DONE**. Do not merge PR 188 from this report.

Stage 2 stays PARKED. Do not start S2-0 from this closeout.

Alembic head remains **`20260927_0027`**.
