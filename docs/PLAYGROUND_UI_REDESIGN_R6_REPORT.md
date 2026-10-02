# Playground UI Redesign — R6 report

Today path merge, desktop Calendar week, clause chips, and Google Calendar
pending-rung extra. R7 responsive closeout is **not** started. Stage 1 remains
frozen except the T33 pin this batch required. Stage 2 remains parked. R5
(U3 leftover + U7) was not reopened.

This file is the batch closeout. Later batches should add
`docs/PLAYGROUND_UI_REDESIGN_R{n}_REPORT.md` the same way.

Authoritative docs:

- [PLAYGROUND_UI_REDESIGN_PLAN.md](PLAYGROUND_UI_REDESIGN_PLAN.md)
- [PLAYGROUND_UI_REDESIGN_TRACKER.md](PLAYGROUND_UI_REDESIGN_TRACKER.md)
- [design/PLAYGROUND_DESIGN_INVENTORY.md](design/PLAYGROUND_DESIGN_INVENTORY.md)

```text
Stage 1               = DONE — 100.0 / 100, frozen
UI Redesign Programme = 90.0 / 100
U0                     = 10 / 10
U1                     = 28 / 28
U2                     = 39 / 39
U3                     = 38 / 38
U4                     = 28 / 28
U5                     = 13 / 13  (includes T42)
U6                     = 15 / 15
U7                     = 12 / 12
R5                     = DONE (frozen)
R6                     = DONE
R7                     = not started
Stage 2                = PARKED
```

