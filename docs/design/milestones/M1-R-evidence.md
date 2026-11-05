# M1-R — Shared shell revision · LOCAL / PRELIMINARY evidence

| Item | Value |
|---|---|
| Branch / PR | `pg-m1r-shell-labels` from `pg-b1-entitlement-foundation` @ `56bdd82`; draft PR #232 — https://github.com/sanjisworking-commits/recall_the_c/pull/232 (base `pg-b1-entitlement-foundation`) |
| Candidate SHA | `e0e486a (code identical to `4e22170`; `e0e486a` adds only test re-pins — `git diff 4e22170 e0e486a -- src` is empty, so the captures below, taken from that tree, are the candidate's)` |
| Baseline SHA | `56bdd82` (B1 tip, before any M1-R edit; captures taken first) |
| Checklist | plan §3.3 (M1R-F01 label, M1R-F02 one Google action, M1R-F03 D33) + owner criteria 2026-11-05 (one navigation surface, five usable phone tabs, avatar visible and clickable; 390 / 561–720 / 1280; light + dark) |
| Original M1 evidence | `docs/design/milestones/M1-evidence.md` — **untouched**, pinned to its own SHA |
| Tooling | `docs/design/proto-comparison-2026-10-19/m1r/tools/capture_m1r.py` (headless Chrome over CDP; dev fake-Google sign-in in-process, cookie never written); dev server `playground-m1r-<tier>` on 8914 |
| Status | LOCAL / PRELIMINARY — hosted checks NOT RUN (no deployment) |

## 1. What changed (scope diff)
- `web/shell.py` (new): `account_status_for_snapshot` / `shell_account_status` — the header account-slot label as one function of the entitlement snapshot: `RecallC Free` · `RecallC Plus` · `RecallC Pro` · `RecallC Max` (legacy holders); halted and expired keep their status titles (`gate_view(...).title`, unchanged text) until 5-20 / M8-R. Registered as a Jinja global in `web/app.py`.
- `base.html`: the account-slot status renders `{{ shell_account_status(request) or 'RecallC Free' }}` on every shared-shell page; the per-route flag chain (`plus_*`, `halted_*`, `expired_*`, `*_chrome`, `*_billing`, `_status_gate`) is removed. One signed-in top nav and one signed-in phone bar (`data-signed-in-phone-tabs`) driven by the `shell_*` flags that the M1 guest shell already used; the three per-cohort Act-page bars (`data-plus-/expired-/signed-in-bareact-phone-tabs`) and their `path == '/laws/ndps'` flags are gone (M1R-F03 / D33). `shell_playground` now includes `/billing/subscriptions`. Asset pins `main88→main89`, `mob107→mob108`, `pg52→pg53`.
- `styles.css`: at `min-width: 561px` **every** `.mobile-tabbar` is hidden (M1 hid only the guest bar) — one navigation surface per page at 561–720. The 561–899 header becomes two rows (brand + account slot, then the tabs, which scroll if needed) with `height: auto`, so neither the tabs nor the avatar wrap under the page title (the overlap recorded in M1 §8).
- `mobile.css`: the shared phone bar shows on Search for signed-in users too; Settings keeps the M1 guest rule and the accepted signed-in screen-11 rule (bar hidden; reached from Profile).
- `partials/playground.html` (`guest_phone_gate`): the two inert `<button type="button">`s ("Sign in", "Create an account") become one real action `Continue with Google` → `/auth/google/start?next=/playground` (M1R-F02 / 5-11). `playground.css`: dead `.pg-guest-gate-create` rule removed; the anchor keeps the 50 px full-width style.
- Guest shell, page bodies, CTAs, gates, redirects: unchanged. The entitlement flag is untouched (`monthly` default); nothing branches on it.

