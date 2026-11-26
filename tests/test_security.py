import pytest
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
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


def _app(**overrides):
    return {**settings.APP, **overrides}


def test_oversized_request_is_rejected_before_parsing(client):
    limit = settings.APP["request_max_bytes"]
    response = client.post(
        reverse("login"),
        data=b"x" * (limit + 1),
        content_type="application/octet-stream",
    )

    assert response.status_code == 413
    assert response.json()["error"] == "request_too_large"
    assert response.json()["limit_bytes"] == limit


@override_settings(APP=_app(request_max_bytes=3 * 1024 * 1024))
def test_request_over_total_limit_is_rejected(client):
    response = client.post(
        reverse("login"),
        data=b"x" * (3 * 1024 * 1024 + 1),
        content_type="application/octet-stream",
    )

    assert response.status_code == 413
    assert response.json()["limit_bytes"] == 3 * 1024 * 1024


def test_multi_file_upload_within_limits_is_accepted(client, monkeypatch):
    from documents.services.intake import IntakeResult

    calls = []

    def fake_process_upload(data, filename, content_type, **kwargs):
        calls.append((filename, len(data)))
        return IntakeResult(None, duplicate=False)

    monkeypatch.setattr("documents.views.process_upload", fake_process_upload)

    user = User.objects.create_user("uploader", password="password")
    group, _ = Group.objects.get_or_create(name="admin")
    user.groups.add(group)
    client.force_login(user)

    twenty_mb = b"x" * (20 * 1024 * 1024)
    response = client.post(
        reverse("documents:upload"),
        {
            "document": [
                SimpleUploadedFile("a.pdf", twenty_mb, content_type="application/pdf"),
                SimpleUploadedFile("b.pdf", twenty_mb, content_type="application/pdf"),
            ]
        },
    )

    assert response.status_code == 302
    assert len(calls) == 2
    assert all(size == 20 * 1024 * 1024 for _, size in calls)


def test_single_file_over_per_file_limit_is_rejected(client):
    user = User.objects.create_user("uploader2", password="password")
    group, _ = Group.objects.get_or_create(name="admin")
    user.groups.add(group)
    client.force_login(user)

    oversized = b"x" * (settings.APP["upload_max_bytes"] + 1)
    response = client.post(
        reverse("documents:upload"),
        {
            "document": SimpleUploadedFile(
                "big.pdf", oversized, content_type="application/pdf"
            )
        },
    )

    assert response.status_code == 302
    from django.contrib.messages import get_messages

    messages = [str(m) for m in get_messages(response.wsgi_request)]
    assert any("supera el máximo" in m for m in messages)
    from documents.models import Document

    assert Document.objects.count() == 0
