# CineScope backend security audit

Reviewed 2026-11-18. This covers the current backend source, contract, migrations,
deployment files, reachable Git history, installed dependencies, isolated tests,
and limited read-only production checks. No frontend changes, deployment, credential
rotation, production migration, permission change, or destructive production test
was performed during this audit.

## Follow-up after operator remediation

On 2026-11-18 the operator reported disabling the Data API and running the scoped
SQL. A subsequent read-only check against the configured CineScope database found
zero effective Data API-role grants on the audited Django tables, and PostgreSQL
connectivity succeeded. Dashboard Data API disablement is operator-reported.
The rate-limit migration is still pending. The runtime role still has CREATEDB,
CREATEROLE and BYPASSRLS, so the restricted-runtime-role action remains open.
The findings below record the original audit state and explain the fixes.

## Readiness and the production blocker

**The table-grant exposure was closed by operator remediation and verified read-only.
Release preparation still requires the rate-limit migration, restricted runtime
role, and the deployment verification described below.**
Local fixes do not close a separate database API that bypasses Django. The Supabase
dashboard's current Data API enablement/exposed-schema settings were not accessible
to this audit. No public Supabase key was used to retrieve private data, and no
evidence of exploitation is claimed.

## Findings and actual fixes

- **Critical — Supabase API-role grants, manual action required.** A read-only
  inspection found `anon` and `authenticated` grants on all 23 sensitive tables
  inspected, with RLS disabled. Affected examples include `auth_user`,
  `django_session`, `accounts_accounttoken`, `library_publicshare`,
  `library_savedtitle`, and `cinescope_cache`. Grants included SELECT, INSERT,
  UPDATE, DELETE and other privileges. If public is exposed through the Data API,
  these permissions allow access outside Django's authentication, ownership and
  CSRF checks. Cache modification is especially dangerous because Django's database
  cache deserializes stored values. No private rows or cache payloads were read.
  Disable the unused Data API, close grants on Django tables/sequences, and prevent
  new migrations from restoring automatic exposure. See the manual steps below.
- **High — overprivileged database runtime role, manual action required.** The
  configured role is not a superuser but has CREATEDB, CREATEROLE and BYPASSRLS.
  Compromise would have a larger impact than ordinary application data access.
  Separate a restricted runtime role from the migration/owner role; no permissions
  were changed automatically.
- **Medium — race-prone throttling, fixed locally.** `common/api.py` previously
  used DatabaseCache `incr()`, which does not guarantee atomic increments and can
  lose updates under concurrency or eviction. `common/throttling.py` and
  `catalog.RateLimitBucket` now use transactions, unique keys and row locks. Counter
  identities are HMAC digests rather than raw or readily guessed emails/IPs.
  Auth IP checks precede schema validation; normalized email limits remain shared
  across IPs. CSRF bootstrap is an ordinary read rather than a password attempt.
  `common/middleware.py` also limits Django admin password attempts.
- **Medium — credential/capability logging gaps, fixed locally.**
  `common/logging.py` now redacts final formatted exception output, bearer values,
  database URIs, session/CSRF cookie values, share URLs, OAuth query values, and
  configured secrets. `config/settings.py` routes Django's development-server
  logger through the same handler. This cannot sanitize Vercel/provider edge logs;
  operators must restrict their access and retention.
- **Medium — email failure account oracle and extra login hashing, fixed locally.**
  `accounts/services.py` previously returned a different status for a known reset
  recipient when SMTP failed, and performed an extra password hash for an unknown
  login address. Configured-provider send failures now produce the same generic
  accepted response, remove the unusable token, and emit a safe operator log.
  Initial registration is rolled back on delivery failure. Missing provider
  configuration still returns a uniform 503. Login now performs one verification
  or dummy hash. Verification is never bypassed. Synchronous delivery still has
  timing differences; no claim of perfectly constant-time email flows is made.
- **Medium — personalized response caching directive missing, fixed locally.**
  `common/middleware.py` now explicitly marks all authenticated responses and
  recommendation responses `private, no-store`, including personalized suggestions.
  Existing private account, share-capability and OAuth protections remain.
- **Low — unsafe deployment configuration accepted, hardened locally.**
  `config/settings.py` rejects wildcard/suffix production host allowances,
  non-HTTPS production origins, origins containing credentials/paths/queries, and
  untrusted TMDB base URLs. It retains Vercel-only forwarded-protocol trust and
  does not enable forwarded-host trust.
- **Low — malformed upstream fields and untrusted outbound links, fixed locally.**
  `catalog/services.py` normalizes malformed catalogue/configuration/detail data to
  safe 502 responses. Availability links are restricted to HTTPS on
  `www.themoviedb.org`; invalid links yield an unavailable section. Existing image
  and YouTube allowlists, fixed TMDB destinations, retries and request budgets remain.

No credential matches were found in the 10 reachable Git commits inspected beyond
the documented placeholder connection string. This is a targeted scan, not proof
that no secret has ever existed in an unreachable commit or external log. Local
environment files, virtualenv and tools are ignored. Credentials previously pasted
into chat were not copied into this report; operators should rotate shared secrets
before wider release. No credentials were replaced by this audit.

