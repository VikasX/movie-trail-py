from django.contrib import admin
from django.contrib.auth.models import User
from django.test import Client, RequestFactory

from core.models import SampleRecord


def test_admin_redirects_anonymous_visitors_to_login():
    response = Client().get("/admin/", secure=True)
    assert response.status_code == 302
    assert response["Location"] == "/admin/login/?next=/admin/"


def test_admin_login_page_renders():
    response = Client().get("/admin/login/", secure=True)
    assert response.status_code == 200
    assert b"CineScope Administration" in response.content
    assert b"csrfmiddlewaretoken" in response.content


def test_admin_requires_active_staff():
    request = RequestFactory().get("/admin/")
    request.user = User(is_active=True, is_staff=False)
    assert not admin.site.has_permission(request)
    request.user.is_staff = True
    assert admin.site.has_permission(request)
    request.user.is_active = False
    assert not admin.site.has_permission(request)


def test_sample_model_is_registered():
    assert admin.site.is_registered(SampleRecord)
