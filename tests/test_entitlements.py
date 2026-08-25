"""Unit tests for the pure access/entitlement logic (web/entitlements.py)."""

from __future__ import annotations

import pytest

from constitution_memorizer.web import entitlements as ent


# --------------------------------------------------------------------------- #
# access level                                                                 #
# --------------------------------------------------------------------------- #
def test_local_single_user_is_subscribed() -> None:
    assert ent.resolve_level(multiuser_enabled=False, has_user=False, subscribed=False) == ent.SUBSCRIBED


def test_multiuser_no_user_is_guest() -> None:
    assert ent.resolve_level(multiuser_enabled=True, has_user=False, subscribed=False) == ent.GUEST


def test_multiuser_signed_in_is_free() -> None:
    assert ent.resolve_level(multiuser_enabled=True, has_user=True, subscribed=False) == ent.FREE


def test_multiuser_subscribed_is_subscribed() -> None:
    assert ent.resolve_level(multiuser_enabled=True, has_user=True, subscribed=True) == ent.SUBSCRIBED


def test_is_subscribed_seam_is_false_until_billing() -> None:
    assert ent.is_subscribed(object()) is False


def test_can_use_auto_plan_follows_subscribed_level() -> None:
    class _State:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Req:
        def __init__(self, *, multiuser: bool, user: object | None):
            self.app = _State(state=_State(multiuser_enabled=multiuser))
            self.state = _State(current_user=user)

    assert ent.can_use_auto_plan(_Req(multiuser=False, user=None)) is True
    assert ent.can_use_auto_plan(_Req(multiuser=True, user=None)) is False
    assert ent.can_use_auto_plan(_Req(multiuser=True, user=object())) is False


# --------------------------------------------------------------------------- #
# mode sets                                                                    #
# --------------------------------------------------------------------------- #
def test_mode_constants_partition_all_six() -> None:
    assert set(ent.OPEN_MODES) | set(ent.SUBSCRIBER_ONLY_MODES) == set(ent.ALL_MODES)
    assert not (set(ent.OPEN_MODES) & set(ent.SUBSCRIBER_ONLY_MODES))
    assert ent.SUBSCRIBER_ONLY_MODES == ("type", "recite")
    assert len(ent.ALL_MODES) == 6


# --------------------------------------------------------------------------- #
# compute_learn_access matrix                                                  #
# --------------------------------------------------------------------------- #
def test_guest_locks_type_recite_no_persist() -> None:
    a = ent.compute_learn_access(ent.GUEST)
    assert a.allowed_modes == ent.OPEN_MODES
    assert a.required_modes == ent.OPEN_MODES
    assert a.locked_modes == ent.SUBSCRIBER_ONLY_MODES
    assert a.can_persist_done is False
    assert a.should_prompt_claim is False
    assert a.cap_reached is False


def test_subscribed_all_six_everywhere() -> None:
    a = ent.compute_learn_access(ent.SUBSCRIBED)
    assert a.allowed_modes == ent.ALL_MODES
    assert a.required_modes == ent.ALL_MODES
    assert a.locked_modes == ()
    assert a.can_persist_done is True


def test_free_claimed_article_all_six() -> None:
    a = ent.compute_learn_access(ent.FREE, article_claimed=True, free_slots_remaining=1)
    assert a.allowed_modes == ent.ALL_MODES
    assert a.required_modes == ent.ALL_MODES
    assert a.locked_modes == ()
    assert a.can_persist_done is True
    assert a.should_prompt_claim is False


def test_free_claimable_all_six_but_prompts_claim() -> None:
    a = ent.compute_learn_access(ent.FREE, article_claimed=False, free_slots_remaining=2)
    assert a.allowed_modes == ent.ALL_MODES
    assert a.locked_modes == ()
    assert a.can_persist_done is True
    assert a.should_prompt_claim is True
    assert a.cap_reached is False


def test_free_cap_reached_locks_type_recite_no_persist() -> None:
    a = ent.compute_learn_access(ent.FREE, article_claimed=False, free_slots_remaining=0)
    assert a.allowed_modes == ent.OPEN_MODES
    assert a.required_modes == ent.OPEN_MODES
    assert a.locked_modes == ent.SUBSCRIBER_ONLY_MODES
    assert a.can_persist_done is False
    assert a.should_prompt_claim is False
    assert a.cap_reached is True
    assert a.is_locked("type") and a.is_locked("recite")
    assert not a.is_locked("read")


