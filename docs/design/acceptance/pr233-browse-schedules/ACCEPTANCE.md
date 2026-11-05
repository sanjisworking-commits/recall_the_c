# Browse / Schedules — one-time shared acceptance (PR #233)

| Item | Value |
|---|---|
| Reviewed SHA | `ea15591` = `main` after the merge of PR #233 (`cursor/schedules-full-extract-1a75` @ `adaf21b`, first parent `ea15591^1`) |
| Scope | the twelve `/browse/schedules/<slug>` pages, the Browse index's twelve Schedule cards, the legacy `/browse/schedule/<slug>` redirect, the 404 for an unknown slug, plus a focused shared-shell regression check (PR #233 touches `base.html`, `styles.css`, `mobile.css`) |
| Method | local dev server on the `main` checkout (fake Google provider, throwaway SQLite); headless Chrome over CDP with the M1-R probe (`capture_m1r.py` from PR #232): navigation surfaces, phone tabs, avatar, header overlaps, horizontal scroll, 44×44 targets, computed contrast; guest at 390 / 720 / 1280 × light / dark (84 rows), Free signed-in at 390 / 1280 light (28 rows); block counts compared with `schedules.json`; the list toggle and language notes exercised in the browser pane; `tests/test_browse_schedules.py`, `tests/test_settings_phone.py`, `tests/test_web_sprint30.py` run on `ea15591` (27 passed) |
| Evidence | representative captures and both probe manifests in this folder (see `README.md`); full set reproducible with the tool |
| Status | **LOCAL** — accepted for shared Browse/Schedule content with the exceptions in §4; hosted check NOT RUN |

Status vocabulary (owner, 2026-11-06): **PASS on `ea15591`** = measured on this SHA; **carried forward** names the SHA whose evidence stands; **FAIL** = defect found on this SHA.

## 1. Shared Schedule content — PASS on `ea15591`

Each distinct content structure was checked once (the policy's "a Sixth Schedule clause tree and a Seventh Schedule list need separate checks"); every page was captured at phone and desktop width in both themes.

| Schedule | Structure (extract block types) | Rendered on `ea15591` | Result |
|---|---|---|---|
| First | 2 tables (States / Union territories), heading, notes | 36 rows as `sched-tr` grids; notes rendered | PASS |
| Second | 4 parts × clauses, 3 pay tables, leads | 4 `sched-sec`, 33 `sched-cl`, 6 pay rows | PASS |
| Third | oaths (`pre`/`post` forms) | 10 oath blocks | PASS |
| Fourth | paragraph + seat-allocation table | 32 rows | PASS |
| Fifth | 7 parts, 25 clauses, headings | 7 / 25 | PASS |
| **Sixth** (clause tree) | 29 paragraphs / 172 clauses, 17 leads, table | **29 `sched-sec` / 172 `sched-cl`** — matches the extract and `test_sixth_and_ninth_match_official_extract` | PASS |
| **Seventh** (lists) | 3 lists with `rows`/`subs` (100 / 61 / 52 entries) | 3 collapsible lists; List I open, II and III collapsed on load; toggle is a real `<button aria-expanded>` (67 px tall), expanding reveals the rows and flips the label (exercised in the browser pane) | PASS |
| Eighth (languages) | 22 languages, 20 with amendment notes | 22 cards, 20 with the `i` marker; note opens on hover, click and **keyboard focus** (real Tab, `focusin` → `data-open`), closes on blur | PASS (see §4.3) |
| **Ninth** (numbered) | 308 paragraph blocks numbered through 284 (omitted numbers stay omitted) | 308 `sched-p` — matches the extract and the unit test | PASS |
| Tenth | 7 parts / 34 clauses | 7 / 34 | PASS |
| Eleventh, Twelfth | one table each | 29 / 18 rows | PASS |
| Browse index | twelve designed Schedule cards | 12 `href="/browse/schedules/…"` cards | PASS |
| `/browse/schedule/sixth` | legacy route | `301 → /browse/schedules/sixth` | PASS |
| `/browse/schedules/thirteenth` | unknown slug | `404` | PASS |

Visual check (captures opened): typography, numbering columns, the clause tree indent, list heads and the language grid read correctly at 390 and 1280 in light and dark; dark theme uses the shared tokens (no light-only colours spotted).

Tier variants: the Schedule pages carry no tier-dependent action. The only guest / signed-in difference is the guest modal partial included for guests (`browse_schedule.html` end); Free signed-in captures of the Sixth Schedule at 390 and 1280 are in this folder as the single representative pair. Plus / Pro / Max share the signed-in evidence (no visible difference; no capture).

## 2. Focused shared-shell regression check — PASS on `ea15591` (no shell change)

- `base.html` diff in PR #233 is the two cache-buster pins only (`main72→main73`, `mob95→mob96`).
- Every changed line in `styles.css` / `mobile.css` sits inside `.sched-*` rules (`.sched-list-head`, `.sched-list-body .sched-tr`, `.sched-notes ol/li → .sched-note`); no shell selector changed.
- Probe: all twelve Schedule pages carry the same shell metrics as `/browse` at each width (surfaces, phone tabs, overlaps, header visibility, target and contrast flags identical across the 13 routes) — the shell renders identically on the new pages.
- Pre-existing `main` shell state recorded, **not** a PR #233 regression and already addressed in the Playground stack (PR #219 M1 / PR #232 M1-R): guest phone-tab labels `--mid` (3.21:1) and a 62×32 "Sign in" control at ≥ 720; the `main` guest header has no `PrimaryTabs--top` nav (the probe reports `surfaces=0` at 1280).

## 3. Automated checks — PASS on `ea15591`
`tests/test_browse_schedules.py` (7: seed of twelve, read-only cards, index cards, every page renders, unknown slug 404, typed blocks, Sixth/Ninth counts), `tests/test_settings_phone.py`, `tests/test_web_sprint30.py`: 27 passed locally. Permission checks: the Schedule pages are public read-only reference for every tier (guest and signed-in both `200`); no tier gate exists to test.

## 4. Exceptions / findings on `ea15591`

### 4.1 FAIL — 4 px horizontal scroll on every Schedule page at ≥ 720 px (pre-existing, from `e84e179`)
`.sched-page { margin: -8px -4px 0 }` (styles.css ≈ 3488, introduced by `e84e179` "Rebuild Browse Schedule cards to the Nov 2026 reference design", i.e. before PR #233) makes the section 1288 px wide in a 1280 px viewport (`scrollWidth 1284`), so `document.documentElement.scrollWidth > innerWidth` on all twelve pages at 720 and 1280, light and dark. The phone rule (`mobile.css` ≈ 5492, `.sched-page { margin: 0 }`) hides it below 561 px, which is why 390 is clean. `/browse` itself is clean at every width. **Fix:** drop the horizontal part of the negative margin (`margin: -8px 0 0`) or clip the wrapper (`overflow-x: clip` on `.sched-page`/`.sheet`); one line, not applied here (acceptance record only).

### 4.2 Observation — Sixth Schedule table
The extract's Sixth Schedule table (paragraph 20) renders through the clause renderer rather than as a `table` block; content is complete (counts match). No action.

### 4.3 Observation — language notes are visual-only
The Eighth Schedule note text lives in `data-sched-tip` and is shown as CSS generated content (`::after`) when `data-open="true"`; there is no `aria-describedby` / `role="tooltip"` and the focused card shows its focus by background wash, not an outline. Keyboard users see it; screen-reader users are not told a note exists. Suggest `aria-describedby` to a visually hidden note element in a follow-up.

### 4.4 Handover paths
`docs/design/schedules/README.md` and the PR #233 description contain no local screenshot paths; the handover's evidence is now this folder, linked from that README.

## 5. Not run
Hosted / staging check (no deployment in scope); automated accessibility scan; screen reader.
