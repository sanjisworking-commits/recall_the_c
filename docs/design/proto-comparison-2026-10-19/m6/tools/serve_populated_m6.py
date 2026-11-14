"""Serve a populated Calendar for capture: the multiuser app with the fake
Google provider and one signed-in account whose progress draws every month
chip state the roadmap legend names — a memorized unit, a review done this
month, a review due today, an overdue review, and scheduled reviews — through
the real month builder (`web/calendar_view.py`). The Auto Plan "Review"
(capacity) chips need a planned day and are not seeded here, so the
data-driven legend item stays absent in these captures. No payment, no
entitlement change: the account is Free unless --tier names a subscription row.

    PYTHONPATH=.:src .venv/bin/python …/serve_populated_m6.py --port 8925 [--tier plus|pro|max|expired|halted]
then
    capture_m1r.py --base http://127.0.0.1:8925 --signin --tier free --routes …/routes.json …
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
_TODAY = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
TIERS = {
    "free": None,
    "plus": {"tier": "plus", "status": "active"},
    "pro": {"tier": "pro", "status": "active"},
    "max": {"tier": "max", "status": "active"},
    "expired": {"tier": "plus", "status": "expired", "period": (_TODAY - timedelta(days=110), _TODAY - timedelta(days=80))},
    "halted": {"tier": "plus", "status": "halted"},
}


def _rows(today: date) -> list[dict]:
    """Progress rows → chips: memorized (first completion), review done
    (later completions inferred from last_completed), due (next_revision ≤
    today), overdue (next_revision in the past), scheduled (future)."""
    return [
        # memorized this month (one completion, review scheduled later this month)
        dict(unit_id="article-14", status="review", times_completed=1, last_completed=today - timedelta(days=2),
             next_revision=today + timedelta(days=5), interval_days=7),
        # review done this month (two completions: memorized day-3, 1-day review day-2), next in 3 days
        dict(unit_id="article-19-clause-1-sub-clause-a", status="review", times_completed=2,
             last_completed=today - timedelta(days=2), next_revision=today + timedelta(days=1), interval_days=3),
        # due today
        dict(unit_id="article-21", status="review", times_completed=1, last_completed=today - timedelta(days=1),
             next_revision=today, interval_days=1),
        # overdue (due three days ago)
        dict(unit_id="article-32-clause-1", status="review", times_completed=1, last_completed=today - timedelta(days=6),
             next_revision=today - timedelta(days=3), interval_days=3),
        # scheduled (next week)
        dict(unit_id="article-1-clause-1", status="review", times_completed=1, last_completed=today - timedelta(days=8),
             next_revision=today + timedelta(days=7), interval_days=15),
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8925)
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
    tmp = Path(tempfile.mkdtemp(prefix="m6-populated-"))
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
    for row in _rows(today):
        eng.repo.upsert_progress(USER, **row)
    eng._invalidate_progress_cache()
    print(f"populated Calendar ready on http://127.0.0.1:{args.port} tier={args.tier} db={tmp}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
