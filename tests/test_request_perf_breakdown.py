"""Request-scoped diagnostic timings for Dashboard and Browse."""

from __future__ import annotations

import ast
import asyncio
import inspect
import logging
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.devices.models import (
    BLOCK_DEVICE_CONFIG_ERROR,
    BLOCK_DEVICE_LIMIT,
    BLOCK_DEVICE_REPLACEMENT_LIMIT,
    BLOCK_DEVICE_REVOKED,
    DeviceAccess,
)
from constitution_memorizer.devices.service import DeviceService
from constitution_memorizer.devices.token import (
    DEVICE_COOKIE_NAME,
    TEST_DEVICE_HMAC_SECRET,
    mint_installation_token,
)
from constitution_memorizer.entitlements.dependencies import (
    apply_device_access,
    commercial_playground_notes,
    device_playground_notes,
    get_entitlement_snapshot,
    record_roster_access_outcome,
    roster_playground_notes,
)
from constitution_memorizer.entitlements.models import (
    BLOCK_NOT_SUBSCRIBED,
    BLOCK_PAID_PERIOD_ENDED,
    BLOCK_PAYMENT_HALTED,
    BLOCK_SIGN_IN_REQUIRED,
    BLOCK_SUBSCRIPTION_PAUSED,
    CONSTITUTION_ACCESS_FULL,
    EntitlementSnapshot,
)
from constitution_memorizer.playground.access import (
    PlaygroundAccess,
    _attach_current_period,
    _ensure_device_and_refresh,
    consume_blocked_response,
    require_law_active_this_period,
)
from constitution_memorizer.playground.roster.models import (
    RESULT_NEW_BLOCKED,
    RESULT_ROSTER_FULL,
)
from constitution_memorizer.playground.db import (
    ensure_sqlite_schema as ensure_overlay_sqlite_schema,
)
from constitution_memorizer.playground.postgres import PostgresPlaygroundRepository
from constitution_memorizer.playground.repository import SqlitePlaygroundRepository
from constitution_memorizer.playground.roster.db import (
    ensure_sqlite_schema as ensure_roster_sqlite_schema,
)
from constitution_memorizer.playground.roster.postgres import PostgresRosterRepository
from constitution_memorizer.playground.roster.period import (
    playground_month_bounds,
    playground_today,
)
from constitution_memorizer.playground.roster.repository import SqliteRosterRepository
from constitution_memorizer.playground.roster.service import RosterService
from constitution_memorizer.playground.service import (
    activate_law,
    persist_entire_act_selection,
)
from constitution_memorizer.playground.schedule import (
    playground_calendar_chips,
    playground_google_extra,
    playground_projection_extra,
    playground_today_context,
)
from constitution_memorizer.playground.source_review import detect_source_changes
from constitution_memorizer.playground.stage_timer import time_playground_stage
from constitution_memorizer.playground.view import build_home_view
from constitution_memorizer.entitlements.service import EntitlementService
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.web import bare_acts
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.request_context import (
    PLAYGROUND_ACCESS_RESULTS,
    PLAYGROUND_DEVICE_RESULTS,
    PLAYGROUND_LAW_STATES,
    PLAYGROUND_ROSTER_RESULTS,
    PLAYGROUND_SUBSCRIPTION_DISPOSITIONS,
    REQUEST_COUNTERS,
    REQUEST_NOTES,
    TIMING_STAGES,
    RequestPerformanceSnapshot,
    begin_request_timings,
    breakdown_includes_raw_path,
    capture_request_performance,
    clear_last_request_performance,
    format_request_breakdown_line,
    get_last_request_performance,
    normalize_request_path_group,
    perf_log_sample_rate,
    record_request_counter,
    record_request_note,
    record_request_timing,
    reset_request_timings,
    should_emit_request_breakdown_log,
    snapshot_request_counters,
    snapshot_request_notes,
    snapshot_request_timings,
)


class CountingProgressRepo:
    """Wraps a real SQLite repo and counts get_progress / list_all_progress."""

    def __init__(self, inner: ProgressRepository) -> None:
        self.inner = inner
        self.get_progress_calls = 0
        self.list_all_progress_calls = 0
        self.list_due_calls = 0
        self.count_by_status_calls = 0
        self.get_profile_calls = 0
        self.list_split_preferences_calls = 0
        self.get_split_preference_calls = 0
        self.load_request_bootstrap_calls = 0

    def __getattr__(self, name: str):
        return getattr(self.inner, name)

    def get_progress(self, user_id, unit_id: str):
        self.get_progress_calls += 1
        return self.inner.get_progress(user_id, unit_id)

    def list_all_progress(self, user_id):
        self.list_all_progress_calls += 1
        return self.inner.list_all_progress(user_id)

    def list_due(self, user_id, as_of, *, include_new: bool = False):
        self.list_due_calls += 1
        return self.inner.list_due(user_id, as_of, include_new=include_new)

    def count_by_status(self, user_id):
        self.count_by_status_calls += 1
        return self.inner.count_by_status(user_id)

    def get_profile(self, user_id):
        self.get_profile_calls += 1
        return self.inner.get_profile(user_id)

    def list_split_preferences(self, user_id):
        self.list_split_preferences_calls += 1
        return self.inner.list_split_preferences(user_id)

    def get_split_preference(self, user_id, parent_clause_id: str):
        self.get_split_preference_calls += 1
        return self.inner.get_split_preference(user_id, parent_clause_id)

    def load_request_bootstrap(self, user_id, **kwargs):
        self.load_request_bootstrap_calls += 1
        return self.inner.load_request_bootstrap(user_id, **kwargs)

    def reset_counts(self) -> None:
        self.get_progress_calls = 0
        self.list_all_progress_calls = 0
        self.list_due_calls = 0
        self.count_by_status_calls = 0
        self.get_profile_calls = 0
        self.list_split_preferences_calls = 0
        self.get_split_preference_calls = 0
        self.load_request_bootstrap_calls = 0

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")
USER_EMAIL = "a@example.com"


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture(autouse=True)
def _clear_performance_snapshot():
    clear_last_request_performance()
    yield
    clear_last_request_performance()


def _settings(**overrides) -> MultiUserSettings:
    base = {
        "APP_ENV": "test",
        "MULTIUSER_ENABLED": "true",
        "AUTH_GOOGLE_ENABLED": "true",
        "AUTH_PHONE_ENABLED": "true",
        "SESSION_SECRET": "test-secret",
        "SUPABASE_URL": "http://example.invalid",
        "SUPABASE_ANON_KEY": "anon",
        "DATABASE_URL": "",
        "COOKIE_SECURE": "false",
    }
    base.update({k: str(v) for k, v in overrides.items()})
    return MultiUserSettings(_env_file=None, **base)


def test_record_timing_noops_outside_request():
    started = perf_counter()
    record_request_timing("profile", started)
    assert snapshot_request_timings() == {}


def test_roadmap_sync_stage_is_whitelisted():
    token = begin_request_timings()
    try:
        record_request_timing("roadmap_sync", perf_counter() - 0.01)
        total_ms, count = snapshot_request_timings()["roadmap_sync"]
        assert count == 1
        assert total_ms > 0
    finally:
        reset_request_timings(token)


def test_unknown_stage_is_rejected():
    with pytest.raises(ValueError, match="Unknown request timing stage"):
        record_request_timing("not_a_stage", perf_counter())
    token = begin_request_timings()
    try:
        with pytest.raises(ValueError, match="Unknown request timing stage"):
            record_request_timing("sql", perf_counter())
        assert snapshot_request_timings() == {}
    finally:
        reset_request_timings(token)


def test_unknown_counter_is_rejected():
    with pytest.raises(ValueError, match="Unknown request counter"):
        record_request_counter("not_a_counter")
    token = begin_request_timings()
    try:
        with pytest.raises(ValueError, match="Unknown request counter"):
            record_request_counter("sql")
        assert snapshot_request_counters() == {}
    finally:
        reset_request_timings(token)


def test_unknown_note_is_rejected():
    with pytest.raises(ValueError, match="Unknown request note"):
        record_request_note("not_a_note", "x")
    token = begin_request_timings()
    try:
        with pytest.raises(ValueError, match="Unknown request note"):
            record_request_note("sql", "x")
        assert snapshot_request_notes() == {}
    finally:
        reset_request_timings(token)


_PLAYGROUND_STAGES = (
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
_PLAYGROUND_COUNTERS = (
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
_PLAYGROUND_NOTES = (
    "playground_access_result",
    "playground_subscription_disposition",
    "playground_device_result",
    "playground_roster_result",
    "playground_law_state",
)


def test_playground_vocabulary_is_accepted_when_collector_bound():
    record_request_timing("playground_entitlement", perf_counter())
    record_request_counter("playground_repo_round_trips")
    record_request_note("playground_access_result", "allowed")
    assert snapshot_request_timings() == {}
    assert snapshot_request_counters() == {}
    assert snapshot_request_notes() == {}
    token = begin_request_timings()
    try:
        record_request_timing("playground_entitlement", perf_counter() - 0.01)
        record_request_counter("playground_repo_round_trips", 2)
        record_request_note("playground_access_result", "allowed")
        total_ms, count = snapshot_request_timings()["playground_entitlement"]
        assert count == 1
        assert total_ms > 0
        assert snapshot_request_counters()["playground_repo_round_trips"] == 2
        assert snapshot_request_notes()["playground_access_result"] == "allowed"
    finally:
        reset_request_timings(token)
    assert snapshot_request_timings() == {}
    assert snapshot_request_counters() == {}
    assert snapshot_request_notes() == {}


def test_playground_note_values_are_not_validated():
    token = begin_request_timings()
    try:
        record_request_note("playground_access_result", "not_a_closed_value")
        assert snapshot_request_notes()["playground_access_result"] == "not_a_closed_value"
    finally:
        reset_request_timings(token)


def test_playground_whitelist_membership():
    assert TIMING_STAGES[-len(_PLAYGROUND_STAGES) :] == _PLAYGROUND_STAGES
    assert TIMING_STAGES[TIMING_STAGES.index("playground_entitlement") - 1] == "roadmap_sync"
    assert REQUEST_COUNTERS[-len(_PLAYGROUND_COUNTERS) :] == _PLAYGROUND_COUNTERS
    assert REQUEST_COUNTERS[REQUEST_COUNTERS.index("playground_db_reads") - 1] == (
        "bare_act_cache_misses"
    )
    assert REQUEST_NOTES[-len(_PLAYGROUND_NOTES) :] == _PLAYGROUND_NOTES
    assert "template" in TIMING_STAGES
    assert "bare_act_load" in TIMING_STAGES
    assert "bare_act_cache_misses" in REQUEST_COUNTERS
    assert "bare_act_hydrations" not in REQUEST_COUNTERS
    assert "auth_state" in REQUEST_NOTES
    assert PLAYGROUND_ACCESS_RESULTS == frozenset(
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
    assert PLAYGROUND_SUBSCRIPTION_DISPOSITIONS == frozenset(
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
    assert PLAYGROUND_DEVICE_RESULTS == frozenset(
        {
            "ok",
            "device_limit",
            "device_revoked",
            "device_config_error",
            "replacement_limit",
            "skipped_unpaid",
        }
    )
    assert PLAYGROUND_ROSTER_RESULTS == frozenset(
        {"ok", "roster_full", "roster_missing", "peek", "local_owner"}
    )
    assert PLAYGROUND_LAW_STATES == frozenset(
        {"none", "active", "removed", "historical", "ineligible"}
    )


_PATH_GROUP_CASES = (
    ("/playground", "/playground"),
    ("/playground/", "/playground"),
    ("/playground?notice=added", "/playground"),
    ("/playground/roster", "/playground/roster"),
    ("/playground/roster/next", "/playground/roster/next"),
    ("/playground/roster/ndps/remove", "/playground/roster/{law_id}/remove"),
    ("/playground/roster/bnss/remove", "/playground/roster/{law_id}/remove"),
    ("/playground/laws/ndps", "/playground/laws/{law_id}"),
    ("/playground/laws/bnss", "/playground/laws/{law_id}"),
    ("/playground/laws/custom-act", "/playground/laws/{law_id}"),
    ("/playground/laws/ndps/add", "/playground/laws/{law_id}/add"),
    ("/playground/laws/ndps/sections", "/playground/laws/{law_id}/sections"),
    ("/playground/laws/ndps/mastered", "/playground/laws/{law_id}/mastered"),
    ("/playground/laws/ndps/source-review", "/playground/laws/{law_id}/source-review"),
    (
        "/playground/laws/ndps/source-review/sections/2",
        "/playground/laws/{law_id}/source-review/sections/{number}",
    ),
    (
        "/playground/laws/ndps/source-review/sections/2(1)",
        "/playground/laws/{law_id}/source-review/sections/{number}",
    ),
    (
        "/playground/laws/ndps/source-review/sections/2/reviewed",
        "/playground/laws/{law_id}/source-review/sections/{number}/reviewed",
    ),
    (
        "/playground/laws/ndps/source-review/sections/2/u/subsection:1",
        "/playground/laws/{law_id}/source-review/sections/{number}/u/{unit}",
    ),
    (
        "/playground/laws/ndps/source-review/sections/2/u/subsection:1/reviewed",
        "/playground/laws/{law_id}/source-review/sections/{number}/u/{unit}/reviewed",
    ),
    (
        "/playground/laws/ndps/sections/2/learn/read",
        "/playground/laws/{law_id}/sections/{number}/learn/{mode}",
    ),
    (
        "/playground/laws/ndps/sections/2/learn/cloze",
        "/playground/laws/{law_id}/sections/{number}/learn/{mode}",
    ),
    (
        "/playground/laws/ndps/sections/2/u/clause:a/learn/test",
        "/playground/laws/{law_id}/sections/{number}/u/{unit}/learn/{mode}",
    ),
    (
        "/playground/laws/ndps/sections/2/learn/read/start",
        "/playground/laws/{law_id}/sections/{number}/learn/{mode}/start",
    ),
    (
        "/playground/laws/ndps/sections/2/learn/read/complete",
        "/playground/laws/{law_id}/sections/{number}/learn/{mode}/complete",
    ),
    (
        "/playground/laws/ndps/sections/2/learn/read/speech",
        "/playground/laws/{law_id}/sections/{number}/learn/{mode}/speech",
    ),
    (
        "/playground/laws/ndps/sections/2/learn/test/quiz",
        "/playground/laws/{law_id}/sections/{number}/learn/{mode}/quiz",
    ),
    (
        "/playground/laws/ndps/sections/2/learned",
        "/playground/laws/{law_id}/sections/{number}/learned",
    ),
    (
        "/playground/laws/ndps/sections/2/mastered",
        "/playground/laws/{law_id}/sections/{number}/mastered",
    ),
    ("/playground/laws/ndps?notice=added#top", "/playground/laws/{law_id}"),
    ("/playground/future-route/opaque-user-value", "/playground/{other}"),
    ("/playground/laws/ndps/not-a-real-action", "/playground/laws/{law_id}/{other}"),
    ("/playground/roster/surprise", "/playground/roster/{other}"),
    ("/dashboard", "/dashboard"),
    ("/dashboard?done=clause-1", "/dashboard"),
    ("/calendar", "/calendar"),
    ("/sitemap.xml", "/sitemap.xml"),
    ("/sitemap-core.xml", "/sitemap-core.xml"),
    ("/sitemap-laws.xml", "/sitemap-laws.xml"),
    ("/sitemap-laws-bnss.xml", "/sitemap-laws-{slug}.xml"),
    ("/sitemap-laws-ndps-2.xml", "/sitemap-laws-{slug}-{chunk}.xml"),
    (
        "/admin/users/11111111-1111-4111-8111-111111111111",
        "/admin/users/{user_id}",
    ),
    (
        "/admin/users/11111111-1111-4111-8111-111111111111/grants",
        "/admin/users/{user_id}/grants",
    ),
    ("/browse/article/20", "/browse/article/20"),
    ("/learn/clause-1", "/learn/clause-1"),
    ("/laws/bns", "/laws/bns"),
    ("/health", "/health"),
)


@pytest.mark.parametrize("raw, expected", _PATH_GROUP_CASES)
def test_normalize_request_path_group(raw: str, expected: str):
    assert normalize_request_path_group(raw) == expected


def test_normalize_request_path_group_unknown_playground_is_bounded():
    grouped = normalize_request_path_group("/playground/future-route/opaque-user-value")
    assert grouped == "/playground/{other}"
    assert "opaque-user-value" not in grouped
    assert "future-route" not in grouped


def test_normalize_request_path_group_is_idempotent():
    samples = (
        "/playground/laws/ndps/sections/2/learn/read/start",
        "/playground/future-route/opaque-user-value",
        "/sitemap-laws-ndps-2.xml",
        "/admin/users/11111111-1111-4111-8111-111111111111",
        "/learn/clause-1",
        "/dashboard?done=clause-1",
    )
    for raw in samples:
        once = normalize_request_path_group(raw)
        assert normalize_request_path_group(once) == once


def test_normalize_request_path_group_does_not_leak_identifiers():
    samples = (
        "/playground/laws/ndps/sections/2(1)/learn/read",
        "/playground/laws/bnss/source-review/sections/2/u/subsection:1",
        "/playground/future-route/opaque-user-value",
        "/playground/laws/ndps?notice=added",
        "/admin/users/11111111-1111-4111-8111-111111111111",
        "/sitemap-laws-bnss.xml",
    )
    joined = "\n".join(normalize_request_path_group(raw) for raw in samples)
    assert "ndps" not in joined
    assert "bnss" not in joined
    assert "2(1)" not in joined
    assert "read" not in joined
    assert "subsection:1" not in joined
    assert "opaque-user-value" not in joined
    assert "11111111-1111-4111-8111-111111111111" not in joined
    assert "notice=added" not in joined
    assert "?" not in joined


def test_repeated_stages_accumulate_duration_and_count():
    token = begin_request_timings()
    try:
        record_request_timing("theme", perf_counter() - 0.01)
        record_request_timing("theme", perf_counter() - 0.02)
        snapshot = snapshot_request_timings()
        total_ms, count = snapshot["theme"]
        assert count == 2
        assert total_ms > 0
    finally:
        reset_request_timings(token)


def test_snapshot_is_independent_copy():
    token = begin_request_timings()
    try:
        record_request_timing("profile", perf_counter() - 0.01)
        snapshot = snapshot_request_timings()
        record_request_timing("profile", perf_counter() - 0.01)
        live = snapshot_request_timings()
        assert snapshot["profile"][1] == 1
        assert live["profile"][1] == 2
        snapshot["profile"] = (0.0, 99)
        assert snapshot_request_timings()["profile"][1] == 2
    finally:
        reset_request_timings(token)
    after_reset = snapshot_request_timings()
    assert after_reset == {}
    assert snapshot["profile"] == (0.0, 99)


def _counting_app(tmp_path: Path) -> tuple[object, CountingProgressRepo]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = open_progress_db(tmp_path / "progress.db")
    repo = CountingProgressRepo(ProgressRepository(conn))
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=USER,
        email=USER_EMAIL,
        display_name="Test User",
    )
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        progress_repo=repo,
    )
    return app, repo


def _counting_client(tmp_path: Path) -> tuple[TestClient, CountingProgressRepo]:
    app, repo = _counting_app(tmp_path)
    client = TestClient(app)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    cb = client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    assert cb.status_code == 303
    repo.reset_counts()
    return client, repo


async def _async_authed_session(
    tmp_path: Path,
) -> tuple[AsyncClient, object, CountingProgressRepo]:
    """Same-task ASGI client so ContextVar snapshots are visible after the request."""
    app, repo = _counting_app(tmp_path)
    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        follow_redirects=False,
    )
    start = await client.get("/auth/google/start")
    state = start.cookies.get("rtc_oauth_state")
    cb = await client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
    )
    assert cb.status_code == 303
    repo.reset_counts()
    return client, app, repo


