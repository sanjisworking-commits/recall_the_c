# Deployment, CI and Structure Hardening — Tracker

Six plans, each with its own approval, implementation authorization,
verification and stop point. Nothing from a later plan starts early.
Plans 3, 4 and 5 are never combined: they are the three places where a
mistake touches production data.

```
Plan 1  CI correctness                      IMPLEMENTED — draft PR open, awaiting merge authorization
Plan 2  Readiness + runtime correctness     QUEUED
Plan 3  Study Archive durable storage       QUEUED
Plan 4  Migration safety (= Gate E3)        IN PROGRESS / BLOCKED ON E3 PRECHECK
Plan 5  Railway deployment configuration    QUEUED (after Plan 4)
Plan 6  Cleanup / efficiency                QUEUED
```

Updated: 2026-10-15.

## Rules that apply to every plan

**Approval rhythm.** Plan written → user approves → user issues
AUTHORIZED TO IMPLEMENT → implementer works on only that plan → reports
SHA, files, tests → review → formal closeout here → next plan.

**Production rule (Plans 3, 4, 5).** Code, configuration and commands may
be prepared, but work stops before any production mutation. The user
performs every Railway apply, migration catch-up, backup and deploy.

**Branches.** Each plan has its own branch cut from the playground branch
head (`cursor/playground-220d`, currently the pinned `5d89fbd`), its own
worktree, and its own draft PR into `cursor/playground-220d`. While the
pin holds, those PRs stay draft and unmerged, because merging would
advance the pinned branch. The user authorizes every merge in writing.
Exception on record: Plan 1 was implemented on `ci/full-suite` from `main`
with draft PR #212 into `main`, on the user's instruction of 2026-10-15,
before this rule was stated; its retargeting is a pending decision.

**Hard boundaries while Gate E3 is open**

- `cursor/playground-220d` is pinned at
  `5d89fbdfb6c712a998ce1fdbc4a7756fee8677b8`: not modified, rebased,
  merged, force-pushed or advanced. PR #188 stays OPEN / DRAFT at that
  head; its recorded CI checks are not rerun.
- `~/.recall_gate_e3_worktree` is not modified.
- No Alembic revision, production database setting, Railway setting
  (`PLAYGROUND_ENABLED` stays `false`) or auth configuration changes
  outside the plan that owns it.
- No production database writes. No deploy of UI changes to the live site
  (it would change the E3 baseline).

**Parallel tracks**

| Track | Work allowed | Restrictions |
|---|---|---|
| A — Gate E3 (Plan 4) | Timeout handling, test scripts, complete the precheck | No production migration until separately authorized |
| B — UI development | Screens, CSS, JS, responsiveness, on its own branch and worktree | No migrations, DB models, auth or deployment config; local DB only, never production Supabase |
| C — PR #188 | Review only | Kept open and draft at the pinned head; never merged |

Parked UI workstreams (Screen 8/9, Screen 11, Stage 2, phone redesign)
need their own go-ahead and are not restarted under E3.

**Sibling documents on this branch:** `docs/PLAYGROUND_UI_REDESIGN_PLAN.md`
and `docs/PLAYGROUND_UI_REDESIGN_TRACKER.md` (UI programme), and
`docs/PLAYGROUND_DELIVERY_TRACKER.md` (Stage 1, frozen). This tracker covers
only the six hardening plans.

## Status board

