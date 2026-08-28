"""Admin → Content: Browse "In news" is site-wide, so it lives behind the
admin guard rather than on a user's Settings page."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.multiuser.settings import clear_settings_cache
from constitution_memorizer.progress.repository import ProgressRepository

from tests.test_admin_preview import _client

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


@pytest.fixture(autouse=True)
def _fresh_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_admin_content_page_shows_the_news_field(tmp_path: Path) -> None:
    client, _repo = _client(tmp_path)
    page = client.get("/admin/content")
    assert page.status_code == 200
    assert 'name="news_articles"' in page.text
    assert "In news" in page.text


def test_admin_can_save_news_articles(tmp_path: Path) -> None:
    client, _repo = _client(tmp_path)
    csrf = client.cookies.get("rtc_csrf")
    saved = client.post(
        "/admin/content",
        data={"csrf_token": csrf, "news_articles": "19, 21"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    engine = client.app.state.engine  # type: ignore[attr-defined]
    assert engine.get_news_articles_raw() == "19, 21"


def test_non_admin_cannot_reach_or_write_content(tmp_path: Path) -> None:
    client, _repo = _client(tmp_path, make_admin=False)
    assert client.get("/admin/content").status_code in (403, 404)

    csrf = client.cookies.get("rtc_csrf")
    blocked = client.post(
        "/admin/content",
        data={"csrf_token": csrf, "news_articles": "99"},
        follow_redirects=False,
    )
    assert blocked.status_code in (403, 404)
    engine = client.app.state.engine  # type: ignore[attr-defined]
    assert engine.get_news_articles_raw() != "99"
