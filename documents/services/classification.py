"""Catalog classification: languages, entities, exams, CEFR, and dates.

Matching is exact after Unicode normalization (NFKC, casefold, whitespace
collapse). Literal printed values are always preserved next to the resolved
catalog entries; unknown values stay unresolved and route to review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from dateutil import parser as date_parser
from django.conf import settings
from django.db import transaction

from catalog.models import (
    CefrConversionRule,
    Entity,
    EntityAlias,
    Equivalence,
    Exam,
    Language,
    LanguageAlias,
)
from catalog.normalization import normalize_catalog_text
from documents.models import Certificate, Document
from documents.services.labels import (
    apply_manual_review_label,
    sync_classification_tags,
)
from documents.services.paperless import DocumentStore

UNKNOWN_ENTITY_LABEL = "Entidad pendiente de identificar"

CLASSIFICATION_REASON_CODES = {
    "missing_essential_fields",
    "unknown_language",
    "unknown_entity",
    "ambiguous_date",
    "low_confidence",
    "multiple_certificates",
    "non_certificate",
    "manual_label_failed",
    "equivalence_not_found",
}

SKIPPED_STATES = {
    Document.ProcessingState.CLASSIFIED.value,
    Document.ProcessingState.PENDING_REVIEW.value,
    Document.ProcessingState.APPROVED.value,
    Document.ProcessingState.REJECTED.value,
}

RUNNABLE_STATES = {Document.ProcessingState.EXTRACTED.value}

CEFR_TOKEN = re.compile(r"(?<![A-Za-z0-9])[ABC][12](?![A-Za-z0-9])", re.IGNORECASE)
SCORE_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")
NUMERIC_DATE = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$")
ISO_DATE = re.compile(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$")

EXPLICIT_DATE_FORMATS = (
    "%d %B %Y",
    "%d %b %Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d de %B de %Y",
    "%d.%m.%Y",
    "%d/%m/%Y",
    "%Y-%m-%d",
)


@dataclass(frozen=True)
class ClassificationResult:
    document: Document
    certificate: Certificate | None
    skipped: bool = False
    refused: bool = False
    error: str = ""
    state: str = ""
    review_reasons: tuple[str, ...] = ()


def _norm(value: str | None) -> str:
    return normalize_catalog_text(value or "")


def resolve_language(literal: str) -> Language | None:
    """Resolve a literal language name through catalog aliases, exact only."""
    normalized = _norm(literal)
    if not normalized:
        return None
    alias = (
        LanguageAlias.objects.filter(language__is_active=True)
        .select_related("language")
        .filter(normalized_alias=normalized)
        .first()
    )
    if alias is not None:
        return alias.language
    for language in Language.objects.filter(is_active=True):
        if _norm(language.name) == normalized or _norm(language.name_es) == normalized:
            return language
    return None


def resolve_entity(literal: str) -> Entity | None:
    """Resolve a literal entity name through catalog aliases, exact only."""
    normalized = _norm(literal)
    if not normalized:
        return None
    alias = (
        EntityAlias.objects.filter(entity__is_active=True)
        .select_related("entity")
        .filter(normalized_alias=normalized)
        .first()
    )
    if alias is not None:
        return alias.entity
    for entity in Entity.objects.filter(is_active=True):
        if _norm(entity.name) == normalized:
            return entity
    return None


def resolve_exam(literal: str, entity: Entity | None, language: Language | None) -> Exam | None:
    """Resolve an exam by normalized name, preferring the resolved entity."""
    normalized = _norm(literal)
    if not normalized:
        return None
    candidates = [
        exam
        for exam in Exam.objects.filter(is_active=True).select_related("entity", "language")
        if _norm(exam.name) == normalized
    ]
    if not candidates:
        return None
    if entity is not None:
        scoped = [exam for exam in candidates if exam.entity_id == entity.pk]
        if scoped:
            candidates = scoped
    if language is not None:
        scoped = [exam for exam in candidates if exam.language_id == language.pk]
        if scoped:
            candidates = scoped
    if len(candidates) == 1:
        return candidates[0]
    return None


def explicit_cefr(level_literal: str) -> str:
    """Return an explicit CEFR token printed in the level text, if any."""
    match = CEFR_TOKEN.search(_norm(level_literal))
    if match is None:
        return ""
    return match.group(0).upper()


def parse_score(value: str) -> Decimal | None:
    """Extract the first numeric score from a literal score string."""
    match = SCORE_NUMBER.search(value or "")
    if match is None:
        return None
    raw = match.group(0).replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def rule_cefr(certificate: Certificate) -> str:
    """Return the CEFR level from a single approved rule matching the score."""
    if certificate.exam_id is None:
        return ""
    score = parse_score(certificate.score_literal)
    if score is None:
        return ""
    levels = list(
        CefrConversionRule.objects.effective()
        .filter(
            exam_id=certificate.exam_id,
            score_min__lte=score,
            score_max__gte=score,
        )
        .values_list("cefr_level", flat=True)
        .distinct()
    )
    return levels[0] if len(levels) == 1 else ""


def _numeric_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_numeric_date(text: str) -> tuple[date | None, bool]:
    """Parse d/m/y style dates; flag ambiguous day/month ordering.

    Ambiguous dates are interpreted day-first so they can be stored as
    ``detected_date`` while still triggering review.
    """
    match = NUMERIC_DATE.match(text.strip())
    if match is None:
        return None, False
    first, second, year = (int(part) for part in match.groups())
    if len(match.group(3)) == 2:
        year += 2000 if year < 70 else 1900
    if first > 12:
        return _numeric_date(year, second, first), False
    if second > 12:
        return _numeric_date(year, first, second), False
    if first == second:
        return _numeric_date(year, first, second), False
    return _numeric_date(year, second, first), True


def _parse_iso_date(text: str) -> date | None:
    match = ISO_DATE.match(text.strip())
    if match is None:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date_text(text: str) -> tuple[date | None, bool]:
    """Return (date, ambiguous). Ambiguous means day/month cannot be decided."""
    cleaned = (text or "").strip()
    if not cleaned:
        return None, False
    iso = _parse_iso_date(cleaned)
    if iso is not None:
        return iso, False
    numeric, ambiguous = _parse_numeric_date(cleaned)
    if ambiguous and numeric is not None:
        return numeric, True
    if numeric is not None:
        return numeric, False
    for fmt in EXPLICIT_DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date(), False
        except ValueError:
            continue
    try:
        parsed = date_parser.parse(cleaned, dayfirst=True, fuzzy=False)
    except (ValueError, OverflowError):
        return None, True
    return parsed.date(), False


DATE_FIELD_BY_ROLE = {
    "issue": "issue_date",
    "exam": "exam_date",
    "result": "result_date",
    "unknown": "detected_date",
}

DATE_FIELDS = ("issue_date", "exam_date", "result_date", "detected_date")


def apply_dates(certificate: Certificate) -> list[str]:
    """Normalize extracted date candidates into typed date fields.

    Candidates whose role is ``unknown`` or whose day/month order is
    ambiguous are stored as ``detected_date`` (when the value itself is
    known) and always keep their original text in ``date_texts``.
    """
    reasons: list[str] = []
    date_texts = certificate.date_texts or {}
    candidates = date_texts.get("candidates") or []
    originals = dict(date_texts.get("originals") or {})
    manual = set(certificate.manual_fields or [])
    assigned: dict[str, date] = {}
    for field_name in DATE_FIELDS:
        if field_name not in manual:
            setattr(certificate, field_name, None)

    for candidate in candidates:
        text = str(candidate.get("text") or "").strip()
        if not text:
            continue
        role = str(candidate.get("role") or "unknown")
        field_name = DATE_FIELD_BY_ROLE.get(role, "detected_date")
        parsed, ambiguous = parse_date_text(text)

        if parsed is None:
            originals.setdefault("detected_date", text)
            if "ambiguous_date" not in reasons:
                reasons.append("ambiguous_date")
            continue

        if ambiguous or role == "unknown":
            field_name = "detected_date"
            if "ambiguous_date" not in reasons:
                reasons.append("ambiguous_date")

        if field_name in assigned or field_name in manual:
            continue
        assigned[field_name] = parsed
        originals[field_name] = text

    for field_name, value in assigned.items():
        setattr(certificate, field_name, value)
    certificate.date_texts = {**date_texts, "originals": originals}
    return reasons


def apply_cefr(certificate: Certificate) -> None:
    """Assign CEFR from an explicit statement or an approved rule."""
    explicit = explicit_cefr(certificate.level_literal)
    if explicit:
        certificate.cefr_level = explicit
        certificate.cefr_source = Certificate.CefrSource.EXPLICIT
        return
    level = rule_cefr(certificate)
    if level:
        certificate.cefr_level = level
        certificate.cefr_source = Certificate.CefrSource.APPROVED_RULE
        return
    certificate.cefr_level = ""
    certificate.cefr_source = ""


def matching_equivalence(certificate: Certificate, rules: list | None = None) -> Equivalence | None:
    """Return the UV L2 rule that determines the certificate's equivalence.

    Score-banded rules win over unbanded ones; unbanded rules act as a
    fallback. Returns None when no rule applies.
    """
    if certificate.exam_id is None:
        return None
    if rules is None:
        rules = list(Equivalence.objects.filter(exam_id=certificate.exam_id, is_active=True))
    score = parse_score(certificate.score_literal)
    if score is not None:
        for rule in rules:
            low_ok = rule.score_min is None or rule.score_min <= score
            high_ok = rule.score_max is None or score <= rule.score_max
            if (rule.score_min is not None or rule.score_max is not None) and low_ok and high_ok:
                return rule
    for rule in rules:
        if rule.score_min is None and rule.score_max is None:
            return rule
    return None


def apply_equivalence(certificate: Certificate) -> None:
    """Resolve the UV L2 accredited level from the matched exam."""
    certificate.equivalence = ""
    rule = matching_equivalence(certificate)
    if rule is not None:
        certificate.equivalence = rule.accredited_level


def equivalence_tooltip(certificate: Certificate, rules: list | None = None) -> str:
    """Human-readable explanation of how the equivalence was computed."""
    if certificate.exam_id is None:
        return "Sin examen asignado: no hay equivalencia que calcular."
    exam_name = certificate.exam.name if certificate.exam_id else certificate.exam_literal
    rule = matching_equivalence(certificate, rules)
    lines = [f"Examen: {exam_name}"]
    score_text = certificate.score_literal.strip() or "(sin puntuación)"
    lines.append(f"Puntuación del certificado: {score_text}")
    if rule is None:
        lines.append("Ninguna regla de la tabla UV L2 aplica a este examen/banda.")
        return "\n".join(lines)
    band = ""
    if rule.score_min is not None or rule.score_max is not None:
        band = f" (banda {rule.score_min if rule.score_min is not None else '−∞'}–{rule.score_max if rule.score_max is not None else '∞'})"
    else:
        band = " (regla general, sin banda)"
    lines.append(f"Regla aplicada{band}: {rule.exam.name} → {rule.accredited_level}")
    lines.append(f"Fuente: {rule.source}")
    return "\n".join(lines)


def aggregate_reasons(certificate: Certificate) -> list[str]:
    """Compute review reasons from the classified certificate."""
    reasons: list[str] = []
    if certificate.is_language_certificate is False:
        reasons.append("non_certificate")
    if certificate.multiple_certificates_suspected:
        reasons.append("multiple_certificates")
    if certificate.language_id is None and certificate.language_literal:
        reasons.append("unknown_language")
    if certificate.entity_id is None and certificate.entity_literal:
        reasons.append("unknown_entity")
    missing: list[str] = []
    if not certificate.student_name.strip():
        missing.append("student_name")
    if certificate.language_id is None:
        missing.append("language")
    if certificate.entity_id is None:
        missing.append("entity")
    if not certificate.level_literal.strip() and not certificate.score_literal.strip():
        missing.append("level_or_score")
    if certificate.issue_date is None:
        missing.append("issue_date")
    if certificate.exam_id is not None and not certificate.equivalence:
        reasons.append("equivalence_not_found")
    if missing:
        reasons.append("missing_essential_fields")
    confidence = certificate.confidence
    threshold = float(settings.APP["confidence_review_threshold"])
    if confidence is not None and confidence < threshold:
        reasons.append("low_confidence")
    return list(dict.fromkeys(reasons))


def _merge_reasons(existing: list, fresh: list[str]) -> list[str]:
    kept = [reason for reason in (existing or []) if reason not in CLASSIFICATION_REASON_CODES]
    merged = kept + [reason for reason in fresh if reason not in kept]
    return list(dict.fromkeys(merged))


def classify_certificate(
    document: Document,
    *,
    store: DocumentStore | None = None,
) -> ClassificationResult:
    """Classify an extracted certificate against the catalog, idempotently."""
    certificate = getattr(document, "certificate", None)
    if certificate is None:
        return ClassificationResult(
            document=document,
            certificate=None,
            refused=True,
            error="Document has no extracted certificate to classify",
        )

    if document.processing_state in SKIPPED_STATES:
        return ClassificationResult(
            document=document,
            certificate=certificate,
            skipped=True,
        )
    if document.processing_state not in RUNNABLE_STATES:
        return ClassificationResult(
            document=document,
            certificate=certificate,
            refused=True,
            error=(f"Classification requires extracted state, got {document.processing_state}"),
        )

    with transaction.atomic():
        manual = set(certificate.manual_fields or [])
        if "language" not in manual:
            certificate.language = resolve_language(certificate.language_literal)
        if "entity" not in manual:
            certificate.entity = resolve_entity(certificate.entity_literal)
        if "exam" not in manual:
            certificate.exam = resolve_exam(
                certificate.exam_literal, certificate.entity, certificate.language
            )
        if "cefr_level" not in manual:
            apply_cefr(certificate)
        if "equivalence" not in manual:
            apply_equivalence(certificate)
        date_reasons = apply_dates(certificate)
        reasons = aggregate_reasons(certificate) + date_reasons
        certificate.review_reasons = _merge_reasons(certificate.review_reasons, reasons)
        certificate.save()

        document.processing_state = Document.ProcessingState.PENDING_REVIEW.value
        document.review_reasons = _merge_reasons(document.review_reasons, reasons)
        document.error_reason = ""
        document.save()

    needs_label = (
        certificate.is_language_certificate is False
        or certificate.language_id is None
        or certificate.entity_id is None
    )
    if needs_label:
        apply_manual_review_label(document, store=store)
        document.refresh_from_db()
    sync_classification_tags(document, store=store)

    return ClassificationResult(
        document=document,
        certificate=certificate,
        state=document.processing_state,
        review_reasons=tuple(certificate.review_reasons or ()),
    )
