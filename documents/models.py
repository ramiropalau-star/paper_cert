import re

from django.conf import settings
from django.db import models

from catalog.models import CefrLevel

NPA_RE = re.compile(r"\d{4}ERASMUS([A-Za-z0-9]+)", re.IGNORECASE)


class Document(models.Model):
    class ProcessingState(models.TextChoices):
        RECEIVED = "received", "Recibido"
        STORED = "stored", "Almacenado"
        TEXT_READY = "text_ready", "Texto listo"
        EXTRACTED = "extracted", "Extraído"
        CLASSIFIED = "classified", "Clasificado"
        PENDING_REVIEW = "pending_review", "Pendiente de revisión"
        APPROVED = "approved", "Aprobado"
        REJECTED = "rejected", "Rechazado"
        ERROR = "error", "Error"

    class TextMethod(models.TextChoices):
        EMBEDDED = "embedded", "Texto embebido"
        OCR = "ocr", "OCR"
        MIXED = "mixed", "Mixto"

    fingerprint = models.CharField(max_length=64, unique=True)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    paperless_document_id = models.CharField(max_length=100, blank=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    text_method = models.CharField(
        max_length=10, choices=TextMethod.choices, blank=True, default=""
    )
    processing_state = models.CharField(
        max_length=20,
        choices=ProcessingState.choices,
        default=ProcessingState.RECEIVED,
        db_index=True,
    )
    error_reason = models.TextField(blank=True)
    review_reasons = models.JSONField(default=list, blank=True)
    recovery_attempts = models.PositiveIntegerField(default=0)
    last_recovery_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="uploaded_documents",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.original_filename

    @property
    def npa(self) -> str:
        """Student NPA parsed from the intake filename, e.g. WF29402."""
        match = NPA_RE.search(self.original_filename or "")
        return match.group(1) if match else ""


class DocumentPage(models.Model):
    class Method(models.TextChoices):
        EMBEDDED = "embedded", "Texto embebido"
        OCR = "ocr", "OCR"

    document = models.ForeignKey(Document, related_name="pages", on_delete=models.CASCADE)
    page_number = models.PositiveIntegerField()
    text = models.TextField(blank=True)
    method = models.CharField(max_length=10, choices=Method.choices)
    ocr_confidence = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["document", "page_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "page_number"],
                name="unique_document_page_number",
            )
        ]

    def __str__(self) -> str:
        return f"{self.document_id} page {self.page_number}"


class Certificate(models.Model):
    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pendiente de revisión"
        VALIDATED = "validated", "Validado"
        APPROVED = "approved", "Aprobado"
        REJECTED = "rejected", "Rechazado"

    class CefrSource(models.TextChoices):
        EXPLICIT = "explicit", "Explícito en el documento"
        APPROVED_RULE = "approved_rule", "Regla aprobada"
        MANUAL = "manual", "Corrección manual"

    document = models.OneToOneField(Document, related_name="certificate", on_delete=models.CASCADE)
    student_name = models.CharField(max_length=300, blank=True)
    language_literal = models.CharField(max_length=200, blank=True)
    language = models.ForeignKey(
        "catalog.Language",
        related_name="certificates",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    entity_literal = models.CharField(max_length=300, blank=True)
    entity = models.ForeignKey(
        "catalog.Entity",
        related_name="certificates",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    issuing_body_literal = models.CharField(max_length=300, blank=True)
    test_center_literal = models.CharField(max_length=300, blank=True)
    exam_literal = models.CharField(max_length=300, blank=True)
    exam = models.ForeignKey(
        "catalog.Exam",
        related_name="certificates",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    level_literal = models.CharField(max_length=200, blank=True)
    cefr_level = models.CharField(max_length=2, choices=CefrLevel.choices, blank=True, default="")
    cefr_source = models.CharField(
        max_length=20, choices=CefrSource.choices, blank=True, default=""
    )
    equivalence = models.CharField(max_length=50, blank=True, default="")
    score_literal = models.CharField(max_length=200, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    exam_date = models.DateField(null=True, blank=True)
    result_date = models.DateField(null=True, blank=True)
    detected_date = models.DateField(null=True, blank=True)
    date_texts = models.JSONField(default=dict, blank=True)
    certificate_code = models.CharField(max_length=200, blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    field_confidence = models.JSONField(default=dict, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    format_score = models.FloatField(null=True, blank=True)
    format_cohort = models.CharField(max_length=300, blank=True, default="")
    is_language_certificate = models.BooleanField(null=True, blank=True, default=None)
    multiple_certificates_suspected = models.BooleanField(default=False)
    review_status = models.CharField(
        max_length=10,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
        db_index=True,
    )
    review_reasons = models.JSONField(default=list, blank=True)
    manual_fields = models.JSONField(default=list, blank=True)
    unverified_fields = models.JSONField(default=list, blank=True)
    prompt_version = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.student_name or f"Certificate for {self.document_id}"


class PaperlessSyncState(models.Model):
    """Singleton watermark for incremental Paperless sync (pk is always 1)."""

    last_added = models.DateTimeField(null=True, blank=True)
    last_paperless_id = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Paperless sync state"
        verbose_name_plural = "Paperless sync state"

    def __str__(self) -> str:
        return f"Sync watermark: {self.last_added}"


class ReviewEvent(models.Model):
    class EventType(models.TextChoices):
        EDIT = "edit", "Edición"
        VALIDATE = "validate", "Validación"
        APPROVE = "approve", "Aprobación"
        REJECT = "reject", "Rechazo"
        REPROCESS = "reprocess", "Reproceso"
        REEXTRACT = "reextract", "Re-extracción"
        LEARN = "learn", "Aprendizaje"

    certificate = models.ForeignKey(Certificate, related_name="events", on_delete=models.CASCADE)
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="review_events",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reason = models.TextField(blank=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.event_type} on {self.certificate_id}"
