import copy
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from library.models import (
    Collection,
    CollectionMembership,
    GuestCollectionMapping,
    PublicShare,
    RecentTitle,
    SavedTitle,
    SyncReceipt,
)


def test_library_save_watch_unsave_and_identity(api, user, title):
    url = "/api/v1/me/library/movie/550/"
    assert api.put(url, {"watched": False}, format="json", secure=True).status_code == 200
    watched = api.put(url, {"watched": True}, format="json", secure=True).json()
    assert watched["watched_at"]
    assert (
        api.put(url, {"watched": True}, format="json", secure=True).json()["watched_at"]
        == watched["watched_at"]
    )
    assert api.get("/api/v1/me/library/", secure=True).json()["count"] == 1
    assert api.get("/api/v1/me/library/?watched=true", secure=True).json()["count"] == 1
    assert api.get("/api/v1/me/library/?watched=false", secure=True).json()["count"] == 0
    assert SavedTitle.objects.filter(user=user).count() == 1
    assert api.delete(url, secure=True).status_code == 204
    assert api.delete(url, secure=True).status_code == 204


def test_collections_memberships_ownership_and_automatic(api, user, title):
    first = api.post("/api/v1/me/collections/", {"name": "Weekend"}, format="json", secure=True)
    assert first.status_code == 201
    cid = first.json()["id"]
    assert (
        api.post(
            "/api/v1/me/collections/", {"name": "weekend"}, format="json", secure=True
        ).status_code
        == 409
    )
    url = f"/api/v1/me/collections/{cid}/items/movie/550/"
    assert api.put(url, secure=True).status_code == 200
    assert api.put(url, secure=True).status_code == 200
    assert SavedTitle.objects.filter(user=user).count() == 1
    assert CollectionMembership.objects.count() == 1
    response = api.get("/api/v1/me/collections/", secure=True)
    ids = {r["id"] for r in response.json()["results"]}
    assert {
        "auto:movies",
        "auto:decade:2020",
        "auto:highly-rated",
        "auto:genre:animation",
        "auto:genre:family",
    }.issubset(ids)
    assert Collection.objects.count() == 1
    assert (
        api.patch(
            "/api/v1/me/collections/auto:movies/", {"name": "bad"}, format="json", secure=True
        ).status_code
        == 403
    )
    assert api.get("/api/v1/me/collections/auto:movies/", secure=True).json()["items"]["count"] == 1
    assert APIClient().get(f"/api/v1/me/collections/{cid}/", secure=True).status_code == 401
    other = type(user).objects.create_user(username="other", email="other@example.com")
    other_collection = Collection.objects.create(user=other, name="Private")
    assert api.get(f"/api/v1/me/collections/{other_collection.pk}/", secure=True).status_code == 404
    assert api.delete(url, secure=True).status_code == 204
    assert SavedTitle.objects.count() == 1  # Removing membership retains saved state.
    api.put(url, secure=True)
    assert api.delete("/api/v1/me/library/movie/550/", secure=True).status_code == 204
    assert CollectionMembership.objects.count() == 0
    assert Collection.objects.count() == 2


def test_sharing_is_frontend_url_and_revocable_per_page(api, user, title):
    collection = Collection.objects.create(user=user, name="Public")
    saved = SavedTitle.objects.create(user=user, title=title)
    CollectionMembership.objects.create(collection=collection, saved_title=saved)
    url = f"/api/v1/me/collections/{collection.pk}/sharing/"
    first = api.put(url, secure=True)
    assert first.status_code == 200
    assert first.json()["url"].startswith("https://frontend.example.com/shared/")
    assert api.put(url, secure=True).json() == first.json()
    token = first.json()["url"].rsplit("/", 1)[-1]
    share = PublicShare.objects.get(collection=collection)
    assert token not in share.encrypted_token and token not in share.token_hash
    public = APIClient()
    response = public.get(f"/api/v1/shared/{token}/", secure=True)
    assert response.status_code == 200
    assert set(response.json()) == {"name", "items"}
    assert "email" not in response.content.decode() and "watched" not in response.content.decode()
    snapshot = response.json()["items"]["meta"]["snapshot"]
    assert api.delete(url, secure=True).status_code == 204
    assert (
        public.get(f"/api/v1/shared/{token}/?snapshot={snapshot}", secure=True).status_code == 404
    )
    assert api.put(url, secure=True).json()["url"] != first.json()["url"]


