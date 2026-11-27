"""Review workflow views: detail, edit, approve/reject, reprocess, verify."""

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from core.permissions import (
    ROLE_REVIEWER,
    ROLE_VIEWER,
    can_delete_documents,
    can_review_documents,
    role_required,
)
from documents.forms import CertificateEditForm
from documents.models import Certificate, Document, ReviewEvent
from documents.review_display import confidence_display, review_reason_items
from documents.services.catalog_resolution import unresolved_catalog_fields
from documents.services.classification import classify_certificate
from documents.services.extraction import extract_certificate
from documents.services.field_aliases import teach_alias as teach_field_alias
from documents.services.review import (
    FIELD_LABELS,
    apply_manual_edit,
    approve_certificate,
    reject_certificate,
    release_manual_field,
    reprocess_document,
    validate_certificate,
)
from documents.services.state import (
    StateTransitionError,
    transition_certificate,
    transition_document,
)
from documents.services.verifiers import verify_at_source

logger = logging.getLogger("documents.views")

FIELD_WARNINGS = {
    "unknown_language": ("language_literal", "Idioma no identificado"),
    "unknown_entity": ("entity_literal", "Entidad pendiente de identificar"),
    "ambiguous_date": ("dates", "Fecha ambigua o sin categoría"),
    "low_confidence": ("confidence", "Confianza baja"),
    "missing_essential_fields": ("fields", "Faltan campos obligatorios"),
    "multiple_certificates": ("document", "Posibles múltiples certificados"),
    "non_certificate": ("document", "No parece un certificado de idioma"),
}


def _paperless_url(document: Document) -> str:
    if not document.paperless_document_id:
        return ""
    base = str(settings.APP.get("paperless_ui_url") or "").rstrip("/")
    if not base:
        return ""
    return f"{base}/documents/{document.paperless_document_id}/"


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
        siblings.filter(created_at__gt=document.created_at).order_by("created_at", "id").first()
    )
    next_document = (
        siblings.filter(created_at__lt=document.created_at).order_by("-created_at", "-id").first()
    )

    warnings: dict[str, str] = {}
    reason_items: list[dict] = []
    confidence = None
    if certificate is not None:
        reasons = list(certificate.review_reasons or []) + list(document.review_reasons or [])
        reason_items = review_reason_items(reasons)
        confidence = confidence_display(certificate.confidence)
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
            "reason_items": reason_items,
            "confidence": confidence,
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
            "unresolved_catalog": unresolved_catalog_fields(certificate),
            "unverified_labels": [
                (field, FIELD_LABELS.get(field, field))
                for field in (certificate.unverified_fields if certificate else [])
            ],
            "reextract_diff": request.session.pop(f"reextract_diff_{document.pk}", None),
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
    if request.POST.get("confirm_reprocess") != "on":
        messages.error(request, "Confirmá el reprocesamiento para continuar.")
        return redirect("documents:detail", pk=document.pk)
    outcome = reprocess_document(document, request.user)
    if outcome.ok:
        messages.success(request, "Documento encolado para reprocesamiento.")
    else:
        messages.error(request, outcome.error)
    return redirect("documents:detail", pk=document.pk)


# Certificate attributes compared before/after a re-extract for the diff.
REEXTRACT_DIFF_FIELDS = (
    "student_name",
    "language_literal",
    "entity_literal",
    "issuing_body_literal",
    "test_center_literal",
    "exam_literal",
    "level_literal",
    "score_literal",
    "certificate_code",
    "issue_date",
    "exam_date",
    "result_date",
    "detected_date",
)


@login_required
@role_required(ROLE_REVIEWER)
@require_POST
def review_teach_alias(request, pk: int):
    """Teach a field-label alias from the review screen, then offer re-extract."""
    document = get_object_or_404(Document, pk=pk)
    certificate = getattr(document, "certificate", None)
    field = request.POST.get("field", "")
    alias = request.POST.get("alias", "")
    scope_entity = None
    if request.POST.get("scope") == "entity" and certificate is not None:
        scope_entity = certificate.entity
    created, message = teach_field_alias(
        field=field, alias=alias, actor=request.user, scope_entity=scope_entity
    )
    if created is None:
        messages.error(request, message)
    else:
        messages.success(
            request,
            f"{message} Para probarlo, usá «Re-extraer» en este documento.",
        )
    return redirect("documents:detail", pk=document.pk)


