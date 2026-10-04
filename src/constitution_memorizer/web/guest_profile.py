"""Guest desktop Profile (CTA map guest/10-screen). Presentation only.

Phone guest `/profile` keeps the production guest card. Subscriber Profile
is unchanged. Sign in uses the existing `/login?next=/profile` Gate path.
"""

from __future__ import annotations

GUEST_PROFILE_PATH = "/profile"
GUEST_PROFILE_NAME = "Guest"
GUEST_PROFILE_META = "Read mode."
GUEST_PROFILE_LEDE = (
    "Sign in to save progress and unlock the Constitution learning experience."
)
GUEST_PROFILE_SIGNIN_HREF = "/login?next=/profile"
GUEST_PROFILE_BARE_ACTS_HREF = "/laws/ndps"
GUEST_PROFILE_BARE_ACTS_LABEL = "Browse the Bare Acts →"
GUEST_PROFILE_REPORT = "Report an issue"


def is_guest_profile_path(path: str) -> bool:
    return path.rstrip("/") == GUEST_PROFILE_PATH
