"""Type mode — RecallC write-it-out, word for word.

Alignment is the shared pure ``recall_align`` helper. Typed attempts are
not stored.
"""

from __future__ import annotations

from constitution_memorizer.web.recall_align import align_text


def type_alignment(canonical_body: str, typed: str):
    return align_text(canonical_body, typed)
