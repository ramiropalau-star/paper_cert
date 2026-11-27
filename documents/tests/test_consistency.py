import json

import pytest

from catalog.models import Entity, Exam
from documents.models import Document, ExtractionRun
from documents.services.classification import classify_certificate
from documents.services.consistency import (
    RERUN_MARKER,
    rerun_with_resolved_profile,
)
from documents.services.extraction import run_model_extraction
from documents.services.ollama import OllamaError
from documents.tests.factories import (
    add_page,
    make_certificate,
    make_document,
    make_format_profile,
)

pytestmark = pytest.mark.django_db


class FakeLlm:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, *, format=None, temperature=0.0):
        self.calls.append({"messages": messages, "format": format})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        pass


def _field(value, *, page=1, quote="quote", confidence=0.9):
    return {
        "value": value,
        "evidence": {"page": page, "quote": quote} if quote else None,
        "confidence": confidence,
    }


def _payload(**overrides):
    data = {
        "is_language_certificate": True,
        "multiple_certificates_suspected": False,
        "student_name": _field("Ada Lovelace", quote="issued to Ada Lovelace"),
        "language": _field("English"),
        "entity": _field("Cambridge English"),
        "issuing_body": _field(None),
        "test_center": _field(None),
        "exam": _field("B2 First"),
        "level": _field("B2"),
        "score": _field("180"),
        "certificate_code": _field("CERT-1"),
        "dates": [
            {
                "text": "12 May 2024",
                "role": "issue",
                "page": 1,
                "quote": "issued 12 May 2024",
            }
        ],
        "confidence": 0.9,
    }
    data.update(overrides)
    return data


_DOC_TEXT = "Cambridge English B2 First\nissued to Ada Lovelace\nScore: 180\nissued 12 May 2024\n"


def _classified_document(pre_detection, *, entity_literal="Other Board", exam_literal=""):
    document = make_document(
        processing_state=Document.ProcessingState.EXTRACTED,
    )
    add_page(document, text=_DOC_TEXT)
    certificate = make_certificate(
        document=document,
        entity_literal=entity_literal,
        exam_literal=exam_literal,
        pre_detection=pre_detection,
    )
    return document, certificate


def _entities():
    detected = Entity.objects.create(name="Cambridge English")
    resolved = Entity.objects.create(name="Other Board")
    exam = Exam.objects.create(entity=resolved, name="Other Exam")
    return detected, resolved, exam


# --- 5.1 consistency check ---


def test_entity_mismatch_flagged():
    detected, resolved, _exam = _entities()
    pre = {
        "result": "match",
        "entity_id": detected.pk,
        "exam_id": None,
        "confidence": 0.9,
        "margin": 0.5,
    }
    document, certificate = _classified_document(pre)

    classify_certificate(document)

    certificate.refresh_from_db()
    assert "entity_mismatch" in certificate.review_reasons
    check = certificate.pre_detection["consistency"]
    assert check["entity_mismatch"] is True
    assert check["pre_detected_entity_id"] == detected.pk
    assert check["resolved_entity_id"] == resolved.pk


def test_ambiguous_pre_detection_no_mismatch():
    detected, _resolved, _exam = _entities()
    pre = {
        "result": "ambiguous",
        "entity_id": detected.pk,
        "exam_id": None,
        "confidence": 0.4,
        "margin": 0.05,
    }
    document, certificate = _classified_document(pre)

    classify_certificate(document)

    certificate.refresh_from_db()
    assert "entity_mismatch" not in certificate.review_reasons
    assert certificate.pre_detection["consistency"]["entity_mismatch"] is False


def test_exam_mismatch_flagged():
    _detected, resolved, exam = _entities()
    pre = {
        "result": "match",
        "entity_id": resolved.pk,
        "exam_id": 999999,  # detected exam no longer exists / different
        "confidence": 0.9,
        "margin": 0.5,
    }
    document, certificate = _classified_document(pre, exam_literal="Other Exam")

    classify_certificate(document)

    certificate.refresh_from_db()
    assert certificate.exam_id == exam.pk
    assert "entity_mismatch" in certificate.review_reasons
    check = certificate.pre_detection["consistency"]
    assert check["exam_mismatch"] is True
    assert check["entity_mismatch"] is False


def test_entity_mismatch_reason_renders():
    from documents.review_display import review_reason_items

    items = review_reason_items(["entity_mismatch"])
    assert items[0]["code"] == "entity_mismatch"
    assert items[0]["known"] is True
    assert items[0]["label"]


