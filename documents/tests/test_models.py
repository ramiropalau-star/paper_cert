import pytest
from django.db import IntegrityError, transaction

from documents.models import Certificate, Document, DocumentPage, ReviewEvent

pytestmark = pytest.mark.django_db


def make_document(**overrides) -> Document:
    data = {
        "fingerprint": "a" * 64,
        "original_filename": "certificate.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
    }
    data.update(overrides)
    return Document.objects.create(**data)


def test_document_defaults_and_fingerprint_uniqueness():
    document = make_document()

    assert document.processing_state == Document.ProcessingState.RECEIVED
    assert document.text_method == ""
    assert document.paperless_document_id == ""
    assert document.page_count is None

    with pytest.raises(IntegrityError), transaction.atomic():
        make_document(original_filename="duplicate.pdf")


def test_certificate_defaults_and_one_per_document():
    document = make_document()
    certificate = Certificate.objects.create(document=document)

    assert certificate.review_status == Certificate.ReviewStatus.PENDING
    assert certificate.cefr_level == ""
    assert certificate.review_reasons == []
    assert certificate.evidence == {}
    assert certificate.is_language_certificate is None

    with pytest.raises(IntegrityError), transaction.atomic():
        Certificate.objects.create(document=document)


def test_document_page_number_is_unique_per_document():
    document = make_document()
    DocumentPage.objects.create(
        document=document,
        page_number=1,
        text="Page one",
        method=DocumentPage.Method.EMBEDDED,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        DocumentPage.objects.create(
            document=document,
            page_number=1,
            text="Duplicate",
            method=DocumentPage.Method.OCR,
        )


def test_document_npa_parsed_from_filename():
    document = make_document(original_filename="2027ERASMUSWF29402_I.Certificado_Idioma_E.pdf")
    assert document.npa == "WF29402"

    assert make_document(fingerprint="b" * 64, original_filename="certificate.pdf").npa == ""
    assert (
        make_document(
            fingerprint="c" * 64,
            original_filename="2024-05-12 certificate.pdf",
        ).npa
        == ""
    )


def test_review_event_stores_payload_and_is_chronological():
    certificate = Certificate.objects.create(document=make_document())
    first = ReviewEvent.objects.create(
        certificate=certificate,
        event_type=ReviewEvent.EventType.EDIT,
        before={"student_name": ""},
        after={"student_name": "Ana"},
    )
    second = ReviewEvent.objects.create(
        certificate=certificate,
        event_type=ReviewEvent.EventType.APPROVE,
    )

    assert list(certificate.events.all()) == [first, second]
    assert first.before == {"student_name": ""}
    assert second.after == {}
