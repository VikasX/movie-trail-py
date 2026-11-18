"""Security boundaries tested with two accounts, isolated storage and mocked providers."""

import copy
import io
import logging
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import get_hasher
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.db import close_old_connections, connection
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountToken
from catalog.models import RateLimitBucket
from common.errors import APIError
from common.logging import RedactCapabilities, SafeFormatter
from common.throttling import client_ip, consume
from library.models import Collection, CollectionMembership, PublicShare, SavedTitle, SyncReceipt
from tests.test_library import sync_payload

pytestmark = pytest.mark.django_db


@pytest.fixture
def fixed_window(monkeypatch):
    # Password hashing takes real time. Keep attempts in one known minute rather
    # than accidentally testing two legitimate windows when the wall clock rolls over.
    now = timezone.now()
    monkeypatch.setattr("common.throttling.timezone.now", lambda: now)


@pytest.fixture
def other_user():
    user = get_user_model().objects.create_user(
        username="second-viewer",
        email="second@example.com",
        password="Another-strong-password-2030!",
    )
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    return user


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "me/", None),
        ("patch", "me/", {"display_name": "Name"}),
        ("get", "me/library/", None),
        ("put", "me/library/movie/550/", {"watched": False}),
        ("delete", "me/library/movie/550/", None),
        ("get", "me/recent/", None),
        ("put", "me/recent/movie/550/", None),
        ("get", "me/collections/", None),
        ("post", "me/collections/", {"name": "Name"}),
        ("get", "me/collections/00000000-0000-0000-0000-000000000001/", None),
        ("patch", "me/collections/00000000-0000-0000-0000-000000000001/", {"name": "Name"}),
        ("delete", "me/collections/00000000-0000-0000-0000-000000000001/", None),
        ("put", "me/collections/00000000-0000-0000-0000-000000000001/items/movie/550/", None),
        ("delete", "me/collections/00000000-0000-0000-0000-000000000001/items/movie/550/", None),
        ("put", "me/collections/00000000-0000-0000-0000-000000000001/sharing/", None),
        ("delete", "me/collections/00000000-0000-0000-0000-000000000001/sharing/", None),
        (
            "post",
            "me/guest-sync/",
            {
                "sync_id": "00000000-0000-0000-0000-000000000001",
                "guest_id": "00000000-0000-0000-0000-000000000002",
                "saved_titles": [],
                "collections": [],
            },
        ),
        ("post", "recommendations/", {"mode": "personalized"}),
    ],
)
def test_every_private_operation_requires_a_session(method, path, body):
    kwargs = {"secure": True}
    if body is not None:
        kwargs.update(data=body, format="json")
    response = getattr(APIClient(), method)("/api/v1/" + path, **kwargs)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "suffix",
    [
        "titles/?page_size=51",
        "titles/?page=0",
        "titles/?sort=password",
        "titles/?year_from=2026&year_to=2025",
        "titles/?genres=unknown",
        "titles/?min_rating=11",
        "titles/?runtime_min=601",
        "titles/?q=" + "x" * 201,
        "titles/invalid/550/",
        "titles/movie/0/",
    ],
)
def test_invalid_catalogue_inputs_are_rejected_before_upstream_requests(suffix):
    assert APIClient().get("/api/v1/" + suffix, secure=True).status_code == 400


@pytest.mark.parametrize(
    "variable,value",
    [
        ("ALLOWED_HOSTS", "*"),
        ("ALLOWED_HOSTS", ".example.com"),
        ("CSRF_TRUSTED_ORIGINS", "https://*.example.com"),
        ("CORS_ALLOWED_ORIGINS", "http://frontend.example.com"),
        ("FRONTEND_PUBLIC_ORIGIN", "https://frontend.example.com/discover"),
        ("BACKEND_PUBLIC_ORIGIN", "https://user:password@backend.example.com"),
        ("TMDB_BASE_URL", "https://untrusted.example.com/3"),
    ],
)
def test_unsafe_production_configuration_fails_without_printing_values(variable, value):
    environment = {**os.environ, variable: value, "DEBUG": "False", "VERCEL": "1"}
    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr


@pytest.mark.parametrize(
    "method,suffix,body",
    [
        ("get", "", None),
        ("patch", "", {"name": "Taken over"}),
        ("delete", "", None),
        ("put", "items/movie/550/", None),
        ("delete", "items/movie/550/", None),
        ("put", "sharing/", None),
        ("delete", "sharing/", None),
    ],
)
def test_other_owner_collection_actions_are_hidden(api, other_user, title, method, suffix, body):
    collection = Collection.objects.create(user=other_user, name="Private collection")
    saved = SavedTitle.objects.create(user=other_user, title=title)
    CollectionMembership.objects.create(collection=collection, saved_title=saved)
    url = f"/api/v1/me/collections/{collection.pk}/{suffix}"
    kwargs = {"secure": True}
    if body is not None:
        kwargs.update(data=body, format="json")
    response = getattr(api, method)(url, **kwargs)
    assert response.status_code == 404
    collection.refresh_from_db()
    assert collection.name == "Private collection"
    assert collection.memberships.count() == 1
    assert not PublicShare.objects.exists()


def test_title_mutations_and_snapshots_are_bound_to_the_current_account(
    api, user, other_user, title
):
    other_saved = SavedTitle.objects.create(user=other_user, title=title, watched=False)
    api.put("/api/v1/me/library/movie/550/", {"watched": True}, format="json", secure=True)
    other_saved.refresh_from_db()
    assert not other_saved.watched
    snapshot = api.get("/api/v1/me/library/", secure=True).json()["meta"]["snapshot"]
    other = APIClient()
    other.force_login(other_user)
    response = other.get(f"/api/v1/me/library/?snapshot={snapshot}", secure=True)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "snapshot_mismatch"
    api.delete("/api/v1/me/library/movie/550/", secure=True)
    assert SavedTitle.objects.filter(user=other_user, title=title).exists()
    assert not SavedTitle.objects.filter(user=user).exists()


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("patch", "/api/v1/me/", {"display_name": "Changed"}),
        ("put", "/api/v1/me/library/movie/550/", {"watched": True}),
        ("delete", "/api/v1/me/library/movie/550/", None),
        ("post", "/api/v1/me/collections/", {"name": "New"}),
        ("post", "/api/v1/auth/logout/", None),
    ],
)
def test_authenticated_writes_require_matching_csrf(user, title, method, path, body):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    client.get("/api/v1/auth/csrf/", secure=True)
    kwargs = {"secure": True}
    if body is not None:
        kwargs.update(data=body, format="json")
    assert getattr(client, method)(path, **kwargs).status_code == 403
    assert getattr(client, method)(path, HTTP_X_CSRFTOKEN="invalid", **kwargs).status_code == 403


def test_csrf_rejects_untrusted_origin_even_with_valid_token(user):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    token = client.get("/api/v1/auth/csrf/", secure=True).json()["csrf_token"]
    response = client.post(
        "/api/v1/me/collections/",
        {"name": "Blocked"},
        format="json",
        secure=True,
        HTTP_X_CSRFTOKEN=token,
        HTTP_ORIGIN="https://evil.example",
    )
    assert response.status_code == 403
    assert not Collection.objects.exists()


def test_sync_size_structure_and_account_receipts(api, user, other_user, title):
    payload = sync_payload(title)
    oversized = api.post(
        "/api/v1/me/guest-sync/", " " * (1048576 + 1), content_type="application/json", secure=True
    )
    assert oversized.status_code == 413
    invalid = copy.deepcopy(payload)
    invalid["collections"][0]["user_id"] = other_user.pk
    assert (
        api.post("/api/v1/me/guest-sync/", invalid, format="json", secure=True).status_code == 400
    )
    invalid = copy.deepcopy(payload)
    invalid["saved_titles"][0]["tmdb_id"] = -1
    assert (
        api.post("/api/v1/me/guest-sync/", invalid, format="json", secure=True).status_code == 400
    )
    assert not SyncReceipt.objects.exists()
    first = api.post("/api/v1/me/guest-sync/", payload, format="json", secure=True)
    assert first.status_code == 200
    other = APIClient()
    other.force_login(other_user)
    second = other.post("/api/v1/me/guest-sync/", payload, format="json", secure=True)
    assert second.status_code == 200
    # The same UUID cannot retrieve another account's result or collection mapping.
    assert first.json()["collection_mappings"] != second.json()["collection_mappings"]
    assert SyncReceipt.objects.filter(user=user).count() == 1
    assert SyncReceipt.objects.filter(user=other_user).count() == 1


