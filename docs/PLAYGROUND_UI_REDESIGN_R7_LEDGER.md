# R7 closeout ledger

U8 only (T40 + V1–V24). Starting HEAD `56065c2`. Alembic `20260927_0027`. PR 188 draft. Stage 1 / R5 / R6 frozen. Stage 2 parked. Do not merge.

Score: `90 + 10 × proven_U8 / 25`. Do not force 100.

This file is the Phase 1–3 freeze. Implementation follows the approved order below. It does not widen the denominator.

## Approved work order

1. Inventory / V24 baseline (this file + `docs/design/PLAYGROUND_DESIGN_INVENTORY.md`)
2. T40 ledger, docs only (this file)
3. V15 D-row ledger (this file)
4. Responsive reconciliation
5. Theme / contrast
6. Reduced motion
7. Keyboard / focus
8. Semantics
9. V11 target / safe-area pass
10. **T40 execution** — only rewrites this ledger authorizes. Do not weaken an assertion merely to pass.
11. **V16 / V17 / V18** frozen-domain regressions, against the current authorized contracts. A semantic failure here is a real STOP. Do not run these before step 10.
12. Focused R7 tests plus full `pytest -m "not integration"`
13. Visual sign-off, CI, and Railway. V19/V20 only after CI and Railway are green.
14. Handoff and tracker closeout. Do not merge.

## Frozen / stop

STOP and report (do not repair inside R7, do not mark the blocked V-row DONE) if R7 discovers:

- a new product decision
- a previously unknown Stage 1 correctness defect
- an R5 semantic regression
- an R6 semantic regression
- a required schema or migration change
- a newly required D or T row outside U8
- a newly discovered Class-B mismatch that would require a **new** Layer 1 D row under §21.3 — do not add the row, do not fix it, do not claim V23 DONE
- an applicable phone control under 44px whose fix needs a frozen product or IA decision — V11 cannot close via `APPROVED DEVIATION`
- a token that fails contrast in light or dark

Fair R7 work: overflow, token misuse, focus visibility, ARIA, target size (padding / min-size without IA change), safe area, responsive collision, raw colour on a Class-B page that is already covered by D1–D17, reduced-motion defect.

`APPROVED DEVIATION` is a **V15** classification only. It is not a way to score V11.

## Chrome rules (locked)

- Phone layouts in `mobile.css` remain `@media (max-width: 560px)`.
- ~768 is the 561–899 band: flex header, **not** the 900px 3-column desktop grid. Week view stays hidden. Treat this band as phone-shell verification (V2), not desktop chrome.
- Desktop chrome starts at **900px** (D18). V3 (~1024) is the desktop collision pass.
- Calendar week is desktop-only (`min-width: 900px`). Exercise at ~1024 and 1280+, not at 390 or ~768.
- Legal stays Class B. Admin stays Class D + V18 regression only. No `.dc.html` edits.

---

## Phase 1 — Inventory / V24 baseline

Confirmed against HEAD `56065c2` and T41:

| | Count |
|---|---|
| Active templates on disk | **81** |
| Unclassified templates | **0** |
| Class A | 19 |
| Class A, verify only | 2 (`browse_index.html`, `laws.html`) |
| Class B | **45** |
| Class C templates | 4 |
| Class D admin | 11 |
| Class E remaining | 0 |

V24 is route-level. Every active HTML route is classified by the template it renders. Redirects, JSON, sitemaps, icons, and the service worker are **no UI**, not unclassified. Admin `/admin*` is Class D (excluded from restyle; V18 still required).

Stale inventory notes at freeze (corrected in `PLAYGROUND_DESIGN_INVENTORY.md` during this freeze, not a product change):

- Guest `GET /playground*` is HTML **200** sign-in gate (T20), JSON 401.
- Paused / halted / expired `GET /playground` is **read-only home** (T19). Learn stays gated.

### Layout families (screenshot sharing)

Shared-family surfaces may cite the same visual proof when shell, component, and layout are identical. Route-specific content is still checked. **Not screenshotted must not mean not inspected.** Representative screenshots are allowed; representative verification is not.

