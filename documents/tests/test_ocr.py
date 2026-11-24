import httpx
import pytest
import respx

from documents.services.ocr import OcrClient, OcrError

BASE_URL = "http://ocr.test"


def client(**overrides) -> OcrClient:
    options = {
        "base_url": BASE_URL,
        "languages": ["eng", "spa"],
        "timeout": 5,
        "retries": 1,
        "page_limit": 10,
    }
    options.update(overrides)
    return OcrClient(**options)


def success_payload():
    return {
        "contract_version": "v1",
        "engine": {"name": "ocrmypdf+tesseract", "tesseract": "5.5.0"},
        "page_count": 2,
        "mean_confidence": 0.91,
        "quality": "ok",
        "pages": [
            {"page_number": 1, "text": "B2 ENGLISH", "method": "ocr", "confidence": 0.93},
            {
                "page_number": 2,
                "text": "EMBEDDED",
                "method": "embedded",
                "confidence": 1.0,
            },
        ],
    }


@respx.mock
def test_extract_parses_pages_and_sends_configuration():
    route = respx.post(f"{BASE_URL}/v1/ocr").respond(json=success_payload())

    result = client().extract(b"%PDF-1.4", "certificate.pdf", "application/pdf")

    assert result.contract_version == "v1"
    assert result.mean_confidence == 0.91
    assert result.quality == "ok"
    assert len(result.pages) == 2
    assert result.pages[0].text == "B2 ENGLISH"
    assert result.pages[1].method == "embedded"
    request = route.calls[0].request
    assert b'name="languages"' in request.content
    assert b"eng,spa" in request.content
    assert b'name="page_limit"' in request.content


@respx.mock
def test_extract_retries_transient_failure():
    route = respx.post(f"{BASE_URL}/v1/ocr").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=success_payload())]
    )

    result = client(retries=1).extract(b"%PDF-1.4", "certificate.pdf", "application/pdf")

    assert result.pages[0].page_number == 1
    assert route.call_count == 2


@respx.mock
def test_extract_exhausts_retries_with_retryable_error():
    respx.post(f"{BASE_URL}/v1/ocr").respond(status_code=500)

    with pytest.raises(OcrError) as excinfo:
        client(retries=2).extract(b"%PDF-1.4", "certificate.pdf", "application/pdf")

    assert excinfo.value.retryable is True
    assert excinfo.value.code == "service_unavailable"


@respx.mock
def test_extract_maps_service_error_payload():
    respx.post(f"{BASE_URL}/v1/ocr").respond(
        status_code=422,
        json={
            "error": {
                "code": "no_text",
                "message": "OCR produced too little usable text",
                "retryable": False,
            }
        },
    )

    with pytest.raises(OcrError) as excinfo:
        client().extract(b"%PDF-1.4", "certificate.pdf", "application/pdf")

    assert excinfo.value.code == "no_text"
    assert excinfo.value.retryable is False
    assert excinfo.value.status_code == 422


@respx.mock
def test_extract_maps_timeout():
    respx.post(f"{BASE_URL}/v1/ocr").mock(side_effect=httpx.TimeoutException("slow"))

    with pytest.raises(OcrError) as excinfo:
        client(retries=0).extract(b"%PDF-1.4", "certificate.pdf", "application/pdf")

    assert excinfo.value.code == "timeout"
    assert excinfo.value.retryable is True


@respx.mock
def test_extract_rejects_malformed_response():
    respx.post(f"{BASE_URL}/v1/ocr").respond(json={"unexpected": True})

    with pytest.raises(OcrError) as excinfo:
        client().extract(b"%PDF-1.4", "certificate.pdf", "application/pdf")

    assert excinfo.value.code == "invalid_response"


def test_languages_and_page_limit_overrides():
    ocr = client()
    assert ocr.languages == ("eng", "spa")
    assert ocr.page_limit == 10
