from django.conf import settings
from django.db import models


class ReportJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "En cola"
        RUNNING = "running", "Generando"
        READY = "ready", "Listo"
        ERROR = "error", "Error"

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    filters = models.JSONField(default=dict, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="report_jobs",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    artifact_path = models.CharField(max_length=500, blank=True)
    counts = models.JSONField(default=dict, blank=True)
    error_reason = models.TextField(blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Report {self.pk} ({self.status})"
