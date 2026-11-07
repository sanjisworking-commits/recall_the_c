"""ASGI entrypoint for hosted web (no Docling / CLI import)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI

logger = logging.getLogger("uvicorn.error")

Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]

HEALTH_PATHS = {"/health", "/healthz"}


def health_app() -> FastAPI:
    app = FastAPI(title="Recall the C")

    @app.get("/health")
    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def create_hosted_app() -> FastAPI:
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


class BootSafeASGI:
    """Accept /healthz before create_app so Railway's probe can pass.

    Uvicorn binds, then runs lifespan, then accepts HTTP. Completing lifespan
    startup with a health-only app and loading the real app in a task keeps the
    replica reachable while units/Postgres initialize. A boot exception leaves
    /healthz up instead of crash-looping the deploy.
    """

    def __init__(self) -> None:
        self._health = health_app()
        self._inner: FastAPI | None = None
        self._boot_task: asyncio.Task[None] | None = None
        self._inner_lifespan_queue: asyncio.Queue[dict[str, Any]] | None = None
        self._inner_lifespan_task: asyncio.Task[None] | None = None

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        kind = scope["type"]
        if kind == "lifespan":
            await self._lifespan(receive, send)
            return
        if kind == "http" and scope.get("path") in HEALTH_PATHS:
            await self._health(scope, receive, send)
            return
        target = self._inner if self._inner is not None else self._health
        await target(scope, receive, send)

    async def _lifespan(self, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
                self._boot_task = asyncio.create_task(self._boot(), name="hosted-boot")
            elif message["type"] == "lifespan.shutdown":
                if self._boot_task is not None:
                    self._boot_task.cancel()
                    try:
                        await self._boot_task
                    except (asyncio.CancelledError, Exception):
                        pass
                await self._shutdown_inner()
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def _boot(self) -> None:
        try:
            inner = await asyncio.to_thread(create_hosted_app)
        except Exception:
            logger.exception("Hosted create_app failed; keeping /healthz-only app")
            return
        try:
            await self._startup_inner(inner)
        except Exception:
            logger.exception("Inner lifespan startup failed; keeping /healthz-only app")
            return
        self._inner = inner
        logger.info("Hosted app ready")

    async def _startup_inner(self, inner: FastAPI) -> None:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        done = asyncio.Event()
        error: list[str] = []

        async def inner_receive() -> dict[str, Any]:
            return await queue.get()

        async def inner_send(message: dict[str, Any]) -> None:
            if message["type"] == "lifespan.startup.complete":
                done.set()
            elif message["type"] == "lifespan.startup.failed":
                error.append(str(message.get("message") or "startup failed"))
                done.set()

        scope = {
            "type": "lifespan",
            "asgi": {"version": "3.0", "spec_version": "2.0"},
            "state": {},
            "app": inner,
        }
        task = asyncio.create_task(inner(scope, inner_receive, inner_send))
        await queue.put({"type": "lifespan.startup"})
        await done.wait()
        if error:
            task.cancel()
            raise RuntimeError(error[0])
        self._inner_lifespan_queue = queue
        self._inner_lifespan_task = task

    async def _shutdown_inner(self) -> None:
        queue = self._inner_lifespan_queue
        task = self._inner_lifespan_task
        if queue is None or task is None:
            return
        await queue.put({"type": "lifespan.shutdown"})
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=10)
        except (asyncio.TimeoutError, Exception):
            task.cancel()


app = BootSafeASGI()
