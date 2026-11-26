"""Catalog administration UI: review and edit UV L2 equivalences."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from catalog.models import (
    CefrLevel,
    Entity,
    EntityAlias,
    Equivalence,
    Exam,
    Language,
)
from catalog.normalization import normalize_catalog_text
from core.permissions import (
    ROLE_REVIEWER,
    ROLE_VIEWER,
    can_review_documents,
    role_required,
)
from documents.models import Document
from documents.services.catalog_resolution import (
    FIELD_SPECS,
    ResolutionOutcome,
    resolve_catalog_field,
    unresolved_catalog_fields,
)

FIELD_LABELS = {
    "entity": "Entidad certificadora",
    "exam": "Examen",
    "language": "Idioma",
}


def _safe_next(request) -> str:
    """Return a validated in-app ``next`` path or an empty string."""
    nxt = request.POST.get("next", "") or request.GET.get("next", "")
    return nxt if nxt.startswith("/catalog/") else ""


def _parse_decimal(value: str) -> Decimal | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation:
        return None


@login_required
@role_required(ROLE_VIEWER)
@require_http_methods(["GET"])
def equivalence_table(request):
    entities = (
        Entity.objects.filter(is_active=True)
        .prefetch_related(
            "exams__equivalences",
            "exams__language",
            "aliases",
        )
        .order_by("name")
    )
    return render(
        request,
        "catalog/equivalences.html",
        {
            "entities": entities,
            "levels": CefrLevel.choices,
            "can_edit": can_review_documents(request.user),
        },
    )


@login_required
@role_required(ROLE_REVIEWER)
@require_POST
def equivalence_update(request, pk: int):
    equivalence = get_object_or_404(Equivalence, pk=pk)
    level = request.POST.get("accredited_level", "")
    score_min = _parse_decimal(request.POST.get("score_min", ""))
    score_max = _parse_decimal(request.POST.get("score_max", ""))
    is_active = request.POST.get("is_active") == "on"

    if level not in CefrLevel.values:
        messages.error(request, "Nivel MCER no válido.")
        return redirect(_safe_next(request) or reverse("catalog:equivalences"))
    if score_min is not None and score_max is not None and score_max < score_min:
        messages.error(request, "La banda mínima no puede ser mayor que la máxima.")
        return redirect(_safe_next(request) or reverse("catalog:equivalences"))

    equivalence.accredited_level = level
    equivalence.score_min = score_min
    equivalence.score_max = score_max
    equivalence.is_active = is_active
    equivalence.save()
    messages.success(request, f"Equivalencia #{equivalence.pk} actualizada.")
    return redirect(_safe_next(request) or reverse("catalog:equivalences"))


@login_required
@role_required(ROLE_REVIEWER)
@require_POST
def equivalence_add(request, exam_id: int):
    exam = get_object_or_404(Exam, pk=exam_id)
    level = request.POST.get("accredited_level", "")
    score_min = _parse_decimal(request.POST.get("score_min", ""))
    score_max = _parse_decimal(request.POST.get("score_max", ""))

    if level not in CefrLevel.values:
        messages.error(request, "Nivel MCER no válido.")
        return redirect(_safe_next(request) or reverse("catalog:equivalences"))
    if score_min is not None and score_max is not None and score_max < score_min:
        messages.error(request, "La banda mínima no puede ser mayor que la máxima.")
        return redirect(_safe_next(request) or reverse("catalog:equivalences"))

    Equivalence.objects.create(
        exam=exam,
        accredited_level=level,
        score_min=score_min,
        score_max=score_max,
        source=request.POST.get("source", "").strip() or "Manual",
    )
    messages.success(request, f"Equivalencia añadida a {exam.name}.")
    return redirect(_safe_next(request) or reverse("catalog:equivalences"))


@login_required
@role_required(ROLE_REVIEWER)
@require_http_methods(["GET", "POST"])
def entity_create(request):
    if request.method == "POST":
        entity_name = request.POST.get("entity_name", "").strip()
        exam_name = request.POST.get("exam_name", "").strip()
        language_id = request.POST.get("language", "")
        aliases_raw = request.POST.get("entity_aliases", "")

        errors = []
        if not entity_name:
            errors.append("El nombre de la entidad es obligatorio.")
        if not exam_name:
            errors.append("El nombre del examen es obligatorio.")
        language = None
        if language_id:
            language = Language.objects.filter(pk=language_id, is_active=True).first()
            if language is None:
                errors.append("Idioma no válido.")

        # Parse equivalence rows: repeated fields eq_level[], eq_min[], eq_max[]
        levels = request.POST.getlist("eq_level")
        mins = request.POST.getlist("eq_min")
        maxs = request.POST.getlist("eq_max")
        eq_rows = []
        for level, raw_min, raw_max in zip(levels, mins, maxs, strict=False):
            level = level.strip()
            if not level:
                continue
            if level not in CefrLevel.values:
                errors.append(f"Nivel MCER no válido en una equivalencia: {level}")
                continue
            eq_min = _parse_decimal(raw_min)
            eq_max = _parse_decimal(raw_max)
            if eq_min is not None and eq_max is not None and eq_max < eq_min:
                errors.append("Una equivalencia tiene banda mínima mayor que la máxima.")
                continue
            eq_rows.append((level, eq_min, eq_max))

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            with transaction.atomic():
                entity, _ = Entity.objects.get_or_create(name=entity_name)
                for alias in aliases_raw.split(","):
                    alias = alias.strip()
                    if alias:
                        EntityAlias.objects.get_or_create(
                            normalized_alias=normalize_catalog_text(alias),
                            defaults={"entity": entity, "alias": alias},
                        )
                exam, _ = Exam.objects.get_or_create(
                    entity=entity,
                    name=exam_name,
                    defaults={"language": language},
                )
                if exam.language_id is None and language is not None:
                    exam.language = language
                    exam.save(update_fields=["language"])
                for level, eq_min, eq_max in eq_rows:
                    Equivalence.objects.create(
                        exam=exam,
                        accredited_level=level,
                        score_min=eq_min,
                        score_max=eq_max,
                        source="Manual",
                    )
            messages.success(
                request,
                f"Entidad '{entity_name}' con examen '{exam_name}' "
                f"y {len(eq_rows)} equivalencias creada.",
            )
            return redirect(_safe_next(request) or reverse("catalog:equivalences"))

    return render(
        request,
        "catalog/entity_form.html",
        {
            "languages": Language.objects.filter(is_active=True),
            "levels": CefrLevel.choices,
        },
    )


def _entity_detail_url(entity: Entity) -> str:
    return reverse("catalog:entity_detail", args=[entity.pk])


@login_required
@role_required(ROLE_VIEWER)
@require_http_methods(["GET"])
def entity_detail(request, pk: int):
    entity = get_object_or_404(
        Entity.objects.prefetch_related(
            "aliases",
            "exams__aliases",
            "exams__equivalences",
            "exams__language",
        ),
        pk=pk,
    )
    return render(
        request,
        "catalog/entity_detail.html",
        {
            "entity": entity,
            "can_edit": can_review_documents(request.user),
            "languages": Language.objects.filter(is_active=True),
            "levels": CefrLevel.choices,
            "date_orders": Entity.DateOrder.choices,
        },
    )


@login_required
@role_required(ROLE_REVIEWER)
@require_POST
def entity_update(request, pk: int):
    entity = get_object_or_404(Entity, pk=pk)
    date_order = request.POST.get("date_order", "")
    if date_order not in {"", *Entity.DateOrder.values}:
        messages.error(request, "Orden de fecha no válido.")
        return redirect(_safe_next(request) or _entity_detail_url(entity))
    entity.date_order = date_order
    entity.is_active = request.POST.get("is_active") == "on"
    entity.save(update_fields=["date_order", "is_active", "updated_at"])
    messages.success(request, f"Entidad '{entity.name}' actualizada.")
    return redirect(_safe_next(request) or _entity_detail_url(entity))


@login_required
@role_required(ROLE_REVIEWER)
@require_POST
def entity_alias_add(request, pk: int):
    entity = get_object_or_404(Entity, pk=pk)
    alias = " ".join((request.POST.get("alias") or "").split())
    if not alias:
        messages.error(request, "El alias no puede estar vacío.")
        return redirect(_safe_next(request) or _entity_detail_url(entity))
    normalized = normalize_catalog_text(alias)
    existing = EntityAlias.objects.filter(normalized_alias=normalized).first()
    if existing is not None:
        if existing.entity_id == entity.pk:
            messages.info(request, "Ese alias ya existía para esta entidad.")
        else:
            messages.error(
                request,
                f"El alias ya está asignado a '{existing.entity.name}'.",
            )
        return redirect(_safe_next(request) or _entity_detail_url(entity))
    EntityAlias.objects.create(entity=entity, alias=alias)
    messages.success(request, f"Alias '{alias}' añadido a '{entity.name}'.")
    return redirect(_safe_next(request) or _entity_detail_url(entity))


@login_required
@role_required(ROLE_REVIEWER)
@require_POST
def exam_create(request, entity_pk: int):
    entity = get_object_or_404(Entity, pk=entity_pk)
    name = " ".join((request.POST.get("name") or "").split())
    if not name:
        messages.error(request, "El nombre del examen no puede estar vacío.")
        return redirect(_safe_next(request) or _entity_detail_url(entity))
    language = None
    language_id = request.POST.get("language", "")
    if language_id:
        language = Language.objects.filter(pk=language_id, is_active=True).first()
        if language is None:
            messages.error(request, "Idioma no válido.")
            return redirect(_safe_next(request) or _entity_detail_url(entity))
    exam, created = Exam.objects.get_or_create(
        entity=entity,
        name=name,
        defaults={"language": language},
    )
    if not created and exam.language_id is None and language is not None:
        exam.language = language
        exam.save(update_fields=["language", "updated_at"])
    if created:
        messages.success(request, f"Examen '{name}' creado en '{entity.name}'.")
    else:
        messages.info(request, f"El examen '{name}' ya existía en '{entity.name}'.")
    return redirect(_safe_next(request) or _entity_detail_url(entity))


def _resolve_candidates(field: str, certificate, query: str):
    """Searchable catalog candidates for the resolve picker."""
    query = query.strip()
    if field == "entity":
        qs = Entity.objects.filter(is_active=True)
        if query:
            qs = qs.filter(
                models.Q(name__icontains=query) | models.Q(aliases__alias__icontains=query)
            ).distinct()
        return qs.order_by("name")[:50]
    if field == "exam":
        if certificate.entity_id is None:
            return Exam.objects.none()
        qs = Exam.objects.filter(is_active=True, entity_id=certificate.entity_id)
        if certificate.language_id is not None:
            qs = qs.filter(
                models.Q(language_id=certificate.language_id)
                | models.Q(language__isnull=True)
            )
        if query:
            qs = qs.filter(
                models.Q(name__icontains=query) | models.Q(aliases__alias__icontains=query)
            ).distinct()
        return qs.select_related("language").order_by("name")[:50]
    if field == "language":
        qs = Language.objects.filter(is_active=True)
        if query:
            qs = qs.filter(
                models.Q(name__icontains=query)
                | models.Q(name_es__icontains=query)
                | models.Q(aliases__alias__icontains=query)
            ).distinct()
        return qs.order_by("name")[:50]
    return Entity.objects.none()


@login_required
@role_required(ROLE_VIEWER)
@require_http_methods(["GET", "POST"])
def catalog_resolve(request):
    """Resolve an unresolved certificate literal to a catalog entry."""
    if request.method == "POST":
        return _catalog_resolve_post(request)

    document = get_object_or_404(
        Document.objects.select_related(
            "certificate__entity", "certificate__language", "certificate__exam"
        ),
        pk=request.GET.get("document", ""),
    )
    field = request.GET.get("field", "")
    certificate = getattr(document, "certificate", None)
    if certificate is None:
        messages.error(request, "El documento no tiene certificado.")
        return redirect("documents:list")
    if field not in FIELD_SPECS:
        messages.error(request, "Campo de catálogo no válido.")
        return redirect("documents:detail", pk=document.pk)

    literal = " ".join(
        (getattr(certificate, f"{field}_literal") or "").split()
    )
    exam_blocked = field == "exam" and certificate.entity_id is None
    query = request.GET.get("q", "")
    candidates = (
        _resolve_candidates(field, certificate, query) if not exam_blocked else []
    )
    return render(
        request,
        "catalog/resolve.html",
        {
            "document": document,
            "certificate": certificate,
            "field": field,
            "field_label": FIELD_LABELS[field],
            "literal": literal,
            "query": query,
            "candidates": candidates,
            "exam_blocked": exam_blocked,
            "can_edit": can_review_documents(request.user),
            "unresolved": unresolved_catalog_fields(certificate),
        },
    )


def _catalog_resolve_post(request):
    document = get_object_or_404(
        Document.objects.select_related(
            "certificate__entity", "certificate__language", "certificate__exam"
        ),
        pk=request.POST.get("document", ""),
    )
    certificate = getattr(document, "certificate", None)
    if certificate is None:
        messages.error(request, "El documento no tiene certificado.")
        return redirect("documents:list")
    field = request.POST.get("field", "")
    if field not in FIELD_SPECS:
        messages.error(request, "Campo de catálogo no válido.")
        return redirect("documents:detail", pk=document.pk)
    if not can_review_documents(request.user):
        raise PermissionDenied

    reclassify = request.POST.get("reclasificar") == "on"
    choice = request.POST.get("choice", "")
    outcome = None

    if choice.startswith("existing:"):
        target_pk = choice.split(":", 1)[1]
        model = FIELD_SPECS[field][2]
        target = model.objects.filter(pk=target_pk, is_active=True).first()
        if target is None:
            messages.error(request, "Entrada de catálogo no válida.")
            return redirect(reverse("catalog:resolve") + _resolve_query(document, field))
        outcome = resolve_catalog_field(
            certificate, field, target, request.user, reclassify=reclassify
        )
    elif choice == "new":
        outcome = _resolve_create_new(request, certificate, field, reclassify)
    else:
        messages.error(request, "Elegí una entrada existente o creá una nueva.")
        return redirect(reverse("catalog:resolve") + _resolve_query(document, field))

    if outcome is None:
        return redirect("documents:detail", pk=document.pk)
    if outcome.ok:
        messages.success(request, f"{FIELD_LABELS[field]} resuelto en el catálogo.")
        if outcome.alias_conflict:
            messages.warning(
                request,
                f"El literal '{outcome.alias_conflict}' ya era alias de otra "
                "entrada; no se reasignó.",
            )
        if outcome.reclassify_error:
            messages.warning(
                request, f"No se pudo reclasificar: {outcome.reclassify_error}"
            )
    else:
        messages.error(request, outcome.error)
    return redirect("documents:detail", pk=document.pk)


def _resolve_query(document, field: str) -> str:
    return f"?document={document.pk}&field={field}"


def _resolve_create_new(request, certificate, field: str, reclassify: bool):
    """Create a catalog entry prefilled from the printed literal, then resolve."""
    literal = " ".join(
        (getattr(certificate, f"{field}_literal") or "").split()
    )
    name = " ".join((request.POST.get("name") or "").split()) or literal
    if not name:
        return ResolutionOutcome(ok=False, error="El nombre no puede estar vacío.")

    if field == "entity":
        target, _ = Entity.objects.get_or_create(name=name)
    elif field == "exam":
        if certificate.entity_id is None:
            return ResolutionOutcome(
                ok=False,
                error="Resolvé primero la entidad certificadora.",
            )
        language = certificate.language
        target, created = Exam.objects.get_or_create(
            entity_id=certificate.entity_id,
            name=name,
            defaults={"language": language},
        )
        if not created and target.language_id is None and language is not None:
            target.language = language
            target.save(update_fields=["language", "updated_at"])
    else:
        return ResolutionOutcome(
            ok=False, error="Los idiomas no se crean desde la resolución."
        )

    return resolve_catalog_field(
        certificate, field, target, request.user, reclassify=reclassify
    )
