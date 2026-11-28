"""pytest plugin: shift the Python clock to FAKE_NOW, to find tests that depend
on the day the suite runs (M8 test corrections, 2026-11-28).

    FAKE_NOW="2026-12-06T18:30:00+05:30" \\
    PYTHONPATH=docs/design/proto-comparison-2026-10-19/m8/tools \\
    .venv/bin/python -m pytest -p fakedate_plugin -q -rf -p no:cacheprovider

Known artefact: tests/test_docling_integration.py::test_docling_extract_smoke
fails under this plugin at every date, the control included, because pandas'
compiled date code rejects the substituted class. It passes without the plugin.

`date.today()`, `datetime.now()/utcnow()/today()` and `time.time()` answer as if
the real clock were FAKE_NOW at start-up and then run on normally. Instances are
always the real classes, so adapters and C-level type checks are unaffected.
Not shifted: the database's own clock (CURRENT_TIMESTAMP), `time.monotonic`.
"""
from __future__ import annotations

import datetime as _dt
import os
import time as _time

# Import libraries that register by exact type before the classes are swapped.
import sqlite3  # noqa: F401
import json  # noqa: F401
import zoneinfo  # noqa: F401
import importlib

for _name in ("pydantic", "pydantic.v1", "pydantic_settings", "fastapi", "fastapi.testclient", "starlette", "httpx",
              "jinja2", "psycopg", "sqlalchemy", "jwt", "email.utils", "http.cookiejar", "http.cookies", "dateutil.parser"):
    try:
        importlib.import_module(_name)
    except Exception:
        pass

_real_date = _dt.date
_real_datetime = _dt.datetime
_real_time = _time.time

_target = _real_datetime.fromisoformat(os.environ["FAKE_NOW"])
if _target.tzinfo is None:
    _target = _target.astimezone()
_OFFSET = _target - _real_datetime.now(_dt.timezone.utc)
_OFFSET_S = _OFFSET.total_seconds()


def _now_utc():
    return _real_datetime.now(_dt.timezone.utc) + _OFFSET


class _DateMeta(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, _real_date) if cls is FakeDate else type.__instancecheck__(cls, obj)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, _real_date) if cls is FakeDate else type.__subclasscheck__(cls, sub)


class _DatetimeMeta(_DateMeta):
    def __instancecheck__(cls, obj):
        return isinstance(obj, _real_datetime) if cls is FakeDatetime else type.__instancecheck__(cls, obj)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, _real_datetime) if cls is FakeDatetime else type.__subclasscheck__(cls, sub)


class FakeDate(_real_date, metaclass=_DateMeta):
    def __new__(cls, *a, **k):
        if cls is FakeDate:
            return _real_date(*a, **k)
        return _real_date.__new__(cls, *a, **k)

    @classmethod
    def today(cls):
        return _now_utc().astimezone().date()


class FakeDatetime(_real_datetime, metaclass=_DatetimeMeta):
    def __new__(cls, *a, **k):
        if cls is FakeDatetime:
            return _real_datetime(*a, **k)
        return _real_datetime.__new__(cls, *a, **k)

    @classmethod
    def now(cls, tz=None):
        now = _now_utc()
        if tz is None:
            return now.astimezone().replace(tzinfo=None)
        return now.astimezone(tz)

    @classmethod
    def today(cls):
        return cls.now()

    @classmethod
    def utcnow(cls):
        return _now_utc().replace(tzinfo=None)


FakeDate.min, FakeDate.max = _real_date.min, _real_date.max
FakeDatetime.min, FakeDatetime.max = _real_datetime.min, _real_datetime.max
FakeDate.__name__ = FakeDate.__qualname__ = "date"
FakeDatetime.__name__ = FakeDatetime.__qualname__ = "datetime"

_dt.date = FakeDate
_dt.datetime = FakeDatetime
_time.time = lambda: _real_time() + _OFFSET_S


def pytest_report_header(config):
    return f"fakedate: clock shifted to {_dt.datetime.now().astimezone().isoformat()} (date.today() = {_dt.date.today()})"
