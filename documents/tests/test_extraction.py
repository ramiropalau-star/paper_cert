import json

import httpx
import pytest
import respx
from django.conf import settings
from django.test import Client, override_settings
from django.urls import reverse
from pydantic import ValidationError

from documents.models import Certificate, Document, DocumentPage
from documents.services.extraction import (
    EXTRACTION_JSON_SCHEMA,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    ExtractionPayload,
    _validate_evidence,
    build_messages,
    document_text,
    extract_certificate,
    parse_payload,
)
from documents.services.ollama import OllamaClient, OllamaError

pytestmark = pytest.mark.django_db

BASE_URL = "http://ollama.test"


def make_document(**overrides) -> Document:
    data = {
        "fingerprint": "c" * 64,
        "original_filename": "certificate.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
        "paperless_document_id": "42",
        "processing_state": Document.ProcessingState.TEXT_READY,
        "text_method": Document.TextMethod.EMBEDDED,
    }
    data.update(overrides)
    return Document.objects.create(**data)


PAGE_TEXT = (
    "student: Ada Lovelace\n"
    "issued 12 May 2024\n"
    "Cambridge English B2 First CERT-123 English quote text"
)


def add_page(document: Document, number: int = 1, text: str = "page text") -> None:
    DocumentPage.objects.create(
        document=document,
        page_number=number,
        text=text,
        method=DocumentPage.Method.EMBEDDED,
    )


def field(value, *, page: int = 1, quote: str = "quote", confidence: float = 0.9):
    return {
        "value": value,
        "evidence": {"page": page, "quote": quote},
        "confidence": confidence,
    }


def payload_dict(**overrides) -> dict:
    data = {
        "is_language_certificate": True,
        "multiple_certificates_suspected": False,
        "student_name": field("Ada Lovelace", quote="student: Ada Lovelace"),
        "language": field("English"),
        "entity": field("Cambridge English"),
        "issuing_body": field(None),
        "test_center": field(None),
        "exam": field("B2 First"),
        "level": field("B2"),
        "score": field("180"),
        "certificate_code": field("CERT-123"),
        "dates": [
            {
                "text": "12 May 2024",
                "role": "issue",
                "page": 1,
                "quote": "issued 12 May 2024",
            }
        ],
        "confidence": 0.87,
    }
    data.update(overrides)
    return data


def chat_response(payload: dict | str) -> httpx.Response:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return httpx.Response(
        200,
        json={"message": {"role": "assistant", "content": content}},
    )


class FakeLlm:
    def __init__(self, responses: list):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.closed = False

    def chat(self, messages, *, format=None, temperature=0.0):
        self.calls.append({"messages": messages, "format": format, "temperature": temperature})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        self.closed = True


class FakeStore:
    def __init__(self):
        self.tags: list[tuple[str, str]] = []
        self.closed = False

    def add_tag(self, document_id, name):
        self.tags.append((document_id, name))
        return True

    def remove_tag(self, document_id, name):
        return True

    def close(self):
        self.closed = True


# --- Ollama client (7.1) ---


@respx.mock
def test_ollama_chat_returns_message_content():
    route = respx.post(f"{BASE_URL}/api/chat").respond(
        json={"message": {"role": "assistant", "content": '{"ok": true}'}}
    )
    client = OllamaClient(base_url=BASE_URL, model="test-model", timeout=5, retries=0)

    content = client.chat([{"role": "user", "content": "hi"}])

    assert content == '{"ok": true}'
    request = json.loads(route.calls[0].request.content)
    assert request["model"] == "test-model"
    assert request["stream"] is False
    assert request["options"]["temperature"] == 0.0


@respx.mock
def test_ollama_chat_sends_schema_format():
    route = respx.post(f"{BASE_URL}/api/chat").respond(json={"message": {"content": "{}"}})
    client = OllamaClient(base_url=BASE_URL, retries=0)

    client.chat([{"role": "user", "content": "hi"}], format={"type": "object"})

    request = json.loads(route.calls[0].request.content)
    assert request["format"] == {"type": "object"}


@respx.mock
def test_ollama_chat_maps_timeout():
    respx.post(f"{BASE_URL}/api/chat").mock(side_effect=httpx.TimeoutException("slow"))
    client = OllamaClient(base_url=BASE_URL, retries=0)

    with pytest.raises(OllamaError) as excinfo:
        client.chat([{"role": "user", "content": "hi"}])

    assert excinfo.value.code == "timeout"
    assert excinfo.value.retryable is True


