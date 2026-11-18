# FILE PURPOSE: Tests saved/watched data, ownership, collections, share revocation and guest
# merges.
# Import copy so the code below can use that module namespace.
import copy

# Import uuid so the code below can use that module namespace.
import uuid

# Import timedelta from datetime (the named Python helper module).
from datetime import timedelta

# Import patch from unittest.mock (the named Python helper module).
from unittest.mock import patch

# Import pytest so the code below can use that module namespace.
import pytest

# Import timezone from django.utils (Django framework/database/security helpers).
from django.utils import timezone

# Import APIClient from rest_framework.test (DRF request/response helpers).
from rest_framework.test import APIClient

# Import Collection, CollectionMembership, GuestCollectionMapping, PublicShare, RecentTitle,
# SavedTitle, SyncReceipt from library.models (our personal-library layer).
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
    # INPUTS TO THIS FUNCTION: api = argument supplied by the caller; user = Django account; title
    # = argument supplied by the caller.
    # url holds the complete public navigation URL built from the approved configured origin.
    # Next, use the fixed value '/api/v1/me/library/movie/550/'.
    url = "/api/v1/me/library/movie/550/"
    # Test expectation: api.put(url, {'watched': False}, format='json', secure=True).status_code
    # == 200. If false, pytest reports a failure at this line.
    assert api.put(url, {"watched": False}, format="json", secure=True).status_code == 200
    # watched holds the new watched boolean requested for a saved title. Next, decode the HTTP
    # response JSON into ordinary Python dictionaries/lists.
    watched = api.put(url, {"watched": True}, format="json", secure=True).json()
    # Test expectation: watched['watched_at']. If false, pytest reports a failure at this line.
    assert watched["watched_at"]
    # Test expectation: api.put(url, {'watched': True}, format='json',
    # secure=True).json()['watched_at'] == watched['watched_at']. If false, pytest reports a
    # failure at this line.
    assert (
        api.put(url, {"watched": True}, format="json", secure=True).json()["watched_at"]
        == watched["watched_at"]
    )
    # Test expectation: api.get('/api/v1/me/library/', secure=True).json()['count'] == 1. If
    # false, pytest reports a failure at this line.
    assert api.get("/api/v1/me/library/", secure=True).json()["count"] == 1
    # Test expectation: api.get('/api/v1/me/library/?watched=true', secure=True).json()['count']
    # == 1. If false, pytest reports a failure at this line.
    assert api.get("/api/v1/me/library/?watched=true", secure=True).json()["count"] == 1
    # Test expectation: api.get('/api/v1/me/library/?watched=false', secure=True).json()['count']
    # == 0. If false, pytest reports a failure at this line.
    assert api.get("/api/v1/me/library/?watched=false", secure=True).json()["count"] == 0
    # Test expectation: SavedTitle.objects.filter(user=user).count() == 1. If false, pytest
    # reports a failure at this line.
    assert SavedTitle.objects.filter(user=user).count() == 1
    # Test expectation: api.delete(url, secure=True).status_code == 204. If false, pytest reports
    # a failure at this line.
    assert api.delete(url, secure=True).status_code == 204
    # Test expectation: api.delete(url, secure=True).status_code == 204. If false, pytest reports
    # a failure at this line.
    assert api.delete(url, secure=True).status_code == 204


