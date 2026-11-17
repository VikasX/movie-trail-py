# CineScope API

A Python 3.12+ Django REST Framework backend using PostgreSQL through Django ORM
and psycopg. Service health, database health, and a read-only database sample API are implemented. Django's built-in
User, permissions, content types and sessions are installed; the sample table is the only custom model. Django admin is available at `/admin/`. There are no authentication APIs,
TMDB calls or background workers.

## Structure

```text
manage.py                   Django CLI at the repository root
config/
  settings.py               Environment, database, DRF and security settings
  urls.py                   API, schema and Swagger routing
  wsgi.py                   Vercel WSGI entry point
  asgi.py                   Standard alternative ASGI entry point
core/
  admin.py                  Sample table management in Django admin
  apps.py                   Core app configuration
  serializers.py            Health response schemas
  urls.py                   Health routes
  views.py                  Liveness and database readiness checks
tests/                      Health, routing and security tests
requirements-dev.in         Development dependency input
uv.lock                     Locked Vercel runtime dependencies
requirements*.txt           Pinned runtime/development dependencies
pyproject.toml              Runtime dependencies, pytest, Ruff and Vercel entry point
vercel.json                 Native Django preset and function settings
.env.example                Environment template without secrets
```

## Local setup

Install Python 3.12 or later. From the repository root in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Paste the generated value into `SECRET_KEY` in `.env`, set `DEBUG=True` for local
HTTP development, and supply your Supabase PostgreSQL URI as `DATABASE_URL`.
Do not overwrite an existing `.env` when repeating setup. If this checkout already
has `.venv` and `.env`, activate the environment and edit `.env` directly.
If activation is blocked, use `.\.venv\Scripts\python.exe` instead of `python`.

On macOS/Linux use `python3.12 -m venv .venv`, `source .venv/bin/activate`, and
`cp .env.example .env`; the remaining Python commands are identical.

After configuring and migrating the database (see below):

```powershell
python manage.py check
# This shell already defines DEBUG=release; override it for local HTTP:
$env:DEBUG = 'True'
python manage.py runserver
```

Liveness and Swagger do not query the database, but Django's development server
checks migration status at startup and therefore needs a reachable database.
Until credentials are configured, use `python manage.py check` and `python -m pytest`
to verify the application without PostgreSQL. `runserver --skip-checks` does not
skip Django's migration-status check. Database health returns 503 when PostgreSQL
is unavailable.

## Environment and security

Settings read `.env` locally; existing process variables take precedence. Vercel
uses its environment variables directly and does not read `.env`.

- `SECRET_KEY`: required random secret, at least 50 characters in production.
- `DEBUG`: defaults to `False`; set `True` only locally. Vercel rejects `True`.
- `ALLOWED_HOSTS`: comma-separated backend hostnames without schemes or paths.
  Production requires explicit hosts and rejects `*`. On Vercel, exact project
  hostnames are also populated from system environment variables automatically.
- `DATABASE_URL`: required PostgreSQL URI. SSL defaults to `require`; weaker modes
  and other engines are rejected. `verify-full` with the appropriate CA is supported
  through URL options. URL-encode special characters in passwords.
- `CORS_ALLOWED_ORIGINS`: comma-separated frontend origins with scheme and port,
  without trailing slashes. Defaults to none.
- `CSRF_TRUSTED_ORIGINS`: explicit trusted origins for future cookie authentication.
  Defaults to none. CSRF middleware remains enabled; CORS credentials are currently
  off. Future cross-origin cookies need deliberate cookie and CSRF configuration.
- `LOG_LEVEL`: application log level, default `INFO`. Logs go to the console.

With debug off, HTTPS redirects, secure cookies, HSTS (one year, current host only),
content sniffing protection and frame denial are enabled. Forwarded HTTPS headers
are trusted only on Vercel; configure proxy trust explicitly for other hosts.
DRF defaults to authenticated access, JSON input/output, page-number pagination
(20 items) and django-filter. Health and documentation explicitly permit anonymous
access. No login endpoint is exposed.

## Supabase and migrations

Use the **session pooler** URI from Supabase's **Connect** dialog (port `5432`)
for both application requests and migrations. Set it as `DATABASE_URL` in `.env`
and in Vercel's environment variables. Connections close after each request
(`CONN_MAX_AGE=0`); SSL is required and the connection timeout defaults to five
seconds. Choose a function region near Supabase. Supabase API keys are not
PostgreSQL credentials. Monitor connection limits when scaling serverless instances.

