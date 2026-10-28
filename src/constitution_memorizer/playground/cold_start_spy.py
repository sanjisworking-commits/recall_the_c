"""T21 / WS11 cold-start import-hydration spy.

Module-level imports are stdlib only. The Bare Act wrap is installed by a
child-local ``sys.meta_path`` loader after ``bare_acts`` exec_module, before
``web.app`` binds ``get_bare_act``. Do not import this module as a way to
load the FastAPI app; the parent spawns a fresh interpreter.
"""

from __future__ import annotations

import argparse
import importlib.abc
import json
import os
import sqlite3
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BARE_ACTS_MODULE = "constitution_memorizer.web.bare_acts"
WEB_APP_MODULE = "constitution_memorizer.web.app"
WEB_ASGI_MODULE = "constitution_memorizer.web.asgi"
POSITIVE_CONTROL_SLUG = "ndps"
MappingLike = dict[str, Any]
KIND_MEASURE = "cold-start"
KIND_SELF_TEST = "cold-start-self-test"
SCHEMA_VERSION = 1
MEASUREMENT_MODE = "fresh_interpreter_subprocess"
CLIENT_SHAPE = "fresh_child_python"
SPY_TARGETS = ("get_bare_act", "_load_cached")
ALEMBIC_HEAD = "20260927_0027"
MODES = (
    "measure",
    "self-test",
    "late-app",
    "late-cache",
    "hang",
    "crash",
    "empty",
    "leak",
)


@dataclass
class SpyState:
    hook_installed: bool = False
    hook_installed_before_web_app_import: bool = False
    wrap_applied: bool = False
    spy_installed_too_late: bool = False
    too_late_reason: str | None = None
    get_bare_act_calls: int = 0
    load_cached_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    hydrated_slugs: list[str] = field(default_factory=list)
    get_bare_act_slugs: list[str] = field(default_factory=list)
    real_load: Any = None
    cache_info_at_wrap: dict[str, int] | None = None
    web_app_in_sys_modules_at_wrap: bool = False
    preimport_web_app: bool = False
    preimport_web_asgi: bool = False
    preimport_bare_acts: bool = False


_STATE = SpyState()
_FINDER: _BareActsSpyFinder | None = None


def spy_state() -> SpyState:
    return _STATE


def reset_spy_state_for_tests() -> None:
    """Parent-process helper. Children are one-shot and do not reset."""
    global _FINDER
    _STATE.__dict__.update(SpyState().__dict__)
    if _FINDER is not None and _FINDER in sys.meta_path:
        sys.meta_path.remove(_FINDER)
    _FINDER = None


class _BareActsSpyLoader(importlib.abc.Loader):
    def __init__(self, wrapped: importlib.abc.Loader) -> None:
        self.wrapped = wrapped

    def create_module(self, spec):  # type: ignore[no-untyped-def]
        create = getattr(self.wrapped, "create_module", None)
        if create is not None:
            return create(spec)
        return None

    def exec_module(self, module) -> None:  # type: ignore[no-untyped-def]
        self.wrapped.exec_module(module)
        _wrap_bare_acts(module)

    def __getattr__(self, name: str):
        return getattr(self.wrapped, name)


class _BareActsSpyFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):  # type: ignore[no-untyped-def]
        if fullname != BARE_ACTS_MODULE:
            return None
        spec = None
        for finder in sys.meta_path:
            if finder is self:
                continue
            find = getattr(finder, "find_spec", None)
            if find is None:
                continue
            spec = find(fullname, path, target)
            if spec is not None:
                break
        if spec is None or spec.loader is None:
            return None
        spec.loader = _BareActsSpyLoader(spec.loader)
        return spec


def _preimport_flags() -> tuple[bool, bool, bool]:
    return (
        WEB_APP_MODULE in sys.modules,
        WEB_ASGI_MODULE in sys.modules,
        BARE_ACTS_MODULE in sys.modules,
    )


