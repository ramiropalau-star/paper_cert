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