def test_collections_memberships_ownership_and_automatic(api, user, title):
    # INPUTS TO THIS FUNCTION: api = argument supplied by the caller; user = Django account; title
    # = argument supplied by the caller.
    # Set first: call api.post with the inputs shown; its definition explains the checks, side
    # effects and return value.
    first = api.post("/api/v1/me/collections/", {"name": "Weekend"}, format="json", secure=True)
    # Test expectation: first.status_code == 201. If false, pytest reports a failure at this line.
    assert first.status_code == 201
    # Set cid: read the entry indexed by 'id' from first.json().
    cid = first.json()["id"]
    # Test expectation: api.post('/api/v1/me/collections/', {'name': 'weekend'}, format='json',
    # secure=True).status_code == 409. If false, pytest reports a failure at this line.
    assert (
        api.post(
            "/api/v1/me/collections/", {"name": "weekend"}, format="json", secure=True
        ).status_code
        == 409
    )
    # url holds the complete public navigation URL built from the approved configured origin.
    # Next, evaluate f'/api/v1/me/collections/{cid}/items/movie/550/'.
    url = f"/api/v1/me/collections/{cid}/items/movie/550/"
    # Test expectation: api.put(url, secure=True).status_code == 200. If false, pytest reports a
    # failure at this line.
    assert api.put(url, secure=True).status_code == 200
    # Test expectation: api.put(url, secure=True).status_code == 200. If false, pytest reports a
    # failure at this line.
    assert api.put(url, secure=True).status_code == 200
    # Test expectation: SavedTitle.objects.filter(user=user).count() == 1. If false, pytest
    # reports a failure at this line.
    assert SavedTitle.objects.filter(user=user).count() == 1
    # Test expectation: CollectionMembership.objects.count() == 1. If false, pytest reports a
    # failure at this line.
    assert CollectionMembership.objects.count() == 1
    # response holds the response produced by the next handler or external HTTP request. Next,
    # look up a named setting/value or make the indicated GET call; the surrounding object
    # determines which.
    response = api.get("/api/v1/me/collections/", secure=True)
    # Set ids: build a set of distinct values for each r in response.json()['results'].
    ids = {r["id"] for r in response.json()["results"]}
    # Test expectation: {'auto:movies', 'auto:decade:2020', 'auto:highly-rated',
    # 'auto:genre:animation', 'auto:genre:family'}.issubset(ids). If false, pytest reports a
    # failure at this line.
    assert {
        "auto:movies",
        "auto:decade:2020",
        "auto:highly-rated",
        "auto:genre:animation",
        "auto:genre:family",
    }.issubset(ids)
    # Test expectation: Collection.objects.count() == 1. If false, pytest reports a failure at
    # this line.
    assert Collection.objects.count() == 1
    # Test expectation: api.patch('/api/v1/me/collections/auto:movies/', {'name': 'bad'},
    # format='json', secure=True).status_code == 403. If false, pytest reports a failure at this
    # line.
    assert (
        api.patch(
            "/api/v1/me/collections/auto:movies/", {"name": "bad"}, format="json", secure=True
        ).status_code
        == 403
    )
    # Test expectation: api.get('/api/v1/me/collections/auto:movies/',
    # secure=True).json()['items']['count'] == 1. If false, pytest reports a failure at this line.
    assert api.get("/api/v1/me/collections/auto:movies/", secure=True).json()["items"]["count"] == 1
    # Test expectation: APIClient().get(f'/api/v1/me/collections/{cid}/', secure=True).status_code
    # == 401. If false, pytest reports a failure at this line.
    assert APIClient().get(f"/api/v1/me/collections/{cid}/", secure=True).status_code == 401
    # Set other: call type(user).objects.create_user with the inputs shown; its definition
    # explains the checks, side effects and return value.
    other = type(user).objects.create_user(username="other", email="other@example.com")
    # Set other_collection: insert a new row and receive the created model object.
    other_collection = Collection.objects.create(user=other, name="Private")
    # Test expectation: api.get(f'/api/v1/me/collections/{other_collection.pk}/',
    # secure=True).status_code == 404. If false, pytest reports a failure at this line.
    assert api.get(f"/api/v1/me/collections/{other_collection.pk}/", secure=True).status_code == 404
    # Test expectation: api.delete(url, secure=True).status_code == 204. If false, pytest reports
    # a failure at this line.
    assert api.delete(url, secure=True).status_code == 204
    # Test expectation: SavedTitle.objects.count() == 1. If false, pytest reports a failure at
    # this line.
    assert SavedTitle.objects.count() == 1  # Removing membership retains saved state.
    # Call api.put with the inputs shown; its definition explains the checks, side effects and
    # return value.
    api.put(url, secure=True)
    # Test expectation: api.delete('/api/v1/me/library/movie/550/', secure=True).status_code ==
    # 204. If false, pytest reports a failure at this line.
    assert api.delete("/api/v1/me/library/movie/550/", secure=True).status_code == 204
    # Test expectation: CollectionMembership.objects.count() == 0. If false, pytest reports a
    # failure at this line.
    assert CollectionMembership.objects.count() == 0
    # Test expectation: Collection.objects.count() == 2. If false, pytest reports a failure at
    # this line.
    assert Collection.objects.count() == 2


