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
R3                     = DONE (post-closeout correction frozen)
R4                     = not started
R5                     = not started
Stage 2                = PARKED
```

**Branch:** `cursor/playground-220d`  
**PR:** [#188](https://github.com/sanjisworking-commits/recall_the_c/pull/188)

The 44.2 programme score from the original closeout was **provisional**. It is restored below only after the post-closeout correction: read-only persistence, unexpected Add failures as 500, the R3 visual matrix, local `pytest -m "not integration"`, and CI green.

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
| Award after CI | [`54b5af9`](https://github.com/sanjisworking-commits/recall_the_c/commit/54b5af9d0fa960e320dcdbf98bec9e0d84d12522) |

| SHA | What |
|-----|------|
| `d4525b1` | Confirm→scope add, T18 kinds, read-only home, Playground-scoped errors |
| `596add2` | `can_view_home` leak tests, Entire Act retry, D142 quotes, test clock freeze |
| `0a16c48` | Materialize streaming error bodies without `MutableHeaders.pop` |
| `27d3418` | Stage 1 M6 accepts “Already in Playground” |
| `3a8dcd0` | Guest HTML GET `/playground` and Learn are 200 gates (T20) |
| `02a27b8` | R3 report + tracker while CI pending; score 28.1 |
| `4cbb443` | SHA pin. Push [36815267937](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36815267937) and PR [36815272810](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36815272810) success |
| `54b5af9` | Award R3: U2 39/39, U3 29/38, programme 44.2 |

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

Original closeout captured only six artifacts. **Superseded** by the post-closeout correction matrix (390/768/1024/1280, light/dark, reduced motion, and the product states listed there).

Local owner UI at `http://127.0.0.1:8011` (do not use the stale :8001 JSON 404).

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

---

## Post-closeout correction

Isolated batch. Do **not** start R4 or R5. Stage 1 remains frozen. Stage 2 remains parked.

Review head (do not freeze 44.2 on this SHA):

```text
86d8e567fd3f1c45aeeb7046298eeb7efc339c11
```

The original closeout claimed the three invariants were fully proven, including GET-home-only paused access with no mutation leakage, and awarded 44.2 from a thin visual set (1280 home, scope, picker, 404, 390 Act-head, 390 home). Post-closeout review found two correctness defects and that visual gap.

