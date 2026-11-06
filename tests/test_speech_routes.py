"""Unit-scoped /learn/{unit}/speech/transcribe: entitlement, limits, alignment."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.speech.limits import MAX_AUDIO_BYTES, SpeechRateLimiter
from constitution_memorizer.speech.provider import (
    SpeechUnavailable,
    Transcript,
    TranscriptWord,
)
from constitution_memorizer.web.app import create_app

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


class FakeSpeechProvider:
    def __init__(self, text: str = "all citizens shall have the right") -> None:
        self.text = text
        self.calls: list[dict] = []

    async def transcribe(self, audio: bytes, *, mime_type: str, keyterms=()) -> Transcript:
        self.calls.append(
            {"nbytes": len(audio), "mime_type": mime_type, "keyterms": list(keyterms)}
        )
        words = tuple(TranscriptWord(word=w) for w in self.text.split())
        return Transcript(text=self.text, words=words)


def _settings() -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None,
        APP_ENV="test",
        MULTIUSER_ENABLED="true",
        AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true",
        SESSION_SECRET="test-secret",
        SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon",
        DATABASE_URL="",
        COOKIE_SECURE="false",
        ARTICLE_ENTITLEMENTS_ENABLED="true",
    )


def _guest_client(tmp_path: Path, provider=None) -> TestClient:
    clear_settings_cache()
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
        speech_provider=provider or FakeSpeechProvider(),
    )
    return TestClient(app)


def _signed_in_client(tmp_path: Path, provider=None) -> TestClient:
    clear_settings_cache()
    store = InMemorySessionStore()
    fake = FakeAuthProvider()
    fake.seed_google_user(
        user_id=UUID("11111111-1111-4111-8111-111111111111"),
        email="a@example.com",
        display_name="User A",
    )
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser=True,
        multiuser_settings=_settings(),
        auth_provider=fake,
        session_store=store,
        speech_provider=provider or FakeSpeechProvider(),
    )
    client = TestClient(app)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(
        f"/auth/callback?code=fake-google-code&state={state}",
        follow_redirects=False,
    )
    return client


def test_missing_unit_404(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    resp = client.post(
        "/learn/no-such/speech/transcribe",
        data={"mode": "letters", "text": "hello"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_guest_letters_typed_alignment(tmp_path: Path) -> None:
    provider = FakeSpeechProvider()
    client = _guest_client(tmp_path, provider)
    resp = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "letters", "text": "No person shall be", "from_index": 0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["transcript"] == "No person shall be"
    hits = {row["index"]: row["status"] for row in body["alignment"]}
    assert 0 not in hits
    assert hits[1] == "match"
    assert hits[2] == "match"
    assert hits[3] == "match"
    assert hits[4] == "match"
    assert provider.calls == []  # typed fallback skips Deepgram
    assert "expected" not in body


def test_expected_form_field_is_ignored(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    resp = client.post(
        "/learn/clause-1/speech/transcribe",
        data={
            "mode": "letters",
            "text": "will",
            "from_index": 3,
            "expected": "shall never be used",
        },
    )
    assert resp.status_code == 200
    hits = {row["index"]: row["status"] for row in resp.json()["alignment"]}
    # clause-1: "(1) No person shall …" — shall is index 3.
    assert 3 in hits
    assert hits[3] == "substitute"


def test_guest_recite_locked(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    resp = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "recite", "text": "No person shall be deprived"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "mode_locked"


def test_audio_success_uses_provider(tmp_path: Path) -> None:
    provider = FakeSpeechProvider("No person shall")
    client = _signed_in_client(tmp_path, provider)
    resp = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "letters", "from_index": 0},
        files={"audio": ("utt.webm", BytesIO(b"fake-bytes"), "audio/webm")},
    )
    assert resp.status_code == 200
    assert provider.calls
    assert provider.calls[0]["nbytes"] == 10
    assert "the" not in provider.calls[0]["keyterms"]
    assert resp.json()["alignment"]


def test_unsupported_mime(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    resp = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "letters"},
        files={"audio": ("utt.bin", BytesIO(b"fake-bytes"), "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "unsupported_type"


def test_filename_suffix_does_not_bypass_mime(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    resp = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "letters"},
        files={"audio": ("utt.webm", BytesIO(b"fake-bytes"), "")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "unsupported_type"


def test_mime_prefix_is_rejected(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    resp = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "letters"},
        files={"audio": ("utt.webm", BytesIO(b"fake-bytes"), "audio/webm-evil")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "unsupported_type"


def test_too_large(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    payload = b"x" * (MAX_AUDIO_BYTES + 1)
    resp = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "letters"},
        files={"audio": ("utt.webm", BytesIO(payload), "audio/webm")},
    )
    assert resp.status_code == 413
    assert resp.json()["error"] == "too_large"


def test_unavailable_provider(tmp_path: Path) -> None:
    class Boom:
        async def transcribe(self, audio, *, mime_type, keyterms=()):
            raise SpeechUnavailable("no key")

    client = _guest_client(tmp_path, Boom())
    resp = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "letters"},
        files={"audio": ("utt.webm", BytesIO(b"fake-bytes"), "audio/webm")},
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "unavailable"


def test_rate_limited(tmp_path: Path) -> None:
    client = _guest_client(tmp_path)
    client.app.state.speech_rate_limiter = SpeechRateLimiter(
        window_seconds=60, max_hits=1
    )
    first = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "letters", "text": "No"},
    )
    assert first.status_code == 200
    second = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "letters", "text": "person"},
    )
    assert second.status_code == 429
    assert second.json()["error"] == "rate_limited"


def test_guest_rate_limit_ignores_spoofed_cookie_and_forwarded_for(
    tmp_path: Path,
) -> None:
    client = _guest_client(tmp_path)
    client.app.state.speech_rate_limiter = SpeechRateLimiter(
        window_seconds=60, max_hits=1
    )
    first = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "letters", "text": "No"},
        headers={"X-Forwarded-For": "203.0.113.10"},
        cookies={"rtc_session": "forged-one"},
    )
    assert first.status_code == 200
    second = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "letters", "text": "person"},
        headers={"X-Forwarded-For": "198.51.100.20"},
        cookies={"rtc_session": "forged-two"},
    )
    assert second.status_code == 429
    assert second.json()["error"] == "rate_limited"


def test_guest_recite_audio_does_not_call_provider(tmp_path: Path) -> None:
    provider = FakeSpeechProvider()
    client = _guest_client(tmp_path, provider)
    resp = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "recite"},
        files={"audio": ("utt.webm", BytesIO(b"fake-bytes"), "audio/webm")},
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "mode_locked"
    assert provider.calls == []


def test_signed_in_claimable_recite_omits_alignment(tmp_path: Path) -> None:
    """RecallC Frees with remaining slots may Recite; alignment is Letters-only."""
    provider = FakeSpeechProvider()
    client = _signed_in_client(tmp_path, provider)
    resp = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "recite", "text": "No person shall"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "alignment" not in body
    assert provider.calls == []


def test_recite_typed_omits_alignment_and_skips_provider(tmp_path: Path) -> None:
    provider = FakeSpeechProvider()
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        speech_provider=provider,
    )
    client = TestClient(app)
    resp = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "recite", "text": "No person shall be convicted"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["transcript"] == "No person shall be convicted"
    assert "alignment" not in body
    assert provider.calls == []


def test_recite_audio_omits_alignment(tmp_path: Path) -> None:
    provider = FakeSpeechProvider("No person shall")
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        speech_provider=provider,
    )
    client = TestClient(app)
    resp = client.post(
        "/learn/clause-1/speech/transcribe",
        data={"mode": "recite"},
        files={"audio": ("utt.webm", BytesIO(b"fake-bytes"), "audio/webm")},
    )
    assert resp.status_code == 200
    assert provider.calls
    assert "alignment" not in resp.json()


def test_app_starts_without_deepgram_key(tmp_path: Path, monkeypatch) -> None:
    from constitution_memorizer.speech.provider import UnavailableSpeechProvider

    # Hermetic: a real DEEPGRAM_API_KEY in the developer's .env must not
    # leak into this assertion (env vars override the .env file).
    monkeypatch.setenv("DEEPGRAM_API_KEY", "")
    clear_settings_cache()
    app = create_app(units_path=MINI_UNITS, db_path=tmp_path / "progress.db")
    assert isinstance(app.state.speech_provider, UnavailableSpeechProvider)
    clear_settings_cache()


def test_speech_align_js_is_not_shipped() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (
        root / "src" / "constitution_memorizer" / "web" / "static" / "speech_align.js"
    ).exists()


# --------------------------------------------------------------------- #
# Live word-by-word Letters over WebSocket                               #
# --------------------------------------------------------------------- #

import asyncio
import json as _json

from constitution_memorizer.speech.provider import (
    LiveTranscriptEvent,
    UnavailableSpeechProvider,
)


class FakeLiveSession:
    """Scripted live session: waits for audio, plays events, waits for stop."""

    def __init__(self, scripted: list[LiveTranscriptEvent]) -> None:
        self._scripted = list(scripted)
        self.audio_chunks: list[bytes] = []
        self._got_audio = asyncio.Event()
        self._finished = asyncio.Event()
        self.closed = False

    async def send_audio(self, chunk: bytes) -> None:
        self.audio_chunks.append(chunk)
        self._got_audio.set()

    async def finish(self) -> None:
        self._finished.set()

    async def close(self) -> None:
        self.closed = True
        self._got_audio.set()
        self._finished.set()

    async def events(self):
        await self._got_audio.wait()
        for event in self._scripted:
            yield event
        await self._finished.wait()


class FakeLiveProvider(FakeSpeechProvider):
    def __init__(self, scripted: list[LiveTranscriptEvent]) -> None:
        super().__init__()
        self.scripted = scripted
        self.sessions: list[FakeLiveSession] = []
        self.live_keyterms: list[list[str]] = []

    async def live_connect(self, *, keyterms=()):
        self.live_keyterms.append(list(keyterms))
        session = FakeLiveSession(self.scripted)
        self.sessions.append(session)
        return session


def test_live_letters_streams_alignment_word_by_word(tmp_path: Path) -> None:
    """Interim results paint matches BEFORE the phrase is finished."""
    provider = FakeLiveProvider(
        [
            LiveTranscriptEvent(text="no person", is_final=False),
            LiveTranscriptEvent(text="no person shall be", is_final=True),
        ]
    )
    client = _guest_client(tmp_path, provider)
    with client.websocket_connect(
        "/learn/clause-1/speech/live?mode=letters&from_index=0"
    ) as ws:
        assert _json.loads(ws.receive_text())["type"] == "ready"
        ws.send_bytes(b"\x01\x02\x03")

        first = _json.loads(ws.receive_text())
        assert first["type"] == "alignment"
        assert first["final"] is False
        interim_hits = {r["index"]: r["status"] for r in first["alignment"]}
        # "no person" already matches display indexes 1 and 2 (0 is "(1)").
        assert interim_hits[1] == "match"
        assert interim_hits[2] == "match"

        second = _json.loads(ws.receive_text())
        assert second["final"] is True
        final_hits = {r["index"]: r["status"] for r in second["alignment"]}
        assert final_hits[3] == "match"
        assert final_hits[4] == "match"
        assert second["transcript"] == "no person shall be"

        ws.send_text(_json.dumps({"type": "stop"}))
        assert _json.loads(ws.receive_text())["type"] == "done"

    session = provider.sessions[0]
    assert session.audio_chunks == [b"\x01\x02\x03"]
    assert session.closed
    # Keyterms come from the unit text, same shortlist as the HTTP route.
    assert provider.live_keyterms and isinstance(provider.live_keyterms[0], list)


def test_live_rejects_non_letters_mode(tmp_path: Path) -> None:
    client = _guest_client(tmp_path, FakeLiveProvider([]))
    with client.websocket_connect(
        "/learn/clause-1/speech/live?mode=recite"
    ) as ws:
        payload = _json.loads(ws.receive_text())
        assert payload == {"type": "error", "error": "invalid_mode"}


def test_live_unknown_unit(tmp_path: Path) -> None:
    client = _guest_client(tmp_path, FakeLiveProvider([]))
    with client.websocket_connect(
        "/learn/no-such-unit/speech/live?mode=letters"
    ) as ws:
        payload = _json.loads(ws.receive_text())
        assert payload == {"type": "error", "error": "not_found"}


def test_live_unavailable_without_key(tmp_path: Path) -> None:
    client = _guest_client(tmp_path, UnavailableSpeechProvider())
    with client.websocket_connect(
        "/learn/clause-1/speech/live?mode=letters"
    ) as ws:
        payload = _json.loads(ws.receive_text())
        assert payload == {"type": "error", "error": "unavailable"}


def test_live_provider_without_live_support(tmp_path: Path) -> None:
    """A transcribe-only provider degrades to the unavailable error frame."""
    client = _guest_client(tmp_path, FakeSpeechProvider())
    with client.websocket_connect(
        "/learn/clause-1/speech/live?mode=letters"
    ) as ws:
        payload = _json.loads(ws.receive_text())
        assert payload == {"type": "error", "error": "unavailable"}


def test_live_rate_limited(tmp_path: Path) -> None:
    provider = FakeLiveProvider([])
    client = _guest_client(tmp_path, provider)
    limiter = client.app.state.speech_rate_limiter
    while limiter.allow("ip:testclient"):
        pass  # drain the guest bucket
    with client.websocket_connect(
        "/learn/clause-1/speech/live?mode=letters"
    ) as ws:
        payload = _json.loads(ws.receive_text())
        assert payload == {"type": "error", "error": "rate_limited"}
    assert provider.sessions == []


def test_live_anchor_slides_across_segments(tmp_path: Path) -> None:
    """Speaking continues past the first pause without a stop/start."""
    provider = FakeLiveProvider(
        [
            LiveTranscriptEvent(
                text="no person accused of any offence shall be", is_final=True
            ),
            LiveTranscriptEvent(
                text="compelled to be a witness against himself", is_final=True
            ),
        ]
    )
    client = _guest_client(tmp_path, provider)
    with client.websocket_connect(
        "/learn/clause-2/speech/live?mode=letters&from_index=0"
    ) as ws:
        assert _json.loads(ws.receive_text())["type"] == "ready"
        ws.send_bytes(b"\x00")
        first = _json.loads(ws.receive_text())
        first_matches = {
            r["index"] for r in first["alignment"] if r["status"] == "match"
        }
        second = _json.loads(ws.receive_text())
        second_matches = {
            r["index"] for r in second["alignment"] if r["status"] == "match"
        }
        ws.send_text(_json.dumps({"type": "stop"}))
        _json.loads(ws.receive_text())  # done
    assert first_matches, "first segment matched nothing"
    # The second segment must keep matching PAST everything the first
    # segment covered — the frozen-anchor bug made this empty.
    assert second_matches
    assert min(second_matches) > max(first_matches)


def test_live_single_long_utterance_outruns_fixed_window(tmp_path: Path) -> None:
    """One unbroken utterance longer than LETTERS_ALIGN_WINDOW fully matches."""
    from constitution_memorizer.speech.align import (
        LETTERS_ALIGN_WINDOW,
        speakable_targets,
    )

    units = _json.loads(MINI_UNITS.read_text())["units"]
    text = next(u["text"] for u in units if u["id"] == "clause-2")
    targets = speakable_targets(text)
    assert len(targets) > LETTERS_ALIGN_WINDOW, "fixture too short for this test"
    spoken = " ".join(word for _index, word in targets)

    provider = FakeLiveProvider([LiveTranscriptEvent(text=spoken, is_final=False)])
    client = _guest_client(tmp_path, provider)
    with client.websocket_connect(
        "/learn/clause-2/speech/live?mode=letters&from_index=0"
    ) as ws:
        assert _json.loads(ws.receive_text())["type"] == "ready"
        ws.send_bytes(b"\x00")
        frame = _json.loads(ws.receive_text())
        matches = {r["index"] for r in frame["alignment"] if r["status"] == "match"}
        ws.send_text(_json.dumps({"type": "stop"}))
    expected = {index for index, _word in targets}
    # Every speakable word matches in ONE frame — the fixed 16-target window
    # used to cap this mid-sentence.
    assert matches == expected


def test_live_interim_reports_substitute_for_wrong_word(tmp_path: Path) -> None:
    """The 'red instantly' feed: interim frames carry substitute hits."""
    provider = FakeLiveProvider(
        [LiveTranscriptEvent(text="no dolphin shall be", is_final=False)]
    )
    client = _guest_client(tmp_path, provider)
    with client.websocket_connect(
        "/learn/clause-1/speech/live?mode=letters&from_index=0"
    ) as ws:
        assert _json.loads(ws.receive_text())["type"] == "ready"
        ws.send_bytes(b"\x00")
        frame = _json.loads(ws.receive_text())
        ws.send_text(_json.dumps({"type": "stop"}))
    assert frame["final"] is False
    hits = {r["index"]: r["status"] for r in frame["alignment"]}
    assert hits[1] == "match"       # "no"
    assert hits[2] == "substitute"  # "dolphin" ≠ "person" → red
    assert hits[3] == "match"       # "shall"
