"""Diagnostics for the four Laws routes.

These pages render no user data, so the question they have to answer in
production is why they ever cost more than a template render. Two things make
that answerable: the breakdown line is emitted for /laws at all, and it says
whether the request was a guest or signed in.
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import (
    MultiUserSettings,
    clear_settings_cache,
)
from constitution_memorizer.web import bare_acts
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.request_context import (
    begin_request_timings,
    record_request_counter,
    reset_request_timings,
    snapshot_request_counters,
    snapshot_request_notes,
    wants_request_breakdown,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")

LAWS_PATHS = (
    "/laws",
    "/laws/ndps",
    "/laws/ndps/section/1",
    "/laws/ndps/section/7A",
    "/laws/ndps/schedule/psychotropic-substances",
)


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


def _client(tmp_path: Path, *, signed_in: bool) -> TestClient:
    provider = FakeAuthProvider()
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
            multiuser=True,
            multiuser_settings=_settings(),
            auth_provider=provider,
            session_store=InMemorySessionStore(),
        )
    )
    if signed_in:
        provider.seed_google_user(
            user_id=USER, email="a@example.com", display_name="A"
        )
        start = client.get("/auth/google/start", follow_redirects=False)
        state = start.cookies.get("rtc_oauth_state")
        client.get(
            f"/auth/callback?code=fake-google-code&state={state}",
            follow_redirects=False,
        )
    return client


def _breakdowns(caplog: logging.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("request_breakdown ")
    ]


# ── The gate ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", LAWS_PATHS)
def test_laws_paths_want_a_breakdown(path: str):
    """Without this every record_request_timing on /laws is a silent no-op."""
    assert wants_request_breakdown(path)


def test_the_gate_did_not_widen_to_everything():
    assert not wants_request_breakdown("/")
    assert not wants_request_breakdown("/tables")
    assert not wants_request_breakdown("/lawsuit")


# ── Guest vs authenticated ────────────────────────────────────────────────


@pytest.mark.parametrize("path", LAWS_PATHS)
def test_guest_laws_request_reads_nothing(
    tmp_path: Path, path: str, caplog: logging.LogCaptureFixture
):
    """The regression guard for the whole diagnosis: guests pay no DB."""
    client = _client(tmp_path, signed_in=False)
    client.get(path)  # warm the Act cache
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        assert client.get(path).status_code == 200
    line = _breakdowns(caplog)[0]
    assert "auth_state=guest" in line
    # No user-scoped read is even attempted, so none of the three nav stages
    # can appear.
    assert "db_reads=" not in line
    assert "theme_ms" not in line
    assert "onboarding_setting_ms" not in line
    assert "nav_due_ms" not in line


def test_signed_in_laws_request_names_all_three_nav_reads(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    """theme + onboarding + due-count must be separately visible.

    Onboarding had no stage at all before this change, so the middle of the
    three suspected waits could not be measured even after deploying.
    """
    client = _client(tmp_path, signed_in=True)
    client.get("/laws/ndps")
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        assert client.get("/laws/ndps").status_code == 200
    line = _breakdowns(caplog)[0]
    assert "path=/laws/ndps" in line
    assert "auth_state=authed" in line
    assert "theme_ms=" in line
    assert "onboarding_setting_ms=" in line
    assert "nav_due_ms=" in line
    assert "template_ms=" in line


def test_a_stage_means_a_real_read_not_merely_a_call(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    """Both stages are recorded on the repo path only, like get_theme.

    A page that already loaded settings in one batch must not report these as
    time spent, or the log would say a cache hit cost something.
    """
    client = _client(tmp_path, signed_in=True)
    client.get("/browse")
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        assert client.get("/browse").status_code == 200
    line = _breakdowns(caplog)[0]
    assert "request_bootstrap_n=1" in line
    assert "theme_ms" not in line
    assert "onboarding_setting_ms" not in line


# ── Act cache diagnostics ─────────────────────────────────────────────────


def test_first_touch_is_a_miss_and_the_next_is_a_hit(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    bare_acts._load_cached.cache_clear()
    client = _client(tmp_path, signed_in=False)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        client.get("/laws/ndps")
        first = _breakdowns(caplog)[0]
        caplog.clear()
        client.get("/laws/ndps")
        second = _breakdowns(caplog)[0]
    assert "bare_act_cache=miss" in first
    assert "bare_act_load_ms=" in first
    assert "bare_act_cache_misses=1" in first
    assert "bare_act_cache=hit" in second
    assert "bare_act_load_ms" not in second


def test_the_act_cache_is_shared_across_all_four_routes(
    tmp_path: Path, caplog: logging.LogCaptureFixture
):
    """Only the first Laws request on a process can be a genuine miss.

    This is why a later route must not be called "cold" merely because it is
    its first URL hit.
    """
    bare_acts._load_cached.cache_clear()
    client = _client(tmp_path, signed_in=False)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        client.get("/laws")
        assert "bare_act_cache=miss" in _breakdowns(caplog)[0]
        for path in LAWS_PATHS[1:]:
            caplog.clear()
            client.get(path)
            assert "bare_act_cache=hit" in _breakdowns(caplog)[0], path


def test_cache_diagnostics_are_request_local():
    """Derived from this request's own counter, never from cache_info().

    `functools.lru_cache` takes no lock across the call, so two concurrent
    first-touch callers may each run the loader body and each honestly record a
    miss. What must never happen is one request reading another's counter.
    """
    outer = begin_request_timings()
    try:
        record_request_counter("bare_act_cache_misses", 1)
        assert snapshot_request_counters()["bare_act_cache_misses"] == 1
        inner = begin_request_timings()
        try:
            # A fresh collector: the outer request's miss is not visible here.
            assert snapshot_request_counters() == {}
            bare_acts.get_bare_act("ndps")
            assert snapshot_request_notes()["bare_act_cache"] in {"hit", "miss"}
        finally:
            reset_request_timings(inner)
    finally:
        reset_request_timings(outer)


def test_diagnostics_are_silent_outside_a_request():
    bare_acts._load_cached.cache_clear()
    assert bare_acts.get_bare_act("ndps") is not None
    assert snapshot_request_counters() == {}
    assert snapshot_request_notes() == {}
