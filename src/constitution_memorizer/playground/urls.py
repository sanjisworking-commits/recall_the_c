"""Canonical Playground HTTP paths. Proof ``/playground/{law_id}`` is retired."""

from __future__ import annotations

PREFIX = "/playground"


def home_path() -> str:
    return PREFIX


def add_path(law_id: str) -> str:
    return f"{PREFIX}/laws/{law_id}/add"


def law_path(law_id: str) -> str:
    return f"{PREFIX}/laws/{law_id}"


def sections_path(law_id: str) -> str:
    return f"{PREFIX}/laws/{law_id}/sections"


def learn_path(law_id: str, number: str, mode: str = "cloze") -> str:
    return f"{PREFIX}/laws/{law_id}/sections/{number}/learn/{mode}"


def learn_complete_path(law_id: str, number: str, mode: str = "cloze") -> str:
    return f"{learn_path(law_id, number, mode)}/complete"
