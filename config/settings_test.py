"""Settings used by the automated test suite."""

import tempfile

from .settings import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

SECRET_KEY = "test-secret-key"
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

_TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="paperless-test-media-")
_TEST_REPORT_ROOT = tempfile.mkdtemp(prefix="paperless-test-reports-")
_TEST_CACHE_ROOT = tempfile.mkdtemp(prefix="paperless-test-cache-")

MEDIA_ROOT = _TEST_MEDIA_ROOT

APP = {
    **APP,  # noqa: F405
    "media_root": _TEST_MEDIA_ROOT,
    "report_output_dir": _TEST_REPORT_ROOT,
    "cache_dir": _TEST_CACHE_ROOT,
    "internal_api_token": "test-internal-token",
    "n8n_processing_webhook_url": "http://n8n.test/webhook/process",
    "n8n_report_webhook_url": "http://n8n.test/webhook/report",
    "n8n_webhook_token": "test-n8n-token",
    "inbox_settle_seconds": 0.0,
    "paperless_url": "http://paperless.test",
    "paperless_ui_url": "http://paperless-ui.test",
    "paperless_token": "test-paperless-token",
    "ocr_url": "http://ocr.test",
    "ollama_url": "http://ollama.test",
    "ollama_model": "test-model",
}

LOGGING["root"]["level"] = "CRITICAL"  # noqa: F405
