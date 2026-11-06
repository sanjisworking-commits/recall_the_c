"""Rebuild the Browse Schedules fixture from the official JS extract."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "design" / "schedules" / "schedules-text.js"
OUT = ROOT / "src" / "constitution_memorizer" / "web" / "schedules.json"
EXPORT = re.compile(r"export const SCHEDULES = (\{.*\})\s*;?\s*$", re.S)


def load_schedules(path: Path) -> dict:
    match = EXPORT.match(path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"No SCHEDULES export in {path}")
    data = json.loads(match.group(1).replace("\\uf02a", "*").replace("\uf02a", "*"))
    if not isinstance(data, dict):
        raise ValueError("SCHEDULES is not an object")
    for body in data.values():
        for block in body.get("blocks") or []:
            if block.get("t") == "list" or block.get("isList"):
                block["open"] = block.get("id") == "I"
    return data


def main() -> int:
    data = load_schedules(SRC)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes, {len(data)} schedules)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
