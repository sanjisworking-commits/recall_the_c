#!/bin/zsh
# REVISION=e3_prep_v3_1_20261015
# Isolated read-only diagnostic: why URL startup options did not set timeouts.
# Session SET/SHOW only. No dumps, Alembic, GRANT, Railway, or merge.
#
#   zsh gate_e3_timeout_diag.zsh
# Paste only E3_DIAG_* lines.
#
# Production observation this explains:
#   E3_LOCK_TIMEOUT=0  E3_STATEMENT_TIMEOUT=2min  E3_IDLE_IN_TX_TIMEOUT=0
# statement_timeout=2min is the hosted default, not proof that our 120s applied.

set -euo pipefail
unsetopt xtrace verbose 2>/dev/null || true
if [[ -o xtrace ]] || [[ -o verbose ]]; then
  print -u2 "E3_DIAG_RESULT=FAIL"
  print -u2 "E3_DIAG_REASON=xtrace_or_verbose_enabled"
  exit 1
fi
umask 077
unset DATABASE_URL POSTGRES_URL SUPABASE_DB_URL DIRECT_URL PGSERVICE PGPASSWORD

abort() { print -u2 "E3_DIAG_RESULT=FAIL"; print -u2 "E3_DIAG_REASON=$1"; exit 1; }

HERE="${0:A:h}"
GUARDS="$HERE/pr188_gate_e3_guards.py"
[[ -f "$GUARDS" ]] || abort "e3_guards_module_missing"
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"

DSN_FILE="$HOME/.recall_direct_dsn"
[[ -f "$DSN_FILE" ]] || abort "dsn_file_missing"
[[ "$(stat -f '%Lp' "$DSN_FILE")" == "600" ]] || abort "dsn_file_mode_not_600"
# shellcheck disable=SC1090
source "$DSN_FILE"
export DIRECT_DATABASE_URL EXPECTED_SUPABASE_REF EXPECTED_DB_NAME
[[ -n "${DIRECT_DATABASE_URL:-}" && -n "${EXPECTED_SUPABASE_REF:-}" && -n "${EXPECTED_DB_NAME:-}" ]] || abort "dsn_vars_absent"
export PGPASSFILE="${PGPASSFILE:-$HOME/.recall_pgpass}"
[[ -f "$PGPASSFILE" ]] || abort "pgpass_file_missing"
[[ "$(stat -f '%Lp' "$PGPASSFILE")" == "600" ]] || abort "pgpass_mode_not_600"
command -v python3 >/dev/null 2>&1 || abort "python3_missing"
command -v psql >/dev/null 2>&1 || abort "psql_missing"

print "E3_DIAG_NO_ALEMBIC=yes"
print "E3_DIAG_NO_GLOBAL_ALTER=yes"
print "E3_DIAG_WRITES_TABLES=no"

python3 - <<'PY'
import os, subprocess, sys
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit
import pr188_gate_e3_guards as guards

def fail(r):
    print("E3_DIAG_RESULT=FAIL")
    print(f"E3_DIAG_REASON={r}")
    sys.exit(1)

def show_sql():
    return r"""
SELECT current_setting('lock_timeout') || '|' ||
       current_setting('statement_timeout') || '|' ||
       current_setting('idle_in_transaction_session_timeout') || '|' ||
       inet_server_port()::text || '|' ||
       current_setting('transaction_read_only');
"""

