"""Sprint 18 — Recite voice accuracy (Web Speech API + LCS map)."""

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


def test_recite_panel_has_voice_and_map_markup(client: TestClient):
    response = client.get("/learn/clause-1?mode=recite")
    assert response.status_code == 200
    html = response.text
    assert 'data-mode="recite"' in html
    assert "data-recite-text=" in html
    assert "data-recite-transcript" in html
    assert "data-recite-map" in html
    assert "data-recite-stats" in html
    assert "data-recite-extras" in html
    assert "data-recite-status" in html
    assert "Speak the Bare Act aloud" in html
    assert "data-recite-toggle" in html
    assert "data-recite-peek" in html
    assert "Hold to peek" in html
    assert "data-recite-fallback" in html
    assert "data-recite-manual" in html
    assert "data-recite-check" in html
    assert "Check accuracy" in html
    assert "recall_align.js?v=sprint22" in html
    assert "speech_client.js?v=speech2" in html
    assert "app.js?v=main49" in html
    # Guards against a stale cache-bust shipping with new markup.
    assert "app.js?v=main26" not in html


def test_recite_css_map_and_listening_styles(client: TestClient):
    css = client.get("/static/styles.css?v=main49")
    assert css.status_code == 200
    text = css.text
    assert ".learn-recite-map-word.is-hit" in text
    assert ".learn-recite-map-word.is-miss" in text
    assert ".learn-recite-status.is-listening" in text
    assert ".learn-recite-transcript.is-live" in text
    assert ".learn-recite-fallback" in text


def test_recite_js_wires_speech_client_and_align(client: TestClient):
    js = client.get("/static/app.js?v=main49")
    assert js.status_code == 200
    text = js.text
    assert "SpeechRecognition" not in text
    assert "webkitSpeechRecognition" not in text
    assert "RecallSpeech" in text
    assert "RecallAlign" in text
    assert "alignText" in text
    assert "Accuracy map" in text
    assert "microphone access" in text
    assert "abortForServiceFailure" in text
    assert 'mode: "recite"' in text


def test_speech_client_js_served(client: TestClient):
    js = client.get("/static/speech_client.js?v=speech2")
    assert js.status_code == 200
    text = js.text
    assert "RecallSpeech" in text
    assert "/speech/transcribe" in text
    assert "MediaRecorder" in text
    assert "from_index" in text
    assert "expected" not in text.lower() or "no expected" in text.lower()


def test_recall_align_js_served(client: TestClient):
    js = client.get("/static/recall_align.js?v=sprint22")
    assert js.status_code == 200
    text = js.text
    assert "alignTokens" in text
    assert "normWord" in text
    assert "statsLabel" in text
