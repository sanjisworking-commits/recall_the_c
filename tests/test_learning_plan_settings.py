"""Settings + onboarding for Self-paced / Auto Plan."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import CSRF_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.service import user_today

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
ADMIN_A = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
ADMIN_B = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


def _settings(*, entitlements: bool = False, admin_enabled: bool = False) -> MultiUserSettings:
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
        ARTICLE_ENTITLEMENTS_ENABLED="true" if entitlements else "false",
        ADMIN_ENABLED="true" if admin_enabled else "false",
    )


def _client(tmp_path: Path, *, entitlements: bool = False) -> TestClient:
    clear_settings_cache()
    return TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
            multiuser=True,
            multiuser_settings=_settings(entitlements=entitlements),
            auth_provider=FakeAuthProvider(),
            session_store=InMemorySessionStore(),
        )
    )


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)


def _session_user_id(client: TestClient) -> UUID:
    store = getattr(client.app.state, "session_store", None)
    sessions = getattr(store, "_sessions", None) if store is not None else None
    newest = sorted(sessions.values(), key=lambda s: s.created_at)[-1]
    return newest.user.id


def _engine(client: TestClient) -> ReminderEngine:
    return client.app.state.engine.for_user(_session_user_id(client))


def _seed_admin(repo: ProgressRepository, user_id: UUID) -> None:
    repo.conn.execute(
        "INSERT INTO user_roles (user_id, role, created_at) VALUES (?, 'admin', ?)",
        (str(user_id), datetime.now(timezone.utc).isoformat()),
    )
    repo.conn.commit()


def _seed_grant(repo: ProgressRepository, user_id: UUID) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    repo.conn.execute(
        """
        INSERT INTO access_grants (
            id, user_id, source, starts_at, ends_at, reason,
            granted_by, created_at
        ) VALUES (?, ?, 'admin_grant', ?, ?, 'test', ?, ?)
        """,
        (
            str(uuid4()),
            str(user_id),
            (now - timedelta(hours=1)).isoformat(),
            (now + timedelta(days=30)).isoformat(),
            str(uuid4()),
            now.isoformat(),
        ),
    )
    repo.conn.commit()


def _admin_client(
    tmp_path: Path,
    *,
    user_id: UUID = ADMIN_A,
    email: str = "admin@recall.app",
    repo: ProgressRepository | None = None,
) -> tuple[TestClient, ProgressRepository]:
    clear_settings_cache()
    if repo is None:
        conn = open_progress_db(tmp_path / "progress.db")
        repo = ProgressRepository(conn)
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=user_id, email=email, display_name="Admin")
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "unused.db",
            multiuser=True,
            multiuser_settings=_settings(entitlements=True, admin_enabled=True),
            auth_provider=provider,
            session_store=InMemorySessionStore(),
            progress_repo=repo,
        )
    )
    _sign_in(client)
    _seed_admin(repo, user_id)
    return client, repo


def _enter_preview(client: TestClient, state: str) -> None:
    csrf = client.cookies.get("rtc_csrf") or ""
    resp = client.post(
        "/admin/preview",
        data={"csrf_token": csrf, "state": state},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert client.cookies.get("rtc_admin_preview") == state


def _commerce_rows(repo: ProgressRepository, user_id: UUID) -> tuple[list, list]:
    orders = repo.conn.execute(
        "SELECT * FROM billing_orders WHERE user_id = ?", (str(user_id),)
    ).fetchall()
    grants = repo.conn.execute(
        "SELECT * FROM access_grants WHERE user_id = ?", (str(user_id),)
    ).fetchall()
    return list(orders), list(grants)


def _plan_row(repo: ProgressRepository, user_id: UUID):
    return repo.conn.execute(
        "SELECT user_id, mode, daily_target FROM user_learning_plan WHERE user_id = ?",
        (str(user_id),),
    ).fetchone()


def test_settings_shows_learning_plan_and_saves_auto(tmp_path: Path):
    client = _client(tmp_path)
    _sign_in(client)
    page = client.get("/settings")
    assert page.status_code == 200
    assert "Learning plan" in page.text
    assert "Self-paced" in page.text
    assert "Auto Plan" in page.text
    saved = client.post(
        "/settings/learning-plan",
        data={"mode": "auto", "daily_target": "5"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    plan = _engine(client).get_learning_plan()
    assert plan.mode == "auto"
    assert plan.daily_target == 5
    assert plan.activated_at is None
    again = client.get("/settings")
    assert "Plan started" in again.text
    assert "Not started" in again.text


def test_onboarding_plan_saves_self_paced(tmp_path: Path):
    client = _client(tmp_path)
    _sign_in(client)
    page = client.get("/onboarding/plan")
    assert page.status_code == 200
    assert "Set a learning plan" in page.text
    csrf = client.cookies.get(CSRF_COOKIE_NAME) or ""
    resp = client.post(
        "/onboarding/plan",
        data={"mode": "self_paced", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert resp.headers["location"] == "/dashboard"
    plan = _engine(client).get_learning_plan()
    assert plan.mode == "self_paced"
    assert plan.activated_at is None


def test_free_account_cannot_enable_auto_plan(tmp_path: Path):
    """HTML lock is not the authority — the server rejects the POST."""
    client = _client(tmp_path, entitlements=True)
    _sign_in(client)
    page = client.get("/settings")
    assert "Part of unlocking every Article" in page.text
    assert 'value="auto" disabled' in page.text
    client.post(
        "/settings/learning-plan",
        data={"mode": "auto", "daily_target": "7"},
        follow_redirects=False,
    )
    plan = _engine(client).get_learning_plan()
    assert plan.mode == "self_paced"
    start = client.post("/learning/start", follow_redirects=False)
    assert start.status_code == 303
    assert start.headers["location"] in ("/dashboard", "/")


def test_admin_can_save_auto_plan_and_switch_to_self_paced(tmp_path: Path):
    client, repo = _admin_client(tmp_path)
    user_id = _session_user_id(client)
    page = client.get("/settings")
    assert page.status_code == 200
    assert "Self-paced" in page.text
    assert "Steady · 3" in page.text
    assert "Balanced · 5" in page.text
    assert "Intensive · 7" in page.text
    assert "Full Recall access · Admin" in page.text
    assert "Paid plan" not in page.text
    assert "Part of unlocking every Article" not in page.text
    assert 'value="auto" disabled' not in page.text

    for target in (3, 5, 7):
        saved = client.post(
            "/settings/learning-plan",
            data={"mode": "auto", "daily_target": str(target)},
            follow_redirects=False,
        )
        assert saved.status_code == 303
        plan = _engine(client).get_learning_plan()
        assert plan.mode == "auto"
        assert plan.daily_target == target

    back = client.post(
        "/settings/learning-plan",
        data={"mode": "self_paced"},
        follow_redirects=False,
    )
    assert back.status_code == 303
    plan = _engine(client).get_learning_plan()
    assert plan.mode == "self_paced"
    assert plan.daily_target is None

    orders, grants = _commerce_rows(repo, user_id)
    assert orders == []
    assert grants == []
    role = repo.conn.execute(
        "SELECT role FROM user_roles WHERE user_id = ?", (str(user_id),)
    ).fetchone()
    assert role["role"] == "admin"


def test_admin_auto_plan_generates_new_capacity(tmp_path: Path):
    client, repo = _admin_client(tmp_path)
    user_id = _session_user_id(client)
    client.post(
        "/settings/learning-plan",
        data={"mode": "auto", "daily_target": "5"},
        follow_redirects=False,
    )
    eng = _engine(client)
    calendar = client.get("/calendar")
    assert calendar.status_code == 200
    assert "NEW ·" in calendar.text

    orders, grants = _commerce_rows(repo, user_id)
    assert orders == []
    assert grants == []
    row = _plan_row(repo, user_id)
    assert row["user_id"] == str(user_id)
    assert row["mode"] == "auto"
    assert row["daily_target"] == 5


def test_admin_access_source_is_admin_not_a_purchase(tmp_path: Path):
    client, repo = _admin_client(tmp_path)
    user_id = _session_user_id(client)
    settings = client.get("/settings")
    assert "Administrator access" in settings.text
    assert "Full Recall access · Admin" in settings.text
    assert "Paid plan" not in settings.text
    assert "Recall active" not in settings.text
    profile = client.get("/profile")
    assert "Administrator access" in profile.text
    assert "No billing attached" in profile.text
    assert "Recall active" not in profile.text
    dash = client.get("/dashboard")
    assert "Administrator access" in dash.text
    assert "Recall active" not in dash.text
    orders, grants = _commerce_rows(repo, user_id)
    assert orders == []
    assert grants == []


def test_one_admin_learning_plan_does_not_affect_another(tmp_path: Path):
    client_a, repo = _admin_client(tmp_path, user_id=ADMIN_A, email="a@recall.app")
    client_b, _ = _admin_client(
        tmp_path, user_id=ADMIN_B, email="b@recall.app", repo=repo
    )
    client_a.post(
        "/settings/learning-plan",
        data={"mode": "auto", "daily_target": "7"},
        follow_redirects=False,
    )
    client_b.post(
        "/settings/learning-plan",
        data={"mode": "auto", "daily_target": "3"},
        follow_redirects=False,
    )
    row_a = _plan_row(repo, ADMIN_A)
    row_b = _plan_row(repo, ADMIN_B)
    assert row_a["mode"] == "auto" and row_a["daily_target"] == 7
    assert row_b["mode"] == "auto" and row_b["daily_target"] == 3
    assert _engine(client_a).get_learning_plan().daily_target == 7
    assert _engine(client_b).get_learning_plan().daily_target == 3


def test_entitlement_preview_does_not_mutate_admin_learning_plan(tmp_path: Path):
    client, repo = _admin_client(tmp_path)
    user_id = _session_user_id(client)
    client.post(
        "/settings/learning-plan",
        data={"mode": "auto", "daily_target": "5"},
        follow_redirects=False,
    )
    assert _engine(client).get_learning_plan().daily_target == 5

    _enter_preview(client, "subscribed")
    previewed = client.get("/settings")
    assert "ADMIN PREVIEW" in previewed.text
    assert "Full Recall access · Admin" in previewed.text
    assert "Administrator access" in previewed.text
    assert "Paid plan" not in previewed.text
    assert "Recall active" not in previewed.text
    assert 'value="auto" disabled' not in previewed.text
    # Preview must not mint a paid identity.
    orders, grants = _commerce_rows(repo, user_id)
    assert orders == []
    assert grants == []

    # A Settings POST while simulating another tier must not rewrite the row.
    client.post(
        "/settings/learning-plan",
        data={"mode": "self_paced"},
        follow_redirects=False,
    )
    plan = _engine(client).get_learning_plan()
    assert plan.mode == "auto"
    assert plan.daily_target == 5

    _enter_preview(client, "free_cap")
    free_preview = client.get("/settings")
    assert "ADMIN PREVIEW" in free_preview.text
    assert "Full Recall access · Admin" in free_preview.text
    assert 'value="auto" disabled' not in free_preview.text
    client.post(
        "/settings/learning-plan",
        data={"mode": "auto", "daily_target": "3"},
        follow_redirects=False,
    )
    plan = _engine(client).get_learning_plan()
    assert plan.mode == "auto"
    assert plan.daily_target == 5
    orders, grants = _commerce_rows(repo, user_id)
    assert orders == []
    assert grants == []


def test_grant_holder_can_enable_auto_plan_without_a_purchase(tmp_path: Path):
    clear_settings_cache()
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    user_id = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=user_id, email="granted@recall.app")
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "unused.db",
            multiuser=True,
            multiuser_settings=_settings(entitlements=True),
            auth_provider=provider,
            session_store=InMemorySessionStore(),
            progress_repo=repo,
        )
    )
    _sign_in(client)
    _seed_grant(repo, user_id)
    page = client.get("/settings")
    assert 'value="auto" disabled' not in page.text
    assert "Full Recall access · Admin" not in page.text
    client.post(
        "/settings/learning-plan",
        data={"mode": "auto", "daily_target": "5"},
        follow_redirects=False,
    )
    plan = _engine(client).get_learning_plan()
    assert plan.mode == "auto"
    assert plan.daily_target == 5
    orders, _grants = _commerce_rows(repo, user_id)
    assert orders == []
    settings = client.get("/settings")
    assert "Recall access granted" in settings.text
    assert "Paid plan" not in settings.text
    assert "Recall active" not in settings.text
