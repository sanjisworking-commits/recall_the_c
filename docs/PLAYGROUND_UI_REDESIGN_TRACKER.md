# Playground UI Redesign + Product Delta — Tracker

**Not the Stage 1 scoreboard.** Do not edit `docs/PLAYGROUND_DELIVERY_TRACKER.md`.

```text
Stage 1               = DONE — 100.0 / 100   (frozen)
UI Redesign Programme = 17.0 / 100
Stage 2               = PARKED until the programme is DONE — 100.0 / 100
```

Authority: `docs/PLAYGROUND_UI_REDESIGN_PLAN.md`. Inventories: `docs/design/PLAYGROUND_DESIGN_INVENTORY.md`.

---

## Repository state

| Field | Value |
|---|---|
| Branch | `cursor/playground-220d` |
| Pre-merge SHA (audit / T1 base) | `a5edca57d06f2a516fb2111be6e2e6f5db507f67` |
| Audit docs SHA | `ed1112ccc95ec32dd4a292ad9852b0834dfff768` |
| **HEAD after human R0 merge** | **`5035ce2e9d6e2ac14a01367d25e41dc12565257f`** |
| Merge commit | `a17134dc0fe06dfef8b79d60754b6e89d62e5521` (`main` @ `0c0a8d5` into playground) |
| Prototype commit | **`58a1a264be4a337d06eee3358ad758bf615815cd`** — two `.dc.html` files only |
| Plan’s recorded remote head | `e03253e` (**stale**) |
| Plan audit snapshot | `c76ba92` |
| `origin/main` | `0c0a8d555748cb5fa63a5fbe0a43998ee5c1d942` |
| Alembic heads | **one:** `20260927_0027` |
| T2 hash-drift | **did not fire.** Snapshot fixture pins 1136 eligible-section hashes including NDPS/BNS/BNSS 1018 and sentinels NDPS s.8 `938804c4…`, BNS s.103 `aea2c0bf…`, BNSS s.479 `2ebe577d…`. |
| T36 prototypes | Desktop `61d8d01a…` (2,902 lines); mobile `361b7e25…` (1,829 lines). Not referenced from `src/`. |
| **R1 closeout HEAD** | **`cf41baf`** (tracker) · last code **`cd1c4c6`**. U1 28/28. Do not start R2. |

Visual columns (390 light/dark, ~768, ~1024, 1280 light/dark, reduced motion) stay `—` until the relevant batch. Technical rows mark Desktop/Mobile **N/A**. Status uses only: `NOT STARTED | IN PROGRESS | BLOCKED | IN REVIEW | DONE`.

---

## Scoreboard

| Milestone | Scope | Weight | Batches | Items | Proven | Score |
|---|---|---|---|---|---|---|
| U0 | Source reconciliation + merge safety | 5 | R0 | 10 | 10 | 5.0 |
| U1 | Shared design system + shells | 12 | R1 | 28 | 28 | 12.0 |
| U2 | Bare Act + Add + clause-level selection | 18 | R2, R3 | 39 | 0 | 0.0 |
| U3 | Home + gates + roster lifecycle | 12 | R3, R5 | 38 | 0 | 0.0 |
| U4 | Act progress + six-mode Learn + speech | 18 | R4 | 28 | 0 | 0.0 |
| U5 | Learned / mastery / amendment states | 8 | R4 | 12 | 0 | 0.0 |
| U6 | Today + Calendar + Google Calendar | 10 | R6 | 15 | 0 | 0.0 |
| U7 | Profile + Settings + account surfaces | 7 | R5 | 12 | 0 | 0.0 |
| U8 | Responsive, a11y, parity, regression | 10 | R7 | 25 | 0 | 0.0 |
| **Total** | | **100** | | **207** | **38** | **17.0 / 100** |

Uniqueness (script-checked from §15.2; no row in two milestones, none omitted):

