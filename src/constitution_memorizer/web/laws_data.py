"""Relevant laws seed loader (Browse-shaped; Learn wiring later)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from constitution_memorizer.utils.json_io import read_json

DEFAULT_LAWS_PATH = Path.cwd() / "data" / "reference" / "laws.seed.json"

# Lightweight mapped-law registry for the /laws catalogue. Explicit ids — the
# catalogue loader must not parse laws.seed.json. A regression test asserts
# this set equals the act ids in that file.
MAPPED_LAW_IDS: frozenset[str] = frozenset(
    {
        "rti-2005",
        "rpa-1951",
        "citizenship-1955",
        "pcr-1955",
        "rte-2009",
        "epa-1986",
        "uapa-1967",
    }
)


@dataclass(frozen=True)
class LawClause:
    ref: str
    text: str


@dataclass(frozen=True)
class LawAct:
    id: str
    name: str
    short: str
    year: int
    articles: tuple[str, ...]
    clauses: tuple[LawClause, ...]

    @property
    def article_labels(self) -> str:
        if not self.articles:
            return "—"
        return ", ".join(f"Art {a}" for a in self.articles)


def _parse_act(raw: dict[str, Any]) -> LawAct:
    clauses = tuple(
        LawClause(ref=str(c["ref"]), text=str(c["text"]))
        for c in raw.get("clauses") or []
    )
    arts = tuple(str(a) for a in raw.get("articles") or raw.get("arts") or [])
    return LawAct(
        id=str(raw["id"]),
        name=str(raw["name"]),
        short=str(raw.get("short") or raw["name"]),
        year=int(raw["year"]),
        articles=arts,
        clauses=clauses,
    )


@lru_cache(maxsize=4)
def _load_cached(path_str: str) -> tuple[LawAct, ...]:
    data = read_json(Path(path_str))
    acts = data.get("acts") if isinstance(data, dict) else data
    return tuple(_parse_act(a) for a in acts or [])


def load_laws(path: Path | str | None = None) -> list[LawAct]:
    resolved = Path(path) if path else DEFAULT_LAWS_PATH
    if not resolved.exists():
        return []
    return list(_load_cached(str(resolved.resolve())))


def get_law(law_id: str, path: Path | str | None = None) -> LawAct | None:
    for act in load_laws(path):
        if act.id == law_id:
            return act
    return None
