"""Sprint 21 — Amendment history (Browse timeline + Learn footnote)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.web.amendments import load_amendments
from constitution_memorizer.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]
AMENDMENT_UNITS = Path(__file__).parent / "fixtures" / "learning" / "amendment_units.json"
AMENDMENT_REVIEWED = Path(__file__).parent / "fixtures" / "learning" / "amendment_reviewed.json"
AMENDMENTS_SEED = ROOT / "data" / "reference" / "amendments.seed.json"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(
        units_path=AMENDMENT_UNITS,
        db_path=tmp_path / "progress.db",
        reviewed_path=AMENDMENT_REVIEWED,
        amendments_path=AMENDMENTS_SEED,
    )
    return TestClient(app)


def test_load_amendments_seed():
    catalog = load_amendments(AMENDMENTS_SEED)
    assert "15" in catalog
    assert len(catalog["15"].amendments) == 3
    assert catalog["14"].amendments == []
    assert catalog["14"].learn_note is None
    assert catalog["15"].learn_note is not None


def test_browse_article_15_shows_timeline(client: TestClient):
    html = client.get("/browse/article/15").text
    assert "Amendment history" in html
    assert "1st Amdt" in html
    assert "93rd Amdt" in html
    assert "103rd Amdt" in html
    assert "Inserted clause (4)" in html
    assert "3 amendments" in html
    assert "amendment-timeline" in html
    assert "/static/styles.css?" in html


def test_browse_article_14_shows_unamended(client: TestClient):
    html = client.get("/browse/article/14").text
    assert "Unamended — this article reads today exactly as adopted in 1950." in html
    assert "Amendment history" not in html
    assert "unamended" in html


def test_browse_article_20_omits_amendment_block(client: TestClient):
    html = client.get("/browse/article/20").text
    assert "Amendment history" not in html
    assert "Unamended —" not in html
    assert "amendment-timeline" not in html


def test_learn_footnote_for_15_and_not_14(client: TestClient):
    html15 = client.get("/learn/art-15").text
    assert "learn-amend-note" in html15
    assert "Amended thrice" in html15
    assert "✦" in html15

    html14 = client.get("/learn/art-14").text
    assert "learn-amend-note" not in html14

    html20 = client.get("/learn/art-20").text
    assert "learn-amend-note" not in html20


def test_amendment_css(client: TestClient):
    css = client.get("/static/styles.css?v=main43").text
    assert ".amendment-badge" in css
    assert ".amendment-timeline" in css
    assert ".learn-amend-note" in css
    assert ".amendment-unamended" in css
