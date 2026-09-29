# Recall the C — Playground UI Redesign + Product Delta Programme

## Context

Two Claude Design prototypes (updated 2026-09-28, synced against the branch)
are to be brought onto `cursor/playground-220d`:

- Desktop: `Recall the C - Playground Desktop.dc.html` (1280px, 2,902 lines)
- Mobile: `Recall the C - Playground.dc.html` (390x844, 1,829 lines)

Source: `~/Downloads/Playground-Mobile.zip` / `Playground-Desktop.zip`
(identical full-project exports).

**Goal.** Fully replace the current Playground UI with the new prototypes,
and build every backend or technical dependency those designs need to
function exactly as intended. Visually approximating the prototypes is not
the goal.

**The plan has two separated layers:**

1. **Layer 1 — Design replacement scope (§9).** Every screen, state,
   component, responsive behaviour, desktop/phone difference, interaction,
   copy change, navigation rule and empty/error/gate state.
2. **Layer 2 — Technical / behavioural changes required by the new design
   (§10).** Every non-visual change the designs depend on: routes, view
   models, server logic, JavaScript, queries, safeguards and tests. This is
   a **mandatory checklist before implementation begins**.

This is **not only a redesign**. Eight approved items change product or
backend behaviour. It is therefore run as a separate programme between the
two stages, and Stage 1 history is not rewritten:

```
Stage 1  DONE 100.0/100  (not rescored; tracker untouched)
   ↓
Playground UI Redesign + Product Delta Programme  (R0–R7, this plan)
   ↓
Desktop + Mobile UI freeze, full regression green
   ↓
Stage 2 S2-0 baseline  (parked until then)
```

## 1. Sources of truth

