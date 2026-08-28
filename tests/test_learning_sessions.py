"""New-learning sessions: Skip, stale links, activation, create-or-get."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.progress.db import open_progress_db
from constitution_memorizer.progress.repository import ProgressRepository
from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.completion import session_entry_mode, with_params
from constitution_memorizer.web.dashboard import build_dashboard_context

from tests.quiz_helpers import complete_all_modes

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


def _client(tmp_path: Path, *, multiuser: bool = False) -> TestClient:
    kwargs: dict = {
        "units_path": MINI_UNITS,
        "db_path": tmp_path / "progress.db",
        "multiuser": multiuser,
    }
    if multiuser:
        clear_settings_cache()
        kwargs["multiuser_settings"] = MultiUserSettings(
            _env_file=None,
            APP_ENV="test",
            MULTIUSER_ENABLED="true",
            AUTH_GOOGLE_ENABLED="true",
            SESSION_SECRET="test-secret",
            SUPABASE_URL="http://example.invalid",
            SUPABASE_ANON_KEY="anon",
            DATABASE_URL="",
            COOKIE_SECURE="false",
        )
        kwargs["auth_provider"] = FakeAuthProvider()
        kwargs["session_store"] = InMemorySessionStore()
    return TestClient(create_app(**kwargs))


def _engine(client: TestClient) -> ReminderEngine:
    engine = client.app.state.engine
    store = getattr(client.app.state, "session_store", None)
    sessions = getattr(store, "_sessions", None) if store is not None else None
    if sessions:
        newest = sorted(sessions.values(), key=lambda s: s.created_at)[-1]
        return engine.for_user(newest.user.id)
    return engine


def _session_of(location: str) -> str:
    return parse_qs(urlsplit(location).query).get("session", [""])[0]


def _start_day_plan(client: TestClient, target: int = 3) -> tuple[str, str]:
    resp = client.post("/learning/plan-my-day", data={"target": target}, follow_redirects=False)
    assert resp.status_code == 303, resp.text
    parts = urlsplit(resp.headers["location"])
    session_id = parse_qs(parts.query).get("session", [""])[0]
    path = parts.path.removesuffix("/choose")
    return session_id, path.rsplit("/", 1)[-1]


def test_skip_on_unlearned_item_does_not_write_review_progress(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    session = eng.create_study_session(
        session_id="day-mix",
        kind="day_plan",
        plan_date=date.today(),
        unit_ids=["clause-1", "article-end"],
    )
    before = eng.get_progress("clause-1")
    assert before is None or before.status == "new"

    page = client.get(f"/learn/clause-1?session={session.id}")
    assert page.status_code == 200
    assert "Skip for today" in page.text
    assert "Again tomorrow" not in page.text

    skip = client.post(
        with_params("/learn/clause-1/skip", {"session": session.id}),
        follow_redirects=False,
    )
    assert skip.status_code == 303
    after = eng.get_progress("clause-1")
    assert after is None or (
        after.status == "new"
        and after.times_completed == 0
        and after.next_revision is None
    )
    refreshed = eng.get_study_session(session.id)
    assert refreshed is not None
    item = refreshed.item_for("clause-1")
    assert item is not None
    assert item.status == "deferred"


def test_yesterday_session_cannot_drive_todays_navigation(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    yesterday = date.today() - timedelta(days=1)
    stale = eng.create_study_session(
        session_id="yesterday-mix",
        kind="day_plan",
        plan_date=yesterday,
        unit_ids=["clause-1", "clause-2"],
    )
    page = client.get(f"/learn/clause-1?session={stale.id}")
    assert page.status_code == 200
    assert 'data-session-id="yesterday-mix"' not in page.text
    assert "Learning 1 of" not in page.text
    assert "Skip for today" not in page.text
    assert "Again tomorrow" in page.text

    complete_all_modes(client, MINI_UNITS, "clause-1")
    done = client.post(
        with_params("/learn/clause-1/done", {"session": stale.id}),
        follow_redirects=False,
    )
    assert done.status_code == 303
    location = done.headers["location"]
    assert _session_of(location) == ""
    refreshed = eng.get_study_session(stale.id)
    assert refreshed is not None
    assert refreshed.item_for("clause-1").status == "pending"


def test_activated_at_is_not_written_on_start(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    eng.upsert_learning_plan(mode="auto", daily_target=3)
    assert eng.get_learning_plan().activated_at is None

    start = client.post("/learning/start", follow_redirects=False)
    assert start.status_code == 303
    assert eng.get_learning_plan().activated_at is None
    parts = urlsplit(start.headers["location"])
    session_id = parse_qs(parts.query).get("session", [""])[0]
    first = parts.path.removesuffix("/choose").rsplit("/", 1)[-1]
    assert session_id

    complete_all_modes(client, MINI_UNITS, first)
    client.post(
        with_params(f"/learn/{first}/done", {"session": session_id}),
        follow_redirects=False,
    )
    plan = eng.get_learning_plan()
    assert plan.activated_at == date.today()


def test_create_or_get_conflict_returns_one_session(tmp_path: Path):
    engine = ReminderEngine.from_paths(tmp_path / "progress.db", MINI_UNITS)
    today = date.today()
    first = engine.create_study_session(
        session_id="winner",
        kind="day_plan",
        plan_date=today,
        unit_ids=["clause-1", "article-end"],
    )
    loser = engine.create_study_session(
        session_id="loser",
        kind="day_plan",
        plan_date=today,
        unit_ids=["clause-2"],
    )
    assert loser.id == first.id
    assert [item.learning_unit_id for item in loser.items] == ["clause-1", "article-end"]
    assert engine.get_study_session("loser") is None


def test_revision_completed_copy_excludes_manual_new_learning(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    today = date.today()
    session = eng.create_study_session(
        session_id="rev-today",
        kind="revision",
        plan_date=today,
        unit_ids=["clause-1", "article-end"],
    )
    eng.set_study_item_status(
        session_id=session.id, unit_id="clause-1", status="completed"
    )
    eng.set_study_item_status(
        session_id=session.id, unit_id="article-end", status="deferred"
    )
    eng.complete_study_session(session.id)
    eng.mark_all_modes_seen("clause-1")
    eng.mark_done("clause-1", as_of=today)
    eng.mark_all_modes_seen("clause-2")
    eng.mark_done("clause-2", as_of=today)

    ctx = build_dashboard_context(eng, display_label="Priya", as_of=today)
    assert ctx["revision_completed_today"] == 1
    assert ctx["completed_today"] >= 2
    assert ctx["revision_completed_today"] != ctx["completed_today"]


def test_session_entry_mode_is_kind_generic():
    assert session_entry_mode("revision") == "read"
    assert session_entry_mode("auto_learning") == "read"
    assert session_entry_mode("day_plan") == "read"


def test_plan_my_day_creates_a_same_day_session(tmp_path: Path):
    client = _client(tmp_path)
    session_id, first = _start_day_plan(client, target=3)
    assert session_id
    session = _engine(client).get_study_session(session_id)
    assert session is not None
    assert session.kind == "day_plan"
    assert session.plan_date == date.today()
    assert first in {item.learning_unit_id for item in session.items}


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)


def test_learn_start_does_not_create_on_get(tmp_path: Path):
    client = _client(tmp_path)
    client.get("/learn/clause-1")
    client.get("/learn/clause-1?flow=auto")
    eng = _engine(client)
    assert eng.active_study_session(kind="auto_learning", plan_date=date.today()) is None
    assert eng.active_study_session(kind="day_plan", plan_date=date.today()) is None


def test_plan_my_day_requires_self_paced_and_blocks_auto_session(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    eng.upsert_learning_plan(mode="auto", daily_target=5)
    blocked = client.get("/learning/plan-my-day", follow_redirects=False)
    assert blocked.status_code == 303
    posted = client.post(
        "/learning/plan-my-day", data={"target": "3"}, follow_redirects=False
    )
    assert posted.status_code == 303
    assert eng.study_session_for_day(kind="day_plan", plan_date=date.today()) is None

    eng.upsert_learning_plan(mode="self_paced", daily_target=None)
    eng.create_study_session(
        session_id="already-auto",
        kind="auto_learning",
        plan_date=date.today(),
        unit_ids=["clause-1"],
    )
    coexist = client.post(
        "/learning/plan-my-day", data={"target": "3"}, follow_redirects=False
    )
    assert coexist.status_code == 303
    assert eng.study_session_for_day(kind="day_plan", plan_date=date.today()) is None


def test_new_learning_yields_to_a_pending_revision_session(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    eng.upsert_learning_plan(mode="auto", daily_target=3)
    eng.create_study_session(
        session_id="rev-pending",
        kind="revision",
        plan_date=date.today(),
        unit_ids=["clause-1"],
    )
    start = client.post("/learning/start", follow_redirects=False)
    assert start.status_code == 303
    assert start.headers["location"] in ("/", "/dashboard")
    assert eng.study_session_for_day(kind="auto_learning", plan_date=date.today()) is None

    eng.upsert_learning_plan(mode="self_paced", daily_target=None)
    plan = client.post(
        "/learning/plan-my-day", data={"target": "3"}, follow_redirects=False
    )
    assert plan.status_code == 303
    assert eng.study_session_for_day(kind="day_plan", plan_date=date.today()) is None


def test_completed_auto_session_renders_todays_learning_complete(tmp_path: Path):
    client = _client(tmp_path, multiuser=True)
    _sign_in(client)
    eng = _engine(client)
    today = date.today()
    eng.upsert_learning_plan(mode="auto", daily_target=3)
    session = eng.create_study_session(
        session_id="auto-done",
        kind="auto_learning",
        plan_date=today,
        unit_ids=["clause-1"],
    )
    eng.set_study_item_status(
        session_id=session.id, unit_id="clause-1", status="completed"
    )
    eng.complete_study_session(session.id)
    ctx = build_dashboard_context(
        eng, display_label="Priya", as_of=today, auto_entitled=True
    )
    assert ctx["learning_cta"] == "learning_complete"
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "Today's learning complete" in page.text
    assert "Start learning →" not in page.text


def test_choose_letters_from_a_session_stays_on_the_queue(tmp_path: Path):
    client = _client(tmp_path)
    eng = _engine(client)
    session = eng.create_study_session(
        session_id="letters-mix",
        kind="day_plan",
        plan_date=date.today(),
        unit_ids=["clause-2", "clause-1"],
    )
    picked = client.post(
        f"/learn/clause-2/choose?session={session.id}",
        data={"mode": "letters"},
        follow_redirects=False,
    )
    assert picked.status_code == 303
    location = picked.headers["location"]
    assert "/learn/clause-2-a" in location
    assert _session_of(location) == session.id

    page = client.get(f"/learn/clause-2-a?session={session.id}")
    assert page.status_code == 200
    assert f'data-session-id="{session.id}"' in page.text
    assert "Skip for today" in page.text

    complete_all_modes(client, MINI_UNITS, "clause-2-a")
    done = client.post(
        with_params("/learn/clause-2-a/done", {"session": session.id}),
        follow_redirects=False,
    )
    assert done.status_code == 303
    assert "/learn/clause-2-b" in done.headers["location"]
    assert _session_of(done.headers["location"]) == session.id

    skip = client.post(
        with_params("/learn/clause-2-b/skip", {"session": session.id}),
        follow_redirects=False,
    )
    assert skip.status_code == 303
    assert "/learn/clause-1" in skip.headers["location"]
    assert _session_of(skip.headers["location"]) == session.id
    refreshed = eng.get_study_session(session.id)
    assert refreshed is not None
    assert [item.learning_unit_id for item in refreshed.items] == [
        "clause-2-a",
        "clause-2-b",
        "clause-1",
    ]
    assert refreshed.item_for("clause-2") is None
    assert refreshed.item_for("clause-2-a").status == "completed"
    assert refreshed.item_for("clause-2-b").status == "deferred"


def _articles_catalog(tmp_path: Path) -> Path:
    units = []
    for index, article in enumerate(
        ["14", "15", "16", "19", "21", "32", "33", "38"], start=1
    ):
        units.append(
            {
                "id": f"u-{article}",
                "type": "CLAUSE",
                "article_number": article,
                "display_title": f"Article {article}",
                "text": f"Text for article {article}.",
                "difficulty": 2,
                "estimated_learning_time": 60,
                "revision_order": index,
                "tags": ["Part III"],
                "allows_letter_split": False,
                "child_unit_ids": [],
                "parent_clause_id": None,
            }
        )
    path = tmp_path / "articles.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "source_document": "fixture",
                "unit_count": len(units),
                "units": units,
            }
        )
    )
    return path


def _entitled_client(
    tmp_path: Path, units_path: Path, *, make_admin: bool = False
) -> tuple[TestClient, ProgressRepository, UUID]:
    clear_settings_cache()
    user_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=user_id, email="mix@example.com")
    settings = MultiUserSettings(
        _env_file=None,
        APP_ENV="test",
        MULTIUSER_ENABLED="true",
        AUTH_GOOGLE_ENABLED="true",
        SESSION_SECRET="test-secret",
        SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon",
        DATABASE_URL="",
        COOKIE_SECURE="false",
        ARTICLE_ENTITLEMENTS_ENABLED="true",
        ADMIN_ENABLED="true" if make_admin else "false",
    )
    client = TestClient(
        create_app(
            units_path=units_path,
            db_path=tmp_path / "unused.db",
            multiuser=True,
            multiuser_settings=settings,
            auth_provider=provider,
            session_store=InMemorySessionStore(),
            progress_repo=repo,
        )
    )
    _sign_in(client)
    if make_admin:
        repo.conn.execute(
            "INSERT INTO user_roles (user_id, role, created_at) VALUES (?, 'admin', ?)",
            (str(user_id), datetime.now(timezone.utc).isoformat()),
        )
        repo.conn.commit()
    return client, repo, user_id


def test_free_mix_respects_zero_remaining_slots_over_html(tmp_path: Path):
    units_path = _articles_catalog(tmp_path)
    client, repo, user_id = _entitled_client(tmp_path, units_path)
    for article in ("14", "15", "16"):
        repo.claim_article(user_id, article)
    saved = client.post(
        "/learning/plan-my-day", data={"target": "5"}, follow_redirects=False
    )
    assert saved.status_code == 303
    eng = _engine(client)
    session = eng.study_session_for_day(kind="day_plan", plan_date=date.today())
    assert session is not None
    articles = {
        eng.get_unit(item.learning_unit_id).article_number
        for item in session.items
        if eng.get_unit(item.learning_unit_id) is not None
    }
    assert articles <= {"14", "15", "16"}


def test_admin_mix_bypasses_free_article_slot_cap(tmp_path: Path):
    units_path = _articles_catalog(tmp_path)
    client, repo, user_id = _entitled_client(tmp_path, units_path, make_admin=True)
    for article in ("14", "15", "16"):
        repo.claim_article(user_id, article)
    saved = client.post(
        "/learning/plan-my-day", data={"target": "5"}, follow_redirects=False
    )
    assert saved.status_code == 303
    eng = _engine(client)
    session = eng.study_session_for_day(kind="day_plan", plan_date=date.today())
    assert session is not None
    articles = {
        eng.get_unit(item.learning_unit_id).article_number
        for item in session.items
        if eng.get_unit(item.learning_unit_id) is not None
    }
    assert articles - {"14", "15", "16"}


def test_free_cap_without_claimed_unseen_hides_plan_my_day(tmp_path: Path):
    units_path = _articles_catalog(tmp_path)
    client, repo, user_id = _entitled_client(tmp_path, units_path)
    for article in ("14", "15", "16"):
        repo.claim_article(user_id, article)
    eng = _engine(client)
    today = date.today()
    for unit_id in ("u-14", "u-15", "u-16"):
        eng.repo.upsert_progress(
            eng.user_id,
            unit_id=unit_id,
            status="review",
            times_completed=1,
            last_completed=today - timedelta(days=10),
            next_revision=today + timedelta(days=10),
            interval_days=15,
        )
    eng._invalidate_progress_cache()
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "Plan my day" not in page.text
    posted = client.post(
        "/learning/plan-my-day", data={"target": "3"}, follow_redirects=False
    )
    assert posted.status_code == 303
    assert eng.study_session_for_day(kind="day_plan", plan_date=today) is None


def test_admin_auto_start_spans_beyond_free_article_cap(tmp_path: Path):
    units_path = _articles_catalog(tmp_path)
    client, repo, user_id = _entitled_client(tmp_path, units_path, make_admin=True)
    for article in ("14", "15", "16"):
        repo.claim_article(user_id, article)
    saved = client.post(
        "/settings/learning-plan",
        data={"mode": "auto", "daily_target": "7"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    plan = _engine(client).get_learning_plan()
    assert plan.mode == "auto"
    assert plan.daily_target == 7
    start = client.post("/learning/start", follow_redirects=False)
    assert start.status_code == 303
    eng = _engine(client)
    session = eng.study_session_for_day(kind="auto_learning", plan_date=date.today())
    assert session is not None
    articles = {
        eng.get_unit(item.learning_unit_id).article_number
        for item in session.items
        if eng.get_unit(item.learning_unit_id) is not None
    }
    assert len(articles) > 3
    orders = repo.conn.execute(
        "SELECT * FROM billing_orders WHERE user_id = ?", (str(user_id),)
    ).fetchall()
    grants = repo.conn.execute(
        "SELECT * FROM access_grants WHERE user_id = ?", (str(user_id),)
    ).fetchall()
    assert list(orders) == []
    assert list(grants) == []


def test_plan_prompt_dashboard_carries_the_phone_sheet(tmp_path: Path):
    """Design 4c: the phone opens Plan my day over Today; the page stays the
    desktop and no-JS route."""
    units_path = _articles_catalog(tmp_path)
    client, _, _ = _entitled_client(tmp_path, units_path)
    html = client.get("/dashboard").text

    assert 'data-sheet-open="plan-day-sheet"' in html
    assert 'id="plan-day-sheet"' in html
    # The anchor keeps its href — desktop and no-JS phones still navigate.
    assert 'href="/learning/plan-my-day"' in html
    # The sheet posts the same four actions as plan_my_day.html.
    assert html.count('action="/learning/plan-my-day"') == 3
    assert 'action="/learning/plan-my-day/dismiss"' in html
    for label in ("Steady · 3", "Balanced · 5", "Intensive · 7", "Not today"):
        assert label in html, label


def test_dashboard_sheet_is_absent_outside_the_plan_prompt(tmp_path: Path):
    client = _client(tmp_path, multiuser=True)
    _sign_in(client)
    eng = _engine(client)
    today = date.today()
    eng.upsert_learning_plan(mode="auto", daily_target=3)
    eng.create_study_session(
        session_id="auto-open",
        kind="auto_learning",
        plan_date=today,
        unit_ids=["clause-1"],
    )
    html = client.get("/dashboard").text
    assert 'id="plan-day-sheet"' not in html


def test_settings_plan_status_reads_as_a_sentence_before_activation(tmp_path: Path):
    """An auto plan that has not been worked yet must not render
    "Plan started Not started"."""
    units_path = _articles_catalog(tmp_path)
    # Admin unlocks Auto Plan; without the entitlement the planner projects no
    # learning days at all and the trailing date clause never renders.
    client, _, _ = _entitled_client(tmp_path, units_path, make_admin=True)
    today = date.today()
    # Save through the real route so the roadmap is built, as it is in the app.
    saved = client.post(
        "/settings/learning-plan",
        data={"mode": "auto", "daily_target": "3"},
        follow_redirects=False,
    )
    assert saved.status_code == 303

    html = client.get("/settings").text
    assert "Plan started Not started" not in html
    assert "Not started yet" in html
    assert "First learning day" in html

    # Once the plan activates, the line returns to the designed copy (frame 1d).
    _engine(client).activate_learning_plan(today)
    html = client.get("/settings").text
    assert "Not started yet" not in html
    assert "First learning day" not in html
    assert f"Plan started {today.strftime('%d %b %Y')}" in " ".join(html.split())
    assert "Next learning day" in html
