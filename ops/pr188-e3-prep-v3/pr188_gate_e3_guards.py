#!/usr/bin/env python3
# REVISION=e3_prep_v3_20261015
"""PR #188 Gate E3 fail-closed guards. No dumps. Session SET/SHOW helpers only."""
from __future__ import annotations

from datetime import datetime, timezone
import sys

LOCK_ALLOWED = {"15s", "15000ms", "00:00:15"}
STMT_ALLOWED = {"120s", "2min", "120000ms", "00:02:00"}
IDLE_ALLOWED = {"60s", "1min", "60000ms", "00:01:00"}
MAX_BACKUP_HOURS = 12
E2_STAMP = "20261015T063833Z"
E2_AGE_SHA = "6ff82b61c3dc89f910d78781b597731cc0e7200fce6c2f46b66376ec9c6faf4c"
CONFIRM = "I_AUTHORIZE_PROD_ALEMBIC_0016_TO_0027"
PINNED_SHA = "5d89fbdfb6c712a998ce1fdbc4a7756fee8677b8"
START_REV = "20260828_0016"
HEAD_REV = "20260927_0027"

# Observed production SHOW when URL startup options were ignored.
OBSERVED_POOLER_DEFAULTS = {
    "lock_timeout": "0",
    "statement_timeout": "2min",
    "idle_in_transaction_session_timeout": "0",
}

TIMEOUT_SPECS: list[tuple[str, str, set[str]]] = [
    ("lock_timeout", "15s", LOCK_ALLOWED),
    ("statement_timeout", "120s", STMT_ALLOWED),
    ("idle_in_transaction_session_timeout", "60s", IDLE_ALLOWED),
]


class TimeoutNotApplied(Exception):
    def __init__(self, name: str, got: str):
        self.name = name
        self.got = got
        self.reason = {
            "lock_timeout": "lock_timeout_not_15s",
            "statement_timeout": "statement_timeout_not_120s",
            "idle_in_transaction_session_timeout": "idle_in_tx_timeout_not_60s",
        }.get(name, "timeout_not_applied")
        super().__init__(self.reason)


def guc_ok(val: str, allowed: set[str]) -> bool:
    return (val or "").strip().lower() in allowed


def check_timeouts(lock_t: str, stmt_t: str, idle_t: str) -> str | None:
    if not guc_ok(lock_t, LOCK_ALLOWED):
        return "lock_timeout_not_15s"
    if not guc_ok(stmt_t, STMT_ALLOWED):
        return "statement_timeout_not_120s"
    if not guc_ok(idle_t, IDLE_ALLOWED):
        return "idle_in_tx_timeout_not_60s"
    return None