- D1–D142: 142
- T1–T41: 41
- V1–V24: 24
- **207**
- X1–X8 are enforced by **T35**, not extra denominator rows.

No newly discovered B/C rows were added, so the denominator is unchanged.

---

## Product deltas A–H

| Id | Delta | Layer 2 | Status |
|---|---|---|---|
| A | Clause-level selection | T8–T16, T30 | NOT STARTED |
| B | Playground pending rung → Google Calendar | T31 | NOT STARTED |
| C | Selected unlearned work in Today | T28 | NOT STARTED |
| D | Desktop Calendar Week | T29 | NOT STARTED |
| E | Real speech on Letters/Recite | T25 | NOT STARTED |
| F | Eligible Acts NDPS, BNS, BNSS, UAPA, PSS, MTP; POTA readable; slug identity | T4, T5 | IN REVIEW |
| G | Paused/expired read-only home | T19 | NOT STARTED |
| H | Guest HTML GET renders gate; JSON 401 | T20 | NOT STARTED |

---

## U0 — Source reconciliation + merge safety (weight 5, 10 items)

R0. Prototypes and inventories are in place. **R1 (U1) is closed on `cf41baf`.**

| ID | Requirement | D/M | Status | Evidence |
|---|---|---|---|---|
| D26 | CTA placed in main’s new Act head | both | DONE | `bare_act.html`: CTA after status note, before About toggle. `test_bare_act_head_has_add_button_for_eligible_laws` |
| D30 | No CTA on repealed Acts; CTA on MTP chapterless page | both | DONE | Eligible six have CTA; `pota` and `uapa-1967` do not. Hub keyed by catalogue id. MTP picker `data-chapterless` |
| T1 | Merge `main` @ `0c0a8d5`; resolve 5 content conflicts; re-place CTA | N/A | DONE | `a17134d`. Five conflicts resolved per plan. Snapshot test now lands so T1 is closed |
| T2 | Hash-drift guard (stop condition) | N/A | DONE | `tests/fixtures/playground/section_source_hashes.json` + `test_playground_source_hashes.py`. NDPS s.8 / BNS s.103 / BNSS s.479 + 1018 learner-Act hashes |
| T3 | Footnote-title guard | N/A | DONE | Mutating `title_annotations` leaves `source_hash` unchanged. Picker/workspace show `list_title`, not `2[` markers |
| T4 | Eligibility: current Acts; slug identity; `laws.html` keyed by slug | N/A | DONE | Eligible `bns bnss ndps uapa pss mtp`. `uapa-1967` and `pota` rejected. Hub lookup `law.full_act_ref or law.id` |
| T6 | Regenerate sitemap; `/playground*` noindex | N/A | DONE | Merge regenerated the seven-Act manifest. `/playground` remains in `NOINDEX_PATH_PREFIXES` |
| T7 | Remove dead CSRF-less cloze path | N/A | DONE | Deleted `playground_cloze.html`; stripped `[data-playground-cloze]` POST from `playground.js` (`?v=pg5`). `complete_cloze()` kept |
| T36 | Tracker (this file); prototypes + handoff committed | N/A | DONE | `58a1a26` committed both named `.dc.html` files. Desktop 2,902 lines SHA-256 `61d8d01a099e8d6776d9dcb925fc6f37a625c98add11554d00fee1049d28c976`. Mobile 1,829 lines SHA-256 `361b7e25087f3c8e26a89156518bc2654594502dc1211a20884a6eed499c0af5`. Not runtime assets. |
| T37 | Re-validate plan against new head | N/A | DONE | Audit at `a5edca5`; merge `a17134d`; prototypes `58a1a26`; U0 complete |

---

## U1 — Shared design system + shells (weight 12, 28 items)

R1 closed on `cf41baf`. Guard held: no `UnitLocator`, clause fields, `unit_count`, new clause routes, new Today/week/speech APIs, or placeholder clause UI.