| Family | Members | Phone | Desktop | Notes |
|---|---|---|---|---|
| A-shell | `base.html`, `playground_base.html` | 390, ~768 | ~1024, 1280 | Shared chrome |
| A-playground-home | `playground.html` | 390, ~768 | ~1024, 1280 | Empty / filled / paused |
| A-add | `playground_add.html` | sheet | dialog | |
| A-picker | `playground_select.html` | footer | aside ≥900 | |
| A-law | `playground_law.html` | 390 | 1280 | |
| A-learn | `playground_learn.html` | 390 | 1280 | All six modes |
| A-complete | `playground_learned.html` | fixed-dark | fixed-dark | Learned + Mastered |
| A-roster | `playground_roster.html`, `playground_remove.html` | 390 | 1280 | |
| A-rollover | `playground_roster_next.html` | footer | aside | |
| A-gate | `playground_gate.html` | 390 | 1280 | Plus D102 variants |
| A-today | `dashboard.html` | 390 | 1280 | |
| A-calendar-month | `calendar.html` month | 390, ~768 | 1280 | |
| A-calendar-week | `calendar.html` week | **n/a** | ~1024, 1280 | Desktop only |
| A-account | `profile.html`, `settings.html`, `subscription_manage.html` | 390 | 1280 | D113 styling frozen |
| A-verify | `browse_index.html`, `laws.html` | 390 | 1280 | V23 verify-only |
| A-act-head | `bare_act.html`, `partials/playground.html` | 390 | 1024+ CTA column | |
| B-browse-reader | `browse_part.html`, `browse_article.html` | 390 | 1280 | Same browse shell |
| B-act-body | `bare_act_section.html`, `bare_act_schedule.html`, `partials/bare_act_footnotes.html`, `partials/bare_act_macros.html` | 390 | 1280 | |
| B-learn | `learn.html`, `choose.html`, `incomplete.html`, `_completion_banner.html`, `_locked_mode.html`, `partials/mode_help_modal.html` | 390 | 1280 | No visual rebuild; V11 min-size allowed |
| B-progress | `progress.html`, `progress_mastered.html` | 390 | 1280 | |
| B-search-tables | `search.html`, `tables.html` | 390 | 1280 | |
| B-memory | `memory.html`, `memory_detail.html` | 390 | 1280 | |
| B-law-detail | `law_detail.html` | 390 | 1280 | Mapped / key-provision |
| B-onboarding | `guest_gate.html`, `welcome.html`, `onboarding_plan.html`, `plan_my_day.html`, `partials/guest_modal.html` | 390 | 1280 | |
| B-home | `home.html` | 390 | 1280 | Signed-in `/` |
| B-purchase | `pricing.html`, `purchase_confirm.html`, `purchase_result.html` | 390 | 1280 | Frozen 404 unless `PRICING_ENABLED` |
| B-auth | `login.html`, `signed_out.html`, `session_expired.html`, `auth_transition.html`, `auth_callback.html`, `partials/auth_shell.html` | 390 | 1280 | Auth family; token/focus/overflow only |
| B-landing | `landing.html`, `landing_light.html` | 390 | 1280 | |
| B-legal | `legal/base.html`, `legal/terms.html`, `legal/privacy.html`, `legal/grievance.html`, `legal/_macros.html` | 390 | 1280 | Class B, not an exclusion |
| B-explainer | `visual_explainer.html`, `visual_explainer_trigger.html` | overlay | overlay | |
| B-dialogs | `partials/report_dialog.html`, `partials/revision_exit_modal.html` | overlay | overlay | |
| C-source | `playground_source_review.html`, `playground_source_review_section.html` | 390 | 1280 | D133–D136 |
| C-devices | `devices.html` | 390 | 1280 | D137 |
| C-checkout | `subscription_checkout.html` | 390 | 1280 | D138 |
| C-errors | D140 / D142 shells | 390 | 1280 | Themed |
| D-admin | `admin/*` (11) | regression only | regression only | No restyle |

### Class B — 45 templates (each must be individually verified **or** family-covered + content checked)

`browse_part.html`, `browse_article.html`, `learn.html`, `choose.html`, `incomplete.html`, `search.html`, `tables.html`, `memory.html`, `memory_detail.html`, `law_detail.html`, `bare_act_section.html`, `bare_act_schedule.html`, `progress.html`, `progress_mastered.html`, `guest_gate.html`, `welcome.html`, `onboarding_plan.html`, `plan_my_day.html`, `home.html`, `pricing.html`, `purchase_confirm.html`, `purchase_result.html`, `login.html`, `signed_out.html`, `session_expired.html`, `auth_transition.html`, `auth_callback.html`, `landing.html`, `landing_light.html`, `legal/base.html`, `legal/terms.html`, `legal/privacy.html`, `legal/grievance.html`, `legal/_macros.html`, `visual_explainer.html`, `visual_explainer_trigger.html`, `_completion_banner.html`, `_locked_mode.html`, `partials/auth_shell.html`, `partials/bare_act_footnotes.html`, `partials/bare_act_macros.html`, `partials/guest_modal.html`, `partials/mode_help_modal.html`, `partials/report_dialog.html`, `partials/revision_exit_modal.html`.

