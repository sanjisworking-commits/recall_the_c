# Playground UI Redesign + Product Delta — Tracker

**Not the Stage 1 scoreboard.** Do not edit `docs/PLAYGROUND_DELIVERY_TRACKER.md`.

```text
Stage 1               = DONE — 100.0 / 100   (frozen)
UI Redesign Programme = 100.0 / 100
Stage 2               = PARKED until a later instruction starts S2-0
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
| **R1 closeout HEAD** | **`cf41baf`** (tracker) · last code **`cd1c4c6`**. U1 28/28. Frozen. |
| **R2 closeout HEAD** | **`d8a1c38`** (tracker) · last code **`1cc00b6`**. U2 24/39. Closed. |
| **R2 correction** | **`f62bd63`** (code). Fail-closed picker POST + bound `UnitLocator`. Programme still **28.1 / 100**. |
| **R3 closeout HEAD** | **`54b5af9`** (award) · CI-green **`4cbb443`**. Score was **provisional**. |
| **R3 post-closeout correction** | Review `86d8e56`. Code `5c3f003` (peek_capacity) + `6194e5b` (D142 theme). U2 **39/39**, U3 **29/38**, programme **44.2 / 100** restored after local+CI. |
| **R4 closeout HEAD** | Implementation `951c349`. Hidden/D92 `4d70c9e`. Tracker `78240b2`. Pin `b57a551`. D141 `5c98d83` / `ceaa0bb` / `286c98c`. Correction pin `42c0cd3`. U4 **28/28**, U5 **13/13**, programme **70.2 / 100**. Frozen. |
| **R5 closeout HEAD** | Implementation `b17d6ab`. Cycle `68d5c2d`. Rollover Done `d034024`. Paint/pg16 `a894a36`. D110 noindex `c35f7d5`. Tracker `b4ac8d1`. Pin `d9039a3`. |
| **R5 post-closeout correction** | Review `d9039a3`. Code `ec32195`. D130 CTA pin `d13c80c`. Tracker `cd78e25`. U3 **38/38**, U7 **12/12**, programme **80.0 / 100** restored after local+CI. R6 not started. |
| **R6 closeout HEAD** | Implementation `0011124`. extra_loader pin `1860dab`. Tracker `34db64f`. Pin `495d5ee`. |
| **R6 post-closeout correction** | Starting SHA `495d5ee`. Code `46f7a9d`. Closeout docs `35d4dd1`. Pin `81548eb`. |
| **R6 T28 minutes correction** | Starting SHA `81548eb`. Code `14179a1`. Closeout docs `c445dad`. T28 **DONE** again. D122 stayed DONE. U6 **15/15**, programme **90.0 / 100** after local+CI. R7 not started. |
| **R7 closeout HEAD** | Starting SHA `56065c2`. Implementation `fc0ca67`. Closeout docs `a2fdde7`. U8 **25/25**, programme **100.0 / 100** after local+CI+Railway. PR 188 stays draft. Stage 2 stays PARKED. |

Visual columns (390 light/dark, ~768, ~1024, 1280 light/dark, reduced motion) stay `—` until the relevant batch. Technical rows mark Desktop/Mobile **N/A**. Status uses only: `NOT STARTED | IN PROGRESS | BLOCKED | DONE | DONE`.

---

## Scoreboard

| Milestone | Scope | Weight | Batches | Items | Proven | Score |
|---|---|---|---|---|---|---|
| U0 | Source reconciliation + merge safety | 5 | R0 | 10 | 10 | 5.0 |
| U1 | Shared design system + shells | 12 | R1 | 28 | 28 | 12.0 |
| U2 | Bare Act + Add + clause-level selection | 18 | R2, R3 | 39 | 39 | 18.0 |
| U3 | Home + gates + roster lifecycle | 12 | R3, R5 | 38 | 38 | 12.0 |
| U4 | Act progress + six-mode Learn + speech | 18 | R4 | 28 | 28 | 18.0 |
| U5 | Learned / mastery / amendment states | 8 | R4 | 13 | 13 | 8.0 |
| U6 | Today + Calendar + Google Calendar | 10 | R6 | 15 | 15 | 10.0 |
| U7 | Profile + Settings + account surfaces | 7 | R5 | 12 | 12 | 7.0 |
| U8 | Responsive, a11y, parity, regression | 10 | R7 | 25 | 25 | 10.0 |
| **Total** | | **100** | | **208** | **208** | **100.0 / 100** |

Uniqueness (script-checked from §15.2; no row in two milestones, none omitted):

- D1–D142: 142
- T1–T42: 42
- V1–V24: 24
- **208**
- X1–X8 are enforced by **T35**, not extra denominator rows.

T42 is the approved R4 locator-aware source-review twin (U5). It is not the rejected auto-merge T42 from the R0 notes. No other B/C rows were added during R4.

---

## Product deltas A–H

| Id | Delta | Layer 2 | Status |
|---|---|---|---|
| A | Clause-level selection | T8–T16, T30 | DONE — T8–T16 (R2); T30 (R6) |
| B | Playground pending rung → Google Calendar | T31 | DONE |
| C | Selected unlearned work in Today | T28 | DONE |
| D | Desktop Calendar Week | T29 | DONE |
| E | Real speech on Letters/Recite | T25 | DONE |
| F | Eligible Acts NDPS, BNS, BNSS, UAPA, PSS, MTP; POTA readable; slug identity | T4, T5 | DONE |
| G | Paused/expired read-only home | T19 | DONE |
| H | Guest HTML GET renders gate; JSON 401 | T20 | DONE |

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

R2 (clause model + picker) is closed on `1cc00b6`. R3 (Add sheet/dialog) is closed on `3a8dcd0` / CI `4cbb443`. U2 is **39 / 39**. Do not start R4 or R5.

| ID | Requirement | D/M | Status | Evidence |
|---|---|---|---|---|
| D11 | Checkbox: none / all / some | both | DONE | `.pg-pick-check` + `aria-checked` true/false/mixed; dash mark for mixed. `test_picker_markup_tri_state_chapterless_and_copy`. `r2_picker_390_mixed.png` |
| D23 | Sticky footers sit above the tab bar | phone | DONE | Picker footer is `.pg-sticky-cta.pg-pick-footer`. R1 `mobile.css` offsets `body[data-mscreen="playground"] .pg-sticky-cta` by `--m-tabbar` + safe-area. Five-tab HTML remains signed-in multiuser (R1 D20). `r2_picker_390_light.png` |
| D27 | CTA labels: guest, free, expired/paused, add, full, pending | both | DONE | T18 `data-pg-kind`. `test_t18_act_head_kinds` |
| D28 | “Already in Playground” banner | both | DONE | Badge + Sections / Start learning or Continue. `test_t18_act_head_kinds`. `r3_act_head_already_in_playground_390.webp` |
| D29 | Desktop head: title left, 380px CTA column | desktop | DONE | `.bareact-head` `minmax(0, 1fr) 380px` from 1024px. `test_d22_d29_d40_assets` |
| D31 | Add container: sheet / dialog | both | DONE | `playground_add.html` `role="dialog"` + R1 sheet/dialog. `test_d22_d29_d40_assets` |
| D32 | Confirm step: space use, remaining, plurals | both | DONE | `add_confirm_copy`. Confirm POST without scope does not consume. `test_t17_confirm_without_scope_shows_scope_and_does_not_consume` |
| D33 | Max skips confirm | both | DONE | `skips_add_confirm` when `playground_law_limit is None` (Max / local / admin). `test_t17_max_skips_confirm_and_opens_on_scope` |
| D34 | Scope step: Entire Act / Choose sections | both | DONE | `scope=entire` / `scope=sections`. `r3_add_scope_entire_or_sections.webp` |
| D35 | Guest add variant | both | DONE | Kind `guest`, `next` preserved. `test_d35_guest_add_sheet_preserves_next` |
| D36 | Subscribe / resume variant with catalogue “from ₹” | both | DONE | Kind `subscribe` / `resume`. `catalogue_from_price`. `test_t18_act_head_kinds` `test_t21_subscribe_gate_plans_come_from_catalogue` |
| D37 | Roster-full variant with upgrade buttons | both | DONE | Kind `roster_full`. Catalogue upgrade CTAs + Plan next month. `test_t18_act_head_kinds` |
| D38 | Pending-payment variant | both | DONE | Kind `pending`. `test_t18_act_head_kinds` |
| D39 | Re-add variant (“No extra space used”) | both | DONE | Kind `re_add`. `test_re_add_uses_no_extra_space` |
| D40 | Focus trap, Escape, scrim, no-JS fallback | both | DONE | `enhanceAddFlow` + R1 `enhanceSheets`. No-JS forms POST confirm then scope |
| D41 | Picker header copy | both | DONE | Back `← {{ act.short_name }}`, h1 “Choose what to learn”. `r2_picker_390_light.png` |
| D42 | Chapter bands; none for chapterless Acts | both | DONE | `picker_page_view` `chapterless = not act.chapters`. MTP `data-chapterless`, no CHAPTER. `r2_picker_mtp_390_chapterless.png` |
| D43 | Section row: checkbox, SECTION n, title | both | DONE | `list_title` (omitted → “Omitted”, no `[` markers). `test_picker_markup` |
| D44 | Status line, five states | both | DONE | `picker_status_line` + dormant progress. Learning / Due / Learned / Mastered / Not started. `test_picker_status_line_uses_real_progress_including_dormant`. `r2_picker_1024_aside.png` |
| D45 | Caret expands clause rows | both | DONE | `<details>` + `aria-expanded`. Only when `enumerate_selectable_units` ≥ 2. `r2_picker_390_mixed.png` |
| D46 | Tri-state section checkbox | both | DONE | none/some/all; mixed uses dash + `aria-checked="mixed"`, not colour alone. JS `indeterminate`. |
| D47 | Omitted / unlearnable rows disabled | both | DONE | `disabled` + POST HTTP 400 (no skip/wipe). `test_nojs_section_and_unit_post_and_omitted_rejection`. Unlearnable-but-non-omitted: no eligible-corpus example; synthetic service fixture. `r2_picker_390_omitted.webp` |
| D48 | Sticky footer count / “clauses partial” | phone | DONE | `provisions_label` + `picker_cta_copy`. Hidden ≥900px. `r2_picker_390_light.png` |
| D49 | Sticky SELECTION aside | desktop | DONE | Shown ≥900px from real selection. `r2_picker_1024_aside.png` `r2_picker_1280_light.png` |
| D50 | Disabled at zero selection | both | DONE | JS disables CTA (`Select sections to add`). No-JS submit still server-authoritative so empty HTML is not `disabled` (would brick no-JS ticks). `r2_picker_390_zero_selection.webp` |
| D128 | Picker lede copy replacement | both | DONE | “Whole sections, or open one and pick clauses.” Stage 1 lede gone. `test_picker_markup` |
| D129 | Picker button copy replacement | both | DONE | `Add N section(s) →` / `(N clause(s) partial)` / `Select sections to add`. `test_provisions_copy_and_cta_grammar` |
| T5 | Chapterless Acts in picker, workspace, progress | N/A | DONE | Generic `chapters == none`. MTP picker/workspace. `test_picker_markup_tri_state_chapterless_and_copy` |
| T8 | Locator grammar; `SectionLocator` / `UnitLocator`; explicit `ordinal` | N/A | DONE | `playground/locators.py`. Bounded `[^:]+`. Malformed units rejected. `UnitLocator` requires eligible `law_id`. `section_unit_map` uses `UnitIdentity`. `test_unit_locator_cannot_exist_unbound` |
| T9 | `playground/units.py` | N/A | DONE | Single authority: enumerate, resolve, lead-in/tail, ordinals, citation, hashes |
| T10 | Unit hash and unit-level source review | N/A | DONE | SHA-256 of section number, `kind:label`, lead-in, unit text. `source_hash_for_locator` in `source_review._classify_locator` |
| T11 | Exclusivity, promotion, dormant progress | N/A | DONE | `normalize_selection_locators`. All units → section locator. Progress rows kept. `test_whole_section_unit_exclusivity_and_all_unit_promotion` `test_switch_preserves_dormant_progress_and_due_excludes_deselected` `test_all_unit_learning_is_not_whole_section_mastery` |
| T12 | Due/schedule join current selection | N/A | DONE | `progress_in_current_selection_sql` EXISTS join. `test_switch_preserves_dormant_progress_and_due_excludes_deselected` |
| T13 | Computed `unit_count`; “provisions” wording | N/A | DONE | SQL alias of `selected_count`. `provisions_label`. No migration |
| T14 | Clause learn routes; `learn_path_for_locator` | N/A | DONE | Parallel `/u/{unit}/learn/{mode}`. Existing section routes kept. `test_learn_path_for_locator_parallel_routes` `test_unit_learn_route_resolves` |
| T15 | Picker POST `section=` / `unit=`; no-JS | N/A | DONE | Fail-closed atomic POST. Invalid values → `SelectionRejected` / HTTP 400 `invalid_selection`; `before_selection == after_selection`. Empty POST still 303-clears. `entire=1` validates extras. `test_nojs_section_and_unit_post_and_omitted_rejection` `test_picker_post_rejects_invalid_payloads_without_mutation` `test_picker_post_valid_plus_invalid_applies_neither` `test_picker_post_entire_act_valid_and_invalid_extras` `test_picker_post_whitespace_absent_and_empty_clears`. Correction `f62bd63` |
| T16 | Per-section status line view model | N/A | DONE | `picker_page_view` / `picker_status_line`. Progress including dormant locators. `1cc00b6` |
| T17 | Scope step after confirm; Max skips confirm | N/A | DONE | Confirm without scope → 200 scope, no consume. Max `data-skip-confirm`. Entire Act recovery `persist_entire_act_selection`. `tests/test_playground_r3.py` |
| T18 | Act-head / add-sheet state model | N/A | DONE | Ten kinds. `view.py` KIND_*. `test_t18_act_head_kinds` |

---

## U3 — Home + gates + roster lifecycle (weight 12, 38 items)

R3 (home + gates) is closed. R5 (roster/rollover restyle) is closed. U3 is **38 / 38**.

| ID | Requirement | D/M | Status |
|---|---|---|---|
| D22 | Primary tabs hidden on hard-gate pages | both | DONE — `data-hard-gate="true"` hides `.PrimaryTabs--top` and `.mobile-tabbar`. Paused home does not set it. `test_d22_d29_d40_assets` |
| D51 | Home header copy (phone/desktop) | both | DONE — kicker “My Playground”, H1 “Playground”. `test_home_copy_provisions_and_empty_state` |
| D52 | Month strip; Manage; Add a law | phone | DONE — `.pg-month-strip`. `r3_home_phone_390.webp` |
| D53 | Law card: segmented bar, single CTA | phone | DONE — `law_card` phone actions. `r3_home_phone_390.webp` |
| D54 | Law card: Up next, chips, three buttons | desktop | DONE — emphasised next card; Continue / Read Bare Act / Manage. `r3_home_ndps_card_1280.webp` |
| D55 | “Law updated” chip | both | DONE — `status_badge('updated', 'Law updated')` when `card.outdated` |
| D56 | Summary tiles | desktop | DONE — Due today / To learn / Learned |
| D57 | Removed this month / Saved progress | both | DONE — home sections from roster + overlay |
| D58 | Capacity aside | desktop | DONE — `.pg-aside` capacity |
| D59 | Plan next month card | both | DONE — `.pg-plan-row` |
| D60 | Empty state | both | DONE — “Your September Playground is empty”. `test_home_copy_provisions_and_empty_state` |
| D61 | Paused banner; Resume CTAs | both | DONE — read-only home. `test_can_view_home_does_not_leak_learn_or_mutations` |
| D62 | Banners: pending, cancel, upgrade, downgrade, welcome | both | DONE — `payment_banners` |
| D63 | Verbatim trust mark | both | DONE — `trust_mark()` “Verbatim, always.” |
| D93 | Roster manager chrome | both | DONE — `RosterManager-head`, used/remaining, rules card. `test_d93_d94_roster_manager_chrome_and_rows`. `r5_roster_390_light.png` |
| D94 | Active / removed rows | both | DONE — Continue/Read/Remove; Add back + Progress saved. `test_d93_d94` `test_d95_remove_dialog_is_sheet` |
| D95 | Remove dialog/sheet | both | DONE — JS `dialog.pg-sheet` launched from roster Remove (`data-pg-sheet`). Phone `--pg-sheet-anchor: bottom` (390 dialog bottom = viewport). Desktop centred, max-width 460px. Direct URL still no-JS. `test_d95_remove_dialog_is_sheet` `test_d95_sheet_responsive_class_contract`. `r5corr_remove_sheet_390_light.png` |
| D96 | Add-law dialog with meter | both | DONE — RosterCapacity + “No extra space used.” `test_d96_add_law_dialog_has_meter_and_saved_line`. `r5_roster_add_1280_light.png` |
| D97 | Rollover title, lede, key | both | DONE — “Your {month} Playground”; Keep/Remove/Undecided key. `test_d97_d100_d130_rollover_key_states_and_copy` |
| D98 | Rollover rows / radiogroup | both | DONE — `role="radiogroup"` keep/decline/undecided. Stage 1 POST names unchanged |
| D99 | Rollover aside / sticky footer | both | DONE — phone sticky footer and desktop aside share D130’s single label. `.RolloverPlanner .pg-sticky-cta` hidden ≥900px. T39 hide tab bar |
| D100 | Downgrade and blocked banners | both | DONE — `rollover_adjustment_required`; `roster_full` / `active_slot_locked`. `test_d100_downgrade_banner` |
| D101 | Guest sign-in gate | both | DONE — HTML 200 “Sign in to use Playground”. `test_d35_guest_add_sheet_preserves_next` T20 |
| D102 | Gate per reason | both | DONE — `gate_view` per block reason. Halted/paused/expired also have read-only home (T19); Learn still gates |
| D103 | Saved-progress tiles on hard gates | both | DONE — `show_saved` on paused/halted/expired gates; home Saved progress when `can_view_home` |
| D104 | Plans stage | both | DONE — `.pg-plan-stage` from catalogue. `test_t21_subscribe_gate_plans_come_from_catalogue` |
| D105 | Plan footnotes | both | DONE — “Monthly. GST included.” + `from_price` |
| D106 | “Included with your account” card | both | DONE — `.pg-included-card` on unsubscribed gate |
| D125 | Home H1 copy | both | DONE — “Playground” |
| D126 | Home lede removed | both | DONE — no billing lede under H1. `test_home_copy_provisions_and_empty_state` |
| D127 | Card links → single Learn CTA (phone) | phone | DONE — `.pg-card-actions--phone` one button |
| D130 | Rollover button copy | both | DONE — one server-derived label. Any unresolved → “Continue with these”, no Done CTA. All Keep/Remove resolved → “Done”. `rollover_submit_label`. `test_d130_*`. `r5corr_rollover_undecided_1280_light.png` |
| D131 | Not-subscribed gate title | both | DONE — Act-head “Subscribe to use Playground”; gate “Unlock Playground” |
| D140 | Playground unavailable / service error | both | DONE — styled 503. Kill-switch styled 404. `test_d140_playground_service_error_is_styled_503` |
| D142 | HTML 404/403/500 / kill-switch 404 | both | DONE — atomic. Path middleware only. Theme boot + `--pg-page` on error shells (`pg11`). `test_d142_playground_html_404_403_500_without_global_handlers` `test_d142_error_html_resolves_theme_and_page_wash` |
| T19 | Paused/expired read-only home; learn blocked | N/A | DONE — `can_view_home` GET-home-only. `peek_capacity` / no `_attach_current_period` when `!can_open`. Persistence before/after in `test_paused_home_get_does_not_create_or_update_roster_period` |
| T20 | Guest HTML GET → gate; JSON 401 | N/A | DONE — 200 HTML; JSON 401; POST fail-closed |
| T21 | Plans stage from catalogue | N/A | DONE — Plus/Pro/Max ₹199/₹399/₹1199 |

Paused/halted/expired GET `/playground` is read-only home (T19). Guest HTML GET is the sign-in gate (T20). Learn/Add/Remove stay blocked when `can_open` is false.

---

## U4 — Act progress + Learn + speech (weight 18, 28 items)

R4. **28 / 28.** Report: [`PLAYGROUND_UI_REDESIGN_R4_REPORT.md`](PLAYGROUND_UI_REDESIGN_R4_REPORT.md).

| ID | Requirement | D/M | Status |
|---|---|---|---|
| D64 | Act progress head | both | DONE |
| D65 | Progress ring | both | DONE |
| D66 | “Next” chip | both | DONE |
| D67 | Waffle of selected provisions | both | DONE |
| D68 | Ladder histogram | both | DONE |
| D69 | Primary Learn CTA; Manage sections | both | DONE |
| D70 | Up next learning prompt | desktop | DONE |
| D71 | Verbatim box show/hide | desktop | DONE |
| D72 | Sections list | desktop | DONE |
| D74 | Empty: no sections selected | both | DONE |
| D75 | Learn top bar / step bar | both | DONE |
| D76 | Eyebrow; VERBATIM BARE ACT chip | both | DONE |
| D77 | Per-mode task heading | both | DONE |
| D78 | Advance labels; methods left; Mark it Done | both | DONE |
| D79 | Read | both | DONE |
| D80 | Cloze | both | DONE |
| D81 | Letters + speech controls | both | DONE |
| D82 | Type | both | DONE |
| D83 | Recite | both | DONE |
| D84 | Test | both | DONE |
| D85 | Clause unit: lead-in as context | both | DONE |
| D87 | Focused column / deck+panel | both | DONE |
| D132 | Law page back copy | both | DONE |
| D139 | Learn failure states | both | DONE |
| D141 | Speech unavailable → typed path | both | DONE — audio limiter; typed fallback after 429/503 |
| T22 | Aggregates: rungs, next-up, scope | N/A | DONE — monotonic completed_scope_count; Next identity matches Stage 1 |
| T23 | Modes-seen drives step bar | N/A | DONE — out-of-order complete preserved |
| T25 | Playground speech route; `window.RecallSpeech` | N/A | DONE — Playground POST twins; Recite map server-owned |

Playground Learn uses window.RecallSpeech.
Playground locator-aware speech POST is server-authoritative.
Constitution default speech URL remains unchanged.

---

## U5 — Learned, revision, mastery, amendments (weight 8, 13 items)

R4. **13 / 13.** T42 is the thirteenth item (locator-aware source-review GET/POST twins).

| ID | Requirement | D/M | Status |
|---|---|---|---|
| D73 | Source-update panel (three variants) | both | DONE |
| D86 | Revision variant + source-outdated line | both | DONE |
| D88 | “Section learned.” screen | both | DONE |
| D89 | Learned count line | both | DONE |
| D90 | “Mastered, verbatim.” | both | DONE |
| D91 | “The whole Act. By heart.” | both | DONE |
| D92 | Fixed dark surface both themes | both | DONE |
| D133 | Source review list | both | DONE |
| D134 | Section review page | both | DONE |
| D135 | Missing / omitted variants | both | DONE |
| D136 | Mastered or Learned **and** Law updated | both | DONE |
| T24 | Completion routes; real aggregates only | N/A | DONE — learned GET after initial 6/6; Day 1–30 stay Learn; Day 60 mastered GET; review stray → workspace |
| T42 | Locator-aware source-review GET/POST twins | N/A | DONE — PSS §38 (2) vs (2)~2 independent; missing-unit Learn redirects to unit review |

---

## U6 — Today + Calendar + Google (weight 10, 15 items)

R6 closed on `1860dab`. Report: [`PLAYGROUND_UI_REDESIGN_R6_REPORT.md`](PLAYGROUND_UI_REDESIGN_R6_REPORT.md). Post-closeout correction from `495d5ee` restored **T28** and **D122**.

| ID | Requirement | D/M | Status |
|---|---|---|---|
| D115 | Today: Playground nodes in the path | both | DONE |
| D116 | Today: current-node card | both | DONE |
| D117 | Today: “New” Playground node | both | DONE |
| D118 | Today: gear opens Settings | phone | DONE |
| D119 | Today: two-column recall + path | desktop | DONE |
| D120 | Calendar cites clauses; “· Playground” | both | DONE |
| D121 | Calendar footnote about Google | phone | DONE |
| D122 | Month / Week switch | desktop | DONE — week header uses `week.summary` after Playground chips; month keeps `calendar.summary` |
| D123 | Week grid, six card states with text | desktop | DONE |
| D124 | Week: empty day, today ring, tap-through | desktop | DONE |
| T28 | Today path merge; New rule; `due_count` excludes New | N/A | DONE — hero follows merged path; Playground current CTA is `current.href`; Constitution-only minutes hidden when a Playground revision is due |
| T29 | Week view model and route | N/A | DONE |
| T30 | Clause citations in calendar | N/A | DONE |
| T31 | Google projection pending Playground rung | N/A | DONE |
| T32 | Narrow missing-schema guards | N/A | DONE |

`/calendar?view=week&date=YYYY-MM-DD` ships on `1860dab`. Invalid ISO date is HTTP 400. Phone stays month.

---

## U7 — Profile + Settings + account (weight 7, 12 items)

R5. **12 / 12.** Report: [`PLAYGROUND_UI_REDESIGN_R5_REPORT.md`](PLAYGROUND_UI_REDESIGN_R5_REPORT.md).

| ID | Requirement | D/M | Status |
|---|---|---|---|
| D107 | Identity card | both | DONE — `data-profile-identity`; Guest / Google / phone meta. `test_d107_d109_profile_subscription_and_devices` |
| D108 | SUBSCRIPTION card | both | DONE — ACTIVE / PAUSED / ON HOLD / PENDING from `snapshot.subscription_status`. Cancel-at-end and scheduled-tier sentences while access stays current. Legacy duration-pass + Free Articles removed from active Profile. `test_d108_*` |
| D109 | Devices n of limit; Learning preferences | both | DONE — `device_count_copy`; “2 of 3” absent. `test_d107_d109_profile_subscription_and_devices` |
| D110 | Guest profile card | both | DONE — GET `/profile` HTML 200. `test_d110_guest_profile_card`. `r5_profile_guest_390_light.png` |
| D111 | Settings phone layout | phone | DONE — account card, STUDY / CALENDAR / APP / ACCOUNT. ACCOUNT is `settings-phone-only`. `test_d111_d113_settings_phone_groups_keep_controls` |
| D112 | Settings phone Reminders row | phone | DONE — `data-settings-reminders` posts `reminder_cadence`. `test_t27_d112_d114_reminders_row_and_first_connect_sheet` |
| D113 | Settings controls keep shipped styling | both | DONE — segmented, theme, verbatim, plan autosubmit unchanged. Desktop Settings keeps shipped chrome |
| D114 | First-connect reminder sheet/dialog | both | DONE — existing `data-gcal-reminder-modal` `role="dialog"` (`=`). `test_t27_d112_d114` |
| D137 | Devices page | both | DONE — count of limit, confirm, revoked list. `test_d137_d138_devices_and_checkout_markup` |
| D138 | Subscription checkout page | both | DONE — `pg-checkout-card`; Razorpay script only. No Razorpay at render. `test_d137_d138` |
| T26 | Subscription card + device count view models | N/A | DONE — snapshot chips including pending/cancel/scheduled; `DeviceService` counts; no device ids on Profile. `test_t26_subscription_card_chips_and_device_copy` `test_d108_t26_pending_profile_card` |
| T27 | Reminders row posts `reminder_cadence` | N/A | DONE — phone form → `/calendar/google/preferences`. `test_t27_d112_d114_reminders_row_and_first_connect_sheet` |

---

## U8 — Closeout (weight 10, 25 items)

R7. Batch report: [`docs/PLAYGROUND_UI_REDESIGN_R7_REPORT.md`](PLAYGROUND_UI_REDESIGN_R7_REPORT.md). Ledger: [`docs/PLAYGROUND_UI_REDESIGN_R7_LEDGER.md`](PLAYGROUND_UI_REDESIGN_R7_LEDGER.md). Finish handoff: [`docs/design/PLAYGROUND-FINISH-HANDOFF.md`](design/PLAYGROUND-FINISH-HANDOFF.md).

Score: `90 + 10 × proven_U8 / 25`. U8 25/25 → **10.0**. Programme **100.0 / 100** by that formula, not forced.

| ID | Requirement | D/M | Status |
|---|---|---|---|
| T40 | Planned test rewrites with reasons | N/A | DONE — ledger T40-1..3 already in R3/R5; T40-4 `test_playground_m8.py` Today path; T40-5 `test_pota_reader.py` eligible six. No assertion weakened merely to pass. Ran **before** V16/V17/V18 |
| V1 | Every screen/state at 390×844 | both | DONE — phone family matrix + HTTP inspect. Tab bar ≤560 |
| V2 | ~768 | both | DONE — 561–899 flex header, no tab bar, no week view. `r7_home_768_light.png` |
| V3 | ~1024 | both | DONE — 900–1039 collision pass. Week 7 columns + Act-head CTA. `r7_calendar_week_1024_light.png`, `r7_act_head_1024_reduced.png` |
| V4 | 1280+ | both | DONE — `r7_home_1280_light.png`, `r7_calendar_week_1280_light.png`, `r7_today_1280_light.png` |
| V5 | Light theme | both | DONE — 390/1024/1280 light shots |
| V6 | Dark theme | both | DONE — `r7_home_390_dark.png`, `r7_home_1280_dark.png`, `r7_legal_privacy_390_dark.png` |
| V7 | Reduced motion | both | DONE — `.panel` collapsed. `r7_home_390_reduced.png`, `r7_act_head_1024_reduced.png` |
| V8 | Keyboard traversal | both | DONE — tab through Settings; existing dialog/radiogroup contracts |
| V9 | Visible focus | both | DONE — global `:focus-visible` 2px `var(--ink)`. `r7_settings_focus_390_light.png` |
| V10 | ARIA dialog / radiogroup / tri-state | both | DONE — calendar + rollover radiogroup; picker `aria-checked`; existing dialogs |
| V11 | 44px targets and safe areas | phone | DONE — Settings `height: auto` + min 44 (D113 styling kept). Learn letters min 44. Not closed via `APPROVED DEVIATION` |
| V12 | Status never colour alone | both | DONE — week legend text + mark; LawStatusBadge text; D102 distinct titles |
| V13 | Contrast light and dark | both | DONE — no token failed contrast. Landing/auth keep shipped palettes |
| V14 | Semantic link vs button | both | DONE — no R7 IA change; existing href vs button usage held |
| V15 | Every D row matched / deviation / n/a | both | DONE — ledger. `APPROVED DEVIATION` is V15 only |
| V16 | Regression: subscriptions, devices, roster | N/A | DONE — after T40. Devices `1 of 2`. Roster HTTP 200 |
| V17 | Regression: six modes, ladder, source review | N/A | DONE — after T40-4. Source-review HTTP 200. M8 path contract current |
| V18 | Regression: SEO, public laws, Constitution, admin | N/A | DONE — guest 200 gate; `/learn/clause-1` 200; admin 404 for non-admin |
| V19 | Full suite green | N/A | DONE — `pytest -m "not integration"` on `fc0ca67`: **2888 passed**, 9 skipped, 1 deselected |
| V20 | CI green | N/A | DONE — CI push [37022804844](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/37022804844), PR [37022809702](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/37022809702), Railway success on `fc0ca67` |
| V21 | Desktop visual sign-off | desktop | DONE — 1024/1280 matrix. Week desktop-only |
| V22 | Mobile visual sign-off | phone | DONE — 390 + ~768. Tab bar only ≤560 |
| V23 | Every class-B surface vs design system | both | DONE — 45 templates inspected. D1–D17 reconciliation only. No new D row. B-landing/B-auth shipped palettes known at freeze |
| V24 | Zero unclassified routes; exclusions documented | N/A | DONE — 81 templates, 0 unclassified. Walk via `_IncludedRouter.original_router`. `/memory` flag-off 404 documented |

Known rewrites (executed): `test_playground_m8.py` “Law revisions” → path nodes; Act loops use `list_playground_eligible_laws()`. Paused hard-gate tests superseded by T19 read-only home (R3). Guest `/playground` 303 superseded by T20 (R3). Guest `/profile` 303 superseded by D110 (R5).

---

## Must not ship (T35 / X1–X8)

Not extra score rows.

| ID | Item | Status |
|---|---|---|
| X1 | Core/Deep/Infinite; ₹149/₹299/₹499; fixed prototype dates | DONE (T35 runtime grep) |
| X2 | “offical”; unsupported Gazette provenance | DONE (T35 `offical`) |
| X3 | Plural bugs | DONE (T35 `1 spaces remaining`) |
| X4 | Unreachable gcal states; contradictory demo data | DONE for greppable demo copy; gcal pending-rung machine closed in R6 (T31/T32) |
| X5 | “Devices 2 of 3”; free-tier copy contradictions | DONE (T35) |
| X6 | Streak chip; Study archive; filled Settings badges | DONE (T35) |
| X7 | Prototype gating holes | DONE for prototype runtime (`DCLogic`/`sc-if`/`support.js` banned in templates); T18/T20 guest+kind model DONE |
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
| T5 | **Closed in R2.** Generic `chapters == none`. MTP picker is chapterless; other Acts keep canonical bands. |
| T6 | Merge regenerated the sitemap over seven Acts. Noindex contract unchanged. |
| T7 | Template deleted; CSRF-less cloze binder removed; `complete_cloze()` kept. |
| T8–T16 | **Closed in R2** on `1cc00b6`. Discriminated locators, `units.py`, picker POST, due join, unit hash. |
| T17–T21 | **Closed in R3** on `3a8dcd0`. Confirm→scope, T18 kinds, paused read-only home, guest HTML 200 / JSON 401, catalogue plans. |
| T22–T25 | No completion screens. Speech is Constitution-scoped. `SpeechClient` vs `RecallSpeech` confirmed. |
| T26–T27 | **Closed in R5** (correction `d13c80c`). SUBSCRIPTION card from entitlement snapshot including PENDING / cancel-at-end / scheduled tier; device “n of limit” from the device service; phone Reminders posts `reminder_cadence`. |
| T28–T32 | **Closed in R6** on `1860dab`. Path merge + New rule; week view; clause chips; Google pending rung; T32 guards. **T28 restored** after the minutes-line correction from `81548eb` (`14179a1`). D122 stayed DONE. |
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

## R7 closeout

Batch report: [`docs/PLAYGROUND_UI_REDESIGN_R7_REPORT.md`](PLAYGROUND_UI_REDESIGN_R7_REPORT.md). Ledger: [`docs/PLAYGROUND_UI_REDESIGN_R7_LEDGER.md`](PLAYGROUND_UI_REDESIGN_R7_LEDGER.md).

**R7 is complete.** Responsive / a11y / parity closeout shipped. Programme **100.0 / 100** by `90 + 10 × 25 / 25`. That is not a forced 100. Stage 1 / R5 / R6 remain frozen. Stage 2 remains PARKED. PR 188 stays draft. Do not merge.

Starting SHA `56065c2`. Implementation `fc0ca67`. Closeout docs `a2fdde7`. T33 `styles.css?v=main76`, `mobile.css?v=mob97`, `playground.css?v=pg18`, `playground.js?v=pg8`.

U8 **25 / 25** → 10.0. Alembic head remains **`20260927_0027`**. No migration. No new B/C denominator rows. Stop log empty.

Approved order held: T40 execution before V16/V17/V18. `test_today_queue_current_roster_only` pins the T28 Today-path contract instead of `"Law revisions"`.

Local `pytest -m "not integration"` on `fc0ca67`: **2888 passed**, 9 skipped, 1 deselected. CI on `fc0ca67`: push [37022804844](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/37022804844) and PR [37022809702](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/37022809702) succeeded. Railway `trustworthy-embrace / recall_the_c-pr-188` success.

Do not start Stage 2 from this closeout.

---

## R6 closeout

Batch report: [`docs/PLAYGROUND_UI_REDESIGN_R6_REPORT.md`](PLAYGROUND_UI_REDESIGN_R6_REPORT.md).

**R6 is complete**, including the T28 minutes-line correction from `81548eb`. D122 was not reopened. Programme **90.0 / 100**. R7 is not started. Stage 1 remains frozen except the T33 pin (`styles.css?v=main75`, `mobile.css?v=mob96`, `playground.css?v=pg17`, `playground.js?v=pg8`). Stage 2 remains PARKED.

Starting SHA `ffe374d`. Implementation `0011124`. extra_loader / UUID pin `1860dab`. Tracker `34db64f`. Pin `495d5ee`. Correction starting SHA `495d5ee`. Correction code `46f7a9d`.

U6 **15 / 15** → 10.0. Deltas A (T30), B (T31), C (T28), D (T29) **DONE**. Alembic head remains **`20260927_0027`**. No migration.

Local `pytest -m "not integration"` on `46f7a9d`: **2876 passed**, 9 skipped, 1 deselected. Focused `tests/test_playground_r6.py` + `tests/test_calendar_week.py`: **28 passed**. Broader R6 + m8/r5/calendar/dashboard: **213 passed**. CI on `46f7a9d`: push [37002096012](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/37002096012) and PR [37002099960](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/37002099960) succeeded. Deployment status succeeded.

Do not start R7 from this closeout.

---

## R6 post-closeout correction

Full write-up: [`PLAYGROUND_UI_REDESIGN_R6_REPORT.md`](PLAYGROUND_UI_REDESIGN_R6_REPORT.md) § Post-closeout correction.

Temporary score until code, tests, visual proof, and CI: U6 **13/15**, programme **88.7 / 100**. Restored U6 **15/15**, programme **90.0 / 100** after that. Only T28 and D122 were reopened. Alembic stayed `20260927_0027`. PR 188 stayed draft. R7 was not started.

| | SHA |
|---|---|
| Starting | `495d5ee` |
| Implementation | `46f7a9d` |
| Closeout docs | `35d4dd1` |
| Commits | `46f7a9d` Align Today hero and week summary with Playground merge. `35d4dd1` Record R6 T28/D122 correction. |

**T28 before:** Today's Recall said Nothing to review today / Plan my day while Today's path showed Section 8(a) NDPS Act Due today / Start revision. Hero was Constitution-only; merge added Playground `due_count` without flipping `today_mode`.

**T28 after:** `apply_merged_today_hero` after `merge_today_path`. `due_count` = Constitution actionable + Playground actionable. Playground New excluded from `due_count` and the goal denominator. If `due_count > 0`: `today_mode=revision`, `show_plan_prompt=False`, `plan_my_day_available=False`. Playground current review CTA = `current.href` (not `POST /revision/start`). Constitution current keeps `/revision/start`.

**Playground-only due proof:** 1 revision due; hero CTA matches NDPS 8(a) path current href. No Nothing to review today / Plan my day / Not today. `r6_correction_today_playground_due_390_light.png`, `r6_correction_today_playground_due_1280_light.png`.

**Mixed due proof:** due_count 2; path current = Playground; hero CTA = Playground href. After Playground is no longer due, Constitution becomes current and may use `/revision/start`. No combined session.

**New-only proof:** due_count 0. New excluded from goal. Does not trigger the Plan my day suppression.

**D122 before:** week title still showed month-derived `calendar.summary` ("0 units memorized this month, 0 reviews completed, 0 reviews scheduled").

**D122 after:** `CalendarWeek.event_count` / `summary` = sum of `week_events` after Playground chips. Week copy is "N unit(s) this week". Month keeps `calendar.summary`. Phone Calendar stays month-only.

**Week aggregate proof:** Playground-only → 1 unit this week (`r6_correction_calendar_week_1280_light.png`). Constitution + Playground chips → 2. Empty week → 0 units this week. No month-stat fallback.

**Focused tests:** `tests/test_playground_r6.py` + `tests/test_calendar_week.py` **28 passed**.

**Full regression:** R5 + m8 + calendar projection/sync/routes + dashboard **213 passed**. `pytest -m "not integration"` **2876 passed**, 9 skipped, 1 deselected.

**CI** on `46f7a9d`: push [37002096012](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/37002096012), PR [37002099960](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/37002099960), Railway deployment status success.

---

## R6 T28 minutes-line correction

Full write-up: [`PLAYGROUND_UI_REDESIGN_R6_REPORT.md`](PLAYGROUND_UI_REDESIGN_R6_REPORT.md) § T28 minutes-line correction.

ChatGPT review of `81548eb` reopened **T28 only**. D122 stayed DONE. Temporary U6 **14/15**, programme **89.3 / 100**. Restored U6 **15/15**, programme **90.0 / 100** after code, tests, visuals, and CI.

| | SHA |
|---|---|
| Starting | `81548eb` |
| Implementation | `14179a1` |
| Closeout docs | `c445dad` |

There is no Playground duration in the product. `show_revision_minutes` is false whenever `playground_due_count > 0`. Constitution-only revision days still print the existing estimate.

**Playground-only:** never "About 0 minutes". Evidence: `r6_t28_hero_minutes_today_390_light.png`, `r6_t28_hero_minutes_today_1280_light.png`.

**Mixed:** Constitution-only minutes are not shown as the total. After Playground is no longer due, the Constitution estimate returns.

**Constitution-only:** existing `About N minute(s) of review` unchanged.

**Focused tests:** 30 passed. Broader R5/m8/calendar/dashboard: 215 passed. `pytest -m "not integration"`: **2878 passed**, 9 skipped, 1 deselected.

**CI** on `14179a1`: push [37013370205](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/37013370205), PR [37013373523](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/37013373523), Railway success.

Do not start R7.

---

## R5 closeout

Batch report: [`docs/PLAYGROUND_UI_REDESIGN_R5_REPORT.md`](PLAYGROUND_UI_REDESIGN_R5_REPORT.md).

**R5 is complete**, including the post-closeout correction for D95, D130, D108, and T26. Roster/rollover restyle, Profile SUBSCRIPTION/devices view models, Settings phone Reminders, and account surfaces shipped. Programme **80.0 / 100**. R4 (T22–T25, T42) was not reopened. R6 is not started. Stage 1 remains frozen except the T33 pin (`playground.css?v=pg17`, `playground.js?v=pg8`, `mobile.css?v=mob95`). Stage 2 remains PARKED.

Original closeout pin `d9039a3`. Correction starting SHA `d9039a3`. Implementation `ec32195`. D130 CTA pin `d13c80c`. Closeout docs `cd78e25`.

U3 leftover this batch: D93–D100, D130 = 9. U3 **38 / 38**. Weighted U3 = 12.0.
U7: D107–D114, D137–D138, T26–T27 = 12. U7 **12 / 12**. Weighted U7 = 7.0. Programme **80.0 / 100**.

Review had reopened D95, D130, D108, T26 (provisional U3 36/38, U7 10/12, programme 78.2). Those four are DONE again after code, tests, visual proof, and CI.

Alembic head remains **`20260927_0027`**. No migration. Keep / Remove / Undecided and slot consumption stay Stage 1. No Razorpay at render.

Local `pytest -m "not integration"` on `d13c80c`: **2848 passed**, 9 skipped, 1 deselected. Focused R5 + billing/entitlement/r1/settings/guest/learn-plan: **225 passed**. `tests/test_playground_r5.py` **23 passed**. CI on `d13c80c`: push [36990837323](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36990837323) and PR [36990842589](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36990842589) succeeded.

Do not start R6 from this closeout.

---

## R4 closeout

Batch report: [`docs/PLAYGROUND_UI_REDESIGN_R4_REPORT.md`](PLAYGROUND_UI_REDESIGN_R4_REPORT.md).

**R4 is complete**, including the D141 typed-fallback correction. Act progress, six-mode Learn, Playground speech, completion, and locator-aware source review shipped. Programme **70.2 / 100**. T22–T25 and T42 were not reopened. R5 and R6 are not started. Stage 1 remains frozen except the m3b / T33 supersessions this batch required. Stage 2 remains PARKED.

Starting SHA `8610aa1`. Implementation `951c349`. Hidden-complete + D92 wash `4d70c9e`. Tracker `78240b2`. Pin `b57a551`. D141 limiter `5c98d83`. Expired-fixture `ceaa0bb`. Closeout docs `286c98c`. Correction pin `42c0cd3`.

U4 **28 / 28** → 18.0. U5 **13 / 13** (T42 included) → 8.0. Alembic head remains **`20260927_0027`**. No migration.

Playground Learn uses `window.RecallSpeech`. Playground locator-aware speech POST is server-authoritative. Constitution default speech URL remains unchanged.

Local after D141: `tests/test_playground_r4.py` **32 passed**; r1 + m3b entitlement grep **13 passed**; `pytest -m "not integration"` **2825 passed**, 9 skipped, 1 deselected. Pre-correction CI run `36966722295` on `b57a551` is green. Correction-head CI on `5867351`: push `36979217456` and PR `36979221146` succeeded.

Do not start R5 or R6 from this closeout.

---

## R3 closeout

Batch report: [`docs/PLAYGROUND_UI_REDESIGN_R3_REPORT.md`](PLAYGROUND_UI_REDESIGN_R3_REPORT.md).

**R3 is complete**, including the post-closeout correction. Confirm→scope, Act-head kinds, read-only paused home with **zero roster writes**, guest HTML gates, and Playground-scoped HTML 404/403/500 (themed) shipped. Programme **44.2 / 100**. R4 and R5 are not started. Stage 1 remains frozen except required T20/T17 supersessions. Stage 2 remains PARKED.

Starting SHA `e82088b`. Implementation `d4525b1`. Award `54b5af9` was **provisional**. Correction review head `86d8e56`. `peek_capacity` + Add-500 `5c3f003`. D142 theme `6194e5b`.

Three non-optional invariants:

1. Entire Act persistence recovery after roster consume (`persist_entire_act_selection`; retry does not consume another slot; progress fingerprint unchanged).
2. `can_view_home` is GET `/playground` only. Learn/Add/Remove/selection/roster writes stay on `can_open`.
3. D142 is atomic: Playground-scoped HTML 404+403+500 without global exception handlers. Kill-switch 404. Repo/roster 503. `{ok, error}` JSON kept.

U2 leftover this batch: D27–D29, D31–D40, T17–T18 = 15. U2 **39 / 39**. Weighted U2 = 18.0.
U3 R3: D22, D51–D63, D101–D106, D125–D127, D131, D140, D142, T19–T21 = 29. U3 **29 / 38**. Weighted U3 = 12 × 29/38 = **9.2**. Programme **44.2 / 100**.

Alembic head remains **`20260927_0027`**. No migration.

Local `pytest -m "not integration"`: **2786 passed, 9 skipped, 1 deselected**. Focused R3 + leftover T20: **21 passed**. Broader r1/m6/m7/m10/m11/m3b/m5a/`test_playground.py`/units: **277 passed**.

CI:

| Commit | Runs | Result |
|---|---|---|
| `3a8dcd0` | [36814133666](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36814133666) (push), [36814136870](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36814136870) (PR) | success |
| `4cbb443` | [36815267937](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36815267937) (push), [36815272810](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36815272810) (PR) | success |

`27d3418` Unit tests failed on leftover T20 guest-303 assertions; `3a8dcd0` superseded those tests and is green.

Do not start R4 or R5.

## R3 post-closeout correction

The original 44.2 award on `54b5af9` was **provisional**. Review on `86d8e56` found:

1. Paused/halted/expired GET `/playground` still called `roster.capacity()` → `ensure_current_period()` (INSERT/UPDATE). Public Act-head `load_membership_index()` did the same.
2. Entire Act Add mapped unexpected exceptions to HTTP 400 `invalid_selection`.
3. Visual evidence was six artifacts, not the R3 matrix.

Fixes:

- `peek_capacity()` for read-only home and public Act-head. `require_playground_home()` skips `_attach_current_period()` when `can_view_home && !can_open`. Proofs: `test_paused_home_get_does_not_create_or_update_roster_period`, `test_halted_and_expired_home_get_do_not_write_roster`, `test_unsubscribed_public_law_get_does_not_write_roster`.
- Entire Act catches only `SelectionRejected` / `LocatorError` / `PlaygroundLawError`. Unexpected → D142 500. Proofs: `test_entire_act_unexpected_error_is_playground_500_without_consume`, `test_entire_act_selection_rejected_is_400_without_consume`.
- Visual matrix at 390/768/1024/1280 light/dark and reduced motion. One visual defect fixed: D142 error pages now boot `cm-theme` and use `--pg-page` (`pg11`).

Code: `5c3f003`, `6194e5b`. Local `pytest -m "not integration"`: **2793 passed**, 9 skipped, 1 deselected. CI: `5c3f003` [36874411970](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36874411970) / [36874420199](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36874420199); `6194e5b` [36876407403](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36876407403) / [36876417171](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36876417171) **success**.

U2 **39 / 39**. U3 **29 / 38**. Programme **44.2 / 100** restored. R4 and R5 not started.

## R2 closeout

Batch report: [`docs/PLAYGROUND_UI_REDESIGN_R2_REPORT.md`](PLAYGROUND_UI_REDESIGN_R2_REPORT.md).

**R2 is complete for its targeted rows (24 of U2’s 39).** Clause locators, unit authority, and the redesigned picker shipped. R3 Add-dialog work is not started. Stage 1 remains frozen. Stage 2 remains PARKED.

Starting SHA `a49d7b8`. Implementation `0f9842b`. T16 dormant-status follow-up `1cc00b6`.

U2 proven this batch: D11, D23, D41–D50, D128–D129, T5, T8–T16 = **24 / 39**. Weighted U2 = 18 × 24/39 = **11.1**. Programme **28.1 / 100**.

Alembic head remains **`20260927_0027`**. No migration.

No law-specific picker/parser/`UnitLocator`/JS/routes. PSS duplicate labels are generic ordinals. MTP chapterless is generic `chapters == none`.

Local `pytest -m "not integration"` on `1cc00b6`: **2760 passed, 9 skipped, 1 deselected** (one new T16 dormant-status test vs `0f9842b`). Focused after `1cc00b6`: `tests/test_playground_units.py` + r1/m8/m11 **85 passed**. CI on `1cc00b6`: workflow runs `36734662452` (push) and `36734670642` (PR) **success**.

No new B/C denominator rows. No class-D product-scope stop. Do not start R3.

## R2 correction

Correction report: [`docs/PLAYGROUND_UI_REDESIGN_R2_CORRECTION_REPORT.md`](PLAYGROUND_UI_REDESIGN_R2_CORRECTION_REPORT.md).

Isolated fixes on the closed R2 picker: invalid POST is HTTP 400 with zero mutation; `UnitLocator` cannot exist unbound. Programme remains **28.1 / 100**. U2 remains **24 / 39**. R3 is not started.

Code `f62bd63`. Local `pytest -m "not integration"`: **2767 passed, 9 skipped, 1 deselected**. Focused: `tests/test_playground_units.py` + m8/m9/m11/`test_playground.py` **136 passed**. CI on `f62bd63`: workflow runs `36751875399` (push) and `36751885785` (PR) **success**.

## R1 closeout

**U1 is complete (28/28).** Shared design system and shells shipped. No R2 work.

Starting SHA `343b090`. Implementation commits: `24b2729`, `5f4a63c`, `d81d36f`, `cd1c4c6`. Tracker closeout: `cf41baf`.

Local `pytest -m "not integration"`: **2742 passed, 9 skipped, 1 deselected**.

Focused: `tests/test_playground_r1.py`, `tests/test_mobile_screens.py`, `tests/test_settings_phone.py`, `tests/test_web_sprint30.py`, `tests/test_playground_m6.py`, `tests/test_playground_m7.py`, `tests/test_guest_first_ux.py` — 223 passed before the full suite.

No new B/C denominator rows. No class-D product-scope stop. Do not start R2.

## R0 readiness

**U0 is complete (10/10).** **U1 is complete (28/28).** **R2 is complete.** **R3 is complete (U2 39/39).** **R4 is complete (U4 28/28, U5 13/13), including the D141 typed-fallback correction.** **R5 is complete (U3 38/38, U7 12/12).** **R6 is complete (U6 15/15), including the T28 minutes-line correction.** **R7 is complete (U8 25/25).** Stage 2 remains PARKED. Do not merge PR 188. Programme **100.0 / 100**.
