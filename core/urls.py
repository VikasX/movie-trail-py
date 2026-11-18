# FILE PURPOSE: Connects the original health/sample URL paths to their view classes.
# Import path from django.urls (Django framework/database/security helpers).
from django.urls import path

# Import DatabaseHealthView, HealthView, SampleRecordView from core.views (the named Python helper
# module).
from core.views import DatabaseHealthView, HealthView, SampleRecordView

# Set app_name: use the fixed value 'core'.
app_name = "core"
# Set urlpatterns: build an ordered list of 3 entries.
urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("health/db/", DatabaseHealthView.as_view(), name="health-db"),
    path("samples/", SampleRecordView.as_view(), name="samples"),
]
