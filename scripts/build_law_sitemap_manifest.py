#!/usr/bin/env python3
"""Build the sitemap URL inventory (``web/law_sitemap_manifest.json``).

Derived runtime metadata, not the canonical statute: the flattened list of
publicly routable section/schedule identifiers per registered Bare Act, plus a
per-source SHA-256 freshness digest. It lives inside the package
(``src/constitution_memorizer/web/``) so it ships in the built wheel and the web
process can emit sitemaps WITHOUT ever hydrating an Act — the deployed sitemap
routes read exactly this file via ``sitemaps._manifest_path()``.

This is the ONE place a full Act is loaded for sitemap purposes. It runs during
ingestion/build/development and is never imported by FastAPI. Regenerate it
whenever a registered runtime file (or patch) changes; the manifest-freshness
test fails loudly if you forget.

    python -m scripts.build_law_sitemap_manifest        # write in place
    python -m scripts.build_law_sitemap_manifest --check # verify only, no write
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from constitution_memorizer.web.bare_acts import (
    BARE_ACTS,
    _data_path,
    get_bare_act,
    runtime_cache_identity,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = (
    ROOT / "src" / "constitution_memorizer" / "web" / "law_sitemap_manifest.json"
)

SCHEMA_VERSION = 1


def _source_digests(slug: str) -> list[dict[str, str]]:
    """Ordered {filename, sha256} for every registered input of ``slug``.

    Ordered filename-then-patches so a composite Act (NDPS = act + schedule
    patch) hashes deterministically and a stale patch is individually
    diagnosable in CI. Bytes are located via the loader's own resolver, so the
    digest is over exactly the file the runtime would read.
    """
    spec = BARE_ACTS[slug]
    digests: list[dict[str, str]] = []
    for filename in (spec.filename, *spec.patch_filenames):
        raw = _data_path(filename).read_bytes()
        digests.append(
            {"filename": filename, "sha256": hashlib.sha256(raw).hexdigest()}
        )
    return digests


def build_manifest() -> dict:
    """Assemble the deterministic manifest dict (laws sorted by slug)."""
    laws: dict[str, dict] = {}
    for slug in sorted(BARE_ACTS):
        spec = BARE_ACTS[slug]
        act = get_bare_act(slug)
        if act is None:  # pragma: no cover - registry/loader disagree
            raise SystemExit(f"registered Act {slug!r} failed to load")
        laws[slug] = {
            "runtime_identity": runtime_cache_identity(spec),
            "sources": _source_digests(slug),
            "sections": [section.number for section in act.section_order],
            "schedules": list(act.public_schedule_slugs),
        }
    return {"schema_version": SCHEMA_VERSION, "laws": laws}


def _serialize(manifest: dict) -> str:
    """Deterministic pretty JSON with a trailing newline."""
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the on-disk manifest differs from a fresh build.",
    )
    args = parser.parse_args(argv)

    text = _serialize(build_manifest())

    if args.check:
        current = args.out.read_text(encoding="utf-8") if args.out.exists() else ""
        if current != text:
            print(
                f"{args.out} is stale — rerun `python -m scripts.build_law_sitemap_manifest`",
                file=sys.stderr,
            )
            return 1
        print(f"{args.out} is up to date")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
