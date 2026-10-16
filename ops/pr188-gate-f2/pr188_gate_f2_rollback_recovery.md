# PR #188 Gate F2 — Rollback and recovery review (2026-10-16)

**GATE F2: PASS WITH QUALIFICATIONS.** Review only.

This document answers two questions that must be settled before anyone
considers merging PR #188. It does **not** authorize that merge, a
Railway change, a deployment, Alembic, or any restore.

| Question | Answer |
|---|---|
| Can the running application be reverted to `0c0a8d5` **without** downgrading the database? | **Yes.** Extra 0017–0027 relations are invisible to `0c0a8d5`. |
| Does the production backup have a sufficiently tested recovery path? | **Procedure yes; live/full/0027-era restore no.** Gate B Attempt 3 is the tested *procedure*. The E2 archive is integrity-verified, not restore-executed. |

F1 remains in force: `PLAYGROUND_ENABLED=false` is confirmed in Railway
production. New subscription and device secrets are not configured. F2
does **not** certify Plus/Pro/Max subscriptions, device enforcement, or
payment processing.

---

## Authorization (this review)

| Action | Status |
|---|---|
| Read-only git of `origin/main` (`0c0a8d5`) and PR #188 head (`5d89fbd`) | Done here |
| Read-only HTTP `GET` of `https://recall-the-c.in` | Done here |
| Closed Gate B / P / E2 backup record | Cited, not re-run |
| Railway writes / dashboard edits | **Not authorized — not done** |
| Deployments | **Not authorized — not done** |
| Alembic upgrade / downgrade / stamp | **Not authorized — not done** |
| Restore into live, drill3, or rehearsal DB | **Not authorized — not done** |
| Merge PR #188 / mark ready | **Not authorized — not done** |

---

## Frozen identities (this review)

| Item | Value |
|---|---|
| PR #188 | https://github.com/sanjisworking-commits/recall_the_c/pull/188 — OPEN, **draft**, unmerged |
| PR head | `5d89fbdfb6c712a998ce1fdbc4a7756fee8677b8` |
| `main` / rollback SHA | `0c0a8d555748cb5fa63a5fbe0a43998ee5c1d942` |
| Live Railway (last recorded) | `trustworthy-embrace` / `env` / `recall-th-c` |
| Kill switch | `PLAYGROUND_ENABLED=false` (F1 confirmed; not re-edited) |
| Operator-reported schema | Alembic `20260927_0027` (E3/E4 operator record; this agent did not run Alembic) |
| Live **app** | still `0c0a8d5` (HTTP below) |
| E2 archive | `recall_prod_gate_e2_20261015T063833Z.tar.age` |
| E2 SHA-256 | `6ff82b61c3dc89f910d78781b597731cc0e7200fce6c2f46b66376ec9c6faf4c` |
| E2 dump revision | `20260828_0016` |
| Gate B dump SHA-256 | `2026e09e9acba2e9b8d6b411c5952f1b4387c80831c58f8882c958180d782cdd` |

Fifteen 0017–0027 application tables (operator E4: present, empty, RLS on):

`user_playground_item`, `user_playground_selection`, `user_playground_progress`,
`user_subscription`, `subscription_webhook_event`, `subscription_charge`,
`user_device`, `user_device_session`, `user_device_replacement`,
`user_playground_period`, `user_playground_roster_item`,
`user_playground_mode_progress`, `user_playground_revision_mode_progress`,
`user_playground_source_change`, `user_playground_source_scan`.

---

## F2-A — Revert the application to `0c0a8d5` without a database downgrade

**Verdict: PASS.**

The intended rollback after a bad HEAD deploy is: redeploy the `0c0a8d5`
image on `env` / `recall-th-c`, **keep** schema `20260927_0027`, **keep**
`PLAYGROUND_ENABLED=false`. No `alembic downgrade`. No dump-restore.

### 1. `0c0a8d5` never names the new relations

`git grep -w` of each of the fifteen table names at
`origin/main` = `0c0a8d5` returned **0 files** for every name.

`0c0a8d5` Alembic files stop at `20260828_0016`. There is no 0017–0027
revision on `main`, so that checkout cannot issue those `DROP TABLE`
statements even if someone ran Alembic from it.

The only `playground` hits on `0c0a8d5` are:

| Path | What it is |
|---|---|
| `src/constitution_memorizer/web/seo.py` | `/playground` in `NOINDEX_PATH_PREFIXES` (robots/meta helper; not a route, not SQL) |
| `data/output/learning_units.json` (and `.min.json`) | Twelfth Schedule corpus text: “parks, gardens, playgrounds” |

