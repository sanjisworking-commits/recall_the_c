#!/usr/bin/env python3
# REVISION=e4_prep_v1_1_20261016
"""PR #188 Gate E4 fail-closed helpers. Read-only. No dumps, GRANT, or Alembic."""
from __future__ import annotations

import json
import os
import re
import stat
import sys
from urllib.parse import parse_qs, unquote, urlsplit

START_REV = "20260828_0016"
HEAD_REV = "20260927_0027"
PINNED_SHA = "5d89fbdfb6c712a998ce1fdbc4a7756fee8677b8"
MAIN_SHA = "0c0a8d555748cb5fa63a5fbe0a43998ee5c1d942"
RAILWAY_EXPECT = "trustworthy-embrace/env/recall-th-c/0c0a8d5/PLAYGROUND_ENABLED=false"
NOW_CONFIRM = "I_AUTHORIZE_E4_NOW_READONLY_AT_0016"
VERIFY_CONFIRM = "I_AUTHORIZE_E4_POST_E3_READONLY_AT_0027"
HTTP_BASE_ALLOWED = "https://recall-the-c.in"
LEGACY_TABLES = [
    "access_grants",
    "app_session",
    "billing_orders",
    "contact_messages",
    "daily_goal_met",
    "issue_reports",
    "learning_unit_progress",
    "user_profile",
    "user_roles",
]
NEW_TABLES = [
    "user_playground_item",
    "user_playground_selection",
    "user_playground_progress",
    "user_subscription",
    "subscription_webhook_event",
    "subscription_charge",
    "user_device",
    "user_device_session",
    "user_device_replacement",
    "user_playground_period",
    "user_playground_roster_item",
    "user_playground_mode_progress",
    "user_playground_revision_mode_progress",
    "user_playground_source_change",
    "user_playground_source_scan",
]