async def _async_authed_client(tmp_path: Path) -> tuple[AsyncClient, CountingProgressRepo]:
    client, _app, repo = await _async_authed_session(tmp_path)
    return client, repo


async def _async_guest_client(tmp_path: Path) -> tuple[AsyncClient, object]:
    app, _repo = _counting_app(tmp_path)
    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        follow_redirects=False,
    )
    return client, app


def _billing_window() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    return now - timedelta(days=1), now + timedelta(days=30)


def _seed_subscription(app, *, tier: str, status: str, user_id=USER):
    start, end = _billing_window()
    return app.state.subscriptions.create_subscription_record(
        user_id,
        tier=tier,
        status=status,
        billing_period_start=start,
        billing_period_end=end,
        is_current=True,
    )


def _seed_period_ended_refund(app, *, user_id=USER):
    start, end = _billing_window()
    sub = app.state.subscriptions.create_subscription_record(
        user_id,
        tier="plus",
        status="active",
        billing_period_start=start,
        billing_period_end=end,
        is_current=True,
    )
    charge = app.state.subscription_charges.upsert_charge(
        provider_payment_id="pay_refund_t3",
        user_subscription_id=sub.id,
        billing_period_start=start,
        billing_period_end=end,
        refund_status="full",
    )
    assert charge.access_effect == "period_ended"
    return sub


class CountingSubscriptions:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.calls = 0

    def get_current_subscription(self, user_id):
        self.calls += 1
        return self.inner.get_current_subscription(user_id)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def _spy_subscriptions(app) -> CountingSubscriptions:
    counting = CountingSubscriptions(app.state.subscriptions)
    app.state.subscriptions = counting
    app.state.entitlement_service._subscriptions = counting
    return counting


def _hydrate_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    hydrated: list[str] = []
    real = bare_acts._load_cached

    def wrapped(slug: str, identity: str):
        hydrated.append(slug)
        return real(slug, identity)

    wrapped.cache_clear = real.cache_clear  # type: ignore[attr-defined]
    monkeypatch.setattr(bare_acts, "_load_cached", wrapped)
    return hydrated


def _commercial_snap(**overrides) -> EntitlementSnapshot:
    fields = {
        "is_authenticated": True,
        "subscription_status": None,
        "tier": None,
        "is_subscribed": False,
        "admin_override": False,
        "can_use_constitution_learn": True,
        "constitution_access": CONSTITUTION_ACCESS_FULL,
        "can_read_laws": True,
        "can_open_playground": False,
        "can_consume_new_playground_law": False,
        "playground_law_limit": None,
        "playground_block_reason": BLOCK_NOT_SUBSCRIBED,
        "billing_period_start": None,
        "billing_period_end": None,
        "legacy_status": None,
    }
    fields.update(overrides)
    return EntitlementSnapshot(**fields)


def _fake_entitlement_request(
    *,
    resolver,
    current_user=None,
    multiuser_enabled=False,
    device_service=None,
):
    state = SimpleNamespace(current_user=current_user, auth_session=None)
    app_state = SimpleNamespace(
        entitlement_service=resolver,
        multiuser_enabled=multiuser_enabled,
        device_service=device_service,
    )
    return SimpleNamespace(
        state=state,
        app=SimpleNamespace(state=app_state),
        cookies={},
        headers={},
    )


def _canned_device_access(*, block_reason=None, current_device_id=None) -> DeviceAccess:
    return DeviceAccess(
        device_limit=2,
        registered_device_count=2 if block_reason == BLOCK_DEVICE_LIMIT else 0,
        current_device_id=current_device_id,
        current_device_registered=False,
        current_device_allowed=block_reason is None,
        current_device_revoked=block_reason == BLOCK_DEVICE_REVOKED,
        device_slots_remaining=0 if block_reason == BLOCK_DEVICE_LIMIT else 2,
        block_reason=block_reason,
    )


