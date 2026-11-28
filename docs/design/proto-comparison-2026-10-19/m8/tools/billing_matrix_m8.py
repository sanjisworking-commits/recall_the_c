"""M8-Ra — billing state / action matrix (for review; nothing is built from it).

For each stored subscription shape it records, by execution against a
throwaway local database:

  * the entitlement the account resolves to (block reason, subscribed, can open);
  * what the billing page (`/billing/subscriptions`) shows: its heading and the
    forms and links it offers (create / change / cancel / checkout);
  * what each billing route does when it is requested directly — Subscribe to
    Plus, Subscribe to Pro, Change to Pro, Change to Plus, Cancel — as the
    route's redirect, the calls it made to the provider client, and the
    subscription rows before and after.

THE PROVIDER IS MOCKED. `MockClient` answers every call with a subscription
that mirrors what the route asked for (a fetch returns the stored status). The
matrix therefore shows what the application decides and asks for; it says
nothing about what Razorpay would answer, whether a mandate is live, or when a
change takes effect. No network call is made.

    PYTHONPATH=.:src .venv/bin/python …/m8/tools/billing_matrix_m8.py --out <dir>
"""
from __future__ import annotations

import argparse
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
from constitution_memorizer.entitlements.dependencies import get_entitlement_snapshot  # noqa: F401
from constitution_memorizer.multiuser.settings import MultiUserSettings, clear_settings_cache
from constitution_memorizer.subscriptions.config import SubscriptionPlanIds
from constitution_memorizer.subscriptions.razorpay import ProviderSubscription
from constitution_memorizer.subscriptions.service import SubscriptionService
from constitution_memorizer.web.app import create_app

ROOT = Path(__file__).resolve().parents[5]
UNITS = ROOT / "data" / "output" / "learning_units.json"
USER = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
OPEN = (NOW - timedelta(days=20), NOW + timedelta(days=10))
ELAPSED = (NOW - timedelta(days=40), NOW - timedelta(days=10))
PLAN_IDS = SubscriptionPlanIds(plus="plan_plus", pro="plan_pro", max="plan_max")
SUB_ID = "sub_m8_local"

# name, reach, row kwargs (None = no row), not_current
SHAPES: list[tuple[str, str, dict | None, bool]] = [
    ("no subscription row", "P", None, False),
    ("created, reservation (no provider id)", "P", {"tier": "plus", "status": "created", "provider": False}, False),
    ("created, checkout open", "P", {"tier": "plus", "status": "created"}, False),
    ("authenticated", "P", {"tier": "plus", "status": "authenticated", "period": OPEN}, False),
    ("active, period open", "P", {"tier": "plus", "status": "active", "period": OPEN}, False),
    ("active, cancel at period end", "P", {"tier": "plus", "status": "active", "period": OPEN, "cancel": True}, False),
    ("active Pro, downgrade to Plus scheduled", "P", {"tier": "pro", "status": "active", "period": OPEN,
                                                    "meta": {"scheduled_tier": "plus", "schedule_change_at": "cycle_end"}}, False),
    ("active, stored period elapsed", "P", {"tier": "plus", "status": "active", "period": ELAPSED}, False),
    ("pending, period open", "P", {"tier": "plus", "status": "pending", "period": OPEN}, False),
    ("pending, stored period elapsed", "P", {"tier": "plus", "status": "pending", "period": ELAPSED}, False),
    ("halted, period open", "P", {"tier": "plus", "status": "halted", "period": OPEN}, False),
    ("halted, stored period elapsed", "P", {"tier": "plus", "status": "halted", "period": ELAPSED}, False),
    ("paused, period open", "P", {"tier": "plus", "status": "paused", "period": OPEN}, False),
    ("paused, stored period elapsed", "P", {"tier": "plus", "status": "paused", "period": ELAPSED}, False),
    ("cancelled, row still current (fixture)", "S", {"tier": "plus", "status": "cancelled", "period": ELAPSED}, False),
    ("expired, row still current (fixture)", "S", {"tier": "plus", "status": "expired", "period": ELAPSED}, False),
    ("expired, row not current (as the service leaves it)", "P", {"tier": "plus", "status": "expired", "period": ELAPSED}, True),
    ("legacy Max, active", "P", {"tier": "max", "status": "active", "period": OPEN}, False),
]
ACTIONS = [
    ("subscribe_plus", "/billing/subscriptions/create", {"tier": "plus"}),
    ("subscribe_pro", "/billing/subscriptions/create", {"tier": "pro"}),
    ("change_to_pro", "/billing/subscriptions/change", {"tier": "pro"}),
    ("change_to_plus", "/billing/subscriptions/change", {"tier": "plus"}),
    ("cancel", "/billing/subscriptions/cancel", {}),
]