## 2. Tests
| Run | Result |
|---|---|
| Full suite `pytest -m "not integration"` on `e0e486a` | **3 failed, 4007 passed, 163 skipped, 14 deselected** (7 m 12 s) |
| Known baseline failures (`test_devices_m4c.py`, present at `6b45d27` and on B1) | 3 — unchanged, not caused by M1-R |
| New failures | none |
| New `tests/test_shell_m1r.py` | 13 passed — label matrix (Free/Plus/Pro/Max, halted, expired titles); label identical on 15 shared-shell routes per tier; one top nav + one phone bar with five tabs and the expected active tab per route (incl. `/billing/subscriptions` → Playground, `/settings` → Profile); D33 on `/laws/{ndps,uapa,bns,mtp}`; guest bar unchanged; CSS rules and asset pins; guest gate one Google action |
| Legacy shell pins re-pointed | 78 test files per `M1R_TEST_CONTRACT` (label `Free account` → `RecallC Free`; per-cohort bar attributes → `data-signed-in-phone-tabs` with "exactly one bar" assertions; base.html flag-chain pins → `web/shell.py` / `shell_account_status`; asset pins; guest-gate source pins; the 561–899 and `min-width: 561px` CSS pins). No page-body, CTA, gate, redirect, status-code or perf assertion was weakened; each change carries an `# M1-R (PR pg-m1r-shell-labels)` comment |
| Playwright geometry tests | SKIPPED locally (`playwright` not installed) — NOT RUN |
| GitHub CI (`[ci full]`) | pending at the time of writing; recorded in the PR |
| Hosted / staging | NOT RUN (no deployment authorised) |

PASS / FAIL / BLOCKED / NOT RUN against the owner's criteria (local, probe-backed): one navigation surface per page — **PASS** at 561, 640, 720, 899 and 1280 for guest, Free, Pro (and 390: the phone bar is the one surface); five usable phone tabs — **PASS** on every shared-shell route except the recorded design exceptions (signed-in Settings, checkout, Article reader, Learn modes); avatar visible and clickable — **PASS** at every width where the header renders (561–1280, all routes except the Add page's open modal); at 390 the phone shell hides the header by design (see §8); account-tier labels — **PASS** (`RecallC Free/Plus/Pro/Max` on every page, halted/expired titles unchanged); 390 / 561–720 / 1280 in light and dark — **captured**; original M1 evidence — **preserved**.

## 3. Baseline findings (56bdd82, before edits)
Captured on `56bdd82` before any edit (tool and routes identical to the candidate run; signed-in Free and Pro at 390/561/640/720/1280 light+dark for Free, 390/640/1280 light for Pro):

- **DV-20 (label):** a **Pro** subscriber read `Free account` on `/browse`, `/browse/part/iii`, `/browse/article/14`, `/laws`, every `/laws/<act>` page, `/laws/ndps/section/8`, `/playground`, `/playground?stage=plans`, `/tables`, `/search` and `/terms`; `RecallC Pro` only on Today, Calendar, Profile, Settings and Billing (the pages whose handlers happened to attach the snapshot). Free read `Free account` everywhere.
- **Two navigation surfaces at 561–720:** every signed-in page except Playground showed the desktop top nav **and** the five-tab phone bar (`s2·t5` in the tables below); guests showed one (M1).
- **Header wrap in the transition range:** at 640 the tabs wrapped under the brand and sat on the page title; at 720 the avatar wrapped below the header onto the title (`baseline/baseline_pro_browse_640x900_light.png`, `…_720x900_light.png` in the archive; `range/` holds the Browse rows).
- **Phone (390):** the desktop header is hidden on every phone screen by the phone shell rule (`mobile.css`: `body[data-mscreen] .site-header { display:none }`), so the account button is not visible there by design; the Profile tab is the account entry. Search showed no bar for signed-in users (guests had five tabs since M1); Settings/Billing/Article showed none (accepted designs).
- No horizontal scroll and no overlapping header children were recorded on any row.

## 4. Candidate route matrix (probe-backed)
Columns: surfaces = visible primary navigation surfaces (top nav + visible phone bars); tabs = visible phone tabs; avatar = account button visible **and** a hit-test at its centre lands on it; overlaps = intersecting visible header children; chip = account-slot text.
Cells read `s<surfaces>·t<tabs>·<avatar>·<chip>`; a cell `~~old~~ → **new**` changed from the baseline (same route, width, theme). `hidden` = the header is not rendered at that width (phone shell); `covered` = an open modal sits over the header (expected on the Add page, which opens its dialog on load); `—` = no account button (guest / landing).

