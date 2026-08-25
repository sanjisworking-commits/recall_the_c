"""Request-scoped diagnostic timings for Learn and browse-article routes."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import LEARN_MODES, ProgressRepository
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.request_context import wants_request_breakdown

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"

from tests.quiz_helpers import complete_all_modes  # noqa: E402
USER = UUID("11111111-1111-4111-8111-111111111111")
USER_EMAIL = "a@example.com"


class CountingProgressRepo:
    """Wraps a real SQLite repo and counts Learn-relevant repository methods."""

    def __init__(self, inner: ProgressRepository) -> None:
        self.inner = inner
        self.get_progress_calls = 0
        self.list_all_progress_calls = 0
        self.list_due_calls = 0
        self.load_request_bootstrap_calls = 0
        self.load_completion_state_calls = 0
        self.commit_completion_calls = 0
        self.list_split_preferences_calls = 0
        self.set_split_preference_calls = 0
        self.mark_mode_seen_calls = 0
        self.modes_seen_calls = 0
        self.modes_complete_calls = 0
        self.ensure_progress_calls = 0
        self.upsert_progress_calls = 0
        self.clear_modes_seen_calls = 0
        self.get_gloss_calls = 0
        self.get_theme_calls = 0

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

    def load_request_bootstrap(self, user_id, **kwargs):
        self.load_request_bootstrap_calls += 1
        return self.inner.load_request_bootstrap(user_id, **kwargs)

    def load_completion_state(self, user_id, unit_id: str):
        self.load_completion_state_calls += 1
        return self.inner.load_completion_state(user_id, unit_id)

    def commit_completion(self, user_id, unit_id: str, progress, **kwargs):
        self.commit_completion_calls += 1
        return self.inner.commit_completion(user_id, unit_id, progress, **kwargs)

    def list_split_preferences(self, user_id):
        self.list_split_preferences_calls += 1
        return self.inner.list_split_preferences(user_id)

    def set_split_preference(self, user_id, parent_clause_id: str, mode: str):
        self.set_split_preference_calls += 1
        return self.inner.set_split_preference(user_id, parent_clause_id, mode)

    def mark_mode_seen(self, user_id, unit_id: str, mode: str):
        self.mark_mode_seen_calls += 1
        return self.inner.mark_mode_seen(user_id, unit_id, mode)

    def modes_seen(self, user_id, unit_id: str):
        self.modes_seen_calls += 1
        return self.inner.modes_seen(user_id, unit_id)

    def modes_complete(self, user_id, unit_id: str):
        self.modes_complete_calls += 1
        return self.inner.modes_complete(user_id, unit_id)

    def ensure_progress(self, user_id, unit_id: str):
        self.ensure_progress_calls += 1
        return self.inner.ensure_progress(user_id, unit_id)

    def upsert_progress(self, user_id, **kwargs):
        self.upsert_progress_calls += 1
        return self.inner.upsert_progress(user_id, **kwargs)

    def clear_modes_seen(self, user_id, unit_id: str):
        self.clear_modes_seen_calls += 1
        return self.inner.clear_modes_seen(user_id, unit_id)

    def get_gloss(self, user_id, article_number: str):
        self.get_gloss_calls += 1
        return self.inner.get_gloss(user_id, article_number)

    def get_theme(self, user_id):
        self.get_theme_calls += 1
        return self.inner.get_theme(user_id)

    def snapshot(self) -> dict[str, int]:
        return {
            "get_progress": self.get_progress_calls,
            "list_all_progress": self.list_all_progress_calls,
            "list_due": self.list_due_calls,
            "load_request_bootstrap": self.load_request_bootstrap_calls,
            "load_completion_state": self.load_completion_state_calls,
            "commit_completion": self.commit_completion_calls,
            "list_split_preferences": self.list_split_preferences_calls,
            "set_split_preference": self.set_split_preference_calls,
            "mark_mode_seen": self.mark_mode_seen_calls,
            "modes_seen": self.modes_seen_calls,
            "modes_complete": self.modes_complete_calls,
            "ensure_progress": self.ensure_progress_calls,
            "upsert_progress": self.upsert_progress_calls,
            "clear_modes_seen": self.clear_modes_seen_calls,
            "get_gloss": self.get_gloss_calls,
            "get_theme": self.get_theme_calls,
        }

    def reset_counts(self) -> None:
        for key in self.snapshot():
            setattr(self, f"{key}_calls", 0)


def _settings() -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None,
        APP_ENV="test",
        MULTIUSER_ENABLED="true",
        AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true",
        SESSION_SECRET="test-secret",
        SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon",
        DATABASE_URL="",
        COOKIE_SECURE="false",
    )


def _counting_client(tmp_path: Path) -> tuple[TestClient, CountingProgressRepo]:
    clear_settings_cache()
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


def test_wants_request_breakdown_paths():
    assert wants_request_breakdown("/dashboard") is True
    assert wants_request_breakdown("/browse") is True

    assert wants_request_breakdown("/browse/article/20") is True
    assert wants_request_breakdown("/browse/article/20/gloss") is False

    assert wants_request_breakdown("/learn/clause-1") is True
    assert wants_request_breakdown("/learn/clause-2/choose") is True
    assert wants_request_breakdown("/learn/clause-1/seen") is True
    assert wants_request_breakdown("/learn/clause-1/done") is True

    assert wants_request_breakdown("/learn/clause-1/again") is False
    assert wants_request_breakdown("/learn/clause-1/reset") is False

    assert wants_request_breakdown("/settings") is True
    assert wants_request_breakdown("/pricing") is True
    assert wants_request_breakdown("/calendar") is True
    assert wants_request_breakdown("/calendar/google/connect") is True
    assert wants_request_breakdown("/calendar/google/callback") is True
    assert wants_request_breakdown("/calendar/google/preferences") is True
    assert wants_request_breakdown("/calendar/google/disconnect") is True
    assert wants_request_breakdown("/calendar/google/retry") is False
    assert wants_request_breakdown("/health") is False
    assert wants_request_breakdown("/static/styles.css") is False


def test_learn_get_records_expected_stages(tmp_path: Path, caplog):
    client, repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.get("/learn/clause-1")
    assert resp.status_code == 200
    messages = _breakdown_messages(caplog)
    assert len(messages) == 1
    line = messages[0]
    assert "path=/learn/clause-1" in line
    assert "auth_session_n=1" in line
    assert "request_bootstrap_n=1" in line
    assert "mode_seen_write_n=1" in line
    assert "learn_build_n=" in line
    assert "template_n=" in line
    assert "progress_preload_n=" not in line
    assert "split_prefs_n=" not in line
    assert "theme_n=" not in line
    assert repo.mark_mode_seen_calls == 1
    assert repo.list_all_progress_calls == 0
    assert repo.load_request_bootstrap_calls == 1


def test_learn_split_redirect_skips_page_stages(tmp_path: Path, caplog):
    client, repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.get("/learn/clause-2", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/learn/clause-2/choose"
    messages = _breakdown_messages(caplog)
    assert len(messages) == 1
    line = messages[0]
    assert "path=/learn/clause-2" in line
    assert "auth_session_n=1" in line
    assert "request_bootstrap_n=1" in line
    assert "learn_build_" not in line
    assert "template_" not in line
    assert "mode_seen_write_" not in line
    assert repo.mark_mode_seen_calls == 0
    assert repo.set_split_preference_calls == 0
    assert repo.load_request_bootstrap_calls == 1


def test_choose_get_shows_chooser(tmp_path: Path, caplog):
    client, repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.get("/learn/clause-2/choose")
    assert resp.status_code == 200
    messages = _breakdown_messages(caplog)
    assert len(messages) == 1
    line = messages[0]
    assert "path=/learn/clause-2/choose" in line
    assert "request_bootstrap_n=1" in line
    assert "completion_n=1" in line
    assert "template_n=" in line
    assert "split_write_" not in line
    assert "split_prefs_n=" not in line
    assert "progress_preload_n=" not in line
    assert "theme_n=" not in line
    assert repo.set_split_preference_calls == 0
    assert repo.load_request_bootstrap_calls == 1
    assert repo.list_split_preferences_calls == 0
    assert repo.list_all_progress_calls == 0
    assert repo.get_theme_calls == 0


def test_choose_post_writes_preference(tmp_path: Path, caplog):
    client, repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.post(
            "/learn/clause-2/choose",
            data={"mode": "letters"},
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/learn/clause-2-a"
    messages = _breakdown_messages(caplog)
    assert len(messages) == 1
    line = messages[0]
    assert "path=/learn/clause-2/choose" in line
    assert "split_write_n=1" in line
    assert "letters" not in line
    assert "request_bootstrap_n=" not in line
    assert "split_prefs_n=" not in line
    assert repo.set_split_preference_calls == 1
    assert repo.load_request_bootstrap_calls == 0
    assert repo.list_split_preferences_calls == 0


def test_seen_post_is_json_write(tmp_path: Path, caplog):
    client, repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.post("/learn/clause-1/seen", data={"mode": "cloze"})
    assert resp.status_code == 200
    messages = _breakdown_messages(caplog)
    assert len(messages) == 1
    line = messages[0]
    assert "path=/learn/clause-1/seen" in line
    assert "mode_seen_write_n=1" in line
    assert "template_" not in line
    assert "cloze" not in line
    assert repo.mark_mode_seen_calls == 1


def test_incomplete_done_redirects_and_times_mode_reads(tmp_path: Path, caplog):
    client, repo = _counting_client(tmp_path)
    # Claim Article 20 up front (marker set) so Done follows the claimed-Article
    # path: no claim prompt and no grandfather backfill in the measured request.
    repo.claim_article(USER, "20")
    repo.set_setting(USER, "free_articles_backfilled", "1")
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.post("/learn/clause-1/done", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/learn/clause-1"
    messages = _breakdown_messages(caplog)
    assert len(messages) == 1
    line = messages[0]
    assert "path=/learn/clause-1/done" in line
    assert "completion_state_n=1" in line
    assert "completion_commit_" not in line
    assert "modes_seen_" not in line
    assert "progress_ensure_" not in line
    assert "progress_update_" not in line
    assert "modes_clear_write_" not in line
    assert repo.load_completion_state_calls == 1
    assert repo.commit_completion_calls == 0
    assert repo.upsert_progress_calls == 0
    assert repo.clear_modes_seen_calls == 0
    assert repo.ensure_progress_calls == 0


def test_complete_done_records_schedule_leaves(tmp_path: Path, caplog):
    client, repo = _counting_client(tmp_path)
    # Claimed Article + backfill marker: Done persists without a claim prompt.
    repo.claim_article(USER, "20")
    repo.set_setting(USER, "free_articles_backfilled", "1")
    complete_all_modes(client, MINI_UNITS, "clause-1")
    repo.reset_counts()
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.post("/learn/clause-1/done", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/learn/clause-2/choose?done=clause-1"
    messages = _breakdown_messages(caplog)
    assert len(messages) == 1
    line = messages[0]
    assert "path=/learn/clause-1/done" in line
    assert "completion_state_n=1" in line
    assert "completion_commit_n=1" in line
    assert "done_schedule_n=1" in line
    assert "progress_ensure_" not in line
    assert "progress_preload_" not in line
    assert "progress_update_" not in line
    assert "modes_clear_write_" not in line
    assert "modes_seen_" not in line
    assert repo.load_completion_state_calls == 1
    assert repo.commit_completion_calls == 1
    assert repo.ensure_progress_calls == 0
    assert repo.upsert_progress_calls == 0
    assert repo.clear_modes_seen_calls == 0
    assert repo.list_all_progress_calls == 0
    assert repo.load_request_bootstrap_calls == 0


def test_browse_article_records_parent_and_gloss(tmp_path: Path, caplog):
    client, repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        resp = client.get("/browse/article/20")
    assert resp.status_code == 200
    messages = _breakdown_messages(caplog)
    assert len(messages) == 1
    line = messages[0]
    assert "path=/browse/article/20" in line
    assert "auth_session_n=1" in line
    assert "article_build_n=1" in line
    assert "gloss_read_n=1" in line
    assert "template_n=" in line
    assert "mode_seen_write_" not in line
    assert "request_bootstrap" not in line
    assert repo.load_request_bootstrap_calls == 0
    assert repo.get_gloss_calls == 1
    if repo.get_progress_calls == 0:
        assert repo.list_all_progress_calls == 0
        assert "progress_preload_" not in line
    else:
        assert repo.list_all_progress_calls == 1
        assert "progress_preload_n=1" in line


def test_health_and_static_remain_silent(tmp_path: Path, caplog):
    client, _repo = _counting_client(tmp_path)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        assert client.get("/health").status_code == 200
        assert client.get("/static/styles.css").status_code == 200
        joined = " ".join(record.getMessage() for record in caplog.records)
    assert "request method=" not in joined
    assert "request_breakdown" not in joined


def test_learn_logs_omit_sensitive_data(tmp_path: Path, caplog):
    client, _repo = _counting_client(tmp_path)
    session_cookie = client.cookies.get("rtc_session") or ""
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        caplog.clear()
        page = client.get("/learn/clause-1?mode=cloze&done=clause-1")
        seen = client.post("/learn/clause-1/seen", data={"mode": "cloze"})
        choose = client.post(
            "/learn/clause-2/choose",
            data={"mode": "whole"},
            follow_redirects=False,
        )
    assert page.status_code == 200
    assert seen.status_code == 200
    assert choose.status_code == 303
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "request_breakdown" in joined
    assert "path=/learn/clause-1" in joined
    assert "path=/learn/clause-1/seen" in joined
    assert "path=/learn/clause-2/choose" in joined
    assert "mode=cloze" not in joined
    assert "done=clause-1" not in joined
    assert "?" not in joined
    assert "whole" not in joined
    assert str(USER) not in joined
    assert USER_EMAIL not in joined
    if session_cookie:
        assert session_cookie not in joined
    assert "cookie" not in joined.lower()
    assert "token" not in joined.lower()
    assert "phone" not in joined.lower()