### Class-B / D-row governance (V23)

§21.3 requires a Layer 1 D row **before** restyling a non-conforming Class-B element. R7 must not widen the denominator. R7 does not silently override §21.3.

| Finding | Action |
|---|---|
| Element already conforms | Record **MATCHED** |
| Mismatch covered by an **existing** D row (D1–D17 tokens/components, D14 focus, D16 motion, D17 tap) | R7 may reconcile |
| Newly discovered mismatch that would need a **new** D row | **STOP**. Do not add. Do not fix. V23 stays open |

No new Class-B D row was authorized at freeze. V23 cannot close if a stop of this kind is open.

### Class C — every template and listed state

No new design.

| ID | Surface / state | Ledger requirement |
|---|---|---|
| D133 | Source review list | `playground_source_review.html` |
| D134 | Source review section | `playground_source_review_section.html` |
| D137 | Devices | `devices.html` |
| D138 | Checkout | `subscription_checkout.html` |
| D102 | Gate variants | free / not subscribed; device limit; device revoked; replacement limit; halted; config error |
| D135 | Missing / omitted | both variants |
| D136 | Learned + Law updated; Mastered + Law updated | both combined states |
| D139 | Learn failure | save failed; stale revision; not due; not selected |
| D140 | Service / unavailable | styled 503 |
| D141 | Speech unavailable / offline | typed path; no dead control |
| D142 | HTML 404 / 403 / 500 / kill-switch 404 | themed shells |

Each Class-C state is explicitly verified (including dark theme, keyboard/focus, status-not-colour-only). Shared chrome may share screenshots.

Guest sign-in (D101) and paused read-only home (T19 / D103) stay in the matrix; they do not stand in for D102 variants.

### Visual matrix (V1–V6, V21, V22)

Stored artifact combinations (representative screenshots only): 390 light, 390 dark, ~768, ~1024, 1280 light, 1280 dark, reduced motion.

Do **not** store 81 × 7 screenshots. Every active surface/state is in this ledger. Every family is exercised at applicable viewports/themes. Playwright `channel="chrome"`. New filenames only.

---

## Phase 2 — T40 ledger (docs only until Phase 10)

Do not rewrite tests until Phase 10. Do not weaken an assertion merely to pass.

| ID | File | Old assertion | Why superseded | New assertion | Authority | Status at freeze |
|---|---|---|---|---|---|---|
| T40-1 | `tests/test_entitlement_m3b.py`, `test_playground_m6.py`, `test_playground_r3.py`, `test_playground_m10.py`, `test_playground_m11.py` | Guest `/playground` 303 to login | Delta H | HTML 200 sign-in gate; JSON 401 | T20 | **Already executed (R3)** |
| T40-2 | `tests/test_private_noindex.py`, `test_playground_r5.py` | Guest GET `/profile` 303 | D110 guest profile card | HTML 200, noindex | D110 | **Already executed (R5)** |
| T40-3 | `tests/test_entitlement_m3b.py`, `test_playground_r3.py`, `test_playground_m6.py` | Paused/expired hard gate page | Delta G | Read-only home; Learn still gated; `data-hard-gate` absent on home | T19 | **Already executed (R3)** |
| T40-4 | `tests/test_playground_m8.py` `test_today_queue_current_roster_only` | `"Law revisions"` heading / weak `data-today-source` only | T28 merged Today path | Keep `"Law revisions" not in page`; pin `data-today-path-card`, `data-today-kind="review"`, eyebrows `Day 3 → 7 · Playground` (BNS) and `Day 1 → 3 · Playground` (NDPS), current CTA `Start revision →`, BNSS absent, BNS before NDPS | T28 / D115–D117 | **Executed Phase 10** |
| T40-5 | Act-enumerating loops | `("ndps", "bns", "bnss")` only | Delta F | Eligible six: `bns bnss ndps uapa pss mtp`. `test_pota_reader.py` `test_current_acts_show_no_badge` now iterates `list_playground_eligible_laws()` | T4 | **Executed Phase 10** |

Cosmetic names (`test_six_modes_generic_across_ndps_bns_bnss`, `test_cloze_integrity_ndps_bns_bnss_section_1`) already iterate `ELIGIBLE_LAWS`. Not rewrites.

