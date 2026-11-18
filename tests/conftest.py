# FILE PURPOSE: Reusable test setup: isolated caches, fake users/data, blocked network and
# response-shape checks.
# Import re so the code below can use that module namespace.
import re

# Import pytest so the code below can use that module namespace.
import pytest

# Import EmailAddress from allauth.account.models (the maintained account/Google integration).
from allauth.account.models import EmailAddress

# Import get_user_model from django.contrib.auth (Django framework/database/security helpers).
from django.contrib.auth import get_user_model

# Import cache from django.core.cache (Django framework/database/security helpers).
from django.core.cache import cache

# Import APIClient from rest_framework.test (DRF request/response helpers).
from rest_framework.test import APIClient

# Import GENRE_KEYS, MOODS from catalog.normalization (our TMDB/normalization layer).
from catalog.normalization import GENRE_KEYS, MOODS

# Import specification, validate from common.contract (our shared API layer).
from common.contract import specification, validate


@pytest.fixture(autouse=True)
def contract_response_checks(monkeypatch):
    """Validate every successful feature-test response against its actual operation."""
    # INPUTS TO THIS FUNCTION: monkeypatch = argument supplied by the caller.
    # Set original: read APIClient.request from the indicated object.
    original = APIClient.request

    def checked(client, **kwargs):
        # INPUTS TO THIS FUNCTION: client = argument supplied by the caller.
        # response holds the response produced by the next handler or external HTTP request. Next,
        # call original with the inputs shown; its definition explains the checks, side effects
        # and return value.
        response = original(client, **kwargs)
        # Enter this branch only when 200 <= response.status_code < 300. Otherwise execution uses
        # its alternative or continues below.
        if 200 <= response.status_code < 300:
            # path holds the route to request externally or the frontend completion path; read the
            # surrounding function for its role. Next, read response.wsgi_request.path from the
            # indicated object.
            path = response.wsgi_request.path
            # method holds the HTTP method in lowercase, used to select the matching feature
            # handler. Next, call response.wsgi_request.method.lower with the inputs shown; its
            # definition explains the checks, side effects and return value.
            method = response.wsgi_request.method.lower()
            # Repeat the following block for each (template, methods) from
            # specification()['paths'].items(). Each iteration handles that one item/pair.
            for template, methods in specification()["paths"].items():
                # Set pattern: call re.sub with the inputs shown; its definition explains the
                # checks, side effects and return value.
                pattern = re.sub(r"\{[^}]+\}", "[^/]+", template)
                # Enter this branch only when re.fullmatch(pattern, path) and method in methods.
                # Otherwise execution uses its alternative or continues below.
                if re.fullmatch(pattern, path) and method in methods:
                    # Set success: look up a named setting/value or make the indicated GET call;
                    # the surrounding object determines which.
                    success = methods[method]["responses"].get(str(response.status_code))
                    # Test expectation: success is not None. If false, pytest reports a failure at
                    # this line.
                    assert success is not None, (method, path, response.status_code)
                    # Set content: look up a named setting/value or make the indicated GET call;
                    # the surrounding object determines which.
                    content = success.get("content", {}).get("application/json")
                    # Enter this branch only when content. Otherwise execution uses its
                    # alternative or continues below.
                    if content:
                        # Call validate with the inputs shown; its definition explains the checks,
                        # side effects and return value.
                        validate(response.json(), content["schema"])
                    # Leave this loop now; no further source pages/items are attempted by this
                    # loop.
                    break
        # Return the result to the caller: reuse response, which was prepared earlier in this
        # function.
        return response

    # Call monkeypatch.setattr with the inputs shown; its definition explains the checks, side
    # effects and return value.
    monkeypatch.setattr(APIClient, "request", checked)


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    # INPUTS TO THIS FUNCTION: monkeypatch = argument supplied by the caller.
    # Perform this shared-cache operation.
    cache.clear()
    # Remember this value for the specified lifetime.
    cache.set(
        "metadata:v2",
        {
            "genres": [{"key": k, "name": k.title()} for k in GENRE_KEYS],
            "languages": [{"code": "en", "name": "English"}, {"code": "ja", "name": "Japanese"}],
            "regions": [{"code": "IN", "name": "India"}, {"code": "US", "name": "United States"}],
            "moods": MOODS,
            "mood_mapping_version": "moods-v2",
            "attribution": {
                "tmdb_notice": "Test attribution",
                "tmdb_url": "https://www.themoviedb.org",
                "watch_providers": "JustWatch",
            },
        },
        86400,
    )

    # Unit tests must never send real credentials or reach an external service.
    def unexpected(*args, **kwargs):
        # Raise AssertionError; normal execution of this block stops here.
        raise AssertionError("Unexpected live HTTP call in test")

    # Call monkeypatch.setattr with the inputs shown; its definition explains the checks, side
    # effects and return value.
    monkeypatch.setattr("httpx.Client.get", unexpected)


@pytest.fixture
def user(db):
    # INPUTS TO THIS FUNCTION: db = argument supplied by the caller.
    # row holds the current database object being read or changed; its model is identified by the
    # query/constructor below. Next, call get_user_model().objects.create_user with the inputs
    # shown; its definition explains the checks, side effects and return value.
    row = get_user_model().objects.create_user(
        username="viewer", email="viewer@example.com", password="Strong-example-password-2030!"
    )
    # Insert a new row and receive the created model object.
    EmailAddress.objects.create(user=row, email=row.email, primary=True, verified=True)
    # Return the result to the caller: reuse row, which was prepared earlier in this function.
    return row


@pytest.fixture
def api(user):
    # INPUTS TO THIS FUNCTION: user = Django account.
    # client holds the reusable interface for requesting TMDB data. Next, call APIClient with the
    # inputs shown; its definition explains the checks, side effects and return value.
    client = APIClient()
    # Call client.force_login with the inputs shown; its definition explains the checks, side
    # effects and return value.
    client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
    # Return the result to the caller: reuse client, which was prepared earlier in this function.
    return client


@pytest.fixture
def raw_movie():
    # Return this named-field dictionary; API handlers turn it into JSON, while helper callers use
    # it directly.
    return {
        "id": 550,
        "title": "Test movie",
        "original_title": "Test movie",
        "release_date": "2025-06-10",
        "genre_ids": [16, 10751],
        "original_language": "en",
        "vote_average": 8.2,
        "vote_count": 400,
        "popularity": 12.0,
        "runtime": 100,
        "adult": False,
        "overview": "Test synopsis",
        "poster_path": "/poster.jpg",
    }


@pytest.fixture
def title(db, raw_movie):
    # INPUTS TO THIS FUNCTION: db = argument supplied by the caller; raw_movie = argument supplied
    # by the caller.
    # Import TitleSnapshot from catalog.models (our TMDB/normalization layer).
    from catalog.models import TitleSnapshot

    # Import summary from catalog.normalization (our TMDB/normalization layer).
    from catalog.normalization import summary

    # data holds the cleaned submitted JSON body (or, in normalization helpers, the upstream
    # object being translated). Next, call summary with the inputs shown; its definition explains
    # the checks, side effects and return value.
    data = summary(raw_movie, "movie")
    # Return the result to the caller: insert a new row and receive the created model object.
    return TitleSnapshot.objects.create(
        media_type="movie", tmdb_id=550, summary=data, genre_keys=[g["key"] for g in data["genres"]]
    )
