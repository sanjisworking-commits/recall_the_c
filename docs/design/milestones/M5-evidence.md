# M5 — Account, Devices and Plans by tier · LOCAL / PRELIMINARY evidence

| Item | Value |
|---|---|
| Branch / PR | `pg-m5-account`, cut from `pg-m4-today` @ `e9ca1e4` (the M4 head under review); draft PR #240 (base `pg-m4-today`) — https://github.com/sanjisworking-commits/recall_the_c/pull/240 |
| Integration | none due: `origin/main` has no commit after `ea15591` (checked 2026-11-07); the M3 integration check on `945a67f` stands. PR #236 (`e73bd41`) is still outside the stack. |
| Checklist | `docs/design/milestones/M5.md` — owner decisions Q1–Q10 taken 2026-11-07, with the boundaries recorded in its §4 |
| Device-test clocks | `1b7d245` — three test-only edits (`tests/test_devices_m4c.py`); executed: `test_devices_m4a` + `m4b` + `m4c` **78 passed**, admin modules 51 passed (§2). No production code or device rule changed. |
| Candidate (rendered source) | `d2d6436` (templates, `playground/view.py`, `playground/access.py`, `playground/routes.py`, `auth/routes.py`, `devices/routes.py`, `web/app.py`, `web/entitlements.py`, the two guest copy modules, the three stylesheets; pins `main93` / `mob112` / `pg56`); tests `8aa3f0f` (`tests/test_account_family.py`, 61 tests; re-pins in `M5-test-changes.md`) |
| Flag | `PLAYGROUND_TIER_MODEL` stays `monthly` by default; read back under both models and under `ARTICLE_ENTITLEMENTS_ENABLED` off / on in the tests |
| Tooling | `…/m1r/tools/capture_m1r.py` (route probe); `…/m5/tools/readback_m5.py` (nine states × two models × five routes); dev launchers `playground-m5-<tier>[-choices]` (port 8922) |
| Status | LOCAL / PRELIMINARY — hosted checks NOT RUN (no deployment). Every row states **PASS on this SHA**, **carried forward from SHA**, **BLOCKED** or **NOT RUN**. "Ready for local acceptance review" is a review recommendation; the accepted-baseline row is added only on the owner's explicit acceptance. |

## 0. Baseline before edit — `e9ca1e4` (`m5/01-baseline-e9ca1e4/`)
Captures: guest and Free, five routes, 390 / 1280 × light / dark (42 rows; one navigation surface, one phone bar at 390, `hScroll` false, 0 low-contrast rows, 0 sub-44 px targets). Read-back (90 rows): the findings W1–W11 of `M5.md` §1, including the **CSRF gap verified by request** — `POST /settings/learning-plan` with no token and with a wrong token both returned 303 and changed the saved plan (pace → Auto, target → 7). The read-back tool's CSRF columns were corrected first (token looked for inside the form element) and the baseline regenerated; both forms read False.

## 1. What changed (scope diff)

