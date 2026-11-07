"""Guest Profile (CTA map guest/10-screen desktop, guest/06-screen phone).

Desktop Sign in uses `/login?next=/profile`. Phone Sign in and Report are
inert type=button controls. Subscriber Profile is unchanged.
"""

from __future__ import annotations

GUEST_PROFILE_PATH = "/profile"
GUEST_PROFILE_NAME = "Guest"
GUEST_PROFILE_META = "Reading as a guest."  # M5 (Q2, owner 2026-11-07)
GUEST_PROFILE_LEDE = (
    "Sign in to save your progress. Reading stays free for everyone."  # M5 (Q2)
)
GUEST_PROFILE_SIGNIN_HREF = "/auth/google/start?next=%2Fprofile"  # M5 (Q2, 5-11): one Google action
GUEST_PROFILE_BARE_ACTS_HREF = "/laws"  # M5: the Laws catalogue (M3), not one Act
GUEST_PROFILE_BARE_ACTS_LABEL = "Browse the Bare Acts →"
GUEST_PROFILE_REPORT = "Report an issue"


def is_guest_profile_path(path: str) -> bool:
    return path.rstrip("/") == GUEST_PROFILE_PATH