def run_psql(url, sql):
    env = os.environ.copy()
    env.pop("PGPASSWORD", None)
    env["PGPASSFILE"] = os.environ["PGPASSFILE"]
    env["PGCONNECT_TIMEOUT"] = "15"
    cmd = [
        "psql", "-X", "-w", "-q", "-v", "ON_ERROR_STOP=1",
        "--pset", "pager=off", "--pset", "footer=off", "--pset", "tuples_only=on",
        url,
    ]
    proc = subprocess.run(cmd, input=sql, env=env, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        fail("psql_noninteractive_failed")
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if len(lines) != 1:
        fail("unexpected_row_count")
    parts = lines[0].split("|")
    if len(parts) != 5:
        fail("diag_row_unparseable")
    return parts

raw = os.environ["DIRECT_DATABASE_URL"]
p = urlsplit(raw)
if p.password is not None:
    fail("password_bearing_url_forbidden")
if p.port == 6543 or p.port != 5432:
    fail("port_not_5432")
if "6543" in raw:
    fail("dsn_contains_6543")

# Phase A: no options in URL.
a_lock, a_stmt, a_idle, a_port, a_ro = run_psql(
    raw,
    "BEGIN READ ONLY;\n" + show_sql() + "COMMIT;\n",
)
print(f"E3_DIAG_A_LOCK={a_lock}")
print(f"E3_DIAG_A_STATEMENT={a_stmt}")
print(f"E3_DIAG_A_IDLE={a_idle}")
print(f"E3_DIAG_A_PORT={a_port}")
print(f"E3_DIAG_A_TX_READ_ONLY={a_ro}")
print("E3_DIAG_A_STARTUP=" + guards.classify_startup_options(a_lock, a_stmt, a_idle))

# Phase B: libpq options= query parameter (the v2 method).
u = urlsplit(raw)
q = dict(parse_qsl(u.query, keep_blank_values=True))
q["options"] = "-c lock_timeout=15s -c statement_timeout=120s -c idle_in_transaction_session_timeout=60s"
opt_url = urlunsplit((u.scheme, u.netloc, u.path, urlencode(q), u.fragment))
b_lock, b_stmt, b_idle, b_port, b_ro = run_psql(
    opt_url,
    "BEGIN READ ONLY;\n" + show_sql() + "COMMIT;\n",
)
print(f"E3_DIAG_B_LOCK={b_lock}")
print(f"E3_DIAG_B_STATEMENT={b_stmt}")
print(f"E3_DIAG_B_IDLE={b_idle}")
print("E3_DIAG_B_STARTUP=" + guards.classify_startup_options(b_lock, b_stmt, b_idle))
print("E3_DIAG_B_MATCHES_A=" + ("yes" if (b_lock, b_stmt, b_idle) == (a_lock, a_stmt, a_idle) else "no"))

# Phase C: session SET then SHOW (no ALTER DATABASE).
c_lock, c_stmt, c_idle, c_port, c_ro = run_psql(
    raw,
    """
SET lock_timeout = '15s';
SET statement_timeout = '120s';
SET idle_in_transaction_session_timeout = '60s';
BEGIN READ ONLY;
SELECT current_setting('lock_timeout') || '|' ||
       current_setting('statement_timeout') || '|' ||
       current_setting('idle_in_transaction_session_timeout') || '|' ||
       inet_server_port()::text || '|' ||
       current_setting('transaction_read_only');
COMMIT;
""",
)
print(f"E3_DIAG_C_LOCK={c_lock}")
print(f"E3_DIAG_C_STATEMENT={c_stmt}")
print(f"E3_DIAG_C_IDLE={c_idle}")
print(f"E3_DIAG_C_PORT={c_port}")
print(f"E3_DIAG_C_TX_READ_ONLY={c_ro}")
reason = guards.check_timeouts(c_lock, c_stmt, c_idle)
if reason:
    fail("session_set_" + reason)
print("E3_DIAG_C_SET_APPLIED=yes")

b_ok = guards.check_timeouts(b_lock, b_stmt, b_idle) is None
if (not b_ok) and reason is None:
    print("E3_DIAG_CONCLUSION=startup_options_not_honored_use_session_set")
elif b_ok:
    print("E3_DIAG_CONCLUSION=startup_options_applied_but_v3_still_uses_session_set")
else:
    print("E3_DIAG_CONCLUSION=session_set_required")
print("E3_DIAG_RESULT=PASS")
print("E3_DIAG_DOES_NOT_AUTHORIZE_E3=yes")
PY
