# FILE PURPOSE: Tests discovery, normalization, moods, trailers, HTTP caching and route
# coverage.
# Import patch from unittest.mock (the named Python helper module).
from unittest.mock import patch

# Import httpx so the code below can use that module namespace.
import httpx

# Import pytest so the code below can use that module namespace.
import pytest

# Import cache from django.core.cache (Django framework/database/security helpers).
from django.core.cache import cache

# Import APIClient from rest_framework.test (DRF request/response helpers).
from rest_framework.test import APIClient

# Import TMDBClient, start_budget from catalog.client (our TMDB/normalization layer).
from catalog.client import TMDBClient, start_budget

# Import summary, trailers from catalog.normalization (our TMDB/normalization layer).
from catalog.normalization import summary, trailers

# Import matches from catalog.services (our TMDB/normalization layer).
from catalog.services import matches

# Import specification, validate from common.contract (our shared API layer).
from common.contract import specification, validate

# Import APIError from common.errors (our shared API layer).
from common.errors import APIError


def check_schema(value, name):
    # INPUTS TO THIS FUNCTION: value = item being checked; name = argument supplied by the caller.
    # Call validate with the inputs shown; its definition explains the checks, side effects and
    # return value.
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
    # INPUTS TO THIS FUNCTION: query = argument supplied by the caller.
    # response holds the response produced by the next handler or external HTTP request. Next,
    # look up a named setting/value or make the indicated GET call; the surrounding object
    # determines which.
    response = APIClient().get("/api/v1/titles/?" + query, secure=True)
    # Test expectation: response.status_code == 400. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 400
    # Call check_schema with the inputs shown; its definition explains the checks, side effects
    # and return value.
    check_schema(response.json(), "Error")


def test_and_genres_and_tv_composite_identity(raw_movie):
    # INPUTS TO THIS FUNCTION: raw_movie = argument supplied by the caller.
    # title holds a referenced title record or normalized card; this is deliberately separate from
    # an owner SavedTitle row. Next, call summary with the inputs shown; its definition explains
    # the checks, side effects and return value.
    title = summary(raw_movie, "movie")
    # Test expectation: matches(title, {'genres': ['animation', 'family'], 'year_from': 2025,
    # 'year_to': 2025}). If false, pytest reports a failure at this line.
    assert matches(title, {"genres": ["animation", "family"], "year_from": 2025, "year_to": 2025})
    # Test expectation: not matches(title, {'genres': ['animation', 'drama']}). If false, pytest
    # reports a failure at this line.
    assert not matches(title, {"genres": ["animation", "drama"]})
    # Set tv: build a dictionary with named fields such as name, first_air_date, genre_ids,
    # episode_run_time.
    tv = {
        **raw_movie,
        "name": "TV",
        "first_air_date": "2025-06-10",
        "genre_ids": [10759, 10765],
        "episode_run_time": [20, 40],
    }
    # Set normalized: call summary with the inputs shown; its definition explains the checks, side
    # effects and return value.
    normalized = summary(tv, "tv")
    # Test expectation: normalized['runtime_minutes'] == 30. If false, pytest reports a failure at
    # this line.
    assert normalized["runtime_minutes"] == 30
    # Test expectation: matches(normalized, {'genres': ['action', 'adventure', 'sci-fi',
    # 'fantasy']}). If false, pytest reports a failure at this line.
    assert matches(normalized, {"genres": ["action", "adventure", "sci-fi", "fantasy"]})
    # Test expectation: normalized['tmdb_id'] == title['tmdb_id'] and normalized['media_type'] !=
    # title['media_type']. If false, pytest reports a failure at this line.
    assert (
        normalized["tmdb_id"] == title["tmdb_id"]
        and normalized["media_type"] != title["media_type"]
    )
    # Call check_schema with the inputs shown; its definition explains the checks, side effects
    # and return value.
    check_schema(normalized, "TitleSummary")


