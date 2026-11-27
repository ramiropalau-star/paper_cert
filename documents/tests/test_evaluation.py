import json
from datetime import date

import pytest
from django.core.management import call_command

from catalog.models import Entity, Exam
from documents.models import (
    Certificate,
    Document,
    EvaluationCase,
    EvaluationRun,
)
from documents.services.evaluation import (
    build_golden_set,
    compare_metrics,
    create_evaluation_run,
    latest_golden_set,
    pages_from_source_text,
    run_evaluation,
)
from documents.tests.factories import (
    add_page,
    make_certificate,
    make_document,
)

pytestmark = pytest.mark.django_db

PAGE_BODY = (
    "student: Ada Lovelace\nCambridge English B2 First\nScore: 180\nDate of Issue: 12 May 2024\n"
)
SOURCE_TEXT = "--- Page 1 ---\n" + PAGE_BODY


def field(value, *, page=1, quote="quote", confidence=0.9):
    return {
        "value": value,
        "evidence": {"page": page, "quote": quote} if value else None,
        "confidence": confidence,
    }


def payload_dict(**overrides):
    data = {
        "is_language_certificate": True,
        "multiple_certificates_suspected": False,
        "student_name": field("Ada Lovelace", quote="student: Ada Lovelace"),
        "language": field("English", quote="Cambridge English B2 First"),
        "entity": field("Cambridge English", quote="Cambridge English B2 First"),
        "issuing_body": field(None),
        "test_center": field(None),
        "exam": field("B2 First", quote="Cambridge English B2 First"),
        "level": field("B2", quote="Cambridge English B2 First"),
        "score": field("180", quote="Score: 180"),
        "certificate_code": field(None),
        "dates": [
            {
                "text": "12 May 2024",
                "role": "issue",
                "page": 1,
                "quote": "Date of Issue: 12 May 2024",
            }
        ],
        "confidence": 0.9,
    }
    data.update(overrides)
    return data


class FakeLLM:
    """Duck-typed OllamaClient returning canned payloads."""

    def __init__(self, payloads=None, error=None):
        self.payloads = list(payloads or [payload_dict()])
        self.error = error
        self.calls = 0

    def chat(self, messages, *, format=None, temperature=0.0):
        self.calls += 1
        if self.error is not None:
            raise self.error
        index = min(self.calls - 1, len(self.payloads) - 1)
        return json.dumps(self.payloads[index])

    def close(self):
        pass


def approved_certificate(**overrides):
    document = make_document(
        processing_state=Document.ProcessingState.PENDING_REVIEW,
    )
    add_page(document, 1, PAGE_BODY)
    data = {
        "document": document,
        "student_name": "Ada Lovelace",
        "language_literal": "English",
        "entity_literal": "Cambridge English",
        "exam_literal": "B2 First",
        "level_literal": "B2",
        "score_literal": "180",
        "issue_date": date(2024, 5, 12),
        "is_language_certificate": True,
        "review_status": Certificate.ReviewStatus.APPROVED,
    }
    data.update(overrides)
    return make_certificate(**data)


def test_golden_set_includes_only_confirmed():
    approved_certificate()
    make_certificate(
        review_status=Certificate.ReviewStatus.REJECTED,
        student_name="Rejected Person",
    )
    make_certificate(review_status=Certificate.ReviewStatus.PENDING)

    result = build_golden_set()

    assert result["set_version"] == 1
    assert result["cases"] == 1
    case = EvaluationCase.objects.get()
    assert case.expected["student_name"] == "Ada Lovelace"
    assert case.expected["issue_date"] == "2024-05-12"
    assert case.source_text == SOURCE_TEXT


def test_golden_set_versions_are_immutable():
    approved_certificate()
    first = build_golden_set()
    EvaluationCase.objects.filter(pk=EvaluationCase.objects.first().pk).update(
        expected={"student_name": "TAMPERED"}
    )
    # A second build creates v2 and leaves v1 rows untouched.
    approved_certificate(student_name="Grace Hopper")
    second = build_golden_set()

    assert first["set_version"] == 1
    assert second["set_version"] == 2
    v1 = EvaluationCase.objects.get(set_version=1)
    assert v1.expected["student_name"] == "TAMPERED"  # history preserved, not rebuilt
    assert EvaluationCase.objects.filter(set_version=2).count() == 2


def test_dry_run_leaves_live_data_unchanged():
    certificate = approved_certificate()
    document = certificate.document
    before = {
        "state": document.processing_state,
        "reasons": list(document.review_reasons or []),
        "student": certificate.student_name,
        "review_status": certificate.review_status,
    }
    build_golden_set()
    # Force the case to pending-source text by rebuilding expected from cert.
    run = create_evaluation_run()
    run_evaluation(run, llm=FakeLLM())

    document.refresh_from_db()
    certificate.refresh_from_db()
    assert document.processing_state == before["state"]
    assert list(document.review_reasons or []) == before["reasons"]
    assert certificate.student_name == before["student"]
    assert certificate.review_status == before["review_status"]
    assert certificate.extraction_run_id is None
    assert run.status == EvaluationRun.Status.COMPLETED


