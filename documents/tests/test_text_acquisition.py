from io import BytesIO

import pytest
from django.test import Client
from django.urls import reverse
from reportlab.pdfgen import canvas

from documents.models import Document, DocumentPage
from documents.services.ocr import OcrError, OcrPage, OcrResult
from documents.services.paperless import PaperlessError
from documents.services.text import acquire_text

pytestmark = pytest.mark.django_db


def text_pdf_bytes(page_texts: list[str]) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(612, 792))
    for text in page_texts:
        pdf.setFont("Helvetica", 14)
        pdf.drawString(50, 700, text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


LONG_TEXT = "LANGUAGE CERTIFICATE CEFR B2 ENGLISH ISSUED BY TESTING BOARD"
SHORT_TEXT = "Certificate page 1"


def make_document(**overrides) -> Document:
    data = {
        "fingerprint": "b" * 64,
        "original_filename": "certificate.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
        "paperless_document_id": "42",
        "processing_state": Document.ProcessingState.STORED,
    }
    data.update(overrides)
    return Document.objects.create(**data)


class FakeOcr:
    def __init__(
        self,
        pages: list[OcrPage] | None = None,
        *,
        error: Exception | None = None,
        mean_confidence: float = 0.9,
        quality: str = "ok",
    ):
        self.pages = pages or []
        self.error = error
        self.mean_confidence = mean_confidence
        self.quality = quality
        self.calls: list[tuple] = []
        self.closed = False

    def extract(self, data, filename, content_type, **kwargs):
        self.calls.append((data, filename, content_type, kwargs))
        if self.error:
            raise self.error
        return OcrResult(
            pages=tuple(self.pages),
            engine={"name": "fake"},
            mean_confidence=self.mean_confidence,
            quality=self.quality,
            contract_version="v1",
        )

    def close(self):
        self.closed = True


class FakeStore:
    def __init__(self, *, data: bytes = b"", tag_error: Exception | None = None):
        self.data = data
        self.tag_error = tag_error
        self.downloaded: list[str] = []
        self.tags: list[tuple[str, str]] = []
        self.removed: list[tuple[str, str]] = []
        self.closed = False

    def download_original(self, document_id):
        self.downloaded.append(document_id)
        return self.data

    def add_tag(self, document_id, name):
        if self.tag_error:
            raise self.tag_error
        self.tags.append((document_id, name))
        return True

    def remove_tag(self, document_id, name):
        if self.tag_error:
            raise self.tag_error
        self.removed.append((document_id, name))
        return True

    def close(self):
        self.closed = True


def ocr_page(
    number: int = 1, text: str = LONG_TEXT, method: str = "ocr", confidence: float = 0.9
) -> OcrPage:
    return OcrPage(page_number=number, text=text, method=method, confidence=confidence)


def test_text_pdf_records_each_page_as_embedded_and_skips_ocr():
    document = make_document()
    ocr = FakeOcr(error=AssertionError("OCR must not run"))
    store = FakeStore()

    result = acquire_text(
        document,
        data=text_pdf_bytes([LONG_TEXT, LONG_TEXT]),
        store=store,
        ocr_client=ocr,
    )

    assert result.text_method == Document.TextMethod.EMBEDDED
    assert result.page_count == 2
    assert document.processing_state == Document.ProcessingState.TEXT_READY
    assert document.pages.count() == 2
    assert list(document.pages.values_list("page_number", "method")) == [
        (1, "embedded"),
        (2, "embedded"),
    ]
    assert ocr.calls == []
    assert store.tags == []


def test_scanned_pdf_uses_ocr_and_records_confidence():
    document = make_document()
    ocr = FakeOcr([ocr_page(text=LONG_TEXT, confidence=0.92)])

    result = acquire_text(
        document,
        data=text_pdf_bytes([SHORT_TEXT]),
        store=FakeStore(),
        ocr_client=ocr,
    )

    assert result.text_method == Document.TextMethod.OCR
    assert result.page_count == 1
    page = document.pages.get(page_number=1)
    assert page.method == DocumentPage.Method.OCR
    assert page.ocr_confidence == 0.92
    assert document.processing_state == Document.ProcessingState.TEXT_READY
    assert len(ocr.calls) == 1


def test_image_only_uses_ocr():
    document = make_document(content_type="image/png", original_filename="certificate.png")
    ocr = FakeOcr([ocr_page(text=LONG_TEXT)])

    result = acquire_text(document, data=b"\x89PNG", store=FakeStore(), ocr_client=ocr)

    assert result.text_method == Document.TextMethod.OCR
    assert document.pages.get(page_number=1).method == DocumentPage.Method.OCR


def test_mixed_pdf_preserves_per_page_methods():
    document = make_document()
    ocr = FakeOcr(
        [
            ocr_page(number=1, text=LONG_TEXT, method="embedded", confidence=1.0),
            ocr_page(number=2, text=LONG_TEXT, method="ocr", confidence=0.88),
        ]
    )

    result = acquire_text(
        document,
        data=text_pdf_bytes([LONG_TEXT, SHORT_TEXT]),
        store=FakeStore(),
        ocr_client=ocr,
    )

    assert result.text_method == Document.TextMethod.MIXED
    assert list(document.pages.values_list("method", flat=True)) == [
        "embedded",
        "ocr",
    ]
    assert result.review_reasons == ()


def test_multipage_ocr_keeps_page_order():
    document = make_document()
    ocr = FakeOcr(
        [
            ocr_page(number=1, text="first page " + LONG_TEXT),
            ocr_page(number=2, text="second page " + LONG_TEXT),
        ]
    )

    result = acquire_text(
        document,
        data=text_pdf_bytes([SHORT_TEXT, SHORT_TEXT]),
        store=FakeStore(),
        ocr_client=ocr,
    )

    assert result.page_count == 2
    assert list(document.pages.values_list("page_number", "text")) == [
        (1, "first page " + LONG_TEXT),
        (2, "second page " + LONG_TEXT),
    ]


def test_low_ocr_confidence_is_flagged_without_stopping_pipeline():
    document = make_document()
    ocr = FakeOcr([ocr_page()], mean_confidence=0.4, quality="low")

    result = acquire_text(
        document,
        data=text_pdf_bytes([SHORT_TEXT]),
        store=FakeStore(),
        ocr_client=ocr,
    )

    assert document.processing_state == Document.ProcessingState.TEXT_READY
    assert "low_ocr_confidence" in result.review_reasons
    assert document.error_reason == ""


def test_insufficient_text_moves_to_review_and_labels_original():
    document = make_document()
    store = FakeStore()
    ocr = FakeOcr([ocr_page(text="hi", confidence=0.9)])

    result = acquire_text(
        document,
        data=text_pdf_bytes([SHORT_TEXT]),
        store=store,
        ocr_client=ocr,
    )

    assert document.processing_state == Document.ProcessingState.PENDING_REVIEW
    assert "insufficient_text" in result.review_reasons
    assert store.tags == [("42", "Otros")]
    assert document.pages.count() == 1


def test_ocr_failure_sets_error_and_keeps_embedded_pages():
    document = make_document()
    store = FakeStore()
    ocr = FakeOcr(error=OcrError("OCR timed out", code="timeout", retryable=True))

    result = acquire_text(
        document,
        data=text_pdf_bytes([SHORT_TEXT]),
        store=store,
        ocr_client=ocr,
    )

    assert document.processing_state == Document.ProcessingState.ERROR
    assert "ocr_failed" in result.review_reasons
    assert "OCR timed out" in document.error_reason
    assert document.pages.get(page_number=1).method == DocumentPage.Method.EMBEDDED
    assert store.tags == [("42", "Otros")]


def test_no_text_is_review_not_error():
    document = make_document()
    store = FakeStore()
    ocr = FakeOcr(error=OcrError("too little text", code="no_text"))

    result = acquire_text(
        document,
        data=text_pdf_bytes([SHORT_TEXT]),
        store=store,
        ocr_client=ocr,
    )

    assert document.processing_state == Document.ProcessingState.PENDING_REVIEW
    assert "insufficient_text" in result.review_reasons
    assert store.tags == [("42", "Otros")]


def test_label_failure_does_not_discard_processing_result():
    document = make_document()
    store = FakeStore(tag_error=PaperlessError("tag API down"))
    ocr = FakeOcr(error=OcrError("OCR timed out", code="timeout"))

    acquire_text(
        document,
        data=text_pdf_bytes([SHORT_TEXT]),
        store=store,
        ocr_client=ocr,
    )

    document.refresh_from_db()
    assert document.processing_state == Document.ProcessingState.ERROR
    assert "ocr_failed" in document.review_reasons
    assert "manual_label_failed" in document.review_reasons


def test_downloads_original_when_data_is_not_supplied():
    document = make_document()
    store = FakeStore(data=text_pdf_bytes([LONG_TEXT]))
    ocr = FakeOcr(error=AssertionError("OCR must not run"))

    result = acquire_text(document, store=store, ocr_client=ocr)

    assert store.downloaded == ["42"]
    assert result.text_method == Document.TextMethod.EMBEDDED
    assert document.processing_state == Document.ProcessingState.TEXT_READY


def test_missing_original_is_an_error():
    document = make_document(
        paperless_document_id="", processing_state=Document.ProcessingState.RECEIVED
    )

    result = acquire_text(document)

    assert document.processing_state == Document.ProcessingState.ERROR
    assert "original_unavailable" in result.review_reasons


def test_internal_endpoint_is_idempotent(monkeypatch, settings):
    monkeypatch.setitem(settings.APP, "internal_api_token", "secret")
    document = make_document()
    store = FakeStore()
    ocr = FakeOcr([ocr_page()])

    def fake_acquire(target):
        return acquire_text(
            target,
            data=text_pdf_bytes([SHORT_TEXT]),
            store=store,
            ocr_client=ocr,
        )

    monkeypatch.setattr("documents.views.internal.acquire_text", fake_acquire)
    client = Client()
    url = reverse("internal-document-text", args=[document.pk])

    first = client.post(url, HTTP_X_INTERNAL_TOKEN="secret")
    second = client.post(url, HTTP_X_INTERNAL_TOKEN="secret")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["state"] == Document.ProcessingState.TEXT_READY
    assert second.json()["page_count"] == 1
    assert DocumentPage.objects.filter(document=document).count() == 1
    assert DocumentPage.objects.get(document=document).text == LONG_TEXT


def test_internal_endpoint_requires_token(settings, monkeypatch):
    monkeypatch.setitem(settings.APP, "internal_api_token", "secret")
    document = make_document()

    response = Client().post(reverse("internal-document-text", args=[document.pk]))

    assert response.status_code == 401


def test_terminal_document_is_not_reprocessed(monkeypatch, settings):
    monkeypatch.setitem(settings.APP, "internal_api_token", "secret")
    document = make_document(processing_state=Document.ProcessingState.APPROVED)

    response = Client().post(
        reverse("internal-document-text", args=[document.pk]),
        HTTP_X_INTERNAL_TOKEN="secret",
    )

    assert response.status_code == 200
    assert response.json()["skipped"] is True
