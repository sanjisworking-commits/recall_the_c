"""The "About this act" panel — a join, not a new source of truth.

Every row comes from somewhere that already owns it. Act number, enactment
date and long title are statutory and are read off the Act's own canonical
JSON. Commencement, ministry, department, jurisdiction and the source's
last-modified date are editorial: they are nowhere in the statute and live in
the catalogue seed beside `status` and `status_note`. The section count is
derived from the Act's own section order and is stored nowhere at all.

Nothing here writes back. An Act with no editorial block still gets a panel —
it just shows fewer rows, which is the honest rendering of what we hold.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from constitution_memorizer.web.bare_acts import BareAct
from constitution_memorizer.web.law_catalog import CatalogLaw

# "16th September, 1985" — how every canonical prints its enactment date.
_SPELLED_DATE = re.compile(
    r"^(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})$"
)
# "1-7-2024" — India Code prints the day and month unpadded about half the time.
_NUMERIC_DATE = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def format_act_date(raw: str) -> str:
    """"16th September, 1985" or "1-7-2024" -> "16-09-1985" / "01-07-2024".

    Presentation only: one format for every date in the card, so a statutory
    date and an editorial one do not sit in the same grid looking like they
    came from different centuries. A date in neither shape is passed through
    verbatim — losing a real fact is worse than an inconsistent one.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    spelled = _SPELLED_DATE.match(text)
    if spelled:
        day, month_name, year = spelled.groups()
        month = _MONTHS.get(month_name.lower())
        if month:
            return f"{int(day):02d}-{month:02d}-{year}"
        return text
    numeric = _NUMERIC_DATE.match(text)
    if numeric:
        day, month, year = numeric.groups()
        return f"{int(day):02d}-{int(month):02d}-{year}"
    return text


@dataclass(frozen=True)
class ActInfoRow:
    key: str
    value: str


@dataclass(frozen=True)
class ActInfoPanel:
    """What the card draws. `rows` is already filtered to what we hold."""

    meta: str
    rows: tuple[ActInfoRow, ...]
    long_title: str

    @property
    def has_content(self) -> bool:
        return bool(self.meta or self.rows or self.long_title)


def build_act_info(act: BareAct, catalog_law: CatalogLaw | None) -> ActInfoPanel:
    """Statutory fields from the Act, editorial fields from the catalogue.

    Row order is the design's. A row whose value we do not have is dropped
    rather than rendered empty, so POTA — which prints no enactment date in
    its source at all — simply has no Enacted line.
    """
    editorial = catalog_law.act_info if catalog_law else None
    pairs = (
        ("Enacted", format_act_date(act.enactment_date)),
        ("In force", format_act_date(editorial.in_force if editorial else "")),
        ("Ministry", editorial.ministry if editorial else ""),
        ("Department", editorial.department if editorial else ""),
        ("Jurisdiction", editorial.jurisdiction if editorial else ""),
        # The Act's own span, not a count. NDPS holds 129 section records
        # because 7A, 27A and the whole 68A-68Z block are insertions, so a
        # count would print "129" under a heading every register gives as 83.
        # The range says what is true without asserting either number.
        ("Sections", act.section_range),
        ("Last modified", format_act_date(editorial.last_modified if editorial else "")),
    )
    return ActInfoPanel(
        meta=f"Act No. {act.act_number}" if act.act_number else "",
        rows=tuple(ActInfoRow(key=k, value=v) for k, v in pairs if v),
        long_title=act.long_title,
    )