def test_metrics_unit_synthetic():
    entity = Entity.objects.create(name="Cambridge English")
    exam = Exam.objects.create(name="B2 First", entity=entity)
    certificate = approved_certificate(entity=entity, exam=exam)
    certificate.entity = entity
    certificate.exam = exam
    certificate.save()
    build_golden_set()
    # Remove the date line from the case source so nothing can recover it.
    EvaluationCase.objects.update(
        source_text=SOURCE_TEXT.replace("Date of Issue: 12 May 2024\n", "")
    )

    # Model returns a wrong score and misses the issue date evidence.
    bad = payload_dict(
        score=field("999", quote="Score: 180"),
        dates=[],
    )
    run = create_evaluation_run()
    run_evaluation(run, llm=FakeLLM([bad]))

    run.refresh_from_db()
    overall = run.metrics["overall"]
    fields = overall["fields"]
    assert fields["student_name"]["normalized_accuracy"] == 1.0
    assert fields["score_literal"]["normalized_accuracy"] == 0.0
    assert fields["issue_date"]["missing"] == 1
    assert overall["schema_validity"] == 1.0
    assert overall["latency"]["total_ms"] >= 0
    assert "Cambridge English" in run.metrics["by_entity"]
    assert "B2 First" in run.metrics["by_exam"]


def test_evidence_validity_counted():
    approved_certificate()
    build_golden_set()
    run = create_evaluation_run()
    run_evaluation(run, llm=FakeLLM())
    run.refresh_from_db()
    # All fixture quotes appear verbatim in SOURCE_TEXT.
    assert run.metrics["overall"]["evidence_validity"] == 1.0


def test_baseline_comparison_reports_regression():
    approved_certificate()
    build_golden_set()

    good_run = create_evaluation_run()
    run_evaluation(good_run, llm=FakeLLM())
    good_run.refresh_from_db()

    bad = payload_dict(student_name=field("Wrong Name", quote="student: Ada Lovelace"))
    bad_run = create_evaluation_run()
    from documents.services.evaluation import run_evaluation_with_baseline

    run_evaluation_with_baseline(bad_run, baseline_run=good_run, llm=FakeLLM([bad]))
    bad_run.refresh_from_db()

    assert bad_run.comparison["regressions"]
    assert "student_name" in bad_run.comparison["regressions"]
    field_cmp = bad_run.comparison["fields"]["student_name"]
    assert field_cmp["status"] == "regression"
    assert field_cmp["baseline"] == 1.0
    assert field_cmp["current"] == 0.0
    # Comparison never mutates live configuration.
    assert not hasattr(bad_run, "is_active")


def test_compare_metrics_improvement_and_same():
    base = {
        "overall": {
            "fields": {
                "score_literal": {"normalized_accuracy": 0.5},
                "student_name": {"normalized_accuracy": 0.9},
            },
            "totals": {"normalized_accuracy": 0.7},
        }
    }
    current = {
        "overall": {
            "fields": {
                "score_literal": {"normalized_accuracy": 0.9},
                "student_name": {"normalized_accuracy": 0.9},
            },
            "totals": {"normalized_accuracy": 0.8},
        }
    }
    out = compare_metrics(base, current, tolerance=0.02)
    assert out["fields"]["score_literal"]["status"] == "improvement"
    assert out["fields"]["student_name"]["status"] == "same"
    assert out["improvements"] == ["score_literal"]
    assert out["regressions"] == []


def test_pages_from_source_text_roundtrip():
    pages = pages_from_source_text(SOURCE_TEXT)
    assert pages == {1: SOURCE_TEXT.split("--- Page 1 ---\n", 1)[1].strip()}


def test_latest_golden_set():
    assert latest_golden_set() is None
    approved_certificate()
    build_golden_set()
    assert latest_golden_set() == (1, 1)


def test_evaluate_command_build_and_list(capsys):
    approved_certificate()
    call_command("evaluate_extraction", "build-set")
    call_command("evaluate_extraction", "list")
    out = capsys.readouterr().out
    assert "v1" in out
    assert "1 cases" in out


def test_evaluate_command_run_with_fake_llm(monkeypatch, capsys):
    approved_certificate()
    call_command("evaluate_extraction", "build-set")

    import documents.services.evaluation as evaluation_service

    monkeypatch.setattr(evaluation_service, "build_ollama_client", lambda: FakeLLM())
    call_command("evaluate_extraction", "run")
    out = capsys.readouterr().out
    assert "Run" in out
    run = EvaluationRun.objects.latest("pk")
    assert run.status == EvaluationRun.Status.COMPLETED
    assert run.metrics["case_count"] == 1
