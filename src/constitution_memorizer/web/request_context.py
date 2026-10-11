"""Per-request bound engine/memory and diagnostic timings."""

from __future__ import annotations

import math
import os
import random
import re
from contextvars import ContextVar, Token
from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from constitution_memorizer.progress.memory import MemoryEngine
    from constitution_memorizer.progress.scheduler import ReminderEngine

bound_engine: ContextVar[ReminderEngine | None] = ContextVar("bound_engine", default=None)
bound_memory: ContextVar[MemoryEngine | None] = ContextVar("bound_memory", default=None)

# stage -> (total_ms, call_count). None = no HTTP request collector bound.
_request_timings: ContextVar[dict[str, tuple[float, int]] | None] = ContextVar(
    "request_timings", default=None
)
# name -> count. Independent of timings so we can log round-trips without ms.
_request_counters: ContextVar[dict[str, int] | None] = ContextVar(
    "request_counters", default=None
)
# name -> diagnostic string (logged only when set).
_request_notes: ContextVar[dict[str, str] | None] = ContextVar(
    "request_notes", default=None
)
# Last finished breakdown request in this task. Independent of collectors.
_last_request_performance: ContextVar[RequestPerformanceSnapshot | None] = ContextVar(
    "last_request_performance", default=None
)


@dataclass(frozen=True)
class RequestPerformanceSnapshot:
    """In-process copy of one request's timing breakdown. Not sent on the wire."""

    path_group: str
    method: str
    status_code: int
    total_ms: float
    timings: dict[str, tuple[float, int]]
    counters: dict[str, int]
    notes: dict[str, str]


TIMING_STAGES: tuple[str, ...] = (
    "auth_session",
    "request_bootstrap",
    "learn_mutation_preload",
    "profile",
    "progress_preload",
    "split_prefs",
    "split_write",
    "news_setting",
    "browse_build",
    "article_build",
    "dashboard_build",
    "dashboard_prep",
    "dashboard_sections",
    "planner_bundle",
    "learning_plan_read",
    "study_sessions_read",
    "auto_plan_read",
    "roadmap_freshness",
    "planner_project",
    "daily_goal_read",
    "due_build",
    "session_write",
    "calendar_build",
    "progress_dashboard",
    "progress_continue",
    "progress_stats",
    "progress_articles",
    "progress_map",
    "progress_recent",
    "article_progress",
    "revision_start",
    "speech_transcribe",
    "learn_build",
    "completion",
    "modes_seen",
    "mode_seen_write",
    "progress_ensure",
    "progress_update",
    "modes_clear_write",
    "completion_state",
    "completion_commit",
    "done_schedule",
    "gloss_read",
    "theme",
    "onboarding_setting",
    "nav_due",
    "bare_act_load",
    "template",
    "access_override",
    "free_articles_backfill_check",
    "claimed_articles",
    "billing_status",
    "admin_hint",
    "settings_frequency",
    "calendar_connection",
    "calendar_prefs",
    "calendar_pending_retry",
    "calendar_pref_write",
    "calendar_sync_schedule",
    "calendar_connection_write",
    "google_token_exchange",
    "google_calendar_check",
    "google_token_revoke",
    "roadmap_sync",
    "playground_entitlement",
    "playground_device",
    "playground_roster_access",
    "playground_home_build",
    "playground_home_summaries",
    "playground_source_presentations",
    "playground_workspace_build",
    "playground_selection_read",
    "playground_mode_progress",
    "playground_revision_progress",
    "playground_rollover_build",
    "playground_rollover_write",
    "playground_learning_build",
    "playground_learning_write",
    "playground_revision_build",
    "playground_revision_write",
    "playground_source_review",
    "playground_source_scan",
    "playground_today",
    "playground_calendar",
    "playground_admin_diagnostics",
)