@respx.mock
def test_ollama_chat_retries_transient_server_error():
    route = respx.post(f"{BASE_URL}/api/chat").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"message": {"content": "done"}}),
        ]
    )
    client = OllamaClient(base_url=BASE_URL, retries=1)

    assert client.chat([{"role": "user", "content": "hi"}]) == "done"
    assert route.call_count == 2


@respx.mock
def test_ollama_chat_server_error_exhausts_retries():
    respx.post(f"{BASE_URL}/api/chat").respond(status_code=500)
    client = OllamaClient(base_url=BASE_URL, retries=1)

    with pytest.raises(OllamaError) as excinfo:
        client.chat([{"role": "user", "content": "hi"}])

    assert excinfo.value.code == "service_unavailable"
    assert excinfo.value.retryable is True


@respx.mock
def test_ollama_chat_rejects_client_error_without_retry():
    route = respx.post(f"{BASE_URL}/api/chat").respond(status_code=400)
    client = OllamaClient(base_url=BASE_URL, retries=2)

    with pytest.raises(OllamaError) as excinfo:
        client.chat([{"role": "user", "content": "hi"}])

    assert excinfo.value.code == "request_rejected"
    assert excinfo.value.retryable is False
    assert route.call_count == 1


@respx.mock
def test_ollama_chat_rejects_malformed_response():
    respx.post(f"{BASE_URL}/api/chat").respond(json={"unexpected": True})
    client = OllamaClient(base_url=BASE_URL, retries=0)

    with pytest.raises(OllamaError) as excinfo:
        client.chat([{"role": "user", "content": "hi"}])

    assert excinfo.value.code == "invalid_response"


# --- Prompt and schema (7.2) ---


def test_extraction_schema_covers_required_fields():
    properties = EXTRACTION_JSON_SCHEMA["properties"]
    for name in (
        "is_language_certificate",
        "multiple_certificates_suspected",
        "student_name",
        "language",
        "entity",
        "issuing_body",
        "test_center",
        "exam",
        "level",
        "score",
        "certificate_code",
        "dates",
        "confidence",
    ):
        assert name in properties
    field_props = properties["student_name"]["properties"]
    assert set(field_props) == {"value", "evidence", "confidence"}
    assert set(field_props["evidence"]["properties"]) == {"page", "quote"}
    assert set(properties["dates"]["items"]["properties"]) == {
        "text",
        "role",
        "page",
        "quote",
    }


def test_prompt_contains_no_invention_and_evidence_rules():
    prompt = SYSTEM_PROMPT.lower()
    assert "never infer" in prompt or "never" in prompt
    assert "fabricate" in prompt
    assert "evidence" in prompt
    assert "untrusted" in prompt


def test_build_messages_marks_document_as_untrusted():
    messages = build_messages("CERTIFICATE TEXT")
    assert messages[0]["role"] == "system"
    assert "<document>" in messages[1]["content"]
    assert "CERTIFICATE TEXT" in messages[1]["content"]
    assert "</document>" in messages[1]["content"]


def test_document_text_includes_page_markers():
    document = make_document()
    add_page(document, 1, "first")
    add_page(document, 2, "second")

    text = document_text(document)

    assert "--- Page 1 ---\nfirst" in text
    assert "--- Page 2 ---\nsecond" in text


def test_parse_payload_validates_schema():
    payload = parse_payload(json.dumps(payload_dict()))
    assert isinstance(payload, ExtractionPayload)
    assert payload.student_name.value == "Ada Lovelace"
    assert payload.dates[0].role == "issue"


def test_parse_payload_rejects_missing_required_field():
    data = payload_dict()
    del data["student_name"]
    with pytest.raises(ValidationError):
        parse_payload(json.dumps(data))


# --- Extraction pipeline (7.3–7.5) ---


def test_successful_extraction_persists_certificate():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    llm = FakeLlm([json.dumps(payload_dict())])
    store = FakeStore()

    result = extract_certificate(document, llm=llm, store=store)

    assert result.state == Document.ProcessingState.EXTRACTED
    assert result.is_language_certificate is True
    certificate = Certificate.objects.get(document=document)
    assert certificate.student_name == "Ada Lovelace"
    assert certificate.language_literal == "English"
    assert certificate.entity_literal == "Cambridge English"
    assert certificate.level_literal == "B2"
    assert certificate.score_literal == "180"
    assert certificate.certificate_code == "CERT-123"
    assert certificate.confidence == 0.87
    assert certificate.prompt_version == PROMPT_VERSION
    assert certificate.evidence["student_name"]["quote"] == "student: Ada Lovelace"
    assert certificate.field_confidence["student_name"] == 0.9
    assert certificate.date_texts["candidates"][0]["text"] == "12 May 2024"
    assert document.processing_state == Document.ProcessingState.EXTRACTED
    call = llm.calls[0]
    assert call["format"] == EXTRACTION_JSON_SCHEMA
    assert call["temperature"] == 0.0


