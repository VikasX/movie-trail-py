"""Load production settings only after isolating tests from local credentials."""

import os
import secrets

os.environ["SECRET_KEY"] = secrets.token_urlsafe(64)
os.environ["DEBUG"] = "False"
os.environ["ALLOWED_HOSTS"] = "testserver,localhost"
os.environ["DATABASE_URL"] = "postgresql://unit_test@127.0.0.1:1/unit_test?sslmode=require"
os.environ["CORS_ALLOWED_ORIGINS"] = "https://frontend.example.com"
os.environ["CSRF_TRUSTED_ORIGINS"] = "https://frontend.example.com"

from config.settings import *  # noqa: E402, F403

# Isolated disposable test DB; never connects to Supabase. Production remains PostgreSQL.
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
API_THROTTLING_ENABLED = False
FRONTEND_PUBLIC_ORIGIN = "https://frontend.example.com"
BACKEND_PUBLIC_ORIGIN = "https://testserver"
from cryptography.fernet import Fernet  # noqa: E402

SHARE_TOKEN_ENCRYPTION_KEY = Fernet.generate_key().decode()
