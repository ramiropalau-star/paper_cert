"""Service-to-service authentication for the ``/internal/`` endpoints."""

import hmac
import logging
from functools import wraps

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

logger = logging.getLogger("core.internal")


def _configured_token() -> str:
    return str(settings.APP.get("internal_api_token") or "")


def internal_token_required(view):
    @wraps(view)
    def wrapped(request: HttpRequest, *args, **kwargs):
        expected = _configured_token()
        provided = request.headers.get("X-Internal-Token", "")
        request_id = request.headers.get("X-Request-ID", "")
        accepted = bool(expected) and hmac.compare_digest(provided, expected)
        logger.info(
            "internal_request",
            extra={
                "method": request.method,
                "path": request.path,
                "request_id": request_id,
                "outcome": "accepted" if accepted else "denied",
            },
        )
        if not accepted:
            return JsonResponse({"error": "unauthorized"}, status=401)
        return view(request, *args, **kwargs)

    return wrapped


@csrf_exempt
@require_GET
@internal_token_required
def internal_health(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "scope": "internal"})
