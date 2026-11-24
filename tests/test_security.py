import pytest
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.test import Client, override_settings
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_login_post_without_csrf_token_is_rejected():
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        reverse("login"),
        {"username": "viewer", "password": "password"},
    )

    assert response.status_code == 403


@override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
def test_login_sets_secure_session_cookie_flags():
    user = User.objects.create_user("viewer", password="password")
    group, _ = Group.objects.get_or_create(name="viewer")
    user.groups.add(group)

    client = Client(enforce_csrf_checks=True)
    login_page = client.get(reverse("login"))
    csrf_token = login_page.cookies["csrftoken"].value

    response = client.post(
        reverse("login"),
        {
            "username": "viewer",
            "password": "password",
            "csrfmiddlewaretoken": csrf_token,
        },
    )

    assert response.status_code == 302
    session_cookie = response.cookies[settings.SESSION_COOKIE_NAME]
    assert bool(session_cookie["secure"]) is True
    assert bool(session_cookie["httponly"]) is True
    assert session_cookie["samesite"] == "Lax"


def test_oversized_request_is_rejected_before_parsing(client):
    limit = settings.APP["upload_max_bytes"]
    response = client.post(
        reverse("login"),
        data=b"x" * (limit + 1),
        content_type="application/octet-stream",
    )

    assert response.status_code == 413
    assert response.json()["error"] == "request_too_large"
    assert response.json()["limit_bytes"] == limit
