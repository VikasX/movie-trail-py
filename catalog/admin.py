# FILE PURPOSE: Shows saved/reference metadata snapshots to staff, without displaying API
# credentials.
# Import admin from django.contrib (Django framework/database/security helpers).
from django.contrib import admin

# Import TitleSnapshot from catalog.models (our TMDB/normalization layer).
from catalog.models import TitleSnapshot


@admin.register(TitleSnapshot)
class TitleSnapshotAdmin(admin.ModelAdmin):
    # Set list_display: build an ordered list of 4 entries.
    list_display = ["media_type", "tmdb_id", "metadata_status", "fetched_at"]
    # Set list_filter: build an ordered list of 2 entries.
    list_filter = ["media_type", "metadata_status"]
    # Set readonly_fields: build an ordered list of 1 entries.
    readonly_fields = ["fetched_at"]