| ID | Requirement | D/M | Status | Evidence |
|---|---|---|---|---|
| D1 | Colour tokens: ink, paper, page, hairlines, muted/faint | both | DONE | `--pg-ink/paper/page/hairline/muted/faint` in light+dark blocks. `test_d1_d16_design_system_primitives_in_css` |
| D2 | Teal family | both | DONE | `--pg-teal` family + `.pg-btn--teal`. 390 teal active tab. `test_d1_d16` |
| D3 | Amber/overdue and destructive families | both | DONE | `--pg-amber*`, `--pg-destructive*`. `DueBadge[data-due]`. Sign out uses destructive |
| D4 | Dark-theme value for every new token | both | DONE | `test_t34_light_and_dark_tokens_and_fixed_dark_surface`. 390/1280 dark shells |
| D5 | Type: Fraunces / Source Sans 3; caps label | both | DONE | Google fonts in `base.html`. `--pg-font-display/ui`, `--pg-label-size: 10.5px` |
| D6 | Radii scale | both | DONE | sheet 22 / card 16 / row 14 / button 12 / chip 999. Logo tile radius 9 |
| D7 | Shadows | both | DONE | `--pg-shadow-press/sheet/dialog/menu` |
| D8 | Buttons: primary, outline, teal, disabled, destructive | both | DONE | `.pg-btn`, `--outline/--teal/--destructive`, `:disabled` |
| D9 | Cards, emphasised card, dashed saved card | both | DONE | `.LawCard--emphasised`, `.pg-card--saved`. NDPS “Up next” card in shells |
| D10 | Chips and badges | both | DONE | `.pg-chip`, `--verbatim/--teal`. Law page VERBATIM chip |
| D12 | Bottom sheet (grabber, scrim, rise) | phone | DONE | `.pg-sheet-panel::before`, `pg-sheet-rise`. `r1_sheet_390_light.png` |
| D13 | Centred dialog (460px) | desktop | DONE | `max-width: 460px`, `.pg-sheet::backdrop`. `r1_dialog_1280_light.png` |
| D14 | Form fields and 2px focus ring | both | DONE | `.pg-field`, `--pg-focus-ring: 2px solid` |
| D15 | Progress visuals: ring, bar, waffle, rungs, capacity | both | DONE | `.pg-progress-ring/bar`, `.pg-waffle`, `.pg-rung`, `.RosterCapacity` on home |
| D16 | Motion; all collapse under reduced motion | both | DONE | `@keyframes pg-*`; `prefers-reduced-motion` + `html:not(.rtc-anim)`. 390 reduced byte-identical to light on this static page |
| D17 | Tap targets ≥44px; safe-area insets | phone | DONE | `--pg-tap: 44px`; `env(safe-area-inset-bottom)` on shell and sticky CTA |
| D18 | Header: logo tile, centred tabs | desktop | DONE | 30×30 radius-9 tile; 3-column grid from 900px; flex below 900. `r1_shell_768/1024/1280_light.png` |
| D19 | Account button and menu | desktop | DONE | Account sibling of Primary nav. `r1_shell_1280_account.png` (Profile, Settings, Calendar, Sign out) |
| D20 | 5-tab bottom bar | phone | DONE | Today/Browse/Playground/Calendar/Profile. Teal active only under `data-mscreen="playground"` |
| D21 | Tab bar hidden on focused screens | phone | DONE | `body[data-mscreen="playground"]:has(.pg-learn/.pg-complete/.pg-surface--fixed-dark)`. `test_t39`, `test_d21`. Learn-screen visual is R4 |
| D24 | Back links | both | DONE | `.pg-back` “← Playground” on select; “← My Playground” on law (`D132` copy stays until R4) |
| D25 | Page widths at 390 / 561–899 / 900–1039 / 1040+ / 1280 | both | DONE | Queries 561/900/1040/1280. Shells at 390, 768, 900, 1024, 1040, 1280. Aside from 900 |
| T33 | Asset version bumps and test pins | N/A | DONE | `styles.css?v=main74`, `mobile.css?v=mob94`, `playground.css?v=pg8`, `playground.js?v=pg6`. Pins in `test_playground_r1`, `test_settings_phone`, `test_web_sprint30` |
| T34 | Dark values; fixed-dark completion surface | N/A | DONE | Every listed token in both theme blocks + `.pg-surface--fixed-dark` |
| T35 | Negative grep for must-not-ship strings (X1–X8) | N/A | DONE | `test_t35_must_not_ship_strings_absent_from_runtime_assets` on templates/static only (docs/prototypes excluded) |
| T38 | Sheet/dialog enhancement; focus trap; fallback | N/A | DONE | `enhanceSheets`: `lastOpener`, Escape, Tab trap, `showModal`, `role=dialog`, no-JS `window.location.href` fallback |
| T39 | Tab-bar hide rules and sticky-footer offset | N/A | DONE | Hide scoped to playground mscreen. `.pg-sticky-cta` offset uses `--m-tabbar` |
| T41 | Route/template inventory; no unclassified template | N/A | DONE | **80 active templates, 0 unclassified.** `test_t41_every_active_template_is_classified`. Inventory §2.5 names class-C in backticks |

