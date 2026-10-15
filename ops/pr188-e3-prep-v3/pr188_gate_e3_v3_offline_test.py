#!/usr/bin/env python3
# REVISION=e3_prep_v3_20261015
"""Offline tests for E3 v3 timeout SET/SHOW and fail-closed upgrade boundaries."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pr188_gate_e3_guards as guards  # noqa: E402
import pr188_gate_e3_alembic_upgrade as wrapper  # noqa: E402

UPGRADE = HERE / "gate_e3_upgrade.zsh"
CONFIRM = guards.CONFIRM
RAILWAY = "trustworthy-embrace/env/recall-th-c/0c0a8d5/PLAYGROUND_ENABLED=false"
E2_STAMP = guards.E2_STAMP
E2_AGE_SHA = guards.E2_AGE_SHA


class FakeCursor:
    def __init__(self, gucs: dict[str, str], apply_set: bool, show_120s_as_2min: bool):
        self.gucs = gucs
        self.apply_set = apply_set
        self.show_120s_as_2min = show_120s_as_2min
        self._last = None

    def execute(self, sql, params=None):
        s = (sql or "").strip()
        upper = s.upper()
        if upper.startswith("SET "):
            rest = s[4:]
            name, _, val = rest.partition("=")
            name = name.strip()
            val = val.strip().strip("';")
            if self.apply_set:
                if name == "statement_timeout" and val == "120s" and self.show_120s_as_2min:
                    self.gucs[name] = "2min"
                else:
                    self.gucs[name] = val
            return
        if upper.startswith("SHOW "):
            name = s[5:].strip()
            self._last = (self.gucs.get(name, "0"),)
            return
        raise AssertionError("unexpected sql: " + s)

    def fetchone(self):
        return self._last

    def close(self):
        return None


class FakeConn:
    def __init__(self, apply_set: bool = True, show_120s_as_2min: bool = False):
        self.gucs = dict(guards.OBSERVED_POOLER_DEFAULTS)
        self.apply_set = apply_set
        self.show_120s_as_2min = show_120s_as_2min

    def cursor(self):
        return FakeCursor(self.gucs, self.apply_set, self.show_120s_as_2min)


def sanitize(text: str) -> str:
    keep = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("E3_") or s.startswith("TEST_"):
            keep.append(s)
    return "\n".join(keep)


def record(results, name, ok, detail):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name)
    if detail:
        print(detail)


def run(argv, env=None):
    proc = subprocess.run(argv, env=env or os.environ.copy(), capture_output=True, text=True, timeout=30)
    return proc.returncode, sanitize((proc.stdout or "") + "\n" + (proc.stderr or ""))


def main() -> int:
    results = []

    # Production observation reproduced without SET.
    reason = guards.check_timeouts("0", "2min", "0")
    klass = guards.classify_startup_options("0", "2min", "0")
    record(
        results,
        "observed_prod_show_without_set",
        reason == "lock_timeout_not_15s" and klass == "startup_options_not_honored",
        f"TEST_REASON={reason}\nTEST_CLASS={klass}",
    )

    rc, text = run(["python3", str(HERE / "pr188_gate_e3_guards.py"), "timeouts", "0", "2min", "0"])
    record(
        results,
        "guards_cli_matches_prod_precheck_fail",
        rc != 0 and "E3_REASON=lock_timeout_not_15s" in text,
        text + f"\nTEST_EXIT={rc}",
    )

    rc, text = run(
        ["python3", str(HERE / "pr188_gate_e3_guards.py"), "classify-startup", "0", "2min", "0"]
    )
    record(
        results,
        "guards_cli_classify_startup_not_honored",
        rc == 0 and "E3_STARTUP_OPTIONS=startup_options_not_honored" in text,
        text + f"\nTEST_EXIT={rc}",
    )

    conn = FakeConn(apply_set=True)
    shown = guards.apply_timeouts_dbapi(conn)
    record(
        results,
        "session_set_then_show_applies_all_three",
        shown["lock_timeout"] == "15s"
        and shown["idle_in_transaction_session_timeout"] == "60s"
        and guards.check_timeouts(
            shown["lock_timeout"], shown["statement_timeout"], shown["idle_in_transaction_session_timeout"]
        )
        is None,
        f"TEST_SHOWN={shown}",
    )

    conn2 = FakeConn(apply_set=True, show_120s_as_2min=True)
    shown2 = guards.apply_timeouts_dbapi(conn2)
    record(
        results,
        "session_set_120s_may_display_as_2min",
        shown2["statement_timeout"] == "2min"
        and guards.check_timeouts("15s", "2min", "60s") is None,
        f"TEST_SHOWN={shown2}",
    )

    conn3 = FakeConn(apply_set=False)
    raised = None
    try:
        guards.apply_timeouts_dbapi(conn3)
    except guards.TimeoutNotApplied as exc:
        raised = exc.reason
    record(
        results,
        "set_noop_still_fails_closed",
        raised == "lock_timeout_not_15s" and conn3.gucs == dict(guards.OBSERVED_POOLER_DEFAULTS),
        f"TEST_RAISED={raised}",
    )

    # urlencode of options uses + for spaces; pooler may also drop options entirely.
    raw = "postgresql://u@db.example.supabase.co:5432/postgres?sslmode=require"
    u = urlsplit(raw)
    q = dict(parse_qsl(u.query, keep_blank_values=True))
    q["options"] = "-c lock_timeout=15s -c statement_timeout=120s -c idle_in_transaction_session_timeout=60s"
    encoded = urlunsplit((u.scheme, u.netloc, u.path, urlencode(q), u.fragment))
    record(
        results,
        "urlencode_options_uses_plus_for_spaces",
        "options=" in encoded and "+" in encoded.split("options=", 1)[1],
        "TEST_ENCODED_HAS_PLUS=yes",
    )

    rc, text = run(["python3", str(HERE / "pr188_gate_e3_alembic_upgrade.py")])
    record(
        results,
        "wrapper_missing_target_no_upgrade",
        rc != 0 and "E3_REASON=alembic_target_not_0027" in text,
        text + f"\nTEST_EXIT={rc}",
    )
    rc, text = run(["python3", str(HERE / "pr188_gate_e3_alembic_upgrade.py"), "head"])
    record(
        results,
        "wrapper_rejects_upgrade_head",
        rc != 0 and "E3_REASON=alembic_target_not_0027" in text,
        text + f"\nTEST_EXIT={rc}",
    )
    env = os.environ.copy()
    env.pop("E3_WORKTREE", None)
    env["DATABASE_URL"] = "postgresql://u@host:5432/postgres?sslmode=require"
    rc, text = run(["python3", str(HERE / "pr188_gate_e3_alembic_upgrade.py"), "20260927_0027"], env=env)
    record(
        results,
        "wrapper_missing_worktree_no_upgrade",
        rc != 0 and "E3_REASON=e3_worktree_missing" in text,
        text + f"\nTEST_EXIT={rc}",
    )

    env = os.environ.copy()
    env.pop("GATE_E3_UPGRADE_CONFIRM", None)
    rc, text = run(["zsh", str(UPGRADE)], env=env)
    record(
        results,
        "missing_confirmation_token",
        rc != 0 and "E3_REASON=missing_or_wrong_confirm_token_upgrade_not_run" in text,
        text + f"\nTEST_EXIT={rc}",
    )

    with tempfile.TemporaryDirectory(prefix="e3v3_sha_") as td:
        home = Path(td) / "home"
        home.mkdir()
        age = home / f"recall_prod_gate_e2_{E2_STAMP}.tar.age"
        age.write_bytes(b"not-the-closed-e2-archive")
        os.chmod(age, 0o600)
        env = os.environ.copy()
        env["HOME"] = str(home)
        env["GATE_E3_UPGRADE_CONFIRM"] = CONFIRM
        env["E3_RAILWAY_CONFIRM"] = RAILWAY
        rc, text = run(["zsh", str(UPGRADE), "/tmp/not-a-repo"], env=env)
        record(
            results,
            "upgrade_wrong_age_sha_before_dsn",
            rc != 0
            and "E3_REASON=e2_age_sha_mismatch" in text
            and "E3_CONFIRM_TOKEN=accepted" in text,
            text + f"\nTEST_EXIT={rc}",
        )

    rc, text = run(["python3", str(HERE / "pr188_gate_e3_guards.py"), "recency", "20200101T000000Z", "12"])
    record(
        results,
        "stale_backup_rejected",
        rc != 0 and "E3_REASON=e2_backup_too_old_refresh_required" in text,
        text + f"\nTEST_EXIT={rc}",
    )

    failed = [r for r in results if not r[1]]
    print(f"TEST_SUMMARY total={len(results)} passed={len(results)-len(failed)} failed={len(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