| Area | Before (`e9ca1e4`) | After (`d2d6436`) | Decision |
|---|---|---|---|
| Profile identity meta | "Signed in with Google" | "RecallC Free · Constitution learning included" / "RecallC {Tier} · Playground included" (halted / expired keep the sign-in line) | Q1 |
| Profile Free card | "Playground / Subscribe to add Bare Acts to a monthly Playground." → `/billing/subscriptions` (`choices`: FREE chip, "View Playground plans") | **"No paid subscription"**; `monthly` body "Playground learning needs a paid plan. Plus and Pro add Bare Acts to your Playground."; `choices` keeps the choices sentence and FREE chip; CTA **"See plans ›"** → `/playground?stage=plans` | Q1 (boundary: no paid subscription, never no entitlement) |
| Profile order | identity, account, subscription (phone) | identity, subscription, account as direct grid children; desktop keeps two columns through grid areas | Q1 |
| Guest Profile | two duplicated blocks; inert Sign in / Report; `/login`; "Read mode."; `/laws/ndps` | one macro for both wrappers; "Continue with Google" → `/auth/google/start?next=%2Fprofile`; Report opens the report dialog; "Reading as a guest."; `/laws` | Q2 |
| Phone halted Profile / Settings | generic panel | the phone expired rules (marker substituted) | Q3 |
| Settings identity line | `access.status_line` ("Recall active") when the boundary is on, else "Signed in with Google" | shell label + sign-in method ("RecallC Free · Signed in with Google"); admin / grant status kept | Q4 |
| Settings Auto Plan note | "Part of unlocking every Article — your saved history is never deleted. Unlock every Article →" `/pricing` | "Auto Plan is part of Plus and Pro. Your saved history is never deleted. See plans ›" → plans stage | Q4 |
| `can_use_auto_plan` | never read the snapshot; `is_subscribed(user)` always False | also True for an active paid tier on the snapshot (not halted / paid-period-ended); Free, admin and grant outcomes unchanged | Q4 (boundary: no new restriction) |
| Settings CSRF | no check, no token (verified) | `require_csrf` on `POST /settings` and `POST /settings/learning-plan` (multiuser only; the single-user install is exempt); token in both forms | Q5 |
| Guest Settings | no STUDY card; inert identity / account / Report controls | the prototype's STUDY card; "Continue with Google" rows → `…?next=%2Fsettings`; Report opens the dialog | Q2 / DV-7 |
| Devices | "SECURITY / Your devices", prose empty state, no desktop rules | "ACCOUNT / Devices", lede "Your plan supports the Playground on up to 2 registered devices. A device is registered the first time you use the Playground on it while a paid plan is active.", REGISTERED cards with Remove / "Remove this device" (confirm step kept), designed empty state, desktop layout | Q6 (boundary: nothing promised to Free) |
| Plans stage | `<a aria-pressed>` cards; Continue `type="button"` with no handler; "Monthly. GST included. from ₹199." | one form: required radios `name="tier"` (label = card), Continue `type="submit"` → `/billing/subscriptions/create` (no subscription) or `/billing/subscriptions/change` (current subscriber), CSRF token; "Monthly. GST included."; current plan shown; Max never offered | Q7 / Q8 (boundaries: prices as configuration; change flow preserved) |
| `?stage=plans` | plans stage only for `not_subscribed` | also rendered for accounts that **can open** the Playground (Free under `choices`, paid holders); paused / expired / halted keep today's home and Resume / Manage flows | Q8 |
| Desktop guest gate | "Sign in" → `/login?next=<deep link>` | "Continue with Google" → `/auth/google/start?next=<quoted deep link>` (the return path preserved) | Q9 |
| "from ₹" | gate footer / plans footer | gone | Q7 |

Untouched: entitlement rules and the flag default, `subscriptions/*` (routes, service, catalogue, prices), the ended-subscription transitions, legacy Max benefits, the Free device policy, `/pricing`, the Learn claim path, the remaining "3 Articles" copy outside these screens.