| Concern | Authority |
|---|---|
| Desktop look and behaviour | Desktop prototype |
| Phone look | Mobile prototype |
| Phone behaviour | Production branch (never the mobile prototype's old commercial semantics) |
| Implementation base | Latest `origin/cursor/playground-220d` (remote head `e03253e` on 2026-09-29; record the actual pre-merge SHA in the tracker), with `main` @ `0c0a8d5` merged first |
| Tiers, prices, limits | Subscription catalogue |

## 2. Approved product deltas (post–Stage 1)

| Id | Delta | Supersedes |
|---|---|---|
| A | Clause-level selection: a section **or** a selectable subsection/clause | Stage 1 "sections only" (23 Sep decision) |
| B | Playground pending revision rung projected into Google Calendar | Constitution-only sync |
| C | Selected, not-yet-learned Playground work appears in Today | Due revisions only |
| D | Desktop Calendar gains Month \| Week; phone stays month | Month only |
| E | Real speech in Letters and Recite, on the existing speech stack | Stub buttons |
| F | Eligible Acts: NDPS, BNS, BNSS, UAPA, PSS, MTP. POTA readable, not addable. `law_id` = Bare Act slug | Generic eligibility |
| G | Expired/paused: read-only home + paused banner; learning routes blocked | Hard gate page |
| H | Guest HTML `GET /playground*` renders the sign-in gate; JSON stays 401 | 303 to login |

## 3. Locked contracts (unchanged)

Guest = public exploration. Signed-in account = full Constitution.
Subscription = Playground. Plus ₹199 / 10 laws, Pro ₹399 / 30, Max ₹1,199 /
unlimited. Device cap 2; replacement policy 3 per rolling 30 days. Modes:
Read, Cloze, Letters, Type, Recite, Test. Ladder 1 → 3 → 7 → 15 → 30 → 60
(Day 15 intentional). Amendment review stays separate from learning history.
`law_id` stays the monthly commercial identity. Removing a law does not
refund its slot. Rollover is Keep / Remove / Undecided.

## 4. Working contracts (adopted)

- **Promotion.** Ticking every selectable unit of a section stores the
  whole-section locator.
- **Clause ≠ section.** Learning every clause does not mark the section
  learned; lead-in and tail were never recalled. Whole-section learning has
  its own lifecycle.
- **Exclusivity.** Per section, the active selection is the section **or**
  one or more units, never both. Switching granularity deletes nothing;
  progress under the inactive granularity is dormant.
- **Deselection.** Due/schedule queries join the current selection, so a
  deselected provision is no longer actionable. History persists.
- **Google Calendar.** Pending rung only, never the full ladder. A
  paused/lapsed Playground projects nothing; it returns on resume.
- **Today "New".** At most one per day, from the most recently active law:
  first selected, unlearned, not source-change blocked, in Act order. Never
  counted in `due_count`.
- **Icon.** Keep the project-owned inline icon until the geodesic-dome
  licence is confirmed.
- **No streak.**
- **Settings.** Shipped styling stays (raised white segment, outline
  badges). Only phone layout deltas and a phone Reminders row are added.

## 5. No migration currently expected

Alembic head is expected to stay `20260927_0027` across R0–R7. Clause
granularity uses the existing `source_locator TEXT` columns, which the
repositories already treat as opaque text. `unit_count` is a **computed SQL
alias / read-model field** in the summary query, never a table column.

This is an expectation, not a constraint to be defended. Clause selection
touches enough aggregate SQL that a real schema need may surface. If it
does: stop, document the conflict, and get a decision before changing
schema. Do not contort a read model to preserve the headline.

Any new Today / Calendar / sync read of Playground tables tolerates their
absence with a **narrow** missing-schema guard (pattern:
`service.active_revision_session`). Unrelated SQL errors are not swallowed.
Constitution Today, Calendar and Google sync must never fail because
Playground schema is unavailable.

## 6. Clause model (R2 specification)

**Locator**

```
{law}:section:{number}
{law}:section:{number}:{kind}:{label}
{law}:section:{number}:{kind}:{label}~2      duplicate printed label
```

- `kind` ∈ `subsection`, `clause`. `label` = printed label without
  parentheses, case preserved.
- Section number parsing is bounded: `(?P<number>[^:]+)` replaces the greedy
  `.+` in `_LOCATOR_RE` (`playground/locators.py`). Confirmed defect: today
  `ndps:section:8:clause:a` parses as section number `8:clause:a`.
- **Not a regex change alone.** `parse_locator()` returns a discriminated
  type, never an overloaded `SectionLocator.number`:

  ```
  SectionLocator(law_id, section_number)
  UnitLocator(law_id, section_number, kind, label, ordinal)
  ```

- `ordinal` is an explicit parsed field, default 1. `~n` is its wire form
  only: `pss:section:38:subsection:2~2` → `label="2"`, `ordinal=2`. The
  string `"2~2"` is never a label. Serialisation omits `~1`.
- Display identity is `label` (shown as printed, "(2)"); persistence
  identity is `(kind, label, ordinal)`. Known case: PSS s.38 prints two
  "(2)".
- Every caller that reads `.number` from a parsed locator is audited and
  switched to match on the type.
- Label paths, not node ids: only MTP nodes carry ids, and those are
  positional parser artefacts.

**One authority: `playground/units.py`** — enumerate selectable units, build
and resolve locators, extract unit text, lead-in and section tail, produce
the citation label. No clause-tree interpretation in routes or templates.

**Selectable unit** = a labelled subsection or clause, descending only
through an unlabelled lead-in paragraph. A section with fewer than two units
stays section-only.

**Unit text** = own text + descendants + following non-unit siblings up to
the next unit. Lead-in = context only. Closing provisos/explanations that
qualify the whole section = section-level tail, learned only with the whole
section.

**Unit hash** = SHA-256 over section number, `kind:label`, lead-in, unit
canonical text. No UI copy.

## 7. Key technical findings carried into the batches

1. Guests are redirected today (`access.py:_deny_open` 334-352); tests
   `test_playground_m6.py:115,422` assert the 303.
2. UAPA has two ids (`uapa-1967`, `uapa`); eligibility accepts either, and
   `laws.html` looks up states by `law.id` while they are keyed by slug.
3. `playground.css` has no phone rules and no teal; `mobile.css` has no
   `body[data-mscreen="playground"]` rules.
4. Merge conflicts (5): `web/app.py`, `templates/bare_act.html`,
   `templates/base.html`, `tests/test_learn_request_breakdown.py`,
   `tests/test_settings_phone.py`. No migration-number collision.
5. Speech endpoint is Constitution-unit scoped
   (`speech/routes.py:69`). Client global is `window.RecallSpeech`; branch
   JS checks `window.SpeechClient`, which never exists.
6. Legacy `[data-playground-cloze]` JS posts without CSRF and serves only
   the orphaned `playground_cloze.html`.

---

## 8. Batches

Eight substantive batches, each one PR into `cursor/playground-220d`. Small
corrections are absorbed into the next related batch. No Railway deploys.

**Before R0 starts:** every Layer 2 row (§10) is reviewed and accepted.
**Before R1 starts:** both inventories in §16 exist.

**Every batch closes on:** a closeout report (§19); its Layer 1 rows and
Layer 2 rows both closed;
focused tests + affected milestone regressions + full non-integration
suite. Never on visual inspection alone.

### R0 — Synchronise and protect canonical source
- Fetch, then fast-forward worktree
  `.claude/worktrees/jovial-darwin-e1fd02` to the latest
  `origin/cursor/playground-220d`. Record the resulting pre-merge SHA in the
  tracker.
- **Review the delta `c76ba92..<pre-merge SHA>` first.** The audit behind
  this plan was taken at `c76ba92`; the remote has since moved to
  `e03253e`. File:line references, the conflict list and the test
  inventory in this plan are re-validated against the new head before any
  other R0 work, and the plan is corrected where they differ.
- Then merge `main` @ `0c0a8d5`.
- Conflict resolutions:
  - `base.html`: keep Playground nav and assets; adopt main's asset
    versions; bump only assets this programme modifies.
  - `bare_act.html`: take main's structure; re-insert the Playground CTA in
    `.bareact-head` after the status note, before the info toggle.
  - `web/app.py`: union imports/context. `/seen` and `/quiz`: use main's
    preload pipeline, then verify Stage 1 intent against
    `docs/PLAYGROUND_M11_REPORT.md`.
  - Tests: resolved from resulting production behaviour, not convenience.
- Eligibility (`playground/eligibility.py`): current Bare Acts only; roster
  identity = `BareActSpec.slug`; the catalogue alias can never create a
  second law. Fix `laws.html` keying.
- Verify eligible `ndps bns bnss uapa pss mtp`; ineligible `pota`,
  `uapa-1967`. POTA stays publicly readable.
- **Hash-drift guard — STOP CONDITION.** Snapshot section hashes for
  NDPS s.8, BNS s.103, BNSS s.479 before and after the merge. If any hash
  changes without an intentional canonical statutory change: **stop. Do not
  proceed to R1.** Resolve canonical hashing first. This is data-integrity
  critical: drift marks every learner's Acts as "Law updated". It is a
  blocker, not a failing test to investigate later.
- **Footnote-title guard:** title annotation changes must not alter the
  canonical section hash.
- Regenerate `law_sitemap_manifest.json`.
- Cleanup, verified-dead only: `playground_cloze.html`; legacy CSRF-less
  cloze block in `playground.js`; `complete_cloze` only if unused. No broad
  legacy cleanup.
- Create `docs/PLAYGROUND_UI_REDESIGN_TRACKER.md` (see §12).

### R1 — Shared design system and shells  *(shell only)*
- **Guard:** R1 may restyle existing states, but no template may depend on
  a clause-level view-model field, and no placeholder clause UI is added to
  wait for R2. R1 ships only: tokens, cards, nav, buttons, sheets/dialogs,
  the responsive shell, and the existing home rendering in the new skin.
  If an R1 change needs data the branch does not already provide, it
  belongs to a later batch.
- Tokens in `static/playground.css`, light and dark: ink, teal, teal tint /
  border / dark, amber + tint, neutral paper/grey scale, radii, shadows. No
  uncontrolled raw hex in rules.
- Shared components: buttons, cards, chips, dialogs, bottom sheets, motion,
  focus ring, safe areas. Reduced motion collapses all animation.
- Desktop shell per desktop prototype: navigation, page width, density,
  multi-column layout, dialogs.
- Phone shell: 5-tab bottom nav, rounded cards, teal states, bottom sheets,
  single column, sticky CTA. Rules in `static/mobile.css` inside
  `@media (max-width:560px)` under `body[data-mscreen="playground"]`;
  extend the `min-width:561px` hide-list. Constitution pages are not
  restyled in R1; they are class B (§21) and verified under the new shell.
- Keep every semantic class the tests pin (`PlaygroundShell`,
  `RosterCapacity`, `LawCard`, `EntitlementGate`, …).

### R2 — Clause-level backend and picker  *(stands alone)*
- Backend per §6: `locators.py`, new `units.py`, `source.py`, `service.py`,
  `learning/service.py`, `source_review.py`, `schedule.py`, `urls.py`
  (`learn_path_for_locator`), `routes.py` (parallel
  `/sections/{n}/u/{unit}/learn/{mode}` + start/complete/quiz), `view.py`,
  `repository.py` + `postgres.py` (computed `unit_count`; selection join),
  `admin/playground_diagnostics.py`. Remove legacy `split(":section:")`
  fallbacks.
- Picker (`playground_select.html`, new `static/playground-select.js`):
  chapter bands (none for chapterless MTP), status line per section,
  expandable rows, tri-state checkbox, clause rows, sticky count footer on
  phone, persistent selection aside on desktop.
- Works without JavaScript: POST `section=` / `unit=`; server normalises.
- Counts say "provisions" when clause selection makes "sections"
  inaccurate. Footer: "Add 1 section (1 clause partial) →" with correct
  plurals.
- New `tests/test_playground_units.py`, including: `parse_locator` returns
  the right type; `~n` round-trips through `ordinal`; `"2~2"` is never a
  label; section numbers never contain `:`.

### R3 — Add flow, Act header, home, gates
- Add flow: confirm → scope step "Entire Act" / "Choose sections".
  Bottom sheet on phone, dialog on desktop. Catalogue tier data only.
- Act header CTA per state: guest, signed-in free, expired/paused, eligible
  subscriber, already active, roster full, pending. "Already in Playground"
  banner with Sections and Continue.
- Home: phone month strip, Manage, Add a law, segmented-progress cards, one
  clear Learn/Continue CTA. Desktop summary tiles, active laws,
  removed/saved, capacity aside.
- Delta G: read-only paused home; mutations blocked.
- Delta H: guest gate page with `next` preserved; JSON 401.
- Gate restyle for every block reason; plans stage from the catalogue.

### R4 — Act progress, Learn, speech, completion
- Act progress: ring, waffle, rung histogram, computed scope eyebrow,
  Next up. Real persisted state; no demo values.
- Learn chrome: step bar, "Step n of 6", advance labels, methods-left copy,
  "Mark it Done", VERBATIM BARE ACT chip. All six modes kept.
- Clause learning: lead-in as context, unit as recall text, citation label.
- Desktop keeps the side/deck layout; phone is a focused single column.
- Speech: new Playground transcription route reusing the existing stack
  (Deepgram Nova-3, 2 MB cap, MIME allowlist, rate limit, alignment, typed
  fallback). Expected text resolved server-side from the locator. Gated by
  the Playground access chain, CSRF as other mutations. Client uses
  `window.RecallSpeech`.
- Completion: server-rendered "Section learned." and "Mastered" screens.
  Dates from lifecycle state. Whole-Act mastery only when the real
  aggregate supports it.

### R5 — Roster, rollover, Profile, Settings
- Roster and rollover: restyle only. Capacity semantics, slot consumption
  and Keep / Remove / Undecided preserved. Phone sticky action clears the
  tab bar.
- Profile: SUBSCRIPTION card (ACTIVE / PAUSED / ON HOLD), Devices
  "n of limit" from the device service, Learning preferences row. Legacy
  lifecycle card kept.
- Settings: shipped controls unchanged. Phone-only Reminders row when
  connected, posting `reminder_cadence` to the existing preferences
  endpoint.

### R6 — Today, Calendar, Google Calendar  *(one scheduling read model)*
- Today: `TodayUnit` gains `source`, `eyebrow`, `cta_label`. Due revisions
  first, then at most one New. Eyebrows "Day 1 → 3 · Playground",
  "New · Playground". `due_count` unchanged.
- In-app calendar: clause citations ("§8(a)") via the shared helper.
- Week view, desktop only: `/calendar?view=week&date=YYYY-MM-DD`, seven
  columns, every state carries text, never colour alone.
- Google: extend the existing projection (`build_projection(..., extra=)`),
  shared daily line cap. Re-sync after Learned, revision advance, selection
  replace, roster remove, roster re-add. A Playground read failure never
  fails Constitution sync.

### R7 — Responsive reconciliation and design closeout
- Full pass over Layer 1 and Layer 2 at every viewport/theme in §13, including a
  ~1024px check for shell collisions.
- Accessibility pass: focus ring, 44px targets, dialog roles, text + mark
  status, reduced motion.
- Commit both prototypes and `PLAYGROUND-FINISH-HANDOFF.md` to
  `docs/design/`; update the design README.
- Close the redesign tracker. Stage 1 tracker is not edited.

**After R7:** do not continue optimising. Confirm desktop stable, mobile
stable, all deltas stable, full regression green. Then retrieve
`RecallC_Stage2_S2-0_Optimization_Baseline_Parked.md` (location to be
confirmed; it is not in the repo as far as I have seen) and begin Stage 2
S2-0 against the final UI.

---

## 9. Layer 1 — Design replacement scope

The "nothing missed" inventory. Kind: **N** new · **R** restyle of something
that exists · **C** copy change · **=** exists, verify only. "Needs" points
at the Layer 2 row(s) the item cannot work without. In the tracker every row
also carries: Automated test · 390 light · 390 dark · 1280 light ·
1280 dark · Reduced motion. A row closes only against real production
state, never against the prototype's demo data.

### 9.1 Design system (cross-cutting)
| # | Item | Phone | Desktop | Batch | Kind | Needs |
|---|---|---|---|---|---|---|
| D1 | Colour tokens: ink, paper, page, hairlines, muted/faint text | ✓ | ✓ | R1 | N | T34 |
| D2 | Teal family (accent, dark, tint, border, done, on-dark) | ✓ | ✓ | R1 | N | T34 |
| D3 | Amber/overdue and destructive families | ✓ | ✓ | R1 | N | T34 |
| D4 | Dark-theme value for every new token | ✓ | ✓ | R1 | N | T34 |
| D5 | Type: Fraunces display over Source Sans 3; caps label 10.5/600 | ✓ | ✓ | R1 | R | — |
| D6 | Radii scale (22 sheet, 16 card, 14 row, 12 button, 999 chip) | ✓ | ✓ | R1 | N | — |
| D7 | Shadows (button press, sheet, dialog, menu) | ✓ | ✓ | R1 | N | — |
| D8 | Buttons: primary, outline, teal, disabled, destructive link; press state | ✓ | ✓ | R1 | R | — |
| D9 | Cards, emphasised card (1.5px ink), dashed "saved" card | ✓ | ✓ | R1 | R | — |
| D10 | Chips and badges: status, due, teal, plan chip, VERBATIM chip | ✓ | ✓ | R1 | R | — |
| D11 | Checkbox: none / all / some | ✓ | ✓ | R2 | N | T15 |
| D12 | Bottom sheet (grabber, scrim, rise) | ✓ | — | R1 | N | T38 |
| D13 | Centred dialog (460px, backdrop, close) | — | ✓ | R1 | R | T38 |
| D14 | Form fields and 2px focus ring | ✓ | ✓ | R1 | R | — |
| D15 | Progress visuals: ring, segmented bar, step bar, waffle cell, rung bar, capacity blocks | ✓ | ✓ | R1 | N | — |
| D16 | Motion: rise, pop, sheet, grow, fade; all collapse under reduced motion | ✓ | ✓ | R1 | N | — |
| D17 | Tap targets ≥44px; safe-area insets | ✓ | — | R1 | N | T39 |

### 9.2 Navigation and shell
| # | Item | Phone | Desktop | Batch | Kind | Needs |
|---|---|---|---|---|---|---|
| D18 | Header: logo tile, centred tabs with icons, active rules | — | ✓ | R1 | R | — |
| D19 | Account button and menu (Profile, Settings, Calendar, Sign out) | — | ✓ | R1 | R | — |
| D20 | 5-tab bottom bar, active rules per screen | ✓ | — | R1 | R | — |
| D21 | Tab bar hidden on focused screens (Learn, completion, Settings) | ✓ | — | R1 | N | T39 |
| D22 | Primary tabs hidden on hard-gate pages | ✓ | ✓ | R3 | N | T18 |
| D23 | Sticky footers sit above the tab bar | ✓ | — | R2, R5 | N | T39 |
| D24 | Back links ("← Playground", "← Laws", "← Today") | ✓ | ✓ | R1 | R | — |
| D25 | Page widths and columns at 390, 561–899, 900–1039, 1040+, 1280 | ✓ | ✓ | R1, R7 | N | — |

### 9.3 Bare Act head
| # | Item | Phone | Desktop | Batch | Kind | Needs |
|---|---|---|---|---|---|---|
| D26 | CTA placed in main's new head (status, About card, tabs) | ✓ | ✓ | R0 | R | T1 |
| D27 | CTA labels: guest, free, expired/paused, add, full, pending | ✓ | ✓ | R3 | C | T18 |
| D28 | "Already in Playground" banner with Sections and Continue | ✓ | ✓ | R3 | N | T18 |
| D29 | Desktop head: title left, 380px CTA column right | — | ✓ | R3 | N | — |
| D30 | No CTA on repealed Acts; CTA on MTP's chapterless page | ✓ | ✓ | R0 | N | T4, T5 |

### 9.4 Add flow
| # | Item | Phone | Desktop | Batch | Kind | Needs |
|---|---|---|---|---|---|---|
| D31 | Container: bottom sheet / centred dialog | sheet | dialog | R3 | R | T38 |
| D32 | Confirm step: space use, remaining, correct singular/plural | ✓ | ✓ | R3 | C | T17 |
| D33 | Max tier skips confirm | ✓ | ✓ | R3 | = | T17 |
| D34 | Scope step: Entire Act / Choose sections + footnote | ✓ | ✓ | R3 | N | T17 |
| D35 | Guest variant | ✓ | ✓ | R3 | R | T20 |
| D36 | Subscribe / resume variant with catalogue "from ₹" line | ✓ | ✓ | R3 | R | T21 |
| D37 | Roster-full variant with upgrade buttons per tier | ✓ | ✓ | R3 | R | T18 |
| D38 | Pending-payment variant | ✓ | ✓ | R3 | R | T18 |
| D39 | Re-add variant ("No extra space used") | ✓ | ✓ | R3 | R | — |
| D40 | Focus trap, Escape, scrim close, no-JS fallback page | ✓ | ✓ | R3 | = | T38 |

### 9.5 Section picker
| # | Item | Phone | Desktop | Batch | Kind | Needs |
|---|---|---|---|---|---|---|
| D41 | Header: back label, "Choose what to learn", helper line | ✓ | ✓ | R2 | C | — |
| D42 | Chapter bands; none for chapterless Acts | ✓ | ✓ | R2 | N | T5 |
| D43 | Section row: checkbox, SECTION n eyebrow, title | ✓ | ✓ | R2 | R | — |
| D44 | Status line, five states with colours and text | ✓ | ✓ | R2 | N | T16 |
| D45 | Caret expands clause rows (indented, 18px checkbox, preview) | ✓ | ✓ | R2 | N | T9, T15 |
| D46 | Tri-state section checkbox | ✓ | ✓ | R2 | N | T11, T15 |
| D47 | Omitted / unlearnable rows disabled | ✓ | ✓ | R2 | = | — |
| D48 | Sticky footer button with count and "clauses partial" | ✓ | — | R2 | N | T13 |
| D49 | Sticky SELECTION aside with count, list and note | — | ✓ | R2 | N | T13 |
| D50 | Disabled state at zero selection | ✓ | ✓ | R2 | N | — |

### 9.6 Playground home
| # | Item | Phone | Desktop | Batch | Kind | Needs |
|---|---|---|---|---|---|---|
| D51 | Header: "Playground" + law count / "MY PLAYGROUND" + month | ✓ | ✓ | R3 | C | — |
| D52 | Month strip with Manage and Add a law; "Manage next month ›" | ✓ | — | R3 | N | — |
| D53 | Law card: title, segmented bar, single Learn/Continue CTA | ✓ | — | R3 | R | T22 |
| D54 | Law card: Up next, status chip, due chip, three buttons | — | ✓ | R3 | R | — |
| D55 | "Law updated" chip and "Review affected provisions" | ✓ | ✓ | R3 | R | — |
| D56 | Summary tiles: Due today, Overdue, Sections learned | — | ✓ | R3 | R | T22 |
| D57 | Removed this month (Add back) and Saved progress sections | ✓ | ✓ | R3 | R | — |
| D58 | Capacity aside: count, block meter, legend, full note | — | ✓ | R3 | R | — |
| D59 | Plan next month card | ✓ | ✓ | R3 | R | — |
| D60 | Empty state | ✓ | ✓ | R3 | C | — |
| D61 | Paused banner; card CTAs become Resume | ✓ | ✓ | R3 | N | T19 |
| D62 | Banners: pending, cancel-at-end, upgrade, downgrade, welcome back | ✓ | ✓ | R3 | R | — |
| D63 | Verbatim trust mark | ✓ | ✓ | R3 | R | — |

### 9.7 Act progress
| # | Item | Phone | Desktop | Batch | Kind | Needs |
|---|---|---|---|---|---|---|
| D64 | Head: back, scope eyebrow, title, membership chip | ✓ | ✓ | R4 | R | T22 |
| D65 | Progress ring with fraction and headline | 84px | 104px | R4 | N | T22 |
| D66 | "Next" chip | ✓ | ✓ | R4 | N | T22 |
| D67 | Waffle of selected provisions | ✓ | ✓ | R4 | N | T22 |
| D68 | "On the ladder" histogram, six rungs, staggered grow | ✓ | ✓ | R4 | N | T22 |
| D69 | Primary Learn CTA naming what is next; Manage sections | ✓ | ✓ | R4 | R | — |
| D70 | Up next learning prompt card | — | ✓ | R4 | R | — |
| D71 | Verbatim box with show/hide | — | ✓ | R4 | R | — |
| D72 | Sections list with status, due, Start/Continue | — | ✓ | R4 | R | — |
| D73 | Source-update panel (three variants) | ✓ | ✓ | R4 | R | — |
| D74 | Empty: no sections selected | ✓ | ✓ | R4 | R | — |

### 9.8 Learn
| # | Item | Phone | Desktop | Batch | Kind | Needs |
|---|---|---|---|---|---|---|
| D75 | Top bar: exit, six-segment step bar, "Step n of 6", help | ✓ | ✓ | R4 | R | T23 |
| D76 | Eyebrow with mode and citation; VERBATIM BARE ACT chip | ✓ | ✓ | R4 | R | T14 |
| D77 | Per-mode task heading (six) | ✓ | ✓ | R4 | C | — |
| D78 | Advance labels per mode; "n methods left"; "Mark it Done" | ✓ | ✓ | R4 | C | T23 |
| D79 | Read presentation | ✓ | ✓ | R4 | R | — |
| D80 | Cloze: density control, blanks, reveal all, status, feedback sheet | ✓ | ✓ | R4 | R | — |
| D81 | Letters: Speak it / Just read, initials, full-text toggle, listening state | ✓ | ✓ | R4 | R | T25 |
| D82 | Type: overlay, live underline, stats, result card | ✓ | ✓ | R4 | R | — |
| D83 | Recite: blurred text, hold to peek, bars, accuracy map, transcript | ✓ | ✓ | R4 | R | T25 |
| D84 | Test: MCQ + fill-in, verdicts, score | ✓ | ✓ | R4 | R | — |
| D85 | Clause unit: lead-in shown as context above the recall text | ✓ | ✓ | R4 | N | T9, T14 |
| D86 | Revision variant ("Revision · Day N") and source-outdated line | ✓ | ✓ | R4 | R | — |
| D87 | Layout: focused single column / deck + panel two-column | ✓ | ✓ | R4 | R | — |

### 9.9 Completion
| # | Item | Phone | Desktop | Batch | Kind | Needs |
|---|---|---|---|---|---|---|
| D88 | "Section learned." dark screen, ladder chips, first-revision line | ✓ | ✓ | R4 | N | T24 |
| D89 | Learned count line ("n of m … learned") | ✓ | ✓ | R4 | N | T24 |
| D90 | "Mastered, verbatim." section screen with real stats | ✓ | ✓ | R4 | N | T24 |
| D91 | "The whole Act. By heart." screen | ✓ | ✓ | R4 | N | T24 |
| D92 | Fixed dark surface in both themes | ✓ | ✓ | R4 | N | T34 |

### 9.10 Roster and rollover
| # | Item | Phone | Desktop | Batch | Kind | Needs |
|---|---|---|---|---|---|---|
| D93 | Roster manager: head, used/remaining, rules card, notice | ✓ | ✓ | R5 | R | — |
| D94 | Active rows (Continue, Read, Remove); removed rows (Add back) | ✓ | ✓ | R5 | R | — |
| D95 | Remove dialog/sheet | ✓ | ✓ | R5 | R | T38 |
| D96 | Add-law dialog with block meter and saved-progress line | ✓ | ✓ | R5 | R | — |
| D97 | Rollover: title, lede, key (Keep / Remove / Undecided) | ✓ | ✓ | R5 | R | — |
| D98 | Rollover rows: three visual states, radiogroup, blocked line | ✓ | ✓ | R5 | R | — |
| D99 | Rollover aside / sticky footer with planned count | footer | aside | R5 | R | T39 |
| D100 | Downgrade and blocked banners | ✓ | ✓ | R5 | R | — |

### 9.11 Gates and plans
| # | Item | Phone | Desktop | Batch | Kind | Needs |
|---|---|---|---|---|---|---|
| D101 | Guest sign-in gate with how-it-works | ✓ | ✓ | R3 | R | T20 |
| D102 | Gate per reason: free, device limit, device revoked, replacement limit, halted, config error | ✓ | ✓ | R3 | R | — |
| D103 | Saved-progress tiles on halted/paused/expired gates | ✓ | ✓ | R3 | R | — |
| D104 | Plans stage: tier selector, plan card, CTA per viewer | pills | 3 cards | R3 | R | T21 |
| D105 | Plan footnotes (GST, renewal, calendar-month wording) | ✓ | ✓ | R3 | C | T21 |
| D106 | "Included with your account" card | ✓ | ✓ | R3 | R | — |

### 9.12 Profile and Settings
| # | Item | Phone | Desktop | Batch | Kind | Needs |
|---|---|---|---|---|---|---|
| D107 | Identity card with meta per state | ✓ | ✓ | R5 | R | T26 |
| D108 | SUBSCRIPTION card: title, chip, stat row, CTA per state | ✓ | ✓ | R5 | N | T26 |
| D109 | Account list: Devices n of limit, Learning preferences | ✓ | ✓ | R5 | N | T26 |
| D110 | Guest profile card | ✓ | ✓ | R5 | R | — |
| D111 | Settings phone layout: account card, STUDY, CALENDAR, APP, ACCOUNT, footer | ✓ | — | R5 | R | — |
| D112 | Settings phone Reminders row | ✓ | — | R5 | N | T27 |
| D113 | Settings controls and badges keep shipped styling | ✓ | ✓ | R5 | = | — |
| D114 | First-connect reminder sheet / dialog | sheet | dialog | R5 | = | — |

### 9.13 Today and Calendar
| # | Item | Phone | Desktop | Batch | Kind | Needs |
|---|---|---|---|---|---|---|
| D115 | Today: Playground nodes in the path with eyebrow | ✓ | ✓ | R6 | N | T28 |
| D116 | Today: current-node card for a Playground provision | ✓ | ✓ | R6 | N | T28 |
| D117 | Today: "New" Playground node | ✓ | ✓ | R6 | N | T28 |
| D118 | Today: gear opens Settings | ✓ | — | R6 | = | — |
| D119 | Today: two-column recall card + path | — | ✓ | R6 | R | — |
| D120 | Calendar rows and chips cite clauses; "· Playground" marker | ✓ | ✓ | R6 | N | T30 |
| D121 | Calendar footnote about Google Calendar | ✓ | — | R6 | C | T31 |
| D122 | Month / Week switch | — | ✓ | R6 | N | T29 |
| D123 | Week grid: seven columns, six card states with text | — | ✓ | R6 | N | T29 |
| D124 | Week: empty day, today ring, tap-through | — | ✓ | R6 | N | T29 |

### 9.14 Copy replacements (branch → design), where not covered above
| # | Where | Branch now | Ships as | Batch |
|---|---|---|---|---|
| D125 | Home H1 | My Playground | Playground (phone) / MY PLAYGROUND + month (desktop) | R3 |
| D126 | Home lede | "Laws on this month's Playground…" | removed | R3 |
| D127 | Card links | Progress · Select sections · Read | single Learn CTA (phone) | R3 |
| D128 | Picker lede | "Entire Act or individual sections. Chapter selection is not in this batch." | "Whole sections, or open one and pick clauses." | R2 |
| D129 | Picker button | Save selection | Add N sections → | R2 |
| D130 | Rollover button | Confirm | Continue with these / Done | R5 |
| D131 | Not-subscribed gate title | Subscribe to use Playground | Unlock Playground | R3 |
| D132 | Law page back | ← My Playground | ← Playground | R4 |

### 9.15 Source review and amendment states
| # | Item | Phone | Desktop | Batch | Kind | Needs |
|---|---|---|---|---|---|---|
| D133 | Source review list: affected provisions, change copy, Review/Open | ✓ | ✓ | R4 | R | T10 |
| D134 | Section review page: current verbatim text, "Mark reviewed" | ✓ | ✓ | R4 | R | T10 |
| D135 | Missing and omitted provision variants | ✓ | ✓ | R4 | R | T10 |
| D136 | Combined state: Mastered or Learned **and** Law updated | ✓ | ✓ | R4 | R | T10 |

### 9.16 Account surfaces and failure states
| # | Item | Phone | Desktop | Batch | Kind | Needs |
|---|---|---|---|---|---|---|
| D137 | Devices page: list, count of limit, remove confirmation, revoked list | ✓ | ✓ | R5 | R | T26 |
| D138 | Subscription checkout page | ✓ | ✓ | R5 | R | T21 |
| D139 | Learn failure states: save failed, stale revision, not due, not selected | ✓ | ✓ | R4 | R | T23 |
| D140 | Playground unavailable / service error page | ✓ | ✓ | R3 | R | — |
| D141 | Speech unavailable or offline: typed path offered, no dead control | ✓ | ✓ | R4 | N | T25 |
| D142 | HTML error surfaces reached from Playground (404, 403, 500, kill-switch 404) | ✓ | ✓ | R3 | R | — |

## 10. Layer 2 — Technical / Behavioural Changes Required by the New Design

**Mandatory checklist before implementation begins.** Every row is reviewed
and accepted before R0 starts. A technical dependency discovered mid-batch
is added here first, with its batch and tests, before any code for it is
written. Delta = the approved product delta (§2) it implements.

### 10.1 Source safety and merge (R0)
| # | Change | Why the design needs it | Touches | Tests | Delta |
|---|---|---|---|---|---|
| T1 | Merge `main`; resolve 5 conflicts; re-place the CTA | Designs assume main's Act head and seven Acts | `base.html`, `bare_act.html`, `web/app.py`, two test files | full suite | — |
| T2 | Hash-drift guard, **stop condition** | A drifted hash shows "Law updated" on every card | `playground/source.py`, new snapshot test | snapshot NDPS s.8, BNS s.103, BNSS s.479 | — |
| T3 | Footnote-title guard | Title anchors from main must not alter hashes or titles shown in picker/cards | `source.py`, `web/bare_acts.py` usage | hash + title tests | — |
| T4 | Eligibility: current Acts only; slug is the identity; `laws.html` keyed by slug | D30; one roster entry per law | `playground/eligibility.py`, `laws.html`, `view.py` | eligible six; `pota`, `uapa-1967` rejected | F |
| T5 | Chapterless Acts in picker, workspace, progress | D42; MTP has no chapters | `playground_select.html`, `view.py`, `units.py` | MTP picker and workspace tests | F |
| T6 | Regenerate sitemap manifest; `/playground*` stays noindex | New Acts, new routes | `law_sitemap_manifest.json`, `seo.py` | sitemap + noindex tests | — |
| T7 | Remove dead CSRF-less cloze path | Security hygiene before new JS lands | `playground.js`, `playground_cloze.html` | grep test | — |
| T37 | Re-validate this plan against the new branch head | Audit was taken at `c76ba92` | plan + tracker | delta review recorded | — |

### 10.2 Clause-level selection (R2)
| # | Change | Why the design needs it | Touches | Tests | Delta |
|---|---|---|---|---|---|
| T8 | Locator grammar; bounded section number; `SectionLocator` / `UnitLocator` with explicit `ordinal` | D45, D46, D85 | `locators.py` and every caller | round-trip, `~n`, rejection | A |
| T9 | `playground/units.py`: enumerate, resolve, unit text, lead-in, tail, citation | D45, D85 | new module; `service.py`, `learning/service.py` | NDPS s.8/9, BNS s.2, PSS s.38, MTP | A |
| T10 | Unit hash and unit-level source review | "Law updated" must be per learned unit | `source.py`, `source_review.py` | hash changes with lead-in; review flow | A |
| T11 | Exclusivity, promotion, dormant progress on granularity switch | D46 | `service.py` selection normalisation | promotion; both-granularity rejection | A |
| T12 | Due and schedule queries join the current selection | Deselected work must leave Today, Calendar, Google | `repository.py`, `postgres.py` | deselect → not due | A |
| T13 | Computed `unit_count`; "provisions" wording; ring denominators | D48, D49, D65 | summary SQL, `view.py` | count tests, 0/1/2 plurals | A |
| T14 | Clause learn routes; `learn_path_for_locator`; `citation_label` | D76, D85, D120 | `routes.py`, `urls.py`, `view.py`, `schedule.py` | route 200/400, six modes → Learned | A |
| T15 | Picker POST contract (`section=`, `unit=`), no-JS path, `playground-select.js` | D45–D50 | `routes.py`, `playground_select.html`, new JS | form normalisation; markup | A |
| T16 | Per-section status line view model | D44 | `view.py` (`section_row_view`) | five states | A |

### 10.3 Add, home, gates (R3)
| # | Change | Why the design needs it | Touches | Tests | Delta |
|---|---|---|---|---|---|
| T17 | Scope step after confirm; Max skips confirm | D32–D34 | `routes.py` add handlers, `playground_add.html` | redirects and copy | — |
| T18 | Act-head and add-sheet state model covers pending, full, paused | D22, D27, D28, D37, D38 | `view.py:law_membership`, `partials/playground.html` | one test per state | — |
| T19 | Access chain: paused/expired render a read-only home; learn and mutations blocked | D61 | `access.py`, `view.py:build_home_view`, `routes.py` | home 200 read-only; learn blocked | G |
| T20 | Guest HTML GET renders the gate; JSON 401; POST unchanged; `next` preserved | D35, D101 | `access.py:_deny_open` | replaces the 303 tests | H |
| T21 | Plans stage reads tiers, prices, limits from the catalogue | D36, D104, D105 | `subscription_manage.html`, `subscriptions/` | "₹199"; no placeholder strings | — |
| T38 | Sheet/dialog enhancement for add, remove, reminder; focus trap; fallback page | D12, D13, D31, D40, D95 | `playground.js:enhanceSheets` | dialog role tests | — |
| T39 | Tab-bar hide rules and sticky-footer offset | D17, D21, D23, D99 | `mobile.css`, `playground_base.html` | selector tests | — |

### 10.4 Progress, Learn, speech (R4)
| # | Change | Why the design needs it | Touches | Tests | Delta |
|---|---|---|---|---|---|
| T22 | Aggregates: per-rung counts, % in ladder, next-up provision, computed scope | D53, D56, D64–D68 | `repository.py`, `view.py`, `routes.py` workspace | counts match rows | — |
| T23 | Modes-seen state drives step bar and "n methods left" | D75, D78 | `playground_learn.html`, `playground-learn.js`, learn view model | step state per mode | — |
| T24 | Completion routes; Mastered aggregates (reviews, days, accuracy) only from real data | D88–D91 | new `playground_learned.html`, `routes.py`, `lifecycle.py` | gated on status; stray visit redirects | — |
| T25 | Playground speech route on the existing stack; expected text server-side; access chain, CSRF, limits; client uses `window.RecallSpeech` | D81, D83 | new route in `playground/` reusing `speech/`; `playground-learn.js` | mirrors `test_speech_routes.py`; fallback test | E |

### 10.5 Profile and Settings (R5)
| # | Change | Why the design needs it | Touches | Tests | Delta |
|---|---|---|---|---|---|
| T26 | Subscription card view model from the entitlement snapshot; device count from the device service | D107–D109 | `auth/routes.py` profile context, `profile.html` | chip per status; "n of 2" | — |
| T27 | Phone Reminders row posts `reminder_cadence` to the existing endpoint | D112 | `settings.html`, `mobile.css` | row present when connected; saves | — |

### 10.6 Today, Calendar, Google (R6)
| # | Change | Why the design needs it | Touches | Tests | Delta |
|---|---|---|---|---|---|
| T28 | Today path merge; New selection rule; `due_count` excludes New | D115–D117 | `web/dashboard.py`, `playground/schedule.py`, `auth/routes.py`, `dashboard.html` | merged path; one New; count | C |
| T29 | Week view model and route | D122–D124 | `web/calendar_view.py`, `web/app.py`, `calendar.html`, `styles.css` | week across month boundary; month unchanged | D |
| T30 | Clause citations in calendar chips and rows | D120 | `playground/schedule.py` | chip label tests | A |
| T31 | Google projection includes pending Playground rung; triggers; entitlement check; failure isolation | D121 | `calendar_sync/projection.py`, `sync.py`, `playground/routes.py` | merged labels, cap, hash, paused excluded | B |
| T32 | Narrow missing-schema guards on Today, Calendar, sync | Constitution pages must survive an unmigrated DB | same as T28, T29, T31 | DB at 0016 renders | — |

### 10.7 Cross-cutting
| # | Change | Why the design needs it | Touches | Tests | Batch |
|---|---|---|---|---|---|
| T33 | Asset version bumps and test pins | Cached CSS/JS would hide the redesign | `base.html`, `test_settings_phone.py` | version pins | every |
| T34 | Dark values derived for every new token; fixed-dark completion surface | Prototypes define no dark theme | `playground.css` | token presence, light + dark | R1 |
| T35 | Negative grep test for strings that must not ship | §11 | templates, static | one test | R1 |
| T36 | Redesign tracker; prototypes and handoff committed | Traceability without touching Stage 1 | `docs/` | — | R0, R7 |
| T40 | Planned test rewrites, each with its reason | Branch tests pin copy and classes | see §13 | — | per batch |
| T41 | Route/template inventory generated and every active route classified A–E | §21 coverage requirement | `docs/design/PLAYGROUND_DESIGN_INVENTORY.md`, tracker | inventory test: no unclassified template | R1 |

### 10.8 Impact record per technical row

Completes the documentation each Layer 2 row must carry. "None expected"
under Data means no schema change is currently expected (§5).

| # | Data / schema | Route / API | Security |
|---|---|---|---|
| T1 | none | none new | preserve CSRF and auth wiring from both sides |
| T2 | none; guards stored hashes | none | data integrity |
| T3 | none | none | data integrity |
| T4 | none; roster `law_id` values constrained to slugs | add/remove routes reject alias and repealed ids (404) | prevents a second roster entry for one law |
| T5 | none | none | — |
| T6 | regenerated manifest file | sitemap output | `/playground*` stays noindex |
| T7 | none | removes an unauthenticated-style POST path | closes a CSRF-less mutation |
| T8 | new locator strings in existing TEXT columns | locator in learn URLs | strict parsing rejects malformed input |
| T9 | none | none | — |
| T10 | unit hashes in existing hash columns | source-review routes accept unit locators | stale-review POST still 409 |
| T11 | selection rows only; progress rows untouched | selection POST normalised server-side | server is the authority, not the client |
| T12 | query change only | none | — |
| T13 | computed alias only | none | — |
| T14 | none | new `/sections/{n}/u/{unit}/learn/{mode}` + start/complete/quiz | same access chain and CSRF as section routes |
| T15 | none | picker POST accepts `unit=` | input validated against enumerated units |
| T16 | none | none | — |
| T17 | none | add flow gains a scope step | confirm POST keeps CSRF |
| T18 | none | none | UI renders server decisions only |
| T19 | none | home GET allowed when paused; learn and POST stay blocked | must not widen write access |
| T20 | none | HTML GET renders gate; JSON 401; POST unchanged | `next` validated as a local path |
| T21 | none | `/billing/subscriptions` | prices never client-supplied |
| T22 | read-only aggregates | none | — |
| T23 | none | none | — |
| T24 | none | new completion GET routes | gated on real lifecycle status |
| T25 | none; audio never stored | new Playground transcribe route | access chain, CSRF, 2 MB cap, MIME allowlist, rate limit |
| T26 | none | profile context | no device identifiers exposed |
| T27 | none | existing preferences POST | CSRF as existing |
| T28 | read-only | none | entitlement checked before listing |
| T29 | read-only | `/calendar?view=week&date=` | date parameter validated |
| T30 | none | none | — |
| T31 | sync payload hash changes | none new; more sync triggers | entitlement resolved server-side per sync |
| T32 | tolerates absent tables | none | narrow guard; other SQL errors surface |
| T33 | none | asset URLs | — |
| T34 | none | none | — |
| T35 | none | none | — |
| T36 | docs only | none | licence check on the dome icon before use |
| T37 | none | none | — |
| T38 | none | fetches existing pages | same-origin only |
| T39 | none | none | — |
| T40 | none | none | — |
| T41 | docs only | none | — |

## 11. Must not ship

Enforced by T35.

| # | Item |
|---|---|
| X1 | Core / Deep / Infinite, ₹149 / ₹299 / ₹499, fixed prototype month dates |
| X2 | "offical"; unsupported Gazette provenance wording |
| X3 | Plural bugs ("1 spaces remaining") |
| X4 | Unreachable gcal states; contradictory demo data |
| X5 | "Devices 2 of 3"; free-tier copy contradictions |
| X6 | Streak chip; Study archive; filled Settings badges |
| X7 | Prototype gating holes (screens reachable without entitlement) |
| X8 | Hard-coded scope labels, names, dates, percentages |

Explicit exclusions are listed once, in §21.4.

## 12. Tracking

- `docs/PLAYGROUND_DELIVERY_TRACKER.md` continues to read
  "Stage 1 DONE — 100/100, Stage 2 PARKED". It is not edited.
- New `docs/PLAYGROUND_UI_REDESIGN_TRACKER.md` tracks R0–R7, product deltas
  A–H, Layer 1 rows D1–D142, Layer 2 rows T1–T41, closeout rows V1–V24 and
  X1–X8, scored per §15 with the columns in §17.

## 13. Verification

**Automated, per batch**

| Batch | Focused targets |
|---|---|
| R0 | hash snapshot test; eligibility tests; `test_law_catalog.py`, `test_act_info_panel.py`, `test_mtp_reader.py`, `test_settings_phone.py`, `test_learn_request_breakdown.py`, sitemap tests, `test_migrations.py`; `alembic heads` = `20260927_0027` (expected); pre-merge SHA recorded |
| R1 | `test_playground_m6.py` CSS contract; `test_mobile_screens.py` |
| R2 | `test_playground_units.py`, `test_playground.py`, `test_playground_m7/m8/m9.py` |
| R3 | `test_playground_m6.py`, `test_entitlement_m3*.py` |
| R4 | `test_playground_m7.py`, new Playground speech tests, `test_speech_routes.py` |
| R5 | `test_roster_m5*.py`, `test_devices_*.py`, `test_subscription*.py`, `test_settings_phone.py` |
| R6 | `test_dashboard.py`, `test_playground_m8.py`, new `test_calendar_week.py`, `test_calendar_projection.py`, `test_calendar_sync.py` |
| R7 | full suite |

Known rewrites: `test_playground_m6.py:115,422` (guest 303 → gate),
`:420` (expired/paused gate → read-only home);
`test_playground_m8.py:676-730` ("Law revisions" block → path nodes);
Act-enumerating loops gain `uapa`, `pss`, `mtp`.

**Visual matrix**, every relevant screen/state: 390x844, ~768, ~1024 and
1280+; light and dark; reduced motion on, and off where animated. Dev server:
`mobile-dev` launch config.

**Critical manual flows at closeout**

- Eligibility: MTP readable + addable; POTA readable, no Add;
  `/playground/laws/uapa-1967/add` → 404; `/playground/laws/uapa/add` valid.
- Clause selection: NDPS s.8 select (a)+(c) → partial; select the rest →
  promotes to whole section. PSS s.38 two "(2)" rows separately selectable.
- Clause learn: complete a unit through all six modes; the whole section is
  not marked Learned.
- Guest: `/playground` → gate HTML with correct `next`.
- Paused: home visible read-only; learn route blocked.
- Today: due nodes + at most one New; `due_count` unchanged by New.
- Week view: desktop only.
- Google: completing a revision updates the event; pause removes the
  Playground line; resume restores it.
- Speech: Letters and Recite work with real speech; without Deepgram
  config or browser support, the typed fallback remains usable.

## 14. Risks

- **Clause selection** changes locator semantics, scheduling, source
  review, learn URLs, progress aggregation, Today and Calendar. It is never
  "implement the prototype"; R2 lands before any UI depends on it.
- **Hash drift on merge** is an R0 stop condition (see R0), not a risk to
  monitor.
- **Stale audit.** Findings were taken at `c76ba92`; the branch is now at
  `e03253e`. R0 re-validates them before relying on any line reference.
- **Test churn.** Branch tests pin exact copy and class names; each batch
  lists what it rewrites and why.
- **Not yet read in detail:** `subscription_manage.html` and its tests,
  roster template tests, `docs/PLAYGROUND_M11_REPORT.md`. R0, R3 and R5
  start by reading them.

## 15. Coverage model — 100-point scorecard

The programme is complete only at **UI Redesign Programme = 100.0 / 100**,
reached through explicit, testable coverage of visual design, responsive
behaviour, interaction, technical dependencies, accessibility,
product-state coverage, backend-contract preservation and regression
safety. It uses Stage 1's delivery discipline: defined milestones, weighted
score, explicit acceptance items, per-batch tests, manual visual
verification, a close-out report, and CI-green final proof.

```
Stage 1               = DONE — 100.0 / 100   (frozen)
UI Redesign Programme = 0.0 / 100
Stage 2               = PARKED until the programme is DONE — 100.0 / 100
```

### 15.1 Definition of done

All of the following are true:

- Every screen in the desktop prototype is represented.
- Every screen in the mobile prototype is represented.
- Every state shown by the prototypes is represented.
- Every Stage 1 production state not shown in the prototypes still has a
  valid redesigned state.
- Every desktop/phone divergence is intentional and documented.
- Every interaction works, not just looks correct.
- Every technical dependency (Layer 2) is implemented.
- Every approved product delta (A–H) is implemented.
- Every accessibility requirement is verified.
- Every relevant Stage 1 backend contract remains green.
- Full regression suite is green; final visual verification is complete.

A screen is not complete if only its default state exists. A visual match
alone does not count as functional completion.

### 15.2 Milestones, weights and acceptance rows

Every Layer 1 row (D), Layer 2 row (T) and closeout row (V) belongs to
exactly one milestone. This assignment was checked by script: no row is
unassigned and none is counted twice.

| Milestone | Scope | Weight | Batches | Acceptance rows | Items |
|---|---|---|---|---|---|
| U0 | Source reconciliation + merge safety | 5 | R0 | D26, D30, T1–T4, T6–T7, T36–T37 | 10 |
| U1 | Shared design system + application shells | 12 | R1 | D1–D10, D12–D21, D24–D25, T33–T35, T38–T39, T41 | 28 |
| U2 | Bare Act + Add flow + clause-level selection | 18 | R2, R3 | D11, D23, D27–D29, D31–D50, D128–D129, T5, T8–T18 | 39 |
| U3 | Playground home + gates + roster lifecycle | 12 | R3, R5 | D22, D51–D63, D93–D106, D125–D127, D130–D131, D140, D142, T19–T21 | 38 |
| U4 | Act progress + six-mode Learn + speech | 18 | R4 | D64–D72, D74–D85, D87, D132, D139, D141, T22–T23, T25 | 28 |
| U5 | Learned, revision, mastery + amendment states | 8 | R4 | D73, D86, D88–D92, D133–D136, T24 | 12 |
| U6 | Today + Calendar + Google Calendar | 10 | R6 | D115–D124, T28–T32 | 15 |
| U7 | Profile + Settings + account surfaces | 7 | R5 | D107–D114, D137–D138, T26–T27 | 12 |
| U8 | Responsive, accessibility, parity + final regression | 10 | R7 | T40, V1–V24 | 25 |
| **Total** | | **100** | | | **207** |

Batches deliver milestones; they are not the same thing. U2 and U3 each
span two batches, so they close only when both have landed.

### 15.3 Closeout rows (U8)

| # | Closeout item |
|---|---|
| V1 | Every screen/state checked at 390x844 |
| V2 | Every screen/state checked at ~768 |
| V3 | Every screen/state checked at ~1024 |
| V4 | Every screen/state checked at 1280+ |
| V5 | Light theme verified |
| V6 | Dark theme verified |
| V7 | Reduced motion verified |
| V8 | Keyboard traversal of every flow |
| V9 | Visible focus state on every control |
| V10 | ARIA: dialog roles, radiogroups, tri-state checkboxes |
| V11 | 44px targets and safe areas |
| V12 | Status never conveyed by colour alone |
| V13 | Contrast verified, light and dark |
| V14 | Semantic link vs button usage |
| V15 | Every D row marked matched / intentional deviation / not applicable, with prototype reference |
| V16 | Regression: subscriptions, devices, roster |
| V17 | Regression: six modes, ladder, source review |
| V18 | Regression: SEO/noindex, public laws, Constitution, admin |
| V19 | Full suite green |
| V20 | CI green |
| V21 | Desktop visual sign-off |
| V22 | Mobile visual sign-off |
| V23 | Every class-B surface verified element by element against the design system at 390 and 1280, light and dark; every non-conforming element raised as a D row and closed |
| V24 | Zero unclassified active routes; every exclusion documented; every obsolete surface retained deliberately or proven unused |

### 15.4 Score rules

No subjective partial credit based on appearance.

```
earned milestone score = proven items / total items × milestone weight
```

Example: U4 weighs 18; with 27 of its items proven out of N, it earns
27 / N × 18. Full weight is awarded only when every item is proven. An item
is proven by evidence: a passing automated test and, for visual rows, the
recorded checks in the tracker columns. Items added later under §18 join
their milestone's denominator.

## 16. Inventories required before U1 begins

### 16.1 Design inventory

Create `docs/design/PLAYGROUND_DESIGN_INVENTORY.md`, built from both
authoritative `.dc.html` files. One entry per prototype screen, recording:
screen name · viewport · route/surface · major components · visible states ·
actions · dialogs/sheets · copy · responsive-specific behaviour · production
equivalent · batch · tracker acceptance IDs. Nothing is omitted because it
resembles another screen. §9 is the starting point; the inventory is where
any row §9 lacks is found and added.

### 16.2 Production-state inventory

The prototypes do not show every real state. Each production state maps to
a prototype state or an intentional designed extension. No state may be
"undefined" at closeout.

| Production state | Covered by | Basis |
|---|---|---|
| Guest | D27, D35, D101, D110 | prototype |
| Free (signed in, no plan) | D27, D36, D102, D104, D108 | prototype |
| Active Plus / Pro / Max | D32, D33, D58, D104, D108 | prototype |
| Pending payment | D38, D62 | desktop prototype |
| Paused / expired | D61, D103, D108 | prototype + delta G |
| Halted | D102, D103 | desktop prototype |
| Cancel at period end | D62 | desktop prototype |
| Upgrade / downgrade scheduled / resubscribed | D62, D100 | desktop prototype |
| Device limited / revoked | D102, D137 | desktop prototype |
| Replacement limited | D102 | desktop prototype |
| Device config error | D102 | designed extension |
| Roster full | D27, D37, D58 | prototype |
| Removed law | D57, D94 | desktop prototype |
| Saved historical law | D57, D96 | desktop prototype |
| Source updated | D55, D73, D133 | branch state, designed extension |
| Missing / omitted provision | D135 | designed extension |
| Mastered + Law updated | D136 | designed extension |
| Not started / Learning / Learned / Due / Mastered | D44, D54, D72 | prototype |
| Overdue | D56, D123 | desktop prototype |
| Empty (no laws, no sections) | D60, D74 | prototype |
| Learn failure (save failed, stale, not due) | D139 | designed extension |
| Service error | D140 | designed extension |
| Speech unavailable / offline | D141 | designed extension |

## 17. Tracker structure

`docs/PLAYGROUND_UI_REDESIGN_TRACKER.md` opens with the three status lines
in §15, then U0–U8. Each acceptance item carries:

Requirement · Desktop · Mobile · Automated test · 390 light · 390 dark ·
~768 · ~1024 · 1280 light · 1280 dark · Reduced motion · Status ·
Evidence / commit

Technical-only items mark Desktop/Mobile "N/A"; automated or integration
evidence is still required. Visual rows also record parity: matched,
intentional deviation, or not applicable, with the prototype reference.

## 18. Nothing-missed rule

Every change discovered during implementation is classified at once:

- **A.** Already represented by an acceptance item.
- **B.** Missing design acceptance item.
- **C.** Missing technical acceptance item.
- **D.** Genuine new scope requiring an explicit decision.

For B or C, the row is added to the tracker, with its milestone, **before**
it is implemented. For D, work stops on that item until decided. No
untracked requirement is silently fixed.

## 19. Per-batch closeout report

Every R0–R7 batch reports, using exact tracker status:

acceptance items targeted · completed · remaining · programme score before ·
programme score after · visual checks · technical checks · focused tests ·
full regression · CI status

Never "mostly complete", "looks good" or "nearly matches".

## 20. Final completion gate

The programme is declared DONE only when U0–U8 are each complete, the score
is 100.0 / 100, and:

- all design inventory rows are accounted for;
- all technical dependency rows are accounted for;
- all original checklist items and all later-discovered items are closed;
- full regression and CI are green;
- desktop and mobile visual sign-off are complete.

Then, and only then:

```
Stage 1               = DONE — 100.0 / 100
UI Redesign Programme = DONE — 100.0 / 100
Stage 2               = NOT STARTED / READY
```

and the parked Stage 2 S2-0 baseline resumes against the final UI.

## 21. Missing pages and unrepresented screens

The prototypes do not contain every production route, page, state, modal,
error surface or transition. **Anything missing from the prototypes is
still in scope unless it is explicitly marked out of scope (§21.4).** An
old page is never left visually untouched merely because the prototypes
omit it. The finished product must read as one coherent application, not
new Playground pages beside legacy-looking leftovers.

### 21.1 Procedure for every surface the prototypes omit

1. Identify the page or surface.
2. Determine whether it is still part of the product.
3. If obsolete, prove it is unused before removal.
4. If active, redesign it to the new visual system.
5. Preserve its business and authorisation behaviour unless this plan
   explicitly changes it.
6. Add it to the design inventory and the tracker.
7. Verify desktop and phone behaviour as applicable.
8. Close it with the same visual, accessibility, functional and regression
   evidence as a prototype-backed screen.

### 21.2 Design derivation order

No separate visual language is invented. Derive, in order, from:

1. Shared tokens and components from U1.
2. The closest equivalent prototype screen.
3. The same interaction pattern elsewhere in the new design.
4. Existing production information architecture and behaviour.

| Unknown surface | Derive from |
|---|---|
| Account page | Profile / Settings card language |
| Entitlement error | Gate / banner language |
| Confirmation flow | Phone bottom sheet / desktop dialog |
| Empty state | Shared empty-state hierarchy |
| Form | Shared field, button and focus primitives |
| List or table | Desktop table/card primitives |

### 21.3 Classification

Before U1 is complete (T41), every active route and template is classified:

- **A** Direct prototype match
- **B** Covered by another design family. Verify against the new design
  system and restyle **every element that does not conform**, not only
  obvious visual clashes.
- **C** Missing from prototype; designed extension required
- **D** Explicitly out of scope
- **E** Obsolete; candidate for removal after proof

No active route may remain unclassified. **Decided:** class-B pages are not
rebuilt wholesale. Each is verified element by element against the shared
tokens and components (colour, type, radii, spacing, buttons, cards, chips,
fields, focus, motion). Every non-conforming element is restyled, however
minor, and recorded as a Layer 1 `D` row before the change. "It is not a
dramatic clash" is not a reason to leave legacy styling in place.

**First-pass classification of the branch's 81 templates** (taken at
`c76ba92`; confirmed or corrected by T41 against the actual head):

