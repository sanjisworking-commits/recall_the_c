# Legacy commercial transition

Milestone 11 inventory. Current product truth lives in [PLAYGROUND.md](PLAYGROUND.md) and [PAYMENT_ENTITLEMENT_AUDIT.md](PAYMENT_ENTITLEMENT_AUDIT.md). This file classifies leftover commercial code so operators can freeze it without deleting data.

**Legacy tables/data retained. Current access paths no longer depend on them. Deletion deferred until a separate proven-unused cleanup.**

Do not map a 365-day (or any N-day) historical purchase to Max, Pro, or Plus.

## Current access (authoritative)

```text
authenticated account → full Constitution Learn
  (all Articles, all six modes, persistence)

Playground commercial truth → user_subscription / admin_override / local-owner
  Plus ₹199 / Pro ₹399 / Max ₹1,199 per month
```

`ARTICLE_ENTITLEMENTS_ENABLED` may remain in config. Signed-in access does not depend on it. Guests still use it for explore-mode surfaces.

Historical duration buyers with no `user_subscription`:

```text
Constitution → full, because signed in
Playground → not automatically subscribed
```

An old `access_grants` row that is still temporally active may appear as historical/account data. It does not control Constitution access, Playground tier, roster capacity, or device allowance.

## Classification

### A. Still required for reading historical records

| Artifact | Why it stays |
|----------|----------------|
| `user_free_articles` | Claim chips / admin history. Not an authorization input for signed-in Learn. |
| `access_grants` | Admin grant history; `admin_audit_log` companions. |
| `billing_orders` | Legacy Razorpay Orders receipts. |
| `web/pricing.py` `PLANS` (3/7/15/30/60/180/365 days) | Model for historical receipts and frozen `/pricing` when `PRICING_ENABLED`. |
| `subscriptions/legacy.py` `classify_legacy_paid_access` | Read-only `legacy_status` on `EntitlementSnapshot`. Never writes `user_subscription`. |
| Admin “Access history” / grant forms | History + support; grants are not Plus/Pro/Max. |
| Profile lifecycle copy keyed on legacy `subscription` | Displays historical duration passes when that object exists. |

### B. Inactive compatibility code

| Artifact | Status |
|----------|--------|
| `ARTICLE_ENTITLEMENTS_ENABLED` | Guest explore + historical status surfaces. Signed-in Constitution ignores the 3-Article cap and Type/Recite lock. |
| `web/entitlements.py` Free-slot matrix | Used for guests and Entitlement Preview, not signed-in authorization. |
| `PRICING_ENABLED` (default false) | 404s `/pricing` and `/subscribe*`. Leftover template links are gated. |
| `/api/billing/order` and `/api/billing/verify` | Live only while `PRICING_ENABLED`; not the Playground catalogue. |
| Admin grant footnote / claim chips | Labelled historical / inactive for access. |

### C. Safe candidate for future deletion

Category C is retained. Delete only after proven unused (no route imports, no current service imports, no runtime migration dependency, no tests except historical fixtures, no admin/history display). The label **category C** is the inventory bucket for later cleanup.

| Artifact | Proof still required |
|----------|----------------------|
| N-day purchase templates (`pricing.html`, `purchase_confirm.html`, `purchase_result.html`) | Confirm no operator still enables `PRICING_ENABLED` for receipts. |
| `web/billing.py` Orders client | Confirm no in-flight legacy orders. |
| 3-Article claim prompt copy in Learn templates | Confirm guest explore copy has a replacement. |
| `user_free_articles` writes on Done | Confirm no report still counts slots as commercial truth. |

### D. Still unexpectedly reachable — must fix before release

None remaining after M11:

* Public/navigation HTML does not link N-day checkout unless `PRICING_ENABLED`.
* Playground billing HTML offers Plus / Pro / Max monthly only.
* Admin no longer teaches “three permanent Articles, Type and Recite locked” as current access.

## Obsolete HTTP routes

| Route | Label |
|-------|--------|
| `GET /pricing` | frozen — 404 unless `PRICING_ENABLED` |
| `GET /subscribe/confirm` | frozen — 404 unless `PRICING_ENABLED` |
| `GET /subscribe/pay` | frozen — 404 unless `PRICING_ENABLED` |
| `GET /subscribe/result` | frozen — 404 unless `PRICING_ENABLED` |
| `POST /api/billing/order` | frozen — 404 unless `PRICING_ENABLED` |
| `POST /api/billing/verify` | frozen — 404 unless `PRICING_ENABLED` |
| `GET/POST /billing/subscriptions*` | **active** — Plus/Pro/Max |
| `POST /api/billing/subscriptions/webhook/razorpay` | **active** — keep ingesting even if Playground UI is killed |
| Admin grant create/revoke | **admin/history-only** — not Playground commerce |

## What M11 deliberately did not delete

* No `DROP TABLE` for `user_free_articles`, `access_grants`, `billing_orders`.
* No rewrite of Constitution progress into Playground overlay tables.
* No mapping of duration SKUs onto monthly tiers.
* Alembic head remains `20260927_0027`.