---

## U2 — Bare Act + Add + clause-level selection (weight 18, 39 items)

R2 + R3. Clause UI must not ship in R1.

| ID | Requirement | D/M | Status |
|---|---|---|---|
| D11 | Checkbox: none / all / some | both | NOT STARTED |
| D23 | Sticky footers sit above the tab bar | phone | NOT STARTED |
| D27 | CTA labels: guest, free, expired/paused, add, full, pending | both | NOT STARTED |
| D28 | “Already in Playground” banner | both | NOT STARTED |
| D29 | Desktop head: title left, 380px CTA column | desktop | NOT STARTED |
| D31 | Add container: sheet / dialog | both | NOT STARTED |
| D32 | Confirm step: space use, remaining, plurals | both | NOT STARTED |
| D33 | Max skips confirm | both | NOT STARTED |
| D34 | Scope step: Entire Act / Choose sections | both | NOT STARTED |
| D35 | Guest add variant | both | NOT STARTED |
| D36 | Subscribe / resume variant with catalogue “from ₹” | both | NOT STARTED |
| D37 | Roster-full variant with upgrade buttons | both | NOT STARTED |
| D38 | Pending-payment variant | both | NOT STARTED |
| D39 | Re-add variant (“No extra space used”) | both | NOT STARTED |
| D40 | Focus trap, Escape, scrim, no-JS fallback | both | NOT STARTED |
| D41 | Picker header copy | both | NOT STARTED |
| D42 | Chapter bands; none for chapterless Acts | both | NOT STARTED |
| D43 | Section row: checkbox, SECTION n, title | both | NOT STARTED |
| D44 | Status line, five states | both | NOT STARTED |
| D45 | Caret expands clause rows | both | NOT STARTED |
| D46 | Tri-state section checkbox | both | NOT STARTED |
| D47 | Omitted / unlearnable rows disabled | both | NOT STARTED |
| D48 | Sticky footer count / “clauses partial” | phone | NOT STARTED |
| D49 | Sticky SELECTION aside | desktop | NOT STARTED |
| D50 | Disabled at zero selection | both | NOT STARTED |
| D128 | Picker lede copy replacement | both | NOT STARTED |
| D129 | Picker button copy replacement | both | NOT STARTED |
| T5 | Chapterless Acts in picker, workspace, progress | N/A | IN PROGRESS |
| T8 | Locator grammar; `SectionLocator` / `UnitLocator`; explicit `ordinal` | N/A | NOT STARTED |
| T9 | `playground/units.py` | N/A | NOT STARTED |
| T10 | Unit hash and unit-level source review | N/A | NOT STARTED |
| T11 | Exclusivity, promotion, dormant progress | N/A | NOT STARTED |
| T12 | Due/schedule join current selection | N/A | NOT STARTED |
| T13 | Computed `unit_count`; “provisions” wording | N/A | NOT STARTED |
| T14 | Clause learn routes; `learn_path_for_locator` | N/A | NOT STARTED |
| T15 | Picker POST `section=` / `unit=`; no-JS | N/A | NOT STARTED |
| T16 | Per-section status line view model | N/A | NOT STARTED |
| T17 | Scope step after confirm; Max skips confirm | N/A | NOT STARTED |
| T18 | Act-head / add-sheet state model | N/A | NOT STARTED |

