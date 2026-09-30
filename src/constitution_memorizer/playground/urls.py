"""Canonical Playground HTTP paths. Proof ``/playground/{law_id}`` is retired."""

from __future__ import annotations

from urllib.parse import quote

from constitution_memorizer.playground.locators import (
    PlaygroundLocator,
    UnitLocator,
    parse_locator,
)

PREFIX = "/playground"


def home_path() -> str:
    return PREFIX


def roster_path(*, add: str | None = None) -> str:
    if add:
        return f"{PREFIX}/roster?add={add}"
    return f"{PREFIX}/roster"


def roster_next_path(*, blocked: str | None = None) -> str:
    if blocked:
        return f"{PREFIX}/roster/next?blocked={blocked}"
    return f"{PREFIX}/roster/next"


def add_path(law_id: str) -> str:
    return f"{PREFIX}/laws/{law_id}/add"


def remove_path(law_id: str) -> str:
    return f"{PREFIX}/roster/{law_id}/remove"


def law_path(law_id: str) -> str:
    return f"{PREFIX}/laws/{law_id}"


def sections_path(law_id: str) -> str:
    return f"{PREFIX}/laws/{law_id}/sections"


def learn_path(
    law_id: str,
    number: str,
    mode: str = "cloze",
    *,
    revision: bool | int | None = None,
) -> str:
    path = f"{PREFIX}/laws/{law_id}/sections/{number}/learn/{mode}"
    if revision:
        path += "?revision=1"
    return path


def learn_complete_path(law_id: str, number: str, mode: str = "cloze") -> str:
    return f"{learn_path(law_id, number, mode)}/complete"


def learn_start_path(law_id: str, number: str, mode: str) -> str:
    return f"{learn_path(law_id, number, mode)}/start"


def learn_quiz_path(law_id: str, number: str) -> str:
    return f"{learn_path(law_id, number, 'test')}/quiz"


def _unit_path_key(locator: UnitLocator) -> str:
    return quote(locator.unit_key, safe=":~")


def learn_path_for_locator(
    locator: PlaygroundLocator | str,
    mode: str = "cloze",
    *,
    revision: bool | int | None = None,
) -> str:
    loc = parse_locator(locator) if isinstance(locator, str) else locator
    if isinstance(loc, UnitLocator):
        path = (
            f"{PREFIX}/laws/{loc.law_id}/sections/{loc.section_number}"
            f"/u/{_unit_path_key(loc)}/learn/{mode}"
        )
        if revision:
            path += "?revision=1"
        return path
    return learn_path(loc.law_id, loc.section_number, mode, revision=revision)


def learn_complete_path_for_locator(
    locator: PlaygroundLocator | str, mode: str = "cloze"
) -> str:
    return f"{learn_path_for_locator(locator, mode)}/complete"


def learn_start_path_for_locator(locator: PlaygroundLocator | str, mode: str) -> str:
    return f"{learn_path_for_locator(locator, mode)}/start"


def learn_quiz_path_for_locator(locator: PlaygroundLocator | str) -> str:
    return f"{learn_path_for_locator(locator, 'test')}/quiz"


def source_review_path(law_id: str) -> str:
    return f"{PREFIX}/laws/{law_id}/source-review"


def source_review_section_path(law_id: str, number: str) -> str:
    return f"{source_review_path(law_id)}/sections/{number}"


def source_review_reviewed_path(law_id: str, number: str) -> str:
    return f"{source_review_section_path(law_id, number)}/reviewed"
