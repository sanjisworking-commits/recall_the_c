"""M6 read-back rows: what each account state is served on the Calendar.

Renders /calendar (month) and /calendar?view=week&date=<today> through the
app's own TestClient for guest, Free, Plus, Pro, Max (legacy), paused,
pending, expired and halted accounts (fixtures identical to the screen tests)
under both tier models and both ARTICLE_ENTITLEMENTS_ENABLED values, and
prints one row per state and view: status / redirect, header label, surface
markers, the legends, toolbar presence, the personal-material create entry
points, the upgrade-sheet presence, the "Continue today's Recall" targets,
the footnote, Playground chip hrefs.

Run from the repository root with the project venv:
    PYTHONPATH=.:src .venv/bin/python docs/design/proto-comparison-2026-10-19/m6/tools/readback_m6.py --out <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.web.app import create_app

ROOT = Path(__file__).resolve().parents[5]
UNITS = ROOT / "data" / "output" / "learning_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")
_TODAY = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
ACTIVE = (_TODAY - timedelta(days=20), _TODAY + timedelta(days=10))
EXPIRED = (_TODAY - timedelta(days=110), _TODAY - timedelta(days=80))
STATES = {
    "guest": None,
    "free": {},
    "plus": {"tier": "plus", "status": "active"},
    "pro": {"tier": "pro", "status": "active"},
    "max": {"tier": "max", "status": "active"},
    "paused": {"tier": "plus", "status": "paused"},
    "pending": {"tier": "plus", "status": "pending"},
    "expired": {"tier": "plus", "status": "expired", "period": EXPIRED},
    "halted": {"tier": "plus", "status": "halted"},
}
LEGACY = ("3 Articles", "Free Articles", "pick any", "Unlock every Article", "Recall active", "from ₹", "/login", "/pricing")


def _settings(tier_model: str, entitlements: bool) -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None, APP_ENV="test", MULTIUSER_ENABLED="true", AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true", SESSION_SECRET="test-secret", SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon", DATABASE_URL="", COOKIE_SECURE="false", PLAYGROUND_TIER_MODEL=tier_model,
        ARTICLE_ENTITLEMENTS_ENABLED="true" if entitlements else "false",
    )


def _app(tmp: Path, tier_model: str, entitlements: bool):
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="a@example.com", display_name="Sanjay", avatar_url=None)
    return create_app(units_path=UNITS, db_path=tmp / "progress.db", multiuser=True,
                      multiuser_settings=_settings(tier_model, entitlements), auth_provider=provider,
                      session_store=InMemorySessionStore())


def _sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    assert client.cookies.get(SESSION_COOKIE_NAME)


def _subscribe(client: TestClient, spec: dict) -> None:
    start, end = spec.get("period", ACTIVE)
    client.app.state.subscriptions.create_subscription_record(
        USER, tier=spec["tier"], status=spec["status"], billing_period_start=start,
        billing_period_end=end, is_current=True)


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def _between(html: str, start: str, end: str) -> str:
    if start not in html:
        return ""
    return html.split(start, 1)[1].split(end, 1)[0]


def _legend(html: str, cls: str) -> list[str]:
    block = _between(html, f'class="{cls}"', "</div>")
    return [t for t in (_text(x) for x in re.findall(r"</span>([^<]+)</span>", block)) if t]


def calendar_row(html: str) -> dict:
    header = _between(html, "<header", "</header>")
    main = _between(html, "<main", "</main>")
    section = main.split("<section", 1)[1].split(">", 1)[0] if "<section" in main else ""
    return {
        "header_status": _text(_between(header, 'class="account-menu-btn-status">', "</span>")),
        "markers": re.findall(r'data-(?:signed-in-calendar|plus-calendar|paid-calendar|halted-calendar|expired-calendar)(?:="[^"]*")?', section),
        "is_week": "is-week" in section,
        "phone_legend": _legend(main, "cal-m-legend"),
        "toolbar": 'class="cal-si-toolbar"' in main,
        "toolbar_legend": _legend(main, "cal-si-legend"),
        "base_legend": _legend(main, "calendar-legend"),
        "week_legend": _legend(main, "calendar-week-legend"),
        "add_task": "data-study-add" in main,
        "cell_add_count": main.count("cal-si-cell-add"),
        "day_add": "data-cal-day-add" in main,
        "editor_dialog": 'id="cal-si-editor"' in html,
        "upgrade_entry": "data-cal-upgrade" in main,
        "upgrade_sheet": 'id="cal-si-upgrade"' in html,
        "continue_hrefs": sorted(set(re.findall(r'class="cal-m-today-continue" href="([^"]+)"', main) + re.findall(r'data-cal-continue-recall href="([^"]+)"', main))),
        "footnote": _text(_between(main, "data-calendar-gcal-footnote>", "</p>")),
        "playground_chip_hrefs": sorted(set(re.findall(r'data-cal-source="playground"[^>]*href="([^"]+)"', main)))[:4],
        "legacy_copy": sorted({p for p in LEGACY if p in main}),
        "sha256": hashlib.sha256(html.encode()).hexdigest()[:16],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", default="monthly,choices")
    ap.add_argument("--entitlements", default="off,on")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    today = date.today().isoformat()
    for model in args.models.split(","):
        for ent in args.entitlements.split(","):
            for state, spec in STATES.items():
                clear_settings_cache()
                with tempfile.TemporaryDirectory() as tmp:
                    with TestClient(_app(Path(tmp), model, ent == "on")) as client:
                        if spec is not None:
                            _sign_in(client)
                            if spec:
                                _subscribe(client, spec)
                            client.app.state.engine.repo.upsert_profile(USER, display_name="Sanjay", avatar_url=None)
                        for key, path in (("month", "/calendar"), ("week", f"/calendar?view=week&date={today}")):
                            r = client.get(path, follow_redirects=False)
                            row = {"state": state, "view": key, "tier_model": model, "entitlements": ent,
                                   "status": r.status_code, "location": r.headers.get("location", "")}
                            if r.status_code == 200:
                                row.update(calendar_row(r.text))
                            rows.append(row)
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    (out / "readback.json").write_text(json.dumps({"sha": sha, "rows": rows}, indent=2, default=str))
    keys = ["state", "view", "tier_model", "entitlements", "status", "location", "header_status", "markers", "is_week",
            "base_legend", "toolbar", "toolbar_legend", "week_legend", "phone_legend", "add_task", "cell_add_count", "day_add",
            "editor_dialog", "upgrade_entry", "upgrade_sheet", "continue_hrefs", "footnote", "playground_chip_hrefs", "legacy_copy"]
    lines = [f"# M6 read-back · Calendar · SHA `{sha}`", "", "| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(k, "")).replace("|", "\\|") for k in keys) + " |")
    (out / "readback.md").write_text("\n".join(lines) + "\n")
    print(f"{len(rows)} rows → {out}")


if __name__ == "__main__":
    main()