class _DeviceCallCounter:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.inspect_calls = 0
        self.ensure_calls = 0

    def inspect_current_device(self, *args, **kwargs):
        self.inspect_calls += 1
        return self.inner.inspect_current_device(*args, **kwargs)

    def ensure_current_device(self, *args, **kwargs):
        self.ensure_calls += 1
        return self.inner.ensure_current_device(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def _spy_device_service(app) -> _DeviceCallCounter:
    counting = _DeviceCallCounter(app.state.device_service)
    app.state.device_service = counting
    return counting


def _seed_other_devices(app, n: int = 2, *, user_id=USER) -> None:
    service = app.state.device_service
    inner = getattr(service, "inner", service)
    for index in range(n):
        access = inner.ensure_current_device(
            user_id,
            mint_installation_token(),
            auth_session_id=f"seed-sess-{index}",
            commercially_eligible=True,
        )
        assert access.current_device_registered is True


def _seed_admin(repo) -> None:
    conn = repo.conn
    conn.execute(
        "INSERT INTO user_roles (user_id, role, created_at) VALUES (?, 'admin', ?)",
        (str(USER), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def _plus_open_snap() -> EntitlementSnapshot:
    return _commercial_snap(
        subscription_status="active",
        tier="plus",
        is_subscribed=True,
        can_open_playground=True,
        can_consume_new_playground_law=True,
        playground_block_reason=None,
        playground_law_limit=10,
    )


def _plus_open_access(*, local_owner: bool = False) -> PlaygroundAccess:
    return PlaygroundAccess(
        user_id=USER,
        snapshot=_plus_open_snap(),
        can_open=True,
        can_consume_new_law=True,
        local_owner=local_owner,
        can_view_home=True,
    )


def _capacity(*, remaining: int | None = 10, used: int = 0):
    return SimpleNamespace(
        period_start=date(2026, 10, 1),
        period_end=date(2026, 11, 1),
        used=used,
        remaining=remaining,
        law_limit=10 if remaining is not None else None,
    )


def _fill_plus_roster(app, monkeypatch: pytest.MonkeyPatch, n: int = 10) -> None:
    from constitution_memorizer.playground.roster import service as roster_service

    real = roster_service.is_playground_eligible_law

    def wrapped(law_id: str) -> bool:
        if str(law_id).startswith("slot-"):
            return True
        return real(law_id)

    monkeypatch.setattr(roster_service, "is_playground_eligible_law", wrapped)
    snap = app.state.entitlement_service.resolve(USER)
    roster = app.state.roster
    for index in range(n):
        result = roster.confirm_add_law(
            USER, f"slot-{index}", snap, can_consume_new_law=True
        )
        assert result.ok, result.status


def _assert_t3_entitlement(
    snap,
    *,
    access: str,
    disposition: str | None = None,
    auth_state: str,
    device_result: str,
    device_lookups: int = 0,
    roster_result: str | None = None,
    roster_access_n: int = 0,
    law_state: str | None = None,
) -> None:
    assert snap is not None
    assert "playground_entitlement" in snap.timings
    assert snap.timings["playground_entitlement"][1] == 1
    assert snap.counters["playground_entitlement_resolves"] == 1
    assert snap.notes["playground_access_result"] == access
    if disposition is None:
        assert "playground_subscription_disposition" not in snap.notes
    else:
        assert snap.notes["playground_subscription_disposition"] == disposition
    assert snap.notes["auth_state"] == auth_state
    assert snap.notes["playground_device_result"] == device_result
    if device_lookups:
        assert snap.counters["playground_device_lookups"] == device_lookups
        assert snap.timings["playground_device"][1] == device_lookups
    else:
        assert "playground_device" not in snap.timings
        assert "playground_device_lookups" not in snap.counters
    if roster_access_n:
        assert snap.timings["playground_roster_access"][1] == roster_access_n
    else:
        assert "playground_roster_access" not in snap.timings
    if roster_result is None:
        assert "playground_roster_result" not in snap.notes
    else:
        assert snap.notes["playground_roster_result"] == roster_result
        assert roster_result != "peek"
    if law_state is None:
        assert "playground_law_state" not in snap.notes
    else:
        assert snap.notes["playground_law_state"] == law_state
        assert law_state != "none"


_T6_COUNTERS = (
    "playground_db_reads",
    "playground_db_writes",
    "playground_repo_round_trips",
    "playground_summary_reads",
    "playground_roster_reads",
    "playground_progress_reads",
    "playground_source_review_reads",
    "playground_revision_reads",
)


def _assert_t6_absent(counters: dict) -> None:
    for name in _T6_COUNTERS:
        assert name not in counters


def _assert_t6_counts(
    counters: dict,
    *,
    db_reads: int = 0,
    db_writes: int = 0,
    roster_reads: int = 0,
    summary_reads: int = 0,
    progress_reads: int = 0,
    revision_reads: int = 0,
    source_review_reads: int = 0,
) -> None:
    expected = {
        "playground_db_reads": db_reads,
        "playground_db_writes": db_writes,
        "playground_repo_round_trips": db_reads + db_writes,
        "playground_roster_reads": roster_reads,
        "playground_summary_reads": summary_reads,
        "playground_progress_reads": progress_reads,
        "playground_revision_reads": revision_reads,
        "playground_source_review_reads": source_review_reads,
    }
    reads = counters.get("playground_db_reads", 0)
    writes = counters.get("playground_db_writes", 0)
    round_trips = counters.get("playground_repo_round_trips", 0)
    assert round_trips == reads + writes
    for name, value in expected.items():
        if value:
            assert counters.get(name) == value, (name, value, dict(counters))
        else:
            assert name not in counters, (name, dict(counters))
    extra = set(counters) & set(_T6_COUNTERS) - set(expected)
    assert not extra, extra


def _t6_sqlite(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(tmp_path / "t6.db")
    conn.row_factory = sqlite3.Row
    ensure_overlay_sqlite_schema(conn)
    ensure_roster_sqlite_schema(conn)
    overlay = SqlitePlaygroundRepository(conn)
    roster_repo = SqliteRosterRepository(conn)
    return overlay, roster_repo, RosterService(roster_repo), conn


_SRC_PLAYGROUND = (
    Path(__file__).resolve().parents[1] / "src/constitution_memorizer/playground"
)


def _count_decorator_spec(node: ast.AST) -> tuple[str, str | None] | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    name = None
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    if name != "count_playground_repo_call":
        return None
    kwargs: dict[str, str | None] = {}
    for kw in node.keywords:
        if kw.arg in {"kind", "domain"}:
            kwargs[kw.arg] = ast.literal_eval(kw.value)
    assert "kind" in kwargs, ast.dump(node)
    return kwargs["kind"], kwargs.get("domain")


def _class_def(path: Path, class_name: str) -> ast.ClassDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise AssertionError(f"{class_name} not found in {path}")


def _public_method_counter_map(
    path: Path, class_name: str
) -> dict[str, tuple[str, str | None]]:
    class_node = _class_def(path, class_name)
    mapping: dict[str, tuple[str, str | None]] = {}
    decorated_private: list[str] = []
    for item in class_node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        spec = None
        for dec in item.decorator_list:
            parsed = _count_decorator_spec(dec)
            if parsed is not None:
                spec = parsed
                break
        if spec is None:
            continue
        if item.name.startswith("_"):
            decorated_private.append(item.name)
        mapping[item.name] = spec
    assert not decorated_private, decorated_private
    return mapping


def _assert_postgres_counter_map_matches_sqlite(
    sqlite_path: Path,
    sqlite_class: str,
    postgres_path: Path,
    postgres_class: str,
) -> dict[str, tuple[str, str | None]]:
    sqlite_map = _public_method_counter_map(sqlite_path, sqlite_class)
    postgres_map = _public_method_counter_map(postgres_path, postgres_class)
    missing = set(sqlite_map) - set(postgres_map)
    extra = set(postgres_map) - set(sqlite_map)
    assert not missing, missing
    assert not extra, extra
    mismatched = {
        name: (sqlite_map[name], postgres_map[name])
        for name in sqlite_map
        if sqlite_map[name] != postgres_map[name]
    }
    assert not mismatched, mismatched
    pg_class = _class_def(postgres_path, postgres_class)
    pg_public = {
        item.name
        for item in pg_class.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not item.name.startswith("_")
        and item.name != "__init__"
    }
    missing_decorator = (set(sqlite_map) & pg_public) - set(postgres_map)
    assert not missing_decorator, missing_decorator
    return postgres_map


class _T7FakeCursor:
    """Local fake cursor. Programmed fetchone values in call order; no SQL parse."""

    def __init__(self, fetchone_queue: list | None = None) -> None:
        self.execute_sql: list[str] = []
        self._fetchone_queue = list(fetchone_queue or [])

    def execute(self, sql, params=None):
        self.execute_sql.append(sql)

    def executemany(self, sql, seq_of_params):
        return None

    def fetchall(self):
        return []

    def fetchone(self):
        if self._fetchone_queue:
            return self._fetchone_queue.pop(0)
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _T7FakeConn:
    def __init__(self, cursor: _T7FakeCursor) -> None:
        self.cursor_obj = cursor
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, row_factory=None):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _T7FakePool:
    def __init__(self, fetchone_queue: list | None = None) -> None:
        self.cursor = _T7FakeCursor(fetchone_queue=fetchone_queue)
        self.conn = _T7FakeConn(self.cursor)

    @contextmanager
    def connection(self):
        yield self.conn


class _T7RaisingPool:
    @contextmanager
    def connection(self):
        raise RuntimeError("t7-spy-closed")
        yield  # pragma: no cover


def _t7_period_row() -> dict:
    start, end = playground_month_bounds()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return {
        "id": "period-1",
        "user_id": str(USER),
        "period_start": start,
        "period_end": end,
        "tier_snapshot": "plus",
        "law_limit": 10,
        "status": "active",
        "confirmed_at": now,
        "created_at": now,
        "updated_at": now,
    }


def _t7_repos(fetchone_queue: list | None = None):
    pool = _T7FakePool(fetchone_queue=fetchone_queue)
    overlay = PostgresPlaygroundRepository(pool)
    roster_repo = PostgresRosterRepository(pool)
    return overlay, roster_repo, RosterService(roster_repo), pool


def _breakdown_messages(caplog: logging.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("request_breakdown ")
    ]


def test_authenticated_dashboard_keeps_one_profile_and_progress(tmp_path: Path):
    client, repo = _counting_client(tmp_path)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert repo.load_request_bootstrap_calls == 1
    assert repo.get_profile_calls == 0
    assert repo.list_all_progress_calls == 0
    assert repo.list_due_calls == 0
    assert repo.count_by_status_calls == 0


def test_authenticated_browse_keeps_one_progress_list(tmp_path: Path):
    client, repo = _counting_client(tmp_path)
    resp = client.get("/browse")
    assert resp.status_code == 200
    assert repo.load_request_bootstrap_calls == 1
    assert repo.list_all_progress_calls == 0
    assert repo.list_due_calls == 0


def test_authenticated_dashboard_breakdown_includes_auth_session(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    client, _repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.get("/dashboard")
    assert resp.status_code == 200
    messages = _breakdown_messages(caplog)
    assert len(messages) == 1
    line = messages[0]
    assert "path=/dashboard" in line
    assert "auth_session_n=1" in line
    assert "request_bootstrap_n=1" in line
    assert "progress_preload_" not in line
    assert "split_prefs_" not in line
    assert "news_setting_" not in line
    assert "theme_" not in line
    assert "dashboard_build_n=" in line
    assert "dashboard_prep_n=1" in line
    assert "template_n=" in line


def test_health_and_static_emit_no_timing_or_breakdown(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    client, _repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        assert client.get("/health").status_code == 200
        assert client.get("/static/styles.css").status_code == 200
        joined = " ".join(record.getMessage() for record in caplog.records)
    assert "request method=" not in joined
    assert "request_breakdown" not in joined


def test_breakdown_logs_omit_sensitive_data(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    client, _repo = _counting_client(tmp_path)
    session_cookie = client.cookies.get("rtc_session") or ""
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        dash = client.get("/dashboard?done=clause-1")
        browse = client.get("/browse")
    assert dash.status_code == 200
    assert browse.status_code == 200
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "request_breakdown" in joined
    assert "path=/dashboard" in joined
    assert "path=/browse" in joined
    assert "done=clause-1" not in joined
    assert "?" not in joined
    assert str(USER) not in joined
    assert USER_EMAIL not in joined
    assert "DATABASE_URL" not in joined
    assert "postgresql://" not in joined
    if session_cookie:
        assert session_cookie not in joined
    assert "cookie" not in joined.lower()
    assert "token" not in joined.lower()
    assert "phone" not in joined.lower()


def _access_messages(caplog: logging.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("request method=")
    ]


def test_capture_request_performance_shape_and_copies():
    token = begin_request_timings()
    try:
        record_request_timing("playground_entitlement", perf_counter() - 0.01)
        record_request_counter("playground_repo_round_trips", 2)
        record_request_note("auth_state", "authed")
        record_request_note("playground_access_result", "allowed")
        returned = capture_request_performance(
            path="/playground/laws/ndps",
            method="GET",
            status_code=200,
            total_ms=12.5,
        )
        assert returned.path_group == "/playground/laws/{law_id}"
        assert "ndps" not in returned.path_group
        assert returned.method == "GET"
        assert returned.status_code == 200
        assert returned.total_ms == 12.5
        assert returned.counters["playground_repo_round_trips"] == 2
        assert returned.notes["auth_state"] == "authed"
        assert returned.notes["playground_access_result"] == "allowed"
        assert returned.timings["playground_entitlement"][1] == 1

        via_get = get_last_request_performance()
        assert via_get is not None
        assert returned is not via_get
        assert returned.timings is not via_get.timings
        assert returned.counters is not via_get.counters
        assert returned.notes is not via_get.notes

        returned.notes["auth_state"] = "mutated-return"
        returned.timings["playground_entitlement"] = (0.0, 99)
        returned.counters["playground_repo_round_trips"] = 0
        after_return_mutation = get_last_request_performance()
        assert after_return_mutation is not None
        assert after_return_mutation.notes["auth_state"] == "authed"
        assert after_return_mutation.timings["playground_entitlement"][1] == 1
        assert after_return_mutation.counters["playground_repo_round_trips"] == 2

        via_get.notes["auth_state"] = "mutated-get"
        via_get.counters["playground_repo_round_trips"] = 99
        after_get_mutation = get_last_request_performance()
        assert after_get_mutation is not None
        assert after_get_mutation.notes["auth_state"] == "authed"
        assert after_get_mutation.counters["playground_repo_round_trips"] == 2
        assert after_get_mutation is not via_get
        assert after_get_mutation.notes is not via_get.notes
    finally:
        reset_request_timings(token)
        clear_last_request_performance()


def test_get_last_request_performance_default_none():
    assert get_last_request_performance() is None


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, 1.0),
        ("", 1.0),
        ("   ", 1.0),
        ("1", 1.0),
        ("1.0", 1.0),
        ("0", 0.0),
        ("0.0", 0.0),
        ("0.05", 0.05),
        ("abc", 1.0),
        ("true", 1.0),
        ("-1", 1.0),
        ("2", 1.0),
        ("nan", 1.0),
        ("NaN", 1.0),
        ("inf", 1.0),
        ("-inf", 1.0),
    ],
)
def test_perf_log_sample_rate_parse(monkeypatch, raw: str | None, expected: float):
    if raw is None:
        monkeypatch.delenv("PERF_LOG_SAMPLE_RATE", raising=False)
    else:
        monkeypatch.setenv("PERF_LOG_SAMPLE_RATE", raw)
    assert perf_log_sample_rate() == expected


def test_should_emit_request_breakdown_log_edges(monkeypatch):
    monkeypatch.setenv("PERF_LOG_SAMPLE_RATE", "1")
    monkeypatch.setattr(
        "constitution_memorizer.web.request_context.random.random",
        lambda: pytest.fail("rate 1 must bypass RNG"),
    )
    assert should_emit_request_breakdown_log() is True

    monkeypatch.setenv("PERF_LOG_SAMPLE_RATE", "0")
    monkeypatch.setattr(
        "constitution_memorizer.web.request_context.random.random",
        lambda: pytest.fail("rate 0 must bypass RNG"),
    )
    assert should_emit_request_breakdown_log() is False

    monkeypatch.setenv("PERF_LOG_SAMPLE_RATE", "0.5")
    monkeypatch.setattr(
        "constitution_memorizer.web.request_context.random.random",
        lambda: 0.49,
    )
    assert should_emit_request_breakdown_log() is True
    monkeypatch.setattr(
        "constitution_memorizer.web.request_context.random.random",
        lambda: 0.51,
    )
    assert should_emit_request_breakdown_log() is False


def test_format_request_breakdown_line_playground_omits_raw_path():
    snap = RequestPerformanceSnapshot(
        path_group="/playground/laws/{law_id}",
        method="GET",
        status_code=200,
        total_ms=12.5,
        timings={},
        counters={},
        notes={"auth_state": "authed"},
    )
    line = format_request_breakdown_line(snap, raw_path="/playground/laws/ndps")
    assert "path_group=/playground/laws/{law_id}" in line
    assert "total_ms=12.5" in line
    assert "path=/playground/laws/ndps" not in line
    assert "ndps" not in line
    assert "?" not in line
    assert breakdown_includes_raw_path("/playground/laws/ndps") is False


def test_format_request_breakdown_line_constitution_keeps_raw_path():
    snap = RequestPerformanceSnapshot(
        path_group="/dashboard",
        method="GET",
        status_code=200,
        total_ms=8.0,
        timings={},
        counters={},
        notes={"auth_state": "authed"},
    )
    line = format_request_breakdown_line(snap, raw_path="/dashboard")
    assert "path=/dashboard" in line
    assert "path_group=/dashboard" in line
    assert "total_ms=8.0" in line
    assert breakdown_includes_raw_path("/dashboard") is True


def test_format_request_breakdown_line_admin_uuid_omitted():
    uuid = "11111111-1111-4111-8111-111111111111"
    snap = RequestPerformanceSnapshot(
        path_group="/admin/users/{user_id}",
        method="GET",
        status_code=200,
        total_ms=3.0,
        timings={},
        counters={},
        notes={"auth_state": "authed"},
    )
    line = format_request_breakdown_line(snap, raw_path=f"/admin/users/{uuid}")
    assert "path_group=/admin/users/{user_id}" in line
    assert uuid not in line
    assert f"path=/admin/users/{uuid}" not in line
    assert breakdown_includes_raw_path(f"/admin/users/{uuid}") is False


def test_format_request_breakdown_line_sitemap_slug_omitted():
    snap = RequestPerformanceSnapshot(
        path_group="/sitemap-laws-{slug}.xml",
        method="GET",
        status_code=200,
        total_ms=1.0,
        timings={},
        counters={},
        notes={"auth_state": "guest"},
    )
    line = format_request_breakdown_line(snap, raw_path="/sitemap-laws-bnss.xml")
    assert "path_group=/sitemap-laws-{slug}.xml" in line
    assert "bnss" not in line
    assert "path=/sitemap-laws-bnss.xml" not in line
    assert breakdown_includes_raw_path("/sitemap-laws-bnss.xml") is False
    assert breakdown_includes_raw_path("/sitemap-laws.xml") is True


def test_sync_testclient_does_not_expose_snapshot_contextvar(tmp_path: Path):
    client, _repo = _counting_client(tmp_path)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert get_last_request_performance() is None


def test_playground_get_produces_snapshot_with_path_group_and_auth_state(
    tmp_path: Path,
):
    async def _go():
        client, _repo = await _async_authed_client(tmp_path)
        try:
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code in {200, 302, 303}
    assert snap is not None
    assert snap.path_group == "/playground"
    assert snap.method == "GET"
    assert snap.status_code == resp.status_code
    assert snap.total_ms >= 0
    assert snap.notes["auth_state"] == "authed"
    assert snap.notes["auth_state"] != "guest"


def test_playground_breakdown_log_uses_path_group_not_law_id(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    client, _repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.get("/playground/laws/ndps")
    assert resp.status_code in {200, 302, 303, 403, 404}
    messages = _breakdown_messages(caplog)
    assert len(messages) == 1
    line = messages[0]
    assert "path_group=/playground/laws/{law_id}" in line
    assert "path_group=" in line
    assert "total_ms=" in line
    assert "path=/playground/laws/ndps" not in line
    assert "ndps" not in line
    assert "?" not in line


def test_dashboard_snapshot_and_breakdown_keep_path(tmp_path: Path, caplog):
    async def _go():
        client, _repo = await _async_authed_client(tmp_path)
        try:
            with caplog.at_level(logging.INFO, logger="uvicorn.error"):
                caplog.clear()
                resp = await client.get("/dashboard")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    assert snap is not None
    assert snap.path_group == "/dashboard"
    assert snap.total_ms > 0
    assert snap.notes["auth_state"] == "authed"
    messages = _breakdown_messages(caplog)
    assert len(messages) == 1
    line = messages[0]
    assert "path=/dashboard" in line
    assert "path_group=/dashboard" in line
    assert "auth_session_n=1" in line
    assert "total_ms=" in line


def test_sample_rate_zero_collects_snapshot_but_does_not_log_breakdown(
    tmp_path: Path, caplog: logging.LogCaptureFixture, monkeypatch
):
    monkeypatch.setenv("PERF_LOG_SAMPLE_RATE", "0")

    async def _go():
        client, _repo = await _async_authed_client(tmp_path)
        try:
            with caplog.at_level(logging.INFO, logger="uvicorn.error"):
                caplog.clear()
                resp = await client.get("/dashboard")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    assert snap is not None
    assert snap.path_group == "/dashboard"
    assert snap.notes["auth_state"] == "authed"
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "request method=" in joined
    assert "request_breakdown" not in joined


def test_sample_rate_one_logs_breakdown(
    tmp_path: Path, caplog: logging.LogCaptureFixture, monkeypatch
):
    monkeypatch.setenv("PERF_LOG_SAMPLE_RATE", "1")
    client, _repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert len(_breakdown_messages(caplog)) == 1


def test_health_clears_snapshot_and_stays_silent(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    async def _go():
        client, _repo = await _async_authed_client(tmp_path)
        try:
            dash = await client.get("/dashboard")
            after_dash = get_last_request_performance()
            with caplog.at_level(logging.INFO, logger="uvicorn.error"):
                caplog.clear()
                health = await client.get("/health")
            after_health = get_last_request_performance()
            return dash, after_dash, health, after_health
        finally:
            await client.aclose()

    dash, after_dash, health, after_health = asyncio.run(_go())
    assert dash.status_code == 200
    assert after_dash is not None
    assert after_dash.path_group == "/dashboard"
    assert health.status_code == 200
    assert after_health is None
    joined = " ".join(record.getMessage() for record in caplog.records)
    assert "request method=" not in joined
    assert "request_breakdown" not in joined


def test_sitemap_xml_snapshot_without_logs(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    async def _go():
        client, _repo = await _async_authed_client(tmp_path)
        try:
            with caplog.at_level(logging.INFO, logger="uvicorn.error"):
                caplog.clear()
                resp = await client.get("/sitemap.xml")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    assert snap is not None
    assert snap.path_group == "/sitemap.xml"
    assert snap.method == "GET"
    assert snap.total_ms >= 0
    # /sitemap.xml is in ROOT_ASSET_PATHS, so auth skips the session lookup
    # and current_user is unset even when the client already holds a cookie.
    # Ruling 7 (auth_state=authed) applies to playground/dashboard snapshot tests.
    assert snap.notes["auth_state"] == "guest"
    joined = " ".join(record.getMessage() for record in caplog.records)
    assert "request method=" not in joined
    assert "request_breakdown" not in joined


def test_snapshot_and_breakdown_omit_query_and_user_id(tmp_path: Path, caplog):
    async def _go():
        client, _repo = await _async_authed_client(tmp_path)
        try:
            with caplog.at_level(logging.INFO, logger="uvicorn.error"):
                caplog.clear()
                dash = await client.get("/dashboard?done=clause-1")
                dash_snap = get_last_request_performance()
                play = await client.get("/playground?notice=added")
                play_snap = get_last_request_performance()
            return dash, dash_snap, play, play_snap
        finally:
            await client.aclose()

    dash, dash_snap, play, play_snap = asyncio.run(_go())
    assert dash.status_code == 200
    assert play.status_code in {200, 302, 303}
    assert dash_snap is not None
    assert play_snap is not None
    assert dash_snap.path_group == "/dashboard"
    assert play_snap.path_group == "/playground"
    assert "?" not in dash_snap.path_group
    assert "?" not in play_snap.path_group
    assert "done" not in dash_snap.path_group
    assert "notice" not in play_snap.path_group
    assert str(USER) not in dash_snap.path_group
    assert str(USER) not in play_snap.notes.values()
    breakdown = "\n".join(_breakdown_messages(caplog))
    assert "done=clause-1" not in breakdown
    assert "notice=added" not in breakdown
    assert "?" not in breakdown
    assert str(USER) not in breakdown
    assert USER_EMAIL not in breakdown


def test_response_has_no_performance_payload_or_headers(tmp_path: Path):
    client, _repo = _counting_client(tmp_path)
    for path in ("/dashboard", "/playground"):
        resp = client.get(path)
        names = {key.lower() for key in resp.headers}
        assert "server-timing" not in names
        assert not any(name.startswith("x-perf") for name in names)
        body = resp.text
        assert "RequestPerformanceSnapshot" not in body
        assert "path_group=" not in body


def test_one_middleware_total_ms_reused_on_snapshot_and_logs(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    async def _go():
        client, _repo = await _async_authed_client(tmp_path)
        try:
            with caplog.at_level(logging.INFO, logger="uvicorn.error"):
                caplog.clear()
                resp = await client.get("/dashboard")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    assert snap is not None
    access = _access_messages(caplog)
    breakdown = _breakdown_messages(caplog)
    assert len(access) == 1
    assert len(breakdown) == 1
    access_total = [
        part.split("=", 1)[1]
        for part in access[0].split()
        if part.startswith("duration_ms=")
    ][0]
    breakdown_total = [
        part.split("=", 1)[1]
        for part in breakdown[0].split()
        if part.startswith("total_ms=")
    ][0]
    assert access_total == breakdown_total
    assert f"{snap.total_ms:.1f}" == access_total


@pytest.mark.parametrize(
    "snapshot, access, disposition",
    [
        (EntitlementService().resolve(None), "guest", None),
        (
            _commercial_snap(
                playground_block_reason=BLOCK_NOT_SUBSCRIBED,
                subscription_status=None,
            ),
            "free",
            None,
        ),
        (
            _commercial_snap(
                subscription_status="pending",
                tier="plus",
                is_subscribed=True,
                can_open_playground=True,
                can_consume_new_playground_law=False,
                playground_block_reason=None,
                playground_law_limit=10,
            ),
            "pending",
            "pending",
        ),
        (
            _commercial_snap(
                subscription_status="paused",
                tier="pro",
                playground_block_reason=BLOCK_SUBSCRIPTION_PAUSED,
            ),
            "paused",
            "paused",
        ),
        (
            _commercial_snap(
                subscription_status="halted",
                tier="max",
                playground_block_reason=BLOCK_PAYMENT_HALTED,
            ),
            "halted",
            "halted",
        ),
        (
            _commercial_snap(
                subscription_status="active",
                tier="plus",
                playground_block_reason=BLOCK_PAID_PERIOD_ENDED,
            ),
            "paid_period_ended",
            "active",
        ),
        (
            _commercial_snap(
                subscription_status="halted",
                tier="max",
                playground_block_reason=BLOCK_PAID_PERIOD_ENDED,
            ),
            "paid_period_ended",
            "halted",
        ),
        (
            _commercial_snap(
                subscription_status="active",
                tier="plus",
                is_subscribed=True,
                can_open_playground=True,
                can_consume_new_playground_law=True,
                playground_block_reason=None,
                playground_law_limit=10,
            ),
            "allowed",
            "active",
        ),
        (
            _commercial_snap(
                admin_override=True,
                can_open_playground=True,
                can_consume_new_playground_law=True,
                playground_block_reason=None,
                subscription_status=None,
            ),
            "allowed",
            None,
        ),
    ],
)
def test_commercial_playground_notes_mapping(snapshot, access, disposition):
    got_access, got_disposition = commercial_playground_notes(snapshot)
    assert got_access == access
    assert got_disposition == disposition
    assert got_access in PLAYGROUND_ACCESS_RESULTS
    if got_disposition is not None:
        assert got_disposition in PLAYGROUND_SUBSCRIPTION_DISPOSITIONS
    blob = f"{got_access} {got_disposition}"
    assert str(USER) not in blob
    assert USER_EMAIL not in blob
    assert "ndps" not in blob
    assert snapshot.tier is None or snapshot.tier not in (got_access, got_disposition or "")


def test_get_entitlement_snapshot_memo_does_not_double_resolve():
    class Spy:
        def __init__(self, inner) -> None:
            self.inner = inner
            self.calls = 0

        def resolve_for_request(self, request, *, now=None):
            self.calls += 1
            return self.inner.resolve_for_request(request, now=now)

    spy = Spy(EntitlementService())
    request = _fake_entitlement_request(resolver=spy, current_user=None)
    token = begin_request_timings()
    try:
        first = get_entitlement_snapshot(request)
        record_request_note("playground_access_result", "mutated")
        second = get_entitlement_snapshot(request)
        assert first is second
        assert spy.calls == 1
        assert snapshot_request_counters()["playground_entitlement_resolves"] == 1
        assert snapshot_request_timings()["playground_entitlement"][1] == 1
        assert snapshot_request_notes()["playground_access_result"] == "mutated"
    finally:
        reset_request_timings(token)


def test_entitlement_records_noop_without_collector():
    request = _fake_entitlement_request(
        resolver=EntitlementService(), current_user=None
    )
    snap = get_entitlement_snapshot(request)
    assert snap.is_authenticated is False
    assert snapshot_request_timings() == {}
    assert snapshot_request_counters() == {}


def test_raising_resolver_counts_attempt_without_fabricated_note():
    class Boom:
        def resolve_for_request(self, request, *, now=None):
            raise RuntimeError("resolve boom")

    request = _fake_entitlement_request(resolver=Boom(), current_user=None)
    token = begin_request_timings()
    try:
        with pytest.raises(RuntimeError, match="resolve boom"):
            get_entitlement_snapshot(request)
        assert snapshot_request_counters()["playground_entitlement_resolves"] == 1
        assert snapshot_request_timings()["playground_entitlement"][1] == 1
        notes = snapshot_request_notes()
        assert "playground_access_result" not in notes
        assert "playground_subscription_disposition" not in notes
        assert not hasattr(request.state, "entitlement_snapshot")
    finally:
        reset_request_timings(token)


def test_direct_entitlement_service_resolve_is_not_instrumented():
    token = begin_request_timings()
    try:
        snap = EntitlementService().resolve(None)
        assert snap.playground_block_reason == BLOCK_SIGN_IN_REQUIRED
        assert snapshot_request_counters() == {}
        assert snapshot_request_timings() == {}
        assert snapshot_request_notes() == {}
    finally:
        reset_request_timings(token)


def test_guest_playground_snapshot_access_result_guest(tmp_path: Path):
    async def _go():
        client, _app = await _async_guest_client(tmp_path)
        try:
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    assert snap is not None
    assert snap.path_group == "/playground"
    _assert_t3_entitlement(
        snap,
        access="guest",
        auth_state="guest",
        device_result="skipped_unpaid",
        device_lookups=0,
    )


def test_free_authed_playground_snapshot_access_result_free(tmp_path: Path):
    async def _go():
        client, _repo = await _async_authed_client(tmp_path)
        try:
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    assert snap is not None
    assert snap.path_group == "/playground"
    _assert_t3_entitlement(
        snap,
        access="free",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )
    assert snap.notes["auth_state"] != "guest"


def test_pending_playground_snapshot_access_result_pending(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="pending")
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="pending",
        disposition="pending",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="ok",
        roster_access_n=1,
    )


def test_paused_playground_snapshot_access_result_paused(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="pro", status="paused")
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="paused",
        disposition="paused",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )


def test_halted_playground_snapshot_access_result_halted(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="max", status="halted")
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="halted",
        disposition="halted",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )


def test_period_ended_playground_snapshot_access_result(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_period_ended_refund(app)
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="paid_period_ended",
        disposition="active",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )


def test_plus_active_playground_snapshot_access_result_allowed(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="allowed",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="ok",
        roster_access_n=1,
    )


def test_halted_home_does_not_increment_entitlement_twice(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="max", status="halted")
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    assert snap is not None
    assert snap.counters["playground_entitlement_resolves"] == 1
    assert snap.timings["playground_entitlement"][1] == 1


def test_guest_and_free_playground_get_do_not_hydrate_acts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    hydrated = _hydrate_spy(monkeypatch)
    guest = TestClient(_counting_app(tmp_path / "guest")[0])
    assert guest.get("/playground").status_code == 200
    free, _repo = _counting_client(tmp_path / "free")
    assert free.get("/playground").status_code == 200
    assert hydrated == []


def test_guest_playground_does_not_read_subscriptions(tmp_path: Path):
    async def _go():
        client, app = await _async_guest_client(tmp_path)
        spy = _spy_subscriptions(app)
        try:
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap, spy.calls
        finally:
            await client.aclose()

    resp, snap, calls = asyncio.run(_go())
    assert resp.status_code == 200
    assert calls == 0
    _assert_t3_entitlement(
        snap,
        access="guest",
        auth_state="guest",
        device_result="skipped_unpaid",
        device_lookups=0,
    )


def test_free_playground_reads_current_subscription_once(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        spy = _spy_subscriptions(app)
        try:
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap, spy.calls
        finally:
            await client.aclose()

    resp, snap, calls = asyncio.run(_go())
    assert resp.status_code == 200
    assert calls == 1
    _assert_t3_entitlement(
        snap,
        access="free",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )


def test_entitlement_notes_omit_pii_on_breakdown_and_snapshot(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    async def _go():
        client, _repo = await _async_authed_client(tmp_path)
        try:
            with caplog.at_level(logging.INFO, logger="uvicorn.error"):
                caplog.clear()
                resp = await client.get("/playground?notice=x")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    assert snap is not None
    assert "?" not in snap.path_group
    assert "notice" not in snap.path_group
    assert str(USER) not in snap.path_group
    assert str(USER) not in snap.notes.values()
    assert USER_EMAIL not in snap.notes.values()
    breakdown = "\n".join(_breakdown_messages(caplog))
    assert str(USER) not in breakdown
    assert USER_EMAIL not in breakdown
    assert "notice=x" not in breakdown
    assert "?" not in breakdown


def test_dashboard_free_snapshot_records_entitlement_once(tmp_path: Path):
    async def _go():
        client, _repo = await _async_authed_client(tmp_path)
        try:
            resp = await client.get("/dashboard")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    assert snap is not None
    assert snap.path_group == "/dashboard"
    _assert_t3_entitlement(
        snap,
        access="free",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )


def test_guest_playground_json_still_401(tmp_path: Path):
    client = TestClient(_counting_app(tmp_path)[0])
    resp = client.get("/playground", headers={"Accept": "application/json"})
    assert resp.status_code == 401
    assert resp.json()["error"] == "auth_required"


@pytest.mark.parametrize(
    "access, commercially_open, ensure_ran, admin_override, device_result, overwrite",
    [
        (None, False, False, False, "skipped_unpaid", None),
        (
            _canned_device_access(block_reason=BLOCK_DEVICE_LIMIT),
            False,
            False,
            False,
            "skipped_unpaid",
            None,
        ),
        (
            _canned_device_access(block_reason=BLOCK_DEVICE_LIMIT),
            True,
            False,
            False,
            "device_limit",
            "device_limit",
        ),
        (
            _canned_device_access(block_reason=BLOCK_DEVICE_REVOKED),
            True,
            True,
            False,
            "device_revoked",
            "device_revoked",
        ),
        (
            _canned_device_access(block_reason=BLOCK_DEVICE_CONFIG_ERROR),
            True,
            True,
            False,
            "device_config_error",
            "device_config_error",
        ),
        (
            _canned_device_access(block_reason=BLOCK_DEVICE_REPLACEMENT_LIMIT),
            True,
            True,
            False,
            "replacement_limit",
            "replacement_limit",
        ),
        (
            _canned_device_access(block_reason=None),
            True,
            True,
            False,
            "ok",
            None,
        ),
        (
            _canned_device_access(block_reason=BLOCK_DEVICE_LIMIT),
            True,
            False,
            True,
            "skipped_unpaid",
            None,
        ),
        (
            _canned_device_access(block_reason=None),
            True,
            True,
            True,
            "ok",
            None,
        ),
    ],
)
def test_device_playground_notes_mapping(
    access,
    commercially_open,
    ensure_ran,
    admin_override,
    device_result,
    overwrite,
):
    got_device, got_overwrite = device_playground_notes(
        access,
        commercially_open=commercially_open,
        ensure_ran=ensure_ran,
        admin_override=admin_override,
    )
    assert got_device == device_result
    assert got_overwrite == overwrite
    assert got_device in PLAYGROUND_DEVICE_RESULTS
    if got_overwrite is not None:
        assert got_overwrite in PLAYGROUND_ACCESS_RESULTS
    blob = f"{got_device} {got_overwrite}"
    assert str(USER) not in blob
    assert USER_EMAIL not in blob
    assert "device_replacement_limit" not in blob
    assert "Mozilla" not in blob
    assert TEST_DEVICE_HMAC_SECRET not in blob


def test_device_notes_use_openness_before_apply():
    access = _canned_device_access(block_reason=BLOCK_DEVICE_LIMIT)
    snap = _plus_open_snap()
    commercially_open = bool(snap.can_open_playground)
    applied = apply_device_access(snap, access)
    assert commercially_open is True
    assert applied.can_open_playground is False
    result, overwrite = device_playground_notes(
        access, commercially_open=commercially_open, ensure_ran=True
    )
    assert result == "device_limit"
    assert overwrite == "device_limit"
    _, inferred = device_playground_notes(
        access, commercially_open=bool(applied.can_open_playground), ensure_ran=True
    )
    assert inferred is None


def test_overlay_skip_guest_does_not_count_or_time_device():
    class Spy:
        def inspect_current_device(self, *args, **kwargs):
            raise AssertionError("guest overlay must not inspect")

        def ensure_current_device(self, *args, **kwargs):
            raise AssertionError("guest overlay must not ensure")

    request = _fake_entitlement_request(
        resolver=EntitlementService(),
        current_user=None,
        multiuser_enabled=True,
        device_service=Spy(),
    )
    token = begin_request_timings()
    try:
        get_entitlement_snapshot(request)
        assert "playground_device" not in snapshot_request_timings()
        assert "playground_device_lookups" not in snapshot_request_counters()
        assert snapshot_request_notes()["playground_device_result"] == "skipped_unpaid"
        assert snapshot_request_counters()["playground_entitlement_resolves"] == 1
    finally:
        reset_request_timings(token)


def test_overlay_inspect_counts_once_on_memo_miss_only():
    class Spy:
        def __init__(self) -> None:
            self.calls = 0

        def inspect_current_device(self, *args, **kwargs):
            self.calls += 1
            return _canned_device_access()

    spy = Spy()
    request = _fake_entitlement_request(
        resolver=EntitlementService(),
        current_user=SimpleNamespace(id=USER),
        multiuser_enabled=True,
        device_service=spy,
    )
    token = begin_request_timings()
    try:
        get_entitlement_snapshot(request)
        record_request_note("playground_device_result", "mutated")
        get_entitlement_snapshot(request)
        assert spy.calls == 1
        assert snapshot_request_counters()["playground_device_lookups"] == 1
        assert snapshot_request_timings()["playground_device"][1] == 1
        assert snapshot_request_notes()["playground_device_result"] == "mutated"
    finally:
        reset_request_timings(token)


def test_raising_inspect_counts_attempt_without_fabricated_device_note():
    class Boom:
        def inspect_current_device(self, *args, **kwargs):
            raise RuntimeError("inspect boom")

    request = _fake_entitlement_request(
        resolver=EntitlementService(),
        current_user=SimpleNamespace(id=USER),
        multiuser_enabled=True,
        device_service=Boom(),
    )
    token = begin_request_timings()
    try:
        with pytest.raises(RuntimeError, match="inspect boom"):
            get_entitlement_snapshot(request)
        assert snapshot_request_counters()["playground_device_lookups"] == 1
        assert snapshot_request_timings()["playground_device"][1] == 1
        notes = snapshot_request_notes()
        assert "playground_device_result" not in notes
        assert notes["playground_access_result"] == "free"
        assert not hasattr(request.state, "entitlement_snapshot")
    finally:
        reset_request_timings(token)


def test_raising_ensure_counts_attempt_without_ok_note():
    class Boom:
        def ensure_current_device(self, *args, **kwargs):
            raise RuntimeError("ensure boom")

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(device_service=Boom())),
        state=SimpleNamespace(
            current_user=SimpleNamespace(id=USER),
            auth_session=None,
        ),
        cookies={},
        headers={},
    )
    token = begin_request_timings()
    try:
        with pytest.raises(RuntimeError, match="ensure boom"):
            _ensure_device_and_refresh(request, _plus_open_snap())
        assert snapshot_request_counters()["playground_device_lookups"] == 1
        assert snapshot_request_timings()["playground_device"][1] == 1
        notes = snapshot_request_notes()
        assert notes.get("playground_device_result") != "ok"
        assert "playground_access_result" not in notes
    finally:
        reset_request_timings(token)


def test_device_records_noop_without_collector():
    request = _fake_entitlement_request(
        resolver=EntitlementService(),
        current_user=SimpleNamespace(id=USER),
        multiuser_enabled=True,
        device_service=SimpleNamespace(
            inspect_current_device=lambda *a, **k: _canned_device_access()
        ),
    )
    snap = get_entitlement_snapshot(request)
    assert snap.is_authenticated is True
    assert snapshot_request_timings() == {}
    assert snapshot_request_counters() == {}


def test_direct_device_service_inspect_is_not_instrumented():
    class NullRepo:
        def count_active(self, user_id):
            return 0

        def get_by_hash(self, user_id, digest):
            return None

        def find_unpaired_revoked(self, user_id):
            return None

    token = begin_request_timings()
    try:
        svc = DeviceService(NullRepo(), hmac_secret="unit-hmac-secret", device_limit=2)
        svc.inspect_current_device(USER, None)
        svc.ensure_current_device(
            USER, None, auth_session_id=None, commercially_eligible=False
        )
        assert snapshot_request_counters() == {}
        assert snapshot_request_timings() == {}
        assert snapshot_request_notes() == {}
    finally:
        reset_request_timings(token)


def test_guest_playground_snapshot_device_skipped_zero_lookups(tmp_path: Path):
    async def _go():
        client, app = await _async_guest_client(tmp_path)
        spy = _spy_device_service(app)
        try:
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap, spy.inspect_calls, spy.ensure_calls
        finally:
            await client.aclose()

    resp, snap, inspect_n, ensure_n = asyncio.run(_go())
    assert resp.status_code == 200
    assert inspect_n == 0
    assert ensure_n == 0
    _assert_t3_entitlement(
        snap,
        access="guest",
        auth_state="guest",
        device_result="skipped_unpaid",
        device_lookups=0,
    )


def test_free_authed_playground_snapshot_device_skipped_one_inspect(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        spy = _spy_device_service(app)
        try:
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap, spy.inspect_calls, spy.ensure_calls
        finally:
            await client.aclose()

    resp, snap, inspect_n, ensure_n = asyncio.run(_go())
    assert resp.status_code == 200
    assert inspect_n == 1
    assert ensure_n == 0
    _assert_t3_entitlement(
        snap,
        access="free",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )


def test_halted_playground_snapshot_does_not_ensure(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        spy = _spy_device_service(app)
        try:
            _seed_subscription(app, tier="max", status="halted")
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap, spy.inspect_calls, spy.ensure_calls
        finally:
            await client.aclose()

    resp, snap, inspect_n, ensure_n = asyncio.run(_go())
    assert resp.status_code == 200
    assert inspect_n == 1
    assert ensure_n == 0
    _assert_t3_entitlement(
        snap,
        access="halted",
        disposition="halted",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )


def test_plus_active_playground_snapshot_device_ok_two_lookups(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        spy = _spy_device_service(app)
        try:
            _seed_subscription(app, tier="plus", status="active")
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap, spy.inspect_calls, spy.ensure_calls
        finally:
            await client.aclose()

    resp, snap, inspect_n, ensure_n = asyncio.run(_go())
    assert resp.status_code == 200
    assert inspect_n == 1
    assert ensure_n == 1
    _assert_t3_entitlement(
        snap,
        access="allowed",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="ok",
        roster_access_n=1,
    )


def test_pending_playground_snapshot_keeps_pending_when_device_ok(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        spy = _spy_device_service(app)
        try:
            _seed_subscription(app, tier="plus", status="pending")
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap, spy.inspect_calls, spy.ensure_calls
        finally:
            await client.aclose()

    resp, snap, inspect_n, ensure_n = asyncio.run(_go())
    assert resp.status_code == 200
    assert inspect_n == 1
    assert ensure_n == 1
    _assert_t3_entitlement(
        snap,
        access="pending",
        disposition="pending",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="ok",
        roster_access_n=1,
    )


def test_dashboard_plus_snapshot_inspects_but_does_not_ensure(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        spy = _spy_device_service(app)
        try:
            _seed_subscription(app, tier="plus", status="active")
            resp = await client.get("/dashboard")
            snap = get_last_request_performance()
            return resp, snap, spy.inspect_calls, spy.ensure_calls
        finally:
            await client.aclose()

    resp, snap, inspect_n, ensure_n = asyncio.run(_go())
    assert resp.status_code == 200
    assert snap is not None
    assert snap.path_group == "/dashboard"
    assert inspect_n == 1
    assert ensure_n == 0
    _assert_t3_entitlement(
        snap,
        access="allowed",
        disposition="active",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )


def test_admin_playground_snapshot_skipped_unpaid_no_ensure(tmp_path: Path):
    async def _go():
        client, app, repo = await _async_authed_session(tmp_path)
        spy = _spy_device_service(app)
        try:
            _seed_admin(repo)
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap, spy.inspect_calls, spy.ensure_calls
        finally:
            await client.aclose()

    resp, snap, inspect_n, ensure_n = asyncio.run(_go())
    assert resp.status_code == 200
    assert inspect_n == 1
    assert ensure_n == 0
    _assert_t3_entitlement(
        snap,
        access="allowed",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
        roster_result="ok",
        roster_access_n=1,
    )


def test_device_limit_overwrites_access_result_on_plus_playground(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            _seed_other_devices(app, n=2)
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            cookie = client.cookies.get(DEVICE_COOKIE_NAME) or ""
            return resp, snap, cookie
        finally:
            await client.aclose()

    resp, snap, cookie = asyncio.run(_go())
    assert resp.status_code == 200
    assert 'data-playground-gate="device_limit"' in resp.text
    _assert_t3_entitlement(
        snap,
        access="device_limit",
        disposition="active",
        auth_state="authed",
        device_result="device_limit",
        device_lookups=2,
    )
    assert str(USER) not in snap.notes.values()
    if cookie:
        assert cookie not in snap.notes.values()
        assert cookie not in snap.path_group


def test_device_revoked_overwrites_access_result_on_plus_playground(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            first = await client.get("/playground")
            assert first.status_code == 200
            token = client.cookies.get(DEVICE_COOKIE_NAME)
            access = app.state.device_service.inspect_current_device(USER, token)
            assert access.current_device_id
            app.state.device_service.revoke_device(USER, access.current_device_id)
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="device_revoked",
        disposition="active",
        auth_state="authed",
        device_result="device_revoked",
        device_lookups=2,
    )


def _install_device_stub(app, access: DeviceAccess):
    inner = app.state.device_service

    class Stub:
        def inspect_current_device(self, *args, **kwargs):
            return access

        def ensure_current_device(self, *args, **kwargs):
            return access

        def __getattr__(self, name):
            return getattr(inner, name)

    app.state.device_service = Stub()


def test_device_config_error_note_and_access_result(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            _install_device_stub(
                app,
                _canned_device_access(block_reason=BLOCK_DEVICE_CONFIG_ERROR),
            )
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="device_config_error",
        disposition="active",
        auth_state="authed",
        device_result="device_config_error",
        device_lookups=2,
    )


def test_replacement_limit_note_maps_short_token(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            _install_device_stub(
                app,
                _canned_device_access(block_reason=BLOCK_DEVICE_REPLACEMENT_LIMIT),
            )
            with caplog.at_level(logging.INFO, logger="uvicorn.error"):
                caplog.clear()
                resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="replacement_limit",
        disposition="active",
        auth_state="authed",
        device_result="replacement_limit",
        device_lookups=2,
    )
    assert "device_replacement_limit" not in snap.notes.values()
    breakdown = "\n".join(_breakdown_messages(caplog))
    assert "device_replacement_limit" not in breakdown
    assert "playground_device_result=replacement_limit" in breakdown


def test_device_notes_omit_token_hmac_ua_ip_on_breakdown_and_snapshot(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            with caplog.at_level(logging.INFO, logger="uvicorn.error"):
                caplog.clear()
                resp = await client.get(
                    "/playground",
                    headers={
                        "User-Agent": "Mozilla/5.0 PrivacyProbe",
                        "X-Forwarded-For": "203.0.113.9",
                    },
                )
            snap = get_last_request_performance()
            cookie = client.cookies.get(DEVICE_COOKIE_NAME) or ""
            return resp, snap, cookie
        finally:
            await client.aclose()

    resp, snap, cookie = asyncio.run(_go())
    assert resp.status_code == 200
    assert snap is not None
    notes = " ".join(snap.notes.values())
    breakdown = "\n".join(_breakdown_messages(caplog))
    blob = f"{notes}\n{snap.path_group}\n{breakdown}"
    assert str(USER) not in blob
    assert USER_EMAIL not in blob
    assert "Mozilla" not in blob
    assert "PrivacyProbe" not in blob
    assert "203.0.113.9" not in blob
    assert TEST_DEVICE_HMAC_SECRET not in blob
    assert "rtc_device" not in blob
    if cookie:
        assert cookie not in blob


def test_free_device_limit_does_not_overwrite_access_result(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _install_device_stub(
                app, _canned_device_access(block_reason=BLOCK_DEVICE_LIMIT)
            )
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="free",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )


@pytest.mark.parametrize(
    "kwargs, roster_result, overwrite, law_state",
    [
        ({"source": "attach", "remaining": 10}, "ok", None, None),
        ({"source": "attach", "remaining": 0}, "roster_full", None, None),
        ({"source": "attach", "remaining": None}, "ok", None, None),
        ({"source": "attach", "local_owner": True, "remaining": 0}, "local_owner", None, None),
        ({"source": "consume_deny"}, "roster_full", "roster_full", None),
        ({"source": "membership", "membership_active": True}, "ok", None, "active"),
        (
            {"source": "membership", "membership_active": False},
            "inactive_law",
            "inactive_law",
            None,
        ),
        (
            {
                "source": "membership",
                "membership_active": False,
                "law_state": "removed",
            },
            "inactive_law",
            "inactive_law",
            "removed",
        ),
        (
            {
                "source": "membership",
                "membership_active": False,
                "law_state": "historical",
            },
            "inactive_law",
            "inactive_law",
            "historical",
        ),
        (
            {
                "source": "membership",
                "membership_active": False,
                "law_state": "none",
            },
            "inactive_law",
            "inactive_law",
            None,
        ),
        (
            {"source": "membership", "period_missing": True},
            "roster_missing",
            "roster_missing",
            None,
        ),
    ],
)
def test_roster_playground_notes_mapping(kwargs, roster_result, overwrite, law_state):
    got_result, got_overwrite, got_state = roster_playground_notes(**kwargs)
    assert got_result == roster_result
    assert got_overwrite == overwrite
    assert got_state == law_state
    assert got_result in PLAYGROUND_ROSTER_RESULTS or got_result in PLAYGROUND_ACCESS_RESULTS
    assert got_result != "peek"
    if got_overwrite is not None:
        assert got_overwrite in PLAYGROUND_ACCESS_RESULTS
    if got_state is not None:
        assert got_state in PLAYGROUND_LAW_STATES
        assert got_state != "none"
    blob = f"{got_result} {got_overwrite} {got_state}"
    assert str(USER) not in blob
    assert USER_EMAIL not in blob
    assert "ndps" not in blob
    assert "10" not in blob


def test_roster_full_attach_does_not_overwrite_allowed():
    result, overwrite, state = roster_playground_notes(source="attach", remaining=0)
    assert result == "roster_full"
    assert overwrite is None
    assert state is None


def test_roster_consume_deny_overwrites_access_result():
    result, overwrite, state = roster_playground_notes(source="consume_deny")
    assert result == "roster_full"
    assert overwrite == "roster_full"
    assert state is None


def test_raising_capacity_times_without_fabricated_roster_note():
    class Boom:
        def capacity(self, *args, **kwargs):
            raise RuntimeError("capacity boom")

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(roster=Boom())),
        state=SimpleNamespace(),
    )
    token = begin_request_timings()
    try:
        with pytest.raises(RuntimeError, match="capacity boom"):
            _attach_current_period(request, _plus_open_access())
        assert snapshot_request_timings()["playground_roster_access"][1] == 1
        notes = snapshot_request_notes()
        assert "playground_roster_result" not in notes
        assert "playground_law_state" not in notes
        assert "playground_roster_reads" not in snapshot_request_counters()
    finally:
        reset_request_timings(token)


def test_raising_is_law_active_times_without_fabricated_roster_note(monkeypatch):
    opened = _plus_open_access()

    class Boom:
        def is_law_active_this_period(self, *args, **kwargs):
            raise RuntimeError("membership boom")

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(roster=Boom())),
    )
    monkeypatch.setattr(
        "constitution_memorizer.playground.access.require_playground_open",
        lambda *args, **kwargs: opened,
    )
    monkeypatch.setattr(
        "constitution_memorizer.playground.access.require_roster_service",
        lambda req: req.app.state.roster,
    )
    token = begin_request_timings()
    try:
        with pytest.raises(RuntimeError, match="membership boom"):
            require_law_active_this_period(
                request,
                templates=None,
                overlay=None,
                law_id="ndps",
                next_url="/playground",
            )
        assert snapshot_request_timings()["playground_roster_access"][1] == 1
        notes = snapshot_request_notes()
        assert "playground_roster_result" not in notes
        assert "playground_law_state" not in notes
        assert "playground_roster_reads" not in snapshot_request_counters()
    finally:
        reset_request_timings(token)


def test_direct_roster_service_calls_are_not_instrumented():
    class Svc:
        def capacity(self, *args, **kwargs):
            return _capacity()

        def is_law_active_this_period(self, *args, **kwargs):
            return True

        def peek_capacity(self, *args, **kwargs):
            return _capacity()

    token = begin_request_timings()
    try:
        Svc().capacity(USER, None)
        Svc().is_law_active_this_period(USER, "ndps")
        Svc().peek_capacity(USER, None)
        assert snapshot_request_timings() == {}
        assert snapshot_request_counters() == {}
        assert snapshot_request_notes() == {}
    finally:
        reset_request_timings(token)


def test_roster_records_noop_without_collector():
    class Cap:
        def capacity(self, *args, **kwargs):
            return _capacity(remaining=4, used=6)

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(roster=Cap())),
        state=SimpleNamespace(),
    )
    _attach_current_period(request, _plus_open_access())
    assert snapshot_request_timings() == {}
    assert snapshot_request_counters() == {}
    assert snapshot_request_notes() == {}


def test_attach_skips_timing_when_no_roster_call():
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(roster=None)),
        state=SimpleNamespace(),
    )
    token = begin_request_timings()
    try:
        _attach_current_period(request, _plus_open_access())
        none_user = PlaygroundAccess(
            user_id=None,
            snapshot=_plus_open_snap(),
            can_open=True,
            can_consume_new_law=True,
            local_owner=False,
            can_view_home=True,
        )
        _attach_current_period(request, none_user)
        assert "playground_roster_access" not in snapshot_request_timings()
        assert "playground_roster_result" not in snapshot_request_notes()
    finally:
        reset_request_timings(token)


def test_attach_full_keeps_allowed_access_result():
    class Cap:
        def capacity(self, *args, **kwargs):
            return _capacity(remaining=0, used=10)

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(roster=Cap())),
        state=SimpleNamespace(),
    )
    token = begin_request_timings()
    try:
        record_request_note("playground_access_result", "allowed")
        _attach_current_period(request, _plus_open_access())
        notes = snapshot_request_notes()
        assert notes["playground_roster_result"] == "roster_full"
        assert notes["playground_access_result"] == "allowed"
        assert "playground_law_state" not in notes
        assert snapshot_request_timings()["playground_roster_access"][1] == 1
    finally:
        reset_request_timings(token)


def test_attach_local_owner_result():
    class Cap:
        def capacity(self, *args, **kwargs):
            return _capacity(remaining=None, used=0)

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(roster=Cap())),
        state=SimpleNamespace(),
    )
    token = begin_request_timings()
    try:
        _attach_current_period(request, _plus_open_access(local_owner=True))
        notes = snapshot_request_notes()
        assert notes["playground_roster_result"] == "local_owner"
        assert "playground_access_result" not in notes
        assert "playground_law_state" not in notes
    finally:
        reset_request_timings(token)