`_LOCATOR_RE` still uses greedy `.+` for section number (`locators.py:19`). `parse_locator` returns only `SectionLocator`. Confirmed T8 defect.

---

## U3 — Home + gates + roster lifecycle (weight 12, 38 items)

R3 + R5.

| ID | Requirement | D/M | Status |
|---|---|---|---|
| D22 | Primary tabs hidden on hard-gate pages | both | NOT STARTED |
| D51 | Home header copy (phone/desktop) | both | NOT STARTED |
| D52 | Month strip; Manage; Add a law | phone | NOT STARTED |
| D53 | Law card: segmented bar, single CTA | phone | NOT STARTED |
| D54 | Law card: Up next, chips, three buttons | desktop | NOT STARTED |
| D55 | “Law updated” chip | both | NOT STARTED |
| D56 | Summary tiles | desktop | NOT STARTED |
| D57 | Removed this month / Saved progress | both | NOT STARTED |
| D58 | Capacity aside | desktop | NOT STARTED |
| D59 | Plan next month card | both | NOT STARTED |
| D60 | Empty state | both | NOT STARTED |
| D61 | Paused banner; Resume CTAs | both | NOT STARTED |
| D62 | Banners: pending, cancel, upgrade, downgrade, welcome | both | NOT STARTED |
| D63 | Verbatim trust mark | both | NOT STARTED |
| D93 | Roster manager chrome | both | NOT STARTED |
| D94 | Active / removed rows | both | NOT STARTED |
| D95 | Remove dialog/sheet | both | NOT STARTED |
| D96 | Add-law dialog with meter | both | NOT STARTED |
| D97 | Rollover title, lede, key | both | NOT STARTED |
| D98 | Rollover rows / radiogroup | both | NOT STARTED |
| D99 | Rollover aside / sticky footer | both | NOT STARTED |
| D100 | Downgrade and blocked banners | both | NOT STARTED |
| D101 | Guest sign-in gate | both | NOT STARTED |
| D102 | Gate per reason | both | NOT STARTED |
| D103 | Saved-progress tiles on hard gates | both | NOT STARTED |
| D104 | Plans stage | both | NOT STARTED |
| D105 | Plan footnotes | both | NOT STARTED |
| D106 | “Included with your account” card | both | NOT STARTED |
| D125 | Home H1 copy | both | NOT STARTED |
| D126 | Home lede removed | both | NOT STARTED |
| D127 | Card links → single Learn CTA (phone) | phone | NOT STARTED |
| D130 | Rollover button copy | both | NOT STARTED |
| D131 | Not-subscribed gate title | both | NOT STARTED |
| D140 | Playground unavailable / service error | both | NOT STARTED |
| D142 | HTML 404/403/500 / kill-switch 404 | both | NOT STARTED |
| T19 | Paused/expired read-only home; learn blocked | N/A | NOT STARTED |
| T20 | Guest HTML GET → gate; JSON 401 | N/A | NOT STARTED |
| T21 | Plans stage from catalogue | N/A | NOT STARTED |

Production today: guest 303 (`test_playground_m6.py:115` and `:422`). Paused is EntitlementGate (`:420` family), not read-only home.

---

## U4 — Act progress + Learn + speech (weight 18, 28 items)

R4.

