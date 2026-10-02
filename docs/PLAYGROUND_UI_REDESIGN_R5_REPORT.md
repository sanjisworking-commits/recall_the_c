# Playground UI Redesign — R5 report

Roster/rollover restyle plus Profile, Settings, and account surfaces. R6 Today / Calendar / Google is **not** started. Stage 1 remains frozen except the T33 pin this batch required. Stage 2 remains parked. R4 (T22–T25, T42) was not reopened.

This file is the batch closeout. Later batches should add `docs/PLAYGROUND_UI_REDESIGN_R{n}_REPORT.md` the same way.

Authoritative docs:

- [PLAYGROUND_UI_REDESIGN_PLAN.md](PLAYGROUND_UI_REDESIGN_PLAN.md)
- [PLAYGROUND_UI_REDESIGN_TRACKER.md](PLAYGROUND_UI_REDESIGN_TRACKER.md)
- [design/PLAYGROUND_DESIGN_INVENTORY.md](design/PLAYGROUND_DESIGN_INVENTORY.md)
- Prototypes: `docs/design/Recall the C - Playground Desktop.dc.html`, `docs/design/Recall the C - Playground.dc.html`

```text
Stage 1               = DONE — 100.0 / 100, frozen
UI Redesign Programme = 80.0 / 100
U0                     = 10 / 10
U1                     = 28 / 28
U2                     = 39 / 39
U3                     = 38 / 38
U4                     = 28 / 28
U5                     = 13 / 13  (includes T42)
U6                     = 0 / 15   (R6)
U7                     = 12 / 12
R4                     = DONE (frozen)
R5                     = DONE
R6                     = not started
Stage 2                = PARKED
```

