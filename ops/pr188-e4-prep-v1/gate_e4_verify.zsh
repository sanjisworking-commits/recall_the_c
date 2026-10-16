#!/bin/zsh
# REVISION=e4_prep_v1_20261016
# FINGERPRINT=e4_verify_readonly_at_0027
# PR #188 Gate E4-verify — post-E3 read-only schema/privilege/HTTP check.
# Requires alembic 20260927_0027. Production is still 20260828_0016, so this
# script MUST FAIL today with e3_not_run_alembic_still_0016.
# Does NOT run Alembic, GRANT, Railway writes, or merge.
#
# Do not run until E3 has been separately authorized, executed, and recorded
# as 0027. For today's 0016 production state use gate_e4_now.zsh instead.
#
#   chmod 700 gate_e4_verify.zsh
#   export GATE_E4_VERIFY_CONFIRM='I_AUTHORIZE_E4_POST_E3_READONLY_AT_0027'
#   export E4_RAILWAY_CONFIRM='trustworthy-embrace/env/recall-th-c/0c0a8d5/PLAYGROUND_ENABLED=false'
#   zsh ./gate_e4_verify.zsh
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

CONFIRM_EXPECT="I_AUTHORIZE_E4_POST_E3_READONLY_AT_0027"
[[ "${GATE_E4_VERIFY_CONFIRM:-}" == "$CONFIRM_EXPECT" ]] || abort "missing_or_wrong_e4_verify_confirm"
print "E4_VERIFY_CONFIRM=accepted"

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

print "E4_SCRIPT=gate_e4_verify"
print "E4_PREP_ONLY=no_writes"
print "E4_REQUIRES_ALEMBIC=20260927_0027"
exec python3 "$RUNNER" verify
