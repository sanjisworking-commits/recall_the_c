#!/usr/bin/env python3
# REVISION=e4_prep_v1_20261016
"""PR #188 Gate E4 runners: `now` (0016 read-only) and `verify` (0027 read-only).

No Alembic, GRANT, stamp, downgrade, Railway writes, or merge.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import HTTPErrorProcessor, Request, build_opener

import pr188_gate_e4_guards as g

LOGDIR_NAME = ".recall_gate_e4_logs"
NOW_BASELINE = ".recall_gate_e4_now_baseline"
VERIFY_REPORT = ".recall_gate_e4_verify_report"
E1_BASELINE = ".recall_gate_e1_baseline"
E3_BASELINE = ".recall_gate_e3_pre_upgrade_baseline"


def fail(reason: str) -> None:
    print("E4_RESULT=FAIL")
    print(f"E4_REASON={reason}")
    raise SystemExit(1)


def logdir() -> Path:
    d = Path.home() / LOGDIR_NAME
    d.mkdir(mode=0o700, exist_ok=True)
    os.chmod(d, 0o700)
    return d


def write_err(name: str, text: str) -> None:
    path = logdir() / name
    path.write_text(text or "", encoding="utf-8")
    os.chmod(path, 0o600)


class _NoRedirect(HTTPErrorProcessor):
    def http_response(self, req, resp):  # noqa: ANN001
        return resp

    https_response = http_response


def http_get(url: str, timeout: int = 15) -> tuple[int, str]:
    opener = build_opener(_NoRedirect)
    req = Request(url, method="GET", headers={"User-Agent": "recall-gate-e4/v1", "Accept": "*/*"})
    try:
        resp = opener.open(req, timeout=timeout)
        body = resp.read(4096).decode("utf-8", "replace")
        code = resp.getcode() if hasattr(resp, "getcode") else getattr(resp, "status", 0)
        return int(code or 0), body
    except URLError as exc:
        reason = g.sanitize_err(str(getattr(exc, "reason", exc)))
        write_err("e4_http.err", reason)
        fail("http_fetch_failed")
        return 0, ""
    except Exception as exc:
        write_err("e4_http.err", type(exc).__name__)
        fail("http_fetch_failed")
        return 0, ""


def check_http() -> None:
    g.check_http_base(os.environ.get("E4_HTTP_BASE", g.HTTP_BASE_ALLOWED))
    base = g.HTTP_BASE_ALLOWED
    print(f"E4_HTTP_BASE={base}")
    health_s, health_b = http_get(base + "/health")
    print(f"E4_HTTP_HEALTH={health_s}")
    r = g.interpret_health(health_s, health_b)
    if r:
        fail(r)
    print("E4_HTTP_HEALTH_JSON=status_ok")
    for path, name in (("/", "home"), ("/laws", "laws")):
        s, _b = http_get(base + path)
        print(f"E4_HTTP_{name.upper()}={s}")
        r = g.interpret_html_ok(s, name)
        if r:
            fail(r)
    s, body = http_get(base + "/playground")
    print(f"E4_HTTP_PLAYGROUND={s}")
    r = g.interpret_playground(s, body)
    if r:
        fail(r)
    print("E4_HTTP_PLAYGROUND_OLD_APP_404=yes")
    s, _b = http_get(base + "/learn")
    print(f"E4_HTTP_LEARN={s}")
    r = g.interpret_learn(s)
    if r:
        fail(r)
    s, _b = http_get(base + "/calendar")
    print(f"E4_HTTP_CALENDAR={s}")
    r = g.interpret_calendar(s)
    if r:
        fail(r)
    print("E4_HTTP_AUTOMATED=pass")
    print("E4_INTERACTIVE_GOOGLE_LOGIN=not_in_script")
    print("E4_INTERACTIVE_LEARN_SIGNED_IN=not_in_script")
    print("E4_INTERACTIVE_RAILWAY_LOGS=not_in_script")


def run_psql(sql: str, app_base: str) -> list[str]:
    env = os.environ.copy()
    env.pop("PGPASSWORD", None)
    env["PGPASSFILE"] = os.environ["PGPASSFILE"]
    env["PGCONNECT_TIMEOUT"] = "15"
    url = os.environ["DIRECT_DATABASE_URL"]
    cmd = [
        "psql", "-X", "-w", "-q",
        "-v", "ON_ERROR_STOP=1",
        "-v", f"app_role_base={app_base}",
        "--pset", "pager=off",
        "--pset", "footer=off",
        "--pset", "tuples_only=on",
        url,
    ]
    try:
        proc = subprocess.run(cmd, input=sql, env=env, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired as e:
        write_err("e4_psql.err", g.sanitize_err(str(e.stderr or "timeout")))
        fail("psql_timeout")
        raise
    if proc.returncode != 0:
        err = g.sanitize_err(proc.stderr or "")
        write_err("e4_psql.err", err)
        print("E4_PSQL_ERROR_CLASS=" + g.classify_psql_err(err))
        fail("psql_noninteractive_failed")
    return [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]


def identity_sql() -> str:
    return r"""