**Branch:** `cursor/playground-220d`  
**PR:** [#188](https://github.com/sanjisworking-commits/recall_the_c/pull/188) (draft)

The 80.0 programme score is calculated from proven tracker rows (U3 leftover 9/9 + U7 12/12), not forced.

---

## Acceptance

| | |
|---|---|
| Targeted | U3 leftover D93–D100, D130. U7 D107–D114, D137–D138, T26–T27. |
| Completed | Restyle, view models, regression, visual matrix, tracker closeout. |
| Remaining | R6 Today/Calendar/Google (U6, T28–T32). Do not start it from this report. |
| Programme score before | 70.2 / 100 |
| Programme score after | **80.0 / 100** |
| Alembic | one head: `20260927_0027`. No R5 migration. |

Roster/rollover is restyle only. Keep / Remove / Undecided and slot consumption stay Stage 1. Entitlement snapshot is the subscription authority. Device counts come from the device service. No Razorpay calls at render. Guest GET `/profile` is HTML 200 (D110). Phone Reminders posts `reminder_cadence` to the existing `/calendar/google/preferences` endpoint (T27). D114 first-connect reminder dialog is the shipped sheet (`=`).

No new Class-D product decision. No newly discovered B/C rows.

---

## Branch state

| | SHA |
|---|---|
| Starting (R4 frozen HEAD) | [`e0c038f`](https://github.com/sanjisworking-commits/recall_the_c/commit/e0c038f) |
| Implementation | [`b17d6ab`](https://github.com/sanjisworking-commits/recall_the_c/commit/b17d6ab) |
| Auth import cycle | [`68d5c2d`](https://github.com/sanjisworking-commits/recall_the_c/commit/68d5c2d) |
| Rollover Done / plan-next card | [`d034024`](https://github.com/sanjisworking-commits/recall_the_c/commit/d034024) |
| Paint/pg16 | [`a894a36`](https://github.com/sanjisworking-commits/recall_the_c/commit/a894a36) |
| D110 noindex rewrite | [`c35f7d5`](https://github.com/sanjisworking-commits/recall_the_c/commit/c35f7d5) |
| Tracker closeout | [`b4ac8d1`](https://github.com/sanjisworking-commits/recall_the_c/commit/b4ac8d1) |

| SHA | What |
|-----|------|
| `b17d6ab` | Roster/rollover restyle; Profile SUBSCRIPTION card; Settings Reminders form; devices/checkout chrome; `tests/test_playground_r5.py` |
| `68d5c2d` | Lazy-import Profile helpers so `create_app` does not cycle through `auth.routes` → `playground.view` |
| `d034024` | Desktop rollover sticky Done hidden; phone footer is Continue only; Plan next month is a card |
| `a894a36` | Disable `.panel` rise on Profile/Settings/checkout; phone Account group `settings-phone-only`; token-only chip colors; T33 `pg16` |
| `c35f7d5` | Guest GET `/profile` stays noindexed; drop `/profile` from 303-gated private pages |
| `b4ac8d1` | R5 report + tracker: U3 38/38, U7 12/12, programme 80.0 |

Nothing from R0–R4 was reopened except the T33 asset pin.

---

## Architecture (thin layer)

R5 is chrome and read-models over Stage 1. It does not duplicate roster capacity, billing, or device engines.

| Concern | Authority |
|---|---|
| Keep / Remove / Undecided | Stage 1 rollover POST (`choice_{law_id}` = keep / decline / undecided) |
| Slot consumption | Stage 1 roster service. Removing does not free a space this month |
| Subscription chip | `playground_subscription_card(snapshot)` from the entitlement snapshot |
| Device “n of limit” | `DeviceService.list_device_summaries` → `device_count_copy`. Never hard-coded “2 of 3” |
| Device identifiers | Not rendered on Profile (T26). Devices page remains the list surface |
| Reminders | Existing `/calendar/google/preferences`. Phone uses a dedicated form so it does not dual-submit `reminder_cadence` with desktop prefs |
| Guest Profile | HTML 200 card. POST still 303/401/403 |
| Today / week / GCal projection | Unchanged. R6 |

`PlaygroundSubscriptionCard` mapping:

- paused → **PAUSED**
- halted → **ON HOLD**
- paid period ended → **PAUSED**
- not subscribed → Subscribe CTA, no chip
- otherwise subscribed → **ACTIVE** plus limit stat

---

## Visual matrix

Captured with Playwright + system Chrome, device metrics. Multiuser seed, so the top nav is Today / Browse / Playground / Calendar / Profile. Phone tab bar hides on `.RolloverPlanner` (T39). Desktop ≥900px hides `.RolloverPlanner .pg-sticky-cta` so Done lives only in the aside.

`.panel { animation: rise }` is skipped on Profile, Settings, and checkout (`pg16`) so those pages paint at full opacity on desktop (phone already set `animation: none`).

| State | Evidence | Notes |
|---|---|---|
| Roster manager 390/1280 | `r5_roster_390_light.png`, `r5_roster_1280_light.png`, `r5_roster_390_dark.png` | Head, 1 of 10 used, rules, Continue/Read/Remove, Plan next month card |
| Add-back dialog | `r5_roster_add_390_light.png`, `r5_roster_add_1280_light.png` | Meter; “No extra space used”; saved-progress line |
| Remove sheet | `r5_remove_390_light.png` | Dialog; progress saved; space not freed |
| Rollover 390/768/1024/1280 | `r5_rollover_390_light.png`, `r5_rollover_1280_light.png`, `r5_rollover_1280_dark.png` | Key; radiogroup; phone Continue with these; desktop Done |
| Rollover reduced motion | `r5_rollover_390_reduced.png` | Same chrome |
| Profile ACTIVE | `r5_profile_active_390_light.png`, `r5_profile_active_1280_light.png`, `r5_profile_active_1280_dark.png` | Identity; Devices n of limit; SUBSCRIPTION ACTIVE + 10 |
| Profile PAUSED | `r5_profile_paused_390_light.png` | PAUSED chip; Resume Playground |
| Guest Profile | `r5_profile_guest_390_light.png`, `r5_profile_guest_1280_light.png` | Guest · Reading only; Sign in; HTML 200 |
| Devices | `r5_devices_390_light.png`, `r5_devices_1280_light.png` | 1 of 2 devices |
| Settings phone | `r5_settings_390_light.png` | Account card; STUDY / APP / ACCOUNT groups |
| Settings desktop | `r5_settings_1280_light.png` | Shipped controls; phone Account group hidden |

---

## Tests

Stage 1 assertions superseded on purpose (record, do not weaken silently):

- T33: `playground.css?v=pg16` (not pg15 / pg14). `mobile.css?v=mob95`.
- Guest GET `/profile` is HTML 200 (D110), not a sign-in 303.

| Run | Result |
|---|---|
| `tests/test_playground_r5.py` | **15 passed** |
| r1 + r5 + settings_phone + r4 asset pin + m5a/m5b + devices_m4a + calendar_routes | **158 passed** |
| `pytest -m "not integration"` on `c35f7d5` | **2840 passed**, 9 skipped, 1 deselected |
| CI on `c35f7d5` | [PR run 36985302956](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36985302956) succeeded. Matching push run 36985297864 was cancelled when this head moved. |

R6 stay-out pin: `TodayUnit` has no `source` / `eyebrow` / `cta_label`; `/calendar` has no `view=week`.

---

## Programme score

| | |
|---|---|
| Before | 70.2 / 100 |
| Newly proven | U3 leftover 9 + U7 12 |
| U3 | 38 / 38 → **12.0** (was 9.2, +2.8) |
| U7 | 12 / 12 → **7.0** |
| After | **80.0 / 100** |

Rows closed this batch:

- U3 leftover: D93, D94, D95, D96, D97, D98, D99, D100, D130
- U7: D107, D108, D109, D110, D111, D112, D113, D114, D137, D138, T26, T27

---

## Remaining / R6 handoff

R5-targeted rows: **DONE**. Do not start R6 from this report.

R6 starts at Today / Calendar / Google (U6, T28–T32, T30). `/calendar?view=week` still does not exist.

Do not reopen R0–R4. Do not change Alembic. Do not reintroduce Constitution gating or historical duration products. Do not add a second roster, billing, or device engine.