## 2. Tests
| Run | Result |
|---|---|
| Device tests after the clock fix (`1b7d245`) | `test_devices_m4a` + `m4b` + `m4c`: **78 passed**; admin modules: 51 passed |
| New module `tests/test_account_family.py` | 61 collected; passed in the cohort run below |
| Account cohort + stack guards (`test_*profile_screen*`, `test_*settings_screen*`, `test_settings_phone`, `test_learning_plan_settings`, `test_devices_m4*`, `test_*playground_gate_screen*`, `test_guest_playground_screen6`, `test_phone_guest_playground_screen3`, `test_entitlement_m3b`, `test_playground_r3`, `test_free_law_choices`, `test_guest_shell_parity`, `test_shell_m1r`, `test_playground_r1`, `test_root_assets`, `test_today_family`, `test_browse_laws_family`, `test_multiuser_auth`, `test_multiuser_isolation`, `test_guest_first_ux`, `test_*add_screen*`, `test_act_head_m2r`) | 0 failed after the re-pins (the last cohort run before the final two guest-Profile pins: 8 failed / 665 passed / 64 skipped; those eight are the pins listed in `M5-test-changes.md` §D and pass on `8aa3f0f`) |
| Full suite on `8aa3f0f` (first run, as observed) | **8 failed, 4153 passed, 176 skipped** (9 min 04 s): the three device-baseline failures are gone; the eight are pins of the retired account copy outside the cohort (`M5-test-changes.md` §D2), re-pinned in `7d75338` — none a behaviour regression (two learning-session posts lacked the new CSRF token; the rest asserted the `/login` link, "Subscribe", "Active devices", the subscriber's home at `?stage=plans`, and the frozen gate-context keyset). |
| Full suite on `7d75338` (rerun, as observed) | **1 failed, 4160 passed, 176 skipped** (9 min 03 s): `tests/test_calendar_routes.py::test_multiuser_settings_drop_study_reminders` posted `/settings` without the new token; re-pinned in the commit that follows (`M5-test-changes.md` §D2). |
| Full suite on `6a807a0` (final, as observed) | **0 failed, 4161 passed, 176 skipped** (9 min 06 s). The three `tests/test_devices_m4c.py` failures that every branch of the stack carried since 2026-10-16 are gone; the "known baseline" wording is retired from this SHA on. GitHub's own run is reported in the PR as it executes (the unit step runs only on `[ci full]`, dispatch or a commit count divisible by 3). |

No behaviour test was weakened (`M5-test-changes.md`). Playwright-gated tests skip locally (not installed).

## 3. Gates
| Gate | Result |
|---|---|
| CSRF (Q5, boundary) | **PASS on `8aa3f0f`**: `test_f04_*` — valid token saves (303, plan changed), missing and invalid tokens → 403 with the plan unchanged, on both routes; the single-user install still posts without a token. |
| Mocked checkout (Q7, boundary) | **PASS on `8aa3f0f`**: the subscription service is replaced by a recorder; Free's form posts to `create` → 303 `/billing/subscriptions/checkout` with `start_subscription(user, "plus")` recorded once; without CSRF → 403 and nothing recorded; `tier=max` → `error=invalid_tier` and nothing recorded. No provider call, no live subscription, no charge. |
| Change flow (Q8, boundary) | **PASS on `8aa3f0f`**: a Plus subscriber's plans stage posts to `change` with the current plan shown; `change_plan(user, "pro")` recorded, `start_subscription` never called; Playground home untouched; paused / expired / halted do not reach the plans stage (read-back). |
| Device-test clocks (Q10) | **PASS on `1b7d245`** (executed; see §2). |

## 4. Route matrix (candidate; captures in `m5/02-candidate-d2d6436/`)

Probe facts on all 84 captured rows (guest 30, Free 30, Plus 20, halted 4): one navigation surface; one phone bar at 320 / 390 and none at 1280; `hScroll` false; 0 low-contrast rows (minimum composited ratio 5.28:1 phone, 5.33:1 desktop); 0 sub-44 px targets; every Tab stop outlined (`focusVisible` on all stops; e.g. Free Profile 14 / 14 at 390, 9 / 9 at 1280; Free Devices 13 / 13 and 14 / 14; plans stage 8 / 8 and 9 / 9).

| Route | Viewer | Widths × themes | Result | Status |
|---|---|---|---|---|
| `/profile` | guest | 320 / 390 / 1280 × light / dark | one block at both widths: "Reading as a guest.", Continue with Google → `…?next=%2Fprofile`, Browse the Bare Acts → `/laws`, Report button | **PASS on `d2d6436`** |
| `/profile` | Free | 320 / 390 / 1280 × light / dark | "RecallC Free · Constitution learning included"; "No paid subscription" + "See plans ›" → plans stage; phone order identity → subscription → account; desktop two columns | **PASS on `d2d6436`** |
| `/profile` | Plus | 390 / 1280 × light / dark | "RecallC Plus · Playground included"; ACTIVE card with roster usage and "Change plan"; Devices "1 of 2" after the Playground visit | **PASS on `d2d6436`** |
| `/profile` | halted | 390 / 1280 light | ON HOLD card "Playground learning is paused. Your progress is saved." + "Manage subscription"; the phone now styled by the halted rules; header "Payment retries have stopped" | **PASS on `d2d6436`** |
| `/profile` | Pro, Max, paused, pending, expired | read-back, both models | cards unchanged (Manage plan / Resume Playground / Manage subscription); identity meta per tier; `choices` differs only in the Free card sentence | **PASS on `d2d6436`** (read-back) |
| `/settings` | guest | 320 / 390 / 1280 × light / dark | STUDY card "Learning plan and revision calendar appear once you sign in."; identity and account rows "Continue with Google" → `…?next=%2Fsettings`; Report opens the dialog | **PASS on `d2d6436`** |
| `/settings` | Free, Plus | 320 / 390 / 1280 (Free) and 390 / 1280 (Plus) × light / dark | identity "RecallC Free / Plus · Signed in with Google"; plan form carries the token; Auto Plan controls live (entitlement boundary off in the dev launcher) | **PASS on `d2d6436`** |
| `/settings` | all nine, both flags | automated (`test_f03_*`) | with the boundary on: Free, paused, expired, halted see "Auto Plan is part of Plus and Pro. See plans ›"; Plus, Pro, Max, pending have the controls; with it off everyone has the controls (unchanged) | **PASS on `8aa3f0f`** |
| `/profile/security/devices` | guest | — | 303 to sign-in | **PASS on `d2d6436`** (read-back + test) |
| `/profile/security/devices` | Free | 320 / 390 / 1280 × light / dark | "Devices", lede, "0 of 2 devices", REGISTERED → "No devices registered yet." card; desktop laid out | **PASS on `d2d6436`** |
| `/profile/security/devices` | Plus | 390 / 1280 × light / dark | one REGISTERED card "Web browser · This device · Web · Last seen … · Registered …" with "Remove this device" (confirm step), "1 of 2 devices" — registered by the real Playground visit on the dev server | **PASS on `d2d6436`** |
| `/profile/security/devices` | isolation, remove, CSRF | automated (`test_f05_*`) | A never lists or removes B's device; remove without token → 403; remove with token → 303 and "Removed devices" | **PASS on `8aa3f0f`** |
| `/playground` gate | guest | 320 / 390 / 1280 × light / dark | desktop intro and phone macro each carry one "Continue with Google"; deep links return to the requested page (`test_f07`) | **PASS on `d2d6436`** |
| `/playground?stage=plans&tier=plus` | Free | 320 / 390 / 1280 × light / dark | radio cards Plus (checked) / Pro, "Monthly. GST included." (no "from ₹"), "Continue with Plus" submit → `create` | **PASS on `d2d6436`** |
| `/playground?stage=plans&tier=pro` | Plus | 390 / 1280 × light / dark | Plus "Current plan" (disabled card), Pro checked, "Switch to Pro" submit → `change` | **PASS on `d2d6436`** |
| `?stage=plans` | Free `choices`, Pro, Max, pending, paused, expired, halted | read-back | Free `choices` and the paid holders reach the stage (`change` form for holders; Max's current plan is not offered, as 5-7 requires); paused, expired, halted keep home | **PASS on `d2d6436`** (read-back) |
| Shell on every M5 route | all | probe rows | one surface, one phone bar, labels | carried forward from `d7d3c30`, re-probed here |

## 5. Visual and accessibility (§3.6)
- Prototype fidelity: Profile identity + SUBSCRIPTION + ACCOUNT order and copy direction per the 18 Oct frames with the decided wording; Devices per the prototype's title / lede / REGISTERED cards (empty state designed, not in the prototype); guest Settings STUDY card (DV-7); gate with one action (DV-9); plans stage as a selectable group (the desktop prototype has no plans frame — DV-14 resolved earlier). Accepted deviations: prototype "Free account" → the M1-R label "RecallC Free"; prototype "Create an account" never shown (Google-only).
- `hScroll` false at 320 / 390 / 1280 on every row; 44 px: every control ≥ 44 px (plan radio cards, Continue 48 px, Remove / Remove this device 44 px, Google rows 44 px); contrast ≥ 5.28:1 on every measured target; keyboard: the plan radios are reachable by Tab and arrow keys with the ring on the card (`:has(:focus-visible)`), every stop outlined; dark theme = palette tokens only (captures in both themes).
- NOT RUN: real 200 % zoom (320 px captures stand as supporting reflow evidence), automated accessibility scan, screen reader, hosted / staging, checkout completion (no billing keys; the create route's responses are asserted with a mocked service).

## 6. Decisions and boundaries (owner, 2026-11-07)
Q1–Q10 as recorded in `M5.md` §4, including: "No paid subscription" means no paid subscription, never no entitlement; no new Auto Plan restriction; CSRF verified by behaviour before and after; prices remain as current configuration, not a pricing decision; a subscriber's plans stage posts to the change flow; the clock fix recorded only on executed results. Record wording: Free = every Article with saved progress and "three permanent law choices per account" (the choices sentence appears only under `choices`).

## 7. Not run and open points
Hosted / staging checks; automated accessibility scan; screen reader; real 200 % zoom; checkout completion. Open points carried: `count_recent_replacements` returns 0 on a repository error (fails open; `devices/service.py:293-296`) — for the hardening programme; the remaining "3 Articles" / "Free Articles" copy in `learn.html`, `_locked_mode.html`, `browse_part.html`, `guest_modal.html`, `pricing.html`, `purchase_*.html` (M9 / B1 activation); the plans-stage title for paid holders still reads the Free gate's "Your RecallC account already includes the complete Constitution." (true, but a holder-specific title is a copy decision for M7-R / M8-R); the dev DB keeps a device registered across tier runs (the halted capture shows "1 of 2").
