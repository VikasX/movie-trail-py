# CineScope Django backend

Python 3.12+, Django/DRF, Supabase PostgreSQL, httpx/TMDB, django-allauth Google OAuth,
and session/CSRF authentication. Implements the versioned `1.0.0-draft.2` contract:
35 `/api/v1/` method/path operations (including three existing scaffold operations),
plus the conventional allauth Google callback: **36 total**.

## Modules

- `core`: existing health/database/sample endpoints and sample admin.
- `accounts`: email registration/verification/login/reset, profile/preferences,
  hashed single-use tokens and Google integration adapters.
- `catalog`: TMDB client, normalized movie/TV cards/details/videos/providers,
  metadata, AND filters, bounded search snapshots and rule-based recommendations.
- `library`: saved/watched state, recent history, custom/computed collections,
  encrypted/hash-indexed public sharing and atomic idempotent guest sync.
- `common`: thin DRF views, strict contract-backed serializers, errors, CSRF,
  request IDs, throttling and snapshot pagination.
- `docs/API_CONTRACT.md` and `docs/openapi.yaml`: shared frontend/backend contract.

## Run locally in PowerShell

Dependencies and a local environment are already prepared in this checkout. On a
fresh checkout with Python installed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# Fresh checkout only; never overwrite working credentials:
Copy-Item .env.example .env
```

Set the variables described below, then run without activating PowerShell scripts:

```powershell
$env:DEBUG = 'True'
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate --plan
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py runserver localhost:8000
```

Use **localhost consistently** for browser auth. Google has registered
`http://localhost:8000/accounts/google/login/callback/`; `127.0.0.1` is a different
cookie/redirect host. Local React is expected at `http://localhost:5173` (change
CORS, CSRF and origins if its port differs). Existing health endpoints also work
on 127.0.0.1. Stop a previous server with Ctrl+C before restarting; use port 8000
for the configured Google callback.

Open:

- http://localhost:8000/api/docs/ ? Swagger with the complete reviewed contract.
- http://localhost:8000/api/schema/?format=json ? OpenAPI JSON.
- http://localhost:8000/api/v1/health/ ? process liveness.
- http://localhost:8000/api/v1/health/db/ ? actual database connectivity.
- http://localhost:8000/api/v1/metadata/ ? filter/mood configuration.
- http://localhost:8000/api/v1/titles/?media_type=movie&genres=animation,family ? AND genres.
- http://localhost:8000/api/v1/titles/movie/550/ ? movie details/trailers/providers.
- http://localhost:8000/api/v1/titles/tv/1399/ ? TV details.
- http://localhost:8000/admin/ ? users and application records.

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py seed_sample
```

Admin superusers are separate from product email verification. Existing admin
accounts keep working at `/admin/`; product login requires a verified EmailAddress
and an email unique ignoring case. Use the verification email flow rather than
claiming existing superusers are verified automatically. Social identity is supplied
by allauth SocialAccount; email/reset tokens use the AccountToken model.

## Environment

`.env` is read only locally. Existing process variables override it; Vercel never
reads it. All `.env*` files except `.env.example` are excluded from Git and function
uploads. Never put real credentials in source, docs, browser code or logs.

- `SECRET_KEY`: random value, at least 50 characters outside debug mode.
- `DEBUG`: False by default and always forced False on Vercel. Use True locally.
- `DATABASE_URL`: Supabase **session pooler** URI (port 5432), with URL-encoded
  password and `?sslmode=require`. Non-PostgreSQL engines and weak SSL modes are
  rejected. Per-request connections close; five-second connection timeout.
- `ALLOWED_HOSTS`: comma-separated exact hosts. Vercel project/deployment hosts
  are added from trusted system environment variables. Wildcard is rejected.
- `FRONTEND_PUBLIC_ORIGIN`: browser React origin, used for email completion links,
  allowed OAuth return paths and `/shared/<token>` links. No trailing slash.
- `BACKEND_PUBLIC_ORIGIN`: **browser-facing** API/OAuth origin, not necessarily the
  upstream function origin. With the production proxy, use the React origin here.
  Locally use `http://localhost:8000`.
