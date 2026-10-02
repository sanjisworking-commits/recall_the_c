# Playground UI Redesign — R4 report

Act progress, six-mode Learn, Playground speech, completion, and locator-aware source review. R5 roster/Profile and R6 Today/Calendar are **not** started. Stage 1 remains frozen except the test supersessions this batch required. Stage 2 remains parked.

This file is the batch closeout. Later batches should add `docs/PLAYGROUND_UI_REDESIGN_R{n}_REPORT.md` the same way.

Authoritative docs:

- [PLAYGROUND_UI_REDESIGN_PLAN.md](PLAYGROUND_UI_REDESIGN_PLAN.md)
- [PLAYGROUND_UI_REDESIGN_TRACKER.md](PLAYGROUND_UI_REDESIGN_TRACKER.md)
- [design/PLAYGROUND_DESIGN_INVENTORY.md](design/PLAYGROUND_DESIGN_INVENTORY.md)
- Prototypes: `docs/design/Recall the C - Playground Desktop.dc.html`, `docs/design/Recall the C - Playground.dc.html`

```text
Stage 1               = DONE — 100.0 / 100, frozen
UI Redesign Programme = 70.2 / 100
U0                     = 10 / 10
U1                     = 28 / 28
U2                     = 39 / 39
U3                     = 29 / 38  (R5 leftover D93–D100, D130)
U4                     = 28 / 28
U5                     = 13 / 13  (includes T42)
R2                     = DONE
R3                     = DONE (post-closeout correction frozen)
R4                     = DONE (D141 typed-fallback correction)
R5                     = not started
R6                     = not started
Stage 2                = PARKED
```

