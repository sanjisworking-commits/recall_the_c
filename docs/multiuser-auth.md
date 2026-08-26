# Multi-user authentication (hosted)

This branch adds Supabase Auth (Google + phone OTP), server-side sessions, and
per-user progress. The Constitution corpus remains shared.

## Guest-first product rule

**Anyone can explore and learn. Signing in is required only to save personal progress.**

| Guests can | Guests cannot (prompt sign-in) |
|---|---|
| Browse, search, read Bare Act + explanations | Save progress / mark done / Again tomorrow |
| Try Learn modes (read/type/etc. without persisting) | Memory notes, personal dashboard, Progress mastery |

There is no guest progress database and no migrate-on-signup. Content is never blurred.

Single-user local mode (`scripts/mac/start-ui.command`, SQLite without
`MULTIUSER_ENABLED`) remains available when `MULTIUSER_ENABLED` is unset/false.

## Page map

```
Guest
  ├─ /                 marketing landing (Start learning → /login; Explore → /browse)
  ├─ /browse, /search  corpus
  ├─ /learn/{id}       try modes + guest banner / sign-in modal
  ├─ /dashboard        inline guest gate
  └─ /progress         inline guest gate

Authentication
  ├─ /login            Google + India phone (+91 / 10 digits) + OTP
  ├─ /auth/transition  “Opening your learning space…”
  ├─ /welcome          first-time display name
  ├─ /signed-out
  └─ /session-expired

Signed-in
  ├─ /dashboard        greeting, due, continue, stats, activity
  ├─ /profile          name, preferences, sign-out / delete
  └─ /progress, /calendar, /memory, /settings
```

## Local setup

1. Create a PostgreSQL database and set `DATABASE_URL` (optional for local SQLite progress).
2. Copy `.env.example` → `.env` and fill secrets.
3. Apply migrations when using Postgres:

```bash
export DATABASE_URL=postgresql://user:password@localhost:5432/recall_the_c_multiuser
alembic upgrade head
# or:
python -m constitution_memorizer.multiuser.migrate
```

4. Launch:

```bash
# macOS
open scripts/mac/start-multiuser.command

# or:
export MULTIUSER_ENABLED=true PORT=8010
python -m constitution_memorizer.cli serve --host 127.0.0.1 --port 8010
```

Hosted (Railway / Railpack):

```bash
python -m uvicorn constitution_memorizer.web.asgi:app --host 0.0.0.0 --port "$PORT"
```

Python is pinned to **3.12.11** in `.python-version` and `railpack.json`. Do not use a floating `3.11` — mise resolves that to a patch with no precompiled binary and the build dies before pip.

`MULTIUSER_ENABLED=true`, Postgres `DATABASE_URL`, and Supabase secrets must be set on the service. Do not set `MULTIUSER_ENABLED` on the local 8001 launcher.

## Supabase dashboard

1. Create a Supabase project.
2. Authentication → Providers → enable **Google**.
3. Authentication → Providers → enable **Phone**.
4. Authentication → URL configuration:
   - Site URL: `APP_BASE_URL`
   - Redirect URLs: `{APP_BASE_URL}/auth/callback`
5. Copy Project URL → `SUPABASE_URL`
6. Copy `anon` public key → `SUPABASE_ANON_KEY`
7. Never put the **service role** key in the web app or browser.

## Google provider

1. Google Cloud Console → OAuth client (Web).
2. Authorized redirect URI must be the Supabase callback
   (`https://<project>.supabase.co/auth/v1/callback`).
   Do **not** put `{APP_BASE_URL}/auth/callback` here — that belongs in
   Supabase → Authentication → URL configuration.
3. Paste Client ID/secret into Supabase Google provider settings.
4. App OAuth uses **PKCE**: `/auth/google/start` stores a code verifier cookie and
   Supabase returns `?code=` to `{APP_BASE_URL}/auth/callback`. Ensure
   `APP_BASE_URL` matches the URL you open in the browser (`http://127.0.0.1:8010`
   vs `http://localhost:8010` must match exactly).

### Why Google says “Sign in to ….supabase.co”

Google shows the **OAuth redirect host** on the consent screen. With Supabase Auth
that host is your project URL (`https://<ref>.supabase.co`), so the screen reads
“Sign in to `<ref>.supabase.co`” even though users came from Recall the C.

To brand it better:

1. Google Cloud → **Google Auth Platform → Branding** (or APIs & Services →
   OAuth consent screen): set **App name** to `Recall the C`, add a logo, and
   support email / home page.
2. Publish the consent screen (Testing → add test users, or Production when ready).
3. Optional (paid Supabase): attach a **custom auth domain** so Google shows
   something like `auth.yourdomain.com` instead of `<ref>.supabase.co`.

The app itself cannot rename that Google screen — it is controlled by Google +
the redirect URI host.

## Phone / SMS provider

1. In Supabase Phone provider, configure an SMS gateway (Twilio, MessageBird, etc.).
2. The UI is India-first (`+91` + 10 digits `^[6-9]\d{9}$`). The server composes E.164
   (`+91…`) before calling Supabase. Full E.164 values are still accepted.
3. Application-level OTP rate limits apply in addition to provider limits.

## Access control (multi-user)

**Public (GET):** `/`, `/browse*`, `/search`, `/learn*` (try modes), `/tables`, `/laws*`,
`/login`, `/auth/*`, `/static/*`, `/health`, `/signed-out`, `/session-expired`

**Auth required:** `/dashboard`, `/progress`, `/calendar`, `/memory*`, `/settings`,
`/profile` (writes), `/api/theme`, and progress-mutating POSTs
(`/learn/*/done`, `/again`, `/seen`, `/choose`, `/reset`, gloss, memory writes).

Unauthenticated mutating POSTs redirect to `/login?next=…&reason=…`.
Learn GET for guests does **not** call `mark_mode_seen`.

## Feature flags

| Variable | Effect |
|----------|--------|
| `AUTH_GOOGLE_ENABLED=false` | Hide Google button / reject Google start |
| `AUTH_PHONE_ENABLED=false` | Show phone option as “not currently available”; reject OTP routes. Hosted environments stay paused until SMS registration completes, even if this flag is still true. Tests (`APP_ENV=test`) honour the flag so OTP flows stay covered. |
| Both false in staging/production | Startup fails |

## Account identity

Google and phone logins may create **different** Supabase user UUIDs.
This phase does **not** auto-link accounts. Account linking is a future feature.

First sign-in without a display name routes to `/welcome`.

## Tests

```bash
pytest -m "not integration" -q
pytest tests/test_multiuser_auth.py tests/test_multiuser_isolation.py tests/test_guest_first_ux.py -q
```

Tests use `FakeAuthProvider` and never contact Google or send SMS.

## Known limitations

- No email/password auth.
- No automatic Google↔phone account linking.
- No guest→account progress transfer.
- Hosted multi-user reminder fan-out is not implemented (CLI reminders remain single-tenant).
- Local SQLite progress DBs are not auto-imported into Postgres.
- Account delete clears personal progress + session; provider-side hard delete is not wired yet.
