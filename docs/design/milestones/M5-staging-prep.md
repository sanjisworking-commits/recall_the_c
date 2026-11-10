# M5 — pre-merge staging deployment preparation (2026-11-10) · NOT DEPLOYED

Owner instruction (2026-11-10): verify the staging target read-only, complete A5 and preserve personal material, check migration compatibility, then deploy the tested candidate with `PLAYGROUND_TIER_MODEL=monthly` only if those prerequisites pass; if container access or preservation is blocked, stop before deployment and report the exact blocker. No merge, no production change, no entitlement activation.

**Outcome: stopped before deployment.** Two prerequisites are blocked (§3, §4). Nothing was deployed, migrated, reset or written anywhere; the existing staging deployment is untouched.

## 1. Candidate and CI

| Item | Value |
|---|---|
| Candidate | PR #240, branch `pg-m5-account`, head `8ccddc2` = the last reviewed SHA (the only commits after the source commit `d2d6436` are tests `8aa3f0f`, `7d75338`, `6a807a0` and the evidence commit `8ccddc2`; the working tree held only uncommitted documentation and the dark halted captures, committed after this record). The deployment SHA would be `8ccddc2`. |
| CI | `workflow_dispatch` on `pg-m5-account`, run 42765509117 on `8ccddc2` — https://github.com/sanjisworking-commits/recall_the_c/actions/runs/42765509117 — pytest **executed** (`Decision: run=true (workflow_dispatch)`). Result: **PENDING** — in progress at the time of this commit; recorded by the follow-up commit once it completes. |
| Local full suite | 0 failed / 4161 passed / 176 skipped on `6a807a0` (`M5-evidence.md` §2), recorded separately from CI. |

## 2. Staging target — verified read-only

| Item | Value |
|---|---|
| Project / environment / service | `recallc-playground-staging` (`a5dd01ad-aa1f-47a8-9c16-c9e6934999ed`) / `production` (`2943667e-f8e2-4967-b59b-489ad6543d78`) / `recall_the_c` (`31703c31-3003-4ccc-9ac0-6a184919c980`) — confirmed by `railway variables` (`RAILWAY_PROJECT_NAME`, `RAILWAY_ENVIRONMENT_NAME`, `RAILWAY_SERVICE_NAME` and the three ids). |
| Configuration (non-secret) | `APP_ENV=staging`, `MULTIUSER_ENABLED=true`, `PLAYGROUND_ENABLED=true`, `ARTICLE_ENTITLEMENTS_ENABLED=false`, `PRICING_ENABLED=false`, `ADMIN_ENABLED=false`, `AUTH_GOOGLE_ENABLED=true`, `AUTH_PHONE_ENABLED=false`, `COOKIE_SECURE=true`; **`PLAYGROUND_TIER_MODEL` is not set** (the application default `monthly` applies). Secret-bearing variables present by name only: `APP_BASE_URL`, `PLAYGROUND_DEVICE_HMAC_SECRET`, `SESSION_SECRET`, `SUPABASE_ANON_KEY`, `SUPABASE_URL`, `RAILWAY_SERVICE_RECALL_THE_C_URL`, `RAILWAY_STATIC_URL`. No value was printed or copied. |
| Database reference | `DATABASE_URL` host `aws-0-ap-northeast-1.pooler.supabase.com`, port 5432, database `postgres`, tenant `postgres.tvygwasuqvtnzjyjtqrq` (the isolated staging Supabase project recorded on 2026-10-18 and 2026-10-28). |
| Existing deployment (recovery record) | `dd04a5a2-9451-48b6-a391-ec5ab02835da`, `SUCCESS`, created 2026-10-25 14:34 UTC, commit `3719b9f0d3ec`, branch `pg-m2-act-head` (the M2 staging deployment); earlier deployments `0eb35808` (`e2ac903a`, pg-m2-act-head) and `b6ad47b0` (`3b37f894`, pg-m1-guest-shell) are `REMOVED`. Public domain `recallthec-production.up.railway.app`. No volume attached (`RAILWAY_VOLUME_*` unset; Check 2 of 2026-10-28). |
| Live migration version | **could not be read** — see §3. Last read value: `20260927_0027` (2026-10-28, §4.9 of the tier-revision plan). |

## 3. BLOCKER A — database availability: BLOCKED (unavailable; cause not established)

- A read-only connection (`default_transaction_read_only=on`, 30 s statement timeout) to the staging `DATABASE_URL` failed at the pooler with `FATAL: (ENOTFOUND) tenant/user postgres.tvygwasuqvtnzjyjtqrq not found` on all three pooler addresses.
- The project's public hostname `tvygwasuqvtnzjyjtqrq.supabase.co` **does not resolve** (`Could not resolve host`); the pooler hostname itself resolves normally.
- The **currently deployed staging app (`3719b9f`) is already failing**: its retained logs (305 lines) consist of the same `tenant/user … not found` connection errors from `pool-1`; `GET /login` answers 200 (no database needed) but `GET /browse` times out after 30 s. The earliest retained log line is a `/login` request, so the start of the outage is not in the retained window.
- Exact errors, verbatim: pooler — `FATAL:  (ENOTFOUND) tenant/user postgres.tvygwasuqvtnzjyjtqrq not found` (each of the three pooler addresses 52.68.3.1, 35.79.125.133, 54.64.190.72); hostname — `curl: Could not resolve host: tvygwasuqvtnzjyjtqrq.supabase.co`; `dig +short` returned no record.
- **These errors establish unavailability only.** They do not establish that the project was deleted: a paused project, a removed pooler tenant, a changed project ref or a misconfigured `DATABASE_URL` would each present this way from outside. No Supabase CLI is installed here and no Supabase credential is held by this session, so the project's actual status must be read from the Supabase dashboard (owner) before concluding paused, deleted or misconfigured. Nothing is to be recreated, reset or re-pointed on the strength of this record.
- Consequence: the live `alembic_version`, the preservation baseline (4 accounts, 3 helper subscriptions, 5 roster periods, roster items, progress, devices as counted on 2026-10-28) and any post-deploy check are **BLOCKED**. Deploying would replace a container that currently cannot reach its database with another that cannot either.