SELECT
  current_setting('transaction_read_only') || '|' ||
  inet_server_port()::text || '|' ||
  current_user || '|' ||
  (SELECT version_num FROM public.alembic_version) || '|' ||
  (SELECT pg_get_userbyid(c.relowner)
     FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname = 'user_profile') || '|' ||
  (SELECT CASE WHEN rolbypassrls THEN 't' ELSE 'f' END
     FROM pg_roles WHERE rolname = current_user) || '|' ||
  (SELECT CASE WHEN rolsuper THEN 't' ELSE 'f' END
     FROM pg_roles WHERE rolname = current_user) || '|' ||
  (SELECT count(*)::text FROM pg_roles WHERE rolname = :'app_role_base') || '|' ||
  (SELECT CASE WHEN has_table_privilege(:'app_role_base', 'public.user_profile', 'SELECT') THEN 't' ELSE 'f' END) || '|' ||
  (SELECT CASE WHEN has_table_privilege(:'app_role_base', 'public.user_profile', 'INSERT') THEN 't' ELSE 'f' END) || '|' ||
  (SELECT CASE WHEN has_table_privilege(:'app_role_base', 'public.user_profile', 'UPDATE') THEN 't' ELSE 'f' END) || '|' ||
  (SELECT CASE WHEN has_table_privilege(:'app_role_base', 'public.user_profile', 'DELETE') THEN 't' ELSE 'f' END);
"""


def counts_sql() -> str:
    parts = []
    for i, name in enumerate(g.LEGACY_TABLES):
        sel = f"SELECT '{name}' || '|' || count(*)::text FROM public.{name}"
        parts.append(sel if i == 0 else "UNION ALL " + sel)
    return "\n".join(parts) + "\nORDER BY 1;\n"


def activity_sql() -> str:
    return r"""
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
"""


def now_extra_sql() -> str:
    in_list = ", ".join("'" + t + "'" for t in g.NEW_TABLES)
    return f"""
SELECT coalesce((
  SELECT string_agg(c.relname, ',' ORDER BY c.relname)
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind = 'r'
    AND c.relname IN ({in_list})
), '');
SELECT coalesce((
  SELECT pg_get_constraintdef(oid)
  FROM pg_constraint
  WHERE conname = 'user_device_platform_check'
  LIMIT 1
), '');
SELECT (
  SELECT count(*)::text
  FROM information_schema.columns
  WHERE table_schema = 'public'
    AND table_name = 'user_playground_progress'
    AND column_name = 'learned_at'
);
"""


def verify_table_sql(name: str) -> str:
    # Names are frozen constants in NEW_TABLES (public identifiers only).
    return f"""
