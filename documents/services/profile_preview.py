"""Anonymized template preview for learned format profiles.

Renders the first page of an approved sample certificate and redacts the
student name (and NPA when present) so reviewers can verify the learned
template without exposing personal data. Returns ``None`` whenever a safe
preview cannot be produced — callers must never serve unredacted content.
"""

from __future__ import annotations

import logging

from catalog.models import FormatProfile
from documents.models import Certificate
from documents.services.format_profile import LEARNED_REVIEW_STATUSES, certificate_year
from documents.services.paperless import PaperlessError, build_document_store

logger = logging.getLogger(__name__)

_PREVIEW_DPI = 110


def _sample_certificate(profile: FormatProfile) -> Certificate | None:
    """Most recent approved/validated cert matching the profile's cohort."""
    qs = (
        Certificate.objects.filter(
            entity_id=profile.entity_id,
            review_status__in=LEARNED_REVIEW_STATUSES,
        )
        .select_related("document")
        .order_by("-updated_at")
    )
    if profile.exam_id is not None:
        qs = qs.filter(exam_id=profile.exam_id)
    if profile.year is not None:
        candidates = [c for c in qs if certificate_year(c) == profile.year]
    else:
        candidates = list(qs)
    return candidates[0] if candidates else None


def _open_document(data: bytes, content_type: str):
    """Open bytes with fitz; supports PDFs and common raster images."""
    import fitz

    filetype = "pdf" if "pdf" in (content_type or "") else None
    try:
        return fitz.open(stream=data, filetype=filetype)
    except Exception:
        if filetype is None:
            raise
        return fitz.open(stream=data)


def render_profile_preview(profile: FormatProfile) -> bytes | None:
    """PNG bytes of the cohort sample with personal data redacted, or None."""
    certificate = _sample_certificate(profile)
    if certificate is None:
        return None
    document = certificate.document
    if not document.paperless_document_id:
        return None

    store = build_document_store()
    try:
        data = store.download_original(document.paperless_document_id)
    except PaperlessError as exc:
        logger.warning("Profile preview: original unavailable: %s", exc)
        return None
    finally:
        store.close()

    try:
        import importlib.util

        if importlib.util.find_spec("fitz") is None:
            logger.warning("Profile preview: PyMuPDF not installed")
            return None
    except ImportError:
        logger.warning("Profile preview: PyMuPDF not installed")
        return None

    pdf = None
    try:
        pdf = _open_document(data, document.content_type)
        if pdf.page_count == 0:
            return None
        page = pdf[0]

        redaction_terms = [
            term for term in {certificate.student_name, document.npa} if term and str(term).strip()
        ]
        applied = 0
        for term in redaction_terms:
            for rect in page.search_for(str(term).strip()):
                page.add_redact_annot(rect, fill=(0, 0, 0))
                applied += 1
        # A named student whose name cannot be located means we cannot prove
        # the preview is anonymized (e.g. name rendered inside an image):
        # refuse rather than risk exposing identity.
        if certificate.student_name and certificate.student_name.strip() and applied == 0:
            return None
        if applied:
            page.apply_redactions()

        pixmap = page.get_pixmap(dpi=_PREVIEW_DPI)
        return pixmap.tobytes("png")
    except Exception:
        logger.exception("Profile preview rendering failed for profile %s", profile.pk)
        return None
    finally:
        if pdf is not None:
            pdf.close()
