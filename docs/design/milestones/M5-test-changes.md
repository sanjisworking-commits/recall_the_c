# M5 — test changes (PR #240, `pg-m5-account`)

Every existing test touched by M5, with its reason. No behaviour test was weakened: assertions that pinned retired copy (the Free card "Subscribe", "Read mode.", "Part of unlocking every Article", the `/login` links, "from ₹"), inert controls (the guest Sign in / Report buttons, the Continue button without a form) or the phrases the owner has since decided ("See plans ›", "No plan yet" → "No paid subscription", "Constitution learning included") were replaced by the assertion of the decided behaviour at the same strength. Commits: device clocks `1b7d245`; source `d2d6436`; tests `8aa3f0f`.

## A. Device-test clocks (commit `1b7d245`)
`tests/test_devices_m4c.py` — three edits: `inspect_current_device(..., now=NOW)` ×3 in `test_existing_registered_device_stays_allowed_at_churn_cap`; `ensure_current_device(..., now=NOW)` in `test_admin_reset_does_not_erase_replacement_history`; `monkeypatch.setattr("constitution_memorizer.devices.repository._utc_now", lambda: NOW)` in `test_admin_clears_replacement_lock_with_audit`. Reason: the fixture seeds replacement rows at `NOW` (2026-09-16) while those three reads ran on the real clock against a rolling 30-day window. Executed: `test_devices_m4a` + `m4b` + `m4c` 78 passed; admin modules 51 passed. No production code changed.

## B. Mechanical asset re-pins (commit `8aa3f0f`)
`styles.css?v=main92 → main93`, `mobile.css?v=mob111 → mob112`, `playground.css?v=pg55 → pg56` in `base.html` and 59 test modules (string replacement only; the list is `git show 8aa3f0f --stat -- tests` minus the files below).

## C. Learning-plan POSTs carry the CSRF token (Q5)
`tests/test_learning_plan_settings.py` — every `client.post("/settings/learning-plan", data={...})` (and the `client_b` variant) now sends `"csrf_token": <client>.cookies.get("rtc_csrf")`, as the Profile and Devices tests already did; the two copy pins on the Free note move from "Part of unlocking every Article" to "Auto Plan is part of Plus and Pro." Behaviour under test is unchanged: Free cannot enable Auto Plan, admin and grant holders can, preview does not mutate.

## D. Account screens re-pointed to the decided copy and markup

