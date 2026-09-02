"""Sprint 16 — Learn Type recall mode (textarea + per-word diff)."""

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


def test_learn_enables_type_tab_and_panel_markup(client: TestClient):
    response = client.get("/learn/clause-1")
    assert response.status_code == 200
    html = response.text
    assert 'data-learn-mode="type"' in html
    assert 'href="/learn/clause-1?mode=type"' in html
    assert "learn-panel-type" in html
    assert "data-type-text=" in html
    assert "data-type-input" in html
    assert "data-type-mirror" in html
    assert "Start typing…" in html
    assert "Type it from memory" in html
    assert "words · 0 correct" in html
    assert "app.js?v=main49" in html


def test_type_mode_query_param_renders_type_active(client: TestClient):
    response = client.get("/learn/clause-1?mode=type")
    assert response.status_code == 200
    html = response.text
    assert 'data-mode="type"' in html
    assert 'data-learn-mode="type"' in html
    assert "learn-panel-type" in html
    assert "(1) No person shall be convicted" in html


def test_type_css_drives_panel_and_diff_styles(client: TestClient):
    css = client.get("/static/styles.css?v=main49")
    assert css.status_code == 200
    text = css.text
    assert '.learn[data-mode="type"] .learn-panel-type' in text
    # Type reports a score, not a diff of the Bare Act wording — the mirror
    # marks the user's own words instead.
    assert ".learn-type-mirror-word.is-correct" in text
    assert ".learn-type-mirror-word.is-wrong" in text
    assert ".learn-type-word" not in text
    assert ".learn-type-diff" not in text
    # The struck-through diff went with the corrections view; wrong words are
    # now marked on the user's own text with a wavy underline.
    assert "underline wavy var(--browse-mark-news)" in text
    assert "underline solid var(--browse-due)" in text


def test_type_js_normalizes_and_scores_words(client: TestClient):
    js = client.get("/static/app.js?v=main49")
    assert js.status_code == 200
    text = js.text
    assert "normWord" in text
    assert "initType" in text
    assert "words · " in text
    assert "correct" in text


def test_type_shows_stem_for_subclause(client: TestClient):
    client.post("/learn/clause-2/choose", data={"mode": "letters"})
    response = client.get("/learn/clause-2-a?mode=type")
    assert response.status_code == 200
    assert "learn-stem" in response.text
