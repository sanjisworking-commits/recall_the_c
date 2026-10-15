#!/bin/zsh
# REVISION=e3_prep_v3_20261015
# FINGERPRINT=recency_final+migration_conn_set_timeouts+worktree
# PR #188 Gate E3 — production Alembic upgrade 0016 → 0027
# REVIEW ONLY. NOT AUTHORIZED TO RUN.
# Requires a later explicit execution message AND:
#   GATE_E3_UPGRADE_CONFIRM=I_AUTHORIZE_PROD_ALEMBIC_0016_TO_0027
# plus a fresh ~/.recall_gate_e3_precheck_ok from gate_e3_precheck.zsh (≤30 min).
# Requires pr188_gate_e3_guards.py in the same directory.
#
# Uses the dedicated detached worktree created by precheck. Does not switch
# the developer's checkout. Rechecks 12-hour backup recency immediately
# before alembic. Timeouts are SET+SHOW on the SAME Alembic DBAPI connection.
#
# Does not: stamp, downgrade, upgrade head, GRANT, Railway, merge, E4, retry loop.
# Wrapper invokes alembic upgrade 20260927_0027 after SET+SHOW on that connection.
#
# After a later execution authorization:
#   chmod 700 ~/Desktop/gate_e3_upgrade.zsh
#   export GATE_E3_UPGRADE_CONFIRM='I_AUTHORIZE_PROD_ALEMBIC_0016_TO_0027'
#   export E3_RAILWAY_CONFIRM='trustworthy-embrace/env/recall-th-c/0c0a8d5/PLAYGROUND_ENABLED=false'
#   zsh ~/Desktop/gate_e3_upgrade.zsh /path/to/recall_the_c
# Paste only E3_* lines.

set -euo pipefail
unsetopt xtrace verbose 2>/dev/null || true
if [[ -o xtrace ]] || [[ -o verbose ]]; then
  print -u2 "E3_RESULT=FAIL"
  print -u2 "E3_REASON=xtrace_or_verbose_enabled"
  exit 1
fi
umask 077
unset DATABASE_URL POSTGRES_URL SUPABASE_DB_URL DIRECT_URL PGSERVICE PGPASSWORD

abort() { print -u2 "E3_RESULT=FAIL"; print -u2 "E3_REASON=$1"; exit 1; }

command -v python3 >/dev/null 2>&1 || abort "python3_missing"
HERE="${0:A:h}"
GUARDS="$HERE/pr188_gate_e3_guards.py"
WRAPPER="$HERE/pr188_gate_e3_alembic_upgrade.py"
[[ -f "$GUARDS" ]] || abort "e3_guards_module_missing"
[[ -f "$WRAPPER" ]] || abort "e3_alembic_wrapper_missing"
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"

CONFIRM_EXPECT="I_AUTHORIZE_PROD_ALEMBIC_0016_TO_0027"
[[ "${GATE_E3_UPGRADE_CONFIRM:-}" == "$CONFIRM_EXPECT" ]] || abort "missing_or_wrong_confirm_token_upgrade_not_run"
RAILWAY_EXPECT="trustworthy-embrace/env/recall-th-c/0c0a8d5/PLAYGROUND_ENABLED=false"
[[ "${E3_RAILWAY_CONFIRM:-}" == "$RAILWAY_EXPECT" ]] || abort "railway_operator_confirm_missing"

SHA="5d89fbdfb6c712a998ce1fdbc4a7756fee8677b8"
START_REV="20260828_0016"
HEAD_REV="20260927_0027"
E2_STAMP="20261015T063833Z"
E2_AGE="$HOME/recall_prod_gate_e2_${E2_STAMP}.tar.age"
E2_AGE_SHA="6ff82b61c3dc89f910d78781b597731cc0e7200fce6c2f46b66376ec9c6faf4c"
SENTINEL="$HOME/.recall_gate_e3_precheck_ok"
E3_BASELINE="$HOME/.recall_gate_e3_pre_upgrade_baseline"
MAX_SENTINEL_AGE=1800