def test_consume_blocked_roster_full_overwrites_without_timing():
    token = begin_request_timings()
    try:
        record_request_note("playground_access_result", "allowed")
        resp = consume_blocked_response(
            SimpleNamespace(),
            templates=None,
            access=_plus_open_access(),
            result_status=RESULT_ROSTER_FULL,
            json_mode=True,
        )
        assert resp.status_code == 403
        body = resp.body.decode()
        assert "roster_full" in body
        assert "inactive_law" not in body
        notes = snapshot_request_notes()
        assert notes["playground_roster_result"] == "roster_full"
        assert notes["playground_access_result"] == "roster_full"
        assert "playground_roster_access" not in snapshot_request_timings()
        assert "playground_law_state" not in notes
    finally:
        reset_request_timings(token)


def test_consume_blocked_new_blocked_is_not_relabeled():
    token = begin_request_timings()
    try:
        record_request_note("playground_access_result", "pending")
        resp = consume_blocked_response(
            SimpleNamespace(),
            templates=None,
            access=_plus_open_access(),
            result_status=RESULT_NEW_BLOCKED,
            json_mode=True,
        )
        assert resp.status_code == 403
        assert "inactive_law" not in resp.body.decode()
        assert "roster_full" not in resp.body.decode()
        notes = snapshot_request_notes()
        assert notes["playground_access_result"] == "pending"
        assert "playground_roster_result" not in notes
        assert "playground_roster_access" not in snapshot_request_timings()
    finally:
        reset_request_timings(token)


