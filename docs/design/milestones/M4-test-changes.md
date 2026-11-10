# M4 — test changes (PR #238, `pg-m4-today`)

Every existing test touched by M4, with its reason. No behaviour test was weakened: each assertion that pinned the retired guest copy (the "save 3 Articles" promise, the two `/login?next=/dashboard` links, the "?" avatar, the "Welcome." guest greeting) was replaced by the assertion of the owner-decided behaviour at the same strength (commit `2c26faf`).

## A. Mechanical asset re-pins
`styles.css?v=main91 → main92`, `mobile.css?v=mob110 → mob111` in `base.html` and 32 test modules (string replacement only; the list is `git show 2c26faf --stat -- tests`).

## B. Guest Today assertions re-pointed (nine assertions, six files)

| File | Test | Was | Now | Decision |
|---|---|---|---|---|
| `tests/test_guest_first_ux.py` | `test_guest_dashboard_progress_and_settings` | "Sign in to save 3 Articles to Recall for free"; `href="/login?next=/dashboard"` | "Sign in to save your progress."; one `href="/auth/google/start?next=%2Fdashboard"`; no `/login?next=/dashboard` | Q3 / 5-11 / D20 |
| | `test_logout_signed_out_page` | "Sign in to save 3 Articles…" after logout | "Sign in to save your progress." | D20 |
| | `test_first_run_guest_branch` | `>?</span>` avatar; CTA `href="/login?next=/dashboard"`; "Sign in to save 3 Articles…" | `dash-avatar-guest` ring and no `?`; "Good morning." + "· Reading as a guest"; "Nothing due yet."; CTA `href="/browse"`; the new card copy; exactly one Google action in `<main>`; no "3 Articles" / `/login` in `<main>` (the shell's own Sign in is M1-R's) | Q2 / Q3 / Q5 |
| | `test_sign_in_from_first_run_returns_to_it` | `href="/login?next=/dashboard"` is the link the guest follows | the Google action is | Q3 |
| `tests/test_multiuser_auth.py` | `test_logout_clears_session` | "Sign in to save 3 Articles…" | "Sign in to save your progress." | D20 |
| `tests/test_multiuser_isolation.py` | `test_logout_a_does_not_invalidate_b` | same phrase for A (present) and B (absent) | same shape with the new phrase | D20 |
| `tests/test_phone_expired_today_screen4.py`, `tests/test_phone_plus_today_screen4.py`, `tests/test_phone_signed_in_today_screen4.py` | the "guest … stay separate" tests | `"Welcome." in guest` | `"Good morning." in guest` and `"· Reading as a guest" in guest` | Q2 |

Unchanged by design: every signed-in pin on "Welcome, Sanjay." (Q2, owner: brand-new accounts keep Welcome), "Nothing due today" for signed-in first run, the screen-04 / screen-08 populated-state, Playground-node, expired / halted and CSS-scope assertions, `test_dashboard.py::…new_user_context` (greeting "Welcome, Priya.").

## C. New module (commit `2c26faf`)
`tests/test_today_family.py` — 39 tests: F01 guest Today; F02 signed-in first run × 8 states + identical bodies for Free / Pro / Max / paused / pending; F03 desktop layout hooks and phone rules untouched; F04 no superseded copy × 9 states × 2 models × 2 phases + lapse wording; F06 path counter; F07 guest permissions + tier-model parity × 5 states; F08 gate × 2 models. Imports the shared fixtures of `test_browse_laws_family.py` (nine account states, both tier models) and the `_make_due` fixture of `test_signed_in_today_screen8.py` for the counter row only.

## D. Tools
`docs/design/proto-comparison-2026-10-19/m4/tools/readback_m4.py`: `starter_rows` now counts `class="dash-firstrun-item"` exactly (the baseline run's column had counted the two `is-compact` plan / tour rows instead; the baseline's other columns are unaffected and the row is re-read on the candidate).
