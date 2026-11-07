"""FastAPI learning UI (Sprint 4+).

Keep this module lazy. Importing constitution_memorizer.web.asgi used to pull
create_app through this file, which loaded the full app module before Uvicorn
could bind — the opposite of BootSafeASGI.
"""

from __future__ import annotations

from typing import Any

__all__ = ["create_app"]


def __getattr__(name: str) -> Any:
    if name == "create_app":
        from constitution_memorizer.web.app import create_app as _create_app

        return _create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
