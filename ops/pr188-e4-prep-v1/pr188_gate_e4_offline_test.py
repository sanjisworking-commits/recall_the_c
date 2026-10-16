#!/usr/bin/env python3
# REVISION=e4_prep_v1_20261016
"""Offline tests for Gate E4 now/verify fail-closed boundaries. No production."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pr188_gate_e4 as runner  # noqa: E402
import pr188_gate_e4_guards as g  # noqa: E402

NOW = HERE / "gate_e4_now.zsh"
VERIFY = HERE / "gate_e4_verify.zsh"


def sanitize(text: str) -> str:
    keep = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("E4_") or s.startswith("TEST_"):
            keep.append(s)
    return "\n".join(keep)


def record(results, name, ok, detail):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name)
    if detail:
        print(detail)


def run(argv, env=None):
    proc = subprocess.run(argv, env=env or os.environ.copy(), capture_output=True, text=True, timeout=20)
    return proc.returncode, sanitize((proc.stdout or "") + "\n" + (proc.stderr or ""))


def main() -> int:
    results = []

    rc, text = run(["zsh", str(NOW)])
    record(
        results,
        "now_missing_confirm",
        rc != 0 and "E4_REASON=missing_or_wrong_e4_now_confirm" in text,
        text + f"\nTEST_EXIT={rc}",
    )

    env = os.environ.copy()
    env["GATE_E4_NOW_CONFIRM"] = g.NOW_CONFIRM
    env.pop("E4_RAILWAY_CONFIRM", None)
    rc, text = run(["zsh", str(NOW)], env=env)
    record(
        results,
        "now_missing_railway_confirm",
        rc != 0 and "E4_REASON=railway_operator_confirm_missing" in text,
        text + f"\nTEST_EXIT={rc}",
    )

    rc, text = run(["zsh", str(VERIFY)])
    record(
        results,
        "verify_missing_confirm",
        rc != 0 and "E4_REASON=missing_or_wrong_e4_verify_confirm" in text,
        text + f"\nTEST_EXIT={rc}",
    )

    env = os.environ.copy()
    env["GATE_E4_VERIFY_CONFIRM"] = g.VERIFY_CONFIRM
    env["E4_RAILWAY_CONFIRM"] = g.RAILWAY_EXPECT
    rc, text = run(["zsh", str(VERIFY)], env=env)
    record(
        results,
        "verify_cloud_workspace_forbidden",
        rc != 0 and "E4_REASON=cloud_workspace_forbidden_use_mac" in text,
        text + f"\nTEST_EXIT={rc}",
    )

    env = os.environ.copy()
    env["GATE_E4_NOW_CONFIRM"] = g.NOW_CONFIRM
    env["E4_RAILWAY_CONFIRM"] = g.RAILWAY_EXPECT
    rc, text = run(["zsh", str(NOW)], env=env)
    record(
        results,
        "now_cloud_workspace_forbidden",
        rc != 0 and "E4_REASON=cloud_workspace_forbidden_use_mac" in text,
        text + f"\nTEST_EXIT={rc}",
    )

    rc, text = run(["python3", str(HERE / "pr188_gate_e4.py")])
    record(
        results,
        "runner_usage",
        rc != 0 and "E4_REASON=e4_usage_now_or_verify" in text,
        text + f"\nTEST_EXIT={rc}",
    )

    blockers = g.check_identity_common(
        "on", "5432", g.START_REV, g.HEAD_REV,
        "1", True, True, "t", "t", "t", "t", "t", "0", "0",
    )
    record(
        results,
        "verify_identity_fails_closed_on_0016",
        blockers == ["alembic_not_0027"],
        f"TEST_BLOCKERS={blockers}",
    )

    blockers_now = g.check_identity_common(
        "on", "5432", g.HEAD_REV, g.START_REV,
        "1", True, True, "t", "t", "t", "t", "t", "0", "0",
    )
    record(
        results,
        "now_identity_fails_closed_on_0027",
        blockers_now == ["alembic_not_0016"],
        f"TEST_BLOCKERS={blockers_now}",
    )

    base = {n: 10 for n in g.LEGACY_TABLES}
    live_inc = dict(base)
    live_inc["app_session"] = 12
    inc, dec = g.count_deltas(base, live_inc)
    record(
        results,
        "legacy_increase_not_fail",
        inc == ["app_session:10->12"] and dec == [],
        f"TEST_INC={inc}\nTEST_DEC={dec}",
    )
    live_dec = dict(base)
    live_dec["user_profile"] = 9
    inc2, dec2 = g.count_deltas(base, live_dec)
    record(
        results,
        "legacy_decrease_is_fail_signal",
        dec2 == ["user_profile:10->9"] and inc2 == [],
        f"TEST_INC={inc2}\nTEST_DEC={dec2}",
    )

    ok_priv = g.new_table_priv_reason(
        "user_subscription", "postgres", "postgres", "t", "f", "t", "t", "t", "t", "0", "0"
    )
    record(results, "new_table_privs_ok", ok_priv is None, f"TEST_REASON={ok_priv}")
    bad_rls = g.new_table_priv_reason(
        "user_subscription", "postgres", "postgres", "f", "f", "t", "t", "t", "t", "0", "0"
    )
    record(
        results,
        "new_table_rls_off_fails",
        bad_rls == "new_table_rls_off:user_subscription",
        f"TEST_REASON={bad_rls}",
    )
    bad_rows = g.new_table_priv_reason(
        "user_device", "postgres", "postgres", "t", "f", "t", "t", "t", "t", "0", "3"
    )
    record(
        results,
        "new_table_nonzero_rows_fails",
        bad_rows == "new_table_nonzero_rows:user_device",
        f"TEST_REASON={bad_rows}",
    )
    bad_pol = g.new_table_priv_reason(
        "user_device", "postgres", "postgres", "t", "f", "t", "t", "t", "t", "1", "0"
    )
    record(
        results,
        "new_table_unexpected_policy_fails",
        bad_pol == "new_table_unexpected_policies:user_device",
        f"TEST_REASON={bad_pol}",
    )

    record(results, "ios_platform_check", g.ios_in_platform_check("CHECK (platform IN ('web', 'android', 'ios'))"), "")
    record(results, "ios_platform_check_missing", not g.ios_in_platform_check("CHECK (platform IN ('web', 'android'))"), "")

    try:
        g.check_http_base("https://recall-the-c.in")
        http_ok = True
        http_reason = None
    except g.E4Fail as exc:
        http_ok = False
        http_reason = exc.reason
    record(results, "http_base_allowed", http_ok, f"TEST_REASON={http_reason}")
    try:
        g.check_http_base("http://127.0.0.1:8000")
        loc_ok, loc_reason = True, None
    except g.E4Fail as exc:
        loc_ok, loc_reason = False, exc.reason
    record(
        results,
        "http_base_rejects_localhost",
        (not loc_ok) and loc_reason == "http_base_not_recall_the_c_in",
        f"TEST_REASON={loc_reason}",
    )
    try:
        g.check_http_base("https://recall-th-c-recallthec-pr-188.up.railway.app")
        pr_ok, pr_reason = True, None
    except g.E4Fail as exc:
        pr_ok, pr_reason = False, exc.reason
    record(
        results,
        "http_base_rejects_pr188_preview",
        (not pr_ok) and pr_reason == "http_base_not_recall_the_c_in",
        f"TEST_REASON={pr_reason}",
    )

    record(
        results,
        "health_ok",
        g.interpret_health(200, '{"status":"ok"}') is None,
        "",
    )
    record(
        results,
        "playground_404_ok",
        g.interpret_playground(404, '{"detail":"Not Found"}') is None,
        "",
    )
    record(
        results,
        "playground_head_ui_fails",
        g.interpret_playground(200, "<title>Sign in to use Playground</title>")
        == "playground_head_ui_not_old_app_404",
        "",
    )
    record(
        results,
        "learn_5xx_fails",
        g.interpret_learn(500) == "learn_5xx",
        "",
    )

    now_sql = runner.sql_now().upper()
    ver_sql = runner.sql_verify().upper()
    record(
        results,
        "sql_now_read_only_no_writes",
        now_sql.startswith("BEGIN READ ONLY")
        and "GRANT " not in now_sql
        and "ALTER TABLE" not in now_sql
        and "INSERT INTO" not in now_sql
        and "UPDATE " not in now_sql
        and "DROP TABLE" not in now_sql
        and "ALEMBIC UPGRADE" not in now_sql,
        "",
    )
    record(
        results,
        "sql_verify_read_only_no_writes",
        ver_sql.startswith("BEGIN READ ONLY")
        and "GRANT " not in ver_sql
        and "ALTER TABLE" not in ver_sql
        and "INSERT INTO" not in ver_sql
        and "DROP TABLE" not in ver_sql
        and "ALEMBIC UPGRADE" not in ver_sql
        and "LIMIT 0" in ver_sql,
        "",
    )

    now_txt = NOW.read_text(encoding="utf-8")
    ver_txt = VERIFY.read_text(encoding="utf-8")
    py_txt = (HERE / "pr188_gate_e4.py").read_text(encoding="utf-8")
    record(
        results,
        "scripts_have_revision_marker",
        "REVISION=e4_prep_v1_20261016" in now_txt
        and "REVISION=e4_prep_v1_20261016" in ver_txt
        and "REVISION=e4_prep_v1_20261016" in py_txt,
        "",
    )
    record(
        results,
        "fifteen_new_tables_frozen",
        g.NEW_TABLES == [
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
        and len(g.NEW_TABLES) == 15
        and len(g.LEGACY_TABLES) == 9,
        f"TEST_NEW={len(g.NEW_TABLES)}",
    )
    combined = now_txt + ver_txt + py_txt
    record(
        results,
        "no_alembic_upgrade_invocation",
        "alembic upgrade" not in combined.lower()
        and "railway variables" not in combined.lower()
        and "gh pr merge" not in combined.lower(),
        "",
    )

    try:
        g.guard_dsn(
            "postgresql://u:secret@db.example.supabase.co:5432/postgres?sslmode=require",
            "exampleref",
            "postgres",
        )
        pw_ok, pw_reason = True, None
    except g.E4Fail as exc:
        pw_ok, pw_reason = False, exc.reason
    record(
        results,
        "dsn_rejects_password_in_url",
        (not pw_ok) and pw_reason == "password_bearing_url_forbidden",
        f"TEST_REASON={pw_reason}",
    )
    try:
        g.guard_dsn(
            "postgresql://u@db.example.supabase.co:6543/postgres?sslmode=require",
            "exampleref",
            "postgres",
        )
        p_ok, p_reason = True, None
    except g.E4Fail as exc:
        p_ok, p_reason = False, exc.reason
    record(
        results,
        "dsn_rejects_6543",
        (not p_ok) and p_reason == "transaction_pooler_port_6543",
        f"TEST_REASON={p_reason}",
    )

    failed = [r for r in results if not r[1]]
    print(f"TEST_SUMMARY total={len(results)} passed={len(results)-len(failed)} failed={len(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
