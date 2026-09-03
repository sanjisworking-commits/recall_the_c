"""Sprint 17 — Learn Recite recall mode (blurred text + hold-to-peek)."""

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


def test_learn_enables_recite_tab_and_panel_markup(client: TestClient):
    response = client.get("/learn/clause-1")
    assert response.status_code == 200
    html = response.text
    assert 'data-learn-mode="recite"' in html
    assert 'href="/learn/clause-1?mode=recite"' in html
    assert "learn-panel-recite" in html
    assert "learn-recite-text" in html
    assert "is-blurred" in html
    assert "data-recite-toggle" in html
    assert "data-recite-peek" in html
    assert "Hold to peek" in html
    assert "Start reciting" in html
    assert "Speak the Bare Act aloud" in html
    assert "app.js?v=main57" in html
    assert "Coming in later sprints" not in html


def test_recite_mode_query_param_renders_recite_active(client: TestClient):
    response = client.get("/learn/clause-1?mode=recite")
    assert response.status_code == 200
    html = response.text
    assert 'data-mode="recite"' in html
    assert 'data-learn-mode="recite"' in html
    assert "learn-panel-recite" in html
    assert "(1) No person shall be convicted" in html


def test_recite_css_blur_and_panel_visibility(client: TestClient):
    css = client.get("/static/styles.css?v=main57")
    assert css.status_code == 200
    text = css.text
    assert '.learn[data-mode="recite"] .learn-panel-recite' in text
    assert ".learn-recite-text.is-blurred" in text
    # diff.md item 7 moved the reveal to the design's 5px / 0.25s.
    assert "filter: blur(5px)" in text
    assert ".learn-recite-toggle.is-active" in text
    assert "var(--destructive)" in text


def test_recite_js_handles_start_stop_and_peek(client: TestClient):
    js = client.get("/static/app.js?v=main57")
    assert js.status_code == 200
    text = js.text
    assert "initRecite" in text
    # The recording label is just "Stop" now — the same one-slot CTA cycle as
    # Letters (Start reciting → Stop → Next), so the two modes read alike.
    assert '"Stop"' in text
    assert "Stop and score" not in text
    assert "Start reciting" in text
    assert "touchstart" in text
    assert "mousedown" in text


def test_recite_shows_stem_for_subclause(client: TestClient):
    client.post("/learn/clause-2/choose", data={"mode": "letters"})
    response = client.get("/learn/clause-2-a?mode=recite")
    assert response.status_code == 200
    assert "learn-stem" in response.text
