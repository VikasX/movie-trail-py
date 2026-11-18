# FILE PURPOSE: Lets staff inspect and edit user preferences in Django admin.
# Import admin from django.contrib (Django framework/database/security helpers).
from django.contrib import admin

# Import UserPreferences from accounts.models (our account layer).
from accounts.models import UserPreferences


@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    # Set list_display: build an ordered list of 4 entries.
    list_display = ["user", "display_name", "display_language", "region"]
    # Set search_fields: build an ordered list of 2 entries.
    search_fields = ["user__email", "display_name"]
