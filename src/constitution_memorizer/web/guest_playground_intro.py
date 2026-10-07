"""Guest desktop Playground intro (CTA map guest/06-screen). Presentation only.

Phone guest `/playground` keeps the production entitlement Gate. Subscriber
home is unchanged. Sign in uses the existing `/login?next=/playground` Gate path.
"""

from __future__ import annotations

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


def is_guest_playground_intro_path(path: str) -> bool:
    return path.rstrip("/") == GUEST_PG_PATH
