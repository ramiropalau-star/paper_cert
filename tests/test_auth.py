from io import StringIO

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from core.permissions import (
    can_delete_documents,
    can_generate_reports,
    can_manage_catalog,
    can_review_documents,
    can_view_documents,
)

pytestmark = pytest.mark.django_db


def make_user(username: str, roles: tuple[str, ...] = ()) -> User:
    user = User.objects.create_user(username, password="password")
    for role in roles:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
    return user


def test_anonymous_request_redirects_to_login(client):
    response = client.get(reverse("home"))

    assert response.status_code == 302
    assert reverse("login") in response["Location"]
    assert "next=/" in response["Location"]


def test_authenticated_user_without_role_is_forbidden(client):
    user = make_user("no-role")
    client.force_login(user)

    assert client.get(reverse("home")).status_code == 403


@pytest.mark.parametrize("role", ["viewer", "reviewer", "admin"])
def test_each_role_can_reach_the_app(client, role):
    user = make_user(f"user-{role}", (role,))
    client.force_login(user)

    assert client.get(reverse("home")).status_code == 200


def test_superuser_can_reach_the_app_without_a_group(client):
    user = User.objects.create_superuser("root", "root@example.com", "password")
    client.force_login(user)

    assert client.get(reverse("home")).status_code == 200


def test_login_and_logout_flow():
    make_user("viewer", ("viewer",))
    client = Client(enforce_csrf_checks=True)

    login_page = client.get(reverse("login"))
    assert login_page.status_code == 200
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
    assert client.get(reverse("home")).status_code == 200

    logout = client.post(
        reverse("logout"),
        {"csrfmiddlewaretoken": client.cookies["csrftoken"].value},
    )
    assert logout.status_code == 302
    assert client.get(reverse("home")).status_code == 302


def test_seed_roles_is_idempotent():
    output = StringIO()
    call_command("seed_roles", stdout=output)
    call_command("seed_roles", stdout=output)

    assert set(Group.objects.values_list("name", flat=True)) == {
        "viewer",
        "reviewer",
        "admin",
    }


def test_role_helpers_follow_the_permission_matrix():
    viewer = make_user("viewer", ("viewer",))
    reviewer = make_user("reviewer", ("reviewer",))
    admin = make_user("admin", ("admin",))
    nobody = make_user("nobody")

    assert can_view_documents(viewer)
    assert can_view_documents(reviewer)
    assert can_view_documents(admin)
    assert not can_view_documents(nobody)

    assert not can_review_documents(viewer)
    assert can_review_documents(reviewer)
    assert can_review_documents(admin)

    assert not can_manage_catalog(reviewer)
    assert can_manage_catalog(admin)
    assert not can_delete_documents(viewer)
    assert can_delete_documents(admin)
    assert can_generate_reports(viewer)
