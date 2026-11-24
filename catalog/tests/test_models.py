import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from catalog.models import (
    CefrConversionRule,
    Entity,
    EntityAlias,
    Exam,
    Language,
    LanguageAlias,
)

pytestmark = pytest.mark.django_db


def test_language_alias_normalizes_and_is_unique():
    language = Language.objects.create(code="eng", name="English")
    alias = LanguageAlias.objects.create(language=language, alias="  English   Language  ")

    assert alias.normalized_alias == "english language"

    with pytest.raises(IntegrityError), transaction.atomic():
        LanguageAlias.objects.create(language=language, alias="english language")


def test_entity_alias_normalizes_and_rejects_duplicates_across_entities():
    first = Entity.objects.create(name="First Entity")
    second = Entity.objects.create(name="Second Entity")

    alias = EntityAlias.objects.create(entity=first, alias="  First   Entity ")
    assert alias.normalized_alias == "first entity"

    with pytest.raises(IntegrityError), transaction.atomic():
        EntityAlias.objects.create(entity=second, alias="first entity")


def test_exam_name_is_unique_per_entity():
    language = Language.objects.create(code="eng", name="English")
    entity = Entity.objects.create(name="Example Board")
    Exam.objects.create(entity=entity, language=language, name="Example Exam")

    with pytest.raises(IntegrityError), transaction.atomic():
        Exam.objects.create(entity=entity, language=language, name="Example Exam")

    other = Entity.objects.create(name="Another Board")
    Exam.objects.create(entity=other, language=language, name="Example Exam")


def test_inactive_cefr_rule_is_allowed_but_not_effective():
    exam = Exam.objects.create(name="Example Exam")
    rule = CefrConversionRule.objects.create(
        exam=exam,
        score_min=7,
        score_max=8,
        cefr_level="C1",
        reference="Placeholder",
    )

    assert rule.is_active is False
    assert rule.approved_at is None
    assert CefrConversionRule.objects.effective().count() == 0


def test_active_cefr_rule_requires_approver_and_reference():
    exam = Exam.objects.create(name="Example Exam")

    with pytest.raises(ValidationError):
        CefrConversionRule.objects.create(
            exam=exam,
            score_min=7,
            score_max=8,
            cefr_level="C1",
            is_active=True,
        )


def test_active_cefr_rule_records_approval_and_is_effective():
    exam = Exam.objects.create(name="Example Exam")
    rule = CefrConversionRule.objects.create(
        exam=exam,
        score_min=7,
        score_max=8,
        cefr_level="C1",
        reference="Official mapping",
        approved_by="Coordinator",
        is_active=True,
    )

    assert rule.approved_at is not None
    assert list(CefrConversionRule.objects.effective()) == [rule]


def test_cefr_rule_rejects_inverted_score_range():
    exam = Exam.objects.create(name="Example Exam")

    with pytest.raises(ValidationError):
        CefrConversionRule.objects.create(
            exam=exam,
            score_min=8,
            score_max=7,
            cefr_level="C1",
        )
