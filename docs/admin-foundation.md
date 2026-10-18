# Admin Foundation (5A/5B) — operations

The `/admin` console is a work tool for exactly one thing: what happened to a
user's Recall access, and the levers to fix it. It sits above the entitlement
layer as another *access source* — never as a fake subscription.

## The identity/commerce split

- **Role** (`user_roles`): who this identity is. Admins get full Recall
  access with `access_source=admin` and `is_subscribed=false` everywhere —
  the database and the UI never claim a purchase that does not exist.
- **Commercial access**: free / manual grant today; payments and
  subscriptions join later through their own billing tables. All of it feeds
  one capability check (`has_active_recall_access`).

## Flags

- `ADMIN_ENABLED` (default **false**) gates `/admin/*` and the Admin nav
  link **only**. It does not touch an admin identity's entitlement bypass —
  that follows the `user_roles` row. Removing the role is how admin access
  is revoked.
- `ADMIN_EMAILS` (default `sanjisworking@gmail.com`) is a comma-separated
  allowlist of signed-in emails that receive Playground `admin_override`
  without a `user_roles` row or a paid subscription. `is_subscribed` stays
  false. It does not open `/admin`. Set `ADMIN_EMAILS=` empty to disable.
- Multiuser off (local single-user serve): the owner keeps full access,
  `/admin` 404s. `multiuser off ≠ admin`.
- Grants become visible to users only while `ARTICLE_ENTITLEMENTS_ENABLED`
  is on (with it off, everyone already has full access).

## Roles (CLI-only until MFA)

```bash
# Hosted (DATABASE_URL from .env)
.venv/bin/python scripts/grant_admin.py --email name@recall.app
.venv/bin/python scripts/revoke_admin.py --user-id <uuid>

# Local SQLite
.venv/bin/python scripts/grant_admin.py --sqlite data/progress/progress.db --user-id <uuid>
```

Both scripts write the audit log. Supabase SQL editor fallback:

```sql
INSERT INTO user_roles (user_id, role) VALUES ('<uuid>', 'admin');
```

Browser-based role management waits until admin accounts are behind MFA
(**launch gate**: before production payments go live, admin accounts must
require MFA — Supabase TOTP with an AAL assertion on at least the sensitive
POSTs: grant/revoke, billing actions, role changes).

## Manual grants

`access_grants` holds admin/promotional grants only (sources `admin_grant`,
`promotion`). Overlap rule: the grant reaching furthest wins; an indefinite
grant beats any dated one. Revoking sets `revoked_at` — rows are never
deleted. Every grant/revoke writes its `admin_audit_log` row in the same
transaction: if the audit insert fails, the mutation rolls back.

## Entitlement preview

`/admin/preview` — four Article-aware states (`free_claimable`,
`free_claimed`, `free_cap`, `subscribed`) set the `rtc_admin_preview`
cookie, honoured only for verified admins. It simulates Learn restrictions
only; the session, nav and account pages still show the real you, and every
previewed state forces both persistence flags off (a claim-confirm while
previewing writes nothing). Test a true signed-out visit in a private
window.

## Dev harness

```bash
.venv/bin/python scripts/dev_admin_server.py --seed-demo   # seed members/grants
.venv/bin/python scripts/dev_admin_server.py               # port 8899, fake auth
```

The dev Google account is seeded as an administrator; `/login` → Google
lands in an admin session.

## Identity directory

`user_profile.email/phone/last_sign_in_at` refresh on every successful
sign-in (`record_identity`), so `/admin/users` search works for users who
have not signed in recently. The label is **Last sign-in** — it moves only
on authentication, never on activity.
