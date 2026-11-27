"""Field label alias lookup for extraction.

Aliases are stored per field and optionally scoped to a catalog entity.
Global aliases (``scope_entity`` null) apply to every document; scoped
aliases apply only when the document's certificate already resolved an
entity — i.e. on re-extract after classification.
"""

from __future__ import annotations

from django.db import IntegrityError

from catalog.models import Entity
from catalog.normalization import normalize_alias_text
from documents.models import Document, FieldLabelAlias

# Alias injection is capped so the prompt and fallbacks stay bounded.
MAX_ALIASES_PER_FIELD = 20


def aliases_for_document(document: Document) -> dict[str, list[str]]:
    """Active aliases applicable to this document, scoped entries first."""
    certificate = getattr(document, "certificate", None)
    entity_id = certificate.entity_id if certificate is not None else None
    return _aliases_for_entity(entity_id)


def aliases_for_fields() -> dict[str, list[str]]:
    """All active global aliases (admin/preview use)."""
    return _aliases_for_entity(None, include_scoped=False)


def _aliases_for_entity(
    entity_id: int | None, *, include_scoped: bool = True
) -> dict[str, list[str]]:
    queryset = FieldLabelAlias.objects.filter(is_active=True)
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
    """Create an alias idempotently. Returns (alias, message)."""
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
            created_by=actor,
        )
    except IntegrityError:
        return None, "Ya existe un alias igual para ese campo y alcance."
    return created, "Alias guardado."


def set_alias_active(alias: FieldLabelAlias, active: bool, actor) -> None:
    alias.is_active = active
    alias.save(update_fields=["is_active", "updated_at"])
