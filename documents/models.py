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
    layout = models.JSONField(null=True, blank=True)

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

    class VerificationStatus(models.TextChoices):
        NONE = "none", "Sin datos de verificación"
        SELF_REPORTED = "self_reported", "Autodeclarado en el documento"
        VERIFIED_AT_SOURCE = "verified_at_source", "Verificado en origen"
        MANUALLY_CONFIRMED = "manually_confirmed", "Confirmado por revisor"

    verification_code = models.CharField(max_length=200, blank=True)
    verification_url = models.CharField(max_length=500, blank=True)
    verification_status = models.CharField(
        max_length=25,
        choices=VerificationStatus.choices,
        default=VerificationStatus.NONE,
        db_index=True,
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="verified_certificates",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_evidence = models.JSONField(default=dict, blank=True)
    prompt_version = models.CharField(max_length=50, blank=True)
    # Deterministic issuer/type pre-detection result recorded before
    # extraction: {result, confidence, margin, entity, exam, language,
    # candidates, classifier_used, version}.
    pre_detection = models.JSONField(default=dict, blank=True)
    extraction_run = models.ForeignKey(
        "ExtractionRun",
        related_name="certificates",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    # Veracity score (0-1 review aid) with its component breakdown.
    veracity_score = models.FloatField(null=True, blank=True)
    veracity_components = models.JSONField(default=dict, blank=True)
    veracity_weights_version = models.CharField(max_length=50, blank=True)
    veracity_computed_at = models.DateTimeField(null=True, blank=True)
    # Field-level comparison against a verifier-returned source document.
    source_comparison = models.JSONField(default=dict, blank=True)
    # Semantic duplicate link: another live certificate with the same identity
    # (code match, or corroborated student/exam/date when no code exists).
    duplicate_of = models.ForeignKey(
        "self",
        related_name="duplicates",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.student_name or f"Certificate for {self.document_id}"


class ExtractionRun(models.Model):
    """One extraction pass over a document, with its configuration metadata."""

    class Status(models.TextChoices):
        RUNNING = "running", "En curso"
        COMPLETED = "completed", "Completado"
        FAILED = "failed", "Fallido"

    document = models.ForeignKey(Document, related_name="extraction_runs", on_delete=models.CASCADE)
    certificate = models.ForeignKey(
        Certificate,
        related_name="extraction_runs",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.RUNNING, db_index=True
    )
    model = models.CharField(max_length=200, blank=True)
    prompt_version = models.CharField(max_length=50, blank=True)
    profile = models.ForeignKey(
        "catalog.FormatProfile",
        related_name="extraction_runs",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    profile_version = models.PositiveIntegerField(null=True, blank=True)
    pre_detection = models.JSONField(default=dict, blank=True)
    pass_count = models.PositiveIntegerField(default=1)
    fallback_used = models.CharField(max_length=30, blank=True, default="")
    fallback_model = models.CharField(max_length=200, blank=True, default="")
    latency_ms = models.FloatField(null=True, blank=True)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        indexes = [
            models.Index(fields=["document", "-started_at"], name="extrun_doc_started"),
            models.Index(fields=["status", "started_at"], name="extrun_status_started"),
        ]

    def __str__(self) -> str:
        return f"ExtractionRun {self.pk} ({self.status}) for {self.document_id}"


class VerifierConfig(models.Model):
    """Per-issuer verifier configuration stored as data, not code."""

    class Parser(models.TextChoices):
        NONE = "", "Sin documento fuente"
        PDF_TEXT = "pdf_text", "Texto de PDF"

    entity = models.ForeignKey(
        "catalog.Entity",
        related_name="verifier_configs",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    host = models.CharField(max_length=253)
    code_pattern = models.CharField(max_length=300, blank=True, default="")
    url_template = models.CharField(max_length=500, blank=True, default="")
    success_criteria = models.JSONField(default=dict, blank=True)
    source_document_parser = models.CharField(
        max_length=20, choices=Parser.choices, blank=True, default=""
    )
    source_field_patterns = models.JSONField(default=dict, blank=True)
    timeout_seconds = models.FloatField(default=10.0)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="verifier_configs",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["host", "entity__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "host"], name="uniq_verifier_config_entity_host"
            )
        ]

    def clean(self):
        from urllib.parse import urlparse

        from django.core.exceptions import ValidationError

        host = (self.host or "").strip().lower()
        if not host or "." not in host or " " in host:
            raise ValidationError({"host": "Host inválido."})
        if self.code_pattern:
            try:
                re.compile(self.code_pattern)
            except re.error as exc:
                raise ValidationError({"code_pattern": f"Regex inválido: {exc}"}) from exc
        if self.url_template:
            template = self.url_template.strip()
            parsed = urlparse(template)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValidationError(
                    {"url_template": "La plantilla debe ser una URL http(s) válida."}
                )
            if (parsed.hostname or "").lower() != host:
                raise ValidationError(
                    {"url_template": "La plantilla debe apuntar al mismo host configurado."}
                )

    def __str__(self) -> str:
        scope = self.entity.name if self.entity_id else "global"
        return f"VerifierConfig {self.host} ({scope})"


class EvaluationRun(models.Model):
    """One offline dry-run evaluation of extraction against a golden set."""

    class Status(models.TextChoices):
        QUEUED = "queued", "En cola"
        RUNNING = "running", "En curso"
        COMPLETED = "completed", "Completado"
        FAILED = "failed", "Fallido"

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True
    )
    set_name = models.CharField(max_length=100, default="default")
    set_version = models.PositiveIntegerField(default=1)
    config = models.JSONField(default=dict, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    comparison = models.JSONField(default=dict, blank=True)
    baseline_run = models.ForeignKey(
        "self",
        related_name="comparisons",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    code_revision = models.CharField(max_length=100, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="evaluation_runs",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["set_name", "set_version"], name="evalrun_set_version"),
            models.Index(fields=["status", "created_at"], name="evalrun_status_created"),
        ]

    def __str__(self) -> str:
        return f"EvaluationRun {self.pk} ({self.status})"


class EvaluationCase(models.Model):
    """A golden-set extraction case built from a human-confirmed certificate."""

    set_name = models.CharField(max_length=100, default="default")
    set_version = models.PositiveIntegerField(default=1)
    certificate = models.ForeignKey(
        Certificate,
        related_name="evaluation_cases",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    entity = models.ForeignKey(
        "catalog.Entity",
        related_name="evaluation_cases",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    exam = models.ForeignKey(
        "catalog.Exam",
        related_name="evaluation_cases",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    profile_version = models.PositiveIntegerField(null=True, blank=True)
    source_text = models.TextField(blank=True)
    expected = models.JSONField(default=dict, blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["set_name", "set_version", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["set_name", "set_version", "certificate"],
                name="uniq_eval_case_cert_version",
            )
        ]
        indexes = [
            models.Index(fields=["set_name", "set_version"], name="evalcase_set_version"),
        ]

    def __str__(self) -> str:
        return f"EvaluationCase {self.pk} ({self.set_name} v{self.set_version})"


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
        VERIFY = "verify", "Verificación en origen"

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


class FieldLabelAlias(models.Model):
    """Configurable label alias: maps a printed label to an extraction field.

    ``scope_entity`` null means the alias applies globally; when set, it
    applies only to documents whose certificate resolves to that entity
    (usable on re-extract, after classification).
    """

    class Field(models.TextChoices):
        STUDENT_NAME = "student_name", "Nombre del alumno"
        LANGUAGE = "language", "Idioma"
        ENTITY = "entity", "Entidad"
        ISSUING_BODY = "issuing_body", "Organismo emisor"
        TEST_CENTER = "test_center", "Centro de examen"
        EXAM = "exam", "Examen"
        LEVEL = "level", "Nivel"
        SCORE = "score", "Puntuación"
        CERTIFICATE_CODE = "certificate_code", "Código de certificado"
        ISSUE_DATE = "issue_date", "Fecha de expedición"
        EXAM_DATE = "exam_date", "Fecha de examen"
        RESULT_DATE = "result_date", "Fecha de resultado"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        LEARNED = "learned", "Aprendido"

    class Lifecycle(models.TextChoices):
        CANDIDATE = "candidate", "Candidato"
        ACTIVE = "active", "Activo"
        REJECTED = "rejected", "Rechazado"

    field = models.CharField(max_length=30, choices=Field.choices, db_index=True)
    alias = models.CharField(max_length=300)
    normalized_alias = models.CharField(max_length=300)
    scope_entity = models.ForeignKey(
        "catalog.Entity",
        related_name="field_label_aliases",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    scope_key = models.CharField(max_length=50)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    lifecycle = models.CharField(
        max_length=10,
        choices=Lifecycle.choices,
        default=Lifecycle.ACTIVE,
        db_index=True,
    )
    support_count = models.PositiveIntegerField(default=0)
    confidence = models.FloatField(null=True, blank=True)
    provenance = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="field_label_aliases",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["field", "alias"]
        constraints = [
            models.UniqueConstraint(
                fields=["field", "normalized_alias", "scope_key"],
                name="uniq_field_alias_scope",
            )
        ]
        indexes = [
            models.Index(fields=["lifecycle", "field", "scope_key"], name="alias_lifecycle_scope"),
        ]

    def __str__(self) -> str:
        scope = self.scope_entity.name if self.scope_entity_id else "global"
        return f"{self.field}: {self.alias} ({scope})"

    def save(self, *args, **kwargs):
        from catalog.normalization import normalize_alias_text

        self.normalized_alias = normalize_alias_text(self.alias)
        self.scope_key = "global" if self.scope_entity_id is None else str(self.scope_entity_id)
        super().save(*args, **kwargs)