| Class | Templates | Rows |
|---|---|---|
| A | `base.html` (shell), `bare_act.html`, `playground_base.html`, `playground.html`, `playground_add.html`, `playground_select.html`, `playground_law.html`, `playground_learn.html`, `playground_remove.html`, `playground_roster.html`, `playground_roster_next.html`, `playground_gate.html`, `subscription_manage.html`, `dashboard.html`, `calendar.html`, `profile.html`, `settings.html`, `partials/playground.html` | D18–D132 |
| A, verify only | `browse_index.html`, `laws.html` (drawn in the desktop prototype to mirror production) | V23 |
| B | `browse_part.html`, `browse_article.html`, `learn.html`, `choose.html`, `incomplete.html`, `search.html`, `tables.html`, `memory.html`, `memory_detail.html`, `law_detail.html`, `bare_act_section.html`, `bare_act_schedule.html`, `progress.html`, `progress_mastered.html`, `guest_gate.html`, `welcome.html`, `onboarding_plan.html`, `plan_my_day.html`, `home.html`, `pricing.html`, `purchase_confirm.html`, `purchase_result.html`, `login.html`, `signed_out.html`, `session_expired.html`, `auth_transition.html`, `auth_callback.html`, `landing.html`, `landing_light.html`, `legal/*` (5), `visual_explainer*.html` (2), `_completion_banner.html`, `_locked_mode.html`, `partials/auth_shell.html`, `partials/bare_act_footnotes.html`, `partials/bare_act_macros.html`, `partials/guest_modal.html`, `partials/mode_help_modal.html`, `partials/report_dialog.html`, `partials/revision_exit_modal.html` | V23 |
| C | `playground_source_review.html`, `playground_source_review_section.html`, `devices.html`, `subscription_checkout.html`; gate reasons with no drawn state; Learn failure states; service and HTML error surfaces; speech-unavailable state | D102, D133–D142 |
| D | `admin/*` (11 incl. base and audit table) | §21.4 |
| E | `playground_cloze.html` | T7 |

