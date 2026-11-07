"""Serve a populated Today for capture: the multiuser app with the fake Google
provider, one signed-in account whose progress holds one completed Article and
two Constitution clauses due today (the screen-08 fixture, `_make_due`), so the
revision hero, the ring and Today's path render. No payment, no entitlement
change: the account is Free unless --tier names a subscription row.

    PYTHONPATH=.:src .venv/bin/python …/serve_populated_m4.py --port 8921 [--tier plus]
then
    capture_m1r.py --base http://127.0.0.1:8921 --signin --tier free …
"""
from __future__ import annotations

import argparse
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import uvicorn

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.web.app import create_app

ROOT = Path(__file__).resolve().parents[5]
UNITS = ROOT / "data" / "output" / "learning_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")
DUE = ["article-14", "article-19-clause-1-sub-clause-a"]
DONE = ["article-1-clause-1"]
_TODAY = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
TIERS = {
    "free": None,
    "plus": {"tier": "plus", "status": "active"},
    "pro": {"tier": "pro", "status": "active"},
    "max": {"tier": "max", "status": "active"},
    "expired": {"tier": "plus", "status": "expired", "period": (_TODAY - timedelta(days=110), _TODAY - timedelta(days=80))},
    "halted": {"tier": "plus", "status": "halted"},
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8921)
    ap.add_argument("--tier", default="free", choices=sorted(TIERS))
    ap.add_argument("--tier-model", default="monthly")
    args = ap.parse_args()
    clear_settings_cache()
    settings = MultiUserSettings(
        _env_file=None, APP_ENV="test", MULTIUSER_ENABLED="true", AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true", SESSION_SECRET="test-secret", SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon", DATABASE_URL="", COOKIE_SECURE="false", PLAYGROUND_TIER_MODEL=args.tier_model,
    )
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="a@example.com", display_name="Sanjay", avatar_url=None)
    tmp = Path(tempfile.mkdtemp(prefix="m4-populated-"))
    app = create_app(units_path=UNITS, db_path=tmp / "progress.db", multiuser=True,
                     multiuser_settings=settings, auth_provider=provider, session_store=InMemorySessionStore())
    repo = app.state.engine.repo
    repo.upsert_profile(USER, display_name="Sanjay", avatar_url=None)
    spec = TIERS[args.tier]
    if spec:
        start, end = spec.get("period", (_TODAY - timedelta(days=20), _TODAY + timedelta(days=10)))
        app.state.subscriptions.create_subscription_record(
            USER, tier=spec["tier"], status=spec["status"], billing_period_start=start,
            billing_period_end=end, is_current=True)
    today = date.today()
    eng = app.state.engine.for_user(USER)
    for unit_id in DONE:
        eng.repo.upsert_progress(USER, unit_id=unit_id, status="review", times_completed=1,
                                 last_completed=today, next_revision=today + timedelta(days=3), interval_days=3)
    for offset, unit_id in enumerate(DUE):
        eng.repo.upsert_progress(USER, unit_id=unit_id, status="review", times_completed=1,
                                 last_completed=today - timedelta(days=1),
                                 next_revision=today - timedelta(days=len(DUE) - offset), interval_days=1)
    eng._invalidate_progress_cache()
    print(f"populated Today ready on http://127.0.0.1:{args.port} tier={args.tier} db={tmp}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
