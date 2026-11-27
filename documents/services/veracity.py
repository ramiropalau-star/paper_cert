"""Veracity scoring: a review aid combining independent evidence signals.

The score is NOT proof of authenticity and never auto-approves: it blends
source-verification status, format/profile match, label-value consistency,
and extraction evidence coverage. Component values and the weights version
are stored on the certificate so the breakdown can be displayed and audited.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils import timezone

from documents.models import Certificate

WEIGHTS_VERSION = "veracity-v1"

# source 0.40 + format 0.25 + consistency 0.20 + evidence 0.15 = 1.00
WEIGHTS = {
    "source": 0.40,
    "format": 0.25,
    "consistency": 0.20,
    "evidence": 0.15,
}

COMPONENT_LABELS = {
    "source": "Verificación en origen",
    "format": "Coincidencia de formato",
    "consistency": "Consistencia de datos",
    "evidence": "Cobertura de evidencia",
}

_SOURCE_VALUES = {
    Certificate.VerificationStatus.VERIFIED_AT_SOURCE: 1.0,
    Certificate.VerificationStatus.MANUALLY_CONFIRMED: 1.0,
    Certificate.VerificationStatus.SELF_REPORTED: 0.4,
    Certificate.VerificationStatus.NONE: 0.0,
}

# Review reasons that indicate label/value inconsistency between the
# pre-detected issuer and the resolved classification.
_CONSISTENCY_REASONS = {"entity_mismatch", "exam_mismatch", "source_mismatch"}
_CONSISTENCY_PENALTY = 0.4

# (certificate attribute, extraction field name) pairs counted for evidence
# coverage. Only populated fields participate; unverified ones score 0.
_EVIDENCE_FIELDS = (
    ("student_name", "student_name"),
    ("entity_literal", "entity"),
    ("exam_literal", "exam"),
    ("level_literal", "level"),
    ("score_literal", "score"),
    ("issue_date", "issue_date"),
    ("certificate_code", "certificate_code"),
)


def _source_component(certificate: Certificate) -> float:
    return _SOURCE_VALUES.get(certificate.verification_status, 0.0)


def _format_component(certificate: Certificate) -> float:
    score = certificate.format_score
    if score is None:
        return 0.0
    value = min(1.0, max(0.0, float(score)))
    # Quality/drift of the issuer profile scales positive evidence only.
    if certificate.entity_id is not None:
        try:
            from documents.services.format_profile import (
                profile_quality_weight,
            )
            from documents.services.profile_context import select_profile

            profile = select_profile(certificate.entity_id, certificate.exam_id)
            if profile is not None:
                value *= profile_quality_weight(profile)
        except Exception:  # noqa: BLE001 - scoring must never break review
            pass
    return round(value, 4)


def _consistency_component(certificate: Certificate) -> float:
    reasons = set(certificate.review_reasons or [])
    if reasons & _CONSISTENCY_REASONS:
        return _CONSISTENCY_PENALTY
    return 1.0


def _evidence_component(certificate: Certificate) -> float:
    unverified = set(certificate.unverified_fields or [])
    populated = 0
    covered = 0
    for attr, field_name in _EVIDENCE_FIELDS:
        value = getattr(certificate, attr, None)
        if value in (None, ""):
            continue
        populated += 1
        if field_name not in unverified:
            covered += 1
    if populated == 0:
        return 0.0
    return round(covered / populated, 4)


def compute_veracity(certificate: Certificate) -> dict[str, Any]:
    """Compute and persist the veracity score with its breakdown."""
    components = {
        "source": _source_component(certificate),
        "format": _format_component(certificate),
        "consistency": _consistency_component(certificate),
        "evidence": _evidence_component(certificate),
    }
    score = round(sum(components[name] * WEIGHTS[name] for name in WEIGHTS), 4)
    breakdown = {
        name: {
            "value": components[name],
            "weight": WEIGHTS[name],
            "label": COMPONENT_LABELS[name],
        }
        for name in WEIGHTS
    }
    certificate.veracity_score = score
    certificate.veracity_components = {
        "weights_version": WEIGHTS_VERSION,
        "components": breakdown,
    }
    certificate.veracity_weights_version = WEIGHTS_VERSION
    certificate.veracity_computed_at = timezone.now()
    certificate.save(
        update_fields=[
            "veracity_score",
            "veracity_components",
            "veracity_weights_version",
            "veracity_computed_at",
            "updated_at",
        ]
    )
    return {"score": score, "components": breakdown}


def veracity_enabled() -> bool:
    return bool(settings.APP.get("veracity_enabled", True))


def maybe_compute_veracity(certificate: Certificate) -> None:
    """Compute veracity when the feature flag is on; never raises."""
    if not veracity_enabled():
        return
    try:
        compute_veracity(certificate)
    except Exception:  # noqa: BLE001 - scoring must never break the pipeline
        pass
