"""Sprint 13 — sixth recall mode panel (Card, since replaced by Test)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
    )
    return TestClient(app)


def test_learn_enables_test_tab_and_quiz_markup(client: TestClient):
    response = client.get("/learn/clause-1")
    assert response.status_code == 200
    html = response.text
    assert 'data-learn-mode="read"' in html
    assert 'data-learn-mode="test"' in html
    assert 'href="/learn/clause-1?mode=test"' in html
    assert 'href="/learn/clause-1?mode=read"' in html
    assert "learn-panel-test" in html
    assert "data-quiz-form" in html
    assert "data-quiz-cycle" in html
    assert "Check answers" in html
    assert 'data-mode="read"' in html
    assert "app.js?v=main44" in html


def test_test_mode_query_param_renders_test_active(client: TestClient):
    """Tab switch must work even without JS via ?mode=test."""
    response = client.get("/learn/clause-1?mode=test")
    assert response.status_code == 200
    html = response.text
    assert 'data-mode="test"' in html
    assert 'data-learn-mode="test"' in html
    assert 'aria-selected="true"' in html
    assert "New questions each revision." in html


def test_legacy_card_mode_redirects_to_test(client: TestClient):
    """Old ?mode=card bookmarks canonicalize to ?mode=test, params intact."""
    resp = client.get("/learn/clause-1?mode=card", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/learn/clause-1?mode=test"
    resp = client.get(
        "/learn/clause-1?mode=card&claim=1", follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/learn/clause-1?mode=test&claim=1"
    # card is not a runtime mode anywhere anymore
    followed = client.get("/learn/clause-1?mode=card")
    assert 'data-mode="test"' in followed.text


def test_test_css_drives_panel_visibility(client: TestClient):
    css = client.get("/static/styles.css")
    assert css.status_code == 200
    text = css.text
    assert '.learn[data-mode="test"] .learn-panel-test' in text
    assert ".learn-panel-test" in text
    assert "display: none" in text
    assert ".learn-card" not in text  # flip styles fully retired


def test_quiz_answers_never_render_in_html(client: TestClient):
    html = client.get("/learn/clause-1?mode=test").text
    panel_start = html.index('data-learn-panel="test"')
    panel_chunk = html[panel_start:]
    assert "answer_index" not in panel_chunk
    assert "answer_text" not in panel_chunk
    # The stem stays out of the test panel (design hasStem).
    assert "learn-stem" not in panel_chunk[:1200]
