"""Deterministic Cloze derivation from canonical Bare Act wording.

No LLM. No stored transformed statute. Density mirrors Constitution:
Light / Medium / Heavy letter-length thresholds.
"""

from __future__ import annotations

from constitution_memorizer.playground.cloze import has_cloze_blanks, letter_len

DENSITY_THRESHOLDS: dict[str, int] = {
    "light": 8,
    "medium": 6,
    "heavy": 4,
}
DEFAULT_DENSITY = "medium"


def cloze_threshold(density: str) -> int:
    return DENSITY_THRESHOLDS.get(density, DENSITY_THRESHOLDS[DEFAULT_DENSITY])


def cloze_blank_indexes(text: str, *, density: str = DEFAULT_DENSITY) -> list[int]:
    threshold = cloze_threshold(density)
    words = text.split()
    return [index for index, word in enumerate(words) if letter_len(word) >= threshold]


def cloze_can_run(text: str) -> bool:
    return has_cloze_blanks(text)


def cloze_needs_fallback(text: str, *, density: str = "heavy") -> bool:
    """Every selected non-empty section must enter Cloze.

    When no word meets even the Heavy density floor, the mode still opens
    on canonical text instead of fake-completing.
    """

    return not cloze_blank_indexes(text, density=density)
