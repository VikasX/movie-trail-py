# FILE PURPOSE: Tests harder failure cases: limits, malformed inputs, token safety and stale
# snapshots.
# Import timedelta from datetime (the named Python helper module).
from datetime import timedelta

# Import patch from unittest.mock (the named Python helper module).
from unittest.mock import patch

# Import httpx so the code below can use that module namespace.
import httpx

# Import pytest so the code below can use that module namespace.
import pytest

# Import EmailAddress from allauth.account.models (the maintained account/Google integration).
from allauth.account.models import EmailAddress

# Import ImmediateHttpResponse from allauth.core.exceptions (the maintained account/Google
# integration).
from allauth.core.exceptions import ImmediateHttpResponse

# Import SocialAccount, SocialLogin from allauth.socialaccount.models (the maintained
# account/Google integration).
from allauth.socialaccount.models import SocialAccount, SocialLogin

# Import get_user_model from django.contrib.auth (Django framework/database/security helpers).
from django.contrib.auth import get_user_model

# Import cache from django.core.cache (Django framework/database/security helpers).
from django.core.cache import cache

# Import RequestFactory from django.test (Django framework/database/security helpers).
from django.test import RequestFactory

# Import timezone from django.utils (Django framework/database/security helpers).
from django.utils import timezone

# Import APIClient from rest_framework.test (DRF request/response helpers).
from rest_framework.test import APIClient

# Import AccountToken from accounts.models (our account layer).
from accounts.models import AccountToken

# Import SocialAdapter from accounts.oauth (our account layer).
from accounts.oauth import SocialAdapter

# Import digest from accounts.services (our account layer).
from accounts.services import digest

# Import TMDBClient, start_budget from catalog.client (our TMDB/normalization layer).
from catalog.client import TMDBClient, start_budget

# Import TitleSnapshot from catalog.models (our TMDB/normalization layer).
from catalog.models import TitleSnapshot

# Import summary from catalog.normalization (our TMDB/normalization layer).
from catalog.normalization import summary

# Import candidates from catalog.services (our TMDB/normalization layer).
from catalog.services import candidates

# Import validate from common.contract (our shared API layer).
from common.contract import validate

# Import APIError from common.errors (our shared API layer).
from common.errors import APIError

# Import RecentTitle, SavedTitle from library.models (our personal-library layer).
from library.models import RecentTitle, SavedTitle


@pytest.mark.django_db
def test_missing_and_revoked_share_tokens_are_generic_404():
    # client holds the reusable interface for requesting TMDB data. Next, call APIClient with the
    # inputs shown; its definition explains the checks, side effects and return value.
    client = APIClient()
    # Repeat the following block for each token from ('bad', 'a' * 43). Each iteration handles
    # that one item/pair.
    for token in ("bad", "a" * 43):
        # response holds the response produced by the next handler or external HTTP request. Next,
        # look up a named setting/value or make the indicated GET call; the surrounding object
        # determines which.
        response = client.get(f"/api/v1/shared/{token}/", secure=True)
        # Test expectation: response.status_code == 404. If false, pytest reports a failure at
        # this line.
        assert response.status_code == 404
        # Call validate with the inputs shown; its definition explains the checks, side effects
        # and return value.
        validate(response.json(), {"$ref": "#/components/schemas/Error"})


def test_runtime_window_is_deterministic_and_capped(raw_movie):
    # INPUTS TO THIS FUNCTION: raw_movie = argument supplied by the caller.
    # Set raws: build a list for each i in range(1, 21).
    raws = [{**raw_movie, "id": i} for i in range(1, 21)]
    # Temporarily replace the indicated dependency for this test, then automatically restore it
    # after the block.
    with (
        patch(
            "catalog.services.TMDBClient.get", return_value={"results": raws, "total_pages": 2}
        ) as get,
        patch(
            "catalog.services.raw_detail",
            side_effect=lambda media, ident, language: {**raw_movie, "id": ident},
        ) as detail,
    ):
        # Set results: call candidates with the inputs shown; its definition explains the checks,
        # side effects and return value.
        results = candidates(
            {"media_type": "movie", "genres": ["animation", "family"], "runtime_min": 90}
        )
    # Test expectation: get.call_count == 2. If false, pytest reports a failure at this line.
    assert get.call_count == 2
    # Test expectation: detail.call_count == 6 and len(results) == 6. If false, pytest reports a
    # failure at this line.
    assert detail.call_count == 6 and len(results) == 6
    # Test expectation: get.call_args_list[0].args[1]['with_genres'] == '16,10751'. If false,
    # pytest reports a failure at this line.
    assert get.call_args_list[0].args[1]["with_genres"] == "16,10751"


