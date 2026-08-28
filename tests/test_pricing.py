"""Pricing model + /pricing page (flag-gated, single-panel duration selector)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from constitution_memorizer.web import pricing as pr
from constitution_memorizer.web.app import create_app
from constitution_memorizer.multiuser.settings import MultiUserSettings

MINI_UNITS = Path(__file__).parent / "fixtures" / "learning" / "mini_units.json"


# --------------------------------------------------------------------------- #
# Model                                                                        #
# --------------------------------------------------------------------------- #
def test_seven_plans_days_ascending_prices_increasing() -> None:
    assert len(pr.PLANS) == 7
    days = [p.days for p in pr.PLANS]
    prices = [p.price_inr for p in pr.PLANS]
    assert days == sorted(days) == [3, 7, 15, 30, 60, 180, 365]
    assert prices == sorted(prices)
    assert len(set(prices)) == len(prices)  # strictly increasing


def test_per_day_strictly_decreasing_and_correct() -> None:
    rates = [pr.per_day(p) for p in pr.PLANS]
    assert rates == sorted(rates, reverse=True)
    assert len(set(rates)) == len(rates)
    assert pr.per_day(pr.get_plan(180)) == 3.88
    assert pr.per_day(pr.get_plan(365)) == 2.74
    for plan in pr.PLANS:
        assert pr.per_day(plan) == round(plan.price_inr / plan.days, 2)


def test_recurring_split_one_time_vs_auto_renew() -> None:
    for plan in pr.PLANS:
        assert plan.recurring is (plan.days > 15)


def test_primary_and_more_partition_all_seven() -> None:
    assert set(pr.PRIMARY_DAYS) | set(pr.MORE_DAYS) == {p.days for p in pr.PLANS}
    assert not (set(pr.PRIMARY_DAYS) & set(pr.MORE_DAYS))
    assert pr.DEFAULT_DAYS == 180
    assert pr.DEFAULT_DAYS in pr.PRIMARY_DAYS


def test_get_plan_fallback_to_hero() -> None:
    assert pr.get_plan(30).days == 30
    assert pr.get_plan("60").days == 60
    for bogus in (None, "abc", 999, -1, ""):
        assert pr.get_plan(bogus).days == pr.DEFAULT_DAYS


def test_billing_line_derives_from_recurring() -> None:
    assert pr.billing_line(pr.get_plan(7)) == "7-day access · No automatic renewal"
    assert pr.billing_line(pr.get_plan(180)) == "Renews every 180 days · Cancel anytime"
    payload = pr.plans_json()
    assert [p["days"] for p in payload] == [3, 7, 15, 30, 60, 180, 365]
    assert all("billing_line" in p and "per_day" in p for p in payload)


# --------------------------------------------------------------------------- #
# Route (flag-gated)                                                           #
# --------------------------------------------------------------------------- #
def _settings(pricing: bool) -> MultiUserSettings:
    return MultiUserSettings(
        _env_file=None,
        APP_ENV="test",
        MULTIUSER_ENABLED="false",
        SESSION_SECRET="test-secret",
        PRICING_ENABLED="true" if pricing else "false",
    )


def _client(tmp_path: Path, *, pricing: bool) -> TestClient:
    app = create_app(
        units_path=MINI_UNITS,
        db_path=tmp_path / "progress.db",
        multiuser_settings=_settings(pricing),
    )
    return TestClient(app)


def test_pricing_404_while_flag_off(tmp_path: Path) -> None:
    client = _client(tmp_path, pricing=False)
    assert client.get("/pricing").status_code == 404
    # And no nav link anywhere.
    home = client.get("/")
    assert 'href="/pricing"' not in home.text


def test_pricing_page_defaults_to_180(tmp_path: Path) -> None:
    client = _client(tmp_path, pricing=True)
    resp = client.get("/pricing")
    assert resp.status_code == 200
    html = resp.text
    assert "Everything in Recall. Choose your duration." in html
    assert "Every Recall plan unlocks the complete experience." in html
    assert "180-Day Recall" in html
    assert "₹699" in html
    assert "₹3.88 / day" in html
    assert "Renews every 180 days · Cancel anytime" in html
    assert "Complete Recall journey" in html
    assert "Learn → Recall → Review → Strengthen → Master" in html
    assert 'id="pricing-data"' in html
    assert "data-pricing-annotation hidden" not in html


def test_pricing_selection_and_billing_wording(tmp_path: Path) -> None:
    client = _client(tmp_path, pricing=True)
    seven = client.get("/pricing?d=7").text
    assert "7-Day Recall" in seven
    assert "₹99" in seven
    assert "₹14.14 / day" in seven
    assert "7-day access · No automatic renewal" in seven
    # No blanket auto-renew statement for a one-time pass.
    assert "Renews every 7 days" not in seven
    assert 'data-pricing-annotation' in seven
    assert 'data-pricing-annotation hidden' in seven or 'data-pricing-annotationhidden' in seven.replace(
        " ", ""
    )
    # The standalone page must hide empty annotation pills (3/7/15 have none).
    assert ".pricing-panel-annotation[hidden]" in seven
    for days in (3, 15):
        page = client.get(f"/pricing?d={days}").text
        assert "data-pricing-annotation" in page
        assert " hidden" in page.split("data-pricing-annotation")[1].split(">")[0]

    thirty = client.get("/pricing?d=30").text
    assert "Renews every 30 days · Cancel anytime" in thirty
    assert "Most flexible" in thirty

    # Unknown / invalid selections fall back to the hero plan.
    assert "180-Day Recall" in client.get("/pricing?d=abc").text
    assert "180-Day Recall" in client.get("/pricing?d=999").text


def test_pricing_free_link_and_feature_strip(tmp_path: Path) -> None:
    client = _client(tmp_path, pricing=True)
    html = client.get("/pricing").text
    assert "Explore for free." in html
    assert "save your first 3 Articles" in html
    assert "Continue free →" in html
    assert "Visual explainers where available" in html
    assert "Type &amp; Recite" in html
    # Single-user (no multiuser): free link goes to Browse, not login.
    assert 'href="/browse">Continue free' in html
