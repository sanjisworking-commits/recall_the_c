"""Shared Playground HTTP clock for tests.

Stage 1 helpers pin roster writes to 16 September 2026 (``NOW``). HTTP routes
call ``playground_today()`` and entitlement ``resolve()`` with ``now=None``.
Default those clocks to the same instant so HTTP consume and ``now=NOW``
capacity stay in one Asia/Kolkata month.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

PLAYGROUND_TEST_NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _playground_test_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    from constitution_memorizer.entitlements import service as entitlement_service
    from constitution_memorizer.playground.roster import period as period_mod

    real_period_utc = period_mod._as_utc
    real_ent_utc = entitlement_service._utc

    def frozen_period_utc(now):
        return real_period_utc(now or PLAYGROUND_TEST_NOW)

    def frozen_ent_utc(now):
        return real_ent_utc(now or PLAYGROUND_TEST_NOW)

    monkeypatch.setattr(period_mod, "_as_utc", frozen_period_utc)
    monkeypatch.setattr(entitlement_service, "_utc", frozen_ent_utc)
