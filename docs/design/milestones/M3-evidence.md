# M3 — Browse and Laws catalogue by tier · LOCAL / PRELIMINARY evidence

| Item | Value |
|---|---|
| Branch / PR | `pg-m3-browse-laws`, cut from `pg-m2r-act-head` @ `9c47d1e`; draft PR #237 (base `pg-m2r-act-head`) — https://github.com/sanjisworking-commits/recall_the_c/pull/237 |
| Integration commit | `945a67f` = merge of `main` @ `ea15591` into `9c47d1e` (no M3 edit; conflicts were the asset pins in `base.html` and the two pin tests, resolved to the stack's pins plus main's new `schedules.js?v=sched1` include); `149047a` re-pins seven stack tests to main's Browse copy and classifies `browse_schedule.html` |
| Candidate (rendered source) | `08f2055` — the Browse / Laws implementation (plus `94a5aa3` card meta, which it builds on) and `8ce26f0` (empty badge wrapper); **tested SHA `55da7eb`** (tests `4a3b0fd`, re-pins `8c161c1`) |
| Checklist | `docs/design/milestones/M3.md` @ `aad33e0` (PR #218) as corrected by the tier-revision plan §3.4; owner decisions of 2026-11-06 (§6) |
| Flag | `PLAYGROUND_TIER_MODEL` stays `monthly` by default; M3 prints no Playground allowance copy under either model (read-back rows under both) |
| Tooling | `docs/design/proto-comparison-2026-10-19/m1r/tools/capture_m1r.py` (route probe: navigation surfaces, phone bar, label, hScroll, 44 px targets, composited contrast, Tab trails); `…/m3/tools/readback_m3.py` (nine account states × two tier models through the app's own TestClient); `…/m3/tools/keyboard_m3.py` (headless CDP: Tab to a Part toggle, Enter / Space, legend filter + Clear); dev launchers `playground-m3-<tier>` (monthly, port 8918) and `playground-m3-<tier>-choices` |
| Status | LOCAL / PRELIMINARY — hosted checks NOT RUN (no deployment). Every row states **PASS on this SHA**, **carried forward from SHA**, **BLOCKED** or **NOT RUN**. **Accepted as the reusable local baseline for Browse, the Laws catalogue and the shell on these surfaces, on tested `55da7eb` (owner-forwarded review, 2026-11-07)**; §8 records the sign-off, its CI qualification and what stays open. |

## 0. Gate 2 — combined baseline on `945a67f` (before any M3 edit)

Focused shell-and-Schedule check (`m3/00-merge-check/{guest,free}/`, 72 rows: `/browse`, `/browse/schedules/eighth`, `/laws`, `/laws/ndps`, `/dashboard`, `/settings` × 390 / 720 / 1280 × light / dark, guest and Free):

| Check | Result on `945a67f` |
|---|---|
| Phone navigation (390) | exactly one phone bar on every route, one navigation surface; Profile tap recorded (`--tap-profile`) |
| Desktop header (720, 1280) | one navigation surface, no phone bar; signed-in label `RecallC Free` on every route (visible at 1280, in the collapsed account control at 390 / 720) |
| Schedules on Browse | 12 Schedule cards present for every viewer; main's lede ("…then the twelve Schedules…") and "Parts, writs, amendments" carried in by the merge |
| Representative Schedule (`/browse/schedules/eighth`) | renders; content as on `main` |
| Horizontal scroll | **none on any of the 72 rows.** The negative margin from `e84e179` is still present on this SHA (`.sched-page` measures 1288 px at a 1280 px viewport, margin `-8px -4px 0`), but the Playground stack's wrappers (`.page-wrap`, `.sheet`, `.main`) carry `overflow-x: hidden`, so the document does not scroll. The fix (`margin: -8px 0 0`) is **not** in this branch; its PASS stays attached to `e73bd41` (PR #236). When PR #236 reaches this branch the probe is re-run and the row moves to PASS on that SHA. |
| Contrast / targets | 0 low-contrast rows, 0 sub-44 px targets (the M1-R shell, carried forward from `d7d3c30`) |
| Tests on `945a67f` | targeted integration suites: 219 passed. Full suite: **10 failed, 4040 passed, 176 skipped** = the 3 known `test_devices_m4c.py` failures + 7 stack tests pinning the pre-Schedules Browse copy / template count, re-pinned in `149047a` (copy only; no behaviour test weakened) |

Carried forward unchanged by the merge: shared shell from M1-R `d7d3c30` (PR #232), Browse/Schedules content and routing from `ea15591` (PR #234 record), Act head and Add dialog from M2-R `3ad4b82` / `bd9347a` (PR #235).

### 0.1 Baseline-before-edit of the M3 surfaces (`m3/01-baseline-945a67f/`)
- Captures (reduced policy): guest `/browse`, `/browse/part/iii`, `/laws`, `/laws/ndps`, `/laws?q=ndps`, `/laws?subject=criminal`, `/laws?status=repealed` at 390 / 1280 × light / dark (28 rows, Tab trails on `browse` and `laws`); Free `/browse`, `/laws`, `/laws/ndps` (12 rows); Plus `/browse`, `/laws` after adding NDPS through the app's own Add sheet (4 rows, light).
- Read-back rows (`readback.md`, `readback.json`; monthly model; today-relative subscription windows): **the Free summary ("Free plan — pick any 3 Articles… Unlock all") is served to Free, Pro, Max, paused and pending accounts**; Plus, expired and halted get none; the guest strip still promises "save 3 Articles"; every signed-in `/laws` prints six per-card Playground buttons on phone; the guest `/laws` is the fixture (chips include "Commercial", omit "Health"); the search field is hidden behind a toggle on every viewer; `/browse` phone shows the Part rail and the Marks sheet. These are the defects M3 closes (§1).

## 1. What changed (scope diff)

| Criterion | Change | Files |
|---|---|---|
| M3-F01 / F02 (Q1, Q5) | One Browse body for both widths. Each Part header is an `<h2>` holding one `<button class="browse-part-toggle" data-browse-part-toggle aria-expanded="true" aria-controls="browse-part-N-body">` over `<div class="browse-part-body" id=…>`; open by default (without JS the page is the open state); `app.js` flips `aria-expanded` and hides only that Part's body. The phone Part-card rail, its per-Part progress work (`part_cards`) and the Marks sheet are retired; the marks filter is the inline legend (icons + text labels, Q2; 44 px items on phone); the phone header keeps only the search icon. `/browse/part/{slug}` stays reachable by URL and from the article reader. main's Schedules section keeps its plain header. | `browse_index.html`, `web/app.py` (`browse_index`), `static/app.js`, `static/mobile.css`, `static/styles.css` |
| M3-F03 (Q4, D19, 5-11) | Banner slot by viewer. Guest: "Reading as a guest. Sign in to save your progress." + one **Continue with Google** action (`/auth/google/start?next=%2Fbrowse`, built with `playground_google_href`). Free: "Free plan — every Article, progress saved." + **View Playground** → `/playground`, shown only when the new snapshot predicate `request_is_free_account` is true — the same partition the shell uses for its `RecallC Free` label — so Plus, Pro, Max and pending never receive it (paused does, as the label does). Expired / halted keep their header status. The dead `access.is_free` "Saved" / "Preview only" markers are gone. No Article restriction, no Playground allowance sentence, no price. | `browse_index.html`, `entitlements/dependencies.py` (`snapshot_is_free_account`, `request_is_free_account`), `web/app.py` |
| M3-F04 / F07 (Q3) | One Laws body for every viewer and width: the guest fixture `web/guest_laws_index.py` and the `data-guest-laws-desktop` section are deleted; one `data-laws-index data-laws-body` section; no card carries a Playground CTA — a card prints at most its status badge through the new `playground_status_badge` macro (same `LawPlaygroundCta` wrapper and data attributes, no `pg-btn` / `pg-lede` / `pg-actions` / `data-pg-sheet`). Desktop Laws CSS consolidated to one rule-set (`body[data-mscreen="laws"]`). | `laws.html`, `partials/playground.html`, `web/app.py` (`laws_page`), `static/styles.css`, `static/mobile.js` |
| M3-F05 (Q5) | The search field is always visible and labelled (`<label for="laws-q">Search laws</label>`, placeholder); the phone toggle is retired from the template and `mobile.js`; chips are All + `catalog.visible_subjects` + Repealed ("Health" in, "Commercial" out); `?q`, `?subject`, `?status=repealed` echo unchanged. | `laws.html`, `static/mobile.js`, `static/mobile.css` |
| M3-F06 (Q3) | Card meta for a full Bare Act equals the Act head's own `BareAct.head_meta_label`, read from the committed sitemap manifest (schema 3, `head_meta_label` per law) — `/laws` still hydrates nothing (`docs/law-loading.md`); key-provisions laws keep the seed's `scope_label`; no seed content change. NDPS `8 Chapters · Sections 1–83 · Schedule`, UAPA `7 Chapters · Sections 1–53 · Schedules`, BNSS `39 Chapters · Sections 1–531 · Schedules`, MTP `Sections 1–8`. | `scripts/build_law_sitemap_manifest.py`, `web/law_sitemap_manifest.json`, `web/law_catalog.py` (`card_meta_label`, `CatalogLaw.card_meta_label`) |
| Pins | `styles.css main90→main91`, `mobile.css mob109→mob110`, `mobile.js mob30→mob31`, `app.js main62→main63`; 44 test modules re-pinned mechanically. | `base.html`, tests |

Untouched: the article reader, the Part reader body, `/search`, `/tables`, the Act head and Add sheet (M2-R), entitlement logic and the flag default, `law_catalog.seed.json`, Playground home copy (M7-R), `/pricing`.

## 2. Tests
| Run | Result |
|---|---|
| New module `tests/test_browse_laws_family.py` (11 tests: F01–F07, the Free-predicate / shell-label invariant, gate 1 × 2 models) | 11 passed |
| Re-pinned screen modules (18 files; reasons in `M3-test-changes.md` §E) | 211 passed, 23 skipped (Playwright, not installed locally) |
| Guard set that must stay green unchanged (`test_laws_request_bootstrap`, `test_laws_request_breakdown`, `test_law_loading`, `test_law_catalog`, the six `test_browse_*` structure/marks modules, `test_browse_schedules`, `test_shell_m1r`, `test_footer_laws_memory`, `test_feature_flags_memory_laws`, `test_act_head_m2r`, `test_bareact_head_family`, `test_playground_r1`) | 203 passed |
| Full suite on the candidate before the last four re-pins (`test_ndps_reader` lede, `test_playground` Laws-hub CTA → badge, `test_signed_in_playground_gate_screen7` "View Playground" ×2) | 7 failed = 3 known `test_devices_m4c.py` baseline + those 4; 4054 passed, 176 skipped |
| Full suite on the tested SHA `55da7eb` (after the re-pins and the badge-wrapper `|trim`) | **3 failed (the known `tests/test_devices_m4c.py` baseline), 4058 passed, 176 skipped** (8 min 17 s) |

No behaviour test was weakened; the three `test_devices_m4c.py` failures are the documented baseline shared by every branch.

## 3. Gate 1 — the Free Article promise through the real Learn → Done flow

| Mode | Result | Evidence |
|---|---|---|
| `monthly` | **PASS on `4a3b0fd`** | `tests/test_browse_laws_family.py::test_gate1_free_account_saves_a_fourth_article_without_a_claim_prompt[monthly]`: a Free account (no subscription row) opens the Learn pages of four distinct Constitution Articles (1, 2, 3, 4), completes every mode through the real `/learn/{unit}/seen` and `/quiz` handlers and posts `/learn/{unit}/done`: no `claim_required`, no `?claim=1` redirect, `ok: true` four times; `ProgressRecord.times_completed == 1` and `next_revision` set for all four; a **fresh session** (new client, same account) reads the same progress and schedule, opens each Learn page without a claim redirect, and the calendar month of each `next_revision` renders; `claimed_articles` stays empty (Free is every Article). |
| `choices` | **PASS on `4a3b0fd`** | same test, `[choices]` parametrisation. |
| Live UI (dev launcher, Free, `monthly`) | observed | signed-in Free `/browse` shows the new summary; `/learn/article-4-clause-1` renders Step 1 of 6 with `data-locked-modes=""` and no claim prompt. A full six-mode click-through in the browser pane was not performed (the pane could not composite frames in this session); the automated flow above exercises the same handlers. |

Outcome: the banner copy rows in §4 are **not BLOCKED** in either mode.

## 4. Route matrix (candidate `08f2055`; captures in `m3/02-candidate-08f2055/`)

Probe facts on every captured row: one navigation surface; one phone bar at 390; `hScroll` false; 0 low-contrast rows (min composited ratio 5.28:1 at phone, 5.33:1 at desktop); 0 sub-44 px shell targets.

| Route | Viewer | Widths × themes | Result | Status |
|---|---|---|---|---|
| `/browse` | guest | 390 / 1280 × light / dark | title + lede; guest strip with one Google action → `/auth/google/start?next=%2Fbrowse`; Laws / Tables cards; inline legend (News, Visualise; icons + labels); "The Constitution" label; 24 Part toggles, each `aria-expanded="true"` over its grid; Schedules section (12 cards); Tab trail 14 / 14 outlined at 390 (search → Google → Laws → Tables → News → Visualise → Part I toggle → Articles…), 8 / 8 at 1280 | **PASS on `08f2055`** |
| `/browse` | Free | 390 / 1280 × light / dark | same body; Free summary "Free plan — every Article, progress saved." + "View Playground"; label `RecallC Free`; Tab trail 14 / 14 and 9 / 9 outlined | **PASS on `08f2055`** |
| `/browse` | Plus (NDPS in Playground) | 390 / 1280 light | same body; **no** banner; label `RecallC Plus` | **PASS on `08f2055`** |
| `/browse` | Pro, Max, pending | read-back, both models | no banner (header label `RecallC Pro` / `RecallC Max` / `RecallC Plus`) | **PASS on `08f2055`** (read-back) |
| `/browse` | paused | read-back, both models | Free summary (the shell labels a paused row `RecallC Free`) | **PASS on `08f2055`** (read-back) |
| `/browse` | expired, halted | read-back, both models | no banner; header status "Your Playground is paused" / "Payment retries have stopped" unchanged | **PASS on `08f2055`** (read-back) |
| `/browse` Part toggles | guest | 390 / 1280 (`keyboard.json`) | Tab reaches the Part I toggle after 7 (390) / 13 (1280) stops with `:focus-visible` (2 px solid outline); toggle box 354×52 / 1200×44; **Enter** → `aria-expanded="false"`, that body `display: none`, Part II still open; **Space** → open again; legend item click → `aria-pressed="true"`, 490 cards hidden; second click clears (0 hidden) | **PASS on `08f2055`** |
| `/browse` widths | guest | 320 / 560 / 561 / 720 / 768 / 844×390, light | no horizontal scroll; two-column article grid at 320 (`minmax(0, 1fr)`); strip wraps | **PASS on `08f2055`** |
| `/browse/part/iii` | guest | 390 / 1280 × light / dark | unchanged page (`← All Parts`, rows); reachable by URL and from `/browse/article/20` | **PASS on `08f2055`** (unchanged; also carried forward from `ea15591`) |
| `/laws` | guest | 390 / 1280 × light / dark | back link; kicker / title / lede; visible labelled search field; chips All · Criminal · Constitutional · Administrative · Environmental · Financial · Health · Repealed; 13 cards with meta from the head rule; no card button; Tab trail 14 / 14 and 8 / 8 outlined | **PASS on `08f2055`** |
| `/laws` | Free | 390 / 1280 × light / dark | identical body; no "Subscribe" / "Unlock" / price anywhere | **PASS on `08f2055`** |
| `/laws` | Plus (NDPS added through the app) | 390 / 1280 light | identical body; one `ALREADY IN PLAYGROUND` badge on the NDPS card, no button | **PASS on `08f2055`** |
| `/laws` | Pro, Max, paused, pending, expired, halted | read-back, both models | identical body; `pg-btn = 0`; chips as above; no price | **PASS on `08f2055`** (read-back) |
| `/laws?q=ndps`, `?subject=criminal`, `?status=repealed` | guest | 390 / 1280 × light / dark | `data-initial-*` echoed; empty state present | **PASS on `08f2055`** |
| `/laws` widths | guest | 320 … 844×390 | no horizontal scroll; chips scroll horizontally | **PASS on `08f2055`** |
| `/laws/{id}` Add dialog | — | — | M2-R `3ad4b82` / `bd9347a` | carried forward |
| Shared shell on both pages | all | all rows | one nav surface, one phone bar, label per snapshot, 0 shell contrast / target findings | carried forward from M1-R `d7d3c30` (re-confirmed by every probe row) |
| Schedules on `/browse` | all | all rows | 12 cards | carried forward from `ea15591` |

## 5. Visual and accessibility (§3.6)

| Check | Status | Note |
|---|---|---|
| V-D01 dark theme | **PASS on `08f2055`** | guest and Free captured in dark at 390 / 1280; tokens only (`--muted`, `--mid`, `--ink`, `--rc-*`); composited contrast ≥ 5.28:1 on every probed control. Palette check, not prototype fidelity. |
| V-A01 keyboard | **PASS on `08f2055`** | Part toggles are real buttons reached by Tab with a visible outline; Enter / Space toggle; legend items `aria-pressed`; search input labelled; chips are buttons with `aria-pressed` (unchanged). |
| V-A02 targets / labels | **PASS on `08f2055`** for new components | Part toggles ≥ 44 px (52 at phone), legend items 44 px at phone, Google action 44 px, search field 44 px, Laws back link 44 px. Pre-existing, not new: the desktop legend items keep their 22 px height (M1 exception, unchanged). |
| V-A03 200 % zoom | NOT RUN | real browser zoom was not available in this session (the pane could not composite frames); the 320 px rows stand as supporting evidence only. |
| V-A04 automated scan / screen reader | NOT RUN | no tooling here. |
| V-F01 fidelity | recorded | phone Browse follows the prototype's layout (title + lede, banner slot, Laws / Tables, legend, collapsible Parts over a two-column grid); the legend keeps icons (Q2 deviation, accessibility-driven); the guest legend label prints "News" where signed-in prints "In news" (pre-existing, open point). Laws phone follows the prototype (back link, kicker, title, lede, search, chips, cards). Desktop regression: Laws desktop now uses the signed-in rule-set for guests too (footer no longer hidden on guest Laws; card padding 16×18 instead of 18×20) — recorded as F08 differences, before / after PNGs in `01-baseline-945a67f/guest` vs `02-candidate-08f2055/guest`. |

## 6. Decisions (owner, 2026-11-06)
| # | Decision |
|---|---|
| Baseline | `pg-m2r-act-head` @ `9c47d1e` + `main` @ `ea15591` (integration commit `945a67f`) |
| Q1 | `/browse/part/{slug}` stays reachable; phone Part rail retired; collapsible Part headers (`<button aria-expanded>`), open by default |
| Q2 | Marks legend: icons with text labels |
| Q3 | one data-driven catalogue for every viewer; card meta from `BareAct.head_meta_label`; chips from `catalog.visible_subjects`; guest fixture deleted |
| Q4 | Free summary for RecallC Free only, phone and desktop; none for Plus / Pro / Max; expired / halted keep their header status |
| Q5 | phone Browse keeps the search icon; marks filter inline (sheet retired); Laws search field visible |
| Copy | Free: "Free plan — every Article, progress saved." + "View Playground" → `/playground` (the review's note: "Unlock all" implied locked Articles); guest: "Reading as a guest. Sign in to save your progress." with one Google action; no price, no law-choice sentence |
| Record | The older checklist's "three active laws" is superseded by **"three permanent law choices per account"** (B1 / M2-R model); M3 itself prints no allowance copy under either model |
| Open point | guest legend label "News" vs signed-in "In news" (pre-existing; not in today's decisions) |

## 7. Not run
Hosted / staging checks; automated accessibility scan; screen reader; real 200 % zoom; a six-mode click-through of gate 1 in the browser pane (the automated flow covers the handlers).

## 8. Owner sign-off (owner-forwarded review, 2026-11-07)

| Item | Record |
|---|---|
| Decision | **Accepted** as the reusable local baseline: the passing M3 checks (§2 tests, §3 gate 1 under both tier models, §4 route matrix, §5 visual / a11y) on tested `55da7eb`. Shared Browse, catalogue and shell evidence is carried forward by SHA; reopen only an affected component or a visible tier difference (see `evidence-carry-forward` policy, 2026-11-06). |
| CI qualification | PR head `5b7679c` (docs only, on top of `55da7eb`): workflow run 42183014839 **succeeded with the unit-test step skipped** (the gate runs pytest only on `workflow_dispatch`, a `[ci full]` commit message, or a commit count divisible by 3); the run on `55da7eb` (42181990900) was cancelled by the concurrency rule when `5b7679c` was pushed. The executed full-suite evidence is therefore the local run on `55da7eb` (§2: 3 known `test_devices_m4c.py` failures / 4058 passed / 176 skipped). The commit that records this section carries `[ci full]` so GitHub executes the unit job on the final head; its result is recorded below once it finishes. |
| GitHub unit run on the final head | PENDING at the time of writing — see the row appended by the follow-up commit. |
| Schedule overflow | stays **open as a follow-up**: on this branch the excess width is hidden by the stack's `overflow-x: hidden` wrappers (§0). Apply PR #236 (`e73bd41`) when that fix is integrated, then rerun the focused width probe and move the row to PASS on that SHA. |
| NOT RUN (recorded, unchanged) | real 200 % zoom, automated accessibility scan, screen reader, hosted / staging checks (§7). |
| Wording follow-up | guest legend "News" vs signed-in "In news" (§6 open point): to be standardised in the next UI batch that touches the Browse legend. |
| Next milestone | M4 — Today (`/dashboard`): remaining scope and tier-specific states, carrying forward the accepted shell (`d7d3c30`) and this Browse / catalogue baseline (`55da7eb`). |

