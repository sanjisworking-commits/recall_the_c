"""Cloze eligibility for Playground — independent of Constitution Learn."""

from __future__ import annotations

# Same floor as Constitution has_cloze_blanks / app.js heavy density.
_MIN_LETTER_LEN = 4


def letter_len(word: str) -> int:
    return sum(1 for ch in word if ch.isascii() and ch.isalpha())


def has_cloze_blanks(text: str) -> bool:
    return any(letter_len(word) >= _MIN_LETTER_LEN for word in text.split())