- `CORS_ALLOWED_ORIGINS`: exact React origins; credentialed CORS is enabled.
- `CSRF_TRUSTED_ORIGINS`: exact trusted browser origins. The configured frontend
  origin is also added. CORS does not replace CSRF.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`: server-only allauth Google app settings.
- `TMDB_READ_ACCESS_TOKEN`: preferred bearer credential. `TMDB_API_KEY` is fallback
  only when the bearer token is missing. `TMDB_BASE_URL` defaults to TMDB v3 HTTPS.
- `SHARE_TOKEN_ENCRYPTION_KEY`: a separate Fernet key. Generate once, preserve across
  deploys, store securely. Changing it requires a deliberate key migration or share
  revocation; it is never derived from Django SECRET_KEY.
- `EMAIL_BACKEND`: console locally; a real SMTP/compatible backend in production.
  Configure `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
  `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`. Production fails safely with 503 when
  email delivery is unconfigured; it does not pretend to send verification emails.
- `LOG_LEVEL`: INFO by default. HTTP client URL logging is suppressed to avoid
  accidental credential query logging. Token/exception bodies are never API output.

The ignored `.env.vercel.local` contains prepared production values and newly
added share-encryption/origin values. Re-import it in Vercel after this change;
never commit it. Production email settings still need actual delivery credentials.
Commented URL-switching examples are kept in the environment files.

## Sessions, CSRF and Google

React requests use `credentials: 'include'`. Bootstrap GET `/api/v1/auth/csrf/`,
retain its JSON `csrf_token`, and send it as `X-CSRFToken` on every POST/PUT/PATCH/
DELETE, including guest recommendations/login. Cookies are host-only, HttpOnly,
SameSite=Lax, Path=/, Secure in production. Login rotates the session/CSRF token;
use the returned replacement token. OAuth completion bootstraps CSRF again before
fetching `/me/` or synchronizing guest data. GETs don't need a CSRF token.

Email: register (generic 202) ? email link on React ? POST email/verify ? login.
The React verification/reset pages submit tokens from their URLs and then remove
those tokens from browser history/referrers. Local console emails expose test links
only in your own terminal; don't use console delivery in production. Reset tokens
expire after one hour, verification after 24 hours; consuming a token invalidates
outstanding tokens of the same purpose. Password reset invalidates existing sessions
through Django's password/session hash checks. Authentication never silently syncs
or deletes browser data.

Google: POST `/api/v1/auth/oauth/start/` with
`{"provider":"google","return_to":"/library"}`. Navigate the browser to its
`authorization_url`. Allauth owns state, PKCE and the callback lifecycle at
`/accounts/google/login/callback/`. There is no competing `/api/v1/.../callback/`.
Google-verified email is required; matching an existing local email never silently
links accounts. Completion redirects to the allowlisted React path with an auth
outcome; no Google tokens are sent to React. Google credentials are configured,
but real browser consent/sign-in is not claimed verified by mocked callback tests.

## Vercel and the frontend proxy

Existing native Django preset, root manage.py, WSGI entry point, Python 3.12 and
Tokyo region remain. Runtime dependencies are in pyproject.toml + uv.lock; pip
requirements are exported from that project metadata. Static files (including admin)
are collected by Vercel at build time. No migrations run at import or per request,
no persistent filesystem or background worker is needed.

For the separate deployed UI/backend, the **frontend agent** must add these rewrites
in the frontend repository (this task does not modify it):

```json
{
  "rewrites": [
    {"source":"/api/:path*","destination":"https://movie-trail-py.vercel.app/api/:path*"},
    {"source":"/accounts/:path*","destination":"https://movie-trail-py.vercel.app/accounts/:path*"}
  ]
}
```

Place API/accounts rewrites before the Vite SPA fallback; `/shared/<token>`,
`/auth/verify-email`, `/auth/reset-password`, `/discover` and `/library` remain public
React routes. Preserve Cookie, all Set-Cookie headers, Origin, query parameters,
CSRF headers and redirects; never CDN-cache auth or private responses. Use an empty
RTK base origin plus `/api/v1/` in this topology.

Backend production variables for that proxy:

```dotenv
FRONTEND_PUBLIC_ORIGIN=https://movie-trail-ui.vercel.app
BACKEND_PUBLIC_ORIGIN=https://movie-trail-ui.vercel.app
CORS_ALLOWED_ORIGINS=https://movie-trail-ui.vercel.app
CSRF_TRUSTED_ORIGINS=https://movie-trail-ui.vercel.app
ALLOWED_HOSTS=movie-trail-py.vercel.app,movie-trail-ui.vercel.app
DEBUG=False
```

Register **exactly** this additional Google authorized redirect URI:
`https://movie-trail-ui.vercel.app/accounts/google/login/callback/`.
The existing local URI stays registered. Both the OAuth start and callback must
use the same browser cookie host. Verify proxy cookie propagation and HTTPS header
behavior in a browser before declaring production auth ready. Django only trusts
Vercel's managed forwarded-protocol header; it does not blindly trust forwarded Host.
Canonical callback/pagination URLs use BACKEND_PUBLIC_ORIGIN explicitly.

