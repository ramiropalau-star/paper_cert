"""Tests for catalog-gap resolution: service, resolve view, badges, filter."""

from datetime import date

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from catalog.models import (
    Entity,
    EntityAlias,
    Equivalence,
    Exam,
    ExamAlias,
    Language,
    LanguageAlias,
)
from documents.models import Certificate, Document, ReviewEvent
from documents.services.catalog_resolution import (
    resolve_catalog_field,
    unresolved_catalog_fields,
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
        "fingerprint": "f" * 64,
        "original_filename": "cert.pdf",
        "content_type": "application/pdf",
        "size_bytes": 10,
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
        "entity_literal": "UV",
        "exam_literal": "",
        "level_literal": "B2",
        "score_literal": "180",
        "issue_date": date(2024, 5, 12),
        "is_language_certificate": True,
        "review_status": Certificate.ReviewStatus.PENDING,
    }
    data.update(overrides)
    return Certificate.objects.create(**data)


# --- service ---


def test_resolve_entity_assigns_fk_alias_and_event():
    actor = make_user("rev1", ("reviewer",))
    document = make_document()
    certificate = make_certificate(document)
    entity = Entity.objects.create(name="Universitat de València")

    outcome = resolve_catalog_field(
        certificate, "entity", entity, actor, reclassify=False
    )

    assert outcome.ok
    certificate.refresh_from_db()
    assert certificate.entity == entity
    assert certificate.entity_literal == "UV"
    assert "entity" in certificate.manual_fields
    assert EntityAlias.objects.filter(
        entity=entity, normalized_alias="uv"
    ).exists()
    event = ReviewEvent.objects.get(certificate=certificate)
    assert event.event_type == ReviewEvent.EventType.EDIT
    assert event.before == {"entity": None}
    assert event.after == {"entity": entity.pk}


def test_resolve_is_idempotent_for_aliases():
    actor = make_user("rev2", ("reviewer",))
    certificate = make_certificate(make_document())
    entity = Entity.objects.create(name="Universitat de València")

    resolve_catalog_field(certificate, "entity", entity, actor, reclassify=False)
    resolve_catalog_field(certificate, "entity", entity, actor, reclassify=False)

    assert EntityAlias.objects.filter(normalized_alias="uv").count() == 1


def test_resolve_reports_alias_conflict_without_reassigning():
    actor = make_user("rev3", ("reviewer",))
    certificate = make_certificate(make_document())
    other = Entity.objects.create(name="Other Board")
    EntityAlias.objects.create(entity=other, alias="UV")
    target = Entity.objects.create(name="Universitat de València")

    outcome = resolve_catalog_field(
        certificate, "entity", target, actor, reclassify=False
    )

    assert outcome.ok
    assert outcome.alias_conflict == "UV"
    certificate.refresh_from_db()
    assert certificate.entity == target
    alias = EntityAlias.objects.get(normalized_alias="uv")
    assert alias.entity == other


def test_resolve_exam_scoped_and_language_alias():
    actor = make_user("rev4", ("reviewer",))
    entity = Entity.objects.create(name="UV")
    language = Language.objects.get(code="eng")
    certificate = make_certificate(
        make_document(fingerprint="a" * 64),
        entity=entity,
        entity_literal="UV",
        exam_literal="Certificat de Valencià",
        language_literal="Valencià",
    )
    exam = Exam.objects.create(entity=entity, name="Altres", language=language)
    lang = Language.objects.get(code="val")

    outcome_exam = resolve_catalog_field(
        certificate, "exam", exam, actor, reclassify=False
    )
    assert outcome_exam.ok
    certificate.refresh_from_db()
    assert certificate.exam == exam
    assert ExamAlias.objects.filter(exam=exam).count() == 1

    outcome_lang = resolve_catalog_field(
        certificate, "language", lang, actor, reclassify=False
    )
    assert outcome_lang.ok
    certificate.refresh_from_db()
    assert certificate.language == lang
    assert LanguageAlias.objects.filter(language=lang, normalized_alias="valencià").exists()


def test_unresolved_catalog_fields():
    certificate = make_certificate(
        make_document(fingerprint="b" * 64),
        exam_literal="Some Exam",
        language=Language.objects.get(code="eng"),
    )
    assert unresolved_catalog_fields(certificate) == ["entity", "exam"]