def sync_payload(title):
    now = timezone.now().isoformat()
    ref = {"media_type": title.media_type, "tmdb_id": title.tmdb_id}
    return {
        "sync_id": str(uuid.uuid4()),
        "guest_id": str(uuid.uuid4()),
        "saved_titles": [{**ref, "watched": True, "saved_at": now, "watched_at": now}],
        "collections": [{"client_id": str(uuid.uuid4()), "name": "Weekend", "items": [ref]}],
    }


def test_guest_sync_idempotency_merges_and_tombstone(api, user, title):
    SavedTitle.objects.create(user=user, title=title)
    Collection.objects.create(user=user, name="Weekend")
    payload = sync_payload(title)
    first = api.post("/api/v1/me/guest-sync/", payload, format="json", secure=True)
    assert first.status_code == 200, first.json()
    assert first.json()["saved_merged"] == 1 and first.json()["saved_created"] == 0
    assert SavedTitle.objects.get(user=user).watched is True
    assert Collection.objects.filter(name="Weekend (Imported 2)").exists()
    assert (
        api.post("/api/v1/me/guest-sync/", payload, format="json", secure=True).json()
        == first.json()
    )
    assert CollectionMembership.objects.count() == 1 and SyncReceipt.objects.count() == 1
    changed = copy.deepcopy(payload)
    changed["saved_titles"][0]["watched"] = False
    changed["saved_titles"][0]["watched_at"] = None
    assert (
        api.post("/api/v1/me/guest-sync/", changed, format="json", secure=True).status_code == 409
    )
    cid = first.json()["collection_mappings"][0]["collection_id"]
    api.delete(f"/api/v1/me/collections/{cid}/", secure=True)
    assert GuestCollectionMapping.objects.get().collection is None
    payload["sync_id"] = str(uuid.uuid4())
    assert (
        api.post("/api/v1/me/guest-sync/", payload, format="json", secure=True).status_code == 409
    )
    assert Collection.objects.count() == 1


def test_guest_sync_validation_and_no_partial_writes(api, user, title):
    payload = sync_payload(title)
    duplicate = copy.deepcopy(payload)
    duplicate["saved_titles"] *= 2
    assert (
        api.post("/api/v1/me/guest-sync/", duplicate, format="json", secure=True).status_code == 400
    )
    payload["saved_titles"][0]["watched_at"] = (timezone.now() + timedelta(days=1)).isoformat()
    assert (
        api.post("/api/v1/me/guest-sync/", payload, format="json", secure=True).status_code == 400
    )
    payload = sync_payload(title)
    payload["collections"][0]["items"].append({"media_type": "movie", "tmdb_id": 999})
    from common.errors import APIError

    with patch("library.sync.resolve_title", side_effect=APIError("unavailable", "private", 503)):
        response = api.post("/api/v1/me/guest-sync/", payload, format="json", secure=True)
    assert response.status_code == 503
    assert not SavedTitle.objects.exists() and not Collection.objects.exists()
    assert not SyncReceipt.objects.exists()


def test_recent_upsert_does_not_save(api, user, title):
    url = "/api/v1/me/recent/movie/550/"
    assert api.put(url, secure=True).status_code == 200
    assert api.put(url, secure=True).status_code == 200
    assert RecentTitle.objects.filter(user=user).count() == 1
    assert not SavedTitle.objects.exists()
    assert api.get("/api/v1/me/recent/", secure=True).json()["count"] == 1


@pytest.mark.parametrize(
    "url", ["/api/v1/me/", "/api/v1/me/library/", "/api/v1/me/collections/", "/api/v1/me/recent/"]
)
def test_account_routes_require_login(url):
    assert APIClient().get(url, secure=True).status_code == 401