@pytest.mark.django_db
def test_composite_ids_can_both_be_saved(api, user, title):
    # INPUTS TO THIS FUNCTION: api = argument supplied by the caller; user = Django account; title
    # = argument supplied by the caller.
    # Set tv_data: build a dictionary with named fields such as media_type.
    tv_data = {**title.summary, "media_type": "tv"}
    # Insert a new row and receive the created model object.
    TitleSnapshot.objects.create(media_type="tv", tmdb_id=550, summary=tv_data, genre_keys=[])
    # Repeat the following block for each media from ('movie', 'tv'). Each iteration handles that
    # one item/pair.
    for media in ("movie", "tv"):
        # Test expectation: api.put(f'/api/v1/me/library/{media}/550/', {'watched': False},
        # format='json', secure=True).status_code == 200. If false, pytest reports a failure at
        # this line.
        assert (
            api.put(
                f"/api/v1/me/library/{media}/550/", {"watched": False}, format="json", secure=True
            ).status_code
            == 200
        )
    # Test expectation: SavedTitle.objects.filter(user=user).count() == 2. If false, pytest
    # reports a failure at this line.
    assert SavedTitle.objects.filter(user=user).count() == 2


def test_unknown_runtime_excluded_and_malformed_upstream_rejected(raw_movie):
    # INPUTS TO THIS FUNCTION: raw_movie = argument supplied by the caller.
    # Import matches from catalog.services (our TMDB/normalization layer).
    from catalog.services import matches

    # Test expectation: not matches(summary({**raw_movie, 'runtime': None}, 'movie'),
    # {'runtime_min': 10}). If false, pytest reports a failure at this line.
    assert not matches(summary({**raw_movie, "runtime": None}, "movie"), {"runtime_min": 10})
    # This test expects the indicated exception. It fails if the block completes without raising
    # it.
    with pytest.raises(APIError) as exc:
        # Call summary with the inputs shown; its definition explains the checks, side effects and
        # return value.
        summary({**raw_movie, "popularity": "invalid"}, "movie")
    # Test expectation: exc.value.status_code == 502. If false, pytest reports a failure at this
    # line.
    assert exc.value.status_code == 502


def test_nonfinite_query_and_blank_search_rejected():
    # Repeat the following block for each query from ('min_rating=nan', 'q=%20%20'). Each
    # iteration handles that one item/pair.
    for query in ("min_rating=nan", "q=%20%20"):
        # Test expectation: APIClient().get('/api/v1/titles/?' + query, secure=True).status_code
        # == 400. If false, pytest reports a failure at this line.
        assert APIClient().get("/api/v1/titles/?" + query, secure=True).status_code == 400


def test_logs_redact_capabilities_and_oauth_parameters():
    # Import logging so the code below can use that module namespace.
    import logging

    # Import RedactCapabilities from common.logging (our shared API layer).
    from common.logging import RedactCapabilities

    # record holds the database row recording this one-time token lifecycle. Next, call
    # logging.LogRecord with the inputs shown; its definition explains the checks, side effects
    # and return value.
    record = logging.LogRecord(
        "test",
        logging.INFO,
        "",
        1,
        "GET %s",
        ("/api/v1/shared/secret-capability/?code=secret-code&state=secret-state",),
        None,
    )
    # Construct a django queryset restricted to the conditions shown; it remains lazy until
    # evaluated.
    RedactCapabilities().filter(record)
    # Test expectation: 'secret-capability' not in record.getMessage(). If false, pytest reports a
    # failure at this line.
    assert "secret-capability" not in record.getMessage()
    # Test expectation: 'secret-code' not in record.getMessage(). If false, pytest reports a
    # failure at this line.
    assert "secret-code" not in record.getMessage()
    # Test expectation: 'secret-state' not in record.getMessage(). If false, pytest reports a
    # failure at this line.
    assert "secret-state" not in record.getMessage()


@pytest.mark.django_db
def test_tmdb_retries_invalid_json_and_budget(monkeypatch, settings):
    # INPUTS TO THIS FUNCTION: monkeypatch = argument supplied by the caller; settings = argument
    # supplied by the caller.
    # Set settings.TMDB_READ_ACCESS_TOKEN: use the fixed value 'test-only'.
    settings.TMDB_READ_ACCESS_TOKEN = "test-only"
    # Set responses: build an ordered list of 2 entries.
    responses = [httpx.Response(503), httpx.Response(200, json={"results": []})]
    # Call monkeypatch.setattr with the inputs shown; its definition explains the checks, side
    # effects and return value.
    monkeypatch.setattr(httpx.Client, "get", lambda *a, **kw: responses.pop(0))
    # Call start_budget with the inputs shown; its definition explains the checks, side effects
    # and return value.
    start_budget()
    # Test expectation: TMDBClient().get('test-retry') == {'results': []}. If false, pytest
    # reports a failure at this line.
    assert TMDBClient().get("test-retry") == {"results": []}
    # Call monkeypatch.setattr with the inputs shown; its definition explains the checks, side
    # effects and return value.
    monkeypatch.setattr(
        httpx.Client, "get", lambda *a, **kw: httpx.Response(200, content=b"invalid-json")
    )
    # This test expects the indicated exception. It fails if the block completes without raising
    # it.
    with pytest.raises(APIError) as exc:
        # Look up a named setting/value or make the indicated get call; the surrounding object
        # determines which.
        TMDBClient().get("test-json")
    # Test expectation: exc.value.status_code == 502. If false, pytest reports a failure at this
    # line.
    assert exc.value.status_code == 502
    # Call monkeypatch.setattr with the inputs shown; its definition explains the checks, side
    # effects and return value.
    monkeypatch.setattr(
        httpx.Client, "get", lambda *a, **kw: httpx.Response(200, json={"results": []})
    )
    # Call start_budget with the inputs shown; its definition explains the checks, side effects
    # and return value.
    start_budget()
    # Repeat the following block for each i from range(8). Each iteration handles that one
    # item/pair.
    for i in range(8):
        # Look up a named setting/value or make the indicated get call; the surrounding object
        # determines which.
        TMDBClient().get(f"budget-{i}")
    # This test expects the indicated exception. It fails if the block completes without raising
    # it.
    with pytest.raises(APIError) as exc:
        # Look up a named setting/value or make the indicated get call; the surrounding object
        # determines which.
        TMDBClient().get("budget-9")
    # Test expectation: exc.value.status_code == 504. If false, pytest reports a failure at this
    # line.
    assert exc.value.status_code == 504


