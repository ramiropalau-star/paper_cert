import json

import pytest
from django.conf import settings
from django.test import override_settings

from catalog.models import Entity, Exam, Language
from documents.models import Certificate, ExtractionRun, FieldLabelAlias
from documents.services.candidates import (
    Candidate,
    CandidateSet,
    apply_candidates,
    candidates_hint,
    extract_candidates,
)
from documents.services.extraction import (
    ExtractionPayload,
    build_messages,
    extract_certificate,
)
from documents.services.profile_context import (
    build_profile_context,
    profile_context_for,
    select_profile,
)
from documents.tests.factories import (
    add_page,
    make_certificate,
    make_document,
    make_format_profile,
)

pytestmark = pytest.mark.django_db


def _catalog():
    language = Language.objects.create(code="en", name="English", name_es="Inglés")
    entity = Entity.objects.create(name="Cambridge English")
    exam = Exam.objects.create(entity=entity, language=language, name="B2 First")
    return entity, exam, language


# --- 4.1 profile context ---


def test_profile_context_includes_labels_shapes_anchors_exemplars():
    entity, exam, _lang = _catalog()
    profile = make_format_profile(
        entity,
        exam=exam,
        value_shapes={"score": {"pattern": "NNN /100"}, "issue_date": {"order": "dmy"}},
    )
    FieldLabelAlias.objects.create(
        field=FieldLabelAlias.Field.STUDENT_NAME,
        alias="Obtained by",
        scope_entity=entity,
        lifecycle=FieldLabelAlias.Lifecycle.ACTIVE,
    )
    approved = make_certificate(
        entity=entity,
        exam=exam,
        review_status=Certificate.ReviewStatus.APPROVED,
        student_name="Grace Hopper",
        certificate_code="SECRET-99",
        issue_date="2024-05-12",
    )
    approved.save()

    context = build_profile_context(profile)

    assert "Obtained by" in context
    assert "NNN /100" in context
    assert "cambridge english" in context
    assert "[REDACTED]" in context
    assert "[DATE]" in context
    assert "Grace Hopper" not in context
    assert "SECRET-99" not in context


def test_profile_context_budget_truncation():
    entity, _exam, _lang = _catalog()
    profile = make_format_profile(
        entity,
        anchors=[{"text": f"anchor line number {i} with enough text", "df": 2} for i in range(30)],
    )
    with override_settings(APP={**settings.APP, "profile_context_max_chars": 400}):
        context = build_profile_context(profile)

    assert len(context) <= 400 + len("[profile context truncated]")


def test_select_profile_prefers_exam_scope():
    entity, exam, _lang = _catalog()
    entity_profile = make_format_profile(entity, year=2024)
    exam_profile = make_format_profile(entity, exam=exam, year=2024)

    assert select_profile(entity.pk, exam.pk) == exam_profile
    assert select_profile(entity.pk) == entity_profile
    assert select_profile(entity.pk, exam_id=999) == entity_profile


def test_profile_context_for_no_profile():
    entity, _exam, _lang = _catalog()
    profile, context = profile_context_for(entity.pk)
    assert profile is None
    assert context == ""


# --- 4.2 candidate pre-pass ---

PAGE_TEXT = (
    "Cambridge English B2 First\nStudent Name: Ada Lovelace\nScore: 180 / 100\nIssued 12 May 2024\n"
)


def test_extract_candidates_finds_labels_scores_dates():
    candidates = extract_candidates({1: PAGE_TEXT}, {})

    assert candidates.fields["student_name"].value == "Ada Lovelace"
    assert candidates.fields["student_name"].page == 1
    assert candidates.fields["score"].value == "180 / 100"
    assert any(c.kind == "date" and "12 May 2024" in c.value for c in candidates.dates)


def test_apply_candidates_verified_and_unverified():
    payload = ExtractionPayload.model_validate(
        {
            "is_language_certificate": True,
            "multiple_certificates_suspected": False,
            "student_name": {"value": None, "evidence": None, "confidence": None},
            "language": {"value": None, "evidence": None, "confidence": None},
            "entity": {"value": None, "evidence": None, "confidence": None},
            "issuing_body": {"value": None, "evidence": None, "confidence": None},
            "test_center": {"value": None, "evidence": None, "confidence": None},
            "exam": {"value": None, "evidence": None, "confidence": None},
            "level": {"value": None, "evidence": None, "confidence": None},
            "score": {"value": None, "evidence": None, "confidence": None},
            "certificate_code": {"value": None, "evidence": None, "confidence": None},
            "dates": [],
            "confidence": 0.5,
        }
    )
    candidates = CandidateSet(
        fields={
            "student_name": Candidate(
                field="student_name",
                value="Ada Lovelace",
                page=1,
                quote="Student Name: Ada Lovelace",
            ),
            "score": Candidate(
                field="score",
                value="999",
                page=1,
                quote="this quote is not in the page text",
            ),
        }
    )

    unverified = apply_candidates(payload, candidates, {1: PAGE_TEXT})

    assert payload.student_name.value == "Ada Lovelace"
    assert payload.student_name.confidence == 0.4
    assert payload.score.value in (None, "")
    assert "student_name" in unverified
    assert "score" not in unverified