| ID | Requirement | D/M | Status |
|---|---|---|---|
| D64 | Act progress head | both | NOT STARTED |
| D65 | Progress ring | both | NOT STARTED |
| D66 | “Next” chip | both | NOT STARTED |
| D67 | Waffle of selected provisions | both | NOT STARTED |
| D68 | Ladder histogram | both | NOT STARTED |
| D69 | Primary Learn CTA; Manage sections | both | NOT STARTED |
| D70 | Up next learning prompt | desktop | NOT STARTED |
| D71 | Verbatim box show/hide | desktop | NOT STARTED |
| D72 | Sections list | desktop | NOT STARTED |
| D74 | Empty: no sections selected | both | NOT STARTED |
| D75 | Learn top bar / step bar | both | NOT STARTED |
| D76 | Eyebrow; VERBATIM BARE ACT chip | both | NOT STARTED |
| D77 | Per-mode task heading | both | NOT STARTED |
| D78 | Advance labels; methods left; Mark it Done | both | NOT STARTED |
| D79 | Read | both | NOT STARTED |
| D80 | Cloze | both | NOT STARTED |
| D81 | Letters + speech controls | both | NOT STARTED |
| D82 | Type | both | NOT STARTED |
| D83 | Recite | both | NOT STARTED |
| D84 | Test | both | NOT STARTED |
| D85 | Clause unit: lead-in as context | both | NOT STARTED |
| D87 | Focused column / deck+panel | both | NOT STARTED |
| D132 | Law page back copy | both | NOT STARTED |
| D139 | Learn failure states | both | NOT STARTED |
| D141 | Speech unavailable → typed path | both | NOT STARTED |
| T22 | Aggregates: rungs, next-up, scope | N/A | NOT STARTED |
| T23 | Modes-seen drives step bar | N/A | NOT STARTED |
| T25 | Playground speech route; `window.RecallSpeech` | N/A | NOT STARTED |

Production: `playground-learn.js` reads `window.SpeechClient` (never global). Constitution client uses `window.RecallSpeech` (`speech_client.js`). Speech HTTP is `POST /learn/{unit_id}/speech/transcribe` (Constitution `unit_id`). Confirmed T25.

---

## U5 — Learned, revision, mastery, amendments (weight 8, 12 items)

R4.

| ID | Requirement | D/M | Status |
|---|---|---|---|
| D73 | Source-update panel (three variants) | both | NOT STARTED |
| D86 | Revision variant + source-outdated line | both | NOT STARTED |
| D88 | “Section learned.” screen | both | NOT STARTED |
| D89 | Learned count line | both | NOT STARTED |
| D90 | “Mastered, verbatim.” | both | NOT STARTED |
| D91 | “The whole Act. By heart.” | both | NOT STARTED |
| D92 | Fixed dark surface both themes | both | NOT STARTED |
| D133 | Source review list | both | NOT STARTED |
| D134 | Section review page | both | NOT STARTED |
| D135 | Missing / omitted variants | both | NOT STARTED |
| D136 | Mastered or Learned **and** Law updated | both | NOT STARTED |
| T24 | Completion routes; real aggregates only | N/A | NOT STARTED |

---

## U6 — Today + Calendar + Google (weight 10, 15 items)

R6.

| ID | Requirement | D/M | Status |
|---|---|---|---|
| D115 | Today: Playground nodes in the path | both | NOT STARTED |
| D116 | Today: current-node card | both | NOT STARTED |
| D117 | Today: “New” Playground node | both | NOT STARTED |
| D118 | Today: gear opens Settings | phone | NOT STARTED |
| D119 | Today: two-column recall + path | desktop | NOT STARTED |
| D120 | Calendar cites clauses; “· Playground” | both | NOT STARTED |
| D121 | Calendar footnote about Google | phone | NOT STARTED |
| D122 | Month / Week switch | desktop | NOT STARTED |
| D123 | Week grid, six card states with text | desktop | NOT STARTED |
| D124 | Week: empty day, today ring, tap-through | desktop | NOT STARTED |
| T28 | Today path merge; New rule; `due_count` excludes New | N/A | NOT STARTED |
| T29 | Week view model and route | N/A | NOT STARTED |
| T30 | Clause citations in calendar | N/A | NOT STARTED |
| T31 | Google projection pending Playground rung | N/A | NOT STARTED |
| T32 | Narrow missing-schema guards | N/A | NOT STARTED |

