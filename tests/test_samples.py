from unittest.mock import patch

from django.db import OperationalError
from rest_framework.test import APIClient

from core.models import SampleRecord


def test_samples_returns_serialized_rows():
    row = SampleRecord(id=1, name="Demo", message="Read from database")
    with patch("core.views.SampleRecord.objects") as manager:
        manager.all.return_value.__getitem__.return_value = [row]
        response = APIClient().get("/api/v1/samples/", secure=True)
    assert response.status_code == 200
    assert response.json() == [{"id": 1, "name": "Demo", "message": "Read from database"}]
    assert "no-store" in response["Cache-Control"]


def test_samples_hides_database_errors(caplog):
    with patch("core.views.SampleRecord.objects") as manager:
        manager.all.side_effect = OperationalError("private connection details")
        response = APIClient().get("/api/v1/samples/", secure=True)
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable."}
    assert "private connection details" not in caplog.text


def test_samples_rejects_writes():
    assert APIClient().post("/api/v1/samples/", {}, format="json", secure=True).status_code == 405
