import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def roles(db):
    call_command("seed_roles", verbosity=0)


def make_user(username: str, role: str | None = None, **kwargs) -> User:
    user = User.objects.create_user(username, password="password123", **kwargs)
    if role:
        user.groups.add(Group.objects.get(name=role))
    return user


def admin_client() -> Client:
    client = Client()
    client.force_login(make_user("root", "admin"))
    return client


# --- 4.1 permission matrix ---


@pytest.mark.parametrize("role", ["viewer", "reviewer"])
def test_user_management_denied_for_non_admins(role):
    client = Client()
    client.force_login(make_user(f"u-{role}", role))

    assert client.get(reverse("accounts:user_list")).status_code == 403
    assert client.get(reverse("accounts:user_create")).status_code == 403
    target = make_user("target", "viewer")
    assert client.get(reverse("accounts:user_edit", args=[target.pk])).status_code == 403
    assert client.post(reverse("accounts:user_create")).status_code == 403


def test_user_management_requires_login(client):
    assert client.get(reverse("accounts:user_list")).status_code == 302


def test_admin_sees_user_list():
    client = admin_client()
    make_user("listed", "viewer")

    response = client.get(reverse("accounts:user_list"))

    assert response.status_code == 200
    assert "listed" in response.content.decode()


# --- 4.2 create ---


def test_create_user_with_role_can_log_in():
    client = admin_client()

    response = client.post(
        reverse("accounts:user_create"),
        {"username": "newbie", "password": "Str0ng!Pass", "role": "reviewer"},
    )

    assert response.status_code == 302
    user = User.objects.get(username="newbie")
    assert user.groups.filter(name="reviewer").exists()
    assert Client().login(username="newbie", password="Str0ng!Pass")


def test_create_duplicate_username_rejected():
    client = admin_client()
    make_user("dup", "viewer")

    response = client.post(
        reverse("accounts:user_create"),
        {"username": "dup", "password": "Str0ng!Pass", "role": "viewer"},
        follow=True,
    )

    assert "Ya existe un usuario" in response.content.decode()
    assert User.objects.filter(username="dup").count() == 1


def test_create_weak_password_rejected():
    client = admin_client()

    response = client.post(
        reverse("accounts:user_create"),
        {"username": "weak", "password": "123", "role": "viewer"},
        follow=True,
    )

    content = response.content.decode()
    assert "contraseña" in content.lower() or "corta" in content.lower()
    assert not User.objects.filter(username="weak").exists()


def test_create_requires_role():
    client = admin_client()

    client.post(
        reverse("accounts:user_create"),
        {"username": "norole", "password": "Str0ng!Pass"},
    )

    assert not User.objects.filter(username="norole").exists()


# --- 4.3 edit ---


def test_edit_changes_role():
    client = admin_client()
    target = make_user("promoted", "viewer")

    client.post(
        reverse("accounts:user_edit", args=[target.pk]),
        {"role": "reviewer", "is_active": "on"},
    )

    target.refresh_from_db()
    assert target.groups.filter(name="reviewer").exists()
    assert not target.groups.filter(name="viewer").exists()


def test_deactivate_blocks_login():
    client = admin_client()
    target = make_user("leaver", "viewer")

    client.post(
        reverse("accounts:user_edit", args=[target.pk]),
        {"role": "viewer"},  # is_active omitted -> inactive
    )

    target.refresh_from_db()
    assert not target.is_active
    assert not Client().login(username="leaver", password="password123")


def test_self_cannot_deactivate():
    client = admin_client()
    admin = User.objects.get(username="root")

    client.post(
        reverse("accounts:user_edit", args=[admin.pk]),
        {"role": "admin"},  # no is_active
    )

    admin.refresh_from_db()
    assert admin.is_active


def test_cannot_remove_last_active_admin():
    client = admin_client()
    root = User.objects.get(username="root")  # sole admin-group user

    # Demoting yourself while being the last active admin is blocked.
    client.post(
        reverse("accounts:user_edit", args=[root.pk]),
        {"role": "viewer", "is_active": "on"},
    )

    root.refresh_from_db()
    assert root.groups.filter(name="admin").exists()


