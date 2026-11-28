# M8-S — Shared style: label contrast, back link, close control · milestone and evidence record

| Item | Value |
|---|---|
| Branch / PR | `pg-m8s-shared-style` (worktree `pg-m8s`), cut from the accepted M7b head `079257e`; draft PR against `pg-m7b-playground-learn` |
| Authority | M8-R plan approved by the owner on 2026-11-27 (after two forwarded reviews): M8-S is the first of two batches authorised for implementation. **The approval authorises implementation; it is not an acceptance of this batch** |
| Closes | W16 (label contrast) and W17 (desktop back link) of `M7.md` / `M7b.md`, within the bounds of §1; the Calendar dialog close control carried by `M6-evidence.md` |
| Baseline | `079257e` — `m8s/01-baseline-079257e/` |
| Candidate | source `ecf84ed`; tests `67c7101`, then the test corrections of §3.1 at `a226c7f` (tests only) — `m8s/02-candidate/` |
| Tooling | `m8/tools/probe_style_m8s.py`; `m7/tools/serve_populated_m7.py` |
| Flags | `PLAYGROUND_TIER_MODEL` `monthly` (default). No template, route, view or script changed |

**Status: candidate with local evidence, verified green on 2026-11-28 and presented for the owner's local acceptance (§8). Not accepted.** No merge, deployment or `choices` activation.

## 1. Bounds (from the approved plan)

Playground label tokens, in the three token blocks only; a Learn-scoped rule for hints whose colour comes from site-wide tokens; the back link; the sheet close control; cache pins. No layout, copy or component change. **The site-wide greys (`--mid`, `--faint`, `--muted` in `styles.css` and `mobile.css`) are not changed.** Colours must clear 4.5:1 with a margin; exclusions are limited to genuinely disabled controls and content that is not visible.

## 2. What changed

| Area | Change |
|---|---|
| Label greys, light | `--pg-muted`, `--pg-mid`, `--pg-faint` are one value, `#626262` (they were `#6b6b6b`, `#8f8f8d`, `#9a9a9a`). On the four Playground surfaces: 5.16:1 on the page colour, 6.10 on paper, 5.84 on the subtle surface, 5.44 on the wash. No grey lighter than this clears the margin on the page colour, so the hierarchy between the three now rests on size, case and letter-spacing |
| Label greys, dark | `--pg-mid` and `--pg-faint` are `#96948f` (they were `#8f8f8d` and `#7d7a73`): 5.25:1 on the subtle surface (the lightest dark surface), 5.80 on paper, 6.36 on the page colour; 5.98 and 5.51 on the site's own dark page and paper, where Playground labels sit on the account and billing pages. `--pg-muted` (`#a8a59e`) is unchanged |
| Fixed-dark surface | Unchanged (5.20–6.55:1 already) |
| Disabled controls | A new token `--pg-disabled` carries the old faint value (`#9a9a9a` light, `#7d7a73` dark, `#8f8f8d` fixed-dark). Only `.pg-btn:disabled` / `.pg-btn.is-disabled` and `.plus-sub-cta:disabled:not(.is-current)` use it. No template renders a link with `pg-btn is-disabled` |
| "Current plan" | Information, not an inert control: `.plus-sub-cta.is-current` keeps the label colour and now passes |
| Back link | The desktop rule `.pg-back { min-height: 32px }` is removed; the base rule's 44 px applies at every width. Manage laws, next month, the picker and the Act progress footer link move 12 px down their page at desktop |
| Learn hints | `.pg-learn .learn-hint`, `.learn-recite-hint`, `.learn-letters-hint`, `.learn-type-lede`, `.learn-test-lede`, `.learn-stem` take `--pg-muted`. They were coloured by the site-wide `--faint` (2.38:1) or `--muted` (4.51:1, no margin) |
| Learn practice-style switch | The unselected option (`.pg-learn .learn-letters-view-btn:not(.is-active)`) takes `--pg-muted`: it sits on the control's own track (`#e2e2e0`), where the site grey gave 4.11:1 |
| Calendar dialog close | `.cal-si-dialog-head button` is 44 × 44 and no longer shrinks (it was 36 × 36, squeezed to 33 × 36 beside a two-line title) |
| Pins | `playground.css` `pg60` → `pg61`; `styles.css` `main94` → `main95`; the Playground error page (`playground/errors.py`) loaded `pg11` and now loads the current pin |

