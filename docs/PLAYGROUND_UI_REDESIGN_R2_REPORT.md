# Playground UI Redesign — R2 report

Clause backend + section/clause picker. Product delta A becomes technically real. R3 Add-flow is **not** started. Stage 1 remains frozen. Stage 2 remains parked.

This file is the batch closeout. Later batches should add `docs/PLAYGROUND_UI_REDESIGN_R{n}_REPORT.md` the same way.

Authoritative docs:

- [PLAYGROUND_UI_REDESIGN_PLAN.md](PLAYGROUND_UI_REDESIGN_PLAN.md)
- [PLAYGROUND_UI_REDESIGN_TRACKER.md](PLAYGROUND_UI_REDESIGN_TRACKER.md)
- [design/PLAYGROUND_DESIGN_INVENTORY.md](design/PLAYGROUND_DESIGN_INVENTORY.md)
- Prototypes: `docs/design/Recall the C - Playground Desktop.dc.html`, `docs/design/Recall the C - Playground.dc.html`

```text
Stage 1               = DONE — 100.0 / 100, frozen
UI Redesign Programme = 28.1 / 100
U0                     = 10 / 10
U1                     = 28 / 28
U2                     = 24 / 39  (R2 closed; R3 not started)
R2                     = DONE
R3                     = not started
Stage 2                = PARKED
```

