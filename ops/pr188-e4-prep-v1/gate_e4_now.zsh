#!/bin/zsh
# REVISION=e4_prep_v1_20261016
# FINGERPRINT=e4_now_readonly_at_0016
# PR #188 Gate E4-now — read-only production check WHILE Alembic is still 0016.
# REVIEW ONLY until ChatGPT verifies this script. Then Grok Bot may run it
# on Sanjali's Mac. Does NOT run Alembic, GRANT, Railway writes, or merge.
#
# Full post-E3 E4 (schema/RLS on 15 new tables) CANNOT pass today: production
# is still 20260828_0016. That verifier is gate_e4_verify.zsh and fail-closes
# with e3_not_run_alembic_still_0016.
#
# After approval:
#   chmod 700 gate_e4_now.zsh
#   export GATE_E4_NOW_CONFIRM='I_AUTHORIZE_E4_NOW_READONLY_AT_0016'
#   export E4_RAILWAY_CONFIRM='trustworthy-embrace/env/recall-th-c/0c0a8d5/PLAYGROUND_ENABLED=false'
#   zsh ./gate_e4_now.zsh
# Paste only E4_* lines.

set -euo pipefail
unsetopt xtrace verbose 2>/dev/null || true
if [[ -o xtrace ]] || [[ -o verbose ]]; then
  print -u2 "E4_RESULT=FAIL"
  print -u2 "E4_REASON=xtrace_or_verbose_enabled"
  exit 1
fi
umask 077
unset DATABASE_URL POSTGRES_URL SUPABASE_DB_URL DIRECT_URL PGSERVICE PGPASSWORD

abort() { print -u2 "E4_RESULT=FAIL"; print -u2 "E4_REASON=$1"; exit 1; }

HERE="${0:A:h}"
RUNNER="$HERE/pr188_gate_e4.py"
GUARDS="$HERE/pr188_gate_e4_guards.py"
[[ -f "$RUNNER" && -f "$GUARDS" ]] || abort "e4_runner_or_guards_missing"
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"

CONFIRM_EXPECT="I_AUTHORIZE_E4_NOW_READONLY_AT_0016"
[[ "${GATE_E4_NOW_CONFIRM:-}" == "$CONFIRM_EXPECT" ]] || abort "missing_or_wrong_e4_now_confirm"
print "E4_NOW_CONFIRM=accepted"

RAILWAY_EXPECT="trustworthy-embrace/env/recall-th-c/0c0a8d5/PLAYGROUND_ENABLED=false"
[[ "${E4_RAILWAY_CONFIRM:-}" == "$RAILWAY_EXPECT" ]] || abort "railway_operator_confirm_missing"
print "E4_RAILWAY_CONFIRM_MATCH=yes"

case "${HERE}" in
  /workspace|/workspace/*) abort "cloud_workspace_forbidden_use_mac" ;;
esac

command -v python3 >/dev/null 2>&1 || abort "python3_missing"
command -v psql >/dev/null 2>&1 || abort "psql_missing"

DSN_FILE="$HOME/.recall_direct_dsn"
[[ -f "$DSN_FILE" ]] || abort "dsn_file_missing"
# shellcheck disable=SC1090
source "$DSN_FILE"
export DIRECT_DATABASE_URL EXPECTED_SUPABASE_REF EXPECTED_DB_NAME RAILWAY_APP_ROLE
export PGPASSFILE="${PGPASSFILE:-$HOME/.recall_pgpass}"
export E4_HTTP_BASE="${E4_HTTP_BASE:-https://recall-the-c.in}"

print "E4_SCRIPT=gate_e4_now"
print "E4_PREP_ONLY=no_writes"
exec python3 "$RUNNER" now
