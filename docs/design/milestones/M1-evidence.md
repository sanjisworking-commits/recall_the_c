# M1 — Guest shell parity · LOCAL / PRELIMINARY evidence

Status: **LOCAL/PRELIMINARY.** Produced from a local run of this branch; it does
**not** close hosted acceptance. Staging still serves the frozen `5d89fbd`
(deployment `32971cbf…`); a staging deployment of this branch needs the
owner's separate authorisation (checklist §7). Merge is not authorised.

| | |
|---|---|
| Checklist | `docs/design/milestones/M1.md` on PR #218 (accepted 2026-10-19 with DV-20 and DV-21 in scope) |
| Baseline | `cursor/playground-220d` @ `5d89fbdfb6c712a998ce1fdbc4a7756fee8677b8` |
| Candidate | `pg-m1-guest-shell` @ `5a03044c1bdbdec21f9581cc0bd8e3db162be894` |
| Local server | the Playground dev launcher pointed at this worktree (fake Google auth, throwaway DB, Free-tier seeded user), port 8912 |
| Capture tool | `docs/design/proto-comparison-2026-10-19/m1/tools/capture_local.py` (headless Chrome Google Chrome 155.0.8059.82 over CDP, DPR 1, fonts awaited, 0.6 s settle; sign-in via the dev provider, cookies injected in-process and never written) |
| Prototype references | 18 Oct exports, hashes in M1.md Appendix A.1; states `viewer=guest` / `viewer=signedIn` via `make_wrappers.py` |
| Evidence folder | `docs/design/proto-comparison-2026-10-19/m1/` — manifests with SHA-256 of every PNG (baseline and candidate, both viewers, both widths, light and dark, plus the responsive set); committed PNGs are the light captures; the complete original set is in the archive named in that folder's README |

## 1. What changed (scope diff)

Source files, candidate vs `5d89fbd` (only the four files the checklist allows):

```
src/constitution_memorizer/web/static/mobile.css   |  25 +--
 .../web/static/playground.css                      |  13 +-
 src/constitution_memorizer/web/static/styles.css   | 109 +++-------
 src/constitution_memorizer/web/templates/base.html | 232 +++------------------
 4 files changed, 77 insertions(+), 302 deletions(-)
```

- `base.html` — viewport meta allows zoom (`maximum-scale=1, user-scalable=no` removed); the per-screen guest flags (`guest_browse_index`, `guest_laws_index`, `guest_bareact_head`, `guest_playground_intro`, `guest_profile`, `guest_settings`, `guest_chrome`) are replaced by one `guest_shell` flag and five `shell_*` active-state flags; one brand link; one guest top-nav branch (Today/Browse/Playground/Calendar/Profile with `aria-current`); the three guest account menus become one `<a class="nav-signin" href="/login">Sign in</a>`; one guest phone bar (`data-guest-phone-tabs`) replaces the four per-screen bars and the legacy `mobile-tabbar is-guest`; the footer Settings link is shown to guests too (the guest account menu that linked it is gone); DV-20: the account-slot subtitle renders on every shared-shell page (the page-flag chain is kept, with a snapshot-aware fallback). Signed-in nav, account menu and tab-bar branches are untouched. Asset pins bumped: `main86→main87`, `mob105→mob106`, `pg48→pg49`.
- `styles.css` — removed: `.guest-pill` rules, the dead `[data-guest-*]` brand/nav/account selectors, the header-grid and `.PrimaryTabs--top { display:none }` overrides on the guest intro and the signed-in gate (DV-21), and the five per-screen `.account-menu-btn-status { display:none }` rules (DV-20). Added: desktop `.site-header > .nav-signin` button style; `body.is-guest .mobile-tabbar { display:none }` at ≥561 px (no duplicate nav at 561–720); generic ≤720 px tab bar uses `grid-auto-flow: column` so it fits four or five tabs; `body.is-guest .page-wrap` gets the same 64 px bottom clearance signed-in pages already had.
- `mobile.css` — removed the `.mobile-tabbar.is-guest` rules; added `body.is-guest[data-mscreen="settings"|"search"] .mobile-tabbar { display:grid }` after the generic hide rule (signed-in Settings/Search keep their frozen bar-less behaviour).
- `playground.css` — the hard-gate rule no longer hides `.PrimaryTabs--top` (DV-21); it hides phone bars except the shared guest bar, and the guest Add sheet page keeps its bar hidden as before; two dead `[data-guest-*-phone-tabs]` selectors removed.

Not changed: any page body, route, redirect, auth, entitlement, billing, device, data or test fixture; `app.py`.

## 2. Tests

Baseline (`5d89fbd`, same environment, 2026-10-19): `3 failed, 3849 passed, 163 skipped, 1 deselected` — the three failures are `tests/test_devices_m4c.py` (`test_existing_registered_device_stays_allowed_at_churn_cap`, `test_admin_reset_does_not_erase_replacement_history`, `test_admin_clears_replacement_lock_with_audit`), pre-existing and unrelated to the shell (device replacement-limit logic).

Candidate (`5a03044c1bdbdec21f9581cc0bd8e3db162be894`): `3 failed, 3903 passed, 163 skipped, 1 deselected, 18 warnings in 385.96s (0:06:25)`
Failures: `FAILED tests/test_devices_m4c.py::test_existing_registered_device_stays_allowed_at_churn_cap`, `FAILED tests/test_devices_m4c.py::test_admin_reset_does_not_erase_replacement_history`, `FAILED tests/test_devices_m4c.py::test_admin_clears_replacement_lock_with_audit`

