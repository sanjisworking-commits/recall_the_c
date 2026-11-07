"""ASGI entrypoint for hosted web (no Docling / CLI import)."""

from __future__ import annotations

import logging

from fastapi import FastAPI

logger = logging.getLogger("uvicorn.error")


def health_only_app(reason: str) -> FastAPI:
    """Tiny app so Railway's /healthz probe can pass after a boot failure.

    A crashing replica never becomes healthy, so zero-downtime deploys stall
    and the previous replica keeps the Postgres pooler full. Serving health
    checks is enough for Railway to finish the deploy; the process logs the
    real error for a follow-up.
    """
    app = FastAPI(title="Recall the C")

    @app.get("/health")
    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    logger.error("Serving health-only app after boot failure: %s", reason)
    return app


def load_hosted_app() -> FastAPI:
    try:
        from constitution_memorizer.multiuser.settings import (
            get_multiuser_settings,
            load_env_file,
        )
        from constitution_memorizer.web.app import create_app

        load_env_file()
        settings = get_multiuser_settings()
        return create_app(
            multiuser=settings.multiuser_enabled,
            multiuser_settings=settings,
        )
    except Exception as exc:
        logger.exception("Hosted create_app failed")
        return health_only_app(str(exc))


app = load_hosted_app()
