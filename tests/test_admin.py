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


def test_admin_panel_access_and_content(client, users):
    url = reverse("admin-panel")

    # Anonymous users are redirected to login.
    assert client.get(url).status_code == 302

    # Viewers cannot access it.
    viewer_group = Group.objects.create(name="viewer")
    viewer = User.objects.create_user("viewer1", password="password")
    viewer.groups.add(viewer_group)
    client.force_login(viewer)
    assert client.get(url).status_code == 403

    # Admins see cards for every subsection.
    client.force_login(users["admin_staff"])
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Aprendizaje del emisor" in content
    assert "Usuarios y acceso" in content
    assert "Configuración del programa" in content

    # Reviewers see learning + users cards but not settings.
    reviewer_group = Group.objects.create(name="reviewer")
    reviewer = User.objects.create_user("reviewer1", password="password")
    reviewer.groups.add(reviewer_group)
    client.force_login(reviewer)
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Aprendizaje del emisor" in content
    assert "Usuarios y acceso" in content
    assert "Configuración del programa" not in content


def test_admin_learning_page(client, users):
    reviewer_group = Group.objects.create(name="reviewer")
    reviewer = User.objects.create_user("reviewer2", password="password")
    reviewer.groups.add(reviewer_group)
    client.force_login(reviewer)

    response = client.get(reverse("admin-learning"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Perfiles de formato" in content
    assert "Aliases de campos" in content
    assert "Verificadores por emisor" in content


def test_admin_users_page(client, users):
    reviewer_group = Group.objects.create(name="reviewer")
    reviewer = User.objects.create_user("reviewer3", password="password")
    reviewer.groups.add(reviewer_group)
    client.force_login(reviewer)

    response = client.get(reverse("admin-users"))
    assert response.status_code == 200
    assert "Cambiar mi contraseña" in response.content.decode()

    client.force_login(users["admin_staff"])
    response = client.get(reverse("admin-users"))
    assert "Usuarios" in response.content.decode()


def test_admin_settings_requires_admin(client, users):
    url = reverse("admin-settings")

    reviewer_group = Group.objects.create(name="reviewer")
    reviewer = User.objects.create_user("reviewer4", password="password")
    reviewer.groups.add(reviewer_group)
    client.force_login(reviewer)
    assert client.get(url).status_code == 403

    client.force_login(users["admin_staff"])
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "ollama_model" in content
    assert "ollama_url" in content
    # Secrets render masked and are never editable inputs.
    assert 'name="email_host_password"' not in content
    assert 'name="internal_api_token"' not in content
    assert 'name="paperless_token"' not in content


def test_admin_settings_save_and_reset(client, users):
    from django.conf import settings

    from core.models import ProgramSetting

    client.force_login(users["admin_staff"])
    original = settings.APP["ollama_timeout_seconds"]

    response = client.post(
        reverse("admin-settings"),
        {"action": "save", "ollama_timeout_seconds": "42.5"},
    )
    assert response.status_code == 302
    assert settings.APP["ollama_timeout_seconds"] == 42.5
    assert ProgramSetting.objects.filter(key="ollama_timeout_seconds").exists()

    client.post(
        reverse("admin-settings"),
        {"action": "reset", "key": "ollama_timeout_seconds"},
    )
    assert settings.APP["ollama_timeout_seconds"] == original
    assert not ProgramSetting.objects.filter(key="ollama_timeout_seconds").exists()


def test_admin_settings_rejects_invalid_value(client, users):
    client.force_login(users["admin_staff"])
    response = client.post(
        reverse("admin-settings"),
        {"action": "save", "ollama_retries": "not-a-number"},
        follow=True,
    )
    assert response.status_code == 200
    messages = [str(m) for m in response.context["messages"]]
    assert any("ollama_retries" in m for m in messages)


def test_admin_settings_rejects_readonly_key(client, users):
    client.force_login(users["admin_staff"])
    response = client.post(
        reverse("admin-settings"),
        {"action": "save", "media_root": "/tmp/evil"},
        follow=True,
    )
    messages = [str(m) for m in response.context["messages"]]
    assert any("no es editable" in m for m in messages)