SELECT '{name}' || '|' ||
       coalesce((
         SELECT pg_get_userbyid(c.relowner)
         FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname = '{name}'
       ), '') || '|' ||
       coalesce((
         SELECT CASE WHEN c.relrowsecurity THEN 't' ELSE 'f' END
         FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname = '{name}'
       ), '') || '|' ||
       coalesce((
         SELECT CASE WHEN c.relforcerowsecurity THEN 't' ELSE 'f' END
         FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname = '{name}'
       ), '') || '|' ||
       CASE WHEN to_regclass('public.{name}') IS NULL THEN ''
            WHEN has_table_privilege(:'app_role_base', 'public.{name}', 'SELECT') THEN 't' ELSE 'f' END || '|' ||
       CASE WHEN to_regclass('public.{name}') IS NULL THEN ''
            WHEN has_table_privilege(:'app_role_base', 'public.{name}', 'INSERT') THEN 't' ELSE 'f' END || '|' ||
       CASE WHEN to_regclass('public.{name}') IS NULL THEN ''
            WHEN has_table_privilege(:'app_role_base', 'public.{name}', 'UPDATE') THEN 't' ELSE 'f' END || '|' ||
       CASE WHEN to_regclass('public.{name}') IS NULL THEN ''
            WHEN has_table_privilege(:'app_role_base', 'public.{name}', 'DELETE') THEN 't' ELSE 'f' END || '|' ||
       (SELECT count(*)::text FROM pg_policies p WHERE p.schemaname = 'public' AND p.tablename = '{name}') || '|' ||
       CASE WHEN to_regclass('public.{name}') IS NULL THEN ''
            ELSE (SELECT count(*)::text FROM public.{name}) END;
"""


def verify_extra_sql() -> str:
    chunks = [verify_table_sql(t) for t in g.NEW_TABLES]
    chunks.append(
        """
