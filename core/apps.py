# FILE PURPOSE: Registers the small original core app with Django.
# Import AppConfig from django.apps (Django framework/database/security helpers).
from django.apps import AppConfig


class CoreConfig(AppConfig):
    # Set default_auto_field: use the fixed value 'django.db.models.BigAutoField'.
    default_auto_field = "django.db.models.BigAutoField"
    # name holds a display name or field label; collection names are trimmed and checked for
    # allowed length. Next, use the fixed value 'core'.
    name = "core"
