"""Sprint 26 — Settings page for notification frequency."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
MINI_REVIEWED = Path(__file__).parent / "fixtures" / "learning" / "mini_reviewed.json"
ROOT = Path(__file__).resolve().parents[1]
AMENDMENTS_SEED = ROOT / "data" / "reference" / "amendments.seed.json"
GLOSS_SEED = ROOT / "data" / "reference" / "gloss_placeholders.seed.json"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        reviewed_path=MINI_REVIEWED,
        amendments_path=AMENDMENTS_SEED,
        gloss_placeholders_path=GLOSS_SEED,
    )
    return TestClient(app)


def test_settings_page_defaults_to_thrice(client: TestClient):
    html = client.get("/settings").text
    assert "Study reminders" in html
    assert "Experience" in html
    assert "Completion sounds" in html
    assert "data-motion-set" in html
    assert "data-sound-set" in html
    assert "macos" in html
    assert "Memory log" in html
    assert 'value="thrice"' in html
    assert "checked" in html
    assert "/static/styles.css?" in html
    assert 'href="/settings"' in html


def test_settings_post_persists_hourly(client: TestClient, tmp_path: Path):
    # Recreate with known db path via a fresh app bound in fixture — use engine from state
    resp = client.post(
        "/settings",
        data={"notification_frequency": "hourly"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings?saved=1"

    html = client.get("/settings?saved=1").text
    assert "Settings saved" in html
    assert 'value="hourly"' in html
    # Browse — In news is site-wide and now lives at /admin/content.
    assert 'name="news_articles"' not in html

    # Confirm via engine on same DB: TestClient shares app.state.engine
    eng: ReminderEngine = client.app.state.engine  # type: ignore[attr-defined]
    assert eng.get_notification_frequency() == "hourly"


def test_settings_rejects_invalid(client: TestClient):
    resp = client.post(
        "/settings",
        data={"notification_frequency": "weekly"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
