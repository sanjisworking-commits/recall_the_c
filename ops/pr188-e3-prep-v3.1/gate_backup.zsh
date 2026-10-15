#!/bin/zsh
# REVISION=e3_prep_v2_20261015
# FINGERPRINT=gate_backup_backup_and_verify-cloud
# Reusable Mac-local production backup entrypoint (future runs).
# REVIEW ONLY until a future backup is separately authorized.
# Does NOT recreate or overwrite the closed Gate E2 archive
#   recall_prod_gate_e2_20261015T063833Z.tar.age
# Does NOT run Alembic, GRANT, Railway, merge, or iCloud upload/download.
#
# Modes:
#   zsh gate_backup.zsh backup
#       identity → PG17 client → baseline → public dump (required) →
#       full dump (best-effort) → list → SHA-256 → age encrypt →
#       local decrypt-and-stream verify.
#       Success is GATE_RESULT=PENDING_REMOTE_VERIFICATION.
#       Local verify is NOT independent iCloud verification.
#
#   zsh gate_backup.zsh verify-cloud ~/Downloads/recall_prod_backup_STAMP.tar.age
#       Compare downloaded .tar.age to $HOME copy, decrypt-and-stream-verify.
#       GATE_RESULT=PASS only after this mode succeeds.
#
# Never prints GATE_RESULT=PASS from backup mode.
# Never extracts plaintext dumps to disk. Never uses python3 - on the tar pipe.
#
# Optional:
#   GATE_BACKUP_EXPECTED_ALEMBIC  default 20260828_0016
#   GATE_BACKUP_PREFIX            default recall_prod_backup

set -euo pipefail
unsetopt xtrace verbose 2>/dev/null || true
if [[ -o xtrace ]] || [[ -o verbose ]]; then
  print -u2 "GATE_RESULT=FAIL"
  print -u2 "GATE_BACKUP_REASON=xtrace_or_verbose_enabled"
  exit 1
fi
umask 077
unset DATABASE_URL POSTGRES_URL SUPABASE_DB_URL DIRECT_URL PGSERVICE PGPASSWORD
export COPYFILE_DISABLE=1

abort() { print -u2 "GATE_RESULT=FAIL"; print -u2 "GATE_BACKUP_REASON=$1"; exit 1; }

MODE="${1:-}"
PREFIX="${GATE_BACKUP_PREFIX:-recall_prod_backup}"
EXPECTED_ALEMBIC="${GATE_BACKUP_EXPECTED_ALEMBIC:-20260828_0016}"
GATE_B="$HOME/recall_backup.dump"
GATE_B_SHA="2026e09e9acba2e9b8d6b411c5952f1b4387c80831c58f8882c958180d782cdd"
E1_BASELINE="$HOME/.recall_gate_e1_baseline"
LOGDIR="$HOME/.recall_gate_backup_logs"
mkdir -p "$LOGDIR"
chmod 700 "$LOGDIR"

print "GATE_BACKUP_MODE=${MODE:-missing}"
print "GATE_BACKUP_ICLOUD_PERFORMED=no"
print "GATE_BACKUP_DOES_NOT_AUTHORIZE_MIGRATION=yes"
print "GATE_BACKUP_PREFIX=$PREFIX"
print "GATE_BACKUP_EXPECTED_ALEMBIC=$EXPECTED_ALEMBIC"

prefer_pg17_path() {
  local d
  for d in \
    /opt/homebrew/opt/postgresql@17/bin \
    /usr/local/opt/postgresql@17/bin \
    /Applications/Postgres.app/Contents/Versions/17/bin \
    /opt/homebrew/opt/libpq/bin \
    /usr/local/opt/libpq/bin
  do
    if [[ -x "$d/pg_dump" && -x "$d/pg_restore" ]]; then
      PATH="$d:$PATH"
      export PATH
      return 0
    fi
  done
  return 0
}

client_major() {
  local bin="$1" out=""
  set +e
  out="$("$bin" --version 2>/dev/null)"
  set -e
  print -r -- "$out" | python3 -c 'import re,sys
t=sys.stdin.read()
m=re.search(r"(\d+)", t)
print(m.group(1) if m else "0")
'
}

