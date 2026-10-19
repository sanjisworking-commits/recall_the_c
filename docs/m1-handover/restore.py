#!/usr/bin/env python3
"""Rebuild the review ZIPs from the plain-text parts in b64/.

GitHub's Download button and Cursor's binary attachment save plus.zip,
pro.zip, and max.zip as 0 KB. The parts under b64/ are ASCII text. This
script joins them and checks the SHA-256 of the original archives.

Usage:
    python3 docs/m1-handover/restore.py
    python3 docs/m1-handover/restore.py /path/to/output-dir
"""

from __future__ import annotations

import base64
import hashlib
import pathlib
import sys

NAMES = ("plus.zip", "pro.zip", "max.zip", "free-pre-grant.zip")


def main() -> int:
    here = pathlib.Path(__file__).resolve().parent
    parts_dir = here / "b64"
    dest = pathlib.Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else pathlib.Path.cwd() / "restored-zips"
    dest.mkdir(parents=True, exist_ok=True)
    expected = _load_sums(parts_dir / "SHA256SUMS")
    for name in NAMES:
        parts = sorted(parts_dir.glob(f"{name}.b64.*"))
        if not parts:
            print(f"missing parts for {name}", file=sys.stderr)
            return 1
        payload = "".join("".join(part.read_text(encoding="ascii").split()) for part in parts)
        data = base64.b64decode(payload, validate=True)
        digest = hashlib.sha256(data).hexdigest()
        want = expected[name]
        if digest != want:
            print(f"{name} sha256 {digest} does not match {want}", file=sys.stderr)
            return 1
        out = dest / name
        out.write_bytes(data)
        print(f"{name} {len(data)} bytes {digest} -> {out}")
    return 0


def _load_sums(path: pathlib.Path) -> dict[str, str]:
    sums: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        if not line.strip():
            continue
        digest, name, _size = line.split()
        sums[name] = digest
    return sums


if __name__ == "__main__":
    raise SystemExit(main())