Skips are Playwright-backed browser tests (`pytest.importorskip("playwright")`); Playwright is not installed in this environment, so those remain **NOT RUN** here, not passed. Browser behaviour was verified instead through the headless-Chrome captures and DOM probes below.

New: `tests/test_guest_shell_parity.py` (54 tests): five-tab guest bar with exactly one current tab on 14 routes; four tabs when `PLAYGROUND_ENABLED=false`; guest bar rendered visible on Settings and Search (CSS order); five-link guest top nav with one Sign in button and no legacy chrome; identical header shell across routes; Landing/Login/auth-surface exceptions unchanged; guest gates (`/calendar`, devices, Playground) unchanged; footer functions and Settings route kept; viewport allows zoom; signed-in top nav and account-slot subtitle on 16 routes (DV-20); signed-in Free phone bar unchanged; DV-21 CSS no longer hides the desktop nav; asset pins bumped.

Existing tests changed (each change is the old shell contract giving way to the accepted one; no behaviour test was weakened to pass):

| File | Change |
|---|---|
| 56 screen-test files | asset pin strings `pg48→pg49`, `main86→main87`, `mob105→mob106` (mechanical, as every previous pin bump) |
| `test_guest_browse_screen2.py` | header now has one `nav-signin` and a brand link; guest account-menu assertions replaced by Sign-in-button assertions; phone bar is `data-guest-phone-tabs` |
| `test_guest_first_ux.py`, `test_guest_laws_screen3.py`, `test_guest_bareact_screen4.py` | guest account menu → Sign in button; brand link |
| `test_guest_playground_screen6.py` | gate header now carries the full nav with Playground current (DV-21) |
| `test_guest_profile_screen10.py` | profile header is the shared five-link shell with Profile current; no Home/Search/Learn |
| `test_phone_guest_playground_screen3.py`, `test_phone_guest_profile_screen6.py`, `test_phone_guest_bare_act_screen1.py`, `test_phone_signed_in_profile_screen6.py` | per-screen bar attributes → `data-guest-phone-tabs` |
| `test_phone_guest_settings_screen7.py` | "no five-tab bar on guest Settings" inverted to the accepted "shared bar visible" |
| `test_playground_m6.py` | "guest nav is not the five product tabs" inverted to the accepted five-tab bar behind the gate |
| `test_phone_signed_in_playground_gate_screen3.py` | hard-gate hide rule text (DV-21) |
| `test_signed_in_settings_screen11.py` | mock-copy check scoped to `<main>` because the header now carries "Free account" (DV-20) |

## 3. Route matrix — guest (frozen → candidate)

Columns show the DOM probe per capture; a bold value is what changed. "PNG identical" compares SHA-256 of the two captures; `/` (Landing) differs only by its entrance animation frame — its shell probe is unchanged and the page is a declared exception.

