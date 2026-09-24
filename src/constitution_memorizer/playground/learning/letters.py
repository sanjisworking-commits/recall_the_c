"""Letters mode: first letters from canonical text at request time.

Never persist initials as a statutory copy.
"""

from __future__ import annotations


def first_letters_display(text: str) -> str:
    parts: list[str] = []
    for word in text.split():
        initial = next((ch for ch in word if ch.isalpha()), "")
        parts.append(initial or word[:1])
    return " ".join(parts)
