from django.contrib import admin

from catalog.models import TitleSnapshot


@admin.register(TitleSnapshot)
class TitleSnapshotAdmin(admin.ModelAdmin):
    list_display = ["media_type", "tmdb_id", "metadata_status", "fetched_at"]
    list_filter = ["media_type", "metadata_status"]
    readonly_fields = ["fetched_at"]
