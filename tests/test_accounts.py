# FILE PURPOSE: Tests account/CSRF/email flows and mocked Google initiation/callbacks.
# Import re so the code below can use that module namespace.
import re

# Import patch from unittest.mock (the named Python helper module).
from unittest.mock import patch

# Import parse_qs, urlsplit from urllib.parse (the named Python helper module).
from urllib.parse import parse_qs, urlsplit

# Import pytest so the code below can use that module namespace.
import pytest

# Import EmailAddress from allauth.account.models (the maintained account/Google integration).
from allauth.account.models import EmailAddress

# Import get_user_model from django.contrib.auth (Django framework/database/security helpers).
from django.contrib.auth import get_user_model

# Import mail from django.core (Django framework/database/security helpers).
from django.core import mail

# Import APIClient from rest_framework.test (DRF request/response helpers).
from rest_framework.test import APIClient

# Import AccountToken from accounts.models (our account layer).
from accounts.models import AccountToken


@pytest.mark.django_db
def test_registration_verification_login_reset(settings):
    # INPUTS TO THIS FUNCTION: settings = argument supplied by the caller.
    # Set settings.DEBUG: use the boolean True.
    settings.DEBUG = True  # Local/test email delivery only.
    # client holds the reusable interface for requesting TMDB data. Next, call APIClient with the
    # inputs shown; its definition explains the checks, side effects and return value.
    client = APIClient(enforce_csrf_checks=True)
    # Set token: read the entry indexed by 'csrf_token' from client.get('/api/v1/auth/csrf/',
    # secure=True).json().
    token = client.get("/api/v1/auth/csrf/", secure=True).json()["csrf_token"]
    # Call client.credentials with the inputs shown; its definition explains the checks, side
    # effects and return value.
    client.credentials(HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="https://testserver")
    # data holds the cleaned submitted JSON body (or, in normalization helpers, the upstream
    # object being translated). Next, build a dictionary with named fields such as email,
    # password, display_name.
    data = {
        "email": "new@example.com",
        "password": "Strong-test-password-2030!",
        "display_name": "New Viewer",
    }
    # response holds the response produced by the next handler or external HTTP request. Next,
    # call client.post with the inputs shown; its definition explains the checks, side effects and
    # return value.
    response = client.post("/api/v1/auth/register/", data, format="json", secure=True)
    # Test expectation: response.status_code == 202. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 202
    # Test expectation: len(mail.outbox) == 1. If false, pytest reports a failure at this line.
    assert len(mail.outbox) == 1
    # Test expectation: client.get('/api/v1/me/', secure=True).status_code == 401. If false,
    # pytest reports a failure at this line.
    assert client.get("/api/v1/me/", secure=True).status_code == 401
    # Test expectation: client.post('/api/v1/auth/login/', {'email': data['email'], 'password':
    # data['password']}, format='json', secure=True).status_code == 403. If false, pytest reports
    # a failure at this line.
    assert (
        client.post(
            "/api/v1/auth/login/",
            {"email": data["email"], "password": data["password"]},
            format="json",
            secure=True,
        ).status_code
        == 403
    )
    # Set verify_token: read the entry indexed by 0 from
    # parse_qs(urlsplit(re.search('https://\\S+', mail.outbox[0].body).group()).query)['token'].
    verify_token = parse_qs(urlsplit(re.search(r"https://\S+", mail.outbox[0].body).group()).query)[
        "token"
    ][0]
    # Test expectation: verify_token not in AccountToken.objects.get().token_hash. If false,
    # pytest reports a failure at this line.
    assert verify_token not in AccountToken.objects.get().token_hash
    # Test expectation: client.post('/api/v1/auth/email/verify/', {'token': verify_token},
    # format='json', secure=True).status_code == 200. If false, pytest reports a failure at this
    # line.
    assert (
        client.post(
            "/api/v1/auth/email/verify/", {"token": verify_token}, format="json", secure=True
        ).status_code
        == 200
    )
    # Test expectation: client.post('/api/v1/auth/email/verify/', {'token': verify_token},
    # format='json', secure=True).status_code == 400. If false, pytest reports a failure at this
    # line.
    assert (
        client.post(
            "/api/v1/auth/email/verify/", {"token": verify_token}, format="json", secure=True
        ).status_code
        == 400
    )
    # Set logged: call client.post with the inputs shown; its definition explains the checks, side
    # effects and return value.
    logged = client.post(
        "/api/v1/auth/login/",
        {"email": data["email"], "password": data["password"]},
        format="json",
        secure=True,
    )
    # Test expectation: logged.status_code == 200. If false, pytest reports a failure at this
    # line.
    assert logged.status_code == 200
    # Call client.credentials with the inputs shown; its definition explains the checks, side
    # effects and return value.
    client.credentials(
        HTTP_X_CSRFTOKEN=logged.json()["csrf_token"], HTTP_ORIGIN="https://testserver"
    )
    # Test expectation: client.get('/api/v1/me/', secure=True).json()['email_verified'] is True.
    # If false, pytest reports a failure at this line.
    assert client.get("/api/v1/me/", secure=True).json()["email_verified"] is True
    # Test expectation: client.patch('/api/v1/me/', {'preferences': {'region': 'US'}},
    # format='json', secure=True).status_code == 200. If false, pytest reports a failure at this
    # line.
    assert (
        client.patch(
            "/api/v1/me/", {"preferences": {"region": "US"}}, format="json", secure=True
        ).status_code
        == 200
    )
    # Reset from a different browser; original authenticated session becomes invalid.
    # Set reset: call APIClient with the inputs shown; its definition explains the checks, side
    # effects and return value.
    reset = APIClient()
    # Test expectation: reset.post('/api/v1/auth/password/reset/', {'email': data['email']},
    # format='json', secure=True).status_code == 202. If false, pytest reports a failure at this
    # line.
    assert (
        reset.post(
            "/api/v1/auth/password/reset/", {"email": data["email"]}, format="json", secure=True
        ).status_code
        == 202
    )
    # Set reset_token: read the entry indexed by 0 from
    # parse_qs(urlsplit(re.search('https://\\S+', mail.outbox[-1].body).group()).query)['token'].
    reset_token = parse_qs(urlsplit(re.search(r"https://\S+", mail.outbox[-1].body).group()).query)[
        "token"
    ][0]
    # Test expectation: reset.post('/api/v1/auth/password/reset/confirm/', {'token': reset_token,
    # 'password': 'Other-strong-password-2030!'}, format='json', secure=True).status_code == 200.
    # If false, pytest reports a failure at this line.
    assert (
        reset.post(
            "/api/v1/auth/password/reset/confirm/",
            {"token": reset_token, "password": "Other-strong-password-2030!"},
            format="json",
            secure=True,
        ).status_code
        == 200
    )
    # Test expectation: client.get('/api/v1/me/', secure=True).status_code == 401. If false,
    # pytest reports a failure at this line.
    assert client.get("/api/v1/me/", secure=True).status_code == 401


