"""Tests for review-driven catalog learning and format profiles."""

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from catalog.models import (
    CefrConversionRule,
    Entity,
    EntityAlias,
    Equivalence,
    Exam,
    FormatProfile,
    Language,
)
from catalog.normalization import normalize_catalog_text
from documents.models import Certificate, Document, DocumentPage, ReviewEvent
from documents.services.classification import classify_certificate, resolve_entity
from documents.services.format_profile import (
    learn_format_profile,
    score_document_format,
)
from documents.services.learning import learn_from_certificate
from documents.services.review import approve_certificate, reject_certificate, validate_certificate

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def catalog(db):
    call_command("seed_catalog", verbosity=0)


def make_user(username: str = "reviewer") -> User:
    return User.objects.create_user(username, password="password")


def make_document(**overrides) -> Document:
    data = {
        "fingerprint": "f" * 64,
        "original_filename": "certificate.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
        "paperless_document_id": "42",
        "processing_state": Document.ProcessingState.PENDING_REVIEW,
    }
    data.update(overrides)
    return Document.objects.create(**data)


def make_certificate(document: Document, **overrides) -> Certificate:
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
        "confidence": 0.9,
        "review_status": Certificate.ReviewStatus.PENDING,
    }
    data.update(overrides)
    return Certificate.objects.create(**data)


def resolved_certificate(document: Document, **overrides) -> Certificate:
    cert = make_certificate(document, **overrides)
    cert.language = Language.objects.get(code="eng")
    cert.entity = Entity.objects.get(name="Cambridge English")
    cert.save()
    return cert


def add_page(document: Document, text: str, number: int = 1) -> None:
    DocumentPage.objects.create(
        document=document,
        page_number=number,
        text=text,
        method=DocumentPage.Method.EMBEDDED,
    )


BOILERPLATE = (
    "cambridge assessment english\n"
    "this is to certify that\n"
    "certificate of proficiency in english"
)


# --- catalog learning service ---


def test_learn_creates_alias_for_literal_variant():
    document = make_document()
    cert = resolved_certificate(document, entity_literal="Cambridge ESOL Exams")

    outcome = learn_from_certificate(cert, make_user())

    entity = Entity.objects.get(name="Cambridge English")
    alias = EntityAlias.objects.get(normalized_alias=normalize_catalog_text("Cambridge ESOL Exams"))
    assert alias.entity_id == entity.pk
    assert resolve_entity("Cambridge ESOL Exams") == entity
    assert outcome["aliases_created"]


def test_learn_is_idempotent():
    document = make_document()
    cert = resolved_certificate(document, entity_literal="Cambridge ESOL Exams")
    user = make_user()

    learn_from_certificate(cert, user)
    second = learn_from_certificate(cert, user)

    assert EntityAlias.objects.filter(
        normalized_alias=normalize_catalog_text("Cambridge ESOL Exams")
    ).count() == 1
    assert second["aliases_created"] == []


def test_learn_alias_conflict_is_skipped():
    other = Entity.objects.create(name="Other Board")
    normalized = normalize_catalog_text("Shared Alias Name")
    EntityAlias.objects.create(entity=other, alias="Shared Alias Name")

    document = make_document()
    cert = resolved_certificate(document, entity_literal="Shared Alias Name")

    outcome = learn_from_certificate(cert, make_user())

    assert EntityAlias.objects.filter(normalized_alias=normalized).count() == 1
    assert EntityAlias.objects.get(normalized_alias=normalized).entity_id == other.pk
    assert outcome["conflicts"]


def test_learn_creates_exam_for_unknown_literal():
    document = make_document()
    cert = resolved_certificate(
        document, exam_literal="KET for Schools", exam=None
    )
    cert.exam = None
    cert.save()

    outcome = learn_from_certificate(cert, make_user())

    exam = Exam.objects.get(entity__name="Cambridge English", name="KET for Schools")
    assert exam.language_id == cert.language_id
    assert outcome["exams_created"] == ["KET for Schools"]


def test_learn_equivalence_creates_review_rule():
    exam = Exam.objects.get(entity__name="Cambridge English", name="B2 First")
    document = make_document()
    cert = resolved_certificate(
        document, exam=exam, exam_literal="B2 First", equivalence="A2"
    )

    outcome = learn_from_certificate(cert, make_user())

    rule = Equivalence.objects.get(exam=exam, accredited_level="A2")
    assert rule.is_active is True
    assert rule.source == "review"
    assert outcome["equivalences_created"]