def test_sharing_is_frontend_url_and_revocable_per_page(api, user, title):
    # INPUTS TO THIS FUNCTION: api = argument supplied by the caller; user = Django account; title
    # = argument supplied by the caller.
    # collection holds the account custom collection matched or created for this guest source.
    # Next, insert a new row and receive the created model object.
    collection = Collection.objects.create(user=user, name="Public")
    # saved holds an account SavedTitle row or the guest saved-row list, depending on the current
    # workflow. Next, insert a new row and receive the created model object.
    saved = SavedTitle.objects.create(user=user, title=title)
    # Insert a new row and receive the created model object.
    CollectionMembership.objects.create(collection=collection, saved_title=saved)
    # url holds the complete public navigation URL built from the approved configured origin.
    # Next, evaluate f'/api/v1/me/collections/{collection.pk}/sharing/'.
    url = f"/api/v1/me/collections/{collection.pk}/sharing/"
    # Set first: call api.put with the inputs shown; its definition explains the checks, side
    # effects and return value.
    first = api.put(url, secure=True)
    # Test expectation: first.status_code == 200. If false, pytest reports a failure at this line.
    assert first.status_code == 200
    # Test expectation: first.json()['url'].startswith('https://frontend.example.com/shared/'). If
    # false, pytest reports a failure at this line.
    assert first.json()["url"].startswith("https://frontend.example.com/shared/")
    # Test expectation: api.put(url, secure=True).json() == first.json(). If false, pytest reports
    # a failure at this line.
    assert api.put(url, secure=True).json() == first.json()
    # Set token: read the entry indexed by -1 from first.json()['url'].rsplit('/', 1).
    token = first.json()["url"].rsplit("/", 1)[-1]
    # share holds the stored public-share state; the recoverable token stays encrypted at rest.
    # Next, look up a named setting/value or make the indicated GET call; the surrounding object
    # determines which.
    share = PublicShare.objects.get(collection=collection)
    # Test expectation: token not in share.encrypted_token and token not in share.token_hash. If
    # false, pytest reports a failure at this line.
    assert token not in share.encrypted_token and token not in share.token_hash
    # Set public: call APIClient with the inputs shown; its definition explains the checks, side
    # effects and return value.
    public = APIClient()
    # response holds the response produced by the next handler or external HTTP request. Next,
    # look up a named setting/value or make the indicated GET call; the surrounding object
    # determines which.
    response = public.get(f"/api/v1/shared/{token}/", secure=True)
    # Test expectation: response.status_code == 200. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 200
    # Test expectation: set(response.json()) == {'name', 'items'}. If false, pytest reports a
    # failure at this line.
    assert set(response.json()) == {"name", "items"}
    # Test expectation: 'email' not in response.content.decode() and 'watched' not in
    # response.content.decode(). If false, pytest reports a failure at this line.
    assert "email" not in response.content.decode() and "watched" not in response.content.decode()
    # Set snapshot: read the entry indexed by 'snapshot' from response.json()['items']['meta'].
    snapshot = response.json()["items"]["meta"]["snapshot"]
    # Test expectation: api.delete(url, secure=True).status_code == 204. If false, pytest reports
    # a failure at this line.
    assert api.delete(url, secure=True).status_code == 204
    # Test expectation: public.get(f'/api/v1/shared/{token}/?snapshot={snapshot}',
    # secure=True).status_code == 404. If false, pytest reports a failure at this line.
    assert (
        public.get(f"/api/v1/shared/{token}/?snapshot={snapshot}", secure=True).status_code == 404
    )
    # Test expectation: api.put(url, secure=True).json()['url'] != first.json()['url']. If false,
    # pytest reports a failure at this line.
    assert api.put(url, secure=True).json()["url"] != first.json()["url"]


def sync_payload(title):
    # INPUTS TO THIS FUNCTION: title = argument supplied by the caller.
    # now holds one server timestamp shared by related changes in this action. Next, format this
    # timestamp as text including its timezone information.
    now = timezone.now().isoformat()
    # Set ref: build a dictionary with named fields such as media_type, tmdb_id.
    ref = {"media_type": title.media_type, "tmdb_id": title.tmdb_id}
    # Return this named-field dictionary; API handlers turn it into JSON, while helper callers use
    # it directly.
    return {
        "sync_id": str(uuid.uuid4()),
        "guest_id": str(uuid.uuid4()),
        "saved_titles": [{**ref, "watched": True, "saved_at": now, "watched_at": now}],
        "collections": [{"client_id": str(uuid.uuid4()), "name": "Weekend", "items": [ref]}],
    }


