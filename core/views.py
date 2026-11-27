"""Health and landing views."""

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from core.permissions import ROLE_VIEWER, role_required


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