def test_discovery_snapshot_does_not_refetch(raw_movie):
    # INPUTS TO THIS FUNCTION: raw_movie = argument supplied by the caller.
    # client holds the reusable interface for requesting TMDB data. Next, call APIClient with the
    # inputs shown; its definition explains the checks, side effects and return value.
    client = APIClient()
    # Temporarily replace the indicated dependency for this test, then automatically restore it
    # after the block.
    with patch(
        "catalog.services.TMDBClient.get", return_value={"results": [raw_movie], "total_pages": 1}
    ) as get:
        # response holds the response produced by the next handler or external HTTP request. Next,
        # look up a named setting/value or make the indicated GET call; the surrounding object
        # determines which.
        response = client.get(
            "/api/v1/titles/?media_type=movie&genres=animation,family&year_from=2025&year_to=2025",
            secure=True,
        )
        # Test expectation: response.status_code == 200. If false, pytest reports a failure at
        # this line.
        assert response.status_code == 200
        # Call check_schema with the inputs shown; its definition explains the checks, side
        # effects and return value.
        check_schema(response.json(), "TitlePage")
        # Test expectation: response.json()['count'] == 1. If false, pytest reports a failure at
        # this line.
        assert response.json()["count"] == 1
        # Test expectation: get.call_count == 1. If false, pytest reports a failure at this line.
        assert get.call_count == 1


def test_snapshot_page_links_and_expiry(raw_movie):
    # INPUTS TO THIS FUNCTION: raw_movie = argument supplied by the caller.
    # client holds the reusable interface for requesting TMDB data. Next, call APIClient with the
    # inputs shown; its definition explains the checks, side effects and return value.
    client = APIClient()
    # Set response_rows: build a list for each i in range(1, 4).
    response_rows = [{**raw_movie, "id": i} for i in range(1, 4)]
    # Temporarily replace the indicated dependency for this test, then automatically restore it
    # after the block.
    with patch(
        "catalog.services.TMDBClient.get", return_value={"results": response_rows, "total_pages": 1}
    ) as get:
        # Set first: look up a named setting/value or make the indicated GET call; the surrounding
        # object determines which.
        first = client.get("/api/v1/titles/?media_type=movie&page_size=1", secure=True)
        # Test expectation: first.status_code == 200. If false, pytest reports a failure at this
        # line.
        assert first.status_code == 200
        # Set next_page: read the entry indexed by 'next' from first.json().
        next_page = first.json()["next"]
        # Set second: look up a named setting/value or make the indicated GET call; the
        # surrounding object determines which.
        second = client.get(next_page, secure=True)
        # Test expectation: second.status_code == 200. If false, pytest reports a failure at this
        # line.
        assert second.status_code == 200
        # Test expectation: second.json()['results'][0]['tmdb_id'] == 2. If false, pytest reports
        # a failure at this line.
        assert second.json()["results"][0]["tmdb_id"] == 2
        # Test expectation: get.call_count == 1. If false, pytest reports a failure at this line.
        assert get.call_count == 1
        # Set token: read the entry indexed by 'snapshot' from first.json()['meta'].
        token = first.json()["meta"]["snapshot"]
        # Test expectation:
        # client.get(f'/api/v1/titles/?media_type=tv&page_size=1&snapshot={token}',
        # secure=True).status_code == 400. If false, pytest reports a failure at this line.
        assert (
            client.get(
                f"/api/v1/titles/?media_type=tv&page_size=1&snapshot={token}", secure=True
            ).status_code
            == 400
        )
        # Remove the named cached entry.
        cache.delete(f"snapshot:{token}")
        # Test expectation: client.get(next_page, secure=True).status_code == 410. If false,
        # pytest reports a failure at this line.
        assert client.get(next_page, secure=True).status_code == 410


@pytest.mark.parametrize("key", ["feel_good", "mind_bending", "dark", "relaxing", "family_night"])
def test_moods_enforce_mapping_and_filters(raw_movie, key):
    # INPUTS TO THIS FUNCTION: raw_movie = argument supplied by the caller; key = argument
    # supplied by the caller.
    # Set rows: build an ordered list of 1 entries.
    rows = [summary(raw_movie, "movie")]
    # Temporarily replace the indicated dependency for this test, then automatically restore it
    # after the block.
    with patch("catalog.recommendations.candidates", return_value=rows):
        # response holds the response produced by the next handler or external HTTP request. Next,
        # call APIClient().post with the inputs shown; its definition explains the checks, side
        # effects and return value.
        response = APIClient().post(
            "/api/v1/recommendations/",
            {"mode": "mood", "mood": key, "filters": {"genres": ["animation", "family"]}},
            format="json",
            secure=True,
        )
    # Test expectation: response.status_code == 200. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 200
    # Call check_schema with the inputs shown; its definition explains the checks, side effects
    # and return value.
    check_schema(response.json(), "RecommendationResult")
    # Enter this branch only when key == 'family_night'. Otherwise execution uses its alternative
    # or continues below.
    if key == "family_night":
        # Test expectation: len(response.json()['results']) == 1. If false, pytest reports a
        # failure at this line.
        assert len(response.json()["results"]) == 1
    # Enter this branch only when key == 'dark'. Otherwise execution uses its alternative or
    # continues below.
    if key == "dark":
        # Test expectation: response.json()['results'] == []. If false, pytest reports a failure
        # at this line.
        assert response.json()["results"] == []


