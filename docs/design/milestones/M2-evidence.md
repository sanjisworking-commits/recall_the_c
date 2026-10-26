# M2 — Bare Act head family · LOCAL / PRELIMINARY evidence

Status: **LOCAL/PRELIMINARY — under owner review (2026-10-20), not accepted.** Produced from a local run of this branch; it does
**not** close hosted acceptance. No staging deployment has been made for M2
(that needs the owner's separate authorisation, checklist §7); the hosted
paid states (Plus/Pro/Max, expired, halted) stay **unverified** until a
staging-only test grant exists. Merge is not authorised. PR #188, #218 and
#219 stay draft; production untouched.

| | |
|---|---|
| Checklist | `docs/design/milestones/M2.md` on PR #218 — decisions Q1–Q4 and §4a approved 2026-10-19; implementation authorised 2026-10-19 after M1's acceptance with documented exceptions |
| Baseline | `pg-m1-guest-shell` @ `9281f27` (branch head; the M1 shell code is `7f78992`, the later commits are evidence and tests only) |
| Candidate | `pg-m2-act-head` @ `a146dff2176d53a645a52fa6fa519f1daf506ccc` (stacked on `pg-m1-guest-shell`) |
| Local servers | the Playground dev launcher pointed at this worktree (fake Google auth, throwaway SQLite DB), port 8913, started once per fixture: `--tier free`, `plus`, `pro`, `max`, `expired`, and a new `halted` tier (subscription status `halted`, the same shape the halted test cohort seeds). The guest matrix was captured on the Free server without signing in. NDPS was added to the roster on the Plus server (the same confirm → scope POSTs the tests send) before the Pro/Max/halted/expired fixtures were captured, so those show a retained law |
| Capture tools | `docs/design/proto-comparison-2026-10-19/m2/tools/` — `capture_m2.py` (headless Google Chrome 155.0.8059.82 over CDP, DPR 1, fonts awaited, 0.6 s settle, sign-in through the dev provider with cookies injected in-process and never written; per route it records a viewport PNG, a full-page PNG, the HTTP status chain and a head probe: kicker, title, meta, CTA labels/hrefs, chapter/schedule/section rows with their hrefs, About toggle, dialog state; routes flagged `sheet` are captured again after the first `[data-pg-sheet]` trigger is clicked), `capture_states.py` (chapter expanded, About open, focused row/schedule), `capture_keyboard.py` (Tab order, Enter on a chapter row, sheet open → Tab cycle → Escape), `capture_proto.py` (the prototype wrapper states), `m2_tables.py` (the §4 tables from the manifests) |
| Prototype references | 18 Oct exports (hashes in M1.md Appendix A.1) served through `make_wrappers.py`; `screen=act&law={ndps,uapa,bns}&viewer={guest,signedIn,plus,pro,max,expired,halted}[&sheet=1]` on both surfaces — 70 PNGs in `m2/proto/` |
| Evidence folder | `docs/design/proto-comparison-2026-10-19/m2/` — `frozen/` and `candidate/` light viewport captures (guest and Free for every route; Plus/Pro/Max/expired/halted for the Act-head and Add rows), `responsive/`, `states/`, `keyboard/`, `proto/`, `manifests/` (every manifest with SHA-256 per PNG, the keyboard trace, and `all_captures_sha256.json` — the hashes of all 1,502 captured PNGs including the dark, full-page and regression captures that are not committed) |
| Test changes | `docs/design/milestones/M2-test-changes.md` — every edited test with its reason |
| Complete capture archive | `~/Downloads/m2-local-evidence-a146dff.zip` (113 MB, SHA-256 `2be1a4b380fbc6912a0c49ef77def6d1d657735bc0819536dea9b6c8374c81d9`): an offline side-by-side gallery (`index.html`) of all 818 viewport captures — frozen, candidate, sheet-opened and prototype, light and dark — plus the 624 full-page captures; every file's hash is also in `manifests/all_captures_sha256.json` |

## 1. What changed (scope diff)

Source files, candidate vs `9281f27`:

```
 src/constitution_memorizer/playground/routes.py                 |   23 +-
 src/constitution_memorizer/web/app.py                           |  154 +--
 src/constitution_memorizer/web/bare_act_page.py                 |  168 +++  (new)
 src/constitution_memorizer/web/bare_acts.py                     |   12 +
 src/constitution_memorizer/web/guest_bareact_head.py            |   83 -    (deleted)
 src/constitution_memorizer/web/static/mobile.css                |  505 --
 src/constitution_memorizer/web/static/mobile.js                 |   11 +-
 src/constitution_memorizer/web/static/playground.css            | 1228 ++----
 src/constitution_memorizer/web/static/playground.js             |   28 +-
 src/constitution_memorizer/web/static/styles.css                |  711 ++---
 src/constitution_memorizer/web/templates/bare_act.html          |  477 ++---
 src/constitution_memorizer/web/templates/base.html              |   10 +-   (cache pins)
 src/constitution_memorizer/web/templates/partials/playground_add_panel.html | 115 + (new)
 src/constitution_memorizer/web/templates/playground_add.html    |  213 +--
```

- `bare_act.html` — one head for every Bare Act and every viewer: `section.panel.ActHead[data-act-head][data-pg-kind][data-membership]` with the band (back link, kicker "Bare Act · India Code" + catalogue status pill, `act.title`, `act.head_meta_label`, the action, About-this-act below it) and one list: `details.bareact-chapter` rows (closed; `summary[aria-expanded]` → the chapter's section links) followed by the schedule rows (unchanged markup, overlay link to the reader; a non-navigable schedule keeps "Not yet browsable in the app"). MTP lists its sections flat. The six per-surface variants, the fixture head, the Chapters/Schedules tab row and the "This Act has no Schedules." line are gone. The action is the live `LawPlaygroundState` by `kind`: guest "Sign in to use Playground", Free "Subscribe to use Playground", subscriber "+ Add to Playground" (all opening the sheet), already active → chip "Already in Playground" + Sections + the state's primary ("Continue"/"Start learning" for a subscriber, "Resume Playground" expired, "Manage subscription" halted) with the state's own hrefs; roster-full / pending / device-blocked keep their ghost button, chip and note; the state's `secondary_copy` prints as a note under the button.
- `web/bare_act_page.py` (new) — `bare_act_page_context(request, bare)` builds the Act page's context (was inline in `app.py`'s `law_detail_page`) and `halted_law_presentation` moved here unchanged; the Laws route and the Add route both use it. `bare_acts.py` gains `BareAct.head_meta_label` (`meta_label` + " · Schedule"/"· Schedules" read off the Act's schedules). `app.py` drops the fixture import and the `guest_screen4` context. No route, eligibility, entitlement, roster, billing or data change.
- `playground_add.html` + `partials/playground_add_panel.html` — one sheet per state, both widths. Opened by URL the page is the Act page with the panel inside `<dialog class="pg-sheet" open data-pg-sheet-direct data-pg-sheet-return="/laws/{id}">` (Q4); `playground.js` re-opens it as a modal, and closing it restores the Act's URL. Opened in-page the fetch sends `X-Requested-With: pg-sheet` and the panel renders alone (as does the no-JS POST re-render), so adding a law never reads the Act JSON (the M6 contract tests keep that). Copy per the prototype: title "Add to Playground"; guest lede/Sign in/Create an account (real links on both widths — the phone twin's inert buttons are gone); Free lede "Turning The UAPA, 1967 into a learning experience needs a plan. Reading it stays free." + "Unlock Playground" → `/playground` + footnote "Plus · Pro · Max — from ₹199 / month. Constitution learning stays free." (tiers and price from the catalogue); subscriber confirm "The UAPA, 1967 joins this month's Playground — learnable, verbatim. The reader itself never changes." + the space lines + the unchanged confirm form and scope step; expired/halted resume and device/pending/full states unchanged in behaviour. Reading names are the registry spec's `short_name` for every Act (the NDPS-only `guest_add_reading_name` and `plus_add_*` variants are no longer rendered).
- CSS — `styles.css`: the per-surface head blocks replaced by one "Bare Act head (M2)" block (desktop + 561–1279 + ≤560 rules, `.ActHead*` and `.ActHead .bareact-*` overrides); `mobile.css`: the guest/Free/Plus phone head blocks removed (the legacy `body[data-mscreen="bareact"] .bareact-chapter-row/.bareact-section-row` rules are kept and still apply); `playground.css`: the guest/Free/Plus/expired/halted Add-sheet variant blocks and the expired phone head replaced by one "Add sheet (M2)" block (`.pg-add-*`). Pins `main87→main88`, `mob106→mob107`, `pg49→pg50`, `playground.js pg8→pg9`, `mobile.js mob29→mob30`.
- JS — `mobile.js` syncs `aria-expanded` on chapter summaries (one-open-at-a-time accordion unchanged); `playground.js` handles the server-opened dialog and sends the sheet-fetch header.

Not changed: readers (`/laws/{id}/section/{n}`, `/laws/{id}/schedule/{s}`), Laws index, Playground home/picker/learn/roster, eligibility, entitlements, device checks, billing, canonical Act JSON, the shell (M1), legal pages.

## 2. Tests (candidate `a146dff`)

Command: `PYTHONPATH=src .venv/bin/python -m pytest -m "not integration" -q -p no:cacheprovider tests`

| Run | Result |
|---|---|
| Full suite at `a146dff` (run 3, 390 s) | **3,948 passed, 3 failed, 163 skipped, 1 deselected** — the three failures are the documented `tests/test_devices_m4c.py` exceptions (`test_existing_registered_device_stays_allowed_at_churn_cap`, `test_admin_reset_does_not_erase_replacement_history`, `test_admin_clears_replacement_lock_with_audit`), identical on M1 and the frozen baseline |
| New `tests/test_bareact_head_family.py` | 39 passed — M2-F01 (every Bare Act renders the generated head; meta == `head_meta_label`; chapter rows == `chapter_count`; schedule rows == `len(schedules)`; the fixture and its context no longer exist), F02 (every section reachable through its chapter row), F03 (schedule rows link to their readers; BNSS's undrawable schedule stays listed and unlinked; BNS/PSS list none), F04 (guest/Free/Plus/Pro/Max/halted CTAs by kind with the live hrefs; Playground disabled → head without a CTA), F05 (direct URL = Act page with the open dialog, one panel; Plus confirm/scope contract and the roster write unchanged; reading names from the registry), F06 (About below the action), F07 (MTP flat) and the stylesheet/pin checks |
| Cohort screen tests (18 files) | rewritten against the contract in `m2/tools/M2_TEST_CONTRACT.md`; all green (Playwright tests skip here as before). Changes and reasons: `M2-test-changes.md` §C |
| Other tests touched | 65 files: 81 accepted-screen pins re-pointed to the new markers, 93 cache-pin assertions bumped, the reader/About/Playground contract tests listed in `M2-test-changes.md` §A–B |
| Skipped | 163 — Playwright not installed (unchanged); those tests are **NOT RUN**, not passed |

Note on the three suite runs: run 1 overlapped with the test rewrite (39 failures, all stale); run 2 on the settled tree had the 3 device exceptions plus one pin on a since-replaced CSS rule (fixed, re-run green); run 3 is the clean record at `a146dff` (logged in the PR).

Source-hash drift: the canonical Act JSON and `BARE_ACTS` are untouched (no `source_hash`/`filename` change), so the registry identity tests (`test_playground.py::test_activation_uses_registry_identity_without_reading_runtime`, `test_playground_m6.py::test_home_and_roster_hydrate_zero_acts`) pass unchanged in substance — the one edit sends the in-page fetch header for the Add GET (§1).

## 3. Functional acceptance (M2-F01…F09)

| Id | Criterion | Evidence | Verdict |
|---|---|---|---|
| F01 | every eligible Act renders the generated head; fixture gone; meta == `head_meta_label`, rows == counts | `test_bareact_head_family.py` (7 Acts incl. POTA); candidate probes: NDPS "8 Chapters · Sections 1–83 · Schedule" / 8 ch + 1 sch; UAPA "7 Chapters · Sections 1–53 · Schedules" / 7 + 4; BNS 20 + 0; BNSS 39 + 2; PSS 8 + 0; MTP "Sections 1–8" / 9 flat (§4) | PASS |
| F02 | every chapter row is a real control; every section reachable | `summary[aria-expanded]` rows; `states/state_chapter-open_*`; keyboard trace: Enter → `aria-expanded=true` on both widths; test asserts every `section_order` href is inside its chapter | PASS |
| F03 | schedule rows link to `/laws/{id}/schedule/{slug}`; non-navigable keep their state | probes: NDPS → `psychotropic-substances`, UAPA 4 rows, BNSS 1 linked + "Not yet browsable in the app"; `states/state_schedule-focus_*` | PASS |
| F04 | CTA authorisation, destinations and forms byte-identical to the frozen `playground_cta` outcomes; only §4a wording changes | §4 tables: guest/Free/Plus/Pro/Max/expired/halted labels and hrefs per kind; the chip's primary now carries the live `primary_href` (`/playground/laws/ndps` or `…/sections`) where the fixture hard-coded `/playground` (recorded as the F04 correction; the frozen full panel for every other Act already linked these) | PASS (one recorded change) |
| F05 | sheet opens in-page on both widths; confirm/scope/roster unchanged; direct URL 200 with the same forms | `candidate/*_sheet.png` (desktop 460 px modal, phone bottom sheet); direct URL status chains: 200 for guest/Free/subscriber-addable/expired/halted, 303 → `/playground/laws/ndps` when the law is already active (unchanged redirect); Plus POST confirm → 303 and roster write in `test_plus_add_sheet_keeps_the_confirm_and_scope_contract` | PASS |
| F06 | About-this-act content reachable per Q2 | `states/state_about-open_*`: card (Act No., Enacted, In force, Ministry, Department, Jurisdiction, Sections, Last modified, long title) below the action | PASS |
| F07 | chapterless Acts list sections flat; no "0 Chapters" | `candidate/cand_*_laws-mtp_*`, `test_a_chapterless_act_lists_its_sections_flat` | PASS |
| F08 | readers and their phone-bar suppression unchanged | `candidate/cand_{guest,free}_ndps-section-8_*`, `…_ndps-schedule_*` vs frozen: identical probes (no head, no bar change) | PASS |
| F09 | full suite, drift 0, sitemap/SEO/packaging green; only the three device exceptions | §2 | PASS with the 3 documented exceptions |

## 4. Route matrix — frozen vs candidate (light, viewport probes)

Columns: frozen head meta / CTA label→href / rows → candidate; "rows" counts visible chapter summaries / schedule rows / section links (the frozen legacy panel hid its schedule rows behind the Schedules tab, so they count 0 there; the fixture head's three rows count as "4 (legacy)" incl. its schedule row). Files are in `m2/frozen/` and `m2/candidate/` (guest and Free for every route; other tiers for the head and Add rows; the rest are hashed in `manifests/all_captures_sha256.json`).

Reading the Plus rows: the frozen Plus NDPS capture predates the roster add (addable state); the frozen already-active state is `manifests/frozen_plus-active.json` / `frozen/frozen-active_plus_*`. The candidate Plus/Pro/Max NDPS rows show the retained law (chip), UAPA the addable state — the two states the checklist asks for.

<!-- generated by tools/m2_tables.py from the manifests -->
| Route | Viewer | Width | Frozen meta / CTA / rows | Candidate meta / CTA / rows | Sheet (cand) | Status | Files (frozen → candidate) |
|---|---|---|---|---|---|---|---|
| `/laws/ndps` | guest | 390 | 6 Chapters · Sections 1–83 · Schedule / Sign in to use Playground→/playground/laws/ndps/add (sheet) / 4 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Sign in to use Playground→/playground/laws/ndps/add (sheet) / 8 ch / 1 sch / 0 sec | open guest 358px | 200 | `frozen_guest_laws-ndps_390x844_light.png` → `cand_guest_laws-ndps_390x844_light.png` |
| `/laws/ndps` | guest | 1280 | 6 Chapters · Sections 1–83 · Schedule / Sign in to use Playground→/playground/laws/ndps/add (sheet) / 4 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Sign in to use Playground→/playground/laws/ndps/add (sheet) / 8 ch / 1 sch / 0 sec | open guest 460px | 200 | `frozen_guest_laws-ndps_1280x900_light.png` → `cand_guest_laws-ndps_1280x900_light.png` |
| `/laws/uapa` | guest | 390 | – / Sign in to use Playground→/playground/laws/uapa/add (sheet) / 7 ch / 0 sch / 67 sec | 7 Chapters · Sections 1–53 · Schedules / Sign in to use Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | open guest 358px | 200 | `frozen_guest_laws-uapa_390x844_light.png` → `cand_guest_laws-uapa_390x844_light.png` |
| `/laws/uapa` | guest | 1280 | – / Sign in to use Playground→/playground/laws/uapa/add (sheet) / 7 ch / 0 sch / 67 sec | 7 Chapters · Sections 1–53 · Schedules / Sign in to use Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | open guest 460px | 200 | `frozen_guest_laws-uapa_1280x900_light.png` → `cand_guest_laws-uapa_1280x900_light.png` |
| `/laws/bns` | guest | 390 | – / Sign in to use Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 358 sec | 20 Chapters · Sections 1–358 / Sign in to use Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 0 sec | – | 200 | `frozen_guest_laws-bns_390x844_light.png` → `cand_guest_laws-bns_390x844_light.png` |
| `/laws/bns` | guest | 1280 | – / Sign in to use Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 358 sec | 20 Chapters · Sections 1–358 / Sign in to use Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 0 sec | – | 200 | `frozen_guest_laws-bns_1280x900_light.png` → `cand_guest_laws-bns_1280x900_light.png` |
| `/laws/bnss` | guest | 390 | – / Sign in to use Playground→/playground/laws/bnss/add (sheet) / 39 ch / 0 sch / 531 sec | 39 Chapters · Sections 1–531 · Schedules / Sign in to use Playground→/playground/laws/bnss/add (sheet) / 39 ch / 2 sch / 0 sec | – | 200 | `frozen_guest_laws-bnss_390x844_light.png` → `cand_guest_laws-bnss_390x844_light.png` |
| `/laws/bnss` | guest | 1280 | – / Sign in to use Playground→/playground/laws/bnss/add (sheet) / 39 ch / 0 sch / 531 sec | 39 Chapters · Sections 1–531 · Schedules / Sign in to use Playground→/playground/laws/bnss/add (sheet) / 39 ch / 2 sch / 0 sec | – | 200 | `frozen_guest_laws-bnss_1280x900_light.png` → `cand_guest_laws-bnss_1280x900_light.png` |
| `/laws/pss` | guest | 390 | – / Sign in to use Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 42 sec | 8 Chapters · Sections 1–38 / Sign in to use Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 0 sec | – | 200 | `frozen_guest_laws-pss_390x844_light.png` → `cand_guest_laws-pss_390x844_light.png` |
| `/laws/pss` | guest | 1280 | – / Sign in to use Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 42 sec | 8 Chapters · Sections 1–38 / Sign in to use Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 0 sec | – | 200 | `frozen_guest_laws-pss_1280x900_light.png` → `cand_guest_laws-pss_1280x900_light.png` |
| `/laws/mtp` | guest | 390 | – / Sign in to use Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | Sections 1–8 / Sign in to use Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | – | 200 | `frozen_guest_laws-mtp_390x844_light.png` → `cand_guest_laws-mtp_390x844_light.png` |
| `/laws/mtp` | guest | 1280 | – / Sign in to use Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | Sections 1–8 / Sign in to use Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | – | 200 | `frozen_guest_laws-mtp_1280x900_light.png` → `cand_guest_laws-mtp_1280x900_light.png` |
| `/playground/laws/ndps/add` | guest | 390 | – / – / 0 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Sign in to use Playground→/playground/laws/ndps/add (sheet) / 8 ch / 1 sch / 0 sec | – | 200 | `frozen_guest_add-ndps-direct_390x844_light.png` → `cand_guest_add-ndps-direct_390x844_light.png` |
| `/playground/laws/ndps/add` | guest | 1280 | – / – / 0 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Sign in to use Playground→/playground/laws/ndps/add (sheet) / 8 ch / 1 sch / 0 sec | – | 200 | `frozen_guest_add-ndps-direct_1280x900_light.png` → `cand_guest_add-ndps-direct_1280x900_light.png` |
| `/playground/laws/uapa/add` | guest | 390 | – / – / 0 (legacy) | 7 Chapters · Sections 1–53 · Schedules / Sign in to use Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | – | 200 | `frozen_guest_add-uapa-direct_390x844_light.png` → `cand_guest_add-uapa-direct_390x844_light.png` |
| `/playground/laws/uapa/add` | guest | 1280 | – / – / 0 (legacy) | 7 Chapters · Sections 1–53 · Schedules / Sign in to use Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | – | 200 | `frozen_guest_add-uapa-direct_1280x900_light.png` → `cand_guest_add-uapa-direct_1280x900_light.png` |
| `/laws/ndps/section/8` | guest | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_guest_ndps-section-8_390x844_light.png` → `cand_guest_ndps-section-8_390x844_light.png` |
| `/laws/ndps/section/8` | guest | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_guest_ndps-section-8_1280x900_light.png` → `cand_guest_ndps-section-8_1280x900_light.png` |
| `/laws/ndps/schedule/psychotropic-substances` | guest | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_guest_ndps-schedule_390x844_light.png` → `cand_guest_ndps-schedule_390x844_light.png` |
| `/laws/ndps/schedule/psychotropic-substances` | guest | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_guest_ndps-schedule_1280x900_light.png` → `cand_guest_ndps-schedule_1280x900_light.png` |
| `/laws/not-an-act` | guest | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 404 | `frozen_guest_laws-unknown_390x844_light.png` → `cand_guest_laws-unknown_390x844_light.png` |
| `/laws/not-an-act` | guest | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 404 | `frozen_guest_laws-unknown_1280x900_light.png` → `cand_guest_laws-unknown_1280x900_light.png` |
| `/laws/ndps` | Free | 390 | 6 Chapters · Sections 1–83 · Schedule / Subscribe to use Playground→/playground/laws/ndps/add (sheet) / 4 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Subscribe to use Playground→/playground/laws/ndps/add (sheet) / 8 ch / 1 sch / 0 sec | open subscribe 358px | 200 | `frozen_free_laws-ndps_390x844_light.png` → `cand_free_laws-ndps_390x844_light.png` |
| `/laws/ndps` | Free | 1280 | 6 Chapters · Sections 1–83 · Schedule / Subscribe to use Playground→/playground/laws/ndps/add (sheet) / 4 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Subscribe to use Playground→/playground/laws/ndps/add (sheet) / 8 ch / 1 sch / 0 sec | open subscribe 460px | 200 | `frozen_free_laws-ndps_1280x900_light.png` → `cand_free_laws-ndps_1280x900_light.png` |
| `/laws/uapa` | Free | 390 | – / Subscribe to use Playground→/playground/laws/uapa/add (sheet) / 7 ch / 0 sch / 67 sec | 7 Chapters · Sections 1–53 · Schedules / Subscribe to use Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | open subscribe 358px | 200 | `frozen_free_laws-uapa_390x844_light.png` → `cand_free_laws-uapa_390x844_light.png` |
| `/laws/uapa` | Free | 1280 | – / Subscribe to use Playground→/playground/laws/uapa/add (sheet) / 7 ch / 0 sch / 67 sec | 7 Chapters · Sections 1–53 · Schedules / Subscribe to use Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | open subscribe 460px | 200 | `frozen_free_laws-uapa_1280x900_light.png` → `cand_free_laws-uapa_1280x900_light.png` |
| `/laws/bns` | Free | 390 | – / Subscribe to use Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 358 sec | 20 Chapters · Sections 1–358 / Subscribe to use Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 0 sec | – | 200 | `frozen_free_laws-bns_390x844_light.png` → `cand_free_laws-bns_390x844_light.png` |
| `/laws/bns` | Free | 1280 | – / Subscribe to use Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 358 sec | 20 Chapters · Sections 1–358 / Subscribe to use Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 0 sec | – | 200 | `frozen_free_laws-bns_1280x900_light.png` → `cand_free_laws-bns_1280x900_light.png` |
| `/laws/bnss` | Free | 390 | – / Subscribe to use Playground→/playground/laws/bnss/add (sheet) / 39 ch / 0 sch / 531 sec | 39 Chapters · Sections 1–531 · Schedules / Subscribe to use Playground→/playground/laws/bnss/add (sheet) / 39 ch / 2 sch / 0 sec | – | 200 | `frozen_free_laws-bnss_390x844_light.png` → `cand_free_laws-bnss_390x844_light.png` |
| `/laws/bnss` | Free | 1280 | – / Subscribe to use Playground→/playground/laws/bnss/add (sheet) / 39 ch / 0 sch / 531 sec | 39 Chapters · Sections 1–531 · Schedules / Subscribe to use Playground→/playground/laws/bnss/add (sheet) / 39 ch / 2 sch / 0 sec | – | 200 | `frozen_free_laws-bnss_1280x900_light.png` → `cand_free_laws-bnss_1280x900_light.png` |
| `/laws/pss` | Free | 390 | – / Subscribe to use Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 42 sec | 8 Chapters · Sections 1–38 / Subscribe to use Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 0 sec | – | 200 | `frozen_free_laws-pss_390x844_light.png` → `cand_free_laws-pss_390x844_light.png` |
| `/laws/pss` | Free | 1280 | – / Subscribe to use Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 42 sec | 8 Chapters · Sections 1–38 / Subscribe to use Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 0 sec | – | 200 | `frozen_free_laws-pss_1280x900_light.png` → `cand_free_laws-pss_1280x900_light.png` |
| `/laws/mtp` | Free | 390 | – / Subscribe to use Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | Sections 1–8 / Subscribe to use Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | – | 200 | `frozen_free_laws-mtp_390x844_light.png` → `cand_free_laws-mtp_390x844_light.png` |
| `/laws/mtp` | Free | 1280 | – / Subscribe to use Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | Sections 1–8 / Subscribe to use Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | – | 200 | `frozen_free_laws-mtp_1280x900_light.png` → `cand_free_laws-mtp_1280x900_light.png` |
| `/playground/laws/ndps/add` | Free | 390 | – / – / 0 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Subscribe to use Playground→/playground/laws/ndps/add (sheet) / 8 ch / 1 sch / 0 sec | – | 200 | `frozen_free_add-ndps-direct_390x844_light.png` → `cand_free_add-ndps-direct_390x844_light.png` |
| `/playground/laws/ndps/add` | Free | 1280 | – / – / 0 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Subscribe to use Playground→/playground/laws/ndps/add (sheet) / 8 ch / 1 sch / 0 sec | – | 200 | `frozen_free_add-ndps-direct_1280x900_light.png` → `cand_free_add-ndps-direct_1280x900_light.png` |
| `/playground/laws/uapa/add` | Free | 390 | – / – / 0 (legacy) | 7 Chapters · Sections 1–53 · Schedules / Subscribe to use Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | – | 200 | `frozen_free_add-uapa-direct_390x844_light.png` → `cand_free_add-uapa-direct_390x844_light.png` |
| `/playground/laws/uapa/add` | Free | 1280 | – / – / 0 (legacy) | 7 Chapters · Sections 1–53 · Schedules / Subscribe to use Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | – | 200 | `frozen_free_add-uapa-direct_1280x900_light.png` → `cand_free_add-uapa-direct_1280x900_light.png` |
| `/laws/ndps/section/8` | Free | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_free_ndps-section-8_390x844_light.png` → `cand_free_ndps-section-8_390x844_light.png` |
| `/laws/ndps/section/8` | Free | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_free_ndps-section-8_1280x900_light.png` → `cand_free_ndps-section-8_1280x900_light.png` |
| `/laws/ndps/schedule/psychotropic-substances` | Free | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_free_ndps-schedule_390x844_light.png` → `cand_free_ndps-schedule_390x844_light.png` |
| `/laws/ndps/schedule/psychotropic-substances` | Free | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_free_ndps-schedule_1280x900_light.png` → `cand_free_ndps-schedule_1280x900_light.png` |
| `/laws/not-an-act` | Free | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 404 | `frozen_free_laws-unknown_390x844_light.png` → `cand_free_laws-unknown_390x844_light.png` |
| `/laws/not-an-act` | Free | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 404 | `frozen_free_laws-unknown_1280x900_light.png` → `cand_free_laws-unknown_1280x900_light.png` |
| `/laws/ndps` | Plus | 390 | 6 Chapters · Sections 1–83 · Schedule / + Add to Playground→/playground/laws/ndps/add (sheet) / 4 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Sections→/playground/laws/ndps/sections; Continue→/playground/laws/ndps / 8 ch / 1 sch / 0 sec | closed None 0px | 200 | `frozen_plus_laws-ndps_390x844_light.png` → `cand_plus_laws-ndps_390x844_light.png` |
| `/laws/ndps` | Plus | 1280 | 6 Chapters · Sections 1–83 · Schedule / + Add to Playground→/playground/laws/ndps/add (sheet) / 4 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Sections→/playground/laws/ndps/sections; Continue→/playground/laws/ndps / 8 ch / 1 sch / 0 sec | closed None 0px | 200 | `frozen_plus_laws-ndps_1280x900_light.png` → `cand_plus_laws-ndps_1280x900_light.png` |
| `/laws/uapa` | Plus | 390 | – / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 0 sch / 67 sec | 7 Chapters · Sections 1–53 · Schedules / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | open eligible_to_add 358px | 200 | `frozen_plus_laws-uapa_390x844_light.png` → `cand_plus_laws-uapa_390x844_light.png` |
| `/laws/uapa` | Plus | 1280 | – / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 0 sch / 67 sec | 7 Chapters · Sections 1–53 · Schedules / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | open eligible_to_add 460px | 200 | `frozen_plus_laws-uapa_1280x900_light.png` → `cand_plus_laws-uapa_1280x900_light.png` |
| `/laws/bns` | Plus | 390 | – / + Add to Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 358 sec | 20 Chapters · Sections 1–358 / + Add to Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 0 sec | – | 200 | `frozen_plus_laws-bns_390x844_light.png` → `cand_plus_laws-bns_390x844_light.png` |
| `/laws/bns` | Plus | 1280 | – / + Add to Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 358 sec | 20 Chapters · Sections 1–358 / + Add to Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 0 sec | – | 200 | `frozen_plus_laws-bns_1280x900_light.png` → `cand_plus_laws-bns_1280x900_light.png` |
| `/laws/bnss` | Plus | 390 | – / + Add to Playground→/playground/laws/bnss/add (sheet) / 39 ch / 0 sch / 531 sec | 39 Chapters · Sections 1–531 · Schedules / + Add to Playground→/playground/laws/bnss/add (sheet) / 39 ch / 2 sch / 0 sec | – | 200 | `frozen_plus_laws-bnss_390x844_light.png` → `cand_plus_laws-bnss_390x844_light.png` |
| `/laws/bnss` | Plus | 1280 | – / + Add to Playground→/playground/laws/bnss/add (sheet) / 39 ch / 0 sch / 531 sec | 39 Chapters · Sections 1–531 · Schedules / + Add to Playground→/playground/laws/bnss/add (sheet) / 39 ch / 2 sch / 0 sec | – | 200 | `frozen_plus_laws-bnss_1280x900_light.png` → `cand_plus_laws-bnss_1280x900_light.png` |
| `/laws/pss` | Plus | 390 | – / + Add to Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 42 sec | 8 Chapters · Sections 1–38 / + Add to Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 0 sec | – | 200 | `frozen_plus_laws-pss_390x844_light.png` → `cand_plus_laws-pss_390x844_light.png` |
| `/laws/pss` | Plus | 1280 | – / + Add to Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 42 sec | 8 Chapters · Sections 1–38 / + Add to Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 0 sec | – | 200 | `frozen_plus_laws-pss_1280x900_light.png` → `cand_plus_laws-pss_1280x900_light.png` |
| `/laws/mtp` | Plus | 390 | – / + Add to Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | Sections 1–8 / + Add to Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | – | 200 | `frozen_plus_laws-mtp_390x844_light.png` → `cand_plus_laws-mtp_390x844_light.png` |
| `/laws/mtp` | Plus | 1280 | – / + Add to Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | Sections 1–8 / + Add to Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | – | 200 | `frozen_plus_laws-mtp_1280x900_light.png` → `cand_plus_laws-mtp_1280x900_light.png` |
| `/playground/laws/ndps/add` | Plus | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_plus_add-ndps-direct_390x844_light.png` → `cand_plus_add-ndps-direct_390x844_light.png` |
| `/playground/laws/ndps/add` | Plus | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_plus_add-ndps-direct_1280x900_light.png` → `cand_plus_add-ndps-direct_1280x900_light.png` |
| `/playground/laws/uapa/add` | Plus | 390 | – / – / 0 (legacy) | 7 Chapters · Sections 1–53 · Schedules / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | – | 200 | `frozen_plus_add-uapa-direct_390x844_light.png` → `cand_plus_add-uapa-direct_390x844_light.png` |
| `/playground/laws/uapa/add` | Plus | 1280 | – / – / 0 (legacy) | 7 Chapters · Sections 1–53 · Schedules / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | – | 200 | `frozen_plus_add-uapa-direct_1280x900_light.png` → `cand_plus_add-uapa-direct_1280x900_light.png` |
| `/laws/ndps/section/8` | Plus | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_plus_ndps-section-8_390x844_light.png` → `cand_plus_ndps-section-8_390x844_light.png` |
| `/laws/ndps/section/8` | Plus | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_plus_ndps-section-8_1280x900_light.png` → `cand_plus_ndps-section-8_1280x900_light.png` |
| `/laws/ndps/schedule/psychotropic-substances` | Plus | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_plus_ndps-schedule_390x844_light.png` → `cand_plus_ndps-schedule_390x844_light.png` |
| `/laws/ndps/schedule/psychotropic-substances` | Plus | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_plus_ndps-schedule_1280x900_light.png` → `cand_plus_ndps-schedule_1280x900_light.png` |
| `/laws/not-an-act` | Plus | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 404 | `frozen_plus_laws-unknown_390x844_light.png` → `cand_plus_laws-unknown_390x844_light.png` |
| `/laws/not-an-act` | Plus | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 404 | `frozen_plus_laws-unknown_1280x900_light.png` → `cand_plus_laws-unknown_1280x900_light.png` |
| `/laws/ndps` | Pro | 390 | – / Sections→/playground/laws/ndps/sections; Continue→/playground/laws/ndps / 8 ch / 0 sch / 129 sec | 8 Chapters · Sections 1–83 · Schedule / Sections→/playground/laws/ndps/sections; Continue→/playground/laws/ndps / 8 ch / 1 sch / 0 sec | closed None 0px | 200 | `frozen_pro_laws-ndps_390x844_light.png` → `cand_pro_laws-ndps_390x844_light.png` |
| `/laws/ndps` | Pro | 1280 | 6 Chapters · Sections 1–83 · Schedule / Continue→/playground / 4 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Sections→/playground/laws/ndps/sections; Continue→/playground/laws/ndps / 8 ch / 1 sch / 0 sec | closed None 0px | 200 | `frozen_pro_laws-ndps_1280x900_light.png` → `cand_pro_laws-ndps_1280x900_light.png` |
| `/laws/uapa` | Pro | 390 | – / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 0 sch / 67 sec | 7 Chapters · Sections 1–53 · Schedules / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | open eligible_to_add 358px | 200 | `frozen_pro_laws-uapa_390x844_light.png` → `cand_pro_laws-uapa_390x844_light.png` |
| `/laws/uapa` | Pro | 1280 | – / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 0 sch / 67 sec | 7 Chapters · Sections 1–53 · Schedules / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | open eligible_to_add 460px | 200 | `frozen_pro_laws-uapa_1280x900_light.png` → `cand_pro_laws-uapa_1280x900_light.png` |
| `/laws/bns` | Pro | 390 | – / + Add to Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 358 sec | 20 Chapters · Sections 1–358 / + Add to Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 0 sec | – | 200 | `frozen_pro_laws-bns_390x844_light.png` → `cand_pro_laws-bns_390x844_light.png` |
| `/laws/bns` | Pro | 1280 | – / + Add to Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 358 sec | 20 Chapters · Sections 1–358 / + Add to Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 0 sec | – | 200 | `frozen_pro_laws-bns_1280x900_light.png` → `cand_pro_laws-bns_1280x900_light.png` |
| `/laws/bnss` | Pro | 390 | – / + Add to Playground→/playground/laws/bnss/add (sheet) / 39 ch / 0 sch / 531 sec | 39 Chapters · Sections 1–531 · Schedules / + Add to Playground→/playground/laws/bnss/add (sheet) / 39 ch / 2 sch / 0 sec | – | 200 | `frozen_pro_laws-bnss_390x844_light.png` → `cand_pro_laws-bnss_390x844_light.png` |
| `/laws/bnss` | Pro | 1280 | – / + Add to Playground→/playground/laws/bnss/add (sheet) / 39 ch / 0 sch / 531 sec | 39 Chapters · Sections 1–531 · Schedules / + Add to Playground→/playground/laws/bnss/add (sheet) / 39 ch / 2 sch / 0 sec | – | 200 | `frozen_pro_laws-bnss_1280x900_light.png` → `cand_pro_laws-bnss_1280x900_light.png` |
| `/laws/pss` | Pro | 390 | – / + Add to Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 42 sec | 8 Chapters · Sections 1–38 / + Add to Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 0 sec | – | 200 | `frozen_pro_laws-pss_390x844_light.png` → `cand_pro_laws-pss_390x844_light.png` |
| `/laws/pss` | Pro | 1280 | – / + Add to Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 42 sec | 8 Chapters · Sections 1–38 / + Add to Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 0 sec | – | 200 | `frozen_pro_laws-pss_1280x900_light.png` → `cand_pro_laws-pss_1280x900_light.png` |
| `/laws/mtp` | Pro | 390 | – / + Add to Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | Sections 1–8 / + Add to Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | – | 200 | `frozen_pro_laws-mtp_390x844_light.png` → `cand_pro_laws-mtp_390x844_light.png` |
| `/laws/mtp` | Pro | 1280 | – / + Add to Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | Sections 1–8 / + Add to Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | – | 200 | `frozen_pro_laws-mtp_1280x900_light.png` → `cand_pro_laws-mtp_1280x900_light.png` |
| `/playground/laws/ndps/add` | Pro | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_pro_add-ndps-direct_390x844_light.png` → `cand_pro_add-ndps-direct_390x844_light.png` |
| `/playground/laws/ndps/add` | Pro | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_pro_add-ndps-direct_1280x900_light.png` → `cand_pro_add-ndps-direct_1280x900_light.png` |
| `/playground/laws/uapa/add` | Pro | 390 | – / – / 0 (legacy) | 7 Chapters · Sections 1–53 · Schedules / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | – | 200 | `frozen_pro_add-uapa-direct_390x844_light.png` → `cand_pro_add-uapa-direct_390x844_light.png` |
| `/playground/laws/uapa/add` | Pro | 1280 | – / – / 0 (legacy) | 7 Chapters · Sections 1–53 · Schedules / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | – | 200 | `frozen_pro_add-uapa-direct_1280x900_light.png` → `cand_pro_add-uapa-direct_1280x900_light.png` |
| `/laws/ndps/section/8` | Pro | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_pro_ndps-section-8_390x844_light.png` → `cand_pro_ndps-section-8_390x844_light.png` |
| `/laws/ndps/section/8` | Pro | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_pro_ndps-section-8_1280x900_light.png` → `cand_pro_ndps-section-8_1280x900_light.png` |
| `/laws/ndps/schedule/psychotropic-substances` | Pro | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_pro_ndps-schedule_390x844_light.png` → `cand_pro_ndps-schedule_390x844_light.png` |
| `/laws/ndps/schedule/psychotropic-substances` | Pro | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_pro_ndps-schedule_1280x900_light.png` → `cand_pro_ndps-schedule_1280x900_light.png` |
| `/laws/not-an-act` | Pro | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 404 | `frozen_pro_laws-unknown_390x844_light.png` → `cand_pro_laws-unknown_390x844_light.png` |
| `/laws/not-an-act` | Pro | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 404 | `frozen_pro_laws-unknown_1280x900_light.png` → `cand_pro_laws-unknown_1280x900_light.png` |
| `/laws/ndps` | Max | 390 | – / Sections→/playground/laws/ndps/sections; Continue→/playground/laws/ndps / 8 ch / 0 sch / 129 sec | 8 Chapters · Sections 1–83 · Schedule / Sections→/playground/laws/ndps/sections; Continue→/playground/laws/ndps / 8 ch / 1 sch / 0 sec | closed None 0px | 200 | `frozen_max_laws-ndps_390x844_light.png` → `cand_max_laws-ndps_390x844_light.png` |
| `/laws/ndps` | Max | 1280 | 6 Chapters · Sections 1–83 · Schedule / Continue→/playground / 4 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Sections→/playground/laws/ndps/sections; Continue→/playground/laws/ndps / 8 ch / 1 sch / 0 sec | closed None 0px | 200 | `frozen_max_laws-ndps_1280x900_light.png` → `cand_max_laws-ndps_1280x900_light.png` |
| `/laws/uapa` | Max | 390 | – / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 0 sch / 67 sec | 7 Chapters · Sections 1–53 · Schedules / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | open eligible_to_add 358px | 200 | `frozen_max_laws-uapa_390x844_light.png` → `cand_max_laws-uapa_390x844_light.png` |
| `/laws/uapa` | Max | 1280 | – / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 0 sch / 67 sec | 7 Chapters · Sections 1–53 · Schedules / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | open eligible_to_add 460px | 200 | `frozen_max_laws-uapa_1280x900_light.png` → `cand_max_laws-uapa_1280x900_light.png` |
| `/laws/bns` | Max | 390 | – / + Add to Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 358 sec | 20 Chapters · Sections 1–358 / + Add to Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 0 sec | – | 200 | `frozen_max_laws-bns_390x844_light.png` → `cand_max_laws-bns_390x844_light.png` |
| `/laws/bns` | Max | 1280 | – / + Add to Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 358 sec | 20 Chapters · Sections 1–358 / + Add to Playground→/playground/laws/bns/add (sheet) / 20 ch / 0 sch / 0 sec | – | 200 | `frozen_max_laws-bns_1280x900_light.png` → `cand_max_laws-bns_1280x900_light.png` |
| `/laws/bnss` | Max | 390 | – / + Add to Playground→/playground/laws/bnss/add (sheet) / 39 ch / 0 sch / 531 sec | 39 Chapters · Sections 1–531 · Schedules / + Add to Playground→/playground/laws/bnss/add (sheet) / 39 ch / 2 sch / 0 sec | – | 200 | `frozen_max_laws-bnss_390x844_light.png` → `cand_max_laws-bnss_390x844_light.png` |
| `/laws/bnss` | Max | 1280 | – / + Add to Playground→/playground/laws/bnss/add (sheet) / 39 ch / 0 sch / 531 sec | 39 Chapters · Sections 1–531 · Schedules / + Add to Playground→/playground/laws/bnss/add (sheet) / 39 ch / 2 sch / 0 sec | – | 200 | `frozen_max_laws-bnss_1280x900_light.png` → `cand_max_laws-bnss_1280x900_light.png` |
| `/laws/pss` | Max | 390 | – / + Add to Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 42 sec | 8 Chapters · Sections 1–38 / + Add to Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 0 sec | – | 200 | `frozen_max_laws-pss_390x844_light.png` → `cand_max_laws-pss_390x844_light.png` |
| `/laws/pss` | Max | 1280 | – / + Add to Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 42 sec | 8 Chapters · Sections 1–38 / + Add to Playground→/playground/laws/pss/add (sheet) / 8 ch / 0 sch / 0 sec | – | 200 | `frozen_max_laws-pss_1280x900_light.png` → `cand_max_laws-pss_1280x900_light.png` |
| `/laws/mtp` | Max | 390 | – / + Add to Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | Sections 1–8 / + Add to Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | – | 200 | `frozen_max_laws-mtp_390x844_light.png` → `cand_max_laws-mtp_390x844_light.png` |
| `/laws/mtp` | Max | 1280 | – / + Add to Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | Sections 1–8 / + Add to Playground→/playground/laws/mtp/add (sheet) / 0 ch / 0 sch / 9 sec | – | 200 | `frozen_max_laws-mtp_1280x900_light.png` → `cand_max_laws-mtp_1280x900_light.png` |
| `/playground/laws/ndps/add` | Max | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_max_add-ndps-direct_390x844_light.png` → `cand_max_add-ndps-direct_390x844_light.png` |
| `/playground/laws/ndps/add` | Max | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_max_add-ndps-direct_1280x900_light.png` → `cand_max_add-ndps-direct_1280x900_light.png` |
| `/playground/laws/uapa/add` | Max | 390 | – / – / 0 (legacy) | 7 Chapters · Sections 1–53 · Schedules / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | – | 200 | `frozen_max_add-uapa-direct_390x844_light.png` → `cand_max_add-uapa-direct_390x844_light.png` |
| `/playground/laws/uapa/add` | Max | 1280 | – / – / 0 (legacy) | 7 Chapters · Sections 1–53 · Schedules / + Add to Playground→/playground/laws/uapa/add (sheet) / 7 ch / 4 sch / 0 sec | – | 200 | `frozen_max_add-uapa-direct_1280x900_light.png` → `cand_max_add-uapa-direct_1280x900_light.png` |
| `/laws/ndps/section/8` | Max | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_max_ndps-section-8_390x844_light.png` → `cand_max_ndps-section-8_390x844_light.png` |
| `/laws/ndps/section/8` | Max | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_max_ndps-section-8_1280x900_light.png` → `cand_max_ndps-section-8_1280x900_light.png` |
| `/laws/ndps/schedule/psychotropic-substances` | Max | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_max_ndps-schedule_390x844_light.png` → `cand_max_ndps-schedule_390x844_light.png` |
| `/laws/ndps/schedule/psychotropic-substances` | Max | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_max_ndps-schedule_1280x900_light.png` → `cand_max_ndps-schedule_1280x900_light.png` |
| `/laws/not-an-act` | Max | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 404 | `frozen_max_laws-unknown_390x844_light.png` → `cand_max_laws-unknown_390x844_light.png` |
| `/laws/not-an-act` | Max | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 404 | `frozen_max_laws-unknown_1280x900_light.png` → `cand_max_laws-unknown_1280x900_light.png` |
| `/laws/ndps` | expired | 390 | 6 Chapters · Sections 1–83 · Schedule / Resume Playground→/billing/subscriptions / 4 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Sections→/playground/laws/ndps/sections; Resume Playground→/billing/subscriptions / 8 ch / 1 sch / 0 sec | closed None 0px | 200 | `frozen_expired_laws-ndps_390x844_light.png` → `cand_expired_laws-ndps_390x844_light.png` |
| `/laws/ndps` | expired | 1280 | 6 Chapters · Sections 1–83 · Schedule / Resume Playground→/billing/subscriptions / 4 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Sections→/playground/laws/ndps/sections; Resume Playground→/billing/subscriptions / 8 ch / 1 sch / 0 sec | closed None 0px | 200 | `frozen_expired_laws-ndps_1280x900_light.png` → `cand_expired_laws-ndps_1280x900_light.png` |
| `/laws/uapa` | expired | 390 | – / Resume Playground→/billing/subscriptions (sheet) / 7 ch / 0 sch / 67 sec | 7 Chapters · Sections 1–53 · Schedules / Resume Playground→/billing/subscriptions (sheet) / 7 ch / 4 sch / 0 sec | closed None 0px | 200 | `frozen_expired_laws-uapa_390x844_light.png` → `cand_expired_laws-uapa_390x844_light.png` |
| `/laws/uapa` | expired | 1280 | – / Resume Playground→/billing/subscriptions (sheet) / 7 ch / 0 sch / 67 sec | 7 Chapters · Sections 1–53 · Schedules / Resume Playground→/billing/subscriptions (sheet) / 7 ch / 4 sch / 0 sec | closed None 0px | 200 | `frozen_expired_laws-uapa_1280x900_light.png` → `cand_expired_laws-uapa_1280x900_light.png` |
| `/laws/bns` | expired | 390 | – / Resume Playground→/billing/subscriptions (sheet) / 20 ch / 0 sch / 358 sec | 20 Chapters · Sections 1–358 / Resume Playground→/billing/subscriptions (sheet) / 20 ch / 0 sch / 0 sec | – | 200 | `frozen_expired_laws-bns_390x844_light.png` → `cand_expired_laws-bns_390x844_light.png` |
| `/laws/bns` | expired | 1280 | – / Resume Playground→/billing/subscriptions (sheet) / 20 ch / 0 sch / 358 sec | 20 Chapters · Sections 1–358 / Resume Playground→/billing/subscriptions (sheet) / 20 ch / 0 sch / 0 sec | – | 200 | `frozen_expired_laws-bns_1280x900_light.png` → `cand_expired_laws-bns_1280x900_light.png` |
| `/laws/bnss` | expired | 390 | – / Resume Playground→/billing/subscriptions (sheet) / 39 ch / 0 sch / 531 sec | 39 Chapters · Sections 1–531 · Schedules / Resume Playground→/billing/subscriptions (sheet) / 39 ch / 2 sch / 0 sec | – | 200 | `frozen_expired_laws-bnss_390x844_light.png` → `cand_expired_laws-bnss_390x844_light.png` |
| `/laws/bnss` | expired | 1280 | – / Resume Playground→/billing/subscriptions (sheet) / 39 ch / 0 sch / 531 sec | 39 Chapters · Sections 1–531 · Schedules / Resume Playground→/billing/subscriptions (sheet) / 39 ch / 2 sch / 0 sec | – | 200 | `frozen_expired_laws-bnss_1280x900_light.png` → `cand_expired_laws-bnss_1280x900_light.png` |
| `/laws/pss` | expired | 390 | – / Resume Playground→/billing/subscriptions (sheet) / 8 ch / 0 sch / 42 sec | 8 Chapters · Sections 1–38 / Resume Playground→/billing/subscriptions (sheet) / 8 ch / 0 sch / 0 sec | – | 200 | `frozen_expired_laws-pss_390x844_light.png` → `cand_expired_laws-pss_390x844_light.png` |
| `/laws/pss` | expired | 1280 | – / Resume Playground→/billing/subscriptions (sheet) / 8 ch / 0 sch / 42 sec | 8 Chapters · Sections 1–38 / Resume Playground→/billing/subscriptions (sheet) / 8 ch / 0 sch / 0 sec | – | 200 | `frozen_expired_laws-pss_1280x900_light.png` → `cand_expired_laws-pss_1280x900_light.png` |
| `/laws/mtp` | expired | 390 | – / Resume Playground→/billing/subscriptions (sheet) / 0 ch / 0 sch / 9 sec | Sections 1–8 / Resume Playground→/billing/subscriptions (sheet) / 0 ch / 0 sch / 9 sec | – | 200 | `frozen_expired_laws-mtp_390x844_light.png` → `cand_expired_laws-mtp_390x844_light.png` |
| `/laws/mtp` | expired | 1280 | – / Resume Playground→/billing/subscriptions (sheet) / 0 ch / 0 sch / 9 sec | Sections 1–8 / Resume Playground→/billing/subscriptions (sheet) / 0 ch / 0 sch / 9 sec | – | 200 | `frozen_expired_laws-mtp_1280x900_light.png` → `cand_expired_laws-mtp_1280x900_light.png` |
| `/playground/laws/ndps/add` | expired | 390 | – / – / 0 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Sections→/playground/laws/ndps/sections; Resume Playground→/billing/subscriptions / 8 ch / 1 sch / 0 sec | – | 200 | `frozen_expired_add-ndps-direct_390x844_light.png` → `cand_expired_add-ndps-direct_390x844_light.png` |
| `/playground/laws/ndps/add` | expired | 1280 | – / – / 0 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Sections→/playground/laws/ndps/sections; Resume Playground→/billing/subscriptions / 8 ch / 1 sch / 0 sec | – | 200 | `frozen_expired_add-ndps-direct_1280x900_light.png` → `cand_expired_add-ndps-direct_1280x900_light.png` |
| `/playground/laws/uapa/add` | expired | 390 | – / – / 0 (legacy) | 7 Chapters · Sections 1–53 · Schedules / Resume Playground→/billing/subscriptions (sheet) / 7 ch / 4 sch / 0 sec | – | 200 | `frozen_expired_add-uapa-direct_390x844_light.png` → `cand_expired_add-uapa-direct_390x844_light.png` |
| `/playground/laws/uapa/add` | expired | 1280 | – / – / 0 (legacy) | 7 Chapters · Sections 1–53 · Schedules / Resume Playground→/billing/subscriptions (sheet) / 7 ch / 4 sch / 0 sec | – | 200 | `frozen_expired_add-uapa-direct_1280x900_light.png` → `cand_expired_add-uapa-direct_1280x900_light.png` |
| `/laws/ndps/section/8` | expired | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_expired_ndps-section-8_390x844_light.png` → `cand_expired_ndps-section-8_390x844_light.png` |
| `/laws/ndps/section/8` | expired | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_expired_ndps-section-8_1280x900_light.png` → `cand_expired_ndps-section-8_1280x900_light.png` |
| `/laws/ndps/schedule/psychotropic-substances` | expired | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_expired_ndps-schedule_390x844_light.png` → `cand_expired_ndps-schedule_390x844_light.png` |
| `/laws/ndps/schedule/psychotropic-substances` | expired | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_expired_ndps-schedule_1280x900_light.png` → `cand_expired_ndps-schedule_1280x900_light.png` |
| `/laws/not-an-act` | expired | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 404 | `frozen_expired_laws-unknown_390x844_light.png` → `cand_expired_laws-unknown_390x844_light.png` |
| `/laws/not-an-act` | expired | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 404 | `frozen_expired_laws-unknown_1280x900_light.png` → `cand_expired_laws-unknown_1280x900_light.png` |
| `/laws/ndps` | halted | 390 | – / Sections→/playground/laws/ndps/sections; Manage subscription→/billing/subscriptions / 8 ch / 0 sch / 129 sec | 8 Chapters · Sections 1–83 · Schedule / Sections→/playground/laws/ndps/sections; Manage subscription→/billing/subscriptions / 8 ch / 1 sch / 0 sec | closed None 0px | 200 | `frozen_halted_laws-ndps_390x844_light.png` → `cand_halted_laws-ndps_390x844_light.png` |
| `/laws/ndps` | halted | 1280 | 6 Chapters · Sections 1–83 · Schedule / Manage subscription→/billing/subscriptions / 4 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Sections→/playground/laws/ndps/sections; Manage subscription→/billing/subscriptions / 8 ch / 1 sch / 0 sec | closed None 0px | 200 | `frozen_halted_laws-ndps_1280x900_light.png` → `cand_halted_laws-ndps_1280x900_light.png` |
| `/laws/uapa` | halted | 390 | – / Manage subscription→/billing/subscriptions / 7 ch / 0 sch / 67 sec | 7 Chapters · Sections 1–53 · Schedules / Manage subscription→/billing/subscriptions / 7 ch / 4 sch / 0 sec | closed None 0px | 200 | `frozen_halted_laws-uapa_390x844_light.png` → `cand_halted_laws-uapa_390x844_light.png` |
| `/laws/uapa` | halted | 1280 | – / Manage subscription→/billing/subscriptions / 7 ch / 0 sch / 67 sec | 7 Chapters · Sections 1–53 · Schedules / Manage subscription→/billing/subscriptions / 7 ch / 4 sch / 0 sec | closed None 0px | 200 | `frozen_halted_laws-uapa_1280x900_light.png` → `cand_halted_laws-uapa_1280x900_light.png` |
| `/laws/bns` | halted | 390 | – / Manage subscription→/billing/subscriptions / 20 ch / 0 sch / 358 sec | 20 Chapters · Sections 1–358 / Manage subscription→/billing/subscriptions / 20 ch / 0 sch / 0 sec | – | 200 | `frozen_halted_laws-bns_390x844_light.png` → `cand_halted_laws-bns_390x844_light.png` |
| `/laws/bns` | halted | 1280 | – / Manage subscription→/billing/subscriptions / 20 ch / 0 sch / 358 sec | 20 Chapters · Sections 1–358 / Manage subscription→/billing/subscriptions / 20 ch / 0 sch / 0 sec | – | 200 | `frozen_halted_laws-bns_1280x900_light.png` → `cand_halted_laws-bns_1280x900_light.png` |
| `/laws/bnss` | halted | 390 | – / Manage subscription→/billing/subscriptions / 39 ch / 0 sch / 531 sec | 39 Chapters · Sections 1–531 · Schedules / Manage subscription→/billing/subscriptions / 39 ch / 2 sch / 0 sec | – | 200 | `frozen_halted_laws-bnss_390x844_light.png` → `cand_halted_laws-bnss_390x844_light.png` |
| `/laws/bnss` | halted | 1280 | – / Manage subscription→/billing/subscriptions / 39 ch / 0 sch / 531 sec | 39 Chapters · Sections 1–531 · Schedules / Manage subscription→/billing/subscriptions / 39 ch / 2 sch / 0 sec | – | 200 | `frozen_halted_laws-bnss_1280x900_light.png` → `cand_halted_laws-bnss_1280x900_light.png` |
| `/laws/pss` | halted | 390 | – / Manage subscription→/billing/subscriptions / 8 ch / 0 sch / 42 sec | 8 Chapters · Sections 1–38 / Manage subscription→/billing/subscriptions / 8 ch / 0 sch / 0 sec | – | 200 | `frozen_halted_laws-pss_390x844_light.png` → `cand_halted_laws-pss_390x844_light.png` |
| `/laws/pss` | halted | 1280 | – / Manage subscription→/billing/subscriptions / 8 ch / 0 sch / 42 sec | 8 Chapters · Sections 1–38 / Manage subscription→/billing/subscriptions / 8 ch / 0 sch / 0 sec | – | 200 | `frozen_halted_laws-pss_1280x900_light.png` → `cand_halted_laws-pss_1280x900_light.png` |
| `/laws/mtp` | halted | 390 | – / Manage subscription→/billing/subscriptions / 0 ch / 0 sch / 9 sec | Sections 1–8 / Manage subscription→/billing/subscriptions / 0 ch / 0 sch / 9 sec | – | 200 | `frozen_halted_laws-mtp_390x844_light.png` → `cand_halted_laws-mtp_390x844_light.png` |
| `/laws/mtp` | halted | 1280 | – / Manage subscription→/billing/subscriptions / 0 ch / 0 sch / 9 sec | Sections 1–8 / Manage subscription→/billing/subscriptions / 0 ch / 0 sch / 9 sec | – | 200 | `frozen_halted_laws-mtp_1280x900_light.png` → `cand_halted_laws-mtp_1280x900_light.png` |
| `/playground/laws/ndps/add` | halted | 390 | – / – / 0 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Sections→/playground/laws/ndps/sections; Manage subscription→/billing/subscriptions / 8 ch / 1 sch / 0 sec | – | 200 | `frozen_halted_add-ndps-direct_390x844_light.png` → `cand_halted_add-ndps-direct_390x844_light.png` |
| `/playground/laws/ndps/add` | halted | 1280 | – / – / 0 (legacy) | 8 Chapters · Sections 1–83 · Schedule / Sections→/playground/laws/ndps/sections; Manage subscription→/billing/subscriptions / 8 ch / 1 sch / 0 sec | – | 200 | `frozen_halted_add-ndps-direct_1280x900_light.png` → `cand_halted_add-ndps-direct_1280x900_light.png` |
| `/playground/laws/uapa/add` | halted | 390 | – / – / 0 (legacy) | 7 Chapters · Sections 1–53 · Schedules / Manage subscription→/billing/subscriptions / 7 ch / 4 sch / 0 sec | – | 200 | `frozen_halted_add-uapa-direct_390x844_light.png` → `cand_halted_add-uapa-direct_390x844_light.png` |
| `/playground/laws/uapa/add` | halted | 1280 | – / – / 0 (legacy) | 7 Chapters · Sections 1–53 · Schedules / Manage subscription→/billing/subscriptions / 7 ch / 4 sch / 0 sec | – | 200 | `frozen_halted_add-uapa-direct_1280x900_light.png` → `cand_halted_add-uapa-direct_1280x900_light.png` |
| `/laws/ndps/section/8` | halted | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_halted_ndps-section-8_390x844_light.png` → `cand_halted_ndps-section-8_390x844_light.png` |
| `/laws/ndps/section/8` | halted | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_halted_ndps-section-8_1280x900_light.png` → `cand_halted_ndps-section-8_1280x900_light.png` |
| `/laws/ndps/schedule/psychotropic-substances` | halted | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_halted_ndps-schedule_390x844_light.png` → `cand_halted_ndps-schedule_390x844_light.png` |
| `/laws/ndps/schedule/psychotropic-substances` | halted | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 200 | `frozen_halted_ndps-schedule_1280x900_light.png` → `cand_halted_ndps-schedule_1280x900_light.png` |
| `/laws/not-an-act` | halted | 390 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 404 | `frozen_halted_laws-unknown_390x844_light.png` → `cand_halted_laws-unknown_390x844_light.png` |
| `/laws/not-an-act` | halted | 1280 | – / – / 0 (legacy) | – / – / 0 (legacy) | – | 404 | `frozen_halted_laws-unknown_1280x900_light.png` → `cand_halted_laws-unknown_1280x900_light.png` |

### 4.1 Behaviour differences found (all recorded, none silent)

| # | Difference | Class | Where recorded |
|---|---|---|---|
| B1 | NDPS head lists eight chapters (I, II, IIA, III, IV, V, VA, VI), not the fixture's three; meta "8 Chapters" | F (fix, Q1) | F01 |
| B2 | Every eligible Act gets the head (frozen: legacy full panel for UAPA/BNS/BNSS/PSS/MTP) | F (DV-3) | F01 |
| B3 | Chapter rows start closed and expand; frozen opened Chapter I | I (Q3, prototype) | F02, `test_ndps_reader` |
| B4 | Chapters/Schedules tab row and "This Act has no Schedules." removed; schedules follow the chapters in one list | I (§2.1) | `test_act_info_panel`, `test_mtp_reader` |
| B5 | Already-active chip primary links the live state (`/playground/laws/{id}` or `…/sections`), label "Continue"/"Start learning"; frozen NDPS head hard-coded "Continue" → `/playground` | F (F04, §4a) | F04, `test_phone_plus_playground_screen3` |
| B6 | `data-plus-bareact`/`data-expired-bareact`/`data-halted-bareact` are bare attributes on every Act (frozen: `="desktop"` on NDPS only) | F | cohort tests |
| B7 | Add by URL is the Act page with the dialog open (frozen: standalone page in the hard-gate shell); in-page fetch and POST re-render keep the standalone panel | F (Q4) | F05, `test_playground_r3::test_d35` |
| B8 | Free sheet: title "Add to Playground" (was "Unlock Playground"), footnote names the plans, no Cancel button (✕/Escape/scrim close it) | I (§2.1 copy) | Free cohort tests |
| B9 | Reading names from the registry spec ("The NDPS Act, 1985", "The UAPA, 1967", "The BNS, 2023" …) for every Act; frozen used "NDPS"/"UAPA" except NDPS's special case | I (§2.1) | `test_reading_names_come_from_the_registry_for_every_act` |
| B10 | Subscriber confirm uses the (formerly NDPS-only) "joins this month's Playground" lede plus the generic space lines for every Act; the Plus-only space wording/reopen footer is not rendered | I (§2.1) | Plus cohort, `test_playground_m6` |
| B11 | The head prints the state's `secondary_copy` for every kind (Free: "Unlock Playground · from ₹199 / month."; guest: "Sign in to add this law to Playground."; expired: the gate title and lines run together — pre-existing string) | U (kept existing copy; the prototype has no line here) | §6 deviations |
| B12 | Never-enrolled expired head: `a.ActHead-btn[data-pg-sheet]` with `href="/billing/subscriptions"` (the state's `opens_sheet` is true for the resume kind), so an in-page click fetches the billing page and the script falls back to navigating there — pre-existing in the frozen `playground_cta` for UAPA; recorded, not changed | U (pre-existing) | §7 |

## 5. Visual and accessibility acceptance

### 5.1 M2-V01 captures
390×844 and 1280×900, light and dark, for every §3 row and viewer (dark and full-page captures hashed in `all_captures_sha256.json`, viewable in the gallery archive); shell crops are the viewport captures. Differences against the prototype state named in §3:

| Route / viewer | Prototype | Candidate | Class |
|---|---|---|---|
| `/laws/ndps` guest 1280 (`proto_act-ndps-guest_desktop`) | band #ececea, back "← Laws" 32 px, kicker 10.5 px #8f8f8d, title Fraunces 28 px, meta 13 px #8f8f8d, CTA 380×48 #141414 r12, rows 56 px (tag 110 px / name 15.5 px / range 12 px #9a9a9a / "›"), 8 chapters + SCHEDULE "Entries 1–110" | same composition; back 44 px tall (hit area), kicker/meta/tag/range in `--muted` #6b6b6b, rows 56 px, About toggle under the meta, schedule tag "THE SCHEDULE", range "Entries 1–110ZT", reference line under the schedule name | G (greys/44 px, recorded), I (About, the Act's own label and range) |
| `/laws/ndps` guest/Free 390 (`proto_act-ndps-*_phone`) | band padding 2/18/16, back 44 px, title 19 px, meta 12 px, CTA 48 px full width, rows 48 px #fafaf9 with "▸", range "1–3" | same; About toggle under the CTA; schedule row carries the reference line | I |
| `/laws/ndps` Plus desktop/phone (chip) | chip #e7f1ef / #bcd8d2, mark 26 px #0e7569, "Already in Playground" 13.5 px #0e5b52, Sections 34 px outline, Continue 34 px #0e7569 | same tokens; buttons 40 px (desktop) / 44 px (phone) | G (44 px targets, recorded) |
| Add sheet Free desktop (`proto_act-uapa-signedIn-sheet_desktop`) | 460 px modal, ✕ top-right, Fraunces 22 px title, lede 13.5 px, Unlock 50 px, footnote 12 px #9a9a9a | same; footnote in `--pg-muted` | G |
| Add sheet Free phone (`proto_act-uapa-signedIn-sheet_phone`) | bottom sheet, handle, title 19 px, footnote "Core · Deep · Infinite — from ₹149" | same geometry; footnote "Plus · Pro · Max — from ₹199 / month." (the approved copy; the phone prototype's plan names are stale) | I (approved §2.1) |
| Add sheet guest | lede + Sign in 50 px + Create an account 46 px | same; both are real links to `/login?next=…` (the phone prototype's inert buttons are not reproduced) | F (rule: placeholders become functional) |
| Add sheet Plus (`proto_act-uapa-plus-sheet_desktop`) | title, lede "joins this month's Playground…", Entire Act / Choose sections | eyebrow month, title, lede, the two space lines, Add to Playground, Cancel; then the scope step | I (confirm step kept: it carries the space accounting) |
| halted / expired heads | not drawn (phone prototype has no halted viewer) | chip with Sections + "Manage subscription" / "Resume Playground"; never-enrolled Acts show the lifecycle button and the gate copy as a note | U (no prototype) |

### 5.2 M2-V02 head geometry (candidate, light)

| | Desktop 1280 | Phone 390 | Prototype |
|---|---|---|---|
| Title | Fraunces 28 px | 19 px | 28 / 19 px |
| CTA | 380×48 at x=860, y=122 (band right) | 354×48 full width | 380×48 / full width 48 |
| Chapter row | 56 px (67 px when the schedule row wraps) | 48 px (59–61 px when the name wraps) | 56 / 48 |
| Sheet | 460×225 centred | 358×239 bottom | 460 / full width |
| Back link | 44 px tall | 44 px | 32 / 44 |

### 5.3 M2-V03 responsive (`m2/responsive/`, `manifests/candidate_responsive.json`)
320, 560, 561, 720, 768, 1024-ish (768×1024) and landscape 844×390, light and dark, NDPS/UAPA/BNSS: no horizontal scroll on any capture; the title wraps; the CTA drops under the title at 561–899 px (x=28, y=213–246) and never overlaps it; ranges never clip (the row's name column is `min-width: 0`). Pre-existing, not M2: at 561–768 px signed-in, the shell's account avatar floats at the band's top-left (present in the frozen baseline, `responsive/frozen_m1server_*` — M1b scope).

### 5.4 M2-A01 keyboard and dialog (`manifests/candidate_keyboard_trace.json`, `keyboard/`)
Tab order from the back link: back → CTA → About → chapter rows in order; Enter on a summary sets `aria-expanded="true"` and reveals the section links (`kbd_enter-opens-chapter_*`); focus rings visible (`outline solid 2px`) on every Tab stop (the back link's first focus in the trace is programmatic, so no ring is expected there; its `:focus-visible` rule is in the CSS). Sheet: Enter on the CTA opens the modal; focus lands on the close button (desktop) / Unlock (phone, the ✕ is hidden there); Tab cycles inside the dialog only; Escape closes it and focus returns to the CTA. Schedule rows are links (`schedule-focus` state). The dialog is `role="dialog"` `aria-modal="true"` with `aria-labelledby="pg-add-title"`.

### 5.5 M2-A02 contrast and targets
Computed from the tokens (`styles.css`, `playground.css`):

| Text | Light | Dark |
|---|---|---|
| kicker / meta / chapter tag / range (`--muted`) on the band `--page` | 4.51 | 6.44 |
| same on `--paper` / `--wash` rows | 5.33 / 5.10 | 5.93 / 6.19 |
| title `--ink` on `--page` | 15.57 | 16.15 |
| CTA `--on-accent` on `--ink` | 18.42 | 16.44 |
| chip text `--pg-teal-dark` on `--pg-teal-tint` | 6.91 | 7.56 (6.14 in the second dark block) |
| Continue `--on-accent` on `--pg-teal` | 5.57 | 5.54 |
| About toggle `--teal` on `--page` | 4.71 | — |
| sheet lede / note `--pg-muted` on `--pg-paper` | 5.33 | 7.14 (5.99) |
| prototype greys #8f8f8d on #ececea / #9a9a9a on #fff (not used) | 2.74 / 2.81 | — |

All ≥ 4.5:1. Targets: back link 44 px, CTA 48 px, chapter rows 56/48 px, schedule rows 56/48 px (overlay link), About toggle 44 px band (padding), sheet buttons 50/46 px, ✕ 44 px. **Deviation:** the chip's Sections/Continue buttons are 40 px tall on desktop (44 px on phone) — the prototype's 34 px raised, but short of 44 px; recorded for owner review.

### 5.6 M2-A03 / A04 / V04
- Reduced motion: the sheet's rise animation is inside the existing `prefers-reduced-motion` guard in `playground.css` (unchanged); the chapter caret has a 0.15 s transform only.
- 200 % zoom by real browser zoom: **NOT RUN** (the browser tools refuse zoom shortcuts, as in M1); the 320 px captures stand in as the reflow emulation and are supporting evidence only.
- Automated accessibility scan (axe/Lighthouse): **BLOCKED** — not installed in this environment, same as M1.
- Screen-reader smoke (VoiceOver): **NOT RUN**.
- Dark mode (V04): palette-consistency only — every colour is a token, both dark blocks checked above; never fidelity.

## 6. Deviations — owner decisions (2026-10-20: all six KEPT)

Owner review 2026-10-20: M2 is **under review, not accepted**; the six deviations below are **owner-kept** (the implementation stays as it is). B12 (the never-enrolled expired head's billing button marked as a sheet opener) and the 561–768 px floating avatar stay out of M2.

| # | Item | Owner decision |
|---|---|---|
| D1 | Accessible greys (`--muted` 4.5:1+) instead of the prototype's #8f8f8d/#9a9a9a for kicker, meta, tags and ranges | **keep** |
| D2 | Chip buttons 40 px on desktop (prototype 34, rule 44) | **keep at 40 px desktop** |
| D3 | The head prints the state's note under the button (B11) | **keep** |
| D4 | "Start learning" (→ Sections) vs "Continue" from the live state | **keep** |
| D5 | Free sheet has no Cancel button (✕, Escape, scrim) | **keep** |
| D6 | Add page title "Add to Playground · {Act title}" | **keep** |

## 7. Outstanding checks and follow-ups

- Hosted matrix: none for M2 (no staging deployment authorised). Guest and Free hosted rows would follow a deployment; Plus/Pro/Max/expired/halted stay unverified without a staging-only grant.
- Dead code left in place (no behaviour): `routes.py::_add_page_context` still computes the NDPS-only `plus_add_*` strings (`plus_add_confirm_copy`) that no template reads; `base.html` keeps the Plus-only `data-plus-bareact-phone-tabs` bar and the `/laws/ndps` header-status gate (shell, M1b/M9 scope).
- B12: the never-enrolled expired head's `data-pg-sheet` on a billing href — pre-existing state behaviour; a design decision for M7/M9.
- The 561–768 px floating avatar on signed-in pages is the shell's (M1b).

## 8. Gates (checklist §7)

| Gate | Status |
|---|---|
| M1 accepted; decisions approved; branch cut from `pg-m1-guest-shell` head; frozen baseline for every §3 row captured before editing | done (`frozen/`, `manifests/frozen_*.json`, all eight fixtures) |
| Implementation within §2.1 | done; two additions beyond the listed files are recorded in §1: `web/bare_act_page.py` (the Act context shared with the Add route, needed for Q4) and `partials/playground_add_panel.html` |
| Tests tied to the candidate SHA; evidence LOCAL/PRELIMINARY | this file, `a146dff` |
| Draft PR | stacked on `pg-m1-guest-shell` (retarget to `cursor/playground-220d` after M1 merges) |
| Staging deployment / hosted rows / merge | **not authorised; not done** |

## 9. Addendum (2026-10-20) — Add-dialog corrections from the owner's source review of `b828b85`

| # | Finding | Fix (this commit) | Verification (`manifests/dialog_verification.json`, `dialog-fix/*.png`, headless Chrome, Plus fixture, 1280 and 390) |
|---|---|---|---|
| 1 | Direct-URL initialisation called `dialog.close()` before `showModal()`, queueing the dismissal handler (label removed, URL rewritten to the Act while the dialog was open) | `playground.js` drops the server's `open` attribute with `removeAttribute("open")` and then calls `showModal()`; `close()` is no longer called during initialisation | direct open: URL stays `/playground/laws/uapa/add` while open, `aria-labelledby="pg-add-title"` → "Add to Playground" (visible), focus on the Close button; Escape → dialog closed, URL `/laws/uapa` (both widths) |
| 2 | Two modal dialogs (host `<dialog>` and the panel's own `role="dialog" aria-modal`); the scope step stayed labelled by the hidden confirm heading | the panel partial carries `role/aria-modal/aria-labelledby` only when rendered alone (no-JS POST re-render, or the sheet fetch before the script lifts it); `playground.js` strips them from any panel it lifts (`demoteToPanel`) so the host is the one landmark; the label follows the visible heading (`visibleHeading`) and the scope step re-labels the host (`pg-sheet:relabel`) or the standalone panel | `roleDialogsInsideHost = 0`, `panelRole = null` on every open; after the confirm step the host's label is `pg-add-scope-title` → "Add The UAPA, 1967", visible, focus on "Entire Act" (both widths) |
| 3 | Phone sheets for guest/Free had no explicit close control (✕ hidden ≤560 px, no Cancel by decision D5) | `playground.css` keeps the 44×44 ✕ (`aria-label="Close"`) visible on the Add panel at ≤560 px; D5's no-Cancel presentation is unchanged | close button `display: flex`, 44×44 at 390 px on direct and in-page opens; clicking it closes the dialog and returns focus to the head's CTA (`A.ActHead-btn`); the rule is kind-independent, so guest and Free sheets get it too |

Also verified: in-page open from the head's CTA labels the host "Add to Playground" and focuses the Close button; after closing, focus returns to the opener on both widths. Direct-URL Escape leaves focus on `<body>` (there is no opener on that page), recorded as expected. Full suite on this tree: 3,950 passed, 163 skipped, 3 failed (the documented device exceptions) — `manifests/pytest_full_run4_dialog_fix.log`. Tests: two new tests in `test_bareact_head_family.py`; five cohort assertions re-pointed to the single landmark (the standalone fetch/POST panel keeps `role="dialog"`, byte-identical otherwise); pins `pg50→pg51`, `playground.js pg9→pg10`.

### 9.1 Follow-up (2026-10-20) — initial label on a panel that opens at the scope step

Owner's source review of `9996c9b`: `labelledBy(panel)` ran before the fetched panel was attached, so every heading had no `offsetParent` and the first (hidden) heading won; Max skips confirmation and opens at the scope step, so its in-page dialog was labelled "Add to Playground" instead of the visible "Add The UAPA, 1967". Fix: the in-page path labels after `replaceChildren()` and `showModal()`, the direct path after `showModal()`; the standalone panel's server-rendered `aria-labelledby` and the served host dialog's label follow the initial step (`pg-add-scope-title` when confirmation is skipped, else `pg-add-title`). Pin `playground.js pg10→pg11`.

Verification (headless Chrome, `manifests/dialog_verification_max.json`, `dialog_verification_plus.json`, `dialog-fix/max/`, `dialog-fix/plus/`):

| Fixture | Width | Direct URL | In-page from the head | Close / Escape |
|---|---|---|---|---|
| Max (opens at scope) | 1280, 390 | host labelled `pg-add-scope-title` → "Add The UAPA, 1967", visible; one landmark; focus on Close | same label; focus on Close | ✕ → closed, focus back on the CTA; Escape on direct → `/laws/uapa` |
| Plus (confirm → scope) | 1280, 390 | "Add to Playground" (visible confirm title); Enter on the primary → scope step relabels to "Add The UAPA, 1967", focus "Entire Act" | "Add to Playground" | as above |

Full suite on this tree: 3,951 passed, 163 skipped, 3 failed (the documented device exceptions) — `manifests/pytest_full_run5_label_fix.log`. Test: `test_the_standalone_panel_is_labelled_by_the_heading_of_its_initial_step` (Max → scope title, Plus → confirm title, on the standalone panel and the served host; the script labels only after `showModal()`).

## 10. Hosted validation — staging deployment `0eb35808-b852-4555-97fd-019122411de1` (= `e2ac903`, 2026-10-20)

Deployment verified from Railway metadata (`SUCCESS`, branch `pg-m2-act-head`, commit `e2ac903aa542f154c6b148f9505e53a5cf6c779b`) and from the served page (`main88` / `mob107` / `pg51` / `pg11`, `data-act-head`, `/health` 200) before any capture. Nothing was deployed, granted or revoked by Claude; no roster write was made on staging.

### 10.1 Guest matrix (headless Chrome, `tools/capture_m2.py`, 390 and 1280, light and dark)

All 44 hosted rows match the local candidate probe for probe (status, meta, CTA label/href/sheet, row types and hrefs, About, sheet open state, no horizontal scroll): `manifests/hosted_guest_0eb35808.json`, light captures in `hosted/guest/`. NDPS 8 chapters + 1 schedule; UAPA 7 + 4; BNS 20 + 0; BNSS 39 + 2; PSS 8 + 0; MTP "Sections 1–8" with 9 flat section links; the guest sheet opens in-page (kind `guest`, 460 px modal / bottom sheet) and by URL over the Act; readers and the 404 unchanged.

States (`hosted/states/`, `manifests/hosted_states_0eb35808.json`): chapter expanded, About open, focused row and focused schedule link on both widths. Keyboard (`hosted/keyboard/`, `manifests/hosted_keyboard_trace_0eb35808.json`): Enter on a chapter row sets `aria-expanded="true"` on both widths; Enter on the CTA opens the sheet with focus on the Close button; Tab cycles inside the dialog (Sign in → Create an account → Close); Escape closes it and focus returns to the CTA.

### 10.2 Signed-in rows from the owner's session (browser pane) — **Pro, not Free**

The session the owner signed in with is the Pro-granted staging account ("RecallC Pro" on Today and Profile, Devices 2 of 2), so these are **Pro rows**; the **Free hosted rows remain unverified**. Method and every probe: `manifests/hosted_signedin_pro_pane_0eb35808.json` (DOM probes from the pane; pointer clicks for the in-page open; no POST).

| Route | Width | Result |
|---|---|---|
| `/laws/ndps`, `/laws/uapa`, `/laws/mtp` | 1280 | generated head, kind `eligible_to_add`, CTA "+ Add to Playground" → `/playground/laws/{id}/add` (sheet); row counts and schedule hrefs as local; MTP flat (no `<details>`, no "Chapter"); About present; no horizontal scroll. Account subtitle reads "Free account" on these path-gated pages for the Pro login — the known DV-20 limitation recorded in the M1 paid-pack review (M5), not M2 |
| `/laws/uapa` in-page open | 1280 | pointer click → dialog open, labelled by the visible "Add to Playground", one landmark, lede "The UAPA, 1967 joins this month's Playground …", Close 44×44 focused; Close click → closed, URL unchanged, focus back on the CTA; Escape likewise |
| `/laws/uapa` chapter row | 1280 | click → `open`, `aria-expanded="true"`, section links visible, no other chapter open |
| `/playground/laws/uapa/add` by URL | 1280, 375 | Act head underneath, served dialog open (`data-pg-sheet-direct`, return `/laws/uapa`), one open dialog, label "Add to Playground" visible, focus on Close; Escape / Close → closed, URL rewritten to `/laws/uapa`, label removed |
| `/laws/ndps` | 375 | head (CTA 48 px, rows 48–59 px, five-tab bar), schedule link; pointer click opens the bottom sheet (about 3 s on staging), label visible, Close 44×44 at the sheet's top-right; Close → focus back on the CTA |

Not covered on staging: Free rows (no Free session), the subscriber Playground/plans routes (device cap 2 of 2 — needs the separately authorised device revocation), the roster write itself (not sent), dark theme for the signed-in session, Plus/Max/expired/halted. M2 acceptance is the owner's decision on this record.

### 10.3 Signed-in Free rows from the owner's session (browser pane, 2026-10-22)

The owner signed out of the earlier Pro session and of Google inside the pane, then signed in with a fresh **Free** account (Today subtitle "Free account"). Method and every probe: `manifests/hosted_signedin_free_pane_0eb35808.json` (DOM probes; pointer clicks for the in-page open — the sheet fetch takes 3–8 s on staging; no POST; no entitlement change).

| Route | Width | Result |
|---|---|---|
| `/laws/ndps`, `/laws/uapa`, `/laws/mtp` | 1280 | generated head, kind `subscribe`, CTA "Subscribe to use Playground" → `/playground/laws/{id}/add` (sheet), note "Unlock Playground · from ₹199 / month."; row counts and schedule hrefs as local; MTP flat; About present; no horizontal scroll; subtitle "Free account" (M1-F10 holds for Free) |
| `/laws/uapa` chapter row | 1280 | click → `open`, `aria-expanded="true"`, section links visible, no other chapter open |
| `/laws/ndps` in-page open | 1280, 375 | pointer click → dialog open, one landmark, labelled by the visible "Add to Playground"; lede "Turning The NDPS Act, 1985 into a learning experience needs a plan. Reading it stays free."; "Unlock Playground" → `/playground`; footnote "Plus · Pro · Max — from ₹199 / month. Constitution learning stays free."; **no Cancel (D5)**; Close 44×44 focused (phone: bottom sheet at y=573, Close at its top-right); Close click → closed, URL unchanged, focus back on the CTA |
| `/playground/laws/uapa/add` by URL | 1280, 375 | Act head underneath, served dialog open (`data-pg-sheet-direct`), one open dialog, label visible, Free copy as above, focus on Close; Escape → closed, URL rewritten to `/laws/uapa`, label and return attribute removed; phone bar present at 375 |

With §10.1 (guest) and §10.2 (Pro), the hosted record now covers guest, Free and one paid tier for the Act heads, chapter expansion, schedule links and the Add dialog (in-page and by URL, both widths). Still unverified on staging: subscriber Playground/plans routes (device cap), Plus/Max/expired/halted, the roster write, dark theme for signed-in sessions.

## 11. Consolidated acceptance table (2026-10-22) — for the owner's decision

Candidate `e2ac903aa542f154c6b148f9505e53a5cf6c779b` (PR #221, draft); staging deployment `0eb35808`. **Updated 2026-10-25** for `3719b9f` / deployment `dd04a5a2` (§13): the Free 390 px and dark rows below are now verified; Pro is device-capped on that deployment. Acceptance and merge are separate decisions; nothing below authorises either.

### 11.1 Coverage by cohort (what was actually run)

| Cohort | Local (candidate, fixtures) | Hosted (staging `0eb35808`) | Phone width on hosted | Themes on hosted |
|---|---|---|---|---|
| Guest | 390 + 1280, light + dark, every §3 route, states, keyboard | headless matrix, all 44 rows match local probe-for-probe; states; keyboard | 390 | light + dark |
| Free | 390 + 1280, light + dark (dev fixture) | owner's fresh Free session in the browser pane: NDPS/UAPA/MTP heads, chapter expansion, schedule links, Add dialog in-page and by URL (§10.3); **`dd04a5a2`: headless matrix through the Free profile, 44 rows match local, states, keyboard, PF-2 (§13.2)** | 375 (pane) and **390** (§13.2) | **light + dark** (§13.2) |
| Pro | 390 + 1280, light + dark (dev fixture `--tier pro`) | owner's Pro-granted session in the pane: same set as Free (§10.2); `dd04a5a2`: heads/rows/schedules/About/states at 390 + 1280, light + dark, but **device-capped (`device_blocked` kind)** — eligible Add rows not reached (§13.3) | **375** (eligible rows); 390 (device-blocked kind only) | light (eligible rows); dark (device-blocked kind only) |
| Plus | 390 + 1280, light + dark (dev fixture, incl. NDPS retained) | **not run** | — | — |
| Max | 390 + 1280, light + dark (dev fixture; Max opens at the scope step, §9.1) | **not run** | — | — |
| Expired, halted | 390 + 1280, light + dark (dev fixtures) | **not run** | — | — |

### 11.2 M2 requirements — verdict per criterion

| Criterion | Guest | Free | Pro | Evidence |
|---|---|---|---|---|
| F01 generated head for every eligible Act (meta == `head_meta_label`, rows == counts; fixture gone) | PASS local + hosted (6 Acts) | PASS local; hosted NDPS/UAPA/MTP | PASS local; hosted NDPS/UAPA/MTP | §3, §10.1–10.3, `test_bareact_head_family` |
| F02 chapter rows are real controls; every section reachable | PASS local + hosted (keyboard Enter → `aria-expanded`) | PASS hosted (click) | PASS hosted (click) | §5.4, §10 |
| F03 schedule rows open their readers; undrawable stays listed/unlinked | PASS local + hosted | PASS hosted | PASS hosted | §10 |
| F04 CTA destinations = live state; only §4a wording changed | PASS local + hosted (`guest` kind) | PASS hosted (`subscribe` → Add sheet, Unlock → `/playground`) | PASS hosted (`eligible_to_add`; live hrefs) | §4, B5, §10 |
| F05 sheet opens in-page and by URL; confirm/scope/roster unchanged; direct URL 200 | PASS local + hosted | PASS hosted (no POST) | PASS hosted dialog; roster write **not sent** (see 11.3) | §9, §10 |
| F06 About reachable below the action (Q2) | PASS local + hosted | PASS hosted | PASS hosted | §10 |
| F07 chapterless Act flat (MTP) | PASS local + hosted | PASS hosted | PASS hosted | §10 |
| F08 readers unchanged | PASS local + hosted (guest) | not repeated (readers are not viewer-dependent) | — | §4 |
| F09 full suite; drift 0 | PASS with the 3 documented device exceptions (CI 39375517921) | — | — | §2, M2.md |
| V01–V03 captures, geometry, responsive 320–844 | PASS local (all cohorts); hosted guest responsive not repeated (M1 established the shell; M2 changed no breakpoint) | — | — | §5.1–5.3 |
| V04 dark = palette consistency only | PASS local (all cohorts); hosted guest dark matches | PASS hosted (`dd04a5a2`, §13.2) | hosted dark: device-blocked kind only (§13.3) | §13 |
| A01 keyboard, one dialog landmark, label, focus return | PASS local + hosted guest (trace); Free/Pro hosted: label, landmark, focus return by pointer + Escape | — | — | §5.4, §9, §10 |
| A02 contrast ≥ 4.5:1; targets | PASS (computed; D1/D2 owner-kept) | — | — | §5.5, §6 |
| A03 reduced motion; 200 % zoom | reduced motion PASS; real zoom **NOT RUN** (tooling) | — | — | §5.6 |
| A04 automated scan; screen reader | **BLOCKED** / **NOT RUN** (same as M1) | — | — | §5.6 |

### 11.3 Unverified items — proposed test or exception

| Item | Status | Proposed |
|---|---|---|
| Signed-in hosted rows at **390 px** | **Free: done** (`dd04a5a2`, §13.2). Pro eligible rows: still 375 only (device cap, §13.3) | Pro 390 folds into the device-revocation item below — **exception candidate** for Pro only |
| Signed-in hosted **dark theme** | **Free: done** (`dd04a5a2`, §13.2). Pro: device-blocked kind only | Pro dark folds into the device-revocation item below — **exception candidate** for Pro only |
| **Plus / Max / expired / halted** on staging | not run (Plus/Max accounts device-capped; no expired/halted staging account) | **proposed explicit M2 exception: local fixture coverage (§3, §9.1) stands in for the hosted check**, with the hosted Plus/Max/expired/halted checks **due before final redesign acceptance** (Plus/Max after the separately authorised device revocation; expired/halted need an owner-performed staging subscription-state change) |
| **Roster write** (confirm → scope → add) on staging | not sent | the write path is unchanged by M2 and covered by the suite; if the owner wants it exercised, run one Add on a **designated staging test account** — note that removing the law afterwards does **not** restore that month's quota, so it is not a clean rollback — otherwise **exception** |
| Real 200 % zoom, automated scan, screen reader | as M1 | carried exceptions (M1b) |

### 11.4 Performance finding (new, requires a decision)

| # | Finding | Measurement (2026-10-22, staging) | Attribution | Proposed action |
|---|---|---|---|---|
| PF-1 | The in-page Add sheet appears 3–8 s after the click for signed-in users; instantly for guests and locally (2026-10-25 on `dd04a5a2`, Free: 5.8–7.1 s in every run, §13.2) | signed-in fetch of `/playground/laws/uapa/add` (sheet header): TTFB 5.8 / 6.1 / 6.5 s; signed-in `/laws/uapa` 4.7 s, `/dashboard` 3.2 s, page navigation TTFB 5.0 s; guest TTFB 0.39–0.56 s for the same URLs; `/health` 0.26–0.55 s | **Measured:** every signed-in request on staging is slow, not only the sheet (the sheet fetch skips the Act, §1, and the Act page itself is as slow); guest requests are fast. **Cause — hypothesis, not established:** the entitlement/roster look-ups on signed-in routes may be making many round trips to the isolated staging database; tracing has not confirmed this. Pre-existing path (M1's signed-in routes use it), made visible by M2's in-page opener. | **tracked under the hardening programme** (trace signed-in request timing on staging and count DB round trips before attributing); not an M2 code change |
| PF-2 | No in-flight feedback while the sheet is fetched: the CTA keeps focus, nothing shows "opening" (no `aria-busy`, no state class in `playground.js`) | handler inspected | **M2 scope** (the opener is M2's) | add an opening state to the trigger (`aria-busy="true"` + a visible pressed/loading style, cleared on open or failure), a few lines of JS/CSS; owner to say whether it is required before acceptance or logged as an M2 follow-up. **Done (owner required it):** fixed in `3719b9f` (§12), verified on staging `dd04a5a2` for guest and Free (§13) |

### 11.5 Not M2 criteria (regression context only; must not widen acceptance)

Subscriber Playground home, plans and device-limit pages (blocked by the device cap; M7/M5), the "Free account" subtitle for subscribers on path-gated pages (DV-20 follow-up, M5), the Browse Free-plan banner for subscribers (M3), Profile limit duplication (M5), Pro capacity overflow (M7), the never-enrolled expired head's billing button marked as a sheet opener (B12, pre-existing), the 561–768 px floating avatar (M1b). These were observed during M1/M2 validation and are recorded where they belong; none is an M2 acceptance criterion.

### 11.6 Decision options

- **Accept with named exceptions**: 11.3 rows as they stand after §13 — Pro eligible rows at 390/dark (device cap), Plus/Max/expired/halted hosted, roster write, zoom/scan/SR, the three device-test exceptions. PF-2 is done; the Free 390/dark rows are done.
- **Require remaining checks**: name which 11.3 rows must run first; the Plus/Max rows additionally need the device revocation.
Merge is a separate decision in either case.

## 12. PF-2 correction (2026-10-22) — opening feedback on the sheet trigger

Owner's direction: fix PF-2 before acceptance. `playground.js` now marks the trigger busy the moment it is clicked (`aria-busy="true"`, class `is-opening`, visible text "Opening…", original label kept in `data-pg-label` and restored), ignores further clicks while the request is in flight (one request per open), and clears the state on success and on every failure path before the existing link fallback (`window.location.href = href`) runs; the `href` is never altered, so the trigger stays a usable link without the script. `playground.css` dims the busy trigger (opacity 0.72), shows a progress cursor and blocks pointer events on it. Pins `pg51→pg52`, `playground.js pg11→pg12`.

Verification (headless Chrome, Free fixture, network latency emulated at 2.5 s; `manifests/busy_verification.json`, `busy/busy_during_{1280,390}.png`):

| Step | 1280 | 390 |
|---|---|---|
| before click | "Subscribe to use Playground", no `aria-busy`, cursor pointer | same |
| 0.3 s after three rapid clicks | "Opening…", `aria-busy="true"`, `is-opening`, opacity 0.72, cursor progress, pointer-events none, href unchanged | same |
| `/add` requests sent for the three clicks | **1** | **1** |
| after the dialog opens | label restored, `aria-busy` removed, dialog open, focus on Close | same |
| after Close | dialog closed, focus back on the trigger with its original label | same |

Full suite on this tree: 3,952 passed, 163 skipped, 3 failed (the documented device exceptions) — `manifests/pytest_full_run6_pf2.log`. Test: `test_the_sheet_trigger_shows_an_opening_state_and_sends_one_request`.

## 13. Hosted validation — staging deployment `dd04a5a2-9451-48b6-a391-ec5ab02835da` (= `3719b9f`, 2026-10-25)

The owner deployed `3719b9f0d3ec3f7fe5a9e0d885a13e7f03ce0ce4` (PR #221) to `recallc-playground-staging` and reported the deployment SUCCESS; the served page was checked for the PF-2 pins (`pg52` / `pg12`, `data-act-head`) before capture. Nothing was deployed, granted or revoked by Claude; no roster write was made; no POST was sent.

**Method (session-reuse policy, 2026-10-22).** One persistent headed Chrome profile per tier, signed in once by the owner (Google); the capture tools attach to the profile's debugging port and open their own tab — they set no cookies and the manifests hold DOM probes, screenshots and hashes only (no session material; grep-checked before staging). The tier was verified from the Today/Profile chrome before each run (`tools/tier.py`): the Free profile shows "Free account", Devices 0 of 2; the Pro profile shows "RecallC Pro · ACTIVE", **Devices 2 of 2**. The matrix tool polls the sheet for up to 15 s; the states/keyboard/busy tools were given the same poll (up to 20 s, time to open recorded) after their first Free run probed at fixed 1–4 s waits and reported the sheet "not open" — that first output was discarded and both runs repeated; the tools in `tools/` are the patched ones.

### 13.1 Guest (headless, `tools/capture_m2.py`)

All 44 rows (390 and 1280, light and dark) match the local candidate probe-for-probe: `manifests/hosted2_guest_dd04a5a2.json`, `hosted2/guest/`. PF-2 on staging for the guest trigger (`manifests/hosted2_busy_guest_dd04a5a2.json`, `hosted2/busy_guest/`): "Opening…" with `aria-busy` within 0.3 s of the click, one `/add` request for three clicks, label restored and Close focused when the sheet opens, focus back on the trigger after Close.

### 13.2 Free (profile port 9461 — the owner's Free staging account)

| Check | 390 × 844 | 1280 × 900 | Files |
|---|---|---|---|
| Matrix: NDPS, UAPA, BNS, BNSS, PSS, MTP heads; NDPS §8 and Schedule readers; `/laws/unknown`; `/playground/laws/{ndps,uapa}/add` by URL; in-page sheet on NDPS and UAPA | light + dark: **22/22 rows match the local Free candidate** (status, meta, CTA label/href/sheet, row types and hrefs, About, sheet open state, no horizontal scroll) | light + dark: **22/22 match** | `manifests/hosted2_free_dd04a5a2.json`, `hosted2/free/` (light + dark PNGs) |
| Head content | kind `subscribe`; CTA "Subscribe to use Playground" → `/playground/laws/{id}/add` (sheet opener); note "Unlock Playground · from ₹199 / month."; NDPS 8 chapters + 1 schedule, UAPA 7 + 4, BNS 20, BNSS 39 + 2, PSS 8, MTP flat (9 section links, no `<details>`); About present; phone bar present; subtitle "Free account" | same (five-tab bar hidden, top nav) | as above |
| In-page sheet | opens (polled), title "Add to Playground", lede "Turning The NDPS Act, 1985 into a learning experience needs a plan. Reading it stays free.", "Unlock Playground" → `/playground`, footnote "Plus · Pro · Max — from ₹199 / month …", **no Cancel (D5)**, Close ✕ at the sheet's top-right, bottom sheet | opens, 460 px centred dialog, same copy | `hosted2_free_*_sheet_*.png` |
| Dark theme (V04, palette consistency only) | head, rows, schedule row, phone bar, bottom sheet all on the dark palette; no light-palette leak (inspected `hosted2_free_laws-ndps_390x844_dark.png`, `hosted2_free_add-ndps-direct_390x844_dark.png`) | same | `hosted2/free/*_dark.png` |
| States (`tools/capture_states.py`) | chapter expanded, About open, focused chapter row, focused schedule link | same | `hosted2/free_states/`, `manifests/hosted2_states_free_dd04a5a2.json` |
| Keyboard (`tools/capture_keyboard.py`) | Tab order Back → CTA → About → rows; Enter on each of four chapter rows sets `aria-expanded="true"`; Enter on the CTA shows "Opening…" and the sheet opens after **5.8 s** with focus on Close; Tab cycles Unlock Playground ↔ Close inside the dialog; Escape closes it and focus returns to the CTA with its label | same; sheet after **7.1 s** | `hosted2/free_keyboard/`, `manifests/hosted2_keyboard_free_dd04a5a2.json` |
| PF-2 (`tools/verify_busy.py`, 2.5 s emulated latency) | before: label, no `aria-busy`; 0.3 s after three rapid clicks: "Opening…", `aria-busy="true"`, `is-opening`, opacity 0.72, cursor progress, pointer-events none, href unchanged; **1** `/add` request; sheet open after **5.82 s**, label restored, `aria-busy` removed, Close focused; after Close: dialog closed, focus on the trigger with its original label | same; open after **6.08 s** | `hosted2/free_busy/busy_during_{390,1280}.png`, `manifests/hosted2_busy_free_dd04a5a2.json` |

PF-1 measurement on this deployment (signed-in Free): the sheet opened 5.8–7.1 s after the click in every run (the matrix poll, the keyboard run without throttling, the busy run with 2.5 s added latency), against an instant open for the guest. Consistent with §11.4; the cause stays a hypothesis for the hardening programme.

### 13.3 Pro (profile port 9463 — the owner's Pro-granted staging account, device-capped)

The account is at its 2-device cap with two older test devices, so the persistent Pro profile's registration was **refused** (`REGISTER_LIMIT`; it is not registered — see §13.5) and on this deployment every Act head serves kind **`device_blocked`**: CTA "Manage devices" → `/profile/security/devices` (a plain ghost link, not a sheet opener), note "Device limit reached. Your subscription supports Playground on up to 2 registered devices." Within that kind the hosted rows match the local Pro candidate for everything except the CTA/kind (meta, row types and hrefs, schedules, About, no horizontal scroll) at 390 and 1280, light and dark, with one explained difference: `/playground/laws/ndps/add` by URL locally answers 303 to the Playground because the Pro fixture already holds NDPS, whereas the staging account does not hold it and gets the Act head with the served dialog (the four `add-ndps-direct` rows; roster state, not M2): `manifests/hosted2_pro_dd04a5a2.json`, `hosted2/pro/`; states captured on both widths (`hosted2/pro_states/`, `manifests/hosted2_states_pro_dd04a5a2.json`). The in-page sheet does not open from this CTA (correct for the kind). `/playground/laws/{ndps,uapa}/add` by URL returns 200 with the served dialog open over the head (panel kind `device_blocked`: title "Add NDPS Act to October?", lines "This will use 1 of your 30 law spaces for October." / "You'll have 29 spaces remaining.", primary "Manage devices", Cancel, Close focused). That composition — the confirm title and capacity lines with the device-limit primary — is the frozen template's (`5d89fbd`, same title/lines/primary/Cancel for `kind == "device_blocked"`), restyled by M2's panel; it is recorded here as an observation, not an M2 defect.

**Consequence for acceptance.** The Pro `eligible_to_add` rows at 390 px and in dark mode are **not verified on staging** by this run; the Pro eligible evidence remains §10.2 (deployment `0eb35808`, 375 px, light). Reaching them needs the separately authorised device revocation on the staging account (not Claude's action), after which the Pro profile pass is a 10-minute rerun of the same tools.

### 13.5 Pro device read-back and revocation proposal (2026-10-26, read-only)

Read through the Pro profile with a GET of `/profile/security/devices` (no form submitted). Times are as the page prints them (naive UTC from `last_seen_at`).

| Device (as listed) | Registered | Last seen | State | Attribution |
|---|---|---|---|---|
| Chrome on macOS — `2135f78c…` | 20 Oct 2026 | 20 Oct 2026 18:11 | Active | the owner's browser-pane Pro session used for §10.2 (2026-10-20) |
| Web browser — `f419faa3…` | 19 Oct 2026 | 19 Oct 2026 20:33 | Active | Cursor's M1 paid-pack capture client (registered 20:32–20:33Z on 2026-10-19 per that pack's `device_readback`) |
| Chrome on Linux | 19 Oct 2026 | 19 Oct 2026 20:33 | Removed | Cursor's other M1 capture client, removed earlier |

The persistent Pro profile (port 9463, created 2026-10-25) is **not** in the list: at 2 of 2 the service answers `REGISTER_LIMIT` and does not register it, hence the `device_blocked` kind in §13.3.

**Proposal (needs the owner's explicit authorisation; nothing has been submitted):** remove **Web browser `f419faa3…`** — the older idle test client, last seen 2026-10-19 — and keep Chrome on macOS (the owner's pane session). After the removal the Pro profile registers itself on its next Playground-gated request (the Act head runs `ensure_current_device`), so no sign-in is needed. Rules checked in `devices/service.py` and `devices/postgres.py`: the limit is 2 active devices; a removal followed by a new registration counts as a replacement, limited to 3 per 30 days; this account would be at 2 of 3 in the window (the Chrome on Linux removal paired with the 20 Oct registration being the first), so the registration is expected to succeed; a removed device is never auto-restored. Then the Pro eligible rows (heads, in-page sheet and direct URL at 390 and 1280, light and dark, states, keyboard, PF-2) are a rerun of the §13.2 tools against port 9463.

### 13.4 Hosted record after this deployment

| Cohort | 390 | 1280 | Dark | States | Keyboard | PF-2 | Add dialog |
|---|---|---|---|---|---|---|---|
| Guest | ✓ | ✓ | ✓ | ✓ | ✓ (§10.1 on `0eb35808`) | ✓ | in-page + URL ✓ |
| Free | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | in-page + URL ✓ |
| Pro | device-blocked kind only | device-blocked kind only | device-blocked kind only | ✓ | — | — | eligible rows at 375 light only (§10.2); device-blocked panel by URL ✓ |
| Plus, Max, expired, halted | not run (local fixtures only) | | | | | | |
