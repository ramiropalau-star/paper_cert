"""Best-effort outbound triggers to the n8n orchestration layer."""

from __future__ import annotations

import logging

import httpx
from django.conf import settings

from documents.models import Document
from reports.models import ReportJob

logger = logging.getLogger("documents.services.n8n")


def notify_processing(document: Document) -> None:
    """Trigger the n8n processing flow for a stored document."""
    url = str(settings.APP.get("n8n_processing_webhook_url") or "")
    if not url:
        return
    token = str(settings.APP.get("n8n_webhook_token") or "")
    try:
        httpx.post(
            url,
            json={"document_id": document.pk},
            headers={"X-Webhook-Token": token},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "n8n_processing_trigger_failed",
            extra={"document_id": document.pk, "error": str(exc)},
        )


def notify_report(job: ReportJob) -> None:
    """Trigger the n8n report flow for a queued job."""
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
