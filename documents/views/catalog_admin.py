"""Catalog-administration views: format profiles and field-label aliases."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from catalog.models import Entity, FormatProfile
from core.permissions import ROLE_REVIEWER, role_required
from documents.models import FieldLabelAlias
from documents.services.field_aliases import teach_alias as teach_field_alias
from documents.services.format_profile import rescore_entity_year


@login_required
@role_required(ROLE_REVIEWER)
@require_http_methods(["GET", "POST"])
def format_profile_list(request):
    """Inspect, deactivate/reactivate and rescore learned format profiles."""
    if request.method == "POST":
        action = request.POST.get("action", "")
        profile = get_object_or_404(
            FormatProfile.objects.select_related("entity", "exam"),
            pk=request.POST.get("profile_id"),
        )
        if action in {"deactivate", "activate"}:
            profile.is_active = action == "activate"
            if profile.is_active:
                profile.deactivated_by = None
                profile.deactivated_at = None
            else:
                profile.deactivated_by = request.user
                profile.deactivated_at = timezone.now()
            profile.save(
                update_fields=[
                    "is_active",
                    "deactivated_by",
                    "deactivated_at",
                    "updated_at",
                ]
            )
            messages.success(request, "Perfil de formato actualizado.")
        elif action == "rescore":
            count = rescore_entity_year(profile.entity_id, profile.year, profile.exam_id)
            messages.success(request, f"Se reprocesaron {count} certificados de la cohorte.")
        else:
            messages.error(request, "Acción inválida.")
        return redirect("documents:format_profiles")

    profiles = FormatProfile.objects.select_related("entity", "exam", "deactivated_by").order_by(
        "entity__name", "-year", "exam__name"
    )
    return render(
        request,
        "documents/format_profiles.html",
        {"profiles": profiles, "can_manage": True},
    )


@login_required
@role_required(ROLE_REVIEWER)
@require_http_methods(["GET", "POST"])
def field_alias_list(request):
    """List and manage field label aliases (reviewer+)."""
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "create":
            scope_entity = None
            entity_id = request.POST.get("scope_entity") or ""
            if entity_id:
                scope_entity = Entity.objects.filter(pk=entity_id).first()
            _created, message = teach_field_alias(
                field=request.POST.get("field", ""),
                alias=request.POST.get("alias", ""),
                actor=request.user,
                scope_entity=scope_entity,
            )
            (messages.error if _created is None else messages.success)(request, message)
        elif action in {"activate", "deactivate"}:
            alias = get_object_or_404(FieldLabelAlias, pk=request.POST.get("alias_id"))
            alias.is_active = action == "activate"
            alias.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "Alias actualizado.")
        return redirect("documents:field_aliases")

    aliases = FieldLabelAlias.objects.select_related("scope_entity", "created_by")
    return render(
        request,
        "documents/field_aliases.html",
        {
            "aliases": aliases,
            "can_manage": True,
            "field_choices": FieldLabelAlias.Field.choices,
            "entities": Entity.objects.filter(is_active=True).order_by("name"),
        },
    )