print "E3_CONFIRM_TOKEN=accepted"
print "E3_UPGRADE_TARGET=$HEAD_REV"
print "E3_UPGRADE_HEAD_ALIAS=forbidden"
print "E3_STAMP_FORBIDDEN=yes"
print "E3_DOWNGRADE_FORBIDDEN=yes"
print "E3_DEVELOPER_CHECKOUT_NOT_SWITCHED=yes"

# Fail-fast archive identity + recency before any DSN or Alembic.
[[ -f "$E2_AGE" ]] || abort "e2_age_archive_missing"
got_sha="$(shasum -a 256 "$E2_AGE" | awk '{print $1}')"
python3 "$GUARDS" sha "$got_sha" "$E2_AGE_SHA"
print "E3_E2_AGE_SHA_OK=yes"
python3 "$GUARDS" recency "$E2_STAMP" 12
print "E3_BACKUP_RECENCY_EARLY=ok"

command -v psql >/dev/null 2>&1 || abort "psql_missing"

REPO="${1:-${RECALL_THE_C_REPO:-}}"
[[ -n "$REPO" ]] || abort "usage_pass_recall_the_c_repo_path"
REPO="${REPO:A}"
[[ -d "$REPO/.git" || -f "$REPO/.git" ]] || abort "repo_not_git"
case "$REPO" in
  /workspace|/workspace/*) abort "cloud_workspace_forbidden_use_mac_clone" ;;
esac

WT="${E3_WORKTREE:-$HOME/.recall_gate_e3_worktree}"
[[ -f "$SENTINEL" ]] || abort "precheck_sentinel_missing_run_precheck"
[[ -f "$E3_BASELINE" ]] || abort "e3_pre_upgrade_baseline_missing"
[[ -e "$WT/.git" ]] || abort "e3_worktree_missing_run_precheck"

python3 - "$SENTINEL" "$SHA" "$START_REV" "$E2_STAMP" "$MAX_SENTINEL_AGE" "$WT" <<'PY'
import sys, time
path, sha, rev, stamp, max_age, wt = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), sys.argv[6]
data = {}
for line in open(path, encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    data[k] = v
age = time.time() - int(data.get("unixtime", "0"))
print(f"E3_PRECHECK_SENTINEL_AGE_SEC={int(age)}")
if data.get("checkout") != sha:
    print("E3_RESULT=FAIL")
    print("E3_REASON=sentinel_checkout_mismatch")
    sys.exit(1)
if data.get("alembic") != rev:
    print("E3_RESULT=FAIL")
    print("E3_REASON=sentinel_revision_mismatch")
    sys.exit(1)
if data.get("e2_stamp") != stamp:
    print("E3_RESULT=FAIL")
    print("E3_REASON=sentinel_e2_stamp_mismatch")
    sys.exit(1)
if data.get("worktree") and data.get("worktree") != wt:
    print("E3_RESULT=FAIL")
    print("E3_REASON=sentinel_worktree_mismatch")
    sys.exit(1)
if age > max_age:
    print("E3_RESULT=FAIL")
    print("E3_REASON=precheck_sentinel_stale_rerun_precheck")
    sys.exit(1)
print("E3_PRECHECK_SENTINEL=fresh")
PY

[[ "$(git -C "$WT" rev-parse HEAD)" == "$SHA" ]] || abort "worktree_checkout_sha"
[[ -z "$(git -C "$WT" status --porcelain)" ]] || abort "worktree_dirty"
print "E3_HEAD=$(git -C "$WT" rev-parse HEAD)"
print "E3_WORKTREE=$WT"
print "E3_DEVELOPER_HEAD=$(git -C "$REPO" rev-parse HEAD)"

VENV="$REPO/.venv-mig-rehearsal"
ALEMBIC="$VENV/bin/alembic"
VPY="$VENV/bin/python"
[[ -x "$ALEMBIC" && -x "$VPY" ]] || abort "venv_mig_rehearsal_missing"

DSN_FILE="$HOME/.recall_direct_dsn"
[[ -f "$DSN_FILE" ]] || abort "dsn_file_missing"
[[ "$(stat -f '%Lp' "$DSN_FILE")" == "600" ]] || abort "dsn_file_mode_not_600"
# shellcheck disable=SC1090
source "$DSN_FILE"
export DIRECT_DATABASE_URL EXPECTED_SUPABASE_REF EXPECTED_DB_NAME RAILWAY_APP_ROLE
[[ -n "${DIRECT_DATABASE_URL:-}" && -n "${EXPECTED_SUPABASE_REF:-}" && -n "${EXPECTED_DB_NAME:-}" ]] || abort "dsn_vars_absent"
export PGPASSFILE="${PGPASSFILE:-$HOME/.recall_pgpass}"
[[ -f "$PGPASSFILE" ]] || abort "pgpass_file_missing"
[[ "$(stat -f '%Lp' "$PGPASSFILE")" == "600" ]] || abort "pgpass_mode_not_600"

LOGDIR="$HOME/.recall_gate_e3_logs"
mkdir -p "$LOGDIR"
chmod 700 "$LOGDIR"
export E3_LOGDIR="$LOGDIR"
export START_REV HEAD_REV

URLFILE="$(mktemp "${TMPDIR:-/tmp}/e3_upgrade_url.XXXXXX")"
chmod 600 "$URLFILE"
cleanup() { rm -f "$URLFILE"; unset DATABASE_URL; }
trap cleanup EXIT
export E3_URLFILE="$URLFILE"

python3 - <<'PY'
import os, subprocess, sys
from urllib.parse import parse_qs, unquote, urlsplit
import pr188_gate_e3_guards as guards

def fail(r):
    print("E3_RESULT=FAIL")
    print(f"E3_REASON={r}")
    sys.exit(1)

def classify(err: str) -> str:
    low = (err or "").lower()
    if "no password supplied" in low or "fe_sendauth" in low:
        return "no_password_supplied_noninteractive"
    if "password authentication failed" in low:
        return "password_authentication_failed"
    if "timeout" in low:
        return "connect_timeout"
    if "connection refused" in low:
        return "connection_refused"
    if "could not connect" in low or "could not translate" in low:
        return "connection_failed"
    return "command_failed_redacted"

def write_err_log(text: str, name: str) -> None:
    logdir = os.environ["E3_LOGDIR"]
    os.makedirs(logdir, mode=0o700, exist_ok=True)
    os.chmod(logdir, 0o700)
    path = os.path.join(logdir, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text or "")
    os.chmod(path, 0o600)

def stderr_text(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return str(raw)

def guard(url: str, ref: str, expected_db: str) -> None:
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    user = unquote(p.username or "")
    db = unquote(p.path.lstrip("/"))
    port = p.port
    if p.scheme not in ("postgresql", "postgres"):
        fail("dsn_not_postgres")
    if p.password is not None:
        fail("password_bearing_url_forbidden")
    if port == 6543:
        fail("transaction_pooler_port_6543")
    if port != 5432:
        fail("port_not_5432")
    if not ref or len(ref) < 8 or db != expected_db:
        fail("dsn_identity")
    if host in {"localhost", "127.0.0.1", "::1"}:
        fail("localhost_forbidden")
    q = parse_qs(p.query)
    if "pgbouncer" in q and any(v.lower() == "true" for v in q["pgbouncer"]):
        fail("transaction_pooler_parameter")
    if "sslmode" not in q or "require" not in q["sslmode"]:
        fail("sslmode_require_missing")
    session = host.endswith(".pooler.supabase.com") and user.lower().endswith("." + ref.lower())
    direct = host == f"db.{ref.lower()}.supabase.co"
    if not (session or direct):
        fail("supabase_host_or_pooler_username_mismatch")

raw = os.environ["DIRECT_DATABASE_URL"]
ref = os.environ["EXPECTED_SUPABASE_REF"].strip()
expected_db = os.environ["EXPECTED_DB_NAME"]
guard(raw, ref, expected_db)
if "6543" in raw:
    fail("dsn_contains_6543")
with open(os.environ["E3_URLFILE"], "w", encoding="utf-8") as fh:
    fh.write(raw)
os.chmod(os.environ["E3_URLFILE"], 0o600)
print("E3_DSN_OPTIONS_NOT_RELIED_ON=yes")
print("E3_PSQL_SET_IS_FAILFAST_ONLY=yes")
print("E3_MIGRATION_TIMEOUTS_REQUIRE_WRAPPER=yes")

sql = r"""
SET lock_timeout = '15s';
SET statement_timeout = '120s';
SET idle_in_transaction_session_timeout = '60s';
BEGIN READ ONLY;
SELECT current_setting('transaction_read_only') || '|' ||
       inet_server_port()::text || '|' ||
       current_setting('lock_timeout') || '|' ||
       current_setting('statement_timeout') || '|' ||
       current_setting('idle_in_transaction_session_timeout') || '|' ||
       (SELECT version_num FROM public.alembic_version);
COMMIT;
"""
env = os.environ.copy()
env.pop("PGPASSWORD", None)
env["PGPASSFILE"] = os.environ["PGPASSFILE"]
env["PGCONNECT_TIMEOUT"] = "15"
cmd = [
    "psql", "-X", "-w", "-q", "-v", "ON_ERROR_STOP=1",
    "--pset", "pager=off", "--pset", "footer=off", "--pset", "tuples_only=on",
    raw,
]
try:
    proc = subprocess.run(cmd, input=sql, env=env, capture_output=True, text=True, timeout=30)
except subprocess.TimeoutExpired as e:
    write_err_log(stderr_text(e.stderr) or "timeout", "e3_upgrade_psql.err")
    fail("psql_timeout")
except OSError:
    fail("psql_os_error")
except subprocess.SubprocessError:
    fail("psql_subprocess_error")
if proc.returncode != 0:
    write_err_log(proc.stderr or "", "e3_upgrade_psql.err")
    print("E3_PSQL_ERROR_CLASS=" + classify(proc.stderr or ""))
    fail("psql_noninteractive_failed")
line = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
if len(line) != 1:
    fail("unexpected_row_count")
tx, inet_port, lock_t, stmt_t, idle_t, ver = line[0].split("|")
print(f"E3_TX_READ_ONLY={tx}")
print(f"E3_INET_PORT={inet_port}")
print(f"E3_LOCK_TIMEOUT={lock_t}")
print(f"E3_STATEMENT_TIMEOUT={stmt_t}")
print(f"E3_IDLE_IN_TX_TIMEOUT={idle_t}")
print(f"E3_ALEMBIC_BEFORE={ver}")
if tx != "on" or inet_port != "5432":
    fail("identity_port")
guc_reason = guards.check_timeouts(lock_t, stmt_t, idle_t)
if guc_reason:
    fail(guc_reason)
print("E3_PSQL_SESSION_TIMEOUTS_VERIFIED=yes")
print("E3_PSQL_CHECK_NOT_SUFFICIENT_FOR_ALEMBIC=yes")
if ver == os.environ["HEAD_REV"]:
    fail("already_0027_do_not_restamp")
if ver != os.environ["START_REV"]:
    fail("alembic_not_0016_stop_no_upgrade")
print("E3_PRE_UPGRADE_REVISION_OK=yes")
PY

# Final execution boundary: recency must still hold immediately before Alembic.
print "E3_BACKUP_RECENCY_FINAL_CHECK=begin"
python3 "$GUARDS" recency "$E2_STAMP" 12
got_sha2="$(shasum -a 256 "$E2_AGE" | awk '{print $1}')"
python3 "$GUARDS" sha "$got_sha2" "$E2_AGE_SHA"
print "E3_BACKUP_RECENCY_FINAL=ok"

DATABASE_URL="$(cat "$URLFILE")"
export DATABASE_URL
export PGPASSFILE
export E3_WORKTREE="$WT"
unset PGPASSWORD

print "E3_ALEMBIC_ARGV=wrapper_upgrade_20260927_0027"
print "E3_ALEMBIC_UPGRADE_HEAD=not_used"
print "E3_ALEMBIC_CLI_BYPASS=wrapper_sets_timeouts_on_connect"
cd "$WT"
set +e
"$VPY" "$WRAPPER" 20260927_0027 >"$LOGDIR/e3_alembic.out" 2>"$LOGDIR/e3_alembic.err"
up_rc=$?
set -e
chmod 600 "$LOGDIR/e3_alembic.out" "$LOGDIR/e3_alembic.err" 2>/dev/null || true
print "E3_ALEMBIC_UPGRADE_EXIT=$up_rc"
print "E3_ALEMBIC_LOG=~/.recall_gate_e3_logs/e3_alembic.err"
if grep -E '^E3_' "$LOGDIR/e3_alembic.out" >/dev/null 2>&1; then
  grep -E '^E3_' "$LOGDIR/e3_alembic.out" || true
fi
if [[ "$up_rc" -eq 0 ]]; then
  grep -q '^E3_MIGRATION_CONN_TIMEOUTS_VERIFIED=yes$' "$LOGDIR/e3_alembic.out" \
    || abort "migration_timeouts_not_verified_on_alembic_connection"
fi

python3 - <<'PY'
import os, subprocess, sys
from urllib.parse import urlsplit

def fail(r):
    print("E3_RESULT=FAIL")
    print(f"E3_REASON={r}")
    sys.exit(1)

def write_err_log(text: str, name: str) -> None:
    path = os.path.join(os.environ["E3_LOGDIR"], name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text or "")
    os.chmod(path, 0o600)

timeout_url = open(os.environ["E3_URLFILE"], encoding="utf-8").read().strip()
if urlsplit(timeout_url).port == 6543:
    fail("timeout_url_contains_6543")
sql = r"""
BEGIN READ ONLY;
SELECT version_num FROM public.alembic_version;
COMMIT;
"""
env = os.environ.copy()
env.pop("PGPASSWORD", None)
env["PGPASSFILE"] = os.environ["PGPASSFILE"]
env["PGCONNECT_TIMEOUT"] = "15"
cmd = [
    "psql", "-X", "-w", "-q", "-v", "ON_ERROR_STOP=1",
    "--pset", "pager=off", "--pset", "footer=off", "--pset", "tuples_only=on",
    timeout_url,
]
proc = subprocess.run(cmd, input=sql, env=env, capture_output=True, text=True, timeout=30)
if proc.returncode != 0:
    write_err_log(proc.stderr or "", "e3_post_upgrade_psql.err")
    fail("post_upgrade_psql_failed")
ver = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
if len(ver) != 1:
    fail("post_upgrade_revision_unparseable")
print(f"E3_ALEMBIC_AFTER={ver[0]}")
open(os.environ["E3_LOGDIR"] + "/e3_alembic_after_revision", "w", encoding="utf-8").write(ver[0] + "\n")
os.chmod(os.environ["E3_LOGDIR"] + "/e3_alembic_after_revision", 0o600)
PY
AFTER="$(cat "$LOGDIR/e3_alembic_after_revision" 2>/dev/null | tr -d '[:space:]')"
print "E3_STOP_AFTER_E3=yes"
print "E3_E4_NOT_RUN=yes"
print "E3_MERGE_NOT_RUN=yes"

if [[ "$up_rc" -eq 0 && "$AFTER" == "$HEAD_REV" ]]; then
  print "E3_RESULT=PASS"
  print "E3_ALEMBIC=$HEAD_REV"
  print "E3_DOES_NOT_AUTHORIZE_E4=yes"
  print "E3_DOES_NOT_AUTHORIZE_MERGE=yes"
  print "E3_NEXT=stop_await_e4_authorization"
  exit 0
fi

print "E3_RESULT=FAIL"
if [[ "$AFTER" == "$START_REV" ]]; then
  print "E3_REASON=upgrade_failed_still_0016"
  print "E3_RETRY=forbidden_until_human_decision"
elif [[ "$AFTER" == "$HEAD_REV" ]]; then
  print "E3_REASON=upgrade_exit_nonzero_but_0027_stop"
  print "E3_RETRY=forbidden"
else
  print "E3_REASON=mid_chain_or_unexpected_revision_stop"
  print "E3_RETRY=forbidden_no_stamp_no_downgrade"
fi
exit 1
