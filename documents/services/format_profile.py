"""Format profiles: learn issuer layout signatures from approved certificates.

Each certifying entity accumulates textual "anchors" — normalized boilerplate
lines that recur across approved certificates — segmented by issuance year so
legitimate layout drift across years is tolerated. Anchors only count when
corroborated by multiple approved samples (document-frequency threshold).
"""

from __future__ import annotations

import math
from typing import Any

from django.conf import settings
from django.db import transaction

from catalog.models import FormatProfile
from catalog.normalization import normalize_catalog_text
from documents.models import Certificate

MIN_ANCHOR_LEN = 8
MAX_ANCHOR_LEN = 160
MIN_ANCHOR_ALPHA = 4
MAX_ANCHORS = 200

LEARNED_REVIEW_STATUSES = (
    Certificate.ReviewStatus.APPROVED,
    Certificate.ReviewStatus.VALIDATED,
)


def _min_samples() -> int:
    return int(settings.APP.get("format_min_samples", 2))


def _min_exam_samples() -> int:
    return int(settings.APP.get("format_min_exam_samples", 3))


def _score_threshold() -> float:
    return float(settings.APP.get("format_score_threshold", 0.4))


def _max_score() -> float:
    return float(settings.APP.get("format_max_score", 0.5))


def certificate_year(certificate: Certificate) -> int | None:
    """Issuance year used for cohorting: issue > exam > detected date."""
    for field in ("issue_date", "exam_date", "detected_date"):
        value = getattr(certificate, field, None)
        if value is not None:
            return value.year
    return None


def _candidate_lines(document) -> set[str]:
    """Normalized text lines eligible to become format anchors."""
    lines: set[str] = set()
    for page in document.pages.all():
        for raw in (page.text or "").splitlines():
            line = normalize_catalog_text(raw)
            if not (MIN_ANCHOR_LEN <= len(line) <= MAX_ANCHOR_LEN):
                continue
            alpha = sum(1 for ch in line if ch.isalpha())
            if alpha < MIN_ANCHOR_ALPHA:
                continue
            lines.add(line)
    return lines


def _cohort_certificates(entity_id: int, year: int, exam_id: int | None = None):
    """Approved/validated certificates of an entity (+optional exam) in a year."""
    qs = Certificate.objects.filter(
        entity_id=entity_id,
        review_status__in=LEARNED_REVIEW_STATUSES,
    ).select_related("document")
    if exam_id is not None:
        qs = qs.filter(exam_id=exam_id)
    return [cert for cert in qs if certificate_year(cert) == year]


def _anchors_for_cohort(certs: list[Certificate]) -> tuple[list[dict[str, Any]], int]:
    """Corroborated anchors for a cohort: df >= max(2, ceil(n/2))."""
    n = len(certs)
    if n == 0:
        return [], 0
    threshold = max(2, math.ceil(n / 2))
    df: dict[str, int] = {}
    for cert in certs:
        for line in _candidate_lines(cert.document):
            df[line] = df.get(line, 0) + 1
    anchors = [{"text": text, "df": count} for text, count in df.items() if count >= threshold]
    anchors.sort(key=lambda item: (-item["df"], item["text"]))
    return anchors[:MAX_ANCHORS], n


def _refresh_profile(entity_id: int, year: int, exam_id: int | None) -> FormatProfile | None:
    certs = _cohort_certificates(entity_id, year, exam_id)
    if not certs:
        return None
    anchors, n = _anchors_for_cohort(certs)
    profile, _ = FormatProfile.objects.get_or_create(
        entity_id=entity_id, exam_id=exam_id, year=year
    )
    profile.anchors = anchors
    profile.sample_count = n
    profile.save(update_fields=["anchors", "sample_count", "updated_at"])
    return profile


def learn_format_profile(certificate: Certificate) -> FormatProfile | None:
    """Update the format cohort(s) this approved certificate belongs to.

    Always refreshes the entity-level (exam=None) cohort; additionally
    maintains an exam-segmented profile once enough samples exist.
    """
    if certificate.entity_id is None:
        return None
    year = certificate_year(certificate)
    if year is None:
        return None
    with transaction.atomic():
        profile = _refresh_profile(certificate.entity_id, year, None)
        if certificate.exam_id is not None:
            cohort = _cohort_certificates(certificate.entity_id, year, certificate.exam_id)
            if len(cohort) >= _min_exam_samples():
                _refresh_profile(certificate.entity_id, year, certificate.exam_id)
    return profile