def test_personalized_requires_authentication():
    # response holds the response produced by the next handler or external HTTP request. Next,
    # call APIClient().post with the inputs shown; its definition explains the checks, side
    # effects and return value.
    response = APIClient().post(
        "/api/v1/recommendations/", {"mode": "personalized"}, format="json", secure=True
    )
    # Test expectation: response.status_code == 401. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 401


def test_personalized_excludes_saved_and_fallback(api, user, title, raw_movie):
    # INPUTS TO THIS FUNCTION: api = argument supplied by the caller; user = Django account; title
    # = argument supplied by the caller; raw_movie = argument supplied by the caller.
    # Import SavedTitle from library.models (our personal-library layer).
    from library.models import SavedTitle

    # Temporarily replace the indicated dependency for this test, then automatically restore it
    # after the block.
    with patch("catalog.recommendations.candidates", return_value=[title.summary]):
        # Test expectation: api.post('/api/v1/recommendations/', {'mode': 'personalized'},
        # format='json', secure=True).json()['basis'] == 'popular_fallback'. If false, pytest
        # reports a failure at this line.
        assert (
            api.post(
                "/api/v1/recommendations/", {"mode": "personalized"}, format="json", secure=True
            ).json()["basis"]
            == "popular_fallback"
        )
        # Insert a new row and receive the created model object.
        SavedTitle.objects.create(user=user, title=title)
        # response holds the response produced by the next handler or external HTTP request. Next,
        # call api.post with the inputs shown; its definition explains the checks, side effects
        # and return value.
        response = api.post(
            "/api/v1/recommendations/", {"mode": "personalized"}, format="json", secure=True
        )
        # Test expectation: response.json()['basis'] == 'saved_metadata'. If false, pytest reports
        # a failure at this line.
        assert response.json()["basis"] == "saved_metadata"
        # Test expectation: response.json()['results'] == []. If false, pytest reports a failure
        # at this line.
        assert response.json()["results"] == []


def test_trailer_order_and_missing():
    # videos holds upstream video candidates, before YouTube/type/language selection. Next, build
    # an ordered list of 3 entries.
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
    # Set result: call trailers with the inputs shown; its definition explains the checks, side
    # effects and return value.
    result = trailers(videos, "en-US")
    # Test expectation: [r['id'] for r in result] == ['1', '2']. If false, pytest reports a
    # failure at this line.
    assert [r["id"] for r in result] == ["1", "2"]
    # Test expectation: trailers([], 'en-US') == []. If false, pytest reports a failure at this
    # line.
    assert trailers([], "en-US") == []
    # Call check_schema with the inputs shown; its definition explains the checks, side effects
    # and return value.
    check_schema(result[0], "Trailer")


@pytest.mark.django_db
def test_details_optional_provider_failure(raw_movie):
    # INPUTS TO THIS FUNCTION: raw_movie = argument supplied by the caller.
    # Temporarily replace the indicated dependency for this test, then automatically restore it
    # after the block.
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
        # response holds the response produced by the next handler or external HTTP request. Next,
        # look up a named setting/value or make the indicated GET call; the surrounding object
        # determines which.
        response = APIClient().get("/api/v1/titles/movie/550/", secure=True)
    # Test expectation: response.status_code == 200. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 200
    # Test expectation: response.json()['selected_trailer_id'] is None. If false, pytest reports a
    # failure at this line.
    assert response.json()["selected_trailer_id"] is None
    # Test expectation: response.json()['availability']['status'] == 'unavailable'. If false,
    # pytest reports a failure at this line.
    assert response.json()["availability"]["status"] == "unavailable"
    # Test expectation: 'private detail' not in response.content.decode(). If false, pytest
    # reports a failure at this line.
    assert "private detail" not in response.content.decode()
    # Call check_schema with the inputs shown; its definition explains the checks, side effects
    # and return value.
    check_schema(response.json(), "TitleDetails")


