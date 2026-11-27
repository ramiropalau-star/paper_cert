"""Service-to-service internal pipeline endpoints."""

import json
import logging

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.internal import internal_token_required
from documents.models import Document
from documents.services.classification import classify_certificate
from documents.services.extraction import extract_certificate
from documents.services.text import acquire_text

logger = logging.getLogger("documents.views")


@csrf_exempt
@require_POST
@internal_token_required
def internal_acquire_text(request, pk: int):
    document = get_object_or_404(Document, pk=pk)
    result = acquire_text(document)
    return JsonResponse(
        {
            "document_id": document.pk,
            "state": document.processing_state,
            "text_method": result.text_method,
            "page_count": result.page_count,
            "review_reasons": list(result.review_reasons),
            "error": result.error,
            "skipped": result.skipped,
        }
    )


@csrf_exempt
@require_POST
@internal_token_required
def internal_extract(request, pk: int):
    document = get_object_or_404(Document, pk=pk)
    result = extract_certificate(document)
    payload = {
        "document_id": document.pk,
        "state": document.processing_state,
        "skipped": result.skipped,
        "refused": result.refused,
        "error": result.error,
        "is_language_certificate": result.is_language_certificate,
        "multiple_certificates_suspected": result.multiple_certificates_suspected,
        "review_reasons": list(result.review_reasons),
    }
    if result.refused:
        return JsonResponse(payload, status=409)
    return JsonResponse(payload)


@csrf_exempt
@require_POST
@internal_token_required
def internal_classify(request, pk: int):
    document = get_object_or_404(Document, pk=pk)
    result = classify_certificate(document)
    payload = {
        "document_id": document.pk,
        "state": document.processing_state,
        "skipped": result.skipped,
        "refused": result.refused,
        "error": result.error,
        "review_reasons": list(result.review_reasons),
    }
    if result.certificate is not None:
        payload["certificate_id"] = result.certificate.pk
        payload["cefr_level"] = result.certificate.cefr_level
        payload["cefr_source"] = result.certificate.cefr_source
        payload["entity_id"] = result.certificate.entity_id
        payload["language_id"] = result.certificate.language_id
        payload["exam_id"] = result.certificate.exam_id
    if result.refused:
        return JsonResponse(payload, status=409)
    return JsonResponse(payload)


def _paperless_document_id(payload) -> str:
    """Extract the Paperless document id from a webhook payload."""
    if not isinstance(payload, dict):
        return ""
    document = payload.get("document")
    if isinstance(document, dict) and document.get("id") is not None:
        return str(document["id"])
    for key in ("document_id", "id"):
        value = payload.get(key)
        if value is not None:
            return str(value)
    return ""


@csrf_exempt
@require_POST
@internal_token_required
def internal_paperless_webhook(request):
    """Receive Paperless-ngx ``document added`` webhooks and ingest the file."""
    from documents.services.paperless_ingest import ingest_paperless_document

    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"error": "invalid JSON"}, status=400)

    document_id = _paperless_document_id(payload) or request.GET.get("document_id", "")
    if not document_id:
        return JsonResponse({"error": "missing document id"}, status=400)

    result = ingest_paperless_document(document_id)
    if result.error:
        return JsonResponse(
            {"document_id": document_id, "error": result.error},
            status=502 if result.error_code == "paperless_error" else 422,
        )
    return JsonResponse(
        {
            "document_id": document_id,
            "app_document_id": result.document.pk if result.document else None,
            "duplicate": result.duplicate,
        }
    )
