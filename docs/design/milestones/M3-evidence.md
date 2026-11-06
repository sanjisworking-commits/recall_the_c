# M3 — Browse and Laws catalogue by tier · LOCAL / PRELIMINARY evidence

| Item | Value |
|---|---|
| Branch / PR | `pg-m3-browse-laws`, cut from `pg-m2r-act-head` @ `9c47d1e`; draft PR (base `pg-m2r-act-head`) — see §0 |
| Integration commit | `945a67f` = merge of `main` @ `ea15591` into `9c47d1e` (no M3 edit; conflicts were the asset pins in `base.html` and the two pin tests, resolved to the stack's pins `main90` / `mob109` / `mob30` plus main's new `schedules.js?v=sched1` include) |
| Checklist | `docs/design/milestones/M3.md` @ `aad33e0` (PR #218) as corrected by the tier-revision plan §3.4; owner decisions of 2026-11-06 (§6) |
| Flag | `PLAYGROUND_TIER_MODEL` stays `monthly` by default; M3 prints no Playground allowance copy under either model |
| Tooling | `docs/design/proto-comparison-2026-10-19/m1r/tools/capture_m1r.py` (route probe: navigation surfaces, phone bar, label, hScroll, 44 px targets, composited contrast, Tab trails), `…/m3/tools/readback_m3.py` (per-tier text read-back through the app's own TestClient); dev launchers `playground-m3-<tier>` (monthly, port 8918) and `playground-m3-<tier>-choices` |
| Status | LOCAL / PRELIMINARY — hosted checks NOT RUN (no deployment). Every row states **PASS on this SHA**, **carried forward from SHA**, **BLOCKED** or **NOT RUN**. |

## 0. Gate 2 — combined baseline on `945a67f` (before any M3 edit)

Focused shell-and-Schedule check (`m3/00-merge-check/{guest,free}/`, 72 rows: `/browse`, `/browse/schedules/eighth`, `/laws`, `/laws/ndps`, `/dashboard`, `/settings` × 390 / 720 / 1280 × light / dark, guest and Free):

| Check | Result on `945a67f` |
|---|---|
| Phone navigation (390) | exactly one phone bar on every route, one navigation surface; Profile tap recorded (`--tap-profile`) |
| Desktop header (720, 1280) | one navigation surface, no phone bar; signed-in label `RecallC Free` on every route (visible at 1280, in the collapsed account control at 390/720) |
| Schedules on Browse | 12 Schedule cards present for every viewer; main's lede ("…then the twelve Schedules…") and "Parts, writs, amendments" carried in by the merge |
| Representative Schedule (`/browse/schedules/eighth`) | renders; content as on `main` |
| Horizontal scroll | **none on any of the 72 rows.** The negative margin from `e84e179` is still present on this SHA (`.sched-page` measures 1288 px at a 1280 px viewport, margin `-8px -4px 0`), but the Playground stack's wrappers (`.page-wrap`, `.sheet`, `.main`) carry `overflow-x: hidden`, so the document does not scroll. The fix (`margin: -8px 0 0`) is **not** in this branch; its PASS stays attached to `e73bd41` (PR #236). When PR #236 reaches this branch the probe is re-run and the row moves to PASS on that SHA. |
| Contrast / targets | 0 low-contrast rows, 0 sub-44 px targets (the M1-R shell, carried forward from `d7d3c30`) |
| Tests on `945a67f` | targeted integration suites (`test_browse_schedules`, `test_shell_m1r`, `test_mobile_screens`, `test_settings_phone`, `test_web_sprint30`, `test_root_assets`, `test_law_loading`, `test_bare_act_sitemap`, `test_laws_request_breakdown`, `test_laws_request_bootstrap`): **219 passed**; full suite: see §2 |

Carried forward unchanged by the merge: shared shell from M1-R `d7d3c30` (PR #232), Browse/Schedules content and routing from `ea15591` (PR #234 record), Act head and Add dialog from M2-R `3ad4b82` / `bd9347a` (PR #235).

### 0.1 Baseline-before-edit of the M3 surfaces (`m3/01-baseline-945a67f/`)
- Captures (reduced policy): guest `/browse`, `/browse/part/iii`, `/laws`, `/laws/ndps`, `/laws?q=ndps`, `/laws?subject=criminal`, `/laws?status=repealed` at 390 / 1280 × light / dark (28 rows, Tab trails on `browse` and `laws`); Free `/browse`, `/laws`, `/laws/ndps` (12 rows); Plus `/browse`, `/laws` after adding NDPS through the app's own Add sheet (4 rows, light).
- Read-back rows (`readback.md`, `readback.json`; monthly model; today-relative subscription windows): **the Free summary ("Free plan — pick any 3 Articles… Unlock all") is served to Free, Pro, Max, paused and pending accounts**; Plus, expired and halted get none; the guest strip still promises "save 3 Articles"; every signed-in `/laws` prints six per-card Playground buttons on phone; the guest `/laws` is the fixture (chips include "Commercial", omit "Health"); the search field is hidden behind a toggle on every viewer; `/browse` phone shows the Part rail and the Marks sheet. These are the defects M3 closes (§1).

## 1. What changed (scope diff)
_(filled as the steps land)_

## 2. Tests
_(filled as the steps land)_

## 3. Gate 1 — Free Article promise through the real Learn → Done flow
**NOT RUN** until executed (see plan). Code inspection: every signed-in account resolves to full Constitution access (`web/entitlements.py::access_level`), so no claim prompt is expected.

## 4. Route matrix
_(filled after implementation)_

## 5. Visual and accessibility
_(filled after implementation)_

## 6. Decisions (owner, 2026-11-06)
| # | Decision |
|---|---|
| Baseline | `pg-m2r-act-head` @ `9c47d1e` + `main` @ `ea15591` (integration commit `945a67f`) |
| Q1 | `/browse/part/{slug}` stays reachable; phone Part rail retired; collapsible Part headers (`<button aria-expanded>`), open by default |
| Q2 | Marks legend: icons with text labels |
| Q3 | one data-driven catalogue for every viewer; card meta from `BareAct.head_meta_label`; chips from `catalog.visible_subjects`; guest fixture deleted |
| Q4 | Free summary for RecallC Free only, phone and desktop; none for Plus / Pro / Max; expired / halted keep their header status |
| Q5 | phone Browse keeps the search icon; marks filter inline (sheet retired); Laws search field visible |
| Copy | Free: "Free plan — every Article, progress saved." + "View Playground" → `/playground`; guest: "Reading as a guest. Sign in to save your progress." with one Google action; no price, no law-choice sentence |
| Record | The older checklist's "three active laws" is superseded by **"three permanent law choices per account"** (B1 / M2-R model); M3 itself prints no allowance copy |

## 7. Not run
Hosted / staging checks; automated accessibility scan; screen reader; gate 1 (until executed).