### Two corrections to the plan's wording

1. The plan named `.pg-sheet-close` as the 33 × 36 px control. The baseline shows `.pg-sheet-close` already measures 44 × 44; the control M6 recorded is the Calendar dialogs' close button, `.cal-si-dialog-head button`, which lives in `styles.css`. That rule was changed instead, which is why `styles.css` and its pin are touched. The rule applies from 561 px; on the phone the Calendar has no such dialog (the probe found none to open).
2. The plan scoped a Learn rule to "hints". The baseline showed the stem and the two ledes in the same family, and the practice-style switch failing on its track; they are included under the same `.pg-learn` scope. Nothing outside `.pg-learn` is affected.

## 3. Tests

New `tests/test_shared_style_m8s.py` — 10 tests:

| ID | Pins |
|---|---|
| S01 | computed from the stylesheet: every label token ≥ **5.0:1** against every surface token of its theme (light, dark, fixed-dark), and against the site stylesheet's page and paper colours in light and dark; the three light greys are one value; none of the old failing values remains in a label token |
| S02 | `--pg-disabled` exists in all three blocks; every rule that uses it is a `:disabled` / `.is-disabled` selector; no template renders a link carrying `pg-btn` and `is-disabled` |
| S03 | "Current plan" keeps `--pg-mid`; only a disabled, non-current plan button takes the disabled colour |
| S04 | no rule gives `.pg-back` a minimum height other than the 44 px token, or a fixed height |
| S05 | `.pg-sheet-close` 44 × 44; `.cal-si-dialog-head button` 44 × 44, not shrinking |
| S06 | the Learn-scoped rules; the site-wide `.learn-hint` rule still reads `--faint` (the site token was not changed) |
| S07 | the error page's stylesheet pin equals the pin in `base.html` |

Re-pinned, none weakened: `playground.css?v=pg60` → `pg61` in 58 modules, `styles.css?v=main94` → `main95` in 32 modules, and the error page's `pg11` → `pg61` in `tests/test_playground_r3.py`.

| Run | SHA | Result |
|---|---|---|
| Template-, static-, Playground-, Learn-, account- and Calendar-related modules, local (stops at the first failure) | `67c7101` tree | 797 passed / 52 skipped / **1 failed** — the test named below |
| Full suite, local | `67c7101` | **4325 passed / 177 skipped / 1 failed** (965.5 s) |
| CI `workflow_dispatch` 46026253567, attempt 1 | `6668f50` (source and tests of `67c7101`) | **failure — pytest executed: 4323 passed / 164 skipped / 14 deselected / 2 failed** (1314.4 s) |
| CI `workflow_dispatch` 46030354524 — **control on the parent branch** | `079257e` | failure — pytest executed: 4314 passed / 164 skipped / 14 deselected / 1 failed (1311.7 s) |
| CI 46026253567, attempt 2 (re-run of the failed job) | `6668f50` | failure — pytest executed: **4324 passed / 164 skipped / 14 deselected / 1 failed** (1343.8 s): the date-dependent test only |
| **Full suite, local, after the corrections of §3.1** | `a226c7f` | **4326 passed / 177 skipped / 0 failed** (1845.8 s; run beside other suites, hence the time) |
| **CI `workflow_dispatch` 46151177318, after the corrections** | `a226c7f` | **success — pytest executed: 4325 passed / 164 skipped / 14 deselected / 0 failed** (1364.1 s) |

