"""Learn Done completion signal: validated ?done=, JSON after persist, guests."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.progress.repository import LEARN_MODES
from constitution_memorizer.web.app import create_app

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
        provider = FakeAuthProvider()
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
        kwargs["auth_provider"] = provider
        kwargs["session_store"] = InMemorySessionStore()
    return TestClient(create_app(**kwargs))


def _visit_all_modes(client: TestClient, unit_id: str) -> None:
    complete_all_modes(client, MINI_UNITS, unit_id)


def test_done_redirect_carries_single_done_param(tmp_path: Path):
    client = _client(tmp_path)
    _visit_all_modes(client, "clause-2-a")
    resp = client.post("/learn/clause-2-a/done", follow_redirects=False)
    assert resp.status_code == 303
    loc = resp.headers["location"]
    assert loc == "/learn/clause-2-b?done=clause-2-a"
    assert loc.count("done=") == 1


def test_fetch_json_done_after_persist(tmp_path: Path):
    client = _client(tmp_path)
    _visit_all_modes(client, "clause-2-a")
    resp = client.post(
        "/learn/clause-2-a/done",
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["next_url"] == "/learn/clause-2-b?done=clause-2-a"
    assert data["article_ref"] == "Article 20(3)(a)"
    assert data["status"] == "review"
    assert data["next_review"] == (date.today() + timedelta(days=1)).isoformat()
    page = client.get("/learn/clause-2-a")
    assert "data-rtc-completion" not in page.text
    progress_html = client.get("/learn/clause-2-b?done=clause-2-a")
    assert 'data-rtc-completion' in progress_html.text
    assert "Review complete" in progress_html.text
    assert "Article 20(3)(a)" in progress_html.text


def test_again_and_reset_never_generate_completion(tmp_path: Path):
    client = _client(tmp_path)
    _visit_all_modes(client, "clause-2-a")
    again = client.post("/learn/clause-2-a/again", follow_redirects=False)
    assert again.status_code == 303
    assert "done=" not in again.headers["location"]
    dest = client.get(again.headers["location"])
    assert "data-rtc-completion" not in dest.text

    _visit_all_modes(client, "clause-2-b")
    client.post("/learn/clause-2-b/done", follow_redirects=False)
    reset = client.post("/learn/clause-2-b/reset", follow_redirects=False)
    assert reset.status_code == 303
    assert "done=" not in reset.headers["location"]
    reset_page = client.get(reset.headers["location"])
    assert "data-rtc-completion" not in reset_page.text


def test_incomplete_modes_no_completion_param(tmp_path: Path):
    client = _client(tmp_path)
    client.get("/learn/clause-1")
    resp = client.post("/learn/clause-1/done", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/learn/clause-1"
    assert "done=" not in resp.headers["location"]
    json_resp = client.post(
        "/learn/clause-1/done",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )
    assert json_resp.status_code == 409
    assert json_resp.json()["ok"] is False


def test_invalid_done_param_renders_no_affirmation(tmp_path: Path):
    client = _client(tmp_path)
    unknown = client.get("/learn/clause-1?done=not-a-unit")
    assert unknown.status_code == 200
    assert "data-rtc-completion" not in unknown.text
    uncompleted = client.get("/learn/clause-1?done=clause-1")
    assert "data-rtc-completion" not in uncompleted.text
    home = client.get("/?done=clause-1")
    assert "data-rtc-completion" not in home.text


def test_guest_cannot_complete(tmp_path: Path):
    client = _client(tmp_path, multiuser=True)
    post = client.post("/learn/clause-1/done", follow_redirects=False)
    assert post.status_code == 303
    assert post.headers["location"].startswith("/login")
    json_post = client.post(
        "/learn/clause-1/done",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )
    assert json_post.status_code == 303
    assert json_post.headers["location"].startswith("/login")
    assert "application/json" not in (json_post.headers.get("content-type") or "")
    page = client.get("/learn/clause-1?done=clause-1")
    assert page.status_code == 200
    assert "data-rtc-completion" not in page.text
    html = client.get("/learn/clause-1").text
    assert 'data-guest-action="mastered"' in html
    assert "learn-action-done" not in html


def test_completion_done_sound_asset_is_served(tmp_path: Path):
    client = _client(tmp_path)
    resp = client.get("/static/completion-done.mp3")
    assert resp.status_code == 200
    assert resp.content[:3] == b"ID3" or resp.content[:2] == b"\xff\xfb" or resp.content[:2] == b"\xff\xf3"
    js = client.get("/static/app.js").text
    assert "/static/completion-done.mp3" in js
    html = client.get("/").text
    assert "app.js?v=main53" in html