Full matrices: `candidate/manifest_<viewer>.json` (SHA-256 per PNG, probe per row). Committed PNGs: light, 390 and 1280, for Browse / NDPS head / Playground / Profile per viewer plus the range rows; the complete set (1,120 PNGs, both themes, every width) is archived at `~/Downloads/m1r-local-evidence-e0e486a.zip` (sha256 `70a47ad98ede3c4d83636c8396865955d5a12f11671dd39e74dc9eb6b63b0700`).

##### guest: baseline 56bdd82 → candidate — light

| Route | 390 | 561 | 640 | 720 | 1280 |
|---|---|---|---|---|---|
| `dashboard` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `browse` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `browse-part-iii` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `article-14` | s0·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `laws` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `laws-ndps` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `laws-uapa` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `ndps-section-8` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `playground` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `playground-plans` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `calendar` | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— |
| `profile` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `settings` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `billing` | s0·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `tables` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `search` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `terms` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `landing` | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— |

##### guest: baseline 56bdd82 → candidate — dark

| Route | 390 | 561 | 640 | 720 | 1280 |
|---|---|---|---|---|---|
| `dashboard` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `browse` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `browse-part-iii` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `article-14` | s0·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `laws` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `laws-ndps` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `laws-uapa` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `ndps-section-8` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `playground` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `playground-plans` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `calendar` | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— |
| `profile` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `settings` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `billing` | s0·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `tables` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `search` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `terms` | s1·t5·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `landing` | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— |

##### free: baseline 56bdd82 → candidate — light

| Route | 390 | 561 | 640 | 720 | 1280 |
|---|---|---|---|---|---|
| `dashboard` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `browse` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `browse-part-iii` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `article-14` | ~~s0·t0·Free account~~ → **s0·t0·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `laws` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `laws-ndps` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `laws-uapa` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `ndps-section-8` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `playground` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `playground-plans` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `calendar` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `profile` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `settings` | ~~s0·t0·Free account~~ → **s0·t0·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `billing` | ~~s0·t0·Free account~~ → **s0·t0·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `tables` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `search` | ~~s0·t0·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `terms` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `landing` | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— |

##### free: baseline 56bdd82 → candidate — dark

| Route | 390 | 561 | 640 | 720 | 1280 |
|---|---|---|---|---|---|
| `dashboard` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `browse` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `browse-part-iii` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `article-14` | ~~s0·t0·Free account~~ → **s0·t0·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `laws` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `laws-ndps` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `laws-uapa` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `ndps-section-8` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `playground` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `playground-plans` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `calendar` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `profile` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `settings` | ~~s0·t0·Free account~~ → **s0·t0·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `billing` | ~~s0·t0·Free account~~ → **s0·t0·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `tables` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `search` | ~~s0·t0·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `terms` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Free** | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Free** |
| `landing` | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— |

##### pro: baseline 56bdd82 → candidate — light

| Route | 390 | 561 | 640 | 720 | 1280 |
|---|---|---|---|---|---|
| `dashboard` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | ~~s2·t5·RecallC Pro~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `browse` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Pro** |
| `browse-part-iii` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Pro** |
| `article-14` | ~~s0·t0·Free account~~ → **s0·t0·hidden·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Pro** |
| `laws` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Pro** |
| `laws-ndps` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Pro** |
| `laws-uapa` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Pro** |
| `ndps-section-8` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Pro** |
| `playground` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Pro** |
| `playground-plans` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Pro** |
| `calendar` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | ~~s2·t5·RecallC Pro~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `profile` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | ~~s2·t5·RecallC Pro~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `settings` | s0·t0·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | ~~s2·t5·RecallC Pro~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `billing` | s0·t0·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | ~~s2·t5·RecallC Pro~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `tables` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Pro** |
| `search` | ~~s0·t0·Free account~~ → **s1·t5·hidden·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Pro** |
| `terms` | ~~s1·t5·Free account~~ → **s1·t5·hidden·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s2·t5·Free account~~ → **s1·t0·ok·RecallC Pro** | s1·t0·ok·RecallC Pro | ~~s1·t0·Free account~~ → **s1·t0·ok·RecallC Pro** |
| `landing` | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— |
| `playground-add-uapa` | s1·t5·hidden·RecallC Pro | s1·t0·covered·RecallC Pro | s1·t0·covered·RecallC Pro | s1·t0·covered·RecallC Pro | s1·t0·covered·RecallC Pro |