There is **no** FastAPI `/playground` router on `0c0a8d5`. Live HTTP matches
that: FastAPI JSON 404, not HEAD’s styled unavailable page.

### 2. Extra empty tables are invisible to the old app

PostgreSQL does not error because unused relations exist. `0c0a8d5` has
no `information_schema` / `pg_tables` walk that would notice them. The
old app’s queries stay on the 0016-era tables (`user_profile`,
`learning_unit_progress`, `app_session`, …).

This is the E-before-F design: schema may be ahead of the running image.

### 3. Deploy start does not run Alembic

`railpack.json` `startCommand` is **identical** on `0c0a8d5` and `5d89fbd`:

```
python -m uvicorn constitution_memorizer.web.asgi:app --host 0.0.0.0 --port $PORT
```

Redeploying `0c0a8d5` starts uvicorn only. It will not stamp, upgrade, or
downgrade. Merge of HEAD also will not migrate; that is why E3 had to
land 0027 first.

### 4. Alembic **downgrade** from HEAD **would** DROP the new tables

Each 0017–0027 revision’s `downgrade()` executes a `DOWNGRADE` SQL
constant. Those statements **drop** (or shrink) the new objects:

| Revision | Downgrade does |
|---|---|
| `20260927_0027` | `DROP TABLE` `user_playground_source_scan`, `user_playground_source_change` |
| `20260925_0026` | `DROP TABLE` `user_playground_revision_mode_progress`; `DROP COLUMN` `learned_at` |
| `20260924_0025` | `DROP TABLE` `user_playground_mode_progress` |
| `20260917_0024` | `DROP TABLE` `user_playground_roster_item`, `user_playground_period` |
| `20260917_0023` | `DROP TABLE` `user_device_replacement` |
| `20260917_0022` | shrinks `user_device_platform_check` (drops `ios`) |
| `20260916_0021` | `DROP TABLE` `user_device_session`, `user_device` |
| `20260916_0020` | `DROP TABLE` `subscription_charge` |
| `20260915_0019` | `DROP TABLE` `subscription_webhook_event` |
| `20260911_0018` | `DROP TABLE` `user_subscription` |
| `20260906_0017` | `DROP TABLE` `user_playground_progress`, `user_playground_selection`, `user_playground_item` |

`alembic/env.py` on HEAD still wraps migrations in **one**
`begin_transaction()` with `NullPool`. A downgrade from 0027 toward 0016
is a single destructive transaction. **Forbidden** as F rollback.

Also forbidden: `alembic stamp`, `UPDATE alembic_version`.

### 5. Live HTTP still shows the old app (rollback target already running)

Independent `GET` on 2026-10-16T08:22:26Z:

| Path | Result | Meaning |
|---|---|---|
| `GET /health` | 200 `{"status":"ok"}` | Site up |
| `GET /playground` | 404 `{"detail":"Not Found"}` `content-type: application/json` | **Old app.** HEAD with `PLAYGROUND_ENABLED=false` would return a **styled** unavailable page via `playground_error_response(..., unavailable=True)` |
| `GET /` | 200, title `Recall the C — Learn the Constitution of India` | Old landing |

Until PR #188 is merged and `recall-th-c` actually deploys `5d89fbd`,
application rollback is a no-op: production is already `0c0a8d5`.

After a future HEAD deploy, the same SHA is still on `main` (this review:
`origin/main` is still `0c0a8d5`). Rollback is a Railway **redeploy of
that existing commit**, not a git revert of `main` and not a database
downgrade.

### 6. Keep the kill switch

HEAD defaults `PLAYGROUND_ENABLED` to **True**
(`src/constitution_memorizer/multiuser/settings.py`). Unsetting the
variable after HEAD is live would turn Playground **on**. Rollback of a
bad HEAD deploy must **leave** `PLAYGROUND_ENABLED=false`.

F2 does not change that variable.

---

## F2-B — Production backup recovery path

**Verdict: PASS WITH QUALIFICATIONS.**

Sufficient for: (a) knowing the **procedure** that restores the
application `public` schema onto a **disposable local** database, and
(b) knowing the E2 archive is complete and byte-identical off-laptop.

**Not** sufficient for: restoring into live; restoring Auth / Storage /
Vault; treating `pg_restore --list` as a restore test of the E2 file;
recovering a 0027-era schema from the E2 dump without data loss.

### What is proven

