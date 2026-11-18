# FILE PURPOSE: Shows the demonstration table in Django admin and names the admin site.
# Import admin from django.contrib (Django framework/database/security helpers).
from django.contrib import admin

# Import SampleRecord from core.models (the named Python helper module).
from core.models import SampleRecord

# Set admin.site.site_header: use the fixed value 'CineScope Administration'.
admin.site.site_header = "CineScope Administration"
# Set admin.site.site_title: use the fixed value 'CineScope Admin'.
admin.site.site_title = "CineScope Admin"
# Set admin.site.index_title: use the fixed value 'Manage CineScope'.
admin.site.index_title = "Manage CineScope"


@admin.register(SampleRecord)
class SampleRecordAdmin(admin.ModelAdmin):
    # Set list_display: build an ordered list of 3 entries.
    list_display = ["id", "name", "message"]
    # Set search_fields: build an ordered list of 2 entries.
    search_fields = ["name", "message"]
