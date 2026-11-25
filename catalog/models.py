from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from catalog.normalization import normalize_catalog_text


class CefrLevel(models.TextChoices):
    A1 = "A1", "A1"
    A2 = "A2", "A2"
    B1 = "B1", "B1"
    B2 = "B2", "B2"
    C1 = "C1", "C1"
    C2 = "C2", "C2"


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Language(TimestampedModel):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    name_es = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class LanguageAlias(TimestampedModel):
    language = models.ForeignKey(Language, related_name="aliases", on_delete=models.CASCADE)
    alias = models.CharField(max_length=100)
    normalized_alias = models.CharField(max_length=100, unique=True, editable=False)

    class Meta:
        ordering = ["alias"]
        verbose_name_plural = "language aliases"

    def save(self, *args, **kwargs):
        self.normalized_alias = normalize_catalog_text(self.alias)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.alias} -> {self.language.name}"


class Entity(TimestampedModel):
    class DateOrder(models.TextChoices):
        DAY_FIRST = "dmy", "Day first (dd/mm/yyyy)"
        MONTH_FIRST = "mdy", "Month first (mm/dd/yyyy)"

    name = models.CharField(max_length=200, unique=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    date_order = models.CharField(
        max_length=3,
        choices=DateOrder.choices,
        blank=True,
        default="",
        help_text="Day/month order used by this entity's certificates.",
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "entities"

    def __str__(self) -> str:
        return self.name


class EntityAlias(TimestampedModel):
    entity = models.ForeignKey(Entity, related_name="aliases", on_delete=models.CASCADE)
    alias = models.CharField(max_length=200)
    normalized_alias = models.CharField(max_length=200, unique=True, editable=False)

    class Meta:
        ordering = ["alias"]
        verbose_name_plural = "entity aliases"

    def save(self, *args, **kwargs):
        self.normalized_alias = normalize_catalog_text(self.alias)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.alias} -> {self.entity.name}"


class Exam(TimestampedModel):
    entity = models.ForeignKey(
        Entity,
        related_name="exams",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    language = models.ForeignKey(
        Language,
        related_name="exams",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["entity", "name"], name="unique_exam_entity_name")
        ]

    def __str__(self) -> str:
        return self.name


class ExamAlias(TimestampedModel):
    exam = models.ForeignKey(Exam, related_name="aliases", on_delete=models.CASCADE)
    alias = models.CharField(max_length=200)
    normalized_alias = models.CharField(max_length=200, unique=True, editable=False)

    class Meta:
        ordering = ["alias"]
        verbose_name_plural = "exam aliases"

    def save(self, *args, **kwargs):
        self.normalized_alias = normalize_catalog_text(self.alias)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.alias} -> {self.exam.name}"


class CefrConversionRuleQuerySet(models.QuerySet):
    def effective(self):
        """Return rules that are active and carry approval metadata."""
        return (
            self.filter(is_active=True, approved_at__isnull=False)
            .exclude(approved_by="")
            .exclude(reference="")
        )


class CefrConversionRule(TimestampedModel):
    exam = models.ForeignKey(Exam, related_name="cefr_rules", on_delete=models.CASCADE)
    score_min = models.DecimalField(max_digits=6, decimal_places=2)
    score_max = models.DecimalField(max_digits=6, decimal_places=2)
    cefr_level = models.CharField(max_length=2, choices=CefrLevel.choices)
    reference = models.TextField(blank=True)
    approved_by = models.CharField(max_length=200, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)

    objects = CefrConversionRuleQuerySet.as_manager()

    class Meta:
        ordering = ["exam__name", "score_min"]
        constraints = [
            models.CheckConstraint(
                condition=Q(score_max__gte=F("score_min")),
                name="cefr_rule_score_range",
            )
        ]

    def clean(self):
        errors: dict[str, str] = {}
        if (
            self.score_min is not None
            and self.score_max is not None
            and self.score_max < self.score_min
        ):
            errors["score_max"] = "El puntaje máximo debe ser mayor o igual al mínimo."
        if self.is_active:
            if not self.approved_by.strip():
                errors["approved_by"] = "Una regla activa requiere un aprobador."
            if not self.reference.strip():
                errors["reference"] = "Una regla activa requiere una referencia."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.is_active and self.approved_at is None:
            self.approved_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.exam.name}: {self.score_min}-{self.score_max} -> {self.cefr_level}"


class Equivalence(TimestampedModel):
    """UV L2 accreditation equivalence for an exam (optionally score-banded)."""

    exam = models.ForeignKey(Exam, related_name="equivalences", on_delete=models.CASCADE)
    accredited_level = models.CharField(max_length=2, choices=CefrLevel.choices)
    score_min = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    score_max = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    label = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=100, default="UV L2")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["exam__name", "score_min"]
        constraints = [
            models.CheckConstraint(
                condition=Q(score_max__isnull=True)
                | Q(score_min__isnull=True)
                | Q(score_max__gte=F("score_min")),
                name="equivalence_score_range",
            )
        ]

    def __str__(self) -> str:
        band = ""
        if self.score_min is not None or self.score_max is not None:
            band = f" {self.score_min}-{self.score_max}"
        return f"{self.exam.name}{band} -> {self.accredited_level}"