def test_learn_equivalence_skips_existing_level():
    exam = Exam.objects.get(entity__name="Cambridge English", name="B2 First")
    document = make_document()
    cert = resolved_certificate(document, exam=exam, equivalence="B2")

    outcome = learn_from_certificate(cert, make_user())

    assert outcome["equivalences_created"] == []
    assert Equivalence.objects.filter(exam=exam, accredited_level="B2").count() == 1


def test_learn_cefr_rule_is_inactive_candidate():
    exam = Exam.objects.get(entity__name="Cambridge English", name="B2 First")
    document = make_document()
    cert = resolved_certificate(
        document,
        exam=exam,
        cefr_source=Certificate.CefrSource.MANUAL,
        cefr_level="B2",
        score_literal="180",
    )
    user = make_user()

    learn_from_certificate(cert, user)
    learn_from_certificate(cert, user)

    rule = CefrConversionRule.objects.get(
        exam=exam, cefr_level="B2", reference=f"review:certificate:{cert.pk}"
    )
    assert rule.is_active is False
    assert rule.score_min == rule.score_max == 180
    assert rule.approved_by == user.username
    assert rule.reference.startswith("review:certificate:")


# --- review hooks ---


def test_approve_runs_learning_and_records_outcome():
    document = make_document()
    cert = resolved_certificate(document, entity_literal="Cambridge ESOL Exams")
    user = make_user()

    outcome = approve_certificate(cert, user)

    assert outcome.ok is True
    assert EntityAlias.objects.filter(
        normalized_alias=normalize_catalog_text("Cambridge ESOL Exams")
    ).exists()
    event = ReviewEvent.objects.get(certificate=cert, event_type=ReviewEvent.EventType.APPROVE)
    assert event.after["learning"]["aliases_created"]


def test_learning_failure_does_not_block_approval(monkeypatch):
    document = make_document()
    cert = resolved_certificate(document)
    user = make_user()

    def boom(certificate, actor):
        raise RuntimeError("catalog exploded")

    monkeypatch.setattr("documents.services.review.learn_from_certificate", boom)

    outcome = approve_certificate(cert, user)

    assert outcome.ok is True
    cert.refresh_from_db()
    assert cert.review_status == Certificate.ReviewStatus.APPROVED


def test_reject_does_not_teach():
    document = make_document()
    cert = resolved_certificate(document, entity_literal="Cambridge ESOL Exams")

    outcome = reject_certificate(cert, make_user(), "not a certificate")

    assert outcome.ok is True
    assert not EntityAlias.objects.filter(
        normalized_alias=normalize_catalog_text("Cambridge ESOL Exams")
    ).exists()


def test_validate_runs_learning():
    document = make_document()
    cert = resolved_certificate(document, entity_literal="Cambridge ESOL Exams")

    outcome = validate_certificate(cert, make_user())

    assert outcome.ok is True
    assert EntityAlias.objects.filter(
        normalized_alias=normalize_catalog_text("Cambridge ESOL Exams")
    ).exists()


# --- format profiles ---


def _approved_certificate(document: Document, year: int = 2024, **overrides) -> Certificate:
    cert = resolved_certificate(
        document,
        issue_date=date(year, 5, 12),
        review_status=Certificate.ReviewStatus.APPROVED,
        **overrides,
    )
    document.processing_state = Document.ProcessingState.APPROVED
    document.save(update_fields=["processing_state"])
    return cert


def test_format_profile_learns_corroborated_anchors():
    doc1 = make_document(fingerprint="1" * 64)
    doc2 = make_document(fingerprint="2" * 64)
    add_page(doc1, BOILERPLATE + "\nunique line one")
    add_page(doc2, BOILERPLATE + "\nunique line two")
    cert1 = _approved_certificate(doc1)
    cert2 = _approved_certificate(doc2)

    learn_format_profile(cert1)
    learn_format_profile(cert2)

    profile = FormatProfile.objects.get(entity=cert1.entity, year=2024, exam__isnull=True)
    texts = {a["text"] for a in profile.anchors}
    assert "this is to certify that" in texts
    assert "unique line one" not in texts
    assert profile.sample_count == 2


def test_format_profile_isolated_by_year():
    old_doc = make_document(fingerprint="3" * 64)
    new_doc = make_document(fingerprint="4" * 64)
    old_text = BOILERPLATE + "\nold layout marker phrase"
    new_text = BOILERPLATE + "\nnew layout marker phrase"
    for doc, text in ((old_doc, old_text), (new_doc, new_text)):
        add_page(doc, text)
        add_page(doc, text, number=2)  # second doc needs 2 samples per cohort
    old_doc2 = make_document(fingerprint="5" * 64)
    new_doc2 = make_document(fingerprint="6" * 64)
    add_page(old_doc2, old_text)
    add_page(new_doc2, new_text)

    for doc, year in (
        (old_doc, 2020), (old_doc2, 2020), (new_doc, 2024), (new_doc2, 2024)
    ):
        cert = _approved_certificate(doc, year=year)
        learn_format_profile(cert)

    old_profile = FormatProfile.objects.get(entity__name="Cambridge English", year=2020, exam__isnull=True)
    new_profile = FormatProfile.objects.get(entity__name="Cambridge English", year=2024, exam__isnull=True)
    old_texts = {a["text"] for a in old_profile.anchors}
    new_texts = {a["text"] for a in new_profile.anchors}
    assert "old layout marker phrase" in old_texts
    assert "old layout marker phrase" not in new_texts
    assert "new layout marker phrase" in new_texts


