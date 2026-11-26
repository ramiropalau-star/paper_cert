"""End-to-end pipeline tests: upload -> text -> extract -> classify -> review."""

import json
from datetime import date

import pytest
from django.core.management import call_command

from catalog.models import Entity, Language
from documents.models import Certificate, Document, DocumentPage
from documents.services.classification import classify_certificate
from documents.services.extraction import extract_certificate
from documents.services.intake import process_upload
from documents.services.ocr import OcrPage, OcrResult
from documents.services.review import approve_certificate
from documents.services.text import acquire_text
from tests.fixturegen import (
    CERTIFICATE_LINES,
    ambiguous_date_pdf_bytes,
    heic_bytes,
    incomplete_pdf_bytes,
    jpg_bytes,
    multipage_pdf_bytes,
    non_certificate_pdf_bytes,
    png_bytes,
    scanned_pdf_bytes,
    text_pdf_bytes,
    tiff_bytes,
    unknown_entity_pdf_bytes,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def catalog(db):
    call_command("seed_catalog", verbosity=0)


class FakeStore:
    def __init__(self, data: bytes = b""):
        self.data = data
        self.tags_added = []
        self.tags_removed = []
        self.closed = False

    def store_document(self, path, filename, content_type):
        return "77"

    def download_original(self, document_id):
        return self.data

    def add_tag(self, document_id, name):
        self.tags_added.append(name)
        return True

    def remove_tag(self, document_id, name):
        self.tags_removed.append(name)
        return True

    def delete_document(self, document_id):
        pass

    def close(self):
        self.closed = True


class StubLLM:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = 0

    def chat(self, messages, *, format=None, temperature=0.0):
        self.calls += 1
        return json.dumps(self.payload)

    def close(self):
        pass


class StubOCR:
    def __init__(self, text: str, pages: int = 1, confidence: float = 0.9):
        self.text = text
        self.pages = pages
        self.confidence = confidence
        self.calls = 0

    def extract(self, data, filename, content_type, **kwargs):
        self.calls += 1
        return OcrResult(
            pages=tuple(
                OcrPage(
                    page_number=index,
                    text=self.text,
                    method="ocr",
                    confidence=self.confidence,
                )
                for index in range(1, self.pages + 1)
            ),
            engine={"name": "stub"},
            mean_confidence=self.confidence,
            quality="ok",
            contract_version="v1",
        )

    def close(self):
        pass


def field(value, *, page: int = 1, quote: str | None = None, confidence: float = 0.9):
    evidence = {"page": page, "quote": quote} if quote is not None else None
    return {
        "value": value,
        "evidence": evidence,
        "confidence": confidence,
    }


def payload_dict(**overrides) -> dict:
    data = {
        "is_language_certificate": True,
        "multiple_certificates_suspected": False,
        "student_name": field("Ada Lovelace", quote="Student Name: Ada Lovelace"),
        "language": field("English"),
        "entity": field("Cambridge English"),
        "issuing_body": field(None),
        "test_center": field(None),
        "exam": field("B2 First"),
        "level": field("B2"),
        "score": field("180"),
        "certificate_code": field("CERT-2024-001"),
        "dates": [
            {
                "text": "12 May 2024",
                "role": "issue",
                "page": 1,
                "quote": "Date of Issue: 12 May 2024",
            }
        ],
        "confidence": 0.9,
    }
    data.update(overrides)
    return data


def run_pipeline(
    data: bytes,
    filename: str,
    content_type: str,
    *,
    llm_payload: dict,
    ocr_text: str = "\n".join(CERTIFICATE_LINES),
    ocr_pages: int = 1,
):
    """Run upload -> acquire -> extract -> classify with fakes."""
    store = FakeStore(data=data)
    result = process_upload(data, filename, content_type, store=store)
    assert result.error == "", result.error
    document = result.document

    acquire_text(document, data=data, store=store, ocr_client=StubOCR(ocr_text, ocr_pages))
    document.refresh_from_db()

    llm = StubLLM(llm_payload)
    extract_certificate(document, llm=llm, store=store)
    document.refresh_from_db()

    classify_certificate(document, store=store)
    document.refresh_from_db()
    return document, store, llm


# --- 13.2 text PDF and scanned PDF ---


def test_text_pdf_end_to_end():
    document, store, llm = run_pipeline(
        text_pdf_bytes(), "cert.pdf", "application/pdf", llm_payload=payload_dict()
    )

    assert llm.calls == 1
    assert document.processing_state == Document.ProcessingState.PENDING_REVIEW.value
    assert document.text_method == Document.TextMethod.EMBEDDED.value
    assert document.page_count == 1

    certificate = document.certificate
    assert certificate.student_name == "Ada Lovelace"
    assert certificate.language == Language.objects.get(code="eng")
    assert certificate.entity == Entity.objects.get(name="Cambridge English")
    assert certificate.cefr_level == "B2"
    assert certificate.issue_date == date(2024, 5, 12)
    assert certificate.is_language_certificate is True

    # idempotent re-run: no duplicate work
    again = classify_certificate(document, store=store)
    assert again.skipped is True
    assert Certificate.objects.count() == 1


def test_scanned_pdf_end_to_end_uses_ocr():
    document, _store, _llm = run_pipeline(
        scanned_pdf_bytes(),
        "scan.pdf",
        "application/pdf",
        llm_payload=payload_dict(),
        ocr_text="Scanned certificate\n" + "\n".join(CERTIFICATE_LINES),
    )

    assert document.text_method == Document.TextMethod.OCR.value
    assert document.page_count == 1
    page = DocumentPage.objects.get(document=document)
    assert page.method == DocumentPage.Method.OCR.value
    assert "Scanned certificate" in page.text
    assert document.certificate.entity == Entity.objects.get(name="Cambridge English")


def test_pipeline_approval_and_report_eligibility():
    document, store, _llm = run_pipeline(
        text_pdf_bytes(), "cert.pdf", "application/pdf", llm_payload=payload_dict()
    )
    outcome = approve_certificate(document.certificate, actor=None, store=store)
    assert outcome.ok is True
    document.refresh_from_db()
    assert document.processing_state == Document.ProcessingState.APPROVED.value
    assert document.certificate.review_status == Certificate.ReviewStatus.APPROVED


# --- 13.3 image and edge-case inputs ---


@pytest.mark.parametrize(
    "builder,filename,content_type",
    [
        (jpg_bytes, "cert.jpg", "image/jpeg"),
        (png_bytes, "cert.png", "image/png"),
        (tiff_bytes, "cert.tiff", "image/tiff"),
        (heic_bytes, "cert.heic", "image/heic"),
    ],
)
def test_image_inputs_end_to_end(builder, filename, content_type):
    document, _store, _llm = run_pipeline(
        builder(), filename, content_type, llm_payload=payload_dict()
    )
    assert document.text_method == Document.TextMethod.OCR.value
    assert document.certificate.student_name == "Ada Lovelace"


def test_multipage_pdf_end_to_end():
    document, _store, _llm = run_pipeline(
        multipage_pdf_bytes(),
        "multi.pdf",
        "application/pdf",
        llm_payload=payload_dict(),
        ocr_pages=3,
    )
    assert document.page_count == 3
    assert DocumentPage.objects.filter(document=document).count() == 3


def test_incomplete_certificate_routes_to_review():
    payload = payload_dict()
    payload["student_name"] = field("Grace Hopper", quote="Student Name: Grace Hopper")
    payload["level"] = field(None)
    payload["score"] = field(None)
    payload["dates"] = []
    document, _store, _llm = run_pipeline(
        incomplete_pdf_bytes(), "incomplete.pdf", "application/pdf", llm_payload=payload
    )
    certificate = document.certificate
    assert certificate.review_status == Certificate.ReviewStatus.PENDING
    assert "missing_essential_fields" in certificate.review_reasons


def test_unknown_entity_stays_literal_and_reviews():
    payload = payload_dict()
    payload["student_name"] = field("Katherine Johnson", quote="Student Name: Katherine Johnson")
    payload["entity"] = field("Acme Language Board")
    payload["exam"] = field("Proficiency Test")
    payload["dates"] = [
        {
            "text": "2024-03-01",
            "role": "issue",
            "page": 1,
            "quote": "Date of Issue: 2024-03-01",
        }
    ]
    document, store, _llm = run_pipeline(
        unknown_entity_pdf_bytes(), "unknown.pdf", "application/pdf", llm_payload=payload
    )
    certificate = document.certificate
    assert certificate.entity is None
    assert certificate.entity_literal == "Acme Language Board"
    assert "unknown_entity" in certificate.review_reasons
    assert "Otros" in store.tags_added


def test_non_certificate_labeled_otros():
    payload = payload_dict(is_language_certificate=False)
    payload["student_name"] = field(None)
    payload["dates"] = []
    document, store, _llm = run_pipeline(
        non_certificate_pdf_bytes(), "invoice.pdf", "application/pdf", llm_payload=payload
    )
    assert document.processing_state == Document.ProcessingState.PENDING_REVIEW.value
    assert "non_certificate" in (document.review_reasons or [])
    assert "Otros" in store.tags_added


def test_ambiguous_date_triggers_review():
    payload = payload_dict()
    # IELTS has no seeded date_order, so day/month stays ambiguous.
    payload["student_name"] = field("Alan Turing", quote="Student Name: Alan Turing")
    payload["entity"] = field("IELTS")
    payload["dates"] = [
        {
            "text": "05/06/2024",
            "role": "issue",
            "page": 1,
            "quote": "Date of Issue: 05/06/2024",
        }
    ]
    document, _store, _llm = run_pipeline(
        ambiguous_date_pdf_bytes(),
        "ambiguous.pdf",
        "application/pdf",
        llm_payload=payload,
    )
    certificate = document.certificate
    # ambiguous day/month stays in detected_date (day-first) and triggers review
    assert certificate.issue_date is None
    assert certificate.detected_date == date(2024, 6, 5)
    assert "ambiguous_date" in certificate.review_reasons


def test_duplicate_upload_creates_single_record():
    data = text_pdf_bytes()
    store = FakeStore(data=data)
    first = process_upload(data, "cert.pdf", "application/pdf", store=store)
    second = process_upload(data, "cert-copy.pdf", "application/pdf", store=store)
    assert first.duplicate is False
    assert second.duplicate is True
    assert second.document.pk == first.document.pk
    assert Document.objects.count() == 1
