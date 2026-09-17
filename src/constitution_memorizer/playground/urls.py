"""Canonical Playground HTTP paths. Proof ``/playground/{law_id}`` is retired."""

from __future__ import annotations

PREFIX = "/playground"


def home_path() -> str:
    return PREFIX


def roster_path(*, add: str | None = None) -> str:
    if add:
        return f"{PREFIX}/roster?add={add}"
    return f"{PREFIX}/roster"


def add_path(law_id: str) -> str:
    return f"{PREFIX}/laws/{law_id}/add"


def remove_path(law_id: str) -> str:
    return f"{PREFIX}/roster/{law_id}/remove"


def law_path(law_id: str) -> str:
    return f"{PREFIX}/laws/{law_id}"


def sections_path(law_id: str) -> str:
    return f"{PREFIX}/laws/{law_id}/sections"


def learn_path(law_id: str, number: str, mode: str = "cloze") -> str:
    return f"{PREFIX}/laws/{law_id}/sections/{number}/learn/{mode}"


def learn_complete_path(law_id: str, number: str, mode: str = "cloze") -> str:
    return f"{learn_path(law_id, number, mode)}/complete"
