"""M7 read-back rows: what each account state is served on the Playground flows.

Renders the Playground home (empty, then populated), Manage laws, the roster
Add confirm, Remove, the rollover page, Act progress, the section picker, one
Learn mode, the learned / mastered pages through the app's own TestClient for
guest, Free, Plus, Pro, Max (legacy), paused, pending, expired and halted
accounts under both tier models, and prints one row per state, model and
route: status / redirect, headings, surface markers, capacity attributes,
every month-model phrase still printed, links to the rollover route, law-card
memberships.

Populated state: reached through the application's own save points only
(POST add with scope=entire, POST sections, POST remove) on a throwaway
database. No payment, grant or entitlement edit beyond the fixture
subscription row the screen tests use.

Run from the repository root with the project venv:
    PYTHONPATH=.:src .venv/bin/python docs/design/proto-comparison-2026-10-19/m7/tools/readback_m7.py --out <dir>
"""
from __future__ import annotations

import argparse
import calendar
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
from constitution_memorizer.playground.learning.modes import PLAYGROUND_LEARN_MODES
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.playground.urls import add_path, law_path, roster_next_path, roster_path, sections_path
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
_M = _TODAY.month
MONTHS = "|".join(calendar.month_name[((_M - 1 + d) % 12) + 1] for d in (-1, 0, 1))
MONTH_RE = re.compile(
    rf"((?i:this month|next month|each month|last month|Playground month|your month|monthly Playground|law spaces?)|\b(?:{MONTHS})\b)"
)
ENTIRE, SECTIONED, REMOVED, CANDIDATE = "ndps", "bns", "uapa", "pss"


def _settings(tier_model: str) -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None, APP_ENV="test", MULTIUSER_ENABLED="true", AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true", SESSION_SECRET="test-secret", SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon", DATABASE_URL="", COOKIE_SECURE="false", PLAYGROUND_TIER_MODEL=tier_model,
        ARTICLE_ENTITLEMENTS_ENABLED="false",
    )


def _app(tmp: Path, tier_model: str):
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="a@example.com", display_name="Sanjay", avatar_url=None)
    return create_app(units_path=UNITS, db_path=tmp / "progress.db", multiuser=True,
                      multiuser_settings=_settings(tier_model), auth_provider=provider,
                      session_store=InMemorySessionStore(), study_materials_dir=tmp / "study-materials")


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


def _csrf(client: TestClient) -> dict:
    token = client.cookies.get("rtc_csrf") or ""
    return {"csrf_token": token} if token else {}


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def _main(html: str) -> str:
    if "<main" not in html:
        return html
    return html.split("<main", 1)[1].split("</main>", 1)[0]


def page_row(html: str) -> dict:
    main = re.sub(r"<script\b.*?</script>", " ", _main(html), flags=re.S)
    text = _text(main)
    hits = []
    for m in MONTH_RE.finditer(text):
        ctx = text[max(0, m.start() - 28): m.end() + 28].strip()
        if ctx not in hits:
            hits.append(ctx)
    cards = re.findall(r'data-law-id="([^"]+)"[^>]*data-membership="([^"]*)"', main)
    return {
        "h1": [_text(x) for x in re.findall(r"<h1[^>]*>(.*?)</h1>", main, flags=re.S)],
        "h2": [_text(x) for x in re.findall(r"<h2[^>]*>(.*?)</h2>", main, flags=re.S)],
        "markers": sorted(set(re.findall(
            r'data-(?:plus|paid|expired|halted)-(?:playground(?:-phone)?|pg-[a-z]+)(?:="[^"]*")?', main))),
        "gate": sorted(set(re.findall(r'data-playground-gate="([^"]*)"', html))),
        "roster_used_limit": sorted(set(re.findall(r'data-roster-used="([^"]*)"[^>]*data-roster-limit="([^"]*)"', main))),
        "month_copy_count": len(hits),
        "month_copy": hits[:14],
        "rollover_links": main.count(roster_next_path()),
        "law_cards": [f"{law}:{membership}" for law, membership in cards][:12],
        "pg_kind": sorted(set(re.findall(r'data-pg-kind="([^"]*)"', html))),
        "sha256": hashlib.sha256(html.encode()).hexdigest()[:16],
    }


def _get(client: TestClient, rows: list, base: dict, key: str, path: str) -> str:
    r = client.get(path, follow_redirects=False)
    row = dict(base, route=key, path=path, status=r.status_code, location=r.headers.get("location", ""))
    if r.status_code == 200:
        row.update(page_row(r.text))
    rows.append(row)
    return r.text if r.status_code == 200 else ""


def _post(client: TestClient, path: str, data: dict) -> str:
    r = client.post(path, data=dict(_csrf(client), **data), follow_redirects=False)
    return f"{r.status_code} {r.headers.get('location', '')[-34:]}".strip()


