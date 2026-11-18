# FILE PURPOSE: Tests admin registration, login-page access and staff-only permissions.
# Import admin from django.contrib (Django framework/database/security helpers).
from django.contrib import admin

# Import User from django.contrib.auth.models (Django framework/database/security helpers).
from django.contrib.auth.models import User

# Import Client, RequestFactory from django.test (Django framework/database/security helpers).
from django.test import Client, RequestFactory

# Import SampleRecord from core.models (the named Python helper module).
from core.models import SampleRecord


def test_admin_redirects_anonymous_visitors_to_login():
    # response holds the response produced by the next handler or external HTTP request. Next,
    # look up a named setting/value or make the indicated GET call; the surrounding object
    # determines which.
    response = Client().get("/admin/", secure=True)
    # Test expectation: response.status_code == 302. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 302
    # Test expectation: response['Location'] == '/admin/login/?next=/admin/'. If false, pytest
    # reports a failure at this line.
    assert response["Location"] == "/admin/login/?next=/admin/"


def test_admin_login_page_renders():
    # response holds the response produced by the next handler or external HTTP request. Next,
    # look up a named setting/value or make the indicated GET call; the surrounding object
    # determines which.
    response = Client().get("/admin/login/", secure=True)
    # Test expectation: response.status_code == 200. If false, pytest reports a failure at this
    # line.
    assert response.status_code == 200
    # Test expectation: b'CineScope Administration' in response.content. If false, pytest reports
    # a failure at this line.
    assert b"CineScope Administration" in response.content
    # Test expectation: b'csrfmiddlewaretoken' in response.content. If false, pytest reports a
    # failure at this line.
    assert b"csrfmiddlewaretoken" in response.content


def test_admin_requires_active_staff():
    # Set request: look up a named setting/value or make the indicated GET call; the surrounding
    # object determines which.
    request = RequestFactory().get("/admin/")
    # Set request.user: prepare a User model object in memory; it is written only by save or
    # bulk_create.
    request.user = User(is_active=True, is_staff=False)
    # Test expectation: not admin.site.has_permission(request). If false, pytest reports a failure
    # at this line.
    assert not admin.site.has_permission(request)
    # Set request.user.is_staff: use the boolean True.
    request.user.is_staff = True
    # Test expectation: admin.site.has_permission(request). If false, pytest reports a failure at
    # this line.
    assert admin.site.has_permission(request)
    # Set request.user.is_active: use the boolean False.
    request.user.is_active = False
    # Test expectation: not admin.site.has_permission(request). If false, pytest reports a failure
    # at this line.
    assert not admin.site.has_permission(request)


def test_sample_model_is_registered():
    # Test expectation: admin.site.is_registered(SampleRecord). If false, pytest reports a failure
    # at this line.
    assert admin.site.is_registered(SampleRecord)