**The local failure, and the first of the two CI failures, is not caused by this batch.** `tests/test_phone_plus_calendar_screen5.py::test_phone_plus_calendar_overdue_done_and_future_constitution` seeds a Constitution revision seven days after the real current date and then reads the current month's Calendar. From the 24th of a 30-day month the revision falls in the next month and the assertion fails. It fails identically on the untouched M7b head `079257e` when run on 2026-11-27, and passed there on 2026-11-21. It is a date-dependent test, left as it is here and flagged for a separate fix; until it is fixed or the month turns, no run of the suite is fully green. Counting it, the batch adds 10 tests and changes no other local result: 4316 passed at M7b → 4325 passed + this 1. The control run on the untouched parent shows the same single failure in CI (4315 passed there on 2026-11-21 → 4314 + this 1).

**The second CI failure** is `tests/test_auto_roadmap.py::test_reconcile_does_not_persist_the_projected_theme_chain`: two reconciles of the automatic roadmap for a fixed date (2026-09-03) gave different fingerprints. It failed in attempt 1 of the run on this branch only. It passed in attempt 2 of the same run on the same commit, did not fail in the control run on the parent, nor locally on this branch (in the full suite, alone, under `TZ=UTC`, or under five hash seeds). This batch changes two stylesheets, two cache pins and the error page's pin; nothing in it is read by the roadmap. It is recorded as an intermittent failure of unknown cause — the same commit failed it once and passed it once — and flagged for investigation with the date-dependent test. No CI run of this batch is green: every one carries the date-dependent failure.

Skipped locally: the Playwright-gated screen tests and the Postgres integration tests; counted as skipped, not passed.

The three paragraphs above describe the runs of 2026-11-27 and are kept as written. Both failures were corrected on 2026-11-28 (§3.1); the intermittent one is no longer "of unknown cause".

### 3.1 Test corrections of 2026-11-28 (tests only; `d12b76c`, `a226c7f`)

On 2026-11-28 a second test of the same Calendar module began to fail. The whole suite was therefore run with the Python clock shifted to nine dates (`m8/tools/fakedate_plugin.py`; results in `m8/date-sweep/`): a control on 2026-09-16, month ends, a year end, the first of a month at 02:00 IST, a leap day and mid-2027. Besides the plugin's one artefact, the control run was clean and the other eight showed **21 date-dependent tests in 13 modules**. All are corrected; no assertion was removed or loosened and no source file changed.

| Tests | Depended on | Correction |
|---|---|---|
| `test_phone_plus_calendar_screen5.py` · `…overdue_done_and_future_constitution` | a review seeded seven days ahead being on the current month's page (fails from the 24th of a 30-day month) | the default page still proves "nothing due today"; the review is then looked for in its own day's list on the page of the month that holds it — a stricter check than "somewhere on the phone page" |
| `test_phone_plus_calendar_screen5.py`, `test_phone_expired_calendar_screen5.py` · `…mixed_due_today_keeps_constitution_today_card` | a fixed 3,500-character slice from today's list, which reaches into the today card late in a month (seen from the 28th) | the slice ends where that day's list ends (`_day_list`) |
| `test_halted_calendar_screen9.py`, `test_expired_calendar_screen9.py` · `…canonical_month_uses_live_state` | tomorrow's scheduled chip being in the current month (fails on a month's last day) | on that day the test also reads next month's page, so the chip's link is still checked instead of skipped |
| 13 `[expired]` cases in `test_account_family.py`, `test_browse_laws_family.py`, `test_calendar_family.py`, `test_playground_family.py`, `test_today_family.py`, `test_phone_halted_calendar_screen5.py` | the shared "expired" period ending 80 days before the *real* date while the suite pins the entitlement clock to 2026-09-16 (`tests/conftest.py`): from 2026-12-06 the period is no longer in that clock's past | the shared periods (`test_browse_laws_family.py::STATES`, and the default period of `test_account_family.py`) are measured from the pinned clock |
| `test_entitlement_m3a.py`, `test_entitlement_m3b.py` · `test_legacy_active_…` | a legacy grant ending 300 days after a fixed 2026-09-16 but resolved against the real clock (fails from mid-July 2027) | the grant ends 300 days after the real clock those tests resolve with |
| `test_admin_users.py` · `test_grant_creates_row_and_audit_atomically` | a fixed end date, 2027-03-01, which the route refuses once it is past | an end date 120 days ahead |
| `test_auto_roadmap.py` · `test_reconcile_does_not_persist_the_projected_theme_chain` — **the intermittent failure, now explained** | the fingerprint compared before and after a second reconcile includes each day's `updated_at`. A reconcile rewrites the window with a new one-second stamp, so the test fails whenever the two reconciles fall either side of a second boundary — the CI log of attempt 1 shows exactly that, `…15:37:43` against `…15:37:44`, with identical content | the test compares the anchor and the window's content; the stamp stays in the fingerprint for the three tests that assert *nothing was written*. Reproduced on every run by making each write stamp one second later than the last (`m8/tools/tickstamp_plugin.py`: 1 failed before, 42 passed after) |