def test_resolve_reclassify_clears_unknown_entity():
    actor = make_user("rev5", ("reviewer",))
    document = make_document()
    certificate = make_certificate(document)
    entity = Entity.objects.create(name="Universitat de València")
    EntityAlias.objects.create(entity=entity, alias="UV")
    certificate.review_reasons = ["unknown_entity"]
    certificate.save(update_fields=["review_reasons"])

    outcome = resolve_catalog_field(certificate, "entity", entity, actor)

    assert outcome.ok
    assert outcome.reclassified
    certificate.refresh_from_db()
    document.refresh_from_db()
    assert certificate.entity == entity
    assert "unknown_entity" not in certificate.review_reasons
    assert document.processing_state == Document.ProcessingState.PENDING_REVIEW


# --- resolve view ---


def _resolve_url(document, field):
    return reverse("catalog:resolve") + f"?document={document.pk}&field={field}"


def test_resolve_page_lists_candidates_for_reviewer():
    client = Client()
    client.force_login(make_user("rev-view", ("reviewer",)))
    document = make_document()
    make_certificate(document)

    response = client.get(_resolve_url(document, "entity"))

    assert response.status_code == 200
    assert b"UV" in response.content
    # seeded entities appear as candidates
    assert b"ETS" in response.content


def test_resolve_page_viewer_read_only():
    client = Client()
    client.force_login(make_user("view-only", ("viewer",)))
    document = make_document()
    make_certificate(document)

    response = client.get(_resolve_url(document, "entity"))

    assert response.status_code == 200
    assert b'name="choice"' not in response.content


