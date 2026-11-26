"""Ingest documents that entered Paperless-ngx outside the app upload flow.

Paperless webhooks (document added) hit the internal endpoint, which calls
``ingest_paperless_document``. The record is created already ``stored`` because
Paperless is the repository of record; deduplication still runs on the SHA-256
fingerprint of the downloaded original.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass

from django.db import transaction

from documents.models import Document
from documents.services.filetype import effective_name, sniffed_type
from documents.services.intake import fingerprint_bytes
from documents.services.n8n import notify_processing
from documents.services.paperless import DocumentStore, PaperlessError, build_document_store
from documents.services.validation import (
    EXTENSION_BY_TYPE as _EXTENSION_BY_MIME,
)
from documents.services.validation import (
    IntakeValidationError,
    validate_upload,
)


@dataclass(frozen=True)
class PaperlessIngestResult:
    document: Document | None
    duplicate: bool = False
    error: str = ""
    error_code: str = ""


def _filename_for(metadata: dict, document_id: str) -> tuple[str, str]:
    original = str(metadata.get("original_file_name") or "").strip()
    mime = str(metadata.get("mime_type") or "").strip() or "application/octet-stream"
    if original:
        return original, mime
    extension = _EXTENSION_BY_MIME.get(mime) or mimetypes.guess_extension(mime) or ".bin"
    return f"paperless-{document_id}{extension}", mime


def ingest_paperless_document(
    paperless_document_id: str,
    *,
    store: DocumentStore | None = None,
    user=None,
) -> PaperlessIngestResult:
    document_id = str(paperless_document_id).strip()
    if not document_id:
        return PaperlessIngestResult(
            None, error="Missing Paperless document id", error_code="bad_request"
        )

    existing = Document.objects.filter(paperless_document_id=document_id).first()
    if existing is not None:
        return PaperlessIngestResult(existing, duplicate=True)

    owns_store = store is None
    store = store or build_document_store()
    try:
        try:
            metadata = store.get_document_metadata(document_id)
            filename, declared_type = _filename_for(metadata, document_id)
            data = store.download_original(document_id)
        except PaperlessError as exc:
            return PaperlessIngestResult(None, error=str(exc), error_code="paperless_error")

        # Paperless archives image originals as PDF; trust the bytes, not the name.
        sniffed = sniffed_type(data)
        if sniffed and sniffed != declared_type:
            declared_type = sniffed
            filename = effective_name(filename, sniffed, _EXTENSION_BY_MIME)

        try:
            validated = validate_upload(data, filename, declared_type)
        except IntakeValidationError as exc:
            return PaperlessIngestResult(None, error=exc.message, error_code=exc.code)

        fingerprint = fingerprint_bytes(validated.data)
        by_fingerprint = Document.objects.filter(fingerprint=fingerprint).first()
        if by_fingerprint is not None:
            return PaperlessIngestResult(by_fingerprint, duplicate=True)

        with transaction.atomic():
            document = Document.objects.create(
                fingerprint=fingerprint,
                original_filename=validated.filename,
                content_type=validated.content_type,
                size_bytes=len(validated.data),
                page_count=validated.page_count,
                paperless_document_id=document_id,
                processing_state=Document.ProcessingState.STORED,
                uploaded_by=user,
            )
    finally:
        if owns_store:
            store.close()

    notify_processing(document)
    return PaperlessIngestResult(document)
