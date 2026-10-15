#!/usr/bin/env python3
# REVISION=e3_prep_v3_1_20261015
"""Offline tests for E3 v3.1 timeout SET/SHOW, venv resolution, and fail-closed upgrade."""
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
PRECHECK = HERE / "gate_e3_precheck.zsh"
CONFIRM = guards.CONFIRM
RAILWAY = "trustworthy-embrace/env/recall-th-c/0c0a8d5/PLAYGROUND_ENABLED=false"
E2_STAMP = guards.E2_STAMP
E2_AGE_SHA = guards.E2_AGE_SHA
IDLE = 0
INTRANS = 2


class FakeInfo:
    def __init__(self, status: int = IDLE):
        self.transaction_status = status
        self.backend_pid = 0


class FakeConn:
    def __init__(
        self,
        apply_set: bool = True,
        show_120s_as_2min: bool = False,
        start_in_txn: bool = False,
    ):
        self.gucs = dict(guards.OBSERVED_POOLER_DEFAULTS)
        self.apply_set = apply_set
        self.show_120s_as_2min = show_120s_as_2min
        self.autocommit = False
        self.info = FakeInfo(INTRANS if start_in_txn else IDLE)

    def cursor(self):
        return FakeCursor(self)


class FakeCursor:
    def __init__(self, conn: FakeConn):
        self.conn = conn
        self._last = None

    def execute(self, sql, params=None):
        s = (sql or "").strip()
        upper = s.upper()
        if not self.conn.autocommit and self.conn.info.transaction_status == IDLE:
            if upper.startswith("SET ") or upper.startswith("SHOW "):
                self.conn.info.transaction_status = INTRANS
        if upper.startswith("SET "):
            rest = s[4:]
            name, _, val = rest.partition("=")
            name = name.strip()
            val = val.strip().strip("';")
            if self.conn.apply_set:
                if name == "statement_timeout" and val == "120s" and self.conn.show_120s_as_2min:
                    self.conn.gucs[name] = "2min"
                else:
                    self.conn.gucs[name] = val
            return
        if upper.startswith("SHOW "):
            name = s[5:].strip()
            self._last = (self.conn.gucs.get(name, "0"),)
            return
        raise AssertionError("unexpected sql: " + s)

    def fetchone(self):
        return self._last

    def close(self):
        return None


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


def _venv_block(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.index('REHEARSAL_SRC="${E3_REHEARSAL_SRC:-$HOME/recall_rehearsal_src}"')
    end = text.index('[[ -d "$REPO/.git" || -f "$REPO/.git" ]]')
    return text[start:end]


def zsh_venv_resolve(repo_arg: str, home: str, extra_env: dict | None = None) -> tuple[int, str]:
    block = _venv_block(UPGRADE)
    script = f"""
set -euo pipefail
abort() {{ print "E3_RESULT=FAIL"; print "E3_REASON=$1"; exit 1; }}
{block}
print "E3_REPO=$REPO"
print "E3_VENV_RESOLVED=$VENV"
print "E3_REHEARSAL_SRC=$REHEARSAL_SRC"
"""
    env = os.environ.copy()
    env["HOME"] = home
    env.pop("E3_REHEARSAL_SRC", None)
    env.pop("E3_REHEARSAL_VENV", None)
    env.pop("RECALL_THE_C_REPO", None)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        ["zsh", "-c", script, "--", repo_arg],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
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

    record(
        results,
        "session_set_leaves_idle_and_restores_autocommit",
        conn.autocommit is False
        and conn.info.transaction_status == IDLE
        and shown.get("transaction_status_after_set") == "idle",
        f"TEST_AUTOCOMMIT={conn.autocommit}\nTEST_TX={conn.info.transaction_status}",
    )

    conn2 = FakeConn(apply_set=True, show_120s_as_2min=True)
    shown2 = guards.apply_timeouts_dbapi(conn2)
    record(
        results,
        "session_set_120s_may_display_as_2min",
        shown2["statement_timeout"] == "2min"
        and guards.check_timeouts("15s", "2min", "60s") is None
        and conn2.info.transaction_status == IDLE,
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
        raised == "lock_timeout_not_15s"
        and conn3.gucs == dict(guards.OBSERVED_POOLER_DEFAULTS)
        and conn3.autocommit is False,
        f"TEST_RAISED={raised}",
    )

    raw_intrans = FakeConn()
    cur = raw_intrans.cursor()
    cur.execute("SET lock_timeout = '15s'")
    record(
        results,
        "set_without_autocommit_would_leave_intrans",
        raw_intrans.info.transaction_status == INTRANS and raw_intrans.autocommit is False,
        f"TEST_TX={raw_intrans.info.transaction_status}",
    )

    txn_conn = FakeConn(start_in_txn=True)
    txn_reason = None
    try:
        guards.apply_timeouts_dbapi(txn_conn)
    except guards.ConnectListenerTxnError as exc:
        txn_reason = exc.reason
    record(
        results,
        "apply_timeouts_refuses_open_transaction",
        txn_reason == "connect_listener_started_inside_open_transaction",
        f"TEST_RAISED={txn_reason}",
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

    with tempfile.TemporaryDirectory(prefix="e3v31_sha_") as td:
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

    pre_txt = PRECHECK.read_text(encoding="utf-8")
    up_txt = UPGRADE.read_text(encoding="utf-8")
    record(
        results,
        "scripts_do_not_use_repo_dot_venv",
        'VENV="$REPO/.venv-mig-rehearsal"' not in pre_txt
        and 'VENV="$REPO/.venv-mig-rehearsal"' not in up_txt
        and "HOME/recall_rehearsal_src" in pre_txt
        and "HOME/recall_rehearsal_src" in up_txt
        and "venv_resolved_from_dev_checkout" in pre_txt
        and "venv_resolved_from_dev_checkout" in up_txt,
        "TEST_VENV_ASSIGNMENT_FROM_REPO=no",
    )

    with tempfile.TemporaryDirectory(prefix="e3v31_venv_") as td:
        home = str(Path(td) / "home")
        os.mkdir(home)
        dev = str(Path(td) / "dev-checkout")
        os.mkdir(dev)
        os.mkdir(Path(dev) / ".venv-mig-rehearsal")
        rc, text = zsh_venv_resolve(dev, home)
        expected_venv = str(Path(home) / "recall_rehearsal_src" / ".venv-mig-rehearsal")
        record(
            results,
            "venv_resolves_to_home_rehearsal_not_dev_checkout",
            rc == 0
            and f"E3_VENV_RESOLVED={expected_venv}" in text
            and "E3_VENV_FROM_DEV_CHECKOUT=no" in text
            and f"E3_REPO={dev}" in text,
            text + f"\nTEST_EXIT={rc}\nTEST_EXPECTED_VENV={expected_venv}",
        )

        rc, text = zsh_venv_resolve(
            dev,
            home,
            extra_env={"E3_REHEARSAL_VENV": str(Path(dev) / ".venv-mig-rehearsal")},
        )
        record(
            results,
            "venv_override_inside_dev_checkout_fail_closed",
            rc != 0 and "E3_REASON=venv_resolved_from_dev_checkout" in text,
            text + f"\nTEST_EXIT={rc}",
        )

    failed = [r for r in results if not r[1]]
    print(f"TEST_SUMMARY total={len(results)} passed={len(results)-len(failed)} failed={len(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