def test_persistence_matrix_can_persist_modes_seen() -> None:
    """R2·3/4: only claimed/subscribed Articles persist modes_seen server-side."""
    assert ent.compute_learn_access(ent.GUEST).can_persist_modes_seen is False
    assert (
        ent.compute_learn_access(ent.FREE, article_claimed=True).can_persist_modes_seen
        is True
    )
    assert (
        ent.compute_learn_access(
            ent.FREE, article_claimed=False, free_slots_remaining=2
        ).can_persist_modes_seen
        is False  # claimable = provisional until claimed on Done
    )
    assert (
        ent.compute_learn_access(
            ent.FREE, article_claimed=False, free_slots_remaining=0
        ).can_persist_modes_seen
        is False  # cap-reached open modes are exploration only
    )
    assert ent.compute_learn_access(ent.SUBSCRIBED).can_persist_modes_seen is True


def test_legacy_over_cap_summary() -> None:
    """R2·6: grandfathered >3 shows saved-Articles wording, never N/3."""
    s = ent.build_access_summary(
        ent.FREE, claimed_articles=("14", "19", "21", "32", "44", "51", "61", "70")
    )
    assert s.legacy_over_cap is True
    assert s.free_slots_remaining == 0
    assert s.cap_reached is True
    assert s.status_line == "Free · 8 saved Articles · Legacy access"
    # Ordinary accounts keep the N/3 form.
    normal = ent.build_access_summary(ent.FREE, claimed_articles=("14", "19"))
    assert normal.legacy_over_cap is False
    assert normal.status_line == "Free · 2 of 3 Articles"


def test_flag_off_resolves_full_access_no_store_reads() -> None:
    """R2·1: dormant flag = legacy full access and zero entitlement reads."""

    class _ExplodingEngine:
        def claimed_articles(self):  # pragma: no cover - must never be called
            raise AssertionError("entitlement store read while flag off")

    req = _Req(multiuser=True, user=object(), entitlements=False)
    a = ent.resolve_learn_access(req, _ExplodingEngine(), 14)
    assert a.allowed_modes == ent.ALL_MODES
    assert a.locked_modes == ()
    assert a.can_persist_modes_seen is True
    assert a.can_persist_done is True
    assert a.should_prompt_claim is False

    s = ent.access_summary(req, _ExplodingEngine())
    assert s.enabled is False


# --------------------------------------------------------------------------- #
# article_key normalization                                                    #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value,expected",
    [(14, "14"), ("19", "19"), (" 21 ", "21"), (None, None), ("", None), ("  ", None)],
)
def test_article_key(value: object, expected: str | None) -> None:
    assert ent.article_key(value) == expected


# --------------------------------------------------------------------------- #
# access summary                                                               #
# --------------------------------------------------------------------------- #
def test_summary_free_zero_claimed() -> None:
    s = ent.build_access_summary(ent.FREE)
    assert s.claimed_count == 0
    assert s.free_slots_remaining == ent.FREE_ARTICLE_LIMIT
    assert s.cap_reached is False
    assert s.status_line == "Free · 0 of 3 Articles"


def test_summary_free_cap_reached() -> None:
    s = ent.build_access_summary(ent.FREE, claimed_articles=("14", "19", "21"))
    assert s.claimed_count == 3
    assert s.free_slots_remaining == 0
    assert s.cap_reached is True


def test_summary_subscribed_no_cap() -> None:
    s = ent.build_access_summary(ent.SUBSCRIBED, claimed_articles=("14", "19", "21", "32"), subscribed=True)
    assert s.cap_reached is False
    assert s.is_subscribed is True
    assert s.status_line == "Recall active"


def test_summary_guest() -> None:
    s = ent.build_access_summary(ent.GUEST)
    assert s.status_line == "Guest"


# --------------------------------------------------------------------------- #
# resolve helpers tolerate an engine without the store yet                     #
# --------------------------------------------------------------------------- #
class _EngineWithClaims:
    def __init__(self, claimed: set[str]) -> None:
        self._claimed = claimed

    def claimed_articles(self) -> set[str]:
        return set(self._claimed)


class _Req:
    def __init__(self, multiuser: bool, user: object, entitlements: bool = True) -> None:
        state = type(
            "S",
            (),
            {
                "multiuser_enabled": multiuser,
                "article_entitlements_enabled": entitlements,
            },
        )()
        self.app = type("A", (), {"state": state})()
        self.state = type("RS", (), {"current_user": user})()


