"""Curator filters for the civic quotes catalog."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_build_quotes():
    path = ROOT / "scripts" / "build_quotes.py"
    spec = importlib.util.spec_from_file_location("build_quotes", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


bq = _load_build_quotes()

KEEP = {
    "text": (
        "Your beliefs become your thoughts, Your thoughts become your words, "
        "Your words become your actions, Your actions become your habits."
    ),
    "author": "Mahatma Gandhi",
}


def test_curate_drops_non_english_scripts_and_latin():
    rows = [
        KEEP,
        {
            "text": "जीवन में सफलता पाने के लिए मेहनत जरूरी है और कुछ नहीं चलता है भाई।",
            "author": "Unknown",
        },
        {
            "text": "السلام عليكم ورحمة الله وبركاته هذا نص عربي طويل بما يكفي الآن.",
            "author": "Unknown",
        },
        {
            "text": "Жизнь даётся человеку один раз и прожить её надо так чтобы не было мучительно.",
            "author": "Unknown",
        },
        {
            "text": "No hay caminos para la paz; la paz es el camino.",
            "author": "Mahatma Gandhi",
        },
        {
            "text": "Keinginan yang sungguh-sungguh dan murni pasti terkabul pada waktunya.",
            "author": "Unknown",
        },
    ]
    kept, stats = bq.curate(rows)
    texts = {row["text"] for row in kept}
    assert KEEP["text"] in texts
    assert stats["non_english"] == 5
    assert len(kept) == 1


def test_curate_drops_incomplete_scrapes():
    rows = [
        KEEP,
        {
            "text": "Guns are our friends because in a country without guns, I'm what's known as",
            "author": "Unknown",
        },
        {
            "text": "and then you win by showing up every single day of the year.",
            "author": "Mahatma Gandhi",
        },
        {
            "text": "I had nothing to escape from except my own inner doubt. I",
            "author": "Barack Obama",
        },
        {
            "text": (
                "They can kill me, but they cannot kill my ideas. They can crush "
                "my body, but they cannot crush my spirit now."
            ),
            "author": "and then you win”",
        },
    ]
    kept, stats = bq.curate(rows)
    texts = {row["text"] for row in kept}
    assert KEEP["text"] in texts
    assert stats["incomplete"] == 3
    assert stats["junk_author"] == 1
    assert len(kept) == 1


def test_curate_keeps_english_aphorisms():
    rows = [
        KEEP,
        {
            "text": (
                "What I used to say to people, when I was much more engagé myself, "
                "is that you can't be apolitical."
            ),
            "author": "Christopher Hitchens",
        },
        {
            "text": "Live life like you'll die tomorrow, learn like you'll live forever now.",
            "author": "Mahatma Gandhi",
        },
        {
            "text": (
                "Whatever you do in life will be insignificant, but it's very "
                "important that you do it, because nobody else will"
            ),
            "author": "Mahatma Gandhi",
        },
    ]
    kept, _stats = bq.curate(rows)
    assert {row["text"] for row in kept} == {row["text"] for row in rows}


def test_curate_strips_trailing_author_quotes():
    rows = [
        {
            "text": (
                "They can kill me, but they cannot kill my ideas. They can crush "
                "my body, but they cannot crush my spirit now."
            ),
            "author": "Bhagat Singh”",
        }
    ]
    kept, _stats = bq.curate(rows)
    assert len(kept) == 1
    assert kept[0]["author"] == "Bhagat Singh"
