"""Unit-scoped speech transcription for Letters and Recite."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, File, Form, Request, UploadFile, WebSocket
from fastapi.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect, WebSocketState

from constitution_memorizer.speech.align import (
    LETTERS_ALIGN_WINDOW,
    AlignmentHit,
    align_text,
    keyterm_shortlist,
    speakable_targets,
    tokenize,
)
from constitution_memorizer.speech.limits import (
    SpeechRateLimiter,
    SpeechTooLarge,
    mime_allowed,
    read_upload_limited,
)
from constitution_memorizer.speech.provider import (
    SpeechError,
    SpeechUnavailable,
    Transcript,
)
from constitution_memorizer.web.entitlements import resolve_learn_access
from constitution_memorizer.web.request_context import bound_engine, record_request_timing

router = APIRouter()

_ALLOWED_MODES = frozenset({"letters", "recite"})


def _engine(request: Request):
    bound = getattr(request.state, "bound_engine", None) or bound_engine.get()
    if bound is not None:
        return bound
    return request.app.state.engine


def _rate_key(request: Request) -> str:
    """Guest buckets are the TCP peer IP, not a cookie or X-Forwarded-For.

    A client-supplied session cookie or spoofed forwarded header must not
    mint a fresh limiter bucket.
    """
    user = getattr(request.state, "current_user", None)
    if user is not None:
        return f"user:{user.id}"
    host = request.client.host if request.client is not None else "unknown"
    return f"ip:{host}"


def _error(code: str, status: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": code}, status_code=status)


def _alignment_payload(hits: list[AlignmentHit]) -> list[dict[str, object]]:
    return [{"index": hit.index, "status": hit.status} for hit in hits]


@router.post("/learn/{unit_id}/speech/transcribe")
async def transcribe_utterance(
    request: Request,
    unit_id: str,
    mode: str = Form(...),
    from_index: int = Form(0),
    text: str = Form(""),
    audio: UploadFile | None = File(None),
    expected: str = Form(""),
) -> JSONResponse:
    # ``expected`` is accepted so a client cannot smuggle it as a surprise
    # field that we then *use*. It is ignored; the unit text is authoritative.
    del expected

    mode = (mode or "").strip().lower()
    if mode not in _ALLOWED_MODES:
        return _error("invalid_mode", 400)

    eng = _engine(request)
    unit = eng.get_unit(unit_id)
    if unit is None:
        return _error("not_found", 404)

    access = resolve_learn_access(request, eng, unit.article_number)
    if access.is_locked(mode):
        return JSONResponse(
            {"ok": False, "error": "mode_locked", "mode": mode},
            status_code=403,
        )

    limiter: SpeechRateLimiter = request.app.state.speech_rate_limiter
    if not limiter.allow(_rate_key(request)):
        return _error("rate_limited", 429)

    typed = (text or "").strip()
    transcript_text = ""
    words_payload: list[dict[str, object]] = []

    if typed:
        transcript_text = typed
    else:
        if audio is None:
            return _error("empty", 400)
        content_type = audio.content_type or ""
        if not mime_allowed(content_type):
            return _error("unsupported_type", 400)
        try:
            audio_bytes = await read_upload_limited(audio)
        except SpeechTooLarge:
            return _error("too_large", 413)
        if not audio_bytes:
            return _error("empty", 400)

        provider = request.app.state.speech_provider
        keyterms = keyterm_shortlist(unit.text)
        try:
            started = time.perf_counter()
            result: Transcript = await provider.transcribe(
                audio_bytes,
                mime_type=content_type.split(";")[0].strip() or "audio/webm",
                keyterms=keyterms,
            )
            record_request_timing("speech_transcribe", started)
        except SpeechUnavailable:
            return _error("unavailable", 503)
        except SpeechError as exc:
            return _error(getattr(exc, "error_code", "provider_error"), 502)

        transcript_text = result.text.strip()
        words_payload = [
            {"word": item.word, "confidence": item.confidence}
            for item in result.words
        ]
        if not transcript_text:
            return _error("empty", 400)

    payload: dict[str, object] = {
        "ok": True,
        "transcript": transcript_text,
        "words": words_payload,
    }
    if mode == "letters":
        try:
            start = max(0, int(from_index))
        except (TypeError, ValueError):
            start = 0
        if start > len(tokenize(unit.text)):
            start = 0
        payload["alignment"] = _alignment_payload(
            align_text(unit.text, transcript_text, from_index=start)
        )
    return JSONResponse(payload)


# --------------------------------------------------------------------- #
# Live word-by-word Letters (browser WS ⇄ server ⇄ Deepgram Live)        #
# --------------------------------------------------------------------- #

logger = logging.getLogger(__name__)

LIVE_MAX_SECONDS = 180
LIVE_MAX_BYTES = 4 * 1024 * 1024  # ~4 MB of opus ≈ well past the time cap


async def _live_send(websocket: WebSocket, payload: dict) -> None:
    if websocket.client_state == WebSocketState.CONNECTED:
        await websocket.send_text(json.dumps(payload))


@router.websocket("/learn/{unit_id}/speech/live")
async def live_letters(websocket: WebSocket, unit_id: str) -> None:
    """Stream mic audio in, push per-word alignment out as the user speaks.

    BaseHTTPMiddleware skips WebSocket scopes, so the session user and the
    entitlement gate are resolved here explicitly, mirroring the HTTP route.
    """
    from constitution_memorizer.auth.dependencies import get_optional_current_user

    await websocket.accept()

    app = websocket.app
    user = None
    if getattr(app.state, "multiuser_enabled", False):
        try:
            # WebSocket duck-types Request: .app/.state/.cookies are enough.
            user = get_optional_current_user(websocket)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001 — treat any session issue as guest
            user = None
    websocket.state.current_user = user

    mode = (websocket.query_params.get("mode") or "letters").strip().lower()
    if mode != "letters":
        await _live_send(websocket, {"type": "error", "error": "invalid_mode"})
        await websocket.close()
        return

    eng = app.state.engine
    if user is not None and hasattr(eng, "for_user"):
        eng = eng.for_user(user.id)
    unit = eng.get_unit(unit_id)
    if unit is None:
        await _live_send(websocket, {"type": "error", "error": "not_found"})
        await websocket.close()
        return

    access = resolve_learn_access(websocket, eng, unit.article_number)
    if access.is_locked(mode):
        await _live_send(websocket, {"type": "error", "error": "mode_locked"})
        await websocket.close()
        return

    limiter: SpeechRateLimiter = app.state.speech_rate_limiter
    if user is not None:
        rate_key = f"user:{user.id}"
    else:
        host = websocket.client.host if websocket.client is not None else "unknown"
        rate_key = f"ip:{host}"
    if not limiter.allow(rate_key):
        await _live_send(websocket, {"type": "error", "error": "rate_limited"})
        await websocket.close()
        return

    try:
        start = max(0, int(websocket.query_params.get("from_index") or 0))
    except (TypeError, ValueError):
        start = 0
    if start > len(tokenize(unit.text)):
        start = 0

    provider = app.state.speech_provider
    live_connect = getattr(provider, "live_connect", None)
    if live_connect is None:
        await _live_send(websocket, {"type": "error", "error": "unavailable"})
        await websocket.close()
        return
    try:
        session = await live_connect(keyterms=keyterm_shortlist(unit.text))
    except SpeechUnavailable:
        await _live_send(websocket, {"type": "error", "error": "unavailable"})
        await websocket.close()
        return
    except SpeechError as exc:
        await _live_send(
            websocket,
            {"type": "error", "error": getattr(exc, "error_code", "provider_error")},
        )
        await websocket.close()
        return

    await _live_send(websocket, {"type": "ready"})

    # Sliding alignment anchor. The aligner's window is deliberately small
    # (prefix-alignment quality), so a live session must move the anchor as
    # finals commit matches — a frozen from_index stalls after ~one window
    # of speech. Interims are aligned per segment with a window sized to the
    # segment, so one long unbroken utterance can't out-run it either.
    matched: set[int] = set()
    anchor = start
    speakable_indexes = [index for index, _word in speakable_targets(unit.text)]
    started_at = time.monotonic()

    async def pump_browser_audio() -> None:
        """Browser → Deepgram. A text "stop" frame flushes the stream."""
        received = 0
        while True:
            try:
                message = await websocket.receive()
            except WebSocketDisconnect:
                await session.close()
                return
            if message.get("type") == "websocket.disconnect":
                await session.close()
                return
            chunk = message.get("bytes")
            if chunk:
                received += len(chunk)
                elapsed = time.monotonic() - started_at
                if received > LIVE_MAX_BYTES or elapsed > LIVE_MAX_SECONDS:
                    await session.finish()
                    return
                await session.send_audio(chunk)
                continue
            text = message.get("text")
            if text:
                try:
                    parsed = json.loads(text)
                except ValueError:
                    continue
                if parsed.get("type") == "stop":
                    await session.finish()
                    return

    pump_task = asyncio.create_task(pump_browser_audio())
    try:
        async for event in session.events():
            if not event.text:
                continue
            heard = tokenize(event.text)
            hits = align_text(
                unit.text,
                event.text,
                from_index=anchor,
                window=len(heard) + LETTERS_ALIGN_WINDOW,
            )
            await _live_send(
                websocket,
                {
                    "type": "alignment",
                    "final": event.is_final,
                    "transcript": event.text,
                    "alignment": _alignment_payload(hits),
                },
            )
            if event.is_final:
                matched.update(
                    hit.index for hit in hits if hit.status == "match"
                )
                for index in speakable_indexes:
                    if index >= start and index not in matched:
                        anchor = index
                        break
                else:
                    anchor = start
        await _live_send(websocket, {"type": "done"})
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 — a live session must never 500 the app
        logger.exception("live letters session failed")
        await _live_send(websocket, {"type": "error", "error": "provider_error"})
    finally:
        pump_task.cancel()
        try:
            await pump_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        await session.close()
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