Run migrations through a **direct** connection (usually port `5432`, requires IPv6
unless your project provides IPv4), or the **session pooler** (port `5432`), from
a trusted local machine or controlled release job. Use a role with DDL privileges.
Confirm the intended project and database; back up production before future schema
changes. Use a separate Supabase project/database for preview environments.

In a separate PowerShell terminal with the virtual environment activated, enter
the direct/session URI without putting credentials in shell history:

```powershell
$migrationUrl = Read-Host 'Supabase direct or session DATABASE_URL' -AsSecureString
$env:DATABASE_URL = [System.Net.NetworkCredential]::new('', $migrationUrl).Password
python manage.py check --database default
python manage.py migrate --plan
python manage.py migrate --noinput
python manage.py showmigrations
Remove-Item Env:DATABASE_URL
Remove-Variable migrationUrl
```

Close that terminal afterward. The runtime continues using its session-pooler URI.
Run migrations once per release, before code requiring the schema receives traffic;
serialize migration jobs. Never run migrations during requests or Vercel builds.
Migrations include Django's built-in auth/contenttypes/sessions tables and
`core_samplerecord`, the public demonstration table. A successful `SELECT 1` checks connectivity, not
schema readiness; inspect `showmigrations` separately.

After migrating, seed the demonstration row explicitly (safe to repeat):

```powershell
python manage.py seed_sample
```

## API

- `GET /api/v1/health/`: 200 with `{"status":"ok","service":"CineScope API"}`.
  Does not access PostgreSQL.
- `GET /api/v1/health/db/`: executes `SELECT 1` through Django's connection.
  200: `{"status":"ok","database":"connected"}`.
  503: `{"status":"error","database":"unavailable"}`.
  Responses and health-check logs omit credentials and internal exception details.
  Health responses are not cached.
- `GET /api/v1/samples/`: reads up to 20 rows from `core_samplerecord` using
  Django ORM. This public endpoint permits reads only and never inserts data.
  Example: `[{"id":1,"name":"CineScope database demo","message":"Hello from PostgreSQL! CineScope is reading database data."}]`.
  Database failures return 503 with `{"detail":"Database unavailable."}`.
- `/api/schema/`: OpenAPI schema (`?format=json` for JSON).
- `/api/docs/`: Swagger UI, with version-pinned JavaScript/CSS from jsDelivr.

```powershell
curl.exe http://127.0.0.1:8000/api/v1/health/
curl.exe -i http://127.0.0.1:8000/api/v1/health/db/
curl.exe http://127.0.0.1:8000/api/v1/samples/
```

## Quality checks

```powershell
python -m pip check
python manage.py check
python -m pytest
python -m ruff check .
python -m ruff format --check .
python manage.py spectacular --validate --fail-on-warn
```

Tests isolate environment values and mock database readiness success/failure.
pytest-django blocks real database access in these unit tests. They do not prove
live connectivity or apply migrations, and never create a Supabase test database.
Before release, run `python manage.py check --deploy` with production settings
(`DEBUG=False`).

The deployment check reports `security.W005` and `security.W021` because HSTS
subdomain coverage and browser preloading are intentionally off. Enable these only
after confirming HTTPS for every affected subdomain and choosing to enroll the
domain in browser preload lists; HSTS already protects this API host.

Runtime dependencies are declared in `pyproject.toml`; Vercel installs them using
`uv.lock`. `requirements.txt` is generated from the same project metadata for pip
users. Development packages in `requirements-dev.txt` use the same runtime versions.
To update, edit `pyproject.toml`, install uv, regenerate the lock and requirements
files, and rerun checks:

```powershell
uv lock
uv pip compile pyproject.toml --python-version 3.12 --universal -o requirements.txt
uv pip compile requirements-dev.in --python-version 3.12 --universal -o requirements-dev.txt
python -m pip install -r requirements-dev.txt
```

## Vercel deployment