classify_errfile() {
  local f="$1"
  GATE_ERRFILE="$f" python3 - <<'PY'
import os
err = ""
path = os.environ.get("GATE_ERRFILE", "")
try:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        err = fh.read()
except OSError:
    pass
low = err.lower()
if "version mismatch" in low or "aborting because of server version" in low:
    print("server_client_version_mismatch")
elif "no password supplied" in low or "fe_sendauth" in low:
    print("no_password_supplied_noninteractive")
elif "password authentication failed" in low:
    print("password_authentication_failed")
elif "timeout" in low:
    print("connect_timeout")
elif "connection refused" in low:
    print("connection_refused")
elif "could not connect" in low or "could not translate" in low:
    print("connection_failed")
elif "too many connections" in low or "remaining connection slots" in low:
    print("too_many_connections")
elif "permission denied" in low:
    print("permission_denied")
else:
    print("command_failed_redacted")
PY
}

fail_db() {
  local logname="$1" exitcode="$2" reason="$3"
  local log="$LOGDIR/$logname"
  chmod 600 "$log" 2>/dev/null || true
  print "GATE_BACKUP_DB_ERROR_CLASS=$(classify_errfile "$log")"
  print "GATE_BACKUP_DB_EXIT=$exitcode"
  print "GATE_BACKUP_DB_ERROR_LOG=~/.recall_gate_backup_logs/$logname"
  abort "$reason"
}