def test_resolve_post_existing_entity():
    client = Client()
    user = make_user("rev-post", ("reviewer",))
    client.force_login(user)
    document = make_document()
    certificate = make_certificate(document)
    entity = Entity.objects.create(name="Universitat de València")

    response = client.post(
        reverse("catalog:resolve"),
        {
            "document": str(document.pk),
            "field": "entity",
            "choice": f"existing:{entity.pk}",
            "reclasificar": "on",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("documents:detail", args=[document.pk])
    certificate.refresh_from_db()
    assert certificate.entity == entity


def test_resolve_post_create_new_entity():
    client = Client()
    client.force_login(make_user("rev-new", ("reviewer",)))
    document = make_document()
    certificate = make_certificate(document, entity_literal="Universitat de València")

    response = client.post(
        reverse("catalog:resolve"),
        {
            "document": str(document.pk),
            "field": "entity",
            "choice": "new",
            "name": "Universitat de València",
            "reclasificar": "on",
        },
    )

    assert response.status_code == 302
    entity = Entity.objects.get(name="Universitat de València")
    certificate.refresh_from_db()
    assert certificate.entity == entity


def test_resolve_post_exam_requires_entity():
    client = Client()
    client.force_login(make_user("rev-exam", ("reviewer",)))
    document = make_document()
    certificate = make_certificate(document, exam_literal="Certificat UV")

    response = client.post(
        reverse("catalog:resolve"),
        {
            "document": str(document.pk),
            "field": "exam",
            "choice": "new",
            "name": "Certificat UV",
        },
    )

    assert response.status_code == 302
    assert not Exam.objects.filter(name="Certificat UV").exists()
    certificate.refresh_from_db()
    assert certificate.exam is None


def test_resolve_post_exam_creates_scoped_exam():
    client = Client()
    client.force_login(make_user("rev-exam2", ("reviewer",)))
    entity = Entity.objects.create(name="UV")
    language = Language.objects.get(code="val")
    document = make_document()
    certificate = make_certificate(
        document,
        entity=entity,
        exam_literal="Certificat de Valencià",
        language=language,
    )

    response = client.post(
        reverse("catalog:resolve"),
        {
            "document": str(document.pk),
            "field": "exam",
            "choice": "new",
            "name": "Certificat de Valencià",
            "reclasificar": "on",
        },
    )

    assert response.status_code == 302
    exam = Exam.objects.get(entity=entity, name="Certificat de Valencià")
    assert exam.language == language
    certificate.refresh_from_db()
    assert certificate.exam == exam


def test_resolve_post_language_existing():
    client = Client()
    client.force_login(make_user("rev-lang", ("reviewer",)))
    document = make_document()
    certificate = make_certificate(
        document, language_literal="Valencià", language=None
    )
    lang = Language.objects.get(code="val")

    response = client.post(
        reverse("catalog:resolve"),
        {
            "document": str(document.pk),
            "field": "language",
            "choice": f"existing:{lang.pk}",
            "reclasificar": "on",
        },
    )

    assert response.status_code == 302
    certificate.refresh_from_db()
    assert certificate.language == lang
    assert LanguageAlias.objects.filter(
        language=lang, normalized_alias="valencià"
    ).exists()


def test_resolve_post_viewer_forbidden():
    client = Client()
    client.force_login(make_user("view-post", ("viewer",)))
    document = make_document()
    make_certificate(document)
    entity = Entity.objects.create(name="UV")

    response = client.post(
        reverse("catalog:resolve"),
        {
            "document": str(document.pk),
            "field": "entity",
            "choice": f"existing:{entity.pk}",
        },
    )

    assert response.status_code == 403


# --- badges and filter ---


def test_list_shows_catalog_badge_only_when_unresolved():
    client = Client()
    client.force_login(make_user("view-list", ("viewer",)))
    unresolved_doc = make_document(fingerprint="c" * 64, original_filename="unresolved.pdf")
    make_certificate(unresolved_doc, entity=None, entity_literal="UV")
    resolved_doc = make_document(fingerprint="d" * 64, original_filename="resolved.pdf")
    entity = Entity.objects.create(name="UV")
    make_certificate(
        resolved_doc,
        entity=entity,
        entity_literal="UV",
        exam_literal="",
        language=None,
        language_literal="",
    )

    response = client.get(reverse("documents:list"))

    assert response.status_code == 200
    content = response.content.decode()
    unresolved_row = content.split("unresolved.pdf")[1].split("</tr>")[0]
    resolved_row = content.split("resolved.pdf")[1].split("</tr>")[0]
    assert "Catálogo pendiente" in unresolved_row
    assert "Catálogo pendiente" not in resolved_row


def test_gallery_shows_catalog_badge():
    client = Client()
    client.force_login(make_user("view-gallery", ("viewer",)))
    document = make_document(fingerprint="e" * 64)
    make_certificate(document, entity=None)

    response = client.get(reverse("documents:gallery"))

    assert response.status_code == 200
    assert "Catálogo".encode() in response.content


def test_detail_shows_badge_and_resolver_link():
    client = Client()
    client.force_login(make_user("rev-detail", ("reviewer",)))
    document = make_document()
    make_certificate(document, entity=None)

    response = client.get(reverse("documents:detail", args=[document.pk]))

    assert response.status_code == 200
    assert "Catálogo pendiente".encode() in response.content
    assert b"field=entity" in response.content


def test_detail_viewer_sees_badge_without_resolver_link():
    client = Client()
    client.force_login(make_user("view-detail", ("viewer",)))
    document = make_document()
    make_certificate(document, entity=None)

    response = client.get(reverse("documents:detail", args=[document.pk]))

    assert response.status_code == 200
    assert "Catálogo pendiente".encode() in response.content
    assert b"field=entity" not in response.content


def test_catalog_pending_filter():
    client = Client()
    client.force_login(make_user("view-filter", ("viewer",)))
    unresolved_doc = make_document(fingerprint="1" * 64, original_filename="pending.pdf")
    make_certificate(unresolved_doc, entity=None)
    resolved_doc = make_document(fingerprint="2" * 64, original_filename="done.pdf")
    entity = Entity.objects.create(name="UV")
    language = Language.objects.get(code="eng")
    exam = Exam.objects.create(entity=entity, name="Exam")
    make_certificate(
        resolved_doc,
        entity=entity,
        exam=exam,
        language=language,
        entity_literal="UV",
        exam_literal="Exam",
        language_literal="English",
    )

    response = client.get(reverse("documents:list") + "?catalog=pending")

    assert response.status_code == 200
    content = response.content.decode()
    assert "pending.pdf" in content
    assert "done.pdf" not in content


# --- auto-refresh status endpoint ---


def test_document_status_endpoint():
    client = Client()
    client.force_login(make_user("view-status", ("viewer",)))
    document = make_document(fingerprint="9" * 64, processing_state="text_ready")
    make_certificate(document)

    response = client.get(reverse("documents:status", args=[document.pk]))

    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "text_ready"
    assert data["has_certificate"] is True


def test_detail_embeds_initial_state_for_poll_guard():
    client = Client()
    client.force_login(make_user("view-poll", ("reviewer",)))
    processing = make_document(fingerprint="8" * 64, processing_state="stored")
    settled = make_document(
        fingerprint="7" * 64, processing_state="pending_review"
    )

    response = client.get(reverse("documents:detail", args=[processing.pk]))
    assert 'initialState = "stored"'.encode() in response.content
    assert b"/status/" in response.content

    response = client.get(reverse("documents:detail", args=[settled.pk]))
    assert 'initialState = "pending_review"'.encode() in response.content
