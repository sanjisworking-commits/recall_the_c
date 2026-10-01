# Playground UI Redesign — R3 report

Add flow, Act-head, home, and gates. Product deltas G and H become technically real. R4 Learn/speech and R5 roster/Profile are **not** started. Stage 1 remains frozen except the T20/T17 test supersessions this batch required. Stage 2 remains parked.

This file is the batch closeout. Later batches should add `docs/PLAYGROUND_UI_REDESIGN_R{n}_REPORT.md` the same way.

Authoritative docs:

- [PLAYGROUND_UI_REDESIGN_PLAN.md](PLAYGROUND_UI_REDESIGN_PLAN.md)
- [PLAYGROUND_UI_REDESIGN_TRACKER.md](PLAYGROUND_UI_REDESIGN_TRACKER.md)
- [design/PLAYGROUND_DESIGN_INVENTORY.md](design/PLAYGROUND_DESIGN_INVENTORY.md)
- Prototypes: `docs/design/Recall the C - Playground Desktop.dc.html`, `docs/design/Recall the C - Playground.dc.html`

```text
Stage 1               = DONE — 100.0 / 100, frozen
UI Redesign Programme = 44.2 / 100
U0                     = 10 / 10
U1                     = 28 / 28
U2                     = 39 / 39
U3                     = 29 / 38  (R3 closed; R5 leftover D93–D100, D130)
R2                     = DONE
R3                     = DONE
R4                     = not started
R5                     = not started
Stage 2                = PARKED
```

