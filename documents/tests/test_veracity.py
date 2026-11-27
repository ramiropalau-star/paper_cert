"""Veracity scoring: components, weights version, and review-aid semantics."""

from datetime import date

import pytest
from django.conf import settings
from django.test import override_settings

from documents.models import Certificate
from documents.services.veracity import (
    WEIGHTS_VERSION,
    compute_veracity,
    maybe_compute_veracity,
)
from documents.tests.factories import add_page, make_document

pytestmark = pytest.mark.django_db


def _cert(**overrides) -> Certificate:
    document = make_document(fingerprint="cert" + str(Certificate.objects.count()))
    add_page(document, text="some certificate text")
    data = {
        "document": document,
        "student_name": "Ada Lovelace",
        "entity_literal": "Cambridge English",
        "exam_literal": "B2 First",
        "level_literal": "B2",
        "score_literal": "180",
        "issue_date": date(2024, 5, 12),
        "certificate_code": "ABC-123",
        "verification_status": Certificate.VerificationStatus.NONE,
        "review_status": Certificate.ReviewStatus.PENDING,
    }
    data.update(overrides)
    return Certificate.objects.create(**data)


def test_source_verified_scores_high():
    cert = _cert(
        verification_status=Certificate.VerificationStatus.VERIFIED_AT_SOURCE,
        format_score=0.9,
    )
    result = compute_veracity(cert)

    assert result["score"] > 0.8
    assert result["components"]["source"]["value"] == 1.0
    assert cert.veracity_weights_version == WEIGHTS_VERSION
    breakdown = cert.veracity_components["components"]
    assert breakdown["source"]["label"]
    assert breakdown["source"]["weight"] == pytest.approx(0.4)


def test_format_only_stays_below_verified_range():
    cert = _cert(
        verification_status=Certificate.VerificationStatus.NONE,
        format_score=0.95,
    )
    result = compute_veracity(cert)

    assert result["components"]["source"]["value"] == 0.0
    # Even perfect format/evidence cannot reach the verified range.
    assert result["score"] < 0.75
    verified = _cert(
        verification_status=Certificate.VerificationStatus.VERIFIED_AT_SOURCE,
        format_score=0.95,
    )
    assert compute_veracity(verified)["score"] > result["score"]


def test_missing_evidence_lowers_score():
    covered = _cert(format_score=0.8)
    missing = _cert(
        format_score=0.8,
        unverified_fields=["student_name", "score", "issue_date", "certificate_code"],
    )
    covered_result = compute_veracity(covered)
    missing_result = compute_veracity(missing)

    assert (
        missing_result["components"]["evidence"]["value"]
        < covered_result["components"]["evidence"]["value"]
    )
    assert missing_result["score"] < covered_result["score"]


def test_consistency_reason_lowers_component():
    cert = _cert(format_score=0.8, review_reasons=["entity_mismatch"])
    result = compute_veracity(cert)
    assert result["components"]["consistency"]["value"] == 0.4


def test_high_score_never_auto_approves():
    cert = _cert(
        verification_status=Certificate.VerificationStatus.MANUALLY_CONFIRMED,
        format_score=1.0,
    )
    compute_veracity(cert)
    cert.refresh_from_db()
    assert cert.review_status == Certificate.ReviewStatus.PENDING


def test_low_quality_profile_reduces_format_component():
    from catalog.models import Entity
    from documents.tests.factories import make_format_profile

    entity = Entity.objects.create(name="Quality Entity")
    make_format_profile(
        entity,
        quality={"anchor_precision": 0.05, "anchor_recall": 0.05},
        sample_count=5,
    )
    cert = _cert(entity=entity, format_score=0.9)
    result = compute_veracity(cert)
    assert result["components"]["format"]["value"] < 0.9


def test_veracity_disabled_by_flag():
    cert = _cert()
    with override_settings(APP={**settings.APP, "veracity_enabled": False}):
        maybe_compute_veracity(cert)
    cert.refresh_from_db()
    assert cert.veracity_score is None