def _populate(client: TestClient) -> dict:
    """Add through the save points; each cell is the response status and redirect target,
    so a refusal (a gate page, or a redirect away from the Playground) is visible."""
    out = {}
    for law in (ENTIRE, REMOVED):
        out[f"add_{law}"] = _post(client, add_path(law), {"confirm": "add", "scope": "entire"})
    out[f"scope_{SECTIONED}"] = _post(client, add_path(SECTIONED), {"confirm": "add", "scope": "sections"})
    out[f"sections_{SECTIONED}"] = _post(client, sections_path(SECTIONED), {"section": ["1", "2"]})
    out[f"remove_{REMOVED}"] = _post(client, f"/playground/roster/{REMOVED}/remove", {})
    # Learning progress for the completion pages: section 1 learned (six modes), section 2
    # taken up the whole ladder. Written through the Playground repository's own
    # completion methods, as the engine tests do; no entitlement or roster row is touched.
    repo = client.app.state.playground
    today = _TODAY.date()
    try:
        if client.app.state.roster.is_law_active_this_period(USER, SECTIONED):
            for mode in PLAYGROUND_LEARN_MODES:
                for n in ("1", "2"):
                    repo.complete_mode(USER, SECTIONED, f"{SECTIONED}:section:{n}", mode,
                                       source_version="v", source_hash="h", as_of=today - timedelta(days=130))
            cursor = today - timedelta(days=129)
            for rung in (1, 3, 7, 15, 30, 60):
                for mode in PLAYGROUND_LEARN_MODES:
                    repo.complete_revision_mode_and_advance_if_ready(
                        USER, SECTIONED, f"{SECTIONED}:section:2", mode, source_version="v", source_hash="h",
                        as_of=cursor, claimed_rung=rung)
                cursor += timedelta(days={1: 3, 3: 7, 7: 15, 15: 30, 30: 60, 60: 0}[rung])
            out["progress"] = "s1 learned, s2 ladder"
        else:
            out["progress"] = "not a member"
    except Exception as exc:  # recorded, never hidden
        out["progress"] = f"error: {type(exc).__name__}: {exc}"[:80]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", default="monthly,choices")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    saves: list[dict] = []
    for model in args.models.split(","):
        for state, spec in STATES.items():
            clear_settings_cache()
            with tempfile.TemporaryDirectory() as tmp:
                with TestClient(_app(Path(tmp), model)) as client:
                    base = {"state": state, "tier_model": model}
                    if spec is not None:
                        _sign_in(client)
                        if spec:
                            _subscribe(client, spec)
                        client.app.state.engine.repo.upsert_profile(USER, display_name="Sanjay", avatar_url=None)
                    _get(client, rows, base, "home_empty", "/playground")
                    if spec is None:
                        continue
                    saves.append(dict(base, **_populate(client)))
                    _get(client, rows, base, "home", "/playground")
                    _get(client, rows, base, "roster", roster_path())
                    _get(client, rows, base, "roster_add", roster_path() + f"?add={CANDIDATE}")
                    _get(client, rows, base, "roster_readd", roster_path() + f"?add={REMOVED}")
                    _get(client, rows, base, "remove", f"/playground/roster/{ENTIRE}/remove")
                    _get(client, rows, base, "rollover", roster_next_path())
                    _get(client, rows, base, "law", law_path(ENTIRE))
                    picker = _get(client, rows, base, "sections", sections_path(SECTIONED))
                    numbers = re.findall(r'name="section"[^>]*value="([^"]+)"', picker) or re.findall(
                        r'value="([^"]+)"[^>]*name="section"', picker)
                    n = "1" if "1" in numbers or not numbers else numbers[0]
                    stem = f"/playground/laws/{SECTIONED}/sections"
                    _get(client, rows, base, "learn_read", f"{stem}/{n}/learn/read")
                    _get(client, rows, base, "learned", f"{stem}/1/learned")
                    _get(client, rows, base, "mastered", f"{stem}/2/mastered")
                    _get(client, rows, base, "act_mastered", f"/playground/laws/{SECTIONED}/mastered")
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    (out / "readback.json").write_text(json.dumps({"sha": sha, "saves": saves, "rows": rows}, indent=2, default=str))
    keys = ["state", "tier_model", "route", "status", "location", "h1", "h2", "markers", "gate", "roster_used_limit",
            "month_copy_count", "month_copy", "rollover_links", "law_cards", "pg_kind"]
    lines = [f"# M7 read-back · Playground flows · SHA `{sha}`", "",
             "Save-point responses used to reach the populated state (status and redirect target; a redirect to the roster, the picker or the law page is a save, anything else is a refusal):", "",
             "| state | tier_model | " + " | ".join(k for k in (saves[0] if saves else {}) if k not in ("state", "tier_model")) + " |",
             "|---|---|" + "---|" * max(0, len(saves[0]) - 2 if saves else 0)]
    for s in saves:
        lines.append("| " + " | ".join(str(v) for v in s.values()) + " |")
    lines += ["", "| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(k, "")).replace("|", "\\|") for k in keys) + " |")
    (out / "readback.md").write_text("\n".join(lines) + "\n")
    print(f"{len(rows)} rows, {len(saves)} populated accounts → {out}")


if __name__ == "__main__":
    main()
