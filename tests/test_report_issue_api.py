"""V1 Report Issue API — validation + insert via injected fake repository."""

from __future__ import annotations

import inspect
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.auth.exceptions import AuthConfigError
from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.reports.repository import (
    IssueReport,
    PostgresIssueReportRepository,
)
from constitution_memorizer.reports.turnstile import (
    TurnstileRejectedError,
    TurnstileUnavailableError,
    TurnstileVerifier,
)
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
FIXED_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")


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


class FakeIssueReportRepository:
    """In-memory stand-in; records create_report kwargs."""

    def __init__(self, *, fail: bool = False, status: str = "new") -> None:
        self.calls: list[dict] = []
        self.fail = fail
        self.status = status

    def create_report(self, **kwargs) -> IssueReport:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("simulated database failure: connection refused")
        return IssueReport(
            id=FIXED_ID,
            status=self.status,
            created_at=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
        )


class FakeIssueReportNotifier:
    """Records send calls; optionally raises."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[dict] = []
        self.fail = fail

    async def send(self, *, report, payload) -> str | None:
        self.calls.append({"report": report, "payload": payload})
        if self.fail:
            raise RuntimeError("simulated Resend failure: API key re_secret_leak")
        return "email_fake"


class FakeTurnstileVerifier:
    """Records verify calls; optionally rejects or is unavailable."""

    def __init__(self, *, outcome: str = "ok") -> None:
        self.calls: list[str] = []
        self.outcome = outcome

    async def verify(self, token: str, **kwargs) -> None:
        self.calls.append(token)
        if self.outcome == "reject":
            raise TurnstileRejectedError("Turnstile verification failed")
        if self.outcome == "unavailable":
            raise TurnstileUnavailableError("Turnstile verification request failed")


def _turnstile_settings(**overrides) -> MultiUserSettings:
    base = {
        "REPORT_TURNSTILE_ENABLED": "true",
        "REPORT_TURNSTILE_SITE_KEY": "test_site_key",
        "REPORT_TURNSTILE_SECRET_KEY": "test_secret_key_do_not_leak",
    }
    base.update(overrides)
    return _settings(**base)


def _login(
    client: TestClient,
    provider: FakeAuthProvider,
    *,
    email: str = "reader@example.com",
) -> None:
    if email not in provider.google_users:
        provider.seed_google_user(email=email, display_name="Reporter")
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )


def _client(
    tmp_path: Path,
    *,
    repo: FakeIssueReportRepository | None | object = ...,
    notifier: FakeIssueReportNotifier | None | object = ...,
    turnstile: FakeTurnstileVerifier | None | object = ...,
    settings: MultiUserSettings | None = None,
    multiuser: bool = True,
    as_guest: bool = False,
    user_email: str = "reader@example.com",
    auth_provider: FakeAuthProvider | None = None,
) -> TestClient:
    provider = auth_provider or FakeAuthProvider()
    kwargs: dict = {
        "units_path": MINI_UNITS,
        "db_path": tmp_path / "progress.db",
        "multiuser": multiuser,
        "multiuser_settings": settings or _settings(),
        "auth_provider": provider,
        "session_store": InMemorySessionStore(),
    }
    if repo is not ...:
        kwargs["issue_report_repo"] = repo
    if notifier is not ...:
        kwargs["issue_report_notifier"] = notifier
    if turnstile is not ...:
        kwargs["issue_report_turnstile_verifier"] = turnstile
    client = TestClient(create_app(**kwargs))
    if multiuser and not as_guest:
        _login(client, provider, email=user_email)
    return client


def _valid_body(**overrides) -> dict:
    body = {
        "article_number": "55",
        "section": "Browse Article",
        "selected_text": "Population means...",
        "issue_type": "incorrect_fact",
        "description": "This appears to use the wrong census reference.",
        "suggested_correction": "Suggested wording...",
        "source_url": "https://example.com/source",
        "page_url": "/browse/article/55",
    }
    body.update(overrides)
    return body


def test_valid_report_returns_201_with_uuid_and_new_status(tmp_path: Path):
    repo = FakeIssueReportRepository()
    client = _client(tmp_path, repo=repo)
    resp = client.post("/api/report-issue", json=_valid_body())
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["report_id"] == str(FIXED_ID)
    assert data["status"] == "new"
    UUID(data["report_id"])  # valid UUID
    assert len(repo.calls) == 1
    assert repo.calls[0]["issue_type"] == "incorrect_fact"
    assert repo.calls[0]["description"].startswith("This appears")


def test_optional_fields_can_be_omitted(tmp_path: Path):
    repo = FakeIssueReportRepository()
    client = _client(tmp_path, repo=repo)
    resp = client.post(
        "/api/report-issue",
        json={
            "issue_type": "typo",
            "description": "Missing hyphen in Bare Act quote.",
            "page_url": "/browse/article/21",
        },
    )
    assert resp.status_code == 201
    call = repo.calls[0]
    assert call["article_number"] is None
    assert call["section"] is None
    assert call["selected_text"] is None
    assert call["suggested_correction"] is None
    assert call["source_url"] is None
    # Server fills reporter_email from the signed-in session.
    assert call["reporter_email"] == "reader@example.com"
    assert call["page_url"] == "/browse/article/21"


def test_invalid_issue_type_rejected(tmp_path: Path):
    repo = FakeIssueReportRepository()
    client = _client(tmp_path, repo=repo)
    resp = client.post(
        "/api/report-issue",
        json=_valid_body(issue_type="not_a_real_type"),
    )
    assert resp.status_code == 422
    assert repo.calls == []


def test_missing_description_rejected(tmp_path: Path):
    repo = FakeIssueReportRepository()
    client = _client(tmp_path, repo=repo)
    body = _valid_body()
    del body["description"]
    resp = client.post("/api/report-issue", json=body)
    assert resp.status_code == 422
    assert repo.calls == []


def test_blank_description_rejected(tmp_path: Path):
    repo = FakeIssueReportRepository()
    client = _client(tmp_path, repo=repo)
    resp = client.post(
        "/api/report-issue",
        json=_valid_body(description="   "),
    )
    assert resp.status_code == 422
    assert repo.calls == []


def test_missing_page_url_rejected(tmp_path: Path):
    repo = FakeIssueReportRepository()
    client = _client(tmp_path, repo=repo)
    body = _valid_body()
    del body["page_url"]
    resp = client.post("/api/report-issue", json=body)
    assert resp.status_code == 422
    assert repo.calls == []


def test_invalid_reporter_email_rejected(tmp_path: Path):
    repo = FakeIssueReportRepository()
    client = _client(tmp_path, repo=repo)
    resp = client.post(
        "/api/report-issue",
        json=_valid_body(reporter_email="not-an-email"),
    )
    assert resp.status_code == 422
    assert repo.calls == []


def test_empty_reporter_email_treated_as_absent(tmp_path: Path):
    repo = FakeIssueReportRepository()
    client = _client(tmp_path, repo=repo)
    resp = client.post(
        "/api/report-issue",
        json=_valid_body(reporter_email="  "),
    )
    assert resp.status_code == 201
    # Blank client email is ignored; session email wins.
    assert repo.calls[0]["reporter_email"] == "reader@example.com"


def test_repository_unavailable_returns_503(tmp_path: Path):
    client = _client(tmp_path, repo=None)
    resp = client.post("/api/report-issue", json=_valid_body())
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Unable to submit report right now."


def test_database_failure_returns_generic_503(tmp_path: Path):
    repo = FakeIssueReportRepository(fail=True)
    client = _client(tmp_path, repo=repo)
    resp = client.post("/api/report-issue", json=_valid_body())
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail == "Unable to submit report right now."
    assert "psycopg" not in detail.lower()
    assert "connection refused" not in detail.lower()
    assert "simulated" not in detail.lower()


def test_guest_post_in_multiuser_returns_401(tmp_path: Path):
    repo = FakeIssueReportRepository()
    notifier = FakeIssueReportNotifier()
    verifier = FakeTurnstileVerifier()
    client = _client(
        tmp_path,
        repo=repo,
        notifier=notifier,
        turnstile=verifier,
        as_guest=True,
        settings=_turnstile_settings(),
    )
    resp = client.post("/api/report-issue", json=_valid_body(), follow_redirects=False)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Sign in to report an issue."
    assert repo.calls == []
    assert notifier.calls == []
    assert verifier.calls == []


def test_repository_sql_is_parameterized():
    source = inspect.getsource(PostgresIssueReportRepository.create_report)
    assert "%s" in source
    assert "RETURNING id, status, created_at" in source
    # No f-string / format interpolation of user fields into SQL.
    assert 'f"' not in source
    assert ".format(" not in source
    # Nine placeholders for the nine inserted columns.
    assert source.count("%s") >= 9
    assert re.search(
        r"INSERT INTO issue_reports\s*\(",
        source,
        re.IGNORECASE,
    )


def test_create_app_wires_postgres_repo_from_database_url(tmp_path: Path):
    from unittest.mock import MagicMock, patch

    dsn = "postgresql://user:pass@localhost:5432/testdb"
    sentinel = MagicMock(name="issue_report_repo")
    with patch(
        "constitution_memorizer.web.app.PostgresIssueReportRepository",
        return_value=sentinel,
    ) as ctor:
        app = create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
            multiuser=False,
            multiuser_settings=_settings(DATABASE_URL=dsn),
            auth_provider=FakeAuthProvider(),
            session_store=InMemorySessionStore(),
        )
    ctor.assert_called_once()
    pool = ctor.call_args.args[0]
    assert pool is app.state.db_pool
    assert pool.min_size == 0
    assert pool.max_size == 5
    assert pool.closed is True
    assert app.state.issue_report_repo is sentinel


def test_create_app_leaves_repo_none_without_database_url(tmp_path: Path):
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=False,
        multiuser_settings=_settings(DATABASE_URL=""),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
    )
    assert app.state.issue_report_repo is None


def test_notifier_called_after_successful_insert(tmp_path: Path):
    repo = FakeIssueReportRepository()
    notifier = FakeIssueReportNotifier()
    client = _client(tmp_path, repo=repo, notifier=notifier)
    resp = client.post("/api/report-issue", json=_valid_body())
    assert resp.status_code == 201
    assert len(repo.calls) == 1
    assert len(notifier.calls) == 1
    assert notifier.calls[0]["report"].id == FIXED_ID
    assert notifier.calls[0]["payload"].issue_type == "incorrect_fact"


def test_notifier_failure_still_returns_201(tmp_path: Path):
    repo = FakeIssueReportRepository()
    notifier = FakeIssueReportNotifier(fail=True)
    client = _client(tmp_path, repo=repo, notifier=notifier)
    resp = client.post("/api/report-issue", json=_valid_body())
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["report_id"] == str(FIXED_ID)
    assert len(notifier.calls) == 1
    body = resp.text
    assert "re_secret_leak" not in body
    assert "Resend" not in body


def test_no_notifier_still_returns_201(tmp_path: Path):
    repo = FakeIssueReportRepository()
    client = _client(tmp_path, repo=repo, notifier=None)
    resp = client.post("/api/report-issue", json=_valid_body())
    assert resp.status_code == 201
    assert resp.json()["success"] is True


def test_database_failure_does_not_call_notifier(tmp_path: Path):
    repo = FakeIssueReportRepository(fail=True)
    notifier = FakeIssueReportNotifier()
    client = _client(tmp_path, repo=repo, notifier=notifier)
    resp = client.post("/api/report-issue", json=_valid_body())
    assert resp.status_code == 503
    assert notifier.calls == []


def test_partial_resend_config_leaves_notifier_disabled(tmp_path: Path):
    repo = FakeIssueReportRepository()
    settings = _settings(
        RESEND_API_KEY="re_only_key",
        REPORT_EMAIL_FROM="",
        REPORT_EMAIL_TO="",
    )
    client = _client(tmp_path, repo=repo, settings=settings)
    assert client.app.state.issue_report_notifier is None
    resp = client.post("/api/report-issue", json=_valid_body())
    assert resp.status_code == 201
    assert resp.json()["success"] is True


def test_two_of_three_resend_settings_leave_notifier_disabled(tmp_path: Path):
    repo = FakeIssueReportRepository()
    settings = _settings(
        RESEND_API_KEY="re_key",
        REPORT_EMAIL_FROM="from@example.com",
        REPORT_EMAIL_TO="",
    )
    client = _client(tmp_path, repo=repo, settings=settings)
    assert client.app.state.issue_report_notifier is None
    resp = client.post("/api/report-issue", json=_valid_body())
    assert resp.status_code == 201


def test_create_app_wires_resend_notifier_when_fully_configured(tmp_path: Path):
    from constitution_memorizer.reports.notifier import ResendIssueReportNotifier

    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=False,
        multiuser_settings=_settings(
            RESEND_API_KEY="re_live_key",
            REPORT_EMAIL_FROM="Recall the C <reports@example.com>",
            REPORT_EMAIL_TO="admin@example.com",
        ),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
        issue_report_repo=FakeIssueReportRepository(),
    )
    notifier = app.state.issue_report_notifier
    assert isinstance(notifier, ResendIssueReportNotifier)
    assert notifier._api_key == "re_live_key"
    assert notifier._from == "Recall the C <reports@example.com>"
    assert notifier._to == "admin@example.com"


def test_turnstile_disabled_no_token_still_201(tmp_path: Path):
    repo = FakeIssueReportRepository()
    client = _client(tmp_path, repo=repo)
    resp = client.post("/api/report-issue", json=_valid_body())
    assert resp.status_code == 201
    assert "turnstile_token" not in repo.calls[0]


def test_turnstile_disabled_injected_verifier_not_called(tmp_path: Path):
    repo = FakeIssueReportRepository()
    verifier = FakeTurnstileVerifier()
    client = _client(
        tmp_path,
        repo=repo,
        turnstile=verifier,
        settings=_settings(REPORT_TURNSTILE_ENABLED="false"),
    )
    resp = client.post("/api/report-issue", json=_valid_body())
    assert resp.status_code == 201
    assert verifier.calls == []
    assert len(repo.calls) == 1


def test_turnstile_enabled_verifier_absent_returns_503(tmp_path: Path):
    repo = FakeIssueReportRepository()
    notifier = FakeIssueReportNotifier()
    provider = FakeAuthProvider()
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_turnstile_settings(),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        issue_report_repo=repo,
        issue_report_notifier=notifier,
    )
    # Defense-in-depth: enabled but verifier somehow missing.
    app.state.issue_report_turnstile_verifier = None
    client = TestClient(app)
    _login(client, provider)
    resp = client.post(
        "/api/report-issue",
        json=_valid_body(turnstile_token="XXXX.DUMMY.TOKEN.XXXX"),
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == (
        "Verification temporarily unavailable. Please try again."
    )
    assert repo.calls == []
    assert notifier.calls == []


def test_turnstile_enabled_missing_token_returns_400(tmp_path: Path):
    repo = FakeIssueReportRepository()
    notifier = FakeIssueReportNotifier()
    verifier = FakeTurnstileVerifier()
    client = _client(
        tmp_path,
        repo=repo,
        notifier=notifier,
        turnstile=verifier,
        settings=_turnstile_settings(),
    )
    resp = client.post("/api/report-issue", json=_valid_body())
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Verification required. Please try again."
    assert verifier.calls == []
    assert repo.calls == []
    assert notifier.calls == []


def test_turnstile_enabled_valid_token_verifies_then_inserts(tmp_path: Path):
    repo = FakeIssueReportRepository()
    notifier = FakeIssueReportNotifier()
    verifier = FakeTurnstileVerifier()
    token = "XXXX.DUMMY.TOKEN.XXXX"
    client = _client(
        tmp_path,
        repo=repo,
        notifier=notifier,
        turnstile=verifier,
        settings=_turnstile_settings(),
    )
    resp = client.post("/api/report-issue", json=_valid_body(turnstile_token=token))
    assert resp.status_code == 201
    assert verifier.calls == [token]
    assert len(repo.calls) == 1
    assert "turnstile_token" not in repo.calls[0]
    assert token not in str(repo.calls[0])
    assert len(notifier.calls) == 1
    assert token not in resp.text
    secret = "test_secret_key_do_not_leak"
    assert secret not in resp.text


def test_turnstile_enabled_invalid_token_returns_400(tmp_path: Path):
    repo = FakeIssueReportRepository()
    notifier = FakeIssueReportNotifier()
    verifier = FakeTurnstileVerifier(outcome="reject")
    client = _client(
        tmp_path,
        repo=repo,
        notifier=notifier,
        turnstile=verifier,
        settings=_turnstile_settings(),
    )
    resp = client.post(
        "/api/report-issue",
        json=_valid_body(turnstile_token="bad-token"),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Verification failed. Please try again."
    assert verifier.calls == ["bad-token"]
    assert repo.calls == []
    assert notifier.calls == []
    assert "bad-token" not in resp.text
    assert "test_secret_key_do_not_leak" not in resp.text


def test_turnstile_siteverify_unavailable_returns_503(tmp_path: Path):
    repo = FakeIssueReportRepository()
    notifier = FakeIssueReportNotifier()
    verifier = FakeTurnstileVerifier(outcome="unavailable")
    client = _client(
        tmp_path,
        repo=repo,
        notifier=notifier,
        turnstile=verifier,
        settings=_turnstile_settings(),
    )
    resp = client.post(
        "/api/report-issue",
        json=_valid_body(turnstile_token="any-token"),
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == (
        "Verification temporarily unavailable. Please try again."
    )
    assert repo.calls == []
    assert notifier.calls == []


def test_turnstile_token_too_long_returns_422(tmp_path: Path):
    repo = FakeIssueReportRepository()
    verifier = FakeTurnstileVerifier()
    client = _client(
        tmp_path,
        repo=repo,
        turnstile=verifier,
        settings=_turnstile_settings(),
    )
    resp = client.post(
        "/api/report-issue",
        json=_valid_body(turnstile_token="x" * 2049),
    )
    assert resp.status_code == 422
    assert repo.calls == []
    assert verifier.calls == []


def test_create_app_rejects_partial_turnstile_config_without_multiuser(
    tmp_path: Path,
):
    with pytest.raises(AuthConfigError, match="REPORT_TURNSTILE_SECRET_KEY"):
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
            multiuser=False,
            multiuser_settings=_settings(
                REPORT_TURNSTILE_ENABLED="true",
                REPORT_TURNSTILE_SITE_KEY="site-only",
                REPORT_TURNSTILE_SECRET_KEY="",
            ),
            auth_provider=FakeAuthProvider(),
            session_store=InMemorySessionStore(),
            issue_report_repo=FakeIssueReportRepository(),
        )


def test_create_app_wires_turnstile_verifier_when_configured(tmp_path: Path):
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=False,
        multiuser_settings=_turnstile_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
        issue_report_repo=FakeIssueReportRepository(),
    )
    assert isinstance(app.state.issue_report_turnstile_verifier, TurnstileVerifier)


def test_authenticated_email_used_as_reporter_email(tmp_path: Path):
    repo = FakeIssueReportRepository()
    notifier = FakeIssueReportNotifier()
    client = _client(
        tmp_path,
        repo=repo,
        notifier=notifier,
        user_email="signed-in@example.com",
    )
    resp = client.post(
        "/api/report-issue",
        json=_valid_body(reporter_email="spoofed@evil.example"),
    )
    assert resp.status_code == 201
    assert repo.calls[0]["reporter_email"] == "signed-in@example.com"
    assert notifier.calls[0]["payload"].reporter_email == "signed-in@example.com"


def test_authenticated_user_without_email_persists_none(tmp_path: Path):
    from constitution_memorizer.auth.models import AuthenticatedUser

    repo = FakeIssueReportRepository()
    provider = FakeAuthProvider()
    provider.google_users["holder@example.com"] = AuthenticatedUser(
        id=UUID("22222222-2222-4222-8222-222222222222"),
        email=None,
        phone="+919876543210",
        display_name="Phone-linked",
        avatar_url=None,
        provider="google",
    )
    client = _client(
        tmp_path,
        repo=repo,
        auth_provider=provider,
        user_email="holder@example.com",
    )
    resp = client.post("/api/report-issue", json=_valid_body())
    assert resp.status_code == 201
    assert repo.calls[0]["reporter_email"] is None


def test_non_multiuser_still_accepts_without_login(tmp_path: Path):
    repo = FakeIssueReportRepository()
    client = _client(tmp_path, repo=repo, multiuser=False)
    resp = client.post("/api/report-issue", json=_valid_body())
    assert resp.status_code == 201
    assert repo.calls[0]["reporter_email"] is None
