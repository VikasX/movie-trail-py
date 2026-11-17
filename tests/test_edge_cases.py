from datetime import timedelta
from unittest.mock import patch

import httpx
import pytest
from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountToken
from accounts.oauth import SocialAdapter
from accounts.services import digest
from catalog.client import TMDBClient, start_budget
from catalog.models import TitleSnapshot
from catalog.normalization import summary
from catalog.services import candidates
from common.contract import validate
from common.errors import APIError
from library.models import RecentTitle, SavedTitle


@pytest.mark.django_db
def test_missing_and_revoked_share_tokens_are_generic_404():
    client = APIClient()
    for token in ("bad", "a" * 43):
        response = client.get(f"/api/v1/shared/{token}/", secure=True)
        assert response.status_code == 404
        validate(response.json(), {"$ref": "#/components/schemas/Error"})


def test_runtime_window_is_deterministic_and_capped(raw_movie):
    raws = [{**raw_movie, "id": i} for i in range(1, 21)]
    with (
        patch(
            "catalog.services.TMDBClient.get", return_value={"results": raws, "total_pages": 2}
        ) as get,
        patch(
            "catalog.services.raw_detail",
            side_effect=lambda media, ident, language: {**raw_movie, "id": ident},
        ) as detail,
    ):
        results = candidates(
            {"media_type": "movie", "genres": ["animation", "family"], "runtime_min": 90}
        )
    assert get.call_count == 2
    assert detail.call_count == 6 and len(results) == 6
    assert get.call_args_list[0].args[1]["with_genres"] == "16,10751"


@pytest.mark.django_db
def test_composite_ids_can_both_be_saved(api, user, title):
    tv_data = {**title.summary, "media_type": "tv"}
    TitleSnapshot.objects.create(media_type="tv", tmdb_id=550, summary=tv_data, genre_keys=[])
    for media in ("movie", "tv"):
        assert (
            api.put(
                f"/api/v1/me/library/{media}/550/", {"watched": False}, format="json", secure=True
            ).status_code
            == 200
        )
    assert SavedTitle.objects.filter(user=user).count() == 2


def test_unknown_runtime_excluded_and_malformed_upstream_rejected(raw_movie):
    from catalog.services import matches

    assert not matches(summary({**raw_movie, "runtime": None}, "movie"), {"runtime_min": 10})
    with pytest.raises(APIError) as exc:
        summary({**raw_movie, "popularity": "invalid"}, "movie")
    assert exc.value.status_code == 502


def test_nonfinite_query_and_blank_search_rejected():
    for query in ("min_rating=nan", "q=%20%20"):
        assert APIClient().get("/api/v1/titles/?" + query, secure=True).status_code == 400


def test_logs_redact_capabilities_and_oauth_parameters():
    import logging

    from common.logging import RedactCapabilities

    record = logging.LogRecord(
        "test",
        logging.INFO,
        "",
        1,
        "GET %s",
        ("/api/v1/shared/secret-capability/?code=secret-code&state=secret-state",),
        None,
    )
    RedactCapabilities().filter(record)
    assert "secret-capability" not in record.getMessage()
    assert "secret-code" not in record.getMessage()
    assert "secret-state" not in record.getMessage()


@pytest.mark.django_db
def test_tmdb_retries_invalid_json_and_budget(monkeypatch, settings):
    settings.TMDB_READ_ACCESS_TOKEN = "test-only"
    responses = [httpx.Response(503), httpx.Response(200, json={"results": []})]
    monkeypatch.setattr(httpx.Client, "get", lambda *a, **kw: responses.pop(0))
    start_budget()
    assert TMDBClient().get("test-retry") == {"results": []}
    monkeypatch.setattr(
        httpx.Client, "get", lambda *a, **kw: httpx.Response(200, content=b"invalid-json")
    )
    with pytest.raises(APIError) as exc:
        TMDBClient().get("test-json")
    assert exc.value.status_code == 502
    monkeypatch.setattr(
        httpx.Client, "get", lambda *a, **kw: httpx.Response(200, json={"results": []})
    )
    start_budget()
    for i in range(8):
        TMDBClient().get(f"budget-{i}")
    with pytest.raises(APIError) as exc:
        TMDBClient().get("budget-9")
    assert exc.value.status_code == 504


@pytest.mark.django_db
def test_expired_and_wrong_purpose_tokens(user):
    AccountToken.objects.create(
        user=user,
        purpose="reset",
        token_hash=digest("expired"),
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    AccountToken.objects.create(
        user=user,
        purpose="reset",
        token_hash=digest("wrong-purpose"),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    for token in ("expired", "wrong-purpose"):
        assert (
            APIClient()
            .post("/api/v1/auth/email/verify/", {"token": token}, format="json", secure=True)
            .status_code
            == 400
        )


def test_google_cannot_link_existing_email(user):
    request = RequestFactory().get("/")
    request.session = {}
    social = SocialLogin(
        user=get_user_model()(email=user.email),
        account=SocialAccount(provider="google", uid="new-google-id"),
        email_addresses=[EmailAddress(email=user.email, verified=True)],
    )
    with pytest.raises(ImmediateHttpResponse) as exc:
        SocialAdapter().pre_social_login(request, social)
    assert "auth=account_link_required" in exc.value.response["Location"]


def test_recent_limit_and_private_snapshots(api, user, title):
    for i in range(1, 53):
        t = TitleSnapshot.objects.create(
            media_type="movie", tmdb_id=1000 + i, summary={**title.summary, "tmdb_id": 1000 + i}
        )
        RecentTitle.objects.create(user=user, title=t)
    api.put("/api/v1/me/recent/movie/550/", secure=True)
    assert RecentTitle.objects.filter(user=user).count() == 50
    response = api.get("/api/v1/me/recent/?page_size=1", secure=True)
    page = response.json()
    assert page["results"][0]["title"]["tmdb_id"] == 550
    cache.delete("snapshot:" + page["meta"]["snapshot"])
    assert api.get(page["next"], secure=True).status_code == 410