def test_membership_false_maps_to_inactive_law_not_missing():
    token = begin_request_timings()
    try:
        record_roster_access_outcome(source="membership", membership_active=False)
        notes = snapshot_request_notes()
        assert notes["playground_roster_result"] == "inactive_law"
        assert notes["playground_access_result"] == "inactive_law"
        assert "playground_law_state" not in notes
    finally:
        reset_request_timings(token)


def test_roster_missing_is_mapper_only():
    result, overwrite, state = roster_playground_notes(
        source="membership", period_missing=True
    )
    assert result == "roster_missing"
    assert overwrite == "roster_missing"
    assert state is None
    source = inspect.getsource(require_law_active_this_period)
    assert "get_period(" not in source
    assert "peek_capacity(" not in source
    assert "period_missing" not in source
    attach_src = inspect.getsource(_attach_current_period)
    assert "peek_capacity(" not in attach_src
    assert "get_period(" not in attach_src


def test_plus_inactive_law_overwrites_access_result(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            resp = await client.get("/playground/laws/ndps")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 303
    assert resp.headers.get("location") == "/laws/ndps"
    _assert_t3_entitlement(
        snap,
        access="inactive_law",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="inactive_law",
        roster_access_n=2,
    )


def test_inactive_json_mode_keeps_not_active_this_period(monkeypatch):
    opened = _plus_open_access()

    class Roster:
        def is_law_active_this_period(self, *args, **kwargs):
            return False

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(roster=Roster())),
    )
    monkeypatch.setattr(
        "constitution_memorizer.playground.access.require_playground_open",
        lambda *args, **kwargs: opened,
    )
    monkeypatch.setattr(
        "constitution_memorizer.playground.access.require_roster_service",
        lambda req: req.app.state.roster,
    )
    token = begin_request_timings()
    try:
        resp = require_law_active_this_period(
            request,
            templates=None,
            overlay=None,
            law_id="ndps",
            next_url="/playground",
            json_mode=True,
        )
        assert resp.status_code == 403
        payload = resp.body.decode()
        assert "not_active_this_period" in payload
        assert "inactive_law" not in payload
        notes = snapshot_request_notes()
        assert notes["playground_access_result"] == "inactive_law"
        assert notes["playground_roster_result"] == "inactive_law"
        assert "playground_law_state" not in notes
    finally:
        reset_request_timings(token)


def test_plus_active_law_records_ok_and_law_state_active(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            snap_ent = app.state.entitlement_service.resolve(USER)
            result = app.state.roster.confirm_add_law(
                USER, "ndps", snap_ent, can_consume_new_law=True
            )
            assert result.ok
            resp = await client.get("/playground/laws/ndps")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="allowed",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="ok",
        roster_access_n=2,
        law_state="active",
    )


def test_plus_removed_law_records_law_state_removed(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            snap_ent = app.state.entitlement_service.resolve(USER)
            assert app.state.roster.confirm_add_law(
                USER, "ndps", snap_ent, can_consume_new_law=True
            ).ok
            activate_law(app.state.playground, USER, "ndps")
            app.state.roster.remove_law_this_period(USER, "ndps", snap_ent)
            resp = await client.get("/playground/laws/ndps")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="inactive_law",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="inactive_law",
        roster_access_n=2,
        law_state="removed",
    )


def test_plus_historical_overlay_records_law_state_historical(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            activate_law(app.state.playground, USER, "ndps")
            resp = await client.get("/playground/laws/ndps")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="inactive_law",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="inactive_law",
        roster_access_n=2,
        law_state="historical",
    )


def test_plus_roster_full_home_keeps_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            _fill_plus_roster(app, monkeypatch)
            resp = await client.get("/playground")
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="allowed",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="roster_full",
        roster_access_n=1,
    )


def test_plus_roster_full_add_overwrites_access_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            _fill_plus_roster(app, monkeypatch)
            await client.get("/playground")
            csrf = client.cookies.get("rtc_csrf") or ""
            resp = await client.post(
                "/playground/laws/ndps/add",
                data={"csrf_token": csrf, "confirm": "add", "scope": "sections"},
                headers={"Accept": "application/json"},
            )
            snap = get_last_request_performance()
            return resp, snap
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code in {200, 403}
    if resp.status_code == 403:
        assert resp.json()["error"] == "roster_full"
    else:
        assert "roster_full" in resp.text
    assert "inactive_law" not in resp.text
    _assert_t3_entitlement(
        snap,
        access="roster_full",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=3,
        roster_result="roster_full",
        roster_access_n=2,
    )


def test_roster_notes_omit_law_text_user_ids_tokens(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            with caplog.at_level(logging.INFO, logger="uvicorn.error"):
                caplog.clear()
                resp = await client.get(
                    "/playground/laws/ndps",
                    headers={
                        "User-Agent": "Mozilla/5.0 PrivacyProbe",
                        "X-Forwarded-For": "203.0.113.9",
                    },
                )
            snap = get_last_request_performance()
            cookie = client.cookies.get(DEVICE_COOKIE_NAME) or ""
            return resp, snap, cookie
        finally:
            await client.aclose()

    resp, snap, cookie = asyncio.run(_go())
    assert resp.status_code == 303
    assert snap is not None
    notes = " ".join(snap.notes.values())
    breakdown = "\n".join(_breakdown_messages(caplog))
    blob = f"{notes}\n{snap.path_group}\n{breakdown}"
    assert str(USER) not in blob
    assert USER_EMAIL not in blob
    assert "ndps" not in blob
    assert "Mozilla" not in blob
    assert "PrivacyProbe" not in blob
    assert "203.0.113.9" not in blob
    assert TEST_DEVICE_HMAC_SECRET not in blob
    if cookie:
        assert cookie not in blob
    assert "none" not in snap.notes.values()
    assert snap.notes.get("playground_roster_result") != "peek"
    assert snap.path_group == "/playground/laws/{law_id}"


def test_repo_counters_uses_contextvar_token_reset_and_wraps():
    src = (
        Path(__file__).resolve().parents[1]
        / "src/constitution_memorizer/playground/repo_counters.py"
    ).read_text(encoding="utf-8")
    assert "token = _repo_counter_depth.set(_repo_counter_depth.get() + 1)" in src
    assert "_repo_counter_depth.reset(token)" in src
    assert "@wraps(fn)" in src
    assert "depth -= 1" not in src
    assert "threading.local" not in src
    assert "request.app" not in src
    assert "sqlite" not in src.lower()
    assert "sqlalchemy" not in src.lower()
    assert "entitlement" not in src.lower()
    assert "subscription" not in src.lower()
    assert "from constitution_memorizer.web.request_context import" in src
    assert src.index("def _increment") < src.index(
        "from constitution_memorizer.web.request_context import"
    )


def test_t6_does_not_add_counter_names():
    assert "playground_roster_writes" not in REQUEST_COUNTERS
    assert "playground_item_reads" not in REQUEST_COUNTERS
    assert "playground_selection_reads" not in REQUEST_COUNTERS
    assert REQUEST_COUNTERS[REQUEST_COUNTERS.index("playground_db_reads") :] == (
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


def test_t6_does_not_instrument_other_sqlite_or_private_helpers():
    root = Path(__file__).resolve().parents[1] / "src/constitution_memorizer"
    devices = (root / "devices/repository.py").read_text(encoding="utf-8")
    subs = (root / "subscriptions/repository.py").read_text(encoding="utf-8")
    assert "count_playground_repo_call" not in devices
    assert "count_playground_repo_call" not in subs
    assert "count_playground_repo_call" not in inspect.getsource(
        SqliteRosterRepository._ensure_period_locked
    )
    assert "count_playground_repo_call" not in inspect.getsource(
        PostgresRosterRepository._ensure_period_locked
    )
    assert "count_playground_repo_call" not in inspect.getsource(
        PostgresPlaygroundRepository._item_from_row
    )
    assert "count_playground_repo_call" not in inspect.getsource(
        PostgresPlaygroundRepository._mode_from_row
    )


def test_sqlite_roster_get_period_increments_roster_reads(tmp_path: Path):
    _overlay, roster_repo, _svc, _conn = _t6_sqlite(tmp_path)
    token = begin_request_timings()
    try:
        roster_repo.get_period(USER, playground_month_bounds()[0])
        _assert_t6_counts(
            snapshot_request_counters(), db_reads=1, roster_reads=1
        )
    finally:
        reset_request_timings(token)


def test_sqlite_list_periods_counts_as_roster_read(tmp_path: Path):
    _overlay, roster_repo, _svc, _conn = _t6_sqlite(tmp_path)
    token = begin_request_timings()
    try:
        roster_repo.list_periods(USER)
        _assert_t6_counts(
            snapshot_request_counters(), db_reads=1, roster_reads=1
        )
    finally:
        reset_request_timings(token)


def test_sqlite_roster_ensure_period_is_write_not_roster_reads(tmp_path: Path):
    _overlay, roster_repo, _svc, _conn = _t6_sqlite(tmp_path)
    start, end = playground_month_bounds()
    token = begin_request_timings()
    try:
        roster_repo.ensure_period(
            USER,
            period_start=start,
            period_end=end,
            tier_snapshot="plus",
            law_limit=10,
        )
        _assert_t6_counts(snapshot_request_counters(), db_writes=1)
    finally:
        reset_request_timings(token)


def test_sqlite_roster_consume_early_return_is_still_write(tmp_path: Path):
    _overlay, roster_repo, svc, _conn = _t6_sqlite(tmp_path)
    snap = _plus_open_snap()
    start, _end = playground_month_bounds()
    svc.ensure_current_period(USER, snap)
    first = roster_repo.consume_law(
        USER,
        period_start=start,
        law_id="ndps",
        law_limit=10,
        allow_new=True,
    )
    assert first.ok or first.status in {RESULT_ROSTER_FULL}
    token = begin_request_timings()
    try:
        again = roster_repo.consume_law(
            USER,
            period_start=start,
            law_id="ndps",
            law_limit=10,
            allow_new=True,
        )
        assert again.status != "ok" or again.ok
        _assert_t6_counts(snapshot_request_counters(), db_writes=1)
    finally:
        reset_request_timings(token)


def test_sqlite_confirm_add_law_counts_ensure_and_consume(tmp_path: Path):
    _overlay, _roster_repo, svc, _conn = _t6_sqlite(tmp_path)
    token = begin_request_timings()
    try:
        result = svc.confirm_add_law(
            USER, "ndps", _plus_open_snap(), can_consume_new_law=True
        )
        assert result.ok
        _assert_t6_counts(snapshot_request_counters(), db_writes=2)
    finally:
        reset_request_timings(token)


def test_sqlite_capacity_counts_ensure_and_count_consumed(tmp_path: Path):
    _overlay, _roster_repo, svc, _conn = _t6_sqlite(tmp_path)
    token = begin_request_timings()
    try:
        svc.capacity(USER, _plus_open_snap())
        _assert_t6_counts(
            snapshot_request_counters(),
            db_reads=1,
            db_writes=1,
            roster_reads=1,
        )
    finally:
        reset_request_timings(token)


def test_sqlite_peek_missing_period_is_one_roster_read(tmp_path: Path):
    _overlay, _roster_repo, svc, _conn = _t6_sqlite(tmp_path)
    token = begin_request_timings()
    try:
        svc.peek_capacity(USER, _plus_open_snap())
        _assert_t6_counts(
            snapshot_request_counters(), db_reads=1, roster_reads=1
        )
    finally:
        reset_request_timings(token)


def test_sqlite_overlay_get_item_has_no_domain_counter(tmp_path: Path):
    overlay, _roster_repo, _svc, _conn = _t6_sqlite(tmp_path)
    token = begin_request_timings()
    try:
        overlay.get_item(USER, "ndps")
        overlay.list_items(USER)
        overlay.list_selection(USER, "ndps")
        _assert_t6_counts(snapshot_request_counters(), db_reads=3)
    finally:
        reset_request_timings(token)


def test_sqlite_list_summaries_increments_summary_reads(tmp_path: Path):
    overlay, _roster_repo, _svc, _conn = _t6_sqlite(tmp_path)
    token = begin_request_timings()
    try:
        overlay.list_playground_summaries(USER, as_of=playground_today())
        _assert_t6_counts(
            snapshot_request_counters(), db_reads=1, summary_reads=1
        )
    finally:
        reset_request_timings(token)


def test_sqlite_empty_summary_law_ids_still_counts(tmp_path: Path):
    overlay, _roster_repo, _svc, _conn = _t6_sqlite(tmp_path)
    token = begin_request_timings()
    try:
        rows = overlay.list_playground_summaries(
            USER, as_of=playground_today(), law_ids=[]
        )
        assert rows == []
        overlay.list_due_revisions(USER, playground_today(), [])
        overlay.list_source_scans(USER, [])
        _assert_t6_counts(
            snapshot_request_counters(),
            db_reads=3,
            summary_reads=1,
            revision_reads=1,
            source_review_reads=1,
        )
    finally:
        reset_request_timings(token)


def test_sqlite_get_progress_increments_progress_reads(tmp_path: Path):
    overlay, _roster_repo, _svc, _conn = _t6_sqlite(tmp_path)
    token = begin_request_timings()
    try:
        overlay.get_progress(USER, "ndps", "ndps:section:1")
        overlay.get_mode_progress(USER, "ndps", "ndps:section:1", "read")
        _assert_t6_counts(
            snapshot_request_counters(), db_reads=2, progress_reads=2
        )
    finally:
        reset_request_timings(token)


def test_sqlite_get_revision_progress_counts_revision_not_progress(tmp_path: Path):
    overlay, _roster_repo, _svc, _conn = _t6_sqlite(tmp_path)
    token = begin_request_timings()
    try:
        overlay.get_revision_progress(USER, "ndps", "ndps:section:1")
        _assert_t6_counts(
            snapshot_request_counters(), db_reads=1, revision_reads=1
        )
    finally:
        reset_request_timings(token)


def test_sqlite_list_source_changes_increments_source_review_reads(tmp_path: Path):
    overlay, _roster_repo, _svc, _conn = _t6_sqlite(tmp_path)
    token = begin_request_timings()
    try:
        overlay.list_source_changes(USER, "ndps")
        _assert_t6_counts(
            snapshot_request_counters(), db_reads=1, source_review_reads=1
        )
    finally:
        reset_request_timings(token)


def test_sqlite_add_item_nested_get_item_does_not_double_count(tmp_path: Path):
    overlay, _roster_repo, _svc, _conn = _t6_sqlite(tmp_path)
    token = begin_request_timings()
    try:
        overlay.add_item(
            USER, "ndps", source_version="v1", law_source_hash="hash"
        )
        _assert_t6_counts(snapshot_request_counters(), db_writes=1)
    finally:
        reset_request_timings(token)


def test_sqlite_complete_mode_nested_is_one_write(tmp_path: Path):
    overlay, _roster_repo, _svc, _conn = _t6_sqlite(tmp_path)
    overlay.add_item(USER, "ndps", source_version="v1", law_source_hash="hash")
    token = begin_request_timings()
    try:
        overlay.complete_mode(
            USER,
            "ndps",
            "ndps:section:1",
            "read",
            source_version="v1",
            source_hash="hash",
        )
        _assert_t6_counts(snapshot_request_counters(), db_writes=1)
    finally:
        reset_request_timings(token)


def test_sqlite_direct_complete_learning_mode_is_one_write(tmp_path: Path):
    overlay, _roster_repo, _svc, _conn = _t6_sqlite(tmp_path)
    token = begin_request_timings()
    try:
        overlay.complete_learning_mode_and_transition_if_ready(
            USER,
            "ndps",
            "ndps:section:1",
            "read",
            source_version="v1",
            source_hash="hash",
        )
        _assert_t6_counts(snapshot_request_counters(), db_writes=1)
    finally:
        reset_request_timings(token)


def test_sqlite_repo_exception_still_increments(tmp_path: Path):
    _overlay, roster_repo, _svc, conn = _t6_sqlite(tmp_path)
    conn.close()
    token = begin_request_timings()
    try:
        with pytest.raises(sqlite3.Error):
            roster_repo.get_period(USER, playground_month_bounds()[0])
        _assert_t6_counts(
            snapshot_request_counters(), db_reads=1, roster_reads=1
        )
    finally:
        reset_request_timings(token)


def test_sqlite_repo_records_noop_without_collector(tmp_path: Path):
    overlay, roster_repo, svc, _conn = _t6_sqlite(tmp_path)
    overlay.get_item(USER, "ndps")
    roster_repo.get_period(USER, playground_month_bounds()[0])
    svc.capacity(USER, _plus_open_snap())
    assert snapshot_request_counters() == {}


def test_sqlite_remove_law_and_apply_rollover_are_writes(tmp_path: Path):
    _overlay, roster_repo, _svc, _conn = _t6_sqlite(tmp_path)
    start, end = playground_month_bounds()
    token = begin_request_timings()
    try:
        roster_repo.remove_law(USER, period_start=start, law_id="ndps")
        roster_repo.apply_rollover(
            USER,
            period_start=start,
            period_end=end,
            tier_snapshot="plus",
            law_limit=10,
            activate=False,
            keep_ids=[],
            decline_ids=[],
            allowed_ids=frozenset(),
            allow_new_keep=True,
        )
        _assert_t6_counts(snapshot_request_counters(), db_writes=2)
    finally:
        reset_request_timings(token)


def test_guest_playground_has_zero_t6_repo_counters(tmp_path: Path):
    async def _go():
        client, _app = await _async_guest_client(tmp_path)
        try:
            resp = await client.get("/playground")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="guest",
        auth_state="guest",
        device_result="skipped_unpaid",
        device_lookups=0,
    )
    _assert_t6_absent(snap.counters)


def test_free_playground_has_zero_t6_repo_counters(tmp_path: Path):
    async def _go():
        client, _repo = await _async_authed_client(tmp_path)
        try:
            resp = await client.get("/playground")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="free",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )
    _assert_t6_absent(snap.counters)


