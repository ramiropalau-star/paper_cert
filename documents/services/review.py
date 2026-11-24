"""Review workflow: edit, approve, reject, and reprocess certificates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from django.db import transaction

from documents.models import Certificate, Document, ReviewEvent
from documents.services.labels import (
    remove_manual_review_label,
    sync_classification_tags,
)
from documents.services.n8n import notify_processing
from documents.services.paperless import DocumentStore

EDITABLE_FIELDS = (
    "student_name",
    "language_literal",
    "entity_literal",
    "issuing_body_literal",
    "test_center_literal",
    "exam_literal",
    "level_literal",
    "score_literal",
    "certificate_code",
    "cefr_level",
    "equivalence",
    "issue_date",
    "exam_date",
    "result_date",
    "detected_date",
    "language_id",
    "entity_id",
    "exam_id",
)

FOREIGN_KEY_FIELDS = {"language_id": "language", "entity_id": "entity", "exam_id": "exam"}

REQUIRED_FOR_APPROVAL = (
    ("student_name", "nombre del alumno"),
    ("language_id", "idioma"),
    ("entity_id", "entidad certificadora"),
    ("level_or_score", "nivel o puntuación"),
    ("issue_date", "fecha de expedición"),
)


@dataclass(frozen=True)
class ReviewOutcome:
    ok: bool
    error: str = ""
    missing: tuple[str, ...] = ()


def _serialize(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "pk"):
        return f"{value._meta.label}:{value.pk}"
    return value


def snapshot_certificate(certificate: Certificate) -> dict[str, Any]:
    return {
        field: _serialize(getattr(certificate, field))
        for field in EDITABLE_FIELDS
        if field in {f.name for f in certificate._meta.fields}
    }


def _apply_edit(certificate: Certificate, cleaned: dict[str, Any]) -> dict[str, Any]:
    """Apply validated values, returning {field: {"before":…, "after":…}}."""
    changes: dict[str, Any] = {}
    for field, new_value in cleaned.items():
        if field not in EDITABLE_FIELDS:
            continue
        attribute = FOREIGN_KEY_FIELDS.get(field, field)
        old_value = getattr(certificate, attribute)
        old_serialized = _serialize(old_value)
        new_serialized = _serialize(new_value)
        if old_serialized == new_serialized:
            continue
        setattr(certificate, attribute, new_value)
        changes[field] = {"before": old_serialized, "after": new_serialized}
    if "cefr_level" in changes:
        certificate.cefr_source = Certificate.CefrSource.MANUAL
    return changes


def apply_manual_edit(
    certificate: Certificate,
    cleaned: dict[str, Any],
    actor,
) -> ReviewOutcome:
    """Validate and persist manual edits with an audit event."""
    with transaction.atomic():
        changes = _apply_edit(certificate, cleaned)
        if not changes:
            return ReviewOutcome(ok=True)
        manual = set(certificate.manual_fields or [])
        manual.update(FOREIGN_KEY_FIELDS.get(field, field) for field in changes)
        certificate.manual_fields = sorted(manual)
        certificate.save()
        ReviewEvent.objects.create(
            certificate=certificate,
            event_type=ReviewEvent.EventType.EDIT,
            actor=actor,
            before={field: changes[field]["before"] for field in changes},
            after={field: changes[field]["after"] for field in changes},
        )
    sync_classification_tags(certificate.document)
    return ReviewOutcome(ok=True)


RELEASABLE_FIELDS = {FOREIGN_KEY_FIELDS.get(field, field) for field in EDITABLE_FIELDS}

FIELD_LABELS = {
    "student_name": "Alumno",
    "language_literal": "Idioma (texto)",
    "language": "Idioma (catálogo)",
    "entity_literal": "Entidad (texto)",
    "entity": "Entidad (catálogo)",
    "issuing_body_literal": "Organismo emisor",
    "test_center_literal": "Centro de examen",
    "exam_literal": "Examen (texto)",
    "exam": "Examen (catálogo)",
    "level_literal": "Nivel literal",
    "score_literal": "Puntuación",
    "certificate_code": "Código",
    "cefr_level": "Nivel MCER",
    "equivalence": "Equivalencia UV L2",
    "issue_date": "Fecha de expedición",
    "exam_date": "Fecha de examen",
    "result_date": "Fecha de resultado",
    "detected_date": "Fecha detectada",
}


def release_manual_field(certificate: Certificate, actor, field: str) -> ReviewOutcome:
    """Unfreeze a manually edited field so reprocessing can overwrite it."""
    if field not in RELEASABLE_FIELDS:
        return ReviewOutcome(ok=False, error="Campo no liberable.")
    manual = list(certificate.manual_fields or [])
    if field not in manual:
        return ReviewOutcome(ok=True)
    manual.remove(field)
    with transaction.atomic():
        certificate.manual_fields = manual
        certificate.save(update_fields=["manual_fields", "updated_at"])
        ReviewEvent.objects.create(
            certificate=certificate,
            event_type=ReviewEvent.EventType.EDIT,
            actor=actor,
            reason="Liberación de campo protegido",
            before={"manual_fields": manual + [field]},
            after={"manual_fields": manual},
        )
    return ReviewOutcome(ok=True)


def missing_required_fields(certificate: Certificate) -> list[str]:
    missing: list[str] = []
    checks = {
        "student_name": bool(certificate.student_name.strip()),
        "language_id": certificate.language_id is not None,
        "entity_id": certificate.entity_id is not None,
        "level_or_score": bool(
            certificate.level_literal.strip() or certificate.score_literal.strip()
        ),
        "issue_date": certificate.issue_date is not None,
    }
    for field, _label in REQUIRED_FOR_APPROVAL:
        if not checks[field]:
            missing.append(field)
    return missing


def approve_certificate(
    certificate: Certificate, actor, *, store: DocumentStore | None = None
) -> ReviewOutcome:
    missing = missing_required_fields(certificate)
    if missing:
        labels = [label for field, label in REQUIRED_FOR_APPROVAL if field in missing]
        return ReviewOutcome(
            ok=False,
            error="Faltan campos obligatorios: " + ", ".join(labels),
            missing=tuple(missing),
        )
    with transaction.atomic():
        before = {
            "review_status": certificate.review_status,
            "processing_state": certificate.document.processing_state,
        }
        certificate.review_status = Certificate.ReviewStatus.APPROVED
        certificate.save(update_fields=["review_status", "updated_at"])
        document = certificate.document
        document.processing_state = Document.ProcessingState.APPROVED
        document.save(update_fields=["processing_state", "updated_at"])
        ReviewEvent.objects.create(
            certificate=certificate,
            event_type=ReviewEvent.EventType.APPROVE,
            actor=actor,
            before=before,
            after={
                "review_status": Certificate.ReviewStatus.APPROVED,
                "processing_state": Document.ProcessingState.APPROVED,
            },
        )
    remove_manual_review_label(document, store=store)
    return ReviewOutcome(ok=True)


def validate_certificate(certificate: Certificate, actor) -> ReviewOutcome:
    """Mark a manually reviewed certificate as validated.

    Validation records that a human checked the extracted values; the
    document remains in ``pending_review`` until it is approved for reports.
    """
    if certificate.review_status == Certificate.ReviewStatus.REJECTED:
        return ReviewOutcome(ok=False, error="No se puede validar un registro rechazado.")
    if certificate.review_status == Certificate.ReviewStatus.APPROVED:
        return ReviewOutcome(ok=False, error="El registro ya está aprobado.")
    if certificate.review_status == Certificate.ReviewStatus.VALIDATED:
        return ReviewOutcome(ok=True)
    with transaction.atomic():
        before = {"review_status": certificate.review_status}
        certificate.review_status = Certificate.ReviewStatus.VALIDATED
        certificate.save(update_fields=["review_status", "updated_at"])
        ReviewEvent.objects.create(
            certificate=certificate,
            event_type=ReviewEvent.EventType.VALIDATE,
            actor=actor,
            before=before,
            after={"review_status": Certificate.ReviewStatus.VALIDATED},
        )
    return ReviewOutcome(ok=True)


def reject_certificate(
    certificate: Certificate,
    actor,
    reason: str,
) -> ReviewOutcome:
    reason = (reason or "").strip()
    if not reason:
        return ReviewOutcome(ok=False, error="El motivo de rechazo es obligatorio.")
    with transaction.atomic():
        before = {
            "review_status": certificate.review_status,
            "processing_state": certificate.document.processing_state,
        }
        certificate.review_status = Certificate.ReviewStatus.REJECTED
        certificate.save(update_fields=["review_status", "updated_at"])
        document = certificate.document
        document.processing_state = Document.ProcessingState.REJECTED
        document.save(update_fields=["processing_state", "updated_at"])
        ReviewEvent.objects.create(
            certificate=certificate,
            event_type=ReviewEvent.EventType.REJECT,
            actor=actor,
            reason=reason,
            before=before,
            after={
                "review_status": Certificate.ReviewStatus.REJECTED,
                "processing_state": Document.ProcessingState.REJECTED,
            },
        )
    return ReviewOutcome(ok=True)


def reprocess_document(
    document: Document, actor, *, store: DocumentStore | None = None
) -> ReviewOutcome:
    """Reset the document for a new pipeline run, preserving history."""
    certificate = getattr(document, "certificate", None)
    with transaction.atomic():
        before = {
            "processing_state": document.processing_state,
            "review_status": (certificate.review_status if certificate is not None else ""),
        }
        document.processing_state = Document.ProcessingState.STORED
        document.error_reason = ""
        document.save(update_fields=["processing_state", "error_reason", "updated_at"])
        if certificate is not None:
            certificate.review_status = Certificate.ReviewStatus.PENDING
            certificate.save(update_fields=["review_status", "updated_at"])
            ReviewEvent.objects.create(
                certificate=certificate,
                event_type=ReviewEvent.EventType.REPROCESS,
                actor=actor,
                before=before,
                after={
                    "processing_state": Document.ProcessingState.STORED,
                    "review_status": Certificate.ReviewStatus.PENDING,
                },
            )
    notify_processing(document)
    return ReviewOutcome(ok=True)