def test_resolve_learn_access_free_claimed_vs_unclaimed() -> None:
    req = _Req(multiuser=True, user=object())
    eng = _EngineWithClaims({"14", "19"})
    claimed = ent.resolve_learn_access(req, eng, 14)
    assert claimed.article_claimed is True and claimed.allowed_modes == ent.ALL_MODES
    unclaimed = ent.resolve_learn_access(req, eng, 32)
    assert unclaimed.article_claimed is False
    assert unclaimed.should_prompt_claim is True  # slot still free (2 claimed)


def test_resolve_learn_access_guest_ignores_store() -> None:
    req = _Req(multiuser=True, user=None)
    a = ent.resolve_learn_access(req, _EngineWithClaims(set()), 14)
    assert a.level == ent.GUEST and a.locked_modes == ent.SUBSCRIBER_ONLY_MODES


def test_access_summary_from_request_and_engine() -> None:
    req = _Req(multiuser=True, user=object())
    s = ent.access_summary(req, _EngineWithClaims({"21", "14"}))
    assert s.level == ent.FREE
    assert s.claimed_articles == ("14", "21")  # numeric sort
    assert s.claimed_count == 2


def test_access_summary_engine_without_store_is_safe() -> None:
    req = _Req(multiuser=True, user=object())
    s = ent.access_summary(req, object())  # engine has no claimed_articles()
    assert s.level == ent.FREE and s.claimed_count == 0


# --------------------------------------------------------------------------- #
# user_free_articles store + grandfather backfill (SQLite integration)        #
# --------------------------------------------------------------------------- #
from datetime import date  # noqa: E402
from pathlib import Path  # noqa: E402
from uuid import UUID  # noqa: E402

from constitution_memorizer.learning.schemas import LearningUnitsDocument  # noqa: E402
from constitution_memorizer.progress.db import open_progress_db  # noqa: E402
from constitution_memorizer.progress.repository import LEARN_MODES, ProgressRepository  # noqa: E402
from constitution_memorizer.progress.scheduler import ReminderEngine  # noqa: E402
from constitution_memorizer.utils.json_io import read_json  # noqa: E402

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"

from tests.quiz_helpers import complete_all_modes  # noqa: E402
USER = UUID("22222222-2222-4222-8222-222222222222")
OTHER_USER = UUID("33333333-3333-4333-8333-333333333333")


def _catalog() -> dict:
    doc = LearningUnitsDocument.model_validate(read_json(MINI_UNITS))
    return {u.id: u for u in doc.units}


def _make_engine(tmp_path: Path) -> ReminderEngine:
    conn = open_progress_db(tmp_path / "progress.db")
    return ReminderEngine(ProgressRepository(conn), _catalog(), user_id=USER)


def test_claim_article_idempotent_one_slot_per_article(tmp_path: Path) -> None:
    eng = _make_engine(tmp_path)
    assert eng.claimed_articles() == set()
    eng.claim_article("20")
    eng.claim_article("20")  # idempotent — many units / repeats = one slot
    eng.claim_article(" 20 ")  # normalized
    assert eng.claimed_articles() == {"20"}
    assert eng.is_article_claimed("20") is True
    assert eng.is_article_claimed("21") is False
    assert eng.is_article_claimed(None) is False


def test_claims_are_user_scoped(tmp_path: Path) -> None:
    eng = _make_engine(tmp_path)
    eng.claim_article("20")
    other = eng.for_user(OTHER_USER)
    assert other.claimed_articles() == set()
    assert other.is_article_claimed("20") is False


def test_claim_requires_article_number(tmp_path: Path) -> None:
    eng = _make_engine(tmp_path)
    with pytest.raises(ValueError):
        eng.claim_article("  ")


def test_grandfather_backfill_from_done_progress(tmp_path: Path) -> None:
    """Distinct parent Articles with genuine Done progress are pre-claimed once."""
    eng = _make_engine(tmp_path)
    # Genuine Done on two units of Article 20 and one of Article 21.
    for unit_id in ("clause-1", "clause-2", "article-end"):
        for mode in LEARN_MODES:
            eng.mark_mode_seen(unit_id, mode)
        eng.mark_done(unit_id, as_of=date(2026, 8, 15))
    # Seen-only unit (no Done) must NOT be grandfathered.
    eng.mark_mode_seen("clause-2-a", "read")

    fresh = eng.for_user(USER)  # fresh caches; triggers lazy backfill
    assert fresh.claimed_articles() == {"20", "21"}  # units of 20 roll up to one

    # Backfill is one-time: later Done progress does not auto-claim.
    for mode in LEARN_MODES:
        fresh.mark_mode_seen("clause-2-a", mode)
    assert fresh.claimed_articles() == {"20", "21"}