`/calendar?view=week` does not exist on this SHA.

---

## U7 — Profile + Settings + account (weight 7, 12 items)

R5.

| ID | Requirement | D/M | Status |
|---|---|---|---|
| D107 | Identity card | both | NOT STARTED |
| D108 | SUBSCRIPTION card | both | NOT STARTED |
| D109 | Devices n of limit; Learning preferences | both | NOT STARTED |
| D110 | Guest profile card | both | NOT STARTED |
| D111 | Settings phone layout | phone | NOT STARTED |
| D112 | Settings phone Reminders row | phone | NOT STARTED |
| D113 | Settings controls keep shipped styling | both | NOT STARTED |
| D114 | First-connect reminder sheet/dialog | both | NOT STARTED |
| D137 | Devices page | both | NOT STARTED |
| D138 | Subscription checkout page | both | NOT STARTED |
| T26 | Subscription card + device count view models | N/A | NOT STARTED |
| T27 | Reminders row posts `reminder_cadence` | N/A | NOT STARTED |

---

## U8 — Closeout (weight 10, 25 items)

R7.

| ID | Requirement | D/M | Status |
|---|---|---|---|
| T40 | Planned test rewrites with reasons | N/A | NOT STARTED |
| V1 | Every screen/state at 390×844 | both | NOT STARTED |
| V2 | ~768 | both | NOT STARTED |
| V3 | ~1024 | both | NOT STARTED |
| V4 | 1280+ | both | NOT STARTED |
| V5 | Light theme | both | NOT STARTED |
| V6 | Dark theme | both | NOT STARTED |
| V7 | Reduced motion | both | NOT STARTED |
| V8 | Keyboard traversal | both | NOT STARTED |
| V9 | Visible focus | both | NOT STARTED |
| V10 | ARIA dialog / radiogroup / tri-state | both | NOT STARTED |
| V11 | 44px targets and safe areas | phone | NOT STARTED |
| V12 | Status never colour alone | both | NOT STARTED |
| V13 | Contrast light and dark | both | NOT STARTED |
| V14 | Semantic link vs button | both | NOT STARTED |
| V15 | Every D row matched / deviation / n/a | both | NOT STARTED |
| V16 | Regression: subscriptions, devices, roster | N/A | NOT STARTED |
| V17 | Regression: six modes, ladder, source review | N/A | NOT STARTED |
| V18 | Regression: SEO, public laws, Constitution, admin | N/A | NOT STARTED |
| V19 | Full suite green | N/A | NOT STARTED |
| V20 | CI green | N/A | NOT STARTED |
| V21 | Desktop visual sign-off | desktop | NOT STARTED |
| V22 | Mobile visual sign-off | phone | NOT STARTED |
| V23 | Every class-B surface vs design system | both | NOT STARTED |
| V24 | Zero unclassified routes; exclusions documented | N/A | NOT STARTED |

Known rewrites (T40 seed; not yet executed): `test_playground_m6.py:115,422` guest 303 → gate; `:420` paused gate → read-only home; `test_playground_m8.py` “Law revisions” → path nodes; Act loops gain `uapa`, `pss`, `mtp`.

---

## Must not ship (T35 / X1–X8)

Not extra score rows.

