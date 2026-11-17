from unittest.mock import patch

import httpx
import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from catalog.client import TMDBClient, start_budget
from catalog.normalization import summary, trailers
from catalog.services import matches
from common.contract import specification, validate
from common.errors import APIError


def check_schema(value, name):
    validate(value, {"$ref": f"#/components/schemas/{name}"})


@pytest.mark.parametrize(
    "query",
    [
        "genres=unknown",
        "year_from=2025&year_to=2020",
        "runtime_min=120&runtime_max=60",
        "min_rating=11",
        "q=a",
        "person_id=287",
        "person_role=actor",
        "q=test&person_id=287&person_role=actor",
        "q=test&feed=trending",
        "surprise=true",
        "genres=family,family",
        "page=0",
    ],
)
def test_invalid_discovery_input(query):
    response = APIClient().get("/api/v1/titles/?" + query, secure=True)
    assert response.status_code == 400
    check_schema(response.json(), "Error")


def test_and_genres_and_tv_composite_identity(raw_movie):
    title = summary(raw_movie, "movie")
    assert matches(title, {"genres": ["animation", "family"], "year_from": 2025, "year_to": 2025})
    assert not matches(title, {"genres": ["animation", "drama"]})
    tv = {
        **raw_movie,
        "name": "TV",
        "first_air_date": "2025-06-10",
        "genre_ids": [10759, 10765],
        "episode_run_time": [20, 40],
    }
    normalized = summary(tv, "tv")
    assert normalized["runtime_minutes"] == 30
    assert matches(normalized, {"genres": ["action", "adventure", "sci-fi", "fantasy"]})
    assert (
        normalized["tmdb_id"] == title["tmdb_id"]
        and normalized["media_type"] != title["media_type"]
    )
    check_schema(normalized, "TitleSummary")


def test_discovery_snapshot_does_not_refetch(raw_movie):
    client = APIClient()
    with patch(
        "catalog.services.TMDBClient.get", return_value={"results": [raw_movie], "total_pages": 1}
    ) as get:
        response = client.get(
            "/api/v1/titles/?media_type=movie&genres=animation,family&year_from=2025&year_to=2025",
            secure=True,
        )
        assert response.status_code == 200
        check_schema(response.json(), "TitlePage")
        assert response.json()["count"] == 1
        assert get.call_count == 1


def test_snapshot_page_links_and_expiry(raw_movie):
    client = APIClient()
    response_rows = [{**raw_movie, "id": i} for i in range(1, 4)]
    with patch(
        "catalog.services.TMDBClient.get", return_value={"results": response_rows, "total_pages": 1}
    ) as get:
        first = client.get("/api/v1/titles/?media_type=movie&page_size=1", secure=True)
        assert first.status_code == 200
        next_page = first.json()["next"]
        second = client.get(next_page, secure=True)
        assert second.status_code == 200
        assert second.json()["results"][0]["tmdb_id"] == 2
        assert get.call_count == 1
        token = first.json()["meta"]["snapshot"]
        assert (
            client.get(
                f"/api/v1/titles/?media_type=tv&page_size=1&snapshot={token}", secure=True
            ).status_code
            == 400
        )
        cache.delete(f"snapshot:{token}")
        assert client.get(next_page, secure=True).status_code == 410


@pytest.mark.parametrize("key", ["feel_good", "mind_bending", "dark", "relaxing", "family_night"])
def test_moods_enforce_mapping_and_filters(raw_movie, key):
    rows = [summary(raw_movie, "movie")]
    with patch("catalog.recommendations.candidates", return_value=rows):
        response = APIClient().post(
            "/api/v1/recommendations/",
            {"mode": "mood", "mood": key, "filters": {"genres": ["animation", "family"]}},
            format="json",
            secure=True,
        )
    assert response.status_code == 200
    check_schema(response.json(), "RecommendationResult")
    if key == "family_night":
        assert len(response.json()["results"]) == 1
    if key == "dark":
        assert response.json()["results"] == []


def test_personalized_requires_authentication():
    response = APIClient().post(
        "/api/v1/recommendations/", {"mode": "personalized"}, format="json", secure=True
    )
    assert response.status_code == 401


def test_personalized_excludes_saved_and_fallback(api, user, title, raw_movie):
    from library.models import SavedTitle

    with patch("catalog.recommendations.candidates", return_value=[title.summary]):
        assert (
            api.post(
                "/api/v1/recommendations/", {"mode": "personalized"}, format="json", secure=True
            ).json()["basis"]
            == "popular_fallback"
        )
        SavedTitle.objects.create(user=user, title=title)
        response = api.post(
            "/api/v1/recommendations/", {"mode": "personalized"}, format="json", secure=True
        )
        assert response.json()["basis"] == "saved_metadata"
        assert response.json()["results"] == []


def test_trailer_order_and_missing():
    videos = [
        {
            "id": "2",
            "site": "YouTube",
            "type": "Trailer",
            "key": "abcdefghijk",
            "iso_639_1": "en",
            "official": False,
        },
        {
            "id": "1",
            "site": "YouTube",
            "type": "Trailer",
            "key": "12345678901",
            "iso_639_1": "en",
            "official": True,
        },
        {"id": "3", "site": "Vimeo", "type": "Trailer", "key": "notallowed"},
    ]
    result = trailers(videos, "en-US")
    assert [r["id"] for r in result] == ["1", "2"]
    assert trailers([], "en-US") == []
    check_schema(result[0], "Trailer")


@pytest.mark.django_db
def test_details_optional_provider_failure(raw_movie):
    with (
        patch(
            "catalog.services.raw_detail",
            return_value={
                **raw_movie,
                "credits": {"cast": [], "crew": []},
                "videos": {"results": []},
            },
        ),
        patch(
            "catalog.services.TMDBClient.get",
            side_effect=APIError("service_unavailable", "private detail", 503),
        ),
    ):
        response = APIClient().get("/api/v1/titles/movie/550/", secure=True)
    assert response.status_code == 200
    assert response.json()["selected_trailer_id"] is None
    assert response.json()["availability"]["status"] == "unavailable"
    assert "private detail" not in response.content.decode()
    check_schema(response.json(), "TitleDetails")


@pytest.mark.django_db
def test_tmdb_client_cache_and_429(monkeypatch, settings):
    settings.TMDB_READ_ACCESS_TOKEN = "test-token"
    call_count = 0

    def get(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        assert kwargs["headers"]["Authorization"] == "Bearer test-token"
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr(httpx.Client, "get", get)
    start_budget()
    client = TMDBClient()
    assert client.get("discover/movie") == {"results": []}
    assert client.get("discover/movie") == {"results": []}
    assert call_count == 1
    monkeypatch.setattr(
        httpx.Client, "get", lambda *a, **kw: httpx.Response(429, headers={"Retry-After": "7"})
    )
    with pytest.raises(APIError) as exc:
        client.get("discover/tv")
    assert exc.value.status_code == 503 and exc.value.retry_after == 7


def test_every_contract_operation_is_routed():
    from django.urls import resolve

    examples = {
        "media_type": "movie",
        "tmdb_id": "550",
        "collection_id": "00000000-0000-4000-8000-000000000001",
        "token": "a" * 43,
    }
    count = 0
    for path, methods in specification()["paths"].items():
        actual = path
        for k, v in examples.items():
            actual = actual.replace("{" + k + "}", v)
        match = resolve(actual)
        for method in methods:
            view = getattr(match.func, "view_class", None)
            if view and hasattr(view, "handlers"):
                assert method in view.handlers
            count += 1
    assert count == 36