def test_backfill_marker_prevents_reclaim_after_removal(tmp_path: Path) -> None:
    eng = _make_engine(tmp_path)
    assert eng.claimed_articles() == set()  # backfill ran on empty progress
    # Later genuine progress does not retroactively grandfather.
    for mode in LEARN_MODES:
        eng.mark_mode_seen("clause-1", mode)
    eng.mark_done("clause-1", as_of=date(2026, 8, 15))
    assert eng.claimed_articles() == set()


# --------------------------------------------------------------------------- #
# Surface rendering: Dashboard chip / Settings line / Profile section          #
# --------------------------------------------------------------------------- #
from fastapi.testclient import TestClient  # noqa: E402

from constitution_memorizer.auth.fake_provider import FakeAuthProvider  # noqa: E402
from constitution_memorizer.auth.sessions import InMemorySessionStore  # noqa: E402
from constitution_memorizer.multiuser.settings import MultiUserSettings  # noqa: E402
from constitution_memorizer.web.app import create_app  # noqa: E402


def _mu_settings(entitlements: bool = True) -> MultiUserSettings:
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
        ARTICLE_ENTITLEMENTS_ENABLED="true" if entitlements else "false",
    )


def _authed_client(
    tmp_path: Path, *, entitlements: bool = True
) -> tuple[TestClient, ProgressRepository]:
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="a@example.com", display_name="Test User")
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_mu_settings(entitlements),
        auth_provider=provider,
        session_store=InMemorySessionStore(),
        progress_repo=repo,
    )
    client = TestClient(app)
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    cb = client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    assert cb.status_code == 303
    return client, repo


def test_free_status_renders_on_dashboard_settings_profile(tmp_path: Path) -> None:
    client, repo = _authed_client(tmp_path)
    repo.claim_article(USER, "20")

    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert "Free · 1/3 Articles" in dash.text

    settings = client.get("/settings")
    assert settings.status_code == 200
    assert "Free · 1 of 3 Articles" in settings.text
    assert "Manage in Profile" in settings.text

    # Profile renders the numbered Free-Article slots (design 05): the empty
    # slot is a row, not an absence, so the allowance is visible at a glance.
    profile = client.get("/profile")
    assert profile.status_code == 200
    assert "Free Articles" in profile.text
    assert "1 of 3 used" in profile.text
    assert "/browse/article/20" in profile.text
    assert profile.text.count("Empty slot") == 2
    assert "Why can't I swap an Article?" in profile.text


def test_guest_sees_no_access_status(tmp_path: Path) -> None:
    conn = open_progress_db(tmp_path / "progress.db")
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_mu_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
        progress_repo=ProgressRepository(conn),
    )
    client = TestClient(app)
    settings = client.get("/settings")
    assert settings.status_code == 200
    assert "Recall access" not in settings.text


# --------------------------------------------------------------------------- #
# Step 2 · claim-on-Done flow                                                  #
# --------------------------------------------------------------------------- #
def _see_all_modes(client: TestClient, unit_id: str) -> None:
    """Complete every mode: /seen for the five, the graded quiz for Test.

    GETs never mark gated modes anymore, so \"seeing\" a mode means
    reporting its completed attempt (or grading the quiz server-side).
    """
    complete_all_modes(client, MINI_UNITS, unit_id)


JSON_HEADERS = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}
ALL_MODES_FIELD = {"modes": ",".join(LEARN_MODES)}


def test_unclaimed_article_mode_visits_stay_provisional(tmp_path: Path) -> None:
    """R2·3: GET/`/seen` on a claimable Article persist nothing server-side."""
    client, repo = _authed_client(tmp_path)
    _see_all_modes(client, "clause-1")
    seen_resp = client.post(
        "/learn/clause-1/seen", data={"mode": "cloze"}, headers=JSON_HEADERS
    )
    assert seen_resp.status_code == 200
    assert seen_resp.json()["persisted"] is False
    assert repo.modes_seen(USER, "clause-1") == set()

    page = client.get("/learn/clause-1")
    assert 'data-seen-provisional="true"' in page.text