##### pro: baseline 56bdd82 → candidate — dark

| Route | 390 | 561 | 640 | 720 | 1280 |
|---|---|---|---|---|---|
| `dashboard` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `browse` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `browse-part-iii` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `article-14` | s0·t0·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `laws` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `laws-ndps` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `laws-uapa` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `ndps-section-8` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `playground` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `playground-plans` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `calendar` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `profile` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `settings` | s0·t0·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `billing` | s0·t0·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `tables` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `search` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `terms` | s1·t5·hidden·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `landing` | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— |
| `playground-add-uapa` | s1·t5·hidden·RecallC Pro | s1·t0·covered·RecallC Pro | s1·t0·covered·RecallC Pro | s1·t0·covered·RecallC Pro | s1·t0·covered·RecallC Pro |


## 5. Widths 561–720 (transition range)
All three viewers at 561, 640, 720 and 899 px after the header fix: one surface, no phone tabs, avatar visible and hit-testable (signed in) or the Sign in button (guest), no header overlaps, no horizontal scroll. Guest `/calendar` is the sign-in gate (no shell by design). Visual check: `range/candidate_free_browse_640x900_light.png` and `…_720x900_light.png` show brand + avatar on the first header row and the tabs on the second; compare `range/baseline_pro_browse_640x900_light.png` / `…_720…` for the overlap.

**guest — light**

| Route | 561 | 640 | 720 | 899 |
|---|---|---|---|---|
| `dashboard` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `browse` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `laws-ndps` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `playground` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `calendar` | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— |
| `profile` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `settings` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `billing` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `search` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `terms` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |

**guest — dark**

| Route | 561 | 640 | 720 | 899 |
|---|---|---|---|---|
| `dashboard` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `browse` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `laws-ndps` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `playground` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `calendar` | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— | s0·t0·—·— |
| `profile` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `settings` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `billing` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `search` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |
| `terms` | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— | s1·t0·—·— |

**free — light**

| Route | 561 | 640 | 720 | 899 |
|---|---|---|---|---|
| `dashboard` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `browse` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `laws-ndps` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `playground` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `calendar` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `profile` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `settings` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `billing` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `search` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `terms` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |

**free — dark**

| Route | 561 | 640 | 720 | 899 |
|---|---|---|---|---|
| `dashboard` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `browse` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `laws-ndps` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `playground` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `calendar` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `profile` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `settings` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `billing` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `search` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |
| `terms` | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free | s1·t0·ok·RecallC Free |

**pro — light**

| Route | 561 | 640 | 720 | 899 |
|---|---|---|---|---|
| `dashboard` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `browse` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `laws-ndps` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `playground` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `calendar` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `profile` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `settings` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `billing` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `search` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `terms` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |

**pro — dark**

| Route | 561 | 640 | 720 | 899 |
|---|---|---|---|---|
| `dashboard` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `browse` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `laws-ndps` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `playground` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `calendar` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `profile` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `settings` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `billing` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `search` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |
| `terms` | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro | s1·t0·ok·RecallC Pro |

## 6. Tier variants (only where the visible result differs)
Only the chip differs between tiers; shell structure is identical, so tier variants were captured on four routes at 390/640/1280 (light). Halted and expired were not re-captured: their label text is unchanged from today's titles (`test_shell_m1r.py::test_halted_and_expired_keep_their_status_titles` pins it).