class MockClient:
    """Stands in for the Razorpay client. Records every call. Not the provider."""

    def __init__(self, stored_status: str = "active", stored_plan: str = "plan_plus") -> None:
        self.calls: list[str] = []
        self.stored_status = stored_status
        self.stored_plan = stored_plan

    @staticmethod
    def _sub(sub_id: str, plan_id: str, status: str) -> ProviderSubscription:
        return ProviderSubscription(id=sub_id, plan_id=plan_id, status=status, current_start=int(OPEN[0].timestamp()),
                                    current_end=int(OPEN[1].timestamp()), customer_id="cust_mock", short_url=None,
                                    has_scheduled_changes=False, raw={"id": sub_id, "plan_id": plan_id, "status": status})

    def verify_checkout_signature(self, **_: str) -> bool:
        self.calls.append("verify_checkout_signature")
        return False

    def create_subscription(self, request) -> ProviderSubscription:
        self.calls.append(f"create_subscription(plan={request.plan_id})")
        return self._sub("sub_m8_new", request.plan_id, "created")

    def fetch_subscription(self, subscription_id: str) -> ProviderSubscription:
        self.calls.append(f"fetch_subscription({subscription_id}) → mock returns stored status '{self.stored_status}'")
        return self._sub(subscription_id, self.stored_plan, self.stored_status)

    def cancel_subscription(self, subscription_id: str, *, cancel_at_cycle_end: bool = True) -> ProviderSubscription:
        self.calls.append(f"cancel_subscription({subscription_id}, cancel_at_cycle_end={cancel_at_cycle_end})")
        return self._sub(subscription_id, self.stored_plan, "active")

    def update_subscription_plan(self, subscription_id: str, *, plan_id: str, schedule_change_at: str) -> ProviderSubscription:
        self.calls.append(f"update_subscription_plan({subscription_id}, plan={plan_id}, schedule_change_at={schedule_change_at})")
        return self._sub(subscription_id, plan_id, "active")


def _settings(tier_model: str) -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None, APP_ENV="test", MULTIUSER_ENABLED="true", AUTH_GOOGLE_ENABLED="true",
        AUTH_PHONE_ENABLED="true", SESSION_SECRET="test-secret", SUPABASE_URL="http://example.invalid",
        SUPABASE_ANON_KEY="anon", DATABASE_URL="", COOKIE_SECURE="false", PLAYGROUND_TIER_MODEL=tier_model,
        ARTICLE_ENTITLEMENTS_ENABLED="false",
    )


def build(tmp: Path, tier_model: str, row: dict | None, not_current: bool) -> tuple[TestClient, MockClient]:
    clear_settings_cache()
    provider = FakeAuthProvider()
    provider.seed_google_user(user_id=USER, email="a@example.com", display_name="Sanjay", avatar_url=None)
    app = create_app(units_path=UNITS, db_path=tmp / "progress.db", multiuser=True, multiuser_settings=_settings(tier_model),
                     auth_provider=provider, session_store=InMemorySessionStore(), study_materials_dir=tmp / "study-materials")
    mock = MockClient(stored_status=(row or {}).get("status", "active"), stored_plan=f"plan_{(row or {}).get('tier', 'plus')}")
    app.state.subscription_service = SubscriptionService(app.state.subscriptions, mock, PLAN_IDS, public_key_id="rzp_test_local_mock")
    client = TestClient(app)
    start = client.get("/auth/google/start", follow_redirects=False)
    client.get(f"/auth/callback?code=fake-google-code&state={start.cookies.get('rtc_oauth_state')}", follow_redirects=False)
    assert client.cookies.get(SESSION_COOKIE_NAME)
    app.state.engine.repo.upsert_profile(USER, display_name="Sanjay", avatar_url=None)
    if row is not None:
        period = row.get("period", (None, None))
        stored = app.state.subscriptions.create_subscription_record(
            USER, tier=row["tier"], status=row["status"], billing_period_start=period[0], billing_period_end=period[1],
            cancel_at_period_end=bool(row.get("cancel")), is_current=True,
            provider_subscription_id=SUB_ID if row.get("provider", True) else None,
            provider_plan_id=f"plan_{row['tier']}", provider_metadata=row.get("meta") or {})
        if not_current:
            app.state.subscriptions.mark_not_current(USER, stored.id)
    return client, mock


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def page(client: TestClient) -> dict:
    r = client.get("/billing/subscriptions")
    main = r.text.split("<main", 1)[1].split("</main>", 1)[0] if "<main" in r.text else r.text
    offers = []
    for form in re.findall(r"<form\b.*?</form>", main, flags=re.S):
        action = re.search(r'action="([^"]*)"', form)
        tiers = re.findall(r'name="tier"[^>]*value="([^"]*)"', form) + re.findall(r'value="([^"]*)"[^>]*name="tier"', form)
        button = re.search(r"<button[^>]*>(.*?)</button>", form, flags=re.S)
        offers.append(f'{_text(button.group(1)) if button else "?"} → POST {action.group(1) if action else "?"}' + (f' [{", ".join(sorted(set(tiers)))}]' if tiers else ""))
    links = sorted({f"{_text(inner)} → {href}" for href, inner in re.findall(r'<a\b[^>]*href="(/billing/[^"]*)"[^>]*>(.*?)</a>', main, flags=re.S)})
    status = re.search(r'class="account-menu-btn-status">([^<]*)<', r.text)
    return {"status": r.status_code, "header": status.group(1).strip() if status else "",
            "h1": [_text(x) for x in re.findall(r"<h1[^>]*>(.*?)</h1>", main, flags=re.S)],
            "offers": offers, "billing_links": links,
            "notes": [_text(x) for x in re.findall(r'<p class="(?:purchase-note|plus-sub-lede)[^"]*"[^>]*>(.*?)</p>', main, flags=re.S)][:3]}


