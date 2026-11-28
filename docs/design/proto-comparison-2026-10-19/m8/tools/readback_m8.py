"""M8-Ra read-back rows: what each subscription and device state is served.

For every state below, under both tier models, the app's own TestClient reads
the header label, the Playground home, `?stage=plans`, the Bare Act head of a
law in the roster and of a law outside it, both Add sheets, Manage laws,
Today, Calendar, Profile, Settings, the billing page and Devices, and records
per page: status / redirect, headings, the gate reason, every link or form
action that leads to the Playground, billing or Devices (with whether the link
is marked as a sheet opener), and a hash of the page body.

Each state is tagged with how the stored shape arises:

  P  production-reachable — the application's own code can leave an account in
     this stored shape
  S  synthetic fixture — a shape the application does not produce; kept
     because existing tests and captures pin it

Neither tag proves what the payment provider does: every state here is seeded
straight into a throwaway local database. No provider call is made.

    PYTHONPATH=.:src .venv/bin/python …/m8/tools/readback_m8.py --out <dir>
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
from constitution_memorizer.playground.learning.modes import PLAYGROUND_LEARN_MODES
from constitution_memorizer.playground.urls import add_path, roster_path, sections_path
from constitution_memorizer.web.app import create_app

ROOT = Path(__file__).resolve().parents[5]
UNITS = ROOT / "data" / "output" / "learning_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")
_TODAY = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
OPEN = (_TODAY - timedelta(days=20), _TODAY + timedelta(days=10))
ELAPSED = (_TODAY - timedelta(days=40), _TODAY - timedelta(days=10))
ENTIRE, SECTIONED, REMOVED, OUTSIDE = "ndps", "bns", "uapa", "pss"

# reach, seed (the active row the account is populated under), then (what the row becomes)
STATES: dict[str, dict] = {
    "free": {"reach": "P", "seed": None},
    "plus": {"reach": "P", "seed": {"tier": "plus"}},
    "max": {"reach": "P", "seed": {"tier": "max"}},
    "pending": {"reach": "P", "seed": {"tier": "plus"}, "then": {"status": "pending"}},
    "paused": {"reach": "P", "seed": {"tier": "plus"}, "then": {"status": "paused"}},
    "halted": {"reach": "P", "seed": {"tier": "plus"}, "then": {"status": "halted"}},
    "halted_elapsed": {"reach": "P", "seed": {"tier": "plus"}, "then": {"status": "halted", "period": ELAPSED}},
    # terminal status on a row that is still current: the shape the expired cohort tests pin
    "expired_fixture": {"reach": "S", "seed": {"tier": "plus"}, "then": {"status": "expired", "period": ELAPSED}},
    # the stored period is over, the provider row has not been reported as ended
    "ended_active": {"reach": "P", "seed": {"tier": "plus"}, "then": {"period": ELAPSED}},
    # what the service leaves after a terminal status: the row is no longer current
    "former_paid": {"reach": "P", "seed": {"tier": "plus"}, "then": {"status": "expired", "period": ELAPSED, "not_current": True}},
    # a checkout that was started and left: a `created` row, current, no paid period
    "abandoned": {"reach": "P", "seed": None, "then_new": {"tier": "plus", "status": "created"}},
    "cancel_at_end": {"reach": "P", "seed": {"tier": "plus"}, "then": {"cancel_at_period_end": True}},
    "scheduled_downgrade": {"reach": "P", "seed": {"tier": "pro"},
                            "then": {"provider_metadata": {"scheduled_tier": "plus", "schedule_change_at": "cycle_end"}}},
}
PAGES = [
    ("home", "/playground"),
    ("plans", "/playground?stage=plans"),
    ("head_in", f"/laws/{ENTIRE}"),
    ("head_out", f"/laws/{OUTSIDE}"),
    ("add_in", add_path(ENTIRE)),
    ("add_out", add_path(OUTSIDE)),
    ("roster", roster_path()),
    ("today", "/dashboard"),
    ("calendar", "/calendar"),
    ("profile", "/profile"),
    ("settings", "/settings"),
    ("billing", "/billing/subscriptions"),
    ("devices", "/profile/security/devices"),
]
LINK_RE = re.compile(r"^(/playground|/billing|/profile/security|/laws/[a-z0-9-]+/?$)")


def _settings(tier_model: str) -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None, APP_ENV="test", MULTIUSER_ENABLED="true", AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true", SESSION_SECRET="test-secret", SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon", DATABASE_URL="", COOKIE_SECURE="false", PLAYGROUND_TIER_MODEL=tier_model,
        ARTICLE_ENTITLEMENTS_ENABLED="false",
    )


def make_app(tmp: Path, tier_model: str):
    clear_settings_cache()
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="a@example.com", display_name="Sanjay", avatar_url=None)
    return create_app(units_path=UNITS, db_path=tmp / "progress.db", multiuser=True,
                      multiuser_settings=_settings(tier_model), auth_provider=provider,
                      session_store=InMemorySessionStore(), study_materials_dir=tmp / "study-materials")


def sign_in(client: TestClient) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = start.cookies.get("rtc_oauth_state")
    client.get(f"/auth/callback?code=fake-google-code&state={state}", follow_redirects=False)
    assert client.cookies.get(SESSION_COOKIE_NAME)


def csrf(client: TestClient) -> dict:
    token = client.cookies.get("rtc_csrf") or ""
    return {"csrf_token": token} if token else {}


def post(client: TestClient, path: str, data: dict) -> str:
    r = client.post(path, data=dict(csrf(client), **data), follow_redirects=False)
    return f"{r.status_code} {r.headers.get('location', '')[-34:]}".strip()


def populate(client: TestClient) -> dict:
    """Through the application's own save points only."""
    out = {}
    for law in (ENTIRE, REMOVED):
        out[f"add_{law}"] = post(client, add_path(law), {"confirm": "add", "scope": "entire"})
    out[f"scope_{SECTIONED}"] = post(client, add_path(SECTIONED), {"confirm": "add", "scope": "sections"})
    out[f"sections_{SECTIONED}"] = post(client, sections_path(SECTIONED), {"section": ["1", "2"]})
    out[f"remove_{REMOVED}"] = post(client, f"/playground/roster/{REMOVED}/remove", {})
    # One learned section whose first revision is due today, so Today and the Calendar have
    # a Playground item to show: written through the Playground repository's own completion
    # method, as the engine tests do. No entitlement or roster row is touched.
    try:
        if client.app.state.roster.is_law_active_this_period(USER, SECTIONED):
            repo = client.app.state.playground
            for mode in PLAYGROUND_LEARN_MODES:
                repo.complete_mode(USER, SECTIONED, f"{SECTIONED}:section:1", mode, source_version="v",
                                   source_hash="h", as_of=_TODAY.date() - timedelta(days=1))
            out["progress"] = "bns s1 learned yesterday"
        else:
            out["progress"] = "not a member"
    except Exception as exc:  # recorded, never hidden
        out["progress"] = f"error: {type(exc).__name__}: {exc}"[:80]
    return out


