from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from catalog.models import CefrConversionRule, Exam
from catalog.normalization import normalize_catalog_text
from documents.models import Certificate, Document
from documents.services.classification import (
    classify_certificate,
    explicit_cefr,
    parse_date_text,
    parse_score,
    resolve_entity,
    resolve_exam,
    resolve_language,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def catalog(db):
    call_command("seed_catalog", verbosity=0)


def make_document(**overrides) -> Document:
    data = {
        "fingerprint": "d" * 64,
        "original_filename": "certificate.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
        "paperless_document_id": "42",
        "processing_state": Document.ProcessingState.EXTRACTED,
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
        "is_language_certificate": True,
        "confidence": 0.9,
        "date_texts": {
            "candidates": [{"text": "12 May 2024", "role": "issue", "page": 1, "quote": "q"}]
        },
    }
    data.update(overrides)
    return Certificate.objects.create(**data)


class FakeStore:
    def __init__(self):
        self.tags: list[tuple[str, str]] = []
        self.closed = False

    def add_tag(self, document_id, name):
        self.tags.append((document_id, name))
        return True

    def remove_tag(self, document_id, name):
        return True

    def close(self):
        self.closed = True


# --- 8.1 normalization and exact alias matching ---


def test_normalize_catalog_text_variants():
    assert normalize_catalog_text("  Cambridge   ENGLISH ") == "cambridge english"
    assert normalize_catalog_text("Ｇｏｅｔｈｅ") == "goethe"
    assert normalize_catalog_text("") == ""


def test_language_alias_matching_accepts_known_variants():
    language = resolve_language("english")
    assert language is not None and language.code == "eng"
    assert resolve_language("Inglés").code == "eng"
    assert resolve_language("  SPANISH  ").code == "spa"


def test_language_matching_rejects_fuzzy_near_matches():
    assert resolve_language("Englsh") is None
    assert resolve_language("English language") is None
    assert resolve_language("") is None


def test_entity_alias_matching_accepts_variants():
    assert resolve_entity("cambridge").name == "Cambridge English"
    assert resolve_entity("Goethe Institut").name == "Goethe-Institut"
    assert resolve_entity("Cervantes").name == "Instituto Cervantes"


def test_entity_matching_rejects_fuzzy_near_matches():
    assert resolve_entity("Cambridge Universyty") is None
    assert resolve_entity("Goethe Institut Berlin") is None


def test_exam_alias_matching_accepts_known_variants():
    exam = resolve_exam("First Certiﬁcate in English", None, None)
    assert exam is not None and exam.name == "B2 First"
    assert resolve_exam("Integrated Skills in English (ISE)", None, None).name == "ISE"
    assert resolve_exam("Examen Inventado", None, None) is None


# --- 8.2 language and entity classification ---


def test_classification_resolves_language_entity_and_exam():
    document = make_document()
    certificate = make_certificate(document)
    store = FakeStore()

    result = classify_certificate(document, store=store)

    certificate.refresh_from_db()
    assert certificate.language.code == "eng"
    assert certificate.entity.name == "Cambridge English"
    assert certificate.exam.name == "B2 First"
    assert certificate.language_literal == "English"
    assert certificate.entity_literal == "Cambridge English"
    assert document.processing_state == Document.ProcessingState.PENDING_REVIEW
    assert result.state == Document.ProcessingState.PENDING_REVIEW


def test_unknown_entity_stays_literal_and_pending_identification():
    document = make_document()
    certificate = make_certificate(document, entity_literal="Universidad Desconocida")

    classify_certificate(document, store=FakeStore())

    certificate.refresh_from_db()
    assert certificate.entity is None
    assert certificate.entity_literal == "Universidad Desconocida"
    assert "unknown_entity" in certificate.review_reasons


def test_unknown_language_stays_unresolved():
    document = make_document()
    certificate = make_certificate(document, language_literal="Klingon")

    classify_certificate(document, store=FakeStore())

    certificate.refresh_from_db()
    assert certificate.language is None
    assert certificate.language_literal == "Klingon"
    assert "unknown_language" in certificate.review_reasons


def test_unresolved_entity_or_language_applies_manual_label():
    document = make_document()
    make_certificate(document, entity_literal="Desconocida")
    store = FakeStore()

    classify_certificate(document, store=store)

    assert store.tags == [("42", "Otros")]


def test_entity_roles_are_not_invented():
    document = make_document()
    certificate = make_certificate(
        document,
        issuing_body_literal="",
        test_center_literal="",
    )

    classify_certificate(document, store=FakeStore())

    certificate.refresh_from_db()
    assert certificate.issuing_body_literal == ""
    assert certificate.test_center_literal == ""
    assert certificate.entity.name == "Cambridge English"


# --- 8.3 CEFR assignment ---


def test_explicit_cefr_level_is_used():
    document = make_document()
    make_certificate(document, level_literal="Level B2 (MCER)")

    classify_certificate(document, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert certificate.cefr_level == "B2"
    assert certificate.cefr_source == Certificate.CefrSource.EXPLICIT


def test_approved_rule_assigns_cefr_and_records_source():
    exam = Exam.objects.get(name="IELTS Academic")
    CefrConversionRule.objects.create(
        exam=exam,
        score_min=Decimal("7.0"),
        score_max=Decimal("8.0"),
        cefr_level="C1",
        reference="Institutional band mapping 2024",
        approved_by="Academic Board",
        is_active=True,
    )
    document = make_document()
    make_certificate(
        document,
        entity_literal="IELTS",
        exam_literal="IELTS Academic",
        level_literal="Band 7.5",
        score_literal="7.5",
    )

    classify_certificate(document, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert certificate.cefr_level == "C1"
    assert certificate.cefr_source == Certificate.CefrSource.APPROVED_RULE


def test_unapproved_or_inactive_rule_never_applies():
    exam = Exam.objects.get(name="IELTS Academic")
    CefrConversionRule.objects.create(
        exam=exam,
        score_min=Decimal("7.0"),
        score_max=Decimal("8.0"),
        cefr_level="C1",
        reference="Placeholder",
        is_active=False,
    )
    document = make_document()
    make_certificate(
        document,
        entity_literal="IELTS",
        exam_literal="IELTS Academic",
        level_literal="",
        score_literal="7.5",
    )

    classify_certificate(document, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert certificate.cefr_level == ""
    assert certificate.cefr_source == ""
    assert certificate.level_literal == ""
    assert certificate.score_literal == "7.5"


def test_no_rule_leaves_cefr_empty_and_preserves_literals():
    document = make_document()
    certificate = make_certificate(document, level_literal="Score 180", score_literal="180")

    classify_certificate(document, store=FakeStore())

    certificate.refresh_from_db()
    assert certificate.cefr_level == ""
    assert certificate.cefr_source == ""
    assert certificate.level_literal == "Score 180"


def test_explicit_cefr_helper():
    assert explicit_cefr("B2") == "B2"
    assert explicit_cefr("nivel c1") == "C1"
    assert explicit_cefr("180") == ""
    assert explicit_cefr("") == ""


def test_parse_score_extracts_numbers():
    assert parse_score("180") == Decimal("180")
    assert parse_score("7,5") == Decimal("7.5")
    assert parse_score("score: 92/100") == Decimal("92")
    assert parse_score("") is None
    assert parse_score("N/A") is None


# --- 8.4 dates ---


def test_parse_date_text_formats():
    parsed, ambiguous = parse_date_text("12 May 2024")
    assert parsed == date(2024, 5, 12) and not ambiguous
    parsed, ambiguous = parse_date_text("2024-05-12")
    assert parsed == date(2024, 5, 12) and not ambiguous
    parsed, ambiguous = parse_date_text("25/12/2024")
    assert parsed == date(2024, 12, 25) and not ambiguous


def test_parse_date_text_ambiguous_day_month():
    parsed, ambiguous = parse_date_text("05/06/2024")
    assert ambiguous is True
    assert parsed == date(2024, 6, 5)


def test_dates_assigned_to_distinct_fields_with_originals():
    document = make_document()
    certificate = make_certificate(
        document,
        date_texts={
            "candidates": [
                {"text": "12 May 2024", "role": "issue", "page": 1, "quote": ""},
                {"text": "10 May 2024", "role": "exam", "page": 1, "quote": ""},
                {"text": "11 May 2024", "role": "result", "page": 1, "quote": ""},
            ]
        },
    )

    classify_certificate(document, store=FakeStore())

    certificate.refresh_from_db()
    assert certificate.issue_date == date(2024, 5, 12)
    assert certificate.exam_date == date(2024, 5, 10)
    assert certificate.result_date == date(2024, 5, 11)
    originals = certificate.date_texts["originals"]
    assert originals["issue_date"] == "12 May 2024"
    assert originals["exam_date"] == "10 May 2024"
    assert originals["result_date"] == "11 May 2024"


def test_single_undetermined_date_becomes_detected_date():
    document = make_document()
    certificate = make_certificate(
        document,
        date_texts={
            "candidates": [{"text": "12 May 2024", "role": "unknown", "page": 1, "quote": ""}]
        },
    )

    classify_certificate(document, store=FakeStore())

    certificate.refresh_from_db()
    assert certificate.detected_date == date(2024, 5, 12)
    assert certificate.issue_date is None
    assert "ambiguous_date" in certificate.review_reasons


def test_ambiguous_day_month_resolved_by_entity_date_order():
    document = make_document()
    certificate = make_certificate(
        document,
        date_texts={
            "candidates": [{"text": "05/06/2024", "role": "issue", "page": 1, "quote": ""}]
        },
    )

    classify_certificate(document, store=FakeStore())

    certificate.refresh_from_db()
    # Cambridge English is seeded with day-first date order.
    assert certificate.issue_date == date(2024, 6, 5)
    assert certificate.detected_date is None
    assert "ambiguous_date" not in certificate.review_reasons
    assert certificate.date_texts["originals"]["issue_date"] == "05/06/2024"


def test_ambiguous_day_month_without_entity_order_stays_detected():
    document = make_document()
    certificate = make_certificate(
        document,
        entity_literal="IELTS",
        date_texts={
            "candidates": [{"text": "05/06/2024", "role": "issue", "page": 1, "quote": ""}]
        },
    )

    classify_certificate(document, store=FakeStore())

    certificate.refresh_from_db()
    assert certificate.issue_date is None
    assert certificate.detected_date == date(2024, 6, 5)
    assert "ambiguous_date" in certificate.review_reasons
    assert certificate.date_texts["originals"]["detected_date"] == "05/06/2024"


def test_labelled_date_candidate_extracts_embedded_date():
    document = make_document()
    certificate = make_certificate(
        document,
        date_texts={
            "candidates": [
                {
                    "text": "Date of Issue: 05/12/2020",
                    "role": "issue",
                    "page": 1,
                    "quote": "",
                }
            ]
        },
    )

    classify_certificate(document, store=FakeStore())

    certificate.refresh_from_db()
    assert certificate.issue_date == date(2020, 12, 5)
    assert certificate.date_texts["originals"]["issue_date"] == "Date of Issue: 05/12/2020"


def test_month_year_candidate_is_not_fabricated():
    document = make_document()
    certificate = make_certificate(
        document,
        date_texts={
            "candidates": [
                {"text": "SEPTEMBER 2020", "role": "exam", "page": 1, "quote": ""}
            ]
        },
    )

    classify_certificate(document, store=FakeStore())

    certificate.refresh_from_db()
    assert certificate.exam_date is None
    assert certificate.issue_date is None
    assert certificate.detected_date is None
    assert "ambiguous_date" in certificate.review_reasons


def test_non_date_candidate_is_ignored():
    document = make_document()
    certificate = make_certificate(
        document,
        date_texts={
            "candidates": [
                {"text": "Firma-4751635", "role": "issue", "page": 1, "quote": ""}
            ]
        },
    )

    classify_certificate(document, store=FakeStore())

    certificate.refresh_from_db()
    assert certificate.issue_date is None
    assert "ambiguous_date" not in certificate.review_reasons


# --- 8.5 review reasons ---


def test_missing_essential_fields_reason():
    document = make_document()
    make_certificate(
        document,
        student_name="",
        level_literal="",
        score_literal="",
        date_texts={"candidates": []},
    )

    classify_certificate(document, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert "missing_essential_fields" in certificate.review_reasons


def test_low_confidence_reason():
    document = make_document()
    make_certificate(document, confidence=0.3)

    classify_certificate(document, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert "low_confidence" in certificate.review_reasons


def test_multiple_certificates_reason():
    document = make_document()
    make_certificate(document, multiple_certificates_suspected=True)

    classify_certificate(document, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert "multiple_certificates" in certificate.review_reasons


def test_non_certificate_reason():
    document = make_document()
    make_certificate(document, is_language_certificate=False)

    classify_certificate(document, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert "non_certificate" in certificate.review_reasons


def test_clean_certificate_has_no_reasons():
    document = make_document()
    make_certificate(document)

    classify_certificate(document, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert certificate.review_reasons == []


# --- 8.6 endpoint idempotency ---


def test_classification_is_idempotent():
    document = make_document()
    certificate = make_certificate(document)

    first = classify_certificate(document, store=FakeStore())
    reasons_after_first = list(Certificate.objects.get(document=document).review_reasons)
    second = classify_certificate(document, store=FakeStore())

    assert first.state == Document.ProcessingState.PENDING_REVIEW
    assert second.skipped is True
    certificate.refresh_from_db()
    assert certificate.language.code == "eng"
    assert certificate.review_reasons == reasons_after_first


def test_internal_classify_endpoint(monkeypatch):
    document = make_document()
    make_certificate(document)

    response = Client().post(
        reverse("internal-document-classify", args=[document.pk]),
        HTTP_X_INTERNAL_TOKEN="test-internal-token",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == Document.ProcessingState.PENDING_REVIEW
    assert payload["cefr_level"] == "B2"
    assert payload["cefr_source"] == "explicit"

    again = Client().post(
        reverse("internal-document-classify", args=[document.pk]),
        HTTP_X_INTERNAL_TOKEN="test-internal-token",
    )
    assert again.json()["skipped"] is True


def test_internal_classify_requires_token_and_valid_state():
    document = make_document(processing_state=Document.ProcessingState.STORED)
    make_certificate(document)

    denied = Client().post(reverse("internal-document-classify", args=[document.pk]))
    assert denied.status_code == 401

    refused = Client().post(
        reverse("internal-document-classify", args=[document.pk]),
        HTTP_X_INTERNAL_TOKEN="test-internal-token",
    )
    assert refused.status_code == 409