def parse_stamp(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def recency_hours(stamp: str, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    t = parse_stamp(stamp)
    return (now - t).total_seconds() / 3600.0


def recency_ok(
    stamp: str, max_hours: float = MAX_BACKUP_HOURS, now: datetime | None = None
) -> tuple[bool, float, str | None]:
    hours = recency_hours(stamp, now=now)
    if hours < 0:
        return False, hours, "e2_stamp_in_the_future"
    if hours > max_hours:
        return False, hours, "e2_backup_too_old_refresh_required"
    return True, hours, None


def sha_ok(got: str, expected: str = E2_AGE_SHA) -> bool:
    g = (got or "").strip().lower()
    e = (expected or "").strip().lower()
    return len(g) == 64 and g == e and all(c in "0123456789abcdef" for c in g)


def confirm_ok(got: str, expected: str = CONFIRM) -> bool:
    return (got or "") == expected


def _cell(row) -> str:
    if row is None:
        return ""
    if isinstance(row, (tuple, list)):
        return str(row[0] if row else "").strip()
    return str(row[0]).strip()


def apply_timeouts_dbapi(dbapi_conn) -> dict[str, str]:
    """Session-level SET then SHOW on an open DBAPI connection.

    Does not ALTER DATABASE / ALTER ROLE. Does not SET LOCAL (those would
    bind to a transaction that Alembic has not opened yet). Values persist
    for this session, including the later Alembic begin_transaction().
    """
    cur = dbapi_conn.cursor()
    shown: dict[str, str] = {}
    try:
        for name, value, _allowed in TIMEOUT_SPECS:
            cur.execute("SET " + name + " = '" + value + "'")
        for name, _value, allowed in TIMEOUT_SPECS:
            cur.execute("SHOW " + name)
            got = _cell(cur.fetchone())
            shown[name] = got
            if not guc_ok(got, allowed):
                raise TimeoutNotApplied(name, got)
        return shown
    finally:
        cur.close()


def classify_startup_options(lock_t: str, stmt_t: str, idle_t: str) -> str:
    """Interpret SHOW values taken immediately after connect (before SET)."""
    if check_timeouts(lock_t, stmt_t, idle_t) is None:
        return "startup_options_applied"
    # Production observation: lock=0 idle=0 statement=2min (Supabase default).
    if (
        (lock_t or "").strip().lower() in {"0", "0s", "off"}
        and (idle_t or "").strip().lower() in {"0", "0s", "off"}
    ):
        return "startup_options_not_honored"
    return "startup_options_incomplete"


def _cli(argv: list[str]) -> int:
    if len(argv) < 2:
        print("E3_RESULT=FAIL")
        print("E3_REASON=guards_usage")
        return 1
    cmd = argv[1]
    if cmd == "recency":
        stamp = argv[2] if len(argv) > 2 else E2_STAMP
        max_h = float(argv[3]) if len(argv) > 3 else float(MAX_BACKUP_HOURS)
        ok, hours, reason = recency_ok(stamp, max_h)
        print(f"E3_E2_STAMP={stamp}")
        print(f"E3_E2_BACKUP_AGE_HOURS={hours:.2f}")
        print(f"E3_E2_BACKUP_MAX_AGE_HOURS={int(max_h)}")
        if not ok:
            print("E3_RESULT=FAIL")
            print(f"E3_REASON={reason}")
            return 1
        print("E3_E2_BACKUP_RECENCY=ok")
        return 0
    if cmd == "timeouts":
        if len(argv) != 5:
            print("E3_RESULT=FAIL")
            print("E3_REASON=guards_timeouts_usage")
            return 1
        reason = check_timeouts(argv[2], argv[3], argv[4])
        if reason:
            print("E3_RESULT=FAIL")
            print(f"E3_REASON={reason}")
            return 1
        print("E3_GUC_LOCK_OK=yes")
        print("E3_GUC_STATEMENT_OK=yes")
        print("E3_GUC_IDLE_OK=yes")
        return 0
    if cmd == "classify-startup":
        if len(argv) != 5:
            print("E3_RESULT=FAIL")
            print("E3_REASON=guards_classify_usage")
            return 1
        print("E3_STARTUP_OPTIONS=" + classify_startup_options(argv[2], argv[3], argv[4]))
        return 0
    if cmd == "sha":
        if len(argv) != 4:
            print("E3_RESULT=FAIL")
            print("E3_REASON=guards_sha_usage")
            return 1
        if not sha_ok(argv[2], argv[3]):
            print("E3_RESULT=FAIL")
            print("E3_REASON=e2_age_sha_mismatch")
            return 1
        print("E3_E2_AGE_SHA_OK=yes")
        return 0
    if cmd == "confirm":
        got = argv[2] if len(argv) > 2 else ""
        if not confirm_ok(got):
            print("E3_RESULT=FAIL")
            print("E3_REASON=missing_or_wrong_confirm_token_upgrade_not_run")
            return 1
        print("E3_CONFIRM_TOKEN=accepted")
        return 0
    print("E3_RESULT=FAIL")
    print("E3_REASON=guards_unknown_command")
    return 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