@login_required
@role_required(ROLE_REVIEWER)
@require_POST
def review_verify_source(request, pk: int):
    """Confirm or unconfirm source verification after checking the issuer portal."""
    document = get_object_or_404(Document, pk=pk)
    certificate = getattr(document, "certificate", None)
    if certificate is None:
        messages.error(request, "El documento no tiene certificado.")
        return redirect("documents:detail", pk=document.pk)

    action = request.POST.get("action", "")
    before_status = certificate.verification_status
    status_enum = Certificate.VerificationStatus
    if action == "confirm":
        certificate.verification_status = status_enum.MANUALLY_CONFIRMED
        certificate.verified_by = request.user
        certificate.verified_at = timezone.now()
    elif action == "unconfirm":
        has_artifacts = bool(certificate.verification_code or certificate.verification_url)
        certificate.verification_status = (
            status_enum.SELF_REPORTED if has_artifacts else status_enum.NONE
        )
        certificate.verified_by = None
        certificate.verified_at = None
    else:
        messages.error(request, "Acción de verificación inválida.")
        return redirect("documents:detail", pk=document.pk)

    with transaction.atomic():
        certificate.save(
            update_fields=[
                "verification_status",
                "verified_by",
                "verified_at",
                "updated_at",
            ]
        )
        ReviewEvent.objects.create(
            certificate=certificate,
            event_type=ReviewEvent.EventType.VERIFY,
            actor=request.user,
            reason=request.POST.get("reason", ""),
            before={"verification_status": before_status},
            after={
                "verification_status": certificate.verification_status,
                "action": action,
            },
        )
    messages.success(request, "Verificación en origen actualizada.")
    return redirect("documents:detail", pk=document.pk)


@login_required
@role_required(ROLE_REVIEWER)
@require_POST
def review_verify_now(request, pk: int):
    """Run the automated source check on demand for this certificate."""
    document = get_object_or_404(Document, pk=pk)
    certificate = getattr(document, "certificate", None)
    if certificate is None:
        messages.error(request, "El documento no tiene certificado.")
        return redirect("documents:detail", pk=document.pk)
    if not certificate.verification_url:
        messages.error(request, "Sin URL de verificación; confirma manualmente en el portal.")
        return redirect("documents:detail", pk=document.pk)

    before = certificate.verification_status
    verify_at_source(certificate)
    certificate.refresh_from_db()
    auto = (certificate.verification_evidence or {}).get("auto_check") or {}
    if certificate.verification_status == Certificate.VerificationStatus.VERIFIED_AT_SOURCE:
        messages.success(request, "Verificado en origen automáticamente.")
    elif auto.get("detail") == "missing_document_id":
        messages.error(
            request,
            "Falta el identificador del documento; re-extrae o confirma manualmente.",
        )
    elif auto:
        messages.error(
            request,
            f"El origen no confirmó el documento ({auto.get('detail', 'sin detalle')}).",
        )
    elif before == certificate.verification_status:
        messages.error(
            request, "Este emisor no tiene verificador automático; confirma manualmente."
        )
    return redirect("documents:detail", pk=document.pk)


@login_required
@role_required(ROLE_REVIEWER)
@require_POST
def review_reextract(request, pk: int):
    """Re-run extraction + classification directly, bypassing the n8n webhook."""
    document = get_object_or_404(Document, pk=pk)
    certificate = getattr(document, "certificate", None)
    before_state = document.processing_state
    before_values = (
        {name: getattr(certificate, name) for name in REEXTRACT_DIFF_FIELDS}
        if certificate is not None
        else {}
    )
    try:
        with transaction.atomic():
            transition_document(
                document,
                Document.ProcessingState.STORED,
                fields={"error_reason": ""},
                reprocess=True,
            )
            if certificate is not None:
                transition_certificate(
                    certificate, Certificate.ReviewStatus.PENDING, reprocess=True
                )
            if certificate is not None:
                ReviewEvent.objects.create(
                    certificate=certificate,
                    event_type=ReviewEvent.EventType.REEXTRACT,
                    actor=request.user,
                    before={"processing_state": before_state},
                    after={"processing_state": Document.ProcessingState.STORED},
                )
    except StateTransitionError:
        messages.error(request, "No se permite re-extraer un documento en este estado.")
        return redirect("documents:detail", pk=document.pk)

    transition_document(document, Document.ProcessingState.TEXT_READY)
    extract_result = extract_certificate(document)
    document.refresh_from_db()
    if document.processing_state == Document.ProcessingState.EXTRACTED:
        classify_certificate(document)
        document.refresh_from_db()
    certificate = getattr(document, "certificate", None)
    if certificate is not None and before_values:
        changes = [
            {
                "field": name,
                "label": FIELD_LABELS.get(name, name),
                "before": str(before_values.get(name) or "—"),
                "after": str(getattr(certificate, name) or "—"),
            }
            for name in REEXTRACT_DIFF_FIELDS
            if str(before_values.get(name) or "") != str(getattr(certificate, name) or "")
        ]
        if changes:
            request.session[f"reextract_diff_{document.pk}"] = changes
    if extract_result.error:
        messages.error(request, f"Re-extracción falló: {extract_result.error}")
    else:
        messages.success(request, "Documento re-extraído.")
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
@role_required(ROLE_REVIEWER)
@require_POST
def bulk_review(request):
    """Apply validate/approve to a set of documents selected in the gallery."""
    action = request.POST.get("action", "")
    pks = request.POST.getlist("documents")
    if action not in {"validate", "approve"} or not pks:
        messages.error(request, "Seleccioná al menos un documento y una acción.")
        return redirect("documents:gallery")

    documents = Document.objects.filter(pk__in=pks).select_related(
        "certificate__language", "certificate__entity", "certificate__exam"
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
        for key in ("state", "q", "language", "entity", "organism", "catalog", "page")
        if request.POST.get(key)
    }
    url = reverse("documents:gallery")
    if params:
        url += "?" + urlencode(params)
    return redirect(url)