def test_extraction_is_idempotent_for_extracted_state():
    document = make_document(processing_state=Document.ProcessingState.EXTRACTED)
    add_page(document, 1, PAGE_TEXT)
    llm = FakeLlm([])

    result = extract_certificate(document, llm=llm)

    assert result.skipped is True
    assert llm.calls == []
    assert Certificate.objects.count() == 0


def test_invalid_json_retried_then_succeeds():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    llm = FakeLlm(["not json", json.dumps(payload_dict())])

    result = extract_certificate(document, llm=llm, store=FakeStore())

    assert result.state == Document.ProcessingState.EXTRACTED
    assert len(llm.calls) == 2
    assert Certificate.objects.filter(document=document).exists()


def test_schema_mismatch_retried_then_succeeds():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    bad = payload_dict()
    del bad["exam"]
    llm = FakeLlm([json.dumps(bad), json.dumps(payload_dict())])

    result = extract_certificate(document, llm=llm, store=FakeStore())

    assert result.state == Document.ProcessingState.EXTRACTED
    assert len(llm.calls) == 2


def test_retries_exhausted_routes_to_review():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    llm = FakeLlm(["garbage"] * 3)
    store = FakeStore()

    result = extract_certificate(document, llm=llm, store=store)

    assert result.state == Document.ProcessingState.PENDING_REVIEW
    assert "invalid_extraction" in document.review_reasons
    assert "failed validation" in document.error_reason
    assert len(llm.calls) == 3
    assert Certificate.objects.filter(document=document).count() == 0
    assert store.tags == [("42", "Otros")]


def test_model_unavailable_sets_error_state():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    llm = FakeLlm([OllamaError("Ollama returned HTTP 503", code="service_unavailable")])
    store = FakeStore()

    result = extract_certificate(document, llm=llm, store=store)

    assert result.state == Document.ProcessingState.ERROR
    assert "model_unavailable" in document.review_reasons
    assert "HTTP 503" in document.error_reason
    assert store.tags == [("42", "Otros")]


def test_input_size_cap_routes_to_review_without_calling_model():
    document = make_document()
    add_page(document, 1, "x" * 5000)
    llm = FakeLlm([])
    store = FakeStore()

    with override_settings(APP={**settings.APP, "llm_max_input_chars": 100}):
        result = extract_certificate(document, llm=llm, store=store)

    assert result.state == Document.ProcessingState.PENDING_REVIEW
    assert "input_too_large" in document.review_reasons
    assert llm.calls == []
    assert store.tags == [("42", "Otros")]


def test_non_certificate_is_flagged_and_sent_to_review():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    payload = payload_dict(is_language_certificate=False)
    llm = FakeLlm([json.dumps(payload)])
    store = FakeStore()

    result = extract_certificate(document, llm=llm, store=store)

    assert result.state == Document.ProcessingState.PENDING_REVIEW
    assert result.is_language_certificate is False
    assert "non_certificate" in document.review_reasons
    certificate = Certificate.objects.get(document=document)
    assert certificate.is_language_certificate is False
    assert store.tags == [("42", "Otros")]


def test_multiple_certificates_flagged_without_silent_merge():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    payload = payload_dict(multiple_certificates_suspected=True)
    llm = FakeLlm([json.dumps(payload)])

    result = extract_certificate(document, llm=llm, store=FakeStore())

    assert result.multiple_certificates_suspected is True
    assert "multiple_certificates" in document.review_reasons
    certificate = Certificate.objects.get(document=document)
    assert certificate.multiple_certificates_suspected is True


def test_missing_text_routes_to_review():
    document = make_document()
    llm = FakeLlm([])

    result = extract_certificate(document, llm=llm, store=FakeStore())

    assert result.state == Document.ProcessingState.PENDING_REVIEW
    assert "missing_text" in document.review_reasons
    assert llm.calls == []