| Tier | Route | 390 | 640 | 1280 |
|---|---|---|---|---|
| plus | `browse` | s1·t5·hidden·RecallC Plus | s1·t0·ok·RecallC Plus | s1·t0·ok·RecallC Plus |
| plus | `laws-ndps` | s1·t5·hidden·RecallC Plus | s1·t0·ok·RecallC Plus | s1·t0·ok·RecallC Plus |
| plus | `playground` | s1·t5·hidden·RecallC Plus | s1·t0·ok·RecallC Plus | s1·t0·ok·RecallC Plus |
| plus | `billing` | s0·t0·hidden·RecallC Plus | s1·t0·ok·RecallC Plus | s1·t0·ok·RecallC Plus |
| max | `browse` | s1·t5·hidden·RecallC Max | s1·t0·ok·RecallC Max | s1·t0·ok·RecallC Max |
| max | `laws-ndps` | s1·t5·hidden·RecallC Max | s1·t0·ok·RecallC Max | s1·t0·ok·RecallC Max |
| max | `playground` | s1·t5·hidden·RecallC Max | s1·t0·ok·RecallC Max | s1·t0·ok·RecallC Max |
| max | `billing` | s0·t0·hidden·RecallC Max | s1·t0·ok·RecallC Max | s1·t0·ok·RecallC Max |

## 7. Accessibility (§3.6)
| Check | Status | Note |
|---|---|---|
| V-D01 dark theme | PASS (captured) | Every candidate row captured in dark as well as light; no new colours were introduced — the label, nav links, tabs and the guest-gate anchor reuse existing tokens (`--muted`, `--ink`, `--pg-ink/--pg-paper`). M1-A02's guest-only contrast rules are unchanged; the signed-in shell keeps its frozen `--mid` labels (see §8). |
| V-A01/V-A02 dialogs | N/A | No dialog changed in M1-R (the Add page's dialog is M2-R's). |
| V-A03 targets | PASS (new control) | The guest gate's single action keeps the 50 px full-width style; top-nav links keep their frozen 38 px on the signed-in shell (exception already recorded in M1 §8, not extended here). |
| V-A04 zoom / automated scan / screen reader | NOT RUN | No tooling in this environment (Playwright not installed; no scanner); never reported on emulation. |
| Keyboard | NOT RUN here | Tab order of the header is unchanged (brand → tabs → account button); verified by DOM order only. |

## 8. Deviations / exceptions recorded for the owner
| ID | Where | Decision needed |
|---|---|---|
| Signed-in Settings phone bar | `mobile.css` keeps the accepted screen-11 rule (bar hidden on signed-in Settings; guests show it since M1). | Confirm the exception, or ask for parity (one CSS line). |
| Avatar at 390 | The phone shell hides the desktop header on every phone screen; the account button is therefore not visible at 390 (Profile tab is the entry). Unchanged by M1-R. | Confirm this satisfies "avatar remains visible and clickable" for phone, or ask for a phone account affordance (a design change, not in this batch). |
| Signed-in A02 (38 px targets, `--mid` inactive labels) | Frozen; M1 §8 asked for the owner's instruction before extending the guest rules to `body.is-authed`. Not changed. | Instruct, or leave. |
| Dev avatar image | The fake provider's `avatar_url` is `https://example.com/a.png`, so local captures show a broken-image glyph in the account button. Production avatars are Google's. | None (dev fixture). |
| Add page avatar `covered` | `/playground/laws/uapa/add` opens its dialog on load; the hit-test lands on the dialog backdrop. Expected for an open modal. | None. |
| DV-22 brand mark, Playground tab glyph | Unchanged (M1 §8 → M9). | None now. |

## 9. Gates
| Gate | Status |
|---|---|
| Implementation authorisation | Granted 2026-11-05 (M1-R; M2-R queued) |
| Local validation | this document — LOCAL / PRELIMINARY |
| Staging deployment | not authorised in this instruction; NOT RUN |
| Hosted acceptance | NOT RUN |
| Owner milestone decision | Pending |
