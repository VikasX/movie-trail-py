from unittest.mock import MagicMock, patch

import pytest
from django.db import OperationalError
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.fixture
def client():
    return APIClient()


def test_health_is_public_json_and_does_not_touch_database(client):
    # pytest-django blocks real database access in unmarked tests.
    response = client.get(reverse("core:health"), secure=True)
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "CineScope API"}
    assert response["Content-Type"] == "application/json"
    assert "no-store" in response["Cache-Control"]


def test_database_health_executes_query(client):
    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)
    with patch("core.views.connection") as connection:
        connection.cursor.return_value.__enter__.return_value = cursor
        response = client.get(reverse("core:health-db"), secure=True)
    cursor.execute.assert_called_once_with("SELECT 1")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_database_failure_does_not_leak_details(client, caplog):
    private_detail = "private database password and internal hostname"
    with patch("core.views.connection") as connection:
        connection.cursor.side_effect = OperationalError(private_detail)
        response = client.get(reverse("core:health-db"), secure=True)
    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}
    assert private_detail not in response.content.decode()
    assert private_detail not in caplog.text
    assert "no-store" in response["Cache-Control"]


def test_database_health_rejects_unexpected_query_result(client):
    with patch("core.views.connection") as connection:
        connection.cursor.return_value.__enter__.return_value.fetchone.return_value = None
        response = client.get(reverse("core:health-db"), secure=True)
    assert response.status_code == 503


@pytest.mark.parametrize("path", ["/api/v1/health/", "/api/v1/health/db/"])
def test_health_rejects_post(client, path):
    assert client.post(path, {}, format="json", secure=True).status_code == 405


def test_schema_describes_both_health_routes(client):
    response = client.get("/api/schema/?format=json", secure=True)
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert {"/api/v1/health/", "/api/v1/health/db/", "/api/v1/samples/"}.issubset(paths)
    assert {"200", "503"}.issubset(paths["/api/v1/health/db/"]["get"]["responses"])


def test_swagger_ui_is_available(client):
    response = client.get("/api/docs/", secure=True)
    assert response.status_code == 200
    assert b"SwaggerUIBundle" in response.content


def test_production_redirects_http_to_https(client):
    response = client.get("/api/v1/health/")
    assert response.status_code == 301
    assert response["Location"] == "https://testserver/api/v1/health/"


@pytest.mark.parametrize(
    "origin,allowed",
    [
        ("https://frontend.example.com", True),
        ("https://untrusted.example.com", False),
    ],
)
def test_cors_only_allows_configured_origins(client, origin, allowed):
    response = client.get("/api/v1/health/", secure=True, HTTP_ORIGIN=origin)
    assert (response.get("Access-Control-Allow-Origin") == origin) is allowed


def test_unknown_host_is_rejected(client):
    response = client.get("/api/v1/health/", secure=True, HTTP_HOST="untrusted.example.com")
    assert response.status_code == 400
