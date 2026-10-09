"""WS6 / execution T13 benchmark harness tests. No duration assertions."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from constitution_memorizer.playground.benchmarking import (
    APP_ENV_TEST_REQUIRED,
    BENCH_USER,
    BNSS_LEARN_MODE,
    BNSS_LEARN_PATH,
    BNSS_PUBLIC_PATH,
    BNSS_WORKSPACE_PATH,
    DEFAULT_BNSS_JSON_PATH,
    DEFAULT_JSON_PATH,
    ELIGIBLE_LAWS,
    PROTOCOL_BNSS_COLD_WARM,
    SCENARIO_BUILDERS,
    SCENARIOS,
    BenchmarkAborted,
    BenchmarkRunConfig,
    assert_cache_class,
    assert_fresh_sqlite,
    bnss_cell_report,
    build_arg_parser,
    classify_cache_snapshot,
    collect_snapshots,
    config_from_args,
    create_benchmark_app,
    evaluate_safety_guard,
    host_is_production_looking,
    largest_eligible_runtime_act,
    percentile_nearest_rank,
    resolve_database_url,
    run_bnss_cold_warm,
    seed_scenario,
    snapshots_to_report,
    sqlite_filesystem_path,
    summarize_numbers,
    synthetic_law_ids,
)
from constitution_memorizer.playground.roster.period import playground_month_bounds

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "benchmark_playground.py"


def _env_without_db(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env.update(extra)
    return env


def test_percentile_nearest_rank_golden():
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert percentile_nearest_rank(values, 50) == 5
    assert percentile_nearest_rank(values, 95) == 10
    assert percentile_nearest_rank(values, 99) == 10


def test_summarize_numbers_includes_required_keys():
    summary = summarize_numbers([2, 4, 6, 8, 10])
    assert summary["count"] == 5
    assert summary["min"] == 2
    assert summary["max"] == 10
    assert set(summary) == {"count", "min", "mean", "p50", "p95", "p99", "max"}


def test_cli_help_subprocess():
    proc = subprocess.run(
        [sys.executable, str(CLI), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    text = proc.stdout
    for flag in (
        "--scenario",
        "--database-url",
        "--app-env",
        "--quick",
        "--json",
        "--explain",
        "--i-accept-nontest-db",
        "--warmup",
        "--iterations",
        "--protocol",
    ):
        assert flag in text
    assert PROTOCOL_BNSS_COLD_WARM in text


def test_app_env_test_is_accepted():
    assert (
        evaluate_safety_guard(
            requested_app_env="test",
            accept_nontest=False,
            explain=False,
            environ={"APP_ENV": "test"},
        )
        == "test"
    )


@pytest.mark.parametrize("value", ["development", "unknown", "prod"])
def test_app_env_nontest_without_allow_is_rejected(value: str):
    with pytest.raises(BenchmarkAborted, match="--app-env test is required"):
        evaluate_safety_guard(
            requested_app_env=value,
            accept_nontest=False,
            explain=False,
            environ={"APP_ENV": "test"},
        )


def test_app_env_development_with_allow_does_not_need_i_accept():
    assert (
        evaluate_safety_guard(
            requested_app_env="development",
            accept_nontest=False,
            explain=False,
            environ={"APP_ENV": "test", "BENCHMARK_ALLOW_NONTEST": "1"},
        )
        == "development"
    )


def test_production_app_env_aborts_without_override():
    with pytest.raises(BenchmarkAborted, match="refusing staging/production"):
        evaluate_safety_guard(
            requested_app_env="test",
            accept_nontest=False,
            explain=False,
            environ={"APP_ENV": "production"},
        )


def test_requested_production_app_env_aborts():
    with pytest.raises(BenchmarkAborted, match="refusing staging/production"):
        evaluate_safety_guard(
            requested_app_env="production",
            accept_nontest=False,
            explain=False,
            environ={"APP_ENV": "test"},
        )


def test_allow_nontest_without_accept_flag_still_aborts():
    with pytest.raises(BenchmarkAborted, match="refusing staging/production"):
        evaluate_safety_guard(
            requested_app_env="test",
            accept_nontest=False,
            explain=False,
            environ={"APP_ENV": "production", "BENCHMARK_ALLOW_NONTEST": "1"},
        )


def test_production_looking_base_url_aborts_even_with_app_env_test():
    with pytest.raises(BenchmarkAborted, match="production-looking"):
        evaluate_safety_guard(
            requested_app_env="test",
            accept_nontest=False,
            explain=False,
            environ={
                "APP_ENV": "test",
                "APP_BASE_URL": "https://app.recall-the-c.in",
            },
        )


@pytest.mark.parametrize("value", ["staging", "production"])
def test_requested_staging_production_need_dual_consent(value: str):
    with pytest.raises(BenchmarkAborted, match="refusing staging/production"):
        evaluate_safety_guard(
            requested_app_env=value,
            accept_nontest=False,
            explain=False,
            environ={"APP_ENV": "test", "BENCHMARK_ALLOW_NONTEST": "1"},
        )
    assert (
        evaluate_safety_guard(
            requested_app_env=value,
            accept_nontest=True,
            explain=False,
            environ={"APP_ENV": "test", "BENCHMARK_ALLOW_NONTEST": "1"},
        )
        == value
    )


def test_process_production_not_masked_by_app_env_test_even_with_consent():
    assert (
        evaluate_safety_guard(
            requested_app_env="test",
            accept_nontest=True,
            explain=False,
            environ={"APP_ENV": "production", "BENCHMARK_ALLOW_NONTEST": "1"},
        )
        == "production"
    )


def test_cli_development_abort_subprocess():
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--scenario",
            "plus-10",
            "--database-url",
            "sqlite:///unused.db",
            "--app-env",
            "development",
            "--quick",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=_env_without_db(APP_ENV="test"),
    )
    assert proc.returncode == 1
    assert APP_ENV_TEST_REQUIRED in proc.stderr


def test_cli_production_abort_subprocess():
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--scenario",
            "plus-10",
            "--database-url",
            "sqlite:///unused.db",
            "--app-env",
            "test",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=_env_without_db(APP_ENV="production"),
    )
    assert proc.returncode == 1
    assert "refusing" in proc.stderr.lower() or "production" in proc.stderr.lower()


def test_explain_aborts_before_database_url():
    args = build_arg_parser().parse_args(
        ["--scenario", "plus-10", "--explain", "--app-env", "test"]
    )
    with pytest.raises(BenchmarkAborted, match="T15"):
        config_from_args(args, environ={})


def test_missing_database_url_does_not_use_process_database_url():
    with pytest.raises(BenchmarkAborted, match="never process DATABASE_URL"):
        resolve_database_url(None, environ={"DATABASE_URL": "sqlite:///secret.db"})


def test_quick_overrides_warmup_and_iterations():
    args = build_arg_parser().parse_args(
        [
            "--scenario",
            "plus-10",
            "--database-url",
            "sqlite:///fresh.db",
            "--app-env",
            "test",
            "--warmup",
            "9",
            "--iterations",
            "40",
            "--quick",
        ]
    )
    config = config_from_args(args, environ={})
    assert config.warmup == 1
    assert config.iterations == 3
    assert config.protocol is None
    assert config.json_path == DEFAULT_JSON_PATH


def test_host_match_uses_dns_label_boundaries():
    assert host_is_production_looking("recall-the-c.in")
    assert host_is_production_looking("www.recallthec.in")
    assert host_is_production_looking("APP.RECALL-THE-C.IN")
    assert not host_is_production_looking("notrecall-the-c.in")
    assert not host_is_production_looking("recall-the-c.in.attacker.example")
    assert not host_is_production_looking("example.com")


def test_sqlite_path_and_nonempty_refusal(tmp_path: Path):
    empty = tmp_path / "empty.db"
    assert sqlite_filesystem_path(f"sqlite:///{empty}") == empty
    abs_url = "sqlite:////tmp/t13-abs.db"
    assert sqlite_filesystem_path(abs_url) == Path("/tmp/t13-abs.db")
    missing = tmp_path / "missing.db"
    assert assert_fresh_sqlite(f"sqlite:///{missing}") == missing
    nonempty = tmp_path / "has-data.db"
    nonempty.write_bytes(b"not-empty")
    with pytest.raises(BenchmarkAborted, match="nonempty"):
        assert_fresh_sqlite(f"sqlite:///{nonempty}")


def test_postgres_url_refused():
    with pytest.raises(BenchmarkAborted, match="T15"):
        sqlite_filesystem_path("postgresql://localhost/recall")


def test_collect_snapshots_aborts_on_non_2xx():
    calls = {"n": 0}

    def request():
        calls["n"] += 1
        return SimpleNamespace(status_code=500)

    with pytest.raises(BenchmarkAborted, match="HTTP 500"):
        collect_snapshots(request, warmup=0, iterations=1)
    assert calls["n"] == 1


def test_all_six_scenario_builders_exist():
    assert tuple(SCENARIO_BUILDERS) == SCENARIOS


def _count_roster(app) -> int:
    start, _end = playground_month_bounds()
    return len(app.state.roster._repo.list_items(BENCH_USER, start))


def test_plus_10_builder_ten_rows_without_hydration(tmp_path: Path):
    db = tmp_path / "plus10.db"
    app = create_benchmark_app(db)
    info = seed_scenario(app, "plus-10")
    assert info["roster_count"] == 10
    assert _count_roster(app) == 10
    ids = set(info["law_ids"])
    assert set(ELIGIBLE_LAWS).issubset(ids)
    assert set(synthetic_law_ids(4)).issubset(ids)


def test_pro_30_builder_thirty_rows_without_hydration(tmp_path: Path):
    db = tmp_path / "pro30.db"
    app = create_benchmark_app(db)
    info = seed_scenario(app, "pro-30")
    assert info["roster_count"] == 30
    assert _count_roster(app) == 30
    assert set(synthetic_law_ids(24)).issubset(set(info["law_ids"]))


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_remaining_builders_do_not_hydrate(tmp_path: Path, scenario: str):
    db = tmp_path / f"{scenario}.db"
    app = create_benchmark_app(db)
    info = seed_scenario(app, scenario)
    assert info["roster_count"] >= 1
    assert _count_roster(app) == info["roster_count"]


def test_json_report_has_distributions_and_no_email():
    snap = SimpleNamespace(
        path_group="/playground",
        method="GET",
        status_code=200,
        total_ms=3.0,
        timings={"playground_home_build": (1.5, 1), "template": (0.4, 1)},
        counters={"playground_repo_round_trips": 9, "playground_db_reads": 7},
        notes={
            "playground_access_result": "allowed",
            "auth_state": "authed",
            "email": "bench@example.invalid",
        },
    )
    payload = snapshots_to_report(
        [snap, snap],
        scenario="plus-10",
        warmup=1,
        iterations=2,
        method="GET",
    )
    assert payload["schema_version"] == 1
    for key in ("total_ms", "playground_repo_round_trips", "playground_db_reads"):
        stats = payload["metrics"][key]
        assert set(stats) == {"count", "min", "mean", "p50", "p95", "p99", "max"}
    assert "playground_home_build" in payload["metrics"]
    assert "template" in payload["metrics"]
    blob = json.dumps(payload)
    assert "bench@example.invalid" not in blob
    assert "email" not in payload.get("notes_observed", {})
    assert payload["notes_observed"]["playground_access_result"] == ["allowed"]
    assert payload["app_env"] == "test"


def test_json_app_env_uses_validated_label():
    snap = SimpleNamespace(
        path_group="/playground",
        method="GET",
        status_code=200,
        total_ms=1.0,
        timings={},
        counters={"playground_repo_round_trips": 1, "playground_db_reads": 1},
        notes={},
    )
    payload = snapshots_to_report(
        [snap],
        scenario="plus-10",
        warmup=0,
        iterations=1,
        method="GET",
        app_env="development",
    )
    assert payload["app_env"] == "development"


def test_absent_stage_zero_means_not_executed():
    present = SimpleNamespace(
        path_group="/playground",
        method="GET",
        status_code=200,
        total_ms=2.0,
        timings={"template": (1.0, 1), "playground_home_build": (2.0, 1)},
        counters={"playground_repo_round_trips": 1, "playground_db_reads": 1},
        notes={},
    )
    absent = SimpleNamespace(
        path_group="/playground",
        method="GET",
        status_code=200,
        total_ms=1.0,
        timings={"template": (1.0, 1)},
        counters={"playground_repo_round_trips": 1, "playground_db_reads": 1},
        notes={},
    )
    payload = snapshots_to_report(
        [present, absent],
        scenario="plus-10",
        warmup=0,
        iterations=2,
        method="GET",
    )
    home = payload["metrics"]["playground_home_build"]
    assert home["count"] == 2
    assert home["min"] == 0.0
    assert home["max"] == 2.0
    assert payload["metrics"]["template"]["min"] == 1.0


def test_user_id_constant_is_uuid():
    assert isinstance(BENCH_USER, UUID)


def _cache_snap(
    *,
    cache: str | None,
    misses: int,
    load: bool,
    path_group: str = "/playground/laws/{law_id}",
):
    timings = {"template": (1.0, 1)}
    if load:
        timings["bare_act_load"] = (9.0, 1)
    notes = {}
    if cache is not None:
        notes["bare_act_cache"] = cache
    return SimpleNamespace(
        path_group=path_group,
        method="GET",
        status_code=200,
        total_ms=5.0,
        timings=timings,
        counters={
            "playground_repo_round_trips": 1,
            "playground_db_reads": 1,
            "bare_act_cache_misses": misses,
        },
        notes=notes,
    )


def test_classify_cache_snapshot_miss_and_hit():
    miss = _cache_snap(cache="miss", misses=1, load=True)
    hit = _cache_snap(cache="hit", misses=0, load=False)
    mixed = _cache_snap(cache="hit", misses=1, load=True)
    assert classify_cache_snapshot(miss) == "miss"
    assert classify_cache_snapshot(hit) == "hit"
    assert classify_cache_snapshot(mixed) == "unknown"


def test_assert_cache_class_rejects_contamination():
    miss = _cache_snap(cache="miss", misses=1, load=True)
    hit = _cache_snap(cache="hit", misses=0, load=False)
    assert_cache_class([miss], "miss", label="cold")
    assert_cache_class([hit], "hit", label="warm")
    with pytest.raises(BenchmarkAborted, match="expected 'miss'"):
        assert_cache_class([hit], "miss", label="cold")
    with pytest.raises(BenchmarkAborted, match="expected 'hit'"):
        assert_cache_class([miss], "hit", label="warm")


def test_bnss_cell_report_refuses_mixed_and_omits_warm_load():
    path_group = "/playground/laws/{law_id}"
    miss = _cache_snap(cache="miss", misses=1, load=True, path_group=path_group)
    hit = _cache_snap(cache="hit", misses=0, load=False, path_group=path_group)
    with pytest.raises(BenchmarkAborted, match="expected 'miss'"):
        bnss_cell_report(
            [miss, hit],
            expected="miss",
            warmup=0,
            iterations=2,
            method="GET",
            app_env="test",
            label="cold",
            path_group=path_group,
        )
    warm = bnss_cell_report(
        [hit, hit],
        expected="hit",
        warmup=1,
        iterations=2,
        method="GET",
        app_env="test",
        label="warm",
        path_group=path_group,
    )
    assert "bare_act_load" not in warm["stages_present"]
    assert "bare_act_load" not in warm["metrics"]
    assert warm["cache_evidence"]["cache_class"] == "hit"
    assert warm["cache_evidence"]["bare_act_load_present_count"] == 0
    cold = bnss_cell_report(
        [miss, miss],
        expected="miss",
        warmup=0,
        iterations=2,
        method="GET",
        app_env="test",
        label="cold",
        path_group=path_group,
    )
    assert "bare_act_load" in cold["stages_present"]
    assert cold["cache_evidence"]["bare_act_load_absent_count"] == 0


def test_protocol_requires_law_workspace_scenario():
    args = build_arg_parser().parse_args(
        [
            "--protocol",
            PROTOCOL_BNSS_COLD_WARM,
            "--scenario",
            "plus-10",
            "--database-url",
            "sqlite:///fresh.db",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="law-workspace"):
        config_from_args(args, environ={})


def test_protocol_defaults_scenario_and_json_path():
    args = build_arg_parser().parse_args(
        [
            "--protocol",
            PROTOCOL_BNSS_COLD_WARM,
            "--database-url",
            "sqlite:///fresh.db",
            "--app-env",
            "test",
            "--quick",
        ]
    )
    config = config_from_args(args, environ={})
    assert config.scenario == "law-workspace"
    assert config.protocol == PROTOCOL_BNSS_COLD_WARM
    assert config.warmup == 1
    assert config.iterations == 3
    assert config.json_path == DEFAULT_BNSS_JSON_PATH


def test_protocol_cli_plus_10_aborts_subprocess():
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--protocol",
            PROTOCOL_BNSS_COLD_WARM,
            "--scenario",
            "plus-10",
            "--database-url",
            "sqlite:///unused.db",
            "--app-env",
            "test",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=_env_without_db(APP_ENV="test"),
    )
    assert proc.returncode == 1
    assert "law-workspace" in proc.stderr


def test_protocol_routes_are_bnss_read_only():
    assert BNSS_WORKSPACE_PATH == "/playground/laws/bnss"
    assert BNSS_LEARN_PATH == "/playground/laws/bnss/sections/1/learn/read"
    assert BNSS_PUBLIC_PATH == "/laws/bnss"
    assert BNSS_LEARN_MODE == "read"
    assert "cloze" not in BNSS_LEARN_PATH
    for path in (BNSS_WORKSPACE_PATH, BNSS_LEARN_PATH, BNSS_PUBLIC_PATH):
        assert "/bnss" in path


def test_largest_eligible_runtime_act_is_bnss():
    from constitution_memorizer.playground.benchmarking import HydrationProbe

    probe = HydrationProbe()
    probe.install()
    try:
        info = largest_eligible_runtime_act()
    finally:
        probe.remove()
    assert probe.calls == 0
    assert info["slug"] == "bnss"
    assert info["filename"] == "bnss_runtime_v1.json"
    assert info["confirmed_largest_eligible"] is True
    assert info["bytes"] > 0


def test_bnss_get_bare_act_miss_then_hit():
    from constitution_memorizer.web.bare_acts import clear_bare_act_cache, get_bare_act
    from constitution_memorizer.web.request_context import (
        begin_request_timings,
        reset_request_timings,
        snapshot_request_counters,
        snapshot_request_notes,
        snapshot_request_timings,
    )

    clear_bare_act_cache()
    first = begin_request_timings()
    try:
        assert get_bare_act("bnss") is not None
        assert snapshot_request_notes()["bare_act_cache"] == "miss"
        assert snapshot_request_counters()["bare_act_cache_misses"] == 1
        assert "bare_act_load" in snapshot_request_timings()
    finally:
        reset_request_timings(first)
    second = begin_request_timings()
    try:
        assert get_bare_act("bnss") is not None
        assert snapshot_request_notes()["bare_act_cache"] == "hit"
        assert snapshot_request_counters().get("bare_act_cache_misses", 0) == 0
        assert "bare_act_load" not in snapshot_request_timings()
    finally:
        reset_request_timings(second)


def test_fresh_app_is_not_a_cold_load(tmp_path: Path):
    from constitution_memorizer.web.bare_acts import clear_bare_act_cache, get_bare_act
    from constitution_memorizer.web.request_context import (
        begin_request_timings,
        reset_request_timings,
        snapshot_request_notes,
        snapshot_request_timings,
    )

    clear_bare_act_cache()
    warmed = begin_request_timings()
    try:
        assert get_bare_act("bnss") is not None
        assert snapshot_request_notes()["bare_act_cache"] == "miss"
    finally:
        reset_request_timings(warmed)
    create_benchmark_app(tmp_path / "fresh-app.db")
    still_warm = begin_request_timings()
    try:
        assert get_bare_act("bnss") is not None
        assert snapshot_request_notes()["bare_act_cache"] == "hit"
        assert "bare_act_load" not in snapshot_request_timings()
    finally:
        reset_request_timings(still_warm)
    clear_bare_act_cache()
    after_clear = begin_request_timings()
    try:
        assert get_bare_act("bnss") is not None
        assert snapshot_request_notes()["bare_act_cache"] == "miss"
        assert "bare_act_load" in snapshot_request_timings()
    finally:
        reset_request_timings(after_clear)


def test_bnss_cold_warm_protocol_http_classifies_cells(tmp_path: Path):
    db = tmp_path / "t14.sqlite"
    report = tmp_path / "t14.json"
    config = BenchmarkRunConfig(
        scenario="law-workspace",
        warmup=0,
        iterations=1,
        database_url=f"sqlite:///{db}",
        app_env="test",
        json_path=report,
        explain=False,
        accept_nontest=False,
        protocol=PROTOCOL_BNSS_COLD_WARM,
    )
    payload = run_bnss_cold_warm(config, environ={"APP_ENV": "test"})
    assert payload["protocol"] == PROTOCOL_BNSS_COLD_WARM
    assert payload["largest_act"]["slug"] == "bnss"
    assert payload["learn_route"]["path"] == BNSS_LEARN_PATH
    assert payload["learn_route"]["mode"] == "read"
    assert set(payload["runs"]) == {
        "playground_workspace",
        "playground_learn",
        "public_bare_act",
    }
    for key, run in payload["runs"].items():
        cold = run["cold"]
        warm = run["warm"]
        assert cold["cache_evidence"]["cache_class"] == "miss"
        assert cold["cache_evidence"]["bare_act_load_present_count"] == 1
        assert cold["warmup_discarded"] == 0
        assert "bare_act_load" in cold["stages_present"]
        assert warm["cache_evidence"]["cache_class"] == "hit"
        assert warm["cache_evidence"]["bare_act_cache_misses_max"] == 0
        assert warm["cache_evidence"]["bare_act_load_present_count"] == 0
        assert "bare_act_load" not in warm["stages_present"]
        assert "bare_act_load" not in warm["metrics"]
    blob = report.read_text(encoding="utf-8")
    assert "bench@example.invalid" not in blob
    assert json.loads(blob)["runs"]["playground_learn"]["path"] == BNSS_LEARN_PATH


def test_cli_protocol_quick_smoke(tmp_path: Path):
    db = tmp_path / "t14-quick.sqlite"
    report = tmp_path / "t14-quick.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--scenario",
            "law-workspace",
            "--protocol",
            PROTOCOL_BNSS_COLD_WARM,
            "--quick",
            "--app-env",
            "test",
            "--database-url",
            f"sqlite:///{db}",
            "--json",
            str(report),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=_env_without_db(APP_ENV="test"),
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["protocol"] == PROTOCOL_BNSS_COLD_WARM
    learn_cold = payload["runs"]["playground_learn"]["cold"]
    learn_warm = payload["runs"]["playground_learn"]["warm"]
    assert learn_cold["iterations"] == 3
    assert learn_cold["warmup_discarded"] == 0
    assert learn_warm["iterations"] == 3
    assert learn_warm["warmup_discarded"] == 1
    assert learn_cold["cache_evidence"]["bare_act_load_present_count"] == 3
    assert learn_warm["cache_evidence"]["bare_act_load_present_count"] == 0
