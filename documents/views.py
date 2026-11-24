"""Upload, review, and internal pipeline views for documents."""

import mimetypes
from datetime import date
from urllib.parse import urlencode

import magic
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from catalog.models import Entity, Equivalence, Exam, Language
from core.internal import internal_token_required
from core.permissions import (
    ROLE_ADMIN,
    ROLE_REVIEWER,
    ROLE_VIEWER,
    can_delete_documents,
    can_review_documents,
    role_required,
)
from documents.forms import CertificateEditForm
from documents.models import Document, ReviewEvent
from documents.services.classification import (
    classify_certificate,
    equivalence_tooltip,
    matching_equivalence,
)
from documents.services.extraction import extract_certificate
from documents.services.intake import process_upload
from documents.services.paperless import PaperlessError, build_document_store
from documents.services.review import (
    FIELD_LABELS,
    apply_manual_edit,
    approve_certificate,
    reject_certificate,
    release_manual_field,
    reprocess_document,
    validate_certificate,
)
from documents.services.text import acquire_text


@login_required
@role_required(ROLE_VIEWER)
@require_http_methods(["GET", "POST"])
def upload(request):
    if request.method == "POST":
        uploads = request.FILES.getlist("document")
        if not uploads:
            messages.error(request, "Seleccioná al menos un archivo para subir.")
            return redirect("documents:upload")

        stored = duplicates = 0
        for uploaded in uploads:
            declared_type = (
                uploaded.content_type
                or mimetypes.guess_type(uploaded.name)[0]
                or "application/octet-stream"
            )
            result = process_upload(
                uploaded.read(),
                uploaded.name,
                declared_type,
                user=request.user,
            )
            if result.error:
                messages.error(request, f"{uploaded.name}: {result.error}")
            elif result.duplicate:
                duplicates += 1
            else:
                stored += 1
        if stored:
            messages.success(
                request, f"{stored} archivo(s) almacenado(s) y en cola de procesamiento."
            )
        if duplicates:
            messages.info(request, f"{duplicates} archivo(s) ya estaban procesados.")
        return redirect("documents:upload")

    return render(request, "documents/upload.html")


@login_required
@role_required(ROLE_ADMIN)
@require_http_methods(["GET", "POST"])
def delete(request, pk: int):
    document = get_object_or_404(Document, pk=pk)
    if request.method == "GET":
        return render(request, "documents/delete.html", {"document": document})

    if document.paperless_document_id:
        store = build_document_store()
        try:
            store.delete_document(document.paperless_document_id)
        except PaperlessError as exc:
            messages.error(
                request,
                f"No se pudo eliminar el original en Paperless: {exc}",
            )
            return redirect("documents:delete", pk=document.pk)
        finally:
            store.close()

    document.delete()
    messages.success(request, "Documento y datos asociados eliminados.")
    return redirect("home")


@login_required
@role_required(ROLE_ADMIN)
@require_http_methods(["GET", "POST"])
def delete_all(request):
    """Wipe every document: Django records and Paperless originals.

    Paperless originals must go too, otherwise the periodic sync would
    re-ingest them on the next cycle.
    """
    if request.method == "GET":
        return render(
            request,
            "documents/delete_all.html",
            {"count": Document.objects.count()},
        )

    store = build_document_store()
    paperless_deleted = 0
    paperless_errors = []
    try:
        for metadata in store.list_documents():
            remote_id = str(metadata.get("id") or "")
            if not remote_id:
                continue
            try:
                store.delete_document(remote_id)
                paperless_deleted += 1
            except PaperlessError as exc:
                paperless_errors.append(f"#{remote_id}: {exc}")
    except PaperlessError as exc:
        paperless_errors.append(str(exc))
    finally:
        store.close()

    deleted, _ = Document.objects.all().delete()
    if paperless_errors:
        messages.warning(
            request,
            f"Registros Django eliminados ({deleted}), pero {len(paperless_errors)} "
            f"originales de Paperless fallaron: {'; '.join(paperless_errors[:3])}",
        )
    else:
        messages.success(
            request,
            f"Eliminados {deleted} documentos de Django y "
            f"{paperless_deleted} originales de Paperless.",
        )
    return redirect("documents:list")


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


