"""WS6 / WS7 / WS8 / WS9 / WS10 / WS11 (T13–T21) benchmark harness tests. No duration assertions."""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from constitution_memorizer.devices.postgres import PostgresDeviceRepository
from constitution_memorizer.playground.benchmarking import (
    APP_ENV_TEST_REQUIRED,
    BENCH_EMAIL,
    BENCH_USER,
    BNSS_LEARN_MODE,
    BNSS_LEARN_PATH,
    BNSS_PUBLIC_PATH,
    BNSS_WORKSPACE_PATH,
    DEFAULT_BNSS_JSON_PATH,
    DEFAULT_CONCURRENCY_BATCHES,
    DEFAULT_CONCURRENCY_JSON_PATH,
    DEFAULT_EXPLAIN_JSON_PATH,
    DEFAULT_JSON_PATH,
    DEFAULT_MUTATION_WAVES,
    DEFAULT_MUTATIONS_JSON_PATH,
    DEFAULT_PAGE_WEIGHT_JSON_PATH,
    DEFAULT_COLD_START_JSON_PATH,
    DEFAULT_WEBHOOKS_JSON_PATH,
    COLD_START_CHILD_TIMEOUT_S,
    COLD_START_MEASUREMENT_MODE,
    GZIP_COMPRESSLEVEL,
    PAGE_WEIGHT_MEASUREMENT_MODE,
    PAGE_WEIGHT_STATIC_DIR,
    WS11_NAMED_FILES,
    MAX_CONCURRENCY,
    ELIGIBLE_LAWS,
    EXPLAIN_QUERY_LABELS,
    NPLUSONE_LAW_LIMIT,
    NPLUSONE_LOCATORS_PER_LAW,
    NPLUSONE_ROSTER_SIZES,
    NPLUSONE_TIER,
    PLAYGROUND_TEST_NOW,
    PROTOCOL_BNSS_COLD_WARM,
    SCENARIO_BUILDERS,
    SCENARIOS,
    WEBHOOK_QUICK_M,
    WEBHOOK_QUICK_N,
    BenchmarkAborted,
    FakeProvider,
    BenchmarkRunConfig,
    ExplainCaptureConn,
    ExplainCaptureCursor,
    ExplainCapturePool,
    HydrationProbe,
    assert_cache_class,
    assert_concurrency_home_no_bare_act,
    assert_concurrency_sqlite,
    assert_concurrency_warm_workspace,
    assert_t19_sqlite,
    assert_t20_sqlite,
    assert_t21_sqlite,
    assert_disposable_postgres,
    assert_fresh_sqlite,
    assert_readonly_select,
    bnss_cell_report,
    build_arg_parser,
    build_nplusone_fixture,
    capture_explain_statements,
    classify_cache_snapshot,
    collect_snapshots,
    config_from_args,
    create_benchmark_app,
    dummy_device_key_hash,
    evaluate_explain_guard,
    evaluate_safety_guard,
    host_is_production_looking,
    largest_eligible_runtime_act,
    parse_concurrency_levels,
    parse_explain_text,
    percentile_nearest_rank,
    resolve_database_url,
    run_bnss_cold_warm,
    run_cold_start_benchmark,
    run_cold_start_self_test,
    spawn_cold_start_child,
    _assert_cold_start_json_safe,
    _cold_start_result_complete,
    MINI_UNITS,
    run_concurrent_batch,
    run_sequential_webhook_duplicate,
    run_single_mutation_wave,
    webhook_delivery_counts,
    first_party_page_weight_totals,
    gzip_equivalent_bytes,
    iter_html_assets,
    page_weight_catalog_key,
    resolve_static_disk_path,
    summarize_html_assets,
    ws11_named_file_inventory,
    _incomplete_page_row,
    sanitize_explain_text,
    seed_scenario,
    snapshots_to_report,
    sqlite_filesystem_path,
    summarize_numbers,
    synthetic_law_ids,
)
from constitution_memorizer.playground.postgres import PostgresPlaygroundRepository
from constitution_memorizer.playground.roster.postgres import PostgresRosterRepository
from constitution_memorizer.subscriptions.postgres import PostgresSubscriptionRepository
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
        "--concurrency",
        "--mutations",
        "--webhooks",
        "--cold-start",
    ):
        assert flag in text
    assert PROTOCOL_BNSS_COLD_WARM in text
    assert "refused until T15" not in text
    assert "disposable PostgreSQL EXPLAIN" in text


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
    with pytest.raises(BenchmarkAborted, match="never process DATABASE_URL"):
        config_from_args(
            args, environ={"DATABASE_URL": "postgresql://127.0.0.1/s2_0_explain"}
        )


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


@pytest.mark.parametrize("n", NPLUSONE_ROSTER_SIZES)
def test_nplusone_builder_matched_density_without_hydration(tmp_path: Path, n: int):
    db = tmp_path / f"nplusone-{n}.db"
    app = create_benchmark_app(db)
    probe = HydrationProbe()
    probe.install()
    try:
        info = build_nplusone_fixture(app, n)
    finally:
        probe.remove()
    assert probe.calls == 0
    assert info["tier"] == NPLUSONE_TIER
    assert info["law_limit"] == NPLUSONE_LAW_LIMIT
    assert info["roster_count"] == n
    assert _count_roster(app) == n
    assert info["law_ids"] == list(synthetic_law_ids(n))
    assert set(info["law_ids"]).isdisjoint(ELIGIBLE_LAWS)
    overlay = app.state.playground
    assert len(overlay.list_items(BENCH_USER)) == n
    due = overlay.list_due_revisions(
        BENCH_USER, PLAYGROUND_TEST_NOW.date(), list(info["law_ids"])
    )
    assert len(due) == n * NPLUSONE_LOCATORS_PER_LAW
    pending = overlay.list_source_changes(
        BENCH_USER, law_ids=list(info["law_ids"]), status="pending"
    )
    assert {row.law_id for row in pending} == set(info["law_ids"])
    assert "nplusone" not in SCENARIO_BUILDERS
    assert build_nplusone_fixture not in SCENARIO_BUILDERS.values()


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


EXPLAIN_CLI = ROOT / "scripts" / "explain_playground_queries.py"
SAMPLE_INDEX_PLAN = ROOT / "tests" / "fixtures" / "explain" / "sample_index_scan.txt"
SAMPLE_NESTED_PLAN = ROOT / "tests" / "fixtures" / "explain" / "sample_nested_loop_seq.txt"


