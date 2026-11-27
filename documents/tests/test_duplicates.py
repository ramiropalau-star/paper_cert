"""Tests for semantic duplicate detection."""

from datetime import date

import pytest
from django.core.management import call_command

from catalog.models import Entity
from documents.models import Certificate, Document
from documents.services.duplicates import (
    DUPLICATE_REASON,
    find_duplicate_certificate,
    refresh_duplicate_flag,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def catalog(db):
    call_command("seed_catalog", verbosity=0)


def make_document(**overrides) -> Document:
    data = {
        "fingerprint": "d" * 64,
        "original_filename": "certificate.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
        "processing_state": Document.ProcessingState.PENDING_REVIEW,
    }
    data.update(overrides)
    return Document.objects.create(**data)


def make_certificate(document: Document, **overrides) -> Certificate:
    data = {
        "document": document,
        "student_name": "Ada Lovelace",
        "language_literal": "English",
        "entity_literal": "Cambridge English",
        "level_literal": "B2",
        "score_literal": "180",
        "issue_date": date(2024, 5, 12),
        "is_language_certificate": True,
    }
    data.update(overrides)
    cert = Certificate.objects.create(**data)
    cert.entity = Entity.objects.get(name="Cambridge English")
    cert.save()
    return cert


def test_same_code_same_entity_is_duplicate():
    first = make_certificate(make_document(fingerprint="1" * 64), certificate_code="ABC-123")
    second = make_certificate(make_document(fingerprint="2" * 64), certificate_code="abc 123")

    assert find_duplicate_certificate(second) == first


def test_same_code_different_entity_is_not_duplicate():
    first = make_certificate(make_document(fingerprint="1" * 64), certificate_code="ABC-123")
    other_entity = Entity.objects.create(name="Other Board")
    second = make_certificate(make_document(fingerprint="2" * 64), certificate_code="ABC-123")
    second.entity = other_entity
    second.save()

    assert find_duplicate_certificate(second) is None
    assert find_duplicate_certificate(first) == first or find_duplicate_certificate(first) is None


def test_different_code_is_not_duplicate():
    make_certificate(make_document(fingerprint="1" * 64), certificate_code="ABC-123")
    second = make_certificate(make_document(fingerprint="2" * 64), certificate_code="XYZ-999")

    assert find_duplicate_certificate(second) is None


def test_code_match_ignores_rejected_certificates():
    make_certificate(
        make_document(fingerprint="1" * 64),
        certificate_code="ABC-123",
        review_status=Certificate.ReviewStatus.REJECTED,
    )
    second = make_certificate(make_document(fingerprint="2" * 64), certificate_code="ABC-123")

    assert find_duplicate_certificate(second) is None


def test_no_code_falls_back_to_student_exam_date():
    first = make_certificate(
        make_document(fingerprint="1" * 64),
        student_name="RAMIRO PALAU",
        exam_literal="Elemental",
        issue_date=date(2024, 3, 1),
    )
    first.exam_id = None
    second = make_certificate(
        make_document(fingerprint="2" * 64),
        student_name="ramiro palau",
        exam_literal="Elemental",
        issue_date=date(2024, 3, 1),
    )
    second.exam_id = None

    assert find_duplicate_certificate(second) == first


def test_same_name_without_corroboration_is_not_duplicate():
    make_certificate(make_document(fingerprint="1" * 64), student_name="Common Name")
    second = make_certificate(
        make_document(fingerprint="2" * 64),
        student_name="Common Name",
        issue_date=date(2020, 1, 1),
    )

    assert find_duplicate_certificate(second) is None


def test_refresh_duplicate_flag_sets_reason_and_link():
    first = make_certificate(make_document(fingerprint="1" * 64), certificate_code="ABC-123")
    second = make_certificate(
        make_document(fingerprint="2" * 64),
        certificate_code="ABC-123",
        review_reasons=["low_confidence"],
    )

    other = refresh_duplicate_flag(second)

    assert other == first
    second.refresh_from_db()
    assert second.duplicate_of_id == first.pk
    assert DUPLICATE_REASON in second.review_reasons
    assert "low_confidence" in second.review_reasons
    assert DUPLICATE_REASON in second.document.review_reasons


def test_refresh_duplicate_flag_clears_when_identity_changes():
    make_certificate(make_document(fingerprint="1" * 64), certificate_code="ABC-123")
    second = make_certificate(make_document(fingerprint="2" * 64), certificate_code="ABC-123")
    refresh_duplicate_flag(second)

    second.certificate_code = "DIFFERENT"
    second.save()
    refresh_duplicate_flag(second)

    second.refresh_from_db()
    assert second.duplicate_of_id is None
    assert DUPLICATE_REASON not in (second.review_reasons or [])
