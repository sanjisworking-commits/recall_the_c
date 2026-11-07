"""M4 read-back rows: what each account state is served on /dashboard (Today).

Renders Today through the app's own TestClient for guest, Free, Plus, Pro, Max
(legacy), paused, pending, expired and halted accounts (local fixtures identical
to the screen tests), in two phases per signed-in state — first run (no
progress) and after one real Learn → Done on Article 1(1) — and prints one row
per state and phase: greeting, subtext, date line, streak chip, access chip,
surface markers, first-run block, CTA labels and hrefs, hero mode and CTA, path
node count, progress strip, and every occurrence of superseded "3 Articles"
copy. Tiers without a visible difference get a read-back row, not a screenshot
(owner evidence policy, 2026-11-06).

Run from the repository root with the project venv:
    PYTHONPATH=.:src .venv/bin/python docs/design/proto-comparison-2026-10-19/m4/tools/readback_m4.py --out <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from constitution_memorizer.auth.fake_provider import FakeAuthProvider
from constitution_memorizer.auth.sessions import SESSION_COOKIE_NAME, InMemorySessionStore
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.web.app import create_app
from tests.quiz_helpers import complete_all_modes

ROOT = Path(__file__).resolve().parents[5]
UNITS = ROOT / "data" / "output" / "learning_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")
FIRST_UNIT = "article-1-clause-1"
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
LEGACY = ("3 Articles", "save 3", "pick any", "Unlock all", "Unlock every Article", "3 slots", "/login")


def _settings(tier_model: str) -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None, APP_ENV="test", MULTIUSER_ENABLED="true", AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true", SESSION_SECRET="test-secret", SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon", DATABASE_URL="", COOKIE_SECURE="false", PLAYGROUND_TIER_MODEL=tier_model,
    )


def _app(tmp: Path, tier_model: str):
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="a@example.com", display_name="Sanjay", avatar_url=None)
    return create_app(units_path=UNITS, db_path=tmp / "progress.db", multiuser=True,
                      multiuser_settings=_settings(tier_model), auth_provider=provider,
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


def _first(html: str, pattern: str) -> str:
    m = re.search(pattern, html, re.S)
    return _text(m.group(1)) if m else ""


def today_row(html: str) -> dict:
    header = _between(html, "<header", "</header>")
    greeting_block = _between(html, 'class="dash-greeting"', "</header>")
    firstrun = _between(html, 'data-today-mode="firstrun"', "</section>")
    signin_block = _between(firstrun, 'class="dash-firstrun-signin"', "</div>")
    plan_block = _between(firstrun, 'class="dash-firstrun-plan"', "</a>")
    hero = _between(html, 'class="dash-card dash-hero', "</article>")
    return {
        "header_status": _text(_between(header, 'class="account-menu-btn-status">', "</span>")),
        "markers": [m for m in ("data-signed-in-today", "data-plus-today", "data-halted-today", "data-expired-today") if m in html],
        "greeting": _first(greeting_block, r'class="display dash-hello">(.*?)</h1>'),
        "subtext": _first(greeting_block, r'class="dash-subtext">(.*?)</p>'),
        "date_line": _first(greeting_block, r'data-today-date>(.*?)</p>'),
        "streak_chip": "rc-streak" in greeting_block,
        "access_chip": _text(_between(greeting_block, 'class="dash-access-chip"', "</span>")),
        "first_run": 'data-today-mode="firstrun"' in html,
        "firstrun_title": _first(firstrun, r'class="dash-firstrun-title">(.*?)</p>'),
        "firstrun_cta": _first(firstrun, r'class="dash-firstrun-cta" href="[^"]*">(.*?)</a>'),
        "firstrun_cta_href": (re.search(r'class="dash-firstrun-cta" href="([^"]*)"', firstrun) or [None, ""])[1],
        "firstrun_note": _first(firstrun, r'class="dash-firstrun-note">(.*?)</p>'),
        "starter_rows": firstrun.count('class="dash-firstrun-item"'),
        "plan_tour_rows": firstrun.count('class="dash-firstrun-item is-compact"'),
        "signin_block": _text(signin_block),
        "signin_hrefs": re.findall(r'href="([^"]+)"', signin_block),
        "plan_block": _text(plan_block),
        "hero_mode": (re.search(r'data-today-mode="(revision|learning)"', html) or [None, ""])[1],
        "hero_title": _first(hero, r'class="dash-due-empty-title">(.*?)</p>') or _first(hero, r'class="dash-due-line">(.*?)</p>'),
        "hero_cta": _first(hero, r'<(?:a|button)[^>]*class="btn dash-btn-full"[^>]*>(.*?)</(?:a|button)>'),
        "hero_cta_href": (re.search(r'class="btn dash-btn-full" href="([^"]*)"', hero) or [None, ""])[1],
        "path_nodes": html.count("data-today-unit="),
        "playground_nodes": html.count('data-today-source="playground"'),
        "strip": 'class="dash-strip"' in html,
        "upcoming": 'class="dash-upcoming"' in html,
        "lapse_banner": 'class="lapse-banner"' in html,
        "legacy_copy": sorted({p for p in LEGACY if p in html}),
        "settings_links": html.count('href="/settings"'),
        "sha256": hashlib.sha256(html.encode()).hexdigest()[:16],
    }


def _row(client: TestClient, state: str, phase: str, model: str) -> dict:
    r = client.get("/dashboard", follow_redirects=False)
    row = {"state": state, "phase": phase, "tier_model": model, "status": r.status_code}
    if r.status_code != 200:
        row["location"] = r.headers.get("location", "")
        return row
    row.update(today_row(r.text))
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", default="monthly,choices")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for model in args.models.split(","):
        for state, spec in STATES.items():
            clear_settings_cache()
            with tempfile.TemporaryDirectory() as tmp:
                app = _app(Path(tmp), model)
                with TestClient(app) as client:
                    if spec is None:
                        rows.append(_row(client, state, "guest", model))
                        continue
                    _sign_in(client)
                    if spec:
                        _subscribe(client, spec)
                    client.app.state.engine.repo.upsert_profile(USER, display_name="Sanjay", avatar_url=None)
                    rows.append(_row(client, state, "first-run", model))
                    complete_all_modes(client, UNITS, FIRST_UNIT)
                    done = client.post(f"/learn/{FIRST_UNIT}/done", headers={"Accept": "application/json"})
                    rows.append({**_row(client, state, "after-one-article", model), "done_status": done.status_code})
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    (out / "readback.json").write_text(json.dumps({"sha": sha, "rows": rows}, indent=2, default=str))
    keys = ["state", "phase", "tier_model", "status", "header_status", "markers", "greeting", "subtext", "date_line",
            "streak_chip", "access_chip", "first_run", "firstrun_title", "firstrun_cta", "firstrun_cta_href", "firstrun_note",
            "starter_rows", "plan_tour_rows", "signin_block", "signin_hrefs", "plan_block", "hero_mode", "hero_title",
            "hero_cta", "hero_cta_href", "path_nodes", "playground_nodes", "strip", "upcoming", "lapse_banner", "legacy_copy"]
    lines = [f"# M4 read-back · /dashboard · SHA `{sha}`", "", "| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(k, "")).replace("|", "\\|") for k in keys) + " |")
    (out / "readback.md").write_text("\n".join(lines) + "\n")
    print(f"{len(rows)} rows → {out}")


if __name__ == "__main__":
    main()
