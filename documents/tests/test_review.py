from datetime import date

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from catalog.models import Entity, Language
from documents.models import Certificate, Document, DocumentPage, ReviewEvent
from documents.services.review import (
    approve_certificate,
    reject_certificate,
    reprocess_document,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def catalog(db):
    call_command("seed_catalog", verbosity=0)


def make_user(username: str, roles: tuple[str, ...] = ()) -> User:
    user = User.objects.create_user(username, password="password")
    for role in roles:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
    return user


def make_document(**overrides) -> Document:
    data = {
        "fingerprint": "e" * 64,
        "original_filename": "certificate.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
        "paperless_document_id": "42",
        "processing_state": Document.ProcessingState.PENDING_REVIEW,
        "text_method": Document.TextMethod.EMBEDDED,
        "page_count": 1,
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


def add_page(document: Document, text: str = "page") -> None:
    DocumentPage.objects.create(
        document=document,
        page_number=1,
        text=text,
        method=DocumentPage.Method.EMBEDDED,
    )


# --- 9.1 document list ---


def test_document_list_requires_login(client):
    assert client.get(reverse("documents:list")).status_code == 302


def test_document_list_renders_all_states():
    viewer = make_user("viewer", ("viewer",))
    client = Client()
    client.force_login(viewer)
    for index, state in enumerate(
        [
            Document.ProcessingState.PENDING_REVIEW,
            Document.ProcessingState.APPROVED,
            Document.ProcessingState.REJECTED,
            Document.ProcessingState.ERROR,
            Document.ProcessingState.TEXT_READY,
        ]
    ):
        make_document(
            fingerprint=f"{index}" * 64,
            original_filename=f"doc-{state}.pdf",
            processing_state=state,
        )

    response = client.get(reverse("documents:list"))

    assert response.status_code == 200
    content = response.content.decode()
    for state in ["Pendiente", "Aprobado", "Rechazado", "Error"]:
        assert state in content


def test_document_list_filters_by_state():
    viewer = make_user("viewer", ("viewer",))
    client = Client()
    client.force_login(viewer)
    make_document(
        fingerprint="1" * 64,
        original_filename="pending.pdf",
        processing_state=Document.ProcessingState.PENDING_REVIEW,
    )
    make_document(
        fingerprint="2" * 64,
        original_filename="approved.pdf",
        processing_state=Document.ProcessingState.APPROVED,
    )
    make_document(
        fingerprint="3" * 64,
        original_filename="error.pdf",
        processing_state=Document.ProcessingState.ERROR,
    )

    response = client.get(reverse("documents:list"), {"state": "error"})

    content = response.content.decode()
    assert "error.pdf" in content
    assert "pending.pdf" not in content
    assert "approved.pdf" not in content


def test_document_list_paginates():
    viewer = make_user("viewer", ("viewer",))
    client = Client()
    client.force_login(viewer)
    for index in range(30):
        make_document(fingerprint=f"{index:064d}", original_filename=f"doc-{index}.pdf")

    first = client.get(reverse("documents:list"))
    second = client.get(reverse("documents:list"), {"page": 2})

    assert len(first.context["page"]) == 25
    assert len(second.context["page"]) == 5


# --- 9.2 review detail ---


def test_review_detail_shows_document_fields_and_warnings():
    viewer = make_user("viewer", ("viewer",))
    client = Client()
    client.force_login(viewer)
    document = make_document()
    make_certificate(
        document,
        entity=None,
        entity_literal="Unknown U",
        review_reasons=["unknown_entity", "low_confidence"],
        confidence=0.3,
        evidence={"student_name": {"page": 1, "quote": "Ada Lovelace"}},
    )
    add_page(document, "certificate text")

    response = client.get(reverse("documents:detail", args=[document.pk]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "certificate.pdf" in content
    assert "Texto embebido" in content
    assert "Ada Lovelace" in content
    assert "Entidad pendiente de identificar" in content
    assert "Confianza baja" in content
    assert "Ver original en Paperless" in content
    assert "certificate text" not in content  # page text not dumped


def test_review_detail_without_certificate():
    viewer = make_user("viewer", ("viewer",))
    client = Client()
    client.force_login(viewer)
    document = make_document(
        processing_state=Document.ProcessingState.ERROR, error_reason="OCR failed"
    )

    response = client.get(reverse("documents:detail", args=[document.pk]))

    assert response.status_code == 200
    assert "no tiene datos extraídos" in response.content.decode()


# --- 9.3 manual edit + audit ---


def test_manual_edit_updates_values_and_records_event():
    reviewer = make_user("reviewer", ("reviewer",))
    client = Client()
    client.force_login(reviewer)
    document = make_document()
    certificate = make_certificate(document)

    response = client.post(
        reverse("documents:edit", args=[document.pk]),
        {
            "student_name": "Ada Byron",
            "language_literal": "English",
            "entity_literal": "Cambridge English",
            "exam_literal": "B2 First",
            "level_literal": "B2",
            "score_literal": "180",
            "issue_date": "2024-05-12",
            "cefr_level": "B2",
        },
    )

    assert response.status_code == 302
    certificate.refresh_from_db()
    assert certificate.student_name == "Ada Byron"
    event = ReviewEvent.objects.get(certificate=certificate)
    assert event.event_type == ReviewEvent.EventType.EDIT
    assert event.actor == reviewer
    assert event.before["student_name"] == "Ada Lovelace"
    assert event.after["student_name"] == "Ada Byron"


def test_manual_edit_rejects_invalid_dates():
    reviewer = make_user("reviewer", ("reviewer",))
    client = Client()
    client.force_login(reviewer)
    document = make_document()
    certificate = make_certificate(document)

    response = client.post(
        reverse("documents:edit", args=[document.pk]),
        {"issue_date": "not-a-date"},
    )

    assert response.status_code == 302
    certificate.refresh_from_db()
    assert certificate.issue_date == date(2024, 5, 12)
    assert ReviewEvent.objects.count() == 0


def test_viewer_cannot_edit(client):
    viewer = make_user("viewer", ("viewer",))
    client.force_login(viewer)
    document = make_document()
    make_certificate(document)

    response = client.post(
        reverse("documents:edit", args=[document.pk]),
        {"student_name": "Mallory"},
    )

    assert response.status_code == 403
    assert Certificate.objects.get(document=document).student_name == "Ada Lovelace"


# --- 9.4 approve / reject ---


def _classified_certificate(document: Document) -> Certificate:
    certificate = make_certificate(document)
    certificate.language = Language.objects.get(code="eng")
    certificate.entity = Entity.objects.get(name="Cambridge English")
    certificate.save()
    return certificate


def test_approve_sets_states_and_records_event():
    reviewer = make_user("reviewer", ("reviewer",))
    client = Client()
    client.force_login(reviewer)
    document = make_document()
    certificate = _classified_certificate(document)

    response = client.post(reverse("documents:approve", args=[document.pk]))

    assert response.status_code == 302
    certificate.refresh_from_db()
    document.refresh_from_db()
    assert certificate.review_status == Certificate.ReviewStatus.APPROVED
    assert document.processing_state == Document.ProcessingState.APPROVED
    assert ReviewEvent.objects.filter(
        certificate=certificate, event_type=ReviewEvent.EventType.APPROVE
    ).exists()


def test_approve_blocked_when_required_fields_missing():
    reviewer = make_user("reviewer", ("reviewer",))
    client = Client()
    client.force_login(reviewer)
    document = make_document()
    certificate = make_certificate(document, issue_date=None)

    response = client.post(reverse("documents:approve", args=[document.pk]), follow=True)

    certificate.refresh_from_db()
    assert certificate.review_status == Certificate.ReviewStatus.PENDING
    assert "fecha de expedición" in response.content.decode()


def test_viewer_cannot_approve(client):
    viewer = make_user("viewer", ("viewer",))
    client.force_login(viewer)
    document = make_document()
    _classified_certificate(document)

    response = client.post(reverse("documents:approve", args=[document.pk]))

    assert response.status_code == 403


def test_reject_requires_reason():
    reviewer = make_user("reviewer", ("reviewer",))
    outcome = reject_certificate(make_certificate(make_document()), reviewer, "  ")
    assert outcome.ok is False


def test_reject_sets_status_and_records_reason():
    reviewer = make_user("reviewer", ("reviewer",))
    document = make_document()
    certificate = _classified_certificate(document)

    outcome = reject_certificate(certificate, reviewer, "Documento ilegible")

    assert outcome.ok is True
    certificate.refresh_from_db()
    document.refresh_from_db()
    assert certificate.review_status == Certificate.ReviewStatus.REJECTED
    assert document.processing_state == Document.ProcessingState.REJECTED
    event = ReviewEvent.objects.get(certificate=certificate)
    assert event.reason == "Documento ilegible"


def test_approve_removes_manual_review_label():
    reviewer = make_user("reviewer", ("reviewer",))
    document = make_document()
    certificate = _classified_certificate(document)

    class FakeStore:
        def __init__(self):
            self.removed = []
            self.closed = False

        def remove_tag(self, document_id, name):
            self.removed.append((document_id, name))
            return True

        def close(self):
            self.closed = True

    store = FakeStore()
    outcome = approve_certificate(certificate, reviewer, store=store)

    assert outcome.ok is True
    assert store.removed == [("42", "Otros")]


# --- 9.5 reprocess ---


def test_reprocess_resets_state_and_preserves_history(monkeypatch):
    reviewer = make_user("reviewer", ("reviewer",))
    document = make_document(
        processing_state=Document.ProcessingState.APPROVED,
        error_reason="old error",
    )
    certificate = _classified_certificate(document)
    certificate.review_status = Certificate.ReviewStatus.APPROVED
    certificate.save()
    ReviewEvent.objects.create(
        certificate=certificate,
        event_type=ReviewEvent.EventType.EDIT,
        actor=reviewer,
        before={"student_name": "Old"},
        after={"student_name": "New"},
    )
    calls = []
    monkeypatch.setattr(
        "documents.services.review.notify_processing",
        lambda doc: calls.append(doc.pk),
    )

    outcome = reprocess_document(document, reviewer)

    assert outcome.ok is True
    document.refresh_from_db()
    certificate.refresh_from_db()
    assert document.processing_state == Document.ProcessingState.STORED
    assert document.error_reason == ""
    assert certificate.review_status == Certificate.ReviewStatus.PENDING
    assert Document.objects.filter(pk=document.pk).count() == 1
    assert Certificate.objects.filter(document=document).count() == 1
    assert ReviewEvent.objects.filter(certificate=certificate).count() == 2
    events = list(ReviewEvent.objects.filter(certificate=certificate))
    assert events[0].event_type == ReviewEvent.EventType.EDIT
    assert events[1].event_type == ReviewEvent.EventType.REPROCESS
    assert calls == [document.pk]


def test_reprocess_view_requires_reviewer(client):
    viewer = make_user("viewer", ("viewer",))
    client.force_login(viewer)
    document = make_document()
    make_certificate(document)

    response = client.post(reverse("documents:reprocess", args=[document.pk]))

    assert response.status_code == 403


# --- 9.6 search and filters ---


def _seed_review_documents():
    english = Entity.objects.get(name="Cambridge English")
    ielts = Entity.objects.get(name="IELTS")
    eng = Language.objects.get(code="eng")
    spa = Language.objects.get(code="spa")
    documents = []
    specs = [
        ("ada.pdf", "Ada Lovelace", eng, english, "B2", date(2024, 1, 10)),
        ("grace.pdf", "Grace Hopper", eng, ielts, "C1", date(2024, 2, 20)),
        (
            "sofia.pdf",
            "Sofía Paz",
            spa,
            Entity.objects.get(name="Instituto Cervantes"),
            "B1",
            date(2024, 3, 5),
        ),
    ]
    for index, (filename, student, language, entity, level, issue) in enumerate(specs):
        document = make_document(
            fingerprint=f"{index + 10}" * 64,
            original_filename=filename,
        )
        make_certificate(
            document,
            student_name=student,
            language_literal=language.name,
            language=language,
            entity_literal=entity.name,
            entity=entity,
            level_literal=level,
            issue_date=issue,
        )
        documents.append(document)
    return documents


def test_search_by_student_name():
    viewer = make_user("viewer", ("viewer",))
    client = Client()
    client.force_login(viewer)
    _seed_review_documents()

    response = client.get(reverse("documents:list"), {"q": "grace"})

    content = response.context["page"].object_list
    assert [d.original_filename for d in content] == ["grace.pdf"]


def test_combined_filters_language_entity_level_issue_date():
    viewer = make_user("viewer", ("viewer",))
    client = Client()
    client.force_login(viewer)
    _seed_review_documents()
    english = Language.objects.get(code="eng")
    cambridge = Entity.objects.get(name="Cambridge English")

    response = client.get(
        reverse("documents:list"),
        {
            "language": str(english.pk),
            "entity": str(cambridge.pk),
            "level": "B2",
            "issue_date": "2024-01-10",
        },
    )

    assert [d.original_filename for d in response.context["page"].object_list] == ["ada.pdf"]


# --- 9.7 history ---


def test_history_renders_events_chronologically():
    viewer = make_user("viewer", ("viewer",))
    client = Client()
    client.force_login(viewer)
    document = make_document()
    certificate = make_certificate(document)
    reviewer = make_user("reviewer", ("reviewer",))
    ReviewEvent.objects.create(
        certificate=certificate,
        event_type=ReviewEvent.EventType.EDIT,
        actor=reviewer,
        before={"student_name": "A"},
        after={"student_name": "B"},
    )
    ReviewEvent.objects.create(
        certificate=certificate,
        event_type=ReviewEvent.EventType.APPROVE,
        actor=reviewer,
    )

    response = client.get(reverse("documents:history", args=[document.pk]))

    assert response.status_code == 200
    events = list(response.context["events"])
    assert [e.event_type for e in events] == [
        ReviewEvent.EventType.EDIT,
        ReviewEvent.EventType.APPROVE,
    ]
    content = response.content.decode()
    assert "Edición" in content
    assert "Aprobación" in content
    assert "reviewer" in content