write_verify_py() {
  local dest="$1"
  cat > "$dest" <<'PY'
import hashlib, os, re, sys, tarfile

def fail(r):
    print("GATE_RESULT=FAIL")
    print(f"GATE_BACKUP_REASON={r}")
    sys.exit(1)

def consume(fh) -> None:
    while fh.read(1024 * 1024):
        pass

def sha256_stream(fh) -> str:
    h = hashlib.sha256()
    while True:
        chunk = fh.read(1024 * 1024)
        if not chunk:
            break
        h.update(chunk)
    return h.hexdigest()

def norm_name(member_name: str) -> str:
    name = (member_name or "").strip()
    if name.startswith("/") or name.startswith("\\"):
        fail("unexpected_archive_member")
    parts = [p for p in name.replace("\\", "/").split("/") if p and p != "."]
    if not parts or ".." in parts or len(parts) != 1:
        fail("unexpected_archive_member")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", parts[0]):
        fail("unexpected_archive_member")
    return parts[0]

base = os.environ.get("GATE_AGE_BASENAME", "")
prefix = os.environ.get("GATE_BACKUP_PREFIX", "recall_prod_backup")
gate_b_sha = (os.environ.get("GATE_B_SHA") or "").strip().lower()
m = re.fullmatch(re.escape(prefix) + r"_(\d{8}T\d{6}Z)\.tar\.age", base)
if not m:
    fail("unexpected_age_filename")
if not re.fullmatch(r"[0-9a-f]{64}", gate_b_sha):
    fail("gate_b_sha_constant_invalid")
stamp = m.group(1)
expected_public = f"{prefix}_public_{stamp}.dump"
expected_full = f"{prefix}_full_{stamp}.dump"
expected_manifest = f"{prefix}_{stamp}.sha256"

digests = {}
manifest_text = None
seen = []

try:
    with tarfile.open(fileobj=sys.stdin.buffer, mode="r|") as tf:
        for member in tf:
            name = norm_name(member.name)
            if (not member.isreg()) or member.issym() or member.islnk() or member.isdir():
                fail("unexpected_archive_member")
            if name in seen:
                fail("duplicate_archive_member")
            seen.append(name)
            fh = tf.extractfile(member)
            if fh is None:
                fail("unexpected_archive_member")
            if name == expected_manifest:
                raw = fh.read()
                try:
                    manifest_text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    fail("manifest_not_utf8")
            elif name in (expected_public, expected_full):
                if name == expected_public and member.size == 0:
                    fail("public_dump_empty")
                digests[name] = sha256_stream(fh)
            else:
                consume(fh)
                fail("unexpected_archive_member")
except tarfile.TarError:
    fail("tar_unreadable")
except OSError:
    fail("tar_os_error")

if manifest_text is None:
    fail("manifest_missing_inside_age")
if expected_public not in digests:
    fail("public_dump_missing_from_archive")

print(f"GATE_BACKUP_INNER_MANIFEST={expected_manifest}")
print(f"GATE_BACKUP_ARCHIVE_MEMBERS={len(seen)}")
print("GATE_BACKUP_PLAINTEXT_DUMPS_WRITTEN=no")

man_entries = []
for line in manifest_text.splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = line.split()
    if len(parts) < 2:
        fail("manifest_line_unparseable")
    digest, path = parts[0].lower(), parts[-1]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        fail("manifest_digest_unparseable")
    bname = os.path.basename(path)
    if not bname or bname in {".", ".."}:
        fail("manifest_line_unparseable")
    man_entries.append((digest, bname))

man_names = [b for _, b in man_entries]
if len(man_names) != len(set(man_names)):
    fail("manifest_duplicate_member")

public_lines = [d for d, b in man_entries if b == expected_public]
full_lines = [d for d, b in man_entries if b == expected_full]
gate_b_lines = [d for d, b in man_entries if b == "recall_backup.dump"]
other = [b for _, b in man_entries if b not in {expected_public, expected_full, "recall_backup.dump"}]
if other:
    fail("unexpected_manifest_member")
if len(public_lines) != 1:
    fail("manifest_public_dump_missing")
if len(gate_b_lines) != 1:
    fail("manifest_gate_b_line_missing")
if gate_b_lines[0] != gate_b_sha:
    fail("gate_b_checksum_changed")
print("GATE_BACKUP_INNER_GATE_B_LINE=present_not_extracted")
print("GATE_BACKUP_GATE_B_UNCHANGED=yes")

if public_lines[0] != digests[expected_public]:
    fail("inner_sha_mismatch")
print(f"GATE_BACKUP_INNER_OK={expected_public}")

full_in_archive = expected_full in digests
full_in_manifest = len(full_lines) == 1
if len(full_lines) > 1:
    fail("manifest_duplicate_member")
if full_in_manifest and not full_in_archive:
    fail("full_dump_missing_from_archive")
if full_in_archive and not full_in_manifest:
    fail("full_dump_not_in_manifest")
if full_in_archive:
    if full_lines[0] != digests[expected_full]:
        fail("inner_sha_mismatch")
    print(f"GATE_BACKUP_INNER_OK={expected_full}")
    print("GATE_BACKUP_INNER_FULL=verified")
    inner_ok = 2
else:
    print("GATE_BACKUP_INNER_FULL=omitted")
    inner_ok = 1

allowed = {expected_public, expected_manifest}
if full_in_archive:
    allowed.add(expected_full)
if set(seen) != allowed:
    fail("unexpected_archive_member")

print(f"GATE_BACKUP_INNER_DUMPS_VERIFIED={inner_ok}")
print("GATE_BACKUP_INNER_VERIFY=PASS")
PY
  chmod 600 "$dest"
}

stream_verify_age() {
  local age_path="$1"
  local verify_py="$LOGDIR/backup_verify_stream.py"
  write_verify_py "$verify_py"
  export GATE_AGE_BASENAME="$(basename "$age_path")"
  export GATE_BACKUP_PREFIX="$PREFIX"
  export GATE_B_SHA
  print "GATE_BACKUP_AGE_DECRYPT_PROMPT=enter_same_passphrase_on_tty"
  age -d -o - "$age_path" | python3 "$verify_py"
}

