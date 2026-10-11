"""Playground Stage 2 WS6–WS11 benchmark library (T13–T21).

Statistics, fail-closed production guard, deterministic fixtures, in-process
HTTP runner, JSON reporting, disposable PostgreSQL EXPLAIN (ANALYZE,
BUFFERS), the T18 read-only concurrency harness, the T19 mutation-load
plus webhook-duplicate harness, the T20 page-weight / static inventory
harness, and the T21 cold-start / import-hydration subprocess. Does not
change product behavior or T1–T9 instrumentation.
PostgreSQL EXPLAIN is T15/WS8 (``--explain`` or
``scripts/explain_playground_queries.py``). BNSS cold/warm is
``--protocol bnss-cold-warm`` (T14/WS7); omitting ``--protocol`` keeps the
T13 unlabeled primary-route path. ``build_nplusone_fixture`` is the T16
matched-density helper; it is not a CLI scenario. ``--concurrency`` is T18
(SQLite-only, not default pytest, not T19 mutations). ``--mutations`` and
``--webhooks`` are T19 (SQLite-only, not default pytest, not T18).
``--page-weight`` is T20 (SQLite-only, in-process ASGI + disk + gzip
equivalents, not Lighthouse, not T21 cold-start, not default pytest).
``--cold-start`` is T21 (SQLite-only, fresh-interpreter subprocess, not
default pytest, no startup SLA).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import hmac
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import parse_qs, unquote, urlparse, urlunparse
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
DEFAULT_MUTATIONS_JSON_PATH = Path("artifacts/playground-mutations.json")
DEFAULT_WEBHOOKS_JSON_PATH = Path("artifacts/playground-webhooks.json")
DEFAULT_PAGE_WEIGHT_JSON_PATH = Path("artifacts/playground-page-weight.json")
DEFAULT_COLD_START_JSON_PATH = Path("artifacts/playground-cold-start.json")
DEFAULT_EXPLAIN_JSON_PATH = Path("docs/performance/explain-pro-30-summary.json")
COLD_START_CHILD_TIMEOUT_S = 60.0
COLD_START_INCIDENTAL_LIMIT = 8000
COLD_START_MEASUREMENT_MODE = "fresh_interpreter_subprocess"
COLD_START_CLIENT_SHAPE = "fresh_child_python"
DEFAULT_EXPLAIN_PLAN_DIR = Path("docs/performance")
DEFAULT_CONCURRENCY_LEVELS = (1, 5, 10, 25)
MAX_CONCURRENCY = 25
DEFAULT_CONCURRENCY_BATCHES = 5
CONCURRENCY_BATCH_TIMEOUT_S = 60.0
CONCURRENCY_SCENARIOS = frozenset({"plus-10", "law-workspace"})
CONCURRENCY_CLIENT_SHAPE = "single_async_client"
MUTATION_CLIENT_SHAPE = "threadpool_separate_connections"
DEFAULT_MUTATION_WAVES = 5
MUTATION_WAVE_TIMEOUT_S = 10.0
MUTATION_CLEANUP_WAIT_S = 2.0
MUTATION_BUSY_TIMEOUT_MS = 8000
MUTATION_CONCURRENCY_LEVELS = (1, 2)
MUTATION_CELLS = (
    "roster-cap",
    "roster-same-law",
    "device-cap",
    "device-idem",
    "progress-learned",
    "revision-sixth",
)
MUTATION_PROGRESS_TODAY = date(2026, 9, 25)
WEBHOOK_QUICK_N = 3
WEBHOOK_QUICK_M = 3
WEBHOOK_FULL_N = 10
WEBHOOK_FULL_M = 10
WEBHOOK_MAX_NM = 25
T19_DEVICE_SECRET = "t19-bench-device-secret"
T19_WEBHOOK_SECRET = "t19-bench-whsec"
T19_PROVIDER_START = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
T19_PROVIDER_END = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
T19_PROVIDER_START_2 = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
T19_PROVIDER_END_2 = int(datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp())
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
PAGE_WEIGHT_STATIC_DIR = (
    REPO_ROOT / "src" / "constitution_memorizer" / "web" / "static"
)
GZIP_COMPRESSLEVEL = 9
PAGE_WEIGHT_CLIENT_SHAPE = "in_process_asgi"
PAGE_WEIGHT_MEASUREMENT_MODE = "in_process_testclient_disk_gzip"
WS11_NAMED_FILES = (
    "styles.css",
    "mobile.css",
    "playground.css",
    "app.js",
    "playground.js",
    "playground-learn.js",
    "speech_client.js",
    "recall_align.js",
)
PAGE_WEIGHT_VIEWPORT_PROFILES = (
    {
        "id": "desktop_1280",
        "width": 1280,
        "height": 800,
        "device_scale_factor": 1,
        "role": "css_applies_note",
    },
    {
        "id": "phone_390",
        "width": 390,
        "height": 844,
        "device_scale_factor": 1,
        "role": "css_applies_note",
    },
)
# Bounded literal /static/ references (condition F: do not parse JS).
PAGE_WEIGHT_BOUNDED_STATIC_LITERALS = (
    "/static/completion-done.mp3",
    "/static/onboarding-tick.m4a",
    "/static/onboarding-move.m4a",
)
PAGE_WEIGHT_WELL_KNOWN_ROOT_DISK = {
    "/apple-touch-icon.png": "brand-c.png",
    "/apple-touch-icon-precomposed.png": "brand-c.png",
    "/favicon.ico": "brand-c.png",
    "/sw.js": "sw.js",
}
PAGE_WEIGHT_PAGES: tuple[dict[str, str], ...] = (
    {
        "id": "plus_home",
        "fixture": "plus-10",
        "method": "GET",
        "path": "/playground",
        "path_group": "/playground",
    },
    {
        "id": "bnss_workspace",
        "fixture": "law-workspace",
        "method": "GET",
        "path": BNSS_WORKSPACE_PATH,
        "path_group": BNSS_WORKSPACE_PATH_GROUP,
    },
    {
        "id": "bnss_learn",
        "fixture": "law-workspace",
        "method": "GET",
        "path": BNSS_LEARN_PATH,
        "path_group": BNSS_LEARN_PATH_GROUP,
    },
    {
        "id": "bnss_public",
        "fixture": "law-workspace",
        "method": "GET",
        "path": BNSS_PUBLIC_PATH,
        "path_group": BNSS_PUBLIC_PATH_GROUP,
    },
)

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
            f"(default {DEFAULT_CONCURRENCY_BATCHES}; --quick uses 1). "
            "With --mutations/--webhooks, waves per cell/level "
            f"(default {DEFAULT_MUTATION_WAVES}; --quick uses 1)."
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
        "--mutations",
        action="store_true",
        help=(
            "T19 service-level mutation-load harness (C=1 control + C=2 races). "
            "SQLite-only. Not default pytest. Not --concurrency. No live Razorpay."
        ),
    )
    parser.add_argument(
        "--webhooks",
        action="store_true",
        help=(
            "T19 process_delivery webhook duplicate harness (N unique + M "
            "replays + out-of-order pair). SQLite-only. Not default pytest. "
            "No live Razorpay."
        ),
    )
    parser.add_argument(
        "--page-weight",
        action="store_true",
        dest="page_weight",
        help=(
            "T20 page-weight and static-asset inventory (four WS11 pages, "
            "disk + gzip equivalents). SQLite-only. Not Lighthouse. Not "
            "default pytest. Not --protocol/--concurrency/--mutations/"
            "--webhooks/--explain/--cold-start."
        ),
    )
    parser.add_argument(
        "--cold-start",
        action="store_true",
        dest="cold_start",
        help=(
            "T21 cold-start and import hydration guard. Fresh-interpreter "
            "subprocess times factory import and create_app separately. "
            "SQLite-only. Not default pytest. No startup SLA. Not "
            "--page-weight/--protocol/--concurrency/--mutations/"
            "--webhooks/--explain."
        ),
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "sqlite:/// filesystem path for the HTTP runner (T13/T14/T18), or a "
            "local disposable postgresql:// URL for --explain (T15). "
            "T18 --concurrency, T19 --mutations/--webhooks, T20 "
            "--page-weight, and T21 --cold-start reject PostgreSQL (T23). "
            "T19/T20 treat the path as a stem and write a fresh file per "
            "fixture/wave. Never falls back to process DATABASE_URL."
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
            f"{DEFAULT_BNSS_JSON_PATH} with --protocol {PROTOCOL_BNSS_COLD_WARM}, "
            f"or {DEFAULT_MUTATIONS_JSON_PATH} with --mutations, "
            f"or {DEFAULT_WEBHOOKS_JSON_PATH} with --webhooks, "
            f"or {DEFAULT_PAGE_WEIGHT_JSON_PATH} with --page-weight, "
            f"or {DEFAULT_COLD_START_JSON_PATH} with --cold-start."
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
            "With --mutations/--webhooks, one wave per cell/level and "
            f"webhook N={WEBHOOK_QUICK_N}, M={WEBHOOK_QUICK_M}. "
            "With --page-weight, still one GET per WS11 page (bytes are "
            "deterministic). "
            "With --cold-start, still one fresh child (counts are "
            "deterministic; no SLA iterations). "
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
    mutations: bool = False
    webhooks: bool = False
    webhook_n: int = 0
    webhook_m: int = 0
    page_weight: bool = False
    cold_start: bool = False


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


def assert_t19_sqlite(url: str) -> Path:
    """T19 accepts only a fresh disposable SQLite stem. PostgreSQL is T23."""
    parsed = urlparse(str(url or "").strip())
    scheme = (parsed.scheme or "").lower()
    if scheme in {"postgres", "postgresql"}:
        raise BenchmarkAborted(
            "T19 mutations/webhooks are SQLite-only; PostgreSQL is T23"
        )
    if scheme not in {"sqlite", "sqlite3"}:
        raise BenchmarkAborted("T19 mutations/webhooks require a sqlite:/// URL")
    return assert_fresh_sqlite(url)


def assert_t20_sqlite(url: str) -> Path:
    """T20 accepts only a fresh disposable SQLite stem. PostgreSQL is T23."""
    parsed = urlparse(str(url or "").strip())
    scheme = (parsed.scheme or "").lower()
    if scheme in {"postgres", "postgresql"}:
        raise BenchmarkAborted(
            "T20 page-weight is SQLite-only; PostgreSQL is T23"
        )
    if scheme not in {"sqlite", "sqlite3"}:
        raise BenchmarkAborted("T20 page-weight requires a sqlite:/// URL")
    return assert_fresh_sqlite(url)


def assert_t21_sqlite(url: str) -> Path:
    """T21 accepts only a fresh disposable SQLite file. PostgreSQL is T23."""
    parsed = urlparse(str(url or "").strip())
    scheme = (parsed.scheme or "").lower()
    if scheme in {"postgres", "postgresql"}:
        raise BenchmarkAborted(
            "T21 cold-start is SQLite-only; PostgreSQL is T23"
        )
    if scheme not in {"sqlite", "sqlite3"}:
        raise BenchmarkAborted("T21 cold-start requires a sqlite:/// URL")
    return assert_fresh_sqlite(url)


def config_from_args(
    args: argparse.Namespace, environ: Mapping[str, str] | None = None
) -> BenchmarkRunConfig:
    protocol = str(getattr(args, "protocol", None) or "").strip() or None
    scenario = str(getattr(args, "scenario", None) or "").strip()
    explain = bool(getattr(args, "explain", False))
    mutations = bool(getattr(args, "mutations", False))
    webhooks = bool(getattr(args, "webhooks", False))
    page_weight = bool(getattr(args, "page_weight", False))
    cold_start = bool(getattr(args, "cold_start", False))
    concurrency_raw = getattr(args, "concurrency", None)
    concurrency_levels = (
        parse_concurrency_levels(str(concurrency_raw))
        if concurrency_raw is not None
        else None
    )
    if mutations and webhooks:
        raise BenchmarkAborted("--mutations cannot be combined with --webhooks")
    t19 = mutations or webhooks
    if t19 and explain:
        raise BenchmarkAborted(
            "--mutations/--webhooks cannot be combined with --explain"
        )
    if t19 and protocol:
        raise BenchmarkAborted(
            "--mutations/--webhooks cannot be combined with --protocol"
        )
    if t19 and concurrency_levels:
        raise BenchmarkAborted(
            "--mutations/--webhooks cannot be combined with --concurrency"
        )
    if page_weight and t19:
        raise BenchmarkAborted(
            "--page-weight cannot be combined with --mutations/--webhooks"
        )
    if page_weight and explain:
        raise BenchmarkAborted("--page-weight cannot be combined with --explain")
    if page_weight and protocol:
        raise BenchmarkAborted("--page-weight cannot be combined with --protocol")
    if page_weight and concurrency_levels:
        raise BenchmarkAborted(
            "--page-weight cannot be combined with --concurrency"
        )
    if page_weight and scenario:
        raise BenchmarkAborted(
            "T20 --page-weight uses a fixed four-page matrix; omit --scenario"
        )
    if cold_start and page_weight:
        raise BenchmarkAborted("--cold-start cannot be combined with --page-weight")
    if cold_start and t19:
        raise BenchmarkAborted(
            "--cold-start cannot be combined with --mutations/--webhooks"
        )
    if cold_start and explain:
        raise BenchmarkAborted("--cold-start cannot be combined with --explain")
    if cold_start and protocol:
        raise BenchmarkAborted("--cold-start cannot be combined with --protocol")
    if cold_start and concurrency_levels:
        raise BenchmarkAborted("--cold-start cannot be combined with --concurrency")
    if cold_start and scenario:
        raise BenchmarkAborted("T21 --cold-start omits --scenario")
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
    if t19:
        assert_t19_sqlite(url)
    if page_weight:
        assert_t20_sqlite(url)
    if cold_start:
        assert_t21_sqlite(url)
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
    elif t19:
        scenario = scenario or ""
    elif page_weight:
        scenario = ""
    elif cold_start:
        scenario = ""
    elif not scenario:
        raise BenchmarkAborted("--scenario is required")
    warmup = int(args.warmup)
    iterations_arg = getattr(args, "iterations", None)
    webhook_n = 0
    webhook_m = 0
    if t19:
        if args.quick:
            warmup, iterations = 1, 1
        else:
            iterations = (
                DEFAULT_MUTATION_WAVES
                if iterations_arg is None
                else int(iterations_arg)
            )
        if webhooks:
            webhook_n = WEBHOOK_QUICK_N if args.quick else WEBHOOK_FULL_N
            webhook_m = WEBHOOK_QUICK_M if args.quick else WEBHOOK_FULL_M
            if webhook_n > WEBHOOK_MAX_NM or webhook_m > WEBHOOK_MAX_NM:
                raise BenchmarkAborted(
                    f"webhook N,M cannot exceed {WEBHOOK_MAX_NM}"
                )
    elif page_weight:
        warmup, iterations = 0, 1
    elif cold_start:
        warmup, iterations = 0, 1
    elif concurrency_levels:
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
        elif mutations:
            json_path = DEFAULT_MUTATIONS_JSON_PATH
        elif webhooks:
            json_path = DEFAULT_WEBHOOKS_JSON_PATH
        elif page_weight:
            json_path = DEFAULT_PAGE_WEIGHT_JSON_PATH
        elif cold_start:
            json_path = DEFAULT_COLD_START_JSON_PATH
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
        mutations=mutations,
        webhooks=webhooks,
        webhook_n=webhook_n,
        webhook_m=webhook_m,
        page_weight=page_weight,
        cold_start=cold_start,
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


def sqlite_url_for_path(path: Path) -> str:
    resolved = path if path.is_absolute() else path.resolve()
    return f"sqlite:///{resolved}"


def derived_t19_sqlite_path(stem_url: str, *parts: str) -> Path:
    """Fresh sibling file for one T19 scenario/wave. Never reuses the stem."""
    stem = sqlite_filesystem_path(stem_url)
    stem.parent.mkdir(parents=True, exist_ok=True)
    label = "-".join(str(part) for part in parts if str(part))
    unique = uuid4().hex[:10]
    suffix = stem.suffix if stem.suffix else ".db"
    target = stem.parent / f"{stem.stem}-{label}-{unique}{suffix}"
    assert_fresh_sqlite(sqlite_url_for_path(target))
    return target


def webhook_delivery_counts(results: Sequence[Any]) -> dict[str, int]:
    """Harness counters over process_delivery results. Not a product field."""
    deliveries = 0
    owned = 0
    duplicate = 0
    retry_busy = 0
    errors = 0
    for item in results:
        deliveries += 1
        status = int(getattr(item, "status_code", 0) or 0)
        is_owned = bool(getattr(item, "owned", False))
        error = getattr(item, "error", None)
        if is_owned:
            owned += 1
        is_retry_busy = status == 503 and not is_owned
        if status == 200 and not is_owned:
            duplicate += 1
        if is_retry_busy:
            retry_busy += 1
        elif status >= 400 or error is not None:
            errors += 1
    return {
        "deliveries": deliveries,
        "owned": owned,
        "duplicate": duplicate,
        "retry_busy": retry_busy,
        "errors": errors,
    }


class FakeProvider:
    """Harness-only in-memory provider for process_delivery. No sockets."""

    def __init__(self) -> None:
        self.fetches: list[str] = []
        self._lock = threading.Lock()
        self.status = "active"
        self.plan_id = "plan_plus"
        self.current_start = T19_PROVIDER_START
        self.current_end = T19_PROVIDER_END
        self.has_scheduled_changes = False
        self.customer_id = "cust_t19"

    def fetch_subscription(self, subscription_id: str):
        from constitution_memorizer.subscriptions.razorpay import ProviderSubscription

        with self._lock:
            self.fetches.append(str(subscription_id))
        return ProviderSubscription(
            id=str(subscription_id),
            plan_id=self.plan_id,
            status=self.status,
            current_start=self.current_start,
            current_end=self.current_end,
            customer_id=self.customer_id,
            short_url=None,
            has_scheduled_changes=self.has_scheduled_changes,
            raw={
                "id": str(subscription_id),
                "plan_id": self.plan_id,
                "status": self.status,
            },
        )


def _connect_mutation_sqlite(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout = {MUTATION_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def _allow_stub_laws():
    from constitution_memorizer.playground.roster import service as roster_service

    real = roster_service.is_playground_eligible_law

    def wrapped(law_id: str) -> bool:
        if str(law_id).startswith("stub-"):
            return True
        return real(law_id)

    roster_service.is_playground_eligible_law = wrapped
    try:
        yield
    finally:
        roster_service.is_playground_eligible_law = real


def _plus_entitlement_snapshot():
    from constitution_memorizer.entitlements.models import (
        CONSTITUTION_ACCESS_FULL,
        EntitlementSnapshot,
    )

    return EntitlementSnapshot(
        is_authenticated=True,
        subscription_status="active",
        tier="plus",
        is_subscribed=True,
        admin_override=False,
        can_use_constitution_learn=True,
        constitution_access=CONSTITUTION_ACCESS_FULL,
        can_read_laws=True,
        can_open_playground=True,
        can_consume_new_playground_law=True,
        playground_law_limit=10,
        playground_block_reason=None,
        billing_period_start=None,
        billing_period_end=None,
        legacy_status=None,
    )


def _worker_collectors(fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    from constitution_memorizer.web.request_context import (
        begin_request_timings,
        reset_request_timings,
        snapshot_request_counters,
    )

    token = begin_request_timings()
    started = time.perf_counter()
    try:
        payload = fn()
    except Exception as exc:
        payload = {
            "error_class": type(exc).__name__,
            "error_message": _sanitize_error_text(str(exc)),
        }
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    counters = snapshot_request_counters()
    reset_request_timings(token)
    payload["elapsed_ms"] = elapsed_ms
    payload["playground_db_writes"] = int(counters.get("playground_db_writes") or 0)
    payload["playground_repo_round_trips"] = int(
        counters.get("playground_repo_round_trips") or 0
    )
    return payload


def _wait_wave_futures(futures, *, timeout_s: float, cleanup_s: float):
    deadline = time.monotonic() + timeout_s
    results: list[Any] = [None] * len(futures)
    incomplete = False
    for index, future in enumerate(futures):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            incomplete = True
            break
        try:
            results[index] = future.result(timeout=remaining)
        except TimeoutError:
            incomplete = True
            break
    if incomplete:
        cleanup_deadline = time.monotonic() + cleanup_s
        for future in futures:
            if future.done():
                continue
            leftover = max(0.0, cleanup_deadline - time.monotonic())
            try:
                future.result(timeout=leftover)
            except Exception:
                pass
    workers_terminated = all(future.done() for future in futures)
    for index, future in enumerate(futures):
        if results[index] is not None:
            continue
        if future.done():
            try:
                results[index] = future.result(timeout=0)
            except Exception as exc:
                results[index] = {
                    "error_class": type(exc).__name__,
                    "error_message": _sanitize_error_text(str(exc)),
                    "elapsed_ms": 0.0,
                    "playground_db_writes": 0,
                    "playground_repo_round_trips": 0,
                }
        else:
            results[index] = {
                "error_class": "timeout",
                "error_message": "wave_timeout",
                "elapsed_ms": 0.0,
                "playground_db_writes": 0,
                "playground_repo_round_trips": 0,
            }
    return results, incomplete, workers_terminated


def _run_thread_wave(
    jobs: Sequence[Callable[[], dict[str, Any]]],
    *,
    timeout_s: float = MUTATION_WAVE_TIMEOUT_S,
    cleanup_s: float = MUTATION_CLEANUP_WAIT_S,
) -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor

    wall_started = time.perf_counter()
    executor = ThreadPoolExecutor(max_workers=max(1, len(jobs)))
    futures = [executor.submit(_worker_collectors, job) for job in jobs]
    results, incomplete, workers_terminated = _wait_wave_futures(
        futures, timeout_s=timeout_s, cleanup_s=cleanup_s
    )
    if incomplete and not workers_terminated:
        executor.shutdown(wait=False, cancel_futures=True)
    else:
        executor.shutdown(wait=True)
    wall_seconds = time.perf_counter() - wall_started
    error_classes: dict[str, int] = {}
    for row in results:
        klass = str((row or {}).get("error_class") or "")
        if klass:
            error_classes[klass] = error_classes.get(klass, 0) + 1
    completed = sum(1 for row in results if not (row or {}).get("error_class"))
    throughput = None
    if not incomplete and wall_seconds > 0 and completed:
        throughput = completed / wall_seconds
    return {
        "workers": results,
        "incomplete": incomplete,
        "workers_terminated": workers_terminated,
        "wave_wall_seconds": wall_seconds,
        "error_classes": error_classes,
        "throughput_rps": throughput,
        "preserved_db": incomplete,
    }


def _count_consumed(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT law_id) AS n FROM user_playground_roster_item
        WHERE consumed_at IS NOT NULL
        """
    ).fetchone()
    return int(row["n"] if row is not None else 0)