## Authentication and permissions

- **Google:** source and existing tests use allauth state, PKCE, server-side code
  exchange, verified provider email, and no silent linking on email collision.
  Provider tokens are not persisted or returned to React. The user reported a
  successful real login before this audit; this audit did not complete a fresh
  interactive Google login. Under the same-origin proxy, both public origins are
  `https://movie-trail-ui.vercel.app`, and the exact callback is
  `https://movie-trail-ui.vercel.app/accounts/google/login/callback/`.
- **Email:** local configuration currently has the console backend and no SMTP host
  or credentials. Production provider settings were not independently inspected.
  Registration/verification/reset behavior passes mocked tests; real production
  delivery remains unverified. All tokens are hashed, expiring, purpose-bound and
  consumed under locks. Password reset invalidates old authenticated sessions via
  Django's password/session hash check.
- **Cookies:** host-only, Path=/, Secure in production, HttpOnly and SameSite=Lax;
  14-day sessions. The deployed UI proxy issued a CSRF cookie with these protections
  during the read-only smoke check. Login/session rotation and server-side logout
  invalidation are tested locally. No cookie Domain workaround was introduced.
- **CSRF:** Django middleware remains enabled; the DRF boundary explicitly checks
  guest unsafe requests as well. Tests cover missing/invalid tokens and an untrusted
  Origin even with a valid token. Refresh the CSRF token after OAuth/login.
- **CORS:** exact allowlist, credentials enabled, no wildcard origin grant. The UI
  proxy is same-origin in the browser; CORS alone is not authorization or CSRF
  protection. Preserve both `/api/*` and `/accounts/*` proxy routes.
- **Logout:** CSRF-protected POST, server-side session deletion, local test verified.

The OpenAPI contract retains **36 operations**: 17 session-required operations and
19 public/session-independent operations, counting the internal Google callback.
The public recommendation operation additionally requires login for personalized
mode. Public logout is idempotent and still requires CSRF.

Protected operations derive the owner from the session: profile GET/PATCH; recent
GET/PUT; library GET/PUT/DELETE; collection list/create/detail/update/delete;
membership PUT/DELETE; sharing PUT/DELETE; and guest-sync POST. Two-account tests
exercise every custom-collection action, independent watched/saved mutations,
private snapshots, and sync-receipt isolation. Another owner's object returns 404.
The same sync UUID in two accounts creates independent receipts, as the contract's
`unique(user, sync_id)` requires; it never replays the first user's result.

Public health/database health/sample routes remain bounded and read-only. Metadata,
discovery, people search, title details and public shares expose no private account
state. Live share capability is checked before snapshot access, including after
revocation. Tokens are random, hash-indexed and encrypted for owner recovery;
re-enabling sharing rotates the token. Django admin is outside the product endpoint
count and requires active staff authentication and Django model permissions.

## Verification

- The final full test run completed with **140 passed and 1 skipped**. The skipped
  case requires isolated PostgreSQL concurrency testing. Ruff lint/format,
  migration consistency and OpenAPI structure/reference validation passed. The
  contract still contains 36 operations.
- Original regression tests and added security tests use an isolated SQLite
  database, locmem cache and mocked TMDB/Google calls. Successful API responses are
  checked against the OpenAPI schemas by the existing test fixture.
- Security coverage includes every private operation without a session; ownership,
  CSRF, malformed/oversized sync, receipt/cache isolation, unsafe configuration,
  pagination/filter bounds, provider failures, log redaction, email failures,
  authentication/admin throttling, secure cookies, session/CSRF rotation and logout.
- A separate concurrency test requires disposable **local** PostgreSQL. The default
  SQLite run skips it because SQLite cannot prove PostgreSQL row-lock behavior.
  `tests/postgres_settings.py` refuses remote hosts and database names outside
  `test_cinescope_*`; it never uses production `DATABASE_URL` for tests.
- Django system checks pass. Deploy checks retain only W005/W021: subdomain HSTS and
  preload are intentionally off because these deployments do not control every
  subdomain and have no verified preload commitment. HTTPS redirect, Secure cookies,
  nosniff, frame denial and one-year HSTS remain enabled in production settings.
- Ruff lint/format and migration consistency are checked. The new migration only
  creates `catalog_ratelimitbucket`; no existing data or table is rewritten.
- The final `pip-audit` scan found no known vulnerabilities in 77 installed packages
  (including the audit/validation tools); no dependency upgrade was indicated.
  Scanner results are point-in-time advisories.
- Live read-only smoke checks returned 200 for backend health, proxied discovery,
  title details/trailers, CSRF bootstrap and database health; anonymous `/me/`
  correctly returned 401. These checked the currently deployed version, not the
  unshipped hardening changes. No production mutations were tested.
- Direct database inspection confirmed client-to-session-pooler TLS. `pg_stat_ssl`
  describes the pooler-to-database hop and reported false; it does not contradict
  libpq's client TLS status. `sslmode=require` encrypts the client connection but
  does not provide the explicit CA/hostname verification of `verify-full`.