Alternative: custom same-site `app.example.com`/`api.example.com` subdomains,
with BACKEND_PUBLIC_ORIGIN on api.example.com, exact credentialed CORS/CSRF origins
and callback registered on api.example.com. Keep host-only cookie domains. Two
unrelated vercel.app origins with direct fetch calls are not a reliable cookie-login
strategy; SameSite=None alone does not solve third-party cookie blocking.

Do not push or deploy automatically. Import variables for the intended Vercel
Production/Preview environment and deploy the reviewed commit manually. Public
shares always return the React frontend URL, never raw API JSON URLs.

## Database migrations and maintenance

Use the session-pooler DATABASE_URL from a trusted local/release terminal. Inspect
`migrate --plan`, back up before future schema changes, and serialize release jobs.
The email-uniqueness migration audits existing nonempty emails and refuses to proceed
if case-insensitive duplicates exist; it never deletes users to resolve a conflict.
New models extend the existing User; auth migrations are not reset. The cache-table
migration creates the shared PostgreSQL cache once. Supabase migrations for this
implementation were applied successfully.

```powershell
.\.venv\Scripts\python.exe manage.py migrate --plan
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py cleanup_expired
```

Maintenance prunes expired receipts/tokens/leases and unreferenced metadata snapshots;
Django DatabaseCache also culls entries within its configured bounds. Keep guest
source mappings/tombstones for retry safety. Never automatically recreate an imported
collection deleted by its owner. Session cleanup can use Django's `clearsessions`.
Use separate Supabase databases/projects for preview versus production.

## Data and serverless behavior

Composite `(media_type, tmdb_id)` identity everywhere. Watched remains saved.
Unsave removes memberships; removing a collection/member retains saved titles.
Automatic genre/decade/8+ rating/movie/TV/watched groups are computed from saved
metadata, never persisted as custom collections. Public share tokens are hashed
for lookup and encrypted for owner recovery; revocation is checked on every page.

Catalogue requests consider up to 40 source candidates using at most two list calls;
All splits 20 per media. Runtime filtering uses a deterministic six-title window
and at most six detail hydrations. Eight total outbound attempts including retries,
15-second deadline, five-second read and two-second connect timeouts; sequential
calls are intentionally conservative (below the three-call concurrency ceiling).
Genres are AND across selections; filters are never relaxed. Post-filtered bounded
results may be empty while matches exist outside the window, and counts/sorts are
not global catalogue counts. No per-card video/provider/keyword fan-out.

Shared PostgreSQL caches upstream/configuration and immutable five-minute result
snapshots. Page 2+ uses the snapshot only; an expired snapshot returns 410. Public
query snapshots may be reused; private first pages are rebuilt after mutations.
Malformed upstream responses fail safely. Optional trailer/provider failures use
warnings. Missing trailers return []/null. Initial mood keyword lists are explicitly
empty until curated TMDB IDs are verified; no AI/LLM infrastructure is introduced.

Guest sync is explicit after login; Not Now makes no request. Stable sync_id/payload
replays for 24h; changed payload with the same key returns 409. Unknown metadata
resolution precedes atomic writes; transient failures commit no user merge data.
Merge uses watched OR, preserves existing account dates/names, unions memberships,
handles name conflicts, quotas, durable source IDs and deleted-source tombstones.
Large uncached imports may need stable smaller batches due to the synchronous budget.

## Checks and tests

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pytest -o cache_dir=.tools/pytest-cache
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe manage.py spectacular --validate --fail-on-warn --file .tools/openapi.yaml
```

Tests use a disposable in-memory SQLite database and local memory cache; they do not
connect to or mutate Supabase. All network calls are blocked unless mocked. PostgreSQL
migration execution and representative real TMDB movie/TV responses were separately
verified against the configured local environment. SQLite tests do not prove concurrent
PostgreSQL locking behavior; owner locks/unique constraints are implemented for the
production PostgreSQL path. Production checks retain the deliberate HSTS subdomain/
preload warnings until every affected hostname is ready for that policy.

To refresh dependency locks, install uv then run:

```powershell
uv lock
uv pip compile pyproject.toml --python-version 3.12 --universal -o requirements.txt
uv pip compile requirements-dev.in --python-version 3.12 --universal -o requirements-dev.txt
```

Still external: real SMTP delivery configuration, frontend proxy/routes, production
Google callback registration and a browser end-to-end Google/email session test.
No new deployment or Git push was performed by this implementation task.