def test_invalid_state_is_refused():
    document = make_document(processing_state=Document.ProcessingState.STORED)
    llm = FakeLlm([])

    result = extract_certificate(document, llm=llm)

    assert result.refused is True
    assert llm.calls == []
    assert document.processing_state == Document.ProcessingState.STORED


# --- Internal endpoint (7.6) ---


def _patch_llm(monkeypatch, llm):
    monkeypatch.setattr(
        "documents.views.internal.extract_certificate",
        lambda document: extract_certificate(document, llm=llm, store=FakeStore()),
    )


def test_internal_extract_endpoint_is_idempotent(monkeypatch):
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    llm = FakeLlm([json.dumps(payload_dict())])
    _patch_llm(monkeypatch, llm)
    client = Client()
    url = reverse("internal-document-extract", args=[document.pk])

    first = client.post(url, HTTP_X_INTERNAL_TOKEN="test-internal-token")
    second = client.post(url, HTTP_X_INTERNAL_TOKEN="test-internal-token")

    assert first.status_code == 200
    assert first.json()["state"] == Document.ProcessingState.EXTRACTED
    assert second.json()["skipped"] is True
    assert Certificate.objects.filter(document=document).count() == 1
    assert len(llm.calls) == 1


def test_internal_extract_endpoint_requires_token(client):
    document = make_document()
    response = client.post(reverse("internal-document-extract", args=[document.pk]))
    assert response.status_code == 401


def test_internal_extract_endpoint_refuses_invalid_state(monkeypatch):
    document = make_document(processing_state=Document.ProcessingState.STORED)
    llm = FakeLlm([])
    _patch_llm(monkeypatch, llm)

    response = Client().post(
        reverse("internal-document-extract", args=[document.pk]),
        HTTP_X_INTERNAL_TOKEN="test-internal-token",
    )

    assert response.status_code == 409
    assert response.json()["refused"] is True


def test_reextraction_preserves_manually_edited_literals():
    document = make_document(processing_state=Document.ProcessingState.TEXT_READY)
    add_page(document, 1, PAGE_TEXT)
    certificate = Certificate.objects.create(
        document=document,
        language_literal="Français",
        manual_fields=["language_literal"],
    )
    llm = FakeLlm([json.dumps(payload_dict(language=field("English")))])

    result = extract_certificate(document, llm=llm, store=FakeStore())

    assert result.state == Document.ProcessingState.EXTRACTED
    certificate.refresh_from_db()
    assert certificate.language_literal == "Français"
    assert certificate.entity_literal == "Cambridge English"


# --- Extraction repair feedback (pipeline-reliability) ---


def test_invalid_output_is_repaired_with_feedback():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    llm = FakeLlm(["not json", json.dumps(payload_dict())])

    result = extract_certificate(document, llm=llm, store=FakeStore())

    assert result.state == Document.ProcessingState.EXTRACTED
    second_call_messages = llm.calls[1]["messages"]
    assert second_call_messages[-2]["role"] == "assistant"
    assert second_call_messages[-2]["content"] == "not json"
    repair = second_call_messages[-1]["content"]
    assert "failed validation" in repair


def test_out_of_range_confidence_is_rejected_and_repaired():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    bad = payload_dict()
    bad["confidence"] = 1.5
    llm = FakeLlm([json.dumps(bad), json.dumps(payload_dict())])

    result = extract_certificate(document, llm=llm, store=FakeStore())

    assert result.state == Document.ProcessingState.EXTRACTED
    assert len(llm.calls) == 2
    repair = llm.calls[1]["messages"][-1]["content"]
    assert "confidence" in repair


def test_unsupported_evidence_quote_is_kept_unverified_without_repair():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    bad = payload_dict()
    bad["student_name"] = field("Ada Lovelace", quote="not on this page")
    llm = FakeLlm([json.dumps(bad)])

    result = extract_certificate(document, llm=llm, store=FakeStore())

    assert result.state == Document.ProcessingState.EXTRACTED
    assert len(llm.calls) == 1
    certificate = Certificate.objects.get(document=document)
    assert "student_name" in certificate.unverified_fields


def test_repair_exhaustion_routes_to_review_with_invalid_extraction():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    bad = payload_dict()
    bad["confidence"] = 1.5
    llm = FakeLlm([json.dumps(bad)] * 3)

    result = extract_certificate(document, llm=llm, store=FakeStore())

    assert result.state == Document.ProcessingState.PENDING_REVIEW
    document.refresh_from_db()
    assert "invalid_extraction" in document.review_reasons
    assert Certificate.objects.filter(document=document).count() == 0