def test_guest_sync_idempotency_merges_and_tombstone(api, user, title):
    # INPUTS TO THIS FUNCTION: api = argument supplied by the caller; user = Django account; title
    # = argument supplied by the caller.
    # Insert a new row and receive the created model object.
    SavedTitle.objects.create(user=user, title=title)
    # Insert a new row and receive the created model object.
    Collection.objects.create(user=user, name="Weekend")
    # Set payload: call sync_payload with the inputs shown; its definition explains the checks,
    # side effects and return value.
    payload = sync_payload(title)
    # Set first: call api.post with the inputs shown; its definition explains the checks, side
    # effects and return value.
    first = api.post("/api/v1/me/guest-sync/", payload, format="json", secure=True)
    # Test expectation: first.status_code == 200. If false, pytest reports a failure at this line.
    assert first.status_code == 200, first.json()
    # Test expectation: first.json()['saved_merged'] == 1 and first.json()['saved_created'] == 0.
    # If false, pytest reports a failure at this line.
    assert first.json()["saved_merged"] == 1 and first.json()["saved_created"] == 0
    # Test expectation: SavedTitle.objects.get(user=user).watched is True. If false, pytest
    # reports a failure at this line.
    assert SavedTitle.objects.get(user=user).watched is True
    # Test expectation: Collection.objects.filter(name='Weekend (Imported 2)').exists(). If false,
    # pytest reports a failure at this line.
    assert Collection.objects.filter(name="Weekend (Imported 2)").exists()
    # Test expectation: api.post('/api/v1/me/guest-sync/', payload, format='json',
    # secure=True).json() == first.json(). If false, pytest reports a failure at this line.
    assert (
        api.post("/api/v1/me/guest-sync/", payload, format="json", secure=True).json()
        == first.json()
    )
    # Test expectation: CollectionMembership.objects.count() == 1 and SyncReceipt.objects.count()
    # == 1. If false, pytest reports a failure at this line.
    assert CollectionMembership.objects.count() == 1 and SyncReceipt.objects.count() == 1
    # Set changed: call copy.deepcopy with the inputs shown; its definition explains the checks,
    # side effects and return value.
    changed = copy.deepcopy(payload)
    # Set changed['saved_titles'][0]['watched']: use the boolean False.
    changed["saved_titles"][0]["watched"] = False
    # Set changed['saved_titles'][0]['watched_at']: use None to represent no known value (JSON
    # null at the API boundary).
    changed["saved_titles"][0]["watched_at"] = None
    # Test expectation: api.post('/api/v1/me/guest-sync/', changed, format='json',
    # secure=True).status_code == 409. If false, pytest reports a failure at this line.
    assert (
        api.post("/api/v1/me/guest-sync/", changed, format="json", secure=True).status_code == 409
    )
    # Set cid: read the entry indexed by 'collection_id' from
    # first.json()['collection_mappings'][0].
    cid = first.json()["collection_mappings"][0]["collection_id"]
    # Delete the selected row(s), applying their configured related-row deletion rules.
    api.delete(f"/api/v1/me/collections/{cid}/", secure=True)
    # Test expectation: GuestCollectionMapping.objects.get().collection is None. If false, pytest
    # reports a failure at this line.
    assert GuestCollectionMapping.objects.get().collection is None
    # Set payload['sync_id']: convert this value to text for an identifier, URL or response field.
    payload["sync_id"] = str(uuid.uuid4())
    # Test expectation: api.post('/api/v1/me/guest-sync/', payload, format='json',
    # secure=True).status_code == 409. If false, pytest reports a failure at this line.
    assert (
        api.post("/api/v1/me/guest-sync/", payload, format="json", secure=True).status_code == 409
    )
    # Test expectation: Collection.objects.count() == 1. If false, pytest reports a failure at
    # this line.
    assert Collection.objects.count() == 1