T40 is **DONE**. T40-4 and T40-5 executed. No assertion was weakened merely to pass. V16/V17/V18 ran after this execution.

---

## Phase 3 — V15 D-row ledger (D1–D142)

Every D row is **MATCHED**, **APPROVED DEVIATION**, or **N/A**. No row disappears because its batch is frozen. Do not reopen frozen functionality to make the prototype literally identical.

### APPROVED DEVIATION (production truth vs prototype demo)

| ID | Why production overrides the prototype |
|---|---|
| D4 | Prototypes define no dark theme. Dark token values were derived (T34). |
| D92 | Fixed-dark completion in both themes; not a prototype dark screen. |
| D51 / D60 | Live month / period copy, not prototype demo “September/October”. |
| D109 | Device copy uses the real cap (2). Prototype “Devices 2 of 3” must not ship (X5). |
| D113 | Settings control **styling** stays shipped (raised segment, outline badges). §4 / §21.4. Hit area may still be corrected for V11. |
| D18 / D20 | Project-owned mark until geodesic-dome licence is confirmed. |
| D104 / D105 / D36 | Catalogue Plus / Pro / Max and GST/renewal wording, not prototype Core/Deep/Infinite or demo prices (X1). |

### N/A

None of D1–D142 is unused. Phone-only rows (D12, D17, D20, D21, D23, D48, D52, D53, D111, D112, D118, D121, D127) shipped on phone. Desktop-only rows (D13, D18, D19, D29, D49, D54, D56, D58, D70–D72, D87, D119, D122–D124) shipped on desktop. Week rows are N/A **on phone** as a viewport, but the D row itself is MATCHED.

### MATCHED

All other D1–D142 rows: MATCHED to the shipped production implementation closed in R0–R6, including D101–D106, D102 gate reasons, D115–D124 (T28 minutes + D122 week summary), D133–D142.

V15 does not close V11.

---

## Phase 4–9 intended reconciliation (existing D rows only)

| Pass | Existing rows | Planned work |
|---|---|---|
| Responsive / ~1024 | D18, D25, D29, D49 | `minmax(0)` / padding on week grid and header in 900–1039; no new IA |
| Overflow | D25 | `overflow-x: hidden` on shell/main |
| Theme / contrast | D1–D4, D142 | Token use; if a token fails contrast, STOP |
| Reduced motion | D16 | Collapse remaining `.panel` / shell motion |
| Focus | D14 | Visible `:focus-visible` on interactive controls without a new keyboard model |
| Semantics | D11, D46, D98, D10 | Existing dialog / radiogroup / tri-state; status not colour-only |
| V11 | D17, D113 | `min-height` / `min-width` 44px on applicable phone controls; Settings styling frozen; Constitution Learn not rebuilt |

T33: bump CSS asset pins when those files change. `playground.js` stays `pg8` unless JS changes.

Shipped: `styles.css?v=main77`, `mobile.css?v=mob98`, `playground.css?v=pg19`, `playground.js?v=pg8`.

## Phase 4–14 outcomes

| Step | Result |
|---|---|
| 4 Responsive | Overflow-x hidden on shell/main. 900–1039 `min-width: 0` on week grid, header, home grid, Act-head CTA. ~768 remains 561–899 flex header (no tab bar). Week stays `min-width: 900px`. |
| 5 Theme / contrast | Token hover `a:hover → var(--browse-due)`; dark theme-toggle `var(--hairline)`. No token failed contrast. |
| 6 Reduced motion | Remaining `.panel` / `.continue-card` motion collapsed under `prefers-reduced-motion` and `html:not(.rtc-anim)`. |
| 7 Keyboard / focus | Global `:focus-visible` 2px `var(--ink)` ring. Settings Self-paced ring photographed. |
| 8 Semantics | Existing dialog / radiogroup / tri-state. Calendar week legend remains text + mark. D102 titles remain distinct. |
| 9 V11 | Playwright 390×844, `channel="chrome"`. Applicable phone controls now `min-height` / `min-width` 44px (month-strip, calendar nav/cells, Today ··· and avatar wrapper, path CTA, search field/cancel, Learn `?` help, Act-head tab/toggle as text links, legal-switch/toc, login brand/guest/legal-nav, sheet close, plan-intro segments). Settings toggle **hit** is 44px; **painted track** stays 46×28 via `::before` (D113). Constitution Learn not rebuilt. Inline prose links, hidden radios, and text labels are not chrome. No approved deviation used to close V11. |
| 10 T40 execution | T40-4 and T40-5 only. See Phase 2. |
| 11 V16 / V17 / V18 | Frozen-domain suite on the authorized contracts. Semantic failure would have been STOP. None fired. |
| 12 Tests | Focused `tests/test_playground_r7.py`. Full `pytest -m "not integration"` on `fc0ca67`: **2888 passed**, 9 skipped, 1 deselected. This V11/V23 correction re-runs focused pins before closeout. |
| 13 Visual / CI / Railway | Representative screenshots from `fc0ca67`. CI/Railway green on that SHA. This correction does not reopen those rows. |
| 14 Handoff | `docs/design/PLAYGROUND-FINISH-HANDOFF.md`. U8 **24/25**. V23 STOP. Do not merge. Stage 2 stays PARKED. |

