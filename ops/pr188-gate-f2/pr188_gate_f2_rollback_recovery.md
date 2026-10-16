# PR #188 Gate F2 — Rollback and recovery review (2026-10-16, rev b)

**GATE F2: PARTIAL PASS — Recovery not yet certified.** Review only.

PR #188 stays **draft**. E3 and E4 remain closed. F1 is compatible with a
restricted, Playground-disabled rollout. F2 is **not fully closed**.

No Railway modifications, migrations, deployments, or PR merges are
authorized by this document. Redeploy / Rollback were **not** clicked.

| Question | Answer |
|---|---|
| Can the application roll back to `0c0a8d5` without downgrading Alembic? | **Yes**, for a restricted rollout (Playground off, new subscriptions not live). E4 already ran the old app on schema `0027`. |
| Is Railway `0c0a8d5` confirmed as a dashboard rollback target? | **Not yet checked** in the Deployments UI. See §4. |
| Is database recovery certified? | **No.** Pre-E3 encrypted backup `20261016T072148Z` is a protected 0016-era point. No post-E3 `0027` snapshot. No full Supabase restore rehearsal. |

This does **not** certify Plus/Pro/Max, device enforcement, or payments.

---

## 1. What is already established

| Check | Finding | Status |
|---|---|---|
| Old application works with migrated database | Operator E4 browser tests after E3; live HTTP still old app | **PASS** |
| Startup command | `railpack.json` startCommand identical on `0c0a8d5` and `5d89fbd` (uvicorn only) | **PASS** |
| Automatic Alembic on startup | Not present in `railpack.json` | **PASS** |
| Playground kill switch | `PLAYGROUND_ENABLED=false` in Railway (F1 confirmed; not re-edited) | **PASS** |
| `0c0a8d5` ignores 0017–0027 tables | `git grep -w` of all 15 names on `origin/main` = 0 files | **PASS** |
| Alembic downgrade from HEAD | Each 0017–0027 `DOWNGRADE` `DROP`s those tables (or drops `learned_at` / shrinks iOS check) | **Forbidden** as rollback |
| Previous Railway deployment retained | Dashboard Deployments list not opened from this environment | **Pending** |
| Restore/redeploy action visible | ⋮ menu not observed | **Pending** |
| Full database restore tested | No | **Pending** |
| Post-E3 `0027` encrypted backup | Not in this record | **Pending** |

The most important result: the existing application has already operated
successfully against the upgraded database. That supports rolling the
**application** back to `0c0a8d5` without downgrading Alembic.

---

## 2. Proposed rollback procedure (not authorized to execute)

If a future PR #188 deployment on `env` / `recall-th-c` fails:

1. **Detect failure** — health, login, Browse, Learn, database errors.
2. **Keep Playground disabled** — preserve `PLAYGROUND_ENABLED=false`.
   Do not unset it (HEAD defaults the flag **True**).