| Route | W | Theme | Status chain | Screen key | Top nav | Phone bar | Current | Account slot | Zoom | PNG identical |
|---|---|---|---|---|---|---|---|---|---|---|
| `/` | 390 | light | / 200 | None | hidden | none | — | — | free | no |
| `/` | 390 | dark | / 200 | None | hidden | none | — | — | free | no |
| `/` | 1280 | light | / 200 | None | hidden | none | — | — | free | yes |
| `/` | 1280 | dark | / 200 | None | hidden | none | — | — | free | yes |
| `/browse` | 390 | light | /browse 200 | browse | hidden | legacy 4-tab → **5-tab** | — → **/browse** | ? Guest Not signed in Settings S → **Sign in** | locked → **free** | no |
| `/browse` | 390 | dark | /browse 200 | browse | hidden | legacy 4-tab → **5-tab** | — → **/browse** | ? Guest Not signed in Settings S → **Sign in** | locked → **free** | no |
| `/browse` | 1280 | light | /browse 200 | browse | visible | none | /browse | ? Guest Not signed in → **Sign in** | locked → **free** | no |
| `/browse` | 1280 | dark | /browse 200 | browse | visible | none | /browse | ? Guest Not signed in → **Sign in** | locked → **free** | no |
| `/browse/part/iii` | 390 | light | /browse/part/iii 200 | part | hidden | legacy 4-tab → **5-tab** | — → **/browse** | Sign in | locked → **free** | no |
| `/browse/part/iii` | 390 | dark | /browse/part/iii 200 | part | hidden | legacy 4-tab → **5-tab** | — → **/browse** | Sign in | locked → **free** | no |
| `/browse/part/iii` | 1280 | light | /browse/part/iii 200 | part | visible | none | — → **/browse** | Sign in | locked → **free** | no |
| `/browse/part/iii` | 1280 | dark | /browse/part/iii 200 | part | visible | none | — → **/browse** | Sign in | locked → **free** | no |
| `/browse/article/14` | 390 | light | /browse/article/14 200 | article | hidden | none | — | Sign in | locked → **free** | yes |
| `/browse/article/14` | 390 | dark | /browse/article/14 200 | article | hidden | none | — | Sign in | locked → **free** | yes |
| `/browse/article/14` | 1280 | light | /browse/article/14 200 | article | visible | none | — → **/browse** | Sign in | locked → **free** | no |
| `/browse/article/14` | 1280 | dark | /browse/article/14 200 | article | visible | none | — → **/browse** | Sign in | locked → **free** | no |
| `/laws` | 390 | light | /laws 200 | laws | hidden | legacy 4-tab → **5-tab** | — → **/browse** | ? Guest Not signed in Settings S → **Sign in** | locked → **free** | no |
| `/laws` | 390 | dark | /laws 200 | laws | hidden | legacy 4-tab → **5-tab** | — → **/browse** | ? Guest Not signed in Settings S → **Sign in** | locked → **free** | no |
| `/laws` | 1280 | light | /laws 200 | laws | visible | none | /browse | ? Guest Not signed in → **Sign in** | locked → **free** | no |
| `/laws` | 1280 | dark | /laws 200 | laws | visible | none | /browse | ? Guest Not signed in → **Sign in** | locked → **free** | no |
| `/laws/ndps` | 390 | light | /laws/ndps 200 | bareact | hidden | 5-tab | /browse | ? Guest Not signed in Settings S → **Sign in** | locked → **free** | yes |
| `/laws/ndps` | 390 | dark | /laws/ndps 200 | bareact | hidden | 5-tab | /browse | ? Guest Not signed in Settings S → **Sign in** | locked → **free** | yes |
| `/laws/ndps` | 1280 | light | /laws/ndps 200 | bareact | visible | none | /browse | ? Guest Not signed in → **Sign in** | locked → **free** | no |
| `/laws/ndps` | 1280 | dark | /laws/ndps 200 | bareact | visible | none | /browse | ? Guest Not signed in → **Sign in** | locked → **free** | no |
| `/laws/uapa` | 390 | light | /laws/uapa 200 | bareact | hidden | legacy 4-tab → **5-tab** | — → **/browse** | Sign in | locked → **free** | no |
| `/laws/uapa` | 390 | dark | /laws/uapa 200 | bareact | hidden | legacy 4-tab → **5-tab** | — → **/browse** | Sign in | locked → **free** | no |
| `/laws/uapa` | 1280 | light | /laws/uapa 200 | bareact | visible | none | — → **/browse** | Sign in | locked → **free** | no |
| `/laws/uapa` | 1280 | dark | /laws/uapa 200 | bareact | visible | none | — → **/browse** | Sign in | locked → **free** | no |
| `/laws/bns` | 390 | light | /laws/bns 200 | bareact | hidden | legacy 4-tab → **5-tab** | — → **/browse** | Sign in | locked → **free** | no |
| `/laws/bns` | 390 | dark | /laws/bns 200 | bareact | hidden | legacy 4-tab → **5-tab** | — → **/browse** | Sign in | locked → **free** | no |
| `/laws/bns` | 1280 | light | /laws/bns 200 | bareact | visible | none | — → **/browse** | Sign in | locked → **free** | no |
| `/laws/bns` | 1280 | dark | /laws/bns 200 | bareact | visible | none | — → **/browse** | Sign in | locked → **free** | no |
| `/laws/mtp` | 390 | light | /laws/mtp 200 | bareact | hidden | legacy 4-tab → **5-tab** | — → **/browse** | Sign in | locked → **free** | no |
| `/laws/mtp` | 390 | dark | /laws/mtp 200 | bareact | hidden | legacy 4-tab → **5-tab** | — → **/browse** | Sign in | locked → **free** | no |
| `/laws/mtp` | 1280 | light | /laws/mtp 200 | bareact | visible | none | — → **/browse** | Sign in | locked → **free** | no |
| `/laws/mtp` | 1280 | dark | /laws/mtp 200 | bareact | visible | none | — → **/browse** | Sign in | locked → **free** | no |
| `/laws/ndps/section/8` | 390 | light | /laws/ndps/section/8 200 | bareactsection | hidden | legacy 4-tab → **5-tab** | — → **/browse** | Sign in | locked → **free** | no |
| `/laws/ndps/section/8` | 390 | dark | /laws/ndps/section/8 200 | bareactsection | hidden | legacy 4-tab → **5-tab** | — → **/browse** | Sign in | locked → **free** | no |
| `/laws/ndps/section/8` | 1280 | light | /laws/ndps/section/8 200 | bareactsection | visible | none | — → **/browse** | Sign in | locked → **free** | no |
| `/laws/ndps/section/8` | 1280 | dark | /laws/ndps/section/8 200 | bareactsection | visible | none | — → **/browse** | Sign in | locked → **free** | no |
| `/playground` | 390 | light | /playground 200 | playground | hidden | 5-tab | /playground | Sign in | locked → **free** | yes |
| `/playground` | 390 | dark | /playground 200 | playground | hidden | 5-tab | /playground | Sign in | locked → **free** | yes |
| `/playground` | 1280 | light | /playground 200 | playground | hidden → **visible** | none | — → **/playground** | Sign in | locked → **free** | no |
| `/playground` | 1280 | dark | /playground 200 | playground | hidden → **visible** | none | — → **/playground** | Sign in | locked → **free** | no |
| `/playground?stage=plans` | 390 | light | /playground?stage=plans 200 | playground | hidden | 5-tab | /playground | Sign in | locked → **free** | yes |
| `/playground?stage=plans` | 390 | dark | /playground?stage=plans 200 | playground | hidden | 5-tab | /playground | Sign in | locked → **free** | yes |
| `/playground?stage=plans` | 1280 | light | /playground?stage=plans 200 | playground | hidden → **visible** | none | — → **/playground** | Sign in | locked → **free** | no |
| `/playground?stage=plans` | 1280 | dark | /playground?stage=plans 200 | playground | hidden → **visible** | none | — → **/playground** | Sign in | locked → **free** | no |
| `/playground?stage=plans&tier=plus` | 390 | light | /playground?stage=plans&tier=plus 200 | playground | hidden | 5-tab | /playground | Sign in | locked → **free** | yes |
| `/playground?stage=plans&tier=plus` | 390 | dark | /playground?stage=plans&tier=plus 200 | playground | hidden | 5-tab | /playground | Sign in | locked → **free** | yes |
| `/playground?stage=plans&tier=plus` | 1280 | light | /playground?stage=plans&tier=plus 200 | playground | hidden → **visible** | none | — → **/playground** | Sign in | locked → **free** | no |
| `/playground?stage=plans&tier=plus` | 1280 | dark | /playground?stage=plans&tier=plus 200 | playground | hidden → **visible** | none | — → **/playground** | Sign in | locked → **free** | no |
| `/playground/laws/uapa/add` | 390 | light | /playground/laws/uapa/add 200 | playground | hidden | none | — | Sign in | locked → **free** | yes |
| `/playground/laws/uapa/add` | 390 | dark | /playground/laws/uapa/add 200 | playground | hidden | none | — | Sign in | locked → **free** | yes |
| `/playground/laws/uapa/add` | 1280 | light | /playground/laws/uapa/add 200 | playground | hidden → **visible** | none | — → **/playground** | Sign in | locked → **free** | no |
| `/playground/laws/uapa/add` | 1280 | dark | /playground/laws/uapa/add 200 | playground | hidden → **visible** | none | — → **/playground** | Sign in | locked → **free** | no |
| `/dashboard` | 390 | light | /dashboard 200 | today | hidden | legacy 4-tab → **5-tab** | — → **/dashboard** | Sign in | locked → **free** | no |
| `/dashboard` | 390 | dark | /dashboard 200 | today | hidden | legacy 4-tab → **5-tab** | — → **/dashboard** | Sign in | locked → **free** | no |
| `/dashboard` | 1280 | light | /dashboard 200 | today | visible | none | — → **/dashboard** | Sign in | locked → **free** | no |
| `/dashboard` | 1280 | dark | /dashboard 200 | today | visible | none | — → **/dashboard** | Sign in | locked → **free** | no |
| `/calendar` | 390 | light | /calendar 303 → /login?next=%2Fcalendar&reason=default 200 | None | hidden | none | — | — | locked | yes |
| `/calendar` | 390 | dark | /calendar 303 → /login?next=%2Fcalendar&reason=default 200 | None | hidden | none | — | — | locked | yes |
| `/calendar` | 1280 | light | /calendar 303 → /login?next=%2Fcalendar&reason=default 200 | None | hidden | none | — | — | locked | yes |
| `/calendar` | 1280 | dark | /calendar 303 → /login?next=%2Fcalendar&reason=default 200 | None | hidden | none | — | — | locked | yes |
| `/profile` | 390 | light | /profile 200 | account | hidden | 5-tab | /profile | Sign in | locked → **free** | yes |
| `/profile` | 390 | dark | /profile 200 | account | hidden | 5-tab | /profile | Sign in | locked → **free** | yes |
| `/profile` | 1280 | light | /profile 200 | account | visible | none | /profile | Sign in | locked → **free** | no |
| `/profile` | 1280 | dark | /profile 200 | account | visible | none | /profile | Sign in | locked → **free** | no |
| `/settings` | 390 | light | /settings 200 | settings | hidden | none → **5-tab** | — → **/profile** | Sign in | locked → **free** | no |
| `/settings` | 390 | dark | /settings 200 | settings | hidden | none → **5-tab** | — → **/profile** | Sign in | locked → **free** | no |
| `/settings` | 1280 | light | /settings 200 | settings | visible | none | — → **/profile** | Sign in | locked → **free** | no |
| `/settings` | 1280 | dark | /settings 200 | settings | visible | none | — → **/profile** | Sign in | locked → **free** | no |
| `/profile/security/devices` | 390 | light | /profile/security/devices 303 → /login?next=%2Fprofile%2Fsecurity%2Fdevices&reason=default 200 | None | hidden | none | — | — | locked | yes |
| `/profile/security/devices` | 390 | dark | /profile/security/devices 303 → /login?next=%2Fprofile%2Fsecurity%2Fdevices&reason=default 200 | None | hidden | none | — | — | locked | yes |
| `/profile/security/devices` | 1280 | light | /profile/security/devices 303 → /login?next=%2Fprofile%2Fsecurity%2Fdevices&reason=default 200 | None | hidden | none | — | — | locked | yes |
| `/profile/security/devices` | 1280 | dark | /profile/security/devices 303 → /login?next=%2Fprofile%2Fsecurity%2Fdevices&reason=default 200 | None | hidden | none | — | — | locked | yes |
| `/tables` | 390 | light | /tables 200 | tables | hidden | legacy 4-tab → **5-tab** | — → **/browse** | Sign in | locked → **free** | no |
| `/tables` | 390 | dark | /tables 200 | tables | hidden | legacy 4-tab → **5-tab** | — → **/browse** | Sign in | locked → **free** | no |
| `/tables` | 1280 | light | /tables 200 | tables | visible | none | — → **/browse** | Sign in | locked → **free** | no |
| `/tables` | 1280 | dark | /tables 200 | tables | visible | none | — → **/browse** | Sign in | locked → **free** | no |
| `/search` | 390 | light | /search 200 | search | hidden | none → **5-tab** | — → **/browse** | Sign in | locked → **free** | no |
| `/search` | 390 | dark | /search 200 | search | hidden | none → **5-tab** | — → **/browse** | Sign in | locked → **free** | no |
| `/search` | 1280 | light | /search 200 | search | visible | none | — → **/browse** | Sign in | locked → **free** | no |
| `/search` | 1280 | dark | /search 200 | search | visible | none | — → **/browse** | Sign in | locked → **free** | no |
| `/terms` | 390 | light | /terms 200 | None | hidden | legacy 4-tab → **5-tab** | — | Sign in | locked → **free** | no |
| `/terms` | 390 | dark | /terms 200 | None | hidden | legacy 4-tab → **5-tab** | — | Sign in | locked → **free** | no |
| `/terms` | 1280 | light | /terms 200 | None | visible | none | — | Sign in | locked → **free** | no |
| `/terms` | 1280 | dark | /terms 200 | None | visible | none | — | Sign in | locked → **free** | no |
| `/privacy` | 390 | light | /privacy 200 | None | hidden | legacy 4-tab → **5-tab** | — | Sign in | locked → **free** | no |
| `/privacy` | 390 | dark | /privacy 200 | None | hidden | legacy 4-tab → **5-tab** | — | Sign in | locked → **free** | no |
| `/privacy` | 1280 | light | /privacy 200 | None | visible | none | — | Sign in | locked → **free** | no |
| `/privacy` | 1280 | dark | /privacy 200 | None | visible | none | — | Sign in | locked → **free** | no |
| `/grievance` | 390 | light | /grievance 200 | None | hidden | legacy 4-tab → **5-tab** | — | Sign in | locked → **free** | no |
| `/grievance` | 390 | dark | /grievance 200 | None | hidden | legacy 4-tab → **5-tab** | — | Sign in | locked → **free** | no |
| `/grievance` | 1280 | light | /grievance 200 | None | visible | none | — | Sign in | locked → **free** | no |
| `/grievance` | 1280 | dark | /grievance 200 | None | visible | none | — | Sign in | locked → **free** | no |


