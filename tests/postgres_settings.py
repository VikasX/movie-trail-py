"""Opt-in concurrency tests against a disposable LOCAL PostgreSQL database only."""

import environ
from django.core.exceptions import ImproperlyConfigured

from tests.settings import *  # noqa: F403

# Never reuse DATABASE_URL: that variable may point at the live Supabase project.
database = environ.Env().db("CINESCOPE_SECURITY_TEST_DATABASE_URL")
if (
    database["ENGINE"] != "django.db.backends.postgresql"
    or database.get("HOST") not in {"localhost", "127.0.0.1", "::1"}
    or not database.get("NAME", "").startswith("test_cinescope_")
):
    raise ImproperlyConfigured(
        "Security tests require a disposable local test_cinescope_* database."
    )
DATABASES = {"default": database}
