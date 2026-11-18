# FILE PURPOSE: Tests the original demonstration endpoint without querying the real database.
# Import patch from unittest.mock (the named Python helper module).
from unittest.mock import patch

# Import OperationalError from django.db (Django framework/database/security helpers).
from django.db import OperationalError

# Import APIClient from rest_framework.test (DRF request/response helpers).
from rest_framework.test import APIClient

# Import SampleRecord from core.models (the named Python helper module).
from core.models import SampleRecord


def test_samples_returns_serialized_rows():
    # row holds the current database object being read or changed; its model is identified by the
    # query/constructor below. Next, call SampleRecord with the inputs shown; its definition
    # explains the checks, side effects and return value.
    row = SampleRecord(id=1, name="Demo", message="Read from database")
    # Temporarily replace the indicated dependency for this test, then automatically restore it
    # after the block.
    with patch("core.views.SampleRecord.objects") as manager:
        # Set manager.all.return_value.__getitem__.return_value: build an ordered list of 1
        # entries.
        manager.all.return_value.__getitem__.return_value = [row]
        # response holds the response produced by the next handler or external HTTP request. Next,
        # look up a named setting/value or make the indicated GET call; the surrounding object
        # determines which.
        response = APIClient().get("/api/v1/samples/", secure=True)
    # Test expectation: response.status_code == 200. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 200
    # Test expectation: response.json() == [{'id': 1, 'name': 'Demo', 'message': 'Read from
    # database'}]. If false, pytest reports a failure at this line.
    assert response.json() == [{"id": 1, "name": "Demo", "message": "Read from database"}]
    # Test expectation: 'no-store' in response['Cache-Control']. If false, pytest reports a
    # failure at this line.
    assert "no-store" in response["Cache-Control"]


def test_samples_hides_database_errors(caplog):
    # INPUTS TO THIS FUNCTION: caplog = argument supplied by the caller.
    # Temporarily replace the indicated dependency for this test, then automatically restore it
    # after the block.
    with patch("core.views.SampleRecord.objects") as manager:
        # Set manager.all.side_effect: call OperationalError with the inputs shown; its definition
        # explains the checks, side effects and return value.
        manager.all.side_effect = OperationalError("private connection details")
        # response holds the response produced by the next handler or external HTTP request. Next,
        # look up a named setting/value or make the indicated GET call; the surrounding object
        # determines which.
        response = APIClient().get("/api/v1/samples/", secure=True)
    # Test expectation: response.status_code == 503. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 503
    # Test expectation: response.json() == {'detail': 'Database unavailable.'}. If false, pytest
    # reports a failure at this line.
    assert response.json() == {"detail": "Database unavailable."}
    # Test expectation: 'private connection details' not in caplog.text. If false, pytest reports
    # a failure at this line.
    assert "private connection details" not in caplog.text


def test_samples_rejects_writes():
    # Test expectation: APIClient().post('/api/v1/samples/', {}, format='json',
    # secure=True).status_code == 405. If false, pytest reports a failure at this line.
    assert APIClient().post("/api/v1/samples/", {}, format="json", secure=True).status_code == 405
