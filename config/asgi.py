# FILE PURPOSE: Alternative Django entry point for an ASGI-compatible server.
"""Standard ASGI entry point for servers that support ASGI."""

# Import os so the code below can use that module namespace.
import os

# Import get_asgi_application from django.core.asgi (Django framework/database/security helpers).
from django.core.asgi import get_asgi_application

# Reuse the existing entry, or create the provided starting value only if absent.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
# Set application: call get_asgi_application with the inputs shown; its definition explains the
# checks, side effects and return value.
application = get_asgi_application()
