"""pytest plugin (`-p tickstamp_plugin`, same PYTHONPATH as fakedate_plugin):
every repository write stamp is one second later than the last.
Makes a comparison that includes a write stamp fail every time instead of only
when two writes straddle a second."""
import itertools
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture(autouse=True)
def _ticking_write_stamps(monkeypatch):
    from constitution_memorizer.progress import repository
    base = datetime(2026, 11, 27, 15, 37, 43, tzinfo=timezone.utc)
    ticks = itertools.count()
    monkeypatch.setattr(repository, "_utc_now_iso", lambda: (base + timedelta(seconds=next(ticks))).isoformat(timespec="seconds"))
