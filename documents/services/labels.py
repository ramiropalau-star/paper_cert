"""Manual-review label helpers for the Paperless document store."""

from __future__ import annotations

import logging

from django.conf import settings

from documents.models import Document
from documents.services.paperless import (
    DocumentStore,
    PaperlessError,
    build_document_store,
)

logger = logging.getLogger("documents.labels")

LABEL_FAILED_REASON = "manual_label_failed"
LABEL_REASONS = {"manual_label_failed"}


def _append_reason(document: Document, reason: str) -> None:
    reasons = list(document.review_reasons or [])
    if reason not in reasons:
        reasons.append(reason)
        document.review_reasons = reasons
        document.save(update_fields=["review_reasons"])


def _tag_name() -> str:
    return str(settings.APP["paperless_other_tag"])


def apply_manual_review_label(document: Document, *, store: DocumentStore | None = None) -> bool:
    """Apply the configured label without blocking processing on failure."""

    if not document.paperless_document_id:
        return False
    owns_store = store is None
    selected = store or build_document_store()
    try:
        return selected.add_tag(document.paperless_document_id, _tag_name())
    except PaperlessError as exc:
        logger.warning(
            "manual_review_label_failed",
            extra={"document_id": document.pk, "outcome": "failed", "error": str(exc)},
        )
        _append_reason(document, LABEL_FAILED_REASON)
        return False
    finally:
        if owns_store:
            selected.close()


def remove_manual_review_label(document: Document, *, store: DocumentStore | None = None) -> bool:
    """Remove the configured label; failures are recorded but do not block review."""

    if not document.paperless_document_id:
        return False
    owns_store = store is None
    selected = store or build_document_store()
    try:
        return selected.remove_tag(document.paperless_document_id, _tag_name())
    except PaperlessError as exc:
        logger.warning(
            "manual_review_label_remove_failed",
            extra={"document_id": document.pk, "outcome": "failed", "error": str(exc)},
        )
        _append_reason(document, LABEL_FAILED_REASON)
        return False
    finally:
        if owns_store:
            selected.close()


TAG_PREFIXES = ("Idioma: ", "Nivel: ", "Entidad: ", "Examen: ", "Equivalencia UV L2: ")


def _desired_classification_tags(certificate) -> set[str]:
    tags: set[str] = set()
    if certificate is None:
        return tags
    language = (
        certificate.language.name if certificate.language_id else certificate.language_literal
    )
    if language:
        tags.add(f"Idioma: {language}")
    level = certificate.cefr_level or certificate.level_literal
    if level:
        tags.add(f"Nivel: {level}")
    entity = certificate.entity.name if certificate.entity_id else certificate.entity_literal
    if entity:
        tags.add(f"Entidad: {entity}")
    exam = certificate.exam.name if certificate.exam_id else certificate.exam_literal
    if exam:
        tags.add(f"Examen: {exam}")
    if certificate.equivalence:
        tags.add(f"Equivalencia UV L2: {certificate.equivalence}")
    return tags


def sync_classification_tags(document: Document, *, store: DocumentStore | None = None) -> bool:
    """Reconcile Paperless tags with the classified certificate values.

    Only tags under ``TAG_PREFIXES`` are managed; other tags are untouched.
    Failures are logged and never block processing.
    """
    if not document.paperless_document_id:
        return False
    certificate = getattr(document, "certificate", None)
    desired = _desired_classification_tags(certificate)
    owns_store = store is None
    selected = store or build_document_store()
    try:
        current = set(selected.document_tag_names(document.paperless_document_id))
        managed = {tag for tag in current if tag.startswith(TAG_PREFIXES)}
        for tag in managed - desired:
            selected.remove_tag(document.paperless_document_id, tag)
        for tag in desired - managed:
            selected.add_tag(document.paperless_document_id, tag)
        return True
    except Exception as exc:  # tag sync is best-effort; never block processing
        logger.warning(
            "classification_tags_sync_failed",
            extra={"document_id": document.pk, "outcome": "failed", "error": str(exc)},
        )
        return False
    finally:
        if owns_store:
            selected.close()
