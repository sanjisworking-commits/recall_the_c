"""Serve a populated Playground for capture: the multiuser app with the fake
Google provider and one signed-in account whose Playground is filled through
the application's own save points (POST add with scope=entire, POST add with
scope=sections followed by the sections save, POST remove) before the server
starts. Learning progress for the completion pages is written through the
Playground repository's completion methods, as the engine tests do.

No payment and no entitlement change: the account is Free unless --tier names
a fixture subscription row, on a throwaway database that is discarded.

Scenarios
  empty      nothing added
  populated  NDPS (entire Act), BNS (sections 1 and 2; section 1 learned,
             section 2 taken up the ladder), UAPA added then removed
  free2      NDPS active, UAPA added then removed (2 choices used)
  learn      (M7b) NDPS (entire Act); BNS sections 1-3: section 1 with Read and
             Cloze completed through the Learn completion endpoint (so the Learn
             pages show a section in progress with its live source identity),
             section 2 taken up the ladder and section 3 learned through the
             repository's completion methods (for the mastered and learned pages)

    PYTHONPATH=.:src .venv/bin/python …/serve_populated_m7.py --port 8927 --tier plus [--tier-model choices] [--scenario populated]
then
    capture_m1r.py --base http://127.0.0.1:8927 --signin --tier plus --routes …/routes.json …
"""
from __future__ import annotations

import argparse
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import uvicorn
from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.playground.learning.modes import PLAYGROUND_LEARN_MODES
from constitution_memorizer.playground.urls import add_path, learn_complete_path, sections_path
from constitution_memorizer.web.app import create_app

ROOT = Path(__file__).resolve().parents[5]
UNITS = ROOT / "data" / "output" / "learning_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")
_TODAY = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
TIERS = {
    "free": None,
    "plus": {"tier": "plus", "status": "active"},
    "pro": {"tier": "pro", "status": "active"},
    "max": {"tier": "max", "status": "active"},
}


def _post(client: TestClient, path: str, data: dict) -> str:
    token = client.cookies.get("rtc_csrf") or ""
    r = client.post(path, data=dict({"csrf_token": token} if token else {}, **data), follow_redirects=False)
    return f"{r.status_code} {r.headers.get('location', '')}".strip()


def _populate(app, scenario: str) -> dict:
    out: dict = {}
    if scenario == "empty":
        return out
    client = TestClient(app)
    start = client.get("/auth/google/start", follow_redirects=False)
    client.get(f"/auth/callback?code=fake-google-code&state={start.cookies.get('rtc_oauth_state')}", follow_redirects=False)
    client.get("/playground")  # sets the CSRF cookie
    for law in ("ndps", "uapa"):
        out[f"add_{law}"] = _post(client, add_path(law), {"confirm": "add", "scope": "entire"})
    if scenario == "populated":
        out["scope_bns"] = _post(client, add_path("bns"), {"confirm": "add", "scope": "sections"})
        out["sections_bns"] = _post(client, sections_path("bns"), {"section": ["1", "2"]})
    if scenario == "learn":
        out["scope_bns"] = _post(client, add_path("bns"), {"confirm": "add", "scope": "sections"})
        out["sections_bns"] = _post(client, sections_path("bns"), {"section": ["1", "2", "3"]})
        for mode in ("read", "cloze"):
            out[f"complete_{mode}"] = _post(client, learn_complete_path("bns", "1", mode), {})
        repo = app.state.playground
        today = _TODAY.date()
        for mode in PLAYGROUND_LEARN_MODES:
            repo.complete_mode(USER, "bns", "bns:section:3", mode, source_version="v", source_hash="h", as_of=today)
            repo.complete_mode(USER, "bns", "bns:section:2", mode, source_version="v", source_hash="h",
                               as_of=today - timedelta(days=130))
        cursor = today - timedelta(days=129)
        for rung in (1, 3, 7, 15, 30, 60):
            for mode in PLAYGROUND_LEARN_MODES:
                repo.complete_revision_mode_and_advance_if_ready(
                    USER, "bns", "bns:section:2", mode, source_version="v", source_hash="h",
                    as_of=cursor, claimed_rung=rung)
            cursor += timedelta(days={1: 3, 3: 7, 7: 15, 15: 30, 30: 60, 60: 0}[rung])
        out["progress"] = "bns s1 read+cloze (HTTP), s2 ladder, s3 learned"
    out["remove_uapa"] = _post(client, "/playground/roster/uapa/remove", {})
    if scenario == "populated" and app.state.roster.is_law_active_this_period(USER, "bns"):
        repo = app.state.playground
        today = _TODAY.date()
        for mode in PLAYGROUND_LEARN_MODES:
            for n in ("1", "2"):
                repo.complete_mode(USER, "bns", f"bns:section:{n}", mode, source_version="v", source_hash="h",
                                   as_of=today - timedelta(days=130))
        cursor = today - timedelta(days=129)
        for rung in (1, 3, 7, 15, 30, 60):
            for mode in PLAYGROUND_LEARN_MODES:
                repo.complete_revision_mode_and_advance_if_ready(
                    USER, "bns", "bns:section:2", mode, source_version="v", source_hash="h",
                    as_of=cursor, claimed_rung=rung)
            cursor += timedelta(days={1: 3, 3: 7, 7: 15, 15: 30, 30: 60, 60: 0}[rung])
        out["progress"] = "bns s1 learned, s2 ladder"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8927)
    ap.add_argument("--tier", default="plus", choices=sorted(TIERS))
    ap.add_argument("--tier-model", default="monthly")
    ap.add_argument("--scenario", default="populated", choices=("empty", "populated", "free2", "learn"))
    args = ap.parse_args()
    clear_settings_cache()
    settings = MultiUserSettings(
        _env_file=None, APP_ENV="test", MULTIUSER_ENABLED="true", AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true", SESSION_SECRET="test-secret", SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon", DATABASE_URL="", COOKIE_SECURE="false", PLAYGROUND_TIER_MODEL=args.tier_model,
    )
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="a@example.com", display_name="Sanjay", avatar_url=None)
    tmp = Path(tempfile.mkdtemp(prefix="m7-populated-"))
    app = create_app(units_path=UNITS, db_path=tmp / "progress.db", multiuser=True,
                     multiuser_settings=settings, auth_provider=provider, session_store=InMemorySessionStore(),
                     study_materials_dir=tmp / "study-materials")
    app.state.engine.repo.upsert_profile(USER, display_name="Sanjay", avatar_url=None)
    spec = TIERS[args.tier]
    if spec:
        app.state.subscriptions.create_subscription_record(
            USER, tier=spec["tier"], status=spec["status"], billing_period_start=_TODAY - timedelta(days=20),
            billing_period_end=_TODAY + timedelta(days=10), is_current=True)
    saves = _populate(app, args.scenario)
    # A paid account registers a device on each new session and is limited to two.
    # The populate client above was one; remove the tool's own device rows so the
    # capture session and the page-probe session are the account's two devices.
    devices = getattr(app.state, "device_service", None)
    if devices is not None:
        conn = devices._repo._conn
        for table in ("user_device_session", "user_device_replacement", "user_device"):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    print(f"populated Playground ready on http://127.0.0.1:{args.port} tier={args.tier} model={args.tier_model} "
          f"scenario={args.scenario} saves={saves}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