## 4. BLOCKER B — material preservation: BLOCKED (A5 container access)

- `railway ssh keys list` → "No SSH keys registered with Railway."; the local agent has no identities and `~/.ssh` holds only the agent socket directory. `railway ssh` therefore cannot connect — the same `BLOCKED(no_ssh_key)` as on 2026-10-28.
- Registering an SSH key with the Railway account is an account security change not covered by this instruction, so it was not done. No volume was attached (per instruction), no container was read, and no personal-material archive or attachment file was located, copied or verified.
- Consequence: preservation of container-local personal material (study-material archives and attachments, 5-9b) is **BLOCKED**. **No container replacement, restart or volume attachment** until A5 and any backup it calls for are complete (owner, 2026-11-10); a restart or a volume attach would replace the container as surely as a deploy.

## 5. Schema compatibility — code inspection PASS; live version and runtime compatibility BLOCKED / unverified

- Deploy mechanics: `railpack.json` `deploy.startCommand` is `python -m uvicorn constitution_memorizer.web.asgi:app …`; there is no pre-deploy command, and no application start-up path runs Alembic (`multiuser/migrate.py` only replays migration 0001's SQL when invoked by hand). Migrations are manual.
- Candidate schema head: `20261103_0028_playground_choice` (B1's permanent-choice ledger `user_playground_choice`), one migration beyond staging's last read version `20260927_0027`. The migration is additive (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, RLS enabled, no data derivation) and its downgrade is deliberately refused.
- Under `monthly` the candidate never reads or writes that table: `EntitlementService` applies the ledger overlay (and its `count_choices`) only when `is_choice_model(self._tier_model)` (`entitlements/service.py:131`), and the roster service's `choice_law_ids`, `is_choice_law` and `_ledger_account` return empty / False unless `choices_model` (`playground/roster/service.py:75-118, 295`). Every other table the candidate uses was present at `0027` on 2026-10-28.
- Verdict from code inspection: with `PLAYGROUND_TIER_MODEL=monthly` the candidate avoids the `0028` ledger entirely, so **no live migration is implied by the deploy**; `0028` would be presented separately, with its preservation checks and recovery procedure, before any switch to `choices`.
- **Live migration version and runtime compatibility remain BLOCKED / unverified** while the database is unreachable: the `0027` value is the 2026-10-28 reading, not a current one, and no request has been exercised by the candidate against the live schema.

## 6. Deployment — NOT DONE
Prerequisites: CI (§1, pending result at the time of writing), target verification (§2 PASS for identity and configuration; migration version BLOCKED), preservation (§3 and §4 BLOCKED), schema compatibility (§5 PASS). Two prerequisites failed, so the exact tested SHA was **not** deployed; `PLAYGROUND_TIER_MODEL` stays unset / `monthly`; no grant, purchase or billing change.

## 7. Hosted acceptance — NOT RUN (blocked by §3)
Google sign-in and return links; Profile / Settings tier labels and save persistence; Settings CSRF rejection without mutation; device isolation and removal with designated test devices; plans selection and create / change routing without a purchase; one shared-navigation and Schedule smoke check — all **NOT RUN**. Local evidence for each stands in `M5-evidence.md` (§3 gates, §4 matrix). Real checkout completion stays NOT RUN by instruction.

## 8. Next operational steps (owner, 2026-11-10)
1. **Establish the staging Supabase project's actual status** from its dashboard (paused / deleted / misconfigured) — the record above does not decide it. No database is recreated, no data reset, no grant changed and nothing deployed around the blocker.
2. **Restore container access for A5** (an SSH key for the Railway account is an account change the owner makes) so `data/progress/study-materials` on the current container can be inventoried and archived read-only; until then no replacement, restart or volume attachment.
3. Only then: re-run the read-only checks (identity, live `alembic_version`, baseline counts), confirm CI on the chosen SHA, deploy `8ccddc2` with `monthly`, and run the §7 checks.
4. M6 planning continues meanwhile; it does not require a deployment.

## 9. Merge blockers recorded
Stack order unresolved (B1 #230 → M1-R #232 → M2-R #235 → M3 #237 → M4 #238 → M5 #240, with PR #236 and #234 against `main`); hosted acceptance of M3–M5 NOT RUN; the PR #238 browser-profile history decision; the `0028` migration to be applied by hand before any `choices` activation; the open points carried in `M5-evidence.md` §7.
