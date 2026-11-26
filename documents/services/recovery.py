"""Recovery of documents and report jobs stuck in intermediate states.

Documents in ``stored``/``text_ready``/``extracted`` are requeued through the
normal n8n pipeline; ``received`` documents are failed because their staged
upload is gone. Report jobs in ``queued``/``running`` are retried locally.
Every action is bounded by a persisted attempt counter and the whole run is
idempotent, so the watcher loop and the ``recover_stuck`` command can overlap
safely.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from documents.models import Document
from documents.services.n8n import notify_processing
from documents.services.state import transition_document
from reports.models import ReportJob
from reports.services import run_report_job

logger = logging.getLogger("documents.recovery")

S = Document.ProcessingState
REASON_EXHAUSTED = "recovery_attempts_exhausted"
REASON_ORPHANED = "recovery_orphaned_received"

DOCUMENT_RETRY_STATES = {S.STORED, S.TEXT_READY, S.EXTRACTED}
DOCUMENT_STALE_STATES = DOCUMENT_RETRY_STATES | {S.RECEIVED}
REPORT_STALE_STATES = {ReportJob.Status.QUEUED, ReportJob.Status.RUNNING}


@dataclass(frozen=True)
class StaleItem:
    pk: int
    state: str
    age_seconds: float
    attempts: int


@dataclass
class RecoveryReport:
    stale_documents: list[StaleItem] = field(default_factory=list)
    stale_reports: list[StaleItem] = field(default_factory=list)
    requeued_documents: int = 0
    failed_documents: int = 0
    retried_reports: int = 0
    failed_reports: int = 0


def _age_seconds(updated_at, now) -> float:
    return max(0.0, (now - updated_at).total_seconds())


def _scan_documents(cutoff, now) -> list[StaleItem]:
    items = []
    for doc in Document.objects.filter(
        processing_state__in=[state.value for state in DOCUMENT_STALE_STATES],
        updated_at__lt=cutoff,
    ):
        items.append(
            StaleItem(
                pk=doc.pk,
                state=doc.processing_state,
                age_seconds=_age_seconds(doc.updated_at, now),
                attempts=doc.recovery_attempts,
            )
        )
    return items


def _scan_reports(cutoff, now) -> list[StaleItem]:
    items = []
    for job in ReportJob.objects.filter(
        status__in=[state.value for state in REPORT_STALE_STATES],
        updated_at__lt=cutoff,
    ):
        items.append(
            StaleItem(
                pk=job.pk,
                state=job.status,
                age_seconds=_age_seconds(job.updated_at, now),
                attempts=job.attempts,
            )
        )
    return items


def _fail_document(document: Document, reason: str, now) -> None:
    transition_document(
        document,
        S.ERROR,
        fields={"error_reason": reason, "last_recovery_at": now},
    )
    logger.warning(
        "recovery_document_failed",
        extra={
            "document_id": document.pk,
            "outcome": "error",
            "reason": reason,
        },
    )


def _recover_document(document_id: int, cutoff, max_attempts, now) -> str:
    """Recover one document inside a row lock; returns the action taken."""
    with transaction.atomic():
        document = Document.objects.select_for_update().get(pk=document_id)
        if document.processing_state not in DOCUMENT_STALE_STATES or document.updated_at >= cutoff:
            return "skipped"

        if document.processing_state == S.RECEIVED:
            _fail_document(document, REASON_ORPHANED, now)
            return "failed"

        if document.recovery_attempts >= max_attempts:
            _fail_document(document, REASON_EXHAUSTED, now)
            return "failed"

        document.recovery_attempts += 1
        document.last_recovery_at = now
        document.save(update_fields=["recovery_attempts", "last_recovery_at", "updated_at"])

    result = notify_processing(document)
    logger.info(
        "recovery_document_requeued",
        extra={
            "document_id": document.pk,
            "outcome": "requeued" if result.delivered else "trigger_failed",
            "status_code": result.status_code,
            "attempt": document.recovery_attempts,
        },
    )
    return "requeued"


def _recover_report(job_id: int, cutoff, max_attempts, now) -> str:
    """Retry one report job locally; returns the action taken."""
    with transaction.atomic():
        job = ReportJob.objects.select_for_update().get(pk=job_id)
        if job.status not in REPORT_STALE_STATES or job.updated_at >= cutoff:
            return "skipped"

        if job.attempts >= max_attempts:
            job.status = ReportJob.Status.ERROR
            job.error_reason = REASON_EXHAUSTED
            job.last_attempt_at = now
            job.save(update_fields=["status", "error_reason", "last_attempt_at", "updated_at"])
            logger.warning(
                "recovery_report_failed",
                extra={"report_id": job.pk, "outcome": "error", "reason": REASON_EXHAUSTED},
            )
            return "failed"

        job.attempts += 1
        job.last_attempt_at = now
        job.save(update_fields=["attempts", "last_attempt_at", "updated_at"])

    try:
        run_report_job(job.pk)
    except Exception as exc:
        logger.warning(
            "recovery_report_retry_failed",
            extra={"report_id": job.pk, "outcome": "error", "error": str(exc)[:200]},
        )
        return "retried"
    logger.info(
        "recovery_report_retried",
        extra={"report_id": job.pk, "outcome": "retried", "attempt": job.attempts},
    )
    return "retried"


def recover_stuck(
    *,
    older_than_seconds: float | None = None,
    max_attempts: int | None = None,
    documents_only: bool = False,
    reports_only: bool = False,
    dry_run: bool = False,
) -> RecoveryReport:
    """Scan for stale work and recover it. ``dry_run`` only reports."""
    app = settings.APP
    stale_seconds = float(
        older_than_seconds
        if older_than_seconds is not None
        else app.get("recovery_stale_seconds") or 0
    )
    attempts_limit = int(
        max_attempts if max_attempts is not None else app.get("recovery_max_attempts") or 0
    )
    now = timezone.now()
    cutoff = now - timedelta(seconds=stale_seconds)
    report = RecoveryReport()

    if not reports_only:
        report.stale_documents = _scan_documents(cutoff, now)
    if not documents_only:
        report.stale_reports = _scan_reports(cutoff, now)

    if dry_run:
        return report

    for item in report.stale_documents:
        try:
            action = _recover_document(item.pk, cutoff, attempts_limit, now)
        except Exception:
            logger.exception("recovery_document_error", extra={"document_id": item.pk})
            continue
        if action == "requeued":
            report.requeued_documents += 1
        elif action == "failed":
            report.failed_documents += 1

    for item in report.stale_reports:
        try:
            action = _recover_report(item.pk, cutoff, attempts_limit, now)
        except Exception:
            logger.exception("recovery_report_error", extra={"report_id": item.pk})
            continue
        if action == "retried":
            report.retried_reports += 1
        elif action == "failed":
            report.failed_reports += 1

    logger.info(
        "recovery_run",
        extra={
            "outcome": "completed",
            "stale_documents": len(report.stale_documents),
            "stale_reports": len(report.stale_reports),
            "requeued_documents": report.requeued_documents,
            "failed_documents": report.failed_documents,
            "retried_reports": report.retried_reports,
            "failed_reports": report.failed_reports,
        },
    )
    return report
