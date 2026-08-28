"""Sprint 14 — Learn Cloze recall mode (tap-to-reveal blanks)."""

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


def test_learn_enables_cloze_tab_and_panel_markup(client: TestClient):
    response = client.get("/learn/clause-1")
    assert response.status_code == 200
    html = response.text
    assert 'data-learn-mode="cloze"' in html
    assert 'href="/learn/clause-1?mode=cloze"' in html
    assert "learn-panel-cloze" in html
    assert "data-cloze-text=" in html
    assert 'data-cloze-action="toggle-all"' in html
    assert "Reveal all" in html
    assert "revealed — tap a blank" in html
    assert 'data-cloze-density="light"' in html
    assert 'data-cloze-density="medium"' in html
    assert 'data-cloze-density="heavy"' in html
    assert "app.js?v=main46" in html


def test_cloze_mode_query_param_renders_cloze_active(client: TestClient):
    response = client.get("/learn/clause-1?mode=cloze")
    assert response.status_code == 200
    html = response.text
    assert 'data-mode="cloze"' in html
    assert 'data-learn-mode="cloze"' in html
    assert "learn-panel-cloze" in html
    assert "(1) No person shall be convicted" in html


def test_cloze_css_drives_panel_visibility_and_blank_styles(client: TestClient):
    css = client.get("/static/styles.css?v=main45")
    assert css.status_code == 200
    text = css.text
    assert '.learn[data-mode="cloze"] .learn-panel-cloze' in text
    assert ".learn-cloze-word.is-blank:not(.is-revealed)" in text
    assert "color: transparent" in text
    assert "border-bottom: 2px solid var(--ink)" in text
    assert ".learn-cloze-word.is-revealed" in text
    assert "font-weight: 600" in text


def test_cloze_shows_stem_for_subclause_unlike_test(client: TestClient):
    """Design hasStem: subclause stem for Cloze, hidden only on Test."""
    # Prefer letters so Learn opens the subclause (not Choose / whole clause).
    client.post(
        "/learn/clause-2/choose",
        data={"mode": "letters"},
        follow_redirects=False,
    )
    cloze = client.get("/learn/clause-2-a?mode=cloze")
    assert cloze.status_code == 200
    assert "learn-stem" in cloze.text

    test_page = client.get("/learn/clause-2-a?mode=test")
    assert test_page.status_code == 200
    # Stem still in markup (shared), but CSS hides it for test mode.
    assert "learn-stem" in test_page.text
    css = client.get("/static/styles.css?v=main45").text
    assert '.learn[data-mode="test"] .learn-stem' in css
    assert "display: none" in css


def test_app_js_includes_cloze_density_thresholds(client: TestClient):
    js = client.get("/static/app.js?v=main46")
    assert js.status_code == 200
    text = js.text
    assert "light: 8" in text
    assert "medium: 6" in text
    assert "heavy: 4" in text
    assert "toggle-all" in text
    assert "Hide again" in text