This uses [Vercel's native Django support](https://vercel.com/docs/frameworks/full-stack/django).
Vercel discovers root `manage.py`; `tool.vercel.entrypoint` selects
`config.wsgi:application`. Django handles routing without rewrites or `api/index.py`.
`.python-version` selects Python 3.12. Vercel installs dependencies from `pyproject.toml` and `uv.lock` and collects
build-time static assets for its CDN. Runtime code uses PostgreSQL sessions and
console logs, with no persistent local storage.

1. Push the code to Git, then import the repository in Vercel. Use this repository
   root and the **Django** preset. Leave build/install commands at their defaults.
   The configured function region is Tokyo (`hnd1`), near the Supabase database.
2. Expand **Environment Variables**, choose **Import .env**, and select the local
   `.env.vercel.local` file prepared in this checkout. It contains a fresh production
   secret, `DEBUG=False`, and the verified Supabase session-pooler connection.
   This file is ignored by Git and excluded from deployment uploads. Vercel needs
   these values in its environment settings; it cannot get them from the Git repo.
3. Click **Deploy**. Exact deployment, branch and production hosts are automatically
   allowed using Vercel's system environment variables. Keep automatic system
   environment variable exposure enabled (the Vercel default). Add custom backend
   domains to `ALLOWED_HOSTS` if they differ from the production URL Vercel supplies.
4. Check `/api/v1/health/`, `/api/v1/health/db/`, `/api/v1/samples/` and `/api/docs/`
   on the deployed HTTPS URL. Supabase migrations and sample seeding are already done.
   Vercel does not run migrations automatically.

Frontend origins are currently empty in the deployment environment file because
no frontend URL has been provided. The API and Swagger work directly in the browser.
Once a frontend is deployed, add its exact origin to `CORS_ALLOWED_ORIGINS` and
`CSRF_TRUSTED_ORIGINS` in Vercel, then redeploy.

Preparing these files does not deploy the application. Live Supabase connectivity,
migrations and Vercel deployment require verification against your environments.

## Initial scaffold verification (before Supabase connection)

Verified locally with Python 3.12.16 and Django 6.1.3:

- Dependencies installed; `pip check` passed.
- Django system checks, 12 pytest tests, Ruff lint and formatting passed.
- OpenAPI validation and `collectstatic` passed.
- WSGI routing and forwarded HTTPS handling, ASGI initialization, and the built-in
  migration dependency graph were checked without a hosted database.
- An actual failed connection returned the expected sanitized 503 response.
- Production checks reported only the two intentional HSTS warnings explained above.

No valid Supabase credentials were available, so live connectivity and migration
execution were not verified. No Vercel deployment was performed. The ignored local
`.env` contains a generated development secret and a placeholder localhost database
URL. `.tools` holds the project-local Python/uv installation used to create `.venv`;
keep it while using this environment, or recreate `.venv` using your own Python.

References: [Django releases](https://www.djangoproject.com/download/),
[Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python),
[Supabase connections](https://supabase.com/docs/guides/database/connect-to-postgres),
[Supabase prepared statements](https://supabase.com/kb/troubleshooting/disabling-prepared-statements-qL8lEL).

## Connected database verification

Verified the supplied Supabase session pooler connection with client SSL active.
Applied all auth/contenttypes/sessions/core migrations and seeded one sample row.
Verified HTTP 200 for both health endpoints, `/api/v1/samples/` (reading the actual
Supabase row), and Swagger. All 15 unit tests, Ruff and OpenAPI validation passed.
The sample model and explicit `seed_sample` command allow verifying real ORM reads
at `/api/v1/samples/`. No credentials belong in tracked files or documentation.
Use the same session-pooler `DATABASE_URL` in Vercel. Deployment remains a separate
step; local database verification does not verify Vercel connectivity.

## Django admin

Django admin is enabled at `/admin/` with Users, Groups and Sample records.
Create your superuser interactively; the password is entered privately in your
terminal and stored as a hash in Supabase:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Enter your preferred username, email (optional), and a strong password. This admin
password is separate from the PostgreSQL connection password. Then start or restart
the development server without activating PowerShell scripts:

```powershell
$env:DEBUG = 'True'
.\.venv\Scripts\python.exe manage.py runserver
```

Open `http://127.0.0.1:8000/admin/` and sign in. Under **Core ? Sample records**, edit
the demo message, save, and refresh `http://127.0.0.1:8000/api/v1/samples/` to see the
changed database value. These edits affect the connected Supabase database.
Only active staff users can access admin; superusers have full permissions.
If port 8000 is occupied, stop the old server or use `runserver 8001`.

The same Supabase superuser also works at `https://YOUR_BACKEND_HOST/admin/` after
deployment. Vercel collects the admin's static assets during its build. Admin log
migrations have been applied locally against Supabase; no admin user is created
or password hardcoded automatically.

### Vercel dependency installation

Keep `pyproject.toml` and `uv.lock` in Git. Vercel prioritizes the project metadata
when it is present, so tool-only metadata without a `[project].dependencies` list
can result in `ModuleNotFoundError: No module named 'django'`. Runtime dependencies
are now explicitly declared and locked. No custom install command is required.