_TIMING_STAGE_SET = frozenset(TIMING_STAGES)
REQUEST_COUNTERS: tuple[str, ...] = (
    "db_reads",
    "learning_plan_reads",
    "study_session_reads",
    "auto_plan_reads",
    "daily_goal_reads",
    "planner_selects",
    "planner_round_trips",
    "modes_seen_rows",
    "bare_act_cache_misses",
    "playground_db_reads",
    "playground_db_writes",
    "playground_repo_round_trips",
    "playground_summary_reads",
    "playground_roster_reads",
    "playground_progress_reads",
    "playground_source_review_reads",
    "playground_revision_reads",
    "playground_entitlement_resolves",
    "playground_device_lookups",
)
_REQUEST_COUNTER_SET = frozenset(REQUEST_COUNTERS)
REQUEST_NOTES: tuple[str, ...] = (
    "planner_pipeline_fallback_reason",
    "auth_state",
    "bare_act_cache",
    "playground_access_result",
    "playground_subscription_disposition",
    "playground_device_result",
    "playground_roster_result",
    "playground_law_state",
)
_REQUEST_NOTE_SET = frozenset(REQUEST_NOTES)

# Closed value sets for later Playground note writers. record_request_note
# still validates names only; these frozensets are not enforced here.
PLAYGROUND_ACCESS_RESULTS: frozenset[str] = frozenset(
    {
        "allowed",
        "guest",
        "free",
        "pending",
        "paused",
        "halted",
        "paid_period_ended",
        "device_limit",
        "device_revoked",
        "device_config_error",
        "replacement_limit",
        "roster_missing",
        "roster_full",
        "inactive_law",
    }
)
PLAYGROUND_SUBSCRIPTION_DISPOSITIONS: frozenset[str] = frozenset(
    {
        "created",
        "authenticated",
        "active",
        "pending",
        "halted",
        "paused",
        "cancelled",
        "completed",
        "expired",
    }
)
PLAYGROUND_DEVICE_RESULTS: frozenset[str] = frozenset(
    {
        "ok",
        "device_limit",
        "device_revoked",
        "device_config_error",
        "replacement_limit",
        "skipped_unpaid",
    }
)
PLAYGROUND_ROSTER_RESULTS: frozenset[str] = frozenset(
    {
        "ok",
        "roster_full",
        "roster_missing",
        "peek",
        "local_owner",
    }
)
PLAYGROUND_LAW_STATES: frozenset[str] = frozenset(
    {
        "none",
        "active",
        "removed",
        "historical",
        "ineligible",
    }
)

_LEARN_BREAKDOWN_SUFFIXES = frozenset({"choose", "seen", "done", "quiz"})
_BREAKDOWN_PATHS = frozenset(
    {
        "/dashboard",
        "/browse",
        "/settings",
        "/pricing",
        "/calendar",
        "/calendar/google/connect",
        "/calendar/google/callback",
        "/calendar/google/preferences",
        "/calendar/google/disconnect",
        "/progress",
        "/progress/mastered",
        "/revision/start",
        "/learning/start",
        "/sitemap.xml",
        "/sitemap-core.xml",
        "/sitemap-laws.xml",
    }
)
_PLAYGROUND_LEARN_ACTIONS = frozenset({"start", "complete", "speech", "quiz"})
_UUID_SEGMENT = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_SITEMAP_LAWS_FILE = re.compile(r"^sitemap-laws-(.+)\.xml$")


def _canonical_request_path(path: str) -> str:
    """Strip query/fragment, collapse slashes, drop a trailing slash."""
    text = str(path or "")
    for sep in ("?", "#"):
        cut = text.find(sep)
        if cut >= 0:
            text = text[:cut]
    if not text or text == "/":
        return "/"
    if not text.startswith("/"):
        text = "/" + text
    while "//" in text:
        text = text.replace("//", "/")
    if len(text) > 1 and text.endswith("/"):
        text = text.rstrip("/") or "/"
    return text


def wants_request_breakdown(path: str) -> bool:
    """True for Dashboard, Browse, Laws, Learn-flow, Settings, Pricing,
    Calendar, Playground, public sitemaps, and GET /admin/users/{user_id}.
    """
    path = _canonical_request_path(path)
    if path in _BREAKDOWN_PATHS:
        return True
    parts = [segment for segment in path.split("/") if segment]
    # Entire Playground router (prefix /playground), including POSTs.
    if parts and parts[0] == "playground":
        return True
    # Exact admin route that calls collect_playground_diagnostics.
    # Not /admin, not /admin/users, not nested POSTs under the user.
    if len(parts) == 3 and parts[0] == "admin" and parts[1] == "users":
        return True
    if (
        len(parts) == 1
        and parts[0].startswith("sitemap-laws-")
        and parts[0].endswith(".xml")
    ):
        return True
    # Every /laws page: the index, an Act, a section, a schedule. These render
    # no user data, so the question they have to answer is why they ever cost
    # more than a template render.
    if parts and parts[0] == "laws":
        return True
    if len(parts) == 3 and parts[0] == "browse" and parts[1] == "article":
        return True
    if (
        len(parts) == 4
        and parts[0] == "api"
        and parts[1] == "articles"
        and parts[3] == "progress"
    ):
        return True
    if (
        len(parts) == 4
        and parts[0] == "learn"
        and parts[2] == "speech"
        and parts[3] == "transcribe"
    ):
        return True
    if not parts or parts[0] != "learn":
        return False
    if len(parts) == 2:
        return True
    return len(parts) == 3 and parts[2] in _LEARN_BREAKDOWN_SUFFIXES


