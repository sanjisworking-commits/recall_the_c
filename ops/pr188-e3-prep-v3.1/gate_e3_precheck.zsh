#!/bin/zsh
# REVISION=e3_prep_v3_1_20261015
# FINGERPRINT=worktree_add_detach+session_set_timeouts+rehearsal_venv
# PR #188 Gate E3 — fail-closed precheck. REVIEW ONLY until approved.
# Does NOT run alembic upgrade, stamp, downgrade, GRANT, Railway, or merge.
# Uses a dedicated detached worktree. Does not switch the developer's checkout.
# Timeouts: session SET + SHOW. URL startup options are NOT relied on (v2 failed:
# lock=0, statement=2min, idle=0 through the session pooler).
#
# Requires pr188_gate_e3_guards.py in the same directory as this script.
#
# After this script is approved:
#   chmod 700 ~/Desktop/gate_e3_precheck.zsh
#   export E3_RAILWAY_CONFIRM='trustworthy-embrace/env/recall-th-c/0c0a8d5/PLAYGROUND_ENABLED=false'
#   zsh ~/Desktop/gate_e3_precheck.zsh /path/to/recall_the_c
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

HERE="${0:A:h}"
GUARDS="$HERE/pr188_gate_e3_guards.py"
[[ -f "$GUARDS" ]] || abort "e3_guards_module_missing"
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"

SHA="5d89fbdfb6c712a998ce1fdbc4a7756fee8677b8"
MAIN_SHA="0c0a8d555748cb5fa63a5fbe0a43998ee5c1d942"
START_REV="20260828_0016"
HEAD_REV="20260927_0027"
E2_STAMP="20261015T063833Z"
E2_AGE="$HOME/recall_prod_gate_e2_${E2_STAMP}.tar.age"
E2_AGE_SHA="6ff82b61c3dc89f910d78781b597731cc0e7200fce6c2f46b66376ec9c6faf4c"
GATE_B="$HOME/recall_backup.dump"
GATE_B_SHA="2026e09e9acba2e9b8d6b411c5952f1b4387c80831c58f8882c958180d782cdd"
E2_BASELINE="$HOME/.recall_gate_e2_pre_e3_baseline"
E3_BASELINE="$HOME/.recall_gate_e3_pre_upgrade_baseline"
E1_BASELINE="$HOME/.recall_gate_e1_baseline"
SENTINEL="$HOME/.recall_gate_e3_precheck_ok"
RAILWAY_EXPECT="trustworthy-embrace/env/recall-th-c/0c0a8d5/PLAYGROUND_ENABLED=false"

REHEARSAL_SRC="${E3_REHEARSAL_SRC:-$HOME/recall_rehearsal_src}"
REHEARSAL_SRC="${REHEARSAL_SRC:A}"
VENV="${E3_REHEARSAL_VENV:-$REHEARSAL_SRC/.venv-mig-rehearsal}"
VENV="${VENV:A}"
REPO="${1:-${RECALL_THE_C_REPO:-$REHEARSAL_SRC}}"
REPO="${REPO:A}"
print "E3_VENV_LOOKUP=E3_REHEARSAL_VENV_or_HOME_recall_rehearsal_src"
print "E3_REHEARSAL_SRC=$REHEARSAL_SRC"
print "E3_VENV_RESOLVED=$VENV"
print "E3_VENV_FROM_DEV_CHECKOUT=no"
# The development checkout is $1 / RECALL_THE_C_REPO. Never use its venv.
if [[ "$VENV" == "$REPO/.venv-mig-rehearsal" && "$REPO" != "$REHEARSAL_SRC" ]]; then
  abort "venv_resolved_from_dev_checkout"
