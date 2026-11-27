"""Tests for bootstrap admin-password validation (production-readiness 1.3/1.4)."""

import os
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = pytest.mark.django_db

COMMAND = "core.management.commands.bootstrap"


def _env(**overrides):
    env = {
        "DJANGO_SUPERUSER_USERNAME": "admin",
        "DJANGO_SUPERUSER_PASSWORD": "Str0ng!Passw0rd",
        "DJANGO_SUPERUSER_EMAIL": "admin@example.com",
    }
    env.update(overrides)
    return mock.patch.dict(os.environ, env, clear=False)


def test_weak_password_rejected_before_any_work():
    with _env(DJANGO_SUPERUSER_PASSWORD="admin"), mock.patch(f"{COMMAND}.call_command") as cc:
        with pytest.raises(CommandError, match="failed validation"):
            call_command("bootstrap")
        cc.assert_not_called()


def test_strong_password_creates_superuser():
    with _env(), mock.patch(f"{COMMAND}.call_command"):
        call_command("bootstrap")
    user = get_user_model().objects.get(username="admin")
    assert user.is_superuser
    assert user.check_password("Str0ng!Passw0rd")


def test_weak_password_bypass_with_override():
    with (
        _env(
            DJANGO_SUPERUSER_PASSWORD="admin",
            BOOTSTRAP_ALLOW_WEAK_PASSWORD="1",
        ),
        mock.patch(f"{COMMAND}.call_command"),
    ):
        call_command("bootstrap")
    assert get_user_model().objects.filter(username="admin").exists()


def test_existing_user_skips_creation():
    get_user_model().objects.create_superuser("admin", "a@b.c", "Str0ng!Passw0rd")
    with _env(), mock.patch(f"{COMMAND}.call_command"):
        call_command("bootstrap")
    assert get_user_model().objects.filter(username="admin").count() == 1
