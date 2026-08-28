"""Sprint 5 tests: Browse, Search, Progress."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.progress_stats import article_progress, path_units_for_article
from constitution_memorizer.web.search import parse_search_query, resolve_search

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
MINI_REVIEWED = Path(__file__).parent / "fixtures" / "learning" / "mini_reviewed.json"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        reviewed_path=MINI_REVIEWED,
    )
    return TestClient(app)


@pytest.fixture
def engine(tmp_path: Path) -> ReminderEngine:
    return ReminderEngine.from_paths(tmp_path / "progress.db", MINI_UNITS)


def test_parse_search_query_shapes():
    assert parse_search_query("20") == ("20", None, None)
    assert parse_search_query("Article 20(2)") == ("20", "2", None)
    assert parse_search_query("19(1)(a)") == ("19", "1", "a")
    assert parse_search_query("nonsense") is None


def test_search_article_redirects_to_browse(client: TestClient):
    response = client.get("/search", params={"q": "21"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/browse/article/21"


def test_search_clause_redirects_to_choose(client: TestClient):
    response = client.get("/search", params={"q": "20(3)"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/learn/clause-2/choose"


def test_resolve_search_clause_and_letter(engine: ReminderEngine):
    # mini fixture ids are synthetic: clause-2 is Article 20(3)
    hit = resolve_search(engine, "20(3)")
    assert hit.redirect_url == "/learn/clause-2/choose"

    hit_letter = resolve_search(engine, "20(3)(a)")
    assert hit_letter.redirect_url == "/learn/clause-2-a"
    assert engine.get_split_preference("clause-2") == "letters"

    # After preference exists, clause search goes straight to learn/letters entry.
    hit_again = resolve_search(engine, "20(3)")
    assert hit_again.redirect_url == "/learn/clause-2-a"


def test_browse_article_shows_text_and_learn_cta(client: TestClient):
    response = client.get("/browse/article/20")
    assert response.status_code == 200
    assert "Protection in respect of conviction" in response.text
    assert "Learn" in response.text
    assert "/learn/" in response.text
    assert "article-adjacent" in response.text
    assert "article-adjacent-footer" not in response.text
    assert response.text.count("Article 21 →") == 1
    assert 'href="/browse/article/21"' in response.text
    assert "← First article" in response.text
    assert "LearningUnitType" not in response.text
    assert "checklist-meta" not in response.text
    assert " · 60s" not in response.text and " · 30s" not in response.text


def test_browse_article_text_has_no_leading_indent(client: TestClient):
    """`.unit-text` uses pre-wrap; template indent must not precede Bare Act text."""
    response = client.get("/browse/article/20")
    assert response.status_code == 200
    match = re.search(
        r'<article class="unit-text browse-article-text"[^>]*>([\s\S]*?)</article>',
        response.text,
    )
    assert match is not None
    inner = match.group(1)
    assert not inner.startswith(("\n", " ", "\t"))
    assert "No person shall be convicted" in inner[:80]


def test_browse_article_prev_next_on_last(client: TestClient):
    response = client.get("/browse/article/21")
    assert response.status_code == 200
    assert 'href="/browse/article/20"' in response.text
    assert response.text.count("← Article 20") == 1
    assert "Last article →" in response.text
    assert "article-adjacent-footer" not in response.text


def test_browse_index(client: TestClient):
    response = client.get("/browse")
    assert response.status_code == 200
    assert "Article 20" in response.text
    assert "Article 21" in response.text


def test_progress_page_and_article_completion(client: TestClient, engine: ReminderEngine):
    # Mark letter path progress after choosing letters
    engine.set_split_preference("clause-2", "letters")
    required, pending = path_units_for_article(engine, "20")
    assert pending is False
    assert [u.id for u in required] == ["clause-1", "clause-2-a", "clause-2-b"]

    engine.mark_all_modes_seen("clause-1")
    engine.mark_done("clause-1")
    engine.mark_all_modes_seen("clause-2-a")
    engine.mark_done("clause-2-a")
    row = article_progress(engine, "20")
    assert row is not None
    assert row.completed == 2
    assert row.required == 3
    assert row.percent == pytest.approx(66.7, abs=0.1)

    # Fresh client/app shares no state — exercise HTML with its own DB via posts
    client.post("/learn/clause-2/choose", data={"mode": "whole"})
    client.post("/learn/clause-1/done")
    page = client.get("/progress")
    assert page.status_code == 200
    assert "Progress" in page.text
    assert "Mastery map" in page.text
    assert "Tracked articles" in page.text


def test_progress_mastered_archive_is_additive(client: TestClient):
    home = client.get("/progress")
    assert home.status_code == 200
    archive = client.get("/progress/mastered")
    assert archive.status_code == 200
    assert "Mastered" in archive.text
    assert 'href="/progress"' in archive.text
