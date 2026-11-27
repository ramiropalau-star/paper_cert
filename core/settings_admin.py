"""Admin helpers for runtime-editable program settings.

Editable keys are those consumed at request/runtime through
``settings.APP``; startup-bound values (email backend, filesystem paths,
cache dir) and secrets stay read-only because mutating ``APP`` would not
reach the Django settings derived from it at boot.
"""

import json
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError

from core.models import ProgramSetting

CACHE_PREFIX = "appcfg:v1:"

# Bound into Django settings at startup or pointing at filesystem layout:
# editing them in ``APP`` would silently not apply.
READ_ONLY_KEYS = frozenset(
    {
        "media_root",
        "report_output_dir",
        "inbox_dir",
        "cache_dir",
        "code_revision",
        "email_backend",
        "email_host",
        "email_port",
        "email_host_user",
        "email_host_password",
        "email_use_tls",
        "default_from_email",
    }
)

SECRET_MARKERS = ("token", "password", "secret")


def is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SECRET_MARKERS)


def is_editable(key: str) -> bool:
    return key in settings.APP and key not in READ_ONLY_KEYS and not is_secret_key(key)


def _coerce(key: str, raw: str) -> Any:
    """Coerce a form string to the type of the current effective value."""
    default = settings.APP.get(key)
    text = (raw or "").strip()
    if isinstance(default, bool):
        lowered = text.lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off", ""}:
            return False
        raise ValidationError(f"{key}: se esperaba un valor booleano.")
    if isinstance(default, int):
        try:
            return int(text)
        except ValueError as exc:
            raise ValidationError(f"{key}: se esperaba un entero.") from exc
    if isinstance(default, float):
        try:
            return float(text)
        except ValueError as exc:
            raise ValidationError(f"{key}: se esperaba un número.") from exc
    if isinstance(default, list):
        if not text:
            return []
        return [item.strip() for item in text.split(",") if item.strip()]
    if isinstance(default, dict):
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{key}: se esperaba un objeto JSON.") from exc
        if not isinstance(value, dict):
            raise ValidationError(f"{key}: se esperaba un objeto JSON.")
        return value
    return text


def _push_cache(key: str, value: Any) -> None:
    cache.set(f"{CACHE_PREFIX}{key}", value, timeout=None)


def save_override(key: str, raw_value: str, user) -> ProgramSetting:
    """Validate, persist and publish a runtime override for ``key``."""
    if not is_editable(key):
        raise ValidationError(f"{key}: este parámetro no es editable en caliente.")
    value = _coerce(key, raw_value)
    setting, _ = ProgramSetting.objects.update_or_create(
        key=key, defaults={"value": value, "updated_by": user}
    )
    _push_cache(key, value)
    return setting


def reset_override(key: str) -> None:
    """Remove a runtime override, restoring the environment default."""
    ProgramSetting.objects.filter(key=key).delete()
    cache.delete(f"{CACHE_PREFIX}{key}")


def prime_cache() -> None:
    """Republish all stored overrides into the shared cache (app startup)."""
    for setting in ProgramSetting.objects.all():
        _push_cache(setting.key, setting.value)


def setting_rows() -> list[dict[str, Any]]:
    """Effective values grouped for display, with editability metadata."""
    overrides = {s.key: s for s in ProgramSetting.objects.all()}
    rows = []
    for key in sorted(settings.APP):
        overridden = key in overrides
        editable = is_editable(key)
        value = settings.APP[key]
        display = "•••" if is_secret_key(key) and value else value
        if isinstance(display, (list, dict)):
            display = json.dumps(display, ensure_ascii=False)
        rows.append(
            {
                "key": key,
                "value": display,
                "editable": editable,
                "overridden": overridden,
                "updated_at": overrides[key].updated_at if overridden else None,
                "updated_by": overrides[key].updated_by if overridden else None,
            }
        )
    return rows
