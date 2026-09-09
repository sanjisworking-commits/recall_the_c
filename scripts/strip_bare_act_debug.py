#!/usr/bin/env python
"""Derive a Bare Act's runtime JSON from its archival canonical file.

The canonical BNS export carries ``source_x`` on every node — the x-coordinate
the PDF parser read the text at. It is a debugging artifact of the parse, not
provenance, and nothing downstream can use it. Dropping it takes the file from
861 KB to 684 KB.

What this deliberately keeps: ``source_pages`` on every node, and the top-level
``source_file`` block (name, sha256, page count, parser). Those say where the
text came from and are worth shipping.

The transform is exactly one thing — recursively remove one key — so the
runtime artifact is verifiable by a single deep equality rather than by
sampling. tests/test_bns_reader.py asserts:

    runtime == recursively_remove_key(archival, "source_x")

Kept in the repo so the derivation is reproducible and reviewable rather than a
hand-edited blob. Re-run after replacing an archival file:

    python scripts/strip_bare_act_debug.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Parser debug only. Anything that answers "where did this text come from?"
# stays — provenance is not debris.
DEBUG_KEYS = frozenset({"source_x"})

# BNSS needs a *path-aware* strip, not a global key drop, because the same key
# means different things in different places. In operative body text
# ``source_x`` is the x-coordinate the parser read at — debris. In the Second
# Schedule's 58 forms it is load-bearing: every one of their fragments carries
# it, and Form 1 puts "Serial No……." and "Police Station………" at the same
# ``source_y`` with different ``source_x``. That pair *is* a two-column header.
# Drop the coordinates there and the forms flatten into an unordered list of
# phrases, which is exactly the content this batch promises to preserve intact
# for a later form renderer.
BNSS_RULES: dict[str, frozenset[str]] = {
    # chapters[].sections[].body[] (recursively)
    "body": frozenset({"source_x"}),
    # schedules[0].parts[].rows[] — audit duplicates of the cell text
    "schedule_rows": frozenset(
        {
            "source_y",
            "offence_lines",
            "punishment_lines",
            "cognizable_lines",
            "bailability_lines",
            "court_lines",
        }
    ),
}

# Whole arrays dropped from the runtime copy: a line-by-line record of the parse,
# useful for auditing the export, never read at runtime.
BNSS_DROP_ARRAYS = frozenset({"source_line_inventory"})

# archival source -> runtime artifact shipped in the package. The names differ
# on purpose: bare_acts._data_path prefers data/reference/<name> over
# web/<name>, so a shared filename would load the archival copy in a source
# checkout and the runtime one in an installed build.
ARTIFACTS: tuple[tuple[Path, Path, str], ...] = (
    (
        ROOT / "data" / "reference" / "bns_canonical_v1.json",
        ROOT / "src" / "constitution_memorizer" / "web" / "bns_runtime_v1.json",
        "flat",
    ),
    # Archival name carries the parser generation (schema 1.2 / parser v3);
    # the runtime name carries this application's first release of it.
    (
        ROOT / "data" / "reference" / "bnss_canonical_v3.json",
        ROOT / "src" / "constitution_memorizer" / "web" / "bnss_runtime_v1.json",
        "bnss",
    ),
    # POTA needs no path-aware mode: it has no forms, no `*_lines` and no
    # `source_line_inventory`, and its Schedule is a numbered list whose order
    # comes from `serial_number` rather than from geometry. `source_x` is
    # debris everywhere in it, so the flat strip is exactly right.
    (
        ROOT / "data" / "reference" / "pota_canonical_v1.json",
        ROOT / "src" / "constitution_memorizer" / "web" / "pota_runtime_v1.json",
        "flat",
    ),
)


def strip_debug_keys(value: Any) -> Any:
    """Recursively drop DEBUG_KEYS. Nothing else is touched, reordered or coerced."""
    if isinstance(value, dict):
        return {
            key: strip_debug_keys(item)
            for key, item in value.items()
            if key not in DEBUG_KEYS
        }
    if isinstance(value, list):
        return [strip_debug_keys(item) for item in value]
    return value


def strip_bnss(document: Any) -> Any:
    """Path-aware strip. See BNSS_RULES for why one key set will not do."""
    out = {k: v for k, v in document.items() if k not in BNSS_DROP_ARRAYS}
    out["chapters"] = [
        {
            **chapter,
            "sections": [
                {**section, "body": _strip_body(section.get("body") or [])}
                for section in chapter.get("sections") or []
            ],
        }
        for chapter in out.get("chapters") or []
    ]
    out["schedules"] = [_strip_schedule(s) for s in out.get("schedules") or []]
    return out


def _strip_body(nodes: list) -> list:
    """Operative text: the x-coordinate is debris, source_pages is provenance."""
    return [
        {
            **{k: v for k, v in node.items() if k not in BNSS_RULES["body"]},
            "children": _strip_body(node.get("children") or []),
        }
        for node in nodes
    ]


def _strip_schedule(schedule: dict) -> dict:
    out = {k: v for k, v in schedule.items() if k not in BNSS_DROP_ARRAYS}
    if "parts" in out:
        out["parts"] = [
            {
                **part,
                "rows": [
                    {
                        k: v
                        for k, v in row.items()
                        if k not in BNSS_RULES["schedule_rows"]
                    }
                    for row in part.get("rows") or []
                ],
            }
            for part in out["parts"]
        ]
    # `forms` is deliberately untouched: its fragments' coordinates are content.
    return out


def build(source: Path, target: Path, mode: str) -> tuple[int, int]:
    archival = json.loads(source.read_text(encoding="utf-8"))
    stripped = strip_bnss(archival) if mode == "bnss" else strip_debug_keys(archival)
    payload = json.dumps(stripped, ensure_ascii=False, indent=1) + "\n"
    target.write_text(payload, encoding="utf-8")
    return source.stat().st_size, target.stat().st_size


def main() -> None:
    for source, target, mode in ARTIFACTS:
        if not source.exists():
            raise SystemExit(f"archival file missing: {source}")
        before, after = build(source, target, mode)
        print(
            f"{source.name} -> {target.name}: "
            f"{before:,} -> {after:,} bytes ({after / before:.0%})"
        )


if __name__ == "__main__":
    main()
