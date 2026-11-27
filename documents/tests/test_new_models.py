import pytest

from catalog.models import Entity
from documents.models import (
    EvaluationCase,
    EvaluationRun,
    ExtractionRun,
    FieldLabelAlias,
    VerifierConfig,
)
from documents.tests.factories import (
    make_certificate,
    make_document,
    make_evaluation_case,
    make_evaluation_run,
    make_extraction_run,
    make_field_alias,
    make_format_profile,
    make_verifier_config,
)

pytestmark = pytest.mark.django_db


def test_factories_build_valid_records():
    entity = Entity.objects.create(name="Cambridge English")
    document = make_document()
    certificate = make_certificate(document=document, entity=entity)
    assert certificate.document_id == document.pk

    run = make_extraction_run(document=document, certificate=certificate)
    assert run.status == ExtractionRun.Status.COMPLETED
    assert run.certificate_id == certificate.pk

    config = make_verifier_config(entity=entity)
    assert config.is_active is True

    case = make_evaluation_case(certificate=certificate, entity=entity)
    assert case.set_version == 1

    eval_run = make_evaluation_run()
    assert eval_run.metrics["overall"]["exact_accuracy"] == 0.9

    alias = make_field_alias()
    assert alias.lifecycle == FieldLabelAlias.Lifecycle.ACTIVE

    profile = make_format_profile(entity)
    assert profile.version == 1
    assert profile.value_shapes == {}
    assert profile.quality == {}


def test_new_model_defaults():
    document = make_document()
    certificate = make_certificate(document=document)

    assert certificate.pre_detection == {}
    assert certificate.veracity_score is None
    assert certificate.veracity_components == {}
    assert certificate.source_comparison == {}
    assert certificate.extraction_run_id is None

    run = ExtractionRun.objects.create(document=document)
    assert run.status == ExtractionRun.Status.RUNNING
    assert run.pass_count == 1

    eval_run = EvaluationRun.objects.create()
    assert eval_run.status == EvaluationRun.Status.QUEUED

    case = EvaluationCase.objects.create(certificate=certificate)
    assert case.expected == {}


def test_verifier_config_validation():
    from django.core.exceptions import ValidationError as DjangoValidationError

    bad = VerifierConfig(host="not a host")
    with pytest.raises(DjangoValidationError):
        bad.full_clean()

    bad_template = VerifierConfig(
        host="verify.example.org",
        url_template="https://other.example.org/check",
    )
    with pytest.raises(DjangoValidationError):
        bad_template.full_clean()

    bad_regex = VerifierConfig(host="verify.example.org", code_pattern="([")
    with pytest.raises(DjangoValidationError):
        bad_regex.full_clean()


def test_certificate_veracity_fields_roundtrip():
    certificate = make_certificate()
    certificate.veracity_score = 0.82
    certificate.veracity_components = {"source": 1.0, "format": 0.7}
    certificate.veracity_weights_version = "veracity-v1"
    certificate.save()
    certificate.refresh_from_db()
    assert certificate.veracity_score == pytest.approx(0.82)
    assert certificate.veracity_components["source"] == 1.0
