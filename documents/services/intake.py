"""Intake state machine: validate, deduplicate, store, and persist."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from django.db import transaction

from documents.models import Document
from documents.services.n8n import notify_processing
from documents.services.paperless import (
    DocumentStore,
    PaperlessError,
    build_document_store,
)
from documents.services.staging import staged_upload
from documents.services.state import transition_document
from documents.services.validation import IntakeValidationError, validate_upload


@dataclass(frozen=True)
class IntakeResult:
    document: Document | None
    duplicate: bool = False
    error: str = ""
    error_code: str = ""


def fingerprint_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def process_upload(
    data: bytes,
    filename: str,
    content_type: str,
    *,
    user=None,
    store: DocumentStore | None = None,
) -> IntakeResult:
    try:
        validated = validate_upload(data, filename, content_type)
    except IntakeValidationError as exc:
        return IntakeResult(None, error=exc.message, error_code=exc.code)

    fingerprint = fingerprint_bytes(data)
    existing = Document.objects.filter(fingerprint=fingerprint).first()
    if existing is not None:
        return IntakeResult(existing, duplicate=True)

    document = Document.objects.create(
        fingerprint=fingerprint,
        original_filename=validated.filename,
        content_type=validated.content_type,
        size_bytes=len(validated.data),
        page_count=validated.page_count,
        processing_state=Document.ProcessingState.RECEIVED,
        uploaded_by=user,
    )

    owns_store = store is None
    store = store or build_document_store()
    try:
        with staged_upload(validated.data, validated.filename) as path:
            paperless_id = store.store_document(path, validated.filename, validated.content_type)
    except PaperlessError as exc:
        transition_document(
            document,
            Document.ProcessingState.ERROR,
            fields={"error_reason": str(exc)},
        )
        return IntakeResult(document, error=str(exc), error_code="paperless_error")
    finally:
        if owns_store:
            store.close()

    with transaction.atomic():
        transition_document(
            document,
            Document.ProcessingState.STORED,
            fields={
                "paperless_document_id": paperless_id,
                "error_reason": "",
            },
        )

    notify_processing(document)
    return IntakeResult(document)