def test_invalid_date_evidence_is_dropped_not_fatal():
    payload = ExtractionPayload.model_validate(
        payload_dict(
            dates=[
                {
                    "text": "12 May 2024",
                    "role": "issue",
                    "page": 1,
                    "quote": "issued 12 May 2024",
                },
                {
                    "text": "bogus",
                    "role": "unknown",
                    "page": 1,
                    "quote": "not on this page",
                },
            ]
        )
    )

    _validate_evidence(payload, {1: PAGE_TEXT})

    assert len(payload.dates) == 1
    assert payload.dates[0].text == "12 May 2024"


def test_invalid_literal_evidence_marks_field_unverified():
    payload = ExtractionPayload.model_validate(
        payload_dict(student_name=field("Ada Lovelace", quote="missing quote"))
    )

    unverified = _validate_evidence(payload, {1: PAGE_TEXT})

    assert unverified == {"student_name"}
    assert payload.student_name.value == "Ada Lovelace"


def test_valid_literal_evidence_is_not_unverified():
    payload = ExtractionPayload.model_validate(payload_dict())

    unverified = _validate_evidence(payload, {1: PAGE_TEXT})

    assert unverified == set()


def test_empty_student_name_uses_label_fallback():
    document = make_document()
    add_page(
        document,
        1,
        "CERTIFICATE OF ENGLISH\n"
        "Obtingut per · Obtenido por · Obtained by\n"
        "Ariadna Vidal García\n"
        "quote",
    )
    data = payload_dict(
        student_name={"value": None, "evidence": None, "confidence": None},
        dates=[],
    )
    llm = FakeLlm([json.dumps(data)])

    result = extract_certificate(document, llm=llm, store=FakeStore())

    assert result.state == Document.ProcessingState.EXTRACTED
    certificate = Certificate.objects.get(document=document)
    assert certificate.student_name == "Ariadna Vidal García"
    assert certificate.evidence["student_name"]["quote"] == "Ariadna Vidal García"


def test_student_name_fallback_rejects_boilerplate():
    document = make_document()
    add_page(
        document,
        1,
        "Obtained by\nCERTIFICATE OF ENGLISH ASSESSMENT\nquote",
    )
    data = payload_dict(
        student_name={"value": None, "evidence": None, "confidence": None},
        dates=[],
    )
    llm = FakeLlm([json.dumps(data)])

    result = extract_certificate(document, llm=llm, store=FakeStore())

    assert result.state == Document.ProcessingState.EXTRACTED
    certificate = Certificate.objects.get(document=document)
    assert certificate.student_name == ""


def test_bad_literal_evidence_keeps_value_marked_unverified():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    data = payload_dict(student_name=field("Ada Lovelace", quote="missing quote"))
    llm = FakeLlm([json.dumps(data)])

    result = extract_certificate(document, llm=llm, store=FakeStore())

    assert result.state == Document.ProcessingState.EXTRACTED
    certificate = Certificate.objects.get(document=document)
    assert certificate.student_name == "Ada Lovelace"
    assert "student_name" in certificate.unverified_fields


