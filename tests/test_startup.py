import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from core.startup import (
    DEFAULT_SECRET_KEY,
    check_secret_key,
    validate_secret_key,
)

STRONG_KEY = "x" * 50


def test_default_key_blocked_when_debug_off():
    with override_settings(DEBUG=False, SECRET_KEY=DEFAULT_SECRET_KEY):
        with pytest.raises(ImproperlyConfigured) as exc:
            validate_secret_key()
    assert "DJANGO_SECRET_KEY" in str(exc.value)
    assert DEFAULT_SECRET_KEY not in str(exc.value)


def test_empty_key_blocked_when_debug_off():
    with override_settings(DEBUG=False, SECRET_KEY=""):
        with pytest.raises(ImproperlyConfigured) as exc:
            validate_secret_key()
    assert "SECRET_KEY" in str(exc.value)


def test_short_key_blocked_when_debug_off():
    with override_settings(DEBUG=False, SECRET_KEY="short-key"):
        with pytest.raises(ImproperlyConfigured) as exc:
            validate_secret_key()
    assert "32" in str(exc.value)


def test_strong_key_allowed_when_debug_off():
    with override_settings(DEBUG=False, SECRET_KEY=STRONG_KEY):
        validate_secret_key()


def test_default_key_allowed_when_debug_on():
    with override_settings(DEBUG=True, SECRET_KEY=DEFAULT_SECRET_KEY):
        validate_secret_key()


def test_system_check_flags_insecure_key():
    with override_settings(DEBUG=False, SECRET_KEY=DEFAULT_SECRET_KEY):
        errors = check_secret_key(None)
    assert len(errors) == 1
    assert errors[0].id == "core.E001"
    assert "DJANGO_SECRET_KEY" in errors[0].msg


def test_system_check_clean_for_strong_key():
    with override_settings(DEBUG=False, SECRET_KEY=STRONG_KEY):
        assert check_secret_key(None) == []