@pytest.mark.django_db
def test_expired_and_wrong_purpose_tokens(user):
    # INPUTS TO THIS FUNCTION: user = Django account.
    # Insert a new row and receive the created model object.
    AccountToken.objects.create(
        user=user,
        purpose="reset",
        token_hash=digest("expired"),
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    # Insert a new row and receive the created model object.
    AccountToken.objects.create(
        user=user,
        purpose="reset",
        token_hash=digest("wrong-purpose"),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    # Repeat the following block for each token from ('expired', 'wrong-purpose'). Each iteration
    # handles that one item/pair.
    for token in ("expired", "wrong-purpose"):
        # Test expectation: APIClient().post('/api/v1/auth/email/verify/', {'token': token},
        # format='json', secure=True).status_code == 400. If false, pytest reports a failure at
        # this line.
        assert (
            APIClient()
            .post("/api/v1/auth/email/verify/", {"token": token}, format="json", secure=True)
            .status_code
            == 400
        )


def test_google_cannot_link_existing_email(user):
    # INPUTS TO THIS FUNCTION: user = Django account.
    # Set request: look up a named setting/value or make the indicated GET call; the surrounding
    # object determines which.
    request = RequestFactory().get("/")
    # Set request.session: build a dictionary with named fields.
    request.session = {}
    # Set social: call SocialLogin with the inputs shown; its definition explains the checks, side
    # effects and return value.
    social = SocialLogin(
        user=get_user_model()(email=user.email),
        account=SocialAccount(provider="google", uid="new-google-id"),
        email_addresses=[EmailAddress(email=user.email, verified=True)],
    )
    # This test expects the indicated exception. It fails if the block completes without raising
    # it.
    with pytest.raises(ImmediateHttpResponse) as exc:
        # Call socialadapter().pre_social_login with the inputs shown; its definition explains the
        # checks, side effects and return value.
        SocialAdapter().pre_social_login(request, social)
    # Test expectation: 'auth=account_link_required' in exc.value.response['Location']. If false,
    # pytest reports a failure at this line.
    assert "auth=account_link_required" in exc.value.response["Location"]


def test_recent_limit_and_private_snapshots(api, user, title):
    # INPUTS TO THIS FUNCTION: api = argument supplied by the caller; user = Django account; title
    # = argument supplied by the caller.
    # Repeat the following block for each i from range(1, 53). Each iteration handles that one
    # item/pair.
    for i in range(1, 53):
        # Set t: insert a new row and receive the created model object.
        t = TitleSnapshot.objects.create(
            media_type="movie", tmdb_id=1000 + i, summary={**title.summary, "tmdb_id": 1000 + i}
        )
        # Insert a new row and receive the created model object.
        RecentTitle.objects.create(user=user, title=t)
    # Call api.put with the inputs shown; its definition explains the checks, side effects and
    # return value.
    api.put("/api/v1/me/recent/movie/550/", secure=True)
    # Test expectation: RecentTitle.objects.filter(user=user).count() == 50. If false, pytest
    # reports a failure at this line.
    assert RecentTitle.objects.filter(user=user).count() == 50
    # response holds the response produced by the next handler or external HTTP request. Next,
    # look up a named setting/value or make the indicated GET call; the surrounding object
    # determines which.
    response = api.get("/api/v1/me/recent/?page_size=1", secure=True)
    # page holds the requested one-based page number. Next, decode the HTTP response JSON into
    # ordinary Python dictionaries/lists.
    page = response.json()
    # Test expectation: page['results'][0]['title']['tmdb_id'] == 550. If false, pytest reports a
    # failure at this line.
    assert page["results"][0]["title"]["tmdb_id"] == 550
    # Remove the named cached entry.
    cache.delete("snapshot:" + page["meta"]["snapshot"])
    # Test expectation: api.get(page['next'], secure=True).status_code == 410. If false, pytest
    # reports a failure at this line.
    assert api.get(page["next"], secure=True).status_code == 410