**Branch:** `cursor/playground-220d`  
**PR:** [#188](https://github.com/sanjisworking-commits/recall_the_c/pull/188)

---

## Branch state

| | SHA |
|---|---|
| Starting (R1 frozen head) | [`a49d7b8`](https://github.com/sanjisworking-commits/recall_the_c/commit/a49d7b8c9137e9a8c6b6d43b2466a92361562479) |
| Implementation | [`0f9842b`](https://github.com/sanjisworking-commits/recall_the_c/commit/0f9842b8719b769d811e55492f5e67e9a7caf7ef) |
| T16 dormant-status follow-up | [`1cc00b6`](https://github.com/sanjisworking-commits/recall_the_c/commit/1cc00b63ca5aa585f65ed4340e39e07fbb74341f) |
| Tracker closeout | [`d8a1c38`](https://github.com/sanjisworking-commits/recall_the_c/commit/d8a1c3873eef3c8773cc3bfb5a43220ecbd7f22b) |
| Tracker pin / CI-green HEAD at this write | [`eb025be`](https://github.com/sanjisworking-commits/recall_the_c/commit/eb025beaebc45098d9d249feae24b81a75485e2b) |

| SHA | What |
|-----|------|
| `0f9842b` | Implement R2 clause locators, unit authority, and picker |
| `1cc00b6` | Derive picker status from real progress, including dormant locators |
| `d8a1c38` | Record R2 closeout: U2 24/39, programme 28.1 / 100 |
| `eb025be` | Pin R2 closeout SHAs on the redesign tracker |

Nothing from R0/R1 was reopened.

---

## Architecture

### Locator grammar

```text
{law_id}:section:{section_number}
{law_id}:section:{section_number}:{kind}:{label}
{law_id}:section:{section_number}:{kind}:{label}~{ordinal}
```

`kind` is `subsection` or `clause`. `ordinal` defaults to 1. `~n` exists only on the wire; it is omitted when `n` is 1. UI prints the label only — never `~2`.

Examples:

```text
bns:section:103
ndps:section:8:subsection:1
ndps:section:8:clause:a
pss:section:38:subsection:2~2
```

Module: [`src/constitution_memorizer/playground/locators.py`](../src/constitution_memorizer/playground/locators.py)

- `SectionLocator(law_id, section_number)`
- `UnitLocator(law_id, section_number, kind, label, ordinal=1)`
- Section numbers are preserved exactly as the canonical Act exposes them.
- Parser uses bounded `[^:]+`. A greedy `.+` would swallow `:subsection:` / `:clause:`.
- Existing section locators remain valid. Malformed unit locators raise `LocatorError`; they are never coerced to section locators.
- Persistence identity is `(kind, label, ordinal)`.

### Unit authority

[`src/constitution_memorizer/playground/units.py`](../src/constitution_memorizer/playground/units.py) is the single authority for:

- enumerate selectable units
- resolve locator → statutory node/unit
- extract unit canonical text
- derive lead-in and tail
- citation / display metadata
- duplicate-label ordinals
- unit hashing inputs

Routes, services, templates, source review, learning, schedule, and admin diagnostics call this module. They do not walk Bare Act trees themselves.

Canonical Bare Act JSON remains the only statutory source. Playground state does not duplicate or AI-generate statute.

### Smart-code

No law-specific picker template, parser, `UnitLocator` subclass, selection JavaScript, or route handler.

- PSS duplicate printed `(2)` is generic ordinal handling, not a PSS `if`.
- MTP chapterless is generic `chapters == none`, not an MTP `if`.

### Database

Alembic remains **one head: `20260927_0027`**. No R2 migration. Existing TEXT locator columns hold the new grammar.

---

## Selection semantics

Within one section:

```text
whole section
XOR
one or more selectable units
```

Never both as the active selection.

Switching whole-section ↔ units does **not** delete learning / progress / revision / mastery history. The inactive locator becomes dormant. Reactivating it resumes the preserved row. Progress is not copied onto the replacement locator.

Ticking every currently selectable unit stores the **whole-section locator** at the selection layer only. Completing every unit does **not** mark the whole section learned: lead-in and tail may remain unrecalled.

Due / revision schedule / next-up operate only over the **currently active selection** (`progress_in_current_selection_sql` `EXISTS` join). Deselected locators keep history and are not actionable.

`unit_count` is a computed alias of `selected_count`. Copy uses “1 provision” / “N provisions”.

---

## Statutory extraction

A selectable unit is a labelled statutory subsection or clause, including its own descendants. Nested labelled children of a parent unit are descendants, not extra picker rows. Sections with fewer than two selectable units stay section-only.

```text
unit text =
    the unit's own statutory text
    + descendants
    + following non-unit siblings belonging to that unit
    until the next selectable peer begins
```

- **Lead-in:** unlabelled introductory material before the first selectable unit. Context only. Not independently learnable.
- **Tail:** whole-section closing provisos / explanations after the last unit. Learned only with the whole section. Not attached to the final unit.

PSS s.38 sentinel: first printed `(2)` → ordinal 1 (`…:subsection:2`); second `(2)` → ordinal 2 (`…:subsection:2~2`); both display `(2)`.

Unit hash is SHA-256 of:

```text
section number
kind:label
lead-in
unit canonical text
```

Stable across CSS, view-model copy, UI chrome, and Playground state. Changes when statutory unit text changes. Unit source review uses `source_hash_for_locator` inside the existing Stage 1 scan; there is no second review subsystem.

---

## Picker

Server is authoritative. POST accepts `section=` and `unit=`. No-JS submission works. JavaScript only improves tri-state, counts, and zero-selection disable.

D50: JS disables the primary action at zero selection. The HTML control stays enabled so a no-JS user who ticks boxes can still POST. Empty / omitted / unlearnable / malformed values are rejected or ignored server-side.

D23: the picker footer is `.pg-sticky-cta.pg-pick-footer`. R1 `mobile.css` offsets it by `--m-tabbar` + safe-area when the signed-in five-tab bar exists. Local single-user serve does not emit that nav HTML (R1 D20 is multiuser). The picker still uses the R1 sticky slot.

| ID | Status | Test / evidence |
|---|---|---|
| D11 | DONE | mixed dash + `aria-checked="mixed"` |
| D23 | DONE | `.pg-sticky-cta` + R1 tab-bar offset |
| D41 | DONE | `← {{ act.short_name }}`, “Choose what to learn” |
| D42 | DONE | chapter bands; MTP `data-chapterless`, no invented CHAPTER |
| D43 | DONE | checkbox, `SECTION n`, `list_title` |
| D44 | DONE | five real states, including dormant progress (`1cc00b6`) |
| D45 | DONE | `<details>` caret; no expander on section-only rows |
| D46 | DONE | none / some / all |
| D47 | DONE | omitted/unlearnable disabled in UI and on POST |
| D48 | DONE | phone sticky count + “clauses partial”; hidden ≥900px |
| D49 | DONE | desktop SELECTION aside from live selection |
| D50 | DONE | JS disable at zero; server still authoritative |
| D128 | DONE | “Whole sections, or open one and pick clauses.” |
| D129 | DONE | `Add N section(s) →` / `(N clause(s) partial)` / `Select sections to add` |

R3 Add-dialog rows D27–D40 were not implemented.

---

## Technical rows

| ID | Status | Notes |
|---|---|---|
| T5 | DONE | Generic chapterless picker / workspace / touched progress |
| T8 | DONE | Discriminated locators |
| T9 | DONE | `playground/units.py` |
| T10 | DONE | Unit hash + existing source-review classify |
| T11 | DONE | Exclusivity, promotion, dormant progress |
| T12 | DONE | Due/schedule join current selection |
| T13 | DONE | Computed `unit_count`; provisions wording |
| T14 | DONE | `learn_path_for_locator` + parallel `/u/{unit}/learn/{mode}` |
| T15 | DONE | no-JS `section=` / `unit=` POST |
| T16 | DONE | Per-section status view model from real progress |

T17–T21 belong to R3 and later.

---

## Performance

A request concerning one law hydrates at most that law. Picker GET/POST call `require_playground_law(law_id)` only.

`test_requested_law_only_hydration_on_picker` asserts an NDPS picker request does not hydrate bns, bnss, pss, or mtp.

No all-law load was added on `/laws`, `/playground`, dashboard, calendar, or picker.

---

## Visual verification

Verified against the live picker at `http://127.0.0.1:8765/playground/laws/{ndps,mtp}/sections` (mini units + seeded sqlite).

| Viewport / state | Artifact |
|---|---|
| 390 light, header / chapters / footer | `r2_picker_390_light.png` |
| 390 mixed / expanded clauses | `r2_picker_390_mixed.png` |
| 390 zero selection (CTA disabled) | `r2_picker_390_zero_selection.webp` |
| 390 whole-section promotion | `r2_picker_390_whole_section.webp` |
| 390 omitted s.65 | `r2_picker_390_omitted.webp` |
| 390 dark | `r2_picker_390_dark.png` |
| ~768 footer, no aside | `r2_picker_768_light.png` |
| ~1024 SELECTION aside + five status states | `r2_picker_1024_aside.png` |
| 1280 light | `r2_picker_1280_light.png` |
| 1280 dark | `r2_picker_1280_dark.png` |
| 1280 focus ring | `r2_picker_1280_focus.png` |
| 390 reduced motion | `r2_picker_390_reduced_motion.png` |
| MTP 390 chapterless | `r2_picker_mtp_390_chapterless.png` |
| MTP 1280 chapterless + aside | `r2_picker_mtp_1280_chapterless.png` |

Do not claim R3 Add-dialog parity.

---

## Tests

Focused corpus: [`tests/test_playground_units.py`](../tests/test_playground_units.py)

Covered: section/unit roundtrip, ordinal default, duplicate ordinal serialization, malformed rejection, PSS s.38 duplicate `(2)`, lead-in, tail exclusion, descendant inclusion, `<2` units stay section-only, exclusivity, dormant progress, reactivation, all-unit selection normalisation, all-unit learning ≠ whole-section mastery, deselected locator excluded from due, unit hash deterministic / statutory-sensitive / presentation-stable, chapterless MTP picker, omitted POST rejection, no-JS section and unit POST, tri-state VM, provisions singular/plural, requested-law-only hydration, five-state status including dormant.

| Run | Result |
|---|---|
| `tests/test_playground_units.py` | 18 passed |
| units + r1 + m8 + m11 after `1cc00b6` | 85 passed |
| `pytest -m "not integration"` on `1cc00b6` | **2760 passed**, 9 skipped, 1 deselected |

CI:

| Commit | Runs | Result |
|---|---|---|
| `0f9842b` | [36732258639](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36732258639) | success |
| `1cc00b6` | [36734662452](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36734662452), [36734670642](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36734670642) | success |
| `eb025be` | [36747038178](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36747038178), [36747043597](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36747043597) | success |

Stage 1 assertions superseded on purpose (record, do not weaken silently):

- Picker lede is no longer “Chapter selection is not in this batch” (D128).
- Picker back is `← {{ act.short_name }}`, not `← Playground` (D41).
- Due/schedule tests seed current selection because T12 joins it.

---

## Programme score

| | |
|---|---|
| Before | 17.0 / 100 |
| Newly proven | D11, D23, D41–D50, D128–D129, T5, T8–T16 |
| U2 proven | 24 / 39 |
| Weighted U2 | 18 × 24/39 = **11.1** |
| After | **28.1 / 100** |

U2 spans R2 + R3. The remaining 15 U2 rows (Add sheet/dialog) are unawarded.

---

## Remaining / R3 handoff

R2-targeted rows: **none open**.

B/C denominator additions: **none**.

Class-D product-scope blocker: **none**.

R3 starts at:

```text
T17–T21
D27–D29
D31–D40
D51+
```

That is confirm → scope (“Entire Act” / “Choose sections”), Add sheet/dialog variants, and home/gate work that consumes the picker. Do not mix it into R2.

Do not reopen R0/R1. Do not start R3 from this report.