STATE_FILTERS = {
    "pending": [Document.ProcessingState.PENDING_REVIEW.value],
    "approved": [Document.ProcessingState.APPROVED.value],
    "rejected": [Document.ProcessingState.REJECTED.value],
    "error": [Document.ProcessingState.ERROR.value],
    "processed": [
        Document.ProcessingState.RECEIVED.value,
        Document.ProcessingState.STORED.value,
        Document.ProcessingState.TEXT_READY.value,
        Document.ProcessingState.EXTRACTED.value,
        Document.ProcessingState.CLASSIFIED.value,
    ],
}

PAGE_SIZE = 25

PROCESSING_STATES = [
    Document.ProcessingState.RECEIVED.value,
    Document.ProcessingState.STORED.value,
    Document.ProcessingState.TEXT_READY.value,
    Document.ProcessingState.EXTRACTED.value,
    Document.ProcessingState.CLASSIFIED.value,
]


def _filter_documents(request):
    queryset = Document.objects.select_related(
        "certificate",
        "certificate__language",
        "certificate__entity",
        "certificate__exam",
        "uploaded_by",
    ).order_by("-created_at")

    state = request.GET.get("state", "")
    if state in STATE_FILTERS:
        queryset = queryset.filter(processing_state__in=STATE_FILTERS[state])

    query = (request.GET.get("q") or "").strip()
    if query:
        queryset = queryset.filter(
            Q(original_filename__icontains=query) | Q(certificate__student_name__icontains=query)
        )

    language = (request.GET.get("language") or "").strip()
    if language:
        queryset = queryset.filter(
            Q(certificate__language_id=language)
            | Q(certificate__language_literal__icontains=language)
        )

    entity = (request.GET.get("entity") or "").strip()
    if entity:
        queryset = queryset.filter(
            Q(certificate__entity_id=entity) | Q(certificate__entity_literal__icontains=entity)
        )

    organism = (request.GET.get("organism") or "").strip()
    if organism:
        queryset = queryset.filter(certificate__issuing_body_literal__icontains=organism)

    level = (request.GET.get("level") or "").strip()
    if level:
        queryset = queryset.filter(
            Q(certificate__cefr_level__iexact=level)
            | Q(certificate__level_literal__icontains=level)
        )

    issue_date_raw = (request.GET.get("issue_date") or "").strip()
    if issue_date_raw:
        try:
            issue_date = date.fromisoformat(issue_date_raw)
        except ValueError:
            issue_date = None
        if issue_date is not None:
            queryset = queryset.filter(certificate__issue_date=issue_date)

    return queryset


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
    queryset = _filter_documents(request)
    page = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))

    certificates = [
        document.certificate
        for document in page
        if getattr(document, "certificate", None) is not None
    ]
    _attach_equivalence_info(certificates)

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
    queryset = _filter_documents(request).filter(certificate__isnull=False)
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
            "languages": Language.objects.filter(is_active=True),
            "entities": Entity.objects.filter(is_active=True),
        },
    )


@login_required
@role_required(ROLE_REVIEWER)
@require_POST
def bulk_review(request):
    """Apply validate/approve to a set of documents selected in the gallery."""
    action = request.POST.get("action", "")
    pks = request.POST.getlist("documents")
    if action not in {"validate", "approve"} or not pks:
        messages.error(request, "Seleccioná al menos un documento y una acción.")
        return redirect("documents:gallery")

    documents = (
        Document.objects.filter(pk__in=pks)
        .select_related("certificate__language", "certificate__entity", "certificate__exam")
    )
    succeeded = failed = 0
    errors: list[str] = []
    for document in documents:
        certificate = getattr(document, "certificate", None)
        if certificate is None:
            failed += 1
            errors.append(f"{document.original_filename}: sin certificado")
            continue
        if action == "validate":
            outcome = validate_certificate(certificate, request.user)
        else:
            outcome = approve_certificate(certificate, request.user)
        if outcome.ok:
            succeeded += 1
        else:
            failed += 1
            errors.append(f"{document.original_filename}: {outcome.error}")

    verb = "validados" if action == "validate" else "aprobados"
    if succeeded:
        messages.success(request, f"{succeeded} documento(s) {verb}.")
    if failed:
        messages.error(request, f"{failed} no se pudieron procesar: {'; '.join(errors[:3])}")

    params = {
        key: request.POST[key]
        for key in ("state", "q", "language", "entity", "organism", "page")
        if request.POST.get(key)
    }
    url = reverse("documents:gallery")
    if params:
        url += "?" + urlencode(params)
    return redirect(url)


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


