"""Guest desktop NDPS Bare Act head (CTA map guest/04-screen). Presentation only.

Phone Bare Act readers and subscriber heads keep `bare_act.html` production
markup. Chapter rows on this surface are display-only.
"""

from __future__ import annotations

from dataclasses import dataclass

from constitution_memorizer.web.bare_acts import EN_DASH

NDPS_SLUG = "ndps"
NDPS_GUEST_PATH = f"/laws/{NDPS_SLUG}"
NDPS_GUEST_TITLE = "The Narcotic Drugs and Psychotropic Substances Act, 1985"
NDPS_GUEST_KICKER = "BARE ACT · INDIA CODE"
NDPS_GUEST_META = f"6 Chapters · Sections 1{EN_DASH}83 · Schedule"
NDPS_GUEST_READING_NAME = "The NDPS Act, 1985"
GUEST_ADD_TITLE = "Add to Playground"


@dataclass(frozen=True)
class GuestBareactRow:
    tag: str
    title: str
    range_label: str


@dataclass(frozen=True)
class GuestBareactHead:
    slug: str
    path: str
    title: str
    kicker: str
    meta: str
    add_href: str
    rows: tuple[GuestBareactRow, ...]


NDPS_GUEST_ROWS: tuple[GuestBareactRow, ...] = (
    GuestBareactRow("CHAPTER I", "Preliminary", f"Sections 1{EN_DASH}3"),
    GuestBareactRow(
        "CHAPTER II",
        "Authorities and Officers",
        f"Sections 4{EN_DASH}7A",
    ),
    GuestBareactRow(
        "CHAPTER III",
        "Prohibition, Control and Regulation",
        f"Sections 8{EN_DASH}14",
    ),
    GuestBareactRow(
        "SCHEDULE",
        "List of Psychotropic Substances",
        f"Entries 1{EN_DASH}110",
    ),
)


def ndps_guest_head() -> GuestBareactHead:
    return GuestBareactHead(
        slug=NDPS_SLUG,
        path=NDPS_GUEST_PATH,
        title=NDPS_GUEST_TITLE,
        kicker=NDPS_GUEST_KICKER,
        meta=NDPS_GUEST_META,
        add_href=f"/playground/laws/{NDPS_SLUG}/add",
        rows=NDPS_GUEST_ROWS,
    )


def is_guest_ndps_head_path(path: str) -> bool:
    return path.rstrip("/") == NDPS_GUEST_PATH


def guest_add_reading_name(law_id: str, short_title: str = "") -> str:
    """Act name used in the guest desktop Add dialog lede."""

    if law_id == NDPS_SLUG:
        return NDPS_GUEST_READING_NAME
    return short_title or law_id