| Proof | Scope |
|---|---|
| Gate B Attempt 3 | Local Postgres 17, new DB `recall_restore_drill3`, stub `anon` / `authenticated` / `service_role` + `auth.uid()` / `auth.role()`, then `pg_restore --exit-on-error --single-transaction --no-owner --no-acl -n public` → exit 0, `alembic_version=20260828_0016`, 25 public tables |
| Gate B dump | `~/recall_backup.dump`, SHA-256 `2026e09e9acba2e9b8d6b411c5952f1b4387c80831c58f8882c958180d782cdd`, left **unchanged** through P and E2 |
| E2 archive | `recall_prod_gate_e2_20261015T063833Z.tar.age`, SHA-256 `6ff82b61…c6faf4c`; iCloud download matched; inner public + full dump SHA-256 matched; `pg_restore --list` exit 0 on both dumps; no plaintext extract during verify |
| E2 dump content era | Production Alembic was `20260828_0016` at dump time (2026-10-15T06:38:33Z) |

Gate B Attempt 1 (full restore) failed on missing `supabase_vault`.
Attempt 2 (`-n public`) failed on missing role `authenticated` for RLS
policies that call `auth.uid()`. Attempt 3 is the verified procedure.

### What is not proven (qualifications, carried from B / P / E2)

1. **The E2 dumps themselves were not restore-executed.** `pg_restore --list`
   plus checksums prove the archive is readable and intact. They do not
   prove a restore of `20261015T063833Z` into any database.
2. **Full dump status remains** `dump_succeeded_restore_unverified`.
3. **Auth / Storage / Vault / extensions / real RLS** restore remains
   **unverified**. A public-schema-only restore does not rebuild GoTrue
   users. Constitution Learn on `0c0a8d5` can serve HTML without those
   objects; **signed-in** Learn cannot if `auth` is gone.
4. **Restoring any dump into live Supabase is disaster-only** and is
   **not** the F rollback. A restore of a dump taken at time T **discards
   every write after T** (sessions, progress, billing_orders, …).
5. **The closed E2 artifact is 0016-era.** After operator-reported E3,
   restoring E2 into live would also **remove 0027 objects** and stamp
   the database back to `20260828_0016`. That is schema downgrade by
   restore, which F2-A explicitly rejects as the application rollback.
6. **No 0027-era dump is restore-tested in this record.** If a later
   disaster must preserve 0027 tables, E2 is the wrong image. Take a
   new, separately named public dump before relying on 0027-era recovery.
   That dump is **not** authorized by this document.
7. `recall_restore_drill3` and `recall_mig_rehearsal` stay frozen. Do not
   DROP, restore into, or migrate them.

### How to use the backup (when separately authorized)

| Situation | Path |
|---|---|
| Bad HEAD **application** deploy; database healthy | **F2-A:** redeploy `0c0a8d5`. Do not touch dumps. |
| Need to **rehearse** public-schema recovery | New local DB on `127.0.0.1:5499` (not drill3), same Attempt 3 stubs, restore **a copy** of the public dump. |
| Live cluster catastrophically unusable | Separate **disaster** authorization. Expect write-loss after dump time, 0016-era schema from E2, and unverified Auth/Storage/Vault. Not Gate F. |

---

## Preferred F rollback (if HEAD is later deployed)

Still **not authorized** to execute. Written so the merge discussion has
an explicit plan:

1. Railway: redeploy git `0c0a8d5` (`Merge pull request #209` / MTP Bare Act)
   on `trustworthy-embrace` / `env` / `recall-th-c` only. Do not operate
   sibling `recall_the_c` (underscore) or historic `memorize_the_c`.
2. Leave Alembic at `20260927_0027`. Leave the fifteen new tables in place.
3. Leave `PLAYGROUND_ENABLED=false`. Do not delete or unset it.
4. Confirm live HTTP returns to FastAPI `/playground` JSON 404 and
   `/health` 200. HEAD’s styled unavailable page must disappear.
5. Do **not** run `alembic downgrade`, `alembic stamp`, or restore-into-live.

---

## What F2 does not certify

- Merge of PR #188, squash vs merge-commit, or marking the draft ready
- Plus / Pro / Max subscriptions, device enforcement, Razorpay, webhooks
- `APP_ENV=production` (deferred to D2)
- New subscription / device secrets (F1: not configured)
- Sibling Railway service `recall_the_c` (underscore) deploy status
- Post-merge Browse / Calendar / Settings against `user_subscription` /
  devices (those queries exist on HEAD, not on `0c0a8d5`)

---

## Gate F (merge) status

**Not authorized.** F2 being a qualified PASS is a **prerequisite
review**, not a merge grant.

Current live state is already the F2-A rollback target: old app, kill
switch on, schema reported at 0027. That is the intended E-before-F
order. It is not a production cutover of Playground Stage 2.