**Branch:** `cursor/playground-220d`  
**PR:** [#188](https://github.com/sanjisworking-commits/recall_the_c/pull/188) (draft)

The 90.0 programme score is calculated from proven tracker rows (U6 15/15),
not forced.

---

## Acceptance

| | |
|---|---|
| Targeted | U6 D115–D124, T28–T32. Deltas A (T30), B (T31), C (T28), D (T29). |
| Completed | Today merge + New rule, week view, clause chips, Google extra, T32 guards, visual matrix, tracker closeout. |
| Remaining | R7 responsive / a11y / parity (U8). Do not start it from this report. |
| Programme score before | 80.0 / 100 |
| Programme score after | **90.0 / 100** |
| Alembic | one head: `20260927_0027`. No R6 migration. |

No new Class-D product decision. No newly discovered B/C rows.

---

## Branch state

| | SHA |
|---|---|
| Starting (R5 frozen HEAD) | [`ffe374d`](https://github.com/sanjisworking-commits/recall_the_c/commit/ffe374d) |
| Implementation | [`0011124`](https://github.com/sanjisworking-commits/recall_the_c/commit/0011124) |
| extra_loader spy / UUID pin | [`1860dab`](https://github.com/sanjisworking-commits/recall_the_c/commit/1860dab) |
| Tracker closeout | [`34db64f`](https://github.com/sanjisworking-commits/recall_the_c/commit/34db64f) |

| SHA | What |
|-----|------|
| `0011124` | Today path merge; week model/route; Playground chips; Google `extra=`; T32 optional tables; T33 `main75`/`mob96` |
| `1860dab` | Keep Constitution sync on the three-arg prepare path; restore UUID import in `test_playground_r6.py` |
| `34db64f` | Tracker + R6 report: U6 15/15, programme 90.0 |

Nothing from R0–R5 was reopened except the T33 asset pin and the planned T40
rewrites (`TodayUnit` fields, `/calendar?view=week`, m8 path nodes).

---

## Architecture (thin layer)

R6 is one scheduling read model over Stage 1. It does not add a queue table,
a calendar table, or a migration.

| Concern | Authority |
|---|---|
| Today merge | Constitution dones, then Playground dues, then Constitution pending, then at most one New. `_restamp_today_path` |
| New rule | Most recently active roster law (`last_activity_at`); first selected unlearned locator not missing/omitted-blocked; Act order |
| `due_count` | Constitution due + Playground dues. New is never counted |
| Goal ring | Same exclusion as `due_count` (New omitted) |
| Entitlement | `playground_view_access.can_open` before listing. Paused/lapsed list nothing Playground |
| Week | Sunday–Saturday via `(weekday()+1)%7`. Phone CSS-hides week even if the URL is `view=week` |
| Chips | `{short} · §{citation} · Playground`. Clause locators use `citation_label` |
| Google extra | Pending Playground rung only (`list_revision_schedule`). Overdue rolls to today. Description cap 15 |
| Isolation | `extra_loader` failures never fail Constitution sync. `playground_google_extra` swallows all Playground errors |
| T32 | Missing optional Playground tables degrade. UNIQUE / other SQL still surfaces |

Constitution learning hero stays in learning mode when the only dues are
Playground — the path current-node card is the Playground revision surface
(D116), so the hero is not flipped to an empty Start revision.

---

## Visual matrix

Captured with Playwright + system Chrome (`channel="chrome"`), device metrics.
Multiuser seed: NDPS Section 8(a) due today, Section 1 unlearned New.

Desktop ≥900px: `.dash-top` is `minmax(280px, 380px) 1fr` (measured 380px + 716px
at 1280). `.calendar-view-switch` and `.calendar-week` show only from 900px.
Phone `data-mscreen="revisions"` hides week, switch, and desktop month grid.

| State | Evidence | Notes |
|---|---|---|
| Today path 390/1280 light | `r6_today_path_390_light.png`, `r6_today_path_1280_light.png` | Day 1 → 3 · Playground current node; New · Playground; gear → Settings |
| Today path 390/1280 dark | `r6_today_path_390_dark.png`, `r6_today_path_1280_dark.png` | Same chrome |
| Today reduced motion | `r6_today_path_390_reduced.png` | Same chrome |
| Week 1280 light/dark | `r6_calendar_week_1280_light.png`, `r6_calendar_week_1280_dark.png` | Month/Week switch; seven columns; today ring; §8(a) · Playground; Review due · Playground; Nothing due; Overdue in legend |
| Week reduced | `r6_calendar_week_1280_reduced.png` | Same chrome |
| Phone calendar | `r6_calendar_phone_390_light.png`, `r6_calendar_phone_390_dark.png` | Month grid; GCal footnote “pending rung only” |
| Month desktop | `r6_calendar_month_1280_light.png` | Dotted Playground chip `NDPS Act · §8(a) · Playground` |
| Walkthrough | `r6_today_path_and_calendar_week.webm` | Today path → month → week → month |

---

## Tests

Stage 1 assertions superseded on purpose (record, do not weaken silently):

- T33: `styles.css?v=main75` (not main74). `mobile.css?v=mob96` (not mob95).
  `playground.css?v=pg17`, `playground.js?v=pg8` unchanged.
- T40: `TodayUnit` has `source` / `eyebrow` / `cta_label`. `/calendar?view=week`
  exists. m8 Today no longer asserts a “Law revisions” block.

| Run | Result |
|---|---|
| `tests/test_playground_r6.py` + `tests/test_calendar_week.py` | **18 passed** |
| Focused R6 + m8 + r5 + r1 + calendar projection/sync + dashboard + settings_phone + sprint30 + study_sessions | **175 passed** |
| `pytest -m "not integration"` on `1860dab` | **2866 passed**, 9 skipped, 1 deselected |
| CI on `1860dab` | push [36997823976](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36997823976) and PR [36997827761](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36997827761) succeeded |

---

## Programme score

| | |
|---|---|
| Before | 80.0 / 100 |
| Newly proven | U6 15 |
| U6 | 15 / 15 → **10.0** |
| After | **90.0 / 100** |

Rows closed this batch:

- U6: D115, D116, D117, D118, D119, D120, D121, D122, D123, D124, T28, T29, T30, T31, T32
- Deltas: A (T30), B (T31), C (T28), D (T29)

---

## Remaining / R7 handoff

R6-targeted rows: **DONE**. Do not start R7 from this report.

R7 starts at responsive reconciliation, accessibility, prototype commit, and
tracker closeout (U8, V1–V24). Stage 2 stays PARKED until the programme is
100.0 / 100.

Alembic head remains **`20260927_0027`**.
