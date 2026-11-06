# Fix for PR #233 acceptance finding 4.1 — 4 px horizontal scroll on Schedule pages at ≥ 720 px

**Change** (this PR, one rule): `.sched-page { margin: -8px -4px 0 }` → `margin: -8px 0 0` in `styles.css`; stylesheet pin `main73` → `main74`; regression test `tests/test_browse_schedules.py::test_schedule_page_wrapper_has_no_horizontal_negative_margin`.

**Re-measurement** (local dev server on this branch, guest, headless Chrome 156 over CDP with the M1-R probe from PR #232; `manifest.json` holds every row with its SHA-256):

| Routes | Widths × themes | Rows | `scrollWidth > innerWidth` before (`ea15591`) | after (this branch) |
|---|---|---|---|---|
| `/browse`, all twelve `/browse/schedules/<ord>`, `/browse/schedule/sixth` (legacy redirect), `/browse/schedules/thirteenth` (404) | 720×900, 1280×900 × light, dark | 60 | 52 (every Schedule page and the redirect; Browse and the 404 were clean) | **0** |

Spot check in the browser pane on `/browse/schedules/eighth`: `scrollWidth` 1280 at `innerWidth` 1280, 720 at 720; `.sched-page` spans 0–1280 px with computed margin `-8px 0px 0px`.

Representative capture: `sched-eighth_1280x900_light.png` (the page with the most interactive content; the other eleven differ only in body). Phone widths (< 561 px) were already clean because `mobile.css` sets `.sched-page { margin: 0 }`, so they were not re-captured. Tier variants add nothing for this fix: the rule is tier-independent, and the shell was not touched.

Unchanged pre-existing `main` guest-shell observations (recorded in the acceptance record, addressed in the Playground stack): 56 rows still report the 62×32 "Sign in" control as a sub-44 px target.