@pytest.mark.django_db
def test_csrf_enforced_for_guests_and_missing_credentials():
    # client holds the reusable interface for requesting TMDB data. Next, call APIClient with the
    # inputs shown; its definition explains the checks, side effects and return value.
    client = APIClient(enforce_csrf_checks=True)
    # Test expectation: client.post('/api/v1/auth/login/', {'email': 'a@example.com', 'password':
    # 'example'}, format='json', secure=True).status_code == 403. If false, pytest reports a
    # failure at this line.
    assert (
        client.post(
            "/api/v1/auth/login/",
            {"email": "a@example.com", "password": "example"},
            format="json",
            secure=True,
        ).status_code
        == 403
    )
    # Test expectation: client.post('/api/v1/recommendations/', {'mode': 'surprise'},
    # format='json', secure=True).status_code == 403. If false, pytest reports a failure at this
    # line.
    assert (
        client.post(
            "/api/v1/recommendations/", {"mode": "surprise"}, format="json", secure=True
        ).status_code
        == 403
    )
    # Set csrf: read the entry indexed by 'csrf_token' from client.get('/api/v1/auth/csrf/',
    # secure=True).json().
    csrf = client.get("/api/v1/auth/csrf/", secure=True).json()["csrf_token"]
    # Call client.credentials with the inputs shown; its definition explains the checks, side
    # effects and return value.
    client.credentials(HTTP_X_CSRFTOKEN=csrf, HTTP_ORIGIN="https://testserver")
    # Test expectation: client.post('/api/v1/auth/login/', {'email': 'a@example.com', 'password':
    # 'example'}, format='json', secure=True).status_code == 401. If false, pytest reports a
    # failure at this line.
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
    # INPUTS TO THIS FUNCTION: settings = argument supplied by the caller.
    # Set settings.DEBUG: use the boolean True.
    settings.DEBUG = True
    # client holds the reusable interface for requesting TMDB data. Next, call APIClient with the
    # inputs shown; its definition explains the checks, side effects and return value.
    client = APIClient()
    # Set unknown: call client.post with the inputs shown; its definition explains the checks,
    # side effects and return value.
    unknown = client.post(
        "/api/v1/auth/password/reset/", {"email": "missing@example.com"}, format="json", secure=True
    )
    # Test expectation: unknown.status_code == 202 and (not mail.outbox). If false, pytest reports
    # a failure at this line.
    assert unknown.status_code == 202 and not mail.outbox
    # Set settings.DEBUG: use the boolean False.
    settings.DEBUG = False
    # Test expectation: client.post('/api/v1/auth/password/reset/', {'email':
    # 'missing@example.com'}, format='json', secure=True).status_code == 503. If false, pytest
    # reports a failure at this line.
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
    # INPUTS TO THIS FUNCTION: api = argument supplied by the caller; user = Django account.
    # response holds the response produced by the next handler or external HTTP request. Next,
    # call api.patch with the inputs shown; its definition explains the checks, side effects and
    # return value.
    response = api.patch("/api/v1/me/", {"is_staff": True}, format="json", secure=True)
    # Test expectation: response.status_code == 400. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 400
    # Call user.refresh_from_db with the inputs shown; its definition explains the checks, side
    # effects and return value.
    user.refresh_from_db()
    # Test expectation: not user.is_staff. If false, pytest reports a failure at this line.
    assert not user.is_staff


