from django.contrib import admin

from core.models import SampleRecord

admin.site.site_header = "CineScope Administration"
admin.site.site_title = "CineScope Admin"
admin.site.index_title = "Manage CineScope"


@admin.register(SampleRecord)
class SampleRecordAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "message"]
    search_fields = ["name", "message"]
