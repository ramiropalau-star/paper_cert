"""WSGI entry point."""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from core.startup import validate_secret_key  # noqa: E402

validate_secret_key()

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