@pytest.mark.django_db
def test_google_start_pkce_callback_and_state(settings):
    # INPUTS TO THIS FUNCTION: settings = argument supplied by the caller.
    # Set settings.SOCIALACCOUNT_PROVIDERS['google']['APPS']: build an ordered list of 1 entries.
    settings.SOCIALACCOUNT_PROVIDERS["google"]["APPS"] = [
        {"client_id": "test-client", "secret": "test-secret", "key": ""}
    ]
    # client holds the reusable interface for requesting TMDB data. Next, call APIClient with the
    # inputs shown; its definition explains the checks, side effects and return value.
    client = APIClient()
    # response holds the response produced by the next handler or external HTTP request. Next,
    # call client.post with the inputs shown; its definition explains the checks, side effects and
    # return value.
    response = client.post(
        "/api/v1/auth/oauth/start/",
        {"provider": "google", "return_to": "/library"},
        format="json",
        secure=True,
    )
    # Test expectation: response.status_code == 200. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 200
    # query holds the outgoing parameter dictionary, built without changing the caller input in
    # place. Next, call parse_qs with the inputs shown; its definition explains the checks, side
    # effects and return value.
    query = parse_qs(urlsplit(response.json()["authorization_url"]).query)
    # Test expectation: query['redirect_uri'] ==
    # ['https://testserver/accounts/google/login/callback/']. If false, pytest reports a failure
    # at this line.
    assert query["redirect_uri"] == ["https://testserver/accounts/google/login/callback/"]
    # Test expectation: query['code_challenge_method'] == ['S256']. If false, pytest reports a
    # failure at this line.
    assert query["code_challenge_method"] == ["S256"]
    # Test expectation: client.get('/accounts/google/login/callback/?state=invalid&code=example',
    # secure=True).status_code == 400. If false, pytest reports a failure at this line.
    assert (
        client.get(
            "/accounts/google/login/callback/?state=invalid&code=example", secure=True
        ).status_code
        == 400
    )
    # Set denied: look up a named setting/value or make the indicated GET call; the surrounding
    # object determines which.
    denied = client.get(
        "/accounts/google/login/callback/",
        {"state": query["state"][0], "error": "access_denied"},
        secure=True,
    )
    # Test expectation: denied.status_code == 302. If false, pytest reports a failure at this
    # line.
    assert denied.status_code == 302
    # Test expectation: 'auth=cancelled' in denied['Location']. If false, pytest reports a failure
    # at this line.
    assert "auth=cancelled" in denied["Location"]
    # State is consumed even on cancellation.
    # Test expectation: client.get('/accounts/google/login/callback/', {'state':
    # query['state'][0], 'error': 'access_denied'}, secure=True).status_code == 400. If false,
    # pytest reports a failure at this line.
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
    # INPUTS TO THIS FUNCTION: settings = argument supplied by the caller.
    # Import SocialAccount, SocialLogin from allauth.socialaccount.models (the maintained
    # account/Google integration).
    from allauth.socialaccount.models import SocialAccount, SocialLogin

    # Set settings.SOCIALACCOUNT_PROVIDERS['google']['APPS']: build an ordered list of 1 entries.
    settings.SOCIALACCOUNT_PROVIDERS["google"]["APPS"] = [
        {"client_id": "test-client", "secret": "test-secret", "key": ""}
    ]
    # client holds the reusable interface for requesting TMDB data. Next, call APIClient with the
    # inputs shown; its definition explains the checks, side effects and return value.
    client = APIClient()
    # Set start: call client.post with the inputs shown; its definition explains the checks, side
    # effects and return value.
    start = client.post(
        "/api/v1/auth/oauth/start/",
        {"provider": "google", "return_to": "/discover"},
        format="json",
        secure=True,
    )
    # Set state: read the entry indexed by 0 from
    # parse_qs(urlsplit(start.json()['authorization_url']).query)['state'].
    state = parse_qs(urlsplit(start.json()["authorization_url"]).query)["state"][0]
    # user holds the Django account involved in this action; do not confuse it with the client-
    # submitted email string. Next, call get_user_model() with the inputs shown; its definition
    # explains the checks, side effects and return value.
    user = get_user_model()(email="google@example.com", first_name="Google", last_name="Viewer")
    # Import get_adapter from allauth.socialaccount.adapter (the maintained account/Google
    # integration).
    from allauth.socialaccount.adapter import get_adapter

    # Import RequestFactory from django.test (Django framework/database/security helpers).
    from django.test import RequestFactory

    # provider holds allauth Google provider object; it owns authorization/state/PKCE
    # construction. Next, call get_adapter().get_provider with the inputs shown; its definition
    # explains the checks, side effects and return value.
    provider = get_adapter().get_provider(RequestFactory().get("/"), provider="google")
    # Set social: call SocialLogin with the inputs shown; its definition explains the checks, side
    # effects and return value.
    social = SocialLogin(
        provider=provider,
        user=user,
        account=SocialAccount(provider="google", uid="subject-example"),
        email_addresses=[EmailAddress(email=user.email, verified=True, primary=True)],
    )
    # Temporarily replace the indicated dependency for this test, then automatically restore it
    # after the block.
    with (
        patch(
            "accounts.oauth.CanonicalGoogleAdapter.get_access_token_data",
            return_value={"access_token": "fake"},
        ),
        patch("accounts.oauth.CanonicalGoogleAdapter.complete_login", return_value=social),
    ):
        # response holds the response produced by the next handler or external HTTP request. Next,
        # look up a named setting/value or make the indicated GET call; the surrounding object
        # determines which.
        response = client.get(
            "/accounts/google/login/callback/", {"state": state, "code": "example"}, secure=True
        )
    # Test expectation: response.status_code == 302. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 302
    # Test expectation: response['Location'] ==
    # 'https://frontend.example.com/discover?auth=success'. If false, pytest reports a failure at
    # this line.
    assert response["Location"] == "https://frontend.example.com/discover?auth=success"
    # Set profile: look up a named setting/value or make the indicated GET call; the surrounding
    # object determines which.
    profile = client.get("/api/v1/me/", secure=True)
    # Test expectation: profile.status_code == 200 and profile.json()['providers'] == ['google'].
    # If false, pytest reports a failure at this line.
    assert profile.status_code == 200 and profile.json()["providers"] == ["google"]
