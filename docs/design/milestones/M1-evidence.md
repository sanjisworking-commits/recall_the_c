# M1 — Guest shell parity · LOCAL / PRELIMINARY evidence

Status: **LOCAL/PRELIMINARY.** Produced from a local run of this branch; it does
**not** close hosted acceptance. Staging still serves the frozen `5d89fbd`
(deployment `32971cbf…`); a staging deployment of this branch needs the
owner's separate authorisation (checklist §7). Merge is not authorised.

| | |
|---|---|
| Checklist | `docs/design/milestones/M1.md` on PR #218 (accepted 2026-10-19 with DV-20 and DV-21 in scope) |
| Baseline | `cursor/playground-220d` @ `5d89fbdfb6c712a998ce1fdbc4a7756fee8677b8` |
| Candidate | `pg-m1-guest-shell` @ `7f78992b257ad223603a99bc286be8bb622be310` |
| Local server | the Playground dev launcher pointed at this worktree (fake Google auth, throwaway DB, Free-tier seeded user), port 8912 |
| Capture tool | `docs/design/proto-comparison-2026-10-19/m1/tools/capture_local.py` (headless Chrome Google Chrome 155.0.8059.82 over CDP, DPR 1, fonts awaited, 0.6 s settle; sign-in via the dev provider, cookies injected in-process and never written) |
| Prototype references | 18 Oct exports, hashes in M1.md Appendix A.1; states `viewer=guest` / `viewer=signedIn` via `make_wrappers.py` |
| Evidence folder | `docs/design/proto-comparison-2026-10-19/m1/` — manifests with SHA-256 of every PNG (baseline and candidate, both viewers, both widths, light and dark, plus the responsive and accessibility sets); light captures committed; **the complete original set, including dark and the frozen signed-in captures, is viewable side by side at the private gallery linked in that folder's README** (https://claude.ai/artifact/1gkWC3z1VfZEwbFryyR2va) and archived with its SHA-256 |

## 1. What changed (scope diff)

Source files, candidate vs `5d89fbd` (only the four files the checklist allows):

```
src/constitution_memorizer/web/static/mobile.css   |  35 ++--
 .../web/static/playground.css                      |  13 +-
 src/constitution_memorizer/web/static/styles.css   | 120 ++++-------
 src/constitution_memorizer/web/templates/base.html | 232 +++------------------
 4 files changed, 98 insertions(+), 302 deletions(-)
```

- `base.html` — viewport meta allows zoom (`maximum-scale=1, user-scalable=no` removed); the per-screen guest flags (`guest_browse_index`, `guest_laws_index`, `guest_bareact_head`, `guest_playground_intro`, `guest_profile`, `guest_settings`, `guest_chrome`) are replaced by one `guest_shell` flag and five `shell_*` active-state flags; one brand link; one guest top-nav branch (Today/Browse/Playground/Calendar/Profile with `aria-current`); the three guest account menus become one `<a class="nav-signin" href="/login">Sign in</a>`; one guest phone bar (`data-guest-phone-tabs`) replaces the four per-screen bars and the legacy `mobile-tabbar is-guest`; the footer Settings link is shown to guests too (the guest account menu that linked it is gone); DV-20: the account-slot subtitle renders on every shared-shell page (the page-flag chain is kept, with a snapshot-aware fallback). Signed-in nav, account menu and tab-bar branches are untouched. Asset pins bumped: `main86→main87`, `mob105→mob106`, `pg48→pg49`.
- `styles.css` — removed: `.guest-pill` rules, the dead `[data-guest-*]` brand/nav/account selectors, the header-grid and `.PrimaryTabs--top { display:none }` overrides on the guest intro and the signed-in gate (DV-21), and the five per-screen `.account-menu-btn-status { display:none }` rules (DV-20). Added: desktop `.site-header > .nav-signin` button style; `body.is-guest .mobile-tabbar { display:none }` at ≥561 px (no duplicate nav at 561–720); generic ≤720 px tab bar uses `grid-auto-flow: column` so it fits four or five tabs; `body.is-guest .page-wrap` gets the same 64 px bottom clearance signed-in pages already had.
- `mobile.css` — removed the `.mobile-tabbar.is-guest` rules; added `body.is-guest[data-mscreen="settings"|"search"] .mobile-tabbar { display:grid }` after the generic hide rule (signed-in Settings/Search keep their frozen bar-less behaviour).
- `playground.css` — the hard-gate rule no longer hides `.PrimaryTabs--top` (DV-21); it hides phone bars except the shared guest bar, and the guest Add sheet page keeps its bar hidden as before; two dead `[data-guest-*-phone-tabs]` selectors removed.

