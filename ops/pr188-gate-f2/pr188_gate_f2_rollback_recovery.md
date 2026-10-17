# PR #188 Gate F2 — Rollback and recovery review (2026-10-16, rev b)

**GATE F2: PARTIAL PASS — Recovery not yet certified.** Review only.
(rev d, 2026-10-17: Railway `76fbfcad` Active on `recall-th-c`; ⋯ present.)

PR #188 stays **draft**. E3 and E4 remain closed. F1 is compatible with a
restricted, Playground-disabled rollout. F2 is **not fully closed**.

No Railway modifications, migrations, deployments, or PR merges are
authorized by this document. Redeploy / Rollback were **not** clicked.

| Question | Answer |
|---|---|
| Can the application roll back to `0c0a8d5` without downgrading Alembic? | **Yes**, for a restricted rollout (Playground off, new subscriptions not live). E4 already ran the old app on schema `0027`. |
| Is Railway `0c0a8d5` confirmed as a dashboard rollback target? | **Yes** — `76fbfcad` is **Active** on `recall-th-c` (PR #209 / `main`). See §4. |
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
| Previous Railway deployment retained | Operator screenshot: `recall-th-c` / `76fbfcad` **Active**, Deployment successful, PR #209 on `main` | **PASS** |
| Restore/redeploy control present | ⋯ overflow on that same deployment header; not opened, not clicked | **PASS** |
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

## 4. Railway rollback availability

**F2 finding: Yes — deployment is retained and a restore/redeploy action is available.**

Operator screenshot (2026-10-17, Mac, read-only). Redeploy / Rollback /
Restart / Remove were **not** clicked. Variables stayed collapsed (38).

| Field | Observed |
|---|---|
| Service | `recall-th-c` |
| Hostname | `recall-the-c.in` |
| Railway id | `76fbfcad` |
| Badge | **Active** |
| Status | Deployment successful |
| Time | 2026-10-15 08:35 GMT+5:30 (Gate D restart) |
| Git | Merge pull request **#209** `feat/mtp-bare-act` on `main` (`sanjisworking-commits/recall_the_c`) |
| Builder | Railpack v0.41.0, `python@3.12.11` |
| Start | `/app/.venv/bin/python -m uvicorn constitution_memorizer.web.asgi:app --host 0.0.0.0 --port $PORT` |
| Actions | **⋯** overflow on this deployment header (not opened) |

Git SHA `0c0a8d5` is not printed as hex in the screenshot. Merge PR #209
on `main` **is** `0c0a8d555748cb5fa63a5fbe0a43998ee5c1d942`.

The ⋯ control is Railway’s documented home for **Redeploy** and, once a
newer deploy removes this one, **Rollback**. It was not opened, so the
item labels were not photographed. That does not change the finding:
this specific build is retained, currently Active, and the restore/
redeploy menu exists on it.

Qualifications that stay in force:

- While `76fbfcad` is **Active**, it is the live app, not a historical
  rollback *from* HEAD. After a later PR #188 deploy, this same row is
  the rollback target.
- **Rollback** (no rebuild) is only listed while the image is inside the
  plan retention window after the deployment is removed. **Redeploy**
  rebuilds this deployment’s original source (PR #209 / `0c0a8d5`) if
  Rollback is hidden.
- After merge, `main` will no longer be `0c0a8d5`. Application rollback
  then depends on keeping this Railway deployment (or an explicit deploy
  of SHA `0c0a8d5`). Do not Remove `76fbfcad`.

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
| Railway Deployments UI | **PASS** — operator screenshot of Active `76fbfcad` / PR #209 / ⋯ |
| Railway writes, Redeploy, Rollback | **Not authorized — not done** |
| Alembic / restore-into-live / post-E3 dump | **Not authorized — not done** |
| Merge PR #188 | **Not authorized — not done** |

---

## 7. Gate F (merge)

**Not authorized.** Railway deploy-history for `0c0a8d5` / `76fbfcad` is
closed as **Yes**. F2 remains a **partial** pass until a separately
authorized post-E3 backup plus disposable restore rehearsal closes the
recovery gap — or an explicit residual-risk acceptance is recorded.

Current live state is already the application rollback target: old app,
kill switch on, schema reported at 0027. That is E-before-F, not a
Playground Stage 2 cutover.
