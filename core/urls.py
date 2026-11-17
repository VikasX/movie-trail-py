from django.urls import path

from core.views import DatabaseHealthView, HealthView, SampleRecordView

app_name = "core"
urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("health/db/", DatabaseHealthView.as_view(), name="health-db"),
    path("samples/", SampleRecordView.as_view(), name="samples"),
]
