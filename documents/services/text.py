"""Text acquisition: embedded PDF text first, OCR only where needed."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import magic
from django.conf import settings
from django.db import transaction
from pypdf import PdfReader

from documents.models import Certificate, Document, DocumentPage
from documents.services.labels import apply_manual_review_label
from documents.services.ocr import (
    OcrClient,
    OcrError,
    OcrPage,
    OcrResult,
    build_ocr_client,
)
from documents.services.paperless import (
    DocumentStore,
    PaperlessError,
    build_document_store,
)
from documents.services.validation import EXTENSION_BY_TYPE as _EXTENSION_BY_TYPE

_SNIFFED_TYPES = set(_EXTENSION_BY_TYPE) | {"image/x-ms-bmp"}


def _sniffed_type(data: bytes) -> str:
    """Detect the real payload type; Paperless may store image archives as PDF."""
    try:
        mime = magic.from_buffer(data[:4096], mime=True)
    except Exception:
        return ""
    return mime if mime in _SNIFFED_TYPES else ""


def _effective_name(filename: str, content_type: str) -> str:
    from pathlib import Path

    extension = _EXTENSION_BY_TYPE.get(content_type)
    if extension is None:
        return filename
    stem = Path(filename or "document").stem
    return f"{stem}{extension}"


TEXT_REASON_CODES = {
    "insufficient_text",
    "low_ocr_confidence",
    "ocr_failed",
    "incomplete_ocr",
    "original_unavailable",
    "manual_label_failed",
    "unreadable",
    "timeout",
    "empty_file",
    "unsupported_file",
    "too_many_pages",
}

SKIPPED_STATES = {
    Document.ProcessingState.EXTRACTED.value,
    Document.ProcessingState.CLASSIFIED.value,
    Document.ProcessingState.APPROVED.value,
    Document.ProcessingState.REJECTED.value,
}


@dataclass(frozen=True)
class TextAcquisitionResult:
    document: Document
    page_count: int | None
    text_method: str
    review_reasons: tuple[str, ...]
    error: str = ""
    skipped: bool = False


def usable_char_count(text: str) -> int:
    """Count non-whitespace characters, matching the sufficiency threshold."""

    return len("".join(text.split()))


def _pdf_texts(data: bytes) -> tuple[list[str], int]:
    reader = PdfReader(BytesIO(data))
    texts = [page.extract_text() or "" for page in reader.pages]
    return texts, len(reader.pages)


def _method_for(pages: list[OcrPage]) -> str:
    methods = {page.method for page in pages}
    if methods == {"embedded"}:
        return Document.TextMethod.EMBEDDED.value
    if methods == {"ocr"}:
        return Document.TextMethod.OCR.value
    return Document.TextMethod.MIXED.value


def _reason_list(document: Document, reasons: list[str]) -> list[str]:
    existing = [
        reason for reason in (document.review_reasons or []) if reason not in TEXT_REASON_CODES
    ]
    merged = existing + [reason for reason in reasons if reason not in existing]
    return list(dict.fromkeys(merged))


def _save(
    document: Document,
    *,
    pages: list[OcrPage] | None,
    text_method: str | None,
    state: str,
    reasons: list[str],
    error: str,
) -> TextAcquisitionResult:
    with transaction.atomic():
        if pages is not None:
            for page in pages:
                DocumentPage.objects.update_or_create(
                    document=document,
                    page_number=page.page_number,
                    defaults={
                        "text": page.text,
                        "method": page.method,
                        "ocr_confidence": page.confidence
                        if page.method == DocumentPage.Method.OCR
                        else None,
                    },
                )
            DocumentPage.objects.filter(document=document, page_number__gt=len(pages)).delete()
            document.page_count = len(pages)
        if text_method is not None:
            document.text_method = text_method
        document.processing_state = state
        document.error_reason = error
        document.review_reasons = _reason_list(document, reasons)
        document.save()
    return TextAcquisitionResult(
        document=document,
        page_count=document.page_count,
        text_method=document.text_method,
        review_reasons=tuple(document.review_reasons or ()),
        error=error,
    )


def _fail(
    document: Document,
    *,
    store: DocumentStore | None,
    code: str,
    message: str,
    state: str = Document.ProcessingState.ERROR.value,
    pages: list[OcrPage] | None = None,
    text_method: str | None = None,
) -> TextAcquisitionResult:
    result = _save(
        document,
        pages=pages,
        text_method=text_method,
        state=state,
        reasons=[code],
        error=message,
    )
    apply_manual_review_label(document, store=store)
    return TextAcquisitionResult(
        document=document,
        page_count=result.page_count,
        text_method=result.text_method,
        review_reasons=tuple(document.review_reasons or ()),
        error=message,
    )


def _should_skip(document: Document) -> bool:
    if document.processing_state in SKIPPED_STATES:
        return True
    if document.processing_state == Document.ProcessingState.PENDING_REVIEW.value:
        return Certificate.objects.filter(document_id=document.pk).exists()
    return False


def _embedded_pages(texts: list[str]) -> list[OcrPage]:
    return [
        OcrPage(
            page_number=index + 1,
            text=text,
            method=DocumentPage.Method.EMBEDDED.value,
            confidence=1.0,
        )
        for index, text in enumerate(texts)
    ]


def _finish_pages(
    document: Document,
    *,
    store: DocumentStore | None,
    pages: list[OcrPage],
    ocr_result: OcrResult | None,
    low_confidence_threshold: float,
    min_text_chars: int,
) -> TextAcquisitionResult:
    text_method = _method_for(pages)
    total = sum(usable_char_count(page.text) for page in pages)
    ocr_pages = [page for page in pages if page.method == DocumentPage.Method.OCR.value]
    reasons: list[str] = []
    if total < min_text_chars:
        reasons.append("insufficient_text")
    if ocr_pages and ocr_result is not None:
        mean_confidence = ocr_result.mean_confidence
        if ocr_result.quality == "low" or mean_confidence < low_confidence_threshold:
            reasons.append("low_ocr_confidence")

    state = (
        Document.ProcessingState.PENDING_REVIEW.value
        if "insufficient_text" in reasons
        else Document.ProcessingState.TEXT_READY.value
    )
    result = _save(
        document,
        pages=pages,
        text_method=text_method,
        state=state,
        reasons=reasons,
        error="",
    )
    if state == Document.ProcessingState.PENDING_REVIEW.value:
        apply_manual_review_label(document, store=store)
        result = TextAcquisitionResult(
            document=document,
            page_count=result.page_count,
            text_method=result.text_method,
            review_reasons=tuple(document.review_reasons or ()),
            error="",
        )
    return result


def acquire_text(
    document: Document,
    *,
    data: bytes | None = None,
    store: DocumentStore | None = None,
    ocr_client: OcrClient | None = None,
) -> TextAcquisitionResult:
    """Acquire text for a stored document, idempotently."""

    if _should_skip(document):
        return TextAcquisitionResult(
            document=document,
            page_count=document.page_count,
            text_method=document.text_method,
            review_reasons=tuple(document.review_reasons or ()),
            skipped=True,
        )

    owns_store = store is None
    owns_ocr = ocr_client is None
    selected_store = store
    selected_ocr = ocr_client
    try:
        if data is None:
            if not document.paperless_document_id:
                return _fail(
                    document,
                    store=selected_store,
                    code="original_unavailable",
                    message="Document has no stored original to process",
                )
            selected_store = selected_store or build_document_store()
            try:
                data = selected_store.download_original(document.paperless_document_id)
            except PaperlessError as exc:
                return _fail(
                    document,
                    store=selected_store,
                    code="original_unavailable",
                    message=str(exc),
                )

        sniffed = _sniffed_type(data)
        effective_type = sniffed or document.content_type or "application/octet-stream"
        effective_name = _effective_name(document.original_filename or "document", effective_type)
        is_pdf = effective_type == "application/pdf"
        app = settings.APP
        min_chars = int(app["ocr_min_text_chars"])
        embedded_threshold = int(app["embedded_text_min_chars"])
        confidence_threshold = float(app["ocr_low_confidence_threshold"])

        if is_pdf:
            try:
                texts, page_count = _pdf_texts(data)
            except Exception:
                return _fail(
                    document,
                    store=selected_store,
                    code="unreadable",
                    message="The PDF could not be parsed",
                )
            if page_count == 0:
                return _fail(
                    document,
                    store=selected_store,
                    code="unreadable",
                    message="The PDF has no pages",
                )

            if all(usable_char_count(text) >= embedded_threshold for text in texts):
                pages = _embedded_pages(texts)
                return _finish_pages(
                    document,
                    store=selected_store,
                    pages=pages,
                    ocr_result=None,
                    low_confidence_threshold=confidence_threshold,
                    min_text_chars=min_chars,
                )

            selected_ocr = selected_ocr or build_ocr_client()
            try:
                ocr_result = selected_ocr.extract(
                    data,
                    effective_name,
                    effective_type,
                )
            except OcrError as exc:
                pages = _embedded_pages(texts)
                no_text = exc.code == "no_text"
                return _fail(
                    document,
                    store=selected_store,
                    code="insufficient_text" if no_text else "ocr_failed",
                    message=str(exc),
                    state=Document.ProcessingState.PENDING_REVIEW.value
                    if no_text
                    else Document.ProcessingState.ERROR.value,
                    pages=pages,
                    text_method=Document.TextMethod.EMBEDDED.value,
                )

            expected = list(range(1, page_count + 1))
            actual = [page.page_number for page in ocr_result.pages]
            if actual != expected:
                return _fail(
                    document,
                    store=selected_store,
                    code="incomplete_ocr",
                    message="OCR did not return every page in order",
                    pages=_embedded_pages(texts),
                    text_method=Document.TextMethod.EMBEDDED.value,
                )
            return _finish_pages(
                document,
                store=selected_store,
                pages=list(ocr_result.pages),
                ocr_result=ocr_result,
                low_confidence_threshold=confidence_threshold,
                min_text_chars=min_chars,
            )

        selected_ocr = selected_ocr or build_ocr_client()
        try:
            ocr_result = selected_ocr.extract(
                data,
                effective_name,
                effective_type,
            )
        except OcrError as exc:
            no_text = exc.code == "no_text"
            return _fail(
                document,
                store=selected_store,
                code="insufficient_text" if no_text else "ocr_failed",
                message=str(exc),
                state=Document.ProcessingState.PENDING_REVIEW.value
                if no_text
                else Document.ProcessingState.ERROR.value,
            )

        return _finish_pages(
            document,
            store=selected_store,
            pages=list(ocr_result.pages),
            ocr_result=ocr_result,
            low_confidence_threshold=confidence_threshold,
            min_text_chars=min_chars,
        )
    finally:
        if owns_ocr and selected_ocr is not None:
            selected_ocr.close()
        if owns_store and selected_store is not None:
            selected_store.close()
