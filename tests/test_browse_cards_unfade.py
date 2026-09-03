"""Browse cards use solid ink colours for tracked and untracked alike."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from constitution_memorizer.progress.scheduler import ReminderEngine
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


def test_browse_cards_share_ink_chrome(tmp_path: Path):
    db = tmp_path / "progress.db"
    ReminderEngine.from_paths(db, MINI_UNITS)
    client = TestClient(create_app(units_path=MINI_UNITS, db_path=db))
    html = client.get("/browse").text
    assert "/static/styles.css?" in html
    assert "is-untracked" in html or "is-tracked" in html

    css = client.get("/static/styles.css?v=main59").text
    assert "--browse-untracked-fg" not in css
    assert "--browse-untracked-bg" not in css
    assert "--browse-untracked-border" not in css

    # Shared tracked/untracked rule keeps ink chrome.
    block = css.split(".browse-article-card.is-tracked,")[1].split("}")[0]
    assert "var(--ink)" in block
    assert "var(--paper)" in block

    title_rule = css.split(".browse-article-title {")[1].split("}")[0]
    assert "var(--ink)" in title_rule
    assert "var(--muted)" not in title_rule
