"""Recite mode — speak the clause; accuracy map is server-owned.

``recite_alignment`` is the only Recite scorer. The Learn client renders
the returned map; it must not call ``RecallAlign`` itself. No audio
retention. No persistent transcript. Speech failure must not make the
mode unusable: typed fallback uses the same Playground speech route.
"""

from __future__ import annotations

from constitution_memorizer.web.recall_align import align_text


def recite_alignment(canonical_body: str, spoken: str):
    return align_text(canonical_body, spoken)
