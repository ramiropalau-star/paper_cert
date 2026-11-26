"""Startup validation for insecure deployment configuration.

``validate_secret_key`` runs from the WSGI/ASGI entry points so build-time
commands (``collectstatic``, ``migrate``) keep working; the registered system
check surfaces the same rule through ``manage.py check``.
"""

from django.conf import settings
from django.core.checks import Error, register
from django.core.exceptions import ImproperlyConfigured

DEFAULT_SECRET_KEY = "dev-insecure-change-me"
MIN_SECRET_KEY_LENGTH = 32


def _secret_key_problem(value: str) -> str | None:
    if not value:
        return "is empty"
    if value == DEFAULT_SECRET_KEY:
        return "is the development default"
    if len(value) < MIN_SECRET_KEY_LENGTH:
        return f"is shorter than {MIN_SECRET_KEY_LENGTH} characters"
    return None


def validate_secret_key() -> None:
    """Refuse to serve requests with an insecure ``DJANGO_SECRET_KEY``."""
    if settings.DEBUG:
        return
    problem = _secret_key_problem(settings.SECRET_KEY)
    if problem is not None:
        raise ImproperlyConfigured(
            f"DJANGO_SECRET_KEY {problem}. "
            "Set a long random value before deploying with DEBUG=false."
        )


@register()
def check_secret_key(app_configs, **kwargs):
    if settings.DEBUG:
        return []
    problem = _secret_key_problem(getattr(settings, "SECRET_KEY", ""))
    if problem is None:
        return []
    return [
        Error(
            f"DJANGO_SECRET_KEY {problem}.",
            hint="Set DJANGO_SECRET_KEY to a long random value for production.",
            id="core.E001",
        )
    ]