def install_hook() -> SpyState:
    """Insert the delegating finder. Fail closed if relevant modules exist."""
    global _FINDER
    pre_app, pre_asgi, pre_bare = _preimport_flags()
    _STATE.preimport_web_app = pre_app
    _STATE.preimport_web_asgi = pre_asgi
    _STATE.preimport_bare_acts = pre_bare
    if pre_app or pre_asgi or pre_bare:
        _STATE.hook_installed = False
        _STATE.hook_installed_before_web_app_import = False
        _STATE.spy_installed_too_late = True
        reasons = []
        if pre_app:
            reasons.append(WEB_APP_MODULE)
        if pre_asgi:
            reasons.append(WEB_ASGI_MODULE)
        if pre_bare:
            reasons.append(BARE_ACTS_MODULE)
        _STATE.too_late_reason = "preimported:" + ",".join(reasons)
        return _STATE
    if _FINDER is None:
        _FINDER = _BareActsSpyFinder()
        sys.meta_path.insert(0, _FINDER)
    _STATE.hook_installed = True
    _STATE.hook_installed_before_web_app_import = True
    return _STATE


def _wrap_bare_acts(module: Any) -> None:
    _STATE.web_app_in_sys_modules_at_wrap = WEB_APP_MODULE in sys.modules
    real_get = module.get_bare_act
    real_load = module._load_cached
    info = real_load.cache_info()
    _STATE.cache_info_at_wrap = {
        "hits": int(info.hits),
        "misses": int(info.misses),
        "currsize": int(info.currsize),
    }
    if info.hits or info.misses or info.currsize:
        _STATE.spy_installed_too_late = True
        _STATE.too_late_reason = "cache_dirty_at_wrap"
        return
    if not _STATE.hook_installed_before_web_app_import:
        _STATE.spy_installed_too_late = True
        _STATE.too_late_reason = "hook_not_installed_before_import"
        return

    def wrapped_get(slug: str):
        _STATE.get_bare_act_calls += 1
        _STATE.get_bare_act_slugs.append(str(slug))
        return real_get(slug)

    def wrapped_load(slug: str, identity: str):
        before = real_load.cache_info()
        _STATE.load_cached_calls += 1
        result = real_load(slug, identity)
        after = real_load.cache_info()
        _STATE.cache_hits += int(after.hits) - int(before.hits)
        _STATE.cache_misses += int(after.misses) - int(before.misses)
        _STATE.hydrated_slugs.append(str(slug))
        return result

    wrapped_load.cache_clear = real_load.cache_clear  # type: ignore[attr-defined]
    wrapped_load.cache_info = real_load.cache_info  # type: ignore[attr-defined]
    module.get_bare_act = wrapped_get
    module._load_cached = wrapped_load
    _STATE.real_load = real_load
    _STATE.wrap_applied = True


def spy_installed_ok() -> bool:
    return (
        _STATE.hook_installed
        and _STATE.hook_installed_before_web_app_import
        and _STATE.wrap_applied
        and not _STATE.spy_installed_too_late
    )


def current_counts() -> dict[str, Any]:
    currsize = 0
    if _STATE.real_load is not None:
        currsize = int(_STATE.real_load.cache_info().currsize)
    elif BARE_ACTS_MODULE in sys.modules:
        cached = getattr(sys.modules[BARE_ACTS_MODULE], "_load_cached", None)
        info = getattr(cached, "cache_info", None)
        if callable(info):
            currsize = int(info().currsize)
    unique_slugs: list[str] = []
    for slug in _STATE.hydrated_slugs:
        if slug not in unique_slugs:
            unique_slugs.append(slug)
    return {
        "get_bare_act_calls": int(_STATE.get_bare_act_calls),
        "load_cached_calls": int(_STATE.load_cached_calls),
        "cache_hits": int(_STATE.cache_hits),
        "cache_misses": int(_STATE.cache_misses),
        "hydrated_slugs": list(unique_slugs),
        "cache_currsize": currsize,
    }


def empty_counts() -> dict[str, Any]:
    return {
        "get_bare_act_calls": 0,
        "load_cached_calls": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "hydrated_slugs": [],
        "cache_currsize": 0,
    }


def delta_counts(after: MappingLike, before: MappingLike) -> dict[str, Any]:
    slugs_after = list(after.get("hydrated_slugs") or [])
    slugs_before = list(before.get("hydrated_slugs") or [])
    new_slugs = [slug for slug in slugs_after if slug not in slugs_before]
    unique: list[str] = []
    for slug in new_slugs:
        if slug not in unique:
            unique.append(slug)
    return {
        "get_bare_act_calls": int(after["get_bare_act_calls"])
        - int(before["get_bare_act_calls"]),
        "load_cached_calls": int(after["load_cached_calls"])
        - int(before["load_cached_calls"]),
        "cache_hits": int(after["cache_hits"]) - int(before["cache_hits"]),
        "cache_misses": int(after["cache_misses"]) - int(before["cache_misses"]),
        "hydrated_slugs": unique,
        "cache_currsize": int(after.get("cache_currsize") or 0),
    }


