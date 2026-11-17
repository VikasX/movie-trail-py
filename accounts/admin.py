from django.contrib import admin

from accounts.models import UserPreferences


@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    list_display = ["user", "display_name", "display_language", "region"]
    search_fields = ["user__email", "display_name"]