def test_explain_sqlite_url_aborts():
    args = build_arg_parser().parse_args(
        [
            "--explain",
            "--scenario",
            "pro-30",
            "--app-env",
            "test",
            "--database-url",
            "sqlite:////tmp/x.sqlite",
        ]
    )
    config = config_from_args(args, environ={})
    with pytest.raises(BenchmarkAborted, match="not sqlite"):
        evaluate_explain_guard(
            requested_app_env=config.app_env,
            accept_nontest=False,
            database_url=config.database_url,
            environ={"APP_ENV": "test"},
        )


def test_explain_railway_url_aborts():
    with pytest.raises(BenchmarkAborted, match="host"):
        assert_disposable_postgres("postgresql://user:pw@db.railway.app/prod")


def test_explain_postgres_maintenance_name_aborts():
    with pytest.raises(BenchmarkAborted, match="maintenance"):
        assert_disposable_postgres("postgresql://127.0.0.1/postgres")


def test_explain_docker_hostname_postgres_aborts():
    with pytest.raises(BenchmarkAborted, match="Docker service hostname"):
        assert_disposable_postgres("postgresql://postgres@postgres/s2_0_explain")


def test_explain_guard_accepts_loopback_disposable_name_without_connect():
    url = "postgresql://127.0.0.1/s2_0_explain"
    parsed = assert_disposable_postgres(url)
    assert parsed["database"] == "s2_0_explain"
    assert parsed["host"] == "127.0.0.1"
    env = evaluate_explain_guard(
        requested_app_env="test",
        accept_nontest=False,
        database_url=url,
        environ={"APP_ENV": "test"},
    )
    assert env == "test"


def test_explain_unix_peer_url_is_allowlisted():
    parsed = assert_disposable_postgres("postgresql:///m11_migrate")
    assert parsed["host"] == ""
    assert parsed["database"] == "m11_migrate"


def test_explain_i_accept_does_not_override_isolation():
    with pytest.raises(BenchmarkAborted, match="host"):
        evaluate_explain_guard(
            requested_app_env="test",
            accept_nontest=True,
            database_url="postgresql://db.railway.app/s2_0_explain",
            environ={"APP_ENV": "test", "BENCHMARK_ALLOW_NONTEST": "1"},
        )


def test_explain_staging_still_needs_dual_consent():
    url = "postgresql://127.0.0.1/s2_0_explain"
    with pytest.raises(BenchmarkAborted, match="refusing staging/production"):
        evaluate_explain_guard(
            requested_app_env="staging",
            accept_nontest=False,
            database_url=url,
            environ={"APP_ENV": "test", "BENCHMARK_ALLOW_NONTEST": "1"},
        )
    assert (
        evaluate_explain_guard(
            requested_app_env="staging",
            accept_nontest=True,
            database_url=url,
            environ={"APP_ENV": "test", "BENCHMARK_ALLOW_NONTEST": "1"},
        )
        == "staging"
    )


def test_explain_defaults_scenario_pro_30():
    args = build_arg_parser().parse_args(
        [
            "--explain",
            "--app-env",
            "test",
            "--database-url",
            "postgresql://127.0.0.1/s2_0_explain",
        ]
    )
    config = config_from_args(args, environ={})
    assert config.explain is True
    assert config.scenario == "pro-30"
    assert config.json_path == DEFAULT_EXPLAIN_JSON_PATH


def test_explain_rejects_unsupported_scenario():
    args = build_arg_parser().parse_args(
        [
            "--explain",
            "--scenario",
            "plus-10",
            "--app-env",
            "test",
            "--database-url",
            "postgresql://127.0.0.1/s2_0_explain",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="unsupported"):
        config_from_args(args, environ={})


def test_explain_plus_protocol_aborts():
    args = build_arg_parser().parse_args(
        [
            "--explain",
            "--protocol",
            PROTOCOL_BNSS_COLD_WARM,
            "--app-env",
            "test",
            "--database-url",
            "postgresql://127.0.0.1/s2_0_explain",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="cannot be combined"):
        config_from_args(args, environ={})


def test_cli_explain_without_url_subprocess():
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--explain",
            "--app-env",
            "test",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=_env_without_db(
            APP_ENV="test",
            DATABASE_URL="postgresql://127.0.0.1/s2_0_explain",
        ),
    )
    assert proc.returncode == 1
    assert "never process DATABASE_URL" in proc.stderr


def test_cli_explain_sqlite_subprocess():
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--scenario",
            "plus-10",
            "--explain",
            "--app-env",
            "test",
            "--database-url",
            "sqlite:////tmp/x.sqlite",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=_env_without_db(APP_ENV="test"),
    )
    assert proc.returncode == 1
    combined = proc.stderr + proc.stdout
    assert "sqlite" in combined.lower() or "unsupported" in combined.lower()


def test_explain_script_help_lists_explain():
    proc = subprocess.run(
        [sys.executable, str(EXPLAIN_CLI), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "--explain" in proc.stdout
    assert "disposable PostgreSQL EXPLAIN" in proc.stdout


def test_readonly_select_refuses_writes():
    assert assert_readonly_select("SELECT 1").upper().startswith("SELECT")
    with pytest.raises(BenchmarkAborted, match="non-SELECT"):
        assert_readonly_select("DELETE FROM user_device")
    with pytest.raises(BenchmarkAborted, match="non-SELECT"):
        assert_readonly_select("EXPLAIN SELECT 1")
    with pytest.raises(BenchmarkAborted, match="multiple"):
        assert_readonly_select("SELECT 1; SELECT 2")


def test_parse_explain_text_hash_right_join_and_sort():
    text = """
Sort  (cost=227.78..227.85 rows=30 width=91) (actual time=3.907..3.911 rows=30 loops=1)
  ->  Hash Right Join  (cost=209.95..227.04 rows=30 width=91) (actual time=2.768..3.897 rows=30 loops=1)
        ->  Seq Scan on user_playground_item i  (cost=0.00..1.60 rows=30 width=43) (actual time=0.012..0.015 rows=30 loops=1)
Planning Time: 0.4 ms
Execution Time: 4.0 ms
"""
    parsed = parse_explain_text(text)
    assert parsed["scan_types"][0] == "Sort"
    assert "Hash Right Join" in parsed["scan_types"]
    assert "Seq Scan" in parsed["scan_types"]
    assert parsed["n_plus_one_hint"] is False


def test_parse_explain_text_golden_index_scan():
    text = SAMPLE_INDEX_PLAN.read_text(encoding="utf-8")
    parsed = parse_explain_text(text)
    assert "Index Scan" in parsed["scan_types"]
    assert parsed["index_names"] == ["user_device_user_hash_key"]
    assert parsed["actual_rows"] == 1
    assert parsed["buffers_shared_hit"] == 4
    assert parsed["buffers_shared_read"] == 1
    assert parsed["planning_time_ms"] == 0.15
    assert parsed["execution_time_ms"] == 0.045
    assert parsed["n_plus_one_hint"] is False


def test_parse_explain_text_nested_loop_seq_is_t16_hint_only():
    text = SAMPLE_NESTED_PLAN.read_text(encoding="utf-8")
    parsed = parse_explain_text(text)
    assert parsed["n_plus_one_hint"] is True
    assert "Nested Loop" in parsed["scan_types"]
    assert "Seq Scan" in parsed["scan_types"]


def test_nested_loop_alone_is_not_n_plus_one():
    text = """
Nested Loop  (cost=0.15..8.19 rows=1 width=32) (actual time=0.020..0.021 rows=1 loops=1)
  ->  Index Scan using user_playground_progress_due on user_playground_progress  (cost=0.15..8.17 rows=1 width=32) (actual time=0.018..0.018 rows=1 loops=1)
        Index Cond: (user_id = '11111111-1111-4111-8111-111111111111'::uuid)
Planning Time: 0.1 ms
Execution Time: 0.03 ms
"""
    parsed = parse_explain_text(text)
    assert "Nested Loop" in parsed["scan_types"]
    assert parsed["n_plus_one_hint"] is False
    assert parsed["t16_note"]


def test_dummy_device_hash_is_hex_not_a_token():
    digest = dummy_device_key_hash()
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    for token in ("@", "Bearer", "eyJ", "rtc_device", "hmac", "token="):
        assert token.lower() not in digest.lower()
    sanitized = sanitize_explain_text(
        f"device_key_hash = '{digest}' email={BENCH_EMAIL}",
        dummy_hash=digest,
    )
    assert digest not in sanitized
    assert BENCH_EMAIL not in sanitized
    assert "<redacted-device-hash>" in sanitized


def test_capture_explain_statements_matches_ws8_inventory():
    captured = capture_explain_statements()
    assert tuple(label for label, _sql, _params in captured) == EXPLAIN_QUERY_LABELS
    by_label = {label: sql for label, sql, _params in captured}
    assert "period_start" in by_label["current_roster_lookup"]
    assert "consumed_at" in by_label["roster_capacity_count"]
    assert "selected_count" in by_label["home_summary_aggregate"]
    assert "IN (" in by_label["home_summary_aggregate"]
    assert by_label["home_summary_aggregate"].count("%s") >= 34
    assert "next_revision" in by_label["due_revisions"]
    assert "next_revision" in by_label["calendar_schedule"]
    assert "revoked_at IS NULL" in by_label["device_count"]
    assert "device_key_hash" in by_label["device_lookup"]
    assert "is_current = TRUE" in by_label["current_subscription"]
    assert "user_playground_source_change" in by_label["source_review_aggregate"]
    for _label, sql, _params in captured:
        assert_readonly_select(sql)


def test_spy_cursor_postgres_repo_sql_predicates():
    cursor = ExplainCaptureCursor()
    pool = ExplainCapturePool(ExplainCaptureConn(cursor))
    uid = BENCH_USER
    roster = PostgresRosterRepository(pool)
    overlay = PostgresPlaygroundRepository(pool)
    devices = PostgresDeviceRepository(pool)
    subs = PostgresSubscriptionRepository(pool)
    roster.list_items(uid, date(2026, 9, 1))
    assert "period_start" in cursor.statements[-1][0]
    cursor.statements.clear()
    roster.count_consumed(uid, date(2026, 9, 1))
    assert "consumed_at" in cursor.statements[-1][0]
    cursor.statements.clear()
    overlay.list_playground_summaries(
        uid, as_of=date(2026, 9, 16), law_ids=list(ELIGIBLE_LAWS) + list(synthetic_law_ids(24))
    )
    sql = cursor.statements[-1][0]
    assert "selected_count" in sql
    assert "IN (" in sql
    cursor.statements.clear()
    overlay.list_due_revisions(uid, date(2026, 9, 16), list(ELIGIBLE_LAWS))
    assert "next_revision" in cursor.statements[-1][0]
    cursor.statements.clear()
    overlay.list_revision_schedule(
        uid, date(2026, 9, 1), date(2026, 10, 1), list(ELIGIBLE_LAWS)
    )
    schedule_sql = cursor.statements[-1][0]
    assert "next_revision" in schedule_sql
    assert schedule_sql.count("%s") >= 3
    cursor.statements.clear()
    devices.count_active(uid)
    assert "revoked_at IS NULL" in cursor.statements[-1][0]
    cursor.statements.clear()
    devices.get_by_hash(uid, dummy_device_key_hash())
    assert "device_key_hash" in cursor.statements[-1][0]
    cursor.statements.clear()
    subs.get_current_subscription(uid)
    assert "is_current = TRUE" in cursor.statements[-1][0]
    cursor.statements.clear()
    overlay.list_source_changes(uid)
    assert "user_playground_source_change" in cursor.statements[-1][0]


def _fake_probe_app(
    *,
    status: int = 200,
    hang: bool = False,
    overlap_target: int = 0,
):
    from constitution_memorizer.web.request_context import (
        begin_request_timings,
        capture_request_performance,
        record_request_counter,
        reset_request_timings,
    )

    state = {
        "current": 0,
        "max": 0,
        "seq": 0,
        "reached": asyncio.Event(),
    }

    async def app(scope, receive, send):
        if scope["type"] != "http":
            return
        await receive()
        if hang:
            await asyncio.Event().wait()
        state["seq"] += 1
        seq = state["seq"]
        state["current"] += 1
        if state["current"] > state["max"]:
            state["max"] = state["current"]
        if overlap_target and state["current"] >= overlap_target:
            state["reached"].set()
        token = begin_request_timings()
        try:
            record_request_counter("playground_repo_round_trips", seq)
            capture_request_performance(
                path="/probe",
                method="GET",
                status_code=status,
                total_ms=float(seq),
            )
        finally:
            reset_request_timings(token)
        if overlap_target:
            try:
                await asyncio.wait_for(state["reached"].wait(), timeout=2)
            except TimeoutError:
                pass
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [[b"content-type", b"text/plain"]],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})
        state["current"] -= 1

    return app, state


def test_parse_concurrency_levels_golden():
    assert parse_concurrency_levels("1,5,10,25") == (1, 5, 10, 25)
    assert parse_concurrency_levels("1, 5, 10, 25") == (1, 5, 10, 25)
    assert parse_concurrency_levels("5,5,1") == (5, 1)
    with pytest.raises(BenchmarkAborted, match="ceiling"):
        parse_concurrency_levels("26")
    with pytest.raises(BenchmarkAborted, match="positive"):
        parse_concurrency_levels("0")
    with pytest.raises(BenchmarkAborted, match="blank"):
        parse_concurrency_levels("1,,5")
    with pytest.raises(BenchmarkAborted, match="comma-separated"):
        parse_concurrency_levels("  ")
    with pytest.raises(BenchmarkAborted, match="invalid"):
        parse_concurrency_levels("abc")


def test_concurrency_help_lists_flag():
    parser = build_arg_parser()
    text = parser.format_help()
    assert "--concurrency" in text
    assert "1,5,10,25" in text


def test_concurrency_without_flag_keeps_sequential_config():
    args = build_arg_parser().parse_args(
        [
            "--scenario",
            "plus-10",
            "--database-url",
            "sqlite:///fresh.db",
            "--app-env",
            "test",
        ]
    )
    config = config_from_args(args, environ={})
    assert config.concurrency_levels is None
    assert config.iterations == 50
    assert config.warmup == 5
    assert config.json_path == DEFAULT_JSON_PATH


def test_concurrency_config_from_args(tmp_path: Path):
    db = tmp_path / "t18.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--scenario",
            "plus-10",
            "--concurrency",
            "1,5,10,25",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    config = config_from_args(args, environ={})
    assert config.concurrency_levels == (1, 5, 10, 25)
    assert config.iterations == DEFAULT_CONCURRENCY_BATCHES
    assert config.warmup == 5
    assert config.json_path == DEFAULT_CONCURRENCY_JSON_PATH
    assert config.protocol is None


def test_concurrency_quick_sets_one_batch(tmp_path: Path):
    db = tmp_path / "t18-quick.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--scenario",
            "law-workspace",
            "--concurrency",
            "1,5,10,25",
            "--quick",
            "--warmup",
            "9",
            "--iterations",
            "40",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    config = config_from_args(args, environ={})
    assert config.concurrency_levels == (1, 5, 10, 25)
    assert config.warmup == 1
    assert config.iterations == 1


def test_concurrency_plus_explain_aborts():
    args = build_arg_parser().parse_args(
        [
            "--scenario",
            "plus-10",
            "--concurrency",
            "1,5",
            "--explain",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--explain"):
        config_from_args(args, environ={})


def test_concurrency_plus_protocol_aborts():
    args = build_arg_parser().parse_args(
        [
            "--protocol",
            PROTOCOL_BNSS_COLD_WARM,
            "--concurrency",
            "1",
            "--database-url",
            "sqlite:///unused.db",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--protocol"):
        config_from_args(args, environ={})


def test_concurrency_rejects_postgresql():
    with pytest.raises(BenchmarkAborted, match="T23"):
        assert_concurrency_sqlite("postgresql://localhost/recall")
    args = build_arg_parser().parse_args(
        [
            "--scenario",
            "plus-10",
            "--concurrency",
            "1",
            "--database-url",
            "postgresql://localhost/recall",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="T23"):
        config_from_args(args, environ={})


def test_concurrency_rejects_unsupported_scenario(tmp_path: Path):
    db = tmp_path / "t18-due.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--scenario",
            "due-heavy",
            "--concurrency",
            "1",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="plus-10 or law-workspace"):
        config_from_args(args, environ={})


def test_concurrency_rejects_level_above_ceiling(tmp_path: Path):
    db = tmp_path / "t18-hi.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--scenario",
            "plus-10",
            "--concurrency",
            str(MAX_CONCURRENCY + 1),
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="ceiling"):
        config_from_args(args, environ={})


def test_concurrency_c1_fake_app():
    async def _go():
        app, _state = _fake_probe_app(status=200)
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver", follow_redirects=False
        ) as client:
            return await run_concurrent_batch(
                client, "/probe", concurrency=1, batch_index=0, timeout_s=5
            )

    result = asyncio.run(_go())
    assert len(result.samples) == 1
    assert result.samples[0].status_code == 200
    assert result.failed_requests == 0
    assert result.completed_requests == 1
    assert result.incomplete is False
    assert result.max_in_flight_observed == 1
    assert result.requested_concurrency == 1


def test_concurrency_c5_overlap_fake_app():
    async def _go():
        app, state = _fake_probe_app(status=200, overlap_target=5)
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver", follow_redirects=False
        ) as client:
            result = await run_concurrent_batch(
                client, "/probe", concurrency=5, batch_index=0, timeout_s=5
            )
            return result, state

    result, state = asyncio.run(_go())
    assert result.max_in_flight_observed == 5
    assert state["max"] == 5
    assert result.completed_requests == 5
    assert result.failed_requests == 0
    assert result.throughput_rps is not None


def test_concurrency_snapshot_attribution():
    from constitution_memorizer.web.request_context import get_last_request_performance

    async def _go():
        app, _state = _fake_probe_app(status=200, overlap_target=5)
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver", follow_redirects=False
        ) as client:
            parent_before = get_last_request_performance()
            result = await run_concurrent_batch(
                client, "/probe", concurrency=5, batch_index=0, timeout_s=5
            )
            parent_after = get_last_request_performance()
            return parent_before, parent_after, result

    parent_before, parent_after, result = asyncio.run(_go())
    assert parent_before is None
    assert parent_after is None
    task_ids = [sample.task_id for sample in result.samples]
    assert len(set(task_ids)) == 5
    identities = [sample.snapshot_identity for sample in result.samples]
    assert None not in identities
    assert len(set(identities)) == 5
    counters = [
        int(sample.snapshot.counters["playground_repo_round_trips"])
        for sample in result.samples
    ]
    assert len(set(counters)) == 5
    assert all(sample.error_class is None for sample in result.samples)


def test_concurrency_timeout_cancellation():
    async def _go():
        app, _state = _fake_probe_app(hang=True)
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver", follow_redirects=False
        ) as client:
            return await run_concurrent_batch(
                client, "/probe", concurrency=2, batch_index=0, timeout_s=0.2
            )

    result = asyncio.run(_go())
    assert result.incomplete is True
    assert result.aborted_reason == "batch_timeout"
    assert result.throughput_rps is None
    assert all(sample.error_class == "timeout" for sample in result.samples)


def test_concurrency_non_200_abort():
    async def _go():
        app, _state = _fake_probe_app(status=500)
        transport = ASGITransport(app=app)
        results = []
        async with AsyncClient(
            transport=transport, base_url="http://testserver", follow_redirects=False
        ) as client:
            for concurrency in (1, 5):
                for batch_index in range(2):
                    result = await run_concurrent_batch(
                        client,
                        "/probe",
                        concurrency=concurrency,
                        batch_index=batch_index,
                        timeout_s=5,
                    )
                    results.append(result)
                    if result.failed_requests or result.aborted_reason:
                        return results
        return results

    results = asyncio.run(_go())
    assert len(results) == 1
    assert results[0].concurrency == 1
    assert results[0].aborted_reason == "http_500"
    assert results[0].samples[0].status_code == 500
    assert results[0].throughput_rps is None


def test_concurrency_warm_cache_classification():
    hit = _cache_snap(cache="hit", misses=0, load=False)
    miss = _cache_snap(cache="miss", misses=1, load=True)
    assert classify_cache_snapshot(hit) == "hit"
    assert_concurrency_warm_workspace(hit, label="warm")
    with pytest.raises(BenchmarkAborted, match="expected 'hit'"):
        assert_concurrency_warm_workspace(miss, label="warm")
    assert_concurrency_home_no_bare_act(
        _cache_snap(cache=None, misses=0, load=False, path_group="/playground"),
        label="home",
    )
    with pytest.raises(BenchmarkAborted, match="Bare Act"):
        assert_concurrency_home_no_bare_act(hit, label="home")
    with pytest.raises(BenchmarkAborted, match="Bare Act"):
        assert_concurrency_home_no_bare_act(miss, label="home")


def test_mutations_help_lists_flag():
    parser = build_arg_parser()
    text = parser.format_help()
    assert "--mutations" in text
    assert "--webhooks" in text
    assert "T19" in text


def test_mutations_without_flag_keeps_sequential_config():
    args = build_arg_parser().parse_args(
        [
            "--scenario",
            "plus-10",
            "--database-url",
            "sqlite:///fresh.db",
            "--app-env",
            "test",
        ]
    )
    config = config_from_args(args, environ={})
    assert config.mutations is False
    assert config.webhooks is False
    assert config.concurrency_levels is None
    assert config.iterations == 50
    assert config.json_path == DEFAULT_JSON_PATH


def test_mutations_config_from_args(tmp_path: Path):
    db = tmp_path / "t19.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--mutations",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    config = config_from_args(args, environ={})
    assert config.mutations is True
    assert config.webhooks is False
    assert config.scenario == ""
    assert config.iterations == DEFAULT_MUTATION_WAVES
    assert config.json_path == DEFAULT_MUTATIONS_JSON_PATH
    assert config.concurrency_levels is None


def test_webhooks_quick_sets_one_wave_and_nm(tmp_path: Path):
    db = tmp_path / "t19-wh.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--webhooks",
            "--quick",
            "--warmup",
            "9",
            "--iterations",
            "40",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    config = config_from_args(args, environ={})
    assert config.webhooks is True
    assert config.warmup == 1
    assert config.iterations == 1
    assert config.webhook_n == WEBHOOK_QUICK_N
    assert config.webhook_m == WEBHOOK_QUICK_M
    assert config.json_path == DEFAULT_WEBHOOKS_JSON_PATH


def test_mutations_plus_concurrency_aborts(tmp_path: Path):
    db = tmp_path / "t19-combo.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--mutations",
            "--concurrency",
            "1",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--concurrency"):
        config_from_args(args, environ={})


def test_mutations_plus_explain_aborts():
    args = build_arg_parser().parse_args(
        [
            "--mutations",
            "--explain",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--explain"):
        config_from_args(args, environ={})


def test_webhooks_plus_protocol_aborts():
    args = build_arg_parser().parse_args(
        [
            "--webhooks",
            "--protocol",
            PROTOCOL_BNSS_COLD_WARM,
            "--database-url",
            "sqlite:///unused.db",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--protocol"):
        config_from_args(args, environ={})


def test_mutations_plus_webhooks_aborts(tmp_path: Path):
    db = tmp_path / "t19-both.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--mutations",
            "--webhooks",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--webhooks"):
        config_from_args(args, environ={})


def test_mutations_rejects_postgresql():
    with pytest.raises(BenchmarkAborted, match="T23"):
        assert_t19_sqlite("postgresql://localhost/recall")
    args = build_arg_parser().parse_args(
        [
            "--mutations",
            "--database-url",
            "postgresql://localhost/recall",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="T23"):
        config_from_args(args, environ={})


def test_webhooks_rejects_postgresql():
    args = build_arg_parser().parse_args(
        [
            "--webhooks",
            "--database-url",
            "postgresql://localhost/recall",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="T23"):
        config_from_args(args, environ={})


def test_webhook_delivery_counts_duplicate_versus_retry_busy():
    from constitution_memorizer.subscriptions.webhooks import WebhookDeliveryResult

    owned = WebhookDeliveryResult(200, owned=True, processing_status="processed")
    duplicate = WebhookDeliveryResult(200, owned=False, processing_status="processed")
    busy = WebhookDeliveryResult(
        503, error="provider", owned=False, processing_status="processing"
    )
    bad = WebhookDeliveryResult(400, error="invalid_signature", owned=False)
    counts = webhook_delivery_counts([owned, duplicate, busy, bad])
    assert counts["deliveries"] == 4
    assert counts["owned"] == 1
    assert counts["duplicate"] == 1
    assert counts["retry_busy"] == 1
    assert counts["errors"] == 1
    busy_only = webhook_delivery_counts([busy])
    assert busy_only["retry_busy"] == 1
    assert busy_only["duplicate"] == 0
    dup_only = webhook_delivery_counts([duplicate])
    assert dup_only["duplicate"] == 1
    assert dup_only["retry_busy"] == 0


def test_webhook_sequential_duplicate_is_one(tmp_path: Path):
    db = tmp_path / "t19-dup.sqlite"
    proof = run_sequential_webhook_duplicate(db)
    assert proof["counts"]["deliveries"] == 2
    assert proof["counts"]["owned"] == 1
    assert proof["counts"]["duplicate"] == 1
    assert proof["counts"]["retry_busy"] == 0
    assert proof["counts"]["errors"] == 0
    assert proof["provider_fetches"] == 1
    assert proof["first"]["status_code"] == 200
    assert proof["first"]["owned"] is True
    assert proof["replay"]["status_code"] == 200
    assert proof["replay"]["owned"] is False
    assert proof["event_rows"] == 1
    assert FakeProvider is not None


def test_mutations_c1_roster_cap_sample(tmp_path: Path):
    db = tmp_path / "t19-roster-c1.sqlite"
    wave = run_single_mutation_wave("roster-cap", db, concurrency=1)
    assert wave["incomplete"] is False
    assert wave["workers_terminated"] is True
    assert wave["correct"] is True
    assert wave["outcome_multiset_observed"] == ["ok"]
    assert wave["integrity_after"]["consumed_distinct"] == 10
    assert wave["aborted_reason"] is None
    assert "elapsed_ms" not in str(wave["correct"])


def test_page_weight_help_lists_flag():
    parser = build_arg_parser()
    text = parser.format_help()
    assert "--page-weight" in text
    assert "T20" in text
    assert "--inventory" not in text


def test_page_weight_without_flag_keeps_sequential_config():
    args = build_arg_parser().parse_args(
        [
            "--scenario",
            "plus-10",
            "--database-url",
            "sqlite:///fresh.db",
            "--app-env",
            "test",
        ]
    )
    config = config_from_args(args, environ={})
    assert config.page_weight is False
    assert config.mutations is False
    assert config.webhooks is False
    assert config.concurrency_levels is None
    assert config.iterations == 50
    assert config.json_path == DEFAULT_JSON_PATH


def test_page_weight_config_from_args(tmp_path: Path):
    db = tmp_path / "t20.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--page-weight",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    config = config_from_args(args, environ={})
    assert config.page_weight is True
    assert config.scenario == ""
    assert config.warmup == 0
    assert config.iterations == 1
    assert config.json_path == DEFAULT_PAGE_WEIGHT_JSON_PATH
    assert config.mutations is False
    assert config.webhooks is False
    assert config.concurrency_levels is None
    assert config.protocol is None


def test_page_weight_plus_mutations_aborts(tmp_path: Path):
    db = tmp_path / "t20-combo.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--page-weight",
            "--mutations",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--mutations"):
        config_from_args(args, environ={})


def test_page_weight_plus_webhooks_aborts(tmp_path: Path):
    db = tmp_path / "t20-wh.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--page-weight",
            "--webhooks",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--webhooks"):
        config_from_args(args, environ={})


def test_page_weight_plus_concurrency_aborts(tmp_path: Path):
    db = tmp_path / "t20-c.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--page-weight",
            "--concurrency",
            "1",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--concurrency"):
        config_from_args(args, environ={})


def test_page_weight_plus_explain_aborts():
    args = build_arg_parser().parse_args(
        [
            "--page-weight",
            "--explain",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--explain"):
        config_from_args(args, environ={})


def test_page_weight_plus_protocol_aborts():
    args = build_arg_parser().parse_args(
        [
            "--page-weight",
            "--protocol",
            PROTOCOL_BNSS_COLD_WARM,
            "--database-url",
            "sqlite:///unused.db",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--protocol"):
        config_from_args(args, environ={})


def test_page_weight_plus_scenario_aborts(tmp_path: Path):
    db = tmp_path / "t20-scen.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--page-weight",
            "--scenario",
            "plus-10",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="omit --scenario"):
        config_from_args(args, environ={})


def test_page_weight_rejects_postgresql():
    with pytest.raises(BenchmarkAborted, match="T23"):
        assert_t20_sqlite("postgresql://localhost/recall")
    args = build_arg_parser().parse_args(
        [
            "--page-weight",
            "--database-url",
            "postgresql://localhost/recall",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="T23"):
        config_from_args(args, environ={})


def test_inventory_playground_css_size_positive():
    sizes = ws11_named_file_inventory()
    assert sizes["playground.css"] > 0
    assert (PAGE_WEIGHT_STATIC_DIR / "playground.css").is_file()


def test_inventory_ws11_named_files_exist():
    sizes = ws11_named_file_inventory()
    assert tuple(sizes) == WS11_NAMED_FILES
    for name, size in sizes.items():
        assert size > 0, name


def test_page_weight_parse_stylesheet_and_script():
    html = """
    <html><head>
    <link rel="stylesheet" href="/static/styles.css?v=main85">
    <script src="/static/app.js?v=main62" defer></script>
    </head></html>
    """
    assets = iter_html_assets(html)
    hrefs = [row["url"] for row in assets if row["kind"] == "stylesheet"]
    srcs = [row["url"] for row in assets if row["kind"] == "script"]
    assert hrefs == ["/static/styles.css?v=main85"]
    assert srcs == ["/static/app.js?v=main62"]
    assert page_weight_catalog_key(hrefs[0]) == "/static/styles.css"
    assert page_weight_catalog_key("/static/styles.css?v=other") == "/static/styles.css"


def test_page_weight_google_fonts_are_third_party():
    html = """
    <html><head>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Fraunces&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/styles.css?v=main85">
    </head></html>
    """
    summary = summarize_html_assets(html, static_dir=PAGE_WEIGHT_STATIC_DIR)
    third_urls = [row["url"] for row in summary["third_party"]]
    assert any("fonts.googleapis.com" in url for url in third_urls)
    css_keys = [row["catalog_key"] for row in summary["first_party_css"]]
    assert "/static/styles.css" in css_keys
    assert all("fonts.googleapis.com" not in key for key in css_keys)
    assert all(row.get("fetch") == "skipped_no_external_network" for row in summary["third_party"])


def test_gzip_equivalent_golden():
    import gzip as gzip_mod

    raw = b"abc" * 100
    expected = len(gzip_mod.compress(raw, compresslevel=GZIP_COMPRESSLEVEL))
    assert gzip_equivalent_bytes(raw) == expected
    assert GZIP_COMPRESSLEVEL == 9


def test_page_weight_missing_static_asset_reported(tmp_path: Path):
    html = '<link rel="stylesheet" href="/static/does-not-exist.css">'
    summary = summarize_html_assets(html, static_dir=tmp_path)
    assert summary["missing_assets"]
    assert summary["complete"] is False
    assert any("does-not-exist.css" in str(item.get("url")) for item in summary["missing_assets"])


def test_page_weight_html_http_500_incomplete():
    spec = {
        "id": "plus_home",
        "fixture": "plus-10",
        "method": "GET",
        "path": "/playground",
        "path_group": "/playground",
    }
    row = _incomplete_page_row(spec, reason="HTTP 500", status_code=500)
    assert row["complete"] is False
    assert row["status_code"] == 500
    assert row["http_failures"]
    assert row["http_failures"][0]["kind"] == "http_error"


def test_page_weight_catalog_key_strips_query():
    assert page_weight_catalog_key("/static/styles.css?v=main85") == "/static/styles.css"
    assert page_weight_catalog_key("/static/styles.css?v=other") == "/static/styles.css"


def test_page_weight_inclusive_vs_unique_shared_css(tmp_path: Path):
    (tmp_path / "styles.css").write_bytes(b"c" * 10)
    (tmp_path / "app.js").write_bytes(b"j" * 4)
    html = (
        '<link rel="stylesheet" href="/static/styles.css?v=a">'
        '<script src="/static/app.js?v=b"></script>'
    )
    one = summarize_html_assets(html, static_dir=tmp_path)
    two = summarize_html_assets(html, static_dir=tmp_path)
    assert one["css_source_bytes"] == 10
    assert two["css_source_bytes"] == 10
    inclusive_css = one["css_source_bytes"] + two["css_source_bytes"]
    unique_css = first_party_page_weight_totals(
        0, one["first_party_css"], []
    )["css_source_bytes"]
    assert inclusive_css == 20
    assert unique_css == 10
    assert one["js_source_bytes"] == 4


def test_static_asset_path_rejects_traversal(tmp_path: Path):
    (tmp_path / "styles.css").write_bytes(b"ok")
    with pytest.raises(BenchmarkAborted, match="rejected"):
        resolve_static_disk_path("/static/../secrets.txt", static_dir=tmp_path)
    resolved = resolve_static_disk_path("/static/styles.css", static_dir=tmp_path)
    assert resolved == (tmp_path / "styles.css").resolve()


def test_static_asset_path_rejects_urlencoded_traversal(tmp_path: Path):
    with pytest.raises(BenchmarkAborted, match="rejected"):
        resolve_static_disk_path("/static/%2e%2e/secrets.txt", static_dir=tmp_path)
    with pytest.raises(BenchmarkAborted, match="rejected"):
        resolve_static_disk_path(
            "/static/foo/%2e%2e/%2e%2e/etc/passwd", static_dir=tmp_path
        )


def test_page_weight_json_allows_font_url_and_digest():
    from constitution_memorizer.playground.benchmarking import (
        _assert_page_weight_json_safe,
    )

    _assert_page_weight_json_safe(
        {
            "third_party": [
                {
                    "url": "https://fonts.googleapis.com/css2?family=Fraunces:wght@400"
                }
            ],
            "sha256": "a" * 64,
        }
    )
    with pytest.raises(BenchmarkAborted, match="fixture email"):
        _assert_page_weight_json_safe({"email": BENCH_EMAIL})


def test_page_weight_measurement_mode_is_in_process():
    assert PAGE_WEIGHT_MEASUREMENT_MODE == "in_process_testclient_disk_gzip"
    help_text = build_arg_parser().format_help()
    assert "--page-weight" in help_text
    assert "Lighthouse" in help_text


def test_cold_start_help_lists_flag():
    parser = build_arg_parser()
    text = parser.format_help()
    assert "--cold-start" in text
    assert "T21" in text
    assert COLD_START_CHILD_TIMEOUT_S == 60.0
    assert COLD_START_MEASUREMENT_MODE == "fresh_interpreter_subprocess"


def test_cold_start_without_flag_keeps_sequential_config():
    args = build_arg_parser().parse_args(
        [
            "--scenario",
            "plus-10",
            "--database-url",
            "sqlite:///fresh.db",
            "--app-env",
            "test",
        ]
    )
    config = config_from_args(args, environ={})
    assert config.cold_start is False
    assert config.page_weight is False
    assert config.json_path == DEFAULT_JSON_PATH


def test_cold_start_config_from_args(tmp_path: Path):
    db = tmp_path / "t21.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--cold-start",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    config = config_from_args(args, environ={})
    assert config.cold_start is True
    assert config.page_weight is False
    assert config.scenario == ""
    assert config.warmup == 0
    assert config.iterations == 1
    assert config.json_path == DEFAULT_COLD_START_JSON_PATH


def test_cold_start_plus_page_weight_aborts(tmp_path: Path):
    db = tmp_path / "t21.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--cold-start",
            "--page-weight",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--page-weight"):
        config_from_args(args, environ={})


def test_cold_start_plus_mutations_aborts(tmp_path: Path):
    db = tmp_path / "t21.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--cold-start",
            "--mutations",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--mutations"):
        config_from_args(args, environ={})


def test_cold_start_plus_webhooks_aborts(tmp_path: Path):
    db = tmp_path / "t21.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--cold-start",
            "--webhooks",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--webhooks"):
        config_from_args(args, environ={})


def test_cold_start_plus_concurrency_aborts(tmp_path: Path):
    db = tmp_path / "t21.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--cold-start",
            "--concurrency",
            "1,5",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--concurrency"):
        config_from_args(args, environ={})


def test_cold_start_plus_explain_aborts():
    args = build_arg_parser().parse_args(
        [
            "--cold-start",
            "--explain",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--explain"):
        config_from_args(args, environ={})


def test_cold_start_plus_protocol_aborts(tmp_path: Path):
    db = tmp_path / "t21.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--cold-start",
            "--protocol",
            PROTOCOL_BNSS_COLD_WARM,
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="--protocol"):
        config_from_args(args, environ={})


def test_cold_start_plus_scenario_aborts(tmp_path: Path):
    db = tmp_path / "t21.sqlite"
    args = build_arg_parser().parse_args(
        [
            "--cold-start",
            "--scenario",
            "plus-10",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="omits --scenario"):
        config_from_args(args, environ={})


def test_cold_start_rejects_postgresql():
    with pytest.raises(BenchmarkAborted, match="T23"):
        assert_t21_sqlite("postgresql://localhost/recall")
    args = build_arg_parser().parse_args(
        [
            "--cold-start",
            "--database-url",
            "postgresql://localhost/recall",
            "--app-env",
            "test",
        ]
    )
    with pytest.raises(BenchmarkAborted, match="T23"):
        config_from_args(args, environ={})


def test_cold_start_json_sanitizer_refuses_secrets():
    _assert_cold_start_json_safe({"duration_ms": 12.5, "hydrated_slugs": []})
    with pytest.raises(BenchmarkAborted, match="fixture email"):
        _assert_cold_start_json_safe({"email": BENCH_EMAIL})
    with pytest.raises(BenchmarkAborted, match="sensitive"):
        _assert_cold_start_json_safe({"auth": "Bearer abc"})
    with pytest.raises(BenchmarkAborted, match="sensitive"):
        _assert_cold_start_json_safe({"cookie": "rtc_device=1"})
    with pytest.raises(BenchmarkAborted, match="production host"):
        _assert_cold_start_json_safe({"url": "https://recall-the-c.in/"})


def test_cold_start_positive_control_subprocess(tmp_path: Path):
    result = tmp_path / "t21-self-test.json"
    payload = run_cold_start_self_test(result_path=result, environ=_env_without_db())
    assert payload["kind"] == "cold-start-self-test"
    assert payload["complete"] is True
    assert payload["spy_installed"] is True
    assert payload["spy_installed_too_late"] is False
    assert payload["hook_installed_before_web_app_import"] is True
    miss = payload["miss"]
    hit = payload["hit"]
    direct = payload["direct_load"]
    assert miss["get_bare_act_calls"] >= 1
    assert miss["load_cached_calls"] >= 1
    assert miss["cache_misses"] >= 1
    assert hit["get_bare_act_calls"] >= 2
    assert hit["load_cached_calls"] >= 2
    assert hit["cache_hits"] >= 1
    assert direct["load_cached_calls"] > hit["load_cached_calls"]
    assert direct["get_bare_act_calls"] == hit["get_bare_act_calls"]
    assert direct["cache_hits"] >= hit["cache_hits"] + 1


def test_cold_start_zero_hydration_fresh_child(tmp_path: Path):
    db = tmp_path / "t21-measure.sqlite"
    report = tmp_path / "t21-measure.json"
    args = build_arg_parser().parse_args(
        [
            "--cold-start",
            "--database-url",
            f"sqlite:///{db}",
            "--app-env",
            "test",
            "--json",
            str(report),
        ]
    )
    config = config_from_args(args, environ={})
    payload = run_cold_start_benchmark(config, environ=_env_without_db(APP_ENV="test"))
    assert payload["kind"] == "cold-start"
    assert payload["complete"] is True
    assert payload["contract_passed"] is True
    assert payload["spy_installed"] is True
    assert payload["spy_installed_too_late"] is False
    assert payload["hook_installed_before_web_app_import"] is True
    assert payload["preimport_web_app"] is False
    assert payload["preimport_web_asgi"] is False
    assert payload["preimport_bare_acts"] is False
    assert payload["first_request"] is None
    assert payload["asgi_imported"] is False
    for phase_name in ("import", "create_app"):
        phase = payload[phase_name]
        assert phase["get_bare_act_calls"] == 0
        assert phase["load_cached_calls"] == 0
        assert phase["cache_hits"] == 0
        assert phase["cache_misses"] == 0
        assert phase["hydrated_slugs"] == []
        assert phase["cache_currsize"] == 0
        duration = phase["duration_ms"]
        assert isinstance(duration, (int, float))
        assert math.isfinite(duration)
        assert duration >= 0
    startup = payload["startup"]
    assert startup["postgres_pool_created"] is False
    assert startup["asgi_imported"] is False
    assert startup["lifespan_ran"] is False
    assert startup["browse_imported_during_create_app"] is True
    assert startup["sqlite_exists_after"] is True
    assert startup["units_json_bytes"] and startup["units_json_bytes"] > 0
    assert MINI_UNITS.name in str(startup["units_json_path"])
    assert "Browse module" in payload["incidental_stdout"]
    blob = report.read_text(encoding="utf-8")
    assert BENCH_EMAIL not in blob
    assert "Lighthouse" not in blob


def test_cold_start_late_app_fails_closed(tmp_path: Path):
    result = tmp_path / "t21-late-app.json"
    spawn = spawn_cold_start_child(
        mode="late-app",
        result_path=result,
        environ=_env_without_db(),
    )
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert spawn["timed_out"] is False
    assert spawn["returncode"] == 1
    assert payload["spy_installed_too_late"] is True
    assert payload["complete"] is False
    assert payload["contract_passed"] is False
    assert payload["hook_installed_before_web_app_import"] is False


def test_cold_start_late_cache_fails_closed(tmp_path: Path):
    result = tmp_path / "t21-late-cache.json"
    spawn = spawn_cold_start_child(
        mode="late-cache",
        result_path=result,
        environ=_env_without_db(),
    )
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert spawn["returncode"] == 1
    assert payload["spy_installed_too_late"] is True
    assert payload["complete"] is False
    assert "preimported" in str(payload.get("too_late_reason") or payload.get("aborted_reason") or "")


def test_cold_start_child_timeout_fails_closed(tmp_path: Path):
    result = tmp_path / "t21-hang.json"
    spawn = spawn_cold_start_child(
        mode="hang",
        result_path=result,
        timeout_s=0.2,
        environ=_env_without_db(),
    )
    assert spawn["timed_out"] is True
    assert not result.exists() or result.stat().st_size == 0


def test_cold_start_child_crash_fails_closed(tmp_path: Path):
    result = tmp_path / "t21-crash.json"
    spawn = spawn_cold_start_child(
        mode="crash",
        result_path=result,
        environ=_env_without_db(),
    )
    assert spawn["timed_out"] is False
    assert spawn["returncode"] == 3
    assert not result.exists()


def test_cold_start_malformed_result_rejected(tmp_path: Path):
    result = tmp_path / "t21-empty.json"
    spawn = spawn_cold_start_child(
        mode="empty",
        result_path=result,
        environ=_env_without_db(),
    )
    assert spawn["returncode"] == 0
    loaded = json.loads(result.read_text(encoding="utf-8"))
    assert loaded == {}
    assert _cold_start_result_complete(loaded) is False


def test_cold_start_leak_fails_contract(tmp_path: Path):
    db = tmp_path / "t21-leak.sqlite"
    result = tmp_path / "t21-leak.json"
    spawn = spawn_cold_start_child(
        mode="leak",
        result_path=result,
        db_path=db,
        units_path=MINI_UNITS,
        environ=_env_without_db(),
    )
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert spawn["returncode"] == 1
    assert payload["complete"] is True
    assert payload["contract_passed"] is False
    assert payload["import"]["get_bare_act_calls"] >= 1
    assert payload["import"]["load_cached_calls"] >= 1


def test_cold_start_t20_schema_unchanged():
    schema = json.loads(
        (ROOT / "docs" / "performance" / "playground-page-weight.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["properties"]["create_app_timed"]["const"] is False


def test_cold_start_t17_loader_spy_lock_untouched():
    text = (ROOT / "tests" / "test_playground_stage2_observability.py").read_text(
        encoding="utf-8"
    )
    assert "def test_t17_active_plus_repeated_zero_hydration" in text
    assert "_hydrate_spy" in text
    assert "from tests.test_playground import _hydrate_spy" in text