### Visual matrix (representative screenshots; every family inspected)

Playwright `channel="chrome"`. New filenames only. First Act-head 1024 shot was mid-rise animation; recapture under reduced motion is the collision proof.

| Family / state | Evidence |
|---|---|
| A-playground-home 390/768/1024/1280 light+dark+reduced | `r7_home_390_light.png`, `r7_home_390_dark.png`, `r7_home_390_reduced.png`, `r7_home_768_light.png`, `r7_home_1024_light.png`, `r7_home_1280_light.png`, `r7_home_1280_dark.png` |
| A-today | `r7_today_390_light_settled.png`, `r7_today_1280_light.png` — New excluded from due_count (frozen T28) |
| A-calendar-month phone | `r7_calendar_month_390_light.png` |
| A-calendar-week desktop | `r7_calendar_week_1024_light.png`, `r7_calendar_week_1280_light.png` |
| A-account | `r7_settings_390_light.png`, `r7_settings_focus_390_light.png`, `r7_profile_390_light.png` |
| A-act-head 1024 | `r7_act_head_1024_reduced.png` — CTA column fits; no collision |
| A-law / picker | `r7_law_390_light.png`, `r7_picker_390_light.png` |
| A-gate guest | `r7_gate_guest_390_light.png` |
| A-verify browse | `r7_browse_390_light.png` |
| B-learn Constitution | `r7_const_learn_390_light.png` |
| B-search | `r7_search_390_light.png` |
| B-legal | `r7_legal_terms_390_dark_view.png`, `r7_legal_privacy_390_dark.png` |
| B-auth | `r7_auth_login_390_light_view.png` |
| B-landing | `r7_landing_390_light.png` — shipped splash palette, not restyled |
| C-devices | `r7_devices_390_light.png`, `r7_devices_1280_light.png` — `1 of 2` |
| C-errors D142 | `r7_d142_404_390_light.png` |
| D102 not-subscribed | HTTP 200 `Unlock Playground` + `data-hard-gate`. Six `gate_view` titles remain distinct |
| T19 paused/halted | HTTP 200 Playground home; `data-hard-gate` absent |

HTTP inspect: 58/58 expected routes. Guest `/playground` HTML 200 sign-in gate. Paused/halted home has no hard-gate. `/memory` is feature-flag 404 when `MEMORY_LOG_ENABLED` is false (documented exclusion). Admin GET 404 for a non-admin (Class D, V18 only).

## Stop log

**V23 STOP.** Class-B landing/auth-family palettes do not use D1–D17 tokens.

| Template | Finding | Rule |
|---|---|---|
| `landing.html` | Splash indigo/cream (`#6E82C8`, `#f4f1ea`, `#4C5C9E`, `#0b0b0b`) | Not D1–D17. Restyle would be a landing rebuild and needs a **new** Layer 1 D row under §21.3. Row not added. Not restyled. |
| `landing_light.html` | Alternate splash raw hex (`#fdfcfa`, `#141414`, `#0E7569`) | Same. Not D1–D17 CSS tokens. |
| `login.html` | Standalone indigo/cream (same family as `landing.html`) | Same. Hit-area padding on brand / `.j-guest` / legal nav only. Palette untouched. |

Do not claim V23 DONE. Do not add the D row. Do not fix the palette inside R7.

Other Class-B templates on this pass: **MATCHED** to D1–D17 tokens, or tap-size mismatches **reconciled** under existing D17 (legal-switch, legal-toc). `signed_out.html`, `session_expired.html`, `auth_transition.html`, `auth_callback.html`, and `partials/auth_shell.html` use `base.html` tokens — MATCHED.

V11 is not in this stop log. 390×844 measure after the min-size pass: no applicable chrome control under 44px. Remaining sub-44 hits are hidden radios, `sr-only` labels, text `<label>`s, and inline prose links (WCAG).