Non-template surfaces are classified the same way: redirect-only routes
(Google connect/callback, auth start/callback), JSON endpoints, sitemaps,
icons and the service worker have no page to redesign and are recorded as
"no UI" in the inventory.

Pages in class B that sit closest to Playground and are checked first:
`bare_act_section.html` and `bare_act_schedule.html` (reached from the Act
head), `guest_gate.html` and `pricing.html` (reached from gates),
`purchase_*` (shares the checkout family), `learn.html` (shares the Learn
deck language).

### 21.4 Explicit exclusions (class D)

| Excluded | Reason | What still must hold |
|---|---|---|
| Admin console (`admin/*`) | User decision | Regression proves admin behaviour intact, incl. Playground device controls on the user page |
| Calendar → Study archive | Code lives on `codex/playground-study-calendar`, not this branch | Calendar "Current" design is fully in scope |
| Settings control restyle | Decision D6: shipped segments and badges stay | Documented as an intentional deviation from both prototypes |
| Clause picking inside the reader itself | Not drawn; selection happens in the picker | — |

Nothing else is excluded. An exclusion not in this table does not exist.

### 21.5 Tracker rule for class C

Every class-C item gets a Layer 1 `D` row **before** implementation,
specifying: surface / route · closest design reference · desktop treatment ·
phone treatment · interaction treatment · technical dependencies ·
accessibility requirements · tests · visual verification. The row joins its
milestone's denominator, so the programme score expands to include newly
discovered active pages.

### 21.6 Completion rule

The programme cannot reach 100.0 / 100 while any active page or state still
uses the old visual language unintentionally. At closeout the evidence
shows:

- all prototype-backed pages redesigned;
- all active non-prototype pages redesigned to the same standard, or
  verified element by element as already conforming;
- all intentional exclusions documented (§21.4);
- all obsolete surfaces retained deliberately or proven safe to remove.
