"""State-transition policy: legal moves, illegal refusals, recovery reset."""

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from catalog.models import Entity, Language
from documents.models import Certificate, Document
from documents.services.review import (
    approve_certificate,
    reject_certificate,
    reprocess_document,
    validate_certificate,
)
from documents.services.state import (
    StateTransitionError,
    certificate_transition_allowed,
    document_transition_allowed,
    transition_certificate,
    transition_document,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def catalog(db):
    call_command("seed_catalog", verbosity=0)


def make_document(state: str, **overrides) -> Document:
    data = {
        "fingerprint": "f" * 64,
        "original_filename": "certificate.pdf",
        "content_type": "application/pdf",
        "size_bytes": 10,
        "processing_state": state,
    }
    data.update(overrides)
    return Document.objects.create(**data)


def make_certificate(document: Document, status: str, **overrides) -> Certificate:
    data = {
        "document": document,
        "student_name": "Ada Lovelace",
        "language_literal": "English",
        "entity_literal": "Cambridge English",
        "level_literal": "B2",
        "issue_date": date(2024, 5, 12),
        "review_status": status,
    }
    data.update(overrides)
    return Certificate.objects.create(**data)


@pytest.mark.parametrize(
    "current,target,expected",
    [
        ("received", "stored", True),
        ("received", "error", True),
        ("received", "approved", False),
        ("stored", "text_ready", True),
        ("stored", "extracted", False),
        ("text_ready", "extracted", True),
        ("extracted", "pending_review", True),
        ("pending_review", "approved", True),
        ("pending_review", "rejected", True),
        ("approved", "rejected", True),
        ("rejected", "approved", False),
        ("error", "stored", False),  # stored only via reprocess flag
        ("stored", "stored", True),  # idempotent self-transition
    ],
)
def test_document_transition_policy(current, target, expected):
    assert document_transition_allowed(current, target) is expected


@pytest.mark.parametrize(
    "current,target,expected",
    [
        ("pending", "validated", True),
        ("pending", "approved", True),
        ("validated", "approved", True),
        ("validated", "rejected", True),
        ("approved", "rejected", True),
        ("approved", "validated", False),
        ("rejected", "approved", False),
        ("rejected", "validated", False),
        ("rejected", "pending", False),
    ],
)
def test_certificate_transition_policy(current, target, expected):
    assert certificate_transition_allowed(current, target) is expected


def test_transition_document_persists_fields_and_resets_attempts():
    document = make_document(
        Document.ProcessingState.TEXT_READY,
        recovery_attempts=2,
        last_recovery_at="2024-01-01T00:00:00Z",
    )
    transition_document(
        document,
        Document.ProcessingState.PENDING_REVIEW,
        fields={"error_reason": "", "review_reasons": ["low_confidence"]},
    )
    document.refresh_from_db()
    assert document.processing_state == Document.ProcessingState.PENDING_REVIEW
    assert document.recovery_attempts == 0
    assert document.review_reasons == ["low_confidence"]


def test_transition_document_keeps_attempts_inside_recoverable_states():
    document = make_document(Document.ProcessingState.STORED, recovery_attempts=2)
    transition_document(document, Document.ProcessingState.TEXT_READY)
    document.refresh_from_db()
    assert document.recovery_attempts == 2


def test_transition_document_refuses_illegal_move():
    document = make_document(Document.ProcessingState.RECEIVED)
    with pytest.raises(StateTransitionError):
        transition_document(document, Document.ProcessingState.APPROVED)
    document.refresh_from_db()
    assert document.processing_state == Document.ProcessingState.RECEIVED


def test_transition_certificate_reprocess_flag_allows_rejected_reset():
    document = make_document(Document.ProcessingState.REJECTED)
    certificate = make_certificate(document, Certificate.ReviewStatus.REJECTED)
    with pytest.raises(StateTransitionError):
        transition_certificate(certificate, Certificate.ReviewStatus.PENDING)
    transition_certificate(certificate, Certificate.ReviewStatus.PENDING, reprocess=True)
    certificate.refresh_from_db()
    assert certificate.review_status == Certificate.ReviewStatus.PENDING


def test_approve_rejected_certificate_is_refused():
    user = User.objects.create_user("reviewer")
    document = make_document(Document.ProcessingState.PENDING_REVIEW)
    certificate = make_certificate(document, Certificate.ReviewStatus.REJECTED)
    outcome = approve_certificate(certificate, user)
    assert not outcome.ok
    certificate.refresh_from_db()
    document.refresh_from_db()
    assert certificate.review_status == Certificate.ReviewStatus.REJECTED
    assert document.processing_state == Document.ProcessingState.PENDING_REVIEW


def test_validate_rejected_certificate_is_refused():
    user = User.objects.create_user("reviewer2")
    document = make_document(Document.ProcessingState.PENDING_REVIEW)
    certificate = make_certificate(document, Certificate.ReviewStatus.REJECTED)
    outcome = validate_certificate(certificate, user)
    assert not outcome.ok
    certificate.refresh_from_db()
    assert certificate.review_status == Certificate.ReviewStatus.REJECTED


def test_approve_updates_document_and_certificate_atomically():
    user = User.objects.create_user("reviewer3")
    document = make_document(Document.ProcessingState.PENDING_REVIEW)
    certificate = make_certificate(document, Certificate.ReviewStatus.PENDING)
    certificate.language = Language.objects.get(code="eng")
    certificate.entity = Entity.objects.get(name="Cambridge English")
    certificate.save()
    outcome = approve_certificate(certificate, user)
    assert outcome.ok
    certificate.refresh_from_db()
    document.refresh_from_db()
    assert certificate.review_status == Certificate.ReviewStatus.APPROVED
    assert document.processing_state == Document.ProcessingState.APPROVED


def test_reprocess_resets_both_records_and_attempts():
    user = User.objects.create_user("reviewer4")
    document = make_document(Document.ProcessingState.APPROVED, recovery_attempts=3)
    certificate = make_certificate(document, Certificate.ReviewStatus.APPROVED)
    outcome = reprocess_document(document, user)
    assert outcome.ok
    document.refresh_from_db()
    certificate.refresh_from_db()
    assert document.processing_state == Document.ProcessingState.STORED
    assert document.recovery_attempts == 0
    assert certificate.review_status == Certificate.ReviewStatus.PENDING


def test_reject_then_approve_cycle_is_refused():
    user = User.objects.create_user("reviewer5")
    document = make_document(Document.ProcessingState.PENDING_REVIEW)
    certificate = make_certificate(document, Certificate.ReviewStatus.PENDING)
    outcome = reject_certificate(certificate, user, "Documento incorrecto")
    assert outcome.ok
    outcome = approve_certificate(certificate, user)
    assert not outcome.ok