class E4Fail(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def strip_ref(name: str, ref: str) -> str:
    n, r = (name or "").strip(), (ref or "").strip()
    suffix = "." + r
    if r and n.lower().endswith(suffix.lower()):
        return n[: -len(suffix)]
    return n


def mode600(path: str) -> bool:
    try:
        return stat.S_IMODE(os.stat(path).st_mode) == 0o600
    except OSError:
        return False


def guard_dsn(url: str, ref: str, expected_db: str) -> str:
    """Return dsn kind (session_pooler|direct) or raise E4Fail."""
    p = urlsplit(url or "")
    host = (p.hostname or "").lower()
    user = unquote(p.username or "")
    db = unquote(p.path.lstrip("/"))
    port = p.port
    if p.scheme not in ("postgresql", "postgres"):
        raise E4Fail("dsn_not_postgres")
    if p.password is not None:
        raise E4Fail("password_bearing_url_forbidden")
    if port == 6543:
        raise E4Fail("transaction_pooler_port_6543")
    if port != 5432:
        raise E4Fail("port_not_5432")
    if not (ref or "").strip() or len(ref.strip()) < 8:
        raise E4Fail("project_ref_missing")
    if db != expected_db:
        raise E4Fail("database_name_mismatch")
    if host in {"localhost", "127.0.0.1", "::1"}:
        raise E4Fail("localhost_forbidden")
    q = parse_qs(p.query)
    if "pgbouncer" in q and any(v.lower() == "true" for v in q["pgbouncer"]):
        raise E4Fail("transaction_pooler_parameter")
    if "sslmode" not in q or "require" not in q["sslmode"]:
        raise E4Fail("sslmode_require_missing")
    session = host.endswith(".pooler.supabase.com") and user.lower().endswith("." + ref.strip().lower())
    direct = host == f"db.{ref.strip().lower()}.supabase.co"
    if not (session or direct):
        raise E4Fail("supabase_host_or_pooler_username_mismatch")
    if "6543" in (url or ""):
        raise E4Fail("dsn_contains_6543")
    return "session_pooler" if session else "direct"


def sanitize_err(s: str) -> str:
    s = re.sub(r"postgres(ql)?://\S+", "postgresql://[redacted]", s or "", flags=re.I)
    s = re.sub(r"password=[^\s]+", "password=[redacted]", s, flags=re.I)
    s = re.sub(r"\bdb\.[A-Za-z0-9]+\.supabase\.co\b", "db.[ref].supabase.co", s)
    s = re.sub(r"\bpostgres\.[A-Za-z0-9]+\b", "postgres.[ref]", s)
    s = re.sub(r"\baws-[A-Za-z0-9.-]+\.pooler\.supabase\.com\b", "[pooler-host]", s)
    s = re.sub(r"\b[A-Za-z0-9.-]+\.supabase\.co\b", "[supabase-host]", s)
    return s.strip()


def classify_psql_err(err: str) -> str:
    low = (err or "").lower()
    if "no password supplied" in low or "fe_sendauth" in low:
        return "no_password_supplied_noninteractive"
    if "password authentication failed" in low:
        return "password_authentication_failed"
    if "cannot execute" in low and "read-only" in low:
        return "read_only_rejected_write"
    if "does not exist" in low or "undefined_table" in low:
        return "undefined_table"
    if "permission denied" in low:
        return "permission_denied"
    if "timeout" in low:
        return "connect_timeout"
    return "command_failed_redacted"


def parse_baseline(path: str) -> dict[str, int]:
    out: dict[str, int] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "|" not in line:
                continue
            name, n = line.split("|", 1)
            if name in LEGACY_TABLES and n.isdigit():
                out[name] = int(n)
    if set(out) != set(LEGACY_TABLES):
        raise E4Fail("baseline_tables_incomplete")
    return out


def count_deltas(baseline: dict[str, int], live: dict[str, int]) -> tuple[list[str], list[str]]:
    inc, dec = [], []
    for name in LEGACY_TABLES:
        b, v = baseline[name], live[name]
        if v > b:
            inc.append(f"{name}:{b}->{v}")
        elif v < b:
            dec.append(f"{name}:{b}->{v}")
    return inc, dec


def check_http_base(base: str) -> None:
    b = (base or "").strip().rstrip("/")
    if b != HTTP_BASE_ALLOWED:
        raise E4Fail("http_base_not_recall_the_c_in")
    p = urlsplit(b)
    if p.scheme != "https":
        raise E4Fail("http_base_not_https")
    if (p.hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}:
        raise E4Fail("http_localhost_forbidden")
    if "pr-188" in (p.hostname or "").lower():
        raise E4Fail("http_pr188_preview_forbidden")


def interpret_health(status: int, body: str) -> str | None:
    if status != 200:
        return "health_not_200"
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return "health_not_json"
    if not isinstance(data, dict) or data.get("status") != "ok":
        return "health_status_not_ok"
    return None


def interpret_html_ok(status: int, name: str) -> str | None:
    if status >= 500:
        return f"{name}_5xx"
    if status != 200:
        return f"{name}_not_200"
    return None


def interpret_playground(status: int, body: str) -> str | None:
    if status == 404:
        return None
    if status == 200 and "playground" in (body or "").lower():
        return "playground_head_ui_not_old_app_404"
    if status >= 500:
        return "playground_5xx"
    return "playground_not_404_old_app_expected"


def interpret_calendar(status: int) -> str | None:
    if status >= 500:
        return "calendar_5xx"
    if status in {301, 302, 303, 307, 308, 401, 403}:
        return None
    if status == 200:
        return None
    return "calendar_unexpected_status"


def interpret_learn(status: int) -> str | None:
    if status >= 500:
        return "learn_5xx"
    if status in {200, 301, 302, 303, 307, 308, 401, 403}:
        return None
    return "learn_unexpected_status"


def ios_in_platform_check(defn: str) -> bool:
    return "ios" in (defn or "").lower()


def new_table_priv_reason(
    name: str,
    owner_stripped: str,
    app_base: str,
    rls: str,
    force: str,
    sel: str,
    ins: str,
    upd: str,
    dele: str,
    policies: str,
    nrows: str,
) -> str | None:
    if not name:
        return "new_table_name_missing"
    if owner_stripped != app_base:
        return f"new_table_owner_mismatch:{name}"
    if rls != "t":
        return f"new_table_rls_off:{name}"
    if force != "f":
        return f"new_table_force_rls:{name}"
    if sel != "t" or ins != "t" or upd != "t" or dele != "t":
        return f"new_table_crud_incomplete:{name}"
    if not (policies or "").isdigit() or int(policies) != 0:
        return f"new_table_unexpected_policies:{name}"
    if not (nrows or "").isdigit():
        return f"new_table_count_unparseable:{name}"
    if int(nrows) != 0:
        return f"new_table_nonzero_rows:{name}"
    return None


def check_identity_common(
    tx: str,
    inet_port: str,
    ver: str,
    expect_rev: str,
    role_exists: str,
    role_match: bool,
    owner_match: bool,
    bypass: str,
    can_sel: str,
    can_ins: str,
    can_upd: str,
    can_del: str,
    hidden_lock: str,
    competing: str,
) -> list[str]:
    blockers = []
    if tx != "on":
        blockers.append("transaction_not_read_only")
    if inet_port != "5432":
        blockers.append("inet_port_not_5432")
    if ver != expect_rev:
        blockers.append("alembic_not_" + ("0016" if expect_rev == START_REV else "0027"))
    if role_exists != "1":
        blockers.append("app_role_missing")
    if not role_match:
        blockers.append("role_strip_mismatch")
    if not owner_match:
        blockers.append("user_profile_owner_mismatch")
    if bypass != "t":
        blockers.append("rolbypassrls_false")
    if can_sel != "t" or can_ins != "t" or can_upd != "t" or can_del != "t":
        blockers.append("user_profile_crud_incomplete")
    if hidden_lock != "0":
        blockers.append("hidden_session_public_lock")
    if competing != "0":
        blockers.append("competing_session")
    return blockers


def _cli(argv: list[str]) -> int:
    if len(argv) < 2:
        print("E4_RESULT=FAIL")
        print("E4_REASON=guards_usage")
        return 1
    cmd = argv[1]
    if cmd == "http-base":
        try:
            check_http_base(argv[2] if len(argv) > 2 else "")
        except E4Fail as exc:
            print("E4_RESULT=FAIL")
            print(f"E4_REASON={exc.reason}")
            return 1
        print("E4_HTTP_BASE=ok")
        return 0
    if cmd == "confirm-now":
        got = argv[2] if len(argv) > 2 else ""
        if got != NOW_CONFIRM:
            print("E4_RESULT=FAIL")
            print("E4_REASON=missing_or_wrong_e4_now_confirm")
            return 1
        print("E4_NOW_CONFIRM=accepted")
        return 0
    if cmd == "confirm-verify":
        got = argv[2] if len(argv) > 2 else ""
        if got != VERIFY_CONFIRM:
            print("E4_RESULT=FAIL")
            print("E4_REASON=missing_or_wrong_e4_verify_confirm")
            return 1
        print("E4_VERIFY_CONFIRM=accepted")
        return 0
    print("E4_RESULT=FAIL")
    print("E4_REASON=guards_unknown_command")
    return 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