def _profile_anchor_map(profile: FormatProfile) -> dict[str, int]:
    return {
        str(item.get("text")): int(item.get("df") or 1)
        for item in (profile.anchors or [])
        if item.get("text")
    }


def _score_against(
    entity_id: int, lines: set[str], year: int | None, exam_id: int | None
) -> tuple[float | None, str]:
    """Score document lines against the best applicable profile of an entity.

    Preference order: exam-segmented cohort for the year, entity-level cohort
    for the year, then the union of all the entity's year cohorts. Returns
    (score, cohort_label) or (None, "") when no profile has enough samples.
    """
    min_samples = _min_samples()
    qs = FormatProfile.objects.filter(entity_id=entity_id, is_active=True)

    if year is not None:
        year_qs = qs.filter(year=year)
        if exam_id is not None:
            exam_profile = year_qs.filter(exam_id=exam_id).first()
            if exam_profile is not None and exam_profile.sample_count >= min_samples:
                score = _weighted_recall(lines, _profile_anchor_map(exam_profile))
                return score, f"{exam_profile.entity.name} {year} / {exam_profile.exam.name}"
        entity_profile = year_qs.filter(exam__isnull=True).first()
        if entity_profile is not None and entity_profile.sample_count >= min_samples:
            score = _weighted_recall(lines, _profile_anchor_map(entity_profile))
            return score, f"{entity_profile.entity.name} {year}"

    # Fallback: union of all year cohorts for this entity (exam-level included
    # only via their anchors; weight = number of cohorts containing the anchor).
    profiles = list(qs)
    if not profiles:
        return None, ""
    merged: dict[str, int] = {}
    total_weight = 0
    for profile in profiles:
        for text, df in _profile_anchor_map(profile).items():
            merged[text] = merged.get(text, 0) + 1
            total_weight += df
    cohort_samples = sum(p.sample_count for p in profiles)
    if cohort_samples < min_samples:
        return None, ""
    score = _weighted_recall(lines, merged)
    entity_name = profiles[0].entity.name
    return score, f"{entity_name} (todos los años)"


def _weighted_recall(lines: set[str], anchors: dict[str, int]) -> float:
    """Recall of profile anchors present in the document, df-weighted."""
    if not anchors:
        return 0.0
    total = sum(anchors.values())
    matched = sum(df for text, df in anchors.items() if text in lines)
    return round(matched / total, 4) if total else 0.0


def score_document_format(certificate: Certificate) -> tuple[float | None, str]:
    """Compute the format score for a classified certificate.

    Returns (score, cohort_label); score is None when no profile applies.
    Applies the cross-entity cap when another issuer's format matches better.
    """
    if certificate.entity_id is None:
        return None, ""
    document = certificate.document
    lines = _candidate_lines(document)
    if not lines:
        return None, ""
    year = certificate_year(certificate)
    score, cohort = _score_against(certificate.entity_id, lines, year, certificate.exam_id)
    if score is None:
        return None, cohort

    best_other: float | None = None
    other_entities = (
        FormatProfile.objects.filter(entity_id__isnull=False, is_active=True)
        .exclude(entity_id=certificate.entity_id)
        .values_list("entity_id", flat=True)
        .distinct()
    )
    for other_id in other_entities:
        other_score, _label = _score_against(other_id, lines, year, certificate.exam_id)
        if other_score is not None and (best_other is None or other_score > best_other):
            best_other = other_score
    if best_other is not None and best_other > score + 0.2:
        score = min(score, _max_score())
    return score, cohort


def rescore_entity_year(entity_id: int, year: int, exam_id: int | None = None) -> int:
    """Recompute format scores for certificates of an entity cohort.

    Returns the number of certificates rescored. Used after a profile is
    deactivated/reactivated so stored scores reflect active profiles.
    """
    certs = Certificate.objects.filter(entity_id=entity_id).select_related("document")
    if exam_id is not None:
        certs = certs.filter(exam_id=exam_id)
    rescored = 0
    for certificate in certs:
        if certificate_year(certificate) != year:
            continue
        score, cohort = score_document_format(certificate)
        certificate.format_score = score
        certificate.format_cohort = cohort or ""
        certificate.save(update_fields=["format_score", "format_cohort", "updated_at"])
        rescored += 1
    return rescored