SELECT coalesce((
  SELECT pg_get_constraintdef(oid)
  FROM pg_constraint
  WHERE conname = 'user_device_platform_check'
  LIMIT 1
), '');
SELECT (
  SELECT count(*)::text
  FROM information_schema.columns
  WHERE table_schema = 'public'
    AND table_name = 'user_playground_progress'
    AND column_name = 'learned_at'
);
"""
    )
    for t in g.NEW_TABLES:
        chunks.append(f"SELECT 1 FROM public.{t} LIMIT 0;\n")
    return "\n".join(chunks)


def sql_now() -> str:
    return (
        "BEGIN READ ONLY;\n"
        + identity_sql()
        + counts_sql()
        + activity_sql()
        + now_extra_sql()
        + "COMMIT;\n"
    )


def sql_verify() -> str:
    return (
        "BEGIN READ ONLY;\n"
        + identity_sql()
        + counts_sql()
        + activity_sql()
        + verify_extra_sql()
        + "COMMIT;\n"
    )


def parse_identity(line: str, ref: str, app_base: str) -> dict:
    ident = line.split("|")
    if len(ident) != 12:
        fail("identity_row_unparseable")
    (tx, inet_port, cur_user, ver, owner, bypass, superuser, role_exists,
     can_sel, can_ins, can_upd, can_del) = ident
    cur_stripped = g.strip_ref(cur_user, ref)
    own_stripped = g.strip_ref(owner, ref)
    print(f"E4_TX_READ_ONLY={tx}")
    print(f"E4_INET_PORT={inet_port}")
    print("E4_CURRENT_USER=" + ("postgres" if cur_stripped == "postgres" else "non_postgres_redacted"))
    print(f"E4_ALEMBIC={ver}")
    print("E4_USER_PROFILE_OWNER=" + ("postgres" if own_stripped == "postgres" else "other_redacted"))
    print(f"E4_ROLBYPASSRLS={'true' if bypass == 't' else 'false'}")
    print(f"E4_ROLSUPER={'true' if superuser == 't' else 'false'}")
    print(f"E4_APP_ROLE_EXISTS={'yes' if role_exists == '1' else 'no'}")
    print(f"E4_PRIV_SELECT={'true' if can_sel == 't' else 'false'}")
    print(f"E4_PRIV_INSERT={'true' if can_ins == 't' else 'false'}")
    print(f"E4_PRIV_UPDATE={'true' if can_upd == 't' else 'false'}")
    print(f"E4_PRIV_DELETE={'true' if can_del == 't' else 'false'}")
    print(f"E4_ROLE_STRIP_MATCH={'yes' if cur_stripped == app_base else 'no'}")
    print(f"E4_OWNER_STRIP_MATCH={'yes' if own_stripped == app_base else 'no'}")
    return {
        "tx": tx,
        "inet_port": inet_port,
        "ver": ver,
        "role_exists": role_exists,
        "role_match": cur_stripped == app_base,
        "owner_match": own_stripped == app_base,
        "bypass": bypass,
        "sel": can_sel,
        "ins": can_ins,
        "upd": can_upd,
        "dele": can_del,
        "app_base": app_base,
        "own_stripped": own_stripped,
    }


def parse_counts(rows: list[str]) -> dict[str, int]:
    live: dict[str, int] = {}
    for row, expected in zip(rows, g.LEGACY_TABLES):
        if "|" not in row:
            fail("count_row_unparseable")
        name, n = row.split("|", 1)
        if name != expected or not n.isdigit():
            fail("count_row_mismatch")
        print(f"E4_COUNT_{name}={n}")
        live[name] = int(n)
    return live


def parse_activity(line: str) -> tuple[str, str, str]:
    act = line.split("|")
    if len(act) != 3 or not all(p.isdigit() for p in act):
        fail("activity_row_unparseable")
    insuf, hidden_lock, competing = act
    print(f"E4_ACTIVITY_INSUFFICIENT_PRIVILEGE={insuf}")
    print("E4_ACTIVITY_INSUFFICIENT_PRIVILEGE_IS_INFO=yes")
    print(f"E4_HIDDEN_PUBLIC_LOCK_SESSIONS={hidden_lock}")
    print(f"E4_COMPETING_SESSIONS={competing}")
    return insuf, hidden_lock, competing


def write_baseline(path: Path, live: dict[str, int], header: str) -> None:
    lines = [header]
    for name in g.LEGACY_TABLES:
        lines.append(f"{name}|{live[name]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def prepare_env() -> tuple[str, str, str]:
    dsn = os.path.expanduser("~/.recall_direct_dsn")
    if not os.path.isfile(dsn):
        fail("dsn_file_missing")
    if not g.mode600(dsn):
        fail("dsn_file_mode_not_600")
    pgpass = os.environ.get("PGPASSFILE") or os.path.expanduser("~/.recall_pgpass")
    if not os.path.isfile(pgpass):
        fail("pgpass_file_missing")
    if not g.mode600(pgpass):
        fail("pgpass_mode_not_600")
    os.environ["PGPASSFILE"] = pgpass
    print("E4_PGPASS_MODE=600")
    url = os.environ.get("DIRECT_DATABASE_URL", "").strip()
    ref = os.environ.get("EXPECTED_SUPABASE_REF", "").strip()
    db = os.environ.get("EXPECTED_DB_NAME", "").strip()
    role = os.environ.get("RAILWAY_APP_ROLE", "").strip()
    if not url or not ref or not db or not role:
        fail("dsn_vars_absent")
    kind = g.guard_dsn(url, ref, db)
    app_base = g.strip_ref(role, ref)
    if not app_base or not all(c.isalnum() or c == "_" for c in app_base):
        fail("app_role_base_not_safe_identifier")
    print("E4_DSN_KIND=" + kind)
    print("E4_DSN_PORT=5432")
    print("E4_DSN_PASSWORD_IN_URL=no")
    print("E4_APP_ROLE_BASE=" + ("postgres" if app_base == "postgres" else "other_redacted"))
    return ref, app_base, db


def cmd_now() -> int:
    print("E4_MODE=now_readonly_at_0016")
    print("E4_EXPECTS_ALEMBIC=" + g.START_REV)
    print("E4_FULL_VERIFY_REQUIRES_0027=yes")
    print("E4_ALEMBIC_NOT_RUN=yes")
    print("E4_RAILWAY_NOT_EDITED=yes")
    print("E4_MERGE_NOT_RUN=yes")
    ref, app_base, _db = prepare_env()
    lines = run_psql(sql_now(), app_base)
    if len(lines) != 14:
        fail("unexpected_row_count")
    ident = parse_identity(lines[0], ref, app_base)
    live = parse_counts(lines[1:10])
    _insuf, hidden, competing = parse_activity(lines[10])
    present = lines[11]
    platform_def = lines[12]
    learned = lines[13]
    print(f"E4_NEW_TABLES_PRESENT={present if present else 'none'}")
    print(f"E4_PLATFORM_CHECK_DEF={'present' if platform_def else 'absent'}")
    print(f"E4_LEARNED_AT_COLUMNS={learned}")
    blockers = g.check_identity_common(
        ident["tx"], ident["inet_port"], ident["ver"], g.START_REV,
        ident["role_exists"], ident["role_match"], ident["owner_match"],
        ident["bypass"], ident["sel"], ident["ins"], ident["upd"], ident["dele"],
        hidden, competing,
    )
    if ident["ver"] == g.HEAD_REV:
        blockers.append("alembic_is_0027_use_gate_e4_verify")
    if present:
        blockers.append("partial_0027_objects_while_0016")
    if platform_def:
        blockers.append("platform_check_present_while_0016")
    if learned != "0":
        blockers.append("learned_at_present_while_0016")
    if blockers:
        print("E4_BLOCKERS=" + ",".join(blockers))
        fail(blockers[0])
    e1 = Path.home() / E1_BASELINE
    if e1.is_file():
        try:
            base = g.parse_baseline(str(e1))
            inc, dec = g.count_deltas(base, live)
            print("E4_E1_DELTA_INCREASES=" + (",".join(inc) if inc else "none"))
            print("E4_E1_DELTA_DECREASES=" + (",".join(dec) if dec else "none"))
            print("E4_E1_DELTA_NOT_AUTHORITATIVE=yes")
        except g.E4Fail:
            print("E4_E1_BASELINE=unreadable_ignored")
    else:
        print("E4_E1_BASELINE=absent")
    write_baseline(
        Path.home() / NOW_BASELINE,
        live,
        "# PR188 E4-now 0016-era counts — not the E3 pre-upgrade comparator",
    )
    print("E4_NOW_BASELINE_FILE=~/.recall_gate_e4_now_baseline")
    print("E4_NOW_BASELINE_MODE=600")
    check_http()
    print("E4_RESULT=PASS")
    print("E4_DOES_NOT_AUTHORIZE_E3=yes")
    print("E4_DOES_NOT_AUTHORIZE_E4_VERIFY=yes")
    print("E4_DOES_NOT_AUTHORIZE_MERGE=yes")
    print("E4_NEXT=stop_e3_still_deferred")
    return 0


def cmd_verify() -> int:
    print("E4_MODE=verify_readonly_at_0027")
    print("E4_EXPECTS_ALEMBIC=" + g.HEAD_REV)
    print("E4_ALEMBIC_NOT_RUN=yes")
    print("E4_RAILWAY_NOT_EDITED=yes")
    print("E4_MERGE_NOT_RUN=yes")
    e3 = Path.home() / E3_BASELINE
    if not e3.is_file():
        fail("e3_pre_upgrade_baseline_missing")
    if not g.mode600(str(e3)):
        fail("e3_pre_upgrade_baseline_mode")
    ref, app_base, _db = prepare_env()
    probe = run_psql("BEGIN READ ONLY;\n" + identity_sql() + "COMMIT;\n", app_base)
    if len(probe) != 1:
        fail("identity_row_unparseable")
    ident_probe = parse_identity(probe[0], ref, app_base)
    if ident_probe["ver"] == g.START_REV:
        print("E4_BLOCKERS=e3_not_run_alembic_still_0016")
        fail("e3_not_run_alembic_still_0016")
    if ident_probe["ver"] != g.HEAD_REV:
        fail("alembic_not_0027")
    lines = run_psql(sql_verify(), app_base)
    # 1 ident + 9 counts + 1 activity + 15 priv + 1 platform + 1 learned = 28
    if len(lines) != 28:
        fail("unexpected_row_count")
    ident = parse_identity(lines[0], ref, app_base)
    if ident["ver"] == g.START_REV:
        print("E4_BLOCKERS=e3_not_run_alembic_still_0016")
        fail("e3_not_run_alembic_still_0016")
    live = parse_counts(lines[1:10])
    _insuf, hidden, competing = parse_activity(lines[10])
    blockers = g.check_identity_common(
        ident["tx"], ident["inet_port"], ident["ver"], g.HEAD_REV,
        ident["role_exists"], ident["role_match"], ident["owner_match"],
        ident["bypass"], ident["sel"], ident["ins"], ident["upd"], ident["dele"],
        hidden, competing,
    )
    for i, name in enumerate(g.NEW_TABLES):
        row = lines[11 + i].split("|")
        if len(row) != 10:
            fail("new_table_row_unparseable")
        tname, owner, rls, force, sel, ins, upd, dele, policies, nrows = row
        if tname != name:
            fail("new_table_row_mismatch")
        if owner == "" and rls == "":
            blockers.append(f"new_table_missing:{name}")
            continue
        own_stripped = g.strip_ref(owner, ref)
        reason = g.new_table_priv_reason(
            name, own_stripped, app_base, rls, force, sel, ins, upd, dele, policies, nrows
        )
        print(f"E4_NEW_{name}_ROWS={nrows}")
        print(f"E4_NEW_{name}_RLS={'on' if rls == 't' else 'off'}")
        print(f"E4_NEW_{name}_POLICIES={policies}")
        if reason:
            blockers.append(reason)
    platform_def = lines[26]
    learned = lines[27]
    print("E4_PLATFORM_CHECK_HAS_IOS=" + ("yes" if g.ios_in_platform_check(platform_def) else "no"))
    print(f"E4_LEARNED_AT_COLUMNS={learned}")
    if not g.ios_in_platform_check(platform_def):
        blockers.append("platform_check_missing_ios")
    if learned != "1":
        blockers.append("learned_at_missing")
    try:
        base = g.parse_baseline(str(e3))
    except g.E4Fail as exc:
        fail(exc.reason)
        raise
    inc, dec = g.count_deltas(base, live)
    print("E4_E3_DELTA_INCREASES=" + (",".join(inc) if inc else "none"))
    print("E4_E3_DELTA_DECREASES=" + (",".join(dec) if dec else "none"))
    if dec:
        blockers.append("legacy_count_decrease")
    print("E4_SELECT_LIMIT_0=issued_in_read_only_txn")
    if blockers:
        print("E4_BLOCKERS=" + ",".join(blockers))
        fail(blockers[0])
    report = Path.home() / VERIFY_REPORT
    report.write_text(
        "alembic=" + g.HEAD_REV + "\n" + "result=PASS\n",
        encoding="utf-8",
    )
    os.chmod(report, 0o600)
    print("E4_VERIFY_REPORT=~/.recall_gate_e4_verify_report")
    check_http()
    print("E4_RESULT=PASS")
    print("E4_DOES_NOT_AUTHORIZE_MERGE=yes")
    print("E4_NEXT=stop_await_gate_f_authorization")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in {"now", "verify"}:
        print("E4_RESULT=FAIL")
        print("E4_REASON=e4_usage_now_or_verify")
        return 1
    try:
        if argv[1] == "now":
            return cmd_now()
        return cmd_verify()
    except g.E4Fail as exc:
        fail(exc.reason)
        return 1
    except SystemExit:
        raise
    except Exception:
        fail("unhandled_e4_error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
