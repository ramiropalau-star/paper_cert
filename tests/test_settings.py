import json
import os
import subprocess
import sys
from pathlib import Path

from config.settings import env_bool, read_app_settings


def test_app_settings_defaults():
    app = read_app_settings({})
    assert app["upload_max_bytes"] == 25 * 1024 * 1024
    assert app["request_max_bytes"] == 100 * 1024 * 1024
    assert app["pdf_max_pages"] == 100
    assert app["ocr_languages"] == ["eng", "spa"]
    assert app["confidence_review_threshold"] == 0.6
    assert app["ocr_retries"] == 2
    assert app["ollama_model"] == "qwen2.5:7b-instruct"
    assert app["paperless_retries"] == 2
    assert app["paperless_retry_backoff_seconds"] == 0.5
    assert app["n8n_webhook_timeout_seconds"] == 10.0
    assert app["recovery_interval_seconds"] == 60.0
    assert app["recovery_stale_seconds"] == 1800.0
    assert app["recovery_max_attempts"] == 3


def test_app_settings_read_environment_overrides():
    app = read_app_settings(
        {
            "APP_UPLOAD_MAX_BYTES": "1024",
            "APP_REQUEST_MAX_BYTES": "4096",
            "APP_PDF_MAX_PAGES": "7",
            "APP_OCR_LANGUAGES": "deu,fra",
            "APP_OCR_URL": "http://ocr.local:9000",
            "APP_OLLAMA_MODEL": "custom-model",
            "APP_OLLAMA_RETRIES": "5",
            "APP_INTERNAL_API_TOKEN": "secret-token",
            "APP_CONFIDENCE_REVIEW_THRESHOLD": "0.8",
            "APP_PAPERLESS_RETRIES": "4",
            "APP_RECOVERY_MAX_ATTEMPTS": "5",
            "APP_RECOVERY_INTERVAL_SECONDS": "0",
        }
    )
    assert app["upload_max_bytes"] == 1024
    assert app["request_max_bytes"] == 4096
    assert app["pdf_max_pages"] == 7
    assert app["ocr_languages"] == ["deu", "fra"]
    assert app["ocr_url"] == "http://ocr.local:9000"
    assert app["ollama_model"] == "custom-model"
    assert app["ollama_retries"] == 5
    assert app["internal_api_token"] == "secret-token"
    assert app["confidence_review_threshold"] == 0.8
    assert app["paperless_retries"] == 4
    assert app["recovery_max_attempts"] == 5
    assert app["recovery_interval_seconds"] == 0.0


def test_env_bool_accepts_common_truthy_values():
    assert env_bool({"FLAG": "true"}, "FLAG")
    assert env_bool({"FLAG": "1"}, "FLAG")
    assert not env_bool({"FLAG": "false"}, "FLAG")
    assert env_bool({}, "FLAG", default=True)


_REPO_ROOT = Path(__file__).resolve().parent.parent

_SECURITY_FLAGS_SNIPPET = (
    "import json, config.settings as s;"
    "print(json.dumps({"
    "'cookies': s.SESSION_COOKIE_SECURE,"
    "'csrf': s.CSRF_COOKIE_SECURE,"
    "'redirect': s.SECURE_SSL_REDIRECT,"
    "'hsts': s.SECURE_HSTS_SECONDS,"
    "'hsts_sub': s.SECURE_HSTS_INCLUDE_SUBDOMAINS}))"
)


def _security_flags(env_overrides):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DJANGO_SECURE", "APP_SCHEME"))
    }
    env.update(env_overrides)
    out = subprocess.run(
        [sys.executable, "-c", _SECURITY_FLAGS_SNIPPET],
        capture_output=True,
        text=True,
        env=env,
        cwd=_REPO_ROOT,
        check=True,
    )
    return json.loads(out.stdout)


def test_https_scheme_enables_transport_security():
    flags = _security_flags({"APP_SCHEME": "https"})
    assert flags == {
        "cookies": True,
        "csrf": True,
        "redirect": True,
        "hsts": 31536000,
        "hsts_sub": True,
    }


def test_http_scheme_keeps_transport_security_off():
    flags = _security_flags({"APP_SCHEME": "http"})
    assert flags == {
        "cookies": False,
        "csrf": False,
        "redirect": False,
        "hsts": 0,
        "hsts_sub": False,
    }


def test_invalid_scheme_falls_back_to_http():
    flags = _security_flags({"APP_SCHEME": "ftp"})
    assert flags["cookies"] is False
    assert flags["redirect"] is False


def test_explicit_secure_overrides_win_over_scheme():
    flags = _security_flags(
        {
            "APP_SCHEME": "https",
            "DJANGO_SECURE_COOKIES": "false",
            "DJANGO_SECURE_SSL_REDIRECT": "false",
            "DJANGO_SECURE_HSTS_SECONDS": "0",
        }
    )
    assert flags["cookies"] is False
    assert flags["csrf"] is False
    assert flags["redirect"] is False
    assert flags["hsts"] == 0
