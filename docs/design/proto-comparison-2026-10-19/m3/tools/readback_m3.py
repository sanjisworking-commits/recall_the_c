"""M3 read-back rows: what each account state is served on /browse and /laws.

Renders both pages through the app's own TestClient for guest, Free, Plus,
Pro, Max (legacy), paused, pending, expired and halted accounts (local
fixtures identical to the screen tests) and prints one row per state: status
chain, header status text, banner slot (guest strip / Free summary / none),
per-card Playground CTA count, chip labels, card meta strings, Part toggles.
Tiers without a visible difference get a read-back row, not a screenshot
(owner evidence policy, 2026-11-06).

Run from the repository root with the project venv:
    PYTHONPATH=src .venv/bin/python docs/design/proto-comparison-2026-10-19/m3/tools/readback_m3.py --out <dir>
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

ROOT = Path(__file__).resolve().parents[5]
UNITS = ROOT / "data" / "output" / "learning_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")
# A live window around today (the screen tests pin dates together with a frozen
# clock; this tool runs against the real clock), and a window that ended months ago.
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


def browse_row(html: str) -> dict:
    header = _between(html, "<header", "</header>")
    banner = "guest-strip" if "data-guest-strip" in html else ("free-summary" if "data-signed-in-browse-strip" in html else "none")
    banner_text = ""
    if banner == "guest-strip":
        banner_text = _text(_between(html, "data-guest-strip", "</div>"))
    elif banner == "free-summary":
        banner_text = _text(_between(html, "data-signed-in-browse-strip", "</div>"))
    return {
        "header_status": _text(_between(header, 'class="account-menu-btn-status">', "</span>")),
        "markers": [m for m in ("data-plus-browse", "data-expired-browse", "data-halted-browse") if m in html],
        "banner": banner,
        "banner_text": banner_text,
        "banner_links": re.findall(r'href="([^"]+)"', _between(html, "data-guest-strip", "</div>") + _between(html, "data-signed-in-browse-strip", "</div>")),
        "part_toggles": html.count("data-browse-part-toggle"),
        "part_rail": "browse-part-rail" in html,
        "marks_sheet": 'id="marks-sheet"' in html or "data-sheet-open" in html,
        "schedule_cards": html.count('class="browse-schedule-card"'),
        "article_cards": html.count('class="browse-article-card'),
    }


def laws_row(html: str) -> dict:
    header = _between(html, "<header", "</header>")
    cards = re.findall(r'data-law-id="([^"]+)"', html)
    metas = re.findall(r'<span class="laws-index-meta">([^<]*)</span>', html)
    chips = re.findall(r'data-laws-chip="[^"]*"[^>]*>([^<]*)</button>', html) + re.findall(r'data-laws-status="repealed"[^>]*>([^<]*)</button>', html)
    return {
        "header_status": _text(_between(header, 'class="account-menu-btn-status">', "</span>")),
        "markers": [m for m in ("data-guest-laws-desktop", "data-signed-in-laws-desktop", "data-plus-laws", "data-expired-laws", "data-halted-laws", "data-laws-phone") if m in html],
        "sections": html.count("data-laws-index"),
        "cards": len(cards),
        "cta_buttons": html.count("pg-btn"),
        "cta_wrappers": html.count("LawPlaygroundCta"),
        "status_badges": re.findall(r'class="LawStatusBadge" data-status="([^"]+)"', html),
        "badge_labels": [_text(x) for x in re.findall(r'class="LawStatusBadge[^"]*"[^>]*>(.*?)</span>', html, re.S)],
        "search_visible": 'data-laws-search hidden' not in html and "data-laws-search" in html,
        "search_toggle": "data-laws-search-toggle" in html,
        "chips": chips,
        "metas": metas[:8],
        "price": "₹" in html,
        "phrases": [p for p in ("Subscribe to use Playground", "Unlock Playground", "Add to Playground", "Create an account") if p in html],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--tier-models", default="monthly,choices")
    ap.add_argument("--sha", default="")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    sha = args.sha or subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    rows = []
    for tier_model in args.tier_models.split(","):
        for state, spec in STATES.items():
            clear_settings_cache()
            with tempfile.TemporaryDirectory() as tmp:
                client = TestClient(_app(Path(tmp), tier_model))
                if spec is not None:
                    _sign_in(client)
                    if spec:
                        _subscribe(client, spec)
                for route in ("/browse", "/laws"):
                    resp = client.get(route, follow_redirects=False)
                    chain = [resp.status_code]
                    html = resp.text
                    row = {"sha": sha, "tier_model": tier_model, "state": state, "route": route, "status_chain": chain,
                           "sha256": hashlib.sha256(html.encode()).hexdigest()[:16]}
                    row.update(browse_row(html) if route == "/browse" else laws_row(html))
                    rows.append(row)
    (out / "readback.json").write_text(json.dumps({"sha": sha, "rows": rows}, indent=1, ensure_ascii=False))
    lines = [f"# Read-back rows @ `{sha}`\n", "| model | state | route | status | header | banner / CTA | notable |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["route"] == "/browse":
            mid = f"{r['banner']}: {r['banner_text'][:70]}"; note = f"toggles={r['part_toggles']} rail={r['part_rail']} sheet={r['marks_sheet']} sched={r['schedule_cards']}"
        else:
            mid = f"pg-btn={r['cta_buttons']} badges={r['status_badges']} {r['badge_labels']}"; note = f"search_visible={r['search_visible']} toggle={r['search_toggle']} chips={r['chips']} price={r['price']} phrases={r['phrases']}"
        lines.append(f"| {r['tier_model']} | {r['state']} | {r['route']} | {r['status_chain']} | {r['header_status']} | {mid} | {note} |")
    (out / "readback.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
