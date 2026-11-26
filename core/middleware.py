import uuid

from django.conf import settings
from django.http import JsonResponse

from core.logging import request_id_var


class RequestIdMiddleware:
    """Propagate ``X-Request-ID`` (or a generated id) through the request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.request_id = request_id
        token = request_id_var.set(request_id)
        try:
            return self.get_response(request)
        finally:
            request_id_var.reset(token)


class RequestSizeLimitMiddleware:
    """Reject requests whose declared body exceeds the total request cap.

    This bounds the whole multipart body; the per-file cap stays in
    ``validate_upload`` so multi-file uploads are not rejected early.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        limit = settings.APP.get("request_max_bytes")
        raw_length = request.META.get("CONTENT_LENGTH", "")
        if limit and raw_length:
            try:
                content_length = int(raw_length)
            except (TypeError, ValueError):
                content_length = 0
            if content_length > int(limit):
                return JsonResponse(
                    {
                        "error": "request_too_large",
                        "limit_bytes": int(limit),
                    },
                    status=413,
                )
        return self.get_response(request)