def apply_state(client: TestClient, name: str) -> dict:
    """Seed, populate, then turn the row into the state. Returns the save-point log."""
    spec = STATES[name]
    subs = client.app.state.subscriptions
    saves: dict = {}
    seed = spec.get("seed")
    if seed:
        subs.create_subscription_record(USER, tier=seed["tier"], status="active", billing_period_start=OPEN[0],
                                        billing_period_end=OPEN[1], is_current=True)
    saves = populate(client)
    then = spec.get("then")
    if then:
        row = subs.get_current_subscription(USER)
        kwargs = {}
        if "status" in then:
            kwargs["status"] = then["status"]
        if "period" in then:
            kwargs["billing_period_start"], kwargs["billing_period_end"] = then["period"]
        if "cancel_at_period_end" in then:
            kwargs["cancel_at_period_end"] = then["cancel_at_period_end"]
        if "provider_metadata" in then:
            kwargs["provider_metadata"] = then["provider_metadata"]
        subs.update_subscription_state(USER, row.id, **kwargs)
        if then.get("not_current"):
            subs.mark_not_current(USER, row.id)
    new = spec.get("then_new")
    if new:
        subs.create_subscription_record(USER, tier=new["tier"], status=new["status"], is_current=True)
    return saves


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def _main(html: str) -> str:
    if "<main" not in html:
        return html
    return html.split("<main", 1)[1].split("</main>", 1)[0]