## 4. Route matrix — signed-in Free regression (frozen → candidate)

| Route | W | Theme | Status chain | Screen key | Top nav | Phone bar | Current | Account slot | Zoom | PNG identical |
|---|---|---|---|---|---|---|---|---|---|---|
| `/` | 390 | light | / 200 | None | hidden | none | — | — | free | no |
| `/` | 390 | dark | / 200 | None | hidden | none | — | — | free | yes |
| `/` | 1280 | light | / 200 | None | hidden | none | — | — | free | yes |
| `/` | 1280 | dark | / 200 | None | hidden | none | — | — | free | yes |
| `/browse` | 390 | light | /browse 200 | browse | hidden | 5-tab | /browse | Playground Tester Free account P | locked → **free** | yes |
| `/browse` | 390 | dark | /browse 200 | browse | hidden | 5-tab | /browse | Playground Tester Free account P | locked → **free** | yes |
| `/browse` | 1280 | light | /browse 200 | browse | visible | none | /browse | Playground Tester Free account | locked → **free** | yes |
| `/browse` | 1280 | dark | /browse 200 | browse | visible | none | /browse | Playground Tester Free account | locked → **free** | yes |
| `/browse/part/iii` | 390 | light | /browse/part/iii 200 | part | hidden | 5-tab | /browse | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/browse/part/iii` | 390 | dark | /browse/part/iii 200 | part | hidden | 5-tab | /browse | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/browse/part/iii` | 1280 | light | /browse/part/iii 200 | part | visible | none | /browse | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/browse/part/iii` | 1280 | dark | /browse/part/iii 200 | part | visible | none | /browse | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/browse/article/14` | 390 | light | /browse/article/14 200 | article | hidden | none | — | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/browse/article/14` | 390 | dark | /browse/article/14 200 | article | hidden | none | — | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/browse/article/14` | 1280 | light | /browse/article/14 200 | article | visible | none | /browse | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/browse/article/14` | 1280 | dark | /browse/article/14 200 | article | visible | none | /browse | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/laws` | 390 | light | /laws 200 | laws | hidden | 5-tab | — | Playground Tester Free account P | locked → **free** | yes |
| `/laws` | 390 | dark | /laws 200 | laws | hidden | 5-tab | — | Playground Tester Free account P | locked → **free** | yes |
| `/laws` | 1280 | light | /laws 200 | laws | visible | none | /browse | Playground Tester Free account | locked → **free** | yes |
| `/laws` | 1280 | dark | /laws 200 | laws | visible | none | /browse | Playground Tester Free account | locked → **free** | yes |
| `/laws/ndps` | 390 | light | /laws/ndps 200 | bareact | hidden | 5-tab | /browse | Playground Tester Free account P | locked → **free** | yes |
| `/laws/ndps` | 390 | dark | /laws/ndps 200 | bareact | hidden | 5-tab | /browse | Playground Tester Free account P | locked → **free** | yes |
| `/laws/ndps` | 1280 | light | /laws/ndps 200 | bareact | visible | none | /browse | Playground Tester Free account | locked → **free** | yes |
| `/laws/ndps` | 1280 | dark | /laws/ndps 200 | bareact | visible | none | /browse | Playground Tester Free account | locked → **free** | yes |
| `/laws/uapa` | 390 | light | /laws/uapa 200 | bareact | hidden | 5-tab | — | Playground Tester Free account P | locked → **free** | yes |
| `/laws/uapa` | 390 | dark | /laws/uapa 200 | bareact | hidden | 5-tab | — | Playground Tester Free account P | locked → **free** | yes |
| `/laws/uapa` | 1280 | light | /laws/uapa 200 | bareact | visible | none | /browse | Playground Tester Free account | locked → **free** | yes |
| `/laws/uapa` | 1280 | dark | /laws/uapa 200 | bareact | visible | none | /browse | Playground Tester Free account | locked → **free** | yes |
| `/laws/bns` | 390 | light | /laws/bns 200 | bareact | hidden | 5-tab | — | Playground Tester Free account P | locked → **free** | yes |
| `/laws/bns` | 390 | dark | /laws/bns 200 | bareact | hidden | 5-tab | — | Playground Tester Free account P | locked → **free** | yes |
| `/laws/bns` | 1280 | light | /laws/bns 200 | bareact | visible | none | /browse | Playground Tester Free account | locked → **free** | yes |
| `/laws/bns` | 1280 | dark | /laws/bns 200 | bareact | visible | none | /browse | Playground Tester Free account | locked → **free** | yes |
| `/laws/mtp` | 390 | light | /laws/mtp 200 | bareact | hidden | 5-tab | — | Playground Tester Free account P | locked → **free** | yes |
| `/laws/mtp` | 390 | dark | /laws/mtp 200 | bareact | hidden | 5-tab | — | Playground Tester Free account P | locked → **free** | yes |
| `/laws/mtp` | 1280 | light | /laws/mtp 200 | bareact | visible | none | /browse | Playground Tester Free account | locked → **free** | yes |
| `/laws/mtp` | 1280 | dark | /laws/mtp 200 | bareact | visible | none | /browse | Playground Tester Free account | locked → **free** | yes |
| `/laws/ndps/section/8` | 390 | light | /laws/ndps/section/8 200 | bareactsection | hidden | 5-tab | — | Playground Tester Free account P | locked → **free** | yes |
| `/laws/ndps/section/8` | 390 | dark | /laws/ndps/section/8 200 | bareactsection | hidden | 5-tab | — | Playground Tester Free account P | locked → **free** | yes |
| `/laws/ndps/section/8` | 1280 | light | /laws/ndps/section/8 200 | bareactsection | visible | none | /browse | Playground Tester Free account | locked → **free** | yes |
| `/laws/ndps/section/8` | 1280 | dark | /laws/ndps/section/8 200 | bareactsection | visible | none | /browse | Playground Tester Free account | locked → **free** | yes |
| `/playground` | 390 | light | /playground 200 | playground | hidden | 5-tab | /playground | Playground Tester Free account P | locked → **free** | yes |
| `/playground` | 390 | dark | /playground 200 | playground | hidden | 5-tab | /playground | Playground Tester Free account P | locked → **free** | yes |
| `/playground` | 1280 | light | /playground 200 | playground | hidden → **visible** | none | — → **/playground** | Playground Tester Free account | locked → **free** | no |
| `/playground` | 1280 | dark | /playground 200 | playground | hidden → **visible** | none | — → **/playground** | Playground Tester Free account | locked → **free** | no |
| `/playground?stage=plans` | 390 | light | /playground?stage=plans 200 | playground | hidden | 5-tab | /playground | Playground Tester Free account P | locked → **free** | yes |
| `/playground?stage=plans` | 390 | dark | /playground?stage=plans 200 | playground | hidden | 5-tab | /playground | Playground Tester Free account P | locked → **free** | yes |
| `/playground?stage=plans` | 1280 | light | /playground?stage=plans 200 | playground | hidden → **visible** | none | — → **/playground** | Playground Tester Free account | locked → **free** | no |
| `/playground?stage=plans` | 1280 | dark | /playground?stage=plans 200 | playground | hidden → **visible** | none | — → **/playground** | Playground Tester Free account | locked → **free** | no |
| `/playground?stage=plans&tier=plus` | 390 | light | /playground?stage=plans&tier=plus 200 | playground | hidden | 5-tab | /playground | Playground Tester Free account P | locked → **free** | yes |
| `/playground?stage=plans&tier=plus` | 390 | dark | /playground?stage=plans&tier=plus 200 | playground | hidden | 5-tab | /playground | Playground Tester Free account P | locked → **free** | yes |
| `/playground?stage=plans&tier=plus` | 1280 | light | /playground?stage=plans&tier=plus 200 | playground | hidden → **visible** | none | — → **/playground** | Playground Tester Free account | locked → **free** | no |
| `/playground?stage=plans&tier=plus` | 1280 | dark | /playground?stage=plans&tier=plus 200 | playground | hidden → **visible** | none | — → **/playground** | Playground Tester Free account | locked → **free** | no |
| `/playground/laws/uapa/add` | 390 | light | /playground/laws/uapa/add 200 | playground | hidden | none | — | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/playground/laws/uapa/add` | 390 | dark | /playground/laws/uapa/add 200 | playground | hidden | none | — | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/playground/laws/uapa/add` | 1280 | light | /playground/laws/uapa/add 200 | playground | hidden → **visible** | none | — → **/playground** | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/playground/laws/uapa/add` | 1280 | dark | /playground/laws/uapa/add 200 | playground | hidden → **visible** | none | — → **/playground** | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/dashboard` | 390 | light | /dashboard 200 | today | hidden | 5-tab | /dashboard | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/dashboard` | 390 | dark | /dashboard 200 | today | hidden | 5-tab | /dashboard | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/dashboard` | 1280 | light | /dashboard 200 | today | visible | none | /dashboard | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/dashboard` | 1280 | dark | /dashboard 200 | today | visible | none | /dashboard | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/calendar` | 390 | light | /calendar 200 | revisions | hidden | 5-tab | /calendar | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/calendar` | 390 | dark | /calendar 200 | revisions | hidden | 5-tab | /calendar | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/calendar` | 1280 | light | /calendar 200 | revisions | visible | none | /calendar | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/calendar` | 1280 | dark | /calendar 200 | revisions | visible | none | /calendar | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/profile` | 390 | light | /profile 200 | account | hidden | 5-tab | /profile | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/profile` | 390 | dark | /profile 200 | account | hidden | 5-tab | /profile | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/profile` | 1280 | light | /profile 200 | account | visible | none | /profile | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/profile` | 1280 | dark | /profile 200 | account | visible | none | /profile | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/settings` | 390 | light | /settings 200 | settings | hidden | none | — | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/settings` | 390 | dark | /settings 200 | settings | hidden | none | — | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/settings` | 1280 | light | /settings 200 | settings | visible | none | — | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/settings` | 1280 | dark | /settings 200 | settings | visible | none | — | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/profile/security/devices` | 390 | light | /profile/security/devices 200 | account | hidden | 5-tab | /profile | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/profile/security/devices` | 390 | dark | /profile/security/devices 200 | account | hidden | 5-tab | /profile | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/profile/security/devices` | 1280 | light | /profile/security/devices 200 | account | visible | none | /profile | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/profile/security/devices` | 1280 | dark | /profile/security/devices 200 | account | visible | none | /profile | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/tables` | 390 | light | /tables 200 | tables | hidden | 5-tab | — | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/tables` | 390 | dark | /tables 200 | tables | hidden | 5-tab | — | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/tables` | 1280 | light | /tables 200 | tables | visible | none | — | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/tables` | 1280 | dark | /tables 200 | tables | visible | none | — | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/search` | 390 | light | /search 200 | search | hidden | none | — | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/search` | 390 | dark | /search 200 | search | hidden | none | — | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/search` | 1280 | light | /search 200 | search | visible | none | — | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/search` | 1280 | dark | /search 200 | search | visible | none | — | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/terms` | 390 | light | /terms 200 | None | hidden | 5-tab | — | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/terms` | 390 | dark | /terms 200 | None | hidden | 5-tab | — | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/terms` | 1280 | light | /terms 200 | None | visible | none | — | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/terms` | 1280 | dark | /terms 200 | None | visible | none | — | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/privacy` | 390 | light | /privacy 200 | None | hidden | 5-tab | — | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/privacy` | 390 | dark | /privacy 200 | None | hidden | 5-tab | — | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/privacy` | 1280 | light | /privacy 200 | None | visible | none | — | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/privacy` | 1280 | dark | /privacy 200 | None | visible | none | — | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/grievance` | 390 | light | /grievance 200 | None | hidden | 5-tab | — | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/grievance` | 390 | dark | /grievance 200 | None | hidden | 5-tab | — | Playground Tester Playground Tes → **Playground Tester Free account P** | locked → **free** | yes |
| `/grievance` | 1280 | light | /grievance 200 | None | visible | none | — | Playground Tester → **Playground Tester Free account** | locked → **free** | no |
| `/grievance` | 1280 | dark | /grievance 200 | None | visible | none | — | Playground Tester → **Playground Tester Free account** | locked → **free** | no |


## 5. Responsive widths (guest, light)

| Route | W×H | Top nav | Phone bar | Current | H-scroll |
|---|---|---|---|---|---|
| `/browse` | 320×568 | hidden | 5-tab | /browse | no |
| `/browse` | 560×800 | hidden | 5-tab | /browse | no |
| `/browse` | 561×800 | visible | none | /browse | no |
| `/browse` | 720×900 | visible | none | /browse | no |
| `/browse` | 768×1024 | visible | none | /browse | no |
| `/browse` | 844×390 | visible | none | /browse | no |
| `/laws/ndps` | 320×568 | hidden | 5-tab | /browse | no |
| `/laws/ndps` | 560×800 | hidden | 5-tab | /browse | no |
| `/laws/ndps` | 561×800 | visible | none | /browse | no |
| `/laws/ndps` | 720×900 | visible | none | /browse | no |
| `/laws/ndps` | 768×1024 | visible | none | /browse | no |
| `/laws/ndps` | 844×390 | visible | none | /browse | no |
| `/playground` | 320×568 | hidden | 5-tab | /playground | no |
| `/playground` | 560×800 | hidden | 5-tab | /playground | no |
| `/playground` | 561×800 | visible | none | /playground | no |
| `/playground` | 720×900 | visible | none | /playground | no |
| `/playground` | 768×1024 | visible | none | /playground | no |
| `/playground` | 844×390 | visible | none | /playground | no |
| `/settings` | 320×568 | hidden | 5-tab | /profile | no |
| `/settings` | 560×800 | hidden | 5-tab | /profile | no |
| `/settings` | 561×800 | visible | none | /profile | no |
| `/settings` | 720×900 | visible | none | /profile | no |
| `/settings` | 768×1024 | visible | none | /profile | no |
| `/settings` | 844×390 | visible | none | /profile | no |
| `/search` | 320×568 | hidden | 5-tab | /browse | no |
| `/search` | 560×800 | hidden | 5-tab | /browse | no |
| `/search` | 561×800 | visible | none | /browse | no |
| `/search` | 720×900 | visible | none | /browse | no |
| `/search` | 768×1024 | visible | none | /browse | no |
| `/search` | 844×390 | visible | none | /browse | no |
| `/terms` | 320×568 | hidden | 5-tab | — | no |
| `/terms` | 560×800 | hidden | 5-tab | — | no |
| `/terms` | 561×800 | visible | none | — | no |
| `/terms` | 720×900 | visible | none | — | no |
| `/terms` | 768×1024 | visible | none | — | no |
| `/terms` | 844×390 | visible | none | — | no |

At 561–720 px the frozen build showed the top nav **and** a phone bar together (guest legacy bar; signed-in five-tab bar). The candidate hides the guest bar once the desktop header exists. The signed-in overlap in that range is pre-existing and was **not** changed (checklist §2 item 7; recorded as a signed-in gap for a later milestone).

## 6. Accessibility

| Criterion | Result | Notes |
|---|---|---|
| M1-A01 landmarks, names, icons | PASS (automated) | `nav[aria-label="Primary"]` and `nav[aria-label="Mobile"]`; links carry text labels; SVG icons are `aria-hidden`; exactly one `aria-current="page"` per nav per page (test). |
| M1-A01 focus order / visible focus | PASS (manual, UA ring) | Shell links use the browser's default `:focus-visible` ring (no custom rule on `.nav-link` / `.mobile-tab`); order is brand → nav links → Sign in → page. No focus trap. Skip-link: **NOT RUN** (none exists in the frozen shell; recorded, not added — scope). |
| M1-A02 text contrast, light | **FAIL → owner decision** | Inactive tab/nav label `--mid #8f8f8d` on `#ffffff` = **3.24:1** (needs 4.5:1 at 10.5–14 px). Pre-existing token shared with the signed-in bar and matching the prototype's grey. Proposed: `--muted #6b6b6b` (5.33:1). Not changed in M1 because it alters the signed-in bar too. Active labels 18.4:1; Sign in button 18.4:1. |
| M1-A02 text contrast, dark | PASS | inactive 5.15:1, active 14.9:1, Sign in 16.4:1. |
| M1-A02 UI contrast | note | hairline/border 1.37:1 (decorative; the bar is also distinguished by position and background). |
| M1-A02 hit targets | PASS | phone tabs ≥ 60 px tall × ≥ 78 px wide at 390; desktop nav links 38 px tall (mouse); Sign in 38 px. |
| M1-A03 zoom | PASS | viewport meta no longer blocks zoom on shared-shell pages; Login keeps its own restriction (disclosed, out of scope). 200 % reflow: shell wraps at 320 px without horizontal scroll (probe `hScroll=false` on all responsive rows). |
| M1-A04 automated scan | NOT RUN | no axe/Lighthouse runner in this environment; the template tests cover the ARIA contract. Record for the hosted pass. |
| M1-V05 dark | palette-only | dark captures consistent (no dark prototype). |