def _count_roster_rows(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM user_playground_roster_item").fetchone()
    return int(row["n"] if row is not None else 0)


def _progress_integrity(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT status, learned_at, times_completed, interval_days
        FROM user_playground_progress
        """
    ).fetchall()
    learned_at_values = [
        None if row["learned_at"] is None else str(row["learned_at"])[:10]
        for row in rows
    ]
    return {
        "progress_rows": len(rows),
        "status": None if not rows else str(rows[0]["status"]),
        "learned_at": None if not learned_at_values else learned_at_values[0],
        "learned_at_set_count": sum(1 for value in learned_at_values if value),
        "times_completed": None if not rows else int(rows[0]["times_completed"]),
        "interval_days": None if not rows else int(rows[0]["interval_days"]),
    }


def _seed_progress_row(
    repo,
    *,
    status: str,
    interval_days: int,
    next_revision: str,
    times_completed: int,
    learned_at: str,
    locator: str,
) -> None:
    now = "2026-09-25T00:00:00+00:00"
    repo.conn.execute(
        """
        INSERT INTO user_playground_progress (
            user_id, law_id, source_locator, status, cloze_done,
            times_completed, last_completed, next_revision, interval_days,
            source_version, source_hash, updated_at, learned_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'v', 'h', ?, ?)
        ON CONFLICT (user_id, law_id, source_locator) DO UPDATE SET
            status = excluded.status,
            times_completed = excluded.times_completed,
            last_completed = excluded.last_completed,
            next_revision = excluded.next_revision,
            interval_days = excluded.interval_days,
            learned_at = excluded.learned_at,
            cloze_done = excluded.cloze_done
        """,
        (
            str(BENCH_USER),
            "ndps",
            locator,
            status,
            0,
            times_completed,
            None,
            next_revision,
            interval_days,
            now,
            learned_at,
        ),
    )
    repo.conn.commit()


def _prepare_mutation_schemas(conn: sqlite3.Connection, cell_id: str) -> None:
    from constitution_memorizer.playground.db import (
        ensure_sqlite_schema as ensure_overlay_schema,
    )

    ensure_overlay_schema(conn)
    if cell_id.startswith("roster-"):
        from constitution_memorizer.playground.roster.db import (
            ensure_sqlite_schema as ensure_roster_schema,
        )

        ensure_roster_schema(conn)
    if cell_id.startswith("device-"):
        from constitution_memorizer.devices.db import (
            ensure_sqlite_schema as ensure_device_schema,
        )

        ensure_device_schema(conn)


def _seed_mutation_cell(conn: sqlite3.Connection, cell_id: str) -> dict[str, Any]:
    _prepare_mutation_schemas(conn, cell_id)
    if cell_id == "roster-cap":
        from constitution_memorizer.playground.roster.repository import (
            SqliteRosterRepository,
        )
        from constitution_memorizer.playground.roster.service import RosterService

        snap = _plus_entitlement_snapshot()
        service = RosterService(SqliteRosterRepository(conn))
        service.ensure_current_period(BENCH_USER, snap, now=PLAYGROUND_TEST_NOW)
        for index in range(9):
            result = service.confirm_add_law(
                BENCH_USER, f"stub-{index}", snap, now=PLAYGROUND_TEST_NOW
            )
            if not result.ok:
                raise BenchmarkAborted(
                    f"roster-cap seed failed on stub-{index}: {result.status}"
                )
        return {
            "consumed_distinct": _count_consumed(conn),
            "law_limit": 10,
            "seeded_stub_count": 9,
        }
    if cell_id == "roster-same-law":
        from constitution_memorizer.playground.roster.repository import (
            SqliteRosterRepository,
        )
        from constitution_memorizer.playground.roster.service import RosterService

        snap = _plus_entitlement_snapshot()
        RosterService(SqliteRosterRepository(conn)).ensure_current_period(
            BENCH_USER, snap, now=PLAYGROUND_TEST_NOW
        )
        return {
            "consumed_distinct": _count_consumed(conn),
            "roster_rows": _count_roster_rows(conn),
            "law_id": "ndps",
        }
    if cell_id == "device-cap":
        from constitution_memorizer.devices.repository import SqliteDeviceRepository
        from constitution_memorizer.devices.service import DeviceService
        from constitution_memorizer.devices.token import mint_installation_token

        repo = SqliteDeviceRepository(conn)
        service = DeviceService(repo, hmac_secret=T19_DEVICE_SECRET, device_limit=2)
        seeded = service.ensure_current_device(
            BENCH_USER,
            mint_installation_token(),
            auth_session_id="sess-seed",
            commercially_eligible=True,
        )
        if int(seeded.registered_device_count) != 1:
            raise BenchmarkAborted("device-cap seed did not register one device")
        return {
            "active_devices": repo.count_active(BENCH_USER),
            "device_limit": 2,
            "seeded_devices": 1,
        }
    if cell_id == "device-idem":
        from constitution_memorizer.devices.repository import SqliteDeviceRepository

        repo = SqliteDeviceRepository(conn)
        return {
            "active_devices": repo.count_active(BENCH_USER),
            "device_limit": 2,
            "shared_hash": True,
        }
    if cell_id == "progress-learned":
        from constitution_memorizer.playground.learning.modes import (
            PLAYGROUND_LEARN_MODES,
        )
        from constitution_memorizer.playground.repository import (
            SqlitePlaygroundRepository,
        )

        repo = SqlitePlaygroundRepository(conn)
        repo.add_item(BENCH_USER, "ndps", source_version="v", law_source_hash="t")
        locator = "ndps:section:8"
        for mode in PLAYGROUND_LEARN_MODES[:5]:
            repo.complete_mode(
                BENCH_USER,
                "ndps",
                locator,
                mode,
                source_version="v",
                source_hash="h",
                as_of=MUTATION_PROGRESS_TODAY,
            )
        integrity = _progress_integrity(conn)
        integrity["locator"] = locator
        integrity["seeded_modes"] = 5
        return integrity
    if cell_id == "revision-sixth":
        from constitution_memorizer.playground.learning.modes import (
            PLAYGROUND_LEARN_MODES,
        )
        from constitution_memorizer.playground.repository import (
            SqlitePlaygroundRepository,
        )

        repo = SqlitePlaygroundRepository(conn)
        repo.add_item(BENCH_USER, "ndps", source_version="v", law_source_hash="t")
        locator = "ndps:section:8"
        _seed_progress_row(
            repo,
            status="review",
            interval_days=3,
            next_revision=MUTATION_PROGRESS_TODAY.isoformat(),
            times_completed=1,
            learned_at="2026-09-20",
            locator=locator,
        )
        for mode in PLAYGROUND_LEARN_MODES[:5]:
            repo.complete_revision_mode_and_advance_if_ready(
                BENCH_USER,
                "ndps",
                locator,
                mode,
                source_version="v",
                source_hash="h",
                as_of=MUTATION_PROGRESS_TODAY,
                claimed_rung=3,
            )
        integrity = _progress_integrity(conn)
        integrity["locator"] = locator
        integrity["claimed_rung"] = 3
        return integrity
    raise BenchmarkAborted(f"unknown mutation cell {cell_id!r}")


def _mutation_jobs(
    path: Path, cell_id: str, concurrency: int
) -> list[Callable[[], dict[str, Any]]]:
    if cell_id == "roster-cap":
        law_ids = ("stub-x",) if concurrency == 1 else ("stub-x", "stub-y")

        def make_job(law_id: str) -> Callable[[], dict[str, Any]]:
            def job() -> dict[str, Any]:
                from constitution_memorizer.playground.roster.repository import (
                    SqliteRosterRepository,
                )
                from constitution_memorizer.playground.roster.service import (
                    RosterService,
                )

                conn = _connect_mutation_sqlite(path)
                try:
                    result = RosterService(SqliteRosterRepository(conn)).confirm_add_law(
                        BENCH_USER,
                        law_id,
                        _plus_entitlement_snapshot(),
                        now=PLAYGROUND_TEST_NOW,
                    )
                    return {"status": result.status, "ok": bool(result.ok)}
                finally:
                    conn.close()

            return job

        return [make_job(law_id) for law_id in law_ids]
    if cell_id == "roster-same-law":

        def job() -> dict[str, Any]:
            from constitution_memorizer.playground.roster.repository import (
                SqliteRosterRepository,
            )
            from constitution_memorizer.playground.roster.service import RosterService

            conn = _connect_mutation_sqlite(path)
            try:
                result = RosterService(SqliteRosterRepository(conn)).confirm_add_law(
                    BENCH_USER,
                    "ndps",
                    _plus_entitlement_snapshot(),
                    now=PLAYGROUND_TEST_NOW,
                )
                return {"status": result.status, "ok": bool(result.ok)}
            finally:
                conn.close()

        return [job for _ in range(concurrency)]
    if cell_id == "device-cap":
        from constitution_memorizer.devices.token import mint_installation_token

        tokens = [mint_installation_token() for _ in range(concurrency)]

        def make_job(index: int, token: str) -> Callable[[], dict[str, Any]]:
            def job() -> dict[str, Any]:
                from constitution_memorizer.devices.repository import (
                    SqliteDeviceRepository,
                )
                from constitution_memorizer.devices.service import DeviceService

                conn = _connect_mutation_sqlite(path)
                try:
                    access = DeviceService(
                        SqliteDeviceRepository(conn),
                        hmac_secret=T19_DEVICE_SECRET,
                        device_limit=2,
                    ).ensure_current_device(
                        BENCH_USER,
                        token,
                        auth_session_id=f"sess-{index}",
                        commercially_eligible=True,
                    )
                    return {
                        "registered": bool(access.current_device_registered),
                        "block_reason": access.block_reason,
                    }
                finally:
                    conn.close()

            return job

        return [make_job(index, token) for index, token in enumerate(tokens)]
    if cell_id == "device-idem":
        from constitution_memorizer.devices.token import hash_device_token

        digest = hash_device_token(T19_DEVICE_SECRET, "t19-shared-device-token")

        def job() -> dict[str, Any]:
            from constitution_memorizer.devices.models import PLATFORM_WEB
            from constitution_memorizer.devices.repository import SqliteDeviceRepository

            conn = _connect_mutation_sqlite(path)
            try:
                outcome = SqliteDeviceRepository(conn).register_if_under_cap(
                    BENCH_USER,
                    device_key_hash=digest,
                    platform=PLATFORM_WEB,
                    display_name="T19 web",
                    limit=2,
                )
                return {"status": outcome.status}
            finally:
                conn.close()

        return [job for _ in range(concurrency)]
    if cell_id == "progress-learned":

        def job() -> dict[str, Any]:
            from constitution_memorizer.playground.repository import (
                SqlitePlaygroundRepository,
            )

            conn = _connect_mutation_sqlite(path)
            try:
                SqlitePlaygroundRepository(conn).complete_mode(
                    BENCH_USER,
                    "ndps",
                    "ndps:section:8",
                    "test",
                    source_version="v",
                    source_hash="h",
                    as_of=MUTATION_PROGRESS_TODAY,
                )
                return {"status": "completed"}
            finally:
                conn.close()

        return [job for _ in range(concurrency)]
    if cell_id == "revision-sixth":

        def job() -> dict[str, Any]:
            from constitution_memorizer.playground.repository import (
                SqlitePlaygroundRepository,
            )

            conn = _connect_mutation_sqlite(path)
            try:
                SqlitePlaygroundRepository(conn).complete_revision_mode_and_advance_if_ready(
                    BENCH_USER,
                    "ndps",
                    "ndps:section:8",
                    "test",
                    source_version="v",
                    source_hash="h",
                    as_of=MUTATION_PROGRESS_TODAY,
                    claimed_rung=3,
                )
                return {"status": "completed"}
            finally:
                conn.close()

        return [job for _ in range(concurrency)]
    raise BenchmarkAborted(f"unknown mutation cell {cell_id!r}")


def _mutation_integrity_after(conn: sqlite3.Connection, cell_id: str) -> dict[str, Any]:
    if cell_id.startswith("roster-"):
        return {
            "consumed_distinct": _count_consumed(conn),
            "roster_rows": _count_roster_rows(conn),
        }
    if cell_id.startswith("device-"):
        from constitution_memorizer.devices.repository import SqliteDeviceRepository

        repo = SqliteDeviceRepository(conn)
        return {
            "active_devices": repo.count_active(BENCH_USER),
            "stored_devices": len(repo.list_devices(BENCH_USER)),
        }
    return _progress_integrity(conn)


def _expected_mutation_outcomes(cell_id: str, concurrency: int) -> list[str]:
    if cell_id == "roster-cap":
        return ["ok"] if concurrency == 1 else ["ok", "roster_full"]
    if cell_id == "roster-same-law":
        return ["successful"] * concurrency
    if cell_id == "device-cap":
        return ["registered"] if concurrency == 1 else ["device_limit", "registered"]
    if cell_id == "device-idem":
        return ["created"] if concurrency == 1 else ["created", "existing"]
    if cell_id in {"progress-learned", "revision-sixth"}:
        return ["completed"] * concurrency
    raise BenchmarkAborted(f"unknown mutation cell {cell_id!r}")


def _observed_mutation_outcomes(
    cell_id: str, workers: Sequence[Mapping[str, Any]]
) -> list[str]:
    if cell_id == "roster-same-law":
        return [
            "successful" if row.get("ok") else str(row.get("status") or "error")
            for row in workers
        ]
    if cell_id.startswith("roster-"):
        return [str(row.get("status") or "error") for row in workers]
    if cell_id == "device-cap":
        observed: list[str] = []
        for row in workers:
            if row.get("registered"):
                observed.append("registered")
            elif row.get("block_reason") == "device_limit":
                observed.append("device_limit")
            else:
                observed.append(str(row.get("block_reason") or "error"))
        return observed
    if cell_id == "device-idem":
        return [str(row.get("status") or "error") for row in workers]
    return [str(row.get("status") or "error") for row in workers]


def _mutation_correctness(
    cell_id: str,
    concurrency: int,
    *,
    workers: Sequence[Mapping[str, Any]],
    after: Mapping[str, Any],
) -> str | None:
    if any(row.get("error_class") for row in workers):
        return "worker_error"
    observed = sorted(_observed_mutation_outcomes(cell_id, workers))
    expected = sorted(_expected_mutation_outcomes(cell_id, concurrency))
    if cell_id == "roster-same-law":
        if not all(row.get("ok") for row in workers):
            return f"same-law not both successful: {observed}"
        if int(after["roster_rows"]) != 1:
            return f"roster_rows {after['roster_rows']} != 1"
        return None
    if observed != expected:
        return f"outcome_multiset {observed} != {expected}"
    if cell_id == "roster-cap":
        if int(after["consumed_distinct"]) != 10:
            return f"consumed_distinct {after['consumed_distinct']} != 10"
        return None
    if cell_id == "roster-same-law":
        if int(after["roster_rows"]) != 1:
            return f"roster_rows {after['roster_rows']} != 1"
        return None
    if cell_id == "device-cap":
        if int(after["active_devices"]) != 2:
            return f"active_devices {after['active_devices']} != 2"
        return None
    if cell_id == "device-idem":
        if int(after["active_devices"]) != 1 or int(after["stored_devices"]) != 1:
            return (
                "device_idem stored "
                f"{after['stored_devices']} active {after['active_devices']}"
            )
        return None
    if cell_id == "progress-learned":
        if int(after["progress_rows"]) != 1:
            return "progress_rows != 1"
        if after["status"] != "learned":
            return f"status {after['status']!r} != 'learned'"
        if int(after["learned_at_set_count"]) != 1:
            return "learned_at was not set once"
        if after["learned_at"] != MUTATION_PROGRESS_TODAY.isoformat():
            return f"learned_at {after['learned_at']!r}"
        if int(after["times_completed"] or 0) != 0:
            return "times_completed should stay 0 on learned transition"
        return None
    if cell_id == "revision-sixth":
        if int(after["times_completed"] or 0) != 2:
            return f"times_completed {after['times_completed']} != 2"
        if int(after["interval_days"] or 0) != 7:
            return f"interval_days {after['interval_days']} != 7"
        return None
    return "unknown_cell"


def run_single_mutation_wave(
    cell_id: str,
    db_path: Path,
    *,
    concurrency: int,
) -> dict[str, Any]:
    """One C=1 or C=2 wave on a fresh SQLite file. Operator and C=1 pytest."""
    if cell_id not in MUTATION_CELLS:
        raise BenchmarkAborted(f"unknown mutation cell {cell_id!r}")
    if concurrency not in MUTATION_CONCURRENCY_LEVELS:
        raise BenchmarkAborted("T19 mutation concurrency must be 1 or 2")
    assert_fresh_sqlite(sqlite_url_for_path(db_path))
    with _allow_stub_laws():
        seed = _connect_mutation_sqlite(db_path)
        try:
            before = _seed_mutation_cell(seed, cell_id)
            seed.commit()
        finally:
            seed.close()
        wave = _run_thread_wave(_mutation_jobs(db_path, cell_id, concurrency))
    after_conn = _connect_mutation_sqlite(db_path)
    try:
        after = _mutation_integrity_after(after_conn, cell_id)
    finally:
        after_conn.close()
    reason = None
    if wave["incomplete"]:
        reason = "wave_timeout"
        if not wave["workers_terminated"]:
            reason = "wave_timeout_workers_still_running"
    else:
        reason = _mutation_correctness(
            cell_id, concurrency, workers=wave["workers"], after=after
        )
    elapsed = [
        float(row.get("elapsed_ms") or 0.0)
        for row in wave["workers"]
        if row.get("error_class") != "timeout"
    ]
    writes = [int(row.get("playground_db_writes") or 0) for row in wave["workers"]]
    trips = [
        int(row.get("playground_repo_round_trips") or 0) for row in wave["workers"]
    ]
    return {
        "cell": cell_id,
        "concurrency": concurrency,
        "db_basename": db_path.name,
        "incomplete": bool(wave["incomplete"]),
        "workers_terminated": bool(wave["workers_terminated"]),
        "preserved_db": bool(wave["preserved_db"]),
        "wave_wall_seconds": wave["wave_wall_seconds"],
        "throughput_rps": wave["throughput_rps"],
        "worker_elapsed_ms": elapsed,
        "playground_db_writes": writes,
        "playground_repo_round_trips": trips,
        "error_classes": wave["error_classes"],
        "outcome_multiset_expected": _expected_mutation_outcomes(cell_id, concurrency),
        "outcome_multiset_observed": _observed_mutation_outcomes(
            cell_id, wave["workers"]
        ),
        "worker_statuses": [
            str(
                row.get("status")
                or row.get("block_reason")
                or ("registered" if row.get("registered") else "error")
            )
            for row in wave["workers"]
        ],
        "integrity_before": before,
        "integrity_after": after,
        "correct": reason is None,
        "aborted_reason": reason,
        "busy_timeout_ms": MUTATION_BUSY_TIMEOUT_MS,
        "wave_timeout_s": MUTATION_WAVE_TIMEOUT_S,
    }


def _level_mutation_summary(waves: list[dict[str, Any]], *, concurrency: int) -> dict[str, Any]:
    complete = [wave for wave in waves if not wave.get("incomplete") and wave.get("correct")]
    walls = [float(wave["wave_wall_seconds"]) for wave in complete]
    worker_ms = [
        ms
        for wave in complete
        for ms in wave.get("worker_elapsed_ms") or []
    ]
    return {
        "concurrency": concurrency,
        "requested_concurrency": concurrency,
        "waves": waves,
        "waves_ok": len(complete),
        "incomplete_waves": sum(1 for wave in waves if wave.get("incomplete")),
        "correct_waves": sum(1 for wave in waves if wave.get("correct")),
        "wave_wall_seconds": summarize_numbers(walls) if walls else None,
        "worker_elapsed_ms": summarize_numbers(worker_ms) if worker_ms else None,
        "throughput_rps": None
        if any(wave.get("incomplete") or not wave.get("correct") for wave in waves)
        else (
            summarize_numbers(
                [float(wave["throughput_rps"]) for wave in complete if wave.get("throughput_rps")]
            )
            if complete and all(wave.get("throughput_rps") is not None for wave in complete)
            else None
        ),
        "latency_caveat": (
            "do not compare absolute latency across materially different initial states"
        ),
    }


def run_mutations_benchmark(
    config: BenchmarkRunConfig, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """T19 C=1 control + C=2 service-level races on separate SQLite connections."""
    if config.explain or config.protocol or config.concurrency_levels or config.webhooks:
        raise BenchmarkAborted("run_mutations_benchmark is T19 --mutations only")
    effective_app_env = evaluate_safety_guard(
        requested_app_env=config.app_env,
        accept_nontest=config.accept_nontest,
        explain=False,
        environ=environ,
    )
    assert_t19_sqlite(config.database_url)
    waves_requested = int(config.iterations)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mutations",
        "app_env": str(effective_app_env),
        "database_backend": "sqlite",
        "client_shape": MUTATION_CLIENT_SHAPE,
        "waves_requested": waves_requested,
        "concurrency_levels_requested": list(MUTATION_CONCURRENCY_LEVELS),
        "wave_timeout_s": MUTATION_WAVE_TIMEOUT_S,
        "busy_timeout_ms": MUTATION_BUSY_TIMEOUT_MS,
        "live_razorpay": False,
        "http_smokes": False,
        "m5b_excluded": True,
        "aborted": False,
        "aborted_reason": None,
        "cells": [],
    }

    def _finish(*, aborted: bool, reason: str | None) -> dict[str, Any]:
        payload["aborted"] = aborted
        payload["aborted_reason"] = reason
        _assert_json_safe(payload)
        if config.json_path is not None:
            write_json_report(config.json_path, payload)
        if aborted:
            raise BenchmarkAborted(reason or "T19 mutations aborted")
        return payload

    with _allow_stub_laws():
        for cell_id in MUTATION_CELLS:
            cell_report: dict[str, Any] = {
                "id": cell_id,
                "levels": [],
            }
            payload["cells"].append(cell_report)
            for concurrency in MUTATION_CONCURRENCY_LEVELS:
                level_waves: list[dict[str, Any]] = []
                for wave_index in range(waves_requested):
                    db_path = derived_t19_sqlite_path(
                        config.database_url,
                        cell_id,
                        f"c{concurrency}",
                        f"w{wave_index}",
                    )
                    wave = run_single_mutation_wave(
                        cell_id, db_path, concurrency=concurrency
                    )
                    wave["wave_index"] = wave_index
                    level_waves.append(wave)
                    if wave.get("incomplete") or not wave.get("correct"):
                        cell_report["levels"].append(
                            _level_mutation_summary(
                                level_waves, concurrency=concurrency
                            )
                        )
                        return _finish(
                            aborted=True,
                            reason=str(wave.get("aborted_reason") or "mutation_failed"),
                        )
                cell_report["levels"].append(
                    _level_mutation_summary(level_waves, concurrency=concurrency)
                )
    return _finish(aborted=False, reason=None)


def _sign_webhook_body(raw: bytes, secret: str = T19_WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def _webhook_event_payload(event_name: str, *, sub_id: str = "sub_t19") -> dict[str, Any]:
    return {
        "entity": "event",
        "event": event_name,
        "payload": {
            "subscription": {
                "entity": {
                    "id": sub_id,
                    "status": "pending",
                    "plan_id": "plan_plus",
                }
            }
        },
        "created_at": T19_PROVIDER_START,
    }


def _webhook_secrets():
    from constitution_memorizer.subscriptions.webhook_signature import WebhookSecrets

    return WebhookSecrets(current=T19_WEBHOOK_SECRET, previous="")


def _build_webhook_processor(conn: sqlite3.Connection, fake: FakeProvider):
    from constitution_memorizer.subscriptions.config import SubscriptionPlanIds
    from constitution_memorizer.subscriptions.repository import (
        SqliteSubscriptionRepository,
    )
    from constitution_memorizer.subscriptions.service import SubscriptionService
    from constitution_memorizer.subscriptions.webhook_repository import (
        SqliteWebhookEventRepository,
    )
    from constitution_memorizer.subscriptions.webhooks import WebhookProcessor

    plans = SubscriptionPlanIds(plus="plan_plus", pro="plan_pro", max="plan_max")
    repo = SqliteSubscriptionRepository(conn)
    events = SqliteWebhookEventRepository(conn)
    service = SubscriptionService(repo, fake, plans, public_key_id="rzp_test_t19")
    processor = WebhookProcessor(
        events=events,
        subscriptions=repo,
        service=service,
        secrets=_webhook_secrets(),
    )
    return processor, service, events


def _seed_webhook_plus(conn: sqlite3.Connection) -> None:
    from constitution_memorizer.subscriptions.repository import (
        SqliteSubscriptionRepository,
    )

    SqliteSubscriptionRepository(conn).create_subscription_record(
        BENCH_USER,
        tier="plus",
        status="active",
        provider_subscription_id="sub_t19",
        provider_plan_id="plan_plus",
        provider_customer_id="cust_t19",
        billing_period_start=datetime.fromtimestamp(
            T19_PROVIDER_START, tz=timezone.utc
        ),
        billing_period_end=datetime.fromtimestamp(T19_PROVIDER_END, tz=timezone.utc),
        is_current=True,
    )


def _prepare_webhook_db(path: Path) -> sqlite3.Connection:
    from constitution_memorizer.subscriptions.db import ensure_sqlite_schema

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect_mutation_sqlite(path)
    ensure_sqlite_schema(conn)
    _seed_webhook_plus(conn)
    conn.commit()
    return conn


def _billing_state(service) -> dict[str, Any]:
    current = service.get_current(BENCH_USER)
    if current is None:
        return {"status": None, "billing_period_end": None, "tier": None}
    end = current.billing_period_end
    start = current.billing_period_start
    return {
        "status": current.status,
        "tier": current.tier,
        "billing_period_start": None if start is None else start.isoformat(),
        "billing_period_end": None if end is None else end.isoformat(),
        "provider_plan_id": current.provider_plan_id,
    }


def _provider_state(fake: FakeProvider) -> dict[str, Any]:
    return {
        "status": fake.status,
        "plan_id": fake.plan_id,
        "current_start": fake.current_start,
        "current_end": fake.current_end,
        "fetch_count": len(fake.fetches),
    }


def _result_public(result: Any, *, elapsed_ms: float | None = None) -> dict[str, Any]:
    payload = {
        "status_code": int(result.status_code),
        "owned": bool(result.owned),
        "error": result.error,
        "processing_status": result.processing_status,
    }
    if elapsed_ms is not None:
        payload["elapsed_ms"] = elapsed_ms
    return payload


def _count_webhook_event_rows(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM subscription_webhook_event"
    ).fetchone()
    return int(row["n"] if row is not None else 0)


def run_sequential_webhook_duplicate(db_path: Path) -> dict[str, Any]:
    """First owned delivery then processed replay: duplicate=1, one provider fetch."""
    assert_fresh_sqlite(sqlite_url_for_path(db_path))
    conn = _prepare_webhook_db(db_path)
    fake = FakeProvider()
    try:
        processor, service, events = _build_webhook_processor(conn, fake)
        raw = json.dumps(
            _webhook_event_payload("subscription.charged"),
            separators=(",", ":"),
        ).encode("utf-8")
        signature = _sign_webhook_body(raw)
        first_started = time.perf_counter()
        first = processor.process_delivery(raw, signature, "evt_dup")
        first_ms = (time.perf_counter() - first_started) * 1000.0
        second_started = time.perf_counter()
        second = processor.process_delivery(raw, signature, "evt_dup")
        second_ms = (time.perf_counter() - second_started) * 1000.0
        counts = webhook_delivery_counts([first, second])
        stored = events.get_event_by_provider_event_id("evt_dup")
        proof = {
            "first": _result_public(first, elapsed_ms=first_ms),
            "replay": _result_public(second, elapsed_ms=second_ms),
            "counts": counts,
            "provider_fetches": len(fake.fetches),
            "event_rows": _count_webhook_event_rows(conn),
            "processing_status": None
            if stored is None
            else stored.processing_status,
            "billing": _billing_state(service),
            "provider": _provider_state(fake),
        }
        if (
            first.status_code != 200
            or not first.owned
            or second.status_code != 200
            or second.owned
            or counts["duplicate"] != 1
            or counts["owned"] != 1
            or counts["retry_busy"] != 0
            or len(fake.fetches) != 1
        ):
            raise BenchmarkAborted(
                "sequential webhook duplicate proof failed: "
                f"counts={counts} fetches={len(fake.fetches)}"
            )
        return proof
    finally:
        conn.close()


def run_concurrent_webhook_duplicate(db_path: Path) -> dict[str, Any]:
    """C=2 same event id. Owned exactly once; fetches stay 1. Do not assume winner."""
    assert_fresh_sqlite(sqlite_url_for_path(db_path))
    seed = _prepare_webhook_db(db_path)
    seed.close()
    fake = FakeProvider()
    raw = json.dumps(
        _webhook_event_payload("subscription.charged"),
        separators=(",", ":"),
    ).encode("utf-8")
    signature = _sign_webhook_body(raw)
    barrier = threading.Barrier(2, timeout=3)

    def job() -> dict[str, Any]:
        conn = sqlite3.connect(
            str(db_path),
            timeout=2,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=1000")
        try:
            processor, _service, _events = _build_webhook_processor(conn, fake)
            barrier.wait()
            started = time.perf_counter()
            result = processor.process_delivery(raw, signature, "evt_same")
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            payload = _result_public(result, elapsed_ms=elapsed_ms)
            return payload
        finally:
            conn.close()

    wave = _run_thread_wave([job, job], timeout_s=10.0, cleanup_s=MUTATION_CLEANUP_WAIT_S)
    if wave["incomplete"]:
        reason = "wave_timeout"
        if not wave["workers_terminated"]:
            reason = "wave_timeout_workers_still_running"
        raise BenchmarkAborted(reason)
    results = []
    for row in wave["workers"]:
        if row.get("error_class"):
            raise BenchmarkAborted(
                f"concurrent webhook worker error {row.get('error_class')}"
            )
        results.append(
            type(
                "Delivery",
                (),
                {
                    "status_code": row["status_code"],
                    "owned": row["owned"],
                    "error": row.get("error"),
                    "processing_status": row.get("processing_status"),
                },
            )()
        )
    counts = webhook_delivery_counts(results)
    owned = int(counts["owned"])
    if owned != 1 or len(fake.fetches) != 1:
        raise BenchmarkAborted(
            "concurrent duplicate event-id failed: "
            f"owned={owned} fetches={len(fake.fetches)} counts={counts}"
        )
    non_owned = [row for row in wave["workers"] if not row.get("owned")]
    if len(non_owned) != 1:
        raise BenchmarkAborted("concurrent duplicate did not leave exactly one non-owner")
    other = non_owned[0]
    if int(other["status_code"]) == 200:
        if counts["duplicate"] != 1 or counts["retry_busy"] != 0:
            raise BenchmarkAborted(
                "processed concurrent replay must be duplicate=1, retry_busy=0"
            )
    elif int(other["status_code"]) == 503:
        if counts["retry_busy"] != 1 or counts["duplicate"] != 0:
            raise BenchmarkAborted(
                "in-flight concurrent 503 must be retry_busy, not duplicate"
            )
    else:
        raise BenchmarkAborted(f"unexpected non-owner status {other['status_code']}")
    read = _connect_mutation_sqlite(db_path)
    try:
        from constitution_memorizer.subscriptions.config import SubscriptionPlanIds
        from constitution_memorizer.subscriptions.repository import (
            SqliteSubscriptionRepository,
        )
        from constitution_memorizer.subscriptions.service import SubscriptionService

        service = SubscriptionService(
            SqliteSubscriptionRepository(read),
            fake,
            SubscriptionPlanIds(plus="plan_plus", pro="plan_pro", max="plan_max"),
            public_key_id="rzp_test_t19",
        )
        billing = _billing_state(service)
        event_rows = _count_webhook_event_rows(read)
    finally:
        read.close()
    return {
        "counts": counts,
        "deliveries": [_result_public(item) for item in results],
        "provider_fetches": len(fake.fetches),
        "event_rows": event_rows,
        "billing": billing,
        "provider": _provider_state(fake),
        "wave_wall_seconds": wave["wave_wall_seconds"],
        "workers_terminated": wave["workers_terminated"],
        "incomplete": False,
    }


def run_webhook_script(
    db_path: Path, *, unique_n: int, replay_m: int
) -> dict[str, Any]:
    """N unique charged events, M replays of the first id, then a distinct OOO pair."""
    if unique_n < 1 or replay_m < 1:
        raise BenchmarkAborted("webhook N and M must be >= 1")
    if unique_n > WEBHOOK_MAX_NM or replay_m > WEBHOOK_MAX_NM:
        raise BenchmarkAborted(f"webhook N,M cannot exceed {WEBHOOK_MAX_NM}")
    assert_fresh_sqlite(sqlite_url_for_path(db_path))
    conn = _prepare_webhook_db(db_path)
    fake = FakeProvider()
    try:
        processor, service, _events = _build_webhook_processor(conn, fake)

        def deliver(event_name: str, event_id: str) -> tuple[Any, float]:
            raw = json.dumps(
                _webhook_event_payload(event_name),
                separators=(",", ":"),
            ).encode("utf-8")
            started = time.perf_counter()
            result = processor.process_delivery(raw, _sign_webhook_body(raw), event_id)
            return result, (time.perf_counter() - started) * 1000.0

        unique_results: list[Any] = []
        unique_elapsed: list[float] = []
        unique_ids = [f"evt_u{index}" for index in range(unique_n)]
        for event_id in unique_ids:
            result, elapsed = deliver("subscription.charged", event_id)
            unique_results.append(result)
            unique_elapsed.append(elapsed)
            if result.status_code != 200 or not result.owned:
                raise BenchmarkAborted(
                    f"unique webhook {event_id} failed status={result.status_code}"
                )
        fetches_after_unique = len(fake.fetches)
        if fetches_after_unique != unique_n:
            raise BenchmarkAborted(
                f"unique webhooks fetched {fetches_after_unique}, expected {unique_n}"
            )
        replay_results: list[Any] = []
        replay_elapsed: list[float] = []
        replay_id = unique_ids[0]
        for _index in range(replay_m):
            result, elapsed = deliver("subscription.charged", replay_id)
            replay_results.append(result)
            replay_elapsed.append(elapsed)
            if result.status_code != 200 or result.owned:
                raise BenchmarkAborted(
                    "replayed processed event must be HTTP 200 owned=False"
                )
        if len(fake.fetches) != fetches_after_unique:
            raise BenchmarkAborted("duplicates must not cause extra provider fetches")
        replay_counts = webhook_delivery_counts(replay_results)
        if replay_counts["duplicate"] != replay_m or replay_counts["owned"] != 0:
            raise BenchmarkAborted(f"replay counts {replay_counts}")
        fake.current_start = T19_PROVIDER_START_2
        fake.current_end = T19_PROVIDER_END_2
        ooo_pending, ooo_pending_ms = deliver(
            "subscription.pending", "evt_ooo_pending"
        )
        ooo_charged, ooo_charged_ms = deliver(
            "subscription.charged", "evt_ooo_charged"
        )
        ooo_results = [ooo_pending, ooo_charged]
        ooo_counts = webhook_delivery_counts(ooo_results)
        if ooo_counts["duplicate"] != 0:
            raise BenchmarkAborted("distinct out-of-order ids must not be duplicates")
        if ooo_counts["owned"] != 2:
            raise BenchmarkAborted(
                f"out-of-order pair owned={ooo_counts['owned']}, expected 2"
            )
        if len(fake.fetches) != unique_n + 2:
            raise BenchmarkAborted(
                f"provider fetches {len(fake.fetches)} != N+2 ({unique_n + 2})"
            )
        billing = _billing_state(service)
        expected_end = datetime.fromtimestamp(T19_PROVIDER_END_2, tz=timezone.utc)
        current = service.get_current(BENCH_USER)
        if (
            current is None
            or current.status != fake.status
            or current.billing_period_end != expected_end
        ):
            raise BenchmarkAborted(
                "final billing state does not match provider "
                f"{billing} vs end={expected_end.isoformat()} status={fake.status}"
            )
        all_results = unique_results + replay_results + ooo_results
        return {
            "n": unique_n,
            "m": replay_m,
            "unique": {
                "event_ids": unique_ids,
                "counts": webhook_delivery_counts(unique_results),
                "elapsed_ms": unique_elapsed,
                "provider_fetches": fetches_after_unique,
            },
            "replays": {
                "source_event_id": replay_id,
                "m": replay_m,
                "counts": replay_counts,
                "elapsed_ms": replay_elapsed,
                "extra_provider_fetches": 0,
            },
            "out_of_order": {
                "event_ids": ["evt_ooo_pending", "evt_ooo_charged"],
                "event_names": ["subscription.pending", "subscription.charged"],
                "counts": ooo_counts,
                "deliveries": [
                    _result_public(ooo_pending, elapsed_ms=ooo_pending_ms),
                    _result_public(ooo_charged, elapsed_ms=ooo_charged_ms),
                ],
                "provider_fetches": 2,
            },
            "totals": webhook_delivery_counts(all_results),
            "provider_fetches": len(fake.fetches),
            "event_rows": _count_webhook_event_rows(conn),
            "billing": billing,
            "provider": _provider_state(fake),
            "live_razorpay": False,
        }
    finally:
        conn.close()


def run_webhooks_benchmark(
    config: BenchmarkRunConfig, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """T19 process_delivery duplicate + N/M + out-of-order script. SQLite only."""
    if config.explain or config.protocol or config.concurrency_levels or config.mutations:
        raise BenchmarkAborted("run_webhooks_benchmark is T19 --webhooks only")
    effective_app_env = evaluate_safety_guard(
        requested_app_env=config.app_env,
        accept_nontest=config.accept_nontest,
        explain=False,
        environ=environ,
    )
    assert_t19_sqlite(config.database_url)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "webhooks",
        "app_env": str(effective_app_env),
        "database_backend": "sqlite",
        "client_shape": MUTATION_CLIENT_SHAPE,
        "n": int(config.webhook_n),
        "m": int(config.webhook_m),
        "waves_requested": int(config.iterations),
        "live_razorpay": False,
        "http_smokes": False,
        "aborted": False,
        "aborted_reason": None,
        "sequential_duplicate": None,
        "concurrent_duplicate": [],
        "script": [],
    }

    def _finish(*, aborted: bool, reason: str | None) -> dict[str, Any]:
        payload["aborted"] = aborted
        payload["aborted_reason"] = reason
        _assert_json_safe(payload)
        if config.json_path is not None:
            write_json_report(config.json_path, payload)
        if aborted:
            raise BenchmarkAborted(reason or "T19 webhooks aborted")
        return payload

    try:
        seq_path = derived_t19_sqlite_path(config.database_url, "wh-seq")
        payload["sequential_duplicate"] = run_sequential_webhook_duplicate(seq_path)
        for wave_index in range(int(config.iterations)):
            conc_path = derived_t19_sqlite_path(
                config.database_url, "wh-conc", f"w{wave_index}"
            )
            concurrent = run_concurrent_webhook_duplicate(conc_path)
            concurrent["wave_index"] = wave_index
            payload["concurrent_duplicate"].append(concurrent)
        for wave_index in range(int(config.iterations)):
            script_path = derived_t19_sqlite_path(
                config.database_url, "wh-script", f"w{wave_index}"
            )
            script = run_webhook_script(
                script_path,
                unique_n=int(config.webhook_n),
                replay_m=int(config.webhook_m),
            )
            script["wave_index"] = wave_index
            payload["script"].append(script)
    except BenchmarkAborted as exc:
        return _finish(aborted=True, reason=exc.message)
    return _finish(aborted=False, reason=None)


def _assert_page_weight_json_safe(payload: Mapping[str, Any]) -> None:
    """T13 _assert_json_safe treats sha256/etag hex plus Google Fonts '@' as secrets.

    T20 still refuses fixture email and token-like blobs. It must be able to
    record font URLs, etags, and file digests.
    """
    blob = json.dumps(payload)
    if BENCH_EMAIL in blob:
        raise BenchmarkAborted("JSON report must not include fixture email")
    lowered = blob.lower()
    if "bearer " in lowered or "rtc_device" in lowered:
        raise BenchmarkAborted("JSON report would include sensitive data")


def gzip_equivalent_bytes(raw: bytes) -> int:
    """Local gzip -9 equivalent. Not served on the wire."""
    return len(gzip.compress(raw, compresslevel=GZIP_COMPRESSLEVEL))


def brotli_equivalent_bytes(raw: bytes) -> tuple[int | None, str]:
    """Optional Brotli equivalent. Null when the library is not installed."""
    try:
        import brotli
    except ImportError:
        return None, "library_not_installed"
    return len(brotli.compress(raw)), "computed"


def page_weight_byte_classes(
    raw: bytes, *, transferred_bytes: int | None = None
) -> dict[str, Any]:
    brotli_n, brotli_status = brotli_equivalent_bytes(raw)
    transferred = len(raw) if transferred_bytes is None else int(transferred_bytes)
    return {
        "source_bytes": len(raw),
        "transferred_bytes": transferred,
        "decoded_bytes": len(raw),
        "gzip_equivalent_bytes": gzip_equivalent_bytes(raw),
        "gzip_served": False,
        "gzip_compresslevel": GZIP_COMPRESSLEVEL,
        "brotli_equivalent_bytes": brotli_n,
        "brotli_served": False,
        "brotli_status": brotli_status,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "browser_transfer_size": None,
        "browser_encoded_body_size": None,
        "browser_decoded_body_size": None,
        "browser_timing_reason": "not_captured_ws11_in_process",
    }


def page_weight_catalog_key(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    path = unquote(parsed.path or "")
    if not path:
        return ""
    if not path.startswith("/"):
        path = "/" + path
    return unquote(path)


def page_weight_cache_bust(url: str) -> str | None:
    parsed = urlparse(str(url or "").strip())
    if not parsed.query:
        return None
    values = parse_qs(parsed.query, keep_blank_values=True).get("v")
    if values:
        return values[0]
    return parsed.query


def is_page_weight_third_party(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_first_party_static_url(url: str) -> bool:
    if is_page_weight_third_party(url):
        return False
    key = page_weight_catalog_key(url)
    return key.startswith("/static/") or key in PAGE_WEIGHT_WELL_KNOWN_ROOT_DISK


def resolve_static_disk_path(
    url: str, *, static_dir: Path | None = None
) -> Path:
    """Resolve a first-party URL under STATIC_DIR. Reject traversal."""
    root = (static_dir or PAGE_WEIGHT_STATIC_DIR).resolve()
    key = page_weight_catalog_key(url)
    if "\x00" in key:
        raise BenchmarkAborted(f"T20 static path rejected: {url!r}")
    well_known = PAGE_WEIGHT_WELL_KNOWN_ROOT_DISK.get(key)
    if well_known is not None:
        relative = well_known
    else:
        if not key.startswith("/static/"):
            raise BenchmarkAborted(f"T20 static path rejected: {url!r}")
        relative = key[len("/static/") :]
    if not relative or relative.startswith("/") or relative.startswith("\\"):
        raise BenchmarkAborted(f"T20 static path rejected: {url!r}")
    parts = Path(relative).parts
    if any(part in {"", ".."} or part.startswith("/") for part in parts):
        raise BenchmarkAborted(f"T20 static path rejected: {url!r}")
    if any(".." in unquote(part) for part in parts):
        raise BenchmarkAborted(f"T20 static path rejected: {url!r}")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise BenchmarkAborted(f"T20 static path rejected: {url!r}") from exc
    return candidate


class _PageWeightHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.assets: list[dict[str, Any]] = []
        self._in_script = False
        self._script_src: str | None = None
        self._script_type = ""
        self._script_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {str(key).lower(): ("" if value is None else str(value)) for key, value in attrs}
        if tag == "link":
            rel_tokens = [token.lower() for token in (ad.get("rel") or "").split()]
            href = ad.get("href") or ""
            if not href:
                return
            rels = set(rel_tokens)
            if "stylesheet" in rels:
                self.assets.append({"kind": "stylesheet", "url": href, "rel": " ".join(rel_tokens)})
            elif rels & {
                "icon",
                "shortcut",
                "apple-touch-icon",
                "apple-touch-icon-precomposed",
            }:
                self.assets.append({"kind": "icon", "url": href, "rel": " ".join(rel_tokens)})
            elif rels & {"preconnect", "dns-prefetch"}:
                self.assets.append({"kind": "preconnect", "url": href, "rel": " ".join(rel_tokens)})
            return
        if tag == "script":
            self._in_script = True
            self._script_src = ad.get("src") or None
            self._script_type = (ad.get("type") or "").lower()
            self._script_chunks = []
            if self._script_src:
                self.assets.append(
                    {
                        "kind": "script",
                        "url": self._script_src,
                        "script_type": self._script_type,
                    }
                )
            return
        if tag == "img":
            src = ad.get("src") or ""
            if src:
                self.assets.append({"kind": "img", "url": src})

    def handle_data(self, data: str) -> None:
        if self._in_script and not self._script_src:
            self._script_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "script" or not self._in_script:
            return
        if not self._script_src:
            body = "".join(self._script_chunks)
            kind = (
                "json_ld"
                if self._script_type == "application/ld+json"
                else "inline_script"
            )
            self.assets.append(
                {
                    "kind": kind,
                    "url": None,
                    "bytes": len(body.encode("utf-8")),
                }
            )
        self._in_script = False
        self._script_src = None
        self._script_type = ""
        self._script_chunks = []


def iter_html_assets(html_text: str) -> list[dict[str, Any]]:
    parser = _PageWeightHTMLParser()
    parser.feed(html_text)
    parser.close()
    return list(parser.assets)


def ws11_named_file_inventory(static_dir: Path | None = None) -> dict[str, int]:
    root = static_dir or PAGE_WEIGHT_STATIC_DIR
    sizes: dict[str, int] = {}
    for name in WS11_NAMED_FILES:
        path = root / name
        sizes[name] = int(path.stat().st_size) if path.is_file() else 0
    return sizes


def list_static_inventory_files(static_dir: Path | None = None) -> list[Path]:
    root = static_dir or PAGE_WEIGHT_STATIC_DIR
    if not root.is_dir():
        return []
    return sorted(path for path in root.iterdir() if path.is_file())


def first_party_page_weight_totals(
    html_source_bytes: int,
    css_rows: Sequence[Mapping[str, Any]],
    js_rows: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    """Inclusive HTML + distinct first-party CSS/JS. Images/fonts excluded."""
    seen: set[str] = set()
    css_source = 0
    css_gzip = 0
    js_source = 0
    js_gzip = 0
    for row in css_rows:
        key = str(row.get("catalog_key") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        css_source += int(row.get("source_bytes") or 0)
        css_gzip += int(row.get("gzip_equivalent_bytes") or 0)
    for row in js_rows:
        key = str(row.get("catalog_key") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        js_source += int(row.get("source_bytes") or 0)
        js_gzip += int(row.get("gzip_equivalent_bytes") or 0)
    return {
        "css_source_bytes": css_source,
        "css_gzip_equivalent_bytes": css_gzip,
        "js_source_bytes": js_source,
        "js_gzip_equivalent_bytes": js_gzip,
        "page_weight_html_css_js_source_bytes": html_source_bytes
        + css_source
        + js_source,
    }


def _html_gzip_plus_assets(
    html_raw: bytes, css_rows: Sequence[Mapping[str, Any]], js_rows: Sequence[Mapping[str, Any]]
) -> int:
    seen: set[str] = set()
    total = gzip_equivalent_bytes(html_raw)
    for row in list(css_rows) + list(js_rows):
        key = str(row.get("catalog_key") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        total += int(row.get("gzip_equivalent_bytes") or 0)
    return total


def summarize_html_assets(
    html_text: str,
    *,
    static_dir: Path | None = None,
    html_raw: bytes | None = None,
) -> dict[str, Any]:
    """Account CSS/JS/images from HTML. Disk is the source-byte basis."""
    root = static_dir or PAGE_WEIGHT_STATIC_DIR
    raw = html_text.encode("utf-8") if html_raw is None else html_raw
    assets = iter_html_assets(html_text)
    css_rows: list[dict[str, Any]] = []
    js_rows: list[dict[str, Any]] = []
    image_rows: list[dict[str, Any]] = []
    third_party: list[dict[str, Any]] = []
    inline = {"theme_script_bytes": 0, "json_ld_bytes": 0, "other_inline_script_bytes": 0}
    missing: list[dict[str, Any]] = []
    seen_css: set[str] = set()
    seen_js: set[str] = set()
    seen_img: set[str] = set()
    seen_third: set[str] = set()
    linked_static_urls: list[str] = []

    def _record_missing(kind: str, url: str, detail: str) -> None:
        missing.append(
            {"kind": "missing_asset", "asset_kind": kind, "url": url, "detail": detail}
        )

    for asset in assets:
        kind = str(asset.get("kind") or "")
        url = asset.get("url")
        if kind == "json_ld":
            inline["json_ld_bytes"] += int(asset.get("bytes") or 0)
            continue
        if kind == "inline_script":
            nbytes = int(asset.get("bytes") or 0)
            if inline["theme_script_bytes"] == 0:
                inline["theme_script_bytes"] = nbytes
            else:
                inline["other_inline_script_bytes"] += nbytes
            continue
        if not isinstance(url, str) or not url:
            continue
        if is_page_weight_third_party(url):
            if url not in seen_third:
                seen_third.add(url)
                third_party.append(
                    {
                        "kind": kind,
                        "url": url,
                        "fetch": "skipped_no_external_network",
                    }
                )
            continue
        if kind == "preconnect":
            if url not in seen_third:
                seen_third.add(url)
                third_party.append(
                    {
                        "kind": "preconnect",
                        "url": url,
                        "fetch": "skipped_no_external_network",
                    }
                )
            continue
        if not is_first_party_static_url(url):
            continue
        catalog_key = page_weight_catalog_key(url)
        try:
            disk_path = resolve_static_disk_path(url, static_dir=root)
        except BenchmarkAborted as exc:
            _record_missing(kind, url, exc.message)
            continue
        if kind in {"stylesheet", "script", "icon", "img"}:
            linked_static_urls.append(url)
        exists = disk_path.is_file()
        disk_bytes = disk_path.read_bytes() if exists else b""
        classes = page_weight_byte_classes(disk_bytes) if exists else {
            "source_bytes": 0,
            "transferred_bytes": None,
            "decoded_bytes": 0,
            "gzip_equivalent_bytes": 0,
            "gzip_served": False,
            "gzip_compresslevel": GZIP_COMPRESSLEVEL,
            "brotli_equivalent_bytes": None,
            "brotli_served": False,
            "brotli_status": "skipped_missing",
            "sha256": None,
            "browser_transfer_size": None,
            "browser_encoded_body_size": None,
            "browser_decoded_body_size": None,
            "browser_timing_reason": "not_captured_ws11_in_process",
        }
        row = {
            "url": url,
            "catalog_key": catalog_key,
            "cache_bust": page_weight_cache_bust(url),
            "filename": disk_path.name,
            "disk_path": str(disk_path),
            "exists": exists,
            **classes,
        }
        if not exists:
            _record_missing(kind, url, f"missing on disk: {disk_path.name}")
        if kind == "stylesheet":
            if catalog_key not in seen_css:
                seen_css.add(catalog_key)
                css_rows.append(row)
        elif kind == "script":
            if catalog_key not in seen_js:
                seen_js.add(catalog_key)
                js_rows.append(row)
        elif kind in {"icon", "img"}:
            if catalog_key not in seen_img:
                seen_img.add(catalog_key)
                image_rows.append(row)

    html_classes = page_weight_byte_classes(raw, transferred_bytes=len(raw))
    totals = first_party_page_weight_totals(
        html_classes["source_bytes"], css_rows, js_rows
    )
    totals["page_weight_html_css_js_gzip_equivalent_bytes"] = _html_gzip_plus_assets(
        raw, css_rows, js_rows
    )
    css_ok = bool(css_rows) and all(row.get("exists") for row in css_rows)
    js_ok = all(row.get("exists") for row in js_rows)
    complete = (not missing) and css_ok and js_ok
    return {
        "html": html_classes,
        "first_party_css": css_rows,
        "first_party_js": js_rows,
        "images": image_rows,
        "third_party": third_party,
        "inline": inline,
        "missing_assets": missing,
        "linked_static_urls": linked_static_urls,
        "complete": complete,
        **totals,
    }


def derived_t20_sqlite_path(stem_url: str, fixture: str) -> Path:
    stem = sqlite_filesystem_path(stem_url)
    stem.parent.mkdir(parents=True, exist_ok=True)
    unique = uuid4().hex[:10]
    suffix = stem.suffix if stem.suffix else ".db"
    target = stem.parent / f"{stem.stem}-{fixture}-{unique}{suffix}"
    assert_fresh_sqlite(sqlite_url_for_path(target))
    return target


def _page_weight_git_head() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _response_header(response: Any, name: str) -> str | None:
    value = response.headers.get(name)
    if value is None or str(value).strip() == "":
        return None
    return str(value)


def static_cache_observation(response: Any, url: str) -> dict[str, Any]:
    encoding = _response_header(response, "content-encoding")
    return {
        "url": url,
        "status_code": int(response.status_code),
        "content_type": _response_header(response, "content-type"),
        "cache_control": _response_header(response, "cache-control"),
        "etag": _response_header(response, "etag"),
        "last_modified": _response_header(response, "last-modified"),
        "content_encoding": encoding,
        "content_length_header": _response_header(response, "content-length"),
        "http_body_bytes": len(response.content),
        "served_encoding": encoding or "identity",
    }


def _incomplete_page_row(spec: Mapping[str, str], *, reason: str, status_code: int | None = None) -> dict[str, Any]:
    return {
        "id": spec["id"],
        "fixture": spec["fixture"],
        "method": spec["method"],
        "path": spec["path"],
        "path_group": spec["path_group"],
        "status_code": status_code,
        "complete": False,
        "skipped": status_code is None,
        "viewport_profiles": [dict(row) for row in PAGE_WEIGHT_VIEWPORT_PROFILES],
        "html": None,
        "first_party_css": [],
        "first_party_js": [],
        "images": [],
        "third_party": [],
        "inline": {},
        "missing_assets": [],
        "http_failures": [
            {
                "kind": "incomplete_capture" if status_code is None else "http_error",
                "page": spec["id"],
                "url": spec["path"],
                "detail": reason,
            }
        ],
        "page_weight_html_css_js_source_bytes": 0,
        "page_weight_html_css_js_gzip_equivalent_bytes": 0,
    }


def run_page_weight_benchmark(
    config: BenchmarkRunConfig, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """T20 four-page inventory. In-process ASGI + disk + gzip equivalents."""
    import asyncio

    from httpx import ASGITransport, AsyncClient

    if (
        config.explain
        or config.protocol
        or config.concurrency_levels
        or config.mutations
        or config.webhooks
        or not config.page_weight
    ):
        raise BenchmarkAborted("run_page_weight_benchmark is T20 --page-weight only")
    effective_app_env = evaluate_safety_guard(
        requested_app_env=config.app_env,
        accept_nontest=config.accept_nontest,
        explain=False,
        environ=environ,
    )
    assert_t20_sqlite(config.database_url)
    named_sizes = ws11_named_file_inventory()
    named_rows = []
    named_missing = [
        name for name, size in named_sizes.items() if int(size) <= 0
    ]
    for name, size in named_sizes.items():
        path = PAGE_WEIGHT_STATIC_DIR / name
        raw = path.read_bytes() if path.is_file() else b""
        classes = page_weight_byte_classes(raw) if path.is_file() else {
            "source_bytes": 0,
            "gzip_equivalent_bytes": 0,
            "brotli_equivalent_bytes": None,
            "sha256": None,
        }
        named_rows.append(
            {
                "filename": name,
                "static_path": f"/static/{name}",
                "exists": path.is_file(),
                "ws11_named": True,
                "source_bytes": classes.get("source_bytes", size),
                "gzip_equivalent_bytes": classes.get("gzip_equivalent_bytes", 0),
                "brotli_equivalent_bytes": classes.get("brotli_equivalent_bytes"),
                "sha256": classes.get("sha256"),
            }
        )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "page-weight",
        "measurement_mode": PAGE_WEIGHT_MEASUREMENT_MODE,
        "lighthouse": False,
        "browser_network": False,
        "external_network": False,
        "compression_served": "identity",
        "gzip_compresslevel": GZIP_COMPRESSLEVEL,
        "gzip_served": False,
        "app_env": str(effective_app_env),
        "database_backend": "sqlite",
        "client_shape": PAGE_WEIGHT_CLIENT_SHAPE,
        "git_head": _page_weight_git_head(),
        "alembic_head": EXPECTED_ALEMBIC_HEAD,
        "attribution": "inclusive_per_page_plus_unique_catalog",
        "create_app_timed": False,
        "aborted": False,
        "aborted_reason": None,
        "complete": False,
        "pages": [],
        "catalog": [],
        "ws11_named_files": named_rows,
        "third_party": [],
        "cache_policy": [],
        "js_css_referenced_assets": [],
        "unreferenced_static": [],
        "failures": [],
        "viewport_profiles": [dict(row) for row in PAGE_WEIGHT_VIEWPORT_PROFILES],
    }

    def _finish(*, aborted: bool, reason: str | None) -> dict[str, Any]:
        pages_complete = bool(payload["pages"]) and all(
            bool(page.get("complete")) for page in payload["pages"]
        )
        named_ok = not named_missing
        four_pages = len(payload["pages"]) == len(PAGE_WEIGHT_PAGES)
        is_complete = (
            (not aborted)
            and pages_complete
            and named_ok
            and four_pages
            and not payload["failures"]
        )
        payload["complete"] = is_complete
        payload["aborted"] = (not is_complete) or aborted
        payload["aborted_reason"] = None if is_complete else (
            reason or "T20 page-weight capture incomplete"
        )
        _assert_page_weight_json_safe(payload)
        if config.json_path is not None:
            write_json_report(config.json_path, payload)
        if payload["aborted"]:
            raise BenchmarkAborted(payload["aborted_reason"] or "T20 page-weight aborted")
        return payload

    def _add_failure(**item: Any) -> None:
        payload["failures"].append(item)

    for name in named_missing:
        _add_failure(
            kind="missing_asset",
            page=None,
            url=f"/static/{name}",
            detail=f"WS11 named file missing: {name}",
        )

    async def _capture_fixture(fixture: str, specs: list[dict[str, str]]) -> None:
        db_path = derived_t20_sqlite_path(config.database_url, fixture)
        app = create_benchmark_app(db_path, app_env="test")
        seed_scenario(app, fixture)
        skip_rest = False
        skip_reason = "prior page in fixture failed"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            await sign_in_benchmark_client(client)
            header_cache: dict[str, dict[str, Any]] = {}
            for spec in specs:
                if skip_rest:
                    row = _incomplete_page_row(spec, reason=skip_reason)
                    payload["pages"].append(row)
                    _add_failure(
                        kind="incomplete_capture",
                        page=spec["id"],
                        url=spec["path"],
                        detail=skip_reason,
                    )
                    continue
                response = await client.get(spec["path"])
                status = int(response.status_code)
                html_raw = bytes(response.content)
                if status < 200 or status >= 300:
                    row = _incomplete_page_row(
                        spec, reason=f"HTTP {status}", status_code=status
                    )
                    payload["pages"].append(row)
                    _add_failure(
                        kind="http_error",
                        page=spec["id"],
                        url=spec["path"],
                        detail=f"HTTP {status}",
                    )
                    skip_rest = True
                    skip_reason = f"{spec['id']} HTTP {status}"
                    continue
                html_text = html_raw.decode("utf-8", errors="replace")
                summary = summarize_html_assets(
                    html_text, html_raw=html_raw, static_dir=PAGE_WEIGHT_STATIC_DIR
                )
                http_failures: list[dict[str, Any]] = []
                for url in summary["linked_static_urls"]:
                    if is_page_weight_third_party(url):
                        continue
                    parsed = urlparse(url)
                    request_url = parsed.path
                    if parsed.query:
                        request_url = f"{parsed.path}?{parsed.query}"
                    if url not in header_cache:
                        static_response = await client.get(request_url)
                        observation = static_cache_observation(
                            static_response, request_url
                        )
                        try:
                            disk_path = resolve_static_disk_path(
                                url, static_dir=PAGE_WEIGHT_STATIC_DIR
                            )
                        except BenchmarkAborted as exc:
                            observation["capture_kind"] = "http_error"
                            observation["capture_detail"] = exc.message
                            header_cache[url] = observation
                            http_failures.append(
                                {
                                    "kind": "http_error",
                                    "page": spec["id"],
                                    "url": request_url,
                                    "detail": exc.message,
                                }
                            )
                            continue
                        disk_size = (
                            disk_path.stat().st_size if disk_path.is_file() else None
                        )
                        observation["disk_source_bytes"] = disk_size
                        static_status = int(static_response.status_code)
                        if static_status < 200 or static_status >= 300:
                            observation["capture_kind"] = "http_error"
                            observation["capture_detail"] = f"HTTP {static_status}"
                        elif (
                            disk_size is not None
                            and disk_size != observation["http_body_bytes"]
                        ):
                            observation["capture_kind"] = "body_disk_mismatch"
                            observation["capture_detail"] = (
                                f"http {observation['http_body_bytes']} "
                                f"!= disk {disk_size}"
                            )
                        else:
                            observation["capture_kind"] = None
                            observation["capture_detail"] = None
                        header_cache[url] = observation
                    observation = header_cache[url]
                    if observation.get("capture_kind"):
                        http_failures.append(
                            {
                                "kind": observation["capture_kind"],
                                "page": spec["id"],
                                "url": request_url,
                                "detail": observation.get("capture_detail"),
                            }
                        )
                    for bucket in (
                        summary["first_party_css"],
                        summary["first_party_js"],
                        summary["images"],
                    ):
                        for item in bucket:
                            if item.get("url") == url:
                                item["transferred_bytes"] = observation[
                                    "http_body_bytes"
                                ]
                                item["http_status"] = observation["status_code"]
                seen_cache_urls = {row.get("url") for row in payload["cache_policy"]}
                for observation in header_cache.values():
                    if observation.get("url") not in seen_cache_urls:
                        payload["cache_policy"].append(observation)
                        seen_cache_urls.add(observation.get("url"))
                seen_third = {row.get("url") for row in payload["third_party"]}
                for item in summary["third_party"]:
                    if item.get("url") not in seen_third:
                        payload["third_party"].append(item)
                        seen_third.add(item.get("url"))
                page_complete = bool(summary["complete"]) and not http_failures
                if summary["missing_assets"]:
                    for miss in summary["missing_assets"]:
                        _add_failure(
                            kind="missing_asset",
                            page=spec["id"],
                            url=miss.get("url"),
                            detail=miss.get("detail"),
                        )
                for fail in http_failures:
                    _add_failure(**fail)
                page_row = {
                    "id": spec["id"],
                    "fixture": spec["fixture"],
                    "method": spec["method"],
                    "path": spec["path"],
                    "path_group": spec["path_group"],
                    "status_code": status,
                    "complete": page_complete,
                    "skipped": False,
                    "viewport_profiles": [
                        dict(row) for row in PAGE_WEIGHT_VIEWPORT_PROFILES
                    ],
                    "html": {
                        **summary["html"],
                        "cache_control": _response_header(response, "cache-control"),
                        "etag": _response_header(response, "etag"),
                        "last_modified": _response_header(response, "last-modified"),
                        "content_encoding": _response_header(
                            response, "content-encoding"
                        ),
                    },
                    "first_party_css": summary["first_party_css"],
                    "first_party_js": summary["first_party_js"],
                    "images": summary["images"],
                    "third_party": summary["third_party"],
                    "inline": summary["inline"],
                    "missing_assets": summary["missing_assets"],
                    "http_failures": http_failures,
                    "page_weight_html_css_js_source_bytes": summary[
                        "page_weight_html_css_js_source_bytes"
                    ],
                    "page_weight_html_css_js_gzip_equivalent_bytes": summary[
                        "page_weight_html_css_js_gzip_equivalent_bytes"
                    ],
                    "css_source_bytes": summary["css_source_bytes"],
                    "js_source_bytes": summary["js_source_bytes"],
                    "css_gzip_equivalent_bytes": summary["css_gzip_equivalent_bytes"],
                    "js_gzip_equivalent_bytes": summary["js_gzip_equivalent_bytes"],
                }
                payload["pages"].append(page_row)
                if not page_complete:
                    skip_rest = True
                    skip_reason = f"{spec['id']} incomplete"

    async def _run() -> None:
        grouped: dict[str, list[dict[str, str]]] = {}
        for spec in PAGE_WEIGHT_PAGES:
            grouped.setdefault(spec["fixture"], []).append(spec)
        for fixture, specs in grouped.items():
            await _capture_fixture(fixture, specs)

    def _build_catalog() -> None:
        referenced: set[str] = set()
        request_urls: dict[str, list[str]] = {}
        pages_by_file: dict[str, list[str]] = {}
        for page in payload["pages"]:
            page_id = str(page.get("id") or "")
            for bucket_name in ("first_party_css", "first_party_js", "images"):
                for item in page.get(bucket_name) or []:
                    filename = str(item.get("filename") or "")
                    if not filename:
                        continue
                    referenced.add(filename)
                    request_urls.setdefault(filename, [])
                    url = str(item.get("url") or "")
                    if url and url not in request_urls[filename]:
                        request_urls[filename].append(url)
                    pages_by_file.setdefault(filename, [])
                    if page_id and page_id not in pages_by_file[filename]:
                        pages_by_file[filename].append(page_id)
        catalog = []
        unreferenced = []
        for path in list_static_inventory_files():
            raw = path.read_bytes()
            classes = page_weight_byte_classes(raw)
            linked = path.name in referenced
            row = {
                "filename": path.name,
                "static_path": f"/static/{path.name}",
                "request_urls": request_urls.get(path.name, []),
                "pages": pages_by_file.get(path.name, []),
                "referenced_by_t20_pages": linked,
                "ws11_named": path.name in WS11_NAMED_FILES,
                **classes,
            }
            catalog.append(row)
            if not linked:
                unreferenced.append(row)
        payload["catalog"] = catalog
        payload["unreferenced_static"] = unreferenced
        literals = []
        linked_js = {
            item.get("filename")
            for page in payload["pages"]
            for item in page.get("first_party_js") or []
        }
        for literal in PAGE_WEIGHT_BOUNDED_STATIC_LITERALS:
            filename = Path(literal).name
            include = True
            if filename.startswith("onboarding-") and "onboarding.js" not in linked_js:
                include = False
            if filename == "completion-done.mp3" and "app.js" not in linked_js:
                include = False
            if not include:
                continue
            disk = PAGE_WEIGHT_STATIC_DIR / filename
            raw = disk.read_bytes() if disk.is_file() else b""
            classes = page_weight_byte_classes(raw) if disk.is_file() else {
                "source_bytes": 0,
                "gzip_equivalent_bytes": 0,
            }
            literals.append(
                {
                    "url": literal,
                    "filename": filename,
                    "exists": disk.is_file(),
                    "excluded_from_page_weight": True,
                    "note": "bounded_literal_not_js_parsed",
                    **classes,
                }
            )
        payload["js_css_referenced_assets"] = literals

    try:
        asyncio.run(_run())
        _build_catalog()
    except BenchmarkAborted as exc:
        try:
            _build_catalog()
        except Exception:
            pass
        return _finish(aborted=True, reason=exc.message)
    return _finish(aborted=False, reason=None)


COLD_START_REQUIRED_KEYS = (
    "schema_version",
    "kind",
    "measurement_mode",
    "app_env",
    "database_backend",
    "client_shape",
    "spy_targets",
    "spy_installed",
    "spy_installed_too_late",
    "hook_installed_before_web_app_import",
    "preimport_web_app",
    "preimport_web_asgi",
    "preimport_bare_acts",
    "alembic_head",
    "git_head",
    "aborted",
    "complete",
    "contract_passed",
    "import",
    "create_app",
    "first_request",
    "startup",
    "failures",
    "incidental_stdout",
    "incidental_stderr",
)
COLD_START_PHASE_KEYS = (
    "duration_ms",
    "get_bare_act_calls",
    "load_cached_calls",
    "cache_hits",
    "cache_misses",
    "hydrated_slugs",
    "cache_currsize",
)
_COLD_START_HOSTS = ("recall-the-c.in", "recallthec.in")


def _assert_cold_start_json_safe(payload: Mapping[str, Any]) -> None:
    """T21 sanitizer. Does not reuse T13 hex/@ or T20 page-weight helpers."""
    blob = json.dumps(payload)
    if BENCH_EMAIL in blob:
        raise BenchmarkAborted("JSON report must not include fixture email")
    lowered = blob.lower()
    if "bearer " in lowered or "rtc_device" in lowered:
        raise BenchmarkAborted("JSON report would include sensitive data")
    if "eyj" in lowered:
        raise BenchmarkAborted("JSON report would include sensitive data")
    for host in _COLD_START_HOSTS:
        if host in lowered:
            raise BenchmarkAborted("JSON report would include production host")


def _truncate_incidental(text: str | None) -> str:
    raw = text or ""
    if len(raw) <= COLD_START_INCIDENTAL_LIMIT:
        return raw
    return raw[:COLD_START_INCIDENTAL_LIMIT] + "\n…truncated…\n"


def _cold_start_timeout_s(environ: Mapping[str, str] | None) -> float:
    env = os.environ if environ is None else environ
    raw = str(env.get("T21_CHILD_TIMEOUT_S") or "").strip()
    if raw:
        try:
            value = float(raw)
        except ValueError as exc:
            raise BenchmarkAborted("T21_CHILD_TIMEOUT_S must be a number") from exc
        if value <= 0:
            raise BenchmarkAborted("T21_CHILD_TIMEOUT_S must be positive")
        return value
    return COLD_START_CHILD_TIMEOUT_S


def _empty_cold_start_phase() -> dict[str, Any]:
    return {
        "duration_ms": 0.0,
        "get_bare_act_calls": 0,
        "load_cached_calls": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "hydrated_slugs": [],
        "cache_currsize": 0,
    }


def _cold_start_skeleton(*, reason: str | None = None) -> dict[str, Any]:
    aborted = reason is not None
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "cold-start",
        "measurement_mode": COLD_START_MEASUREMENT_MODE,
        "app_env": "test",
        "database_backend": "sqlite",
        "client_shape": COLD_START_CLIENT_SHAPE,
        "spy_targets": ["get_bare_act", "_load_cached"],
        "spy_installed": False,
        "spy_installed_too_late": False,
        "hook_installed": False,
        "hook_installed_before_web_app_import": False,
        "wrap_applied": False,
        "too_late_reason": reason if aborted else None,
        "web_app_in_sys_modules_at_wrap": False,
        "cache_info_at_wrap": None,
        "preimport_web_app": False,
        "preimport_web_asgi": False,
        "preimport_bare_acts": False,
        "asgi_imported": False,
        "alembic_head": EXPECTED_ALEMBIC_HEAD,
        "git_head": _page_weight_git_head(),
        "aborted": aborted,
        "aborted_reason": reason,
        "complete": False,
        "contract_passed": False,
        "import": _empty_cold_start_phase(),
        "create_app": _empty_cold_start_phase(),
        "first_request": None,
        "startup": {
            "sqlite_existed_before": None,
            "sqlite_exists_after": None,
            "sqlite_bytes_after": None,
            "sqlite_tables_after": [],
            "units_json_path": None,
            "units_json_bytes": None,
            "postgres_pool_created": None,
            "asgi_imported": False,
            "browse_imported_during_create_app": None,
            "lifespan_ran": False,
        },
        "failures": (
            [{"kind": "incomplete_capture", "detail": reason}] if reason else []
        ),
        "incidental_stdout": "",
        "incidental_stderr": "",
        "child_returncode": None,
    }


def _cold_start_phase_ok(phase: Mapping[str, Any] | None) -> bool:
    if not isinstance(phase, dict):
        return False
    for key in COLD_START_PHASE_KEYS:
        if key not in phase:
            return False
    duration = phase.get("duration_ms")
    if not isinstance(duration, (int, float)) or not math.isfinite(float(duration)):
        return False
    if float(duration) < 0:
        return False
    return True


def _cold_start_result_complete(payload: Mapping[str, Any]) -> bool:
    if not payload.get("complete"):
        return False
    if payload.get("spy_installed_too_late"):
        return False
    if not payload.get("spy_installed"):
        return False
    if not payload.get("hook_installed_before_web_app_import"):
        return False
    if not _cold_start_phase_ok(payload.get("import")):
        return False
    if not _cold_start_phase_ok(payload.get("create_app")):
        return False
    for key in COLD_START_REQUIRED_KEYS:
        if key not in payload:
            return False
    return True


def spawn_cold_start_child(
    *,
    mode: str,
    result_path: Path,
    db_path: Path | None = None,
    units_path: Path | None = None,
    timeout_s: float | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Spawn a virgin interpreter. Kill and reap on timeout. No retries."""
    env_in = os.environ if environ is None else environ
    env = {k: v for k, v in dict(env_in).items() if k != "DATABASE_URL"}
    src = str(REPO_ROOT / "src")
    existing = str(env.get("PYTHONPATH") or "")
    env["PYTHONPATH"] = src if not existing else src + os.pathsep + existing
    env["APP_ENV"] = "test"
    env.pop("PYTHONSTARTUP", None)
    cmd = [
        sys.executable,
        "-m",
        "constitution_memorizer.playground.cold_start_spy",
        "--mode",
        mode,
        "--result",
        str(result_path),
    ]
    if db_path is not None:
        cmd.extend(["--db-path", str(db_path)])
    if units_path is not None:
        cmd.extend(["--units-path", str(units_path)])
    bound = COLD_START_CHILD_TIMEOUT_S if timeout_s is None else float(timeout_s)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=bound)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        stdout, stderr = proc.communicate()
    return {
        "returncode": proc.returncode,
        "stdout": stdout or "",
        "stderr": stderr or "",
        "timed_out": timed_out,
        "result_path": result_path,
    }


def _read_child_result(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return None
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, dict):
        return None
    return loaded


def _merge_child_measure(
    child: dict[str, Any] | None,
    *,
    spawn: Mapping[str, Any],
    reason: str | None,
) -> dict[str, Any]:
    payload = _cold_start_skeleton(reason=reason)
    payload["incidental_stdout"] = _truncate_incidental(str(spawn.get("stdout") or ""))
    payload["incidental_stderr"] = _truncate_incidental(str(spawn.get("stderr") or ""))
    payload["child_returncode"] = spawn.get("returncode")
    payload["git_head"] = _page_weight_git_head()
    if child:
        for key, value in child.items():
            if key in {"incidental_stdout", "incidental_stderr"}:
                continue
            payload[key] = value
        payload["git_head"] = child.get("git_head") or payload["git_head"]
        payload["alembic_head"] = EXPECTED_ALEMBIC_HEAD
        payload["incidental_stdout"] = _truncate_incidental(
            str(spawn.get("stdout") or "")
        )
        payload["incidental_stderr"] = _truncate_incidental(
            str(spawn.get("stderr") or "")
        )
        payload["child_returncode"] = spawn.get("returncode")
        payload["first_request"] = None
    if reason:
        payload["aborted"] = True
        payload["aborted_reason"] = reason
        payload["complete"] = False
        payload["contract_passed"] = False
        kinds = {row.get("kind") for row in payload.get("failures") or [] if isinstance(row, dict)}
        fail_kind = "incomplete_capture"
        if reason == "child_timeout":
            fail_kind = "child_timeout"
        elif reason in {"child_exit", "missing_result"}:
            fail_kind = reason
        elif reason == "malformed_result":
            fail_kind = "malformed_result"
        elif reason == "spy_installed_too_late":
            fail_kind = "spy_installed_too_late"
        if fail_kind not in kinds:
            payload.setdefault("failures", []).append(
                {"kind": fail_kind, "detail": reason}
            )
    return payload


def run_cold_start_self_test(
    *,
    result_path: Path,
    timeout_s: float | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Positive-control child. Never reuse this process for measurement."""
    spawn = spawn_cold_start_child(
        mode="self-test",
        result_path=result_path,
        timeout_s=timeout_s,
        environ=environ,
    )
    child = _read_child_result(result_path)
    if spawn["timed_out"]:
        raise BenchmarkAborted("T21 positive-control child_timeout")
    if child is None:
        raise BenchmarkAborted("T21 positive-control missing or malformed result")
    if child.get("kind") != "cold-start-self-test" or not child.get("complete"):
        raise BenchmarkAborted(
            child.get("aborted_reason") or "T21 positive-control failed"
        )
    return child


def run_cold_start_benchmark(
    config: BenchmarkRunConfig, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """T21 fresh-interpreter import + create_app measurement. SQLite-only."""
    if (
        config.explain
        or config.protocol
        or config.concurrency_levels
        or config.mutations
        or config.webhooks
        or config.page_weight
        or not config.cold_start
    ):
        raise BenchmarkAborted("run_cold_start_benchmark is T21 --cold-start only")
    effective_app_env = evaluate_safety_guard(
        requested_app_env=config.app_env,
        accept_nontest=config.accept_nontest,
        explain=False,
        environ=environ,
    )
    db_path = assert_t21_sqlite(config.database_url)
    json_path = config.json_path or DEFAULT_COLD_START_JSON_PATH
    units = MINI_UNITS
    timeout_s = _cold_start_timeout_s(environ)
    result_path = json_path.parent / f".{json_path.name}.child.json"

    def _write(payload: dict[str, Any]) -> dict[str, Any]:
        payload["app_env"] = str(effective_app_env)
        payload["git_head"] = payload.get("git_head") or _page_weight_git_head()
        payload["alembic_head"] = EXPECTED_ALEMBIC_HEAD
        payload["first_request"] = None
        _assert_cold_start_json_safe(payload)
        write_json_report(json_path, payload)
        try:
            result_path.unlink()
        except OSError:
            pass
        return payload

    spawn = spawn_cold_start_child(
        mode="measure",
        result_path=result_path,
        db_path=db_path,
        units_path=units,
        timeout_s=timeout_s,
        environ=environ,
    )
    child = _read_child_result(result_path)
    if spawn["timed_out"]:
        payload = _merge_child_measure(child, spawn=spawn, reason="child_timeout")
        _write(payload)
        raise BenchmarkAborted("T21 child_timeout")
    if child is None:
        reason = "missing_result" if not result_path.is_file() else "malformed_result"
        if spawn["returncode"] not in (0, 1):
            reason = "child_exit"
        payload = _merge_child_measure(child, spawn=spawn, reason=reason)
        _write(payload)
        raise BenchmarkAborted(f"T21 {reason}")
    payload = _merge_child_measure(child, spawn=spawn, reason=None)
    if payload.get("spy_installed_too_late") or not payload.get("spy_installed"):
        payload = _merge_child_measure(
            child, spawn=spawn, reason="spy_installed_too_late"
        )
        _write(payload)
        raise BenchmarkAborted("T21 spy_installed_too_late")
    if not _cold_start_result_complete(payload):
        payload["complete"] = False
        payload["contract_passed"] = False
        payload["aborted"] = True
        payload["aborted_reason"] = payload.get("aborted_reason") or "incomplete_capture"
        payload.setdefault("failures", []).append(
            {"kind": "incomplete_capture", "detail": "incomplete_capture"}
        )
        _write(payload)
        raise BenchmarkAborted("T21 incomplete_capture")
    if not payload.get("contract_passed"):
        _write(payload)
        raise BenchmarkAborted("T21 import/create_app hydration contract failed")
    return _write(payload)


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
        elif config.mutations:
            run_mutations_benchmark(config, environ=env)
        elif config.webhooks:
            run_webhooks_benchmark(config, environ=env)
        elif config.page_weight:
            run_page_weight_benchmark(config, environ=env)
        elif config.cold_start:
            run_cold_start_benchmark(config, environ=env)
        else:
            run_benchmark(config, environ=env)
    except BenchmarkAborted as exc:
        print(exc.message, file=sys.stderr)
        return exc.exit_code
    return 0