@pytest.mark.parametrize(
    "seed, access, disposition",
    [
        (
            lambda app: _seed_subscription(app, tier="max", status="halted"),
            "halted",
            "halted",
        ),
        (
            lambda app: _seed_subscription(app, tier="pro", status="paused"),
            "paused",
            "paused",
        ),
        (
            lambda app: _seed_period_ended_refund(app),
            "paid_period_ended",
            "active",
        ),
    ],
)
def test_read_only_home_t6_reads_without_writes_or_t5(
    tmp_path: Path, seed, access, disposition
):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            seed(app)
            resp = await client.get("/playground")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access=access,
        disposition=disposition,
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )
    _assert_t6_counts(
        snap.counters,
        db_reads=5,
        roster_reads=3,
        summary_reads=1,
    )


def test_plus_empty_home_records_duplicate_capacity_writes(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            resp = await client.get("/playground")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="allowed",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="ok",
        roster_access_n=1,
    )
    _assert_t6_counts(
        snap.counters,
        db_reads=7,
        db_writes=2,
        roster_reads=5,
        summary_reads=1,
    )


def test_pending_home_t6_matches_plus_empty(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="pending")
            resp = await client.get("/playground")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="pending",
        disposition="pending",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="ok",
        roster_access_n=1,
    )
    _assert_t6_counts(
        snap.counters,
        db_reads=7,
        db_writes=2,
        roster_reads=5,
        summary_reads=1,
    )


def test_admin_playground_t6_matches_plus_empty_writes(tmp_path: Path):
    async def _go():
        client, app, repo = await _async_authed_session(tmp_path)
        try:
            _seed_admin(repo)
            resp = await client.get("/playground")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="allowed",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
        roster_result="ok",
        roster_access_n=1,
    )
    _assert_t6_counts(
        snap.counters,
        db_reads=7,
        db_writes=2,
        roster_reads=5,
        summary_reads=1,
    )


def test_dashboard_plus_t6_reads_without_t5_records_t9_today(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            resp = await client.get("/dashboard")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="allowed",
        disposition="active",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )
    _assert_t9_today_only(snap)
    _assert_t6_counts(
        snap.counters,
        db_reads=3,
        roster_reads=2,
        revision_reads=1,
    )


def test_plus_active_law_workspace_t6_counts(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            snap_ent = app.state.entitlement_service.resolve(USER)
            assert app.state.roster.confirm_add_law(
                USER, "ndps", snap_ent, can_consume_new_law=True
            ).ok
            resp = await client.get("/playground/laws/ndps")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="allowed",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="ok",
        roster_access_n=2,
        law_state="active",
    )
    _assert_t6_counts(
        snap.counters,
        db_reads=11,
        db_writes=1,
        roster_reads=3,
        progress_reads=2,
        revision_reads=1,
        source_review_reads=2,
    )


def test_plus_inactive_law_t6_counts(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            resp = await client.get("/playground/laws/ndps")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 303
    assert resp.headers.get("location") == "/laws/ndps"
    _assert_t3_entitlement(
        snap,
        access="inactive_law",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="inactive_law",
        roster_access_n=2,
    )
    _assert_t6_counts(
        snap.counters,
        db_reads=4,
        db_writes=1,
        roster_reads=3,
    )


def test_plus_full_add_consume_deny_t6_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            _fill_plus_roster(app, monkeypatch)
            await client.get("/playground")
            csrf = client.cookies.get("rtc_csrf") or ""
            resp = await client.post(
                "/playground/laws/ndps/add",
                data={"csrf_token": csrf, "confirm": "add", "scope": "sections"},
                headers={"Accept": "application/json"},
            )
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code in {200, 403}
    _assert_t3_entitlement(
        snap,
        access="roster_full",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=3,
        roster_result="roster_full",
        roster_access_n=2,
    )
    _assert_t6_counts(
        snap.counters,
        db_reads=5,
        db_writes=5,
        roster_reads=4,
    )


def test_plus_full_home_keeps_two_capacity_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            _fill_plus_roster(app, monkeypatch)
            resp = await client.get("/playground")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="allowed",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="roster_full",
        roster_access_n=1,
    )
    assert snap.counters.get("playground_db_writes") == 2
    assert snap.counters.get("playground_roster_reads", 0) >= 5
    reads = snap.counters.get("playground_db_reads", 0)
    writes = snap.counters.get("playground_db_writes", 0)
    assert snap.counters.get("playground_repo_round_trips", 0) == reads + writes


def test_t6_http_omits_sql_and_ids_on_breakdown(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            with caplog.at_level(logging.INFO, logger="uvicorn.error"):
                caplog.clear()
                resp = await client.get("/playground")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    notes = " ".join(snap.notes.values())
    breakdown = "\n".join(_breakdown_messages(caplog))
    blob = f"{notes}\n{snap.path_group}\n{breakdown}\n{snap.counters}"
    assert str(USER) not in blob
    assert USER_EMAIL not in blob
    assert "ndps" not in blob
    assert "SELECT " not in blob
    assert "INSERT " not in blob
    assert "?" not in snap.path_group
    assert "playground_today" not in snap.timings
    assert "playground_calendar" not in snap.timings
    assert snap.timings["playground_home_build"][1] == 1


def test_postgres_overlay_decorator_map_matches_sqlite():
    postgres_map = _assert_postgres_counter_map_matches_sqlite(
        _SRC_PLAYGROUND / "repository.py",
        "SqlitePlaygroundRepository",
        _SRC_PLAYGROUND / "postgres.py",
        "PostgresPlaygroundRepository",
    )
    assert postgres_map["get_item"] == ("read", None)
    assert postgres_map["list_items"] == ("read", None)
    assert postgres_map["list_selection"] == ("read", None)
    assert postgres_map["list_playground_summaries"] == ("read", "summary")
    assert postgres_map["get_progress"] == ("read", "progress")
    assert postgres_map["get_mode_progress"] == ("read", "progress")
    assert postgres_map["get_revision_progress"] == ("read", "revision")
    assert postgres_map["list_due_revisions"] == ("read", "revision")
    assert postgres_map["list_source_scans"] == ("read", "source_review")
    assert postgres_map["add_item"] == ("write", None)
    assert postgres_map["complete_mode"] == ("write", None)
    assert postgres_map["complete_learning_mode_and_transition_if_ready"] == (
        "write",
        None,
    )
    assert "_item_from_row" not in postgres_map
    assert "_mode_from_row" not in postgres_map


def test_postgres_roster_decorator_map_matches_sqlite():
    postgres_map = _assert_postgres_counter_map_matches_sqlite(
        _SRC_PLAYGROUND / "roster" / "repository.py",
        "SqliteRosterRepository",
        _SRC_PLAYGROUND / "roster" / "postgres.py",
        "PostgresRosterRepository",
    )
    assert postgres_map["get_period"] == ("read", "roster")
    assert postgres_map["list_periods"] == ("read", "roster")
    assert postgres_map["get_item"] == ("read", "roster")
    assert postgres_map["list_items"] == ("read", "roster")
    assert postgres_map["count_consumed"] == ("read", "roster")
    assert postgres_map["ensure_period"] == ("write", None)
    assert postgres_map["consume_law"] == ("write", None)
    assert postgres_map["remove_law"] == ("write", None)
    assert postgres_map["apply_rollover"] == ("write", None)
    assert "_ensure_period_locked" not in postgres_map
    assert "_count_consumed_locked" not in postgres_map


def test_postgres_get_item_is_undomain_read():
    overlay, _roster, _svc, _pool = _t7_repos()
    token = begin_request_timings()
    try:
        overlay.get_item(USER, "ndps")
        overlay.list_items(USER)
        overlay.list_selection(USER, "ndps")
        _assert_t6_counts(snapshot_request_counters(), db_reads=3)
    finally:
        reset_request_timings(token)


def test_postgres_list_periods_is_roster_read():
    _overlay, roster, _svc, _pool = _t7_repos()
    token = begin_request_timings()
    try:
        roster.list_periods(USER)
        _assert_t6_counts(
            snapshot_request_counters(), db_reads=1, roster_reads=1
        )
    finally:
        reset_request_timings(token)


def test_postgres_empty_summary_law_ids_still_counts():
    overlay, _roster, _svc, pool = _t7_repos()
    token = begin_request_timings()
    try:
        rows = overlay.list_playground_summaries(
            USER, as_of=playground_today(), law_ids=[]
        )
        assert rows == []
        assert pool.cursor.execute_sql == []
        _assert_t6_counts(
            snapshot_request_counters(), db_reads=1, summary_reads=1
        )
    finally:
        reset_request_timings(token)


def test_postgres_empty_due_revisions_and_scans_still_count():
    overlay, _roster, _svc, pool = _t7_repos()
    token = begin_request_timings()
    try:
        overlay.list_due_revisions(USER, playground_today(), [])
        overlay.list_source_scans(USER, [])
        overlay.list_source_changes(USER, law_ids=[])
        assert pool.cursor.execute_sql == []
        _assert_t6_counts(
            snapshot_request_counters(),
            db_reads=3,
            revision_reads=1,
            source_review_reads=2,
        )
    finally:
        reset_request_timings(token)


def test_postgres_get_revision_progress_is_revision_not_progress():
    overlay, _roster, _svc, _pool = _t7_repos()
    token = begin_request_timings()
    try:
        overlay.get_revision_progress(USER, "ndps", "ndps:section:1")
        _assert_t6_counts(
            snapshot_request_counters(), db_reads=1, revision_reads=1
        )
    finally:
        reset_request_timings(token)


def test_postgres_get_progress_increments_progress_reads():
    overlay, _roster, _svc, _pool = _t7_repos()
    token = begin_request_timings()
    try:
        overlay.get_progress(USER, "ndps", "ndps:section:1")
        overlay.get_mode_progress(USER, "ndps", "ndps:section:1", "read")
        _assert_t6_counts(
            snapshot_request_counters(), db_reads=2, progress_reads=2
        )
    finally:
        reset_request_timings(token)


def test_postgres_add_item_nested_get_item_is_one_write():
    overlay, _roster, _svc, _pool = _t7_repos()
    token = begin_request_timings()
    try:
        overlay.add_item(
            USER, "ndps", source_version="v1", law_source_hash="hash"
        )
        _assert_t6_counts(snapshot_request_counters(), db_writes=1)
    finally:
        reset_request_timings(token)


def test_postgres_complete_mode_nested_is_one_write():
    overlay, _roster, _svc, _pool = _t7_repos(fetchone_queue=[{"n": 0}])
    token = begin_request_timings()
    try:
        with pytest.raises(AssertionError):
            overlay.complete_mode(
                USER,
                "ndps",
                "ndps:section:1",
                "read",
                source_version="v1",
                source_hash="hash",
            )
        _assert_t6_counts(snapshot_request_counters(), db_writes=1)
    finally:
        reset_request_timings(token)


def test_postgres_direct_complete_learning_mode_is_one_write():
    overlay, _roster, _svc, _pool = _t7_repos(fetchone_queue=[{"n": 0}])
    token = begin_request_timings()
    try:
        with pytest.raises(AssertionError):
            overlay.complete_learning_mode_and_transition_if_ready(
                USER,
                "ndps",
                "ndps:section:1",
                "read",
                source_version="v1",
                source_hash="hash",
            )
        _assert_t6_counts(snapshot_request_counters(), db_writes=1)
    finally:
        reset_request_timings(token)


def test_postgres_ensure_period_is_write():
    period = _t7_period_row()
    _overlay, roster, _svc, _pool = _t7_repos(
        fetchone_queue=[period, {"n": 0}, period]
    )
    start, end = playground_month_bounds()
    token = begin_request_timings()
    try:
        roster.ensure_period(
            USER,
            period_start=start,
            period_end=end,
            tier_snapshot="plus",
            law_limit=10,
        )
        _assert_t6_counts(snapshot_request_counters(), db_writes=1)
    finally:
        reset_request_timings(token)


def test_postgres_consume_missing_period_is_still_write():
    _overlay, roster, _svc, _pool = _t7_repos()
    start, _end = playground_month_bounds()
    token = begin_request_timings()
    try:
        result = roster.consume_law(
            USER,
            period_start=start,
            law_id="ndps",
            law_limit=10,
            allow_new=True,
        )
        assert result.status == RESULT_NEW_BLOCKED
        _assert_t6_counts(snapshot_request_counters(), db_writes=1)
    finally:
        reset_request_timings(token)


def test_postgres_capacity_is_one_write_plus_one_read():
    period = _t7_period_row()
    _overlay, _roster, svc, _pool = _t7_repos(
        fetchone_queue=[period, {"n": 0}, period, {"n": 0}]
    )
    token = begin_request_timings()
    try:
        svc.capacity(USER, _plus_open_snap())
        _assert_t6_counts(
            snapshot_request_counters(),
            db_reads=1,
            db_writes=1,
            roster_reads=1,
        )
    finally:
        reset_request_timings(token)


def test_postgres_confirm_add_law_is_two_writes():
    period = _t7_period_row()
    _overlay, _roster, svc, _pool = _t7_repos(
        fetchone_queue=[period, {"n": 0}, period]
    )
    token = begin_request_timings()
    try:
        svc.confirm_add_law(
            USER, "ndps", _plus_open_snap(), can_consume_new_law=True
        )
        _assert_t6_counts(snapshot_request_counters(), db_writes=2)
    finally:
        reset_request_timings(token)


def test_postgres_peek_missing_period_is_one_roster_read():
    _overlay, _roster, svc, _pool = _t7_repos()
    token = begin_request_timings()
    try:
        svc.peek_capacity(USER, _plus_open_snap())
        _assert_t6_counts(
            snapshot_request_counters(), db_reads=1, roster_reads=1
        )
    finally:
        reset_request_timings(token)


def test_postgres_repo_exception_still_increments():
    roster = PostgresRosterRepository(_T7RaisingPool())
    token = begin_request_timings()
    try:
        with pytest.raises(RuntimeError, match="t7-spy-closed"):
            roster.get_period(USER, playground_month_bounds()[0])
        _assert_t6_counts(
            snapshot_request_counters(), db_reads=1, roster_reads=1
        )
    finally:
        reset_request_timings(token)


def test_postgres_repo_records_noop_without_collector():
    overlay, roster, _svc, _pool = _t7_repos()
    overlay.get_item(USER, "ndps")
    roster.get_period(USER, playground_month_bounds()[0])
    period = _t7_period_row()
    _overlay, _roster, svc, _cap_pool = _t7_repos(
        fetchone_queue=[period, {"n": 0}, period, {"n": 0}]
    )
    svc.capacity(USER, _plus_open_snap())
    assert snapshot_request_counters() == {}


def test_postgres_round_trips_equals_reads_plus_writes():
    overlay, roster, _svc, _pool = _t7_repos()
    token = begin_request_timings()
    try:
        overlay.get_item(USER, "ndps")
        overlay.list_playground_summaries(
            USER, as_of=playground_today(), law_ids=[]
        )
        roster.list_periods(USER)
        roster.consume_law(
            USER,
            period_start=playground_month_bounds()[0],
            law_id="ndps",
            law_limit=10,
            allow_new=True,
        )
        counters = snapshot_request_counters()
        reads = counters.get("playground_db_reads", 0)
        writes = counters.get("playground_db_writes", 0)
        assert counters.get("playground_repo_round_trips") == reads + writes
        _assert_t6_counts(
            counters,
            db_reads=3,
            db_writes=1,
            summary_reads=1,
            roster_reads=1,
        )
    finally:
        reset_request_timings(token)


def test_postgres_repo_counters_are_integer_t1_names():
    overlay, roster, _svc, _pool = _t7_repos()
    token = begin_request_timings()
    try:
        overlay.get_item(USER, "ndps")
        overlay.list_playground_summaries(
            USER, as_of=playground_today(), law_ids=[]
        )
        overlay.get_progress(USER, "ndps", "ndps:section:1")
        overlay.get_revision_progress(USER, "ndps", "ndps:section:1")
        overlay.list_source_scans(USER, [])
        roster.list_periods(USER)
        counters = snapshot_request_counters()
        assert set(counters) <= set(REQUEST_COUNTERS)
        assert all(isinstance(value, int) for value in counters.values())
        blob = " ".join(counters)
        assert "SELECT" not in blob
        assert "ndps" not in blob
        assert str(USER) not in blob
        assert "%" not in blob
    finally:
        reset_request_timings(token)


def test_postgres_remove_law_and_apply_rollover_are_writes():
    _overlay, roster, _svc, _pool = _t7_repos()
    start, end = playground_month_bounds()
    token = begin_request_timings()
    try:
        roster.remove_law(USER, period_start=start, law_id="ndps")
        roster.apply_rollover(
            USER,
            period_start=start,
            period_end=end,
            tier_snapshot="plus",
            law_limit=10,
            activate=False,
            keep_ids=[],
            decline_ids=[],
            allowed_ids=frozenset(),
            allow_new_keep=True,
        )
        _assert_t6_counts(snapshot_request_counters(), db_writes=2)
    finally:
        reset_request_timings(token)


def test_t7_does_not_add_names_or_touch_sqlite_http_table():
    assert "playground_roster_writes" not in REQUEST_COUNTERS
    assert REQUEST_COUNTERS[REQUEST_COUNTERS.index("playground_db_reads") :] == (
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


_T8_VIEW_STAGES = (
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
    "playground_admin_diagnostics",
)

_T8_HOME_CONTEXT_KEYS = frozenset(
    {
        "home_view",
        "cards",
        "new_law_notice",
        "roster_path",
        "hard_gate",
        "read_only",
        "plus_playground",
        "halted_playground",
        "halted_gate",
        "halted_header_status",
        "expired_playground",
        "expired_gate",
        "expired_header_status",
    }
)

_T8_GATE_CONTEXT_KEYS = frozenset(
    {
        "gate",
        "playground_gate",
        "hard_gate",
        "title",
        "lede",
        "body",
        "cta_label",
        "cta_href",
        "secondary_label",
        "secondary_href",
        "block_reason",
        "consume_blocked",
        "saved_laws",
        "saved_learned",
        "catalogue_plans",
        "from_price",
        "show_included",
        "pg_gate_stage",
        "selected_tier",
        "gate_selector_plans",
        "gate_continue_label",
        "gate_how_steps",
        "current_plan_tier",
        "guest_gate_values",
        "guest_gate_footnote",
    }
)

_T8_INSTRUMENTATION_MARKERS = (
    "playground_home_build",
    "playground_workspace_build",
    "RequestPerformanceSnapshot",
    "path_group=",
    "Server-Timing",
    "x-perf",
    "total_ms",
)


def _assert_t8_n(timings: dict, stage: str, n: int = 1) -> None:
    assert stage in timings, (stage, timings)
    ms, count = timings[stage]
    assert count == n, (stage, count, n, timings)
    assert ms >= 0


def _assert_t8_absent(timings: dict, *stages: str) -> None:
    for stage in stages:
        assert stage not in timings, (stage, timings)


def _assert_t8_home_stages(snap) -> None:
    _assert_t8_n(snap.timings, "playground_home_build")
    _assert_t8_n(snap.timings, "playground_home_summaries")
    _assert_t8_n(snap.timings, "playground_source_presentations")
    _assert_t8_n(snap.timings, "template")
    _assert_t8_absent(
        snap.timings,
        "playground_workspace_build",
        "playground_today",
        "playground_calendar",
        "playground_source_scan",
        "playground_admin_diagnostics",
    )


def _assert_t8_no_view_stages(snap, *, allow_template: bool = False) -> None:
    for stage in _T8_VIEW_STAGES:
        assert stage not in snap.timings, (stage, snap.timings)
    if not allow_template:
        assert "template" not in snap.timings


def _assert_t9_absent(timings: dict) -> None:
    _assert_t8_absent(timings, "playground_today", "playground_calendar")


def _assert_t9_today_only(snap) -> None:
    _assert_t8_n(snap.timings, "playground_today")
    _assert_t8_absent(snap.timings, "playground_calendar")


def _assert_t9_calendar_only(snap) -> None:
    _assert_t8_n(snap.timings, "playground_calendar")
    _assert_t8_absent(snap.timings, "playground_today")


def _spy_template_contexts(app) -> list[tuple[str, frozenset[str], dict]]:
    templates = app.state.templates
    captured: list[tuple[str, frozenset[str], dict]] = []
    real = templates.TemplateResponse

    def wrapped(request, name, context, *args, **kwargs):
        captured.append((name, frozenset(context.keys()), dict(context)))
        return real(request, name, context, *args, **kwargs)

    templates.TemplateResponse = wrapped
    return captured


def _plus_ndps_on_roster(app) -> None:
    snap_ent = app.state.entitlement_service.resolve(USER)
    assert app.state.roster.confirm_add_law(
        USER, "ndps", snap_ent, can_consume_new_law=True
    ).ok


def _plus_ndps_selected(app) -> None:
    _plus_ndps_on_roster(app)
    persist_entire_act_selection(app.state.playground, USER, "ndps")


def test_plus_empty_home_records_t8_home_stages(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            resp = await client.get("/playground")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="allowed",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="ok",
        roster_access_n=1,
    )
    _assert_t8_home_stages(snap)
    _assert_t6_counts(
        snap.counters,
        db_reads=7,
        db_writes=2,
        roster_reads=5,
        summary_reads=1,
    )
    assert snap.total_ms >= 0
    assert "playground_total" not in snap.timings


@pytest.mark.parametrize(
    "seed, access, disposition",
    [
        (
            lambda app: _seed_subscription(app, tier="max", status="halted"),
            "halted",
            "halted",
        ),
        (
            lambda app: _seed_subscription(app, tier="pro", status="paused"),
            "paused",
            "paused",
        ),
        (
            lambda app: _seed_period_ended_refund(app),
            "paid_period_ended",
            "active",
        ),
    ],
)
def test_read_only_home_records_t8_home_without_t5(
    tmp_path: Path, seed, access, disposition
):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            seed(app)
            resp = await client.get("/playground")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access=access,
        disposition=disposition,
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )
    _assert_t8_home_stages(snap)
    _assert_t6_counts(
        snap.counters,
        db_reads=5,
        roster_reads=3,
        summary_reads=1,
    )


def test_guest_playground_has_template_without_home_build(tmp_path: Path):
    async def _go():
        client, _app = await _async_guest_client(tmp_path)
        try:
            resp = await client.get("/playground")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="guest",
        auth_state="guest",
        device_result="skipped_unpaid",
        device_lookups=0,
    )
    _assert_t8_n(snap.timings, "template")
    _assert_t8_no_view_stages(snap, allow_template=True)
    _assert_t9_absent(snap.timings)
    _assert_t6_absent(snap.counters)


