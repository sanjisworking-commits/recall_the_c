"""Per-request bound engine/memory and diagnostic timings."""

from __future__ import annotations

from contextvars import ContextVar, Token
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

TIMING_STAGES: tuple[str, ...] = (
    "auth_session",
    "request_bootstrap",
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
)
_REQUEST_COUNTER_SET = frozenset(REQUEST_COUNTERS)
REQUEST_NOTES: tuple[str, ...] = (
    "planner_pipeline_fallback_reason",
    "auth_state",
    "bare_act_cache",
)
_REQUEST_NOTE_SET = frozenset(REQUEST_NOTES)
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
    }
)


def wants_request_breakdown(path: str) -> bool:
    """True for Dashboard, Browse, Laws, Learn-flow, Settings, Pricing, Calendar."""
    if path in _BREAKDOWN_PATHS:
        return True
    parts = [segment for segment in path.split("/") if segment]
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
