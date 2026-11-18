# FILE PURPOSE: Tests the original health endpoints and basic JSON/security behavior.
# Import MagicMock, patch from unittest.mock (the named Python helper module).
from unittest.mock import MagicMock, patch

# Import pytest so the code below can use that module namespace.
import pytest

# Import OperationalError from django.db (Django framework/database/security helpers).
from django.db import OperationalError

# Import reverse from django.urls (Django framework/database/security helpers).
from django.urls import reverse

# Import APIClient from rest_framework.test (DRF request/response helpers).
from rest_framework.test import APIClient


@pytest.fixture
def client():
    # Return the result to the caller: call APIClient with the inputs shown; its definition
    # explains the checks, side effects and return value.
    return APIClient()


def test_health_is_public_json_and_does_not_touch_database(client):
    # pytest-django blocks real database access in unmarked tests.
    # INPUTS TO THIS FUNCTION: client = argument supplied by the caller.
    # response holds the response produced by the next handler or external HTTP request. Next,
    # look up a named setting/value or make the indicated GET call; the surrounding object
    # determines which.
    response = client.get(reverse("core:health"), secure=True)
    # Test expectation: response.status_code == 200. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 200
    # Test expectation: response.json() == {'status': 'ok', 'service': 'CineScope API'}. If false,
    # pytest reports a failure at this line.
    assert response.json() == {"status": "ok", "service": "CineScope API"}
    # Test expectation: response['Content-Type'] == 'application/json'. If false, pytest reports a
    # failure at this line.
    assert response["Content-Type"] == "application/json"
    # Test expectation: 'no-store' in response['Cache-Control']. If false, pytest reports a
    # failure at this line.
    assert "no-store" in response["Cache-Control"]


def test_database_health_executes_query(client):
    # INPUTS TO THIS FUNCTION: client = argument supplied by the caller.
    # Set cursor: call MagicMock with the inputs shown; its definition explains the checks, side
    # effects and return value.
    cursor = MagicMock()
    # Set cursor.fetchone.return_value: keep these related values together as a tuple: 1.
    cursor.fetchone.return_value = (1,)
    # Temporarily replace the indicated dependency for this test, then automatically restore it
    # after the block.
    with patch("core.views.connection") as connection:
        # Set connection.cursor.return_value.__enter__.return_value: reuse cursor, which was
        # prepared earlier in this function.
        connection.cursor.return_value.__enter__.return_value = cursor
        # response holds the response produced by the next handler or external HTTP request. Next,
        # look up a named setting/value or make the indicated GET call; the surrounding object
        # determines which.
        response = client.get(reverse("core:health-db"), secure=True)
    # Call cursor.execute.assert_called_once_with with the inputs shown; its definition explains
    # the checks, side effects and return value.
    cursor.execute.assert_called_once_with("SELECT 1")
    # Test expectation: response.status_code == 200. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 200
    # Test expectation: response.json() == {'status': 'ok', 'database': 'connected'}. If false,
    # pytest reports a failure at this line.
    assert response.json() == {"status": "ok", "database": "connected"}


def test_database_failure_does_not_leak_details(client, caplog):
    # INPUTS TO THIS FUNCTION: client = argument supplied by the caller; caplog = argument
    # supplied by the caller.
    # Set private_detail: use the fixed value 'private database password and internal hostname'.
    private_detail = "private database password and internal hostname"
    # Temporarily replace the indicated dependency for this test, then automatically restore it
    # after the block.
    with patch("core.views.connection") as connection:
        # Set connection.cursor.side_effect: call OperationalError with the inputs shown; its
        # definition explains the checks, side effects and return value.
        connection.cursor.side_effect = OperationalError(private_detail)
        # response holds the response produced by the next handler or external HTTP request. Next,
        # look up a named setting/value or make the indicated GET call; the surrounding object
        # determines which.
        response = client.get(reverse("core:health-db"), secure=True)
    # Test expectation: response.status_code == 503. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 503
    # Test expectation: response.json() == {'status': 'error', 'database': 'unavailable'}. If
    # false, pytest reports a failure at this line.
    assert response.json() == {"status": "error", "database": "unavailable"}
    # Test expectation: private_detail not in response.content.decode(). If false, pytest reports
    # a failure at this line.
    assert private_detail not in response.content.decode()
    # Test expectation: private_detail not in caplog.text. If false, pytest reports a failure at
    # this line.
    assert private_detail not in caplog.text
    # Test expectation: 'no-store' in response['Cache-Control']. If false, pytest reports a
    # failure at this line.
    assert "no-store" in response["Cache-Control"]