def test_free_playground_has_template_without_home_build(tmp_path: Path):
    async def _go():
        client, _repo = await _async_authed_client(tmp_path)
        try:
            resp = await client.get("/playground")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="free",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )
    _assert_t8_n(snap.timings, "template")
    _assert_t8_no_view_stages(snap, allow_template=True)
    _assert_t9_absent(snap.timings)
    _assert_t6_absent(snap.counters)


@pytest.mark.parametrize("kind", ("pending", "admin"))
def test_pending_and_admin_home_match_plus_empty_t8(tmp_path: Path, kind: str):
    async def _go():
        client, app, repo = await _async_authed_session(tmp_path)
        try:
            if kind == "pending":
                _seed_subscription(app, tier="plus", status="pending")
            else:
                _seed_admin(repo)
            resp = await client.get("/playground")
            return resp, get_last_request_performance(), kind
        finally:
            await client.aclose()

    resp, snap, kind = asyncio.run(_go())
    assert resp.status_code == 200
    if kind == "pending":
        _assert_t3_entitlement(
            snap,
            access="pending",
            disposition="pending",
            auth_state="authed",
            device_result="ok",
            device_lookups=2,
            roster_result="ok",
            roster_access_n=1,
        )
    else:
        _assert_t3_entitlement(
            snap,
            access="allowed",
            auth_state="authed",
            device_result="skipped_unpaid",
            device_lookups=1,
            roster_result="ok",
            roster_access_n=1,
        )
    _assert_t8_home_stages(snap)
    _assert_t6_counts(
        snap.counters,
        db_reads=7,
        db_writes=2,
        roster_reads=5,
        summary_reads=1,
    )


def test_plus_active_workspace_records_t8_workspace_stages(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            _plus_ndps_on_roster(app)
            resp = await client.get("/playground/laws/ndps")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="allowed",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="ok",
        roster_access_n=2,
        law_state="active",
    )
    _assert_t8_n(snap.timings, "playground_workspace_build")
    _assert_t8_n(snap.timings, "playground_selection_read")
    _assert_t8_n(snap.timings, "playground_mode_progress")
    _assert_t8_n(snap.timings, "playground_revision_progress")
    _assert_t8_n(snap.timings, "template")
    _assert_t8_absent(
        snap.timings,
        "playground_home_build",
        "playground_today",
        "playground_calendar",
        "playground_source_scan",
    )
    _assert_t6_counts(
        snap.counters,
        db_reads=11,
        db_writes=1,
        roster_reads=3,
        progress_reads=2,
        revision_reads=1,
        source_review_reads=2,
    )


