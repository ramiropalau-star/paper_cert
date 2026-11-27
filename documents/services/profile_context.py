"""Profile-guided extraction context.

Builds the pass-2 prompt section for a detected issuer: learned field
labels, learned value shapes, expected format anchors, and anonymized
exemplars from approved certificates — all bounded by a character budget.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings

from catalog.models import FormatProfile
from documents.models import Certificate, FieldLabelAlias
from documents.services.format_profile import LEARNED_REVIEW_STATUSES

MAX_ANCHORS_IN_PROMPT = 20
MAX_LABELS_PER_FIELD = 10
MAX_EXEMPLARS = 3
TRUNCATION_NOTE = "[profile context truncated]"

# Fields whose values are personal data and must be masked in exemplars.
_PII_FIELDS = {"student_name", "certificate_code"}
_DATE_FIELDS = {"issue_date", "exam_date", "result_date", "detected_date"}


def _max_chars() -> int:
    return int(settings.APP.get("profile_context_max_chars", 4000))


def select_profile(entity_id: int, exam_id: int | None = None) -> FormatProfile | None:
    """Pick the best active profile for an entity, preferring exam scope."""
    base = FormatProfile.objects.filter(entity_id=entity_id, is_active=True)
    if exam_id is not None:
        exam_profile = base.filter(exam_id=exam_id).order_by("-year", "-version").first()
        if exam_profile is not None:
            return exam_profile
    return base.filter(exam__isnull=True).order_by("-year", "-version").first()


def _learned_labels(entity_id: int) -> dict[str, list[str]]:
    """Active learned/manual aliases scoped to the entity, per field."""
    result: dict[str, list[str]] = {}
    aliases = (
        FieldLabelAlias.objects.filter(
            scope_entity_id=entity_id,
            lifecycle=FieldLabelAlias.Lifecycle.ACTIVE,
            is_active=True,
        )
        .order_by("field", "alias")
        .values_list("field", "alias")
    )
    for field, alias in aliases:
        bucket = result.setdefault(field, [])
        if alias not in bucket and len(bucket) < MAX_LABELS_PER_FIELD:
            bucket.append(alias)
    return result


def _value_shapes(profile: FormatProfile) -> dict[str, Any]:
    return profile.value_shapes or {}


def _anchor_lines(profile: FormatProfile) -> list[str]:
    anchors = profile.anchors or []
    lines = [str(item.get("text")) for item in anchors if item.get("text")]
    return lines[:MAX_ANCHORS_IN_PROMPT]


def _mask_exemplar_value(field: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if field in _PII_FIELDS:
        return "[REDACTED]"
    if field in _DATE_FIELDS:
        return "[DATE]"
    return text


def _exemplar_lines(entity_id: int, exam_id: int | None) -> list[str]:
    """Anonymized one-line summaries of approved certificates for the issuer."""
    qs = Certificate.objects.filter(
        entity_id=entity_id,
        review_status__in=LEARNED_REVIEW_STATUSES,
    ).order_by("-updated_at")
    if exam_id is not None:
        qs = qs.filter(exam_id=exam_id)
    lines: list[str] = []
    for cert in qs[:MAX_EXEMPLARS]:
        parts = []
        for attr in (
            "language_literal",
            "entity_literal",
            "exam_literal",
            "level_literal",
            "score_literal",
            "student_name",
            "certificate_code",
        ):
            masked = _mask_exemplar_value(attr, getattr(cert, attr, ""))
            if masked:
                parts.append(f"{attr}={masked}")
        for attr in ("issue_date", "exam_date", "result_date"):
            value = getattr(cert, attr, None)
            if value is not None:
                parts.append(f"{attr}=[DATE]")
        if parts:
            lines.append("  " + ", ".join(parts))
    return lines


def build_profile_context(profile: FormatProfile, *, entity_id: int | None = None) -> str:
    """Render the profile-guided prompt section within the char budget."""
    entity_id = entity_id if entity_id is not None else profile.entity_id
    exam_id = profile.exam_id
    max_chars = _max_chars()

    sections: list[tuple[str, list[str]]] = []

    labels = _learned_labels(entity_id)
    label_lines = [
        f"  - {field}: {', '.join(repr(a) for a in aliases)}"
        for field, aliases in sorted(labels.items())
    ]
    if label_lines:
        sections.append(("Learned labels for this issuer", label_lines))

    shapes = _value_shapes(profile)
    if shapes:
        shape_lines = [f"  - {field}: {shape}" for field, shape in sorted(shapes.items())]
        sections.append(("Expected value shapes", shape_lines))

    anchors = _anchor_lines(profile)
    if anchors:
        sections.append(("Expected layout anchors", [f"  - {a}" for a in anchors]))

    exemplars = _exemplar_lines(entity_id, exam_id)
    if exemplars:
        sections.append(("Anonymized exemplars", exemplars))

    def render() -> str:
        out = [
            "Issuer profile context (learned from approved certificates; "
            "use it to recognize labels and value formats, but still quote "
            "verbatim evidence):"
        ]
        for title, lines in sections:
            out.append(f"{title}:")
            out.extend(lines)
        return "\n".join(out)

    text = render()
    # Budget: drop trailing sections first (exemplars, then anchors, labels).
    while len(text) > max_chars and sections:
        sections.pop()
        text = render()
    if len(text) > max_chars:
        text = text[: max_chars - len(TRUNCATION_NOTE)] + TRUNCATION_NOTE
    return text


def profile_context_for(
    entity_id: int, exam_id: int | None = None
) -> tuple[FormatProfile | None, str]:
    """Resolve the profile and its prompt context; ('', profile) when none."""
    profile = select_profile(entity_id, exam_id)
    if profile is None:
        return None, ""
    return profile, build_profile_context(profile)
