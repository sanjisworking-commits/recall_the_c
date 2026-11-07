"""Constitution Schedules appear on Browse after Parts I–XXII as read-only cards."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.browse import load_browse_schedules_seed
from constitution_memorizer.web.schedules import (
    browse_schedule_cards,
    build_schedule_view,
    load_schedule_bodies,
)

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


def test_browse_schedules_seed_has_all_twelve():
    seed = load_browse_schedules_seed()
    slugs = [row["slug"] for row in seed]
    assert slugs == [
        "first",
        "second",
        "third",
        "fourth",
        "fifth",
        "sixth",
        "seventh",
        "eighth",
        "ninth",
        "tenth",
        "eleventh",
        "twelfth",
    ]
    assert seed[0]["ord"] == "First"
    assert seed[-1]["ord"] == "Twelfth"
    assert seed[0]["refs"] == "Arts. 1, 4"


def test_browse_schedule_cards_are_read_only():
    cards = browse_schedule_cards()
    assert len(cards) == 12
    assert cards[0].href == "/browse/schedules/first"
    assert cards[0].ord == "First"
    assert cards[6].title == "Union, State and Concurrent Lists"


def test_browse_index_lists_designed_schedule_cards(tmp_path: Path):
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
        )
    )
    html = client.get("/browse").text
    assert "Twelve Schedules annexed to the Constitution" in html
    assert "First Schedule" in html
    assert "Twelfth Schedule" in html
    assert "Emoluments, allowances and privileges" in html
    assert "Arts. 1, 4" in html
    assert 'href="/browse/schedules/first"' in html
    assert 'href="/browse/schedules/twelfth"' in html
    assert 'id="schedules"' in html
    assert "browse-schedule-card" in html
    assert "Learn" not in html.split("id=\"schedules\"", 1)[1][:800]


def test_browse_schedule_pages(tmp_path: Path):
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
        )
    )
    first = client.get("/browse/schedules/first")
    assert first.status_code == 200
    assert "The States and the Union territories" in first.text
    assert "Andhra Pradesh" in first.text
    assert "Read-only reference" in first.text
    assert first.text.count("[Articles 1 and 4]") == 1
    assert 'href="/learn/' not in first.text
    assert 'href="/browse/schedules/second"' in first.text

    seventh = client.get("/browse/schedules/seventh")
    assert seventh.status_code == 200
    assert "Union List" in seventh.text
    assert "Defence of India" in seventh.text
    assert "100 entries" in seventh.text
    assert "List I" in seventh.text

    eighth = client.get("/browse/schedules/eighth")
    assert eighth.status_code == 200
    assert "Assamese" in eighth.text
    assert "Konkani" in eighth.text
    assert "Added 2003" in eighth.text

    third = client.get("/browse/schedules/third")
    assert third.status_code == 200
    assert "Form I" in third.text
    assert "do swear in the name of God" in third.text
    assert "solemnly affirm" in third.text

    sixth = client.get("/browse/schedules/sixth")
    assert sixth.status_code == 200
    assert "Autonomous districts and autonomous regions" in sixth.text
    assert "20BA" in sixth.text

    ninth = client.get("/browse/schedules/ninth")
    assert ninth.status_code == 200
    assert "The Bihar Land Reforms Act, 1950" in ninth.text
    assert "284." in ninth.text

    legacy = client.get("/browse/schedule/first", follow_redirects=False)
    assert legacy.status_code == 301
    assert legacy.headers["location"] == "/browse/schedules/first"


def test_unknown_schedule_is_404(tmp_path: Path):
    client = TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
        )
    )
    assert client.get("/browse/schedules/thirteenth").status_code == 404


def test_build_schedule_view_has_typed_blocks():
    first = build_schedule_view(None, "first")
    assert first is not None
    kinds = {block.get("t") for block in first.blocks}
    assert "table" in kinds
    assert "ref" in kinds
    assert first.cite == "[Articles 1 and 4]"
    assert first.blocks[0]["s"] == "[Articles 1 and 4]"
    tenth = build_schedule_view(None, "tenth")
    assert tenth is not None
    assert any(block.get("title") == "Interpretation" for block in tenth.blocks)


def test_sixth_and_ninth_match_official_extract():
    sixth = build_schedule_view(None, "sixth")
    assert sixth is not None
    assert sum(1 for block in sixth.blocks if block.get("t") == "sec") == 29
    assert sum(1 for block in sixth.blocks if block.get("t") == "cl") == 172

    ninth = build_schedule_view(None, "ninth")
    assert ninth is not None
    paragraphs = [block.get("s") or "" for block in ninth.blocks if block.get("t") == "p"]
    assert any(text.startswith("1.") for text in paragraphs)
    assert any("284." in text for text in paragraphs)
    assert len(paragraphs) >= 284

    seventh = build_schedule_view(None, "seventh")
    assert seventh is not None
    lists = [block for block in seventh.blocks if block.get("t") == "list"]
    assert [block.get("id") for block in lists] == ["I", "II", "III"]
    assert [len(block.get("rows") or []) for block in lists] == [100, 61, 52]
    assert lists[0].get("open") is True

    bodies = load_schedule_bodies()
    assert set(bodies) == {
        "first",
        "second",
        "third",
        "fourth",
        "fifth",
        "sixth",
        "seventh",
        "eighth",
        "ninth",
        "tenth",
        "eleventh",
        "twelfth",
    }