## Required operator actions before release

1. **Contain the Supabase API exposure first.** Since this app uses Django ORM and
   not Supabase REST/GraphQL, disable the Data API in Supabase's Data API settings
   if nothing else needs it. Turn off automatic exposure for new tables. If the
   project serves other apps, remove the Django tables from public API access
   without disabling services they need. Review and manually execute
   [the scoped SQL](sql/supabase_restrict_data_api.sql) to revoke existing table
   and sequence grants and future grants for the migration role. The script is
   not a Django migration and has **not** been executed. Its verification query
   must return zero rows. New migrations must not reopen these grants.
   If retaining the Data API, also review exposed views, security-definer RPCs and
   inherited grants; the scoped table/sequence script does not audit those routes.
2. Inspect Supabase Data API/access logs to assess whether sensitive tables were
   reachable or accessed. If exposure is confirmed or cannot be bounded, treat it
   as an incident: rotate affected secrets, invalidate sessions and one-time/share
   capabilities, and review password/account changes. Do not silently delete user
   data. No exploitation or credential exfiltration was verified in this audit.
3. Provision a restricted runtime database role without CREATEDB, CREATEROLE or
   BYPASSRLS. Grant only schema usage, required Django-table DML and sequence access;
   keep DDL under a separate migration role. Test with staging before switching
   the runtime `DATABASE_URL`. Review network restrictions and enable CA/hostname
   verification with the provider-supported certificate setup where feasible.
4. Review the new migration with the trusted migration credentials, then apply it
   **before** shipping this version. Never run migration commands on each request:

   ```powershell
   .venv\Scripts\python.exe manage.py migrate --plan
   .venv\Scripts\python.exe manage.py migrate
   ```

   These commands use the environment's `DATABASE_URL`: confirm the intended target
   and normal backup/rollback procedure first. No production migration was applied
   by this audit. Apply the grant restrictions to the new table too, or prevent
   those grants through migration-role defaults before it is created.
5. Keep Vercel `DEBUG=False`, a strong unique `SECRET_KEY`, stable
   `SHARE_TOKEN_ENCRYPTION_KEY`, exact backend `ALLOWED_HOSTS`, and the existing
   server-side TMDB/Google secrets. For the proxy topology set both
   `FRONTEND_PUBLIC_ORIGIN` and `BACKEND_PUBLIC_ORIGIN` to the UI origin; set exact
   HTTPS `CSRF_TRUSTED_ORIGINS` and `CORS_ALLOWED_ORIGINS`. Do not add `/api/docs`
   or a callback path to an origin. Redeploy manually after environment updates.
6. To enable email, verify a sender/domain with a transactional provider, configure
   `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `EMAIL_HOST`,
   `EMAIL_PORT=587`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS=True`,
   and the verified `DEFAULT_FROM_EMAIL`. Use provider-specific credentials and
   STARTTLS settings. Configure SPF/DKIM as the provider requires. Test real
   verification and reset delivery without disabling mandatory verification.
   Monitor delivery-failure logs: a generic 202 does not prove mail was delivered.
7. Run `python manage.py cleanup_expired` regularly from a trusted operator job
   outside request handling; it now prunes expired rate buckets too. Also run
   Django's `clearsessions`. No Redis, Celery, paid service or worker was added.
   The database cache can retain expired physical rows until normal culling or
   scheduled database maintenance; avoid a blanket cache clear during active
   sessions because it invalidates snapshots.
8. Verify direct and proxied client-IP behavior and Vercel edge abuse rules. Only
   the Vercel-supplied IP is trusted when running on Vercel; an extra proxy can
   collapse multiple users into one IP allowance. Do not trust a browser-provided
   forwarded chain as a workaround. Distributed attackers, fixed-window bursts,
   unauthenticated database-health traffic and platform-level denial of service
   still need edge protection/monitoring. No paid infrastructure was introduced.

The TMDB client's 15-second budget is checked before attempts and after completed
responses. HTTPX read timeouts apply to individual I/O waits; they are not a hard
whole-response timer. The Vercel function's configured 30-second limit remains the
outer boundary. No arbitrary-host fetch, unbounded list refill or fan-out was added.

To run the optional PostgreSQL test, provision a disposable local server/database
with an isolated role allowed to create test databases, set
`CINESCOPE_SECURITY_TEST_DATABASE_URL` to its `test_cinescope_*` database URI, and run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_security.py --ds=tests.postgres_settings
```

Do not point this setting at Supabase or any production database. After containment,
repeat authenticated Google login, save/watch/collection/share/revoke/logout and
real email flows on staging, then smoke-check the released deployment. Source tests
and a working public health check do not prove production security.

## References

- [Supabase: securing the Data API](https://supabase.com/docs/guides/api/securing-your-api)
  explains disabling unused Data APIs and removing automatic/existing grants.
- [Django: caching](https://docs.djangoproject.com/en/dev/topics/cache/)
  documents that cache increment operations are not guaranteed atomic.
- [Vercel request headers](https://vercel.com/docs/headers/request-headers)
  describes platform-forwarded IP/protocol headers and proxy limitations.