| File | Was | Now | Decision |
|---|---|---|---|
| `test_signed_in_profile_screen10.py`, `test_phone_signed_in_profile_screen6.py` | Free card "Subscribe to add Bare Acts to a monthly Playground." / `>Subscribe<` → `/billing/subscriptions`; identity "Signed in with Google"; `MOCK_SCREEN_COPY` forbade "RecallC Free · Constitution learning included" | "Playground learning needs a paid plan. Plus and Pro add Bare Acts to your Playground." / `>See plans ›<` → `/playground?stage=plans`; identity "RecallC Free · Constitution learning included"; the phrase leaves the forbidden list | Q1 |
| `test_plus_profile_screen10.py`, `test_phone_plus_profile_screen6.py`, `test_expired_profile_screen10.py`, `test_halted_profile_screen10.py`, `test_phone_expired_profile_screen6.py` | the Free control case asserted `>Subscribe<`; Plus identity "Signed in with Google" | `>See plans ›<`; "RecallC Plus · Playground included" | Q1 |
| `test_guest_profile_screen10.py`, `test_phone_guest_profile_screen6.py` | "Read mode.", lede "…unlock the Constitution learning experience.", Sign in → `/login?next=/profile` (desktop) / inert button (phone), Report `div` / inert button, Browse the Bare Acts → `/laws/ndps`; `GUEST_PROFILE_SIGNIN_HREF` and `data-report-open` in the phone forbidden tuple; "buttons are handlerless in source" | the constants in `web/guest_profile.py` carry the decided copy ("Reading as a guest.", "Sign in to save your progress. Reading stays free for everyone.", `/auth/google/start?next=%2Fprofile`, `/laws`); both wrappers render one macro with a Google anchor and a `data-report-open` button; "block has real actions in source"; "desktop sign-in uses google" | Q2 |
| `test_signed_in_settings_screen11.py`, `test_phone_signed_in_settings_screen7.py` | identity "Signed in with Google" and "RecallC Free" forbidden in the body / source | "RecallC Free · Signed in with Google"; "RecallC Free" allowed (the shell label) | Q4 |
| `test_phone_plus_settings_screen7.py` | status `== "Signed in with Google"`; `INVENTED` forbade "See plans" / "No plan yet" | `== "RecallC Plus · Signed in with Google"`; decided phrases removed | Q4 |
| `test_expired_settings_screen11.py`, `test_halted_settings_screen11.py`, `test_phone_expired_settings_screen7.py`, `test_plus_settings_screen11.py` | `LOCKED_COPY` "Part of unlocking every Article — your saved history is never deleted." + `href="/pricing"` "Unlock every Article →"; `INVENTED` forbade "See plans" / "No plan yet" | "Auto Plan is part of Plus and Pro. Your saved history is never deleted." + `href="/playground?stage=plans"` "See plans ›"; decided phrases removed; the phone-block CSS slice stops at the M5 marker so the halted copy and the plans rules outside it are not counted | Q4 / Q3 / Q7 |
| `test_phone_expired_settings_screen7.py` | `name="csrf_token"` **not** in the plan form | `name="csrf_token"` in the plan form | Q5 |
| `test_phone_guest_settings_screen7.py`, `test_settings_phone.py` | identity / account Sign in and Report "handlerless" buttons; `data-report-section="Settings"` forbidden for guests | identity and account rows are `Continue with Google` anchors → `/auth/google/start?next=%2Fsettings`; the guest Report opens the report dialog | Q2 |
| `test_devices_m4b.py` | "Your devices" / "Active devices" on the Devices page | `>Devices</h1>` / `>Registered</p>` (the Profile's own "Your devices" row is unchanged) | Q6 |
| `test_signed_in_playground_gate_screen7.py`, `test_phone_signed_in_playground_gate_screen3.py` | cards as links `?stage=plans&tier=`, `aria-pressed` / `aria-current`; Continue `type="button"` with no handler, absent without a selection; no `<form>` and no `/billing/subscriptions` in the gate; Plus with `?stage=plans` got home | radios `name="tier"` (`required checked` when selected); Continue `type="submit"` always in the one form, "Continue" until a tier is chosen; `action="/billing/subscriptions/create"`; no `href="/billing/subscriptions` link; Plus gets the plans stage with `data-pg-plan-form="change"` and its current plan; tests renamed `…_submits_the_plans_form`, `…_without_selection` | Q7 / Q8 |
| `test_guest_playground_screen6.py`, `test_phone_guest_playground_screen3.py` | desktop `>Sign in<` → `/login?next=/playground`; the phone block must not contain the desktop href | `GUEST_PG_SIGNIN_HREF` (`web/guest_playground_intro.py`) is the Google href; desktop `>Continue with Google<`; the phone block carries the same single action once | Q9 |
| `test_entitlement_m3b.py` | `/login?next={path}` on the guest gate for deep links | `/auth/google/start?next={quote(path)}` — the return path is preserved | Q9 |
| `test_playground_r3.py` | `/billing/subscriptions` absent from the plans page | no `href="/billing/subscriptions` link (the form action is the route) | Q7 |

## D2. Pins outside the account cohort, found by the first full-suite run (commit `7d75338`)

| File | Was | Now | Decision |
|---|---|---|---|
| `test_learning_sessions.py` (2 posts) | `POST /settings/learning-plan` without a token | the token is sent | Q5 |
| `test_phone_plus_playground_screen3.py` | a subscriber's `?stage=plans&tier=pro` renders home | the plans stage with `data-pg-plan-form="change"` and the current plan; home asserted on `/playground` | Q8 |
| `test_playground.py` | guest gate carries `/login?next=/playground` | `/auth/google/start?next=%2Fplayground` | Q9 |
| `test_playground_r5.py` | Free card `cta_label == "Subscribe"`; Devices page "Active devices" | `"See plans ›"` with title "No paid subscription"; `>Registered</p>` | Q1 / Q6 |
| `test_request_perf_breakdown.py` | `_T8_GATE_CONTEXT_KEYS` frozen set | + `csrf_token`, `guest_google_href` (the plans form's token and the guest intro's deep-link action) | Q7 / Q9 |
| `test_calendar_routes.py::test_multiuser_settings_drop_study_reminders` (found by the rerun) | two multiuser `POST /settings` without a token | the token is sent; the 303 save and the 400 for an invalid frequency are unchanged | Q5 |

## E. New module (commit `8aa3f0f`)
`tests/test_account_family.py` — 61 tests: F01 Profile × (2 models + 8 states); F02 guest Profile / Settings; F03 Settings identity and Auto Plan × 8 states × 2 entitlement flags + the Free / Plus / halted predicate check; F04 CSRF (valid / missing / invalid on both routes; single-user exempt); F05 Devices (guest redirect, empty state, populated through `ensure_current_device`, isolation, CSRF on remove, remove); F06 plans form (create with a mocked service, Max refused by the route, change for a subscriber, reachable under `choices`); F07 gate (deep-link Google action × 2, no "from ₹" × 8); F08 protected POSTs (guest; signed-in × 8) and tier-model parity for guest / expired / halted; template sweep.

## F. Tools
`m5/tools/readback_m5.py`: the CSRF columns read the token inside the form element (`csrf_in_plan_form`, `csrf_in_settings_form`), not anywhere later on the page; the baseline read-back was regenerated with the corrected tool before the candidate run.