def phase_is_clean(phase: MappingLike) -> bool:
    return (
        int(phase.get("get_bare_act_calls") or 0) == 0
        and int(phase.get("load_cached_calls") or 0) == 0
        and int(phase.get("cache_hits") or 0) == 0
        and int(phase.get("cache_misses") or 0) == 0
        and not list(phase.get("hydrated_slugs") or [])
        and int(phase.get("cache_currsize") or 0) == 0
    )


def install_evidence() -> dict[str, Any]:
    return {
        "hook_installed": bool(_STATE.hook_installed),
        "hook_installed_before_web_app_import": bool(
            _STATE.hook_installed_before_web_app_import
        ),
        "wrap_applied": bool(_STATE.wrap_applied),
        "spy_installed": spy_installed_ok(),
        "spy_installed_too_late": bool(_STATE.spy_installed_too_late),
        "too_late_reason": _STATE.too_late_reason,
        "web_app_in_sys_modules_at_wrap": bool(_STATE.web_app_in_sys_modules_at_wrap),
        "cache_info_at_wrap": _STATE.cache_info_at_wrap,
        "preimport_web_app": bool(_STATE.preimport_web_app),
        "preimport_web_asgi": bool(_STATE.preimport_web_asgi),
        "preimport_bare_acts": bool(_STATE.preimport_bare_acts),
        "asgi_imported": WEB_ASGI_MODULE in sys.modules,
    }


def _phase_dict(duration_ms: float, counts: MappingLike) -> dict[str, Any]:
    return {
        "duration_ms": float(duration_ms),
        "get_bare_act_calls": int(counts["get_bare_act_calls"]),
        "load_cached_calls": int(counts["load_cached_calls"]),
        "cache_hits": int(counts["cache_hits"]),
        "cache_misses": int(counts["cache_misses"]),
        "hydrated_slugs": list(counts.get("hydrated_slugs") or []),
        "cache_currsize": int(counts.get("cache_currsize") or 0),
    }


def _sqlite_tables(db_path: Path) -> list[str]:
    if not db_path.is_file():
        return []
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1"
        ).fetchall()
    finally:
        conn.close()
    return [str(row[0]) for row in rows]


def _incomplete_measure(
    *,
    reason: str,
    import_phase: dict[str, Any] | None = None,
    create_phase: dict[str, Any] | None = None,
    startup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _measure_skeleton()
    payload["aborted"] = True
    payload["aborted_reason"] = reason
    payload["complete"] = False
    payload["contract_passed"] = False
    payload["failures"] = [{"kind": "incomplete_capture", "detail": reason}]
    payload.update(install_evidence())
    if import_phase is not None:
        payload["import"] = import_phase
    if create_phase is not None:
        payload["create_app"] = create_phase
    if startup is not None:
        payload["startup"] = startup
    return payload


def _measure_skeleton() -> dict[str, Any]:
    evidence = install_evidence()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND_MEASURE,
        "measurement_mode": MEASUREMENT_MODE,
        "app_env": "test",
        "database_backend": "sqlite",
        "client_shape": CLIENT_SHAPE,
        "spy_targets": list(SPY_TARGETS),
        "alembic_head": ALEMBIC_HEAD,
        "git_head": None,
        "aborted": False,
        "aborted_reason": None,
        "complete": False,
        "contract_passed": False,
        "import": _phase_dict(0.0, empty_counts()),
        "create_app": _phase_dict(0.0, empty_counts()),
        "first_request": None,
        "startup": {
            "sqlite_existed_before": None,
            "sqlite_exists_after": None,
            "sqlite_bytes_after": None,
            "sqlite_tables_after": [],
            "units_json_path": None,
            "units_json_bytes": None,
            "postgres_pool_created": None,
            "asgi_imported": WEB_ASGI_MODULE in sys.modules,
            "browse_imported_during_create_app": None,
            "lifespan_ran": False,
        },
        "failures": [],
        **evidence,
    }


