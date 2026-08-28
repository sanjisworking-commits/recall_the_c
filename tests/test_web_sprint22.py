"""Sprint 22 — Explain it back gloss on Browse article."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]
AMENDMENT_UNITS = Path(__file__).parent / "fixtures" / "learning" / "amendment_units.json"
AMENDMENT_REVIEWED = Path(__file__).parent / "fixtures" / "learning" / "amendment_reviewed.json"
AMENDMENTS_SEED = ROOT / "data" / "reference" / "amendments.seed.json"
GLOSS_SEED = ROOT / "data" / "reference" / "gloss_placeholders.seed.json"
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"
MINI_REVIEWED = Path(__file__).parent / "fixtures" / "learning" / "mini_reviewed.json"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(
        units_path=AMENDMENT_UNITS,
        db_path=tmp_path / "progress.db",
        reviewed_path=AMENDMENT_REVIEWED,
        amendments_path=AMENDMENTS_SEED,
        gloss_placeholders_path=GLOSS_SEED,
    )
    return TestClient(app)


@pytest.fixture
def mini_client(tmp_path: Path) -> TestClient:
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "mini.db",
        reviewed_path=MINI_REVIEWED,
        amendments_path=AMENDMENTS_SEED,
        gloss_placeholders_path=GLOSS_SEED,
    )
    return TestClient(app)


def test_explain_back_section_on_every_article(client: TestClient):
    html = client.get("/browse/article/20").text
    assert "Explain it back" in html
    assert "explain-back-input" in html
    assert "In your own words, as if to a friend" in html
    assert "Saved automatically" in html
    assert "/static/styles.css?" in html


def test_gloss_placeholder_for_seeded_article(client: TestClient):
    html = client.get("/browse/article/14").text
    assert "e.g. The State must treat every person equally under the law…" in html


def test_put_gloss_persists_and_reload(client: TestClient):
    put = client.put(
        "/browse/article/21/gloss",
        json={"text": "Life and liberty need a fair process."},
    )
    assert put.status_code == 200
    body = put.json()
    assert body["ok"] is True
    assert body["words"] == 7

    html = client.get("/browse/article/21").text
    assert "Life and liberty need a fair process." in html
    assert "7 words · saved" in html
    assert "explain-back-clear" in html


def test_empty_put_deletes_gloss(client: TestClient):
    client.put("/browse/article/21/gloss", json={"text": "something"})
    cleared = client.put("/browse/article/21/gloss", json={"text": "   "})
    assert cleared.status_code == 200
    assert cleared.json()["words"] == 0
    html = client.get("/browse/article/21").text
    assert "Saved automatically — rewrite it whenever your understanding sharpens." in html


def test_delete_gloss(client: TestClient):
    client.put("/browse/article/15/gloss", json={"text": "plain meaning here"})
    deleted = client.delete("/browse/article/15/gloss")
    assert deleted.status_code == 200
    html = client.get("/browse/article/15").text
    assert "plain meaning here" not in html


def test_reset_progress_keeps_gloss(client: TestClient):
    client.put("/browse/article/14/gloss", json={"text": "equal under the law"})
    client.post("/learn/art-14/done")
    reset = client.post("/reset")
    assert reset.status_code in (303, 200)
    html = client.get("/browse/article/14").text
    assert "equal under the law" in html


def test_explain_back_css(mini_client: TestClient):
    css = mini_client.get("/static/styles.css?v=main45").text
    assert ".explain-back-input" in css
    assert "background: var(--paper)" in css
    assert ".explain-back-clear" in css
    js = mini_client.get("/static/app.js?v=main47").text
    assert "initExplainBack" in js
    assert "500" in js