| ID | Item | Status |
|---|---|---|
| X1 | Core/Deep/Infinite; ₹149/₹299/₹499; fixed prototype dates | DONE (T35 runtime grep) |
| X2 | “offical”; unsupported Gazette provenance | DONE (T35 `offical`) |
| X3 | Plural bugs | DONE (T35 `1 spaces remaining`) |
| X4 | Unreachable gcal states; contradictory demo data | DONE for greppable demo copy; gcal state machine remains R6 (T31/T32) |
| X5 | “Devices 2 of 3”; free-tier copy contradictions | DONE (T35) |
| X6 | Streak chip; Study archive; filled Settings badges | DONE (T35) |
| X7 | Prototype gating holes | DONE for prototype runtime (`DCLogic`/`sc-if`/`support.js` banned in templates); entitlement holes remain T18/T20 |
| X8 | Hard-coded scope labels, names, dates, percentages | DONE (T35 `36% learned`, `geodesic-dome`) |

---

## Layer 2 review (before R0)

Every T1–T41 row was read against current `a5edca5` production code. **Accepted to start R0 merge/safety work.** Notes:

| T | Review |
|---|---|
| T1 | **Landed on `a17134d`.** Five content conflicts unchanged in identity. Extra files auto-merged. `/seen` took main’s pipelined preload. |
| T2 | Stop condition **did not fire** on merge. Snapshot fixture + tests now pin hashes. |
| T3 | Title-annotation mutation does not change `source_hash`. Picker/cards use plain titles. |
| T4 | **Landed with the merge.** Eligible six current slugs; `pota` and `uapa-1967` rejected. Hub keyed by slug. |
| T5 | MTP picker is chapterless (`data-chapterless`). Full D42 chapter-band picker remains R2. |
| T6 | Merge regenerated the sitemap over seven Acts. Noindex contract unchanged. |
| T7 | Template deleted; CSRF-less cloze binder removed; `complete_cloze()` kept. |
| T8–T16 | `units.py` absent. Locator greedy `.+` confirmed. No clause routes. |
| T17–T21 | Add is confirm-only (no scope step). Guest 303. Paused = hard gate. |
| T22–T25 | No completion screens. Speech is Constitution-scoped. `SpeechClient` vs `RecallSpeech` confirmed. |
| T26–T27 | Profile has no SUBSCRIPTION card from entitlement snapshot as specified. |
| T28–T32 | No week view. Today is Constitution-path. |
| T33–T41 | `playground.css` tokens + phone rules exist. T33 pins `main74` / `mob94` / `pg8` / `pg6`. T35 greps runtime only. T41 **80/0**. |

No missing technical dependency was found that is not already a T row. Auto-merge review is folded into T1, not a new T42.

---

## Blockers (product / source)

| ID | Blocker | Blocks | Decision needed |
|---|---|---|---|
| B1 | Named prototype files | ~~blocked R1~~ | **Resolved** on `58a1a26`. Both files present at the plan paths. |
| B2 | T2 hash-drift is an R0 **stop condition**, not a maybe | R1+ if hashes change without a statutory change | Snapshot fixture now exists. A failing snapshot test is a stop, not a later investigation. |

No new product delta (class D) was found. Deltas A–H already cover guest gate, paused home, eligibility, clause selection, Today, week view, speech, and Google.

---

## R1 closeout

**U1 is complete (28/28).** Shared design system and shells shipped. No R2 work.

Starting SHA `343b090`. Implementation commits: `24b2729`, `5f4a63c`, `d81d36f`, `cd1c4c6`. Tracker closeout: `cf41baf`.

Local `pytest -m "not integration"`: **2742 passed, 9 skipped, 1 deselected**.

Focused: `tests/test_playground_r1.py`, `tests/test_mobile_screens.py`, `tests/test_settings_phone.py`, `tests/test_web_sprint30.py`, `tests/test_playground_m6.py`, `tests/test_playground_m7.py`, `tests/test_guest_first_ux.py` — 223 passed before the full suite.

No new B/C denominator rows. No class-D product-scope stop. Do not start R2.

## R0 readiness

**U0 is complete (10/10).** **U1 is complete (28/28).** Stage 2 remains PARKED. Do not start R2.