| | SHA |
|---|---|
| Review / starting head | [`86d8e56`](https://github.com/sanjisworking-commits/recall_the_c/commit/86d8e567fd3f1c45aeeb7046298eeb7efc339c11) |
| Correction 1–2 (read-only peek + Add 500) | [`5c3f003`](https://github.com/sanjisworking-commits/recall_the_c/commit/5c3f003353d7fafacebabcbdd5b1e6c9aecc19a3) |
| Correction 3 visual + D142 theme | [`6194e5b`](https://github.com/sanjisworking-commits/recall_the_c/commit/6194e5b8a5bf91882e89a977ae2a9b6671287315) |

### Correction 1 — paused read-only home performs zero roster mutation

`RosterService.capacity()` still mutates via `ensure_current_period()` (INSERT if missing; UPDATE `updated_at` / tier / limit / status when present). That path is correct for `can_open` writes.

Read-only surfaces now use `peek_capacity()`:

- existing current period → stored limit + consumed count, unchanged
- missing current period → used 0 + snapshot/catalogue limit, **no INSERT**

When `access.can_view_home and not access.can_open`, `require_playground_home()` does not call `_attach_current_period()`. `build_home_view()` uses `peek_capacity()`. `load_membership_index()` / public Act-head CTAs also peek, so a signed-in unsubscribed GET `/laws/{slug}` cannot create a Playground period merely to render Sign in / Subscribe / Add.

Proof:

- `test_paused_home_get_does_not_create_or_update_roster_period` — missing period and existing period; period rows, roster items, consumed count, and `updated_at` unchanged
- `test_halted_and_expired_home_get_do_not_write_roster`
- `test_unsubscribed_public_law_get_does_not_write_roster`
- `test_peek_capacity_does_not_call_ensure`

Add / roster mutation paths still call `capacity()` / `ensure_current_period()` after `require_playground_open`.

### Correction 2 — unexpected Entire Act failures are Playground 500

Removed:

```python
except Exception:
    raise HTTPException(status_code=400, detail="invalid_selection")
```

Entire Act pre-consume now catches only `SelectionRejected`, `LocatorError` → 400 `invalid_selection`, and `PlaygroundLawError` → 404. Unexpected exceptions propagate to the R3 Playground-scoped 500 middleware.

Proof:

- `test_entire_act_unexpected_error_is_playground_500_without_consume` — fault-injected `RuntimeError` during `require_playground_law` → HTTP 500 styled Playground error; slot not consumed; overlay not activated; selection unchanged
- `test_entire_act_selection_rejected_is_400_without_consume` — empty locators → 400 `invalid_selection`; zero consume

### Correction 3 — R3 visual acceptance matrix

Verified the current implementation first. Did not change UI merely to manufacture screenshots.

The matrix found one R3 visual defect: standalone D142 HTML (403/404/500/503/kill-switch) ignored `html[data-theme]` and painted on white instead of `--pg-page`. Fixed in this batch (`cm-theme` boot + `body.playground-app:has(.PlaygroundShell[data-playground-error])`). `playground.css` cache-bust `pg10` → `pg11` (T33 pin follows the asset; R1 is not reopened).

| State | Evidence | Shared primitive |
|---|---|---|
| Guest home / Act / Add | `r3_guest_home_390_light.png`, 390/1280 dark, `r3_guest_act_390_light.png` | Hard-gate hides Primary tabs |
| Subscribe + catalogue Plus/Pro/Max ₹199/399/1199 | `r3_subscribe_catalogue_1280_light.png`, 390/768/1280 dark | Hard-gate; Constitution included card |
| Bare Act eligible Add | `r3_act_head_eligible_390_viewport.png`, 1280 Act-head | T18 `eligible_to_add` |
| Already in Playground | `r3_act_head_already_in_playground_390.png` light/dark | Badge + Sections / Start learning |
| Add confirm Plus | `r3_add_confirm_plus_390_light.png` sheet; 768; `r3_add_confirm_plus_1280_focus.png` dialog | 900px sheet→dialog |
| Add confirm Pro | `r3_add_confirm_pro_1280.png` | Same confirm step as Plus |
| Max direct scope | `r3_max_direct_scope_1280.png`, 390 | Skip confirm; Entire Act / Choose sections |
| Scope Entire Act / Choose sections | `r3_add_scope_entire_or_sections.png` 390/1024/1280 dark | Confirm-only POST does not consume |
| Empty picker after Choose sections | `r3_empty_picker_390_viewport.png`, `r3_empty_picker_1024_viewport.png` | R2 picker at zero selection; desktop SELECTION aside |
| Roster full | `r3_roster_full_act_390.png`, add 390/1280 | T18 `roster_full` |
| Pending | `r3_pending_act_390.png`, `r3_pending_add_390.png` | Isolated pending (not also roster-full) |
| Re-add | `r3_re_add_390.png`, 1280 | “No extra space used.” |
| Device blocked | `r3_device_blocked_390.png` | Hard-gate; same EntitlementGate family |
| Paused read-only home | `r3_paused_home_1280_light.png` 390/768/1280 dark | Normal shell; Resume; **no** `data-hard-gate` |
| Halted / expired | `r3_halted_home_1280_light.png` | Same `can_view_home` shell as paused |
| Empty paid home | `r3_empty_home_1280_light.png` 390/768/1024/1280 dark | “Your September Playground is empty” |
| Populated paid home | `r3_home_ndps_card_1280.png`, `r3_home_phone_390.png` 390/768/1024 dark | Desktop three buttons + aside; phone single CTA |
| Removed / saved progress | `r3_matrix/r3_removed_home_390_light.png` | Progress saved + Add back |
| Law updated | `r3_law_updated_home_1280.png` | Text badge, not colour-only |
| Styled 404/403/500/503 | `r3_playground_html_404_390_light.png` / `_390_dark.png` / `_1280_dark.png`, 403/500/503 counterparts | After theme fix |
| Kill-switch 404 | `r3_playground_kill_switch_404_390_dark.png` | Unavailable copy; status 404 |
| Reduced motion | `r3_add_confirm_plus_390_reduced.png` | `prefers-reduced-motion: reduce` |
| Focus | `r3_add_confirm_plus_1280_focus.png` | `:focus-visible` ring on Add |

Checks recorded by probe + inspection: dark tokens on home/add/errors; no header collision on Playground shells; sheet handle ≤560px vs centred dialog ≥900px; tab suppression only on hard gates; paused home keeps Today/Browse/Playground/Calendar/Profile; 44px `--pg-tap` on `.pg-btn`; status badges include text labels; reduced-motion disables sheet animation.

Full-page Bare Act screenshots overlay the fixed tabbar on mid-list rows; live `body[data-mscreen] .panel` already pads `calc(var(--m-tabbar) + 28px)`. Viewport Act-head shots are the representative evidence.

### Tests and CI

Retained R3 proofs: Entire Act retry idempotence, Choose sections empty-selection, T18 kinds, guest HTML 200 / JSON 401, paused Learn/write block, D140, atomic D142 403/404/500, kill switch, catalogue plans, re-add, R2 fail-closed picker.

| Run | Result |
|---|---|
| `tests/test_playground_r3.py` + `tests/test_playground_r1.py` | **38 passed** |
| `pytest -m "not integration"` | **2793 passed**, 9 skipped, 1 deselected |

CI:

| Commit | Runs | Result |
|---|---|---|
| `5c3f003` | [36874411970](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36874411970) (push), [36874420199](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36874420199) (PR) | success |
| `6194e5b` | [36876407403](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36876407403) (push), [36876417171](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36876417171) (PR) | success |

### Score

All R3-targeted rows remain proven after the correction. No new points.

| | |
|---|---|
| U2 | **39 / 39** |
| U3 | **29 / 38** |
| Programme | **44.2 / 100** |

R4 and R5 were not started. Core R3 architecture (discriminated Act state, guest 200/JSON 401, Entire-Act retry, catalogue plans, scoped error middleware, same-period re-add, strict Learn/write blocking) is unchanged; this batch only closed the read-only persistence leak, the Add 400-masking, and the visual/D142 theme gap.

