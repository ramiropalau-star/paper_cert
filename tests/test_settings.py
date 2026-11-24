from config.settings import env_bool, read_app_settings


def test_app_settings_defaults():
    app = read_app_settings({})
    assert app["upload_max_bytes"] == 25 * 1024 * 1024
    assert app["pdf_max_pages"] == 100
    assert app["ocr_languages"] == ["eng", "spa"]
    assert app["confidence_review_threshold"] == 0.6
    assert app["ocr_retries"] == 2
    assert app["ollama_model"] == "qwen2.5:7b-instruct"


def test_app_settings_read_environment_overrides():
    app = read_app_settings(
        {
            "APP_UPLOAD_MAX_BYTES": "1024",
            "APP_PDF_MAX_PAGES": "7",
            "APP_OCR_LANGUAGES": "deu,fra",
            "APP_OCR_URL": "http://ocr.local:9000",
            "APP_OLLAMA_MODEL": "custom-model",
            "APP_OLLAMA_RETRIES": "5",
            "APP_INTERNAL_API_TOKEN": "secret-token",
            "APP_CONFIDENCE_REVIEW_THRESHOLD": "0.8",
        }
    )
    assert app["upload_max_bytes"] == 1024
    assert app["pdf_max_pages"] == 7
    assert app["ocr_languages"] == ["deu", "fra"]
    assert app["ocr_url"] == "http://ocr.local:9000"
    assert app["ollama_model"] == "custom-model"
    assert app["ollama_retries"] == 5
    assert app["internal_api_token"] == "secret-token"
    assert app["confidence_review_threshold"] == 0.8


def test_env_bool_accepts_common_truthy_values():
    assert env_bool({"FLAG": "true"}, "FLAG")
    assert env_bool({"FLAG": "1"}, "FLAG")
    assert not env_bool({"FLAG": "false"}, "FLAG")
    assert env_bool({}, "FLAG", default=True)