Not changed: any page body, route, redirect, auth, entitlement, billing, device, data or test fixture; `app.py`.

### 1.1 Scope expansion requested (checklist §4 regression-only rows)

The universal `guest_shell` branch also reaches four route families that §4 lists as regression-only. What changed there, and the two ways to resolve it:

| Route family | Frozen guest chrome | Candidate guest chrome | Body / behaviour |
|---|---|---|---|
| `/browse/part/{slug}` | legacy top nav + legacy four-tab bar | shared top nav + five-tab bar (Browse current) | unchanged |
| `/browse/article/{n}` (Constitution reader) | legacy top nav; phone bar hidden by `data-mscreen="article"` | shared top nav; phone bar still hidden (rule untouched) | unchanged; sticky "Learn" action unchanged |
| `/laws/{id}/section/{n}`, `/laws/{id}/schedule/{s}` (Act readers) | legacy top nav + legacy four-tab bar (`bareactsection` / `bareactschedule` do not hide it) | shared top nav + five-tab bar | unchanged |
| `/playground/laws/{id}/add` (guest, direct URL) | brand + Sign in header; no phone bar | shared top nav + Sign in; phone bar still hidden (explicit rule) | unchanged |

**Request:** accept this expansion (the owner's design direction is five-tab navigation on every guest screen, and leaving these four families on the legacy chrome would re-introduce a second guest shell). **Alternative:** if the exceptions must stand, the frozen legacy branch can be restored for exactly these four families in a follow-up commit before any staging deployment — say which.

## 2. Tests

**The suite is not green; it carries three documented exceptions.** Baseline (`5d89fbd`, same environment, 2026-10-19): `3 failed, 3849 passed, 163 skipped, 1 deselected` — the three failures are `tests/test_devices_m4c.py` (`test_existing_registered_device_stays_allowed_at_churn_cap`, `test_admin_reset_does_not_erase_replacement_history`, `test_admin_clears_replacement_lock_with_audit`), pre-existing and unrelated to the shell (device replacement-limit logic).

Candidate (`7f78992b257ad223603a99bc286be8bb622be310`): `3 failed, 3904 passed, 163 skipped, 1 deselected, 18 warnings in 389.15s (0:06:29)`
Failures: `FAILED tests/test_devices_m4c.py::test_existing_registered_device_stays_allowed_at_churn_cap`, `FAILED tests/test_devices_m4c.py::test_admin_reset_does_not_erase_replacement_history`, `FAILED tests/test_devices_m4c.py::test_admin_clears_replacement_lock_with_audit`

Skips are Playwright-backed browser tests (`pytest.importorskip("playwright")`); Playwright is not installed in this environment, so those remain **NOT RUN** here, not passed. Browser behaviour was verified instead through the headless-Chrome captures and DOM probes below.

New: `tests/test_guest_shell_parity.py` (55 tests, incl. the M1-A02 guest-scope rule test): five-tab guest bar with exactly one current tab on 14 routes; four tabs when `PLAYGROUND_ENABLED=false`; guest bar rendered visible on Settings and Search (CSS order); five-link guest top nav with one Sign in button and no legacy chrome; identical header shell across routes; Landing/Login/auth-surface exceptions unchanged; guest gates (`/calendar`, devices, Playground) unchanged; footer functions and Settings route kept; viewport allows zoom; signed-in top nav and account-slot subtitle on 16 routes (DV-20); signed-in Free phone bar unchanged; DV-21 CSS no longer hides the desktop nav; asset pins bumped.

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
| `/laws/ndps` | 390 | light | /laws/ndps 200 | bareact | hidden | 5-tab | /browse | ? Guest Not signed in Settings S → **Sign in** | locked → **free** | no |
| `/laws/ndps` | 390 | dark | /laws/ndps 200 | bareact | hidden | 5-tab | /browse | ? Guest Not signed in Settings S → **Sign in** | locked → **free** | no |
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
| `/playground` | 390 | light | /playground 200 | playground | hidden | 5-tab | /playground | Sign in | locked → **free** | no |
| `/playground` | 390 | dark | /playground 200 | playground | hidden | 5-tab | /playground | Sign in | locked → **free** | no |
| `/playground` | 1280 | light | /playground 200 | playground | hidden → **visible** | none | — → **/playground** | Sign in | locked → **free** | no |
| `/playground` | 1280 | dark | /playground 200 | playground | hidden → **visible** | none | — → **/playground** | Sign in | locked → **free** | no |
| `/playground?stage=plans` | 390 | light | /playground?stage=plans 200 | playground | hidden | 5-tab | /playground | Sign in | locked → **free** | no |
| `/playground?stage=plans` | 390 | dark | /playground?stage=plans 200 | playground | hidden | 5-tab | /playground | Sign in | locked → **free** | no |
| `/playground?stage=plans` | 1280 | light | /playground?stage=plans 200 | playground | hidden → **visible** | none | — → **/playground** | Sign in | locked → **free** | no |
| `/playground?stage=plans` | 1280 | dark | /playground?stage=plans 200 | playground | hidden → **visible** | none | — → **/playground** | Sign in | locked → **free** | no |
| `/playground?stage=plans&tier=plus` | 390 | light | /playground?stage=plans&tier=plus 200 | playground | hidden | 5-tab | /playground | Sign in | locked → **free** | no |
| `/playground?stage=plans&tier=plus` | 390 | dark | /playground?stage=plans&tier=plus 200 | playground | hidden | 5-tab | /playground | Sign in | locked → **free** | no |
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
| `/profile` | 390 | light | /profile 200 | account | hidden | 5-tab | /profile | Sign in | locked → **free** | no |
| `/profile` | 390 | dark | /profile 200 | account | hidden | 5-tab | /profile | Sign in | locked → **free** | no |
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

Evidence files: `docs/design/proto-comparison-2026-10-19/m1/a11y/` (`a11y.json`, zoom and focus PNGs). Verdicts use PASS / FAIL / BLOCKED / NOT RUN exactly.

| Criterion | Guest shell (M1 scope) | Signed-in shell (regression-only) | Evidence |
|---|---|---|---|
| M1-A01 landmarks and names | **PASS** — AX tree exposes `navigation "Primary"` (desktop) / `navigation "Mobile"` (phone) with link names Today, Browse, Playground, Calendar, Profile; footer `navigation "Tools"` and `"Legal"`; no SVG exposed (all `aria-hidden`); exactly one `aria-current="page"` per nav per page (template tests). | unchanged | `a11y.json → axtree` |
| M1-A01 focus order and visible focus | **PASS with one recorded finding** — desktop trace (`a11y.json → keyboard`, `/browse` and `/settings` at 1280): brand → Today → Browse → Playground → Calendar → Profile → Sign in (account slot) → page content (on `/browse` the next stop is the strip's own Sign in, then Laws); every stop shows the browser's `solid 2px` ink outline. Phone: the tab bar sits after `<main>` in DOM order, so it is reached after the page content (frozen signed-in bar has the same placement). No focus trap. **No skip-to-content link exists** in the frozen shell; none was added (scope). | unchanged | `a11y.json → keyboard`, `focus_*.png` |
| M1-A02 text contrast (light) | **FIXED → PASS** — inactive labels now `--muted` `#6b6b6b` on `#ffffff` = **5.33:1** (guest-scoped rules in `styles.css` / `mobile.css`); active 18.4:1; Sign in 18.4:1. | **FAIL, unchanged (exception requested)** — `--mid` `#8f8f8d` = 3.24:1 on the signed-in bars; the same rule could be extended to `body.is-authed` on the owner's say-so. | token arithmetic in §6.1 |
| M1-A02 text contrast (dark) | **PASS** — inactive 5.93:1, active 14.9:1, Sign in 16.4:1. | PASS (5.15:1) | §6.1 |
| M1-A02 UI/focus contrast ≥ 3:1 | **PASS** — focus outline `#141414` on paper 18.4:1; the hairline (1.37:1) is decorative, the bar is distinguished by position/background. | same | — |
| M1-A02 targets ≥ 44×44 CSS px | **FIXED → PASS at 1× zoom** — desktop nav links 80–111 × 44, Sign in 77 × 44 (was 38 tall); phone tabs 78 × 60 at 390. | **FAIL, unchanged (exception requested)** — signed-in desktop links stay 38 px tall. | `a11y.json → zoom[*].targets` |
| M1-A03 zoom allowed | **PASS** — shared viewport meta no longer sets `maximum-scale` / `user-scalable=no` (test). Login keeps its own restriction (disclosed, out of scope). | same meta | HTML |
| M1-A03 200 % zoom / reflow | **Supporting evidence only (emulated); the real check is NOT RUN, see §7b** — 200 % zoom emulated as the CSS viewport halved at DSF 2 (1280 → 640×450; 390 → 195×422): no horizontal scroll, nav/bar present and usable on `/browse`, `/settings`, `/playground`, `/terms`. Finding: at 195 CSS px the five phone tabs are 34 CSS px wide (68 device px) — below 44 CSS px at that extreme; recorded, not treated as a failure of the 1× contract. A real browser-zoom pass (⌘+) is **NOT RUN** here. | same emulation applies | `zoom_*.png` |
| M1-A03 reduced motion | NOT RUN (no shell animation was added or removed) | — | — |
| M1-A04 automated scan | **BLOCKED** — no axe/Lighthouse runner is available in this environment and installing one (npm packages) was not authorised; the ARIA contract is covered by template tests and the AX-tree dump above. Must run in the hosted pass. | BLOCKED | — |
| M1-A01 screen-reader smoke | **NOT RUN** (manual VoiceOver pass not performed in this session); the AX tree is the proxy. | NOT RUN | — |
| M1-V05 dark | palette-only check: consistent (no dark prototype). | same | dark captures |

### 6.1 Contrast arithmetic (WCAG 2.x relative luminance)

| Pair | Ratio |
|---|---|
| `--mid #8f8f8d` on paper `#ffffff` (frozen inactive label, light) | 3.24:1 |
| `--muted #6b6b6b` on paper `#ffffff` (guest inactive label, light, candidate) | 5.33:1 |
| `--ink #141414` on paper (active label / Sign in text on ink inverted) | 18.42:1 |
| `--mid #8f8f8d` on paper `#1e1e1d` (dark) | 5.15:1 |
| `--muted #9a9a9a` on paper `#1e1e1d` (guest inactive label, dark) | 5.93:1 |
| `--ink #f2f2f0` on paper `#1e1e1d` (dark active) | 14.88:1 |
| hairline on paper (light / dark) | 1.37:1 / 1.32:1 |

## 7. Visual comparison against the prototype shell (light)

| Surface | Prototype (`viewer=guest`) | Candidate | Verdict |
|---|---|---|---|
| Phone bar | five tabs, icon + 10.5 px label, active ink, inactive grey, 60 px, hairline top | same structure and geometry (shared with the signed-in bar); inactive labels **`--muted`** instead of the prototype grey (accessibility-driven, see §6) | MATCH in structure; **recorded intentional deviation**: accessible grey; the Playground icon glyph (app grid vs prototype brain) is the app's icon set — G minor, not M1 |
| Desktop top nav | brand · Today/Browse/Playground/Calendar/Profile pill nav · black "Sign in" button right; inactive labels in the prototype's grey | same structure; Sign in is a **44 px** black rounded button in the account slot; nav links **44 px** tall (prototype ≈38 px); inactive labels **`--muted #6b6b6b`** instead of the prototype grey (accessibility-driven, see §6) | MATCH in structure; **recorded intentional deviations**: 44 px targets and accessible grey |
| Brand mark | filled black square "C" on every page | filled square on Browse/Laws/NDPS/gate/Profile; outlined glyph on legacy pages (UAPA/BNS heads, Today, Settings, legal, readers) because the invert rule is per-screen | **G (shell, open)** — DV-22 proposed: unify the brand mark; not changed in M1 (the same rules style signed-in pages) |
| Guest gate (desktop) | full nav + Sign in | now full nav + Sign in, Playground current | MATCH (was: brand + guest menu only) |
| Legal pages | not drawn | inherited shell, no current tab | per checklist |

## 7a. Functional correctness, assessed separately from visual fidelity (owner rule, 2026-10-19)

The prototype guides appearance only. This table lists every working control or page the M1 shell change touched and what happened to it; nothing was disabled because the prototype draws it disabled or omits it.

| Function (frozen) | Where it lived | Candidate | Status |
|---|---|---|---|
| Sign in entry for guests (desktop) | guest account menu on Browse/Laws/NDPS/gate/Profile; `Sign in` link in the legacy nav elsewhere | one `Sign in` button in the account slot on every shared-shell page; the Browse strip's own Sign in link is unchanged | **kept, unified** |
| Settings route for guests (desktop) | "Settings" item inside the guest account menu | footer "Settings" link now shown to guests; `/settings` itself unchanged | **kept** (moved; test `test_guest_footer_keeps_functions_and_a_route_to_settings`) |
| Guest "Sign out" item | guest account menu (no-op for guests: closed the menu) | removed with the menu | **removed, no-op** — it performed no action for a guest |
| Today / Browse / Playground / Calendar / Profile tabs (phone) | five tabs only on NDPS head, gate, Profile; legacy Browse/Search/Learn/Sign in elsewhere | five tabs everywhere for guests | **kept and extended**; every tab is a real link |
| Search and Learn entries for guests (phone) | legacy bar tabs | not in the five-tab bar; `/search` reachable from the Browse page's search control and by URL; `/learn/*` reachable from Articles | **kept as pages**, no longer bar tabs (prototype omits them; the pages still work — see guest `/search` captures) |
| Calendar gate for guests | `/calendar` → 303 to `/login?next=%2Fcalendar&reason=default` | identical (test `test_guest_gates_are_preserved`) | **enforced** |
| Devices gate for guests | 303 to login | identical | **enforced** |
| Playground gate (guest, sign-in required) | `/playground` 200 with the sign-in gate | identical body; nav added | **enforced** |
| Footer: Tables, Relevant laws, Contact us, theme chip, legal links | all pages | unchanged (plus Settings for guests) | **kept** |
| Google-only sign-in | `/login` standalone | unchanged | **enforced** |
| Zoom | blocked on shared shell | allowed | **enabled** (was a restriction the application did not need) |
| Signed-in account menu (Profile, Settings, Learn, Progress, Calendar, Memory log, Admin, Sign out) | account slot | unchanged markup | **kept** |

## 7b. Required accessibility checks still outstanding

Viewport/DPR emulation and the AX-tree inspection are supporting evidence only. These checklist items are **not complete** and M1 cannot be labelled "accessibility accepted" until they run (locally or in the hosted pass):

| Check | State | What would close it |
|---|---|---|
| Real browser zoom to 200 % (⌘+ / Ctrl+) | NOT RUN — attempted 2026-10-19 in Chrome via the automation tools, which refuse page-zoom shortcuts; the §6 emulation is supporting evidence only | a zoom pass in a real browser at 200 % on the §4 routes, recorded with the resulting CSS viewport and overflow result |
| Screen-reader smoke pass | NOT RUN | VoiceOver (macOS) or NVDA pass over the shell: landmarks announced, link names, current-page state |
| Automated accessibility scan | BLOCKED | an axe-core or Lighthouse run per distinct shell state; needs a runner this environment lacks (installing one requires authorisation) |

## 7c. Reviewer recommendations recorded (2026-10-19) — pending the owner's decision

| Item | Recommendation | Owner decision |
|---|---|---|
| Expanded guest-shell scope (§1.1) | approve **chrome only** for the four families; reader bar suppression, page bodies and access gates preserved (they are: the `article` suppression rule and the guest Add bar rule are untouched, bodies unchanged, gates tested) | **Approved 2026-10-19** (chrome only) |
| Accessible guest grey and 44 px guest targets | keep; record as intentional prototype deviations (recorded in §7) | **Approved 2026-10-19** |
| Signed-in accessibility (38 px, `--mid`) | temporary **M1-only exception** with a named follow-up milestone; not accessibility acceptance | **Granted 2026-10-19** as an M1-only exception, tracked in M1b before final redesign acceptance |
| DV-22 brand mark | batch into M9 polish | **Deferred to M9, 2026-10-19** |
| Signed-in double nav at 561–720 px | track explicitly for correction before final acceptance | **Exception granted 2026-10-19**, tracked in M1b |

## 8. Deviations still open after M1 (for the owner)

| ID | Where | Class | Proposal |
|---|---|---|---|
| A02 contrast (prototype) | guest inactive labels now `--muted`, darker than the prototype's grey | accessibility-driven deviation from the prototype (for owner review) | keep; or revert if the owner prefers the prototype grey with a documented exception |
| DV-22 | brand mark style differs by page | G (shell) | unify to the filled square in a follow-up shell item |
| signed-in 561–720 | top nav + phone bar both visible | pre-existing signed-in gap | leave for a signed-in shell milestone |
| Playground tab icon | glyph differs from prototype | G minor (icon set) | M9 polish |
| signed-in A02 | 38 px desktop links; `--mid` labels (3.24:1 light) on the signed-in shell | pre-existing; exception requested | extend the guest-scoped rules to `body.is-authed` on the owner's instruction |
| scope §1.1 | Browse Part, Constitution reader, Act readers, guest Add page received the shared chrome | scope expansion requested | accept, or restore the legacy branch for those four families |

## 9. Gates

| Gate | Status |
|---|---|
| Checklist approval | Accepted 2026-10-19 (+DV-20, DV-21) |
| Implementation authorisation | Granted 2026-10-19 (local only) |
| Branch / PR | `pg-m1-guest-shell` from `5d89fbd`; draft PR into `cursor/playground-220d` |
| Local validation | see §2–§7 — LOCAL/PRELIMINARY |
| Staging deployment authorisation | **Granted 2026-10-19 for validation only** — the owner performs the deploy of `pg-m1-guest-shell` to `recallc-playground-staging`; no merge; deployment does not accept M1 |
| Hosted acceptance | **Not run** |
| Owner milestone decision | Pending |
