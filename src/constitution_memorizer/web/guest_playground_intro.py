"""Guest Playground Gate copy (desktop guest/06-screen, phone shared/05).

Presentation only. Desktop intro and phone Gate share this helper so Shared
05 can reuse the same values. Subscriber home is unchanged. Desktop Sign in
keeps `/login?next=/playground`. Phone CTAs are handlerless.
"""

from __future__ import annotations

from typing import NamedTuple

GUEST_PG_PATH = "/playground"
GUEST_PG_KICKER = "Playground"
GUEST_PG_TITLE = "Sign in to build your law-learning Playground."
GUEST_PG_LEDE = (
    "Turns any Act into a learning experience. "
    "Reading the Bare Acts stays free for everyone."
)
GUEST_PG_HOW = "How Playground works"
GUEST_PG_STEPS: tuple[str, ...] = (
    "Add laws to your month — up to your plan’s spaces.",
    "Learn each section verbatim through six recall modes.",
    "Revise on the ladder: day 1, 3, 7, 15, 30 and 60.",
    "Progress stays saved, in or out of Playground.",
)
GUEST_PG_NOTE = (
    "You'll come straight back to this page. Signing in also unlocks "
    "the full Constitution learning experience, free. Reading the Bare Acts "
    "stays free for everyone."
)
GUEST_PG_SIGNIN_HREF = "/login?next=/playground"


class GuestGateValue(NamedTuple):
    title: str
    body: str


GUEST_GATE_VALUES: tuple[GuestGateValue, ...] = (
    GuestGateValue(
        "Six recall methods",
        "Read, cloze, first letters, type, recite and test — one section at a time.",
    ),
    GuestGateValue(
        "A spaced ladder",
        "Reviews on day 1, 3, 7, 15, 30 and 60. The app tells you what is due.",
    ),
    GuestGateValue(
        "Verbatim, always",
        "You learn the Bare Act text itself from the official Gazette source.",
    ),
)
GUEST_GATE_FOOTNOTE = (
    "Signing in also unlocks the full Constitution learning experience, free. "
    "Reading the Bare Acts stays free for everyone."
)


def is_guest_playground_intro_path(path: str) -> bool:
    return path.rstrip("/") == GUEST_PG_PATH
