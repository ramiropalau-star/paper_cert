from django.contrib import admin

from core.admin import AdminRoleRequiredMixin
from reports.models import ReportJob


@admin.register(ReportJob)
class ReportJobAdmin(AdminRoleRequiredMixin, admin.ModelAdmin):
    list_display = ("id", "status", "requested_by", "created_at", "completed_at")
    list_filter = ("status", "created_at")
    search_fields = ("requested_by__username", "artifact_path")
    readonly_fields = ("created_at", "updated_at", "completed_at")
