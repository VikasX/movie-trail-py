# FILE PURPOSE: First routing stop: choose admin, product API, Google callback or API
# documentation.
# Import admin from django.contrib (Django framework/database/security helpers).
from django.contrib import admin

# Import include, path from django.urls (Django framework/database/security helpers).
from django.urls import include, path

# Import SpectacularAPIView, SpectacularSwaggerView from drf_spectacular.views (the named Python
# helper module).
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# Import callback from accounts.oauth (our account layer).
from accounts.oauth import callback

# Set urlpatterns: build an ordered list of 6 entries.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("core.urls")),
    path("api/v1/", include("common.urls")),
    path("accounts/google/login/callback/", callback, name="google_callback"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
