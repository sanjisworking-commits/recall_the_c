"""Playground Stage 2 WS6/WS7 benchmark library (execution T13 + T14).

Statistics, fail-closed production guard, deterministic fixtures, in-process
HTTP runner, and JSON reporting. Does not change product behavior or T2–T9
instrumentation. PostgreSQL EXPLAIN is T15/WS8. BNSS cold/warm is
``--protocol bnss-cold-warm`` (T14/WS7); omitting ``--protocol`` keeps the
T13 unlabeled primary-route path.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import unquote, urlparse
from uuid import UUID

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
DEFAULT_JSON_PATH = Path("artifacts/playground-performance-baseline.json")
DEFAULT_BNSS_JSON_PATH = Path("artifacts/playground-bnss-cold-warm.json")
PROTOCOL_BNSS_COLD_WARM = "bnss-cold-warm"
PROTOCOLS = (PROTOCOL_BNSS_COLD_WARM,)
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
    """Abort before app creation or DB access. Return the effective env label."""
    env = os.environ if environ is None else environ
    if explain:
        raise BenchmarkAborted(
            "EXPLAIN is WS8/T15; not implemented in T13"
        )
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
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument(
        "--database-url",
        default=None,
        help="Required sqlite:/// path. Never falls back to DATABASE_URL.",
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
        help="Parsed then refused until T15/WS8",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help=(
            "Override warmup=1 and iterations=3. "
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


def config_from_args(
    args: argparse.Namespace, environ: Mapping[str, str] | None = None
) -> BenchmarkRunConfig:
    if args.explain:
        raise BenchmarkAborted("EXPLAIN is WS8/T15; not implemented in T13")
    protocol = str(getattr(args, "protocol", None) or "").strip() or None
    scenario = str(getattr(args, "scenario", None) or "").strip()
    if protocol == PROTOCOL_BNSS_COLD_WARM:
        if not scenario:
            scenario = "law-workspace"
        if scenario != "law-workspace":
            raise BenchmarkAborted(
                "--protocol bnss-cold-warm requires --scenario law-workspace"
            )
    elif not scenario:
        raise BenchmarkAborted("--scenario is required")
    warmup = int(args.warmup)
    iterations = int(args.iterations)
    if args.quick:
        warmup, iterations = 1, 3
    if warmup < 0 or iterations < 1:
        raise BenchmarkAborted("warmup must be >= 0 and iterations >= 1")
    url = resolve_database_url(args.database_url, environ)
    json_raw = getattr(args, "json", None)
    if json_raw is None:
        json_path = (
            DEFAULT_BNSS_JSON_PATH
            if protocol == PROTOCOL_BNSS_COLD_WARM
            else DEFAULT_JSON_PATH
        )
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
        explain=bool(args.explain),
        accept_nontest=bool(args.accept_nontest),
        protocol=protocol,
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
        explain=config.explain,
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


def run_benchmark(
    config: BenchmarkRunConfig, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    import asyncio

    from httpx import ASGITransport, AsyncClient

    effective_app_env = evaluate_safety_guard(
        requested_app_env=config.app_env,
        accept_nontest=config.accept_nontest,
        explain=config.explain,
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
        if config.protocol == PROTOCOL_BNSS_COLD_WARM:
            run_bnss_cold_warm(config, environ=env)
        else:
            run_benchmark(config, environ=env)
    except BenchmarkAborted as exc:
        print(exc.message, file=sys.stderr)
        return exc.exit_code
    return 0
