from django.urls import path

from accounts import oauth
from accounts import services as accounts
from catalog import recommendations
from catalog import services as catalog
from common.api import endpoint
from library import services as library
from library.sync import sync

app_name = "api"


def route(url, contract, **handlers):
    return path(
        url, endpoint("/api/v1/" + contract, **handlers), name=contract.replace("/", "-").strip("-")
    )


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
