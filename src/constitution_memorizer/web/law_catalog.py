"""Static /laws index catalogue — metadata only, never Bare Act or clause JSON."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from constitution_memorizer.utils.json_io import read_json
from constitution_memorizer.web.bare_acts import BARE_ACTS
from constitution_memorizer.web.laws_data import MAPPED_LAW_IDS

DEFAULT_CATALOG_PATH = Path.cwd() / "data" / "reference" / "law_catalog.seed.json"

PRIMARY_CONTENT_KINDS = frozenset({"full_act", "key_provisions"})
KIND_LABELS = {"full_act": "FULL ACT", "key_provisions": "KEY PROVISIONS"}


class CatalogError(ValueError):
    """The catalogue seed is invalid or a capability ref is unregistered."""


@dataclass(frozen=True)
class LawSubject:
    id: str
    label: str
    display_order: int


@dataclass(frozen=True)
class CatalogLaw:
    id: str
    title: str
    short_title: str
    year: int
    aliases: tuple[str, ...]
    subjects: tuple[str, ...]
    primary_subject: str
    display_order: int
    scope_label: str
    primary_content: str
    full_act_ref: str | None
    key_provisions_ref: str | None
    tag_line: str
    href: str
    search_blob: str


@dataclass(frozen=True)
class LawCatalog:
    subjects: tuple[LawSubject, ...]
    laws: tuple[CatalogLaw, ...]

    @property
    def visible_subjects(self) -> tuple[LawSubject, ...]:
        used = {sid for law in self.laws for sid in law.subjects}
        return tuple(s for s in self.subjects if s.id in used)


def normalize_search(*parts: object) -> str:
    chunks: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, (list, tuple)):
            chunks.extend(str(item) for item in part if item is not None and str(item))
            continue
        text = str(part).strip()
        if text:
            chunks.append(text)
    return " ".join(" ".join(chunks).lower().split())


def _capability_ref(raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise CatalogError("content capability must be an object or null")
    ref = raw.get("ref")
    if ref is None or str(ref).strip() == "":
        raise CatalogError("content capability is missing ref")
    return str(ref)


def _parse_subjects(raw: Any) -> tuple[LawSubject, ...]:
    if not isinstance(raw, list) or not raw:
        raise CatalogError("catalogue subjects[] is required")
    seen: set[str] = set()
    subjects: list[LawSubject] = []
    for item in raw:
        if not isinstance(item, dict):
            raise CatalogError("subject entries must be objects")
        sid = str(item.get("id") or "").strip()
        label = str(item.get("label") or "").strip()
        if not sid or not label:
            raise CatalogError("subject is missing id or label")
        if sid in seen:
            raise CatalogError(f"duplicate subject id: {sid}")
        seen.add(sid)
        try:
            order = int(item["display_order"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalogError(f"subject {sid} is missing a valid display_order") from exc
        subjects.append(LawSubject(id=sid, label=label, display_order=order))
    subjects.sort(key=lambda s: (s.display_order, s.id))
    return tuple(subjects)


def _parse_law(
    raw: dict[str, Any],
    subject_by_id: dict[str, LawSubject],
    bare_act_ids: frozenset[str],
    mapped_law_ids: frozenset[str],
) -> CatalogLaw:
    law_id = str(raw.get("id") or "").strip()
    if not law_id:
        raise CatalogError("law is missing id")
    title = str(raw.get("title") or "").strip()
    short_title = str(raw.get("short_title") or "").strip()
    scope_label = str(raw.get("scope_label") or "").strip()
    if not title or not short_title or not scope_label:
        raise CatalogError(f"{law_id}: title, short_title and scope_label are required")
    try:
        year = int(raw["year"])
        display_order = int(raw["display_order"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CatalogError(f"{law_id}: year and display_order must be integers") from exc

    subject_ids = tuple(str(s).strip() for s in (raw.get("subjects") or []) if str(s).strip())
    if not subject_ids:
        raise CatalogError(f"{law_id}: subjects[] is required")
    for sid in subject_ids:
        if sid not in subject_by_id:
            raise CatalogError(f"{law_id}: unknown subject {sid}")
    primary_subject = str(raw.get("primary_subject") or "").strip()
    if primary_subject not in subject_ids:
        raise CatalogError(f"{law_id}: primary_subject must be one of subjects[]")

    primary_content = str(raw.get("primary_content") or "").strip()
    if primary_content not in PRIMARY_CONTENT_KINDS:
        raise CatalogError(f"{law_id}: primary_content must be full_act or key_provisions")

    content = raw.get("content")
    if not isinstance(content, dict):
        raise CatalogError(f"{law_id}: content object is required")
    full_act_ref = _capability_ref(content.get("full_act"))
    key_provisions_ref = _capability_ref(content.get("key_provisions"))
    if full_act_ref is None and key_provisions_ref is None:
        raise CatalogError(f"{law_id}: at least one content capability is required")
    if primary_content == "full_act" and not full_act_ref:
        raise CatalogError(f"{law_id}: primary_content full_act has no capability")
    if primary_content == "key_provisions" and not key_provisions_ref:
        raise CatalogError(f"{law_id}: primary_content key_provisions has no capability")
    if full_act_ref is not None and full_act_ref not in bare_act_ids:
        raise CatalogError(f"{law_id}: full_act ref {full_act_ref} is not in BARE_ACTS")
    if key_provisions_ref is not None and key_provisions_ref not in mapped_law_ids:
        raise CatalogError(
            f"{law_id}: key_provisions ref {key_provisions_ref} is not in MAPPED_LAW_IDS"
        )

    href_ref = full_act_ref if primary_content == "full_act" else key_provisions_ref
    aliases = tuple(str(a).strip() for a in (raw.get("aliases") or []) if str(a).strip())
    primary_label = subject_by_id[primary_subject].label
    kind_label = KIND_LABELS[primary_content]
    tag_line = f"{primary_label.upper()} · {kind_label}"
    subject_labels = tuple(subject_by_id[sid].label for sid in subject_ids)
    search_blob = normalize_search(
        title, short_title, aliases, year, subject_ids, subject_labels
    )
    return CatalogLaw(
        id=law_id,
        title=title,
        short_title=short_title,
        year=year,
        aliases=aliases,
        subjects=subject_ids,
        primary_subject=primary_subject,
        display_order=display_order,
        scope_label=scope_label,
        primary_content=primary_content,
        full_act_ref=full_act_ref,
        key_provisions_ref=key_provisions_ref,
        tag_line=tag_line,
        href=f"/laws/{href_ref}",
        search_blob=search_blob,
    )


def parse_catalog(
    data: dict[str, Any],
    *,
    bare_act_ids: Iterable[str],
    mapped_law_ids: Iterable[str],
) -> LawCatalog:
    subjects = _parse_subjects(data.get("subjects"))
    subject_by_id = {s.id: s for s in subjects}
    bare = frozenset(bare_act_ids)
    mapped = frozenset(mapped_law_ids)
    raw_laws = data.get("laws")
    if not isinstance(raw_laws, list):
        raise CatalogError("catalogue laws[] is required")
    seen: set[str] = set()
    laws: list[CatalogLaw] = []
    for item in raw_laws:
        if not isinstance(item, dict):
            raise CatalogError("law entries must be objects")
        law = _parse_law(item, subject_by_id, bare, mapped)
        if law.id in seen:
            raise CatalogError(f"duplicate law id: {law.id}")
        seen.add(law.id)
        laws.append(law)
    laws.sort(key=lambda law: (law.display_order, law.id))
    return LawCatalog(subjects=subjects, laws=tuple(laws))


@lru_cache(maxsize=8)
def _load_cached(
    path_str: str, bare_key: tuple[str, ...], mapped_key: tuple[str, ...]
) -> LawCatalog:
    data = read_json(Path(path_str))
    if not isinstance(data, dict):
        raise CatalogError("catalogue root must be an object")
    return parse_catalog(
        data, bare_act_ids=bare_key, mapped_law_ids=mapped_key
    )


def load_catalog(
    path: Path | str | None = None,
    *,
    bare_act_ids: Iterable[str] | None = None,
    mapped_law_ids: Iterable[str] | None = None,
) -> LawCatalog:
    resolved = Path(path) if path else DEFAULT_CATALOG_PATH
    if not resolved.exists():
        raise CatalogError(f"catalogue not found: {resolved}")
    bare = tuple(sorted(bare_act_ids if bare_act_ids is not None else BARE_ACTS))
    mapped = tuple(
        sorted(mapped_law_ids if mapped_law_ids is not None else MAPPED_LAW_IDS)
    )
    return _load_cached(str(resolved.resolve()), bare, mapped)