def rows(client: TestClient) -> list[str]:
    out = []
    for r in client.app.state.subscription_service.list_history(USER):
        meta = dict(r.provider_metadata or {})
        out.append(f"{r.tier}/{r.status}/{'current' if r.is_current else 'not-current'}"
                   + ("/cancel-at-end" if r.cancel_at_period_end else "")
                   + (f"/scheduled→{meta['scheduled_tier']}" if meta.get("scheduled_tier") else "")
                   + ("/reservation" if meta.get("reservation") else ""))
    return sorted(out)


def snapshot(client: TestClient) -> dict:
    client.get("/profile")
    svc = client.app.state.entitlement_service
    snap = svc.resolve(USER) if hasattr(svc, "resolve") else None
    if snap is None:
        return {}
    return {"block_reason": snap.playground_block_reason, "is_subscribed": snap.is_subscribed,
            "can_open_playground": snap.can_open_playground, "can_add_new_law": snap.can_consume_new_playground_law}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--models", default="monthly,choices")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    table = []
    for model in args.models.split(","):
        for name, reach, row, not_current in SHAPES:
            with tempfile.TemporaryDirectory() as tmp:
                client, _ = build(Path(tmp), model, row, not_current)
                entry = {"tier_model": model, "shape": name, "reach": reach, "entitlement": snapshot(client),
                         "billing_page": page(client), "rows_before": rows(client), "actions": {}}
            for key, path, data in ACTIONS:
                with tempfile.TemporaryDirectory() as tmp:
                    client, mock = build(Path(tmp), model, row, not_current)
                    token = client.cookies.get("rtc_csrf") or ""
                    r = client.post(path, data=dict({"csrf_token": token} if token else {}, **data), follow_redirects=False)
                    entry["actions"][key] = {"http": r.status_code, "redirect": r.headers.get("location", ""),
                                             "provider_calls": list(mock.calls), "rows_after": rows(client)}
            table.append(entry)
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    (out / "billing-matrix.json").write_text(json.dumps({"sha": sha, "provider": "MOCKED — not Razorpay", "rows": table}, indent=1, default=str))
    lines = [f"# Billing state / action matrix · SHA `{sha}` · provider MOCKED", "",
             "Generated by `m8/tools/billing_matrix_m8.py`. Reach: P = production-reachable stored shape, S = synthetic fixture. "
             "A route's \"provider calls\" are calls to a mock that mirrors the stored row; nothing here shows what the provider would do.", ""]
    for model in args.models.split(","):
        lines += [f"## `{model}`", "", "| Stored shape | Reach | Resolves to | Billing page heading | Page offers | Subscribe (Plus) | Change to Pro | Cancel |", "|---|---|---|---|---|---|---|---|"]
        for e in (t for t in table if t["tier_model"] == model):
            ent = e["entitlement"]
            res = f'{ent.get("block_reason") or "open"}; subscribed={ent.get("is_subscribed")}'
            cell = lambda k: (lambda a: f'{a["redirect"].replace("/billing/subscriptions", "…") or a["http"]}'
                              + (f' · calls: {"; ".join(c.split(" →")[0] for c in a["provider_calls"])}' if a["provider_calls"] else " · no provider call")
                              + (f' · rows → {", ".join(a["rows_after"])}' if a["rows_after"] != e["rows_before"] else " · rows unchanged"))(e["actions"][k])
            lines.append("| " + " | ".join([e["shape"], e["reach"], res, "; ".join(e["billing_page"]["h1"]) or "—",
                                             "<br>".join(e["billing_page"]["offers"] + e["billing_page"]["billing_links"]) or "nothing",
                                             cell("subscribe_plus"), cell("change_to_pro"), cell("cancel")]) + " |")
        lines.append("")
    (out / "billing-matrix.md").write_text("\n".join(lines) + "\n")
    print(f"{len(table)} shapes → {out} (sha {sha})")


if __name__ == "__main__":
    main()
