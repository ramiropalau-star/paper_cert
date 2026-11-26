"""Resolve printed catalog literals to catalog entries from the review UI.

Assigns the resolved foreign key, preserves the printed literal, registers
the literal as an alias (idempotent on ``normalized_alias``), writes an audit
``ReviewEvent``, freezes the field against re-extraction, and optionally
re-runs classification so dependent fields and review reasons refresh.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction

from catalog.models import (
    Entity,
    EntityAlias,
    Exam,
    ExamAlias,
    Language,
    LanguageAlias,
)
from catalog.normalization import normalize_catalog_text
from documents.models import Certificate, Document, ReviewEvent
from documents.services.reclassification import reclassify_document

# field -> (fk attribute, literal attribute, target model, alias model)
FIELD_SPECS = {
    "entity": ("entity", "entity_literal", Entity, EntityAlias),
    "exam": ("exam", "exam_literal", Exam, ExamAlias),
    "language": ("language", "language_literal", Language, LanguageAlias),
}


@dataclass
class ResolutionOutcome:
    ok: bool
    error: str = ""
    alias_conflict: str = ""
    reclassified: bool = False
    reclassify_error: str = ""
    details: dict = field(default_factory=dict)


def unresolved_catalog_fields(certificate: Certificate | None) -> list[str]:
    """Catalog fields whose printed literal is set but FK is unresolved."""
    if certificate is None:
        return []
    fields = []
    for name, (fk_attr, literal_attr, _model, _alias) in FIELD_SPECS.items():
        literal = (getattr(certificate, literal_attr) or "").strip()
        if literal and getattr(certificate, fk_attr + "_id") is None:
            fields.append(name)
    return fields


def _alias_owner_id(alias, fk_attr: str) -> int | None:
    return getattr(alias, fk_attr + "_id", None)


def resolve_catalog_field(
    certificate: Certificate,
    field_name: str,
    target,
    actor,
    *,
    reclassify: bool = True,
) -> ResolutionOutcome:
    """Assign ``target`` to ``certificate.<field>`` with alias + audit."""
    spec = FIELD_SPECS.get(field_name)
    if spec is None:
        return ResolutionOutcome(ok=False, error="Campo de catálogo no resoluble.")
    fk_attr, literal_attr, model, alias_model = spec
    if not isinstance(target, model):
        return ResolutionOutcome(ok=False, error="Destino de catálogo no válido.")

    literal = " ".join((getattr(certificate, literal_attr) or "").split())
    normalized = normalize_catalog_text(literal)
    alias_conflict = ""

    with transaction.atomic():
        old_owner = getattr(certificate, fk_attr)
        before_id = old_owner.pk if old_owner is not None else None
        setattr(certificate, fk_attr, target)
        manual = set(certificate.manual_fields or [])
        manual.add(fk_attr)
        certificate.manual_fields = sorted(manual)
        certificate.save(update_fields=[fk_attr, "manual_fields", "updated_at"])

        owner_name = getattr(target, "name", "")
        if normalized and normalized != normalize_catalog_text(owner_name):
            alias_obj, created = alias_model.objects.get_or_create(
                normalized_alias=normalized,
                defaults={fk_attr: target, "alias": literal},
            )
            if not created and _alias_owner_id(alias_obj, fk_attr) != target.pk:
                alias_conflict = literal

        after = {fk_attr: target.pk}
        if alias_conflict:
            after["alias_conflict"] = alias_conflict
        ReviewEvent.objects.create(
            certificate=certificate,
            event_type=ReviewEvent.EventType.EDIT,
            actor=actor,
            reason=f"Resolución de catálogo: {field_name}",
            before={fk_attr: before_id},
            after=after,
        )

    outcome = ResolutionOutcome(ok=True, alias_conflict=alias_conflict)
    if reclassify:
        _maybe_reclassify(certificate, outcome)
    return outcome


def _maybe_reclassify(certificate: Certificate, outcome: ResolutionOutcome) -> None:
    document = certificate.document
    if document.processing_state != Document.ProcessingState.PENDING_REVIEW:
        return
    result = reclassify_document(document)
    if result.error:
        outcome.reclassify_error = result.error
    elif result.refused:
        outcome.reclassify_error = result.error or "classification refused"
    else:
        outcome.reclassified = True