def test_score_fallback_fills_empty_score():
    document = make_document()
    add_page(document, 1, PAGE_TEXT + "\nOverall Score\n80 /100\n")
    data = payload_dict(score={"value": None, "evidence": None, "confidence": None})
    llm = FakeLlm([json.dumps(data)])

    extract_certificate(document, llm=llm, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert certificate.score_literal == "80 /100"
    assert "score_literal" in certificate.unverified_fields


def test_issue_date_fallback_fills_empty_dates():
    document = make_document()
    add_page(
        document,
        1,
        "Cambridge English B2 First CERT-123 English quote text\nDate of issue: 5 May 2024",
    )
    data = payload_dict(dates=[])
    llm = FakeLlm([json.dumps(data)])

    extract_certificate(document, llm=llm, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    candidates = certificate.date_texts["candidates"]
    assert any(c["role"] == "issue" and "5 May 2024" in c["text"] for c in candidates)
    assert "issue_date" in certificate.unverified_fields


def test_second_pass_recovers_missing_score_and_date():
    document = make_document()
    add_page(document, 1, "Cambridge English B2 First CERT-123 English quote text")
    primary = payload_dict(
        score={"value": None, "evidence": None, "confidence": None},
        dates=[],
    )
    focused = payload_dict(
        score=field("99", quote="quote"),
        dates=[{"text": "12 May 2024", "role": "issue", "page": 1, "quote": "quote"}],
    )
    llm = FakeLlm([json.dumps(primary), json.dumps(focused)])

    extract_certificate(document, llm=llm, store=FakeStore())

    assert len(llm.calls) == 2
    assert "missed" in llm.calls[1]["messages"][1]["content"]
    certificate = Certificate.objects.get(document=document)
    assert certificate.score_literal == "99"
    assert certificate.date_texts["candidates"]


def test_second_pass_skipped_when_fields_present():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    llm = FakeLlm([json.dumps(payload_dict())])

    extract_certificate(document, llm=llm, store=FakeStore())

    assert len(llm.calls) == 1


def test_unverified_marks_excluded_for_manual_fields():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    Certificate.objects.create(
        document=document,
        student_name="Manual Name",
        manual_fields=["student_name"],
    )
    data = payload_dict(student_name=field("Ada Lovelace", quote="missing quote"))
    llm = FakeLlm([json.dumps(data)])

    extract_certificate(document, llm=llm, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert certificate.student_name == "Manual Name"
    assert "student_name" not in certificate.unverified_fields


def test_harvest_trilingual_date_block_dedupes_to_one_candidate():
    document = make_document()
    add_page(
        document,
        1,
        "CERTIFICAT DE · CERTIFICADO DE · CERTIFICATE OF\n"
        "80\n/100\n"
        "18 Setembre 2026 \n· \n18 Septiembre 2026 \n· \n18 September 2026\n"
        "Ref: 2161",
    )
    data = payload_dict(dates=[])
    llm = FakeLlm([json.dumps(data)])

    extract_certificate(document, llm=llm, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    candidates = certificate.date_texts["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["text"] == "18 Setembre 2026"
    assert candidates[0]["role"] == "unknown"


def test_harvest_skips_birth_dates_and_implausible_years():
    document = make_document()
    add_page(
        document,
        1,
        "Date of birth: 03/04/1990\nBorn 1990-04-03\nIssued 12/05/2024\n0399\n",
    )
    data = payload_dict(dates=[])
    llm = FakeLlm([json.dumps(data)])

    extract_certificate(document, llm=llm, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    texts = [c["text"] for c in certificate.date_texts["candidates"]]
    assert "03/04/1990" not in texts
    assert "1990-04-03" not in texts
    assert "0399" not in texts
    assert any("12/05/2024" in t for t in texts)


def test_harvest_dedupes_against_model_candidates():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    llm = FakeLlm([json.dumps(payload_dict())])

    extract_certificate(document, llm=llm, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    dates = [
        c["text"]
        for c in certificate.date_texts["candidates"]
        if "May 2024" in c["text"] or "2024" in c["text"]
    ]
    assert len(dates) == len(set(dates))


def test_student_name_strips_leading_honorifics():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    data = payload_dict(student_name=field("Doña María González Pérez"))
    llm = FakeLlm([json.dumps(data)])

    extract_certificate(document, llm=llm, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert certificate.student_name == "María González Pérez"
    assert certificate.evidence["student_name"]["stripped_titles"] == ["Doña"]


def test_student_name_strips_multilingual_titles():
    for raw, expected in (
        ("Mr. John Smith", "John Smith"),
        ("Mme Claire Martin", "Claire Martin"),
        ("Frau Anna Schmidt", "Anna Schmidt"),
        ("Senhora Maria Silva", "Maria Silva"),
        ("Senyora Anna Vidal", "Anna Vidal"),
    ):
        document = make_document(fingerprint=str(abs(hash(raw))))
        add_page(document, 1, PAGE_TEXT)
        data = payload_dict(student_name=field(raw))
        llm = FakeLlm([json.dumps(data)])

        extract_certificate(document, llm=llm, store=FakeStore())

        certificate = Certificate.objects.get(document=document)
        assert certificate.student_name == expected, raw


def test_student_name_preserves_ambiguous_tokens():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    data = payload_dict(student_name=field("Don Pablo Rivera"))
    llm = FakeLlm([json.dumps(data)])

    extract_certificate(document, llm=llm, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert certificate.student_name == "Don Pablo Rivera"


def test_student_name_keeps_two_word_remainder():
    document = make_document()
    add_page(document, 1, PAGE_TEXT)
    data = payload_dict(student_name=field("Doña María"))
    llm = FakeLlm([json.dumps(data)])

    extract_certificate(document, llm=llm, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert certificate.student_name == "Doña María"
