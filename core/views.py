"""Health and landing views."""

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from core.permissions import ROLE_VIEWER, role_required


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


@login_required
@role_required(ROLE_VIEWER)
@require_GET
def home(request: HttpRequest):
    return render(request, "core/home.html")
