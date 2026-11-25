"""Excel report generation and report-job orchestration."""

from __future__ import annotations

import io
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from documents.models import Certificate, ReviewEvent
from documents.services.classification import parse_date_text
from reports.models import ReportJob

logger = logging.getLogger("reports.services")

MAIN_SHEET = "Certificados"
PENDING_SHEET = "Pendientes de revisión"
REJECTED_SHEET = "Rechazados"

HEADERS = [
    "Alumno",
    "NPA",
    "Idioma",
    "Nivel",
    "Nivel MCER",
    "Equivalencia UV L2",
    "Entidad certificadora",
    "Fecha de expedición",
    "Certificado o examen",
    "Puntuación",
    "Estado",
    "Fecha de procesamiento",
    "Referencia al documento",
    "Nombre del fichero",
    "Código de certificado",
    "Centro de examen",
    "Organismo emisor",
    "Motivo del rechazo",
]

REVIEW_STATUS_LABELS = {
    Certificate.ReviewStatus.APPROVED: "Aprobado",
    Certificate.ReviewStatus.PENDING: "Pendiente de revisión",
    Certificate.ReviewStatus.VALIDATED: "Validado",
    Certificate.ReviewStatus.REJECTED: "Rechazado",
}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _maybe_id(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def certificates_queryset(filters: dict[str, Any], *, status: str) -> QuerySet[Certificate]:
    """Certificates matching the report filters for a review status."""
    queryset = (
        Certificate.objects.select_related("document", "language", "entity", "exam")
        .prefetch_related(
            Prefetch(
                "events",
                queryset=ReviewEvent.objects.filter(
                    event_type=ReviewEvent.EventType.REJECT
                ).order_by("-created_at", "-id"),
                to_attr="reject_events",
            )
        )
        .filter(review_status=status)
    )

    student = _norm(filters.get("student") or filters.get("q"))
    if student:
        queryset = queryset.filter(student_name__icontains=student)

    language = _norm(filters.get("language"))
    if language:
        language_id = _maybe_id(language)
        query = (
            Q(language_literal__icontains=language)
            | Q(language__code__iexact=language)
            | Q(language__name__icontains=language)
        )
        if language_id is not None:
            query |= Q(language_id=language_id)
        queryset = queryset.filter(query)

    entity = _norm(filters.get("entity"))
    if entity:
        entity_id = _maybe_id(entity)
        query = Q(entity_literal__icontains=entity) | Q(entity__name__icontains=entity)
        if entity_id is not None:
            query |= Q(entity_id=entity_id)
        queryset = queryset.filter(query)

    level = _norm(filters.get("level"))
    if level:
        queryset = queryset.filter(Q(cefr_level__iexact=level) | Q(level_literal__icontains=level))

    issue_exact = _norm(filters.get("issue_date"))
    issue_from = _norm(filters.get("issue_date_from"))
    issue_to = _norm(filters.get("issue_date_to"))
    if issue_exact:
        parsed, _ambiguous = parse_date_text(issue_exact)
        if parsed is not None:
            queryset = queryset.filter(issue_date=parsed)
    else:
        parsed, _ = parse_date_text(issue_from)
        if parsed is not None:
            queryset = queryset.filter(issue_date__gte=parsed)
        parsed, _ = parse_date_text(issue_to)
        if parsed is not None:
            queryset = queryset.filter(issue_date__lte=parsed)

    return queryset.order_by("student_name", "id")


def _date_cell(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _reject_reason(certificate: Certificate) -> str:
    events = getattr(certificate, "reject_events", None)
    if events is None:
        event = (
            certificate.events.filter(event_type=ReviewEvent.EventType.REJECT)
            .order_by("-created_at", "-id")
            .first()
        )
        return event.reason if event else ""
    return events[0].reason if events else ""


def _row_values(certificate: Certificate) -> list[Any]:
    document = certificate.document
    status_label = REVIEW_STATUS_LABELS.get(
        certificate.review_status, certificate.get_review_status_display()
    )
    return [
        certificate.student_name,
        document.npa,
        (certificate.language.name if certificate.language_id else certificate.language_literal)
        or "",
        certificate.level_literal,
        certificate.cefr_level,
        certificate.equivalence,
        (certificate.entity.name if certificate.entity_id else certificate.entity_literal) or "",
        _date_cell(certificate.issue_date),
        (certificate.exam.name if certificate.exam_id else certificate.exam_literal) or "",
        certificate.score_literal,
        status_label,
        _date_cell(document.updated_at),
        document.paperless_document_id or str(document.pk),
        document.original_filename,
        certificate.certificate_code,
        certificate.test_center_literal,
        certificate.issuing_body_literal,
        _reject_reason(certificate),
    ]


def build_workbook(
    approved: list[Certificate],
    pending: list[Certificate] | None = None,
    rejected: list[Certificate] | None = None,
) -> bytes:
    """Build the .xlsx workbook in write-only mode."""
    workbook = Workbook(write_only=True)
    last_col = get_column_letter(len(HEADERS))

    def _sheet(name: str, certificates: list[Certificate]):
        sheet = workbook.create_sheet(name)
        sheet.append(HEADERS)
        for certificate in certificates:
            sheet.append(_row_values(certificate))
        sheet.auto_filter.ref = f"A1:{last_col}{len(certificates) + 1}"

    _sheet(MAIN_SHEET, approved)
    if pending is not None:
        _sheet(PENDING_SHEET, pending)
    if rejected:
        _sheet(REJECTED_SHEET, rejected)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _report_dir() -> Path:
    path = Path(str(settings.APP["report_output_dir"]))
    path.mkdir(parents=True, exist_ok=True)
    return path


def generate_report(job: ReportJob) -> ReportJob:
    """Generate the workbook for a queued/running job."""
    filters = job.filters or {}
    include_pending = bool(filters.get("include_pending", True))

    approved = list(certificates_queryset(filters, status=Certificate.ReviewStatus.APPROVED))
    pending = (
        list(certificates_queryset(filters, status=Certificate.ReviewStatus.PENDING))
        + list(certificates_queryset(filters, status=Certificate.ReviewStatus.VALIDATED))
        if include_pending
        else []
    )
    rejected = list(certificates_queryset(filters, status=Certificate.ReviewStatus.REJECTED))

    if not approved and not pending and not rejected:
        job.status = ReportJob.Status.ERROR
        job.error_reason = "No hay registros que coincidan con los filtros."
        job.completed_at = timezone.now()
        job.save()
        return job

    content = build_workbook(
        approved, pending if include_pending else None, rejected or None
    )
    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    filename = f"certificados-{job.pk}-{stamp}.xlsx"
    path = _report_dir() / filename
    path.write_bytes(content)

    job.status = ReportJob.Status.READY
    job.artifact_path = str(path)
    job.error_reason = ""
    job.completed_at = timezone.now()
    job.save()
    return job


def run_report_job(job_id: int) -> ReportJob | None:
    """Idempotently run a report job; returns None when missing."""
    try:
        job = ReportJob.objects.get(pk=job_id)
    except ReportJob.DoesNotExist:
        return None
    if job.status == ReportJob.Status.READY:
        return job
    with transaction.atomic():
        job.status = ReportJob.Status.RUNNING
        job.save(update_fields=["status", "updated_at"])
    return generate_report(job)


def _notify_report(job: ReportJob) -> None:
    """Best-effort trigger of the n8n report flow."""
    url = str(settings.APP.get("n8n_report_webhook_url") or "")
    if not url:
        return
    token = str(settings.APP.get("n8n_webhook_token") or "")
    try:
        httpx.post(
            url,
            json={"report_job_id": job.pk},
            headers={"X-Webhook-Token": token},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "n8n_report_trigger_failed",
            extra={"report_job_id": job.pk, "error": str(exc)},
        )


def create_report_job(filters: dict[str, Any], user) -> ReportJob:
    job = ReportJob.objects.create(
        filters=filters,
        requested_by=user,
        status=ReportJob.Status.QUEUED,
    )
    _notify_report(job)
    return job
