"""Format profiles: learn issuer layout signatures from approved certificates.

Each certifying entity accumulates textual "anchors" — normalized boilerplate
lines that recur across approved certificates — segmented by issuance year so
legitimate layout drift across years is tolerated. Anchors only count when
corroborated by multiple approved samples (document-frequency threshold).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

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

# Source-verified certificates contribute more weight to anchors and value
# shapes, but never bypass the distinct-sample corroboration threshold.
VERIFIED_STATUSES = (
    Certificate.VerificationStatus.VERIFIED_AT_SOURCE,
    Certificate.VerificationStatus.MANUALLY_CONFIRMED,
)

MAX_VERSION_HISTORY = 5
MAX_VALUE_SHAPES = 12
MAX_LAYOUT_ANCHORS = 100
LAYOUT_ANCHOR_PREFIX = "layout:"

# Lines that look like extracted metadata (lowercase ``key: value`` noise such
# as ``language: english``) are never eligible as anchors. Printed labels like
# "Date taken:" normalize to "date taken:" and do not match this pattern.
_METADATA_LINE_RE = re.compile(r"^[a-z][a-z0-9_]*:\s")


def _verified_weight(certificate: Certificate) -> float:
    if certificate.verification_status in VERIFIED_STATUSES:
        return float(settings.APP.get("format_verified_weight", 2.0))
    return 1.0


def _quality_floor() -> float:
    return float(settings.APP.get("profile_quality_floor", 0.5))


def _drift_threshold() -> float:
    return float(settings.APP.get("profile_drift_threshold", 0.3))


def profile_quality_weight(profile: FormatProfile) -> float:
    """Positive-evidence multiplier for a profile's measured quality.

    Low-quality or drifting profiles contribute less positive evidence but
    never negative evidence: the weight only scales scores downward toward
    zero, and callers must not treat a missing anchor as a penalty.
    """
    quality = profile.quality or {}
    weight = 1.0
    precision = quality.get("anchor_precision")
    if precision is not None and precision < _quality_floor():
        weight = min(weight, max(0.2, precision / _quality_floor() * 0.5))
    if profile.drift_detected:
        weight = min(weight, 0.5)
    return round(weight, 4)


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
            if _METADATA_LINE_RE.match(line):
                continue
            if not (MIN_ANCHOR_LEN <= len(line) <= MAX_ANCHOR_LEN):
                continue
            alpha = sum(1 for ch in line if ch.isalpha())
            if alpha < MIN_ANCHOR_ALPHA:
                continue
            lines.add(line)
    return lines


def _cohort_certificates(entity_id: int, year: int | None, exam_id: int | None = None):
    """Approved/validated certificates of an entity (+optional exam).

    ``year=None`` selects the entity-level pool: every approved sample of the
    entity regardless of issuance year.
    """
    qs = Certificate.objects.filter(
        entity_id=entity_id,
        review_status__in=LEARNED_REVIEW_STATUSES,
    ).select_related("document")
    if exam_id is not None:
        qs = qs.filter(exam_id=exam_id)
    certs = list(qs)
    if year is None:
        return certs
    return [cert for cert in certs if certificate_year(cert) == year]


def _region_bucket(ratio: float) -> int:
    """Coarse left/center/right or top/middle/bottom bucket (0-2)."""
    if ratio < 1 / 3:
        return 0
    if ratio < 2 / 3:
        return 1
    return 2


def _image_size_bucket(area_fraction: float) -> str:
    if area_fraction < 0.02:
        return "s"
    if area_fraction < 0.10:
        return "m"
    return "l"


def _bbox_ratio(bbox: list, page_w: float, page_h: float) -> tuple[float, float] | None:
    """Normalized (x, y) center of a bbox; None when data is unusable."""
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return ((x0 + x1) / 2 / page_w, (y0 + y1) / 2 / page_h)


def _layout_tokens(document) -> set[str]:
    """Recurring-friendly layout features of a document's pages.

    Tokens bucket positions coarsely so minor template shifts between centers
    or years still corroborate: ``tline:<vb>:<hb>:<normalized text>`` for
    positioned text lines and ``image:<vb>:<hb>:<size>`` for image regions.
    """
    tokens: set[str] = set()
    for page in document.pages.all():
        layout = page.layout or {}
        dims = layout.get("page") or {}
        page_w = dims.get("w")
        page_h = dims.get("h")
        if not page_w or not page_h:
            continue
        for item in layout.get("lines") or []:
            text = normalize_catalog_text(item.get("text") or "")
            if not (MIN_ANCHOR_LEN <= len(text) <= MAX_ANCHOR_LEN):
                continue
            alpha = sum(1 for ch in text if ch.isalpha())
            if alpha < MIN_ANCHOR_ALPHA:
                continue
            center = _bbox_ratio(item.get("bbox"), page_w, page_h)
            if center is None:
                continue
            vb, hb = _region_bucket(center[0]), _region_bucket(center[1])
            tokens.add(f"tline:{vb}:{hb}:{text}")
        page_area = page_w * page_h
        for item in layout.get("images") or []:
            center = _bbox_ratio(item.get("bbox"), page_w, page_h)
            if center is None:
                continue
            bbox = item["bbox"]
            area = abs(float(bbox[2]) - float(bbox[0])) * abs(float(bbox[3]) - float(bbox[1]))
            vb, hb = _region_bucket(center[0]), _region_bucket(center[1])
            tokens.add(f"image:{vb}:{hb}:{_image_size_bucket(area / page_area)}")
    return tokens


def _document_features(document) -> set[str]:
    """All format features of a document: text lines + layout tokens."""
    return _candidate_lines(document) | {
        f"{LAYOUT_ANCHOR_PREFIX}{token}" for token in _layout_tokens(document)
    }


def _anchors_for_cohort(
    certs: list[Certificate], *, pool: bool = False
) -> tuple[list[dict[str, Any]], int]:
    """Corroborated anchors for a cohort.

    ``df`` counts distinct cohort documents containing the anchor (the
    corroboration threshold); ``wdf`` is the verified-sample-weighted count
    used only for ranking. Verified samples therefore strengthen anchor
    ordering without relaxing corroboration.

    ``pool=True`` (entity-level cohort spanning several years) additionally
    requires anchors to appear in at least two distinct issuance years, so
    year-specific boilerplate cannot leak into the pooled profile — unless
    the whole pool is single-year, where the normal rule applies.
    """
    n = len(certs)
    if n == 0:
        return [], 0
    threshold = max(2, math.ceil(n / 2))
    pool_years = {certificate_year(c) for c in certs}
    pool_years.discard(None)
    require_multi_year = pool and len(pool_years) > 1
    df: dict[str, int] = {}
    wdf: dict[str, float] = {}
    line_years: dict[str, set[int]] = {}
    layout_df: dict[str, int] = {}
    layout_wdf: dict[str, float] = {}
    layout_years: dict[str, set[int]] = {}
    for cert in certs:
        weight = _verified_weight(cert)
        year = certificate_year(cert)
        for line in _candidate_lines(cert.document):
            df[line] = df.get(line, 0) + 1
            wdf[line] = wdf.get(line, 0.0) + weight
            if year is not None:
                line_years.setdefault(line, set()).add(year)
        for token in _layout_tokens(cert.document):
            layout_df[token] = layout_df.get(token, 0) + 1
            layout_wdf[token] = layout_wdf.get(token, 0.0) + weight
            if year is not None:
                layout_years.setdefault(token, set()).add(year)

    def _pool_ok(years_map: dict[str, set[int]], key: str) -> bool:
        return not require_multi_year or len(years_map.get(key, ())) >= 2

    anchors = [
        {"text": text, "df": count, "wdf": round(wdf[text], 3)}
        for text, count in df.items()
        if count >= threshold and _pool_ok(line_years, text)
    ]
    anchors.sort(key=lambda item: (-item["wdf"], item["text"]))
    layout_anchors = [
        {"kind": "layout", "feature": token, "df": count, "wdf": round(layout_wdf[token], 3)}
        for token, count in layout_df.items()
        if count >= threshold and _pool_ok(layout_years, token)
    ]
    layout_anchors.sort(key=lambda item: (-item["wdf"], item["feature"]))
    return anchors[:MAX_ANCHORS] + layout_anchors[:MAX_LAYOUT_ANCHORS], n


_NUMERIC_DATE_RE = re.compile(r"(\d{1,4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,4})")
_ALPHA_RE = re.compile(r"[A-Za-zÀ-ÿ]{3,}")


def _date_order_shape(text: str) -> str:
    """Classify a raw date candidate: dmy / mdy / ymd / named / other."""
    if _ALPHA_RE.search(text):
        return "named"
    match = _NUMERIC_DATE_RE.search(text)
    if not match:
        return "other"
    groups = match.groups()
    if len(groups[0]) == 4:
        return "ymd"
    first, second = int(groups[0]), int(groups[1])
    if first > 12 and second <= 12:
        return "dmy"
    if second > 12 and first <= 12:
        return "mdy"
    # Both orders plausible: fall back to day-first when the entity prefers it.
    return "ambiguous"


def _score_shape(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d{1,3}", text):
        return "int"
    if re.fullmatch(r"\d{1,3}[.,]\d{1,2}", text):
        return "decimal"
    if re.fullmatch(r"\d{1,3}\s*/\s*\d{1,3}", text):
        return "fraction"
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9+\-]*", text):
        return "letter"
    return "mixed"


def _code_shape(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    classes = ""
    if any(ch.isdigit() for ch in text):
        classes += "d"
    if any(ch.isalpha() for ch in text):
        classes += "a"
    if any(ch in "-_./" for ch in text):
        classes += "s"
    return f"{classes or 'other'}-{len(text)}"


def _value_shapes_for_cohort(certs: list[Certificate]) -> dict[str, Any]:
    """Learned value shapes: date order per role, score/code shape, level
    vocabulary — verified samples weighted, corroborated by distinct count."""
    date_orders: dict[str, Counter] = {}
    score_shapes: Counter = Counter()
    code_shapes: Counter = Counter()
    level_values: Counter = Counter()
    for cert in certs:
        weight = _verified_weight(cert)
        for candidate in (cert.date_texts or {}).get("candidates") or []:
            role = str(candidate.get("role") or "")
            if not role:
                continue
            shape = _date_order_shape(str(candidate.get("text") or ""))
            if shape and shape != "other":
                date_orders.setdefault(role, Counter())[shape] += weight
        shape = _score_shape(cert.score_literal)
        if shape:
            score_shapes[shape] += weight
        shape = _code_shape(cert.certificate_code)
        if shape:
            code_shapes[shape] += weight
        level = (cert.level_literal or cert.cefr_level or "").strip()
        if level:
            level_values[level] += weight

    shapes: dict[str, Any] = {}
    for role, counter in sorted(date_orders.items()):
        if counter:
            top = counter.most_common(1)[0][0]
            shapes[f"date_order_{role}"] = top
    if score_shapes:
        shapes["score_shape"] = score_shapes.most_common(1)[0][0]
    if code_shapes:
        shapes["code_shape"] = code_shapes.most_common(1)[0][0]
    if level_values:
        top = [value for value, _w in level_values.most_common(MAX_VALUE_SHAPES)]
        shapes["level_values"] = ", ".join(top)
    return shapes


def _cohort_quality(certs: list[Certificate], anchors: list[dict[str, Any]]) -> dict[str, Any]:
    """Precision/recall of the text anchors measured on the cohort itself.

    Layout anchors are excluded: quality metrics are defined over normalized
    text lines only.
    """
    text_anchors = [item for item in anchors if item.get("text")]
    if not text_anchors or not certs:
        return {"sample_count": len(certs)} if certs else {}
    anchor_texts = {str(item["text"]) for item in text_anchors}
    total = len(text_anchors)
    recalls = []
    for cert in certs:
        lines = _candidate_lines(cert.document)
        recalls.append(sum(1 for text in anchor_texts if text in lines) / total)
    # Precision: mean share of each anchor's cohort presence (df/n).
    n = len(certs)
    precision = sum(item["df"] / n for item in text_anchors) / total
    return {
        "anchor_precision": round(precision, 4),
        "anchor_recall": round(sum(recalls) / len(recalls), 4),
        "sample_count": n,
    }


def _anchor_texts(anchors: list[dict[str, Any]]) -> set[str]:
    return {str(item.get("text")) for item in anchors if item.get("text")}


def _anchor_keys(anchors: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """Identity of every anchor, text or layout, for change detection."""
    keys = {("text", str(item["text"])) for item in anchors if item.get("text")}
    keys |= {
        ("layout", str(item["feature"]))
        for item in anchors
        if item.get("kind") == "layout" and item.get("feature")
    }
    return keys


def _churn_and_drift(
    profile: FormatProfile | None,
    new_anchors: list[dict[str, Any]],
    certs: list[Certificate],
) -> tuple[float, bool, dict[str, Any]]:
    """Compare the new anchor set with the previous version.

    Returns (churn, drift_detected, drift_detail). Drift fires when the
    previous anchors are barely present in the new cohort — recent approved
    samples diverged from what older samples shared.
    """
    if profile is None or not profile.anchors:
        return 0.0, False, {}
    old_texts = _anchor_texts(profile.anchors)
    new_texts = _anchor_texts(new_anchors)
    union = old_texts | new_texts
    churn = round(1 - len(old_texts & new_texts) / len(union), 4) if union else 0.0

    # Drift compares the PREVIOUS anchors against the most recent approved
    # samples only — the cohort as a whole always contains the documents the
    # anchors were learned from, so checking everything would never fire.
    recent = sorted(certs, key=lambda c: c.updated_at, reverse=True)
    recent = recent[: max(1, math.ceil(len(recent) / 2))]
    if old_texts and recent:
        hits = 0
        checks = 0
        for cert in recent:
            lines = _candidate_lines(cert.document)
            for text in old_texts:
                checks += 1
                if text in lines:
                    hits += 1
        old_recall = hits / checks if checks else 0.0
    else:
        old_recall = 0.0
    drift = old_recall < _drift_threshold()
    detail = (
        {
            "old_anchor_recall": round(old_recall, 4),
            "threshold": _drift_threshold(),
            "previous_version": profile.version,
            "detected_at": timezone.now().isoformat(),
        }
        if drift
        else {}
    )
    return churn, drift, detail


def _snapshot_version(profile: FormatProfile) -> None:
    """Append the current state to the bounded audit history."""
    history = list(profile.version_history or [])
    history.append(
        {
            "version": profile.version,
            "anchors": len(profile.anchors or []),
            "sample_count": profile.sample_count,
            "quality": profile.quality or {},
            "snapshot_at": timezone.now().isoformat(),
        }
    )
    profile.version_history = history[-MAX_VERSION_HISTORY:]


def _refresh_profile(
    entity_id: int, year: int | None, exam_id: int | None, *, force_version: bool = False
) -> FormatProfile | None:
    certs = _cohort_certificates(entity_id, year, exam_id)
    if not certs:
        return None
    anchors, n = _anchors_for_cohort(certs, pool=year is None)
    shapes = _value_shapes_for_cohort(certs)
    profile = FormatProfile.objects.filter(entity_id=entity_id, exam_id=exam_id, year=year).first()

    changed = (
        profile is None
        or _anchor_keys(profile.anchors) != _anchor_keys(anchors)
        or (profile.value_shapes or {}) != shapes
    )
    churn, drift, drift_detail = _churn_and_drift(profile, anchors, certs)
    quality = _cohort_quality(certs, anchors)
    quality["anchor_churn"] = churn

    if profile is None:
        profile = FormatProfile(entity_id=entity_id, exam_id=exam_id, year=year)
    elif changed or force_version:
        _snapshot_version(profile)
        profile.version += 1

    profile.anchors = anchors
    profile.sample_count = n
    profile.value_shapes = shapes
    profile.quality = quality
    profile.drift_detected = drift
    profile.drift_detail = drift_detail
    years = sorted({y for c in certs if (y := certificate_year(c)) is not None})
    profile.provenance = {
        "source": "learned",
        "learned_from": "approved_certificates",
        "sample_years": [years[0], years[-1]] if years else [],
        "verified_samples": sum(1 for c in certs if c.verification_status in VERIFIED_STATUSES),
        "rebuilt_at": timezone.now().isoformat(),
    }
    profile.last_rebuilt_at = timezone.now()
    profile.save()
    return profile


def rebuild_profile(profile: FormatProfile) -> FormatProfile | None:
    """Rebuild one profile cohort from its current approved samples.

    ``year=None`` profiles are the entity-level pools and rebuild from every
    approved sample of the entity. Always bumps the version and preserves the
    previous state in ``version_history`` for audit, even when anchors are
    unchanged.
    """
    return _refresh_profile(profile.entity_id, profile.year, profile.exam_id, force_version=True)


def learn_format_profile(certificate: Certificate) -> FormatProfile | None:
    """Update the format cohort(s) this approved certificate belongs to.

    Always refreshes the entity-level (exam=None) cohort, the entity pool
    profile spanning all years, and additionally maintains an
    exam-segmented profile once enough samples exist.
    """
    if certificate.entity_id is None:
        return None
    year = certificate_year(certificate)
    if year is None:
        return None
    with transaction.atomic():
        profile = _refresh_profile(certificate.entity_id, year, None)
        _refresh_profile(certificate.entity_id, None, None)
        if certificate.exam_id is not None:
            cohort = _cohort_certificates(certificate.entity_id, year, certificate.exam_id)
            if len(cohort) >= _min_exam_samples():
                _refresh_profile(certificate.entity_id, year, certificate.exam_id)
    return profile


def _profile_anchor_map(profile: FormatProfile) -> dict[str, float]:
    """Anchor weights for scoring: verified-weighted df when present.

    Layout anchors are keyed ``layout:<feature>`` so they match the prefixed
    tokens produced by ``_document_features``.
    """
    result: dict[str, float] = {}
    for item in profile.anchors or []:
        weight = item.get("wdf") or item.get("df") or 1
        if item.get("kind") == "layout" and item.get("feature"):
            result[f"{LAYOUT_ANCHOR_PREFIX}{item['feature']}"] = float(weight)
        elif item.get("text"):
            result[str(item["text"])] = float(weight)
    return result


def _score_against(
    entity_id: int, features: set[str], year: int | None, exam_id: int | None
) -> tuple[float | None, str, float]:
    """Score document features against the best applicable profile of an entity.

    Preference order: exam-segmented cohort for the year, entity-level cohort
    for the year, exam pool across years, entity pool across years, then the
    union of all the entity's year cohorts. Returns (score, cohort_label,
    quality_weight) or (None, "", 1.0) when no profile has enough samples.
    """
    min_samples = _min_samples()
    qs = FormatProfile.objects.filter(entity_id=entity_id, is_active=True)

    if year is not None:
        year_qs = qs.filter(year=year)
        if exam_id is not None:
            exam_profile = year_qs.filter(exam_id=exam_id).first()
            if exam_profile is not None and exam_profile.sample_count >= min_samples:
                score = _weighted_recall(features, _profile_anchor_map(exam_profile))
                cohort = f"{exam_profile.entity.name} {year} / {exam_profile.exam.name}"
                return score, cohort, profile_quality_weight(exam_profile)
        entity_profile = year_qs.filter(exam__isnull=True).first()
        if entity_profile is not None and entity_profile.sample_count >= min_samples:
            score = _weighted_recall(features, _profile_anchor_map(entity_profile))
            cohort = f"{entity_profile.entity.name} {year}"
            return score, cohort, profile_quality_weight(entity_profile)

    pool_profiles = qs.filter(year__isnull=True).order_by("exam_id")
    if exam_id is not None:
        exam_pool = pool_profiles.filter(exam_id=exam_id).first()
        if exam_pool is not None and exam_pool.sample_count >= min_samples:
            score = _weighted_recall(features, _profile_anchor_map(exam_pool))
            cohort = f"{exam_pool.entity.name} (todos los años) / {exam_pool.exam.name}"
            return score, cohort, profile_quality_weight(exam_pool)
    entity_pool = pool_profiles.filter(exam__isnull=True).first()
    if entity_pool is not None and entity_pool.sample_count >= min_samples:
        score = _weighted_recall(features, _profile_anchor_map(entity_pool))
        cohort = f"{entity_pool.entity.name} (todos los años)"
        return score, cohort, profile_quality_weight(entity_pool)

    # Fallback: union of all year cohorts for this entity (exam-level included
    # only via their anchors; weight = number of cohorts containing the anchor).
    profiles = [p for p in qs if p.year is not None]
    if not profiles:
        return None, "", 1.0
    merged: dict[str, float] = {}
    for profile in profiles:
        for text in _profile_anchor_map(profile):
            merged[text] = merged.get(text, 0.0) + 1.0
    cohort_samples = sum(p.sample_count for p in profiles)
    if cohort_samples < min_samples:
        return None, "", 1.0
    score = _weighted_recall(features, merged)
    entity_name = profiles[0].entity.name
    quality_weight = min(profile_quality_weight(p) for p in profiles)
    return score, f"{entity_name} (todos los años)", quality_weight


def _weighted_recall(lines: set[str], anchors: dict[str, float]) -> float:
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
    features = _document_features(document)
    if not features:
        return None, ""
    year = certificate_year(certificate)
    score, cohort, quality_weight = _score_against(
        certificate.entity_id, features, year, certificate.exam_id
    )
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
        other_score, _label, _w = _score_against(other_id, features, year, certificate.exam_id)
        if other_score is not None and (best_other is None or other_score > best_other):
            best_other = other_score
    if best_other is not None and best_other > score + 0.2:
        score = min(score, _max_score())
    # Low-quality/drifting profiles contribute less positive evidence; they
    # never contribute negative evidence (score stays >= 0).
    if quality_weight < 1.0:
        score = round(score * quality_weight, 4)
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
        if year is not None and certificate_year(certificate) != year:
            continue
        score, cohort = score_document_format(certificate)
        certificate.format_score = score
        certificate.format_cohort = cohort or ""
        certificate.save(update_fields=["format_score", "format_cohort", "updated_at"])
        rescored += 1
    return rescored