After the corrections the full suite was run again at five of the simulated dates on the corrected tree: no failure at any of them besides the plugin's artefact (`m8/date-sweep/date-sweep.md`).

**Limits.** The sweep covers those dates and two times of day on a machine in Asia/Kolkata; it does not prove the suite free of date dependence at every date, in every zone, or where the database's own clock decides. `test_auto_roadmap.py` and `test_admin_users.py` are identical on `main`, so `main` has the same two defects (the intermittent roadmap failure, and the admin grant test from 2027-03-02) until these commits reach it; the other corrected modules exist only in this stack. The suite still runs on two clocks — entitlements and the roster pinned to 2026-09-16, everything else on the real date; that arrangement is the root of most of these and is not changed here.

## 4. Probe results — baseline `079257e` against the candidate

Per page, summed over 390 and 1280 px in both themes. "Failing" counts text under 4.5:1 that is neither inside a disabled control nor invisible. "Min" is the lowest ratio of ordinary text on the page.

| Page | Failing, baseline → candidate | Min, baseline → candidate | Back link at 1280 |
|---|---|---|---|
| Playground home | 5 → **0** | 2.74 → 5.16 | — |
| Manage laws | 8 → **0** | 2.38 → 5.16 | 78 × 32 → 78 × 44 |
| Next month | 4 → **0** | 2.74 → 5.16 | 78 × 32 → 78 × 44 |
| Remove | 2 → **0** | 3.24 → 5.80 | — |
| Act progress | 19 → **0** | 2.74 → 5.03 | footer link 78 × 32 → 78 × 44 (head link already 44) |
| Section picker (BNS) | 2139 → **0** | 2.38 → 4.71 | 93 × 32 → 93 × 44 |
| Learn `read` | 14 → **0** | 2.38 → 5.16 | — |
| Learn `recite` | 14 → **0** | 2.38 → 4.51 | — |
| Learn `cloze`, `type` | 12 → **0** each | 2.74 → 4.51 | — |
| Learn `letters` | 14 → **0** | 2.74 → 4.51 | — |
| Learn `test` | 12 → **0** | 2.74 → 5.16 | — |
| Completion pages | 0 → 0 | 6.55 → 6.55 | — |
| Add sheet (Plus, Free, signed out) | 8 → **0** | 3.24 → 5.80 | close 44 × 44 → 44 × 44 |
| Gate, Free under `monthly` | 2 → **0** | 3.24 → 5.02 | — |
| Gate, signed out | 5 → **0** | 2.69 → 5.02 | — |
| Billing | 4 → **0** ("Current plan" was exempt as disabled; it now passes) | 2.38 → 4.51 | — |
| Playground error page | 2 → **0** | 2.74 → 5.16 | — |
| Calendar upgrade sheet (1280) | 0 → 0 | 5.33 → 6.10 | close 33 × 36 → **44 × 44** |
| Calendar editor dialog (1280) | 1 → 1 (see §5) | 3.32 → 3.32 | close 36 × 36 → **44 × 44** |