def test_demote_admin_allowed_when_another_admin_remains():
    client = admin_client()
    other = make_user("other-admin", "admin")
    target = make_user("target-admin", "admin")

    client.post(
        reverse("accounts:user_edit", args=[target.pk]),
        {"role": "viewer", "is_active": "on"},
    )

    target.refresh_from_db()
    assert target.groups.filter(name="viewer").exists()
    assert other.groups.filter(name="admin").exists()


# --- 4.4 passwords ---


def test_admin_reset_password():
    client = admin_client()
    target = make_user("resetme", "viewer")

    client.post(
        reverse("accounts:user_edit", args=[target.pk]),
        {"role": "viewer", "is_active": "on", "new_password": "N3w!Passw0rd"},
    )

    target.refresh_from_db()
    assert target.check_password("N3w!Passw0rd")
    assert not target.check_password("password123")


def test_self_password_change_requires_current():
    client = Client()
    user = make_user("selfie", "viewer")
    client.force_login(user)

    bad = client.post(
        reverse("password_change"),
        {
            "old_password": "wrong",
            "new_password1": "An0ther!Pass",
            "new_password2": "An0ther!Pass",
        },
    )
    assert bad.status_code == 200

    user.refresh_from_db()
    assert user.check_password("password123")

    ok = client.post(
        reverse("password_change"),
        {
            "old_password": "password123",
            "new_password1": "An0ther!Pass",
            "new_password2": "An0ther!Pass",
        },
    )
    assert ok.status_code == 302
    user.refresh_from_db()
    assert user.check_password("An0ther!Pass")


# --- 4.5 reset flow ---


def test_create_user_accepts_email():
    client = admin_client()

    client.post(
        reverse("accounts:user_create"),
        {
            "username": "withemail",
            "password": "Str0ng!Pass",
            "email": "w@example.com",
            "role": "viewer",
        },
    )

    assert User.objects.get(username="withemail").email == "w@example.com"


def test_password_reset_form_uses_email():
    User.objects.create_user("mailuser2", email="m@example.com", password="x" * 12)

    response = Client().post(reverse("password_reset"), {"email": "m@example.com"})

    assert response.status_code == 302
    assert len(mail.outbox) == 1
    assert "reset" in mail.outbox[0].body or "password" in mail.outbox[0].body.lower()


def test_password_reset_unknown_email_is_silent():
    response = Client().post(reverse("password_reset"), {"email": "nobody@example.com"})

    assert response.status_code == 302  # same confirmation, no email
    assert len(mail.outbox) == 0


def test_password_reset_confirm_with_valid_token():
    from django.contrib.auth.tokens import default_token_generator

    user = User.objects.create_user("tok", email="t@example.com", password="x" * 12)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    client = Client()
    # Django 5.2: valid token redirects to a token-less "set-password" URL
    # backed by the session.
    first = client.post(
        reverse("password_reset_confirm", args=[uid, token]),
        {"new_password1": "R3set!Pass", "new_password2": "R3set!Pass"},
    )
    assert first.status_code == 302
    second = client.post(
        first["Location"],
        {"new_password1": "R3set!Pass", "new_password2": "R3set!Pass"},
    )
    assert second.status_code == 302

    user.refresh_from_db()
    assert user.check_password("R3set!Pass")


def test_password_reset_confirm_invalid_token_shows_form():
    user = User.objects.create_user("tokbad", email="tb@example.com", password="x" * 12)
    uid = urlsafe_base64_encode(force_bytes(user.pk))

    response = Client().get(
        reverse("password_reset_confirm", args=[uid, "bad-token"]),
    )

    assert response.status_code == 200
    assert (
        "inválido" in response.content.decode().lower()
        or "expir" in response.content.decode().lower()
    )


# --- 4.6 context processor ---


def test_can_manage_users_context():
    admin = make_user("ctx-admin", "admin")
    viewer = make_user("ctx-viewer", "viewer")

    for user, expected in [(admin, True), (viewer, False)]:
        client = Client()
        client.force_login(user)
        response = client.get(reverse("home"))
        assert response.context["can_manage_users"] is expected