def test_personalized_and_authenticated_responses_cannot_be_shared_cached(api, monkeypatch):
    monkeypatch.setattr("catalog.recommendations.candidates", lambda *args, **kwargs: [])
    response = api.post(
        "/api/v1/recommendations/", {"mode": "personalized"}, format="json", secure=True
    )
    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store"
    assert api.get("/api/v1/metadata/", secure=True)["Cache-Control"] == "private, no-store"


def test_login_uses_one_hash_for_unknown_and_existing_accounts(user):
    client = APIClient()
    hasher = get_hasher()
    for email in (user.email, "nonexistent@example.com"):
        with patch.object(hasher, "encode", wraps=hasher.encode) as encode:
            response = client.post(
                "/api/v1/auth/login/",
                {
                    "email": email,
                    "password": "Incorrect-example-password-2030!",
                },
                format="json",
                secure=True,
            )
        assert response.status_code == 401
        assert encode.call_count == 1


def test_email_transport_failure_does_not_disclose_accounts(user, settings):
    settings.DEBUG = True
    responses = []
    with patch("accounts.services.send_mail", side_effect=OSError("private SMTP details")):
        for email in (user.email, "unknown@example.com"):
            responses.append(
                APIClient().post(
                    "/api/v1/auth/password/reset/", {"email": email}, format="json", secure=True
                )
            )
        register = APIClient().post(
            "/api/v1/auth/register/",
            {
                "email": "new@example.com",
                "password": "Strong-example-password-2030!",
                "display_name": "New viewer",
            },
            format="json",
            secure=True,
        )
    assert [r.status_code for r in responses] == [202, 202]
    assert responses[0].json() == responses[1].json() == register.json()
    assert not AccountToken.objects.exists()
    assert not get_user_model().objects.filter(email="new@example.com").exists()


def test_login_rotates_session_csrf_and_logout_invalidates_it(user):
    client = APIClient(enforce_csrf_checks=True)
    old_csrf = client.get("/api/v1/auth/csrf/", secure=True).json()["csrf_token"]
    session = client.session
    session["before_login"] = True
    session.save()
    old_session = session.session_key
    client.cookies["sessionid"] = old_session
    old_secret = client.cookies["csrftoken"].value
    response = client.post(
        "/api/v1/auth/login/",
        {
            "email": user.email,
            "password": "Strong-example-password-2030!",
        },
        format="json",
        secure=True,
        HTTP_X_CSRFTOKEN=old_csrf,
        HTTP_ORIGIN="https://testserver",
    )
    assert response.status_code == 200
    session_key = client.cookies["sessionid"].value
    assert session_key != old_session
    assert client.cookies["csrftoken"].value != old_secret
    assert not Session.objects.filter(session_key=old_session).exists()
    cookie = response.cookies["sessionid"]
    assert cookie["secure"] and cookie["httponly"] and cookie["samesite"] == "Lax"
    assert not cookie["domain"]
    logout = client.post(
        "/api/v1/auth/logout/",
        secure=True,
        HTTP_X_CSRFTOKEN=response.json()["csrf_token"],
        HTTP_ORIGIN="https://testserver",
    )
    assert logout.status_code == 204
    assert not Session.objects.filter(session_key=session_key).exists()
    assert client.get("/api/v1/me/", secure=True).status_code == 401


def test_auth_limit_is_shared_across_clients_and_not_reset_by_cache_eviction(
    settings, fixed_window
):
    settings.API_THROTTLING_ENABLED = True
    for _ in range(5):
        response = APIClient().post(
            "/api/v1/auth/login/",
            {
                "email": "unknown@example.com",
                "password": "incorrect",
            },
            format="json",
            secure=True,
        )
        assert response.status_code == 401
    cache.clear()
    response = APIClient().post("/api/v1/auth/login/", {}, format="json", secure=True)
    assert response.status_code == 429
    assert 1 <= int(response["Retry-After"]) <= 60
    assert RateLimitBucket.objects.count() == 2
    # Bootstrap is an ordinary read, not another password attempt.
    assert APIClient().get("/api/v1/auth/csrf/", secure=True).status_code == 200


