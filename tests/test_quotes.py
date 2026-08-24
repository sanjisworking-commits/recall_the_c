"""Curated quotes catalog and deterministic selection."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from constitution_memorizer.web.quotes import get_quote_for, load_quotes

QUOTES_PATH = Path(__file__).resolve().parents[1] / "data" / "reference" / "quotes.json"

_TRAILING_INCOMPLETE = re.compile(r"([,;:—–-]|\.\.\.)\s*$")


def test_quotes_json_loads_with_schema():
    quotes = load_quotes(QUOTES_PATH)
    assert quotes
    for row in quotes:
        assert set(row.keys()) == {"text", "author"}
        assert isinstance(row["text"], str) and row["text"].strip()
        assert isinstance(row["author"], str) and row["author"].strip()
        assert 40 <= len(row["text"]) <= 220


def test_quotes_catalog_is_english_and_complete():
    quotes = load_quotes(QUOTES_PATH)
    assert quotes
    for row in quotes:
        text = row["text"]
        assert not text[:1].islower()
        assert _TRAILING_INCOMPLETE.search(text) is None
        other = letters = 0
        for ch in text:
            if not ch.isalpha():
                continue
            letters += 1
            if "LATIN" not in unicodedata.name(ch, ""):
                other += 1
        if letters:
            assert other / letters < 0.15
    blob = "\n".join(row["text"] for row in quotes)
    for needle in (
        "No hay caminos",
        "Debemos ser el cambio",
        "Hanibal Barca",
        "Guns are our friends because",
        "Keinginan yang sungguh",
        "Vivre simplement, pour que",
        "La grandezza di una nazione",
    ):
        assert needle not in blob


def test_get_quote_for_is_deterministic():
    quotes = load_quotes(QUOTES_PATH)
    seed = "00000000-0000-4000-8000-000000000001:clause-1:2026-08-14:2"
    first = get_quote_for(quotes, seed)
    second = get_quote_for(quotes, seed)
    assert first == second
    other = get_quote_for(quotes, seed + ":x")
    assert other is not None
    # Different seed may collide but almost always differs on this catalog.
    assert first != other or len(quotes) == 1


def test_get_quote_for_empty_catalog():
    assert get_quote_for([], "anything") is None
