"""M5 read-back rows: what each account state is served on the account family.

Renders /profile, /settings, /profile/security/devices, /playground and
/playground?stage=plans&tier=plus through the app's own TestClient for guest,
Free, Plus, Pro, Max (legacy), paused, pending, expired and halted accounts
(local fixtures identical to the screen tests) under both tier models, and
prints one row per state and route: status / redirect, header label, surface
markers, identity line, subscription card (title, chip, body, CTA label and
href), the Devices row, section order, the Settings identity line and pace
note, the Devices page title / count / empty copy, the gate stage, CTA labels,
price strings, Google and login hrefs, the plans-stage cards and the Continue
control's form target. Tiers without a visible difference get a read-back row,
not a screenshot (owner evidence policy, 2026-11-06).

Run from the repository root with the project venv:
    PYTHONPATH=.:src .venv/bin/python docs/design/proto-comparison-2026-10-19/m5/tools/readback_m5.py --out <dir>
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
ROUTES = {
    "profile": "/profile",
    "settings": "/settings",
    "devices": "/profile/security/devices",
    "gate": "/playground",
    "plans": "/playground?stage=plans&tier=plus",
}
LEGACY = ("3 Articles", "Free Articles", "pick any", "Unlock every Article", "Recall active", "from ₹", "/login", "/pricing")


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


def _common(html: str) -> dict:
    header = _between(html, "<header", "</header>")
    main = _between(html, "<main", "</main>")
    return {
        "header_status": _text(_between(header, 'class="account-menu-btn-status">', "</span>")),
        "google_hrefs": sorted(set(re.findall(r'href="(/auth/google/start[^"]*)"', main))),
        "login_hrefs": sorted(set(re.findall(r'href="(/login[^"]*)"', main))),
        "legacy_copy": sorted({p for p in LEGACY if p in main}),
        "sha256": hashlib.sha256(html.encode()).hexdigest()[:16],
    }


def profile_row(html: str) -> dict:
    main = _between(html, "<main", "</main>")
    card = _between(main, 'class="pg-sub-card', "</article>")
    row = _common(html)
    row.update({
        "markers": re.findall(r'data-(?:signed-in-profile|plus-profile|halted-profile|expired-profile|guest-profile-desktop|phone-profile)(?:="[^"]*")?', main),
        "identity_meta": _first(main, r'class="profile-name">[^<]*</h2>\s*<p class="muted">(.*?)</p>'),
        "card_title": _first(card, r"<h2>(.*?)</h2>"),
        "card_chip": _first(card, r'class="pg-sub-chip"[^>]*>(.*?)</span>'),
        "card_body": _first(card, r'class="pg-lede">(.*?)</p>'),
        "card_cta": _first(card, r'class="pg-btn[^"]*" href="[^"]*">(.*?)</a>'),
        "card_cta_href": (re.search(r'class="pg-btn[^"]*" href="([^"]*)"', card) or [None, ""])[1],
        "devices_row": _first(main, r'href="/profile/security/devices">Devices<span class="pg-account-meta">(.*?)</span>'),
        "section_order": [t for t in re.findall(r"<h2[^>]*>([^<]+)</h2>", main)][:8],
        "report_control": "button" if re.search(r"<button[^>]*data-report-open", main) else ("div" if re.search(r"<div[^>]*data-report-open", main) else ("a" if "data-report-open" in main else "none")),
    })
    return row


def settings_row(html: str) -> dict:
    main = _between(html, "<main", "</main>")
    row = _common(html)
    note = _between(main, 'class="settings-note settings-plan-locked"', "</p>")
    row.update({
        "markers": re.findall(r'data-(?:phone-settings|signed-in-settings|plus-settings|halted-settings|expired-settings)(?:="[^"]*")?', main),
        "identity_name": _first(main, r'class="settings-account-name">(.*?)</span>'),
        "identity_status": _first(main, r'class="settings-account-status">(.*?)</span>'),
        "pace_note": _text(note),
        "pace_note_href": (re.search(r'href="([^"]*)"', note) or [None, ""])[1],
        "auto_plan_controls_enabled": 'name="daily_target" value="5" disabled' not in main and "segmented-input" in main,
        "study_card_guest": "appear once you sign in" in main,
        "csrf_in_plan_form": bool(re.search(r'action="/settings/learning-plan"[^>]*>.*?csrf_token', main, re.S)),
    })
    return row


def devices_row(html: str) -> dict:
    main = _between(html, "<main", "</main>")
    row = _common(html)
    row.update({
        "eyebrow": _first(main, r'class="eyebrow">(.*?)</p>'),
        "title": _first(main, r'<h1[^>]*>(.*?)</h1>'),
        "count": _first(main, r"data-device-count>(.*?)</p>"),
        "empty_copy": _first(main, r'class="muted">(No active devices.*?)</p>'),
        "remove_forms": main.count('/remove"'),
    })
    return row


def gate_row(html: str) -> dict:
    main = _between(html, "<main", "</main>")
    row = _common(html)
    row.update({
        "markers": re.findall(r'data-(?:guest-pg-intro|signed-in-pg-gate|pg-gate-stage="[^"]*"|playground-gate="[^"]*")', main),
        "title": _first(main, r'<h1[^>]*>(.*?)</h1>'),
        "cta_labels": [_text(t) for t in re.findall(r'class="pg-btn[^"]*"[^>]*>(.*?)</a>', main)][:4],
        "guest_actions": [_text(t) for t in re.findall(r'class="guest-pg-signin"[^>]*>(.*?)</a>', main)],
        "prices": sorted(set(re.findall(r"₹[\d,]+", main))),
        "from_price_note": _first(main, r'class="pg-note">(Monthly\..*?)</p>'),
        "plan_cards": re.findall(r'data-tier="([a-z]+)"', main),
        "plan_card_elements": re.findall(r'<(a|article|input)[^>]*class="pg-plan-card[^"]*"', main)[:4],
        "current_plan": re.findall(r'data-pg-plan-current', main) != [],
        "continue_label": _first(main, r'data-pg-plan-continue[^>]*>(.*?)</button>'),
        "continue_form_action": (re.search(r'<form[^>]*action="([^"]*)"[^>]*>(?:(?!</form>).)*data-pg-plan-continue', main, re.S) or [None, ""])[1],
    })
    return row


ROW_FN = {"profile": profile_row, "settings": settings_row, "devices": devices_row, "gate": gate_row, "plans": gate_row}


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
                with TestClient(_app(Path(tmp), model)) as client:
                    if spec is not None:
                        _sign_in(client)
                        if spec:
                            _subscribe(client, spec)
                        client.app.state.engine.repo.upsert_profile(USER, display_name="Sanjay", avatar_url=None)
                    for key, path in ROUTES.items():
                        r = client.get(path, follow_redirects=False)
                        row = {"state": state, "route": key, "tier_model": model, "status": r.status_code,
                               "location": r.headers.get("location", "")}
                        if r.status_code == 200:
                            row.update(ROW_FN[key](r.text))
                        rows.append(row)
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    (out / "readback.json").write_text(json.dumps({"sha": sha, "rows": rows}, indent=2, default=str))
    lines = [f"# M5 read-back · account family · SHA `{sha}`", ""]
    for key in ROUTES:
        sub = [r for r in rows if r["route"] == key]
        keys = [k for k in sub[0].keys() if k not in ("route", "sha256")] if sub else []
        for r in sub:
            for k in r:
                if k not in keys and k not in ("route", "sha256"):
                    keys.append(k)
        lines += [f"## {key} (`{ROUTES[key]}`)", "", "| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
        for r in sub:
            lines.append("| " + " | ".join(str(r.get(k, "")).replace("|", "\\|") for k in keys) + " |")
        lines.append("")
    (out / "readback.md").write_text("\n".join(lines))
    print(f"{len(rows)} rows → {out}")


if __name__ == "__main__":
    main()
