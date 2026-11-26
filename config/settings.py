"""Django settings driven by environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(environ: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(environ: Mapping[str, str], name: str, default: int) -> int:
    raw = environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def env_float(environ: Mapping[str, str], name: str, default: float) -> float:
    raw = environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def env_list(environ: Mapping[str, str], name: str, default: str = "") -> list[str]:
    raw = environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def read_app_settings(environ: Mapping[str, str] | None = None) -> dict[str, object]:
    """Return the application settings derived from an environment mapping."""
    source: Mapping[str, str] = os.environ if environ is None else environ
    return {
        "upload_max_bytes": env_int(source, "APP_UPLOAD_MAX_BYTES", 25 * 1024 * 1024),
        "request_max_bytes": env_int(source, "APP_REQUEST_MAX_BYTES", 100 * 1024 * 1024),
        "pdf_max_pages": env_int(source, "APP_PDF_MAX_PAGES", 100),
        "embedded_text_min_chars": env_int(source, "APP_EMBEDDED_TEXT_MIN_CHARS", 30),
        "ocr_min_text_chars": env_int(source, "APP_OCR_MIN_TEXT_CHARS", 30),
        "ocr_low_confidence_threshold": env_float(source, "APP_OCR_LOW_CONFIDENCE_THRESHOLD", 0.55),
        "ocr_languages": env_list(source, "APP_OCR_LANGUAGES", "eng,spa"),
        "ocr_url": source.get("APP_OCR_URL", "http://ocr:8000"),
        "ocr_timeout_seconds": env_float(source, "APP_OCR_TIMEOUT_SECONDS", 660.0),
        "ocr_retries": env_int(source, "APP_OCR_RETRIES", 2),
        "ollama_url": source.get("APP_OLLAMA_URL", "http://ollama:11434"),
        "ollama_model": source.get("APP_OLLAMA_MODEL", "qwen2.5:7b-instruct"),
        "ollama_timeout_seconds": env_float(source, "APP_OLLAMA_TIMEOUT_SECONDS", 180.0),
        "ollama_retries": env_int(source, "APP_OLLAMA_RETRIES", 2),
        "llm_max_input_chars": env_int(source, "APP_LLM_MAX_INPUT_CHARS", 40000),
        "confidence_review_threshold": env_float(source, "APP_CONFIDENCE_REVIEW_THRESHOLD", 0.6),
        "paperless_url": source.get("APP_PAPERLESS_URL", "http://paperless:8000"),
        "paperless_ui_url": source.get("APP_PAPERLESS_UI_URL", source.get("APP_PAPERLESS_URL", "")),
        "paperless_token": source.get("APP_PAPERLESS_TOKEN", ""),
        "paperless_other_tag": source.get("APP_PAPERLESS_OTHER_TAG", "Otros"),
        "paperless_timeout_seconds": env_float(source, "APP_PAPERLESS_TIMEOUT_SECONDS", 30.0),
        "paperless_poll_interval_seconds": env_float(
            source, "APP_PAPERLESS_POLL_INTERVAL_SECONDS", 1.0
        ),
        "paperless_poll_timeout_seconds": env_float(
            source, "APP_PAPERLESS_POLL_TIMEOUT_SECONDS", 60.0
        ),
        "internal_api_token": source.get("APP_INTERNAL_API_TOKEN", ""),
        "n8n_processing_webhook_url": source.get("APP_N8N_PROCESSING_WEBHOOK_URL", ""),
        "n8n_report_webhook_url": source.get("APP_N8N_REPORT_WEBHOOK_URL", ""),
        "n8n_webhook_token": source.get("APP_N8N_WEBHOOK_TOKEN", ""),
        "media_root": source.get("APP_MEDIA_ROOT", str(BASE_DIR / "var" / "media")),
        "report_output_dir": source.get("APP_REPORT_OUTPUT_DIR", str(BASE_DIR / "var" / "reports")),
        "inbox_dir": source.get("APP_INBOX_DIR", str(BASE_DIR / "var" / "inbox")),
        "inbox_poll_seconds": env_float(source, "APP_INBOX_POLL_SECONDS", 10.0),
        "paperless_sync_seconds": env_float(source, "APP_PAPERLESS_SYNC_SECONDS", 60.0),
        "sync_overlap_seconds": env_float(source, "APP_SYNC_OVERLAP_SECONDS", 600.0),
        "cache_dir": source.get("APP_CACHE_DIR", str(BASE_DIR / "var" / "cache")),
        "paperless_webhook_target": source.get("APP_PAPERLESS_WEBHOOK_TARGET", ""),
        "paperless_retries": env_int(source, "APP_PAPERLESS_RETRIES", 2),
        "paperless_retry_backoff_seconds": env_float(
            source, "APP_PAPERLESS_RETRY_BACKOFF_SECONDS", 0.5
        ),
        "n8n_webhook_timeout_seconds": env_float(source, "APP_N8N_WEBHOOK_TIMEOUT_SECONDS", 10.0),
        "recovery_interval_seconds": env_float(source, "APP_RECOVERY_INTERVAL_SECONDS", 60.0),
        "recovery_stale_seconds": env_float(source, "APP_RECOVERY_STALE_SECONDS", 1800.0),
        "recovery_max_attempts": env_int(source, "APP_RECOVERY_MAX_ATTEMPTS", 3),
    }


APP = read_app_settings()

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = env_bool(os.environ, "DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list(os.environ, "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
CSRF_TRUSTED_ORIGINS = env_list(os.environ, "DJANGO_CSRF_TRUSTED_ORIGINS", "")
if not CSRF_TRUSTED_ORIGINS:
    # Fallback: trust http(s) origins built from ALLOWED_HOSTS on APP_PORT so
    # fresh deployments without an explicit DJANGO_CSRF_TRUSTED_ORIGINS still
    # accept browser POSTs (login, forms) on the published port.
    _csrf_port = os.environ.get("APP_PORT", "8000")
    CSRF_TRUSTED_ORIGINS = [
        f"{scheme}://{host}:{_csrf_port}"
        for host in ALLOWED_HOSTS
        if host not in ("*", "")
        for scheme in ("http", "https")
    ]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "catalog",
    "documents",
    "reports",
]

MIDDLEWARE = [
    "core.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.RequestSizeLimitMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DB_ENGINE = os.environ.get("DB_ENGINE", "postgres")
if DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("DB_NAME", str(BASE_DIR / "var" / "db.sqlite3")),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "paperless_certs"),
            "USER": os.environ.get("DB_USER", "paperless"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "db"),
            "PORT": os.environ.get("DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_ROOT = APP["media_root"]
MEDIA_URL = "media/"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": APP["cache_dir"],
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env_bool(os.environ, "DJANGO_SECURE_COOKIES", not DEBUG)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_SSL_REDIRECT = env_bool(os.environ, "DJANGO_SECURE_SSL_REDIRECT", False)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "SAMEORIGIN"

# Reject oversized non-file request bodies early. File size limits are enforced in intake.
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

LOG_FORMAT = os.environ.get("LOG_FORMAT", "keyvalue")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {
            "()": (
                "core.logging.JsonFormatter"
                if LOG_FORMAT == "json"
                else "core.logging.KeyValueFormatter"
            ),
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "filters": {
        "request_id": {"()": "core.logging.RequestIdFilter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "plain",
            "filters": ["request_id"],
        },
    },
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}
