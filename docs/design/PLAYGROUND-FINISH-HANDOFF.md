# Playground — production finish handoff

This is the **production** closeout for the Playground UI redesign programme
(U0–U8). It is not the design-preview file [`PLAYGROUND-HANDOFF.md`](PLAYGROUND-HANDOFF.md)
and it is not a Stage 1 scoreboard.

Do **not** edit the `.dc.html` prototypes from this file. They stay design
artifacts. Runtime is FastAPI + Jinja + `styles.css` / `mobile.css` /
`playground.css`.

```text
Stage 1               = DONE — 100.0 / 100, frozen
UI Redesign Programme = 99.6 / 100
Stage 2               = PARKED
PR 188                = draft — do not merge from R7
Alembic               = 20260927_0027 (one head)
```

Authority: [`docs/PLAYGROUND_UI_REDESIGN_PLAN.md`](../PLAYGROUND_UI_REDESIGN_PLAN.md),
[`docs/PLAYGROUND_UI_REDESIGN_TRACKER.md`](../PLAYGROUND_UI_REDESIGN_TRACKER.md),
[`docs/PLAYGROUND_UI_REDESIGN_R7_LEDGER.md`](../PLAYGROUND_UI_REDESIGN_R7_LEDGER.md),
[`PLAYGROUND_DESIGN_INVENTORY.md`](PLAYGROUND_DESIGN_INVENTORY.md).

---

## Chrome (locked)

| Band | Width | Shell |
|---|---|---|
| Phone tab bar | `max-width: 560px` | Bottom `PrimaryTabs--bottom` |
| Flex header | 561–899 | Phone-shell verification. **Not** desktop. Week view hidden |
| Desktop | `min-width: 900px` | Top tabs, 3-column where designed |
| Collision pass | 900–1039 | `min-width: 0` on week grid, header, home grid, Act-head CTA |
| Calendar week | `min-width: 900px` only | Exercise at ~1024 and 1280, never at 390 or ~768 |

## Tokens

Shared system (`--ink`, `--page`, `--paper`, `--hairline`, `--muted`,
`--faint`, `--browse-due`, `--pg-*`). Dark values exist (D4 / T34).
Fixed-dark completion screens stay fixed-dark (D92).

Landing (`landing.html` / `landing_light.html`) and standalone login
(`login.html`) keep the **shipped** palettes they already had at freeze.
Those palettes are **not** D1–D17. Restyling them onto Playground tokens
would be a new Layer 1 D row under §21.3. R7 did not add that row and
does not claim V23 done. Other auth-family templates that already use
`base.html` tokens (`signed_out.html`, `session_expired.html`,
`auth_transition.html`, `auth_callback.html`, `partials/auth_shell.html`)
are MATCHED.

## Frozen product rules (do not reopen)

- Guest `GET /playground*` is HTML **200** sign-in gate. JSON stays 401 (T20).
- Paused / halted / expired `GET /playground` is **read-only home**. Learn
  stays gated. `data-hard-gate` is absent on that home (T19).
- Eligible laws: `bns bnss ndps uapa pss mtp`. POTA readable, not eligible.
- Today merge: Constitution dones, Playground dues, Constitution pending,
  at most one New. New is **not** in `due_count` (T28).
- Calendar week is desktop-only. Legend is text + mark, never colour alone.
- Settings **styling** stays shipped (D113). Hit area may be 44px.
- Legal is Class B. Admin is Class D (no restyle; V18 regression only).
- Capacity, Keep/Remove/Undecided, device cap (2), catalogue Plus/Pro/Max
  and GST copy are Stage 1 / R3–R5 facts.

## Classes (§21.3)

| Class | Count | R7 duty |
|---|---|---|
| A | 19 + 2 verify-only | Production Playground / Today / Calendar / account |
| B | 45 | Token / focus / overflow / 44px against D1–D17. Inspect every template even when screenshots are shared |
| C | 4 templates + listed states D102, D133–D142 | No new design. Every listed state in the R7 ledger |
| D | 11 admin | Excluded from restyle |
| E | 0 | `playground_cloze.html` deleted (T7) |

A **new** Class-B mismatch that needs a new Layer 1 D row is a stop: do
not add the row, do not fix it, do not claim V23 done.

## Asset pins (T33)

`styles.css?v=main77` · `mobile.css?v=mob98` · `playground.css?v=pg19` ·
`playground.js?v=pg8`

Bump the CSS pin when that file changes. Leave `pg8` unless JS changes.

## What R7 changed

Overflow, focus rings, reduced motion, 44px min-size, and the 900–1039
collision band. Two test rewrites (T40-4 Today path, T40-5 eligible-act
loop). No schema change. No IA change.

## After this file

Do not continue optimising. Confirm desktop stable, mobile stable, deltas
stable, full regression green. Stage 2 S2-0 stays **PARKED** until a later
instruction retrieves
`RecallC_Stage2_S2-0_Optimization_Baseline_Parked.md`.