def test_auth_email_limit_applies_across_different_ips(settings, fixed_window):
    settings.API_THROTTLING_ENABLED = True
    for n in range(6):
        response = APIClient().post(
            "/api/v1/auth/login/",
            {
                "email": "same@example.com",
                "password": "incorrect",
            },
            format="json",
            secure=True,
            REMOTE_ADDR=f"192.0.2.{n + 1}",
        )
        assert response.status_code == (401 if n < 5 else 429)


def test_admin_password_attempts_have_a_separate_limit(settings, fixed_window):
    settings.API_THROTTLING_ENABLED = True
    for _ in range(5):
        assert APIClient().post("/admin/login/", secure=True).status_code == 200
    assert APIClient().post("/admin/login/", secure=True).status_code == 429


def test_forwarded_ip_is_trusted_only_on_vercel(settings):
    request = RequestFactory().get(
        "/",
        REMOTE_ADDR="192.0.2.1",
        HTTP_X_FORWARDED_FOR="192.0.2.99",
        HTTP_X_VERCEL_FORWARDED_FOR="192.0.2.2",
    )
    settings.IS_VERCEL = False
    assert client_ip(request) == "192.0.2.1"
    settings.IS_VERCEL = True
    assert client_ip(request) == "192.0.2.2"


@pytest.mark.django_db(transaction=True)
def test_postgresql_counters_do_not_lose_concurrent_increments(settings, fixed_window):
    if connection.vendor != "postgresql":
        pytest.skip("Requires a separately configured isolated PostgreSQL test database.")
    settings.API_THROTTLING_ENABLED = True

    def attempt(_):
        close_old_connections()
        try:
            consume("concurrent-test", "same-client", 5)
            return True
        except APIError as exc:
            assert exc.status_code == 429
            return False
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(20)))
    assert sum(results) == 5


def test_final_logs_redact_tracebacks_credentials_and_capabilities(settings):
    settings.TMDB_READ_ACCESS_TOKEN = "test-private-bearer-value"
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RedactCapabilities())
    handler.setFormatter(SafeFormatter("%(message)s"))
    try:
        raise RuntimeError(
            "postgresql://user:private-password@db.example/database "
            "test-private-bearer-value /shared/private-capability "
            "?code=private-code sessionid=private-cookie"
        )
    except RuntimeError:
        record = logging.LogRecord(
            "security-test", logging.ERROR, "", 1, "Provider failed", (), sys.exc_info()
        )
        handler.handle(record)
    output = stream.getvalue()
    for secret in (
        "private-password",
        "test-private-bearer-value",
        "private-capability",
        "private-code",
        "private-cookie",
    ):
        assert secret not in output
    assert "RuntimeError" in output


@pytest.mark.parametrize(
    "payload", [None, [], {"results": [None]}, {"results": [], "total_pages": []}]
)
def test_malformed_catalogue_data_is_a_safe_502(api, monkeypatch, payload):
    monkeypatch.setattr("catalog.services.TMDBClient.get", lambda *a, **kw: payload)
    response = api.get("/api/v1/titles/", secure=True)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_invalid"


def test_untrusted_provider_links_are_not_exposed(api, raw_movie, monkeypatch):
    def get(self, path, *args, **kwargs):
        if path.endswith("watch/providers"):
            return {"results": {"IN": {"link": "javascript:alert(1)"}}}
        return {**raw_movie, "credits": {"cast": [], "crew": []}, "videos": {"results": []}}

    monkeypatch.setattr("catalog.services.TMDBClient.get", get)
    response = api.get("/api/v1/titles/movie/550/", secure=True)
    assert response.status_code == 200
    assert response.json()["availability"]["link"] is None
    assert response.json()["availability"]["status"] == "unavailable"


def test_internal_exception_details_never_reach_the_client(api, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("private-password C:/internal/location SECRET_KEY=private")

    monkeypatch.setattr("catalog.services.metadata_values", fail)
    response = api.get("/api/v1/metadata/", secure=True)
    assert response.status_code == 500
    assert b"private-password" not in response.content
    assert b"internal/location" not in response.content


def test_excessively_nested_json_has_a_safe_validation_response():
    response = APIClient().post(
        "/api/v1/recommendations/",
        "[" * 2000 + "0" + "]" * 2000,
        content_type="application/json",
        secure=True,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