def normalize_request_path_group(path: str) -> str:
    """Collapse a request path to a low-cardinality metric label.

    Strips query/fragment. Templates Playground law ids, section numbers,
    units and learn modes; templates sitemap law slugs; templates admin
    user UUIDs. Unknown Playground remainder collapses to ``{other}``.
    Does not rewrite Constitution Learn/Browse article ids.
    """
    path = _canonical_request_path(path)
    if path == "/":
        return "/"
    parts = [segment for segment in path.split("/") if segment]
    if not parts:
        return "/"
    if parts[0] == "playground":
        return _normalize_playground_path_group(parts)
    if len(parts) == 1:
        sitemap_group = _normalize_sitemap_path_group(parts[0])
        if sitemap_group is not None:
            return sitemap_group
    if parts[0] == "admin":
        return _normalize_admin_path_group(parts)
    return path


def _normalize_playground_path_group(parts: list[str]) -> str:
    rest = parts[1:]
    if not rest:
        return "/playground"
    if rest[0] == "roster":
        return _normalize_playground_roster(rest[1:])
    if rest[0] == "laws":
        return _normalize_playground_laws(rest[1:])
    return "/playground/{other}"


def _with_other(prefix: str) -> str:
    return prefix + "/{other}"


def _normalize_playground_roster(rest: list[str]) -> str:
    if not rest:
        return "/playground/roster"
    if rest[0] == "next":
        if len(rest) == 1:
            return "/playground/roster/next"
        return _with_other("/playground/roster/next")
    if len(rest) >= 2 and rest[1] == "remove":
        prefix = "/playground/roster/{law_id}/remove"
        if len(rest) == 2:
            return prefix
        return _with_other(prefix)
    return "/playground/roster/{other}"


def _normalize_playground_laws(rest: list[str]) -> str:
    if not rest:
        return "/playground/laws/{other}"
    prefix = "/playground/laws/{law_id}"
    action_rest = rest[1:]
    if not action_rest:
        return prefix
    action = action_rest[0]
    if action == "add":
        if len(action_rest) == 1:
            return prefix + "/add"
        return _with_other(prefix + "/add")
    if action == "mastered":
        if len(action_rest) == 1:
            return prefix + "/mastered"
        return _with_other(prefix + "/mastered")
    if action == "sections":
        return _normalize_playground_sections(prefix, action_rest[1:])
    if action == "source-review":
        return _normalize_playground_source_review(prefix, action_rest[1:])
    return _with_other(prefix)


def _known_section_suffix(after_number: list[str]) -> bool:
    if not after_number:
        return False
    head = after_number[0]
    if head in {"learned", "mastered", "learn"}:
        return True
    return head == "u" and len(after_number) >= 2


def _normalize_playground_sections(prefix: str, rest: list[str]) -> str:
    sections = prefix + "/sections"
    if not rest:
        return sections
    if not _known_section_suffix(rest[1:]):
        return _with_other(sections)
    return _normalize_section_leaf(prefix + "/sections/{number}", rest[1:])


def _normalize_section_leaf(prefix: str, after_number: list[str]) -> str:
    head = after_number[0]
    if head == "learn":
        return _normalize_playground_learn(prefix, after_number[1:])
    if head in {"learned", "mastered"}:
        leaf = prefix + "/" + head
        if len(after_number) == 1:
            return leaf
        return _with_other(leaf)
    # head == "u" and a unit segment exists (checked by caller).
    return _normalize_playground_unit_leaf(prefix, after_number[1:])


