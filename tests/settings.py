# FILE PURPOSE: Test-only settings. Uses a disposable SQLite database instead of the real
# Supabase database.
"""Load production settings only after isolating tests from local credentials."""

# Import os so the code below can use that module namespace.
import os

# Import secrets so the code below can use that module namespace.
import secrets

# Set os.environ['SECRET_KEY']: generate cryptographically strong random URL-safe text, not a
# predictable sequence.
os.environ["SECRET_KEY"] = secrets.token_urlsafe(64)
# Set os.environ['DEBUG']: use the fixed value 'False'.
os.environ["DEBUG"] = "False"
# Set os.environ['ALLOWED_HOSTS']: use the fixed value 'testserver,localhost'.
os.environ["ALLOWED_HOSTS"] = "testserver,localhost"
# Set os.environ['DATABASE_URL']: use the fixed value
# 'postgresql://unit_test@127.0.0.1:1/unit_test?sslmode=require'.
os.environ["DATABASE_URL"] = "postgresql://unit_test@127.0.0.1:1/unit_test?sslmode=require"
# Set os.environ['CORS_ALLOWED_ORIGINS']: use the fixed value 'https://frontend.example.com'.
os.environ["CORS_ALLOWED_ORIGINS"] = "https://frontend.example.com"
# Set os.environ['CSRF_TRUSTED_ORIGINS']: use the fixed value 'https://frontend.example.com'.
os.environ["CSRF_TRUSTED_ORIGINS"] = "https://frontend.example.com"
os.environ["FRONTEND_PUBLIC_ORIGIN"] = "https://frontend.example.com"
os.environ["BACKEND_PUBLIC_ORIGIN"] = "https://testserver"

# Import * from config.settings (the named Python helper module).
from config.settings import *  # noqa: E402, F403

# Isolated disposable test DB; never connects to Supabase. Production remains PostgreSQL.
# Set DATABASES: build a dictionary with named fields such as default.
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
# Set CACHES: build a dictionary with named fields such as default.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
# Set EMAIL_BACKEND: use the fixed value 'django.core.mail.backends.locmem.EmailBackend'.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
# Set API_THROTTLING_ENABLED: use the boolean False.
API_THROTTLING_ENABLED = False
# Set FRONTEND_PUBLIC_ORIGIN: use the fixed value 'https://frontend.example.com'.
FRONTEND_PUBLIC_ORIGIN = "https://frontend.example.com"
# Set BACKEND_PUBLIC_ORIGIN: use the fixed value 'https://testserver'.
BACKEND_PUBLIC_ORIGIN = "https://testserver"
# Import Fernet from cryptography.fernet (authenticated encryption support).
from cryptography.fernet import Fernet  # noqa: E402

# Set SHARE_TOKEN_ENCRYPTION_KEY: convert bytes back into text after decryption or another bytes-
# producing operation.
SHARE_TOKEN_ENCRYPTION_KEY = Fernet.generate_key().decode()
