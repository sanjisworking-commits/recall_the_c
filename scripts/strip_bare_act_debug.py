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

# archival source -> runtime artifact shipped in the package. The names differ
# on purpose: bare_acts._data_path prefers data/reference/<name> over
# web/<name>, so a shared filename would load the archival copy in a source
# checkout and the runtime one in an installed build.
ARTIFACTS: tuple[tuple[Path, Path], ...] = (
    (
        ROOT / "data" / "reference" / "bns_canonical_v1.json",
        ROOT / "src" / "constitution_memorizer" / "web" / "bns_runtime_v1.json",
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


def build(source: Path, target: Path) -> tuple[int, int]:
    archival = json.loads(source.read_text(encoding="utf-8"))
    payload = json.dumps(
        strip_debug_keys(archival), ensure_ascii=False, indent=1
    ) + "\n"
    target.write_text(payload, encoding="utf-8")
    return source.stat().st_size, target.stat().st_size


def main() -> None:
    for source, target in ARTIFACTS:
        if not source.exists():
            raise SystemExit(f"archival file missing: {source}")
        before, after = build(source, target)
        print(
            f"{source.name} -> {target.name}: "
            f"{before:,} -> {after:,} bytes ({after / before:.0%})"
        )


if __name__ == "__main__":
    main()