def test_format_score_high_for_matching_document():
    docs = []
    for i in range(2):
        doc = make_document(fingerprint=f"{i+10}" * 64)
        add_page(doc, BOILERPLATE)
        cert = _approved_certificate(doc)
        learn_format_profile(cert)
        docs.append(doc)

    probe_doc = make_document(fingerprint="9" * 64, processing_state=Document.ProcessingState.PENDING_REVIEW)
    add_page(probe_doc, BOILERPLATE + "\nsome student name here")
    probe = resolved_certificate(probe_doc)

    score, cohort = score_document_format(probe)

    assert score is not None and score > 0.8
    assert "2024" in cohort


def test_format_score_none_without_samples():
    doc = make_document()
    add_page(doc, BOILERPLATE)
    cert = _approved_certificate(doc)
    learn_format_profile(cert)

    probe_doc = make_document(fingerprint="8" * 64)
    add_page(probe_doc, BOILERPLATE)
    probe = resolved_certificate(probe_doc)

    score, _cohort = score_document_format(probe)

    assert score is None


def test_classification_blends_format_score_and_flags_mismatch():
    entity = Entity.objects.get(name="Cambridge English")
    FormatProfile.objects.create(
        entity=entity,
        year=2024,
        sample_count=3,
        anchors=[{"text": "totally unrelated boilerplate phrase", "df": 3}],
    )
    document = make_document(
        fingerprint="7" * 64,
        processing_state=Document.ProcessingState.EXTRACTED,
    )
    add_page(document, "cambridge assessment english certificate text here")
    cert = make_certificate(
        document,
        language_literal="English",
        entity_literal="Cambridge English",
        exam_literal="B2 First",
        level_literal="B2",
        score_literal="180",
        issue_date=None,
        date_texts={
            "candidates": [
                {"text": "12 May 2024", "role": "issue", "page": 1, "quote": "q"}
            ]
        },
    )

    result = classify_certificate(document)

    assert result.state == Document.ProcessingState.PENDING_REVIEW
    cert.refresh_from_db()
    assert cert.format_score == 0.0
    assert cert.format_cohort
    assert "format_mismatch" in cert.review_reasons
    assert cert.review_reasons and "format_mismatch" in result.review_reasons
    assert cert.confidence == round(0.9 * 0.7 + 0.0 * 0.3, 4)


def test_detail_shows_format_score_and_cohort():
    from django.contrib.auth.models import Group
    from django.test import Client
    from django.urls import reverse

    user = User.objects.create_user("fmtviewer", password="password")
    group, _ = Group.objects.get_or_create(name="viewer")
    user.groups.add(group)
    client = Client()
    client.force_login(user)

    document = make_document()
    cert = resolved_certificate(
        document, format_score=0.83, format_cohort="Cambridge English 2024"
    )

    response = client.get(reverse("documents:detail", args=[document.pk]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Formato" in content
    assert "0,83" in content
    assert "Cambridge English 2024" in content


# --- learn_from_history backfill ---


def test_learn_from_history_command_is_idempotent():
    from django.core.management import call_command as cmd

    doc = make_document()
    _approved_certificate(doc, entity_literal="Cambridge ESOL Exams")

    cmd("learn_from_history", verbosity=0)
    cmd("learn_from_history", verbosity=0)

    assert EntityAlias.objects.filter(
        normalized_alias=normalize_catalog_text("Cambridge ESOL Exams")
    ).count() == 1
    assert ReviewEvent.objects.filter(
        event_type=ReviewEvent.EventType.LEARN
    ).count() == 1


def test_learn_from_history_dry_run_writes_nothing():
    from django.core.management import call_command as cmd

    doc = make_document()
    _approved_certificate(doc, entity_literal="Cambridge ESOL Exams")

    cmd("learn_from_history", "--dry-run", verbosity=0)

    assert not EntityAlias.objects.filter(
        normalized_alias=normalize_catalog_text("Cambridge ESOL Exams")
    ).exists()
    assert not FormatProfile.objects.exists()
