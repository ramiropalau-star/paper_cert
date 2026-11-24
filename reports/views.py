"""Report job UI views and internal generation endpoint."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import content_disposition_header
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from catalog.models import Entity, Language
from core.internal import internal_token_required
from core.permissions import ROLE_VIEWER, role_required
from reports.models import ReportJob
from reports.services import create_report_job, run_report_job

FILTER_KEYS = (
    "student",
    "language",
    "entity",
    "level",
    "issue_date",
    "issue_date_from",
    "issue_date_to",
    "include_pending",
)


def _collect_filters(request) -> dict:
    filters: dict = {}
    for key in FILTER_KEYS:
        value = request.POST.get(key) or request.GET.get(key) or ""
        if key == "include_pending":
            filters[key] = value.lower() in {"1", "true", "on", "yes"}
        elif value:
            filters[key] = value.strip()
    return filters


@login_required
@role_required(ROLE_VIEWER)
@require_http_methods(["GET", "POST"])
def report_list(request):
    if request.method == "POST":
        job = create_report_job(_collect_filters(request), request.user)
        messages.success(request, f"Reporte #{job.pk} en cola.")
        return redirect("reports:detail", pk=job.pk)

    jobs = ReportJob.objects.select_related("requested_by")[:50]
    return render(
        request,
        "reports/list.html",
        {
            "jobs": jobs,
            "languages": Language.objects.filter(is_active=True),
            "entities": Entity.objects.filter(is_active=True),
        },
    )


@login_required
@role_required(ROLE_VIEWER)
@require_GET
def report_detail(request, pk: int):
    job = get_object_or_404(ReportJob, pk=pk)
    return render(request, "reports/detail.html", {"job": job})


@login_required
@role_required(ROLE_VIEWER)
@require_GET
def report_status(request, pk: int):
    job = get_object_or_404(ReportJob, pk=pk)
    return JsonResponse(
        {
            "id": job.pk,
            "status": job.status,
            "status_display": job.get_status_display(),
            "error_reason": job.error_reason,
            "download_url": (
                f"/reports/{job.pk}/download/" if job.status == ReportJob.Status.READY else None
            ),
        }
    )


@login_required
@role_required(ROLE_VIEWER)
@require_GET
def report_download(request, pk: int):
    job = get_object_or_404(ReportJob, pk=pk)
    if job.status != ReportJob.Status.READY or not job.artifact_path:
        raise Http404("El reporte no está listo.")
    from pathlib import Path

    path = Path(job.artifact_path)
    if not path.is_file():
        raise Http404("El artefacto del reporte no existe.")
    filename = path.name
    response = FileResponse(
        path.open("rb"),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = content_disposition_header(True, filename)
    return response


@csrf_exempt
@require_POST
@internal_token_required
def internal_run_report(request, pk: int):
    """n8n report flow: run (or re-run idempotently) a report job."""
    job = run_report_job(pk)
    if job is None:
        return JsonResponse({"error": "not_found"}, status=404)
    return JsonResponse(
        {
            "id": job.pk,
            "status": job.status,
            "error_reason": job.error_reason,
        }
    )
