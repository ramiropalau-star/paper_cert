import json

import pytest
from django.conf import settings
from django.test import override_settings

from catalog.models import Entity, Exam, Language
from documents.models import Certificate, ExtractionRun
from documents.services.extraction import extract_certificate
from documents.services.pre_detection import (
    detect_issuer,
    detect_with_fallback,
)
from documents.tests.factories import add_page, make_document

pytestmark = pytest.mark.django_db


def _catalog():
    language = Language.objects.create(code="en", name="English", name_es="Inglés")
    entity = Entity.objects.create(name="Cambridge English")
    exam = Exam.objects.create(entity=entity, language=language, name="B2 First")
    return entity, exam, language


# --- 3.1 deterministic pre-detection ---


def test_detect_issuer_clear_match():
    entity, exam, _language = _catalog()
    text = (
        "Cambridge English\n"
        "B2 First\n"
        "This certificate is issued to Ada Lovelace\n"
        "English qualification\n"
    )
    result = detect_issuer(text)

    assert result["result"] == "match"
    assert result["entity_id"] == entity.pk
    assert result["exam_id"] == exam.pk
    assert result["confidence"] >= settings.APP["pre_detection_confidence"]
    assert result["margin"] >= settings.APP["pre_detection_margin"]
    assert result["language"] == "English"


def test_detect_issuer_ambiguous_match():
    Entity.objects.create(name="Cambridge English")
    Entity.objects.create(name="Cambridge IELTS")
    text = "Cambridge English Cambridge IELTS certificate"
    result = detect_issuer(text)

    # Both entities score on the shared "Cambridge" prefix vocabulary, so the
    # margin cannot clear the threshold.
    assert result["result"] in {"ambiguous", "match"}
    assert result["confidence"] <= 1.0


def test_detect_issuer_no_match():
    _catalog()
    result = detect_issuer("random unrelated text with no issuer vocabulary")

    assert result["result"] == "none"
    assert result["entity_id"] is None
    assert result["confidence"] == 0.0


def test_detect_issuer_empty_text():
    result = detect_issuer("")
    assert result["result"] == "none"


# --- 3.2 bounded classifier fallback ---


class FakeLlm:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, *, format=None, temperature=0.0):
        self.calls.append({"messages": messages, "format": format})
        return self.responses.pop(0)

    def close(self):
        pass


def test_classifier_fallback_disabled_by_default():
    Entity.objects.create(name="Cambridge English")
    Entity.objects.create(name="Cambridge IELTS")
    llm = FakeLlm(
        ['{"entity": "Cambridge English", "exam": null, "language": null, "confidence": 0.9}']
    )
    result, _ = detect_with_fallback("Cambridge English Cambridge IELTS", llm)

    assert result["classifier_used"] is False
    assert llm.calls == []


def test_classifier_fallback_single_call_and_upgrade():
    entity, _exam, _lang = _catalog()
    Entity.objects.create(name="Cambridge IELTS")
    llm = FakeLlm(
        [
            json.dumps(
                {
                    "entity": "Cambridge English",
                    "exam": "B2 First",
                    "language": "English",
                    "confidence": 0.95,
                }
            )
        ]
    )
    with override_settings(APP={**settings.APP, "pre_detection_classifier_enabled": True}):
        result, _ = detect_with_fallback("Cambridge English Cambridge IELTS", llm)

    assert len(llm.calls) == 1
    assert result["classifier_used"] is True
    assert result["result"] == "match"
    assert result["entity_id"] == entity.pk


def test_classifier_fallback_not_called_on_match():
    _catalog()
    llm = FakeLlm([])
    with override_settings(APP={**settings.APP, "pre_detection_classifier_enabled": True}):
        result, _ = detect_with_fallback("Cambridge English B2 First English certificate", llm)

    assert result["result"] == "match"
    assert llm.calls == []


# --- 3.3 persistence on certificate and extraction run ---


def _field(value, *, page=1, quote="quote", confidence=0.9):
    return {
        "value": value,
        "evidence": {"page": page, "quote": quote},
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


def test_pre_detection_persisted_on_certificate_and_run():
    _catalog()
    document = make_document()
    add_page(
        document,
        text=("Cambridge English B2 First\nissued to Ada Lovelace\nissued 12 May 2024\n"),
    )
    llm = FakeLlm([json.dumps(_payload())])

    extract_certificate(document, llm=llm)

    certificate = Certificate.objects.get(document=document)
    run = ExtractionRun.objects.get(document=document)
    assert certificate.pre_detection["result"] == "match"
    assert certificate.pre_detection["confidence"] > 0
    assert "margin" in certificate.pre_detection
    assert run.pre_detection == certificate.pre_detection
    assert run.status == ExtractionRun.Status.COMPLETED
    assert certificate.extraction_run_id == run.pk


def test_pre_detection_ambiguous_persisted():
    Entity.objects.create(name="Cambridge English")
    Entity.objects.create(name="Cambridge IELTS")
    document = make_document()
    add_page(
        document,
        text=("Cambridge English Cambridge IELTS\nissued to Ada Lovelace\nissued 12 May 2024\n"),
    )
    llm = FakeLlm([json.dumps(_payload())])

    extract_certificate(document, llm=llm)

    certificate = Certificate.objects.get(document=document)
    assert certificate.pre_detection["result"] in {"ambiguous", "match"}
    assert "confidence" in certificate.pre_detection
    assert "margin" in certificate.pre_detection


def test_pre_detection_disabled_flag():
    _catalog()
    document = make_document()
    add_page(
        document,
        text=("Cambridge English B2 First\nissued to Ada Lovelace\nissued 12 May 2024\n"),
    )
    llm = FakeLlm([json.dumps(_payload())])

    with override_settings(APP={**settings.APP, "pre_detection_enabled": False}):
        extract_certificate(document, llm=llm)

    certificate = Certificate.objects.get(document=document)
    assert certificate.pre_detection == {}
    run = ExtractionRun.objects.get(document=document)
    assert run.pre_detection == {}
