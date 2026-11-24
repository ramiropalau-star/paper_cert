"""Catalog administration UI: review and edit UV L2 equivalences."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from catalog.models import CefrLevel, Entity, EntityAlias, Equivalence, Exam, Language
from catalog.normalization import normalize_catalog_text
from core.permissions import (
    ROLE_REVIEWER,
    ROLE_VIEWER,
    can_review_documents,
    role_required,
)


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
        return redirect("catalog:equivalences")
    if score_min is not None and score_max is not None and score_max < score_min:
        messages.error(request, "La banda mínima no puede ser mayor que la máxima.")
        return redirect("catalog:equivalences")

    equivalence.accredited_level = level
    equivalence.score_min = score_min
    equivalence.score_max = score_max
    equivalence.is_active = is_active
    equivalence.save()
    messages.success(request, f"Equivalencia #{equivalence.pk} actualizada.")
    return redirect("catalog:equivalences")


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
        return redirect("catalog:equivalences")
    if score_min is not None and score_max is not None and score_max < score_min:
        messages.error(request, "La banda mínima no puede ser mayor que la máxima.")
        return redirect("catalog:equivalences")

    Equivalence.objects.create(
        exam=exam,
        accredited_level=level,
        score_min=score_min,
        score_max=score_max,
        source=request.POST.get("source", "").strip() or "Manual",
    )
    messages.success(request, f"Equivalencia añadida a {exam.name}.")
    return redirect("catalog:equivalences")


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
            return redirect("catalog:equivalences")

    return render(
        request,
        "catalog/entity_form.html",
        {
            "languages": Language.objects.filter(is_active=True),
            "levels": CefrLevel.choices,
        },
    )