**Branch:** `cursor/playground-220d`  
**PR:** [#188](https://github.com/sanjisworking-commits/recall_the_c/pull/188)

---

## Acceptance

| | |
|---|---|
| Targeted | Confirm → scope; Act-head kinds; read-only paused home; guest HTML gate; Playground-scoped HTML errors. Three non-optional invariants below. |
| Completed | Implementation, invariant proofs, Stage 1 supersessions required by T20/T17, visual check of add/home/404. |
| Remaining | R4 Learn/speech and R5 roster/Profile. Do not start them from this report. |
| Programme score before | 28.1 / 100 |
| Programme score after | **44.2 / 100** |
| Alembic | one head: `20260927_0027`. No R3 migration. |

Three invariants are **not optional**. Partial D142 scores zero.

---

## Branch state

| | SHA |
|---|---|
| Starting (R2 correction HEAD) | [`e82088b`](https://github.com/sanjisworking-commits/recall_the_c/commit/e82088b) |
| Implementation | [`d4525b1`](https://github.com/sanjisworking-commits/recall_the_c/commit/d4525b13afc87acc94691154edd3ddeb2b578f49) |
| Invariant follow-up | [`596add2`](https://github.com/sanjisworking-commits/recall_the_c/commit/596add2fad9f85bed28265113ac050285514d5ab) |
| Middleware body rebuild | [`0a16c48`](https://github.com/sanjisworking-commits/recall_the_c/commit/0a16c4849dcad6c77fe4ee1b205e071ff69e4f65) |
| M6 Act-head copy | [`27d3418`](https://github.com/sanjisworking-commits/recall_the_c/commit/27d34183916527eca4016a8cb97450d35d32aedf) |
| T20 guest GET supersession | [`3a8dcd0`](https://github.com/sanjisworking-commits/recall_the_c/commit/3a8dcd0f3901fcb741dc1f280c9520929727ed06) |
| Tracker closeout | [`02a27b8`](https://github.com/sanjisworking-commits/recall_the_c/commit/02a27b84c8d22d64684ebb917b11e4d9f69d6e5e) |

| SHA | What |
|-----|------|
| `d4525b1` | Confirm→scope add, T18 kinds, read-only home, Playground-scoped errors |
| `596add2` | `can_view_home` leak tests, Entire Act retry, D142 quotes, test clock freeze |
| `0a16c48` | Materialize streaming error bodies without `MutableHeaders.pop` |
| `27d3418` | Stage 1 M6 accepts “Already in Playground” |
| `3a8dcd0` | Guest HTML GET `/playground` and Learn are 200 gates (T20) |
| `02a27b8` | R3 report + tracker while CI pending; score 28.1 |
| `4cbb443` | SHA pin. Push [36815267937](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36815267937) and PR [36815272810](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36815272810) success |

Nothing from R0/R1/R2 was reopened except the Stage 1 assertions listed under Tests.

---

## Three invariants

### 1. Entire Act persistence recovery

Roster consume happens only after Entire Act locators validate. Overlay write is `persist_entire_act_selection`: idempotent `activate_law` plus `replace_selection` overwrite. Progress / history rows are not deleted.

If overlay write fails after a successful consume:

- the law stays on the current roster
- used capacity does not increase on retry
- retry finishes the intended Entire Act selection
- `_progress_fingerprint` (lifecycle + mode_progress) is unchanged

Already-active `scope=entire` still calls `persist_entire_act_selection` (recovery path without a second consume). Choose sections consumes/activates with an empty selection; empty picker is valid.

Proof: `test_entire_act_persist_recovers_after_overlay_failure_without_second_slot`, `test_persist_entire_act_selection_is_idempotent`, `test_choose_sections_consumes_and_opens_empty_picker`.

### 2. Access precedence — `can_view_home` is GET-home-only

Locked chain is unchanged:

```text
PLAYGROUND_ENABLED
→ authentication
→ commercial
→ device
→ roster/capacity
→ law membership
```

`can_view_home` is a commercial-layer exception for paused / halted / paid-period-ended. It authorizes **GET `/playground` only** via `require_playground_home` (one call site). Learn, Add, Remove, selection, and roster writes stay on `require_playground_open` / `require_playground_new_law`.

Paused home is not a hard gate (`data-hard-gate` absent). Learn HTML is a gate; Learn JSON is `{ok, error}` 403; POST add/select/remove do not mutate.

Guests, free, and device-blocked still hard-gate. Guest HTML GET is 200 sign-in; JSON is 401; POST stays fail-closed.

Proof: `test_can_view_home_does_not_leak_learn_or_mutations`, `test_can_view_home_does_not_apply_to_guest_free_or_device`, `test_t19_halted_and_expired_home_are_read_only`, `test_t20_guest_json_stays_401_on_home_and_learn`.

### 3. D142 is one atomic row

Playground-scoped HTML 404 + 403 + 500 all ship together, or the row is NOT STARTED and scores zero.

- Path-scoped middleware `playground_html_errors` → `playground_error_middleware`
- No `@app.exception_handler` / `add_exception_handler`
- Non-Playground paths keep Starlette/FastAPI defaults
- `{ok, error}` JSON APIs stay JSON (bodies are materialized so streaming responses are readable)
- FastAPI `{detail}` JSON 403/404/500/503 on `/playground*` becomes styled HTML for HTML clients
- Kill-switch (`PLAYGROUND_ENABLED=false`) is styled **404** (`unavailable=True`)
- Repo/roster outage is styled **503** (D140). Middleware does not map 503 → 404

Proof: `test_d142_playground_html_404_403_500_without_global_handlers`, `test_d140_playground_service_error_is_styled_503`, `test_structured_playground_json_is_not_restyled_to_html`.

---

## Add flow (T17, D31–D40)

```text
GET /playground/laws/{id}/add
  guest / subscribe / resume / device / pending / full → kind sheet (no consume)
  Max / local_owner / admin → skip confirm (`playground_law_limit is None`)
  else → confirm

POST confirm without scope → 200 scope step. Roster unused. Overlay unused.

POST confirm + scope=entire
  validate locators → consume → persist_entire_act_selection → law workspace

POST confirm + scope=sections
  consume → activate_law → empty picker (valid)

POST already-active + scope=entire → persist_entire_act_selection (no consume)
```

Confirm-only POST no longer mutates. Same-period re-add is `kind=re_add` (“No extra space used.”) and does not call `require_playground_new_law`.

T18 `kind`: `unavailable | guest | subscribe | resume | device_blocked | pending | roster_full | already_active | re_add | eligible_to_add`.

---

## Home and gates

- Phone: month strip, Manage, Add a law, segmented cards, one Learn/Continue CTA.
- Desktop: summary tiles, capacity aside, three card buttons.
- Copy: H1 “Playground”, “In Playground this month”, “provisions”, “Verbatim, always.” Empty: “Your {month} Playground is empty”.
- Paused/halted/expired: read-only home, Resume banners, cards do not Add/Remove.
- Guest HTML GET `/playground*` → 200 gate with `next` preserved. JSON 401.
- Subscribe gate plans from catalogue: Plus / Pro / Max, ₹199 / ₹399 / ₹1199. No ₹149 / ₹299 / ₹499.
- “Included with your account” Constitution card on the unsubscribed gate.
- Hard-gate shell `data-hard-gate="true"` hides primary tabs (D22). Paused home does not set it.

Product: Guest = Constitution/Bare Acts, Playground → sign in. Signed-in unsubscribed = full Constitution Learn, Playground → subscribe. Plus 10 / Pro 30 / Max unlimited monthly Playground. Constitution gating and historical duration products stay gone.

---

## Design rows this batch

U2 leftover (15): D27–D29, D31–D40, T17–T18.

U3 R3 (29): D22, D51–D63, D101–D106, D125–D127, D131, D140, D142, T19–T21.

R5 leftover (not started): D93–D100, D130.

R4 (not started): U4/U5 Learn, speech, completion.

---

## Visual verification

Local owner UI at `http://127.0.0.1:8011` (do not use the stale :8001 JSON 404).

| Viewport / state | Artifact |
|---|---|
| 1280 home NDPS card | `r3_home_ndps_card_1280.webp` |
| Add scope Entire Act / Choose sections | `r3_add_scope_entire_or_sections.webp` |
| Empty picker after Choose sections | `r3_empty_picker_after_choose_sections.webp` |
| Styled Playground HTML 404 | `r3_playground_html_404.webp` |
| 390 Act-head Already in Playground | `r3_act_head_already_in_playground_390.webp` |
| 390 home | `r3_home_phone_390.webp` |

Do not claim R4 Learn-mode parity or R5 roster/rollover restyle.

---

## Tests

Focused corpus: [`tests/test_playground_r3.py`](../tests/test_playground_r3.py)

Covered: confirm without scope does not consume; Max skips confirm; Choose sections empty picker; Entire Act overlay-fail recovery without a second slot; idempotent Entire Act persist; paused home leak (Learn/Add/Remove/selection/roster); guest/free/device still hard-gate; D142 404+403+500 plus kill-switch 404 without global handlers; D140 503; T18 kinds; guest add `next`; guest JSON 401; catalogue plans; halted/expired read-only home; D22/D29/D40 assets; home copy; re-add; `{ok, error}` JSON kept.

Test HTTP clock: autouse `tests/conftest.py` freezes `period._as_utc` and entitlement `_utc` to 16 September 2026 12:00 UTC when `now=None`, matching Stage 1 `NOW`. Production still uses live Asia/Kolkata.

Stage 1 assertions superseded on purpose (record, do not weaken silently):

- Guest HTML GET `/playground` and Learn are **200** sign-in gates, not 303 `/login` (`test_playground.py`, `test_entitlement_m3b.py`, `test_playground_m6.py`, `test_playground_m7.py`, `test_playground_m10.py`).
- JSON guest remains 401.
- Local owner / skip-confirm POST without `scope` is **200 scope**, not 303 roster (`test_roster_m5a.py`). Helpers send `scope=sections`.
- M6 Act-head copy accepts “Already in Playground” (`test_playground_m6.py`).
- M11 access-chain string names `can_view_home` as GET-home-only (`test_playground_m11.py`).

| Run | Result |
|---|---|
| `tests/test_playground_r3.py` + leftover T20 | **21 passed** |
| R3 + r1/m6/m7/m10/m11/m3b/m5a/`test_playground.py`/units | **277 passed** |
| `pytest -m "not integration"` | **2786 passed**, 9 skipped, 1 deselected |

CI:

| Commit | Runs | Result |
|---|---|---|
| `3a8dcd0` | [36814133666](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36814133666) (push), [36814136870](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36814136870) (PR) | success |
| `4cbb443` | [36815267937](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36815267937) (push), [36815272810](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36815272810) (PR) | success |

`27d3418` Unit tests failed on leftover T20 guest-303 assertions; `3a8dcd0` superseded those tests and is green.

---

## Programme score

| | |
|---|---|
| Before | 28.1 / 100 |
| Newly proven | U2 leftover 15 + U3 R3 29 |
| U2 | 39 / 39 → **18.0** |
| U3 | 29 / 38 → 12 × 29/38 = **9.2** |
| After | **44.2 / 100** |

R5 leftover U3 rows (D93–D100, D130) stay unawarded.

---

## Remaining / R4 handoff

R3-targeted rows: **DONE**. Do not start R4 or R5 from this report.

R4 starts at Act progress, six-mode Learn chrome, Playground speech, completion screens (U4/U5).

R5 starts at roster/rollover restyle (D93–D100, D130) and Profile/Settings (U7).

Do not reopen R0/R1/R2. Do not change Alembic. Do not reintroduce Constitution gating or historical duration products.