@pytest.mark.django_db
def test_tmdb_client_cache_and_429(monkeypatch, settings):
    # INPUTS TO THIS FUNCTION: monkeypatch = argument supplied by the caller; settings = argument
    # supplied by the caller.
    # Set settings.TMDB_READ_ACCESS_TOKEN: use the fixed value 'test-token'.
    settings.TMDB_READ_ACCESS_TOKEN = "test-token"
    # Set call_count: use the fixed value 0.
    call_count = 0

    def get(self, url, **kwargs):
        # INPUTS TO THIS FUNCTION: self = this class instance; url = argument supplied by the
        # caller.
        nonlocal call_count
        # Add to call_count using use the fixed value 1.
        call_count += 1
        # Test expectation: kwargs['headers']['Authorization'] == 'Bearer test-token'. If false,
        # pytest reports a failure at this line.
        assert kwargs["headers"]["Authorization"] == "Bearer test-token"
        # Return the result to the caller: call httpx.Response with the inputs shown; its
        # definition explains the checks, side effects and return value.
        return httpx.Response(200, json={"results": []})

    # Call monkeypatch.setattr with the inputs shown; its definition explains the checks, side
    # effects and return value.
    monkeypatch.setattr(httpx.Client, "get", get)
    # Call start_budget with the inputs shown; its definition explains the checks, side effects
    # and return value.
    start_budget()
    # client holds the reusable interface for requesting TMDB data. Next, call TMDBClient with the
    # inputs shown; its definition explains the checks, side effects and return value.
    client = TMDBClient()
    # Test expectation: client.get('discover/movie') == {'results': []}. If false, pytest reports
    # a failure at this line.
    assert client.get("discover/movie") == {"results": []}
    # Test expectation: client.get('discover/movie') == {'results': []}. If false, pytest reports
    # a failure at this line.
    assert client.get("discover/movie") == {"results": []}
    # Test expectation: call_count == 1. If false, pytest reports a failure at this line.
    assert call_count == 1
    # Call monkeypatch.setattr with the inputs shown; its definition explains the checks, side
    # effects and return value.
    monkeypatch.setattr(
        httpx.Client, "get", lambda *a, **kw: httpx.Response(429, headers={"Retry-After": "7"})
    )
    # This test expects the indicated exception. It fails if the block completes without raising
    # it.
    with pytest.raises(APIError) as exc:
        # Look up a named setting/value or make the indicated get call; the surrounding object
        # determines which.
        client.get("discover/tv")
    # Test expectation: exc.value.status_code == 503 and exc.value.retry_after == 7. If false,
    # pytest reports a failure at this line.
    assert exc.value.status_code == 503 and exc.value.retry_after == 7


def test_every_contract_operation_is_routed():
    # Import resolve from django.urls (Django framework/database/security helpers).
    from django.urls import resolve

    # Set examples: build a dictionary with named fields such as media_type, tmdb_id,
    # collection_id, token.
    examples = {
        "media_type": "movie",
        "tmdb_id": "550",
        "collection_id": "00000000-0000-4000-8000-000000000001",
        "token": "a" * 43,
    }
    # count holds the current list length or request counter; it does not mean the full size of
    # TMDB. Next, use the fixed value 0.
    count = 0
    # Repeat the following block for each (path, methods) from specification()['paths'].items().
    # Each iteration handles that one item/pair.
    for path, methods in specification()["paths"].items():
        # Set actual: reuse path, which was prepared earlier in this function.
        actual = path
        # Repeat the following block for each (k, v) from examples.items(). Each iteration handles
        # that one item/pair.
        for k, v in examples.items():
            # Set actual: call actual.replace with the inputs shown; its definition explains the
            # checks, side effects and return value.
            actual = actual.replace("{" + k + "}", v)
        # Set match: call resolve with the inputs shown; its definition explains the checks, side
        # effects and return value.
        match = resolve(actual)
        # Repeat the following block for each method from methods. Each iteration handles that one
        # item/pair.
        for method in methods:
            # Set view: call getattr with the inputs shown; its definition explains the checks,
            # side effects and return value.
            view = getattr(match.func, "view_class", None)
            # Enter this branch only when view and hasattr(view, 'handlers'). Otherwise execution
            # uses its alternative or continues below.
            if view and hasattr(view, "handlers"):
                # Test expectation: method in view.handlers. If false, pytest reports a failure at
                # this line.
                assert method in view.handlers
            # Add to count using use the fixed value 1.
            count += 1
    # Test expectation: count == 36. If false, pytest reports a failure at this line.
    assert count == 36
