"""ASGI entry point."""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from core.startup import validate_secret_key  # noqa: E402

validate_secret_key()

from django.core.asgi import get_asgi_application  # noqa: E402

application = get_asgi_application()