mode_verify_cloud() {
  local DOWN="${2:-}"
  [[ -n "$DOWN" && -f "$DOWN" ]] || abort "usage_verify_cloud_pass_downloaded_age_path"
  command -v age >/dev/null 2>&1 || abort "age_missing"
  command -v python3 >/dev/null 2>&1 || abort "python3_missing"
  command -v shasum >/dev/null 2>&1 || abort "shasum_missing"
  local base
  base="$(basename "$DOWN")"
  [[ "$base" == ${PREFIX}_*.tar.age ]] || abort "unexpected_age_filename"
  local LOCAL="$HOME/$base"
  [[ -f "$LOCAL" ]] || abort "local_age_missing_in_home"
  [[ "$DOWN" != "$LOCAL" ]] || abort "download_path_must_differ_from_local_home_copy"
  local sha_local sha_down
  sha_local="$(shasum -a 256 "$LOCAL" | awk '{print $1}')"
  sha_down="$(shasum -a 256 "$DOWN" | awk '{print $1}')"
  print "GATE_BACKUP_AGE_SHA_LOCAL=$sha_local"
  print "GATE_BACKUP_AGE_SHA_DOWNLOAD=$sha_down"
  [[ "$sha_local" == "$sha_down" ]] || abort "icloud_download_sha_mismatch"
  print "GATE_BACKUP_ICLOUD_AGE_SHA_MATCH=yes"
  print "GATE_BACKUP_ICLOUD_CLAIMED_BY_SCRIPT=no"
  stream_verify_age "$DOWN"
  print "GATE_BACKUP_CLOUD_VERIFY=PASS"
  print "GATE_RESULT=PASS"
  print "GATE_BACKUP_DOES_NOT_AUTHORIZE_MIGRATION=yes"
}