def _normalize_playground_unit_leaf(prefix: str, after_u: list[str]) -> str:
    unit_prefix = prefix + "/u/{unit}"
    after_unit = after_u[1:]
    if not after_unit:
        return _with_other(prefix + "/u")
    head = after_unit[0]
    if head == "learn":
        return _normalize_playground_learn(unit_prefix, after_unit[1:])
    if head in {"learned", "mastered"}:
        leaf = unit_prefix + "/" + head
        if len(after_unit) == 1:
            return leaf
        return _with_other(leaf)
    return _with_other(prefix + "/u")


def _normalize_playground_learn(prefix: str, after_learn: list[str]) -> str:
    if not after_learn:
        return _with_other(prefix + "/learn")
    learn_prefix = prefix + "/learn/{mode}"
    after_mode = after_learn[1:]
    if not after_mode:
        return learn_prefix
    action = after_mode[0]
    if action in _PLAYGROUND_LEARN_ACTIONS:
        leaf = learn_prefix + "/" + action
        if len(after_mode) == 1:
            return leaf
        return _with_other(leaf)
    return _with_other(learn_prefix)


def _normalize_playground_source_review(prefix: str, rest: list[str]) -> str:
    source_review = prefix + "/source-review"
    if not rest:
        return source_review
    if rest[0] != "sections":
        return _with_other(source_review)
    after_sections = rest[1:]
    if not after_sections:
        return _with_other(source_review)
    number_prefix = source_review + "/sections/{number}"
    after_number = after_sections[1:]
    if not after_number:
        return number_prefix
    if after_number[0] == "reviewed":
        leaf = number_prefix + "/reviewed"
        if len(after_number) == 1:
            return leaf
        return _with_other(leaf)
    if after_number[0] == "u":
        after_u = after_number[1:]
        if not after_u:
            return _with_other(number_prefix + "/u")
        unit_prefix = number_prefix + "/u/{unit}"
        after_unit = after_u[1:]
        if not after_unit:
            return unit_prefix
        if after_unit[0] == "reviewed":
            leaf = unit_prefix + "/reviewed"
            if len(after_unit) == 1:
                return leaf
            return _with_other(leaf)
        return _with_other(unit_prefix)
    return _with_other(number_prefix)


def _normalize_sitemap_path_group(filename: str) -> str | None:
    if filename in {
        "sitemap.xml",
        "sitemap-core.xml",
        "sitemap-laws.xml",
        "sitemap-laws-{slug}.xml",
        "sitemap-laws-{slug}-{chunk}.xml",
    }:
        return "/" + filename
    matched = _SITEMAP_LAWS_FILE.match(filename)
    if matched is None:
        return None
    body = matched.group(1)
    slug, sep, maybe_n = body.rpartition("-")
    if sep and maybe_n.isdigit():
        return "/sitemap-laws-{slug}-{chunk}.xml"
    return "/sitemap-laws-{slug}.xml"


def _normalize_admin_path_group(parts: list[str]) -> str:
    out: list[str] = []
    for index, segment in enumerate(parts):
        if (
            _UUID_SEGMENT.match(segment)
            and index >= 2
            and parts[0] == "admin"
            and parts[1] == "users"
        ):
            out.append("{user_id}")
        else:
            out.append(segment)
    return "/" + "/".join(out)


def begin_request_timings() -> Token:
    """Bind empty timing + counter collectors for this request."""
    _request_counters.set({})
    _request_notes.set({})
    return _request_timings.set({})


def reset_request_timings(token: Token) -> None:
    """Restore the previous collector binding."""
    _request_timings.reset(token)
    _request_counters.set(None)
    _request_notes.set(None)


def snapshot_request_timings() -> dict[str, tuple[float, int]]:
    """Independent copy of recorded stages, or {} if no collector is bound."""
    current = _request_timings.get()
    if current is None:
        return {}
    return dict(current)


def record_request_timing(stage: str, started: float) -> None:
    """Accumulate elapsed ms for a whitelisted stage. No-op outside a request."""
    if stage not in _TIMING_STAGE_SET:
        raise ValueError(f"Unknown request timing stage: {stage}")
    current = _request_timings.get()
    if current is None:
        return
    elapsed_ms = (perf_counter() - started) * 1000.0
    total_ms, count = current.get(stage, (0.0, 0))
    current[stage] = (total_ms + elapsed_ms, count + 1)


def record_request_counter(name: str, n: int = 1) -> None:
    """Increment a whitelisted per-request counter. No-op outside a request."""
    if name not in _REQUEST_COUNTER_SET:
        raise ValueError(f"Unknown request counter: {name}")
    current = _request_counters.get()
    if current is None:
        return
    current[name] = current.get(name, 0) + n


