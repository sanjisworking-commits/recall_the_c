"""R4 — Act progress, six-mode Learn, speech, completion, source-review T42.

Closes U4 (28) and U5 (13, including T42). Stage 1 engines stay authoritative.
No R5/R6 work. Alembic head remains 20260927_0027.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from alembic.config import Config
from alembic.script import ScriptDirectory

from constitution_memorizer.playground.learning.modes import (
    PLAYGROUND_LEARN_MODES,
    PLAYGROUND_MODE_ADVANCE,
    PLAYGROUND_MODE_TASKS,
)
from constitution_memorizer.playground.lifecycle import LIFECYCLE_LEARNED, LIFECYCLE_MASTERED, LIFECYCLE_REVIEW
from constitution_memorizer.playground.locators import parse_locator, section_locator
from constitution_memorizer.playground.progress import (
    build_act_progress,
    choose_next_workspace_row,
)
from constitution_memorizer.playground.source import locators_for_act
from constitution_memorizer.playground.urls import (
    act_mastered_path,
    law_path,
    learn_complete_path,
    learn_path,
    learn_path_for_locator,
    learn_speech_path_for_locator,
    learned_path_for_locator,
    mastered_path_for_locator,
    remove_path,
    sections_path,
    source_review_path,
    source_review_path_for_locator,
    source_review_reviewed_path_for_locator,
    source_review_section_path,
)
from constitution_memorizer.progress.user_ids import LOCAL_USER_ID
from constitution_memorizer.speech.limits import MAX_AUDIO_BYTES, SpeechRateLimiter
from constitution_memorizer.speech.provider import SpeechUnavailable
from constitution_memorizer.web.app import create_app
from constitution_memorizer.web.bare_acts import get_bare_act
from tests.test_entitlement_m3b import _guest_client
from tests.test_playground import MINI_UNITS, _add_and_select, _add_law, _client
from tests.test_playground_m7 import _complete, _json_post
from tests.test_playground_m8 import TODAY, _complete_six, _seed_progress
from tests.test_playground_m9 import _patch_act, _stale_registry
from tests.test_roster_m5a import USER, _authed_client, _confirm_add, _csrf, _subscribe
from tests.test_speech_routes import FakeSpeechProvider

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "20260927_0027"
STATIC = ROOT / "src/constitution_memorizer/web/static"
TEMPLATES = ROOT / "src/constitution_memorizer/web/templates"
MODES = PLAYGROUND_LEARN_MODES


class _Life(SimpleNamespace):
    pass


def _row(
    locator: str,
    *,
    status: str = "not_started",
    life: str = "",
    interval: int = 0,
    completed: int = 0,
    due: bool = False,
    missing: bool = False,
    source_change_kind: str = "",
    href: str = "/x",
    cta: str = "Continue",
    citation: str = "",
    due_label: str = "",
) -> dict:
    progress = None
    if life:
        progress = _Life(status=life, interval_days=interval, next_revision=None)
    return {
        "locator": locator,
        "status": status,
        "progress": progress,
        "completed_count": completed,
        "due": due,
        "missing": missing,
        "source_change_kind": source_change_kind,
        "href": href,
        "cta": cta,
        "citation": citation or locator,
        "due_label": due_label,
        "title": locator,
    }


def _speech_client(tmp_path: Path, provider=None) -> TestClient:
    return TestClient(
        create_app(
            units_path=MINI_UNITS,
            db_path=tmp_path / "progress.db",
            speech_provider=provider or FakeSpeechProvider(),
        )
    )


def _audio_file():
    return {"audio": ("utt.webm", BytesIO(b"fake-audio"), "audio/webm")}


def _speech_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("rtc_csrf") or ""
    return {"X-CSRF-Token": token} if token else {}


def _speech_csrf(client: TestClient) -> dict[str, str]:
    return _csrf(client)


def _post_audio(client: TestClient, url: str):
    return client.post(
        url,
        data=_speech_csrf(client),
        files=_audio_file(),
        headers=_speech_headers(client),
    )


def _post_typed(
    client: TestClient,
    url: str,
    text: str = "This Act may be called",
    **extra,
):
    data = {"text": text, "expected": "client text must not win"}
    data.update(_speech_csrf(client))
    data.update(extra)
    return client.post(url, data=data, headers=_speech_headers(client))


def _ready_subscribed(tmp_path: Path, provider=None) -> tuple[TestClient, object]:
    provider = provider or FakeSpeechProvider()
    client = _authed_client(tmp_path)
    client.app.state.speech_provider = provider
    _subscribe(client)
    assert _confirm_add(client, "ndps").status_code == 303
    saved = client.post(
        sections_path("ndps"),
        data={**_csrf(client), "section": "1"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    return client, provider


def test_alembic_head_unchanged():
    cfg = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [EXPECTED_HEAD]


def test_t22_completed_scope_is_monotonic_and_histogram_excludes_mastered():
    rows = [
        _row("ndps:section:1", life=LIFECYCLE_LEARNED, status="learned"),
        _row("ndps:section:2", life=LIFECYCLE_REVIEW, interval=7, status="learned"),
        _row("ndps:section:3", life=LIFECYCLE_MASTERED, status="mastered"),
        _row("ndps:section:4", completed=2, status="learning"),
    ]
    facts = build_act_progress(rows, law_id="ndps")
    assert facts.completed_scope_count == 3
    assert facts.learned_count == 1
    assert facts.review_count == 1
    assert facts.mastered_count == 1
    assert facts.learning_count == 1
    assert facts.fraction_label == "3/4"
    by_day = {rung.days: rung.count for rung in facts.rungs}
    assert by_day[1] == 1
    assert by_day[7] == 1
    assert by_day[3] == 0
    assert by_day[60] == 0
    learned_then_review = [
        _row("ndps:section:1", life=LIFECYCLE_REVIEW, interval=1, status="due", due=True),
        _row("ndps:section:3", life=LIFECYCLE_MASTERED, status="mastered"),
        _row("ndps:section:2", life=LIFECYCLE_LEARNED, status="learned"),
        _row("ndps:section:4", completed=2, status="learning"),
    ]
    later = build_act_progress(learned_then_review, law_id="ndps")
    assert later.completed_scope_count == facts.completed_scope_count


def test_t22_next_identity_matches_workspace_rule():
    rows = [
        _row("a", completed=6, source_change_kind="changed"),
        _row("b", due=True, missing=True, source_change_kind="missing"),
        _row("c", due=True, citation="Section 3", href="/c", cta="Revise"),
        _row("d", completed=2, href="/d", cta="Continue"),
    ]
    nxt = choose_next_workspace_row(rows)
    assert nxt is not None
    assert nxt["locator"] == "c"
    facts = build_act_progress(rows, law_id="ndps")
    assert facts.next_locator == "c"
    incomplete = [
        _row("a", completed=6, source_change_kind="changed"),
        _row("d", completed=2, href="/d", cta="Continue", citation="Section 4"),
    ]
    assert choose_next_workspace_row(incomplete)["locator"] == "d"


def test_t22_entire_act_uses_effective_learnable(monkeypatch: pytest.MonkeyPatch):
    act = get_bare_act("ndps")
    entire = locators_for_act("ndps", act=act)
    monkeypatch.setattr(
        "constitution_memorizer.playground.progress.locators_for_act",
        lambda law_id, act=None: entire[:2],
    )
    rows = [
        _row(entire[0].value, life=LIFECYCLE_MASTERED, status="mastered"),
        _row(entire[1].value, life=LIFECYCLE_MASTERED, status="mastered"),
        _row("ndps:section:999", missing=True, source_change_kind="missing"),
    ]
    facts = build_act_progress(rows, law_id="ndps", act=act)
    assert facts.entire_act is True
    partial = [
        _row(entire[0].value, life=LIFECYCLE_MASTERED, status="mastered"),
    ]
    assert build_act_progress(partial, law_id="ndps", act=act).entire_act is False


def test_d64_d74_d132_workspace_chrome(tmp_path: Path):
    client = _client(tmp_path)
    empty_add = _add_law(client, "ndps")
    assert empty_add.status_code == 303
    empty = client.get(law_path("ndps"))
    assert empty.status_code == 200
    assert "← Playground" in empty.text
    assert "Nothing selected yet" in empty.text or "No provisions selected" in empty.text
    assert "Manage sections" in empty.text
    _add_and_select(client, "ndps", "1")
    page = client.get(law_path("ndps"))
    assert "pg-progress-ring--act" in page.text
    assert "pg-waffle" in page.text
    assert "On the ladder" in page.text
    assert "pg-chip--next" in page.text or "Next ·" in page.text
    assert "Learn Section 1" in page.text or "Start learning" in page.text
    assert "Manage sections" in page.text
    assert "Up next" in page.text
    assert "VERBATIM TEXT" in page.text
    assert "pg-act-section-list" in page.text
    assert "← My Playground" not in page.text


def test_t23_modes_seen_step_bar_and_out_of_order(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    first = client.get(learn_path("ndps", "1", "read"))
    assert first.status_code == 200
    assert "Step 1 of 6" in first.text
    assert "6 methods" in first.text or "methods left" in first.text
    assert "VERBATIM BARE ACT" in first.text
    assert "First, read it once." in first.text
    assert "Mark as read" in first.text
    posted = _complete(client, "ndps", "1", "recite")
    assert posted.status_code == 200
    assert posted.json()["ok"] is True
    assert posted.json()["all_methods_complete"] is False
    again = client.get(learn_path("ndps", "1", "read"))
    stepper = again.text.split("pg-mode-stepper", 1)[1].split("pg-mode-step-label", 1)[0]
    assert "data-step-mode=\"recite\"" in stepper
    assert "is-done" in stepper
    assert "window.SpeechClient" not in (
        STATIC / "playground-learn.js"
    ).read_text(encoding="utf-8")
    assert "window.RecallSpeech" in (
        STATIC / "playground-learn.js"
    ).read_text(encoding="utf-8")


def test_d85_unit_lead_in_is_context(tmp_path: Path):
    from constitution_memorizer.playground.units import enumerate_selectable_units

    client = _client(tmp_path)
    _add_law(client, "ndps")
    act = get_bare_act("ndps")
    assert act is not None
    units = enumerate_selectable_units(act.section("8"), law_id="ndps")
    assert units
    unit = units[0]
    saved = client.post(
        sections_path("ndps"),
        data={"unit": unit.locator.value},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    page = client.get(learn_path_for_locator(unit.locator, "read"))
    assert page.status_code == 200
    assert "pg-learn-lead-in" in page.text
    assert unit.lead_in[:20] in page.text


def test_t25_letters_typed_skips_provider_and_ignores_expected(tmp_path: Path):
    provider = FakeSpeechProvider("unused")
    client = _speech_client(tmp_path, provider)
    _add_and_select(client, "ndps", "1")
    loc = section_locator("ndps", "1")
    body = client.get(learn_path("ndps", "1", "letters")).text
    assert "data-pg-speech-url" in body
    assert "data-letters-fallback" in body
    assert "Type the next words" in body
    resp = client.post(
        learn_speech_path_for_locator(loc, "letters"),
        data={
            "text": "This Act may be called",
            "expected": "should never be used",
            "from_index": 0,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["transcript"] == "This Act may be called"
    assert "expected" not in payload
    assert payload["alignment"]
    assert provider.calls == []


def test_t25_recite_alignment_is_server_owned(tmp_path: Path):
    client = _speech_client(tmp_path, FakeSpeechProvider())
    _add_and_select(client, "ndps", "1")
    loc = section_locator("ndps", "1")
    page = client.get(learn_path("ndps", "1", "recite"))
    assert "data-recite-fallback" in page.text
    resp = client.post(
        learn_speech_path_for_locator(loc, "recite"),
        data={"text": "This Act may be called the Narcotic Drugs"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    alignment = payload["alignment"]
    assert isinstance(alignment, dict)
    assert alignment["source_words"]
    assert "hit_indices" in alignment
    assert "percent" in alignment
    assert "stats_label" in alignment
    js = (STATIC / "playground-learn.js").read_text(encoding="utf-8")
    assert "RecallAlign" not in js.split("function initRecite", 1)[1].split("function initTest", 1)[0]


def test_t25_rejects_without_provider(tmp_path: Path):
    provider = FakeSpeechProvider()
    client = _speech_client(tmp_path, provider)
    _add_and_select(client, "ndps", "1")
    loc = section_locator("ndps", "1")
    url = learn_speech_path_for_locator(loc, "letters")
    empty = client.post(url, data={})
    assert empty.status_code == 400
    assert empty.json()["error"] == "empty"
    bad_type = client.post(
        url,
        files={"audio": ("utt.txt", BytesIO(b"hello"), "text/plain")},
    )
    assert bad_type.status_code == 400
    assert bad_type.json()["error"] == "unsupported_type"
    huge = client.post(
        url,
        files={"audio": ("utt.webm", BytesIO(b"x" * (MAX_AUDIO_BYTES + 1)), "audio/webm")},
    )
    assert huge.status_code == 413
    assert huge.json()["error"] == "too_large"
    assert provider.calls == []
    invalid = client.post(
        learn_speech_path_for_locator(loc, "read"),
        data={"text": "hello"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"] == "invalid_mode"


def test_d141_letters_rate_limit_then_typed_fallback(tmp_path: Path):
    provider = FakeSpeechProvider()
    client = _speech_client(tmp_path, provider)
    _add_and_select(client, "ndps", "1")
    url = learn_speech_path_for_locator(section_locator("ndps", "1"), "letters")
    client.app.state.speech_rate_limiter = SpeechRateLimiter(
        window_seconds=60, max_hits=1
    )
    first = _post_audio(client, url)
    assert first.status_code == 200
    assert first.json()["ok"] is True
    assert len(provider.calls) == 1
    second = _post_audio(client, url)
    assert second.status_code == 429
    assert second.json()["error"] == "rate_limited"
    assert len(provider.calls) == 1
    typed = _post_typed(client, url)
    assert typed.status_code == 200
    payload = typed.json()
    assert payload["ok"] is True
    assert payload["transcript"] == "This Act may be called"
    assert "expected" not in payload
    assert payload["alignment"]
    assert len(provider.calls) == 1


def test_d141_recite_rate_limit_then_typed_fallback(tmp_path: Path):
    provider = FakeSpeechProvider()
    client = _speech_client(tmp_path, provider)
    _add_and_select(client, "ndps", "1")
    url = learn_speech_path_for_locator(section_locator("ndps", "1"), "recite")
    client.app.state.speech_rate_limiter = SpeechRateLimiter(
        window_seconds=60, max_hits=1
    )
    first = _post_audio(client, url)
    assert first.status_code == 200
    assert len(provider.calls) == 1
    second = _post_audio(client, url)
    assert second.status_code == 429
    assert second.json()["error"] == "rate_limited"
    assert len(provider.calls) == 1
    typed = _post_typed(client, url, text="This Act may be called the Narcotic Drugs")
    assert typed.status_code == 200
    payload = typed.json()
    assert payload["ok"] is True
    alignment = payload["alignment"]
    assert isinstance(alignment, dict)
    assert alignment["source_words"]
    assert "hit_indices" in alignment
    assert "percent" in alignment
    assert "stats_label" in alignment
    assert len(provider.calls) == 1


def test_d141_unavailable_then_typed_fallback(tmp_path: Path):
    class Boom:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def transcribe(self, audio, *, mime_type, keyterms=()):
            self.calls.append(
                {"nbytes": len(audio), "mime_type": mime_type, "keyterms": list(keyterms)}
            )
            raise SpeechUnavailable("no key")

    provider = Boom()
    client = _speech_client(tmp_path, provider)
    _add_and_select(client, "ndps", "1")
    url = learn_speech_path_for_locator(section_locator("ndps", "1"), "letters")
    down = _post_audio(client, url)
    assert down.status_code == 503
    assert down.json()["error"] == "unavailable"
    assert len(provider.calls) == 1
    typed = _post_typed(client, url)
    assert typed.status_code == 200
    payload = typed.json()
    assert payload["ok"] is True
    assert payload["transcript"] == "This Act may be called"
    assert payload["alignment"]
    assert len(provider.calls) == 1


def test_d141_typed_fallback_keeps_access_gates(tmp_path: Path):
    loc = section_locator("ndps", "1")
    letters = learn_speech_path_for_locator(loc, "letters")
    read_url = learn_speech_path_for_locator(loc, "read")

    guest_provider = FakeSpeechProvider()
    guest = _guest_client(tmp_path / "guest")
    guest.app.state.speech_provider = guest_provider
    guest_denied = _post_typed(guest, letters)
    assert guest_denied.status_code == 401
    assert guest_denied.json()["error"] == "auth_required"
    assert guest_provider.calls == []

    free_provider = FakeSpeechProvider()
    free = _authed_client(tmp_path / "free")
    free.app.state.speech_provider = free_provider
    free_denied = _post_typed(free, letters)
    assert free_denied.status_code == 403
    assert free_denied.json()["error"] == "not_subscribed"
    assert free_provider.calls == []

    for status, folder, error in (
        ("paused", "paused", "subscription_paused"),
        ("halted", "halted", "payment_halted"),
    ):
        provider = FakeSpeechProvider()
        client, _ = _ready_subscribed(tmp_path / folder, provider)
        sub = client.app.state.subscriptions.get_current_subscription(USER)
        client.app.state.subscriptions.update_subscription_state(
            USER, sub.id, status=status
        )
        denied = _post_typed(client, letters)
        assert denied.status_code == 403, status
        assert denied.json()["error"] == error
        assert provider.calls == []

    expired_provider = FakeSpeechProvider()
    expired, _ = _ready_subscribed(tmp_path / "expired", expired_provider)
    sub = expired.app.state.subscriptions.get_current_subscription(USER)
    expired.app.state.subscription_charges.upsert_charge(
        provider_payment_id="pay_d141_refund",
        user_subscription_id=sub.id,
        billing_period_start=sub.billing_period_start,
        billing_period_end=sub.billing_period_end,
        refund_status="full",
    )
    expired_denied = _post_typed(expired, letters)
    assert expired_denied.status_code == 403
    assert expired_denied.json()["error"] == "paid_period_ended"
    assert expired_provider.calls == []

    device_provider = FakeSpeechProvider()
    device, _ = _ready_subscribed(tmp_path / "device", device_provider)
    assert device.get("/playground").status_code == 200
    devices = device.app.state.device_service.list_devices(USER)
    active = [row for row in devices if not row.is_revoked]
    assert active
    device.app.state.device_service.revoke_device(USER, active[0].id)
    device_denied = _post_typed(device, letters)
    assert device_denied.status_code == 403
    assert device_denied.json()["error"] == "device_revoked"
    assert device_provider.calls == []

    inactive_provider = FakeSpeechProvider()
    inactive, _ = _ready_subscribed(tmp_path / "inactive", inactive_provider)
    removed = inactive.post(
        remove_path("ndps"),
        data=_csrf(inactive),
        follow_redirects=False,
    )
    assert removed.status_code in {200, 303}
    inactive_denied = _post_typed(inactive, letters)
    assert inactive_denied.status_code == 403
    assert inactive_denied.json()["error"] == "not_active_this_period"
    assert inactive_provider.calls == []

    unselected_provider = FakeSpeechProvider()
    unselected = _authed_client(tmp_path / "unselected")
    unselected.app.state.speech_provider = unselected_provider
    _subscribe(unselected)
    assert _confirm_add(unselected, "ndps").status_code == 303
    unselected_denied = _post_typed(unselected, letters)
    assert unselected_denied.status_code == 400
    assert unselected_denied.json()["error"] == "not_selected"
    assert unselected_provider.calls == []

    from constitution_memorizer.playground.units import enumerate_selectable_units

    dormant_provider = FakeSpeechProvider()
    dormant = _authed_client(tmp_path / "dormant")
    dormant.app.state.speech_provider = dormant_provider
    _subscribe(dormant)
    assert _confirm_add(dormant, "ndps").status_code == 303
    act = get_bare_act("ndps")
    assert act is not None
    units = enumerate_selectable_units(act.section("8"), law_id="ndps")
    assert units
    saved_unit = dormant.post(
        sections_path("ndps"),
        data={**_csrf(dormant), "unit": units[0].locator.value},
        follow_redirects=False,
    )
    assert saved_unit.status_code == 303
    dormant_url = learn_speech_path_for_locator(section_locator("ndps", "8"), "letters")
    dormant_denied = _post_typed(dormant, dormant_url)
    assert dormant_denied.status_code == 400
    assert dormant_denied.json()["error"] == "not_selected"
    assert dormant_provider.calls == []

    csrf_provider = FakeSpeechProvider()
    csrf_client, _ = _ready_subscribed(tmp_path / "csrf", csrf_provider)
    bad_csrf = csrf_client.post(
        letters,
        data={"text": "This Act", "csrf_token": "nope"},
        headers={"X-CSRF-Token": "nope"},
    )
    assert bad_csrf.status_code == 403
    assert csrf_provider.calls == []

    mode_provider = FakeSpeechProvider()
    mode_client, _ = _ready_subscribed(tmp_path / "mode", mode_provider)
    invalid = _post_typed(mode_client, read_url)
    assert invalid.status_code == 400
    assert invalid.json()["error"] == "invalid_mode"
    assert mode_provider.calls == []


def test_t25_csrf_required_when_session_present(tmp_path: Path):
    client = _authed_client(tmp_path)
    _subscribe(client)
    added = _confirm_add(client, "ndps")
    assert added.status_code == 303
    saved = client.post(
        sections_path("ndps"),
        data={**_csrf(client), "section": "1"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    loc = section_locator("ndps", "1")
    denied = client.post(
        learn_speech_path_for_locator(loc, "letters"),
        data={"text": "This Act"},
    )
    assert denied.status_code == 403
    token = client.cookies.get("rtc_csrf") or ""
    ok = client.post(
        learn_speech_path_for_locator(loc, "letters"),
        data={"text": "This Act", "csrf_token": token},
        headers={"X-CSRF-Token": token},
    )
    assert ok.status_code == 200


def test_t24_learned_get_after_initial_six(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    loc = section_locator("ndps", "1")
    repo = client.app.state.playground
    for mode in ("read", "cloze", "letters", "type", "test"):
        repo.complete_mode(
            LOCAL_USER_ID,
            "ndps",
            loc.value,
            mode,
            source_version="v",
            source_hash="h",
            as_of=TODAY,
        )
    last = _complete(client, "ndps", "1", "recite")
    assert last.status_code == 200
    payload = last.json()
    assert payload["all_methods_complete"] is True
    assert payload["learned"] is True
    assert payload["completion_href"] == learned_path_for_locator(loc)
    page = client.get(learned_path_for_locator(loc))
    assert page.status_code == 200
    assert "Section learned." in page.text
    assert "pg-surface--fixed-dark" in page.text
    assert "of" in page.text and "learned" in page.text
    assert "Ambedkar" not in page.text
    assert "36%" not in page.text
    assert "First revision · Day 1" in page.text


def test_t24_review_stray_get_redirects_and_mastered_gates(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    loc = section_locator("ndps", "1").value
    repo = client.app.state.playground
    _complete_six(repo, LOCAL_USER_ID, "ndps", loc, as_of=TODAY)
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "ndps",
        loc,
        status="review",
        interval_days=3,
        next_revision=TODAY.isoformat(),
        times_completed=1,
        learned_at=TODAY.isoformat(),
    )
    parsed = parse_locator(loc)
    review = client.get(learned_path_for_locator(parsed), follow_redirects=False)
    assert review.status_code == 303
    assert review.headers["location"] == law_path("ndps")
    not_mastered = client.get(mastered_path_for_locator(parsed), follow_redirects=False)
    assert not_mastered.status_code == 303
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "ndps",
        loc,
        status="mastered",
        interval_days=60,
        next_revision=None,
        times_completed=6,
        learned_at=TODAY.isoformat(),
    )
    mastered = client.get(mastered_path_for_locator(parsed))
    assert mastered.status_code == 200
    assert "Mastered, verbatim." in mastered.text
    assert "Completed all six review rungs through Day 60" in mastered.text
    assert "Ambedkar" not in mastered.text
    whole = client.get(act_mastered_path("ndps"), follow_redirects=False)
    assert whole.status_code == 303


def test_t24_revision_six_stays_in_learn_until_day_60(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "constitution_memorizer.playground.routes.playground_today",
        lambda now=None: TODAY,
    )
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    loc = section_locator("ndps", "1")
    repo = client.app.state.playground
    _complete_six(repo, LOCAL_USER_ID, "ndps", loc.value, as_of=TODAY)
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "ndps",
        loc.value,
        status="review",
        interval_days=3,
        next_revision=TODAY.isoformat(),
        times_completed=1,
        learned_at=TODAY.isoformat(),
    )
    for mode in ("read", "cloze", "letters", "type", "test"):
        repo.complete_revision_mode_and_advance_if_ready(
            LOCAL_USER_ID,
            "ndps",
            loc.value,
            mode,
            source_version="v",
            source_hash="h",
            as_of=TODAY,
            claimed_rung=3,
        )
    last = _json_post(
        client,
        learn_complete_path("ndps", "1", "recite"),
        {"revision": 1, "rung_days": 3},
    )
    assert last.status_code == 200
    payload = last.json()
    assert payload["ok"] is True
    assert payload["all_methods_complete"] is True
    assert payload["revision"] is True
    assert payload["completion_href"] == ""
    assert "Day 3 complete" in payload["methods_complete_label"]
    stray = client.get(learned_path_for_locator(loc), follow_redirects=False)
    assert stray.status_code == 303
    assert stray.headers["location"] == law_path("ndps")
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "ndps",
        loc.value,
        status="review",
        interval_days=60,
        next_revision=TODAY.isoformat(),
        times_completed=5,
        learned_at=TODAY.isoformat(),
    )
    for mode in ("read", "cloze", "letters", "type", "test"):
        repo.complete_revision_mode_and_advance_if_ready(
            LOCAL_USER_ID,
            "ndps",
            loc.value,
            mode,
            source_version="v",
            source_hash="h",
            as_of=TODAY,
            claimed_rung=60,
        )
    mastered_last = _json_post(
        client,
        learn_complete_path("ndps", "1", "recite"),
        {"revision": 1, "rung_days": 60},
    )
    mastered_payload = mastered_last.json()
    assert mastered_payload["all_methods_complete"] is True
    assert mastered_payload["mastered"] is True
    assert mastered_payload["completion_href"] == mastered_path_for_locator(loc)
    page = client.get(mastered_path_for_locator(loc))
    assert page.status_code == 200
    assert "Mastered, verbatim." in page.text


def test_t24_d91_whole_act_and_d136_source_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    loc = section_locator("ndps", "1")
    repo = client.app.state.playground
    _complete_six(repo, LOCAL_USER_ID, "ndps", loc.value, as_of=TODAY)
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "ndps",
        loc.value,
        status="mastered",
        interval_days=60,
        next_revision=None,
        times_completed=6,
        learned_at=TODAY.isoformat(),
    )
    monkeypatch.setattr(
        "constitution_memorizer.playground.progress.locators_for_act",
        lambda law_id, act=None: [loc],
    )
    page = client.get(act_mastered_path("ndps"))
    assert page.status_code == 200
    assert "The whole Act. By heart." in page.text
    identity = __import__(
        "constitution_memorizer.playground.eligibility", fromlist=["playground_law_source_identity"]
    ).playground_law_source_identity("ndps")
    repo.upsert_source_change(
        LOCAL_USER_ID,
        "ndps",
        loc.value,
        detected_source_version=identity.source_version,
        detected_law_source_hash=identity.identity_token,
        previous_source_version="old",
        previous_section_hash="aaa",
        current_source_version=identity.source_version,
        current_law_source_hash=identity.identity_token,
        current_section_hash="bbb",
        change_kind="changed",
        had_learning=True,
        had_selection=True,
    )
    with_flag = client.get(mastered_path_for_locator(loc))
    assert with_flag.status_code == 200
    assert "Law updated" in with_flag.text
    assert "The whole Act. By heart." in with_flag.text or "Mastered, verbatim." in with_flag.text


def test_t42_pss_duplicate_printed_two_are_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    first = parse_locator("pss:section:38:subsection:2")
    second = parse_locator("pss:section:38:subsection:2~2")
    client = _client(tmp_path)
    _add_law(client, "pss")
    saved = client.post(
        sections_path("pss"),
        data={"unit": [first.value, second.value]},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    repo = client.app.state.playground
    _complete_six(repo, LOCAL_USER_ID, "pss", first.value, as_of=TODAY)
    _complete_six(repo, LOCAL_USER_ID, "pss", second.value, as_of=TODAY)
    _stale_registry(monkeypatch, "pss", version="9", token="pss-stale")
    listing = client.get(source_review_path("pss"))
    assert listing.status_code == 200
    first_href = source_review_path_for_locator(first)
    second_href = source_review_path_for_locator(second)
    assert first_href != second_href
    assert first_href in listing.text
    assert second_href in listing.text
    detail_first = client.get(first_href)
    assert detail_first.status_code == 200
    assert "Section 38(2)" in detail_first.text
    assert "Mark reviewed" in detail_first.text
    detail_second = client.get(second_href)
    assert detail_second.status_code == 200
    section_only = client.get(source_review_section_path("pss", "38"))
    assert section_only.status_code == 404
    identity = __import__(
        "constitution_memorizer.playground.eligibility",
        fromlist=["playground_law_source_identity"],
    ).playground_law_source_identity("pss")
    posted = client.post(
        source_review_reviewed_path_for_locator(first),
        data={
            "detected_source_version": identity.source_version,
            "detected_law_source_hash": identity.identity_token,
        },
        follow_redirects=False,
    )
    assert posted.status_code == 303
    still = repo.get_source_change(
        LOCAL_USER_ID,
        "pss",
        second.value,
        current_source_version=identity.source_version,
        current_law_source_hash=identity.identity_token,
    )
    first_after = repo.get_source_change(
        LOCAL_USER_ID,
        "pss",
        first.value,
        current_source_version=identity.source_version,
        current_law_source_hash=identity.identity_token,
    )
    assert first_after is None or first_after.status == "reviewed"
    assert still is not None
    assert still.status == "pending"


def test_t42_missing_unit_learn_redirects_to_unit_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from constitution_memorizer.playground.learning.service import LearnProvisionError
    from constitution_memorizer.playground import routes as routes_mod

    loc = parse_locator("pss:section:38:subsection:2")
    client = _client(tmp_path)
    _add_law(client, "pss")
    client.post(
        sections_path("pss"),
        data={"unit": loc.value},
        follow_redirects=False,
    )
    real = routes_mod.load_learn_provision

    def boom(law_id, number, *, act=None, unit=None):
        if unit:
            raise LearnProvisionError("missing unit")
        return real(law_id, number, act=act, unit=unit)

    monkeypatch.setattr(routes_mod, "load_learn_provision", boom)
    page = client.get(learn_path_for_locator(loc, "read"), follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"] == source_review_path_for_locator(loc)
    assert "/u/" in page.headers["location"]


def test_d135_omitted_and_missing_copy_on_review_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    loc = section_locator("ndps", "1").value
    repo = client.app.state.playground
    _complete_six(repo, LOCAL_USER_ID, "ndps", loc, as_of=TODAY)
    _stale_registry(monkeypatch)
    _patch_act(monkeypatch, "ndps", omit=("1",))
    from constitution_memorizer.playground.source_review import detect_source_changes

    detect_source_changes(repo, LOCAL_USER_ID, "ndps")
    omitted = client.get(source_review_section_path("ndps", "1"))
    assert omitted.status_code == 200
    assert "omitted in the current source" in omitted.text
    assert "Mark reviewed" in omitted.text
    _patch_act(monkeypatch, "ndps", missing=("1",))
    detect_source_changes(repo, LOCAL_USER_ID, "ndps")
    missing = client.get(source_review_section_path("ndps", "1"))
    assert missing.status_code == 200
    assert "No longer present in the current source" in missing.text


def test_d73_source_update_panel_variants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    loc = section_locator("ndps", "1").value
    repo = client.app.state.playground
    _complete_six(repo, LOCAL_USER_ID, "ndps", loc, as_of=TODAY)
    _stale_registry(monkeypatch)
    page = client.get(law_path("ndps"))
    assert "Law updated" in page.text
    assert "Review affected provisions" in page.text
    law_html = (TEMPLATES / "playground_law.html").read_text(encoding="utf-8")
    assert "1 learned provision changed since your recorded learning source." in law_html
    assert "Source updated. Your learned provisions are unchanged." in law_html
    assert "source_state.status == 'update_detected'" in law_html


def test_d86_revision_and_source_outdated_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "constitution_memorizer.playground.routes.playground_today",
        lambda now=None: TODAY,
    )
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    loc = section_locator("ndps", "1").value
    repo = client.app.state.playground
    _complete_six(repo, LOCAL_USER_ID, "ndps", loc, as_of=TODAY)
    _seed_progress(
        repo,
        LOCAL_USER_ID,
        "ndps",
        loc,
        status="review",
        interval_days=3,
        next_revision=TODAY.isoformat(),
        times_completed=1,
        learned_at=TODAY.isoformat(),
    )
    page = client.get(learn_path("ndps", "1", "read") + "?revision=1")
    assert page.status_code == 200
    assert "Revision · Day 3" in page.text
    assert "Law updated. Revealed text is the live Bare Act wording." in page.text


def test_d139_failure_copy_in_client():
    js = (STATIC / "playground-learn.js").read_text(encoding="utf-8")
    assert "Could not save this method yet." in js
    assert "This revision already moved on" in js
    assert "This revision is not due yet." in js
    assert "This provision is not in your selection." in js


def test_r4_hydration_one_act_on_workspace_learn_speech_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from constitution_memorizer.web import bare_acts
    from constitution_memorizer.web.bare_acts import clear_bare_act_cache

    client = _speech_client(tmp_path, FakeSpeechProvider())
    _add_and_select(client, "bns", "1")
    loc = section_locator("bns", "1")
    repo = client.app.state.playground
    _complete_six(repo, LOCAL_USER_ID, "bns", loc.value, as_of=TODAY)
    hydrated: list[str] = []
    real = bare_acts.get_bare_act

    def wrapped(slug, *args, **kwargs):
        hydrated.append(str(slug))
        return real(slug, *args, **kwargs)

    monkeypatch.setattr(bare_acts, "get_bare_act", wrapped)
    clear_bare_act_cache()
    for call in (
        lambda: client.get(law_path("bns")),
        lambda: client.get(learn_path("bns", "1", "letters")),
        lambda: client.post(
            learn_speech_path_for_locator(loc, "letters"),
            data={"text": "Whoever"},
        ),
        lambda: client.get(learned_path_for_locator(loc)),
        lambda: client.get(source_review_path("bns")),
    ):
        hydrated.clear()
        call()
        others = [slug for slug in hydrated if slug not in {"bns", "None"}]
        assert "ndps" not in others
        assert "bnss" not in others


def test_r4_assets_and_no_duplicate_engines():
    js = (STATIC / "playground-learn.js").read_text(encoding="utf-8")
    speech = (STATIC / "speech_client.js").read_text(encoding="utf-8")
    css = (STATIC / "playground.css").read_text(encoding="utf-8")
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "playground-learn.js?v=pg3" in base
    assert "speech_client.js?v=speech3" in base
    assert "playground.css?v=pg16" in base
    assert "options.url" in speech
    assert "csrf_token" in speech
    assert "RecallSpeech" in js
    assert "SpeechClient" not in js
    assert "Speech recognition is unavailable. Type the words instead." in js
    assert "Speech recognition is unavailable. Type what you recited." in js
    assert 'code === "unavailable" || code === "rate_limited"' in js
    assert "--pg-ring-size: 84px" in css
    assert "--pg-ring-size: 104px" in css
    routes = (
        ROOT / "src/constitution_memorizer/playground/routes.py"
    ).read_text(encoding="utf-8")
    assert "def _playground_speech" in routes
    assert "recite_alignment" in routes
    assert "/learn/{unit_id}/speech/transcribe" not in routes
    speech_fn = routes.split("async def _playground_speech", 1)[1].split("@router.post", 1)[0]
    typed_at = speech_fn.find("if not typed:")
    limiter_at = speech_fn.find("limiter.allow(")
    assert 0 <= typed_at < limiter_at
    assert ".PlaygroundShell [hidden]" in css
    assert "display: none !important" in css
    assert "html:has(.pg-complete.pg-surface--fixed-dark) .site-header" in css


def test_d75_d84_six_mode_chrome_and_advance_labels(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    for mode in MODES:
        page = client.get(learn_path("ndps", "1", mode))
        assert page.status_code == 200, mode
        assert PLAYGROUND_MODE_TASKS[mode] in page.text
        assert PLAYGROUND_MODE_ADVANCE[mode] in page.text
        assert "Step " in page.text and "of 6" in page.text
        assert "VERBATIM BARE ACT" in page.text
        assert "pg-mode-stepper" in page.text
        assert f'data-pg-learn-panel="{mode}"' in page.text
    read = client.get(learn_path("ndps", "1", "read")).text
    assert "First, read it once." in read
    cloze = client.get(learn_path("ndps", "1", "cloze")).text
    assert "Fill the gaps from memory." in cloze
    assert "data-cloze-density" in cloze
    letters = client.get(learn_path("ndps", "1", "letters")).text
    assert "Speak it" in letters
    assert "data-letters-manual" in letters
    typed = client.get(learn_path("ndps", "1", "type")).text
    assert 'data-pg-complete hidden' in typed
    assert "Start typing" in typed
    recite = client.get(learn_path("ndps", "1", "recite")).text
    assert "Hold to peek" in recite
    assert 'data-pg-complete hidden' in recite
    assert "data-recite-manual" in recite
    quiz = client.get(learn_path("ndps", "1", "test")).text
    assert "A short checkpoint." in quiz
    assert "data-pg-quiz-form" in quiz
    denied = _complete(client, "ndps", "1", "test")
    assert denied.status_code == 404


def test_d87_desktop_deck_panel_layout_is_1040():
    css = (STATIC / "playground.css").read_text(encoding="utf-8")
    assert "minmax(220px, 280px)" not in css
    needle = "@media (min-width: 1040px)"
    found = False
    start = 0
    while True:
        idx = css.find(needle, start)
        if idx == -1:
            break
        block = css[idx : idx + 1400]
        if ".pg-learn-deck" in block and "minmax(280px, 360px)" in block:
            found = True
            assert "display: grid" in block
            assert ".pg-learn-panel" in block
            break
        start = idx + len(needle)
    assert found


def test_d88_d92_completion_copy_and_fixed_dark(tmp_path: Path):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    loc = section_locator("ndps", "1")
    repo = client.app.state.playground
    _complete_six(repo, LOCAL_USER_ID, "ndps", loc.value, as_of=TODAY)
    learned = client.get(learned_path_for_locator(loc))
    assert learned.status_code == 200
    assert "Section learned." in learned.text
    assert "First revision · Day 1" in learned.text
    assert "pg-surface--fixed-dark" in learned.text
    assert "pg-complete-chip" in learned.text
    assert "Ambedkar" not in learned.text
    assert "36%" not in learned.text
    css = (STATIC / "playground.css").read_text(encoding="utf-8")
    assert "html:has(.pg-surface--fixed-dark)" in css
    assert "html:has(.pg-complete.pg-surface--fixed-dark) .site-header" in css


def test_d133_d134_source_review_list_and_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    client = _client(tmp_path)
    _add_and_select(client, "ndps", "1")
    loc = section_locator("ndps", "1")
    repo = client.app.state.playground
    _complete_six(repo, LOCAL_USER_ID, "ndps", loc.value, as_of=TODAY)
    _stale_registry(monkeypatch)
    listing = client.get(source_review_path("ndps"))
    assert listing.status_code == 200
    assert "Source review" in listing.text
    assert "Law updated" in listing.text
    assert source_review_path_for_locator(loc) in listing.text
    detail = client.get(source_review_path_for_locator(loc))
    assert detail.status_code == 200
    assert "Mark reviewed" in detail.text
    assert "This provision has changed since your recorded learning source." in detail.text
    assert "VERBATIM TEXT" in detail.text or "verbatim" in detail.text.lower()


def test_d141_typed_speech_fallback_is_present():
    html = (TEMPLATES / "playground_learn.html").read_text(encoding="utf-8")
    js = (STATIC / "playground-learn.js").read_text(encoding="utf-8")
    assert "data-letters-manual" in html
    assert "data-recite-manual" in html
    assert "Microphone unavailable. Use the typed path." in js
    assert "Speech recognition may be unavailable. Type the next words" in html
    assert "Speech may be unavailable. Type what you recited" in html
    assert "data-letters-check-text" in html
    assert "data-recite-check" in html