def _dialog(html: str) -> str:
    m = re.search(r'<[a-z]+[^>]*class="[^"]*pg-sheet-panel[^"]*"[^>]*>(.*?)</(?:section|div|dialog|form)>\s*(?:</dialog>|<script|$)', html, flags=re.S)
    return m.group(1) if m else ""


def _stable(main: str) -> str:
    """The page body with everything that differs between two renders of the same
    state removed: request tokens, generated ids and clock times. Nothing of it is
    kept — only the hash of the result is recorded."""
    text = re.sub(r"\s+", " ", main)
    text = re.sub(r'="[A-Za-z0-9_-]{24,}"', '="T"', text)                                   # CSRF / study tokens
    text = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "ID", text)  # generated ids
    text = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b(?: ?(?:AM|PM|UTC|IST))?", "TIME", text)        # clock times
    return text


def page_row(html: str) -> dict:
    main = re.sub(r"<script\b.*?</script>", " ", _main(html), flags=re.S)
    links = []
    for tag, inner in re.findall(r"(<a\b[^>]*>)(.*?)</a>", main, flags=re.S):
        href = re.search(r'href="([^"]*)"', tag)
        if not href or not LINK_RE.match(href.group(1)):
            continue
        item = f'{_text(inner)[:34]} → {href.group(1)}' + (" [sheet-opener]" if "data-pg-sheet" in tag and "data-pg-sheet-close" not in tag else "")
        if item not in links:
            links.append(item)
    uuid = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    forms = sorted(set(re.sub(uuid, "ID", a) for a in re.findall(r'<form\b[^>]*action="(/(?:billing|playground|profile/security)[^"]*)"', main)))
    links = list(dict.fromkeys(re.sub(uuid, "ID", item) for item in links))
    status = re.search(r'class="account-menu-btn-status">([^<]*)<', html)
    add_title = re.search(r'id="pg-add(?:-scope)?-title"[^>]*>(.*?)</h1>', html, flags=re.S)
    return {
        "header": status.group(1).strip() if status else "",
        "title": _text(re.search(r"<title>(.*?)</title>", html, flags=re.S).group(1)) if "<title>" in html else "",
        "h1": [_text(x) for x in re.findall(r"<h1[^>]*>(.*?)</h1>", main, flags=re.S)][:3],
        "add_title": _text(add_title.group(1)) if add_title else "",
        "gate": sorted(set(re.findall(r'data-playground-gate="([^"]*)"', html))),
        "pg_kind": sorted(set(re.findall(r'data-pg-kind="([^"]*)"', html))),
        "links": links[:16],
        "forms": forms,
        # links in the page body that name a Playground law (a Today item, a Calendar chip)
        "law_item_links": sorted({h for h in re.findall(r'href="([^"]+)"', main) if re.match(r"/playground/laws/[a-z0-9-]+/sections/", h)})[:6],
        "mentions_bns": bool(re.search(r"\bBNS\b", _text(main))),
        "plan_form": (re.search(r'data-pg-plan-form="([^"]*)"', main) or [None, ""])[1],
        "device_lede": _text((re.search(r"data-device-lede>(.*?)</p>", main, flags=re.S) or [None, ""])[1]),
        "main_sha": hashlib.sha256(_stable(main).encode()).hexdigest()[:16],
    }


def read_pages(client: TestClient, base: dict, rows: list) -> None:
    for key, path in PAGES:
        r = client.get(path, follow_redirects=False)
        row = dict(base, page=key, path=path, status=r.status_code, location=r.headers.get("location", ""))
        if r.status_code == 200:
            row.update(page_row(r.text))
        rows.append(row)