def _paperless_url(document: Document) -> str:
    if not document.paperless_document_id:
        return ""
    base = str(settings.APP.get("paperless_ui_url") or settings.APP["paperless_url"]).rstrip("/")
    return f"{base}/documents/{document.paperless_document_id}/"


FIELD_WARNINGS = {
    "unknown_language": ("language_literal", "Idioma no identificado"),
    "unknown_entity": ("entity_literal", "Entidad pendiente de identificar"),
    "ambiguous_date": ("dates", "Fecha ambigua o sin categoría"),
    "low_confidence": ("confidence", "Confianza baja"),
    "missing_essential_fields": ("fields", "Faltan campos obligatorios"),
    "multiple_certificates": ("document", "Posibles múltiples certificados"),
    "non_certificate": ("document", "No parece un certificado de idioma"),
}


@login_required
@role_required(ROLE_VIEWER)
@require_http_methods(["GET"])
def review_detail(request, pk: int):
    document = get_object_or_404(
        Document.objects.select_related(
            "certificate__language",
            "certificate__entity",
            "certificate__exam",
        ),
        pk=pk,
    )
    certificate = getattr(document, "certificate", None)
    form = CertificateEditForm(initial=_edit_initial(certificate))
    can_review = can_review_documents(request.user)
    editing = bool(can_review and certificate is not None and request.GET.get("edit") == "1")

    siblings = Document.objects.order_by("-created_at", "-id")
    previous_document = (
        siblings.filter(created_at__gt=document.created_at)
        .order_by("created_at", "id")
        .first()
    )
    next_document = (
        siblings.filter(created_at__lt=document.created_at)
        .order_by("-created_at", "-id")
        .first()
    )

    warnings: dict[str, str] = {}
    if certificate is not None:
        reasons = list(certificate.review_reasons or []) + list(document.review_reasons or [])
        for reason in dict.fromkeys(reasons):
            mapped = FIELD_WARNINGS.get(reason)
            if mapped:
                warnings[mapped[0]] = mapped[1]
    return render(
        request,
        "documents/detail.html",
        {
            "document": document,
            "certificate": certificate,
            "form": form,
            "warnings": warnings,
            "paperless_url": _paperless_url(document),
            "can_review": can_review,
            "editing": editing,
            "previous_document": previous_document,
            "next_document": next_document,
            "can_delete": can_delete_documents(request.user),
            "manual_field_labels": [
                (field, FIELD_LABELS.get(field, field))
                for field in (certificate.manual_fields if certificate else [])
            ],
        },
    )


def _edit_initial(certificate) -> dict:
    if certificate is None:
        return {}
    return {
        "student_name": certificate.student_name,
        "language_literal": certificate.language_literal,
        "entity_literal": certificate.entity_literal,
        "issuing_body_literal": certificate.issuing_body_literal,
        "test_center_literal": certificate.test_center_literal,
        "exam_literal": certificate.exam_literal,
        "level_literal": certificate.level_literal,
        "score_literal": certificate.score_literal,
        "certificate_code": certificate.certificate_code,
        "cefr_level": certificate.cefr_level,
        "equivalence": certificate.equivalence,
        "issue_date": certificate.issue_date,
        "exam_date": certificate.exam_date,
        "result_date": certificate.result_date,
        "detected_date": certificate.detected_date,
        "language": certificate.language,
        "entity": certificate.entity,
        "exam": certificate.exam,
    }


@login_required
@role_required(ROLE_REVIEWER)
@require_POST
def review_edit(request, pk: int):
    document = get_object_or_404(Document, pk=pk)
    certificate = getattr(document, "certificate", None)
    if certificate is None:
        messages.error(request, "El documento no tiene datos para editar.")
        return redirect("documents:list")
    form = CertificateEditForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Revisá los campos: hay valores inválidos.")
        return redirect("documents:detail", pk=document.pk)
    outcome = apply_manual_edit(certificate, form.to_certificate_values(), request.user)
    if outcome.ok:
        messages.success(request, "Cambios guardados.")
    else:
        messages.error(request, outcome.error)
    return redirect("documents:detail", pk=document.pk)


