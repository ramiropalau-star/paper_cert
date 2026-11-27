"""Format-profile quality, drift, versioning, and verified weighting."""

from datetime import date

import pytest
from django.core.management import call_command

from catalog.models import Entity, FormatProfile
from documents.models import Certificate, Document
from documents.services.format_profile import (
    learn_format_profile,
    profile_quality_weight,
    rebuild_profile,
    score_document_format,
)
from documents.tests.factories import add_page, make_document

pytestmark = pytest.mark.django_db

BOILERPLATE = (
    "cambridge assessment english\nthis is to certify that\ncertificate of proficiency in english"
)
NEW_BOILERPLATE = (
    "oxford international exams\nthis certificate is awarded to\ncandidate of english assessment"
)


def _entity() -> Entity:
    entity, _ = Entity.objects.get_or_create(name="Cambridge English")
    return entity


def _approved_cert(document: Document, entity: Entity, **overrides) -> Certificate:
    data = {
        "document": document,
        "entity": entity,
        "entity_literal": entity.name,
        "student_name": "Ada Lovelace",
        "level_literal": "B2",
        "score_literal": "180",
        "issue_date": date(2024, 5, 12),
        "review_status": Certificate.ReviewStatus.APPROVED,
    }
    data.update(overrides)
    return Certificate.objects.create(**data)


def _pair_with_text(entity: Entity, text: str, tag: str):
    docs = []
    certs = []
    for i, suffix in enumerate(("a", "b")):
        doc = make_document(fingerprint=f"{tag}{i}" * 32)
        add_page(doc, text=text + f"\nstudent line {suffix}")
        certs.append(_approved_cert(doc, entity))
        docs.append(doc)
    return docs, certs


def _profile(entity: Entity) -> FormatProfile:
    return FormatProfile.objects.get(entity=entity, year=2024, exam__isnull=True)


# --- 7.1 versioning, provenance, rebuild ---


def test_profile_records_provenance_and_quality_on_learn():
    entity = _entity()
    _docs, certs = _pair_with_text(entity, BOILERPLATE, "p")
    for cert in certs:
        learn_format_profile(cert)

    profile = _profile(entity)
    assert profile.version == 1
    assert profile.last_rebuilt_at is not None
    assert profile.provenance["learned_from"] == "approved_certificates"
    assert profile.provenance["verified_samples"] == 0
    assert profile.sample_count == 2


def test_anchor_change_bumps_version_and_preserves_history():
    entity = _entity()
    _docs, certs = _pair_with_text(entity, BOILERPLATE, "v")
    for cert in certs:
        learn_format_profile(cert)
    profile = _profile(entity)
    version_before = profile.version

    # Two more approved samples introduce a new shared anchor line.
    for i, suffix in enumerate(("c", "d")):
        doc = make_document(fingerprint=f"w{i}" * 32)
        add_page(doc, text=BOILERPLATE + "\nnew shared layout phrase\n" + suffix)
        learn_format_profile(_approved_cert(doc, entity))

    profile.refresh_from_db()
    assert profile.version == version_before + 1
    assert profile.version_history
    assert profile.version_history[-1]["version"] == version_before
    texts = {a["text"] for a in profile.anchors}
    assert "new shared layout phrase" in texts


def test_rebuild_profile_always_bumps_version():
    entity = _entity()
    _docs, certs = _pair_with_text(entity, BOILERPLATE, "r")
    for cert in certs:
        learn_format_profile(cert)
    profile = _profile(entity)
    version_before = profile.version

    result = rebuild_profile(profile)

    assert result is not None
    assert result.version == version_before + 1
    assert result.version_history[-1]["version"] == version_before


def test_rebuild_command_rebuilds_and_deactivates_empty_cohorts():
    entity = _entity()
    _docs, certs = _pair_with_text(entity, BOILERPLATE, "c")
    for cert in certs:
        learn_format_profile(cert)
    call_command("rebuild_format_profiles", verbosity=0)
    profile = _profile(entity)
    assert profile.last_rebuilt_at is not None

    # Removing approval from the cohort deactivates rather than deletes.
    Certificate.objects.filter(entity=entity).update(
        review_status=Certificate.ReviewStatus.REJECTED
    )
    call_command("rebuild_format_profiles", verbosity=0)
    profile.refresh_from_db()
    assert profile.is_active is False


