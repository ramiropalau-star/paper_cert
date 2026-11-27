"""Read-only document browsing views: list, gallery, queue, originals."""

import logging

import magic
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import BooleanField, Case, Value, When
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from catalog.models import Entity, Equivalence, Exam, Language
from core.permissions import ROLE_VIEWER, can_delete_documents, role_required
from documents.filters import doubtful_format_q, filter_documents
from documents.models import Certificate, Document
from documents.review_display import veracity_band, veracity_display
from documents.services.classification import equivalence_tooltip, matching_equivalence
from documents.services.paperless import PaperlessError, build_document_store

logger = logging.getLogger("documents.views")

PAGE_SIZE = 25

PROCESSING_STATES = [
    Document.ProcessingState.RECEIVED.value,
    Document.ProcessingState.STORED.value,
    Document.ProcessingState.TEXT_READY.value,
    Document.ProcessingState.EXTRACTED.value,
    Document.ProcessingState.CLASSIFIED.value,
]


def _attach_equivalence_info(certificates: list) -> None:
    """Annotate each certificate with its matching UV L2 rule and tooltip."""
    exam_ids = {c.exam_id for c in certificates if c.exam_id}
    rules_by_exam: dict[int, list] = {}
    for rule in (
        Equivalence.objects.filter(exam_id__in=exam_ids, is_active=True)
        .select_related("exam")
        .order_by("score_min")
    ):
        rules_by_exam.setdefault(rule.exam_id, []).append(rule)
    for certificate in certificates:
        rules = rules_by_exam.get(certificate.exam_id, [])
        certificate.equivalence_tip = equivalence_tooltip(certificate, rules)
        rule = matching_equivalence(certificate, rules)
        certificate.equivalence_rule_pk = rule.pk if rule is not None else None


@login_required
@role_required(ROLE_VIEWER)
@require_http_methods(["GET"])
def document_list(request):
    queryset = filter_documents(request.GET).annotate(
        format_doubtful=Case(
            When(doubtful_format_q(), then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        )
    )
    page = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))

    certificates = [
        document.certificate
        for document in page
        if getattr(document, "certificate", None) is not None
    ]
    _attach_equivalence_info(certificates)
    review_ui_enabled = bool(settings.APP.get("review_ui_enabled", True))
    if review_ui_enabled:
        for certificate in certificates:
            certificate.veracity_info = veracity_display(certificate.veracity_score)
            certificate.veracity_band = veracity_band(certificate.veracity_score)

    return render(
        request,
        "documents/list.html",
        {
            "page": page,
            "state": request.GET.get("state", ""),
            "query": request.GET.get("q", ""),
            "language": request.GET.get("language", ""),
            "entity": request.GET.get("entity", ""),
            "level": request.GET.get("level", ""),
            "issue_date": request.GET.get("issue_date", ""),
            "catalog": request.GET.get("catalog", ""),
            "unverified": request.GET.get("unverified", ""),
            "verification": request.GET.get("verification", ""),
            "format": request.GET.get("format", ""),
            "format_threshold": float(settings.APP.get("format_score_threshold", 0.4)),
            "review_ui_enabled": review_ui_enabled,
            "verification_choices": Certificate.VerificationStatus.choices,
            "languages": Language.objects.filter(is_active=True),
            "entities": Entity.objects.filter(is_active=True),
            "exams": Exam.objects.filter(is_active=True),
            "can_delete": can_delete_documents(request.user),
        },
    )


@login_required
@role_required(ROLE_VIEWER)
@require_http_methods(["GET"])
def document_gallery(request):
    """Visual gallery of certificate images with catalog filters."""
    queryset = filter_documents(request.GET).filter(certificate__isnull=False)
    page = Paginator(queryset, 24).get_page(request.GET.get("page"))
    certificates = [
        document.certificate
        for document in page
        if getattr(document, "certificate", None) is not None
    ]
    _attach_equivalence_info(certificates)
    return render(
        request,
        "documents/gallery.html",
        {
            "page": page,
            "state": request.GET.get("state", ""),
            "query": request.GET.get("q", ""),
            "language": request.GET.get("language", ""),
            "entity": request.GET.get("entity", ""),
            "organism": request.GET.get("organism", ""),
            "catalog": request.GET.get("catalog", ""),
            "languages": Language.objects.filter(is_active=True),
            "entities": Entity.objects.filter(is_active=True),
        },
    )


@login_required
@role_required(ROLE_VIEWER)
@require_http_methods(["GET"])
def document_queue(request):
    """Live view of documents currently moving through the pipeline."""
    documents = (
        Document.objects.filter(processing_state__in=PROCESSING_STATES)
        .select_related("certificate", "uploaded_by")
        .order_by("updated_at")
    )
    return render(
        request,
        "documents/queue.html",
        {"documents": documents, "count": documents.count()},
    )


@login_required
@role_required(ROLE_VIEWER)
@require_http_methods(["GET"])
def document_original(request, pk: int):
    """Stream the original file from Paperless for in-app review."""
    document = get_object_or_404(Document, pk=pk)
    if not document.paperless_document_id:
        raise Http404("El documento no tiene original en Paperless.")
    store = build_document_store()
    try:
        data = store.download_original(document.paperless_document_id)
    except PaperlessError as exc:
        raise Http404("No se pudo descargar el original.") from exc
    content_type = (
        magic.from_buffer(data, mime=True) or document.content_type or "application/octet-stream"
    )
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = 'inline; filename="original"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


THUMBNAIL_CACHE_TIMEOUT = 60 * 60 * 24
_THUMBNAIL_PLACEHOLDER_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="260">'
    b'<rect width="200" height="260" fill="#e5e7eb"/>'
    b'<rect x="45" y="45" width="110" height="140" rx="6" fill="#9ca3af"/>'
    b'<text x="100" y="225" font-family="sans-serif" font-size="14" '
    b'fill="#6b7280" text-anchor="middle">Sin vista previa</text>'
    b"</svg>"
)


def _thumbnail_response(data: bytes, content_type: str) -> HttpResponse:
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = 'inline; filename="thumbnail"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@role_required(ROLE_VIEWER)
@require_http_methods(["GET"])
def document_thumbnail(request, pk: int):
    """Stream the Paperless thumbnail (always an image) for gallery cards."""
    document = get_object_or_404(Document, pk=pk)
    if not document.paperless_document_id:
        raise Http404("El documento no tiene original en Paperless.")
    cache_key = f"thumbnail:{document.paperless_document_id}:{document.updated_at.timestamp()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return _thumbnail_response(cached["content"], cached.get("content_type") or "")
    store = build_document_store()
    try:
        data = store.download_thumbnail(document.paperless_document_id)
    except PaperlessError:
        return _thumbnail_response(_THUMBNAIL_PLACEHOLDER_SVG, "image/svg+xml")
    content_type = magic.from_buffer(data, mime=True) or "application/octet-stream"
    cache.set(
        cache_key,
        {"content": data, "content_type": content_type},
        THUMBNAIL_CACHE_TIMEOUT,
    )
    return _thumbnail_response(data, content_type)


@login_required
@role_required(ROLE_VIEWER)
@require_http_methods(["GET"])
def document_status(request, pk: int):
    """Lightweight JSON poll target for the review detail auto-refresh."""
    document = get_object_or_404(Document, pk=pk)
    return JsonResponse(
        {
            "state": document.processing_state,
            "has_certificate": hasattr(document, "certificate"),
        }
    )