def _build_create_app(units_path: Path, db_path: Path):
    from uuid import UUID

    from constitution_memorizer.auth.fake_provider import FakeAuthProvider
    from constitution_memorizer.auth.sessions import InMemorySessionStore
    from constitution_memorizer.multiuser.settings import (
        MultiUserSettings,
        clear_settings_cache,
    )
    from constitution_memorizer.web.app import create_app

    clear_settings_cache()
    settings = MultiUserSettings(
        _env_file=None,
        APP_ENV="test",
        MULTIUSER_ENABLED="true",
        AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true",
        SESSION_SECRET="cold-start-secret",
        SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon",
        DATABASE_URL="",
        COOKIE_SECURE="false",
        APP_BASE_URL="http://127.0.0.1:8010",
    )
    provider = FakeAuthProvider()
    provider.seed_google_user(
        user_id=UUID("11111111-1111-4111-8111-111111111111"),
        email="coldstart-local.invalid",
        display_name="Cold Start",
        avatar_url=None,
    )
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_app(
        units_path=units_path,
        db_path=db_path,
        multiuser=True,
        multiuser_settings=settings,
        auth_provider=provider,
        session_store=InMemorySessionStore(),
    )


def run_measure(*, units_path: Path, db_path: Path, leak: bool = False) -> dict[str, Any]:
    install_hook()
    if _STATE.spy_installed_too_late or not _STATE.hook_installed:
        return _incomplete_measure(
            reason=_STATE.too_late_reason or "spy_installed_too_late"
        )
    t0 = time.perf_counter()
    from constitution_memorizer.web.app import create_app

    import_ms = (time.perf_counter() - t0) * 1000.0
    del create_app
    if WEB_ASGI_MODULE in sys.modules:
        return _incomplete_measure(reason="asgi_import_fuses_create_app")
    if not spy_installed_ok():
        return _incomplete_measure(
            reason=_STATE.too_late_reason or "spy_not_installed_after_import"
        )
    if leak:
        from constitution_memorizer.web.bare_acts import get_bare_act

        get_bare_act(POSITIVE_CONTROL_SLUG)
    import_counts = current_counts()
    import_phase = _phase_dict(import_ms, import_counts)
    existed_before = db_path.exists()
    t1 = time.perf_counter()
    app = _build_create_app(units_path, db_path)
    create_ms = (time.perf_counter() - t1) * 1000.0
    create_counts = delta_counts(current_counts(), import_counts)
    create_phase = _phase_dict(create_ms, create_counts)
    units_bytes = units_path.stat().st_size if units_path.is_file() else None
    tables: list[str] = []
    tables_error = None
    try:
        tables = _sqlite_tables(db_path)
    except sqlite3.Error as exc:
        tables_error = type(exc).__name__
    startup = {
        "sqlite_existed_before": bool(existed_before),
        "sqlite_exists_after": db_path.exists(),
        "sqlite_bytes_after": db_path.stat().st_size if db_path.is_file() else None,
        "sqlite_tables_after": tables,
        "units_json_path": str(units_path),
        "units_json_bytes": units_bytes,
        "postgres_pool_created": getattr(app.state, "db_pool", None) is not None,
        "asgi_imported": WEB_ASGI_MODULE in sys.modules,
        "browse_imported_during_create_app": "constitution_memorizer.web.browse"
        in sys.modules,
        "lifespan_ran": False,
    }
    if tables_error is not None:
        return _incomplete_measure(
            reason=f"sqlite_master:{tables_error}",
            import_phase=import_phase,
            create_phase=create_phase,
            startup=startup,
        )
    contract = phase_is_clean(import_phase) and phase_is_clean(create_phase)
    payload = _measure_skeleton()
    payload.update(install_evidence())
    payload["import"] = import_phase
    payload["create_app"] = create_phase
    payload["startup"] = startup
    payload["aborted"] = False
    payload["aborted_reason"] = None
    payload["complete"] = True
    payload["contract_passed"] = bool(contract)
    payload["failures"] = (
        []
        if contract
        else [{"kind": "hydration_contract", "detail": "unexpected Act hydration"}]
    )
    payload["asgi_imported"] = WEB_ASGI_MODULE in sys.modules
    return payload