No horizontal scroll and no script exception on any row. The phone picker in the dark theme — 4.10:1 at baseline for "SECTION n" and "Not started" — is 5.80:1.

**Where the minimum is 4.51 or 4.71:** that text is coloured by the site-wide `--muted` (`#6b6b6b`), not by a Playground token. It passes 4.5:1 without the margin this batch gives the Playground tokens.

**Exempt readings on the candidate, by selector:**

| Selector | Page | Why |
|---|---|---|
| `span.visually-hidden` | Act progress | clipped to one pixel: text for assistive technology |
| `span.learn-cloze-word.is-blank` | Learn `cloze`, dark theme | drawn in the colour of its own blank until revealed |

No reading on the candidate is exempt as "disabled".

Frames (baseline and candidate of the same name): home 390 and 1280 light; Manage laws 1280 light; Act progress 1280 light; picker 390 light, 1280 light, 390 dark; Learn `read` and `recite` 390 light; Add sheet 390 light; Free gate 1280 light; and the candidate's Calendar upgrade sheet at 1280.

## 5. Open — not fixed here, not a pass

The plan's pass condition was "no text under 4.5:1 on these pages". It is met on every Playground page above. **It is not met on Profile and Devices**, and the probe found failures on two Calendar surfaces while measuring the close control. All of it is coloured by site-wide tokens or rules in `styles.css` / `mobile.css`, outside this batch's bounds, and is unchanged from the baseline:

| Page | Reading | Source |
|---|---|---|
| Profile (Plus and Free), light | `p.pg-eyebrow` "SUBSCRIPTION" 2.74:1; `p.muted` identity line 3.24:1 | `styles.css` `[data-signed-in-profile] .pg-eyebrow` and `.muted` (site `--mid`) |
| Profile, dark | "Sign out" and "Delete account…" 2.54:1 (`#b42318` on the dark paper) | site destructive colour, not re-set for the dark theme |
| Profile, phone | provider badge "G" 3.2:1 | brand-coloured letter in a badge |
| Devices, phone, light | lede, "REGISTERED", "This device", device meta 2.74–3.24:1 | `styles.css` / `mobile.css` `[data-devices-page] …` (site `--mid`) |
| Calendar month, phone | past-day numbers 1.66:1 (light) and 1.88:1 (dark); weekday letters 2.74:1; "TODAY · NOTHING DUE" 3.24:1; the note under it 2.38:1 | `mobile.css` `.cal-m-*`, `.revisions-*`. `M6.md` records no low-contrast text on Calendar; these readings come from this probe's measurement of the page body at 390 px on 2026-11-27 and should be confirmed before either statement is relied on |
| Calendar editor dialog, dark | "Save & schedule" 3.32:1 (white on teal) | `styles.css` `.cal-si-save` |

Target sizes under 44 px, also unchanged and outside this batch: Profile "Change plan" / "See plans ›" 38 px tall at 1280; the Free gate's "View Playground plans" 42 px tall at 1280; the Calendar editor's fields and buttons 40–43 px tall.

A separate correction of the site-wide greys would close most of these; it touches every page of the application and is not proposed here.

## 6. Evidence this batch supersedes

Accepted screenshots of the Playground pages (M7a, M7b and the Playground rows of earlier milestones) were taken with the old label colours and, at desktop width, the 32 px back link. **Their label colour and, on Manage laws, next month, the picker and Act progress at desktop, the vertical position of everything below the back link (12 px lower) are superseded by this batch.** They are not retaken beyond the frames listed in §4; layout, copy and behaviour in them stand. Pages that do not use these tokens — the shell, the Bare Act head, Browse, Today, the Calendar grid, the completion pages — are carried unchanged, except the Calendar dialogs' close control.

## 7. Not run and limitations

