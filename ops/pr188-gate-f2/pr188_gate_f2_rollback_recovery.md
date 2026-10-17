# PR #188 Gate F2 — Rollback and recovery review (rev e, 2026-10-17)

**GATE F2: PARTIAL PASS.** Review only. Recovery not certified.
(rev f: ⋯ menu on Active `76fbfcad` lists Restart, Redeploy, Remove.)

PR #188 stays **draft**. E3 and E4 remain closed. F1 is compatible with a
restricted, Playground-disabled rollout. F2 is **not fully closed**.

No Railway changes, deployment actions, database migrations,
restorations, or PR merges are authorized.

---

## Recorded Railway finding

“Yes — deployment is retained and a restore/redeploy action is available.”

| Check | Finding |
|---|---|
| Railway service | `trustworthy-embrace` / `env` / `recall-th-c` |
| Deployment ID | `76fbfcad` |
| Deployment state | Active — successful |
| Git commit | `0c0a8d5` (Merge PR #209) |
| Production hostname | `recall-the-c.in` |
| Startup | Uvicorn only; no automatic Alembic |
| Deployment overflow control | Opened read-only; items listed below |

**⋯ menu on Active `76fbfcad` (observed, not clicked):**

| Item | Present |
|---|---|
| Restart | Yes |
| Redeploy | Yes |
| Remove | Yes (red; **do not click**) |
| Rollback | **No** — expected while this deployment is Active |

**Redeploy** of this specific build is independently verified.
**Rollback** is not listed on the live row. Railway only offers Rollback
on a *previous* deployment after a newer one replaces it, and only while
the image is inside the plan retention window. After a later PR #188
deploy, re-check this same `76fbfcad` row for a Rollback item without
clicking it.

---

## Updated F2 status

| Requirement | Status |
|---|---|
| Historical deployment retained | **PASS** |
| Application rollback compatibility with schema `0027` | **PASS** |
| Specific rollback/redeploy menu action | **Redeploy observed** on Active `76fbfcad`. **Rollback not listed** (expected while Active) |
| Post-E3 encrypted backup | **Pending** |
| Disposable restore rehearsal | **Pending** |
| Full database recovery certification | **Not established** |

Application rollback to `0c0a8d5` without an Alembic downgrade remains
viable for a **restricted** rollout (Playground off, new subscriptions
not live). E4 already ran the old app on schema `0027`. `0c0a8d5` has no
Razorpay subscription webhook; rollback after live billing is not this
path.

---

## 1. Application rollback (PASS, restricted)

- `0c0a8d5` never names the fifteen 0017–0027 tables.
- Extra empty relations are invisible to the old app.
- `railpack.json` / live start command is uvicorn only (screenshot:
  `/app/.venv/bin/python -m uvicorn constitution_memorizer.web.asgi:app
  --host 0.0.0.0 --port $PORT`).
- Alembic **downgrade** from HEAD would `DROP` those tables — forbidden.
- Keep `PLAYGROUND_ENABLED=false`. Do not unset it.

If a later HEAD deploy fails, a **separately authorized** rollback
targets `76fbfcad` / `0c0a8d5` on `recall-th-c` only, leaves Alembic at
`20260927_0027`, then rechecks `/health`, Google sign-in, Browse/Learn,
and `/playground` FastAPI JSON 404.

---

## 2. Database recovery (not certified)

The verified encrypted backup **`20261016T072148Z`** was taken **before
E3**. It is a 0016-era recovery point. It does not contain revision
`0027` or the fifteen new tables.

Gate B Attempt 3 remains the verified **procedure** for a public-schema
restore onto a disposable local database. That is not a restore of the
post-E3 schema, not a live restore, and not Auth/Storage/Vault.

A live restore of a 0016-era dump would discard writes after dump time
**and** drop 0027 objects. That is disaster-only, not F rollback.

---

## 3. Recommended next gate — F3 (not authorized)

**F3 — Post-E3 backup and disposable recovery rehearsal**, subject to
**separate authorization**.

Goal, when later authorized:

1. Capture the production database at Alembic `20260927_0027`.
2. Independently verify an encrypted off-device copy.
3. Restore into an **isolated** database (new local DB; not
   `recall_restore_drill3`, not `recall_mig_rehearsal`, not live
   Supabase).

F3 must **not** modify live production, change Railway, click Restart /
Redeploy / Remove, run Alembic, or merge PR #188.

This document does **not** authorize F3, dumps, `age` encrypt, or any
restore.

---

## 4. Frozen identities

| Item | Value |
|---|---|
| PR #188 | OPEN, **draft**, unmerged |
| PR head | `5d89fbdfb6c712a998ce1fdbc4a7756fee8677b8` |
| `main` / rollback SHA | `0c0a8d555748cb5fa63a5fbe0a43998ee5c1d942` |
| Live Railway | `trustworthy-embrace` / `env` / `recall-th-c` / `76fbfcad` **Active** |
| Kill switch | `PLAYGROUND_ENABLED=false` |
| Operator schema | `20260927_0027` |
| Pre-E3 backup | `20261016T072148Z` (0016-era) |

---

## 5. Gate F (merge)

**Not authorized.** Until F3 (or an explicit residual-risk acceptance)
closes recovery, F2 stays a partial pass and PR #188 stays draft.
