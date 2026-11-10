# M4 — Today by tier · LOCAL / PRELIMINARY evidence

| Item | Value |
|---|---|
| Branch / PR | `pg-m4-today`, cut from `pg-m3-browse-laws` @ `6186863` (the signed-off M3 head); draft PR (base `pg-m3-browse-laws`) |
| Integration | none due: `origin/main` has no commit after `ea15591` (checked 2026-11-07); the M3 integration check on `945a67f` stands. The overflow fix PR #236 (`e73bd41`) is still outside the stack. |
| Checklist | `docs/design/milestones/M4.md` (PROPOSED 2026-11-07); owner decisions Q1–Q7 taken 2026-11-07 (§6) |
| Flag | `PLAYGROUND_TIER_MODEL` stays `monthly` by default; Today renders identically under `choices` (§0 read-back) |
| Tooling | `…/m1r/tools/capture_m1r.py` (route probe); `…/m4/tools/readback_m4.py` (nine states × two models × first run / after one real Learn → Done, through the app's TestClient); `…/m4/tools/serve_populated_m4.py` (serves a populated Today — one completed Article, two clauses due — for signed-in captures); dev launchers `playground-m4-<tier>[-choices]` (port 8920) |
| Candidate (rendered source) | `3e06fb0` (template, context, both stylesheets, pins `main92` / `mob111`) + the 320 px greeting follow-up that follows it; tests `2c26faf` (`tests/test_today_family.py`, 39 tests; nine re-pointed assertions; 32 pin files) |
| Status | LOCAL / PRELIMINARY — hosted checks NOT RUN (no deployment). Every row states **PASS on this SHA**, **carried forward from SHA**, **BLOCKED** or **NOT RUN**. **Accepted as the reusable local Today baseline on candidate `3e06fb0` / tests `2c26faf` (owner-forwarded review, 2026-11-10; §9).** |

## 0. Baseline before edit — `6186863` (`m4/01-baseline-6186863/`)

Captures (reduced policy; light + dark; Tab trails on every light row): guest `/dashboard` 390 / 1280 (`guest/`), Free first run 390 / 1280 (`free/`), Free populated 390 / 1280 (`free-populated/`, served by `serve_populated_m4.py`). Probe facts on all 12 rows: one navigation surface, one phone bar at 390, `hScroll` false, 0 overlaps, 0 sub-44 px shell targets (the M1-R shell, carried forward from `d7d3c30`); Free rows show `RecallC Free`.

Read-back (`readback/readback.md`, `.json`; 34 rows = guest + 8 signed-in states × first run / after one Article, × `monthly` / `choices`):

| Finding | Detail |
|---|---|
| Populated Today already matches the prototype | phone and desktop: "Good morning, Sanjay." + date + streak chip; ring `0/1`, "1 revision due", "Start revision →"; Today's path with the "DAY 1 REVISION" eyebrow and the node CTA; desktop two columns (`.dash-top` grid at ≥ 900 px). After one real Learn → Done with nothing due: "Nothing to review today" + "Plan my day →" (plan prompt), progress strip, Next up rail. |
| Desktop first run is unstyled | guest and every signed-in tier at 1280: bare text, inline links, no cards (W1 in `M4.md`). Phone first run is styled. |
| Guest copy and routes | "Welcome." / "Reading as a guest", no date line; "Nothing due today"; hero CTA `/login?next=/dashboard`; sign-in card "Sign in to save 3 Articles to Recall for free — progress, streaks and revision schedules need an account." + Sign in → `/login?next=/dashboard` (legacy list hit: `/login`, `3 Articles`, `save 3`). |
| Signed-in first run | identical for Free, Plus, Pro, Max, paused, pending, expired, halted: "Welcome, Sanjay." + "Your account is ready. Here's a good first step." + date line + `0-day streak`; hero + 2 starter rows + plan / tour rows; no access chip, no "Free plan" row (dead branches, W3). Header: `RecallC Free` / `Plus` / `Pro` / `Max`, paused → `RecallC Free`, pending → `RecallC Plus`, expired → "Your Playground is paused", halted → "Payment retries have stopped"; markers `data-plus-today` / `data-expired-today` / `data-halted-today` as before. |
| Tier models | 0 differences between `monthly` and `choices` on any row. |
| Gate-style check | `POST /learn/article-1-clause-1/done` → 200 for every signed-in state (no claim prompt), Today leaves first run and shows the plan prompt. |

Carried forward: shell `d7d3c30`; Browse / Laws `55da7eb`; Act head and Add `3ad4b82` / `bd9347a`; Browse / Schedules `ea15591` (overflow PASS with `e73bd41`).

## 1. What changed (scope diff)

| Area | Before (`6186863`) | After (`3e06fb0`) | Decision |
|---|---|---|---|
| Desktop first run | bare text and inline links at ≥ 561 px for guests and every signed-in tier (every `.dash-firstrun-*` rule was phone-only) | cards from 561 px; at ≥ 900 px the hero sits left and the starter rows, plan / tour rows (signed-in) or sign-in card (guest) stack in a second column, the same grid as the populated Today; guest Today takes the signed-in page treatment (`data-guest-today`) | Q5 |
| Guest greeting | "Welcome." + subtext "Reading as a guest", no date, "?" avatar | "Good morning." over "{date} · Reading as a guest", empty dashed ring | Q2 |
| Guest hero | "Nothing due today"; CTA → `/login?next=/dashboard` | "Nothing due yet."; CTA → `/browse` (guest note kept) | Q3 |
| Guest sign-in card | "Sign in to save 3 Articles to Recall for free — progress, streaks and revision schedules need an account." + Sign in → `/login?next=/dashboard` | "Sign in to save your progress. Your daily revisions, streak and path will show here." + one **Continue with Google** → `/auth/google/start?next=%2Fdashboard` (`data-guest-gate-google`) | Q3 / 5-11 / D20 |
| Signed-in greeting | "Welcome, {name}." on first run, "Good morning, {name}." after | unchanged (owner: brand-new accounts keep Welcome) | Q2 |
| Free chip / plan row | dead branches on `access.is_free` ("Free · n/3 Articles"; "You're on the Free plan · 3 Articles free · See plans") | removed; the admin / grant status chip stays | Q4 |
| Lapse banner | "Your n Free Articles are still yours … Revisions for the other Articles are paused" | "Every Article, your progress and your revision schedule stay yours. Playground revisions are paused, not deleted — they resume where they were." | Q4 |
| Path header (desktop) | "Today's path" | "Today's path … {done} of {total} reviewed" when a goal exists; hidden on phone; never on first run | Q6 |
| Populated Today, Playground nodes, expired / halted bindings, Plan my day, completion banner, strip, Next up | unchanged | unchanged (screen-04 / screen-08 modules green) | — |
| Tier bodies | identical across tiers | identical across tiers; no banner, price or allowance sentence added | Q7 |

Untouched: `web/entitlements.py`, the entitlement snapshot and flag, `auth/routes.py`, Learn and the claim path, Calendar, Profile / Settings, `/pricing`, `purchase_result.html`, `_locked_mode.html`, `learn.html` (D20 remainder → M9 / B1 activation), the Playground home.

## 2. Tests
| Run | Result |
|---|---|
| New module `tests/test_today_family.py` (F01, F02 × 8 + identity, F03, F04 × 18 + lapse wording, F06, F07 × 6, F08 × 2) | 39 passed |
| Today cohort + stack guards (`test_dashboard`, `test_guest_first_ux`, `test_multiuser_auth`, `test_multiuser_isolation`, the twelve `*today_screen*` modules, `test_root_assets`, `test_browse_laws_family`, `test_shell_m1r`, `test_playground_r1`, `test_act_head_m2r`) | 221 passed, 14 skipped (Playwright, not installed locally) |
| Full suite on the candidate | **3 failed (the known `tests/test_devices_m4c.py` baseline: `test_existing_registered_device_stays_allowed_at_churn_cap`, `test_admin_reset_does_not_erase_replacement_history`, `test_admin_clears_replacement_lock_with_audit`), 4097 passed, 176 skipped** (8 min 48 s; run on `2c26faf` before the CSS-only `dc50253`) |

| GitHub run on head `e9ca1e4` (run 42355818704; the unit step executed because the commit count 909 is divisible by 3) | **3 failed, 4096 passed, 163 skipped, 14 deselected** (17 min 32 s). The three failures are the documented `tests/test_devices_m4c.py` baseline (`test_admin_clears_replacement_lock_with_audit`, `test_admin_reset_does_not_erase_replacement_history`, `test_existing_registered_device_stays_allowed_at_churn_cap`); the job therefore concludes `failure` as on every branch of the stack. Recorded separately from the local run above. |

Count difference between the local and the GitHub run, verified by collected IDs (2026-11-07): both collect 4276 tests. CI runs `pytest -m "not integration"` and deselects the 14 `integration`-marked tests; run locally those 14 give 1 passed (`tests/test_docling_integration.py::test_docling_extract_smoke`) and 13 skipped (`test_free_law_choices_postgres.py` ×10, `test_subscription_billing_postgres.py` ×3 — `PLAYGROUND_PG_TEST_URL` not set). Hence local 4097 = CI 4096 + the docling smoke test, and local 176 skipped = CI 163 + the 13 Postgres skips.

No behaviour test was weakened (`M4-test-changes.md`).

## 3. Gate — the Free promise reaches Today (M4-F08)
**PASS on `2c26faf` under `monthly` and `choices`** (automated, production units): a Free account completes Learn → Done on four distinct Articles (`article-1-clause-1`, `article-2`, `article-3`, `article-4-clause-1`); every `/learn/{unit}/done` returns 200 with no `claim_required` and no `?claim=1` redirect; the progress rows carry `next_revision`; `build_dashboard_context(as_of=<fourth Article's due date>)` on the same engine leaves first run, counts the due unit and lists the fourth Article on Today's path as a `review` node; a fresh sign-in sees ≥ 4 Articles started on the strip; no "3 Articles" copy anywhere in the body.

## 4. Route matrix (candidate; captures in `m4/02-candidate-3e06fb0/`)

Probe facts on every captured row: one navigation surface; one phone bar at 320 / 390 and none at 720 / 1280; `hScroll` false; 0 low-contrast rows (minimum composited ratio 5.28:1 light phone, 5.33:1 light desktop, 5.93:1 dark); 0 sub-44 px shell targets (`smallTargets` empty on every row; the `RecallC Free` text label is not a control). Tab trails (light rows): guest 320 → 12 / 12 outlined, 390 → 12 / 12 (the 13th stop is `body`), 720 / 1280 → 8 / 8; Free first run 12 / 12, 12 / 12, 9 / 9, 9 / 9; Free populated 9 / 9 at 390, 8 / 8 at 1280 — every stop outlined `2px solid` ink.

| Route | Viewer | Widths × themes | Result | Status |
|---|---|---|---|---|
| `/dashboard` first run | guest | 320 / 390 / 720 / 1280 × light / dark | "Good morning." + "{date} · Reading as a guest" + ring; "Nothing due yet."; hero CTA → `/browse`; guest note; Good places to begin (2 rows); sign-in card with one Google action; two columns at 1280; theme toggle stays on the greeting row at 320 | **PASS on `3e06fb0` + follow-up** |
| `/dashboard` first run | Free | 320 / 390 / 720 / 1280 × light / dark | "Welcome, {name}." + date + streak; hero; starter rows; Set a learning plan · Take the two-minute tour; two columns at 1280; label `RecallC Free` | **PASS on `3e06fb0`** |
| `/dashboard` populated | Free (two clauses due, one Article done) | 390 / 1280 × light / dark | ring `0/1`, "1 revision due", path node "DAY 1 REVISION · Article 14"; desktop path header "0 of 1 reviewed"; phone unchanged | **PASS on `3e06fb0`** |
| `/dashboard` first run + after one Article | Plus, Pro, Max, paused, pending | read-back, both models | identical body to Free (labels `RecallC Plus` / `Pro` / `Max` / `Free` / `Plus`; `data-plus-today` on Plus only); after one Learn → Done: "Nothing to review today" + Plan my day, strip, Next up | **PASS on `3e06fb0`** (read-back) |
| `/dashboard` | expired, halted | read-back, both models | same body; header status "Your Playground is paused" / "Payment retries have stopped"; `data-expired-today` / `data-halted-today`; Playground bindings carried by `test_expired_today_screen8` / `test_halted_today_screen8` / the phone screen-04 modules | **PASS on `3e06fb0`** (read-back + tests) |
| `/dashboard` Playground due / New nodes, bound CTAs | Plus, expired, halted | automated | unchanged | carried forward (screen-04 / screen-08 modules green on `2c26faf`) |
| Shell on `/dashboard` | all | probe rows above | one surface, one phone bar, labels | carried forward from `d7d3c30` (M1-R), re-probed here |
| Tier models | all nine states | read-back | 0 differences `monthly` vs `choices` | **PASS on `3e06fb0`** |

## 5. Visual and accessibility (§3.6)
- Prototype fidelity: guest Today matches the 18 Oct frames (`proto_phone_today_guest.png`, `proto_desk_today_guest.png`) in structure and copy direction — greeting, date line with the guest note, "Nothing due yet.", one primary action; the app keeps its working starter rows (§0.2a, Q1) and uses the hero CTA for "Browse" rather than a second button. Signed-in first run keeps the accepted content, now in the prototype's card language on desktop. Populated Today unchanged; the desktop counter follows the prototype's "n of m reviewed".
- Accepted deviations: the prototype's "STATE Due / All done" toggle is not built (no working counterpart, Q6); the prototype's guest card copy "Sign in to save 3 Articles…" is superseded by the owner's copy (D20).
- `hScroll` false at 320 / 390 / 720 / 1280 (every row); 44 px: every control ≥ 44 px (CTA 48 px desktop / 52 px phone, Google action 44 px, starter rows 52–58 px, phone tabs 60 px); contrast ≥ 5.28:1 on every measured target; focus rings on every Tab stop; dark theme = palette tokens only (captures in both themes).
- NOT RUN: real 200 % zoom, automated accessibility scan, screen reader (the browser pane could not composite frames this session). The 320 px captures (guest and Free, light and dark, `hScroll` false, theme toggle kept on the greeting row) provide supporting reflow evidence; they are not a zoom test.

## 6. Decisions (owner, 2026-11-07, via the M4 question set)
Q1 keep and restyle the accepted dashboard content (guests keep the starter rows, not the plan / tour rows); **Q2 brand-new accounts keep "Welcome, {name}."**, everyone else and guests follow the prototype greeting, date line on every cohort; Q3 one Continue-with-Google action, hero CTA → `/browse` for guests, "Nothing due yet."; Q4 dead Free chip and plan row deleted, lapse banner reworded to the all-Articles rule; Q5 two-column desktop first run at ≥ 900 px; Q6 "n of m reviewed" counter yes, STATE toggle no; Q7 no tier body on Today. Record wording: Free = every Article with saved progress and "three permanent law choices per account" (no allowance copy is printed on Today).

## 7. Not run
Hosted / staging checks; automated accessibility scan; screen reader; real 200 % zoom; a Plus populated capture with a Playground node (read-back row + existing screen tests instead, reduced policy).

## 8. Browser-profile files committed in `490f930` (removed in `f181079`)

The capture tool writes a throwaway headless-Chrome profile beside its output. The first M4 commit picked up ten files from three such profiles; `f181079` removed them from the index and added `.chrome-profile*/` to `.gitignore`. They remain reachable in the branch history unless it is rewritten (a force-push, which this session's policy blocked — owner decision before merge).

Paths (under `docs/design/proto-comparison-2026-10-19/m4/01-baseline-6186863/`), from `git ls-tree -r --name-only 490f930`:

| Path | Bytes | What the recorded inspection found |
|---|---|---|
| `guest/.chrome-profile/Local State` · `free/.chrome-profile/Local State` · `free-populated/.chrome-profile/Local State` | 4118 · 4116 · 4120 | Chrome preferences JSON (96 leaf keys: metrics, variations, tab stats, profile info-cache). Keys whose names suggest secrets were read: `local.password_hash_data_list` = `[]`; `profile.info_cache.Default.gaia_id` = `""`, `user_name` = `""`, `name` = `"Your Chrome"`, `signin.with_credential_provider` = `false`; `session_id_generator_last_value` and `signin.active_accounts_last_emitted` are Chrome counters. No string value matches `http`, `127.0.0.1`, `localhost`, `8920` or `8921`. |
| `guest/…/Variations` · `free/…/Variations` · `free-populated/…/Variations` | 85 each | two metric keys: `user_experience_metrics.stability.exited_cleanly`, `variations_crash_streak`. |
| `free/.chrome-profile/Breadcrumbs` | 526 | one text line: `0:00:04 Tab1 RenderProcessGone`. |
| `guest/.chrome-profile/Default/Reporting and NEL-journal` | 21032 | a SQLite rollback journal, not a database (it does not open as one): printable strings ≥ 4 characters extracted — only the schemas of `meta`, `nel_policies`, `reporting_endpoints`, `reporting_endpoint_groups`; zero occurrences of `127.0.0.1`, `localhost`, `8920`, `http`. |
| `free/…/Reporting and NEL-journal` · `free-populated/…/Reporting and NEL-journal` | 0 | empty. |

Not present in the commit: `Cookies`, `Login Data`, `Web Data`, `Sessions/`, `Network/`, any `.ldb` file.

Method: `git ls-tree -r --name-only 490f930` for the paths and `git cat-file -s` for sizes; the JSON files parsed in full with every leaf key listed and the name-flagged values read; the text files read; the binary journal identified by its header and searched by printable-string extraction. **Limit:** string extraction from a binary journal cannot prove the absence of every sensitive byte sequence. **Conclusion: no credentials, tokens or session data found by the recorded inspection.**

## 9. Owner sign-off (owner-forwarded review, 2026-11-10)

| Item | Record |
|---|---|
| Decision | **Accepted** as the reusable local baseline for Today (`/dashboard`): the §4 route matrix, §3 gate and §5 visual / a11y rows on candidate `3e06fb0` (+ `dc50253`) with tests `2c26faf`. Reuse by SHA; reopen only when the Today template, context, their stylesheets or a shared dependency changes the rendering or behaviour. The shared shell, Browse and Today screenshot matrices are not repeated for later milestones (owner, 2026-11-10). |
| Executed runs | local 3 / 4097 / 176 on `2c26faf` (the three = the device baseline of the time); GitHub 42355818704 on `e9ca1e4`: 3 / 4096 / 163 / 14 deselected (§2). The device baseline is retired from `1b7d245` (M5) onward; this record keeps its lines as observed. |
| Browser-profile files | §8 stands (no credentials, tokens or session data found by the recorded inspection); a history rewrite before merge remains the owner's decision. |
| NOT RUN | real 200 % zoom (320 px captures as supporting reflow evidence), automated accessibility scan, screen reader, hosted / staging. |
| Separate decisions | merge, deployment and entitlement activation. |

