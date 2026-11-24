import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

pytestmark = pytest.mark.django_db


@pytest.fixture
def users():
    admin_group = Group.objects.create(name="admin")
    superuser = User.objects.create_superuser("root", "root@example.com", "password")
    admin_staff = User.objects.create_user("admin-staff", password="password", is_staff=True)
    admin_staff.groups.add(admin_group)
    plain_staff = User.objects.create_user("plain-staff", password="password", is_staff=True)
    non_staff = User.objects.create_user("non-staff", password="password")
    return {
        "superuser": superuser,
        "admin_staff": admin_staff,
        "plain_staff": plain_staff,
        "non_staff": non_staff,
    }


def test_catalog_admin_requires_admin_role(client, users):
    url = reverse("admin:catalog_language_changelist")

    client.force_login(users["superuser"])
    assert client.get(url).status_code == 200

    client.force_login(users["admin_staff"])
    assert client.get(url).status_code == 200

    client.force_login(users["plain_staff"])
    assert client.get(url).status_code == 403

    client.force_login(users["non_staff"])
    response = client.get(url)
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


def test_user_admin_requires_admin_role(client, users):
    url = reverse("admin:auth_user_changelist")

    client.force_login(users["admin_staff"])
    assert client.get(url).status_code == 200

    client.force_login(users["plain_staff"])
    assert client.get(url).status_code == 403