def test_database_health_rejects_unexpected_query_result(client):
    # INPUTS TO THIS FUNCTION: client = argument supplied by the caller.
    # Temporarily replace the indicated dependency for this test, then automatically restore it
    # after the block.
    with patch("core.views.connection") as connection:
        # Set connection.cursor.return_value.__enter__.return_value.fetchone.return_value: use
        # None to represent no known value (JSON null at the API boundary).
        connection.cursor.return_value.__enter__.return_value.fetchone.return_value = None
        # response holds the response produced by the next handler or external HTTP request. Next,
        # look up a named setting/value or make the indicated GET call; the surrounding object
        # determines which.
        response = client.get(reverse("core:health-db"), secure=True)
    # Test expectation: response.status_code == 503. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 503


@pytest.mark.parametrize("path", ["/api/v1/health/", "/api/v1/health/db/"])
def test_health_rejects_post(client, path):
    # INPUTS TO THIS FUNCTION: client = argument supplied by the caller; path = argument supplied
    # by the caller.
    # Test expectation: client.post(path, {}, format='json', secure=True).status_code == 405. If
    # false, pytest reports a failure at this line.
    assert client.post(path, {}, format="json", secure=True).status_code == 405


def test_schema_describes_both_health_routes(client):
    # INPUTS TO THIS FUNCTION: client = argument supplied by the caller.
    # response holds the response produced by the next handler or external HTTP request. Next,
    # look up a named setting/value or make the indicated GET call; the surrounding object
    # determines which.
    response = client.get("/api/schema/?format=json", secure=True)
    # Test expectation: response.status_code == 200. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 200
    # Set paths: read the entry indexed by 'paths' from response.json().
    paths = response.json()["paths"]
    # Test expectation: {'/api/v1/health/', '/api/v1/health/db/',
    # '/api/v1/samples/'}.issubset(paths). If false, pytest reports a failure at this line.
    assert {"/api/v1/health/", "/api/v1/health/db/", "/api/v1/samples/"}.issubset(paths)
    # Test expectation: {'200', '503'}.issubset(paths['/api/v1/health/db/']['get']['responses']).
    # If false, pytest reports a failure at this line.
    assert {"200", "503"}.issubset(paths["/api/v1/health/db/"]["get"]["responses"])


def test_swagger_ui_is_available(client):
    # INPUTS TO THIS FUNCTION: client = argument supplied by the caller.
    # response holds the response produced by the next handler or external HTTP request. Next,
    # look up a named setting/value or make the indicated GET call; the surrounding object
    # determines which.
    response = client.get("/api/docs/", secure=True)
    # Test expectation: response.status_code == 200. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 200
    # Test expectation: b'SwaggerUIBundle' in response.content. If false, pytest reports a failure
    # at this line.
    assert b"SwaggerUIBundle" in response.content


def test_production_redirects_http_to_https(client):
    # INPUTS TO THIS FUNCTION: client = argument supplied by the caller.
    # response holds the response produced by the next handler or external HTTP request. Next,
    # look up a named setting/value or make the indicated GET call; the surrounding object
    # determines which.
    response = client.get("/api/v1/health/")
    # Test expectation: response.status_code == 301. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 301
    # Test expectation: response['Location'] == 'https://testserver/api/v1/health/'. If false,
    # pytest reports a failure at this line.
    assert response["Location"] == "https://testserver/api/v1/health/"


@pytest.mark.parametrize(
    "origin,allowed",
    [
        ("https://frontend.example.com", True),
        ("https://untrusted.example.com", False),
    ],
)
def test_cors_only_allows_configured_origins(client, origin, allowed):
    # INPUTS TO THIS FUNCTION: client = argument supplied by the caller; origin = argument
    # supplied by the caller; allowed = argument supplied by the caller.
    # response holds the response produced by the next handler or external HTTP request. Next,
    # look up a named setting/value or make the indicated GET call; the surrounding object
    # determines which.
    response = client.get("/api/v1/health/", secure=True, HTTP_ORIGIN=origin)
    # Test expectation: (response.get('Access-Control-Allow-Origin') == origin) is allowed. If
    # false, pytest reports a failure at this line.
    assert (response.get("Access-Control-Allow-Origin") == origin) is allowed


def test_unknown_host_is_rejected(client):
    # INPUTS TO THIS FUNCTION: client = argument supplied by the caller.
    # response holds the response produced by the next handler or external HTTP request. Next,
    # look up a named setting/value or make the indicated GET call; the surrounding object
    # determines which.
    response = client.get("/api/v1/health/", secure=True, HTTP_HOST="untrusted.example.com")
    # Test expectation: response.status_code == 400. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 400
