from django.conf import settings
from django.http import JsonResponse


class RequestSizeLimitMiddleware:
    """Reject requests whose declared body exceeds the configured upload cap."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        limit = settings.APP.get("upload_max_bytes")
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
