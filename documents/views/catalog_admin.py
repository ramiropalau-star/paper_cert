"""Catalog-administration views: format profiles, field-label aliases, and
per-issuer verifier configuration."""

import json
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from catalog.models import Entity, FormatProfile
from core.permissions import ROLE_REVIEWER, role_required
from documents.models import FieldLabelAlias, VerifierConfig
from documents.services.field_aliases import (
    set_alias_lifecycle,
)
from documents.services.field_aliases import (
    teach_alias as teach_field_alias,
)
from documents.services.format_profile import rescore_entity_year
from documents.services.profile_preview import render_profile_preview


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
        "entity__name", F("year").desc(nulls_last=True), "exam__name"
    )
    return render(
        request,
        "documents/format_profiles.html",
        {"profiles": profiles, "can_manage": True},
    )


def _preview_placeholder() -> bytes:
    """Simple PNG shown when no anonymized sample can be produced."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (640, 160), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 70), "Sin muestra disponible", fill="black")
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


@login_required
@role_required(ROLE_REVIEWER)
@require_http_methods(["GET"])
def format_profile_preview(request, pk):
    """Anonymized render of a profile's sample certificate (reviewer+)."""
    profile = get_object_or_404(FormatProfile.objects.select_related("entity", "exam"), pk=pk)
    cache_key = f"fmtprof-preview:{profile.pk}:{profile.version}"
    png = cache.get(cache_key)
    if png is None:
        png = render_profile_preview(profile) or _preview_placeholder()
        cache.set(cache_key, png, timeout=3600)
    return HttpResponse(png, content_type="image/png")


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
        elif action == "activate":
            alias = get_object_or_404(FieldLabelAlias, pk=request.POST.get("alias_id"))
            ok, message = set_alias_lifecycle(alias, FieldLabelAlias.Lifecycle.ACTIVE, request.user)
            (messages.error if not ok else messages.success)(request, message)
        elif action == "deactivate":
            alias = get_object_or_404(FieldLabelAlias, pk=request.POST.get("alias_id"))
            alias.is_active = False
            alias.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "Alias desactivado.")
        elif action == "reject":
            alias = get_object_or_404(FieldLabelAlias, pk=request.POST.get("alias_id"))
            ok, message = set_alias_lifecycle(
                alias, FieldLabelAlias.Lifecycle.REJECTED, request.user
            )
            (messages.error if not ok else messages.success)(request, message)
        return redirect("documents:field_aliases")

    aliases = FieldLabelAlias.objects.select_related("scope_entity", "created_by")
    return render(
        request,
        "documents/field_aliases.html",
        {
            "aliases": aliases,
            "can_manage": True,
            "field_choices": FieldLabelAlias.Field.choices,
            "lifecycle_choices": FieldLabelAlias.Lifecycle.choices,
            "entities": Entity.objects.filter(is_active=True).order_by("name"),
        },
    )


def _json_field(raw: str, field_name: str) -> dict:
    """Parse an optional JSON object form field; raises ValueError on bad JSON."""
    raw = (raw or "").strip()
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} debe ser un objeto JSON.")
    return value


@login_required
@role_required(ROLE_REVIEWER)
@require_http_methods(["GET", "POST"])
def verifier_config_list(request):
    """Manage per-issuer verifier configuration (reviewer+; viewers denied)."""
    if request.method == "POST":
        action = request.POST.get("action", "")
        try:
            if action == "create":
                config = VerifierConfig(created_by=request.user)
            elif action == "update":
                config = get_object_or_404(VerifierConfig, pk=request.POST.get("config_id"))
            else:
                messages.error(request, "Acción inválida.")
                return redirect("documents:verifier_configs")

            entity_id = request.POST.get("entity") or ""
            config.entity = Entity.objects.filter(pk=entity_id).first() if entity_id else None
            config.host = request.POST.get("host", "")
            config.code_pattern = request.POST.get("code_pattern", "")
            config.url_template = request.POST.get("url_template", "")
            config.success_criteria = _json_field(
                request.POST.get("success_criteria", ""), "success_criteria"
            )
            config.source_document_parser = request.POST.get("source_document_parser", "")
            config.source_field_patterns = _json_field(
                request.POST.get("source_field_patterns", ""),
                "source_field_patterns",
            )
            try:
                config.timeout_seconds = float(request.POST.get("timeout_seconds") or 10.0)
            except ValueError:
                raise ValidationError({"timeout_seconds": "Timeout inválido."}) from None
            if not 1.0 <= config.timeout_seconds <= 120.0:
                raise ValidationError(
                    {"timeout_seconds": "El timeout debe estar entre 1 y 120 segundos."}
                )
            config.is_active = request.POST.get("is_active") == "on"
            config.full_clean()
            config.save()
            messages.success(request, "Configuración de verificación guardada.")
        except (ValidationError, ValueError) as exc:
            if isinstance(exc, ValidationError):
                detail = "; ".join(str(message) for message in exc.messages)
            else:
                detail = str(exc)
            messages.error(request, f"Configuración inválida: {detail}")
        return redirect("documents:verifier_configs")

    configs = list(
        VerifierConfig.objects.select_related("entity", "created_by").order_by(
            "host", "entity__name"
        )
    )
    for config in configs:
        config.success_criteria_json = json.dumps(config.success_criteria or {})
        config.source_field_patterns_json = json.dumps(config.source_field_patterns or {})
    return render(
        request,
        "documents/verifier_configs.html",
        {
            "configs": configs,
            "can_manage": True,
            "entities": Entity.objects.filter(is_active=True).order_by("name"),
            "parser_choices": VerifierConfig.Parser.choices,
        },
    )
