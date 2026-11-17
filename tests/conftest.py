import re

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from catalog.normalization import GENRE_KEYS, MOODS
from common.contract import specification, validate


@pytest.fixture(autouse=True)
def contract_response_checks(monkeypatch):
    """Validate every successful feature-test response against its actual operation."""
    original = APIClient.request

    def checked(client, **kwargs):
        response = original(client, **kwargs)
        if 200 <= response.status_code < 300:
            path = response.wsgi_request.path
            method = response.wsgi_request.method.lower()
            for template, methods in specification()["paths"].items():
                pattern = re.sub(r"\{[^}]+\}", "[^/]+", template)
                if re.fullmatch(pattern, path) and method in methods:
                    success = methods[method]["responses"].get(str(response.status_code))
                    assert success is not None, (method, path, response.status_code)
                    content = success.get("content", {}).get("application/json")
                    if content:
                        validate(response.json(), content["schema"])
                    break
        return response

    monkeypatch.setattr(APIClient, "request", checked)


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    cache.clear()
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
        raise AssertionError("Unexpected live HTTP call in test")

    monkeypatch.setattr("httpx.Client.get", unexpected)


@pytest.fixture
def user(db):
    row = get_user_model().objects.create_user(
        username="viewer", email="viewer@example.com", password="Strong-example-password-2030!"
    )
    EmailAddress.objects.create(user=row, email=row.email, primary=True, verified=True)
    return row


@pytest.fixture
def api(user):
    client = APIClient()
    client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
    return client


@pytest.fixture
def raw_movie():
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
    from catalog.models import TitleSnapshot
    from catalog.normalization import summary

    data = summary(raw_movie, "movie")
    return TitleSnapshot.objects.create(
        media_type="movie", tmdb_id=550, summary=data, genre_keys=[g["key"] for g in data["genres"]]
    )
