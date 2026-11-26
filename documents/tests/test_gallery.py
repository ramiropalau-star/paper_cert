from datetime import date

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from catalog.models import Entity, Equivalence, Exam, Language
from documents.models import Certificate, Document

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


def make_document(index: int = 0, **overrides) -> Document:
    data = {
        "fingerprint": f"{index:064d}",
        "original_filename": f"cert-{index}.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
        "paperless_document_id": str(100 + index),
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


def _classified(document: Document) -> Certificate:
    certificate = make_certificate(document)
    certificate.language = Language.objects.get(code="eng")
    certificate.entity = Entity.objects.get(name="Cambridge English")
    certificate.equivalence = "B2"
    certificate.save()
    return certificate


# --- gallery ---


def test_gallery_requires_login(client):
    assert client.get(reverse("documents:gallery")).status_code == 302


def test_gallery_renders_certificate_cards():
    viewer = make_user("viewer", ("viewer",))
    client = Client()
    client.force_login(viewer)
    document = make_document(1, content_type="image/png")
    _classified(document)
    make_document(2)  # no certificate -> excluded

    response = client.get(reverse("documents:gallery"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Ada Lovelace" in content
    assert "Cambridge English" in content
    assert "Equiv. UV:" in content
    assert ">B2</a>" in content or ">B2<" in content
    assert 'name="documents"' in content
    assert f'value="{document.pk}"' in content
    assert content.count("gallery-card") == 1


def test_gallery_uses_thumbnail_endpoint_for_cards():
    viewer = make_user("viewer", ("viewer",))
    client = Client()
    client.force_login(viewer)
    document = make_document(1, content_type="image/png")
    make_certificate(document)

    response = client.get(reverse("documents:gallery"))

    content = response.content.decode()
    assert f"/documents/{document.pk}/thumbnail/" in content
    assert "<img" in content


def test_gallery_links_equivalence_to_catalog_rule():
    viewer = make_user("viewer", ("viewer",))
    client = Client()
    client.force_login(viewer)
    entity = Entity.objects.get(name="Cambridge English")
    exam = Exam.objects.create(entity=entity, name="B2 First Link Test")
    rule = Equivalence.objects.create(exam=exam, accredited_level="B2")
    document = make_document(1)
    make_certificate(document, exam=exam, equivalence="B2")

    response = client.get(reverse("documents:gallery"))

    content = response.content.decode()
    assert f"#eq-{rule.pk}" in content
    assert "catalog" in content or "/catalog/" in content or "equivalences" in content


def test_gallery_zoom_button_present_for_documents_with_original():
    viewer = make_user("viewer", ("viewer",))
    client = Client()
    client.force_login(viewer)
    document = make_document(1, content_type="image/png")
    make_certificate(document)

    response = client.get(reverse("documents:gallery"))

    content = response.content.decode()
    assert 'class="zoom-btn"' in content
    assert "zoom-tip" in content


def test_gallery_filters_by_language_entity_organism():
    viewer = make_user("viewer", ("viewer",))
    client = Client()
    client.force_login(viewer)
    eng = Language.objects.get(code="eng")
    spa = Language.objects.get(code="spa")
    cambridge = Entity.objects.get(name="Cambridge English")
    ielts = Entity.objects.get(name="IELTS")

    d1 = make_document(1)
    make_certificate(
        d1,
        student_name="Ada",
        language=eng,
        entity=cambridge,
        issuing_body_literal="University of Cambridge",
    )
    d2 = make_document(2)
    make_certificate(
        d2,
        student_name="Grace",
        language=spa,
        entity=ielts,
        issuing_body_literal="British Council",
    )

    response = client.get(
        reverse("documents:gallery"),
        {"language": str(eng.pk), "entity": str(cambridge.pk), "organism": "Cambridge"},
    )
    assert [d.original_filename for d in response.context["page"].object_list] == ["cert-1.pdf"]

    response = client.get(reverse("documents:gallery"), {"organism": "Council"})
    assert [d.original_filename for d in response.context["page"].object_list] == ["cert-2.pdf"]


# --- bulk review ---


def test_bulk_validate_marks_certificates_validated():
    reviewer = make_user("reviewer", ("reviewer",))
    client = Client()
    client.force_login(reviewer)
    d1 = make_document(1)
    d2 = make_document(2)
    c1 = make_certificate(d1)
    c2 = make_certificate(d2)

    response = client.post(
        reverse("documents:bulk_review"),
        {"action": "validate", "documents": [str(d1.pk), str(d2.pk)]},
    )

    assert response.status_code == 302
    c1.refresh_from_db()
    c2.refresh_from_db()
    assert c1.review_status == Certificate.ReviewStatus.VALIDATED
    assert c2.review_status == Certificate.ReviewStatus.VALIDATED


def test_bulk_approve_sets_states():
    reviewer = make_user("reviewer", ("reviewer",))
    client = Client()
    client.force_login(reviewer)
    d1 = make_document(1)
    d2 = make_document(2)
    c1 = _classified(d1)
    c2 = _classified(d2)

    response = client.post(
        reverse("documents:bulk_review"),
        {"action": "approve", "documents": [str(d1.pk), str(d2.pk)]},
    )

    assert response.status_code == 302
    for certificate, document in ((c1, d1), (c2, d2)):
        certificate.refresh_from_db()
        document.refresh_from_db()
        assert certificate.review_status == Certificate.ReviewStatus.APPROVED
        assert document.processing_state == Document.ProcessingState.APPROVED


def test_bulk_approve_reports_failures():
    reviewer = make_user("reviewer", ("reviewer",))
    client = Client()
    client.force_login(reviewer)
    ok_doc = make_document(1)
    _classified(ok_doc)
    missing_doc = make_document(2)
    make_certificate(missing_doc, issue_date=None)  # missing required field

    response = client.post(
        reverse("documents:bulk_review"),
        {
            "action": "approve",
            "documents": [str(ok_doc.pk), str(missing_doc.pk)],
        },
        follow=True,
    )

    content = response.content.decode()
    assert "1 documento(s) aprobados" in content
    assert "1 no se pudieron procesar" in content


def test_bulk_review_requires_reviewer_and_selection(client):
    viewer = make_user("viewer", ("viewer",))
    client.force_login(viewer)
    document = make_document(1)
    make_certificate(document)

    response = client.post(
        reverse("documents:bulk_review"),
        {"action": "validate", "documents": [str(document.pk)]},
    )
    assert response.status_code == 403

    reviewer = make_user("reviewer", ("reviewer",))
    client.force_login(reviewer)
    response = client.post(reverse("documents:bulk_review"), {"action": "validate"})
    assert response.status_code == 302


def test_bulk_review_preserves_filters_on_redirect():
    reviewer = make_user("reviewer", ("reviewer",))
    client = Client()
    client.force_login(reviewer)
    document = make_document(1)
    make_certificate(document)
    eng = Language.objects.get(code="eng")

    response = client.post(
        reverse("documents:bulk_review"),
        {
            "action": "validate",
            "documents": [str(document.pk)],
            "language": str(eng.pk),
            "organism": "Cambridge",
        },
    )

    assert response.status_code == 302
    assert "language=" in response.url
    assert "organism=Cambridge" in response.url


# --- detail navigation and inline edit ---


def _set_created_at(document: Document, value: str) -> None:
    Document.objects.filter(pk=document.pk).update(created_at=value)


def test_detail_prev_next_within_pending_queue():
    viewer = make_user("viewer", ("viewer",))
    client = Client()
    client.force_login(viewer)
    d1 = make_document(1)
    d2 = make_document(2)
    d3 = make_document(3)
    _set_created_at(d1, "2024-01-01T10:00:00+00:00")
    _set_created_at(d2, "2024-01-02T10:00:00+00:00")
    _set_created_at(d3, "2024-01-03T10:00:00+00:00")
    for d in (d1, d2, d3):
        make_certificate(d)

    response = client.get(reverse("documents:detail", args=[d2.pk]))

    assert response.context["previous_document"].pk == d3.pk
    assert response.context["next_document"].pk == d1.pk
    content = response.content.decode()
    assert "Siguiente" in content and "Anterior" in content


def test_detail_edit_mode_renders_form_fields():
    reviewer = make_user("reviewer", ("reviewer",))
    client = Client()
    client.force_login(reviewer)
    document = make_document(1)
    make_certificate(document)

    response = client.get(reverse("documents:detail", args=[document.pk]) + "?edit=1")

    assert response.status_code == 200
    content = response.content.decode()
    assert "is-editing" in content
    assert 'name="student_name"' in content
    assert 'name="language"' in content
    assert "Guardar cambios" in content


def test_detail_edit_mode_hidden_for_viewer():
    viewer = make_user("viewer", ("viewer",))
    client = Client()
    client.force_login(viewer)
    document = make_document(1)
    make_certificate(document)

    response = client.get(reverse("documents:detail", args=[document.pk]) + "?edit=1")

    assert "is-editing" not in response.content.decode()