def test_guest_sync_validation_and_no_partial_writes(api, user, title):
    # INPUTS TO THIS FUNCTION: api = argument supplied by the caller; user = Django account; title
    # = argument supplied by the caller.
    # Set payload: call sync_payload with the inputs shown; its definition explains the checks,
    # side effects and return value.
    payload = sync_payload(title)
    # Set duplicate: call copy.deepcopy with the inputs shown; its definition explains the checks,
    # side effects and return value.
    duplicate = copy.deepcopy(payload)
    # Update duplicate['saved_titles'] using use the fixed value 2.
    duplicate["saved_titles"] *= 2
    # Test expectation: api.post('/api/v1/me/guest-sync/', duplicate, format='json',
    # secure=True).status_code == 400. If false, pytest reports a failure at this line.
    assert (
        api.post("/api/v1/me/guest-sync/", duplicate, format="json", secure=True).status_code == 400
    )
    # Set payload['saved_titles'][0]['watched_at']: format this timestamp as text including its
    # timezone information.
    payload["saved_titles"][0]["watched_at"] = (timezone.now() + timedelta(days=1)).isoformat()
    # Test expectation: api.post('/api/v1/me/guest-sync/', payload, format='json',
    # secure=True).status_code == 400. If false, pytest reports a failure at this line.
    assert (
        api.post("/api/v1/me/guest-sync/", payload, format="json", secure=True).status_code == 400
    )
    # Set payload: call sync_payload with the inputs shown; its definition explains the checks,
    # side effects and return value.
    payload = sync_payload(title)
    # Add one item at the end of this list.
    payload["collections"][0]["items"].append({"media_type": "movie", "tmdb_id": 999})
    # Import APIError from common.errors (our shared API layer).
    from common.errors import APIError

    # Temporarily replace the indicated dependency for this test, then automatically restore it
    # after the block.
    with patch("library.sync.resolve_title", side_effect=APIError("unavailable", "private", 503)):
        # response holds the response produced by the next handler or external HTTP request. Next,
        # call api.post with the inputs shown; its definition explains the checks, side effects
        # and return value.
        response = api.post("/api/v1/me/guest-sync/", payload, format="json", secure=True)
    # Test expectation: response.status_code == 503. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 503
    # Test expectation: not SavedTitle.objects.exists() and (not Collection.objects.exists()). If
    # false, pytest reports a failure at this line.
    assert not SavedTitle.objects.exists() and not Collection.objects.exists()
    # Test expectation: not SyncReceipt.objects.exists(). If false, pytest reports a failure at
    # this line.
    assert not SyncReceipt.objects.exists()


def test_recent_upsert_does_not_save(api, user, title):
    # INPUTS TO THIS FUNCTION: api = argument supplied by the caller; user = Django account; title
    # = argument supplied by the caller.
    # url holds the complete public navigation URL built from the approved configured origin.
    # Next, use the fixed value '/api/v1/me/recent/movie/550/'.
    url = "/api/v1/me/recent/movie/550/"
    # Test expectation: api.put(url, secure=True).status_code == 200. If false, pytest reports a
    # failure at this line.
    assert api.put(url, secure=True).status_code == 200
    # Test expectation: api.put(url, secure=True).status_code == 200. If false, pytest reports a
    # failure at this line.
    assert api.put(url, secure=True).status_code == 200
    # Test expectation: RecentTitle.objects.filter(user=user).count() == 1. If false, pytest
    # reports a failure at this line.
    assert RecentTitle.objects.filter(user=user).count() == 1
    # Test expectation: not SavedTitle.objects.exists(). If false, pytest reports a failure at
    # this line.
    assert not SavedTitle.objects.exists()
    # Test expectation: api.get('/api/v1/me/recent/', secure=True).json()['count'] == 1. If false,
    # pytest reports a failure at this line.
    assert api.get("/api/v1/me/recent/", secure=True).json()["count"] == 1


@pytest.mark.parametrize(
    "url", ["/api/v1/me/", "/api/v1/me/library/", "/api/v1/me/collections/", "/api/v1/me/recent/"]
)
def test_account_routes_require_login(url):
    # INPUTS TO THIS FUNCTION: url = argument supplied by the caller.
    # Test expectation: APIClient().get(url, secure=True).status_code == 401. If false, pytest
    # reports a failure at this line.
    assert APIClient().get(url, secure=True).status_code == 401