**Branch:** `cursor/playground-220d`  
**PR:** [#188](https://github.com/sanjisworking-commits/recall_the_c/pull/188)

The 70.2 programme score is calculated from proven tracker rows (U4 28/28 + U5 13/13), not forced.

---

## Acceptance

| | |
|---|---|
| Targeted | Act progress read-model; six-mode Learn chrome; Playground speech POST; distinct initial / revision / mastery completion; locator-aware source-review (T42). |
| Completed | Implementation, regression, visual matrix, tracker closeout. |
| Remaining | R5 roster/Profile (U3 leftover + U7). R6 Today/Calendar/Google. Do not start them from this report. |
| Programme score before | 44.2 / 100 |
| Programme score after | **70.2 / 100** |
| Alembic | one head: `20260927_0027`. No R4 migration. |

Amendments A–G from the approved R4 plan are binding. No new Class-D product decision. No newly discovered B/C rows during implementation; T42 is the approved thirteenth U5 item (locator-aware source-review twins). That T42 is not the rejected auto-merge T42 noted in the R0 tracker.

---

## Branch state

| | SHA |
|---|---|
| Starting (R3 frozen HEAD) | [`8610aa1`](https://github.com/sanjisworking-commits/recall_the_c/commit/8610aa1) |
| Implementation | [`951c349`](https://github.com/sanjisworking-commits/recall_the_c/commit/951c349) |
| Hidden-complete + D92 wash | [`4d70c9e`](https://github.com/sanjisworking-commits/recall_the_c/commit/4d70c9e) |
| Tracker closeout | [`78240b2`](https://github.com/sanjisworking-commits/recall_the_c/commit/78240b2) |
| Pin | [`b57a551`](https://github.com/sanjisworking-commits/recall_the_c/commit/b57a551) |
| D141 limiter (audio-only) | [`5c98d83`](https://github.com/sanjisworking-commits/recall_the_c/commit/5c98d83) |
| D141 expired-fixture match | [`ceaa0bb`](https://github.com/sanjisworking-commits/recall_the_c/commit/ceaa0bb) |
| D141 closeout docs | [`286c98c`](https://github.com/sanjisworking-commits/recall_the_c/commit/286c98c) |

| SHA | What |
|-----|------|
| `951c349` | ActProgress, Learn restyle, speech POST, completion GET, T42 twins |
| `4d70c9e` | `[hidden]` beats `.pg-btn` display; D92 html/body/sheet wash; Cloze advance label; U4/U5 chrome pins; T33 `pg14`; m3b entitlement-status grep |
| `78240b2` | R4 report + tracker: U4 28/28, U5 13/13, programme 70.2 |
| `b57a551` | Pin closeout SHAs |
| `5c98d83` | Speech-provider limiter on audio only; typed fallback proofs |
| `ceaa0bb` | Expired D141 fixture uses subscription billing-period bounds |
| `286c98c` | Tracker SpeechClient cleanup; D141 DONE; programme 70.2 restored |

Nothing from R0/R1/R2/R3 was reopened except the Stage 1 assertions listed under Tests.

---

## Architecture (thin layer)

R4 is a read-model and chrome layer over Stage 1. It does not duplicate lifecycle, speech, or source-review engines.

| Concern | Authority |
|---|---|
| Lifecycle learned / review / mastered | `playground/lifecycle.py`, repository |
| Mode complete, including out-of-order and Test-via-quiz | Stage 1 `complete_mode` / `complete_revision_mode_and_advance_if_ready`; HTTP `/complete` still **404s Test** |
| Next identity | Stage 1 workspace loop, now `choose_next_workspace_row` |
| Recite alignment | Server `recite_alignment`; client renders the map, does not own it |
| Letters typed path | `align_text`; `expected=` ignored; `text=` skips the provider **and** the speech-provider limiter |
| Statutory text | Hydrated Bare Act; never client-authored |
| Mastery / completion GET | Server status gate; stray review GET → workspace |
| Source review | Existing detect/review engine; T42 adds unit locator GET/POST twins |

`completed_scope_count` = learned ∪ review ∪ mastered (monotonic). Histogram: learned → Day 1, review → pending rung, mastered excluded. Whole-Act D91 compares `locators_for_act` to effective learnable locators (missing/omitted excluded).

---

## Amendments A–G

| | Binding rule | Proof |
|---|---|---|
| A | Locator-aware source review through T42 | `test_t42_pss_duplicate_printed_two_are_independent`, `test_t42_missing_unit_learn_redirects_to_unit_review` |
| B | Distinct initial / revision / mastery completion | `test_t24_learned_get_after_initial_six`, `test_t24_revision_six_stays_in_learn_until_day_60`, `test_t24_review_stray_get_redirects_and_mastered_gates` |
| C | Monotonic Act progress | `test_t22_completed_scope_is_monotonic_and_histogram_excludes_mastered` |
| D | Server-owned Recite alignment | `test_t25_recite_alignment_is_server_owned` |
| E | Evidence-based completion copy; no Ambedkar / invented % | `test_t24_*`, T35, learned/mastered screenshots |
| F | Source-change-aware whole-Act mastery + D136 overlay | `test_t24_d91_whole_act_and_d136_source_pending` |
| G | Preserve six-mode / out-of-order complete | `test_t23_modes_seen_step_bar_and_out_of_order`; Test HTTP complete stays 404 |

---

## Visual matrix

Captured at 390 / 768 / 1024 / 1280, light and dark, plus 390 reduced-motion Act progress. Playwright + system Chrome, device metrics (not a full desktop window). Local owner seed is `multiuser=false`, so the top nav is Constitution Home / Browse / Calendar / Progress / Search. That is documented, not an R4 regression. D21 still hides the phone tab bar on Learn and completion.

Playwright probes on the live seed:

- Type `[data-pg-complete]` **is hidden** (`Mark Type done` not painted; `.pg-btn { display: inline-flex }` no longer wins)
- Learned `html` background `rgb(20, 20, 20)` (`#141414`); site-header hidden
- Recite “Hold to peek” visible

| State | Evidence | Notes |
|---|---|---|
| Act progress ring / Next / waffle / histogram | `r4_act_progress_390_light.png`, `_390_dark.png`, `_1280_light.png` | 4/5 learned; Next · Section 2 (due); mastered excluded from Day 60 column |
| Empty Act | `r4_empty_bns_390_light.png` | “Nothing selected yet”; Manage sections |
| Desktop Up next / verbatim / section list | `r4_act_progress_1280_light.png` | Shown at ≥900px |
| Read / Cloze / Letters / Type / Recite / Test | `r4_learn_{mode}_390_light.png` | Task headings + Stage 1 advance labels |
| Desktop deck + panel | `r4_learn_read_1280_light.png` | D87 at 1040px |
| Type complete hidden | `r4_learn_type_390_light.png` | Check visible; Mark Type done not |
| Recite blur + Hold to peek + typed path | `r4_learn_recite_390_light.png`, `r4_recite_peek_390_light.png` | D83 / D141 |
| Letters typed fallback | `r4_learn_letters_390_light.png` | Speak it / Just read + Check typed words |
| Revision Day 7 | `r4_revision_day7_390_light.png` | “Revision · Day 7”; source-outdated line |
| Section learned | `r4_learned_390_light.png`, `_390_dark.png` | Fixed-dark; First revision · Day 1; no Ambedkar |
| Mastered, verbatim | `r4_mastered_390_light.png` | All six chips done; Day 60 copy from real rungs |
| Source-review list | `r4_source_review_list_390_light.png` | D133; learned/mastered + changed |
| Source-review section | `r4_source_review_section_390_light.png` | D134; Mark reviewed; current verbatim |
| Reduced motion | `r4_act_progress_390_reduced.png` | Histogram/ring transitions off |

Prototype completion quote (“Constitution is not a mere lawyers’ document… — B. R. Ambedkar”) is **not** shipped. Completion notes are server facts only.

---

## Tests

Stage 1 assertions superseded on purpose (record, do not weaken silently):

- m3b: `if status ==` grep is entitlement statuses only (`active` / `paused` / `halted` / `expired`). Lifecycle `if status == "mastered"` in Playground HTTP is allowed.
- T33: `playground.css?v=pg14` (not pg13).
- m11: CSRF inventory allowlists Playground speech twins and unit `/reviewed`.

| Run | Result |
|---|---|
| `tests/test_playground_r4.py` + r1 + m3b entitlement grep on `b57a551` | **42 passed** |
| `pytest -m "not integration"` on `b57a551` | **2822 passed**, 9 skipped, 1 deselected |
| CI on `b57a551` | [run 36966722295](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36966722295) succeeded |

See **Post-closeout correction (D141)** for the later limiter fix and the 2825-passed suite.

---

## Programme score

| | |
|---|---|
| Before | 44.2 / 100 |
| Newly proven | U4 28 + U5 13 |
| U4 | 28 / 28 → **18.0** |
| U5 | 13 / 13 → **8.0** |
| After | **70.2 / 100** |

U5 denominator is 13 because T42 is an approved U5 technical row. Weighted U5 is still 8. Remaining U3 rows (D93–D100, D130) stay unawarded for R5.

---

## Post-closeout correction (D141)

Acceptance review of `b57a551` found one real D141 contract failure: `_playground_speech()` ran `speech_rate_limiter.allow()` **before** the typed/audio split, so typed Check after an audio 429 received another 429. T25 stayed DONE. T22–T24 and T42 were not reopened. 70.2/100 was provisional; the proven score until this fix was U4 27/28 → **69.6 / 100**.

No new UI. Letters and Recite already map `unavailable` / `rate_limited` to typed-path copy via `window.RecallSpeech`. Constitution `/learn/{unit_id}/speech/transcribe` is unchanged.

### SHAs

| | SHA |
|---|---|
| Starting correction | [`b57a551`](https://github.com/sanjisworking-commits/recall_the_c/commit/b57a551) |
| Limiter on audio only | [`5c98d83`](https://github.com/sanjisworking-commits/recall_the_c/commit/5c98d83) |
| Expired-fixture period match | [`ceaa0bb`](https://github.com/sanjisworking-commits/recall_the_c/commit/ceaa0bb) |
| Closeout docs | [`286c98c`](https://github.com/sanjisworking-commits/recall_the_c/commit/286c98c) |
| Ending correction | [`42c0cd3`](https://github.com/sanjisworking-commits/recall_the_c/commit/42c0cd3) |

### Limiter ordering

Old:

```text
CSRF → _gate_learn → speech_rate_limiter.allow(...) → typed or audio
```

New:

```text
CSRF
→ Playground Learn access chain
→ validate mode
→ if typed text: canonical server comparison; no limiter; no provider
→ if audio: speech-provider rate limit → MIME → 2 MB → provider → server alignment
```

Typed fallback still requires Playground enabled, authenticated/allowed account, commercial Learn access, device, current-law roster membership, active selected locator, CSRF, valid Letters/Recite mode, and server-owned canonical text. `expected=` remains non-authoritative.

### Proofs

| Case | Test | Result |
|---|---|---|
| Letters audio #1 succeeds, audio #2 429, typed fallback 200, provider count unchanged | `test_d141_letters_rate_limit_then_typed_fallback` | green |
| Recite same invariant; `recite_alignment` map returned | `test_d141_recite_rate_limit_then_typed_fallback` | green |
| Audio 503 unavailable then typed 200; provider unused for typed | `test_d141_unavailable_then_typed_fallback` | green |
| Guest / free / paused / halted / expired / device revoked / inactive law / unselected / dormant locator / bad CSRF / invalid mode; no provider call | `test_d141_typed_fallback_keeps_access_gates` | green |

Client copy already present in `playground-learn.js`:

- Letters 429/503 → “Speech recognition is unavailable. Type the words instead.”
- Recite 429/503 → “Speech recognition is unavailable. Type what you recited.”
- Check posts `text=` through `window.RecallSpeech` (no new endpoint)

### Runs

| Run | Result |
|---|---|
| `tests/test_playground_r4.py` | **32 passed** |
| r1 + m3b entitlement grep | **13 passed** |
| `pytest -m "not integration"` | **2825 passed**, 9 skipped, 1 deselected |
| CI on `b57a551` (pre-correction) | [run 36966722295](https://github.com/sanjisworking-commits/recall_the_c/actions/runs/36966722295) succeeded |
| CI on correction head | recorded when the workflows for this head finish |

Alembic head remains **`20260927_0027`**. No R5/R6 work.

### Score restoration

After D141 functional tests, full non-integration regression, and (pending) correction-head CI:

```text
U4 = 28 / 28
U5 = 13 / 13
Programme = 70.2 / 100
```

No new points.

---

## Remaining / R5 handoff

R4-targeted rows: **DONE**. Do not start R5 or R6 from this report.

R5 starts at roster/rollover restyle (D93–D100, D130) and Profile/Settings (U7).

R6 starts at Today / Calendar / Google (U6, T28–T32, T30).

Do not reopen R0–R3. Do not change Alembic. Do not reintroduce Constitution gating or historical duration products. Do not add a second lifecycle, speech, or source-review engine.
