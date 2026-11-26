"""Stuck-work recovery: requeue, exhaustion, orphaning, idempotency."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from documents.models import Document
from documents.services import recovery
from documents.services.n8n import TriggerResult
from documents.services.recovery import recover_stuck
from reports.models import ReportJob

pytestmark = pytest.mark.django_db


def make_document(state: str, *, stale: bool = True, **overrides) -> Document:
    data = {
        "fingerprint": "d" * 64,
        "original_filename": "certificate.pdf",
        "content_type": "application/pdf",
        "size_bytes": 10,
        "processing_state": state,
        "paperless_document_id": "42",
    }
    data.update(overrides)
    document = Document.objects.create(**data)
    if stale:
        Document.objects.filter(pk=document.pk).update(
            updated_at=timezone.now() - timedelta(hours=2)
        )
        document.refresh_from_db()
    return document


def make_job(status: str, *, stale: bool = True, **overrides) -> ReportJob:
    job = ReportJob.objects.create(status=status, **overrides)
    if stale:
        ReportJob.objects.filter(pk=job.pk).update(updated_at=timezone.now() - timedelta(hours=2))
        job.refresh_from_db()
    return job


@pytest.fixture
def no_trigger(monkeypatch):
    calls = []

    def fake_notify(document):
        calls.append(document.pk)
        return TriggerResult(delivered=True, status_code=200)

    monkeypatch.setattr(recovery, "notify_processing", fake_notify)
    return calls


def test_stale_stored_document_is_requeued(no_trigger):
    document = make_document(Document.ProcessingState.STORED)

    report = recover_stuck()

    assert report.requeued_documents == 1
    assert no_trigger == [document.pk]
    document.refresh_from_db()
    assert document.recovery_attempts == 1
    assert document.last_recovery_at is not None
    assert Document.objects.count() == 1


@pytest.mark.parametrize("state", ["text_ready", "extracted"])
def test_stale_later_states_are_requeued(state, no_trigger):
    document = make_document(state)

    report = recover_stuck()

    assert report.requeued_documents == 1
    assert no_trigger == [document.pk]


def test_orphaned_received_document_fails(no_trigger):
    document = make_document(Document.ProcessingState.RECEIVED)

    report = recover_stuck()

    assert report.failed_documents == 1
    assert no_trigger == []
    document.refresh_from_db()
    assert document.processing_state == Document.ProcessingState.ERROR
    assert document.error_reason == "recovery_orphaned_received"


def test_recovery_budget_exhaustion_marks_error(no_trigger):
    document = make_document(Document.ProcessingState.STORED, recovery_attempts=3)

    report = recover_stuck(max_attempts=3)

    assert report.failed_documents == 1
    assert no_trigger == []
    document.refresh_from_db()
    assert document.processing_state == Document.ProcessingState.ERROR
    assert document.error_reason == "recovery_attempts_exhausted"


def test_fresh_and_terminal_documents_untouched(no_trigger):
    make_document(Document.ProcessingState.STORED, stale=False)
    make_document(Document.ProcessingState.APPROVED, fingerprint="e" * 64)
    make_document(Document.ProcessingState.PENDING_REVIEW, fingerprint="f" * 64)

    report = recover_stuck()

    assert report.stale_documents == []
    assert report.requeued_documents == 0
    assert no_trigger == []


def test_dry_run_reports_without_writes(no_trigger):
    document = make_document(Document.ProcessingState.STORED)
    make_job(ReportJob.Status.QUEUED)

    report = recover_stuck(dry_run=True)

    assert len(report.stale_documents) == 1
    assert len(report.stale_reports) == 1
    assert report.stale_documents[0].attempts == 0
    document.refresh_from_db()
    assert document.recovery_attempts == 0
    assert document.last_recovery_at is None


def test_recovery_is_idempotent_second_run_skips(no_trigger):
    make_document(Document.ProcessingState.STORED)

    recover_stuck()
    report = recover_stuck()

    # Second run finds the document fresh again only if updated_at moved;
    # simulate continued staleness by aging it again.
    Document.objects.update(updated_at=timezone.now() - timedelta(hours=2))
    report = recover_stuck()
    assert report.requeued_documents == 1
    assert len(no_trigger) == 2


def test_stale_queued_report_job_is_retried(monkeypatch):
    job = make_job(ReportJob.Status.QUEUED)
    calls = []

    def fake_run(job_id):
        calls.append(job_id)
        job_obj = ReportJob.objects.get(pk=job_id)
        job_obj.status = ReportJob.Status.READY
        job_obj.save()
        return job_obj

    monkeypatch.setattr(recovery, "run_report_job", fake_run)

    report = recover_stuck(documents_only=False, reports_only=True)

    assert report.retried_reports == 1
    assert calls == [job.pk]
    job.refresh_from_db()
    assert job.attempts == 1
    assert job.status == ReportJob.Status.READY


def test_report_recovery_budget_exhaustion(monkeypatch):
    job = make_job(ReportJob.Status.RUNNING, attempts=3)
    calls = []
    monkeypatch.setattr(recovery, "run_report_job", lambda job_id: calls.append(job_id))

    report = recover_stuck(reports_only=True, max_attempts=3)

    assert report.failed_reports == 1
    assert calls == []
    job.refresh_from_db()
    assert job.status == ReportJob.Status.ERROR
    assert job.error_reason == "recovery_attempts_exhausted"


def test_ready_report_job_untouched():
    job = make_job(ReportJob.Status.READY)

    report = recover_stuck(reports_only=True)

    assert report.stale_reports == []
    job.refresh_from_db()
    assert job.status == ReportJob.Status.READY


def test_recover_stuck_command_dry_run(client):
    make_document(Document.ProcessingState.STORED)

    call_command("recover_stuck", "--dry-run", stdout=StringIO())

    document = Document.objects.get()
    assert document.recovery_attempts == 0


def test_recover_stuck_command_runs(client, monkeypatch):
    document = make_document(Document.ProcessingState.STORED)
    monkeypatch.setattr(
        recovery,
        "notify_processing",
        lambda doc: TriggerResult(delivered=True, status_code=200),
    )

    call_command("recover_stuck", "--documents-only", stdout=StringIO())

    document.refresh_from_db()
    assert document.recovery_attempts == 1


def test_recovery_logs_do_not_leak_content(caplog, no_trigger):
    import logging

    document = make_document(Document.ProcessingState.STORED)
    document.pages.create(
        page_number=1,
        text="SECRET PAGE TEXT student passport number",
        method="embedded",
    )
    with caplog.at_level(logging.INFO, logger="documents.recovery"):
        recover_stuck()
    output = "\n".join(record.getMessage() for record in caplog.records)
    assert "SECRET PAGE TEXT" not in output
    assert "recovery_document_requeued" in output