def run_self_test() -> dict[str, Any]:
    install_hook()
    if _STATE.spy_installed_too_late or not _STATE.hook_installed:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND_SELF_TEST,
            "complete": False,
            "aborted": True,
            "aborted_reason": _STATE.too_late_reason or "spy_installed_too_late",
            "spy_installed": False,
            "spy_installed_too_late": True,
            **install_evidence(),
        }
    from constitution_memorizer.web.bare_acts import (
        BARE_ACTS,
        _load_cached,
        get_bare_act,
        runtime_cache_identity,
    )

    if not spy_installed_ok():
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND_SELF_TEST,
            "complete": False,
            "aborted": True,
            "aborted_reason": _STATE.too_late_reason or "spy_not_installed",
            **install_evidence(),
        }
    miss_act = get_bare_act(POSITIVE_CONTROL_SLUG)
    miss = current_counts()
    hit_act = get_bare_act(POSITIVE_CONTROL_SLUG)
    hit = current_counts()
    spec = BARE_ACTS[POSITIVE_CONTROL_SLUG]
    direct = _load_cached(POSITIVE_CONTROL_SLUG, runtime_cache_identity(spec))
    after_direct = current_counts()
    complete = (
        miss_act is not None
        and hit_act is not None
        and direct is not None
        and int(miss["get_bare_act_calls"]) >= 1
        and int(miss["load_cached_calls"]) >= 1
        and int(miss["cache_misses"]) >= 1
        and int(hit["get_bare_act_calls"]) >= 2
        and int(hit["load_cached_calls"]) >= 2
        and int(hit["cache_hits"]) >= 1
        and int(after_direct["load_cached_calls"])
        > int(after_direct["get_bare_act_calls"])
        and int(after_direct["load_cached_calls"]) > int(hit["load_cached_calls"])
        and int(after_direct["get_bare_act_calls"]) == int(hit["get_bare_act_calls"])
        and int(after_direct["cache_hits"]) >= int(hit["cache_hits"]) + 1
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND_SELF_TEST,
        "complete": bool(complete),
        "aborted": not complete,
        "aborted_reason": None if complete else "positive_control_mismatch",
        "contract_passed": bool(complete),
        "miss": miss,
        "hit": hit,
        "direct_load": after_direct,
        **install_evidence(),
    }


def run_late_app() -> dict[str, Any]:
    from constitution_memorizer.web.app import create_app

    del create_app
    install_hook()
    payload = _incomplete_measure(
        reason=_STATE.too_late_reason or "spy_installed_too_late"
    )
    payload["spy_installed_too_late"] = True
    return payload


def run_late_cache() -> dict[str, Any]:
    from constitution_memorizer.web.bare_acts import get_bare_act

    get_bare_act(POSITIVE_CONTROL_SLUG)
    install_hook()
    payload = _incomplete_measure(
        reason=_STATE.too_late_reason or "spy_installed_too_late"
    )
    payload["spy_installed_too_late"] = True
    return payload


def write_result(path: Path, payload: MappingLike) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="cold_start_spy")
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--db-path", default="")
    parser.add_argument("--units-path", default="")
    return parser.parse_args(argv)


def child_exit_code(mode: str, payload: MappingLike) -> int:
    if mode in {"late-app", "late-cache", "leak"}:
        complete = bool(payload.get("complete"))
        contract = bool(payload.get("contract_passed"))
        if mode == "leak":
            return 0 if complete and contract else 1
        return 1
    if mode == "self-test":
        return 0 if payload.get("complete") else 1
    complete = bool(payload.get("complete"))
    contract = bool(payload.get("contract_passed"))
    return 0 if complete and contract else 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result_path = Path(args.result)
    if args.mode == "hang":
        time.sleep(120)
        return 1
    if args.mode == "crash":
        os._exit(3)
    if args.mode == "empty":
        write_result(result_path, {})
        return 0
    try:
        if args.mode in {"measure", "leak"}:
            units = Path(args.units_path)
            db_path = Path(args.db_path)
            payload = run_measure(
                units_path=units, db_path=db_path, leak=args.mode == "leak"
            )
        elif args.mode == "self-test":
            payload = run_self_test()
        elif args.mode == "late-app":
            payload = run_late_app()
        elif args.mode == "late-cache":
            payload = run_late_cache()
        else:
            payload = _incomplete_measure(reason=f"unknown_mode:{args.mode}")
        write_result(result_path, payload)
        return child_exit_code(args.mode, payload)
    except Exception as exc:
        payload = _incomplete_measure(reason=f"{type(exc).__name__}")
        payload["failures"] = [
            {
                "kind": "child_exit",
                "detail": type(exc).__name__,
            }
        ]
        try:
            write_result(result_path, payload)
        except OSError:
            pass
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