def test_done_on_unclaimed_article_prompts_claim(tmp_path: Path) -> None:
    client, repo = _authed_client(tmp_path)

    # JSON with the client's provisional mode list: claim_required, nothing
    # persisted yet.
    resp = client.post(
        "/learn/clause-1/done", data=ALL_MODES_FIELD, headers=JSON_HEADERS
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "claim_required"
    assert body["article_number"] == "20"
    assert body["slots_remaining"] == 3
    assert repo.get_progress(USER, "clause-1") is None
    assert repo.claimed_articles(USER) == set()

    # HTML: redirect to the claim panel, which renders server-side.
    resp = client.post(
        "/learn/clause-1/done", data=ALL_MODES_FIELD, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/learn/clause-1?claim=1"
    panel = client.get("/learn/clause-1?claim=1")
    assert "Add Article 20 to your Free Articles?" in panel.text
    assert 'name="claim_article"' in panel.text

    # Confirming claims + persists Done + schedules in one request.
    resp = client.post(
        "/learn/clause-1/done",
        data={"claim_article": "1", **ALL_MODES_FIELD},
        headers=JSON_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert repo.claimed_articles(USER) == {"20"}
    progress = repo.get_progress(USER, "clause-1")
    assert progress is not None and progress.times_completed == 1
    assert progress.next_revision is not None


def test_decline_claim_persists_nothing(tmp_path: Path) -> None:
    client, repo = _authed_client(tmp_path)
    resp = client.post(
        "/learn/clause-1/done", data=ALL_MODES_FIELD, headers=JSON_HEADERS
    )
    assert resp.status_code == 409
    # "Not now" = simply not confirming; state is untouched.
    assert repo.claimed_articles(USER) == set()
    assert repo.get_progress(USER, "clause-1") is None
    assert repo.modes_seen(USER, "clause-1") == set()


def test_done_on_claimed_article_never_asks_again(tmp_path: Path) -> None:
    client, repo = _authed_client(tmp_path)
    repo.claim_article(USER, "20")
    _see_all_modes(client, "clause-1")  # claimed Article -> GETs persist seen
    assert repo.modes_seen(USER, "clause-1") == set(LEARN_MODES)
    resp = client.post("/learn/clause-1/done", headers=JSON_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert repo.claimed_articles(USER) == {"20"}  # still one slot


def test_claim_prompt_requires_complete_modes(tmp_path: Path) -> None:
    client, repo = _authed_client(tmp_path)
    # Partial provisional list -> the claim prompt is never offered.
    resp = client.post(
        "/learn/clause-1/done", data={"modes": "read,cloze"}, headers=JSON_HEADERS
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "modes_incomplete"
    assert repo.claimed_articles(USER) == set()

    # Forged mode names never count.
    resp = client.post(
        "/learn/clause-1/done",
        data={"modes": "read,cloze,letters,type,recite,test,bogus"},
        headers=JSON_HEADERS,
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "claim_required"


def test_cap_reached_done_gates_and_persists_nothing(tmp_path: Path) -> None:
    client, repo = _authed_client(tmp_path)
    for n in ("101", "102", "103"):
        repo.claim_article(USER, n)
    _see_all_modes(client, "clause-1")  # Article 20 would be the 4th

    resp = client.post("/learn/clause-1/done", headers=JSON_HEADERS)
    assert resp.status_code == 402
    assert resp.json()["error"] == "subscription_required"
    assert repo.get_progress(USER, "clause-1") is None
    assert repo.claimed_articles(USER) == {"101", "102", "103"}

    # Even an explicit claim_article=1 cannot bypass the cap.
    resp = client.post(
        "/learn/clause-1/done", data={"claim_article": "1"}, headers=JSON_HEADERS
    )
    assert resp.status_code == 402
    assert repo.claimed_articles(USER) == {"101", "102", "103"}

    # HTML path renders the gate panel.
    resp = client.post("/learn/clause-1/done", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/learn/clause-1?gate=subscription"
    panel = client.get("/learn/clause-1?gate=subscription")
    assert "Your 3 Free Articles are in use" in panel.text


# --------------------------------------------------------------------------- #
# Step 3 · Article-aware Learn locks                                           #
# --------------------------------------------------------------------------- #
def test_cap_reached_locks_type_recite_in_learn(tmp_path: Path) -> None:
    client, repo = _authed_client(tmp_path)
    for n in ("101", "102", "103"):
        repo.claim_article(USER, n)

    page = client.get("/learn/clause-1")  # Article 20 -> unclaimed, cap reached
    assert 'data-locked-modes="type,recite"' in page.text
    assert "Type 🔒" in page.text and "Recite 🔒" in page.text
    assert "Part of full Recall access" in page.text
    assert "See your Free Articles" in page.text

    # Opening a locked mode never records it seen.
    client.get("/learn/clause-1?mode=type")
    assert repo.modes_seen(USER, "clause-1") == set()

    # The /seen endpoint refuses locked modes outright.
    resp = client.post(
        "/learn/clause-1/seen", data={"mode": "recite"}, headers=JSON_HEADERS
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "mode_locked"
    assert repo.modes_seen(USER, "clause-1") == set()


def test_claimed_article_shows_all_six_unlocked(tmp_path: Path) -> None:
    client, repo = _authed_client(tmp_path)
    for n in ("20", "102", "103"):
        repo.claim_article(USER, n)
    page = client.get("/learn/clause-1")  # Article 20 claimed
    assert 'data-locked-modes=""' in page.text
    assert "🔒" not in page.text
    # Type is gated: opening the tab marks nothing; a completed attempt does.
    client.get("/learn/clause-1?mode=type")
    assert "type" not in repo.modes_seen(USER, "clause-1")
    client.post("/learn/clause-1/seen", data={"mode": "type"})
    assert "type" in repo.modes_seen(USER, "clause-1")


def test_guest_sees_locked_modes_with_signin_return(tmp_path: Path) -> None:
    conn = open_progress_db(tmp_path / "progress.db")
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_mu_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
        progress_repo=ProgressRepository(conn),
    )
    client = TestClient(app)
    page = client.get("/learn/clause-1?mode=type")
    assert 'data-locked-modes="type,recite"' in page.text
    assert "Sign in to use your Free Articles" in page.text
    # The sign-in link returns to the SAME Article + requested mode.
    assert "next=/learn/clause-1%3Fmode%3Dtype" in page.text
    # Guests never see pricing framing on the locked panel.
    assert "/pricing" not in page.text


# --------------------------------------------------------------------------- #
# R2·1 · flag off = legacy behavior end-to-end                                 #
# --------------------------------------------------------------------------- #
def test_flag_off_keeps_legacy_learn_flow(tmp_path: Path) -> None:
    client, repo = _authed_client(tmp_path, entitlements=False)

    # No locks, no provisional marker in the page.
    page = client.get("/learn/clause-1")
    assert 'data-locked-modes=""' in page.text
    assert "data-seen-provisional" not in page.text
    assert "🔒" not in page.text

    # GET + /seen persist exactly as before the boundary existed.
    _see_all_modes(client, "clause-1")
    assert repo.modes_seen(USER, "clause-1") == set(LEARN_MODES)

    # Done persists directly — no claim prompt, no gate, no claims created.
    resp = client.post("/learn/clause-1/done", headers=JSON_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert repo.get_progress(USER, "clause-1").times_completed == 1
    assert repo.claimed_articles(USER) == set()

    # Status surfaces stay hidden.
    dash = client.get("/dashboard")
    assert "Articles" not in dash.text or "dash-access-chip" not in dash.text
    settings_page = client.get("/settings")
    assert "Recall access" not in settings_page.text
    profile = client.get("/profile")
    assert "Recall access" not in profile.text


# --------------------------------------------------------------------------- #
# Step 4 · Article-aware Done + single-transaction claim                       #
# --------------------------------------------------------------------------- #
def test_claim_rides_in_commit_completion_transaction(tmp_path: Path) -> None:
    """Claim + Done persist atomically — a failed commit claims nothing."""
    from constitution_memorizer.progress.repository import CompletionProgress

    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    good = CompletionProgress(
        status="review",
        times_completed=1,
        last_completed=date(2026, 8, 16),
        next_revision=date(2026, 8, 17),
        interval_days=1,
        ease_factor=2.5,
    )
    record = repo.commit_completion(USER, "clause-1", good, claim_article="20")
    assert record.times_completed == 1
    assert repo.claimed_articles(USER) == {"20"}

    # Force a failure mid-transaction (unbindable value in the progress row):
    bad = CompletionProgress(
        status="review",
        times_completed=object(),  # type: ignore[arg-type]
        last_completed=date(2026, 8, 16),
        next_revision=date(2026, 8, 17),
        interval_days=1,
        ease_factor=2.5,
    )
    with pytest.raises(Exception):
        repo.commit_completion(USER, "article-end", bad, claim_article="21")
    # The claim from the failed transaction must NOT survive.
    assert repo.claimed_articles(USER) == {"20"}
    assert repo.get_progress(USER, "article-end") is None


def test_mark_done_with_claim_updates_cache_and_store(tmp_path: Path) -> None:
    eng = _make_engine(tmp_path)
    for mode in LEARN_MODES:
        eng.mark_mode_seen("clause-1", mode)
    result = eng.mark_done(
        "clause-1", as_of=date(2026, 8, 16), require_all_modes=False, claim_article="20"
    )
    assert result.progress.times_completed == 1
    assert eng.claimed_articles() == {"20"}
    assert eng.is_article_claimed("20") is True


def test_cap_article_done_affordance_requires_four(tmp_path: Path) -> None:
    """Guest/cap Articles need only the four open modes to reach the Done CTA."""
    client, repo = _authed_client(tmp_path)
    for n in ("101", "102", "103"):
        repo.claim_article(USER, n)
    page = client.get("/learn/clause-1")  # cap-reached Article 20
    assert 'data-required-modes="read,cloze,letters,test"' in page.text
    assert "0 of 4 methods visited" in page.text


def test_entitlement_aware_done_button_state() -> None:
    from constitution_memorizer.web.service import done_button_state, methods_tracker_line

    class _Unit:
        type = type("T", (), {"value": "CLAUSE"})()
        display_title = "Article 20(1)"

    unit = _Unit()
    open_four = set(ent.OPEN_MODES)
    # All four open modes visited satisfies a four-mode requirement…
    state = done_button_state(unit, open_four, required=open_four)  # type: ignore[arg-type]
    assert state["unlocked"] is True
    # …but not the default six-mode requirement.
    state = done_button_state(unit, open_four)  # type: ignore[arg-type]
    assert state["unlocked"] is False
    assert state["missing"] == ["recite", "type"]
    # Tracker copy scales with the required count; six-mode copy is unchanged.
    assert "of 4 methods" in methods_tracker_line(1, 4)
    assert methods_tracker_line(4, 4).startswith("All 4 methods visited")
    assert "of 6 methods" in methods_tracker_line(1)
    assert "all six" in methods_tracker_line(1)


def test_forged_claim_and_gate_params_render_nothing(tmp_path: Path) -> None:
    client, repo = _authed_client(tmp_path)
    # Slots free -> gate param is not honored; unclaimed w/ slots -> claim honored
    # only when modes complete state does not matter for display, but cap does.
    page = client.get("/learn/clause-1?gate=subscription")
    assert "Your 3 Free Articles are in use" not in page.text
    repo.claim_article(USER, "20")
    page = client.get("/learn/clause-1?claim=1")  # already claimed -> no prompt
    assert "Add Article 20 to your Free Articles?" not in page.text


def test_guest_done_never_claims(tmp_path: Path) -> None:
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "unused.db",
        multiuser=True,
        multiuser_settings=_mu_settings(),
        auth_provider=FakeAuthProvider(),
        session_store=InMemorySessionStore(),
        progress_repo=repo,
    )
    client = TestClient(app)
    resp = client.post("/learn/clause-1/done", headers=JSON_HEADERS, follow_redirects=False)
    # Guests are sent to sign-in before any Done handling; nothing persists.
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login?")
    assert repo.claimed_articles(USER) == set()
    assert repo.get_progress(USER, "clause-1") is None


def test_learn_access_resolves_from_real_store(tmp_path: Path) -> None:
    eng = _make_engine(tmp_path)
    req = _Req(multiuser=True, user=object())
    eng.claim_article("20")

    claimed = ent.resolve_learn_access(req, eng, "20")
    assert claimed.article_claimed is True
    assert claimed.allowed_modes == ent.ALL_MODES

    claimable = ent.resolve_learn_access(req, eng, "21")
    assert claimable.should_prompt_claim is True
    assert claimable.free_slots_remaining == 2

    eng.claim_article("21")
    eng.claim_article("22")
    capped = ent.resolve_learn_access(req, eng, "32")
    assert capped.cap_reached is True
    assert capped.locked_modes == ent.SUBSCRIBER_ONLY_MODES
    assert capped.can_persist_done is False

    summary = ent.access_summary(req, eng)
    assert summary.claimed_count == 3
    assert summary.cap_reached is True
    assert summary.status_line == "Free · 3 of 3 Articles"


# --------------------------------------------------------------------------- #
# Admin role + manual grants: access_source, no fake subscription             #
# --------------------------------------------------------------------------- #
from datetime import datetime, timedelta, timezone  # noqa: E402
from uuid import uuid4  # noqa: E402


def _seed_admin_role(repo: ProgressRepository, user_id: UUID) -> None:
    repo.conn.execute(
        "INSERT INTO user_roles (user_id, role, created_at) VALUES (?, 'admin', ?)",
        (str(user_id), datetime.now(timezone.utc).isoformat()),
    )
    repo.conn.commit()


def _seed_grant(
    repo: ProgressRepository,
    user_id: UUID,
    *,
    source: str = "admin_grant",
    ends_at: datetime | None = None,
) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    repo.conn.execute(
        """
        INSERT INTO access_grants (
            id, user_id, source, starts_at, ends_at, reason,
            granted_by, created_at
        ) VALUES (?, ?, ?, ?, ?, 'test', ?, ?)
        """,
        (
            str(uuid4()),
            str(user_id),
            source,
            (now - timedelta(hours=1)).isoformat(),
            ends_at.isoformat() if ends_at else None,
            str(uuid4()),
            now.isoformat(),
        ),
    )
    repo.conn.commit()


def test_admin_resolves_full_access_without_subscription(tmp_path: Path) -> None:
    client, repo = _authed_client(tmp_path)
    _seed_admin_role(repo, USER)

    # Learn: all six modes, no locks, no claim prompt, no cap.
    page = client.get("/learn/clause-1")
    assert page.status_code == 200
    assert 'data-locked-modes=""' in page.text

    # Dashboard chip says administrator, never a subscription.
    dash = client.get("/dashboard")
    assert "Administrator access" in dash.text
    assert "Recall active" not in dash.text


def test_admin_done_never_writes_free_article_slot(tmp_path: Path) -> None:
    client, repo = _authed_client(tmp_path)
    _seed_admin_role(repo, USER)
    complete_all_modes(client, MINI_UNITS, "clause-1")
    done = client.post(
        "/learn/clause-1/done", headers={"accept": "application/json"}
    )
    assert done.status_code == 200
    # Done persisted as progress, but no Free-Article slot was consumed.
    assert repo.claimed_articles(USER) == set()
    assert repo.get_progress(USER, "clause-1") is not None


def test_grant_holder_resolves_subscribed_with_source(tmp_path: Path) -> None:
    ends = datetime.now(timezone.utc) + timedelta(days=30)
    client, repo = _authed_client(tmp_path)
    _seed_grant(repo, USER, ends_at=ends)

    page = client.get("/learn/clause-1")
    assert page.status_code == 200
    assert 'data-locked-modes=""' in page.text

    dash = client.get("/dashboard")
    assert "Recall access granted" in dash.text
    assert "Recall active" not in dash.text


def test_access_level_stays_three_valued(tmp_path: Path) -> None:
    # Even for an admin, access_level returns "subscribed" — the admin-ness
    # lives in is_admin/access_source on the result objects.
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    from constitution_memorizer.admin.store import SqliteAccessStore

    _seed_admin_role(repo, USER)
    store = SqliteAccessStore(conn)

    class _State:
        current_user = type("U", (), {"id": USER})()

    class _AppState:
        multiuser_enabled = True
        article_entitlements_enabled = True
        access_store = store

    req = type(
        "R",
        (),
        {"app": type("A", (), {"state": _AppState()})(), "state": _State()},
    )()
    assert ent.access_level(req) == ent.SUBSCRIBED

    access = ent.resolve_learn_access(req, _EngineWithClaims(set()), 14)
    assert access.level == ent.SUBSCRIBED
    assert access.is_admin is True
    assert access.access_source == "admin"
    assert access.locked_modes == ()

    summary = ent.access_summary(req, _EngineWithClaims(set()))
    assert summary.level == ent.SUBSCRIBED
    assert summary.is_subscribed is False
    assert summary.access_source == "admin"
    assert summary.status_line == "Administrator access"


def test_grant_summary_carries_expiry_and_no_subscription(tmp_path: Path) -> None:
    conn = open_progress_db(tmp_path / "progress.db")
    repo = ProgressRepository(conn)
    ends = datetime(2026, 9, 30, 18, 29, 59, tzinfo=timezone.utc)
    _seed_grant(repo, USER, source="promotion", ends_at=None)
    _seed_grant(repo, USER, source="admin_grant", ends_at=ends)
    from constitution_memorizer.admin.store import SqliteAccessStore

    store = SqliteAccessStore(conn)

    class _State:
        current_user = type("U", (), {"id": USER})()

    class _AppState:
        multiuser_enabled = True
        article_entitlements_enabled = True
        access_store = store

    req = type(
        "R",
        (),
        {"app": type("A", (), {"state": _AppState()})(), "state": _State()},
    )()
    summary = ent.access_summary(req, _EngineWithClaims({"14"}))
    # Indefinite promotion beats the dated grant; no expiry is printed.
    assert summary.access_source == "promotion"
    assert summary.renews_or_expires_on is None
    assert summary.is_subscribed is False
    assert summary.status_line == "Recall access granted"
    # Claims survive and stay listed for grant holders.
    assert summary.claimed_articles == ("14",)