3. **Restore the previous application deployment** — target git
   `0c0a8d5` (`0c0a8d555748cb5fa63a5fbe0a43998ee5c1d942`, Merge PR #209),
   **only after a separately authorized rollback**. Operate only
   `trustworthy-embrace` / `env` / `recall-th-c`. Ignore sibling
   `recall_the_c` (underscore) and historic `memorize_the_c`.
4. **Preserve database revision `20260927_0027`** — no `alembic downgrade`,
   no `alembic stamp`, no table deletion, no restore-into-live.
5. **Recheck live health** — `/health` 200, Google sign-in, Constitution
   Browse/Learn, `/playground` FastAPI JSON 404 (not HEAD’s styled page).

### Billing limitation

`0c0a8d5` has **zero** Python files containing `webhook`. PR #188 head
registers `POST /api/billing/subscriptions/webhook/razorpay` via
`subscriptions/webhook_routes.py`. Rolling back to `0c0a8d5` **drops that
route**.

This rollback is suitable for a **controlled release with Playground and
new subscriptions disabled**. It is **not** suitable after live
subscription billing has begun.

---

## 3. Database recovery gap

The verified encrypted backup dated **`20261016T072148Z`** was taken
**before E3**. It is a protected pre-migration recovery point at Alembic
`20260828_0016`. It does **not** contain revision `0027` or the fifteen
new tables.

Earlier closed Gate E2 archive `recall_prod_gate_e2_20261015T063833Z.tar.age`
(SHA `6ff82b61c3dc89f910d78781b597731cc0e7200fce6c2f46b66376ec9c6faf4c`)
is the same class of 0016-era artifact. Gate B Attempt 3 remains the
verified **procedure** for a public-schema restore onto a **disposable
local** database (stubs, 25 tables, `0016`). That is not a restore of
`20261016T072148Z`, not a live restore, and not Auth/Storage/Vault.

| Recovery need | Status |
|---|---|
| Pre-E3 public-schema dump exists and is encrypted off-laptop | Recorded (`20261016T072148Z`) |
| Gate B Attempt 3 procedure | Proven on local Postgres 17 |
| Restore of that file executed | **No** (`pg_restore --list` / checksums ≠ restore) |
| Full Supabase restore rehearsal | **No** |
| Post-E3 snapshot at `0027` | **No** |
| Restore into live as F rollback | **Forbidden** (discards writes after dump time T; would also drop 0027 objects if the dump is 0016-era) |

**Before releasing new application code**, take a separately authorized,
fresh **post-E3** encrypted backup and run a **disposable-environment**
restore rehearsal. **Neither operation is authorized by this review.**

---

## 4. Railway rollback availability — this environment

**F2 finding: Not yet checked** (Deployments UI).

This cloud VM has no Railway dashboard session (unauthenticated fetch of
the Gate D deployment URL returns Login / 404). There is no Railway API
token here. **No Redeploy, Rollback, Restart, or Remove was sent.**

Read-only corroboration that is **not** a substitute for the ⋮ menu:

| Source | What it shows |
|---|---|
| GitHub commit status on `0c0a8d5` | Context `trustworthy-embrace - recall-th-c` = **success**, description `Success - recall-the-c.in`, updated 2026-10-15T03:07:57Z |
| Status target | Service `recall-th-c`, environment `env` (`4352cbd8-…`), Railway deployment **`76fbfcad`** (Gate D restart of the same git SHA) |
| Live HTTP 2026-10-16 | `/health` 200 `{"status":"ok"}`; `/playground` 404 `{"detail":"Not Found"}` `application/json` (old app still serving) |
| GitHub environment `trustworthy-embrace / env` | Deployment `6656601995` (sha `0c0a8d5`, created 2026-09-25) latest GitHub state **inactive** after sibling `7082767438` (`5d89fbd`) on the **same GitHub environment**. That sibling is **not** `recall-th-c`. Do not treat GitHub env inactivity as “live `recall-th-c` left `0c0a8d5`”. |

### What the Mac dashboard still has to answer

Open Railway → `trustworthy-embrace` → `env` → `recall-th-c` → **Deployments**.
Do not click Redeploy, Rollback, or any other action.

| If you see | Record as |
|---|---|
| Active `0c0a8d5` / `76fbfcad` retained, and ⋮ shows Rollback and/or Redeploy | Yes — deployment is retained and a restore/redeploy action is available |
| The row is visible, but ⋮ has no Rollback and no Redeploy | Deployment is visible, but no restore/redeploy action is available |
| No `0c0a8d5` / `76fbfcad` row on this service | I cannot find this deployment |

Railway docs (not observed in the UI here):

- **Rollback** restores a previous deployment’s image and custom variables
  **without a rebuild**, only while the image is inside the plan’s
  retention window after that deployment is removed. Outside the window
  the Rollback item is **hidden**.
- **Redeploy** from a previous deployment’s ⋮ menu rebuilds that
  deployment’s original source and configuration. It is the fallback
  when Rollback is hidden.
- After PR #188 merges, `main` will no longer be `0c0a8d5`. Application
  rollback then **depends** on that historical Railway deployment (or an
  explicit deploy of SHA `0c0a8d5`). Confirming the ⋮ menu **before**
  merge is the remaining F2 deploy-history check.

---

## 5. Frozen identities

| Item | Value |
|---|---|
| PR #188 | OPEN, **draft**, unmerged — https://github.com/sanjisworking-commits/recall_the_c/pull/188 |
| PR head | `5d89fbdfb6c712a998ce1fdbc4a7756fee8677b8` |
| `main` / rollback SHA | `0c0a8d555748cb5fa63a5fbe0a43998ee5c1d942` |
| Live service | `trustworthy-embrace` / `env` / `recall-th-c` |
| Kill switch | `PLAYGROUND_ENABLED=false` |
| Operator schema | `20260927_0027` (E3/E4 closed; this agent did not run Alembic) |
| Pre-E3 backup (F2 recovery point) | `20261016T072148Z` (0016-era) |
| Gate B dump SHA-256 | `2026e09e9acba2e9b8d6b411c5952f1b4387c80831c58f8882c958180d782cdd` |

---

## 6. Authorization (this revision)

| Action | Status |
|---|---|
| Read-only git `0c0a8d5` vs `5d89fbd` | Done |
| Read-only HTTP `https://recall-the-c.in` | Done |
| Read-only GitHub deployments / commit statuses | Done |
| Railway Deployments UI | **Not opened — Pending** |
| Railway writes, Redeploy, Rollback | **Not authorized — not done** |
| Alembic / restore-into-live / post-E3 dump | **Not authorized — not done** |
| Merge PR #188 | **Not authorized — not done** |

---

## 7. Gate F (merge)

**Not authorized.** F2 remains a **partial** pass until:

1. Mac dashboard confirms `0c0a8d5` is retained on `recall-th-c` with a
   visible restore/redeploy action (without clicking it), and
2. A separately authorized post-E3 backup plus disposable restore
   rehearsal closes the recovery gap — or an explicit residual-risk
   acceptance is recorded.

Current live state is already the application rollback target: old app,
kill switch on, schema reported at 0027. That is E-before-F, not a
Playground Stage 2 cutover.