- Hosted comparison: NOT RUN (staging blocked, `M5-staging-prep.md`).
- **Browser zoom: NOT RUN.** Automated accessibility scan, screen reader: NOT RUN.
- Playwright-gated screen tests: skipped locally (not installed).
- Live speech; Google Calendar connect / disconnect: NOT RUN (not touched).
- The probe measures the colour of text against the first opaque background behind it. It does not measure text over images or gradients, focus indicators, or non-text contrast.
- One Plus account under `monthly`, a Free account under `monthly`, a Free account under `choices` (Calendar sheet only) and a signed-out visitor were probed. The paused, halted and expired Playground pages use the same tokens and were not probed here; they are in M8-Ra's matrix.
- Devices was probed with one registered device; Profile and billing with the Plus fixture.
- Of M7b's route list, the Act progress page of a law with no progress (`law-new`) was not probed; of M7a's, the Manage-laws Add and re-add confirms were probed only through the Act's Add sheet. They use the same tokens.

## 8. Review for local acceptance (2026-11-28)

Prepared for the owner's decision. Green runs support acceptance; they are not acceptance.

**Scope against the approved plan (M8-S bounds).**

| Approved item | Delivered | Evidence |
|---|---|---|
| Label tokens changed only in the three token blocks; every label token ≥ 5.0:1 on every surface of its theme, by a computed test | yes | S01; §4 |
| The three light greys agree | yes — one value, `#626262` | S01 |
| Exclusions limited to genuinely disabled controls and content that is not visible | yes — `--pg-disabled` only on `:disabled` / `.is-disabled`; two exempt readings, both non-visible content; "Current plan" passes instead of being exempt | S02, S03; §4 |
| Learn hints through a `.pg-learn`-scoped rule; site-wide greys untouched | yes, and wider within `.pg-learn` than "hints" (correction 2 of §2) | S06 |
| Back link 44 px at desktop | yes | S04; §4 |
| Sheet close control 44 × 44 | the Playground sheet's close was already 44 × 44; the 33 × 36 control was the Calendar dialogs' close, in `styles.css`, and that was changed (correction 1 of §2) | S05; §4 |
| Cache pins, including the error page's | yes | S07 |
| No layout, copy or component change | no template, route, view or script changed | the diff of `ecf84ed` |

**Two departures from the plan's wording, for the owner to accept or reject with the batch:** `styles.css` and its pin are touched (one rule, the Calendar dialog close); the Learn-scoped rule covers the stem, two ledes and the practice-style switch as well as the hints. Both are inside `.pg-learn` or the one named control.

**Verification on exact commits.**

| Check | Commit | Result |
|---|---|---|
| Full suite, local | `a226c7f` | 4326 passed / 177 skipped / 0 failed |
| CI, pytest executed | `a226c7f` (run 46151177318) | 4325 passed / 164 skipped / 14 deselected / 0 failed |
| Probes, frames, target sizes (§4) | taken on source `ecf84ed` at `67c7101` | **carried**: no file under `src/` has changed since `ecf84ed` (`git diff ecf84ed a226c7f -- src` is empty); the commits since are tests, records and evidence |
| Earlier runs (§3) | `67c7101`, `6668f50` | superseded as results; kept as the record of the two failures and their cause |

The pull-request head adds this record and the sweep evidence to `a226c7f`; it changes no test and no source file.

**Retained as open — acceptance would not close them:** every row of §5 (Profile, Devices, phone Calendar, the Calendar editor's Save button, all from site-wide tokens; the targets under 44 px); the superseded frames of §6, not retaken.

**Retained as NOT RUN:** every entry of §7 — hosted comparison, browser zoom, accessibility scan, screen reader, the Playwright-gated tests, live speech, Google Calendar connect / disconnect — and the probe's own limits.

**What local acceptance would mean:** this head becomes the local baseline for Playground label colours, the back link and the two close controls. It would not be hosted acceptance, a merge, a deployment or an activation of `choices`.

## 9. Owner sign-off

None recorded. Sign-off is recorded only against the owner's direct answer.
