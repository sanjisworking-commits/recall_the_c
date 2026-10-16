PR #188 Gate E4 preparation bundle — REVISION e4_prep_v1_20261016
Read-only. No Alembic, Railway variable changes, GRANT, stamp, or merge.

What E4 is
----------
E4 as designed is **post-migration verification after a successful E3**.
It expects production Alembic **20260927_0027**, 15 new public tables with 0
rows, owner/RLS/CRUD on those tables, 0016-era counts vs the E3 pre-upgrade
baseline (equal or increase only), and old-app HTTP on https://recall-the-c.in
while Railway remains git 0c0a8d5 / PLAYGROUND_ENABLED=false.

Production today
----------------
Alembic is still **20260828_0016**. E3 was deferred and has not run.
Therefore **gate_e4_verify.zsh cannot PASS** on live production. It fail-closes
with `e3_not_run_alembic_still_0016` after a read-only identity query (it does
not CREATE/ALTER/upgrade).

What can safely run now
-----------------------
**gate_e4_now.zsh** — read-only at 0016:

- DSN guard (5432, sslmode=require, no password in URL, not 6543)
- BEGIN READ ONLY identity (alembic must be 0016)
- user_profile owner / BYPASSRLS / CRUD still match E1
- nine 0016-era counts recorded to ~/.recall_gate_e4_now_baseline
- **none** of the 15 Playground/subscription/device tables present
  (presence while still 0016 = partial-migration FAIL)
- user_device_platform_check and learned_at absent
- competing sessions / hidden public locks
- HTTP: /health 200 {"status":"ok"}; / and /laws 200; /playground **404**
  (old app, not HEAD Playground UI); /learn and /calendar not 5xx

Not in the script (operator/ChatGPT after output): Google sign-in, signed-in
Constitution Learn, Railway log scan. Printed as E4_INTERACTIVE_*=not_in_script.

Reject any file that does not contain REVISION=e4_prep_v1_20261016.

Files
-----
gate_e4_now.zsh                 run this after ChatGPT verifies (0016)
gate_e4_verify.zsh              post-E3 only (expects 0027)
pr188_gate_e4.py
pr188_gate_e4_guards.py
pr188_gate_e4_offline_test.py
SHA256SUMS
README.txt
OPERATOR.md
TEST_EVIDENCE.md
