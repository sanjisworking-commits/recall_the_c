"""T2 hash-drift snapshot and T3 footnote-title guard.

If SHA-256 over section number, title, and canonical body text changes
without an intentional statutory change, stop. Drift marks every learner's
Act as "Law updated".
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from constitution_memorizer.playground.eligibility import list_playground_eligible_laws
from constitution_memorizer.playground.source import (
    canonical_body_text,
    hash_payload,
    source_hash,
)
from constitution_memorizer.web.bare_acts import get_bare_act

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "tests" / "fixtures" / "playground" / "section_source_hashes.json"
LEARNER_ACTS = ("ndps", "bns", "bnss")
SENTINELS = (("ndps", "8"), ("bns", "103"), ("bnss", "479"))
SRC = ROOT / "src" / "constitution_memorizer"


def _snapshot() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _live_hashes(law_id: str) -> dict[str, str]:
    act = get_bare_act(law_id)
    assert act is not None
    return {section.number: source_hash(section) for section in act.section_order}


def test_sentinel_section_hashes_match_post_merge_snapshot():
    data = _snapshot()
    for law_id, number in SENTINELS:
        live = source_hash(get_bare_act(law_id).section(number))
        expected = data["sentinels"][f"{law_id}:section:{number}"]
        assert live == expected, (
            f"{law_id} section {number} hash drifted. Stop. Do not proceed to R1. "
            f"expected {expected} live {live}"
        )


def test_learner_act_section_hashes_match_snapshot():
    """Every NDPS/BNS/BNSS section hash is pinned. 1018 sections at merge."""
    data = _snapshot()
    mismatches: list[str] = []
    for law_id in LEARNER_ACTS:
        live = _live_hashes(law_id)
        expected = data["hashes"][law_id]
        extra = sorted(set(live) - set(expected))
        missing = sorted(set(expected) - set(live))
        if extra or missing:
            mismatches.append(
                f"{law_id}: extra={extra[:8]} missing={missing[:8]}"
            )
            continue
        drifted = [
            number
            for number, digest in live.items()
            if digest != expected[number]
        ]
        if drifted:
            mismatches.append(f"{law_id}: drifted {drifted[:8]}")
    assert not mismatches, (
        "Canonical section hashes changed without an intentional statutory "
        "change. Stop. Do not proceed to R1. " + "; ".join(mismatches)
    )
    assert sum(data["counts"][law_id] for law_id in LEARNER_ACTS) == 1018


def test_new_act_section_hashes_match_snapshot():
    """UAPA, PSS and MTP are pinned so later reader work cannot silently drift."""
    data = _snapshot()
    for law_id in list_playground_eligible_laws():
        if law_id in LEARNER_ACTS:
            continue
        live = _live_hashes(law_id)
        expected = data["hashes"][law_id]
        assert live == expected, f"{law_id} section hashes drifted"


def test_hash_payload_is_number_title_and_body_only():
    section = get_bare_act("ndps").section("8")
    body = canonical_body_text(section)
    assert hash_payload(section) == f"{section.number}\n{section.title}\n{body}"
    assert "title_annotations" not in hash_payload(section)
    assert "footnote" not in hash_payload(section)


def test_title_annotations_do_not_change_source_hash():
    """T3: footnote title anchors are display-only."""
    mtp = get_bare_act("mtp").section("4")
    ndps = get_bare_act("ndps").section("8A")
    assert mtp.title_annotations
    assert ndps.title_annotations
    junk = (
        {
            "type": "footnote",
            "marker": "99",
            "note_id": "synthetic",
            "start": 0,
            "end": len(mtp.title),
            "anchor_text": mtp.title,
        },
    )
    for section in (mtp, ndps):
        mutated = replace(section, title_annotations=section.title_annotations + junk)
        assert mutated.title_annotations != section.title_annotations
        assert mutated.title == section.title
        assert hash_payload(mutated) == hash_payload(section)
        assert source_hash(mutated) == source_hash(section)


def test_picker_and_cards_show_plain_titles_not_footnote_markers(tmp_path: Path):
    from tests.test_playground import _add_and_select, _client
    from constitution_memorizer.playground.urls import law_path, sections_path

    mtp4 = get_bare_act("mtp").section("4")
    ndps8a = get_bare_act("ndps").section("8A")
    assert mtp4.list_title == mtp4.title
    assert ndps8a.list_title == ndps8a.title
    assert not mtp4.list_title[0].isdigit()
    assert "2[" not in mtp4.list_title
    assert "2[" not in ndps8a.list_title

    client = _client(tmp_path)
    _add_and_select(client, "mtp", "4")
    picker = client.get(sections_path("mtp"))
    assert picker.status_code == 200
    assert mtp4.list_title in picker.text
    assert "2[Place" not in picker.text
    workspace = client.get(law_path("mtp"))
    assert workspace.status_code == 200
    assert mtp4.list_title in workspace.text
    assert "2[Place" not in workspace.text


def test_dead_csrf_less_cloze_path_removed():
    """T7: orphaned cloze template and CSRF-less POST binder are gone."""
    template = SRC / "web" / "templates" / "playground_cloze.html"
    js = (SRC / "web" / "static" / "playground.js").read_text(encoding="utf-8")
    assert not template.exists()
    assert "data-playground-cloze" not in js
    assert "initPlaygroundCloze" not in js
    templates = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (SRC / "web" / "templates").rglob("*.html")
    )
    assert "playground_cloze.html" not in templates
    assert "data-playground-cloze" not in templates
    routes = (SRC / "playground" / "routes.py").read_text(encoding="utf-8")
    assert "complete_cloze" not in routes
    repo = (SRC / "playground" / "repository.py").read_text(encoding="utf-8")
    assert "def complete_cloze" in repo
