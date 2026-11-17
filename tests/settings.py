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
