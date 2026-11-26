from datetime import date
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from documents.models import Certificate, Document, ReviewEvent
from documents.services.classification import classify_certificate
from documents.services.review import validate_certificate

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
        "fingerprint": "f" * 64,
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
        "issue_date": date(2024, 5, 12),
        "is_language_certificate": True,
        "confidence": 0.9,
    }
    data.update(overrides)
    return Certificate.objects.create(**data)


class FakeStore:
    def __init__(self):
        self.tags = []

    def add_tag(self, document_id, name):
        self.tags.append((document_id, name))
        return True

    def remove_tag(self, document_id, name):
        return True


# --- equivalence resolution ---


def test_equivalence_resolves_for_level_named_exam():
    document = make_document()
    make_certificate(document)

    classify_certificate(document, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert certificate.exam.name == "B2 First"
    assert certificate.equivalence == "B2"
    assert "equivalence_not_found" not in certificate.review_reasons


def test_equivalence_uses_score_band_for_ielts():
    document = make_document()
    make_certificate(
        document,
        entity_literal="IELTS",
        exam_literal="IELTS Academic",
        level_literal="",
        score_literal="6.0",
    )

    classify_certificate(document, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert certificate.equivalence == "B2"


def test_equivalence_out_of_band_leaves_empty_and_reviews():
    document = make_document()
    make_certificate(
        document,
        entity_literal="IELTS",
        exam_literal="IELTS Academic",
        level_literal="",
        score_literal="9.5",
    )

    classify_certificate(document, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert certificate.equivalence == ""
    assert "equivalence_not_found" in certificate.review_reasons


def test_exam_without_equivalence_routes_to_review():
    document = make_document()
    make_certificate(
        document,
        entity_literal="TOEIC",
        exam_literal="TOEIC Listening and Reading",
        level_literal="B2",
        score_literal="900",
    )

    classify_certificate(document, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert certificate.exam.name == "TOEIC Listening and Reading"
    assert certificate.equivalence == ""
    assert "equivalence_not_found" in certificate.review_reasons


def test_manual_equivalence_edit_is_audited():
    document = make_document()
    certificate = make_certificate(document, equivalence="")
    reviewer = make_user("reviewer", ("reviewer",))

    from documents.forms import CertificateEditForm

    form = CertificateEditForm(
        data={
            "student_name": "Ada Lovelace",
            "equivalence": "C1",
            "language": "",
            "entity": "",
            "exam": "",
        }
    )
    assert form.is_valid(), form.errors
    from documents.services.review import apply_manual_edit

    outcome = apply_manual_edit(certificate, form.to_certificate_values(), reviewer)

    assert outcome.ok
    certificate.refresh_from_db()
    assert certificate.equivalence == "C1"
    event = certificate.events.get(event_type=ReviewEvent.EventType.EDIT)
    assert event.after["equivalence"] == "C1"


# --- validated status ---


def test_validate_marks_certificate_validated():
    document = make_document(processing_state=Document.ProcessingState.PENDING_REVIEW)
    certificate = make_certificate(document)
    reviewer = make_user("reviewer", ("reviewer",))

    outcome = validate_certificate(certificate, reviewer)

    assert outcome.ok
    certificate.refresh_from_db()
    assert certificate.review_status == Certificate.ReviewStatus.VALIDATED
    assert document.processing_state == Document.ProcessingState.PENDING_REVIEW
    assert certificate.events.filter(event_type=ReviewEvent.EventType.VALIDATE).exists()


def test_validate_rejects_approved_and_rejected():
    reviewer = make_user("reviewer", ("reviewer",))
    approved = make_certificate(
        make_document(fingerprint="a" * 64),
        review_status=Certificate.ReviewStatus.APPROVED,
    )
    rejected = make_certificate(
        make_document(fingerprint="b" * 64),
        review_status=Certificate.ReviewStatus.REJECTED,
    )

    assert not validate_certificate(approved, reviewer).ok
    assert not validate_certificate(rejected, reviewer).ok


def test_validate_view_requires_reviewer():
    viewer = make_user("viewer", ("viewer",))
    client = Client()
    client.force_login(viewer)
    document = make_document()
    make_certificate(document)

    response = client.post(reverse("documents:validate", args=[document.pk]))

    assert response.status_code == 403
    assert Certificate.objects.get(document=document).review_status == (
        Certificate.ReviewStatus.PENDING
    )


def test_validate_view_sets_status():
    reviewer = make_user("reviewer2", ("reviewer",))
    client = Client()
    client.force_login(reviewer)
    document = make_document()
    make_certificate(document)

    response = client.post(reverse("documents:validate", args=[document.pk]))

    assert response.status_code == 302
    assert Certificate.objects.get(document=document).review_status == (
        Certificate.ReviewStatus.VALIDATED
    )


# --- in-app document viewer ---


def test_document_original_streams_from_paperless():
    viewer = make_user("viewer2", ("viewer",))
    client = Client()
    client.force_login(viewer)
    document = make_document()

    pdf_bytes = b"%PDF-1.4 fake"
    with patch("documents.views.build_document_store") as build_store:
        store = build_store.return_value
        store.download_original.return_value = pdf_bytes
        response = client.get(reverse("documents:original", args=[document.pk]))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content == pdf_bytes
    store.download_original.assert_called_once_with("42")


def test_document_original_404_without_paperless_id():
    viewer = make_user("viewer3", ("viewer",))
    client = Client()
    client.force_login(viewer)
    document = make_document(paperless_document_id="")

    response = client.get(reverse("documents:original", args=[document.pk]))

    assert response.status_code == 404


def test_document_thumbnail_streams_from_paperless():
    viewer = make_user("viewer4", ("viewer",))
    client = Client()
    client.force_login(viewer)
    document = make_document()

    webp_bytes = b"RIFF\x00\x00\x00\x00WEBP"
    with patch("documents.views.build_document_store") as build_store:
        store = build_store.return_value
        store.download_thumbnail.return_value = webp_bytes
        response = client.get(reverse("documents:thumbnail", args=[document.pk]))

    assert response.status_code == 200
    assert response.content == webp_bytes
    store.download_thumbnail.assert_called_once_with("42")


def test_document_thumbnail_serves_cache_hit_without_paperless():
    from django.core.cache import cache

    cache.clear()
    viewer = make_user("viewer-thumb", ("viewer",))
    client = Client()
    client.force_login(viewer)
    document = make_document(fingerprint="a1" * 32)

    webp_bytes = b"RIFF\x00\x00\x00\x00WEBP"
    with patch("documents.views.build_document_store") as build_store:
        store = build_store.return_value
        store.download_thumbnail.return_value = webp_bytes
        first = client.get(reverse("documents:thumbnail", args=[document.pk]))
        second = client.get(reverse("documents:thumbnail", args=[document.pk]))

    assert first.status_code == second.status_code == 200
    assert second.content == webp_bytes
    store.download_thumbnail.assert_called_once_with("42")


def test_document_thumbnail_refetches_on_version_change():
    from datetime import timedelta

    from django.core.cache import cache
    from django.utils import timezone

    cache.clear()
    viewer = make_user("viewer-thumb2", ("viewer",))
    client = Client()
    client.force_login(viewer)
    document = make_document(fingerprint="a2" * 32)

    with patch("documents.views.build_document_store") as build_store:
        store = build_store.return_value
        store.download_thumbnail.return_value = b"RIFF\x00\x00\x00\x00WEBP"
        client.get(reverse("documents:thumbnail", args=[document.pk]))
        Document.objects.filter(pk=document.pk).update(
            updated_at=timezone.now() + timedelta(days=1)
        )
        client.get(reverse("documents:thumbnail", args=[document.pk]))

    assert store.download_thumbnail.call_count == 2


def test_document_thumbnail_returns_placeholder_on_paperless_failure():
    from django.core.cache import cache

    from documents.services.paperless import PaperlessError

    cache.clear()
    viewer = make_user("viewer-thumb3", ("viewer",))
    client = Client()
    client.force_login(viewer)
    document = make_document(fingerprint="a3" * 32)

    with patch("documents.views.build_document_store") as build_store:
        store = build_store.return_value
        store.download_thumbnail.side_effect = PaperlessError("down")
        response = client.get(reverse("documents:thumbnail", args=[document.pk]))

    assert response.status_code == 200
    assert response["Content-Type"] == "image/svg+xml"
    assert b"<svg" in response.content


def test_document_original_requires_login(client):
    document = make_document()
    response = client.get(reverse("documents:original", args=[document.pk]))
    assert response.status_code == 302


# --- report includes equivalence and validated ---


def test_workbook_shows_equivalence_and_validated_status():
    import io

    from openpyxl import load_workbook

    from reports.services import build_workbook

    reviewer = make_user("reviewer3", ("reviewer",))
    validated_doc = make_document(fingerprint="d" * 64)
    validated_cert = make_certificate(validated_doc, equivalence="C1")
    validate_certificate(validated_cert, reviewer)

    content = build_workbook([], [validated_cert])
    workbook = load_workbook(io.BytesIO(content))
    rows = list(workbook["Pendientes de revisión"].iter_rows(values_only=True))

    header = list(rows[0])
    assert "Equivalencia UV L2" in header
    data = list(rows[1])
    assert data[header.index("Equivalencia UV L2")] == "C1"
    assert data[header.index("Estado")] == "Validado"


class TagStore(FakeStore):
    def __init__(self, existing=()):
        super().__init__()
        self.tag_names = set(existing)

    def document_tag_names(self, document_id):
        return list(self.tag_names)

    def set_tags(self, document_id, names):
        self.tag_names = set(names)
        return True

    def add_tag(self, document_id, name):
        self.tag_names.add(name)
        return True

    def remove_tag(self, document_id, name):
        self.tag_names.discard(name)
        return True


def test_classification_syncs_paperless_tags():
    document = make_document()
    make_certificate(document)
    store = TagStore()

    classify_certificate(document, store=store)

    assert "Idioma: English" in store.tag_names
    assert "Nivel: B2" in store.tag_names
    assert "Entidad: Cambridge English" in store.tag_names
    assert "Examen: B2 First" in store.tag_names
    assert "Equivalencia UV L2: B2" in store.tag_names


def test_tag_sync_reconciles_stale_tags():
    document = make_document()
    make_certificate(document)
    store = TagStore(existing={"Entidad: Old Entity", "Otro tag"})

    classify_certificate(document, store=store)

    assert "Entidad: Old Entity" not in store.tag_names
    assert "Entidad: Cambridge English" in store.tag_names
    assert "Otro tag" in store.tag_names


def test_manual_language_survives_reprocess_and_classify():
    from catalog.models import Language
    from documents.forms import CertificateEditForm
    from documents.services.review import apply_manual_edit

    document = make_document()
    certificate = make_certificate(
        document,
        language_literal="Klingon",
        entity_literal="Unknown Board",
        exam_literal="",
        level_literal="",
        score_literal="",
    )
    reviewer = make_user("rev-manual", ("reviewer",))
    french = Language.objects.get(code="fra")
    form = CertificateEditForm(
        data={
            "student_name": "Ada Lovelace",
            "language_literal": "Français",
            "language": str(french.pk),
        }
    )
    assert form.is_valid(), form.errors
    assert apply_manual_edit(certificate, form.to_certificate_values(), reviewer).ok

    # Simulate re-extraction overwriting literals, then re-classification.
    certificate.refresh_from_db()
    assert certificate.language.code == "fra"
    assert "language" in certificate.manual_fields
    assert "language_literal" in certificate.manual_fields

    # Re-classify: manual FK and literal must be preserved.
    certificate.language_literal = "Klingon"  # stale value pre-edit scenario guard
    certificate.save(update_fields=["language_literal"])
    document.processing_state = Document.ProcessingState.EXTRACTED
    document.save(update_fields=["processing_state"])
    # restore corrected literal as extraction-preservation would
    certificate.language_literal = "Français"
    certificate.save(update_fields=["language_literal"])

    classify_certificate(document, store=FakeStore())
    certificate.refresh_from_db()
    assert certificate.language.code == "fra"
    assert certificate.language_literal == "Français"


def test_release_manual_field_unfreezes_field():
    from documents.services.review import release_manual_field

    document = make_document()
    certificate = make_certificate(document, manual_fields=["language_literal", "score_literal"])
    reviewer = make_user("rev-rel", ("reviewer",))

    outcome = release_manual_field(certificate, reviewer, "language_literal")

    assert outcome.ok
    certificate.refresh_from_db()
    assert certificate.manual_fields == ["score_literal"]
    assert certificate.events.filter(
        event_type=ReviewEvent.EventType.EDIT, reason="Liberación de campo protegido"
    ).exists()


def test_release_manual_field_rejects_unknown_field():
    from documents.services.review import release_manual_field

    document = make_document()
    certificate = make_certificate(document, manual_fields=["language_literal"])
    reviewer = make_user("rev-rel2", ("reviewer",))

    assert not release_manual_field(certificate, reviewer, "bogus").ok
    assert not release_manual_field(certificate, reviewer, "confidence").ok


def test_release_field_view():
    reviewer = make_user("rev-rel3", ("reviewer",))
    client = Client()
    client.force_login(reviewer)
    document = make_document()
    make_certificate(document, manual_fields=["level_literal"])

    response = client.post(
        reverse("documents:release_field", args=[document.pk]),
        {"field": "level_literal"},
    )

    assert response.status_code == 302
    assert Certificate.objects.get(document=document).manual_fields == []
