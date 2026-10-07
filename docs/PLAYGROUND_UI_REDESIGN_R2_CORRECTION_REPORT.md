# Playground UI Redesign — R2 correction report

Isolated R2 defect fixes on the closed clause picker. R3 Add-flow is **not** started. Stage 1 remains frozen. Stage 2 remains parked. Programme score is unchanged.

Authoritative docs:

- [PLAYGROUND_UI_REDESIGN_PLAN.md](PLAYGROUND_UI_REDESIGN_PLAN.md)
- [PLAYGROUND_UI_REDESIGN_TRACKER.md](PLAYGROUND_UI_REDESIGN_TRACKER.md)
- [PLAYGROUND_UI_REDESIGN_R2_REPORT.md](PLAYGROUND_UI_REDESIGN_R2_REPORT.md)

```text
Stage 1               = DONE — 100.0 / 100, frozen
UI Redesign Programme = 28.1 / 100
U0                     = 10 / 10
U1                     = 28 / 28
U2                     = 24 / 39  (R2 closed; R3 not started)
R2                     = DONE (correction applied)
R3                     = not started
Stage 2                = PARKED
```

**Branch:** `cursor/playground-220d`  
**PR:** [#188](https://github.com/sanjisworking-commits/recall_the_c/pull/188)

---

## Acceptance

| | |
|---|---|
| Targeted | Fail-closed picker POST (atomic HTTP 400, zero mutation). Bound `UnitLocator` / internal `UnitIdentity`. Required atomic tests. |
| Completed | Both defects and the required atomic proofs. |
| Remaining | None for this correction. R3 Add-flow rows stay NOT STARTED. |
| Programme score before | 28.1 / 100 |
| Programme score after | 28.1 / 100 |
| Visual checks | Not required. No picker layout/copy change. |
| Technical checks | `SelectionRejected` → HTTP 400 `invalid_selection`. Validation before promotion / XOR / Entire Act / `activate_law` / `replace_selection`. `UnitLocator(law_id="")` raises. |
| Focused tests | `tests/test_playground_units.py` + `test_playground_m8.py` + `test_playground_m9.py` + `test_playground_m11.py` + `test_playground.py`: **136 passed** |
| Full regression | `pytest -m "not integration"` on `f62bd63`: **2767 passed, 9 skipped, 1 deselected** |
| CI | Push `36751875399` and PR `36751885785` on `f62bd63`: **success** |

---

## Branch state

| | SHA |
|---|---|
| R2 implementation | [`0f9842b`](https://github.com/sanjisworking-commits/recall_the_c/commit/0f9842b8719b769d811e55492f5e67e9a7caf7ef) |
| R2 closeout pin | [`eb025be`](https://github.com/sanjisworking-commits/recall_the_c/commit/eb025beaebc45098d9d249feae24b81a75485e2b) |
| Correction (code) | [`f62bd63`](https://github.com/sanjisworking-commits/recall_the_c/commit/f62bd63c2013ef4dc8c13d533969bb6b27a1a0bd) |

Nothing from R0/R1 was reopened. Alembic head remains **`20260927_0027`**.

---

## Defect 1 — fail-closed picker POST

Invalid `section=` / `unit=` values previously skipped in `normalize_selection_locators`. The route always called `replace_selection`, so an invalid-only payload stored `[]` and wiped a valid selection. `entire=1` returned `locators_for_act` without inspecting extras. `activate_law` ran before validation.

Now:

- Trim is used only to classify emptiness. `""` / whitespace-only → absent. Any non-empty value must validate as submitted (no rewrite of numbers, labels, case, ordinals, or locator content).
- `SelectionRejected` is the selection-transaction error. `LocatorError` remains locator representation / construction.
- `normalize_selection_locators` / `selection_rows` validate every present value before promotion, XOR, Entire Act expansion, or persistence.
- `entire=1` still validates extras. Invalid extras reject the request. Valid extras are then ignored; the stored result is Entire Act.
- `playground_select_save` maps `SelectionRejected` to HTTP 400 `invalid_selection` and does not leak exception text.
- `activate_law` and `replace_selection` run only after validation succeeds. Rejected POSTs leave selection and overlay item byte-equivalent.

Legitimate empty POST (no `entire`, every `section` / `unit` absent) still 303-clears.

---

## Defect 2 — bound `UnitLocator`

`section_unit_map()` constructed `UnitLocator(law_id="")`. `UnitLocator.__post_init__` did not require an eligible law id.

Now:

```text
UnitIdentity
    section_number, kind, label, ordinal
        ↓ bind law
UnitLocator
    law_id, section_number, kind, label, ordinal
```

`UnitIdentity` has no wire form and no `.value`. `section_unit_map()` operates on identities. `enumerate_selectable_units(..., law_id=)` requires a Playground-eligible law id and binds real `UnitLocator` values through `unit_locator()`. Direct `UnitLocator(law_id="", ...)` raises `LocatorError`.

---

## Required atomic proofs

```text
valid A + invalid B
→ HTTP 400
→ neither A nor B is applied

entire=1 + invalid extra
→ HTTP 400
→ previous selection unchanged

entire=1 + valid extras
→ succeeds
→ normalized result is Entire Act

whitespace-only section/unit values
→ treated as absent

empty valid POST
→ 303
→ intentionally clears selection
```

Also: padded present values (`section=" 8 "`) → 400; omitted NDPS s.65 + malformed unit → 400 with prior units unchanged.

Unlearnable-but-non-omitted: scanned eligible corpus (`not is_omitted` and empty `canonical_body_text`) — **no genuine example**. Service-level synthetic `ActSection` (`99Z`, `status="active"`, empty body) on a replaced NDPS `section_order`. Canonical Bare Act JSON was not modified.

---

## Score

U2 stays **24 / 39**. Weighted U2 stays **11.1**. Programme stays **28.1 / 100**. This correction re-proves T15 (and tightens T8 / D47 evidence). It does not close R3 rows.

Do not start R3.
