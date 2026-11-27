from django.conf import settings
from django.db import models


class ProgramSetting(models.Model):
    """Runtime override for an ``APP`` program setting.

    Overrides are mirrored into the shared cache so every web worker picks
    them up without a restart; this table is the durable source of truth.
    """

    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField()
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return f"{self.key}={self.value!r}"
