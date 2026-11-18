# FILE PURPOSE: Product route map: each URL/method points to an account, catalogue or library
# service.
# Import path from django.urls (Django framework/database/security helpers).
from django.urls import path

# Import oauth from accounts (our account layer).
from accounts import oauth

# Import services from accounts (our account layer).
from accounts import services as accounts

# Import recommendations from catalog (our TMDB/normalization layer).
from catalog import recommendations

# Import services from catalog (our TMDB/normalization layer).
from catalog import services as catalog

# Import endpoint from common.api (our shared API layer).
from common.api import endpoint

# Import services from library (our personal-library layer).
from library import services as library

# Import sync from library.sync (our personal-library layer).
from library.sync import sync

# Set app_name: use the fixed value 'api'.
app_name = "api"


# Attach the real Django URL spelling to its contract spelling and service handlers.
def route(url, contract, **handlers):
    # INPUTS TO THIS FUNCTION: url = argument supplied by the caller; contract = argument supplied
    # by the caller.
    # Return the result to the caller: call path with the inputs shown; its definition explains
    # the checks, side effects and return value.
    return path(
        url, endpoint("/api/v1/" + contract, **handlers), name=contract.replace("/", "-").strip("-")
    )


# Set urlpatterns: build an ordered list of 25 entries.
urlpatterns = [
    route("metadata/", "metadata/", get=catalog.metadata),
    route("auth/csrf/", "auth/csrf/", get=accounts.csrf),
    route("auth/register/", "auth/register/", post=accounts.register),
    route("auth/login/", "auth/login/", post=accounts.login),
    route("auth/logout/", "auth/logout/", post=accounts.logout),
    route("auth/email/verify/", "auth/email/verify/", post=accounts.consume_token),
    route("auth/email/verification/", "auth/email/verification/", post=accounts.send_instructions),
    route("auth/password/reset/", "auth/password/reset/", post=accounts.send_instructions),
    route(
        "auth/password/reset/confirm/", "auth/password/reset/confirm/", post=accounts.consume_token
    ),
    route("auth/oauth/start/", "auth/oauth/start/", post=oauth.start),
    route("me/", "me/", get=accounts.me, patch=accounts.me),
    route("people/", "people/", get=catalog.search_people),
    route("titles/", "titles/", get=catalog.discover),
    route("recommendations/", "recommendations/", post=recommendations.recommend),
    route(
        "titles/<str:media_type>/<int:tmdb_id>/",
        "titles/{media_type}/{tmdb_id}/",
        get=catalog.details,
    ),
    route("me/recent/", "me/recent/", get=library.recent),
    route(
        "me/recent/<str:media_type>/<int:tmdb_id>/",
        "me/recent/{media_type}/{tmdb_id}/",
        put=library.record_recent,
    ),
    route("me/library/", "me/library/", get=library.library),
    route(
        "me/library/<str:media_type>/<int:tmdb_id>/",
        "me/library/{media_type}/{tmdb_id}/",
        put=library.saved_title,
        delete=library.saved_title,
    ),
    route("me/collections/", "me/collections/", get=library.collections, post=library.collections),
    route(
        "me/collections/<str:collection_id>/",
        "me/collections/{collection_id}/",
        get=library.collection_detail,
        patch=library.collection_detail,
        delete=library.collection_detail,
    ),
    route(
        "me/collections/<str:collection_id>/items/<str:media_type>/<int:tmdb_id>/",
        "me/collections/{collection_id}/items/{media_type}/{tmdb_id}/",
        put=library.membership,
        delete=library.membership,
    ),
    route(
        "me/collections/<str:collection_id>/sharing/",
        "me/collections/{collection_id}/sharing/",
        put=library.sharing,
        delete=library.sharing,
    ),
    route("shared/<str:token>/", "shared/{token}/", get=library.shared),
    route("me/guest-sync/", "me/guest-sync/", post=sync),
]