| # | Plan | Status | Branch / PR | Implemented at | Closeout |
|---|---|---|---|---|---|
| 1 | CI correctness | Implemented, verified; draft PR open into `main` | `ci/full-suite` (from `main`) → [#212](https://github.com/sanjisworking-commits/recall_the_c/pull/212) (draft) | `edd7805595470e4f2f7c36b0e105bea06a3b0945` | pending: merge authorization, and whether to retarget onto the playground branch |
| 2 | Readiness + runtime correctness | Queued | — | — | — |
| 3 | Study Archive durable storage | Queued | — | — | — |
| 4 | Migration safety = Gate E3 | In progress, blocked on E3 precheck | `~/.recall_gate_e3_worktree` at `5d89fbd` (Cursor) | — | — |
| 5 | Railway deployment configuration | Queued, after 4 | — | — | — |
| 6 | Cleanup / efficiency | Queued | — | — | — |

## Plan 1 — CI correctness

**Owner:** Claude. **Branch:** `ci/full-suite` from `main` @ `0c0a8d5`.
**Scope:** `.github/workflows/ci.yml` only.

| Acceptance item | Status | Evidence |
|---|---|---|
| Python pinned to 3.12.11 (matches `.python-version`, Railway) | done | `edd7805` |
| pip cache keyed on `pyproject.toml` + the job's requirements file | done | run 38737144098: "Cache saved" on both jobs |
| One concurrency group per branch (`head_ref \|\| ref_name`) | done | `edd7805` |
| `workflow_dispatch` trigger | done | `edd7805` |
| Full non-integration suite on every push and PR; no commit-count gate | done (main never had the gate; the playground branch inherits this file when it next takes `main`) | run 38737144098: 2151 passed, 9 skipped, 1 deselected, 3:57 |
| PR runs test the merge commit | done | checkout log: `Merge edd7805… into 0c0a8d5…` |
| `Package install` job: wheel built, installed like Railway (`requirements-web.txt` then wheel `--no-deps`), ASGI import from `site-packages`, packaging test | done | run 38737144098: ASGI app created from `/tmp/prod-venv/lib/python3.12/site-packages/…`; 7 passed |
| Local validation at the same commit | done | suite 2151 passed, 9 skipped, 1 deselected (1:34); package steps green; 7 passed |
| Branch protection: require `Unit tests` and `Package install` on `main` | not started (dashboard, user) | — |
| Merge | awaiting authorization | — |

**Not changed:** `-m "not integration"` filter (one Docling test) kept;
no source, test, dependency, Alembic, Railway or auth file.

**Closeout:** merge SHA ______ · date ______ · reviewer ______.

## Plan 2 — Readiness + production runtime correctness

**Scope:** `GET /ready` (200 only after lifespan startup and a 2 s
`SELECT 1` on the pool; 503 otherwise; no Act hydration, no Supabase, no
Google); `/ready` added to `ROOT_ASSET_PATHS`, the noindex list and the
fast-path tests, never to `_BREAKDOWN_PATHS`; packaged fallback for
`data/reference/learning_relationships.seed.json`
(`planner/relationships.py:29` reads it only by repo path, so it is empty
in production today); audit of every `parents[3]` loader with one test
that boots from a non-repo working directory. No Railway change.

| Acceptance item | Status |
|---|---|
| `/ready` route and lifespan ready flag, with tests | not started |
| `/ready` excluded from session lookup and breakdown logging | not started |
| `learning_relationships.seed.json` packaged and loader falls back | not started |
| Loader audit test from a non-repo cwd | not started |
| App boots from a production-like install locally and in CI | not started |

**Stop point:** app boots correctly from a production-like install,
locally and in CI. **Closeout:** ______.

## Plan 3 — Study Archive durable storage

**Scope:** `web/study_archive/` package with `StudyArchiveStore` protocol
(SQLite for development, Postgres for hosted) and `StudyFileStore`
protocol (local filesystem for development, private Supabase Storage
bucket for hosted, service-role key server-side only); migration `0028`
(`study_entry` with `user_id`, `study_asset` with `position`,
`study_review`, indexes, RLS); session CSRF replaces the per-process
`X-Study-Token`; `DELETE` routes for entry and asset; account deletion
removes archive rows and bucket objects; user timezone for "not in the
future"; `STUDY_ARCHIVE_ENABLED`, `SUPABASE_SERVICE_ROLE_KEY`,
`STUDY_STORAGE_BUCKET`, `STUDY_MATERIALS_DIR` settings with startup
validation; feature stays enabled in production (no temporary disable).

| Acceptance item | Status |
|---|---|
| Store protocol + SQLite + Postgres implementations | not started |
| File store protocol + local + Supabase Storage client (MockTransport tests) | not started |
| Migration 0028 and the 12 head pins updated | not started |
| Session CSRF on mutating routes; allowlist labels updated | not started |
| Account deletion cleans rows and objects | not started |
| Multi-user ownership tests (user A cannot read or mark user B's entries) | not started |
| Survives restart and redeploy; no hosted path depends on Railway disk | not started |
| Tracker/plan reconciliation: X6 exclusion reversed by dated decision | not started |

**Stop point:** feature survives restart and redeploy semantics; no hosted
path depends on Railway disk. **Closeout:** ______.

## Plan 4 — Database migration safety (Gate E3)

**Owner:** Cursor, in `~/.recall_gate_e3_worktree` at `5d89fbd`.
**Status:** BLOCKED ON E3 PRECHECK. The production session-pooler
precheck returned `lock_timeout = 0` (expected 15 s),
`statement_timeout = 2min` (expected 120 s),
`idle_in_transaction_session_timeout = 0` (expected 60 s). Cursor is
correcting the timeout handling. Claude does not duplicate this and runs
no production migration command.

| Acceptance item | Status |
|---|---|
| Precheck passes with the expected timeouts | blocked |
| Production revision reviewed (`alembic current`) | — |
| Backup of the provider behind `DATABASE_URL` taken (user) | — |
| Destructive migrations reviewed (`0005`, `0011` delete rows irreversibly; `0014` dedupes) | — |
| Manual catch-up to head `20260927_0027` (user) | — |
| `scripts/verify_postgres_migrations.py` exit 0 against production | — |
| Schema-drift detection: `/ready` returns 503 when the DB is behind head | — |

**Stop point:** production known to be at head and verified.
**Closeout:** ______.

## Plan 5 — Railway deployment configuration

**Scope:** `railway config pull` to establish `.railway/railway.ts` from
the real service (`recall-th-c`, environment `env`); `healthcheck:
"/ready"`, `healthcheckTimeout`, `preDeploy: "alembic upgrade head"`
with a finite timeout, non-secret `env`, supported restart and deployment
settings; watch paths and restart policy stay in the dashboard if the IaC
file does not round-trip them; `docs/DEPLOYMENT_RUNBOOK.md` records every
dashboard-only value. The user runs `plan`/`apply` and the deploy.
Depends on Plan 2 (`/ready`) and Plan 4 (DB at head).

| Acceptance item | Status |
|---|---|
| IaC file pulled from the live service and committed as baseline | not started |
| Healthcheck `/ready` with timeout | not started |
| Pre-deploy `alembic upgrade head` with timeout | not started |
| Watch paths set (dashboard or IaC) | not started |
| Runbook with every dashboard-only setting and the service/environment ids | not started |
| One real deploy with pre-deploy and readiness verified (user) | not started |

**Stop point:** one successful real Railway deploy with pre-deploy and
readiness verified. **Closeout:** ______.

## Plan 6 — Cleanup and efficiency

**Scope:** `pyproject.toml` as the single dependency source (Railway
`pip install .`, CI `pip install -e ".[dev]"`, then delete the three
requirements files); delete the duplicate root
`Constitution_Of_India_2026.pdf`; Railpack layer excludes for docs, tests,
corpus inputs and archives after the package job proves the app boots
without them; `GZipMiddleware` and `Cache-Control` for versioned static
assets. Later and separately: `web/app.py` route-module extraction (with
the source-text test constraints recorded in the plan) and the
`data/runtime` vs `data/corpus` split.

| Acceptance item | Status |
|---|---|
| Dependency source of truth consolidated | not started |
| Duplicate PDF removed | not started |
| Payload excludes | not started |
| Static caching and compression | not started |
| (Later) `app.py` modularisation | not started |
| (Later) runtime/corpus data split | not started |

**Closeout:** ______.

## Decision log

| Date | Decision |
|---|---|
| 2026-10-10 | Full suite on every push; no fast/full split now. |
| 2026-10-10 | Migrations move to a Railway pre-deploy step, after a one-time manual catch-up with backup. |
| 2026-10-10 | Study Archive stays enabled in production, backed by Postgres metadata and private Supabase Storage; local disk is never durable state. |
| 2026-10-10 | Railway settings go into `.railway/railway.ts` now (config-as-code is deprecated, cutoff 2026-12-01). |
| 2026-10-15 | Plan 1 lands on `ci/full-suite` from `main` as a draft PR into `main`; the pinned playground branch is not touched. |
| 2026-10-15 | Gate E3 = Plan 4, owned by Cursor, blocked on the pooler precheck. |
| 2026-10-15 | Hardening branches are cut from the playground branch, not `main`; draft PRs target `cursor/playground-220d` and stay unmerged while the pin holds. This tracker lives on `docs/hardening-tracker` from `5d89fbd`. |

## Closeout record

| Plan | Merge SHA | Date | CI run | Verified by |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |
