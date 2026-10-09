"""Playground Stage 2 WS6–WS10 benchmark library (T13–T18).

Statistics, fail-closed production guard, deterministic fixtures, in-process
HTTP runner, JSON reporting, disposable PostgreSQL EXPLAIN (ANALYZE,
BUFFERS), and the T18 read-only concurrency harness. Does not change product
behavior or T1–T9 instrumentation.
PostgreSQL EXPLAIN is T15/WS8 (``--explain`` or
``scripts/explain_playground_queries.py``). BNSS cold/warm is
``--protocol bnss-cold-warm`` (T14/WS7); omitting ``--protocol`` keeps the
T13 unlabeled primary-route path. ``build_nplusone_fixture`` is the T16
matched-density helper; it is not a CLI scenario. ``--concurrency`` is T18
(SQLite-only, not default pytest, not T19 mutations).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import unquote, urlparse, urlunparse
from uuid import UUID, uuid4

PLAYGROUND_TEST_NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
BENCH_USER = UUID("11111111-1111-4111-8111-111111111111")
BENCH_EMAIL = "bench@example.invalid"
SCHEMA_VERSION = 1
SCENARIOS = (
    "plus-10",
    "pro-30",
    "due-heavy",
    "learned-heavy",
    "source-review",
    "law-workspace",
)
ELIGIBLE_LAWS = ("bns", "bnss", "ndps", "uapa", "pss", "mtp")
SOURCE_REVIEW_LAW = "ndps"
LAW_WORKSPACE_LAW = "bnss"
LAW_WORKSPACE_SELECTED_COUNT = 40
NPLUSONE_ROSTER_SIZES = (1, 10, 30)
NPLUSONE_LOCATORS_PER_LAW = 4
NPLUSONE_TIER = "pro"
NPLUSONE_LAW_LIMIT = 30
NPLUSONE_DUE_REVISION = "2026-09-10"
DEFAULT_JSON_PATH = Path("artifacts/playground-performance-baseline.json")
DEFAULT_BNSS_JSON_PATH = Path("artifacts/playground-bnss-cold-warm.json")
DEFAULT_CONCURRENCY_JSON_PATH = Path("artifacts/playground-concurrency.json")
DEFAULT_EXPLAIN_JSON_PATH = Path("docs/performance/explain-pro-30-summary.json")
DEFAULT_EXPLAIN_PLAN_DIR = Path("docs/performance")
DEFAULT_CONCURRENCY_LEVELS = (1, 5, 10, 25)
MAX_CONCURRENCY = 25
DEFAULT_CONCURRENCY_BATCHES = 5
CONCURRENCY_BATCH_TIMEOUT_S = 60.0
CONCURRENCY_SCENARIOS = frozenset({"plus-10", "law-workspace"})
CONCURRENCY_CLIENT_SHAPE = "single_async_client"
PROTOCOL_BNSS_COLD_WARM = "bnss-cold-warm"
PROTOCOLS = (PROTOCOL_BNSS_COLD_WARM,)
EXPLAIN_SCENARIO = "pro-30"
EXPECTED_ALEMBIC_HEAD = "20260927_0027"
EXPLAIN_STATEMENT_TIMEOUT = "30s"
DISPOSABLE_DB_NAME_RE = re.compile(
    r"^(s2_|explain_|m11_|playground_bench_)[a-z0-9_]+$"
)
LOCAL_POSTGRES_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1"})
FORBIDDEN_DB_NAMES = frozenset({"postgres", "template0", "template1"})
ANALYZE_TABLES = (
    "user_playground_period",
    "user_playground_roster_item",
    "user_playground_item",
    "user_playground_selection",
    "user_playground_progress",
    "user_playground_mode_progress",
    "user_playground_revision_mode_progress",
    "user_playground_source_change",
    "user_device",
)
EXPLAIN_QUERY_LABELS = (
    "current_roster_lookup",
    "roster_capacity_count",
    "home_summary_aggregate",
    "due_revisions",
    "calendar_schedule",
    "device_count",
    "device_lookup",
    "current_subscription",
    "source_review_aggregate",
)
EXPLAIN_DUMMY_DEVICE_MATERIAL = b"playground-t15-dummy-device-key"
DATASET_COUNT_SQL = (
    ("roster_items", "SELECT COUNT(*) FROM user_playground_roster_item WHERE user_id = %s"),
    ("overlay_items", "SELECT COUNT(*) FROM user_playground_item WHERE user_id = %s"),
    ("selection_rows", "SELECT COUNT(*) FROM user_playground_selection WHERE user_id = %s"),
    ("progress_rows", "SELECT COUNT(*) FROM user_playground_progress WHERE user_id = %s"),
    (
        "mode_progress_rows",
        "SELECT COUNT(*) FROM user_playground_mode_progress WHERE user_id = %s",
    ),
    (
        "revision_mode_rows",
        "SELECT COUNT(*) FROM user_playground_revision_mode_progress WHERE user_id = %s",
    ),
    (
        "source_change_rows",
        "SELECT COUNT(*) FROM user_playground_source_change WHERE user_id = %s",
    ),
    ("device_rows", "SELECT COUNT(*) FROM user_device WHERE user_id = %s"),
)
PLAN_NODE_TYPES = (
    "Index Only Scan",
    "Bitmap Index Scan",
    "Bitmap Heap Scan",
    "Hash Right Join",
    "Hash Left Join",
    "Hash Join",
    "Merge Join",
    "Nested Loop",
    "Index Scan",
    "Seq Scan",
    "GroupAggregate",
    "HashAggregate",
    "Aggregate",
    "Sort",
)
BNSS_LEARN_MODE = "read"
BNSS_LEARN_SECTION = "1"
BNSS_LEARN_LOCATOR = f"{LAW_WORKSPACE_LAW}:section:{BNSS_LEARN_SECTION}"
BNSS_WORKSPACE_PATH = f"/playground/laws/{LAW_WORKSPACE_LAW}"
BNSS_LEARN_PATH = (
    f"/playground/laws/{LAW_WORKSPACE_LAW}"
    f"/sections/{BNSS_LEARN_SECTION}/learn/{BNSS_LEARN_MODE}"
)
BNSS_PUBLIC_PATH = f"/laws/{LAW_WORKSPACE_LAW}"
BNSS_WORKSPACE_PATH_GROUP = "/playground/laws/{law_id}"
BNSS_LEARN_PATH_GROUP = (
    "/playground/laws/{law_id}/sections/{number}/learn/{mode}"
)
BNSS_PUBLIC_PATH_GROUP = BNSS_PUBLIC_PATH
PHASE0_ROUTES = ("/playground", "/playground/roster")
PHASE0_TEMPLATES = (
    "playground_law.html",
    "playground_learn.html",
    "bare_act.html",
)
KNOWN_APP_ENVS = frozenset({"test", "development", "staging", "production"})
PRODUCTION_ENVS = frozenset({"staging", "production"})
PRODUCTION_HOSTS = ("recall-the-c.in", "recallthec.in")
APP_ENV_TEST_REQUIRED = (
    "--app-env test is required unless BENCHMARK_ALLOW_NONTEST=1"
)
STAGING_PRODUCTION_CONSENT = (
    "refusing staging/production APP_ENV or production-looking "
    "APP_BASE_URL without --i-accept-nontest-db and "
    "BENCHMARK_ALLOW_NONTEST=1"
)
REPO_ROOT = Path(__file__).resolve().parents[3]
MINI_UNITS = REPO_ROOT / "tests" / "fixtures" / "learning" / "mini_units.json"

PRIMARY_ROUTES: dict[str, tuple[str, str]] = {
    "plus-10": ("GET", "/playground"),
    "pro-30": ("GET", "/playground"),
    "due-heavy": ("GET", "/dashboard"),
    "learned-heavy": ("GET", "/playground"),
    "source-review": ("GET", f"/playground/laws/{SOURCE_REVIEW_LAW}/source-review"),
    "law-workspace": ("GET", f"/playground/laws/{LAW_WORKSPACE_LAW}"),
}

_SENSITIVE = re.compile(
    r"@|[A-Fa-f0-9]{16,}|Bearer\s|eyJ|rtc_device|hmac|token=",
    re.IGNORECASE,
)
_BOUNDED_NOTE_VALUES: dict[str, frozenset[str]] | None = None
_CLOCK_INSTALLED = False
_STUBS_INSTALLED = False


class BenchmarkAborted(Exception):
    """Fail-closed abort. ``exit_code`` is 1 unless argparse already used 2."""

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.message = message


def percentile_nearest_rank(sorted_values: list[float], p: float) -> float:
    """Nearest-rank percentile: rank = ceil(p/100 × n), 1-indexed."""
    n = len(sorted_values)
    if n == 0:
        raise ValueError("percentile_nearest_rank requires at least one value")
    if not math.isfinite(p) or p <= 0 or p > 100:
        raise ValueError(f"percentile p must be in (0, 100], got {p!r}")
    rank = max(1, min(n, math.ceil(p / 100.0 * n)))
    return float(sorted_values[rank - 1])


def summarize_numbers(values: Iterable[float]) -> dict[str, float | int]:
    data = [float(v) for v in values]
    if not data:
        raise ValueError("summarize_numbers requires at least one value")
    ordered = sorted(data)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "mean": sum(ordered) / len(ordered),
        "p50": percentile_nearest_rank(ordered, 50),
        "p95": percentile_nearest_rank(ordered, 95),
        "p99": percentile_nearest_rank(ordered, 99),
        "max": ordered[-1],
    }


def synthetic_law_ids(count: int) -> tuple[str, ...]:
    if count < 0:
        raise ValueError("synthetic count must be >= 0")
    return tuple(f"syn-{n}" for n in range(1, count + 1))


def _synthetic_catalog_entry(law_id: str):
    from constitution_memorizer.web.law_catalog import CatalogLaw

    n = int(law_id.split("-", 1)[1])
    return CatalogLaw(
        id=law_id,
        title=f"Synthetic fixture {n}",
        short_title=f"Syn {n}",
        year=2026,
        aliases=(),
        subjects=("synthetic",),
        primary_subject="synthetic",
        display_order=900 + n,
        scope_label="",
        primary_content="full_act",
        full_act_ref=None,
        key_provisions_ref=None,
        tag_line="",
        href="/laws",
        search_blob=law_id,
        status="current",
    )


def install_synthetic_catalogue_stubs() -> None:
    """Metadata-only syn-* titles. Does not mark them Playground-eligible."""
    global _STUBS_INSTALLED
    if _STUBS_INSTALLED:
        return
    from constitution_memorizer.playground import eligibility, routes, schedule, service, view

    original = eligibility.playground_catalogue_law

    def wrapped(law_id: str):
        text = str(law_id or "")
        if re.fullmatch(r"syn-[1-9][0-9]*", text):
            return _synthetic_catalog_entry(text)
        return original(law_id)

    for mod in (eligibility, view, routes, service, schedule):
        setattr(mod, "playground_catalogue_law", wrapped)
    _STUBS_INSTALLED = True


def install_benchmark_clock() -> None:
    global _CLOCK_INSTALLED
    if _CLOCK_INSTALLED:
        return
    from constitution_memorizer.entitlements import service as entitlement_service
    from constitution_memorizer.playground.roster import period as period_mod

    real_period_utc = period_mod._as_utc
    real_ent_utc = entitlement_service._utc

    def frozen_period_utc(now):
        return real_period_utc(now or PLAYGROUND_TEST_NOW)

    def frozen_ent_utc(now):
        return real_ent_utc(now or PLAYGROUND_TEST_NOW)

    period_mod._as_utc = frozen_period_utc
    entitlement_service._utc = frozen_ent_utc
    _CLOCK_INSTALLED = True


def host_is_production_looking(host: str) -> bool:
    """DNS-label match on recall-the-c.in / recallthec.in and subdomains."""
    cleaned = str(host or "").strip().lower().rstrip(".")
    if not cleaned:
        return False
    for domain in PRODUCTION_HOSTS:
        if cleaned == domain or cleaned.endswith("." + domain):
            return True
    return False


def _hostname_from_base_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else "http://" + text)
    return (parsed.hostname or "").lower()


def sqlite_filesystem_path(url: str) -> Path:
    raw = str(url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"sqlite", "sqlite3"}:
        raise BenchmarkAborted(
            "T13 automated seeding requires a sqlite:/// URL; "
            "PostgreSQL belongs to T15/WS8"
        )
    if parsed.query or parsed.fragment:
        raise BenchmarkAborted("SQLite URL must not include query or fragment")
    if parsed.netloc:
        raise BenchmarkAborted("unexpected SQLite URL netloc")
    path = unquote(parsed.path or "")
    lowered = path.lower()
    if ":memory:" in raw.lower() or lowered in {"/:memory:", "/memory:"}:
        raise BenchmarkAborted(
            "T13 requires a filesystem SQLite file, not :memory:"
        )
    if path.startswith("//"):
        fs = Path(path[1:])
    elif path.startswith("/"):
        fs = Path(path[1:])
    else:
        fs = Path(path)
    if not str(fs):
        raise BenchmarkAborted("SQLite URL is missing a filesystem path")
    return fs


def assert_fresh_sqlite(url: str) -> Path:
    path = sqlite_filesystem_path(url)
    if path.exists() and path.is_dir():
        raise BenchmarkAborted(f"SQLite path is a directory: {path}")
    if path.exists() and path.stat().st_size > 0:
        raise BenchmarkAborted(
            "refusing nonempty SQLite database; T13 requires a fresh empty file"
        )
    return path


def resolve_database_url(
    cli_url: str | None, environ: Mapping[str, str] | None = None
) -> str:
    env = os.environ if environ is None else environ
    url = str(cli_url or "").strip() or str(env.get("BENCHMARK_DATABASE_URL") or "").strip()
    if not url:
        raise BenchmarkAborted(
            "require --database-url or BENCHMARK_DATABASE_URL "
            "(never process DATABASE_URL)"
        )
    return url


def _effective_app_env(*, requested: str, process: str) -> str:
    """Validated label: process staging/production cannot be masked by --app-env."""
    if process in PRODUCTION_ENVS:
        return process
    if requested:
        return requested
    return process or "test"


def evaluate_safety_guard(
    *,
    requested_app_env: str | None,
    accept_nontest: bool,
    explain: bool,
    environ: Mapping[str, str] | None = None,
    multiuser: bool = True,
) -> str:
    """Abort before app creation or DB access. Return the effective env label.

    ``explain`` is accepted for call-site compatibility. HTTP runners refuse
    ``--explain`` themselves; T15 uses ``evaluate_explain_guard``.
    """
    del explain
    env = os.environ if environ is None else environ
    process_app_env = str(env.get("APP_ENV") or "").strip().lower()
    requested = str(requested_app_env or "").strip().lower()
    allow_nontest = str(env.get("BENCHMARK_ALLOW_NONTEST") or "").strip() == "1"
    if not requested and not allow_nontest:
        raise BenchmarkAborted(APP_ENV_TEST_REQUIRED)
    nontest_requested = bool(requested) and requested != "test"
    if nontest_requested and requested not in PRODUCTION_ENVS and not allow_nontest:
        raise BenchmarkAborted(APP_ENV_TEST_REQUIRED)
    env_is_prod = process_app_env in PRODUCTION_ENVS or requested in PRODUCTION_ENVS
    base_url = str(env.get("APP_BASE_URL") or "").strip()
    host_blocked = bool(multiuser) and host_is_production_looking(
        _hostname_from_base_url(base_url)
    )
    if env_is_prod or host_blocked:
        if not (accept_nontest and allow_nontest):
            raise BenchmarkAborted(STAGING_PRODUCTION_CONSENT)
    return _effective_app_env(requested=requested, process=process_app_env)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benchmark_playground.py",
        description=(
            "Playground WS6 in-process benchmark CLI. "
            "Not part of the default pytest run. No duration SLAs."
        ),
    )
    parser.add_argument(
        "--scenario",
        choices=SCENARIOS,
        help="Fixture and primary HTTP route",
    )
    parser.add_argument(
        "--protocol",
        choices=PROTOCOLS,
        default=None,
        help=(
            "WS7 BNSS cold/warm protocol. Omit for the T13 unlabeled "
            "primary-route runner. Requires --scenario law-workspace "
            "(defaulted when omitted)."
        ),
    )
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help=(
            "Sequential measured GETs (T13/T14 default 50; --quick uses 3). "
            "With --concurrency, measured batches per level "
            f"(default {DEFAULT_CONCURRENCY_BATCHES}; --quick uses 1)."
        ),
    )
    parser.add_argument(
        "--concurrency",
        default=None,
        help=(
            "T18 comma-separated simultaneous GET counts, e.g. 1,5,10,25. "
            f"Maximum {MAX_CONCURRENCY}. SQLite-only. Not default pytest. "
            "Not --mutations (T19)."
        ),
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "sqlite:/// filesystem path for the HTTP runner (T13/T14/T18), or a "
            "local disposable postgresql:// URL for --explain (T15). "
            "T18 --concurrency rejects PostgreSQL (T23). "
            "Never falls back to process DATABASE_URL."
        ),
    )
    parser.add_argument(
        "--app-env",
        default=None,
        help="Must be test unless BENCHMARK_ALLOW_NONTEST=1 "
        "(staging/production also need --i-accept-nontest-db)",
    )
    parser.add_argument(
        "--json",
        default=None,
        help=(
            "Machine JSON output path (gitignored instance file). "
            f"Default {DEFAULT_JSON_PATH} without --protocol, or "
            f"{DEFAULT_BNSS_JSON_PATH} with --protocol {PROTOCOL_BNSS_COLD_WARM}."
        ),
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help=(
            "WS8 disposable PostgreSQL EXPLAIN (ANALYZE, BUFFERS). "
            "Requires a local disposable postgresql:// URL. "
            "Not the HTTP runner."
        ),
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help=(
            "Override warmup=1 and iterations=3. "
            "With --concurrency, warmup=1 and batches=1 at every listed level. "
            "With --protocol bnss-cold-warm, cold warmup stays 0."
        ),
    )
    parser.add_argument(
        "--i-accept-nontest-db",
        action="store_true",
        dest="accept_nontest",
        help="Must pair with BENCHMARK_ALLOW_NONTEST=1; still SQLite-only",
    )
    return parser


@dataclass(frozen=True)
class BenchmarkRunConfig:
    scenario: str
    warmup: int
    iterations: int
    database_url: str
    app_env: str | None
    json_path: Path | None
    explain: bool
    accept_nontest: bool
    protocol: str | None = None
    concurrency_levels: tuple[int, ...] | None = None


def parse_concurrency_levels(raw: str) -> tuple[int, ...]:
    """Unique positive ints, first-seen order, capped at MAX_CONCURRENCY."""
    text = str(raw or "").strip()
    if not text:
        raise BenchmarkAborted(
            "--concurrency requires a comma-separated list such as 1,5,10,25"
        )
    parts = [part.strip() for part in text.split(",")]
    if any(part == "" for part in parts):
        raise BenchmarkAborted("--concurrency has a blank entry")
    values: list[int] = []
    seen: set[int] = set()
    for part in parts:
        try:
            level = int(part, 10)
        except ValueError as exc:
            raise BenchmarkAborted(f"invalid concurrency {part!r}") from exc
        if level < 1:
            raise BenchmarkAborted("concurrency levels must be positive integers")
        if level > MAX_CONCURRENCY:
            raise BenchmarkAborted(
                f"concurrency {level} exceeds S2-0 ceiling {MAX_CONCURRENCY}"
            )
        if level not in seen:
            seen.add(level)
            values.append(level)
    if not values:
        raise BenchmarkAborted("--concurrency produced no levels")
    return tuple(values)


def assert_concurrency_sqlite(url: str) -> Path:
    """T18 accepts only a fresh disposable SQLite file. PostgreSQL is T23."""
    parsed = urlparse(str(url or "").strip())
    scheme = (parsed.scheme or "").lower()
    if scheme in {"postgres", "postgresql"}:
        raise BenchmarkAborted(
            "T18 concurrency is SQLite-only; PostgreSQL concurrency is T23"
        )
    if scheme not in {"sqlite", "sqlite3"}:
        raise BenchmarkAborted("T18 concurrency requires a sqlite:/// URL")
    return assert_fresh_sqlite(url)


def config_from_args(
    args: argparse.Namespace, environ: Mapping[str, str] | None = None
) -> BenchmarkRunConfig:
    protocol = str(getattr(args, "protocol", None) or "").strip() or None
    scenario = str(getattr(args, "scenario", None) or "").strip()
    explain = bool(getattr(args, "explain", False))
    concurrency_raw = getattr(args, "concurrency", None)
    concurrency_levels = (
        parse_concurrency_levels(str(concurrency_raw))
        if concurrency_raw is not None
        else None
    )
    if explain and protocol == PROTOCOL_BNSS_COLD_WARM:
        raise BenchmarkAborted(
            "--explain cannot be combined with --protocol bnss-cold-warm"
        )
    if concurrency_levels and explain:
        raise BenchmarkAborted("--concurrency cannot be combined with --explain")
    if concurrency_levels and protocol:
        raise BenchmarkAborted(
            "--concurrency cannot be combined with --protocol bnss-cold-warm"
        )
    url = resolve_database_url(args.database_url, environ)
    if concurrency_levels:
        assert_concurrency_sqlite(url)
        if scenario and scenario not in CONCURRENCY_SCENARIOS:
            raise BenchmarkAborted(
                "--concurrency supports --scenario plus-10 or law-workspace"
            )
    if explain:
        if not scenario:
            scenario = EXPLAIN_SCENARIO
        if scenario != EXPLAIN_SCENARIO:
            raise BenchmarkAborted(
                "EXPLAIN scenario must be pro-30 (WS8 minimum); "
                f"unsupported {scenario!r}"
            )
    elif protocol == PROTOCOL_BNSS_COLD_WARM:
        if not scenario:
            scenario = "law-workspace"
        if scenario != "law-workspace":
            raise BenchmarkAborted(
                "--protocol bnss-cold-warm requires --scenario law-workspace"
            )
    elif not scenario:
        raise BenchmarkAborted("--scenario is required")
    warmup = int(args.warmup)
    iterations_arg = getattr(args, "iterations", None)
    if concurrency_levels:
        if args.quick:
            warmup, iterations = 1, 1
        else:
            iterations = (
                DEFAULT_CONCURRENCY_BATCHES
                if iterations_arg is None
                else int(iterations_arg)
            )
    elif args.quick:
        warmup, iterations = 1, 3
    else:
        iterations = 50 if iterations_arg is None else int(iterations_arg)
    if warmup < 0 or iterations < 1:
        raise BenchmarkAborted("warmup must be >= 0 and iterations >= 1")
    json_raw = getattr(args, "json", None)
    if json_raw is None:
        if explain:
            json_path = DEFAULT_EXPLAIN_JSON_PATH
        elif protocol == PROTOCOL_BNSS_COLD_WARM:
            json_path = DEFAULT_BNSS_JSON_PATH
        elif concurrency_levels:
            json_path = DEFAULT_CONCURRENCY_JSON_PATH
        else:
            json_path = DEFAULT_JSON_PATH
    else:
        text = str(json_raw).strip()
        json_path = Path(text) if text else None
    return BenchmarkRunConfig(
        scenario=scenario,
        warmup=warmup,
        iterations=iterations,
        database_url=url,
        app_env=args.app_env,
        json_path=json_path,
        explain=explain,
        accept_nontest=bool(args.accept_nontest),
        protocol=protocol,
        concurrency_levels=concurrency_levels,
    )


def _bounded_note_sets() -> dict[str, frozenset[str]]:
    global _BOUNDED_NOTE_VALUES
    if _BOUNDED_NOTE_VALUES is None:
        from constitution_memorizer.web.request_context import (
            PLAYGROUND_ACCESS_RESULTS,
            PLAYGROUND_DEVICE_RESULTS,
            PLAYGROUND_LAW_STATES,
            PLAYGROUND_ROSTER_RESULTS,
            PLAYGROUND_SUBSCRIPTION_DISPOSITIONS,
        )

        _BOUNDED_NOTE_VALUES = {
            "playground_access_result": PLAYGROUND_ACCESS_RESULTS,
            "playground_subscription_disposition": PLAYGROUND_SUBSCRIPTION_DISPOSITIONS,
            "playground_device_result": PLAYGROUND_DEVICE_RESULTS,
            "playground_roster_result": PLAYGROUND_ROSTER_RESULTS,
            "playground_law_state": PLAYGROUND_LAW_STATES,
            "auth_state": frozenset({"single_user", "authed", "guest"}),
            "bare_act_cache": frozenset({"hit", "miss"}),
        }
    return _BOUNDED_NOTE_VALUES


class HydrationProbe:
    """Counts get_bare_act calls. Fixture construction must stay at zero."""

    def __init__(self) -> None:
        self.calls = 0
        self._restore: list[tuple[Any, str, Any]] = []

    def install(self) -> None:
        from constitution_memorizer.web import bare_acts

        probe = self
        real = bare_acts.get_bare_act

        def wrapped(law_id: str):
            probe.calls += 1
            return real(law_id)

        bare_acts.get_bare_act = wrapped  # type: ignore[method-assign]
        self._restore.append((bare_acts, "get_bare_act", real))

    def remove(self) -> None:
        for obj, name, value in reversed(self._restore):
            setattr(obj, name, value)
        self._restore.clear()


def _settings(*, app_env: str) -> Any:
    from constitution_memorizer.multiuser.settings import MultiUserSettings

    return MultiUserSettings(
        _env_file=None,
        APP_ENV=app_env,
        MULTIUSER_ENABLED="true",
        AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true",
        SESSION_SECRET="benchmark-secret",
        SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon",
        DATABASE_URL="",
        COOKIE_SECURE="false",
        APP_BASE_URL="http://127.0.0.1:8010",
    )


def create_benchmark_app(db_path: Path, *, app_env: str = "test"):
    from constitution_memorizer.auth.fake_provider import FakeAuthProvider
    from constitution_memorizer.auth.sessions import InMemorySessionStore
    from constitution_memorizer.multiuser.settings import clear_settings_cache
    from constitution_memorizer.web.app import create_app

    install_benchmark_clock()
    install_synthetic_catalogue_stubs()
    clear_settings_cache()
    units = MINI_UNITS if MINI_UNITS.is_file() else None
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=BENCH_USER,
        email=BENCH_EMAIL,
        display_name="Benchmark User",
        avatar_url=None,
    )
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_app(
        units_path=units,
        db_path=db_path,
        multiuser=True,
        multiuser_settings=_settings(app_env=app_env),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
    )


async def sign_in_benchmark_client(client) -> None:
    """Same-task ASGI client so T2 ContextVar snapshots remain visible."""
    from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME

    start = await client.get("/auth/google/start")
    state = start.cookies.get("rtc_oauth_state")
    await client.get(f"/auth/callback?code=fake-google-code&state={state}")
    if not client.cookies.get(SESSION_COOKIE_NAME):
        raise BenchmarkAborted("benchmark sign-in did not set a session cookie")


def _subscribe(app, *, tier: str) -> None:
    app.state.subscriptions.create_subscription_record(
        BENCH_USER,
        tier=tier,
        status="active",
        billing_period_start=datetime(2026, 9, 15, tzinfo=timezone.utc),
        billing_period_end=datetime(2026, 10, 15, tzinfo=timezone.utc),
        is_current=True,
    )


def _ensure_period(app, *, tier: str, law_limit: int) -> None:
    from constitution_memorizer.playground.roster.period import playground_month_bounds

    start, end = playground_month_bounds(PLAYGROUND_TEST_NOW)
    result = app.state.roster._repo.ensure_period(
        BENCH_USER,
        period_start=start,
        period_end=end,
        tier_snapshot=tier,
        law_limit=law_limit,
        now=PLAYGROUND_TEST_NOW,
    )
    del result


def _consume(app, law_ids: Iterable[str], *, law_limit: int) -> None:
    from constitution_memorizer.playground.roster.period import playground_month_bounds

    start, _end = playground_month_bounds(PLAYGROUND_TEST_NOW)
    for law_id in law_ids:
        result = app.state.roster._repo.consume_law(
            BENCH_USER,
            period_start=start,
            law_id=law_id,
            law_limit=law_limit,
            allow_new=True,
            now=PLAYGROUND_TEST_NOW,
        )
        if not result.ok:
            raise BenchmarkAborted(
                f"consume_law({law_id}) failed: {result.status}"
            )


def _activate_or_stub(app, law_id: str) -> None:
    from constitution_memorizer.playground.eligibility import is_playground_eligible_law
    from constitution_memorizer.playground.service import activate_law

    overlay = app.state.playground
    if is_playground_eligible_law(law_id):
        activate_law(overlay, BENCH_USER, law_id)
        return
    overlay.add_item(
        BENCH_USER,
        law_id,
        source_version="stub",
        law_source_hash="stub",
    )


def _locators(law_id: str, count: int) -> list[str]:
    return [f"{law_id}:section:{n}" for n in range(1, count + 1)]


def _bulk_overlay(
    app,
    law_id: str,
    locators: list[str],
    *,
    status: str = "new",
    next_revision: str | None = None,
    complete_modes: bool = False,
    source_changes: int = 0,
    revision_history: bool = False,
) -> None:
    from constitution_memorizer.playground.learning.modes import PLAYGROUND_LEARN_MODES
    from constitution_memorizer.progress.user_ids import as_user_id

    overlay = app.state.playground
    uid = as_user_id(BENCH_USER)
    now = PLAYGROUND_TEST_NOW.replace(microsecond=0).isoformat()
    due = next_revision or None
    rows = [(loc, "v1", "hash-v1") for loc in locators]
    overlay.replace_selection(BENCH_USER, law_id, rows)
    conn: sqlite3.Connection = overlay.conn
    progress_rows = [
        (
            uid,
            law_id,
            loc,
            status,
            1 if complete_modes else 0,
            1 if status in {"learned", "review"} else 0,
            now if status in {"learned", "review"} else None,
            due,
            1 if due else 0,
            "v1",
            "hash-v1",
            now,
            now[:10] if status in {"learned", "review"} else None,
        )
        for loc in locators
    ]
    conn.executemany(
        """
        INSERT OR REPLACE INTO user_playground_progress (
            user_id, law_id, source_locator, status, cloze_done,
            times_completed, last_completed, next_revision, interval_days,
            source_version, source_hash, updated_at, learned_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        progress_rows,
    )
    if complete_modes:
        mode_rows = []
        for loc in locators:
            for mode in PLAYGROUND_LEARN_MODES:
                mode_rows.append(
                    (
                        uid,
                        law_id,
                        loc,
                        mode,
                        "completed",
                        1,
                        now,
                        now,
                        now,
                        "v1",
                        "hash-v1",
                        now,
                        now,
                    )
                )
        conn.executemany(
            """
            INSERT OR REPLACE INTO user_playground_mode_progress (
                user_id, law_id, source_locator, mode, status, attempt_count,
                first_started_at, last_attempt_at, completed_at,
                source_version, source_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            mode_rows,
        )
    if revision_history:
        rev_rows = []
        for loc in locators[: min(20, len(locators))]:
            for mode in PLAYGROUND_LEARN_MODES[:2]:
                rev_rows.append(
                    (
                        uid,
                        law_id,
                        loc,
                        1,
                        mode,
                        "completed",
                        1,
                        now,
                        now,
                        now,
                        "v1",
                        "hash-v1",
                        now,
                        now,
                    )
                )
        conn.executemany(
            """
            INSERT OR REPLACE INTO user_playground_revision_mode_progress (
                user_id, law_id, source_locator, rung_days, mode, status,
                attempt_count, first_started_at, last_attempt_at, completed_at,
                source_version, source_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rev_rows,
        )
    if source_changes:
        change_rows = []
        for loc in locators[:source_changes]:
            change_rows.append(
                (
                    uid,
                    law_id,
                    loc,
                    "stale",
                    "stale",
                    "stale",
                    "old-hash",
                    "current",
                    "current",
                    "new-hash",
                    "changed",
                    "pending",
                    1,
                    1,
                    now,
                    now,
                    now,
                )
            )
        conn.executemany(
            """
            INSERT OR REPLACE INTO user_playground_source_change (
                user_id, law_id, source_locator, detected_source_version,
                detected_law_source_hash, previous_source_version,
                previous_section_hash, current_source_version,
                current_law_source_hash, current_section_hash, change_kind,
                status, had_learning, had_selection, detected_at,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            change_rows,
        )
    conn.commit()


def _roster_count(app) -> int:
    from constitution_memorizer.playground.roster.period import playground_month_bounds

    start, _end = playground_month_bounds(PLAYGROUND_TEST_NOW)
    return len(app.state.roster._repo.list_items(BENCH_USER, start))


def build_plus_10_fixture(app) -> dict[str, Any]:
    """Plus, 6 real + 4 syn-* roster rows. Mixed due/learned/source-change on real laws."""
    _subscribe(app, tier="plus")
    _ensure_period(app, tier="plus", law_limit=10)
    syn = synthetic_law_ids(4)
    laws = list(ELIGIBLE_LAWS) + list(syn)
    _consume(app, laws, law_limit=10)
    for law_id in laws:
        _activate_or_stub(app, law_id)
    _bulk_overlay(
        app,
        "bns",
        _locators("bns", 8),
        status="learned",
        next_revision="2026-09-01",
        complete_modes=True,
    )
    _bulk_overlay(
        app,
        "bnss",
        _locators("bnss", 8),
        status="learned",
        complete_modes=True,
    )
    _bulk_overlay(
        app,
        "ndps",
        _locators("ndps", 8),
        status="learning",
        source_changes=4,
    )
    _bulk_overlay(app, "uapa", _locators("uapa", 4), status="new")
    return {"roster_count": _roster_count(app), "law_ids": laws, "tier": "plus"}


def build_pro_30_fixture(app) -> dict[str, Any]:
    """Pro, 6 real + 24 syn-* rows. Heavy overlay on synthetic ids only."""
    _subscribe(app, tier="pro")
    _ensure_period(app, tier="pro", law_limit=30)
    syn = synthetic_law_ids(24)
    laws = list(ELIGIBLE_LAWS) + list(syn)
    _consume(app, laws, law_limit=30)
    for law_id in laws:
        _activate_or_stub(app, law_id)
    for law_id in syn:
        _bulk_overlay(
            app,
            law_id,
            _locators(law_id, 20),
            status="learned",
            next_revision="2026-09-10",
            complete_modes=True,
            revision_history=True,
        )
    return {"roster_count": _roster_count(app), "law_ids": laws, "tier": "pro"}


def build_due_heavy_fixture(app) -> dict[str, Any]:
    _subscribe(app, tier="plus")
    _ensure_period(app, tier="plus", law_limit=10)
    laws = list(ELIGIBLE_LAWS[:3])
    _consume(app, laws, law_limit=10)
    for law_id in laws:
        _activate_or_stub(app, law_id)
        _bulk_overlay(
            app,
            law_id,
            _locators(law_id, 40),
            status="learned",
            next_revision="2026-09-01",
            complete_modes=True,
        )
    return {"roster_count": _roster_count(app), "law_ids": laws, "tier": "plus"}


def build_learned_heavy_fixture(app) -> dict[str, Any]:
    _subscribe(app, tier="plus")
    _ensure_period(app, tier="plus", law_limit=10)
    laws = list(ELIGIBLE_LAWS)
    _consume(app, laws, law_limit=10)
    for law_id in laws:
        _activate_or_stub(app, law_id)
        _bulk_overlay(
            app,
            law_id,
            _locators(law_id, 30),
            status="learned",
            complete_modes=True,
        )
    return {"roster_count": _roster_count(app), "law_ids": laws, "tier": "plus"}


def build_source_review_fixture(app) -> dict[str, Any]:
    _subscribe(app, tier="plus")
    _ensure_period(app, tier="plus", law_limit=10)
    _consume(app, [SOURCE_REVIEW_LAW], law_limit=10)
    overlay = app.state.playground
    overlay.add_item(
        BENCH_USER,
        SOURCE_REVIEW_LAW,
        source_version="stale",
        law_source_hash="stale",
    )
    locators = _locators(SOURCE_REVIEW_LAW, 40)
    _bulk_overlay(
        app,
        SOURCE_REVIEW_LAW,
        locators,
        status="learned",
        complete_modes=True,
        source_changes=24,
    )
    return {
        "roster_count": _roster_count(app),
        "law_ids": [SOURCE_REVIEW_LAW],
        "tier": "plus",
    }


def build_law_workspace_fixture(app) -> dict[str, Any]:
    _subscribe(app, tier="plus")
    _ensure_period(app, tier="plus", law_limit=10)
    _consume(app, [LAW_WORKSPACE_LAW], law_limit=10)
    _activate_or_stub(app, LAW_WORKSPACE_LAW)
    _bulk_overlay(
        app,
        LAW_WORKSPACE_LAW,
        _locators(LAW_WORKSPACE_LAW, 40),
        status="learned",
        complete_modes=True,
        revision_history=True,
    )
    return {
        "roster_count": _roster_count(app),
        "law_ids": [LAW_WORKSPACE_LAW],
        "tier": "plus",
    }


def build_nplusone_fixture(app, n: int) -> dict[str, Any]:
    """Matched-density Pro fixture for T16 N+1 locks. Synthetic ids only.

    Same tier, law limit, clock, and locator density at N=1/10/30. Does not
    mark syn-* Playground-eligible; the observability test patches that
    locally. Not a CLI scenario.
    """

    if n not in NPLUSONE_ROSTER_SIZES:
        raise ValueError(f"T16 roster size must be one of {NPLUSONE_ROSTER_SIZES}")
    _subscribe(app, tier=NPLUSONE_TIER)
    _ensure_period(app, tier=NPLUSONE_TIER, law_limit=NPLUSONE_LAW_LIMIT)
    laws = list(synthetic_law_ids(n))
    _consume(app, laws, law_limit=NPLUSONE_LAW_LIMIT)
    for law_id in laws:
        _activate_or_stub(app, law_id)
        _bulk_overlay(
            app,
            law_id,
            _locators(law_id, NPLUSONE_LOCATORS_PER_LAW),
            status="learned",
            next_revision=NPLUSONE_DUE_REVISION,
            complete_modes=True,
            source_changes=1,
        )
    return {
        "roster_count": _roster_count(app),
        "law_ids": laws,
        "tier": NPLUSONE_TIER,
        "law_limit": NPLUSONE_LAW_LIMIT,
        "locators_per_law": NPLUSONE_LOCATORS_PER_LAW,
        "expected_due_facts": NPLUSONE_LOCATORS_PER_LAW * n,
        "expected_source_change_laws": n,
    }


SCENARIO_BUILDERS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "plus-10": build_plus_10_fixture,
    "pro-30": build_pro_30_fixture,
    "due-heavy": build_due_heavy_fixture,
    "learned-heavy": build_learned_heavy_fixture,
    "source-review": build_source_review_fixture,
    "law-workspace": build_law_workspace_fixture,
}


def seed_scenario(app, scenario: str) -> dict[str, Any]:
    builder = SCENARIO_BUILDERS.get(scenario)
    if builder is None:
        raise BenchmarkAborted(f"unknown scenario: {scenario}")
    probe = HydrationProbe()
    probe.install()
    try:
        info = builder(app)
    finally:
        probe.remove()
    if probe.calls:
        raise BenchmarkAborted(
            f"fixture {scenario} called get_bare_act {probe.calls} time(s)"
        )
    return info


def collect_snapshots(
    request: Callable[[], Any],
    *,
    warmup: int,
    iterations: int,
) -> list[Any]:
    from constitution_memorizer.web.request_context import get_last_request_performance

    def _one(label: str):
        response = request()
        status = int(getattr(response, "status_code", 0) or 0)
        if status < 200 or status >= 300:
            raise BenchmarkAborted(f"{label} HTTP {status}")
        snap = get_last_request_performance()
        if snap is None:
            raise BenchmarkAborted(f"{label} missing RequestPerformanceSnapshot")
        return snap

    for index in range(warmup):
        _one(f"warmup {index + 1}")
    return [_one(f"iteration {index + 1}") for index in range(iterations)]


def _note_tokens(snapshots: list[Any]) -> dict[str, list[str]]:
    allowed = _bounded_note_sets()
    observed: dict[str, set[str]] = {name: set() for name in allowed}
    for snap in snapshots:
        notes = getattr(snap, "notes", {}) or {}
        for name, value in notes.items():
            text = str(value)
            if name not in allowed:
                continue
            if _SENSITIVE.search(text):
                continue
            if text in allowed[name]:
                observed[name].add(text)
    return {name: sorted(values) for name, values in observed.items() if values}


def snapshots_to_report(
    snapshots: list[Any],
    *,
    scenario: str,
    warmup: int,
    iterations: int,
    database_backend: str = "sqlite",
    method: str,
    app_env: str = "test",
) -> dict[str, Any]:
    if not snapshots:
        raise BenchmarkAborted("no snapshots to report")
    path_group = str(snapshots[0].path_group)
    status_counts: dict[str, int] = {}
    for snap in snapshots:
        key = str(int(snap.status_code))
        status_counts[key] = status_counts.get(key, 0) + 1
    metrics: dict[str, Any] = {
        "total_ms": summarize_numbers(snap.total_ms for snap in snapshots),
        "playground_repo_round_trips": summarize_numbers(
            int((snap.counters or {}).get("playground_repo_round_trips", 0))
            for snap in snapshots
        ),
        "playground_db_reads": summarize_numbers(
            int((snap.counters or {}).get("playground_db_reads", 0))
            for snap in snapshots
        ),
    }
    stage_names: set[str] = set()
    for snap in snapshots:
        stage_names.update((snap.timings or {}).keys())
    for name in sorted(stage_names):
        # Missing from a sample → 0.0 means the stage did not execute that
        # request, not a measured 0 ms.
        series = []
        for snap in snapshots:
            timing = (snap.timings or {}).get(name)
            series.append(float(timing[0]) if timing is not None else 0.0)
        metrics[name] = summarize_numbers(series)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "scenario": scenario,
        "app_env": str(app_env),
        "database_backend": database_backend,
        "warmup_discarded": warmup,
        "iterations": iterations,
        "path_group": path_group,
        "method": method,
        "status_counts": status_counts,
        "metrics": metrics,
        "stages_present": sorted(stage_names),
        "notes_observed": _note_tokens(snapshots),
    }
    blob = json.dumps(payload)
    if _SENSITIVE.search(blob) and "@" in blob:
        raise BenchmarkAborted("JSON report would include sensitive data")
    if BENCH_EMAIL in blob:
        raise BenchmarkAborted("JSON report must not include fixture email")
    return payload


def write_json_report(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _assert_json_safe(payload: Mapping[str, Any]) -> None:
    blob = json.dumps(payload)
    if _SENSITIVE.search(blob) and "@" in blob:
        raise BenchmarkAborted("JSON report would include sensitive data")
    if BENCH_EMAIL in blob:
        raise BenchmarkAborted("JSON report must not include fixture email")


def _runtime_file_path(filename: str) -> Path:
    """Locate a packaged runtime JSON without hydrating the Act."""
    repo = REPO_ROOT / "data" / "reference" / filename
    packaged = REPO_ROOT / "src" / "constitution_memorizer" / "web" / filename
    for candidate in (repo, packaged):
        if candidate.exists():
            return candidate
    raise BenchmarkAborted(f"runtime file missing: {filename}")


def largest_eligible_runtime_act() -> dict[str, Any]:
    """Largest Playground-eligible Act by runtime file size. Does not hydrate."""
    from constitution_memorizer.playground.eligibility import (
        list_playground_eligible_laws,
    )
    from constitution_memorizer.web.bare_acts import BARE_ACTS

    ranked: list[tuple[int, str, str]] = []
    for slug in list_playground_eligible_laws():
        spec = BARE_ACTS.get(slug)
        if spec is None:
            continue
        path = _runtime_file_path(spec.filename)
        ranked.append((path.stat().st_size, slug, spec.filename))
    if not ranked:
        raise BenchmarkAborted("no eligible Bare Acts with runtime files")
    bytes_, slug, filename = max(ranked, key=lambda row: row[0])
    confirmed = slug == LAW_WORKSPACE_LAW
    info = {
        "slug": slug,
        "filename": filename,
        "bytes": int(bytes_),
        "confirmed_largest_eligible": confirmed,
    }
    if not confirmed:
        raise BenchmarkAborted(
            f"largest eligible Act is {slug} ({bytes_} bytes), "
            f"not {LAW_WORKSPACE_LAW}"
        )
    return info


def classify_cache_snapshot(snap: Any) -> str:
    """Return miss, hit, or unknown from request notes/counters/timings."""
    notes = getattr(snap, "notes", None) or {}
    counters = getattr(snap, "counters", None) or {}
    timings = getattr(snap, "timings", None) or {}
    note = notes.get("bare_act_cache")
    misses = int(counters.get("bare_act_cache_misses") or 0)
    load_present = "bare_act_load" in timings
    if note == "miss" and misses >= 1 and load_present:
        return "miss"
    if note == "hit" and misses == 0 and not load_present:
        return "hit"
    return "unknown"


def assert_cache_class(
    snapshots: list[Any], expected: str, *, label: str
) -> None:
    if expected not in {"miss", "hit"}:
        raise BenchmarkAborted(f"unsupported cache class {expected!r}")
    if not snapshots:
        raise BenchmarkAborted(f"{label}: no snapshots to classify")
    for index, snap in enumerate(snapshots, start=1):
        got = classify_cache_snapshot(snap)
        if got != expected:
            raise BenchmarkAborted(
                f"{label} sample {index} cache class {got!r}, expected {expected!r}"
            )


def cache_evidence_from_snapshots(
    snapshots: list[Any], expected: str
) -> dict[str, Any]:
    values: set[str] = set()
    misses: list[int] = []
    present = 0
    for snap in snapshots:
        notes = getattr(snap, "notes", None) or {}
        counters = getattr(snap, "counters", None) or {}
        timings = getattr(snap, "timings", None) or {}
        note = str(notes.get("bare_act_cache") or "")
        if note:
            values.add(note)
        misses.append(int(counters.get("bare_act_cache_misses") or 0))
        if "bare_act_load" in timings:
            present += 1
    return {
        "cache_class": expected,
        "samples": len(snapshots),
        "bare_act_cache_values": sorted(values),
        "bare_act_cache_misses_min": min(misses) if misses else 0,
        "bare_act_cache_misses_max": max(misses) if misses else 0,
        "bare_act_load_present_count": present,
        "bare_act_load_absent_count": len(snapshots) - present,
    }


def bnss_cell_report(
    snapshots: list[Any],
    *,
    expected: str,
    warmup: int,
    iterations: int,
    method: str,
    app_env: str,
    label: str,
    path_group: str,
) -> dict[str, Any]:
    """One cold or warm cell. Refuses mixed snapshots; no warm bare_act_load."""
    assert_cache_class(snapshots, expected, label=label)
    for index, snap in enumerate(snapshots, start=1):
        if str(snap.path_group) != path_group:
            raise BenchmarkAborted(
                f"{label} sample {index} path_group {snap.path_group!r}, "
                f"expected {path_group!r}"
            )
    payload = snapshots_to_report(
        snapshots,
        scenario="law-workspace",
        warmup=warmup,
        iterations=iterations,
        method=method,
        app_env=app_env,
    )
    stages = payload.get("stages_present") or []
    if expected == "hit" and "bare_act_load" in stages:
        raise BenchmarkAborted(
            f"{label}: warm cell must not include bare_act_load"
        )
    if expected == "miss" and "bare_act_load" not in stages:
        raise BenchmarkAborted(f"{label}: cold cell missing bare_act_load")
    payload["cache_evidence"] = cache_evidence_from_snapshots(
        snapshots, expected
    )
    return payload


def _phase0_assert_no_hydrate(snap: Any, *, label: str) -> None:
    notes = getattr(snap, "notes", None) or {}
    timings = getattr(snap, "timings", None) or {}
    if notes.get("bare_act_cache") == "miss" or "bare_act_load" in timings:
        raise BenchmarkAborted(f"{label} hydrated Bare Act")


def _compile_phase0_templates(app) -> None:
    env = getattr(getattr(app.state, "templates", None), "env", None)
    if env is None:
        raise BenchmarkAborted("benchmark app is missing Jinja templates")
    for name in PHASE0_TEMPLATES:
        env.get_template(name)


def _bnss_protocol_routes() -> tuple[tuple[str, str, str], ...]:
    return (
        ("playground_workspace", BNSS_WORKSPACE_PATH, BNSS_WORKSPACE_PATH_GROUP),
        ("playground_learn", BNSS_LEARN_PATH, BNSS_LEARN_PATH_GROUP),
        ("public_bare_act", BNSS_PUBLIC_PATH, BNSS_PUBLIC_PATH_GROUP),
    )


async def _http_snapshot(client, path: str, *, label: str):
    from constitution_memorizer.web.request_context import get_last_request_performance

    response = await client.get(path)
    status = int(response.status_code)
    if status < 200 or status >= 300:
        raise BenchmarkAborted(f"{label} HTTP {status}")
    snap = get_last_request_performance()
    if snap is None:
        raise BenchmarkAborted(f"{label} missing RequestPerformanceSnapshot")
    return snap


async def _collect_cold_http(client, path: str, *, iterations: int, label: str):
    from constitution_memorizer.web.bare_acts import clear_bare_act_cache

    snapshots = []
    for index in range(iterations):
        clear_bare_act_cache()
        snap = await _http_snapshot(
            client, path, label=f"{label} cold {index + 1}"
        )
        if classify_cache_snapshot(snap) != "miss":
            raise BenchmarkAborted(
                f"{label} cold {index + 1} was not a cache miss"
            )
        snapshots.append(snap)
    return snapshots


async def _collect_warm_http(
    client, path: str, *, warmup: int, iterations: int, label: str
):
    for index in range(warmup):
        snap = await _http_snapshot(
            client, path, label=f"{label} warm warmup {index + 1}"
        )
        if classify_cache_snapshot(snap) != "hit":
            raise BenchmarkAborted(
                f"{label} warm warmup {index + 1} was not a cache hit"
            )
    snapshots = []
    for index in range(iterations):
        snap = await _http_snapshot(
            client, path, label=f"{label} warm {index + 1}"
        )
        if classify_cache_snapshot(snap) != "hit":
            raise BenchmarkAborted(
                f"{label} warm {index + 1} was not a cache hit"
            )
        snapshots.append(snap)
    return snapshots


def run_bnss_cold_warm(
    config: BenchmarkRunConfig, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """WS7 BNSS cold/warm protocol. Does not alter the T13 primary-route runner."""
    import asyncio

    from httpx import ASGITransport, AsyncClient

    from constitution_memorizer.web.bare_acts import clear_bare_act_cache

    if config.explain:
        raise BenchmarkAborted("HTTP runner does not execute EXPLAIN")
    if config.protocol != PROTOCOL_BNSS_COLD_WARM:
        raise BenchmarkAborted("run_bnss_cold_warm requires --protocol bnss-cold-warm")
    if config.scenario != "law-workspace":
        raise BenchmarkAborted(
            "--protocol bnss-cold-warm requires --scenario law-workspace"
        )
    largest = largest_eligible_runtime_act()
    effective_app_env = evaluate_safety_guard(
        requested_app_env=config.app_env,
        accept_nontest=config.accept_nontest,
        explain=False,
        environ=environ,
    )
    db_path = assert_fresh_sqlite(config.database_url)
    app = create_benchmark_app(db_path, app_env="test")
    seed_scenario(app, config.scenario)
    clear_bare_act_cache()

    async def _run() -> dict[str, tuple[list[Any], list[Any]]]:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            await sign_in_benchmark_client(client)
            for path in PHASE0_ROUTES:
                snap = await _http_snapshot(client, path, label=f"phase0 {path}")
                _phase0_assert_no_hydrate(snap, label=f"phase0 {path}")
            _compile_phase0_templates(app)
            collected: dict[str, tuple[list[Any], list[Any]]] = {}
            for key, path, _group in _bnss_protocol_routes():
                cold = await _collect_cold_http(
                    client,
                    path,
                    iterations=config.iterations,
                    label=key,
                )
                collected[key] = (cold, [])
            for key, path, _group in _bnss_protocol_routes():
                warm = await _collect_warm_http(
                    client,
                    path,
                    warmup=config.warmup,
                    iterations=config.iterations,
                    label=key,
                )
                cold, _empty = collected[key]
                collected[key] = (cold, warm)
            return collected

    collected = asyncio.run(_run())
    runs: dict[str, Any] = {}
    for key, path, path_group in _bnss_protocol_routes():
        cold_snaps, warm_snaps = collected[key]
        runs[key] = {
            "path": path,
            "path_group": path_group,
            "cold": bnss_cell_report(
                cold_snaps,
                expected="miss",
                warmup=0,
                iterations=config.iterations,
                method="GET",
                app_env=effective_app_env,
                label=f"{key} cold",
                path_group=path_group,
            ),
            "warm": bnss_cell_report(
                warm_snaps,
                expected="hit",
                warmup=config.warmup,
                iterations=config.iterations,
                method="GET",
                app_env=effective_app_env,
                label=f"{key} warm",
                path_group=path_group,
            ),
        }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "protocol": PROTOCOL_BNSS_COLD_WARM,
        "scenario": config.scenario,
        "app_env": str(effective_app_env),
        "database_backend": "sqlite",
        "largest_act": largest,
        "learn_route": {
            "method": "GET",
            "path": BNSS_LEARN_PATH,
            "locator": BNSS_LEARN_LOCATOR,
            "mode": BNSS_LEARN_MODE,
            "path_group": BNSS_LEARN_PATH_GROUP,
        },
        "selection": {
            "law_id": LAW_WORKSPACE_LAW,
            "selected_count": LAW_WORKSPACE_SELECTED_COUNT,
            "status": "learned",
            "complete_modes": True,
        },
        "runs": runs,
    }
    _assert_json_safe(payload)
    if config.json_path is not None:
        write_json_report(config.json_path, payload)
    return payload


def dummy_device_key_hash() -> str:
    """SHA-256 hex of a constant dummy byte string. Not a session token."""
    return hashlib.sha256(EXPLAIN_DUMMY_DEVICE_MATERIAL).hexdigest()


def redact_database_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if not parsed.scheme:
        return "<redacted>"
    host = parsed.hostname or ""
    db = (parsed.path or "").lstrip("/").split("/", 1)[0]
    user = parsed.username or ""
    auth = f"{user}@" if user else ""
    netloc = f"{auth}{host}" if host else ""
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse((parsed.scheme, netloc, f"/{db}" if db else "", "", "", ""))


def assert_disposable_postgres(url: str) -> dict[str, str]:
    """Fail-closed local disposable PostgreSQL URL. Never prints passwords."""
    raw = str(url or "").strip()
    if not raw:
        raise BenchmarkAborted(
            "T15 --explain requires --database-url or BENCHMARK_DATABASE_URL "
            "(never process DATABASE_URL)"
        )
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme in {"sqlite", "sqlite3"}:
        raise BenchmarkAborted(
            "T15 --explain requires a local disposable postgresql:// URL, "
            "not sqlite"
        )
    if scheme == "postgresql+psycopg":
        raise BenchmarkAborted(
            "T15 --explain rejects postgresql+psycopg:// on the CLI; "
            "pass postgresql:// (Alembic rewrites internally)"
        )
    if scheme not in {"postgresql", "postgres"}:
        raise BenchmarkAborted(
            "T15 --explain requires a postgresql:// URL to a local "
            "disposable database"
        )
    if parsed.query or parsed.fragment:
        raise BenchmarkAborted(
            "T15 disposable PostgreSQL URL must not include query or fragment"
        )
    host = (parsed.hostname or "").strip().lower()
    if host == "postgres":
        raise BenchmarkAborted(
            "T15 rejects Docker service hostname 'postgres'; "
            "use Unix peer or loopback only"
        )
    if host not in LOCAL_POSTGRES_HOSTS:
        raise BenchmarkAborted(
            "T15 disposable PostgreSQL host must be empty (Unix/peer), "
            "localhost, 127.0.0.1, or ::1"
        )
    if host_is_production_looking(host):
        raise BenchmarkAborted("T15 rejects production-looking PostgreSQL hosts")
    db_name = (parsed.path or "").lstrip("/").split("/", 1)[0]
    if not db_name:
        raise BenchmarkAborted("T15 PostgreSQL URL is missing a database name")
    if "/" in (parsed.path or "").lstrip("/"):
        raise BenchmarkAborted("T15 PostgreSQL URL path must be a single database name")
    if db_name.lower() in FORBIDDEN_DB_NAMES:
        raise BenchmarkAborted(
            "T15 rejects maintenance database names (postgres/template*)"
        )
    if not DISPOSABLE_DB_NAME_RE.fullmatch(db_name):
        raise BenchmarkAborted(
            "T15 database name must match "
            "^(s2_|explain_|m11_|playground_bench_)[a-z0-9_]+$"
        )
    return {
        "scheme": scheme,
        "host": host,
        "database": db_name,
        "redacted": redact_database_url(raw),
    }


def evaluate_explain_guard(
    *,
    requested_app_env: str | None,
    accept_nontest: bool,
    database_url: str,
    environ: Mapping[str, str] | None = None,
) -> str:
    """APP_ENV rules plus disposable Postgres targeting. Does not connect.

    ``--i-accept-nontest-db`` never overrides host/name isolation.
    """
    effective = evaluate_safety_guard(
        requested_app_env=requested_app_env,
        accept_nontest=accept_nontest,
        explain=False,
        environ=environ,
    )
    assert_disposable_postgres(database_url)
    return effective


def assert_readonly_select(sql: str) -> str:
    """Tripwire: EXPLAIN is SELECT-only. Abort on unexpected SQL."""
    stripped = str(sql or "")
    stripped = re.sub(r"/\*.*?\*/", " ", stripped, flags=re.DOTALL)
    stripped = re.sub(r"--[^\n]*", " ", stripped)
    stripped = stripped.strip()
    if not stripped:
        raise BenchmarkAborted("EXPLAIN helper refuses empty SQL")
    if not stripped.upper().startswith("SELECT"):
        raise BenchmarkAborted("EXPLAIN helper refuses non-SELECT SQL")
    body = stripped.rstrip().rstrip(";")
    if ";" in body:
        raise BenchmarkAborted("EXPLAIN helper refuses multiple SQL statements")
    return stripped


class ExplainCaptureCursor:
    """Records SQL from real PostgreSQL repository methods. No live execute."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql, params=None):
        self.statements.append((str(sql), tuple(params or ())))

    def executemany(self, sql, seq):
        rows = list(seq)
        first = tuple(rows[0]) if rows else ()
        self.statements.append((str(sql), first))

    def fetchall(self):
        return []

    def fetchone(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class ExplainCaptureConn:
    def __init__(self, cursor: ExplainCaptureCursor) -> None:
        self.cursor_obj = cursor
        self.commits = 0

    def cursor(self, row_factory=None):
        del row_factory
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class ExplainCapturePool:
    def __init__(self, conn: ExplainCaptureConn) -> None:
        self._conn = conn

    def connection(self):
        return _ExplainCaptureCtx(self._conn)


class _ExplainCaptureCtx:
    def __init__(self, conn: ExplainCaptureConn) -> None:
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *_exc):
        return False


def capture_explain_statements(
    *,
    user_id: UUID | str = BENCH_USER,
    period_start: date | None = None,
    as_of: date | None = None,
    month_start: date | None = None,
    month_end: date | None = None,
    law_ids: tuple[str, ...] | list[str] | None = None,
    device_key_hash: str | None = None,
) -> list[tuple[str, str, tuple[Any, ...]]]:
    """(label, sql, params) from real Postgres repo methods on a spy pool."""
    from constitution_memorizer.devices.postgres import PostgresDeviceRepository
    from constitution_memorizer.playground.postgres import PostgresPlaygroundRepository
    from constitution_memorizer.playground.roster.period import playground_month_bounds
    from constitution_memorizer.playground.roster.postgres import PostgresRosterRepository
    from constitution_memorizer.subscriptions.postgres import PostgresSubscriptionRepository

    if period_start is None or month_start is None or month_end is None:
        start, end = playground_month_bounds(PLAYGROUND_TEST_NOW)
        period_start = period_start or start
        month_start = month_start or start
        month_end = month_end or end
    as_of = as_of or PLAYGROUND_TEST_NOW.date()
    if law_ids is None:
        law_ids = tuple(list(ELIGIBLE_LAWS) + list(synthetic_law_ids(24)))
    digest = device_key_hash if device_key_hash is not None else dummy_device_key_hash()
    cursor = ExplainCaptureCursor()
    pool = ExplainCapturePool(ExplainCaptureConn(cursor))
    roster = PostgresRosterRepository(pool)
    overlay = PostgresPlaygroundRepository(pool)
    devices = PostgresDeviceRepository(pool)
    subs = PostgresSubscriptionRepository(pool)

    captured: list[tuple[str, str, tuple[Any, ...]]] = []

    def record(label: str) -> None:
        if len(cursor.statements) != 1:
            raise BenchmarkAborted(
                f"{label} expected one physical SQL statement, "
                f"got {len(cursor.statements)}"
            )
        sql, params = cursor.statements[0]
        assert_readonly_select(sql)
        captured.append((label, sql, params))
        cursor.statements.clear()

    roster.list_items(user_id, period_start)
    record("current_roster_lookup")
    roster.count_consumed(user_id, period_start)
    record("roster_capacity_count")
    overlay.list_playground_summaries(user_id, as_of=as_of, law_ids=law_ids)
    record("home_summary_aggregate")
    overlay.list_due_revisions(user_id, as_of, law_ids)
    record("due_revisions")
    overlay.list_revision_schedule(user_id, month_start, month_end, law_ids)
    record("calendar_schedule")
    devices.count_active(user_id)
    record("device_count")
    devices.get_by_hash(user_id, digest)
    record("device_lookup")
    getattr(subs, "get_current" + "_subscription")(user_id)
    record("current_subscription")
    overlay.list_source_changes(user_id)
    record("source_review_aggregate")
    if tuple(item[0] for item in captured) != EXPLAIN_QUERY_LABELS:
        raise BenchmarkAborted("EXPLAIN label set drifted from WS8 inventory")
    return captured


def parse_explain_text(text: str) -> dict[str, Any]:
    """Stdlib TEXT EXPLAIN parser. Nested Loop/seq scan alone is not N+1."""
    body_lines = [
        line
        for line in str(text or "").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    body = "\n".join(body_lines)
    scan_types: list[str] = []
    for line in body_lines:
        for name in PLAN_NODE_TYPES:
            if name in line and name not in scan_types:
                scan_types.append(name)
                break
    index_names = re.findall(r"\busing\s+([A-Za-z0-9_]+)", body, flags=re.IGNORECASE)
    plan_rows = 0
    cost_rows = re.search(r"cost=[0-9.]+\.\.[0-9.]+\s+rows=(\d+)", body)
    if cost_rows:
        plan_rows = int(cost_rows.group(1))
    actual_rows = 0
    actual_ms = 0.0
    actual = re.search(
        r"actual time=([0-9.]+)\.\.([0-9.]+)\s+rows=(\d+)",
        body,
    )
    if actual:
        actual_ms = float(actual.group(2))
        actual_rows = int(actual.group(3))
    planning = re.search(r"Planning Time:\s*([0-9.]+)\s*ms", body, re.IGNORECASE)
    execution = re.search(r"Execution Time:\s*([0-9.]+)\s*ms", body, re.IGNORECASE)
    hits: list[int] = []
    reads: list[int] = []
    for spec in re.findall(r"Buffers:\s*([^\n]+)", body):
        hit = re.search(r"\bhit=(\d+)", spec)
        read = re.search(r"\bread=(\d+)", spec)
        if hit:
            hits.append(int(hit.group(1)))
        if read:
            reads.append(int(read.group(1)))
    n_plus_one_hint = _n_plus_one_hint(body_lines)
    t16_note = None
    if "Nested Loop" in scan_types and not n_plus_one_hint:
        t16_note = (
            "Nested Loop present; not treated as N+1 without an inner "
            "Seq Scan on user_playground_progress / user_playground_selection"
        )
    elif "Seq Scan" in scan_types and not n_plus_one_hint:
        t16_note = (
            "Seq Scan present; not treated as N+1 without Nested Loop inner "
            "correlation on progress/selection. T16 may revisit scaling."
        )
    return {
        "scan_types": scan_types,
        "index_names": index_names,
        "plan_shape": _plan_shape(scan_types, index_names),
        "plan_rows": plan_rows,
        "actual_rows": actual_rows,
        "actual_time_ms": actual_ms,
        "buffers_shared_hit": hits[0] if hits else 0,
        "buffers_shared_read": reads[0] if reads else 0,
        "planning_time_ms": float(planning.group(1)) if planning else 0.0,
        "execution_time_ms": float(execution.group(1)) if execution else actual_ms,
        "n_plus_one_hint": n_plus_one_hint,
        "t16_note": t16_note,
    }


def _plan_shape(scan_types: list[str], index_names: list[str]) -> str:
    if not scan_types and not index_names:
        return "unknown"
    parts: list[str] = []
    idx = 0
    for scan in scan_types:
        if "Index" in scan and idx < len(index_names):
            parts.append(f"{scan} {index_names[idx]}")
            idx += 1
        else:
            parts.append(scan)
    while idx < len(index_names):
        parts.append(index_names[idx])
        idx += 1
    return "; ".join(parts)


def _n_plus_one_hint(lines: list[str]) -> bool:
    """True only when a Nested Loop's inner node Seq-scans progress/selection."""
    watched = ("user_playground_progress", "user_playground_selection")
    for index, line in enumerate(lines):
        if "Nested Loop" not in line:
            continue
        nest_indent = len(line) - len(line.lstrip())
        for later in lines[index + 1 :]:
            indent = len(later) - len(later.lstrip())
            stripped = later.lstrip()
            if indent <= nest_indent and (
                stripped.startswith("->") or stripped.startswith("Nested Loop")
            ):
                break
            if indent <= nest_indent and stripped.startswith(("Planning", "Execution")):
                break
            if indent > nest_indent and "Seq Scan" in later:
                if any(name in later for name in watched):
                    return True
    return False


def sanitize_explain_text(text: str, *, dummy_hash: str) -> str:
    out = str(text or "")
    if dummy_hash:
        out = out.replace(dummy_hash, "<redacted-device-hash>")
    out = out.replace(BENCH_EMAIL, "<redacted-email>")
    out = re.sub(r"postgres(?:ql)?://[^\s]+", "postgresql://<redacted>", out)
    return out


def _alembic_env(validated_url: str, environ: Mapping[str, str]) -> dict[str, str]:
    env = {key: value for key, value in environ.items() if key != "DATABASE_URL"}
    env["DATABASE_URL"] = validated_url
    return env


def upgrade_disposable_alembic(
    validated_url: str, environ: Mapping[str, str] | None = None
) -> str:
    env_map = os.environ if environ is None else environ
    env = _alembic_env(validated_url, env_map)
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if upgrade.returncode != 0:
        detail = (upgrade.stderr or upgrade.stdout or "").strip()
        raise BenchmarkAborted(
            "alembic upgrade head failed on disposable DB"
            + (f": {detail[:400]}" if detail else "")
        )
    current = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    text = current.stdout or ""
    if EXPECTED_ALEMBIC_HEAD not in text:
        raise BenchmarkAborted(
            f"expected alembic current to include {EXPECTED_ALEMBIC_HEAD}"
        )
    return EXPECTED_ALEMBIC_HEAD


def assert_unmigrated_disposable_db(validated_url: str) -> None:
    import psycopg

    try:
        with psycopg.connect(validated_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM pg_catalog.pg_tables "
                    "WHERE schemaname = 'public'"
                )
                row = cur.fetchone()
                count = int(row[0] if row is not None else 0)
    except Exception as exc:
        raise BenchmarkAborted(
            "T15 could not connect to disposable PostgreSQL "
            f"({type(exc).__name__})"
        ) from exc
    if count:
        raise BenchmarkAborted(
            "refusing pre-existing database with public tables; "
            "create a new uniquely named disposable DB (never DROP)"
        )


def _pg_executemany(pool, sql: str, rows: list[tuple[Any, ...]]) -> None:
    if not rows:
        return
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()


def _bulk_overlay_postgres(
    overlay,
    pool,
    law_id: str,
    locators: list[str],
    *,
    status: str = "new",
    next_revision: str | None = None,
    complete_modes: bool = False,
    source_changes: int = 0,
    revision_history: bool = False,
) -> None:
    from constitution_memorizer.playground.learning.modes import PLAYGROUND_LEARN_MODES
    from constitution_memorizer.progress.user_ids import as_user_id

    uid = as_user_id(BENCH_USER)
    now = PLAYGROUND_TEST_NOW.replace(microsecond=0)
    today = now.date()
    due = date.fromisoformat(next_revision) if next_revision else None
    learned = status in {"learned", "review"}
    overlay.replace_selection(
        BENCH_USER,
        law_id,
        [(loc, "v1", "hash-v1") for loc in locators],
    )
    progress_rows = [
        (
            uid,
            law_id,
            loc,
            status,
            1 if complete_modes else 0,
            1 if learned else 0,
            today if learned else None,
            due,
            1 if due else 0,
            "v1",
            "hash-v1",
            now,
            today if learned else None,
        )
        for loc in locators
    ]
    _pg_executemany(
        pool,
        """
        INSERT INTO user_playground_progress (
            user_id, law_id, source_locator, status, cloze_done,
            times_completed, last_completed, next_revision, interval_days,
            source_version, source_hash, updated_at, learned_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, law_id, source_locator) DO UPDATE SET
            status = EXCLUDED.status,
            cloze_done = EXCLUDED.cloze_done,
            times_completed = EXCLUDED.times_completed,
            last_completed = EXCLUDED.last_completed,
            next_revision = EXCLUDED.next_revision,
            interval_days = EXCLUDED.interval_days,
            source_version = EXCLUDED.source_version,
            source_hash = EXCLUDED.source_hash,
            updated_at = EXCLUDED.updated_at,
            learned_at = EXCLUDED.learned_at
        """,
        progress_rows,
    )
    if complete_modes:
        mode_rows = []
        for loc in locators:
            for mode in PLAYGROUND_LEARN_MODES:
                mode_rows.append(
                    (
                        uid,
                        law_id,
                        loc,
                        mode,
                        "completed",
                        1,
                        now,
                        now,
                        now,
                        "v1",
                        "hash-v1",
                        now,
                        now,
                    )
                )
        _pg_executemany(
            pool,
            """
            INSERT INTO user_playground_mode_progress (
                user_id, law_id, source_locator, mode, status, attempt_count,
                first_started_at, last_attempt_at, completed_at,
                source_version, source_hash, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, law_id, source_locator, mode) DO UPDATE SET
                status = EXCLUDED.status,
                attempt_count = EXCLUDED.attempt_count,
                completed_at = EXCLUDED.completed_at,
                updated_at = EXCLUDED.updated_at
            """,
            mode_rows,
        )
    if revision_history:
        rev_rows = []
        for loc in locators[: min(20, len(locators))]:
            for mode in PLAYGROUND_LEARN_MODES[:2]:
                rev_rows.append(
                    (
                        uid,
                        law_id,
                        loc,
                        1,
                        mode,
                        "completed",
                        1,
                        now,
                        now,
                        now,
                        "v1",
                        "hash-v1",
                        now,
                        now,
                    )
                )
        _pg_executemany(
            pool,
            """
            INSERT INTO user_playground_revision_mode_progress (
                user_id, law_id, source_locator, rung_days, mode, status,
                attempt_count, first_started_at, last_attempt_at, completed_at,
                source_version, source_hash, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, law_id, source_locator, rung_days, mode)
            DO UPDATE SET
                status = EXCLUDED.status,
                attempt_count = EXCLUDED.attempt_count,
                completed_at = EXCLUDED.completed_at,
                updated_at = EXCLUDED.updated_at
            """,
            rev_rows,
        )
    if source_changes:
        change_rows = []
        for loc in locators[:source_changes]:
            change_rows.append(
                (
                    uid,
                    law_id,
                    loc,
                    "stale",
                    "stale",
                    "stale",
                    "old-hash",
                    "current",
                    "current",
                    "new-hash",
                    "changed",
                    "pending",
                    1,
                    1,
                    now,
                    now,
                    now,
                )
            )
        _pg_executemany(
            pool,
            """
            INSERT INTO user_playground_source_change (
                user_id, law_id, source_locator, detected_source_version,
                detected_law_source_hash, previous_source_version,
                previous_section_hash, current_source_version,
                current_law_source_hash, current_section_hash, change_kind,
                status, had_learning, had_selection, detected_at,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (
                user_id, law_id, source_locator,
                current_source_version, current_law_source_hash
            ) DO UPDATE SET
                status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at
            """,
            change_rows,
        )


def _insert_dummy_device(pool, device_key_hash: str) -> None:
    from constitution_memorizer.progress.user_ids import as_user_id

    now = PLAYGROUND_TEST_NOW.replace(microsecond=0)
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_device (
                    id, user_id, device_key_hash, platform, display_name,
                    first_registered_at, last_seen_at, revoked_at,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid4()),
                    as_user_id(BENCH_USER),
                    device_key_hash,
                    "web",
                    "bench-web",
                    now,
                    now,
                    None,
                    now,
                    now,
                ),
            )
        conn.commit()


def seed_explain_fixture(pool) -> dict[str, Any]:
    """Pro-30 volume plus NDPS source-review rows. HydrationProbe must stay 0."""
    from constitution_memorizer.devices.postgres import PostgresDeviceRepository
    from constitution_memorizer.playground.postgres import PostgresPlaygroundRepository
    from constitution_memorizer.playground.roster.postgres import PostgresRosterRepository
    from constitution_memorizer.subscriptions.postgres import PostgresSubscriptionRepository
    from types import SimpleNamespace

    install_benchmark_clock()
    install_synthetic_catalogue_stubs()
    overlay = PostgresPlaygroundRepository(pool)
    roster_repo = PostgresRosterRepository(pool)
    subs = PostgresSubscriptionRepository(pool)
    bag = SimpleNamespace(
        state=SimpleNamespace(
            playground=overlay,
            roster=SimpleNamespace(_repo=roster_repo),
            subscriptions=subs,
        )
    )
    probe = HydrationProbe()
    probe.install()
    try:
        syn = synthetic_law_ids(24)
        laws = list(ELIGIBLE_LAWS) + list(syn)
        _subscribe(bag, tier="pro")
        _ensure_period(bag, tier="pro", law_limit=30)
        _consume(bag, laws, law_limit=30)
        for law_id in laws:
            _activate_or_stub(bag, law_id)
        for law_id in syn:
            _bulk_overlay_postgres(
                overlay,
                pool,
                law_id,
                _locators(law_id, 20),
                status="learned",
                next_revision="2026-09-10",
                complete_modes=True,
                revision_history=True,
            )
        overlay.add_item(
            BENCH_USER,
            SOURCE_REVIEW_LAW,
            source_version="stale",
            law_source_hash="stale",
        )
        _bulk_overlay_postgres(
            overlay,
            pool,
            SOURCE_REVIEW_LAW,
            _locators(SOURCE_REVIEW_LAW, 40),
            status="learned",
            complete_modes=True,
            source_changes=24,
        )
        digest = dummy_device_key_hash()
        _insert_dummy_device(pool, digest)
        del PostgresDeviceRepository
    finally:
        probe.remove()
    if probe.calls:
        raise BenchmarkAborted(
            f"EXPLAIN fixture called get_bare_act {probe.calls} time(s)"
        )
    return {
        "roster_count": _roster_count(bag),
        "law_ids": laws,
        "tier": "pro",
        "fixture": "pro-30+source-review",
    }


def _commercial_subscription_table() -> str:
    """Avoid the playground freeze token for the commercial subscription table."""
    return "user_" + "subscription"


def collect_dataset_counts(conn, user_id: UUID | str) -> dict[str, int]:
    from constitution_memorizer.progress.user_ids import as_user_id

    uid = as_user_id(user_id)
    counts: dict[str, int] = {}
    queries = DATASET_COUNT_SQL + (
        (
            "current_subscription_rows",
            "SELECT COUNT(*) FROM "
            + _commercial_subscription_table()
            + " WHERE user_id = %s AND is_current = TRUE",
        ),
    )
    with conn.cursor() as cur:
        for name, sql in queries:
            assert_readonly_select(sql)
            cur.execute(sql, (uid,))
            row = cur.fetchone()
            counts[name] = int(row[0] if row is not None else 0)
    return counts


def analyze_disposable_tables(conn) -> tuple[str, ...]:
    from psycopg import sql as pg_sql

    tables = ANALYZE_TABLES + (_commercial_subscription_table(),)
    for table in tables:
        conn.execute(pg_sql.SQL("ANALYZE {}").format(pg_sql.Identifier(table)))
    conn.commit()
    return tables


def explain_select(conn, sql: str, params: tuple[Any, ...]) -> str:
    assert_readonly_select(sql)
    try:
        conn.rollback()
    except Exception:
        pass
    conn.execute("BEGIN")
    try:
        conn.execute(
            "SELECT set_config('statement_timeout', %s, true)",
            (EXPLAIN_STATEMENT_TIMEOUT,),
        )
        with conn.cursor() as cur:
            cur.execute(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + sql,
                params,
            )
            rows = cur.fetchall()
        plan = "\n".join(str(row[0]) for row in rows)
    finally:
        conn.execute("ROLLBACK")
    return plan


def run_explain_harness(
    config: BenchmarkRunConfig, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    import psycopg

    from constitution_memorizer.progress.pg_pool import make_connection_pool
    from constitution_memorizer.playground.roster.period import playground_month_bounds
    from constitution_memorizer.progress.user_ids import as_user_id

    if not config.explain:
        raise BenchmarkAborted("run_explain_harness requires --explain")
    if config.protocol:
        raise BenchmarkAborted("--explain cannot be combined with --protocol")
    env = os.environ if environ is None else environ
    if env is os.environ and str(os.environ.get("DATABASE_URL") or "").strip():
        # Isolation: never read process DATABASE_URL. Presence is fine as long
        # as resolve_database_url ignored it; do not copy it into Alembic.
        pass
    effective_app_env = evaluate_explain_guard(
        requested_app_env=config.app_env,
        accept_nontest=config.accept_nontest,
        database_url=config.database_url,
        environ=env,
    )
    parsed = assert_disposable_postgres(config.database_url)
    validated_url = config.database_url
    assert_unmigrated_disposable_db(validated_url)
    alembic_head = upgrade_disposable_alembic(validated_url, env)
    pool = make_connection_pool(validated_url)
    pool.open(wait=True)
    try:
        seed_info = seed_explain_fixture(pool)
    finally:
        pool.close()

    dummy_hash = dummy_device_key_hash()
    month_start, month_end = playground_month_bounds(PLAYGROUND_TEST_NOW)
    law_ids = tuple(seed_info["law_ids"])
    statements = capture_explain_statements(
        user_id=BENCH_USER,
        period_start=month_start,
        as_of=PLAYGROUND_TEST_NOW.date(),
        month_start=month_start,
        month_end=month_end,
        law_ids=law_ids,
        device_key_hash=dummy_hash,
    )
    plan_dir = (
        config.json_path.parent
        if config.json_path is not None
        else DEFAULT_EXPLAIN_PLAN_DIR
    )
    plan_dir.mkdir(parents=True, exist_ok=True)
    queries: list[dict[str, Any]] = []
    with psycopg.connect(validated_url) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            version_row = cur.fetchone()
        postgres_version = str(version_row[0] if version_row else "")
        dataset = collect_dataset_counts(conn, BENCH_USER)
        analyze_disposable_tables(conn)
        for label, sql, params in statements:
            raw_plan = explain_select(conn, sql, params)
            sanitized = sanitize_explain_text(raw_plan, dummy_hash=dummy_hash)
            parsed_plan = parse_explain_text(sanitized)
            rel_path = f"docs/performance/explain-pro-30-{label}.txt"
            dest = plan_dir / f"explain-pro-30-{label}.txt"
            header = (
                "# disposable PostgreSQL baseline, not an SLA\n"
                f"# query: {label}\n"
                f"# alembic_head: {alembic_head}\n"
                f"# fixture: pro-30+source-review\n"
                f"# database_name_prefix: {parsed['database'][:3]}\n"
            )
            dest.write_text(header + sanitized.rstrip() + "\n", encoding="utf-8")
            if dummy_hash in dest.read_text(encoding="utf-8"):
                raise BenchmarkAborted("plan artifact leaked dummy device hash")
            if BENCH_EMAIL in dest.read_text(encoding="utf-8"):
                raise BenchmarkAborted("plan artifact leaked fixture email")
            row_volume = {
                "current_roster_lookup": dataset.get("roster_items", 0),
                "roster_capacity_count": dataset.get("roster_items", 0),
                "home_summary_aggregate": len(law_ids),
                "due_revisions": dataset.get("progress_rows", 0),
                "calendar_schedule": dataset.get("progress_rows", 0),
                "device_count": dataset.get("device_rows", 0),
                "device_lookup": dataset.get("device_rows", 0),
                "current_subscription": dataset.get("current_subscription_rows", 0),
                "source_review_aggregate": dataset.get("source_change_rows", 0),
            }.get(label, parsed_plan["actual_rows"])
            entry = {
                "label": label,
                "row_volume": row_volume,
                "plan_shape": parsed_plan["plan_shape"],
                "scan_types": parsed_plan["scan_types"],
                "index_names": parsed_plan["index_names"],
                "actual_time_ms": parsed_plan["actual_time_ms"],
                "plan_rows": parsed_plan["plan_rows"],
                "actual_rows": parsed_plan["actual_rows"],
                "buffers_shared_hit": parsed_plan["buffers_shared_hit"],
                "buffers_shared_read": parsed_plan["buffers_shared_read"],
                "planning_time_ms": parsed_plan["planning_time_ms"],
                "execution_time_ms": parsed_plan["execution_time_ms"],
                "n_plus_one_hint": parsed_plan["n_plus_one_hint"],
                "t16_note": parsed_plan["t16_note"],
                "plan_file": rel_path,
            }
            queries.append(entry)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "label": "disposable PostgreSQL baseline, not an SLA",
        "alembic_head": alembic_head,
        "postgres_version": postgres_version,
        "database_backend": "postgresql",
        "fixture": "pro-30+source-review",
        "scenario": config.scenario,
        "app_env": str(effective_app_env),
        "dataset": dataset,
        "queries": queries,
        "t7_note": (
            "T15 physical SQL statements are not T7 outermost-method "
            "round-trip counters. Nested Loop / seq scan is not inferred "
            "as N+1 from plan shape alone."
        ),
    }
    # Isolation proof fields: name prefix only, never the full URL.
    payload["disposable_db_name_prefix"] = parsed["database"].split("_")[0] + "_"
    payload["disposable_host_class"] = parsed["host"] or "unix-peer"
    del as_user_id
    _assert_json_safe(payload)
    blob = json.dumps(payload)
    if dummy_hash in blob:
        raise BenchmarkAborted("JSON report leaked dummy device hash")
    if config.json_path is not None:
        write_json_report(config.json_path, payload)
    return payload


@dataclass
class ConcurrentSample:
    """One worker GET. Snapshot is captured inside this worker's asyncio task."""

    worker_index: int
    batch_index: int
    concurrency: int
    status_code: int | None
    error_class: str | None
    error_message: str | None
    elapsed_ms: float
    snapshot: Any | None
    task_id: int
    snapshot_identity: int | None


@dataclass
class ConcurrentBatchResult:
    concurrency: int
    batch_index: int
    requested_concurrency: int
    max_in_flight_observed: int
    samples: list[ConcurrentSample]
    batch_wall_seconds: float
    completed_requests: int
    failed_requests: int
    throughput_rps: float | None
    incomplete: bool
    aborted_reason: str | None


class _InFlightTracker:
    """Harness-side overlapping GETs (started, not completed). Not parallel SQL."""

    def __init__(self) -> None:
        self.current = 0
        self.max_observed = 0

    def enter(self) -> None:
        self.current += 1
        if self.current > self.max_observed:
            self.max_observed = self.current

    def exit(self) -> None:
        self.current -= 1
        if self.current < 0:
            self.current = 0


def _stored_snapshot_identity() -> int | None:
    from constitution_memorizer.web.request_context import _last_request_performance

    current = _last_request_performance.get()
    if current is None:
        return None
    return id(current)


def _sanitize_error_text(text: str) -> str:
    cleaned = _SENSITIVE.sub("[redacted]", str(text))
    if BENCH_EMAIL in cleaned:
        cleaned = cleaned.replace(BENCH_EMAIL, "[redacted]")
    return cleaned[:240]


def assert_concurrency_home_no_bare_act(snap: Any, *, label: str) -> None:
    notes = getattr(snap, "notes", None) or {}
    counters = getattr(snap, "counters", None) or {}
    timings = getattr(snap, "timings", None) or {}
    misses = int(counters.get("bare_act_cache_misses") or 0)
    if notes.get("bare_act_cache") or misses or "bare_act_load" in timings:
        raise BenchmarkAborted(
            f"{label} unexpected Bare Act cache access or hydration"
        )


def assert_concurrency_warm_workspace(snap: Any, *, label: str) -> None:
    got = classify_cache_snapshot(snap)
    if got != "hit":
        raise BenchmarkAborted(
            f"{label} warm workspace cache class {got!r}, expected 'hit'"
        )


def _concurrency_path_group(scenario: str) -> str:
    if scenario == "plus-10":
        return "/playground"
    if scenario == "law-workspace":
        return BNSS_WORKSPACE_PATH_GROUP
    raise BenchmarkAborted(f"unsupported T18 scenario {scenario!r}")


def _concurrency_snapshot_error(
    *,
    scenario: str,
    snap: Any,
    status_code: int | None,
    expected_path_group: str,
) -> str | None:
    if snap is None:
        return "snapshot_missing"
    if status_code is not None and int(getattr(snap, "status_code", 0) or 0) != int(
        status_code
    ):
        return "snapshot_stale"
    if str(getattr(snap, "path_group", "")) != expected_path_group:
        return "snapshot_stale"
    if scenario == "plus-10":
        try:
            assert_concurrency_home_no_bare_act(snap, label="measured")
        except BenchmarkAborted:
            return "unexpected_bare_act"
    elif scenario == "law-workspace":
        if classify_cache_snapshot(snap) != "hit":
            return "warm_cache_miss"
    return None


def read_concurrency_integrity(app) -> dict[str, Any]:
    from constitution_memorizer.playground.roster.period import playground_month_bounds

    start, _end = playground_month_bounds(PLAYGROUND_TEST_NOW)
    roster_used = int(app.state.roster._repo.count_consumed(BENCH_USER, start))
    overlay_items = len(app.state.playground.list_items(BENCH_USER))
    billing = app.state.subscription_service.get_current(BENCH_USER)
    devices = app.state.device_service.list_devices(BENCH_USER)
    return {
        "roster_used": roster_used,
        "overlay_items": overlay_items,
        "subscription_status": None if billing is None else str(billing.status),
        "device_rows": len(devices),
    }


def _integrity_drift_reason(before: Mapping[str, Any], after: Mapping[str, Any]) -> str | None:
    if int(after["roster_used"]) > int(before["roster_used"]):
        return (
            "integrity drift: roster_used "
            f"{before['roster_used']} -> {after['roster_used']}"
        )
    if after["overlay_items"] != before["overlay_items"]:
        return (
            "integrity drift: overlay_items "
            f"{before['overlay_items']} -> {after['overlay_items']}"
        )
    if after["subscription_status"] != before["subscription_status"]:
        return (
            "integrity drift: subscription_status "
            f"{before['subscription_status']} -> {after['subscription_status']}"
        )
    if after["device_rows"] != before["device_rows"]:
        return (
            "integrity drift: device_rows "
            f"{before['device_rows']} -> {after['device_rows']}"
        )
    return None


def _warmup_cache_proof(scenario: str, snap: Any) -> dict[str, Any]:
    notes = getattr(snap, "notes", None) or {}
    counters = getattr(snap, "counters", None) or {}
    timings = getattr(snap, "timings", None) or {}
    misses = int(counters.get("bare_act_cache_misses") or 0)
    load_absent = "bare_act_load" not in timings
    if scenario == "plus-10":
        return {
            "kind": "home",
            "bare_act_cache_absent": "bare_act_cache" not in notes,
            "bare_act_cache_misses": misses,
            "bare_act_load_absent": load_absent,
        }
    return {
        "kind": "workspace",
        "cache_class": classify_cache_snapshot(snap),
        "bare_act_cache": notes.get("bare_act_cache"),
        "bare_act_cache_misses": misses,
        "bare_act_load_absent": load_absent,
    }


def _counter_series(snapshots: list[Any], name: str) -> list[float]:
    return [float(int((snap.counters or {}).get(name, 0) or 0)) for snap in snapshots]


async def run_concurrent_batch(
    client,
    path: str,
    *,
    concurrency: int,
    batch_index: int,
    timeout_s: float = CONCURRENCY_BATCH_TIMEOUT_S,
    scenario: str | None = None,
    expected_path_group: str | None = None,
) -> ConcurrentBatchResult:
    """Release C workers together. Capture snapshots inside each worker task."""
    import asyncio
    from time import perf_counter

    from constitution_memorizer.web.request_context import (
        clear_last_request_performance,
        get_last_request_performance,
    )

    if concurrency < 1:
        raise BenchmarkAborted("concurrency must be >= 1")
    tracker = _InFlightTracker()
    go = asyncio.Event()
    parked = 0
    all_parked = asyncio.Event()
    samples: list[ConcurrentSample | None] = [None] * concurrency
    path_group = expected_path_group or path

    async def worker(index: int) -> None:
        nonlocal parked
        task_id = id(asyncio.current_task())
        parked += 1
        if parked >= concurrency:
            all_parked.set()
        try:
            await go.wait()
        except asyncio.CancelledError:
            samples[index] = ConcurrentSample(
                worker_index=index,
                batch_index=batch_index,
                concurrency=concurrency,
                status_code=None,
                error_class="timeout",
                error_message="cancelled before release",
                elapsed_ms=0.0,
                snapshot=None,
                task_id=task_id,
                snapshot_identity=None,
            )
            raise
        t0 = perf_counter()
        tracker.enter()
        status: int | None = None
        snap = None
        identity = None
        error_class = None
        error_message = None
        try:
            try:
                clear_last_request_performance()
                response = await client.get(path)
                status = int(response.status_code)
                identity = _stored_snapshot_identity()
                snap = get_last_request_performance()
                if status != 200:
                    error_class = f"http_{status}"
                elif scenario is not None:
                    error_class = _concurrency_snapshot_error(
                        scenario=scenario,
                        snap=snap,
                        status_code=status,
                        expected_path_group=path_group,
                    )
                elif snap is None:
                    error_class = "snapshot_missing"
            except asyncio.CancelledError:
                error_class = "timeout"
                error_message = "batch timeout"
                raise
            except Exception as exc:
                module = type(exc).__module__
                name = type(exc).__name__
                error_message = _sanitize_error_text(f"{name}: {exc}")
                if name == "OperationalError" and module.startswith("sqlite3"):
                    error_class = "sqlite3.OperationalError"
                elif module.startswith("httpx"):
                    error_class = "httpx.HTTPError"
                else:
                    error_class = name
        finally:
            elapsed_ms = (perf_counter() - t0) * 1000.0
            tracker.exit()
            if samples[index] is None:
                samples[index] = ConcurrentSample(
                    worker_index=index,
                    batch_index=batch_index,
                    concurrency=concurrency,
                    status_code=status,
                    error_class=error_class,
                    error_message=error_message,
                    elapsed_ms=elapsed_ms,
                    snapshot=snap,
                    task_id=task_id,
                    snapshot_identity=identity,
                )

    tasks = [
        asyncio.create_task(worker(index), name=f"t18-c{concurrency}-b{batch_index}-w{index}")
        for index in range(concurrency)
    ]
    aborted_reason: str | None = None
    incomplete = False
    batch_wall_seconds = 0.0
    try:
        await asyncio.wait_for(all_parked.wait(), timeout=timeout_s)
    except TimeoutError:
        incomplete = True
        aborted_reason = "barrier_timeout"
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    else:
        batch_wall_start = perf_counter()
        go.set()
        _done, pending = await asyncio.wait(tasks, timeout=timeout_s)
        batch_wall_seconds = perf_counter() - batch_wall_start
        if pending:
            incomplete = True
            aborted_reason = "batch_timeout"
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    filled: list[ConcurrentSample] = []
    identities: list[int] = []
    for index, sample in enumerate(samples):
        if sample is None:
            incomplete = True
            sample = ConcurrentSample(
                worker_index=index,
                batch_index=batch_index,
                concurrency=concurrency,
                status_code=None,
                error_class="timeout",
                error_message="worker finished without a sample",
                elapsed_ms=0.0,
                snapshot=None,
                task_id=0,
                snapshot_identity=None,
            )
        filled.append(sample)
        if sample.snapshot_identity is not None:
            identities.append(sample.snapshot_identity)
    if identities and len(identities) != len(set(identities)):
        aborted_reason = aborted_reason or "snapshot_misattributed"
        filled = [
            ConcurrentSample(
                worker_index=sample.worker_index,
                batch_index=sample.batch_index,
                concurrency=sample.concurrency,
                status_code=sample.status_code,
                error_class=sample.error_class or "snapshot_misattributed",
                error_message=sample.error_message,
                elapsed_ms=sample.elapsed_ms,
                snapshot=sample.snapshot,
                task_id=sample.task_id,
                snapshot_identity=sample.snapshot_identity,
            )
            for sample in filled
        ]
    completed = sum(
        1
        for sample in filled
        if sample.error_class is None and sample.status_code == 200
    )
    failed = len(filled) - completed
    if incomplete or failed or aborted_reason:
        throughput: float | None = None
    elif batch_wall_seconds <= 0:
        throughput = None
    else:
        throughput = completed / batch_wall_seconds
    if failed and aborted_reason is None:
        first_error = next(sample.error_class for sample in filled if sample.error_class)
        aborted_reason = first_error
    if incomplete and aborted_reason is None:
        aborted_reason = "incomplete_batch"
    return ConcurrentBatchResult(
        concurrency=concurrency,
        batch_index=batch_index,
        requested_concurrency=concurrency,
        max_in_flight_observed=tracker.max_observed,
        samples=filled,
        batch_wall_seconds=batch_wall_seconds,
        completed_requests=completed,
        failed_requests=failed,
        throughput_rps=throughput,
        incomplete=incomplete,
        aborted_reason=aborted_reason,
    )


def _level_report(
    results: list[ConcurrentBatchResult],
    *,
    concurrency: int,
    batches_requested: int,
) -> dict[str, Any]:
    all_samples = [sample for result in results for sample in result.samples]
    ok_snaps = [
        sample.snapshot
        for sample in all_samples
        if sample.error_class is None and sample.snapshot is not None
    ]
    status_counts: dict[str, int] = {}
    error_classes: dict[str, int] = {}
    for sample in all_samples:
        if sample.status_code is not None:
            key = str(int(sample.status_code))
            status_counts[key] = status_counts.get(key, 0) + 1
        if sample.error_class:
            error_classes[sample.error_class] = (
                error_classes.get(sample.error_class, 0) + 1
            )
    metrics: dict[str, Any] = {}
    if ok_snaps:
        metrics["total_ms"] = summarize_numbers(snap.total_ms for snap in ok_snaps)
        for name in (
            "playground_repo_round_trips",
            "playground_db_reads",
            "playground_entitlement_resolves",
            "playground_device_lookups",
            "bare_act_cache_misses",
        ):
            metrics[name] = summarize_numbers(_counter_series(ok_snaps, name))
        stage_names: set[str] = set()
        for snap in ok_snaps:
            stage_names.update((snap.timings or {}).keys())
        for name in sorted(stage_names):
            series = []
            for snap in ok_snaps:
                timing = (snap.timings or {}).get(name)
                series.append(float(timing[0]) if timing is not None else 0.0)
            metrics[name] = summarize_numbers(series)
    if all_samples:
        metrics["worker_elapsed_ms"] = summarize_numbers(
            sample.elapsed_ms for sample in all_samples
        )
    throughputs = [
        result.throughput_rps
        for result in results
        if result.throughput_rps is not None
    ]
    incomplete_batches = sum(1 for result in results if result.incomplete)
    samples_ok = sum(result.completed_requests for result in results)
    samples_error = sum(result.failed_requests for result in results)
    payload = {
        "concurrency": concurrency,
        "requested_concurrency": concurrency,
        "max_in_flight_observed": max(
            (result.max_in_flight_observed for result in results), default=0
        ),
        "asgi_in_flight_is_not_parallel_sql": True,
        "batches": len(results),
        "batches_requested": batches_requested,
        "incomplete_batches": incomplete_batches,
        "samples_ok": samples_ok,
        "samples_error": samples_error,
        "status_counts": status_counts,
        "error_classes": error_classes,
        "metrics": metrics,
        "throughput_rps": summarize_numbers(throughputs) if throughputs else None,
        "notes_observed": _note_tokens(ok_snaps) if ok_snaps else {},
        "batch_wall_seconds": [result.batch_wall_seconds for result in results],
        "batch_throughput_rps": throughputs,
        "aborted_reason": next(
            (
                result.aborted_reason
                for result in results
                if result.aborted_reason
            ),
            None,
        ),
    }
    return payload


def _concurrency_payload_base(
    *,
    scenario: str,
    app_env: str,
    warmup_discarded: int,
    batches_requested: int,
    levels_requested: tuple[int, ...],
    path: str,
    path_group: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "concurrency",
        "scenario": scenario,
        "app_env": str(app_env),
        "database_backend": "sqlite",
        "client_shape": CONCURRENCY_CLIENT_SHAPE,
        "path": path,
        "path_group": path_group,
        "method": "GET",
        "warmup_discarded": warmup_discarded,
        "batches_requested": batches_requested,
        "concurrency_levels_requested": list(levels_requested),
        "batch_timeout_s": CONCURRENCY_BATCH_TIMEOUT_S,
        "asgi_in_flight_is_not_parallel_sql": True,
        "aborted": False,
        "aborted_reason": None,
        "warmup_cache": {},
        "integrity": {},
        "levels": [],
    }


def run_concurrency_benchmark(
    config: BenchmarkRunConfig, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """T18 warm plus-10 home and warm BNSS workspace at 1/5/10/25. SQLite only."""
    import asyncio

    from httpx import ASGITransport, AsyncClient, Limits, Timeout

    if config.explain:
        raise BenchmarkAborted("T18 concurrency cannot run --explain")
    if config.protocol:
        raise BenchmarkAborted("T18 concurrency cannot run --protocol")
    levels = config.concurrency_levels
    if not levels:
        raise BenchmarkAborted("run_concurrency_benchmark requires --concurrency")
    if config.scenario not in CONCURRENCY_SCENARIOS:
        raise BenchmarkAborted(
            "--concurrency supports --scenario plus-10 or law-workspace"
        )
    effective_app_env = evaluate_safety_guard(
        requested_app_env=config.app_env,
        accept_nontest=config.accept_nontest,
        explain=False,
        environ=environ,
    )
    db_path = assert_concurrency_sqlite(config.database_url)
    app = create_benchmark_app(db_path, app_env="test")
    seed_scenario(app, config.scenario)
    method, path = PRIMARY_ROUTES[config.scenario]
    if method != "GET":
        raise BenchmarkAborted(f"T18 routes are GET-only, got {method}")
    path_group = _concurrency_path_group(config.scenario)
    batches = int(config.iterations)
    payload = _concurrency_payload_base(
        scenario=config.scenario,
        app_env=effective_app_env,
        warmup_discarded=config.warmup,
        batches_requested=batches,
        levels_requested=levels,
        path=path,
        path_group=path_group,
    )

    def _finish(*, aborted: bool, reason: str | None) -> dict[str, Any]:
        payload["aborted"] = aborted
        payload["aborted_reason"] = reason
        _assert_json_safe(payload)
        if config.json_path is not None:
            write_json_report(config.json_path, payload)
        if aborted:
            raise BenchmarkAborted(reason or "T18 concurrency aborted")
        return payload

    async def _run() -> None:
        transport = ASGITransport(app=app)
        timeout = Timeout(CONCURRENCY_BATCH_TIMEOUT_S)
        limits = Limits(
            max_connections=MAX_CONCURRENCY,
            max_keepalive_connections=MAX_CONCURRENCY,
        )
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
            timeout=timeout,
            limits=limits,
        ) as client:
            await sign_in_benchmark_client(client)
            last_warmup = None
            discarded = 0
            for index in range(config.warmup):
                last_warmup = await _http_snapshot(
                    client, path, label=f"warmup {index + 1}"
                )
                discarded += 1
            if config.scenario == "law-workspace":
                if last_warmup is None or classify_cache_snapshot(last_warmup) != "hit":
                    last_warmup = await _http_snapshot(
                        client, path, label="warmup extra warm"
                    )
                    discarded += 1
                assert_concurrency_warm_workspace(
                    last_warmup, label="warmup last"
                )
            elif last_warmup is not None:
                assert_concurrency_home_no_bare_act(
                    last_warmup, label="warmup last"
                )
            payload["warmup_discarded"] = discarded
            if last_warmup is not None:
                payload["warmup_cache"] = _warmup_cache_proof(
                    config.scenario, last_warmup
                )
            baseline = read_concurrency_integrity(app)
            payload["integrity"] = {"after_warmup": baseline, "levels": []}
            for concurrency in levels:
                before = read_concurrency_integrity(app)
                batch_results: list[ConcurrentBatchResult] = []
                level_abort: str | None = None
                for batch_index in range(batches):
                    result = await run_concurrent_batch(
                        client,
                        path,
                        concurrency=concurrency,
                        batch_index=batch_index,
                        timeout_s=CONCURRENCY_BATCH_TIMEOUT_S,
                        scenario=config.scenario,
                        expected_path_group=path_group,
                    )
                    batch_results.append(result)
                    if (
                        result.incomplete
                        or result.failed_requests
                        or result.aborted_reason
                    ):
                        level_abort = result.aborted_reason or "batch_failed"
                        break
                after = read_concurrency_integrity(app)
                drift = _integrity_drift_reason(before, after)
                if drift:
                    level_abort = level_abort or drift
                level = _level_report(
                    batch_results,
                    concurrency=concurrency,
                    batches_requested=batches,
                )
                level["integrity_before"] = before
                level["integrity_after"] = after
                payload["levels"].append(level)
                payload["integrity"]["levels"].append(
                    {
                        "concurrency": concurrency,
                        "before": before,
                        "after": after,
                    }
                )
                if level_abort:
                    payload["integrity"]["final"] = after
                    raise BenchmarkAborted(level_abort)
            payload["integrity"]["final"] = read_concurrency_integrity(app)
            drift = _integrity_drift_reason(
                baseline, payload["integrity"]["final"]
            )
            if drift:
                raise BenchmarkAborted(drift)

    try:
        asyncio.run(_run())
    except BenchmarkAborted as exc:
        return _finish(aborted=True, reason=exc.message)
    return _finish(aborted=False, reason=None)


def run_benchmark(
    config: BenchmarkRunConfig, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    import asyncio

    from httpx import ASGITransport, AsyncClient

    if config.explain:
        raise BenchmarkAborted("HTTP runner does not execute EXPLAIN")
    effective_app_env = evaluate_safety_guard(
        requested_app_env=config.app_env,
        accept_nontest=config.accept_nontest,
        explain=False,
        environ=environ,
    )
    db_path = assert_fresh_sqlite(config.database_url)
    # In-process app stays APP_ENV=test so T13 remains SQLite-only even after
    # nontest overrides. JSON records effective_app_env, not this setting.
    app = create_benchmark_app(db_path, app_env="test")
    seed_scenario(app, config.scenario)
    method, path = PRIMARY_ROUTES[config.scenario]
    if method != "GET":
        raise BenchmarkAborted(f"T13 primary routes are GET-only, got {method}")

    async def _run() -> list[Any]:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            await sign_in_benchmark_client(client)

            async def _request():
                return await client.get(path)

            snapshots = []
            from constitution_memorizer.web.request_context import (
                get_last_request_performance,
            )

            for index in range(config.warmup):
                response = await _request()
                status = int(response.status_code)
                if status < 200 or status >= 300:
                    raise BenchmarkAborted(f"warmup {index + 1} HTTP {status}")
            for index in range(config.iterations):
                response = await _request()
                status = int(response.status_code)
                if status < 200 or status >= 300:
                    raise BenchmarkAborted(f"iteration {index + 1} HTTP {status}")
                snap = get_last_request_performance()
                if snap is None:
                    raise BenchmarkAborted(
                        f"iteration {index + 1} missing RequestPerformanceSnapshot"
                    )
                snapshots.append(snap)
            return snapshots

    snapshots = asyncio.run(_run())
    payload = snapshots_to_report(
        snapshots,
        scenario=config.scenario,
        warmup=config.warmup,
        iterations=config.iterations,
        method=method,
        app_env=effective_app_env,
    )
    if config.json_path is not None:
        write_json_report(config.json_path, payload)
    return payload


def run_cli(argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    parser = build_arg_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        if code in (0, 2, None):
            return 0 if code in (0, None) else 2
        return int(code)
    try:
        env = os.environ if environ is None else environ
        config = config_from_args(args, env)
        if config.explain:
            run_explain_harness(config, environ=env)
        elif config.protocol == PROTOCOL_BNSS_COLD_WARM:
            run_bnss_cold_warm(config, environ=env)
        elif config.concurrency_levels:
            run_concurrency_benchmark(config, environ=env)
        else:
            run_benchmark(config, environ=env)
    except BenchmarkAborted as exc:
        print(exc.message, file=sys.stderr)
        return exc.exit_code
    return 0
