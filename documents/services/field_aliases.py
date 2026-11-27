"""Field label alias lookup, lifecycle, and corroboration for extraction.

Aliases are stored per field and optionally scoped to a catalog entity.
Global aliases (``scope_entity`` null) apply to every document; scoped
aliases apply when the document's certificate resolved that entity or when
issuer pre-detection matched it before extraction. Only ``active`` aliases
are used; ``candidate`` aliases await corroboration or reviewer
confirmation, and ``rejected`` aliases are never used.

Manual aliases are authoritative: they are created ``active`` and learned
aliases never auto-activate over an existing active alias.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from catalog.models import Entity
from catalog.normalization import normalize_alias_text
from documents.models import Document, FieldLabelAlias

# Alias injection is capped so the prompt and fallbacks stay bounded.
MAX_ALIASES_PER_FIELD = 20

ACTIVE = FieldLabelAlias.Lifecycle.ACTIVE
CANDIDATE = FieldLabelAlias.Lifecycle.CANDIDATE
REJECTED = FieldLabelAlias.Lifecycle.REJECTED


def _corroboration_min() -> int:
    return int(settings.APP.get("alias_corroboration_min", 2))


def _confidence(support_count: int, verified_count: int = 0) -> float:
    """Confidence from distinct observations; verified sightings add a
    bounded bonus without ever bypassing the corroboration threshold."""
    base = support_count / (support_count + 1)
    bonus = min(0.15, 0.05 * verified_count)
    return round(min(0.98, base + bonus), 3)


def _verified_count(provenance: dict[str, Any] | None) -> int:
    return int((provenance or {}).get("verified_observations") or 0)


def aliases_for_document(document: Document) -> dict[str, list[str]]:
    """Active aliases applicable to this document, scoped entries first."""
    certificate = getattr(document, "certificate", None)
    entity_id = certificate.entity_id if certificate is not None else None
    return _aliases_for_entity(entity_id)


def aliases_for_pre_detection(pre_detection: dict[str, Any] | None) -> dict[str, list[str]]:
    """Active aliases for a pre-detection match, before any certificate exists.

    Returns global aliases only when pre-detection is not a confident match,
    so scoped aliases are never applied speculatively.
    """
    entity_id = None
    if (pre_detection or {}).get("result") == "match":
        entity_id = pre_detection.get("entity_id")
    return _aliases_for_entity(entity_id)


def aliases_for_fields() -> dict[str, list[str]]:
    """All active global aliases (admin/preview use)."""
    return _aliases_for_entity(None, include_scoped=False)


def _aliases_for_entity(
    entity_id: int | None, *, include_scoped: bool = True
) -> dict[str, list[str]]:
    queryset = FieldLabelAlias.objects.filter(is_active=True, lifecycle=ACTIVE)
    global_aliases = queryset.filter(scope_entity__isnull=True)
    scoped = (
        queryset.filter(scope_entity_id=entity_id)
        if include_scoped and entity_id is not None
        else FieldLabelAlias.objects.none()
    )
    result: dict[str, list[str]] = {}
    for alias in list(scoped) + list(global_aliases):
        bucket = result.setdefault(alias.field, [])
        if alias.alias not in bucket and len(bucket) < MAX_ALIASES_PER_FIELD:
            bucket.append(alias.alias)
    return result


def teach_alias(
    *,
    field: str,
    alias: str,
    actor,
    scope_entity: Entity | None = None,
) -> tuple[FieldLabelAlias | None, str]:
    """Create a manual alias idempotently. Returns (alias, message)."""
    alias = (alias or "").strip()
    if not alias:
        return None, "El alias no puede estar vacío."
    if field not in FieldLabelAlias.Field.values:
        return None, "Campo de extracción inválido."
    normalized = normalize_alias_text(alias)
    scope_key = str(scope_entity.pk) if scope_entity else "global"
    exists = FieldLabelAlias.objects.filter(
        field=field, normalized_alias=normalized, scope_key=scope_key
    ).exists()
    if exists:
        return None, "Ya existe un alias igual para ese campo y alcance."
    try:
        created = FieldLabelAlias.objects.create(
            field=field,
            alias=alias,
            scope_entity=scope_entity,
            source=FieldLabelAlias.Source.MANUAL,
            lifecycle=ACTIVE,
            is_active=True,
            created_by=actor,
        )
    except IntegrityError:
        return None, "Ya existe un alias igual para ese campo y alcance."
    return created, "Alias guardado."


def set_alias_active(alias: FieldLabelAlias, active: bool, actor) -> None:
    alias.is_active = active
    alias.save(update_fields=["is_active", "updated_at"])


def _scope_key(scope_entity: Entity | None) -> str:
    return "global" if scope_entity is None else str(scope_entity.pk)


def _label_conflict(field: str, normalized: str, scope_key: str) -> bool:
    """True when the same printed label is already active for another field.

    A learned label that would map to two different fields in the same scope
    is ambiguous; the existing active alias keeps winning and the candidate
    must wait for a reviewer.
    """
    return (
        FieldLabelAlias.objects.filter(
            normalized_alias=normalized,
            scope_key=scope_key,
            lifecycle=ACTIVE,
            is_active=True,
        )
        .exclude(field=field)
        .exists()
    )


def _append_provenance(alias: FieldLabelAlias, entry: dict[str, Any]) -> None:
    provenance = dict(alias.provenance or {})
    observations = list(provenance.get("observations") or [])
    observations.append(entry)
    provenance["observations"] = observations[-50:]
    alias.provenance = provenance


def propose_alias_candidate(
    *,
    field: str,
    alias: str,
    scope_entity: Entity | None = None,
    provenance: dict[str, Any] | None = None,
    actor=None,
) -> tuple[FieldLabelAlias | None, str]:
    """Record a learned alias observation as a candidate.

    Returns (alias_or_none, outcome) where outcome is one of ``created``,
    ``corroborated``, ``conflict``, ``rejected``, ``exists``, or ``invalid``.
    Candidates activate only after ``APP_ALIAS_CORROBORATION_MIN`` distinct
    observations without a label conflict; manual aliases are never touched.
    """
    alias = (alias or "").strip()
    if not alias:
        return None, "invalid"
    if field not in FieldLabelAlias.Field.values:
        return None, "invalid"
    normalized = normalize_alias_text(alias)
    scope_key = _scope_key(scope_entity)
    observation = dict(provenance or {})
    observation.setdefault("observed_at", timezone.now().isoformat())

    with transaction.atomic():
        existing = (
            FieldLabelAlias.objects.select_for_update()
            .filter(field=field, normalized_alias=normalized, scope_key=scope_key)
            .first()
        )
        if existing is not None:
            if existing.lifecycle == REJECTED:
                return None, "rejected"
            if existing.lifecycle == ACTIVE:
                # Manual/active authority: record the sighting but change
                # nothing that affects extraction.
                _append_provenance(existing, observation)
                existing.support_count = (existing.support_count or 0) + 1
                if observation.get("verified"):
                    prov = existing.provenance or {}
                    prov["verified_observations"] = _verified_count(prov) + 1
                    existing.provenance = prov
                existing.confidence = _confidence(
                    existing.support_count, _verified_count(existing.provenance)
                )
                existing.save(
                    update_fields=["provenance", "support_count", "confidence", "updated_at"]
                )
                return existing, "exists"
            # Candidate: corroborate.
            cert_id = observation.get("certificate_id")
            known = {
                obs.get("certificate_id")
                for obs in (existing.provenance or {}).get("observations", [])
            }
            if cert_id is not None and cert_id in known:
                return existing, "exists"
            existing.support_count = (existing.support_count or 0) + 1
            if observation.get("verified"):
                prov = existing.provenance or {}
                prov["verified_observations"] = _verified_count(prov) + 1
                existing.provenance = prov
            existing.confidence = _confidence(
                existing.support_count, _verified_count(existing.provenance)
            )
            _append_provenance(existing, observation)
            conflict = _label_conflict(field, normalized, scope_key)
            if conflict:
                existing.provenance = {
                    **(existing.provenance or {}),
                    "conflict": True,
                }
                existing.save(
                    update_fields=[
                        "support_count",
                        "confidence",
                        "provenance",
                        "updated_at",
                    ]
                )
                return existing, "conflict"
            if existing.support_count >= _corroboration_min():
                existing.lifecycle = ACTIVE
                existing.is_active = True
                existing.save(
                    update_fields=[
                        "lifecycle",
                        "is_active",
                        "support_count",
                        "confidence",
                        "provenance",
                        "updated_at",
                    ]
                )
                return existing, "corroborated"
            existing.save(update_fields=["support_count", "confidence", "provenance", "updated_at"])
            return existing, "candidate"

        conflict = _label_conflict(field, normalized, scope_key)
        initial_provenance = {"observations": [observation], "conflict": conflict}
        if observation.get("verified"):
            initial_provenance["verified_observations"] = 1
        candidate = FieldLabelAlias.objects.create(
            field=field,
            alias=alias,
            scope_entity=scope_entity,
            source=FieldLabelAlias.Source.LEARNED,
            lifecycle=CANDIDATE,
            is_active=False,
            support_count=1,
            confidence=_confidence(1, 1 if observation.get("verified") else 0),
            provenance=initial_provenance,
            created_by=actor,
        )
        if conflict:
            return candidate, "conflict"
        if candidate.support_count >= _corroboration_min():
            candidate.lifecycle = ACTIVE
            candidate.is_active = True
            candidate.save(update_fields=["lifecycle", "is_active", "updated_at"])
            return candidate, "corroborated"
        return candidate, "created"


def set_alias_lifecycle(alias: FieldLabelAlias, lifecycle: str, actor) -> tuple[bool, str]:
    """Reviewer-driven lifecycle transition. Returns (ok, message)."""
    if lifecycle not in FieldLabelAlias.Lifecycle.values:
        return False, "Estado inválido."
    alias.lifecycle = lifecycle
    alias.is_active = lifecycle == ACTIVE
    alias.provenance = {
        **(alias.provenance or {}),
        "last_transition": {
            "to": lifecycle,
            "actor": str(getattr(actor, "username", actor) or ""),
            "at": timezone.now().isoformat(),
        },
    }
    alias.save(update_fields=["lifecycle", "is_active", "provenance", "updated_at"])
    return True, "Alias actualizado."


# Certificate edit fields that map to an alias-able extraction field.
_EDIT_TO_ALIAS_FIELD = {
    "student_name": "student_name",
    "language_literal": "language",
    "entity_literal": "entity",
    "issuing_body_literal": "issuing_body",
    "test_center_literal": "test_center",
    "exam_literal": "exam",
    "level_literal": "level",
    "score_literal": "score",
    "certificate_code": "certificate_code",
}

_LABEL_MAX_LEN = 60


def _looks_like_label(text: str) -> bool:
    text = text.strip(" \t:;.-–—·|")
    if not 2 <= len(text) <= _LABEL_MAX_LEN:
        return False
    if any(ch.isdigit() for ch in text):
        return False
    letters = sum(ch.isalpha() for ch in text)
    return letters >= max(2, len(text) // 3)


def _printed_label_for_value(document, value: str) -> str | None:
    """Find a plausible printed label adjacent to a corrected value.

    Checks the same line before the value, then the previous non-empty
    line. Returns the label text or None when nothing label-like exists.
    """
    from documents.services.extraction import _norm_text

    needle = _norm_text(value)
    if not needle:
        return None
    for page in document.pages.order_by("page_number"):
        lines = (page.text or "").splitlines()
        for index, raw in enumerate(lines):
            folded = _norm_text(raw)
            pos = folded.find(needle)
            if pos < 0:
                continue
            # Same-line prefix: take raw text up to the value's position.
            # Folded/raw lengths can differ slightly; approximate by
            # searching the raw line case-insensitively for the value.
            lowered = raw.casefold()
            raw_pos = lowered.find(value.strip().casefold())
            if raw_pos > 0:
                prefix = raw[:raw_pos].strip(" \t:;.-–—·|")
                if _looks_like_label(prefix):
                    return prefix
            for prev in range(index - 1, max(index - 4, -1), -1):
                candidate = lines[prev].strip()
                if not candidate:
                    continue
                if _looks_like_label(candidate):
                    return candidate
                return None
    return None


def propose_correction_aliases(certificate, edits: dict[str, Any], actor) -> list[str]:
    """Propose candidate aliases for corrected literal fields.

    For each edited literal field whose printed label is identifiable in
    the document text, records a learned candidate scoped to the
    certificate's entity. Candidates never activate without corroboration
    or reviewer confirmation. Returns human-readable notes.
    """
    notes: list[str] = []
    document = certificate.document
    for edit_field, alias_field in _EDIT_TO_ALIAS_FIELD.items():
        new_value = edits.get(edit_field)
        if not isinstance(new_value, str) or not new_value.strip():
            continue
        label = _printed_label_for_value(document, new_value)
        if label is None:
            continue
        _alias, outcome = propose_alias_candidate(
            field=alias_field,
            alias=label,
            scope_entity=certificate.entity,
            provenance={
                "source": "review_correction",
                "certificate_id": certificate.pk,
                "edit_field": edit_field,
                "actor": str(getattr(actor, "username", actor) or ""),
            },
            actor=actor,
        )
        if outcome in {"created", "corroborated", "candidate", "conflict"}:
            notes.append(
                f"Se propuso el alias candidato «{label}» para {alias_field} "
                "(pendiente de corroboración o confirmación)."
            )
    return notes
