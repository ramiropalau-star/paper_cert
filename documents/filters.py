"""Queryset filtering for the document list and gallery views."""

from datetime import date

from django.conf import settings
from django.db.models import BooleanField, Case, Exists, OuterRef, Q, QuerySet, Value, When

from catalog.models import FormatProfile
from documents.models import Certificate, Document


def _unresolved(fk: str, literal: str) -> Q:
    return Q(**{f"certificate__{fk}__isnull": True}) & Q(
        **{f"certificate__{literal}__regex": r"\S"}
    )


UNRESOLVED_CATALOG_Q = Q(certificate__isnull=False) & (
    _unresolved("entity", "entity_literal")
    | _unresolved("exam", "exam_literal")
    | _unresolved("language", "language_literal")
)

STATE_FILTERS = {
    "pending": [Document.ProcessingState.PENDING_REVIEW.value],
    "approved": [Document.ProcessingState.APPROVED.value],
    "rejected": [Document.ProcessingState.REJECTED.value],
    "error": [Document.ProcessingState.ERROR.value],
    "processed": [
        Document.ProcessingState.RECEIVED.value,
        Document.ProcessingState.STORED.value,
        Document.ProcessingState.TEXT_READY.value,
        Document.ProcessingState.EXTRACTED.value,
        Document.ProcessingState.CLASSIFIED.value,
    ],
}


def filter_documents(params) -> QuerySet:
    """Apply the GET filters shared by the list and gallery views.

    ``params`` is a mapping with ``.get`` (``request.GET`` or a plain dict).
    Invalid values degrade to literal-text matches or are ignored; they never
    raise.
    """
    queryset = Document.objects.select_related(
        "certificate",
        "certificate__language",
        "certificate__entity",
        "certificate__exam",
        "uploaded_by",
    ).order_by("-created_at")

    queryset = queryset.annotate(
        catalog_pending=Case(
            When(UNRESOLVED_CATALOG_Q, then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        )
    )

    state = params.get("state") or ""
    if state in STATE_FILTERS:
        queryset = queryset.filter(processing_state__in=STATE_FILTERS[state])

    query = (params.get("q") or "").strip()
    if query:
        queryset = queryset.filter(
            Q(original_filename__icontains=query) | Q(certificate__student_name__icontains=query)
        )

    language = (params.get("language") or "").strip()
    if language:
        clauses = Q(certificate__language_literal__icontains=language)
        if language.isdigit():
            clauses |= Q(certificate__language_id=language)
        queryset = queryset.filter(clauses)

    entity = (params.get("entity") or "").strip()
    if entity:
        clauses = Q(certificate__entity_literal__icontains=entity)
        if entity.isdigit():
            clauses |= Q(certificate__entity_id=entity)
        queryset = queryset.filter(clauses)

    organism = (params.get("organism") or "").strip()
    if organism:
        queryset = queryset.filter(certificate__issuing_body_literal__icontains=organism)

    level = (params.get("level") or "").strip()
    if level:
        queryset = queryset.filter(
            Q(certificate__cefr_level__iexact=level)
            | Q(certificate__level_literal__icontains=level)
        )

    issue_date_raw = (params.get("issue_date") or "").strip()
    if issue_date_raw:
        try:
            issue_date = date.fromisoformat(issue_date_raw)
        except ValueError:
            issue_date = None
        if issue_date is not None:
            queryset = queryset.filter(certificate__issue_date=issue_date)

    catalog = (params.get("catalog") or "").strip()
    if catalog == "pending":
        queryset = queryset.filter(UNRESOLVED_CATALOG_Q)

    if (params.get("unverified") or "").strip() in {"1", "true", "yes"}:
        queryset = queryset.filter(certificate__unverified_fields__isnull=False).exclude(
            certificate__unverified_fields=[]
        )

    verification = (params.get("verification") or "").strip()
    if verification in Certificate.VerificationStatus.values:
        queryset = queryset.filter(certificate__verification_status=verification)

    if (params.get("format") or "").strip() == "doubtful":
        queryset = queryset.filter(doubtful_format_q())

    return queryset


def doubtful_format_q() -> Q:
    """Q matching documents whose format confidence is doubtful.

    Doubtful = format_score below the configured threshold, or no score at
    all while the certificate's entity has an active profile with enough
    samples (a profile exists that could have scored it).
    """
    threshold = float(settings.APP.get("format_score_threshold", 0.4))
    min_samples = int(settings.APP.get("format_min_samples", 2))
    qualifying_profile = FormatProfile.objects.filter(
        entity_id=OuterRef("certificate__entity_id"),
        is_active=True,
        sample_count__gte=min_samples,
    )
    return Q(certificate__format_score__lt=threshold) | (
        Q(certificate__format_score__isnull=True)
        & Q(certificate__entity_id__isnull=False)
        & Exists(qualifying_profile)
    )