# --- 7.2 quality metrics, drift, down-weighting ---


def test_quality_metrics_recorded():
    entity = _entity()
    _docs, certs = _pair_with_text(entity, BOILERPLATE, "q")
    for cert in certs:
        learn_format_profile(cert)

    quality = _profile(entity).quality
    assert quality["sample_count"] == 2
    assert 0 < quality["anchor_precision"] <= 1
    assert 0 < quality["anchor_recall"] <= 1
    assert "anchor_churn" in quality


def test_value_shapes_learned():
    entity = _entity()
    _docs, certs = _pair_with_text(entity, BOILERPLATE, "s")
    for cert in certs:
        learn_format_profile(cert)

    shapes = _profile(entity).value_shapes
    assert shapes["score_shape"] == "int"
    assert "B2" in shapes["level_values"]


def test_drift_detected_when_recent_samples_diverge():
    entity = _entity()
    _docs, certs = _pair_with_text(entity, BOILERPLATE, "d")
    for cert in certs:
        learn_format_profile(cert)

    # Two newer approved samples use a completely different layout.
    new_certs = []
    for i, suffix in enumerate(("e", "f")):
        doc = make_document(fingerprint=f"n{i}" * 32)
        add_page(doc, text=NEW_BOILERPLATE + f"\nmarker {suffix}")
        cert = _approved_cert(doc, entity)
        new_certs.append(cert)
        learn_format_profile(cert)

    profile = _profile(entity)
    assert profile.drift_detected is True
    assert profile.drift_detail["old_anchor_recall"] < 0.3
    assert profile.quality["anchor_churn"] > 0


def test_low_quality_profile_downweights_format_score():
    entity = _entity()
    _docs, certs = _pair_with_text(entity, BOILERPLATE, "l")
    for cert in certs:
        learn_format_profile(cert)

    probe_doc = make_document(fingerprint="probe" * 8)
    add_page(probe_doc, text=BOILERPLATE + "\nstudent probe line")
    probe = _approved_cert(probe_doc, entity, review_status=Certificate.ReviewStatus.PENDING)

    score_full, _ = score_document_format(probe)
    assert score_full is not None and score_full > 0

    profile = _profile(entity)
    profile.quality = {"anchor_precision": 0.05, "anchor_recall": 0.05}
    profile.save(update_fields=["quality"])

    score_low, _ = score_document_format(probe)
    assert score_low is not None
    assert score_low < score_full
    assert profile_quality_weight(profile) < 1.0


def test_drifting_profile_caps_quality_weight():
    entity = _entity()
    _docs, certs = _pair_with_text(entity, BOILERPLATE, "w")
    for cert in certs:
        learn_format_profile(cert)
    profile = _profile(entity)
    profile.drift_detected = True
    profile.save(update_fields=["drift_detected"])
    assert profile_quality_weight(profile) <= 0.5


# --- 7.3 verified weighting and corroboration ---


def test_verified_samples_increase_anchor_weight():
    entity = _entity()
    docs, certs = _pair_with_text(entity, BOILERPLATE, "vw")
    certs[1].verification_status = Certificate.VerificationStatus.VERIFIED_AT_SOURCE
    certs[1].save(update_fields=["verification_status"])
    for cert in certs:
        learn_format_profile(cert)

    profile = _profile(entity)
    anchor = next(a for a in profile.anchors if a["text"] == "this is to certify that")
    assert anchor["df"] == 2  # corroboration counts distinct samples
    assert anchor["wdf"] == pytest.approx(3.0)  # 1 + verified weight 2
    assert profile.provenance["verified_samples"] == 1


def test_verified_sample_alone_does_not_create_anchors():
    entity = _entity()
    doc = make_document(fingerprint="solo" * 10)
    add_page(doc, text=BOILERPLATE)
    cert = _approved_cert(
        doc,
        entity,
        verification_status=Certificate.VerificationStatus.VERIFIED_AT_SOURCE,
    )
    learn_format_profile(cert)

    profile = _profile(entity)
    assert profile.sample_count == 1
    assert profile.anchors == []