def test_apply_candidates_empty_set_is_noop():
    payload = ExtractionPayload.model_validate(
        {
            "is_language_certificate": True,
            "multiple_certificates_suspected": False,
            "student_name": {"value": "X", "evidence": None, "confidence": None},
            "language": {"value": None, "evidence": None, "confidence": None},
            "entity": {"value": None, "evidence": None, "confidence": None},
            "issuing_body": {"value": None, "evidence": None, "confidence": None},
            "test_center": {"value": None, "evidence": None, "confidence": None},
            "exam": {"value": None, "evidence": None, "confidence": None},
            "level": {"value": None, "evidence": None, "confidence": None},
            "score": {"value": None, "evidence": None, "confidence": None},
            "certificate_code": {"value": None, "evidence": None, "confidence": None},
            "dates": [],
            "confidence": 0.5,
        }
    )
    assert apply_candidates(payload, CandidateSet(), {1: PAGE_TEXT}) == set()
    assert payload.student_name.value == "X"


def test_candidates_hint_renders():
    hint = candidates_hint(
        CandidateSet(fields={"exam": Candidate(field="exam", value="B2 First", page=1, quote="q")})
    )
    assert "B2 First" in hint
    assert candidates_hint(CandidateSet()) == ""


# --- 4.3/4.4 integration ---


class FakeLlm:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, *, format=None, temperature=0.0):
        self.calls.append({"messages": messages, "format": format})
        return self.responses.pop(0)

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


_DOC_TEXT = (
    "Cambridge English B2 First\n"
    "Student Name: Ada Lovelace\n"
    "issued to Ada Lovelace\n"
    "issued 12 May 2024\n"
)


def test_detected_issuer_uses_profile_context_and_records_metadata():
    entity, exam, _lang = _catalog()
    profile = make_format_profile(
        entity,
        value_shapes={"score": {"pattern": "NNN /100"}},
    )
    document = make_document()
    add_page(document, text=_DOC_TEXT)
    llm = FakeLlm([json.dumps(_payload())])

    extract_certificate(document, llm=llm)

    sent = llm.calls[0]["messages"][1]["content"]
    assert "Issuer profile context" in sent
    assert "NNN /100" in sent
    run = ExtractionRun.objects.get(document=document)
    assert run.profile_id == profile.pk
    assert run.profile_version == profile.version
    assert run.model == settings.APP["ollama_model"]
    assert run.prompt_version
    assert run.pre_detection["result"] == "match"
    assert run.pass_count >= 1
    assert run.latency_ms is not None


def test_ambiguous_pre_detection_uses_global_instruction():
    Entity.objects.create(name="Cambridge English")
    Entity.objects.create(name="Cambridge IELTS")
    document = make_document()
    add_page(document, text=_DOC_TEXT)
    llm = FakeLlm([json.dumps(_payload())])

    extract_certificate(document, llm=llm)

    sent = llm.calls[0]["messages"][1]["content"]
    assert "Issuer profile context" not in sent
    assert "Deterministic candidates" not in sent
    run = ExtractionRun.objects.get(document=document)
    assert run.profile_id is None
    assert run.profile_version is None


def test_profile_guided_flag_disabled():
    entity, _exam, _lang = _catalog()
    make_format_profile(entity)
    document = make_document()
    add_page(document, text=_DOC_TEXT)
    llm = FakeLlm([json.dumps(_payload())])

    with override_settings(APP={**settings.APP, "profile_guided_extraction_enabled": False}):
        extract_certificate(document, llm=llm)

    sent = llm.calls[0]["messages"][1]["content"]
    assert "Issuer profile context" not in sent
    run = ExtractionRun.objects.get(document=document)
    assert run.profile_id is None


def test_build_messages_includes_context_and_candidates():
    messages = build_messages(
        "doc text",
        {},
        profile_context="Issuer profile context: ...",
        candidates_hint="Deterministic candidates found ...",
    )
    content = messages[1]["content"]
    assert "Issuer profile context" in content
    assert "Deterministic candidates" in content