def test_matching_issuer_no_mismatch():
    detected, _resolved, _exam = _entities()
    pre = {
        "result": "match",
        "entity_id": detected.pk,
        "exam_id": None,
        "confidence": 0.9,
        "margin": 0.5,
    }
    document = make_document(processing_state=Document.ProcessingState.EXTRACTED)
    add_page(document, text=_DOC_TEXT)
    certificate = make_certificate(
        document=document,
        entity_literal="Cambridge English",
        pre_detection=pre,
    )

    classify_certificate(document)

    certificate.refresh_from_db()
    assert "entity_mismatch" not in certificate.review_reasons


# --- 5.2 bounded re-extraction ---


def test_rerun_once_with_resolved_profile():
    _detected, resolved, _exam = _entities()
    profile = make_format_profile(resolved)
    document, certificate = _classified_document(
        {
            "result": "match",
            "entity_id": Entity.objects.create(name="Wrong Board").pk,
            "exam_id": None,
            "confidence": 0.9,
            "margin": 0.5,
        }
    )
    certificate.entity = resolved
    certificate.exam = None
    certificate.save()
    llm = FakeLlm([json.dumps(_payload(entity=_field("Other Board")))])

    assert rerun_with_resolved_profile(document, certificate, llm=llm) is True
    assert rerun_with_resolved_profile(document, certificate, llm=llm) is False

    run = ExtractionRun.objects.get(document=document, fallback_used=RERUN_MARKER)
    assert run.status == ExtractionRun.Status.COMPLETED
    assert run.profile_id == profile.pk
    assert len(llm.calls) == 1


def test_rerun_skipped_without_profile_or_entity():
    _detected, _resolved, _exam = _entities()
    document, certificate = _classified_document({"result": "none"})
    certificate.entity = None
    certificate.save()

    assert rerun_with_resolved_profile(document, certificate, llm=FakeLlm([])) is False
    assert not ExtractionRun.objects.filter(document=document, fallback_used=RERUN_MARKER).exists()


# --- 5.3 bounded fallback-model escalation ---


def _incomplete_payload(**overrides):
    data = _payload(
        score=_field(None),
        dates=[],
    )
    data.update(overrides)
    return data


# Text deliberately lacks score/date patterns so deterministic fallbacks
# cannot fill the critical fields before the fallback model runs.
_FALLBACK_DOC_TEXT = "Cambridge English B2 First\nissued to Ada Lovelace\n"


def test_fallback_model_runs_for_missing_critical_fields():
    page_texts = {1: _FALLBACK_DOC_TEXT}
    primary = FakeLlm(
        [
            json.dumps(_incomplete_payload()),
            json.dumps(_incomplete_payload()),
        ]
    )
    fallback = FakeLlm(
        [
            json.dumps(
                _payload(
                    score=_field("185", quote="Score: 185"),
                    dates=[
                        {
                            "text": "12 May 2024",
                            "role": "issue",
                            "page": 1,
                            "quote": "issued 12 May 2024",
                        }
                    ],
                )
            )
        ]
    )

    outcome = run_model_extraction(
        _FALLBACK_DOC_TEXT, page_texts, {}, primary, fallback_llm=fallback
    )

    assert outcome.fallback_used == "fallback_model"
    assert outcome.fallback_model
    assert outcome.payload.score.value == "185"
    assert len(fallback.calls) == 1
    # The fallback prompt is scoped to the missing fields only.
    fallback_prompt = fallback.calls[0]["messages"][1]["content"]
    assert "score" in fallback_prompt


def test_fallback_skipped_when_extraction_complete():
    page_texts = {1: _DOC_TEXT}
    primary = FakeLlm([json.dumps(_payload())])
    fallback = FakeLlm([])

    outcome = run_model_extraction(_DOC_TEXT, page_texts, {}, primary, fallback_llm=fallback)

    assert outcome.fallback_used == ""
    assert fallback.calls == []


def test_fallback_failure_is_recorded():
    page_texts = {1: _FALLBACK_DOC_TEXT}
    primary = FakeLlm(
        [
            json.dumps(_incomplete_payload()),
            json.dumps(_incomplete_payload()),
        ]
    )
    fallback = FakeLlm([OllamaError("down", code="service_unavailable")])

    outcome = run_model_extraction(
        _FALLBACK_DOC_TEXT, page_texts, {}, primary, fallback_llm=fallback
    )

    assert outcome.fallback_used == ""
    assert outcome.fallback_error
    assert outcome.payload is not None
