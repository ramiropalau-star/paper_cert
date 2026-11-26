"""Single state-transition policy for documents and certificates.

All pipeline stages, review actions, and recovery go through these helpers so
an illegal move is refused before anything is persisted. Transitions that leave
the recoverable processing states reset the recovery bookkeeping.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from documents.models import Certificate, Document


class StateTransitionError(Exception):
    """Raised when a requested state change is not allowed."""


S = Document.ProcessingState

DOCUMENT_TRANSITIONS: dict[str, set[str]] = {
    S.RECEIVED: {S.STORED, S.ERROR},
    S.STORED: {S.TEXT_READY, S.PENDING_REVIEW, S.ERROR},
    S.TEXT_READY: {S.EXTRACTED, S.PENDING_REVIEW, S.ERROR},
    S.EXTRACTED: {S.PENDING_REVIEW, S.ERROR},
    S.PENDING_REVIEW: {S.APPROVED, S.REJECTED},
    S.APPROVED: {S.REJECTED},
    S.REJECTED: set(),
    S.ERROR: set(),
}

RECOVERABLE_STATES = {S.STORED, S.TEXT_READY, S.EXTRACTED}

REPROCESSABLE_DOCUMENT_STATES = {
    S.PENDING_REVIEW,
    S.APPROVED,
    S.REJECTED,
    S.ERROR,
}

R = Certificate.ReviewStatus

CERTIFICATE_TRANSITIONS: dict[str, set[str]] = {
    R.PENDING: {R.VALIDATED, R.APPROVED, R.REJECTED},
    R.VALIDATED: {R.APPROVED, R.REJECTED},
    R.APPROVED: {R.REJECTED},
    R.REJECTED: set(),
}


def document_transition_allowed(current: str, target: str) -> bool:
    if current == target:
        return True
    return target in DOCUMENT_TRANSITIONS.get(current, set())


def certificate_transition_allowed(current: str, target: str) -> bool:
    if current == target:
        return True
    return target in CERTIFICATE_TRANSITIONS.get(current, set())


def transition_document(
    document: Document,
    new_state: str,
    *,
    fields: dict[str, Any] | None = None,
    reprocess: bool = False,
) -> Document:
    """Move ``document`` to ``new_state`` after validating the transition.

    ``fields`` carries extra column values to persist in the same save
    (``error_reason``, ``review_reasons``, ``text_method``, ...). Leaving a
    recoverable state resets ``recovery_attempts``. ``reprocess=True`` allows
    the reprocess-only move back to ``stored``.
    """
    current = document.processing_state
    allowed = document_transition_allowed(current, new_state)
    if not allowed and reprocess and new_state == S.STORED:
        allowed = current in REPROCESSABLE_DOCUMENT_STATES or current == S.STORED
    if not allowed:
        raise StateTransitionError(f"Illegal document transition: {current} -> {new_state}")

    extra = dict(fields or {})
    for name, value in extra.items():
        setattr(document, name, value)
    document.processing_state = new_state

    update_fields = ["processing_state", "updated_at", *extra.keys()]
    if current != new_state and (
        new_state == S.PENDING_REVIEW or (new_state == S.ERROR and hasattr(document, "certificate"))
    ):
        document.processed_at = timezone.now()
        if "processed_at" not in update_fields:
            update_fields.append("processed_at")
    if current in RECOVERABLE_STATES and new_state not in RECOVERABLE_STATES:
        document.recovery_attempts = 0
        if "recovery_attempts" not in update_fields:
            update_fields.append("recovery_attempts")
    document.save(update_fields=update_fields)
    return document


def transition_certificate(
    certificate: Certificate,
    new_status: str,
    *,
    reprocess: bool = False,
) -> Certificate:
    """Move ``certificate`` to ``new_status`` after validating the transition.

    ``reprocess=True`` permits the reset to ``pending`` from any status,
    including terminal ``rejected``.
    """
    current = certificate.review_status
    allowed = certificate_transition_allowed(current, new_status)
    if not allowed and reprocess and new_status == R.PENDING:
        allowed = True
    if not allowed:
        raise StateTransitionError(f"Illegal certificate transition: {current} -> {new_status}")
    certificate.review_status = new_status
    certificate.save(update_fields=["review_status", "updated_at"])
    return certificate
