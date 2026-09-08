"""Stage 1 law-loading contract: metadata startup, per-law lazy cache.

Importing the registry, starting the app, and rendering /laws must not
hydrate BNS or NDPS. See docs/law-loading.md.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constitution_memorizer.web import bare_acts
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import (
    BARE_ACTS,
    clear_bare_act_cache,
    get_bare_act,
    runtime_cache_identity,
)

REPO = Path(__file__).resolve().parents[1]
MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"

RUNTIME_NAMES = frozenset(
    {
        "bns_runtime_v1.json",
        "ndps_act_final.json",
        "ndps_schedule_patch.json",
        "bns_canonical_v1.json",
    }
)
BNS_NAMES = frozenset({"bns_runtime_v1.json", "bns_canonical_v1.json"})
NDPS_NAMES = frozenset({"ndps_act_final.json", "ndps_schedule_patch.json"})


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    )


def _guard_reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    opened: list[str] = []
    real = bare_acts.read_json

    def wrapped(path: Path):
        opened.append(Path(path).name)
        return real(path)

    monkeypatch.setattr(bare_acts, "read_json", wrapped)
    return opened


def test_runtime_cache_identity_uses_registry_not_file_bytes():
    spec = BARE_ACTS["bns"]
    assert spec.source_hash is None
    assert runtime_cache_identity(spec) == "bns:1:bns_runtime_v1.json"
    assert runtime_cache_identity(BARE_ACTS["ndps"]) == "ndps:1:ndps_act_final.json"


def test_importing_law_modules_does_not_open_runtime_files():
    """A post-import monkeypatch cannot prove import itself was clean."""
    script = r"""
import sys
from pathlib import Path

forbidden = {
    "bns_runtime_v1.json",
    "ndps_act_final.json",
    "ndps_schedule_patch.json",
    "bns_canonical_v1.json",
}

def hook(event, args):
    if event != "open":
        return
    raw = args[0]
    if isinstance(raw, int):
        return
    name = Path(str(raw)).name
    if name in forbidden:
        raise AssertionError(f"import opened law file: {raw}")

sys.addaudithook(hook)
import constitution_memorizer.web.bare_acts  # noqa: F401
import constitution_memorizer.web.law_catalog  # noqa: F401
import constitution_memorizer.web.app  # noqa: F401
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO / "src"), str(REPO), env.get("PYTHONPATH", "")]
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_create_app_does_not_hydrate_bare_acts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    clear_bare_act_cache()
    opened = _guard_reads(monkeypatch)
    create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    assert not RUNTIME_NAMES.intersection(opened)


def test_get_laws_does_not_hydrate_bare_acts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    clear_bare_act_cache()
    opened = _guard_reads(monkeypatch)
    response = _client(tmp_path).get("/laws")
    assert response.status_code == 200
    assert not RUNTIME_NAMES.intersection(opened)


def test_requesting_bns_does_not_load_ndps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    clear_bare_act_cache()
    opened = _guard_reads(monkeypatch)
    response = _client(tmp_path).get("/laws/bns")
    assert response.status_code == 200
    assert NDPS_NAMES.isdisjoint(opened)
    assert "bns_runtime_v1.json" in opened
    assert "bns_canonical_v1.json" not in opened


def test_requesting_ndps_does_not_load_bns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    clear_bare_act_cache()
    opened = _guard_reads(monkeypatch)
    response = _client(tmp_path).get("/laws/ndps")
    assert response.status_code == 200
    assert BNS_NAMES.isdisjoint(opened)
    assert "ndps_act_final.json" in opened


def test_cold_bns_parses_once_then_reuses_cache(monkeypatch: pytest.MonkeyPatch):
    clear_bare_act_cache()
    opened = _guard_reads(monkeypatch)
    first = get_bare_act("bns")
    after_first = list(opened)
    second = get_bare_act("bns")
    assert first is second
    assert after_first.count("bns_runtime_v1.json") == 1
    assert opened == after_first


def test_cold_ndps_parses_once_then_reuses_cache(monkeypatch: pytest.MonkeyPatch):
    clear_bare_act_cache()
    opened = _guard_reads(monkeypatch)
    first = get_bare_act("ndps")
    after_first = list(opened)
    second = get_bare_act("ndps")
    assert first is second
    assert after_first.count("ndps_act_final.json") == 1
    assert after_first.count("ndps_schedule_patch.json") == 1
    assert opened == after_first


def test_distinct_runtime_identities_do_not_share_cache(
    monkeypatch: pytest.MonkeyPatch,
):
    clear_bare_act_cache()
    reads: list[str] = []

    def fake_read(path: Path):
        reads.append(Path(path).name)
        return {"document": {}, "chapters": [], "schedules": [], "footnotes": []}

    monkeypatch.setattr(bare_acts, "read_json", fake_read)
    first = bare_acts._load_cached("bns", "bns:1:aaa")
    second = bare_acts._load_cached("bns", "bns:1:bbb")
    again = bare_acts._load_cached("bns", "bns:1:aaa")
    assert first is again
    assert first is not second
    assert reads.count("bns_runtime_v1.json") == 2