def test_plus_inactive_workspace_has_no_t8_view_or_template(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            resp = await client.get("/playground/laws/ndps")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 303
    assert resp.headers.get("location") == "/laws/ndps"
    _assert_t3_entitlement(
        snap,
        access="inactive_law",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=2,
        roster_result="inactive_law",
        roster_access_n=2,
    )
    _assert_t8_no_view_stages(snap)
    _assert_t9_absent(snap.timings)
    _assert_t6_counts(
        snap.counters,
        db_reads=4,
        db_writes=1,
        roster_reads=3,
    )


def test_full_roster_consume_deny_has_no_t8_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            _fill_plus_roster(app, monkeypatch)
            await client.get("/playground")
            csrf = client.cookies.get("rtc_csrf") or ""
            resp = await client.post(
                "/playground/laws/ndps/add",
                data={"csrf_token": csrf, "confirm": "add", "scope": "sections"},
                headers={"Accept": "application/json"},
            )
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code in {200, 403}
    _assert_t3_entitlement(
        snap,
        access="roster_full",
        disposition="active",
        auth_state="authed",
        device_result="ok",
        device_lookups=3,
        roster_result="roster_full",
        roster_access_n=2,
    )
    _assert_t8_absent(
        snap.timings,
        "playground_home_build",
        "playground_workspace_build",
        "playground_today",
        "playground_calendar",
    )
    content_type = resp.headers.get("content-type") or ""
    if "application/json" in content_type:
        assert "template" not in snap.timings
    _assert_t6_counts(
        snap.counters,
        db_reads=5,
        db_writes=5,
        roster_reads=4,
    )


def test_dashboard_plus_has_no_t8_playground_view_stages(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            resp = await client.get("/dashboard")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="allowed",
        disposition="active",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )
    _assert_t8_no_view_stages(snap, allow_template=True)
    _assert_t9_today_only(snap)
    _assert_t6_counts(
        snap.counters,
        db_reads=3,
        roster_reads=2,
        revision_reads=1,
    )


@pytest.mark.parametrize(
    "path, extra_absent",
    [
        ("/playground/roster", ("playground_rollover_build",)),
        ("/playground/laws/ndps/sections", ("playground_workspace_build",)),
    ],
)
def test_roster_and_picker_template_without_build_stages(
    tmp_path: Path, path: str, extra_absent: tuple[str, ...]
):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            _plus_ndps_on_roster(app)
            resp = await client.get(path)
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t8_n(snap.timings, "template")
    _assert_t8_absent(
        snap.timings,
        "playground_home_build",
        "playground_workspace_build",
        "playground_today",
        "playground_calendar",
        *extra_absent,
    )
    if path.endswith("/sections"):
        _assert_t8_n(snap.timings, "playground_selection_read")
        _assert_t8_absent(
            snap.timings, "playground_mode_progress", "playground_revision_progress"
        )


def test_home_build_times_duplicate_capacity_not_t5(tmp_path: Path):
    overlay, _roster_repo, roster, _conn = _t6_sqlite(tmp_path)
    token = begin_request_timings()
    try:
        with time_playground_stage("playground_home_build"):
            build_home_view(
                access=_plus_open_access(),
                roster=roster,
                overlay=overlay,
                notice="",
            )
        timings = snapshot_request_timings()
        _assert_t8_n(timings, "playground_home_build")
        _assert_t8_n(timings, "playground_home_summaries")
        _assert_t8_n(timings, "playground_source_presentations")
        assert "playground_roster_access" not in timings
        _assert_t6_counts(
            snapshot_request_counters(),
            db_reads=6,
            db_writes=1,
            roster_reads=4,
            summary_reads=1,
        )
    finally:
        reset_request_timings(token)


def test_empty_summary_law_ids_still_time_home_summaries(tmp_path: Path):
    overlay, _roster_repo, roster, _conn = _t6_sqlite(tmp_path)
    token = begin_request_timings()
    try:
        build_home_view(
            access=_plus_open_access(),
            roster=roster,
            overlay=overlay,
            notice="",
        )
        timings = snapshot_request_timings()
        _assert_t8_n(timings, "playground_home_summaries")
        _assert_t8_n(timings, "playground_source_presentations")
        assert "playground_home_build" not in timings
    finally:
        reset_request_timings(token)


def test_nested_home_summaries_do_not_add_a_second_home_build(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            resp = await client.get("/playground")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t8_n(snap.timings, "playground_home_build")
    _assert_t8_n(snap.timings, "playground_home_summaries")


def test_t8_stage_records_in_finally_on_exception():
    token = begin_request_timings()
    try:
        with pytest.raises(RuntimeError, match="boom"):
            with time_playground_stage("playground_home_build"):
                raise RuntimeError("boom")
        _assert_t8_n(snapshot_request_timings(), "playground_home_build")
    finally:
        reset_request_timings(token)


def test_t8_noop_without_collector(tmp_path: Path):
    with time_playground_stage("playground_home_build"):
        pass
    assert snapshot_request_timings() == {}
    overlay, _roster_repo, roster, _conn = _t6_sqlite(tmp_path)
    build_home_view(
        access=_plus_open_access(),
        roster=roster,
        overlay=overlay,
        notice="",
    )
    assert snapshot_request_timings() == {}
    detect_source_changes(overlay, USER, "ndps")
    assert snapshot_request_timings() == {}


def test_t8_template_bytes_match_unwrapped_render(tmp_path: Path):
    from starlette.requests import Request

    app, _repo = _counting_app(tmp_path)
    templates = app.state.templates
    request = Request(
        {
            "type": "http",
            "asgi": {"spec_version": "2.3", "version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/playground/roster/ndps/remove",
            "raw_path": b"/playground/roster/ndps/remove",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "root_path": "",
            "app": app,
        }
    )
    context = {
        "law_id": "ndps",
        "month_name": "October",
        "short_title": "NDPS",
    }
    token = begin_request_timings()
    try:
        with time_playground_stage("template"):
            timed = templates.TemplateResponse(
                request, "playground_remove.html", dict(context)
            )
        untimed = templates.TemplateResponse(
            request, "playground_remove.html", dict(context)
        )
        assert timed.body == untimed.body
        _assert_t8_n(snapshot_request_timings(), "template")
        body = timed.body.decode("utf-8", "replace")
        for marker in _T8_INSTRUMENTATION_MARKERS:
            assert marker not in body
    finally:
        reset_request_timings(token)


def test_t8_html_omits_stage_names_and_ids(tmp_path: Path, caplog):
    async def _go():
        results = []
        guest, _gapp = await _async_guest_client(tmp_path / "guest")
        try:
            with caplog.at_level(logging.INFO, logger="uvicorn.error"):
                caplog.clear()
                resp = await guest.get("/playground")
            results.append(("guest", resp, get_last_request_performance()))
        finally:
            await guest.aclose()
        client, app, _repo = await _async_authed_session(tmp_path / "plus")
        try:
            _seed_subscription(app, tier="plus", status="active")
            captured = _spy_template_contexts(app)
            resp = await client.get("/playground")
            results.append(("plus_home", resp, get_last_request_performance(), captured[:]))
            _plus_ndps_on_roster(app)
            captured.clear()
            resp = await client.get("/playground/laws/ndps")
            results.append(
                ("plus_workspace", resp, get_last_request_performance(), captured[:])
            )
            return results
        finally:
            await client.aclose()

    results = asyncio.run(_go())
    guest_resp, guest_snap = results[0][1], results[0][2]
    plus_home_resp, plus_home_snap, plus_home_ctx = (
        results[1][1],
        results[1][2],
        results[1][3],
    )
    plus_ws_resp, plus_ws_snap = results[2][1], results[2][2]
    for resp, snap in (
        (guest_resp, guest_snap),
        (plus_home_resp, plus_home_snap),
        (plus_ws_resp, plus_ws_snap),
    ):
        assert resp.status_code == 200
        header_names = {name.lower() for name in resp.headers}
        assert "server-timing" not in header_names
        assert "x-perf" not in header_names
        notes = " ".join(snap.notes.values())
        breakdown = "\n".join(_breakdown_messages(caplog))
        meta = f"{notes}\n{snap.path_group}\n{breakdown}\n{list(snap.timings)}\n{snap.counters}"
        assert str(USER) not in meta
        assert USER_EMAIL not in meta
        body = resp.content.decode("utf-8", "replace")
        for marker in _T8_INSTRUMENTATION_MARKERS:
            assert marker not in body
        assert "SELECT " not in meta
        assert "INSERT " not in meta
        assert "?" not in snap.path_group
    home_names = {name for name, _keys, _ctx in plus_home_ctx}
    assert "playground.html" in home_names
    home_keys = next(
        keys for name, keys, _ctx in plus_home_ctx if name == "playground.html"
    )
    assert home_keys == _T8_HOME_CONTEXT_KEYS
    home_ctx = next(
        ctx for name, _keys, ctx in plus_home_ctx if name == "playground.html"
    )
    for forbidden in _T8_VIEW_STAGES + ("template", "total_ms", "timings"):
        assert forbidden not in home_ctx


def test_t8_gate_context_keyset_frozen(tmp_path: Path):
    async def _go():
        client, app = await _async_guest_client(tmp_path)
        try:
            captured = _spy_template_contexts(app)
            resp = await client.get("/playground")
            return resp, captured
        finally:
            await client.aclose()

    resp, captured = asyncio.run(_go())
    assert resp.status_code == 200
    assert captured
    name, keys, ctx = captured[0]
    assert name == "playground_gate.html"
    assert keys == _T8_GATE_CONTEXT_KEYS
    for forbidden in _T8_VIEW_STAGES + ("template", "total_ms", "timings"):
        assert forbidden not in ctx


def test_t8_does_not_add_vocabulary():
    assert TIMING_STAGES[-len(_PLAYGROUND_STAGES) :] == _PLAYGROUND_STAGES
    for name in (
        "playground_roster_build",
        "playground_picker_build",
        "playground_gate",
        "playground_template",
        "playground_home_template",
        "playground_gate_template",
        "playground_total",
    ):
        assert name not in TIMING_STAGES
        assert name not in REQUEST_COUNTERS
    assert "template" in TIMING_STAGES


def test_middleware_remains_only_total(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            resp = await client.get("/playground")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    assert snap.total_ms >= 0
    assert "playground_total" not in snap.timings
    assert "playground_home_build" in snap.timings


def test_rollover_build_and_write_stages(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            got = await client.get("/playground/roster/next")
            get_snap = get_last_request_performance()
            csrf = client.cookies.get("rtc_csrf") or ""
            posted = await client.post(
                "/playground/roster/next",
                data={"csrf_token": csrf},
            )
            post_snap = get_last_request_performance()
            return got, get_snap, posted, post_snap
        finally:
            await client.aclose()

    got, get_snap, posted, post_snap = asyncio.run(_go())
    assert got.status_code == 200
    _assert_t8_n(get_snap.timings, "playground_rollover_build")
    _assert_t8_n(get_snap.timings, "template")
    _assert_t8_absent(
        get_snap.timings,
        "playground_rollover_write",
        "playground_workspace_build",
        "playground_home_build",
        "playground_today",
        "playground_calendar",
    )
    assert posted.status_code in {303, 400}
    _assert_t8_n(post_snap.timings, "playground_rollover_write")
    _assert_t8_absent(
        post_snap.timings,
        "playground_rollover_build",
        "template",
        "playground_workspace_build",
    )


def test_learning_build_not_revision_on_learn_get(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            _plus_ndps_selected(app)
            resp = await client.get("/playground/laws/ndps/sections/1/learn/read")
            get_snap = get_last_request_performance()
            csrf = client.cookies.get("rtc_csrf") or ""
            started = await client.post(
                "/playground/laws/ndps/sections/1/learn/read/start",
                json={},
                headers={"X-CSRF-Token": csrf, "Accept": "application/json"},
            )
            write_snap = get_last_request_performance()
            return resp, get_snap, started, write_snap
        finally:
            await client.aclose()

    resp, get_snap, started, write_snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t8_n(get_snap.timings, "playground_learning_build")
    _assert_t8_n(get_snap.timings, "template")
    _assert_t8_absent(
        get_snap.timings,
        "playground_revision_build",
        "playground_learning_write",
        "playground_revision_write",
        "playground_home_build",
        "playground_workspace_build",
    )
    assert started.status_code == 200
    _assert_t8_n(write_snap.timings, "playground_learning_write")
    _assert_t8_absent(
        write_snap.timings,
        "playground_revision_write",
        "playground_learning_build",
        "playground_revision_build",
        "template",
    )


def test_revision_build_not_learning_on_due_revision_get(tmp_path: Path):
    from constitution_memorizer.playground.locators import section_locator
    from constitution_memorizer.playground.roster.period import playground_today
    from tests.test_playground_m8 import _seed_progress

    loc = section_locator("ndps", "1").value
    today = playground_today().isoformat()

    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            _plus_ndps_selected(app)
            _seed_progress(
                app.state.playground,
                USER,
                "ndps",
                loc,
                status="review",
                interval_days=3,
                next_revision=today,
                times_completed=1,
                learned_at=today,
            )
            resp = await client.get(
                "/playground/laws/ndps/sections/1/learn/read?revision=1"
            )
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t8_n(snap.timings, "playground_revision_build")
    _assert_t8_n(snap.timings, "template")
    _assert_t8_absent(
        snap.timings,
        "playground_learning_build",
        "playground_revision_write",
        "playground_learning_write",
    )


def test_source_scan_times_detect_source_changes(tmp_path: Path):
    overlay, _roster_repo, _svc, _conn = _t6_sqlite(tmp_path)
    token = begin_request_timings()
    try:
        detect_source_changes(overlay, USER, "ndps")
        assert "playground_source_scan" not in snapshot_request_timings()
    finally:
        reset_request_timings(token)
    overlay.add_item(USER, "ndps", source_version="stale", law_source_hash="stale")
    token = begin_request_timings()
    try:
        detect_source_changes(overlay, USER, "ndps")
        _assert_t8_n(snapshot_request_timings(), "playground_source_scan")
    finally:
        reset_request_timings(token)


def test_source_review_records_stage_without_scan_on_fresh_law(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            _plus_ndps_selected(app)
            resp = await client.get("/playground/laws/ndps/source-review")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t8_n(snap.timings, "playground_source_review")
    _assert_t8_n(snap.timings, "template")
    _assert_t8_absent(
        snap.timings,
        "playground_source_scan",
        "playground_workspace_build",
        "playground_home_build",
    )


def test_admin_user_detail_times_playground_admin_diagnostics(tmp_path: Path):
    async def _go():
        client, app, repo = await _async_authed_session(tmp_path)
        try:
            _seed_admin(repo)
            app.state.admin_enabled = True
            resp = await client.get(f"/admin/users/{USER}")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t8_n(snap.timings, "playground_admin_diagnostics")
    _assert_t8_absent(
        snap.timings,
        "playground_home_build",
        "playground_workspace_build",
        "playground_today",
        "playground_calendar",
    )
    assert snap.path_group == "/admin/users/{user_id}"
    assert str(USER) not in snap.path_group


def test_stage_timer_has_no_route_or_contextvar():
    src = inspect.getsource(time_playground_stage)
    module_path = Path(__file__).resolve().parents[1] / (
        "src/constitution_memorizer/playground/stage_timer.py"
    )
    module_src = module_path.read_text(encoding="utf-8")
    assert "perf_counter" in src
    assert "record_request_timing" in src
    assert "finally:" in src
    assert "ContextVar" not in module_src
    assert "TIMING_STAGES" not in module_src
    assert "/playground" not in module_src


_T9_DASHBOARD_REQUIRED_KEYS = frozenset(
    {
        "today_units",
        "playground_due_units",
        "playground_new_unit",
        "playground_due_count",
        "law_revisions",
        "law_revision_count",
        "plus_today",
        "halted_today",
        "expired_today",
        "dashboard_state",
    }
)
_T9_CALENDAR_REQUIRED_KEYS = frozenset(
    {
        "calendar",
        "week",
        "calendar_view",
        "plus_calendar",
        "halted_calendar",
        "expired_calendar",
    }
)
_T9_INSTRUMENTATION_MARKERS = _T8_INSTRUMENTATION_MARKERS + (
    "playground_today",
    "playground_calendar",
)
_T9_CONTEXT_TIMING_KEYS = _T8_VIEW_STAGES + (
    "playground_today",
    "playground_calendar",
    "template",
    "total_ms",
    "timings",
)


def _assert_t9_dashboard_plus_contract(snap) -> None:
    _assert_t3_entitlement(
        snap,
        access="allowed",
        disposition="active",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )
    _assert_t9_today_only(snap)
    _assert_t8_no_view_stages(snap, allow_template=True)
    _assert_t8_n(snap.timings, "template")
    assert snap.timings["template"][1] == 1
    assert snap.path_group == "/dashboard"
    assert snap.total_ms >= 0
    assert "playground_total" not in snap.timings
    _assert_t6_counts(
        snap.counters,
        db_reads=3,
        roster_reads=2,
        revision_reads=1,
    )


def test_dashboard_plus_records_t9_today_without_calendar(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            resp = await client.get("/dashboard")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t9_dashboard_plus_contract(snap)


def test_dashboard_guest_has_no_t9(tmp_path: Path):
    async def _go():
        client, _app = await _async_guest_client(tmp_path)
        try:
            resp = await client.get("/dashboard")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t9_absent(snap.timings)


def test_dashboard_free_has_no_t9(tmp_path: Path):
    async def _go():
        client, _repo = await _async_authed_client(tmp_path)
        try:
            resp = await client.get("/dashboard")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="free",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )
    _assert_t9_absent(snap.timings)
    _assert_t6_absent(snap.counters)


def test_dashboard_paused_has_no_t9(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="pro", status="paused")
            resp = await client.get("/dashboard")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="paused",
        disposition="paused",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )
    _assert_t9_absent(snap.timings)
    _assert_t6_absent(snap.counters)


@pytest.mark.parametrize(
    "seed, access, disposition",
    [
        (
            lambda app: _seed_subscription(app, tier="max", status="halted"),
            "halted",
            "halted",
        ),
        (
            lambda app: _seed_period_ended_refund(app),
            "paid_period_ended",
            "active",
        ),
    ],
)
def test_dashboard_halted_and_expired_record_t9_today(
    tmp_path: Path, seed, access, disposition
):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            seed(app)
            resp = await client.get("/dashboard")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access=access,
        disposition=disposition,
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )
    _assert_t9_today_only(snap)
    _assert_t8_no_view_stages(snap, allow_template=True)
    _assert_t6_counts(
        snap.counters,
        db_reads=3,
        roster_reads=2,
        revision_reads=1,
    )


@pytest.mark.parametrize("kind", ("pending", "admin"))
def test_dashboard_pending_and_admin_match_plus_t9(tmp_path: Path, kind: str):
    async def _go():
        client, app, repo = await _async_authed_session(tmp_path)
        try:
            if kind == "pending":
                _seed_subscription(app, tier="plus", status="pending")
            else:
                _seed_admin(repo)
            resp = await client.get("/dashboard")
            return resp, get_last_request_performance(), kind
        finally:
            await client.aclose()

    resp, snap, kind = asyncio.run(_go())
    assert resp.status_code == 200
    if kind == "pending":
        _assert_t3_entitlement(
            snap,
            access="pending",
            disposition="pending",
            auth_state="authed",
            device_result="skipped_unpaid",
            device_lookups=1,
        )
    else:
        _assert_t3_entitlement(
            snap,
            access="allowed",
            auth_state="authed",
            device_result="skipped_unpaid",
            device_lookups=1,
        )
    _assert_t9_today_only(snap)
    _assert_t8_no_view_stages(snap, allow_template=True)
    _assert_t6_counts(
        snap.counters,
        db_reads=3,
        roster_reads=2,
        revision_reads=1,
    )


def test_calendar_plus_records_t9_calendar_without_today(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            resp = await client.get("/calendar")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t3_entitlement(
        snap,
        access="allowed",
        disposition="active",
        auth_state="authed",
        device_result="skipped_unpaid",
        device_lookups=1,
    )
    _assert_t9_calendar_only(snap)
    _assert_t8_no_view_stages(snap, allow_template=True)
    _assert_t8_n(snap.timings, "template")
    assert snap.timings["template"][1] == 1
    assert snap.path_group == "/calendar"
    assert snap.total_ms >= 0
    assert "playground_total" not in snap.timings
    _assert_t6_counts(
        snap.counters,
        db_reads=2,
        roster_reads=1,
        revision_reads=1,
    )


def test_calendar_guest_and_free_have_no_t9(tmp_path: Path):
    async def _guest():
        client, _app = await _async_guest_client(tmp_path / "guest")
        try:
            resp = await client.get("/calendar")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    async def _free():
        client, _repo = await _async_authed_client(tmp_path / "free")
        try:
            resp = await client.get("/calendar")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    guest_resp, guest_snap = asyncio.run(_guest())
    free_resp, free_snap = asyncio.run(_free())
    assert guest_resp.status_code == 303
    assert free_resp.status_code == 200
    assert guest_snap is not None
    _assert_t9_absent(guest_snap.timings)
    _assert_t9_absent(free_snap.timings)
    _assert_t6_absent(free_snap.counters)


def test_calendar_paused_has_no_t9(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="pro", status="paused")
            resp = await client.get("/calendar")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t9_absent(snap.timings)
    _assert_t6_absent(snap.counters)


@pytest.mark.parametrize(
    "seed",
    [
        lambda app: _seed_subscription(app, tier="max", status="halted"),
        lambda app: _seed_period_ended_refund(app),
    ],
)
def test_calendar_halted_and_expired_record_t9_calendar(tmp_path: Path, seed):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            seed(app)
            resp = await client.get("/calendar")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t9_calendar_only(snap)
    _assert_t8_no_view_stages(snap, allow_template=True)
    _assert_t6_counts(
        snap.counters,
        db_reads=2,
        roster_reads=1,
        revision_reads=1,
    )


def test_calendar_week_view_times_chips_once(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            resp = await client.get("/calendar?view=week")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t9_calendar_only(snap)
    _assert_t8_n(snap.timings, "playground_calendar")
    _assert_t6_counts(
        snap.counters,
        db_reads=2,
        roster_reads=1,
        revision_reads=1,
    )


def test_playground_routes_still_omit_t9(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            home = await client.get("/playground")
            home_snap = get_last_request_performance()
            _plus_ndps_on_roster(app)
            workspace = await client.get("/playground/laws/ndps")
            workspace_snap = get_last_request_performance()
            return home, home_snap, workspace, workspace_snap
        finally:
            await client.aclose()

    home, home_snap, workspace, workspace_snap = asyncio.run(_go())
    assert home.status_code == 200
    assert workspace.status_code == 200
    _assert_t8_home_stages(home_snap)
    _assert_t9_absent(home_snap.timings)
    _assert_t9_absent(workspace_snap.timings)
    _assert_t6_counts(
        home_snap.counters,
        db_reads=7,
        db_writes=2,
        roster_reads=5,
        summary_reads=1,
    )


def test_google_extra_does_not_record_playground_calendar():
    from constitution_memorizer.playground.schedule import (
        apply_expired_today_hero,
        apply_merged_today_hero,
        attach_playground_calendar_chips,
        merge_today_path,
        reconcile_expired_playground_calendar_chips,
        reconcile_expired_playground_today,
        reconcile_halted_playground_calendar_chips,
        reconcile_halted_playground_today,
    )

    for fn in (
        playground_google_extra,
        playground_projection_extra,
        attach_playground_calendar_chips,
        merge_today_path,
        reconcile_expired_playground_calendar_chips,
        reconcile_halted_playground_calendar_chips,
        reconcile_expired_playground_today,
        reconcile_halted_playground_today,
        apply_merged_today_hero,
        apply_expired_today_hero,
    ):
        assert "time_playground_stage" not in inspect.getsource(fn)


def test_t9_today_skips_timer_on_missing_overlay():
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(playground=None, roster=None))
    )
    token = begin_request_timings()
    try:
        ctx = playground_today_context(request)
        assert ctx["playground_due_count"] == 0
        assert "playground_today" not in snapshot_request_timings()
    finally:
        reset_request_timings(token)


def test_t9_today_empty_plus_still_n_1(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            resp = await client.get("/dashboard")
            return resp, get_last_request_performance()
        finally:
            await client.aclose()

    resp, snap = asyncio.run(_go())
    assert resp.status_code == 200
    _assert_t8_n(snap.timings, "playground_today")
    assert snap.timings["playground_today"][1] == 1


def test_t9_records_in_finally_on_exception(tmp_path: Path, monkeypatch):
    overlay, _roster_repo, roster, _conn = _t6_sqlite(tmp_path)

    def boom_today(*_args, **_kwargs):
        raise RuntimeError("today boom")

    monkeypatch.setattr(
        "constitution_memorizer.playground.schedule.playground_view_access",
        lambda _request: _plus_open_access(),
    )
    monkeypatch.setattr(
        "constitution_memorizer.playground.schedule.law_revision_today_items",
        boom_today,
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(playground=overlay, roster=roster))
    )
    token = begin_request_timings()
    try:
        with pytest.raises(RuntimeError, match="today boom"):
            playground_today_context(request)
        _assert_t8_n(snapshot_request_timings(), "playground_today")
    finally:
        reset_request_timings(token)

    class BoomOverlay:
        def list_revision_schedule(self, *_args, **_kwargs):
            raise RuntimeError("calendar boom")

    class Roster:
        def active_roster_items(self, _user_id):
            return []

    token = begin_request_timings()
    try:
        with pytest.raises(RuntimeError, match="calendar boom"):
            playground_calendar_chips(
                BoomOverlay(),
                Roster(),
                USER,
                month_start=date(2026, 10, 1),
                month_end=date(2026, 10, 31),
                today=date(2026, 10, 9),
            )
        _assert_t8_n(snapshot_request_timings(), "playground_calendar")
    finally:
        reset_request_timings(token)


def test_t9_noop_without_collector(tmp_path: Path):
    overlay, _roster_repo, roster, _conn = _t6_sqlite(tmp_path)
    playground_calendar_chips(
        overlay,
        roster,
        USER,
        month_start=date(2026, 10, 1),
        month_end=date(2026, 10, 31),
        today=date(2026, 10, 9),
    )
    assert snapshot_request_timings() == {}
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(playground=None, roster=None))
    )
    playground_today_context(request)
    assert snapshot_request_timings() == {}


def test_t9_does_not_change_dashboard_or_calendar_context_keys(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            captured = _spy_template_contexts(app)
            dash = await client.get("/dashboard")
            dash_ctx = captured[:]
            captured.clear()
            cal = await client.get("/calendar")
            cal_ctx = captured[:]
            return dash, dash_ctx, cal, cal_ctx
        finally:
            await client.aclose()

    dash, dash_ctx, cal, cal_ctx = asyncio.run(_go())
    assert dash.status_code == 200
    assert cal.status_code == 200
    dash_keys = next(keys for name, keys, _ctx in dash_ctx if name == "dashboard.html")
    cal_keys = next(keys for name, keys, _ctx in cal_ctx if name == "calendar.html")
    assert _T9_DASHBOARD_REQUIRED_KEYS <= dash_keys
    assert _T9_CALENDAR_REQUIRED_KEYS <= cal_keys
    dash_context = next(ctx for name, _keys, ctx in dash_ctx if name == "dashboard.html")
    cal_context = next(ctx for name, _keys, ctx in cal_ctx if name == "calendar.html")
    for forbidden in _T9_CONTEXT_TIMING_KEYS:
        assert forbidden not in dash_context
        assert forbidden not in cal_context


def test_t9_html_omits_stage_names_and_ids(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    async def _go():
        results = []
        guest, _gapp = await _async_guest_client(tmp_path / "guest")
        try:
            resp = await guest.get("/dashboard")
            results.append(("guest_dash", resp, get_last_request_performance()))
        finally:
            await guest.aclose()
        client, app, _repo = await _async_authed_session(tmp_path / "plus")
        try:
            _seed_subscription(app, tier="plus", status="active")
            with caplog.at_level(logging.INFO, logger="uvicorn.error"):
                caplog.clear()
                dash = await client.get("/dashboard")
                results.append(("plus_dash", dash, get_last_request_performance()))
                cal = await client.get("/calendar")
                results.append(("plus_cal", cal, get_last_request_performance()))
            halted_client, halted_app, _hrepo = await _async_authed_session(
                tmp_path / "halted"
            )
            try:
                _seed_subscription(halted_app, tier="max", status="halted")
                halted = await halted_client.get("/dashboard")
                results.append(("halted_dash", halted, get_last_request_performance()))
            finally:
                await halted_client.aclose()
            return results
        finally:
            await client.aclose()

    results = asyncio.run(_go())
    for _label, resp, snap in results:
        assert resp.status_code == 200
        header_names = {name.lower() for name in resp.headers}
        assert "server-timing" not in header_names
        assert "x-perf" not in header_names
        notes = " ".join(snap.notes.values())
        breakdown = "\n".join(_breakdown_messages(caplog))
        meta = (
            f"{notes}\n{snap.path_group}\n{breakdown}\n"
            f"{list(snap.timings)}\n{snap.counters}"
        )
        assert str(USER) not in meta
        assert USER_EMAIL not in meta
        body = resp.content.decode("utf-8", "replace")
        for marker in _T9_INSTRUMENTATION_MARKERS:
            assert marker not in body
        assert "SELECT " not in meta
        assert "INSERT " not in meta
        assert "?" not in snap.path_group


def test_t9_does_not_add_vocabulary():
    assert "playground_today" in TIMING_STAGES
    assert "playground_calendar" in TIMING_STAGES
    for name in (
        "playground_today_build",
        "playground_today_context",
        "playground_calendar_chips",
        "playground_calendar_build",
        "playground_google",
        "playground_projection",
        "playground_hero",
        "playground_total",
    ):
        assert name not in TIMING_STAGES
        assert name not in REQUEST_COUNTERS
    assert TIMING_STAGES[-len(_PLAYGROUND_STAGES) :] == _PLAYGROUND_STAGES


def test_t9_does_not_double_wrap_template(tmp_path: Path):
    async def _go():
        client, app, _repo = await _async_authed_session(tmp_path)
        try:
            _seed_subscription(app, tier="plus", status="active")
            dash = await client.get("/dashboard")
            dash_snap = get_last_request_performance()
            cal = await client.get("/calendar")
            cal_snap = get_last_request_performance()
            return dash, dash_snap, cal, cal_snap
        finally:
            await client.aclose()

    dash, dash_snap, cal, cal_snap = asyncio.run(_go())
    assert dash.status_code == 200
    assert cal.status_code == 200
    assert dash_snap.timings["template"][1] == 1
    assert cal_snap.timings["template"][1] == 1