@login_required
@role_required(ROLE_REVIEWER)
@require_POST
def review_approve(request, pk: int):
    document = get_object_or_404(Document, pk=pk)
    certificate = getattr(document, "certificate", None)
    if certificate is None:
        messages.error(request, "El documento no tiene certificado.")
        return redirect("documents:list")
    outcome = approve_certificate(certificate, request.user)
    if outcome.ok:
        messages.success(request, "Registro aprobado.")
    else:
        messages.error(request, outcome.error)
    return redirect("documents:detail", pk=document.pk)


@login_required
@role_required(ROLE_REVIEWER)
@require_POST
def review_validate(request, pk: int):
    document = get_object_or_404(Document, pk=pk)
    certificate = getattr(document, "certificate", None)
    if certificate is None:
        messages.error(request, "El documento no tiene certificado.")
        return redirect("documents:list")
    outcome = validate_certificate(certificate, request.user)
    if outcome.ok:
        messages.success(request, "Registro validado manualmente.")
    else:
        messages.error(request, outcome.error)
    return redirect("documents:detail", pk=document.pk)


@login_required
@role_required(ROLE_REVIEWER)
@require_POST
def review_reject(request, pk: int):
    document = get_object_or_404(Document, pk=pk)
    certificate = getattr(document, "certificate", None)
    if certificate is None:
        messages.error(request, "El documento no tiene certificado.")
        return redirect("documents:list")
    outcome = reject_certificate(certificate, request.user, request.POST.get("reason", ""))
    if outcome.ok:
        messages.success(request, "Registro rechazado.")
    else:
        messages.error(request, outcome.error)
    return redirect("documents:detail", pk=document.pk)


@login_required
@role_required(ROLE_REVIEWER)
@require_POST
def review_release_field(request, pk: int):
    document = get_object_or_404(Document, pk=pk)
    certificate = getattr(document, "certificate", None)
    if certificate is None:
        messages.error(request, "El documento no tiene certificado.")
        return redirect("documents:list")
    outcome = release_manual_field(certificate, request.user, request.POST.get("field", ""))
    if outcome.ok:
        messages.success(request, "Campo liberado: volverá a extraerse al reprocesar.")
    else:
        messages.error(request, outcome.error)
    return redirect("documents:detail", pk=document.pk)


@login_required
@role_required(ROLE_REVIEWER)
@require_POST
def review_reprocess(request, pk: int):
    document = get_object_or_404(Document, pk=pk)
    outcome = reprocess_document(document, request.user)
    if outcome.ok:
        messages.success(request, "Documento encolado para reprocesamiento.")
    else:
        messages.error(request, outcome.error)
    return redirect("documents:detail", pk=document.pk)


@login_required
@role_required(ROLE_VIEWER)
@require_http_methods(["GET"])
def review_history(request, pk: int):
    document = get_object_or_404(Document, pk=pk)
    certificate = getattr(document, "certificate", None)
    events = (
        certificate.events.select_related("actor").all()
        if certificate is not None
        else ReviewEvent.objects.none()
    )
    return render(
        request,
        "documents/history.html",
        {"document": document, "certificate": certificate, "events": events},
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


@login_required
@role_required(ROLE_VIEWER)
@require_http_methods(["GET"])
def document_thumbnail(request, pk: int):
    """Stream the Paperless thumbnail (always an image) for gallery cards."""
    document = get_object_or_404(Document, pk=pk)
    if not document.paperless_document_id:
        raise Http404("El documento no tiene original en Paperless.")
    store = build_document_store()
    try:
        data = store.download_thumbnail(document.paperless_document_id)
    except PaperlessError as exc:
        raise Http404("No se pudo descargar la miniatura.") from exc
    content_type = (
        magic.from_buffer(data, mime=True) or "application/octet-stream"
    )
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = 'inline; filename="thumbnail"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


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
    import json

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
