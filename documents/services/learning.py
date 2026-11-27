"""Review-driven catalog learning.

Turns human-verified review decisions into durable catalog knowledge:
aliases for printed literals, equivalence rules, and CEFR conversion rule
candidates. Learning only ever adds rows; it never modifies or deactivates
existing catalog entries, and it is idempotent across re-approvals.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from catalog.models import (
    CefrConversionRule,
    CefrLevel,
    EntityAlias,
    Equivalence,
    Exam,
    ExamAlias,
    LanguageAlias,
)
from catalog.normalization import normalize_catalog_text
from documents.models import Certificate
from documents.services.classification import parse_score

ALIAS_SPECS = (
    ("language_literal", "language", LanguageAlias, "language"),
    ("entity_literal", "entity", EntityAlias, "entity"),
    ("exam_literal", "exam", ExamAlias, "exam"),
)


def _normalized(value: str) -> str:
    return normalize_catalog_text(value or "")


def _learn_aliases(certificate: Certificate, outcome: dict[str, Any]) -> None:
    for literal_field, fk_field, alias_model, owner_field in ALIAS_SPECS:
        literal = (getattr(certificate, literal_field) or "").strip()
        owner = getattr(certificate, fk_field)
        if not literal or owner is None:
            continue
        normalized = _normalized(literal)
        if not normalized:
            continue
        owner_name = getattr(owner, "name", "")
        if normalized == _normalized(owner_name):
            continue
        existing = alias_model.objects.filter(normalized_alias=normalized).first()
        if existing is not None:
            if getattr(existing, owner_field + "_id") != owner.pk:
                outcome["conflicts"].append(
                    {
                        "kind": "alias",
                        "literal": literal,
                        "normalized": normalized,
                        "existing": str(existing),
                    }
                )
            continue
        alias_model.objects.create(**{owner_field: owner, "alias": literal})
        outcome["aliases_created"].append(f"{literal} -> {owner_name}")


def _learn_exam(certificate: Certificate, outcome: dict[str, Any]) -> None:
    """Create an Exam for an unambiguous literal under a resolved entity.

    Only fires when the entity (and optionally language) resolved, no exam
    was matched, and the literal is non-empty. The literal becomes the exam
    name; exact-name matching covers it without a separate alias.
    """
    if certificate.exam_id is not None or certificate.entity_id is None:
        return
    literal = (certificate.exam_literal or "").strip()
    if not literal:
        return
    name = " ".join(literal.split())
    normalized = _normalized(name)
    clash = (
        Exam.objects.filter(entity_id=certificate.entity_id, is_active=True)
        .filter(name__iexact=name)
        .exists()
    )
    if clash or not normalized:
        return
    Exam.objects.create(
        name=name,
        entity_id=certificate.entity_id,
        language_id=certificate.language_id,
    )
    outcome["exams_created"].append(name)


def _learn_equivalence(certificate: Certificate, outcome: dict[str, Any]) -> None:
    """Record an unbanded UV L2 equivalence for the exam when none exists."""
    if certificate.exam_id is None:
        return
    level = (certificate.equivalence or "").strip()
    if level not in CefrLevel.values:
        return
    exists = Equivalence.objects.filter(
        exam_id=certificate.exam_id, accredited_level=level
    ).exists()
    if exists:
        return
    Equivalence.objects.create(
        exam_id=certificate.exam_id,
        accredited_level=level,
        source="review",
        label=(certificate.certificate_code or "")[:200],
        is_active=True,
    )
    outcome["equivalences_created"].append(f"{certificate.exam.name} -> {level}")


def _learn_cefr_rule(certificate: Certificate, actor, outcome: dict[str, Any]) -> None:
    """Record an inactive CEFR conversion rule candidate from a manual fix.

    The band is the exact observed score; a human must widen it and activate
    the rule (the model's own validation requires approver + reference).
    """
    if certificate.cefr_source != Certificate.CefrSource.MANUAL:
        return
    if certificate.exam_id is None or not certificate.cefr_level:
        return
    score = parse_score(certificate.score_literal)
    if score is None:
        return
    reference = f"review:certificate:{certificate.pk}"
    exists = CefrConversionRule.objects.filter(
        exam_id=certificate.exam_id,
        score_min=score,
        score_max=score,
        cefr_level=certificate.cefr_level,
        reference=reference,
    ).exists()
    if exists:
        return
    CefrConversionRule.objects.create(
        exam_id=certificate.exam_id,
        score_min=score,
        score_max=score,
        cefr_level=certificate.cefr_level,
        approved_by=str(getattr(actor, "username", actor) or "")[:200],
        approved_at=timezone.now(),
        reference=reference,
        is_active=False,
    )
    outcome["cefr_rules_created"].append(
        f"{certificate.exam.name} {score} -> {certificate.cefr_level} (inactive)"
    )


def learn_from_certificate(certificate: Certificate, actor) -> dict[str, Any]:
    """Learn catalog knowledge from an approved/validated certificate.

    Idempotent: re-running on the same certificate creates nothing new.
    Returns a summary dict for audit purposes.
    """
    outcome: dict[str, Any] = {
        "aliases_created": [],
        "exams_created": [],
        "equivalences_created": [],
        "cefr_rules_created": [],
        "conflicts": [],
    }
    with transaction.atomic():
        _learn_exam(certificate, outcome)
        _learn_aliases(certificate, outcome)
        _learn_equivalence(certificate, outcome)
        _learn_cefr_rule(certificate, actor, outcome)
    return outcome
