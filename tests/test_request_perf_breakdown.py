"""Request-scoped diagnostic timings for Dashboard and Browse."""

from __future__ import annotations

import logging
from pathlib import Path
from time import perf_counter
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
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
    begin_request_timings,
    normalize_request_path_group,
    record_request_counter,
    record_request_note,
    record_request_timing,
    reset_request_timings,
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


def _counting_client(tmp_path: Path) -> tuple[TestClient, CountingProgressRepo]:
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
