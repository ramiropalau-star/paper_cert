"""Health and landing views."""

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_http_methods

from core.models import ProgramSetting
from core.permissions import (
    ROLE_REVIEWER,
    ROLE_VIEWER,
    can_manage_users,
    role_required,
)


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


@require_GET
def ready(request: HttpRequest) -> HttpResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ready"})


@login_required
@role_required(ROLE_VIEWER)
@require_GET
def home(request: HttpRequest):
    return render(request, "core/home.html")


# (section title, [setting keys]) shown on the admin settings page, in order.
_SETTINGS_SECTIONS = [
    (
        "Extracción",
        [
            "ollama_url",
            "ollama_model",
            "ollama_timeout_seconds",
            "llm_max_input_chars",
            "confidence_review_threshold",
            "extraction_fallback_model",
        ],
    ),
    (
        "Aprendizaje del emisor",
        [
            "pre_detection_enabled",
            "pre_detection_confidence",
            "pre_detection_margin",
            "pre_detection_classifier_enabled",
            "profile_guided_extraction_enabled",
            "profile_context_max_chars",
            "alias_corroboration_min",
            "format_min_samples",
            "format_min_exam_samples",
            "format_score_threshold",
            "format_max_score",
            "format_verified_weight",
            "profile_quality_floor",
            "profile_drift_threshold",
            "veracity_enabled",
            "review_ui_enabled",
            "eval_regression_tolerance",
        ],
    ),
    (
        "Paperless-ngx",
        [
            "paperless_url",
            "paperless_ui_url",
            "paperless_other_tag",
            "paperless_timeout_seconds",
            "paperless_poll_interval_seconds",
            "paperless_poll_timeout_seconds",
            "paperless_sync_seconds",
            "sync_overlap_seconds",
        ],
    ),
    (
        "OCR",
        [
            "ocr_url",
            "ocr_languages",
            "ocr_timeout_seconds",
            "ocr_retries",
            "ocr_low_confidence_threshold",
        ],
    ),
    (
        "Correo",
        [
            "email_backend",
            "email_host",
            "email_port",
            "email_host_user",
            "email_use_tls",
            "default_from_email",
        ],
    ),
    (
        "n8n",
        [
            "n8n_processing_webhook_url",
            "n8n_report_webhook_url",
            "n8n_webhook_timeout_seconds",
        ],
    ),
    (
        "Técnico",
        [
            "media_root",
            "report_output_dir",
            "inbox_dir",
            "inbox_poll_seconds",
            "inbox_settle_seconds",
            "cache_dir",
            "upload_max_bytes",
            "pdf_max_pages",
            "embedded_text_min_chars",
            "code_revision",
            "qr_decode_enabled",
        ],
    ),
]


def _settings_rows():
    from django.conf import settings

    from core.settings_admin import is_editable, is_secret_key

    overrides = {s.key for s in ProgramSetting.objects.all()}
    sections = []
    for title, keys in _SETTINGS_SECTIONS:
        rows = []
        for key in keys:
            value = settings.APP.get(key, "")
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            secret = is_secret_key(key)
            if secret and value:
                value = "•••"
            editable = is_editable(key)
            rows.append(
                {
                    "key": key,
                    "value": value,
                    "editable": editable,
                    "overridden": key in overrides,
                    "secret": secret,
                }
            )
        sections.append({"title": title, "rows": rows})
    listed = {key for _, keys in _SETTINGS_SECTIONS for key in keys}

    def _display_value(key):
        value = settings.APP.get(key, "")
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        if is_secret_key(key) and value:
            return "•••"
        return value

    others = [
        {
            "key": key,
            "value": _display_value(key),
            "editable": is_editable(key),
            "overridden": key in overrides,
            "secret": is_secret_key(key),
        }
        for key in sorted(settings.APP)
        if key not in listed
    ]
    if others:
        sections.append({"title": "Otros parámetros", "rows": others})
    return sections


@login_required
@role_required(ROLE_REVIEWER)
@require_GET
def admin_panel(request: HttpRequest):
    """Admin landing page: cards linking to each admin subsection."""
    return render(
        request,
        "core/admin_panel.html",
        {"is_admin": can_manage_users(request.user)},
    )


@login_required
@role_required(ROLE_REVIEWER)
@require_GET
def admin_learning(request: HttpRequest):
    """Issuer-learning tools subsection."""
    return render(request, "core/admin_learning.html")


@login_required
@role_required(ROLE_REVIEWER)
@require_GET
def admin_users(request: HttpRequest):
    """Users and access subsection."""
    return render(request, "core/admin_users.html", {"is_admin": can_manage_users(request.user)})


@login_required
@role_required(ROLE_REVIEWER)
@require_http_methods(["GET", "POST"])
def admin_settings(request: HttpRequest):
    """Program configuration: runtime-editable settings, admin only."""
    if not can_manage_users(request.user):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied
    if request.method == "POST":
        return _admin_settings_post(request)
    return render(
        request,
        "core/admin_settings.html",
        {"settings_sections": _settings_rows()},
    )


def _admin_settings_post(request: HttpRequest):
    from django.contrib import messages
    from django.core.exceptions import ValidationError
    from django.shortcuts import redirect

    from core.settings_admin import reset_override, save_override

    action = request.POST.get("action", "")
    try:
        if action == "reset":
            reset_override(request.POST.get("key", ""))
            messages.success(request, "Parámetro restablecido al valor del entorno.")
        elif action == "reset_all":
            for setting in ProgramSetting.objects.all():
                reset_override(setting.key)
            messages.success(request, "Todos los parámetros restablecidos.")
        elif action == "save":
            from django.conf import settings as django_settings

            from core.settings_admin import is_editable as _is_editable

            errors = []
            for key in request.POST:
                if key in django_settings.APP and not _is_editable(key):
                    errors.append(f"{key}: este parámetro no es editable en caliente.")
            if not errors:
                for section in _settings_rows():
                    for row in section["rows"]:
                        if not row["editable"]:
                            continue
                        key = row["key"]
                        if key not in request.POST:
                            continue
                        try:
                            save_override(key, request.POST.get(key, ""), request.user)
                        except ValidationError as exc:
                            errors.extend(exc.messages)
            if errors:
                for error in errors:
                    messages.error(request, error)
            else:
                messages.success(request, "Configuración guardada; aplicada en caliente.")
        else:
            messages.error(request, "Acción inválida.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("admin-settings")