fi
[[ -d "$REPO/.git" || -f "$REPO/.git" ]] || abort "repo_not_git"
[[ -f "$REPO/alembic/env.py" ]] || abort "alembic_env_missing"
case "$REPO" in
  /workspace|/workspace/*) abort "cloud_workspace_forbidden_use_mac_clone" ;;
esac

[[ "${E3_RAILWAY_CONFIRM:-}" == "$RAILWAY_EXPECT" ]] || abort "railway_operator_confirm_missing"

command -v python3 >/dev/null 2>&1 || abort "python3_missing"
command -v psql >/dev/null 2>&1 || abort "psql_missing"
command -v git >/dev/null 2>&1 || abort "git_missing"
command -v shasum >/dev/null 2>&1 || abort "shasum_missing"

print "E3_PREP_ONLY=yes"
print "E3_UPGRADE_NOT_RUN=yes"
print "E3_PR=188"
print "E3_REQUIRED_CHECKOUT=$SHA"
print "E3_REQUIRED_MAIN=$MAIN_SHA"
print "E3_REQUIRED_START=$START_REV"
print "E3_REQUIRED_HEAD=$HEAD_REV"
print "E3_RAILWAY_CONFIRM_MATCH=yes"
print "E3_PLAYGROUND_KILL_SWITCH_EXPECTED=false"
print "E3_DEVELOPER_CHECKOUT_NOT_SWITCHED=yes"

WT="${E3_WORKTREE:-$HOME/.recall_gate_e3_worktree}"
print "E3_WORKTREE=$WT"

# Git identity against origin; do not pull, switch, or dirty-check the developer tree.
main_remote="$(git -C "$REPO" ls-remote origin refs/heads/main 2>/dev/null | awk '{print $1}')"
[[ "$main_remote" == "$MAIN_SHA" ]] || abort "main_drifted"
print "E3_ORIGIN_MAIN=$main_remote"
print "E3_DEVELOPER_HEAD=$(git -C "$REPO" rev-parse HEAD)"
if command -v gh >/dev/null 2>&1; then
  pr_json="$(gh pr view 188 --json isDraft,state,headRefOid -q '.state+"|"+(.isDraft|tostring)+"|"+.headRefOid' 2>/dev/null || true)"
  [[ -n "$pr_json" ]] || abort "gh_pr_188_unreadable"
  [[ "$pr_json" == "OPEN|true|$SHA" ]] || abort "pr_188_not_open_draft_at_pinned_sha"
  print "E3_PR_188=OPEN_DRAFT_PINNED_SHA"
else
  print "E3_PR_188=gh_missing_origin_main_checked"
fi
if ! git -C "$REPO" cat-file -t "$SHA" >/dev/null 2>&1; then
  git -C "$REPO" fetch origin "$SHA"
fi
if [[ -e "$WT" ]]; then
  [[ -f "$WT/.git" || -d "$WT/.git" ]] || abort "e3_worktree_path_exists_not_git"
  [[ "$(git -C "$WT" rev-parse HEAD)" == "$SHA" ]] || abort "e3_worktree_wrong_sha"
  [[ -z "$(git -C "$WT" status --porcelain)" ]] || abort "e3_worktree_dirty"
  print "E3_WORKTREE_REUSED=yes"
else
  git -C "$REPO" worktree add --detach "$WT" "$SHA"
  print "E3_WORKTREE_CREATED=yes"
fi
[[ "$(git -C "$WT" rev-parse HEAD)" == "$SHA" ]] || abort "checkout_sha"
[[ -z "$(git -C "$WT" status --porcelain)" ]] || abort "dirty_worktree"
print "E3_HEAD=$(git -C "$WT" rev-parse HEAD)"
print "E3_DETACHED_WORKTREE=yes"

ALEMBIC="$VENV/bin/alembic"
VPY="$VENV/bin/python"
[[ -x "$ALEMBIC" && -x "$VPY" ]] || abort "rehearsal_venv_missing_expected_HOME_recall_rehearsal_src"
"$VPY" -c "import alembic, psycopg" >/dev/null 2>&1 || abort "venv_alembic_or_psycopg_missing"
heads="$(cd "$WT" && "$ALEMBIC" heads | awk '{print $1}')"
head_count="$(print -r -- "$heads" | awk 'NF{n++} END{print n+0}')"
print "E3_ALEMBIC_HEADS_COUNT=$head_count"
print "E3_ALEMBIC_HEADS_VALUE=$(print -r -- "$heads" | tr '\n' ',' | sed 's/,$//')"
[[ "$head_count" == "1" && "$heads" == "$HEAD_REV" ]] || abort "alembic_heads_not_single_0027"
[[ -f "$WT/alembic/versions/20260927_0027_playground_source_changes.py" ]] || abort "revision_0027_file_missing"
print "E3_VENV=ok"

[[ -f "$E2_AGE" ]] || abort "e2_age_archive_missing"
got_sha="$(shasum -a 256 "$E2_AGE" | awk '{print $1}')"
print "E3_E2_AGE_SHA=$got_sha"
python3 "$GUARDS" sha "$got_sha" "$E2_AGE_SHA"
[[ -f "$GATE_B" ]] || abort "gate_b_missing"
gb="$(shasum -a 256 "$GATE_B" | awk '{print $1}')"
print "E3_GATE_B_SHA=$gb"
[[ "$gb" == "$GATE_B_SHA" ]] || abort "gate_b_checksum_changed"
print "E3_GATE_B_UNCHANGED=yes"
[[ -f "$E2_BASELINE" ]] || abort "e2_pre_e3_baseline_missing"
[[ "$(stat -f '%Lp' "$E2_BASELINE")" == "600" ]] || abort "e2_pre_e3_baseline_mode"
print "E3_E2_PRE_E3_BASELINE=present"
print "E3_E1_BASELINE_UNTOUCHED=yes"
python3 "$GUARDS" recency "$E2_STAMP" 12

DSN_FILE="$HOME/.recall_direct_dsn"
[[ -f "$DSN_FILE" ]] || abort "dsn_file_missing"
[[ "$(stat -f '%Lp' "$DSN_FILE")" == "600" ]] || abort "dsn_file_mode_not_600"
# shellcheck disable=SC1090
source "$DSN_FILE"
export DIRECT_DATABASE_URL EXPECTED_SUPABASE_REF EXPECTED_DB_NAME RAILWAY_APP_ROLE
[[ -n "${DIRECT_DATABASE_URL:-}" && -n "${EXPECTED_SUPABASE_REF:-}" && -n "${EXPECTED_DB_NAME:-}" && -n "${RAILWAY_APP_ROLE:-}" ]] || abort "dsn_vars_absent"
export PGPASSFILE="${PGPASSFILE:-$HOME/.recall_pgpass}"
[[ -f "$PGPASSFILE" ]] || abort "pgpass_file_missing"
[[ "$(stat -f '%Lp' "$PGPASSFILE")" == "600" ]] || abort "pgpass_mode_not_600"
print "E3_PGPASS_MODE=600"

LOGDIR="$HOME/.recall_gate_e3_logs"
mkdir -p "$LOGDIR"
chmod 700 "$LOGDIR"
export E3_LOGDIR="$LOGDIR"
export E3_BASELINE E1_BASELINE SENTINEL SHA START_REV
export E3_E2_STAMP="$E2_STAMP"
export E3_WORKTREE="$WT"

URLFILE="$(mktemp "${TMPDIR:-/tmp}/e3_timeout_url.XXXXXX")"
chmod 600 "$URLFILE"
cleanup() { rm -f "$URLFILE"; }
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

def guard(url: str, ref: str, expected_db: str, label: str) -> None:
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    user = unquote(p.username or "")
    db = unquote(p.path.lstrip("/"))
    port = p.port
    if p.scheme not in ("postgresql", "postgres"):
        fail(label + "_dsn_not_postgres")
    if p.password is not None:
        fail(label + "_password_bearing_url_forbidden")
    if port == 6543:
        fail(label + "_transaction_pooler_port_6543")
    if port != 5432:
        fail(label + "_port_not_5432")
    if not ref or len(ref) < 8:
        fail(label + "_project_ref_missing")
    if db != expected_db:
        fail(label + "_database_name_mismatch")
    if host in {"localhost", "127.0.0.1", "::1"}:
        fail(label + "_localhost_forbidden")
    q = parse_qs(p.query)
    if "pgbouncer" in q and any(v.lower() == "true" for v in q["pgbouncer"]):
        fail(label + "_transaction_pooler_parameter")
    if "sslmode" not in q or "require" not in q["sslmode"]:
        fail(label + "_sslmode_require_missing")
    session = host.endswith(".pooler.supabase.com") and user.lower().endswith("." + ref.lower())
    direct = host == f"db.{ref.lower()}.supabase.co"
    if not (session or direct):
        fail(label + "_supabase_host_or_pooler_username_mismatch")
    print("E3_DSN_KIND=" + ("session_pooler" if session else "direct") + "_" + label)
    print("E3_DSN_PORT=5432")
    print("E3_DSN_PASSWORD_IN_URL=no")

try:
    raw = os.environ["DIRECT_DATABASE_URL"]
    ref = os.environ["EXPECTED_SUPABASE_REF"].strip()
    expected_db = os.environ["EXPECTED_DB_NAME"]
    guard(raw, ref, expected_db, "direct")
    if "6543" in raw:
        fail("dsn_contains_6543")
    urlfile = os.environ["E3_URLFILE"]
    with open(urlfile, "w", encoding="utf-8") as fh:
        fh.write(raw)
    os.chmod(urlfile, 0o600)
    print("E3_DSN_OPTIONS_NOT_RELIED_ON=yes")
    print("E3_TIMEOUT_SOURCE=session_set")
    print("E3_TIMEOUT_URL_PRINTED=no")

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
SELECT 'access_grants' || '|' || count(*)::text FROM public.access_grants
UNION ALL SELECT 'app_session' || '|' || count(*)::text FROM public.app_session
UNION ALL SELECT 'billing_orders' || '|' || count(*)::text FROM public.billing_orders
UNION ALL SELECT 'contact_messages' || '|' || count(*)::text FROM public.contact_messages
UNION ALL SELECT 'daily_goal_met' || '|' || count(*)::text FROM public.daily_goal_met
UNION ALL SELECT 'issue_reports' || '|' || count(*)::text FROM public.issue_reports
UNION ALL SELECT 'learning_unit_progress' || '|' || count(*)::text FROM public.learning_unit_progress
UNION ALL SELECT 'user_profile' || '|' || count(*)::text FROM public.user_profile
UNION ALL SELECT 'user_roles' || '|' || count(*)::text FROM public.user_roles
ORDER BY 1;
SELECT
  (SELECT count(*)::text
     FROM pg_stat_activity
     WHERE datname = current_database()
       AND pid <> pg_backend_pid()
       AND query = '<insufficient privilege>')
  || '|' ||
  (SELECT count(*)::text
     FROM pg_stat_activity a
     WHERE a.datname = current_database()
       AND a.pid <> pg_backend_pid()
       AND a.query = '<insufficient privilege>'
       AND EXISTS (
         SELECT 1
         FROM pg_locks l
         INNER JOIN pg_class c ON c.oid = l.relation
         INNER JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE l.pid = a.pid
           AND n.nspname = 'public'
       ))
  || '|' ||
  (SELECT count(*)::text
     FROM pg_stat_activity a
     WHERE a.datname = current_database()
       AND a.pid <> pg_backend_pid()
       AND a.query IS DISTINCT FROM '<insufficient privilege>'
       AND (
         a.query ILIKE '%alembic_version%'
         OR (
           a.state IS DISTINCT FROM 'idle'
           AND EXISTS (
             SELECT 1
             FROM pg_locks l
             INNER JOIN pg_class c ON c.oid = l.relation
             INNER JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE l.pid = a.pid
               AND n.nspname = 'public'
           )
         )
       ));
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
        write_err_log(stderr_text(e.stderr) or "timeout", "e3_precheck_psql.err")
        print("E3_PSQL_ERROR_CLASS=connect_timeout")
        fail("psql_timeout")
    except OSError:
        write_err_log("os_error", "e3_precheck_psql.err")
        print("E3_PSQL_ERROR_CLASS=os_error")
        fail("psql_os_error")
    except subprocess.SubprocessError:
        write_err_log("subprocess_error", "e3_precheck_psql.err")
        print("E3_PSQL_ERROR_CLASS=subprocess_error")
        fail("psql_subprocess_error")
    if proc.returncode != 0:
        write_err_log(proc.stderr or "", "e3_precheck_psql.err")
        print("E3_PSQL_ERROR_CLASS=" + classify(proc.stderr or ""))
        fail("psql_noninteractive_failed")
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if len(lines) != 11:
        fail("unexpected_row_count")
    ident = lines[0].split("|")
    if len(ident) != 6:
        fail("identity_row_unparseable")
    tx, inet_port, lock_t, stmt_t, idle_t, ver = ident
    print(f"E3_TX_READ_ONLY={tx}")
    print(f"E3_INET_PORT={inet_port}")
    print(f"E3_LOCK_TIMEOUT={lock_t}")
    print(f"E3_STATEMENT_TIMEOUT={stmt_t}")
    print(f"E3_IDLE_IN_TX_TIMEOUT={idle_t}")
    print(f"E3_ALEMBIC={ver}")
    if tx != "on":
        fail("transaction_not_read_only")
    if inet_port != "5432":
        fail("inet_port_not_5432")
    guc_reason = guards.check_timeouts(lock_t, stmt_t, idle_t)
    if guc_reason:
        fail(guc_reason)
    print("E3_SESSION_TIMEOUTS_VERIFIED=yes")
    print("E3_TIMEOUTS_APPLIED_VIA_SET=yes")
    if ver != os.environ["START_REV"]:
        fail("alembic_not_0016")
    expected = [
        "access_grants", "app_session", "billing_orders", "contact_messages",
        "daily_goal_met", "issue_reports", "learning_unit_progress",
        "user_profile", "user_roles",
    ]
    count_lines = []
    for row, name in zip(lines[1:10], expected):
        t, n = row.split("|", 1)
        if t != name or not n.isdigit():
            fail("count_row_mismatch")
        print(f"E3_COUNT_{t}={n}")
        count_lines.append(row)
    act = lines[10].split("|")
    if len(act) != 3 or not all(p.isdigit() for p in act):
        fail("activity_row_unparseable")
    insuf, hidden_lock, competing = act
    print(f"E3_ACTIVITY_INSUFFICIENT_PRIVILEGE={insuf}")
    print("E3_ACTIVITY_INSUFFICIENT_PRIVILEGE_IS_INFO=yes")
    print(f"E3_HIDDEN_PUBLIC_LOCK_SESSIONS={hidden_lock}")
    print(f"E3_COMPETING_SESSIONS={competing}")
    if hidden_lock != "0":
        fail("hidden_session_public_lock")
    if competing != "0":
        fail("competing_session")
    e1 = os.environ["E1_BASELINE"]
    e3 = os.environ["E3_BASELINE"]
    if os.path.abspath(e3) == os.path.abspath(e1):
        fail("refusing_to_overwrite_e1_baseline")
    with open(e3, "w", encoding="utf-8") as fh:
        fh.write("# PR188 E3 pre-upgrade count baseline — immediately before authorized upgrade\n")
        for row in count_lines:
            fh.write(row + "\n")
    os.chmod(e3, 0o600)
    print("E3_PRE_UPGRADE_BASELINE_FILE=~/.recall_gate_e3_pre_upgrade_baseline")
    print("E3_PRE_UPGRADE_BASELINE_MODE=600")
    print("E3_PRE_UPGRADE_BASELINE_WRITTEN=yes")
    import time
    sent = os.environ["SENTINEL"]
    with open(sent, "w", encoding="utf-8") as fh:
        fh.write("checkout=" + os.environ["SHA"] + "\n")
        fh.write("alembic=" + os.environ["START_REV"] + "\n")
        fh.write("unixtime=" + str(int(time.time())) + "\n")
        fh.write("e2_stamp=" + os.environ["E3_E2_STAMP"] + "\n")
        fh.write("worktree=" + os.environ["E3_WORKTREE"] + "\n")
    os.chmod(sent, 0o600)
    print("E3_PRECHECK_SENTINEL=~/.recall_gate_e3_precheck_ok")
    print("E3_PRECHECK=PASS")
    print("E3_RESULT=PENDING_EXECUTION_AUTHORIZATION")
    print("E3_UPGRADE_COMMAND=alembic upgrade 20260927_0027")
    print("E3_DOES_NOT_AUTHORIZE_E3_EXECUTION=yes")
    print("E3_DOES_NOT_AUTHORIZE_E4=yes")
    print("E3_DOES_NOT_AUTHORIZE_MERGE=yes")
    print("E3_NEXT=stop_await_explicit_upgrade_authorization")
except SystemExit:
    raise
except Exception:
    fail("unhandled_e3_precheck_error")
PY
