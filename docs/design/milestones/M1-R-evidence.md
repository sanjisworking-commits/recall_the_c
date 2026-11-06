# M1-R — Shared shell revision · LOCAL / PRELIMINARY evidence

| Item | Value |
|---|---|
| Branch / PR | `pg-m1r-shell-labels` from `pg-b1-entitlement-foundation` @ `56bdd82`; draft PR #232 — https://github.com/sanjisworking-commits/recall_the_c/pull/232 (base `pg-b1-entitlement-foundation`) |
| Candidate SHA | `e0e486a` for sections 1–9 (code identical to `4e22170`; `e0e486a` adds only test re-pins — `git diff 4e22170 e0e486a -- src` is empty, so those captures are the candidate's). **Close-out candidate `d7d3c30`** for section 10 (owner decisions of 2026-11-06). |
| Baseline SHA | `56bdd82` (B1 tip, before any M1-R edit; captures taken first) |
| Checklist | plan §3.3 (M1R-F01 label, M1R-F02 one Google action, M1R-F03 D33) + owner criteria 2026-11-05 (one navigation surface, five usable phone tabs, avatar visible and clickable; 390 / 561–720 / 1280; light + dark) |
| Original M1 evidence | `docs/design/milestones/M1-evidence.md` — **untouched**, pinned to its own SHA |
| Tooling | `docs/design/proto-comparison-2026-10-19/m1r/tools/capture_m1r.py` (headless Chrome over CDP; dev fake-Google sign-in in-process, cookie never written); dev server `playground-m1r-<tier>` on 8914 |
| Status | LOCAL / PRELIMINARY — hosted checks NOT RUN (no deployment). Evidence policy (owner, 2026-11-06): each row below states **PASS on this SHA** or **carried forward from an earlier SHA**. **Accepted as the reusable local baseline of the shared shell on tested `d7d3c30` (owner-forwarded review, 2026-11-06)**: the measured navigation, Profile entry, tier labels, touch targets, contrast and keyboard focus (head `e6f9110`, CI: 3 known `test_devices_m4c.py` failures / 4007 passed); §10 covers phone Profile access, the Settings tab bar, tier labels, keyboard focus, contrast and 44 px targets. Reuse it by SHA wherever this shell is used. |

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
| V-A03 targets | PASS (new control) on `e0e486a`; **shared-shell 44×44 PASS on `d7d3c30`** (§10.3) | The guest gate's single action keeps the 50 px full-width style. Top-nav links are 44 px tall for every viewer since `d7d3c30`; every visible shell control measured ≥ 44×44 in all 370 close rows. |
| V-A04 zoom / automated scan / screen reader | zoom: **PASS on `d7d3c30`** as reflow (§10.4); automated scan and screen reader: NOT RUN | Reflow checked at 320 CSS px (the 400 % equivalent of a 1280 px window) and 640 px (200 %): one surface, no horizontal scroll, no header overlap. No scanner or screen reader was run; never reported on emulation. |
| Keyboard | **PASS on `d7d3c30`** (§10.5) | Real Tab key events: header trail brand → five tabs → Pricing → account button (or Sign in), every stop with the 2 px `:focus-visible` outline; phone-bar trail Tab/Shift+Tab across the five tabs, 8/8 stops outlined, for guest, Free and Pro at 320/390/561/640/720/1280. |

## 8. Deviations / exceptions recorded for the owner
| ID | Where | Decision needed |
|---|---|---|
| Signed-in Settings phone bar | **Decided 2026-11-06 → parity.** `d7d3c30` shows the shared five-tab bar on signed-in Settings with Profile current (§10.2). | Closed. |
| Avatar at 390 | **Decided 2026-11-06 → Profile is the account entry at phone widths; the desktop avatar is hidden there by design.** Verified by tapping the Profile tab on every phone row (§10.6): lands on `/profile`, shows the signed-in identity, Profile current. | Closed (recorded). |
| Signed-in A02 (38 px targets, `--mid` inactive labels) | **Decided 2026-11-06 → applied to the whole shared shell** in `d7d3c30`: 44 px top-nav links, `--muted` phone-tab labels, measured contrast ≥ 5.05:1 on every shell label (§10.3). | Closed. |
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
| Owner milestone decision | Three shell decisions taken 2026-11-06 and implemented in `d7d3c30` (§10); milestone acceptance pending the owner's record |

## 10. Close-out on `d7d3c30` (owner decisions of 2026-11-06)

Captured once more after the three decisions, on the same local pipeline, for guest, Free and Pro at **320, 390, 561, 640, 720 and 1280 px**, light and dark, nine routes each (`/dashboard`, `/browse`, `/laws/ndps`, `/playground`, `/calendar`, `/profile`, `/settings`, `/search`, `/billing/subscriptions`): **370 rows**, every one probe-backed. Status vocabulary follows the owner's evidence policy: **PASS on `d7d3c30`** means measured on this SHA; **carried forward** names the SHA whose evidence still stands.

### 10.1 What changed since `e0e486a`
| Decision | Change | Files |
|---|---|---|
| 1 · Phone avatar | No code change. Profile is the account entry at phone widths; the desktop avatar is hidden there by the phone shell (`mobile.css` shell rule, unchanged). Verified by tapping it (§10.6). | — |
| 2 · Signed-in Settings | The shared five-tab bar shows on Settings for every viewer; the generic hide list no longer names `settings`; the Free, Plus and Expired Settings blocks no longer hide the bar and the panel clears it (`calc(var(--m-tabbar) + 28px + safe-area)`). Profile stays current (`shell_profile` covers `/settings*`). | `mobile.css`, `playground.css` |
| 3 · Signed-in accessibility | A02 applies to the whole shared shell: `.PrimaryTabs--top .nav-link` is 44 px tall for every viewer; phone-tab labels use `--muted`; the guest-only rules and the frozen 38 px / `--mid` rules are removed. The ≥ 561 rule sets **no colour**: the first attempt set `--muted` there, which out-specified `.nav-link.is-active` and painted the active pill grey-on-ink (3.46:1 light / 2.51:1 dark) — the new contrast probe caught it and the rule was corrected before this capture. | `styles.css`, `mobile.css` |
| Evidence | Representative light **and dark** captures committed under `docs/design/proto-comparison-2026-10-19/m1r/close/` (14 PNGs + three manifests) so reviewers can open them from the PR. | docs |
| Pins | `main89→main90`, `mob108→mob109`, `pg53→pg54`. | `base.html`, 59 test modules |

Tests: `tests/test_guest_shell_parity.py` (A02 rules now shared: 44 px, no colour in the ≥ 561 rule, base `--muted` / active `--on-accent`), `tests/test_shell_m1r.py`, the guest / Free / Plus / Expired Settings screen-7 suites (bar shown, panel clearance) and `tests/test_settings_phone.py`. Full suite on `d7d3c30`: **3 failed (the known `tests/test_devices_m4c.py` baseline, unchanged), 4007 passed, 163 skipped, 14 deselected** (local, 7 min 08 s).

### 10.2 Route matrix — PASS on `d7d3c30`
Cell = `s<surfaces>·t<phone tabs>·<avatar>`; avatar `ok` = visible and the hit-test lands on it, `hidden` = desktop header hidden by the phone shell (decision 1), `none` = guest (Sign in button instead). Flags would read `SMALL` (a shell control under 44×44), `LOWC` (a shell label under 4.5:1), `HSCROLL`, `OVL`; **no row carries any flag**. Light and dark rows were identical in every cell.

**guest**

| route | 320 | 390 | 561 | 640 | 720 | 1280 |
|---|---|---|---|---|---|---|
| `dashboard` | s1·t5·none | s1·t5·none | s1·t0·none | s1·t0·none | s1·t0·none | s1·t0·none |
| `browse` | s1·t5·none | s1·t5·none | s1·t0·none | s1·t0·none | s1·t0·none | s1·t0·none |
| `laws-ndps` | s1·t5·none | s1·t5·none | s1·t0·none | s1·t0·none | s1·t0·none | s1·t0·none |
| `playground` | s1·t5·none | s1·t5·none | s1·t0·none | s1·t0·none | s1·t0·none | s1·t0·none |
| `calendar` | s0·t0·none | s0·t0·none | s0·t0·none | s0·t0·none | s0·t0·none | s0·t0·none |
| `profile` | s1·t5·none | s1·t5·none | s1·t0·none | s1·t0·none | s1·t0·none | s1·t0·none |
| `settings` | s1·t5·none | s1·t5·none | s1·t0·none | s1·t0·none | s1·t0·none | s1·t0·none |
| `search` | s1·t5·none | s1·t5·none | s1·t0·none | s1·t0·none | s1·t0·none | s1·t0·none |
| `billing` | s0·t0·none | s0·t0·none | s1·t0·none | s1·t0·none | s1·t0·none | s1·t0·none |

**free**

| route | 320 | 390 | 561 | 640 | 720 | 1280 |
|---|---|---|---|---|---|---|
| `dashboard` | s1·t5·hidden | s1·t5·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |
| `browse` | s1·t5·hidden | s1·t5·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |
| `laws-ndps` | s1·t5·hidden | s1·t5·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |
| `playground` | s1·t5·hidden | s1·t5·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |
| `calendar` | s1·t5·hidden | s1·t5·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |
| `profile` | s1·t5·hidden | s1·t5·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |
| `settings` | s1·t5·hidden | s1·t5·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |
| `search` | s1·t5·hidden | s1·t5·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |
| `billing` | s0·t0·hidden | s0·t0·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |

**pro**

| route | 320 | 390 | 561 | 640 | 720 | 1280 |
|---|---|---|---|---|---|---|
| `dashboard` | s1·t5·hidden | s1·t5·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |
| `browse` | s1·t5·hidden | s1·t5·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |
| `laws-ndps` | s1·t5·hidden | s1·t5·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |
| `playground` | s1·t5·hidden | s1·t5·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |
| `calendar` | s1·t5·hidden | s1·t5·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |
| `profile` | s1·t5·hidden | s1·t5·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |
| `settings` | s1·t5·hidden | s1·t5·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |
| `search` | s1·t5·hidden | s1·t5·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |
| `billing` | s0·t0·hidden | s0·t0·hidden | s1·t0·ok | s1·t0·ok | s1·t0·ok | s1·t0·ok |

Pre-existing, by design, unchanged (carried forward from `e0e486a`): guest `/calendar` is the sign-in gate (no shell); `/billing/subscriptions` at phone widths is the bar-less checkout screen; `/search` shows the shared bar for everyone (M1-R).

### 10.3 Contrast and target sizes — PASS on `d7d3c30`
Measured on the rendered page: text colour against the composited background behind each control (the phone bar's 94 % paper mix composites to `#fefefe`). Every distinct (viewer, theme, control, state) combination:

| viewer | theme | control | state | fg | bg | ratio | box |
|---|---|---|---|---|---|---|---|
| guest | light | phonetab | current | `#141414` | `#fefefe` | **18.24** | 64×60 |
| guest | light | phonetab | inactive | `#6b6b6b` | `#fefefe` | **5.28** | 64×60 |
| guest | dark | phonetab | current | `#f2f2f0` | `#1e1e1d` | **14.96** | 64×60 |
| guest | dark | phonetab | inactive | `#9a9a9a` | `#1e1e1d` | **5.96** | 64×60 |
| guest | light | topnav | current | `#ffffff` | `#141414` | **18.42** | 80×44 |
| guest | light | topnav | inactive | `#6b6b6b` | `#ffffff` | **5.33** | 87×44 |
| guest | light | signin | inactive | `#ffffff` | `#141414` | **18.42** | 77×44 |
| guest | dark | topnav | current | `#141414` | `#f2f2f0` | **16.44** | 80×44 |
| guest | dark | topnav | inactive | `#9a9a9a` | `#1e1e1d` | **5.93** | 87×44 |
| guest | dark | signin | inactive | `#141414` | `#f2f2f0` | **16.44** | 77×44 |
| guest | dark | phonetab | current | `#ecebe6` | `#1e1e1d` | **14.05** | 64×60 |
| free | light | phonetab | current | `#141414` | `#fefefe` | **18.24** | 64×60 |
| free | light | phonetab | inactive | `#6b6b6b` | `#fefefe` | **5.28** | 64×60 |
| free | dark | phonetab | current | `#f2f2f0` | `#1e1e1d` | **14.96** | 64×60 |
| free | dark | phonetab | inactive | `#9a9a9a` | `#1e1e1d` | **5.96** | 64×60 |
| free | light | topnav | current | `#ffffff` | `#141414` | **18.42** | 80×44 |
| free | light | topnav | inactive | `#6b6b6b` | `#ffffff` | **5.33** | 87×44 |
| free | light | account | inactive | `#000000` | `#ffffff` | **21** | 52×48 |
| free | dark | topnav | current | `#141414` | `#f2f2f0` | **16.44** | 80×44 |
| free | dark | topnav | inactive | `#9a9a9a` | `#1e1e1d` | **5.93** | 87×44 |
| free | dark | account | inactive | `#ffffff` | `#1e1e1d` | **16.68** | 52×48 |
| free | light | chip | inactive | `#6b6b6b` | `#ffffff` | **5.33** | 118×14 |
| free | dark | chip | inactive | `#9a9a9a` | `#1e1e1d` | **5.93** | 118×14 |
| free | light | account | inactive | `#000000` | `#ffffff` | **21** | 44×44 |
| free | dark | account | inactive | `#ffffff` | `#1e1e1d` | **16.68** | 44×44 |
| free | dark | phonetab | current | `#ecebe6` | `#1e1e1d` | **14.05** | 64×60 |
| pro | light | phonetab | current | `#141414` | `#fefefe` | **18.24** | 64×60 |
| pro | light | phonetab | inactive | `#6b6b6b` | `#fefefe` | **5.28** | 64×60 |
| pro | dark | phonetab | current | `#f2f2f0` | `#1e1e1d` | **14.96** | 64×60 |
| pro | dark | phonetab | inactive | `#9a9a9a` | `#1e1e1d` | **5.96** | 64×60 |
| pro | light | topnav | current | `#ffffff` | `#141414` | **18.42** | 80×44 |
| pro | light | topnav | inactive | `#6b6b6b` | `#ffffff` | **5.33** | 87×44 |
| pro | light | account | inactive | `#000000` | `#ffffff` | **21** | 52×48 |
| pro | dark | topnav | current | `#141414` | `#f2f2f0` | **16.44** | 80×44 |
| pro | dark | topnav | inactive | `#9a9a9a` | `#1e1e1d` | **5.93** | 87×44 |
| pro | dark | account | inactive | `#ffffff` | `#1e1e1d` | **16.68** | 52×48 |
| pro | light | chip | inactive | `#6b6b6b` | `#ffffff` | **5.33** | 118×14 |
| pro | dark | chip | inactive | `#9a9a9a` | `#1e1e1d` | **5.93** | 118×14 |
| pro | light | account | inactive | `#000000` | `#ffffff` | **21** | 44×44 |
| pro | dark | account | inactive | `#ffffff` | `#1e1e1d` | **16.68** | 44×44 |
| pro | light | phonetab | current | `#0e7569` | `#fefefe` | **5.52** | 64×60 |
| pro | dark | phonetab | current | `#2a9d8f` | `#1e1e1d` | **5.05** | 64×60 |

Rows with any shell control under 44×44: **0**. Rows with any shell label under 4.5:1: **0**.

Lowest shell-label ratio across all rows: **5.05:1** (Pro, dark, Playground's teal active tab); lowest inactive label: **5.28:1** light / **5.93:1** dark. Smallest shell control: **44×44** (account button at 561–899, where its copy is hidden); top-nav links 80–124 × 44; phone tabs 64 × 60 at 320 px and 78 × 60 at 390 px.

### 10.4 Reflow / zoom — PASS on `d7d3c30` (reflow only)
320 CSS px (≙ 400 % zoom of a 1280 px window) and 640 CSS px (≙ 200 %) are in the matrix above: one navigation surface, five phone tabs at 320, no horizontal scroll, no header overlap, no small target. Browser text-only zoom, an automated scanner and a screen reader were **NOT RUN**.

### 10.5 Keyboard focus — PASS on `d7d3c30`
Real Tab / Shift+Tab key events over CDP; after every stop the focused element, its `:focus-visible` state and its computed outline were recorded. Header trail at ≥ 561: brand → Today → Browse → Playground → Calendar → Profile → Pricing → account button (guests: → Sign in), **every stop outlined** (`2px solid` ink; teal on the account button). Phone-bar trail at 320/390: the bar sits last in the DOM, so focus was placed on its first tab and then driven with Tab ×4 and Shift+Tab ×4 — **8/8 stops outlined** for guest, Free and Pro on Browse and Settings. (The 14-stop "page content only" trails at phone widths show that page content precedes the fixed bar in tab order; the bar is reachable after it. "Playground Tes…" is the account button's visible copy at 1280, "Account menu" its label below 900.)

| viewer | route | width | trail | stops with visible outline | shell stops |
|---|---|---|---|---|---|
| guest | `browse` | 320 | focusTrail | 14/14 | 0: (page content only) |
| guest | `browse` | 320 | phoneBarTrail | 8/8 | 8: Browse → Playground → Calendar → Profile → Today |
| guest | `browse` | 390 | focusTrail | 14/14 | 0: (page content only) |
| guest | `browse` | 390 | phoneBarTrail | 8/8 | 8: Browse → Playground → Calendar → Profile → Today |
| guest | `browse` | 561 | focusTrail | 8/8 | 7: Recall the C → Today → Browse → Playground → Calendar → Profile → Sign in |
| guest | `browse` | 640 | focusTrail | 8/8 | 7: Recall the C → Today → Browse → Playground → Calendar → Profile → Sign in |
| guest | `browse` | 720 | focusTrail | 8/8 | 7: Recall the C → Today → Browse → Playground → Calendar → Profile → Sign in |
| guest | `browse` | 1280 | focusTrail | 8/8 | 7: Recall the C → Today → Browse → Playground → Calendar → Profile → Sign in |
| guest | `settings` | 320 | focusTrail | 2/2 | 1: ← Today |
| guest | `settings` | 320 | phoneBarTrail | 8/8 | 8: Browse → Playground → Calendar → Profile → Today |
| guest | `settings` | 390 | focusTrail | 2/2 | 1: ← Today |
| guest | `settings` | 390 | phoneBarTrail | 8/8 | 8: Browse → Playground → Calendar → Profile → Today |
| guest | `settings` | 561 | focusTrail | 8/8 | 7: Recall the C → Today → Browse → Playground → Calendar → Profile → Sign in |
| guest | `settings` | 640 | focusTrail | 8/8 | 7: Recall the C → Today → Browse → Playground → Calendar → Profile → Sign in |
| guest | `settings` | 720 | focusTrail | 8/8 | 7: Recall the C → Today → Browse → Playground → Calendar → Profile → Sign in |
| guest | `settings` | 1280 | focusTrail | 8/8 | 7: Recall the C → Today → Browse → Playground → Calendar → Profile → Sign in |
| free | `browse` | 320 | focusTrail | 14/14 | 0: (page content only) |
| free | `browse` | 320 | phoneBarTrail | 8/8 | 8: Browse → Playground → Calendar → Profile → Today |
| free | `browse` | 390 | focusTrail | 14/14 | 0: (page content only) |
| free | `browse` | 390 | phoneBarTrail | 8/8 | 8: Browse → Playground → Calendar → Profile → Today |
| free | `browse` | 561 | focusTrail | 9/9 | 8: Recall the C → Today → Browse → Playground → Calendar → Profile → Pricing → Account menu |
| free | `browse` | 640 | focusTrail | 9/9 | 8: Recall the C → Today → Browse → Playground → Calendar → Profile → Pricing → Account menu |
| free | `browse` | 720 | focusTrail | 9/9 | 8: Recall the C → Today → Browse → Playground → Calendar → Profile → Pricing → Account menu |
| free | `browse` | 1280 | focusTrail | 9/9 | 8: Recall the C → Today → Browse → Playground → Calendar → Profile → Pricing → Playground Tes |
| free | `settings` | 320 | focusTrail | 2/2 | 1: ← Today |
| free | `settings` | 320 | phoneBarTrail | 8/8 | 8: Browse → Playground → Calendar → Profile → Today |
| free | `settings` | 390 | focusTrail | 2/2 | 1: ← Today |
| free | `settings` | 390 | phoneBarTrail | 8/8 | 8: Browse → Playground → Calendar → Profile → Today |
| free | `settings` | 561 | focusTrail | 9/9 | 8: Recall the C → Today → Browse → Playground → Calendar → Profile → Pricing → Account menu |
| free | `settings` | 640 | focusTrail | 9/9 | 8: Recall the C → Today → Browse → Playground → Calendar → Profile → Pricing → Account menu |
| free | `settings` | 720 | focusTrail | 9/9 | 8: Recall the C → Today → Browse → Playground → Calendar → Profile → Pricing → Account menu |
| free | `settings` | 1280 | focusTrail | 9/9 | 8: Recall the C → Today → Browse → Playground → Calendar → Profile → Pricing → Playground Tes |
| pro | `browse` | 320 | focusTrail | 14/14 | 0: (page content only) |
| pro | `browse` | 320 | phoneBarTrail | 8/8 | 8: Browse → Playground → Calendar → Profile → Today |
| pro | `browse` | 390 | focusTrail | 14/14 | 0: (page content only) |
| pro | `browse` | 390 | phoneBarTrail | 8/8 | 8: Browse → Playground → Calendar → Profile → Today |
| pro | `browse` | 561 | focusTrail | 9/9 | 8: Recall the C → Today → Browse → Playground → Calendar → Profile → Pricing → Account menu |
| pro | `browse` | 640 | focusTrail | 9/9 | 8: Recall the C → Today → Browse → Playground → Calendar → Profile → Pricing → Account menu |
| pro | `browse` | 720 | focusTrail | 9/9 | 8: Recall the C → Today → Browse → Playground → Calendar → Profile → Pricing → Account menu |
| pro | `browse` | 1280 | focusTrail | 9/9 | 8: Recall the C → Today → Browse → Playground → Calendar → Profile → Pricing → Playground Tes |
| pro | `settings` | 320 | focusTrail | 2/2 | 1: ← Today |
| pro | `settings` | 320 | phoneBarTrail | 8/8 | 8: Browse → Playground → Calendar → Profile → Today |
| pro | `settings` | 390 | focusTrail | 2/2 | 1: ← Today |
| pro | `settings` | 390 | phoneBarTrail | 8/8 | 8: Browse → Playground → Calendar → Profile → Today |
| pro | `settings` | 561 | focusTrail | 9/9 | 8: Recall the C → Today → Browse → Playground → Calendar → Profile → Pricing → Account menu |
| pro | `settings` | 640 | focusTrail | 9/9 | 8: Recall the C → Today → Browse → Playground → Calendar → Profile → Pricing → Account menu |
| pro | `settings` | 720 | focusTrail | 9/9 | 8: Recall the C → Today → Browse → Playground → Calendar → Profile → Pricing → Account menu |
| pro | `settings` | 1280 | focusTrail | 9/9 | 8: Recall the C → Today → Browse → Playground → Calendar → Profile → Pricing → Playground Tes |

### 10.6 Profile tab tap at phone widths — PASS on `d7d3c30`
After each 320/390 light probe the Profile tab's centre was clicked with a real mouse event. Every tap landed on `/profile` (`data-mscreen="account"`), the Profile tab became current, and the page showed the viewer's identity — the signed-in display name (with the account e-mail further down the page) for Free and Pro, "Guest" for guests. Landing-page screenshot: `close/close-pro_pro_browse_390x844_light_tap-profile.png`.

| viewer | from | width | lands on | identity shown | current tab after | email on page |
|---|---|---|---|---|---|---|
| guest | `dashboard` | 320 | `/profile` (account) | Guest | Profile | no |
| guest | `dashboard` | 390 | `/profile` (account) | Guest | Profile | no |
| guest | `browse` | 320 | `/profile` (account) | Guest | Profile | no |
| guest | `browse` | 390 | `/profile` (account) | Guest | Profile | no |
| guest | `laws-ndps` | 320 | `/profile` (account) | Guest | Profile | no |
| guest | `laws-ndps` | 390 | `/profile` (account) | Guest | Profile | no |
| guest | `playground` | 320 | `/profile` (account) | Guest | Profile | no |
| guest | `playground` | 390 | `/profile` (account) | Guest | Profile | no |
| guest | `profile` | 320 | `/profile` (account) | Guest | Profile | no |
| guest | `profile` | 390 | `/profile` (account) | Guest | Profile | no |
| guest | `settings` | 320 | `/profile` (account) | Guest | Profile | no |
| guest | `settings` | 390 | `/profile` (account) | Guest | Profile | no |
| guest | `search` | 320 | `/profile` (account) | Guest | Profile | no |
| guest | `search` | 390 | `/profile` (account) | Guest | Profile | no |
| free | `dashboard` | 320 | `/profile` (account) | Playground Tester | Profile | yes |
| free | `dashboard` | 390 | `/profile` (account) | Playground Tester | Profile | yes |
| free | `browse` | 320 | `/profile` (account) | Playground Tester | Profile | yes |
| free | `browse` | 390 | `/profile` (account) | Playground Tester | Profile | yes |
| free | `laws-ndps` | 320 | `/profile` (account) | Playground Tester | Profile | yes |
| free | `laws-ndps` | 390 | `/profile` (account) | Playground Tester | Profile | yes |
| free | `playground` | 320 | `/profile` (account) | Playground Tester | Profile | yes |
| free | `playground` | 390 | `/profile` (account) | Playground Tester | Profile | yes |
| free | `calendar` | 320 | `/profile` (account) | Playground Tester | Profile | yes |
| free | `calendar` | 390 | `/profile` (account) | Playground Tester | Profile | yes |
| free | `profile` | 320 | `/profile` (account) | Playground Tester | Profile | yes |
| free | `profile` | 390 | `/profile` (account) | Playground Tester | Profile | yes |
| free | `settings` | 320 | `/profile` (account) | Playground Tester | Profile | yes |
| free | `settings` | 390 | `/profile` (account) | Playground Tester | Profile | yes |
| free | `search` | 320 | `/profile` (account) | Playground Tester | Profile | yes |
| free | `search` | 390 | `/profile` (account) | Playground Tester | Profile | yes |
| pro | `dashboard` | 320 | `/profile` (account) | Playground Tester | Profile | yes |
| pro | `dashboard` | 390 | `/profile` (account) | Playground Tester | Profile | yes |
| pro | `browse` | 320 | `/profile` (account) | Playground Tester | Profile | yes |
| pro | `browse` | 390 | `/profile` (account) | Playground Tester | Profile | yes |
| pro | `laws-ndps` | 320 | `/profile` (account) | Playground Tester | Profile | yes |
| pro | `laws-ndps` | 390 | `/profile` (account) | Playground Tester | Profile | yes |
| pro | `playground` | 320 | `/profile` (account) | Playground Tester | Profile | yes |
| pro | `playground` | 390 | `/profile` (account) | Playground Tester | Profile | yes |
| pro | `calendar` | 320 | `/profile` (account) | Playground Tester | Profile | yes |
| pro | `calendar` | 390 | `/profile` (account) | Playground Tester | Profile | yes |
| pro | `profile` | 320 | `/profile` (account) | Playground Tester | Profile | yes |
| pro | `profile` | 390 | `/profile` (account) | Playground Tester | Profile | yes |
| pro | `settings` | 320 | `/profile` (account) | Playground Tester | Profile | yes |
| pro | `settings` | 390 | `/profile` (account) | Playground Tester | Profile | yes |
| pro | `search` | 320 | `/profile` (account) | Playground Tester | Profile | yes |
| pro | `search` | 390 | `/profile` (account) | Playground Tester | Profile | yes |

### 10.7 Carried forward (unchanged by the close-out)
| Item | Evidence SHA | Why it still stands |
|---|---|---|
| Tier label on every shared page (M1R-F01, DV-20), Plus / Max chip variants | `e0e486a` | `web/shell.py` and the `base.html` slot are untouched; the close matrix re-confirms `RecallC Free` / `RecallC Pro` on every signed-in row. |
| One signed-in nav + one phone bar, D33 (Act pages light Browse) | `e0e486a` | Templates untouched; the close matrix re-confirms `s1` on every non-gate row. |
| 561–899 two-row header, no overlaps | `e0e486a` (range re-capture) | CSS block untouched; close rows at 561/640/720 show `overlaps=0`. |
| Guest Playground gate: one Google action (M1R-F02 / 5-11) | `e0e486a` | Untouched. |
| Original M1 evidence | its own SHA (`docs/design/milestones/M1-evidence.md`) | Untouched. |

### 10.8 Still open / not run
| Item | Status |
|---|---|
| Automated accessibility scan, screen reader | NOT RUN (no tooling here; to be run on a hosted build) |
| Hosted / staging checks | NOT RUN (no deployment authorised) |
| Dev avatar placeholder (`https://example.com/a.png`) | dev fixture, unchanged |
| DV-22 brand mark, Playground tab glyph | M9 |
| M2-R | draft PR #235 (`pg-m2r-act-head`, stacked on this branch); its evidence carries this shell forward from `d7d3c30` |
| Owner sign-off | **Accepted** (owner-forwarded review, 2026-11-06) as the reusable local shared-shell baseline on `d7d3c30`. Reopen only when `web/shell.py`, `base.html`, the shell CSS/JS, their data or a shared dependency changes the shell's rendering or behaviour; automated permission checks continue for every tier regardless. |
| Combined SHA with Browse/Schedules | `main @ ea15591` (PR #233; acceptance record in PR #234, overflow fix in PR #236) is not yet an ancestor of this branch. When they first come together, run one focused shell-and-Schedule check on the combined SHA; afterwards reopen shared evidence only on change. |