def snapshot_request_counters() -> dict[str, int]:
    """Independent copy of recorded counters, or {} if no collector is bound."""
    current = _request_counters.get()
    if current is None:
        return {}
    return dict(current)


def record_request_note(name: str, value: str) -> None:
    """Record a whitelisted diagnostic string. No-op outside a request."""
    if name not in _REQUEST_NOTE_SET:
        raise ValueError(f"Unknown request note: {name}")
    current = _request_notes.get()
    if current is None:
        return
    current[name] = value


def snapshot_request_notes() -> dict[str, str]:
    """Independent copy of recorded notes, or {} if no collector is bound."""
    current = _request_notes.get()
    if current is None:
        return {}
    return dict(current)


def _clone_request_performance(
    snapshot: RequestPerformanceSnapshot,
) -> RequestPerformanceSnapshot:
    return RequestPerformanceSnapshot(
        path_group=snapshot.path_group,
        method=snapshot.method,
        status_code=snapshot.status_code,
        total_ms=snapshot.total_ms,
        timings=dict(snapshot.timings),
        counters=dict(snapshot.counters),
        notes=dict(snapshot.notes),
    )


def clear_last_request_performance() -> None:
    """Drop the task-local snapshot. Called at the start of every request."""
    _last_request_performance.set(None)


def capture_request_performance(
    *,
    path: str,
    method: str,
    status_code: int,
    total_ms: float,
) -> RequestPerformanceSnapshot:
    """Store a fresh snapshot from the current collectors; return a separate clone."""
    stored = RequestPerformanceSnapshot(
        path_group=normalize_request_path_group(path),
        method=method,
        status_code=int(status_code),
        total_ms=float(total_ms),
        timings=snapshot_request_timings(),
        counters=snapshot_request_counters(),
        notes=snapshot_request_notes(),
    )
    _last_request_performance.set(stored)
    return _clone_request_performance(stored)


def get_last_request_performance() -> RequestPerformanceSnapshot | None:
    """Fresh clone of the last snapshot in this task, or None."""
    current = _last_request_performance.get()
    if current is None:
        return None
    return _clone_request_performance(current)


def perf_log_sample_rate() -> float:
    """PERF_LOG_SAMPLE_RATE in [0, 1]. Missing, invalid, non-finite, or out of range → 1.0."""
    raw = os.environ.get("PERF_LOG_SAMPLE_RATE")
    if raw is None or str(raw).strip() == "":
        return 1.0
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        return 1.0
    return value


def should_emit_request_breakdown_log() -> bool:
    """Whether to emit the request_breakdown line. Does not affect collection."""
    rate = perf_log_sample_rate()
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() < rate


def breakdown_includes_raw_path(path: str) -> bool:
    """False when a raw path= label would leak a law id, UUID, or sitemap slug."""
    canonical = _canonical_request_path(path)
    parts = [segment for segment in canonical.split("/") if segment]
    if parts and parts[0] == "playground":
        return False
    if len(parts) == 3 and parts[0] == "admin" and parts[1] == "users":
        return False
    if (
        len(parts) == 1
        and parts[0].startswith("sitemap-laws-")
        and parts[0].endswith(".xml")
        and parts[0] != "sitemap-laws.xml"
    ):
        return False
    return True


def format_request_breakdown_line(
    snapshot: RequestPerformanceSnapshot,
    *,
    raw_path: str,
) -> str:
    """Build the request_breakdown log line. Constitution keeps path=; others do not."""
    parts = [f"request_breakdown method={snapshot.method}"]
    if breakdown_includes_raw_path(raw_path):
        parts.append(f"path={_canonical_request_path(raw_path)}")
    parts.append(f"path_group={snapshot.path_group}")
    parts.append(f"total_ms={snapshot.total_ms:.1f}")
    for stage in TIMING_STAGES:
        if stage not in snapshot.timings:
            continue
        stage_ms, count = snapshot.timings[stage]
        parts.append(f"{stage}_ms={stage_ms:.1f}")
        parts.append(f"{stage}_n={count}")
    for name, count in snapshot.counters.items():
        parts.append(f"{name}={count}")
    for name, value in snapshot.notes.items():
        parts.append(f"{name}={value}")
    return " ".join(parts)