def device_rows(tmp: Path, model: str, rows: list) -> None:
    """Device states on an active Plus account: a third browser at the limit; the
    current browser after its device was removed; the replacement limit."""
    app = make_app(tmp, model)
    app.state.subscriptions.create_subscription_record(USER, tier="plus", status="active", billing_period_start=OPEN[0],
                                                       billing_period_end=OPEN[1], is_current=True)
    a, b, c = TestClient(app), TestClient(app), TestClient(app)
    for cl in (a, b):
        sign_in(cl)
        cl.get("/playground")
    app.state.engine.repo.upsert_profile(USER, display_name="Sanjay", avatar_url=None)
    populate(a)
    sign_in(c)
    base = {"tier_model": model, "reach": "P"}
    for key, path in (("home", "/playground"), ("head_out", f"/laws/{OUTSIDE}"), ("add_out", add_path(OUTSIDE)),
                      ("today", "/dashboard"), ("calendar", "/calendar"), ("devices", "/profile/security/devices")):
        r = c.get(path, follow_redirects=False)
        row = dict(base, state="device_limit", page=key, path=path, status=r.status_code, location=r.headers.get("location", ""))
        if r.status_code == 200:
            row.update(page_row(r.text))
        rows.append(row)
    # browser b removes its own device: the page offers the current device through a
    # confirm step; the removal signs b out and b keeps its device cookie
    page = b.get("/profile/security/devices").text
    cur = re.search(r"/profile/security/devices\?confirm=([0-9a-f-]{8,})", page)
    log = {"current_device_offered": bool(cur)}
    if cur:
        target = cur.group(1)
        log["confirm_page"] = b.get(f"/profile/security/devices?confirm={target}", follow_redirects=False).status_code
        log["remove"] = post(b, f"/profile/security/devices/{target}/remove", {})
        log["signed_out"] = not b.cookies.get(SESSION_COOKIE_NAME)
        sign_in(b)
        for key, path in (("home", "/playground"), ("head_out", f"/laws/{OUTSIDE}"), ("add_out", add_path(OUTSIDE)),
                          ("today", "/dashboard"), ("calendar", "/calendar"), ("devices", "/profile/security/devices")):
            r = b.get(path, follow_redirects=False)
            row = dict(base, state="device_revoked", page=key, path=path, status=r.status_code, location=r.headers.get("location", ""))
            if r.status_code == 200:
                row.update(page_row(r.text))
            rows.append(row)
    rows.append(dict(base, state="device_log", page="-", path="-", status=0, location="", note=json.dumps(log, default=str)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", default="monthly,choices")
    ap.add_argument("--states", default=",".join(STATES))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    saves: list[dict] = []
    for model in args.models.split(","):
        for state in args.states.split(","):
            with tempfile.TemporaryDirectory() as tmp:
                with TestClient(make_app(Path(tmp), model)) as client:
                    sign_in(client)
                    client.app.state.engine.repo.upsert_profile(USER, display_name="Sanjay", avatar_url=None)
                    base = {"state": state, "tier_model": model, "reach": STATES[state]["reach"]}
                    saves.append(dict(base, **apply_state(client, state)))
                    read_pages(client, base, rows)
        with tempfile.TemporaryDirectory() as tmp:
            device_rows(Path(tmp), model, rows)
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    (out / "readback.json").write_text(json.dumps({"sha": sha, "captured_on": _TODAY.date().isoformat(), "saves": saves, "rows": rows}, indent=1, default=str))
    keys = ["state", "reach", "tier_model", "page", "status", "location", "header", "h1", "add_title", "gate", "pg_kind", "plan_form", "links", "forms", "device_lede", "main_sha"]
    lines = [f"# M8-Ra read-back · subscription and device states · SHA `{sha}`", "",
             "Reach: P = production-reachable stored shape, S = synthetic fixture. Every state is seeded locally; none proves provider behaviour.", "",
             "| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(k, "")).replace("|", "\\|") for k in keys) + " |")
    (out / "readback.md").write_text("\n".join(lines) + "\n")
    print(f"{len(rows)} rows → {out} (sha {sha})")


if __name__ == "__main__":
    main()
