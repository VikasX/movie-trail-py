import re
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from rest_framework.test import APIClient

from accounts.models import AccountToken


@pytest.mark.django_db
def test_registration_verification_login_reset(settings):
    settings.DEBUG = True  # Local/test email delivery only.
    client = APIClient(enforce_csrf_checks=True)
    token = client.get("/api/v1/auth/csrf/", secure=True).json()["csrf_token"]
    client.credentials(HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="https://testserver")
    data = {
        "email": "new@example.com",
        "password": "Strong-test-password-2030!",
        "display_name": "New Viewer",
    }
    response = client.post("/api/v1/auth/register/", data, format="json", secure=True)
    assert response.status_code == 202
    assert len(mail.outbox) == 1
    assert client.get("/api/v1/me/", secure=True).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login/",
            {"email": data["email"], "password": data["password"]},
            format="json",
            secure=True,
        ).status_code
        == 403
    )
    verify_token = parse_qs(urlsplit(re.search(r"https://\S+", mail.outbox[0].body).group()).query)[
        "token"
    ][0]
    assert verify_token not in AccountToken.objects.get().token_hash
    assert (
        client.post(
            "/api/v1/auth/email/verify/", {"token": verify_token}, format="json", secure=True
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/auth/email/verify/", {"token": verify_token}, format="json", secure=True
        ).status_code
        == 400
    )
    logged = client.post(
        "/api/v1/auth/login/",
        {"email": data["email"], "password": data["password"]},
        format="json",
        secure=True,
    )
    assert logged.status_code == 200
    client.credentials(
        HTTP_X_CSRFTOKEN=logged.json()["csrf_token"], HTTP_ORIGIN="https://testserver"
    )
    assert client.get("/api/v1/me/", secure=True).json()["email_verified"] is True
    assert (
        client.patch(
            "/api/v1/me/", {"preferences": {"region": "US"}}, format="json", secure=True
        ).status_code
        == 200
    )
    # Reset from a different browser; original authenticated session becomes invalid.
    reset = APIClient()
    assert (
        reset.post(
            "/api/v1/auth/password/reset/", {"email": data["email"]}, format="json", secure=True
        ).status_code
        == 202
    )
    reset_token = parse_qs(urlsplit(re.search(r"https://\S+", mail.outbox[-1].body).group()).query)[
        "token"
    ][0]
    assert (
        reset.post(
            "/api/v1/auth/password/reset/confirm/",
            {"token": reset_token, "password": "Other-strong-password-2030!"},
            format="json",
            secure=True,
        ).status_code
        == 200
    )
    assert client.get("/api/v1/me/", secure=True).status_code == 401


@pytest.mark.django_db
def test_csrf_enforced_for_guests_and_missing_credentials():
    client = APIClient(enforce_csrf_checks=True)
    assert (
        client.post(
            "/api/v1/auth/login/",
            {"email": "a@example.com", "password": "example"},
            format="json",
            secure=True,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/recommendations/", {"mode": "surprise"}, format="json", secure=True
        ).status_code
        == 403
    )
    csrf = client.get("/api/v1/auth/csrf/", secure=True).json()["csrf_token"]
    client.credentials(HTTP_X_CSRFTOKEN=csrf, HTTP_ORIGIN="https://testserver")
    assert (
        client.post(
            "/api/v1/auth/login/",
            {"email": "a@example.com", "password": "example"},
            format="json",
            secure=True,
        ).status_code
        == 401
    )


@pytest.mark.django_db
def test_non_enumerating_requests_and_production_email_guard(settings):
    settings.DEBUG = True
    client = APIClient()
    unknown = client.post(
        "/api/v1/auth/password/reset/", {"email": "missing@example.com"}, format="json", secure=True
    )
    assert unknown.status_code == 202 and not mail.outbox
    settings.DEBUG = False
    assert (
        client.post(
            "/api/v1/auth/password/reset/",
            {"email": "missing@example.com"},
            format="json",
            secure=True,
        ).status_code
        == 503
    )


def test_preferences_cannot_grant_staff(api, user):
    response = api.patch("/api/v1/me/", {"is_staff": True}, format="json", secure=True)
    assert response.status_code == 400
    user.refresh_from_db()
    assert not user.is_staff


@pytest.mark.django_db
def test_google_start_pkce_callback_and_state(settings):
    settings.SOCIALACCOUNT_PROVIDERS["google"]["APPS"] = [
        {"client_id": "test-client", "secret": "test-secret", "key": ""}
    ]
    client = APIClient()
    response = client.post(
        "/api/v1/auth/oauth/start/",
        {"provider": "google", "return_to": "/library"},
        format="json",
        secure=True,
    )
    assert response.status_code == 200
    query = parse_qs(urlsplit(response.json()["authorization_url"]).query)
    assert query["redirect_uri"] == ["https://testserver/accounts/google/login/callback/"]
    assert query["code_challenge_method"] == ["S256"]
    assert (
        client.get(
            "/accounts/google/login/callback/?state=invalid&code=example", secure=True
        ).status_code
        == 400
    )
    denied = client.get(
        "/accounts/google/login/callback/",
        {"state": query["state"][0], "error": "access_denied"},
        secure=True,
    )
    assert denied.status_code == 302
    assert "auth=cancelled" in denied["Location"]
    # State is consumed even on cancellation.
    assert (
        client.get(
            "/accounts/google/login/callback/",
            {"state": query["state"][0], "error": "access_denied"},
            secure=True,
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_google_mocked_success_uses_allauth_callback(settings):
    from allauth.socialaccount.models import SocialAccount, SocialLogin

    settings.SOCIALACCOUNT_PROVIDERS["google"]["APPS"] = [
        {"client_id": "test-client", "secret": "test-secret", "key": ""}
    ]
    client = APIClient()
    start = client.post(
        "/api/v1/auth/oauth/start/",
        {"provider": "google", "return_to": "/discover"},
        format="json",
        secure=True,
    )
    state = parse_qs(urlsplit(start.json()["authorization_url"]).query)["state"][0]
    user = get_user_model()(email="google@example.com", first_name="Google", last_name="Viewer")
    from allauth.socialaccount.adapter import get_adapter
    from django.test import RequestFactory

    provider = get_adapter().get_provider(RequestFactory().get("/"), provider="google")
    social = SocialLogin(
        provider=provider,
        user=user,
        account=SocialAccount(provider="google", uid="subject-example"),
        email_addresses=[EmailAddress(email=user.email, verified=True, primary=True)],
    )
    with (
        patch(
            "accounts.oauth.CanonicalGoogleAdapter.get_access_token_data",
            return_value={"access_token": "fake"},
        ),
        patch("accounts.oauth.CanonicalGoogleAdapter.complete_login", return_value=social),
    ):
        response = client.get(
            "/accounts/google/login/callback/", {"state": state, "code": "example"}, secure=True
        )
    assert response.status_code == 302
    assert response["Location"] == "https://frontend.example.com/discover?auth=success"
    profile = client.get("/api/v1/me/", secure=True)
    assert profile.status_code == 200 and profile.json()["providers"] == ["google"]
