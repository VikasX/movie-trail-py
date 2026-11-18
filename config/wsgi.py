# FILE PURPOSE: Starts the Django application for WSGI hosts, including this Vercel deployment.
"""WSGI entry point, also loaded by Vercel's native Django preset."""

# Import os so the code below can use that module namespace.
import os

# Import get_wsgi_application from django.core.wsgi (Django framework/database/security helpers).
from django.core.wsgi import get_wsgi_application

# Reuse the existing entry, or create the provided starting value only if absent.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
# Set application: call get_wsgi_application with the inputs shown; its definition explains the
# checks, side effects and return value.
application = get_wsgi_application()
