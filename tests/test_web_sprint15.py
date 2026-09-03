"""Sprint 15 — Learn Letters recall mode (first-letter initials ⇄ full text)."""

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


def test_learn_enables_letters_tab_and_panel_markup(client: TestClient):
    response = client.get("/learn/clause-1")
    assert response.status_code == 200
    html = response.text
    assert 'data-learn-mode="letters"' in html
    assert 'href="/learn/clause-1?mode=letters"' in html
    assert "learn-panel-letters" in html
    assert "data-letters-text=" in html
    assert "data-letters-toggle" in html
    assert "data-letters-speak" in html
    assert "data-letters-check" in html
    assert "data-letters-display" in html
    assert "data-letters-manual" in html
    assert "Full text" in html
    # Speak and check are one button now; "Check phrase" is a JS label.
    assert "data-letters-speak" in html
    assert "data-letters-check" not in html.split("data-letters-check-text")[0]
    assert "Use the first letters." in html
    assert "speech_client.js?v=speech2" in html
    assert "app.js?v=main53" in html
    assert "speech_align.js" not in html


def test_letters_mode_query_param_renders_letters_active(client: TestClient):
    response = client.get("/learn/clause-1?mode=letters")
    assert response.status_code == 200
    html = response.text
    assert 'data-mode="letters"' in html
    assert 'data-learn-mode="letters"' in html
    assert "learn-panel-letters" in html
    assert "(1) No person shall be convicted" in html


def test_letters_css_drives_panel_and_initials_styles(client: TestClient):
    css = client.get("/static/styles.css?v=main53")
    assert css.status_code == 200
    text = css.text
    assert '.learn[data-mode="letters"] .learn-panel-letters' in text
    assert ".learn-letters-text.is-initials" in text
    initials = text.split(".learn-letters-text.is-initials {", 1)[1].split("}", 1)[0]
    assert "var(--font-display)" in initials
    assert "letter-spacing: 0.24em" in initials
    assert "font-weight: 600" in initials
    assert ".learn-letters-text.is-full" in text
    full = text.split(".learn-letters-text.is-full {", 1)[1].split("}", 1)[0]
    assert "var(--font-display)" in full
    assert "letter-spacing: normal" in full
    assert ".learn-letters-cue.is-correct" in text
    assert ".learn-letters-cue.is-wrong" in text
    assert ".learn-letters-cue.is-listening" in text
    assert ".learn-letters-cue.is-structural" in text
    assert "--letters-correct" in text
    assert "prefers-reduced-motion" in text


def test_letters_js_builds_initials_like_prototype(client: TestClient):
    js = client.get("/static/app.js?v=main53")
    assert js.status_code == 200
    text = js.text
    assert "initialsFor" in text
    assert "earliestUnresolvedIndex" in text
    assert "fromIndex" in text
    assert "applyAlignment" in text
    assert "Back to initials" in text
    assert "Full text" in text
    assert "Checking…" in text
    assert "RecallSpeech" in text
    assert "webkitSpeechRecognition" not in text
    assert "SpeechRecognition" not in text
    assert "markModeAttempted" in text
    assert 'markModeAttempted("letters")' in text
    assert 'markModeAttempted("test")' not in text
    assert "is-correct" in text
    assert "is-wrong" in text
    assert "is-listening" in text
    # Renamed and hoisted: Type skips clause markers using the same rule.
    assert "isStructuralToken" in text
    assert "LETTERS_ADVANCE_RATIO = 0.8" in text
    assert "is-structural" in text
    assert r"/^[A-Za-z]/" in text or "/^[A-Za-z]/" in text


def test_letters_shows_stem_for_subclause(client: TestClient):
    client.post("/learn/clause-2/choose", data={"mode": "letters"})
    response = client.get("/learn/clause-2-a?mode=letters")
    assert response.status_code == 200
    assert "learn-stem" in response.text