## 7. Visual comparison against the prototype shell (light)

| Surface | Prototype (`viewer=guest`) | Candidate | Verdict |
|---|---|---|---|
| Phone bar | five tabs, icon + 10.5 px label, active ink, inactive grey, 60 px, hairline top | same structure and geometry (shared with the signed-in bar) | MATCH, except the Playground icon glyph (app grid vs prototype brain) which is the app's existing icon set — G minor, not M1 |
| Desktop top nav | brand · Today/Browse/Playground/Calendar/Profile pill nav · black "Sign in" button right | same; Sign in is a 38 px black rounded button in the account slot | MATCH |
| Brand mark | filled black square "C" on every page | filled square on Browse/Laws/NDPS/gate/Profile; outlined glyph on legacy pages (UAPA/BNS heads, Today, Settings, legal, readers) because the invert rule is per-screen | **G (shell, open)** — DV-22 proposed: unify the brand mark; not changed in M1 (the same rules style signed-in pages) |
| Guest gate (desktop) | full nav + Sign in | now full nav + Sign in, Playground current | MATCH (was: brand + guest menu only) |
| Legal pages | not drawn | inherited shell, no current tab | per checklist |

## 8. Deviations still open after M1 (for the owner)

| ID | Where | Class | Proposal |
|---|---|---|---|
| A02 contrast | inactive tab/nav label colour (light) | accessibility vs prototype | switch `--mid` → `--muted` for shell labels in a follow-up (affects signed-in too) |
| DV-22 | brand mark style differs by page | G (shell) | unify to the filled square in a follow-up shell item |
| signed-in 561–720 | top nav + phone bar both visible | pre-existing signed-in gap | leave for a signed-in shell milestone |
| Playground tab icon | glyph differs from prototype | G minor (icon set) | M9 polish |

## 9. Gates

| Gate | Status |
|---|---|
| Checklist approval | Accepted 2026-10-19 (+DV-20, DV-21) |
| Implementation authorisation | Granted 2026-10-19 (local only) |
| Branch / PR | `pg-m1-guest-shell` from `5d89fbd`; draft PR into `cursor/playground-220d` |
| Local validation | see §2–§7 — LOCAL/PRELIMINARY |
| Staging deployment authorisation | **Not granted** |
| Hosted acceptance | **Not run** |
| Owner milestone decision | Pending |
