"""Best-effort outbound triggers to the n8n orchestration layer."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from django.conf import settings

from documents.models import Document
from reports.models import ReportJob

logger = logging.getLogger("documents.services.n8n")


@dataclass(frozen=True)
class TriggerResult:
    delivered: bool
    status_code: int | None = None
    error: str = ""


def _post(url: str, payload: dict, timeout: float) -> TriggerResult:
    token = str(settings.APP.get("n8n_webhook_token") or "")
    try:
        response = httpx.post(
            url,
            json=payload,
            headers={"X-Webhook-Token": token},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        return TriggerResult(delivered=False, error=str(exc))

    status_code = response.status_code
    error = ""
    if not 200 <= status_code < 300:
        error = f"HTTP {status_code}"
    else:
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and body.get("error"):
            error = str(body.get("error"))
    return TriggerResult(
        delivered=not error,
        status_code=status_code,
        error=error,
    )


def _log_failure(event: str, extra: dict, result: TriggerResult) -> None:
    logger.warning(
        event,
        extra={
            **extra,
            "outcome": "trigger_failed",
            "status_code": result.status_code,
            "error": result.error[:200],
        },
    )


def notify_processing(document: Document) -> TriggerResult:
    """Trigger the n8n processing flow for a stored document.

    Best-effort: a failed trigger is logged and reported, never raised, so the
    persisted state remains the source of truth for recovery.
    """
    url = str(settings.APP.get("n8n_processing_webhook_url") or "")
    if not url:
        return TriggerResult(delivered=False, error="no webhook url configured")
    timeout = float(settings.APP.get("n8n_webhook_timeout_seconds") or 10.0)
    result = _post(url, {"document_id": document.pk}, timeout)
    if not result.delivered:
        _log_failure(
            "n8n_processing_trigger_failed",
            {"document_id": document.pk},
            result,
        )
    return result


def notify_report(job: ReportJob) -> TriggerResult:
    """Trigger the n8n report flow for a queued job."""
    url = str(settings.APP.get("n8n_report_webhook_url") or "")
    if not url:
        return TriggerResult(delivered=False, error="no webhook url configured")
    timeout = float(settings.APP.get("n8n_webhook_timeout_seconds") or 10.0)
    result = _post(url, {"report_job_id": job.pk}, timeout)
    if not result.delivered:
        _log_failure(
            "n8n_report_trigger_failed",
            {"report_job_id": job.pk},
            result,
        )
    return result
