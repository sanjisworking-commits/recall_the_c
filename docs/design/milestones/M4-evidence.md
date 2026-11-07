# M4 — Today by tier · LOCAL / PRELIMINARY evidence

| Item | Value |
|---|---|
| Branch / PR | `pg-m4-today`, cut from `pg-m3-browse-laws` @ `6186863` (the signed-off M3 head); draft PR (base `pg-m3-browse-laws`) |
| Integration | none due: `origin/main` has no commit after `ea15591` (checked 2026-11-07); the M3 integration check on `945a67f` stands. The overflow fix PR #236 (`e73bd41`) is still outside the stack. |
| Checklist | `docs/design/milestones/M4.md` (PROPOSED 2026-11-07; owner decisions §4 pending) |
| Flag | `PLAYGROUND_TIER_MODEL` stays `monthly` by default; Today renders identically under `choices` (§0 read-back) |
| Tooling | `…/m1r/tools/capture_m1r.py` (route probe); `…/m4/tools/readback_m4.py` (nine states × two models × first run / after one real Learn → Done, through the app's TestClient); `…/m4/tools/serve_populated_m4.py` (serves a populated Today — one completed Article, two clauses due — for signed-in captures); dev launchers `playground-m4-<tier>[-choices]` (port 8920) |
| Status | LOCAL / PRELIMINARY — baseline recorded; implementation not started. Every row states **PASS on this SHA**, **carried forward from SHA**, **BLOCKED** or **NOT RUN**. |

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
Pending implementation.

## 2. Tests
Pending.

## 3. Gate — the Free promise reaches Today (M4-F08)
NOT RUN yet (automated test planned under both tier models).

## 4. Route matrix
Pending.

## 5. Visual and accessibility
Pending.

## 6. Decisions
Owner decisions Q1–Q7 (`M4.md` §4) pending.

## 7. Not run
Hosted / staging checks; automated accessibility scan; screen reader; real 200 % zoom.
