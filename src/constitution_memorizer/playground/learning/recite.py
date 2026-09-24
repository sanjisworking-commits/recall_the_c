"""Recite mode — speak the clause; accuracy map is client-side.

No audio retention. No persistent transcript. Speech failure must not
make the mode unusable: the same manual/read fallback as Constitution.
"""

from __future__ import annotations

from constitution_memorizer.web.recall_align import align_text


def recite_alignment(canonical_body: str, spoken: str):
    return align_text(canonical_body, spoken)