mode_backup() {
  prefer_pg17_path
  command -v python3 >/dev/null 2>&1 || abort "python3_missing"
  command -v pg_dump >/dev/null 2>&1 || abort "pg_dump_missing"
  command -v pg_restore >/dev/null 2>&1 || abort "pg_restore_missing"
  command -v psql >/dev/null 2>&1 || abort "psql_missing"
  command -v age >/dev/null 2>&1 || abort "age_missing"
  command -v tar >/dev/null 2>&1 || abort "tar_missing"
  command -v shasum >/dev/null 2>&1 || abort "shasum_missing"

  local DUMP_MAJ REST_MAJ
  DUMP_MAJ="$(client_major pg_dump)"
  REST_MAJ="$(client_major pg_restore)"
  print "GATE_BACKUP_PG_DUMP_CLIENT_MAJOR=$DUMP_MAJ"
  print "GATE_BACKUP_PG_RESTORE_CLIENT_MAJOR=$REST_MAJ"
  if ! [[ "$DUMP_MAJ" == [0-9]## ]] || (( DUMP_MAJ < 17 )); then
    abort "pg_dump_client_major_below_17"
  fi
  if ! [[ "$REST_MAJ" == [0-9]## ]] || (( REST_MAJ < 17 )); then
    abort "pg_restore_client_major_below_17"
  fi

  local DSN_FILE="$HOME/.recall_direct_dsn"
  [[ -f "$DSN_FILE" ]] || abort "dsn_file_missing"
  [[ "$(stat -f '%Lp' "$DSN_FILE")" == "600" ]] || abort "dsn_file_mode_not_600"
  # shellcheck disable=SC1090
  source "$DSN_FILE"
  export DIRECT_DATABASE_URL EXPECTED_SUPABASE_REF EXPECTED_DB_NAME RAILWAY_APP_ROLE
  [[ -n "${DIRECT_DATABASE_URL:-}" && -n "${EXPECTED_SUPABASE_REF:-}" && -n "${EXPECTED_DB_NAME:-}" ]] || abort "dsn_vars_absent"
  export PGPASSFILE="${PGPASSFILE:-$HOME/.recall_pgpass}"
  [[ -f "$PGPASSFILE" ]] || abort "pgpass_file_missing"
  [[ "$(stat -f '%Lp' "$PGPASSFILE")" == "600" ]] || abort "pgpass_mode_not_600"
  [[ -f "$GATE_B" ]] || abort "gate_b_dump_missing"
  print "GATE_BACKUP_PGPASS_MODE=600"
  print "GATE_BACKUP_E1_BASELINE_UNTOUCHED=yes"

  export GATE_BACKUP_BASELINE_STAMP_PLACEHOLDER=1
  export E1_BASELINE EXPECTED_ALEMBIC
  export GATE_BACKUP_LOGDIR="$LOGDIR"
  local STAMP
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  export GATE_BACKUP_STAMP="$STAMP"
  local BASELINE="$HOME/.recall_gate_backup_baseline_${STAMP}"
  export GATE_BACKUP_BASELINE="$BASELINE"
  [[ ! -e "$BASELINE" ]] || abort "refusing_to_overwrite_existing_backup_baseline"

  python3 - <<'PY'
import os, subprocess, sys
from urllib.parse import parse_qs, unquote, urlsplit

def fail(r):
    print("GATE_RESULT=FAIL")
    print(f"GATE_BACKUP_REASON={r}")
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
    logdir = os.environ["GATE_BACKUP_LOGDIR"]
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

try:
    url = os.environ["DIRECT_DATABASE_URL"]
    ref = os.environ["EXPECTED_SUPABASE_REF"].strip()
    expected_db = os.environ["EXPECTED_DB_NAME"]
    expected_rev = os.environ["EXPECTED_ALEMBIC"]
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    user = unquote(p.username or "")
    db = unquote(p.path.lstrip("/"))
    port = p.port
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
    print("GATE_BACKUP_DSN_KIND=" + ("session_pooler" if session else "direct"))
    print("GATE_BACKUP_DSN_PORT=5432")
    print("GATE_BACKUP_DSN_PASSWORD_IN_URL=no")

    sql = r"""
BEGIN READ ONLY;
SELECT current_setting('transaction_read_only') || '|' ||
       inet_server_port()::text || '|' ||
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
COMMIT;
"""
    env = os.environ.copy()
    env.pop("PGPASSWORD", None)
    env["PGPASSFILE"] = os.environ["PGPASSFILE"]
    env["PGCONNECT_TIMEOUT"] = "15"
    cmd = [
        "psql", "-X", "-w", "-q", "-v", "ON_ERROR_STOP=1",
        "--pset", "pager=off", "--pset", "footer=off", "--pset", "tuples_only=on",
        url,
    ]
    try:
        proc = subprocess.run(
            cmd, input=sql, env=env, capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired as e:
        write_err_log(stderr_text(e.stderr) or "timeout", "backup_identity_psql.err")
        print("GATE_BACKUP_PSQL_ERROR_CLASS=connect_timeout")
        fail("psql_timeout")
    except OSError:
        write_err_log("os_error", "backup_identity_psql.err")
        print("GATE_BACKUP_PSQL_ERROR_CLASS=os_error")
        fail("psql_os_error")
    except subprocess.SubprocessError:
        write_err_log("subprocess_error", "backup_identity_psql.err")
        print("GATE_BACKUP_PSQL_ERROR_CLASS=subprocess_error")
        fail("psql_subprocess_error")
    if proc.returncode != 0:
        write_err_log(proc.stderr or "", "backup_identity_psql.err")
        print("GATE_BACKUP_PSQL_ERROR_CLASS=" + classify(proc.stderr or ""))
        fail("psql_noninteractive_failed")
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if len(lines) != 10:
        fail("unexpected_row_count")
    tx, inet_port, ver = lines[0].split("|")
    print(f"GATE_BACKUP_TX_READ_ONLY={tx}")
    print(f"GATE_BACKUP_INET_PORT={inet_port}")
    print(f"GATE_BACKUP_ALEMBIC={ver}")
    if tx != "on" or inet_port != "5432" or ver != expected_rev:
        fail("identity_revision")
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
        print(f"GATE_BACKUP_COUNT_{t}={n}")
        count_lines.append(row)
    e1 = os.environ["E1_BASELINE"]
    baseline = os.environ["GATE_BACKUP_BASELINE"]
    if os.path.abspath(baseline) == os.path.abspath(e1):
        fail("refusing_to_overwrite_e1_baseline")
    with open(baseline, "w", encoding="utf-8") as fh:
        fh.write("# recall backup nine-table baseline stamp=" + os.environ["GATE_BACKUP_STAMP"] + "\n")
        for row in count_lines:
            fh.write(row + "\n")
    os.chmod(baseline, 0o600)
    print("GATE_BACKUP_BASELINE_WRITTEN=yes")
    print("GATE_BACKUP_IDENTITY=PASS")
except SystemExit:
    raise
except Exception:
    fail("unhandled_identity_error")
PY

  local gb_sha
  gb_sha="$(shasum -a 256 "$GATE_B" | awk '{print $1}')"
  print "GATE_BACKUP_GATE_B_SHA=$gb_sha"
  [[ "$gb_sha" == "$GATE_B_SHA" ]] || abort "gate_b_checksum_changed"
  print "GATE_BACKUP_GATE_B_UNCHANGED=yes"

  local PUBLIC_DUMP="$HOME/${PREFIX}_public_${STAMP}.dump"
  local FULL_DUMP="$HOME/${PREFIX}_full_${STAMP}.dump"
  local PUBLIC_TOC="$HOME/${PREFIX}_public_${STAMP}.toc"
  local FULL_TOC="$HOME/${PREFIX}_full_${STAMP}.toc"
  local MANIFEST="$HOME/${PREFIX}_${STAMP}.sha256"
  local AGE_OUT="$HOME/${PREFIX}_${STAMP}.tar.age"
  local f
  for f in "$PUBLIC_DUMP" "$FULL_DUMP" "$PUBLIC_TOC" "$FULL_TOC" "$MANIFEST" "$AGE_OUT"; do
    [[ ! -e "$f" ]] || abort "refusing_to_overwrite_existing_backup_artifact"
  done
  print "GATE_BACKUP_STAMP=$STAMP"
  print "GATE_BACKUP_PUBLIC_DUMP_BASENAME=$(basename "$PUBLIC_DUMP")"
  print "GATE_BACKUP_CLOSED_E2_UNTOUCHED=yes"

  export PGCONNECT_TIMEOUT=15
  local pub_rc pub_list_rc full_rc full_list_rc FULL_OK
  set +e
  pg_dump -w -Fc --no-owner -n public -f "$PUBLIC_DUMP" "$DIRECT_DATABASE_URL" 2>"$LOGDIR/backup_public_pg_dump.err"
  pub_rc=$?
  set -e
  chmod 600 "$LOGDIR/backup_public_pg_dump.err"
  print "GATE_BACKUP_PUBLIC_DUMP_EXIT=$pub_rc"
  if [[ $pub_rc -ne 0 ]]; then
    rm -f "$PUBLIC_DUMP"
    fail_db backup_public_pg_dump.err "$pub_rc" public_dump_failed
  fi
  [[ -s "$PUBLIC_DUMP" ]] || abort "public_dump_empty"
  print "GATE_BACKUP_PUBLIC_DUMP_BYTES=$(stat -f '%z' "$PUBLIC_DUMP")"
  chmod 600 "$PUBLIC_DUMP"

  set +e
  pg_restore --list "$PUBLIC_DUMP" > "$PUBLIC_TOC" 2>"$LOGDIR/backup_public_pg_restore_list.err"
  pub_list_rc=$?
  set -e
  chmod 600 "$LOGDIR/backup_public_pg_restore_list.err"
  print "GATE_BACKUP_PUBLIC_LIST_EXIT=$pub_list_rc"
  if [[ $pub_list_rc -ne 0 ]]; then
    fail_db backup_public_pg_restore_list.err "$pub_list_rc" public_dump_list_failed
  fi
  chmod 600 "$PUBLIC_TOC"

  set +e
  pg_dump -w -Fc --no-owner -f "$FULL_DUMP" "$DIRECT_DATABASE_URL" 2>"$LOGDIR/backup_full_pg_dump.err"
  full_rc=$?
  set -e
  chmod 600 "$LOGDIR/backup_full_pg_dump.err"
  print "GATE_BACKUP_FULL_DUMP_EXIT=$full_rc"
  if [[ $full_rc -ne 0 ]]; then
    print "GATE_BACKUP_DB_ERROR_CLASS=$(classify_errfile "$LOGDIR/backup_full_pg_dump.err")"
    print "GATE_BACKUP_DB_ERROR_LOG=~/.recall_gate_backup_logs/backup_full_pg_dump.err"
  fi
  FULL_OK=0
  if [[ $full_rc -eq 0 && -s "$FULL_DUMP" ]]; then
    FULL_OK=1
    print "GATE_BACKUP_FULL_DUMP_BYTES=$(stat -f '%z' "$FULL_DUMP")"
    chmod 600 "$FULL_DUMP"
    set +e
    pg_restore --list "$FULL_DUMP" > "$FULL_TOC" 2>"$LOGDIR/backup_full_pg_restore_list.err"
    full_list_rc=$?
    set -e
    chmod 600 "$LOGDIR/backup_full_pg_restore_list.err"
    print "GATE_BACKUP_FULL_LIST_EXIT=$full_list_rc"
    if [[ $full_list_rc -eq 0 ]]; then
      print "GATE_BACKUP_FULL_DUMP_STATUS=dump_succeeded_restore_unverified"
      chmod 600 "$FULL_TOC"
    else
      print "GATE_BACKUP_DB_ERROR_CLASS=$(classify_errfile "$LOGDIR/backup_full_pg_restore_list.err")"
      print "GATE_BACKUP_FULL_DUMP_STATUS=dump_ok_list_failed_not_recovery_archive"
      FULL_OK=0
    fi
  else
    print "GATE_BACKUP_FULL_DUMP_STATUS=failed_not_recovery_archive"
    [[ -e "$FULL_DUMP" ]] && rm -f "$FULL_DUMP"
  fi

  {
    shasum -a 256 "$PUBLIC_DUMP"
    [[ $FULL_OK -eq 1 ]] && shasum -a 256 "$FULL_DUMP"
    shasum -a 256 "$GATE_B"
  } > "$MANIFEST"
  chmod 600 "$MANIFEST"
  print "GATE_BACKUP_PUBLIC_SHA256=$(awk 'NR==1{print $1}' "$MANIFEST")"
  if [[ $FULL_OK -eq 1 ]]; then
    print "GATE_BACKUP_FULL_SHA256=$(awk 'NR==2{print $1}' "$MANIFEST")"
  else
    print "GATE_BACKUP_FULL_SHA256=omitted"
  fi

  local TAR_MEMBERS
  TAR_MEMBERS=("$(basename "$PUBLIC_DUMP")" "$(basename "$MANIFEST")")
  if [[ $FULL_OK -eq 1 ]]; then
    TAR_MEMBERS+=("$(basename "$FULL_DUMP")")
  fi
  print "GATE_BACKUP_AGE_PROMPT=enter_passphrase_on_tty_do_not_paste_here"
  tar -C "$HOME" -cf - "${TAR_MEMBERS[@]}" | age -e -p -o "$AGE_OUT"
  [[ -s "$AGE_OUT" ]] || abort "age_output_empty"
  chmod 600 "$AGE_OUT"
  print "GATE_BACKUP_AGE_BASENAME=$(basename "$AGE_OUT")"
  print "GATE_BACKUP_AGE_BYTES=$(stat -f '%z' "$AGE_OUT")"
  print "GATE_BACKUP_AGE_SHA256=$(shasum -a 256 "$AGE_OUT" | awk '{print $1}')"
  print "GATE_BACKUP_UNENCRYPTED_COMBINED_TAR=not_written"

  print "GATE_BACKUP_LOCAL_DECRYPT_VERIFY=begin"
  stream_verify_age "$AGE_OUT"
  print "GATE_BACKUP_LOCAL_DECRYPT_VERIFY=PASS"
  print "GATE_BACKUP_LOCAL=PASS"
  print "GATE_RESULT=PENDING_REMOTE_VERIFICATION"
  print "GATE_BACKUP_ICLOUD=upload_only_the_age_file_then_independent_download"
  print "GATE_BACKUP_ICLOUD_PERFORMED=no"
  print "GATE_BACKUP_DOES_NOT_AUTHORIZE_MIGRATION=yes"
  print "GATE_BACKUP_NEXT=manual_icloud_then_verify-cloud"
}

case "$MODE" in
  backup) mode_backup ;;
  verify-cloud) mode_verify_cloud "$@" ;;
  *) abort "usage_gate_backup_backup_or_verify-cloud" ;;
esac
