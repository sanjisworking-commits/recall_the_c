"""Read-only Constitution Schedules for Browse (design handover, Nov 2026)."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from constitution_memorizer.utils.json_io import read_json
from constitution_memorizer.web.browse import load_browse_schedules_seed

_PACKAGE_BODIES = Path(__file__).resolve().parent / "schedules.json"
_REPO_BODIES = Path(__file__).resolve().parents[3] / "data" / "reference" / "schedules.json"
_CWD_BODIES = Path.cwd() / "data" / "reference" / "schedules.json"


@dataclass(frozen=True)
class BrowseScheduleCard:
    slug: str
    ord: str
    roman: str
    title: str
    refs: str
    href: str


@dataclass(frozen=True)
class BrowseScheduleView:
    slug: str
    ord: str
    roman: str
    title: str
    refs: str
    meta: str
    cite: str
    blocks: list[dict[str, Any]]
    notes: list[str]
    prev_slug: str | None
    next_slug: str | None
    prev_ord: str | None
    next_ord: str | None


def schedule_href(slug: str) -> str:
    return f"/browse/schedules/{slug.strip().lower()}"


def browse_schedule_cards(_engine: Any = None) -> list[BrowseScheduleCard]:
    cards: list[BrowseScheduleCard] = []
    for row in load_browse_schedules_seed():
        slug = str(row["slug"]).strip().lower()
        cards.append(
            BrowseScheduleCard(
                slug=slug,
                ord=str(row.get("ord") or "").strip(),
                roman=str(row.get("roman") or "").strip(),
                title=str(row.get("title") or "").strip(),
                refs=str(row.get("refs") or "").strip(),
                href=schedule_href(slug),
            )
        )
    return cards


def find_schedule_card(
    cards: list[BrowseScheduleCard], slug: str
) -> BrowseScheduleCard | None:
    wanted = slug.strip().lower()
    for card in cards:
        if card.slug == wanted:
            return card
    return None


@lru_cache(maxsize=1)
def load_schedule_bodies() -> dict[str, Any]:
    for path in (_PACKAGE_BODIES, _REPO_BODIES, _CWD_BODIES):
        if path.exists():
            data = read_json(path)
            if isinstance(data, dict):
                return data
    return {}


def build_schedule_view(_engine: Any, slug: str) -> BrowseScheduleView | None:
    cards = browse_schedule_cards()
    card = find_schedule_card(cards, slug)
    if card is None:
        return None
    index = cards.index(card)
    prev_card = cards[index - 1] if index > 0 else None
    next_card = cards[index + 1] if index + 1 < len(cards) else None
    seed = next(
        (row for row in load_browse_schedules_seed() if row.get("slug") == card.slug),
        {},
    )
    body = load_schedule_bodies().get(card.slug) or {}
    blocks = list(body.get("blocks") or [])
    notes = [str(n) for n in (body.get("notes") or [])]
    return BrowseScheduleView(
        slug=card.slug,
        ord=card.ord,
        roman=card.roman,
        title=card.title,
        refs=card.refs,
        meta=str(seed.get("meta") or f"{card.refs} · Read-only reference"),
        cite=str(seed.get("cite") or ""),
        blocks=blocks,
        notes=notes,
        prev_slug=prev_card.slug if prev_card else None,
        next_slug=next_card.slug if next_card else None,
        prev_ord=prev_card.ord if prev_card else None,
        next_ord=next_card.ord if next_card else None,
    )
