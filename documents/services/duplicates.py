"""Semantic duplicate detection for certificates.

Byte-level fingerprints only catch identical files; the same certificate
re-downloaded or re-exported arrives with different bytes. Once a certificate
is classified we can compare identity signals: certificate code first, then
student + exam/date corroboration when no code is available.
"""

from __future__ import annotations

from documents.models import Certificate
from documents.services.review_reasons import merge_review_reasons

DUPLICATE_REASON = "possible_duplicate"

# Certificates in these states still occupy the identity; rejected ones do not.
_LIVE_STATUSES = (
    Certificate.ReviewStatus.PENDING,
    Certificate.ReviewStatus.VALIDATED,
    Certificate.ReviewStatus.APPROVED,
)

# Reason codes owned by duplicate detection when refreshing flags outside the
# classification stage (e.g. after a manual edit).
_OWNED = {DUPLICATE_REASON}


def _compact(value: str | None) -> str:
    """Normalized alphanumeric key for codes and names.

    Punctuation and spacing are dropped so ``ABC-123`` matches ``abc 123``.
    """
    from catalog.normalization import normalize_catalog_text

    return "".join(ch for ch in normalize_catalog_text(value or "") if ch.isalnum())


def _identity_corroborates(cert: Certificate, other: Certificate) -> bool:
    """True when two code-less certificates plausibly describe the same one.

    Requires no contradiction on exam and at least one shared signal among
    exam, issue date or exam date. Name+entity alone is too weak (siblings,
    namesakes).
    """
    if cert.exam_id and other.exam_id and cert.exam_id != other.exam_id:
        return False
    shared = False
    if cert.exam_id and cert.exam_id == other.exam_id:
        shared = True
    for field in ("issue_date", "exam_date", "result_date"):
        mine = getattr(cert, field, None)
        theirs = getattr(other, field, None)
        if mine and theirs:
            if mine == theirs:
                shared = True
            else:
                return False
    return shared


def find_duplicate_certificate(certificate: Certificate) -> Certificate | None:
    """Return the live certificate this one duplicates, or None.

    Code match wins when both sides carry a code. Without a code on this
    certificate, falls back to entity + student name + corroborating
    exam/date signals.
    """
    if certificate.entity_id is None or certificate.pk is None:
        return None
    others = (
        Certificate.objects.filter(entity_id=certificate.entity_id)
        .exclude(pk=certificate.pk)
        .exclude(review_status=Certificate.ReviewStatus.REJECTED)
        .select_related("document")
    )
    code = _compact(certificate.certificate_code)
    if code:
        for other in others:
            if _compact(other.certificate_code) == code:
                return other
        return None

    name = _compact(certificate.student_name)
    if not name:
        return None
    for other in others:
        if _compact(other.student_name) != name:
            continue
        if _identity_corroborates(certificate, other):
            return other
    return None


def refresh_duplicate_flag(certificate: Certificate) -> Certificate | None:
    """Recompute ``duplicate_of`` and the ``possible_duplicate`` reason.

    Returns the matching certificate when found. Safe to call after manual
    edits; updates both certificate and document reason lists.
    """
    other = find_duplicate_certificate(certificate)
    certificate.duplicate_of = other
    fields = ["duplicate_of", "updated_at"]

    cert_reasons = merge_review_reasons(
        certificate.review_reasons, [DUPLICATE_REASON] if other else [], _OWNED
    )
    if cert_reasons != (certificate.review_reasons or []):
        certificate.review_reasons = cert_reasons
        fields.append("review_reasons")
    certificate.save(update_fields=fields)

    document = certificate.document
    doc_reasons = merge_review_reasons(
        document.review_reasons, [DUPLICATE_REASON] if other else [], _OWNED
    )
    if doc_reasons != (document.review_reasons or []):
        document.review_reasons = doc_reasons
        document.save(update_fields=["review_reasons", "updated_at"])
    return other
