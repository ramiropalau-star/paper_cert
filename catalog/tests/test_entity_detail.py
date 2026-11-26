"""Tests for the catalog entity detail page and its write handlers."""

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client
from django.urls import reverse

from catalog.models import Entity, EntityAlias, Equivalence, Exam, Language

pytestmark = pytest.mark.django_db


def make_user(username: str, roles: tuple[str, ...] = ()) -> User:
    user = User.objects.create_user(username, password="password")
    for role in roles:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
    return user


def make_entity() -> Entity:
    return Entity.objects.create(name="Test Board")


def detail_url(entity: Entity) -> str:
    return reverse("catalog:entity_detail", args=[entity.pk])


def test_entity_detail_viewer_read_only():
    client = Client()
    client.force_login(make_user("view-ent", ("viewer",)))
    entity = make_entity()
    EntityAlias.objects.create(entity=entity, alias="TB")
    exam = Exam.objects.create(entity=entity, name="Exam One")
    Equivalence.objects.create(exam=exam, accredited_level="B2")

    response = client.get(detail_url(entity))

    assert response.status_code == 200
    assert b"Test Board" in response.content
    assert b"TB" in response.content
    assert b"Exam One" in response.content
    # no write controls for viewers
    assert b'name="alias"' not in response.content
    assert b'name="date_order"' not in response.content
    assert "Añadir equivalencia".encode() not in response.content


def test_entity_detail_reviewer_sees_write_controls():
    client = Client()
    client.force_login(make_user("rev-ent", ("reviewer",)))
    entity = make_entity()

    response = client.get(detail_url(entity))

    assert response.status_code == 200
    assert b'name="alias"' in response.content
    assert b'name="date_order"' in response.content
    assert b"Crear examen" in response.content


def test_entity_update_metadata():
    client = Client()
    client.force_login(make_user("rev-upd", ("reviewer",)))
    entity = make_entity()

    response = client.post(
        reverse("catalog:entity_update", args=[entity.pk]),
        {"date_order": "dmy", "is_active": "on", "next": detail_url(entity)},
    )

    assert response.status_code == 302
    assert response.url == detail_url(entity)
    entity.refresh_from_db()
    assert entity.date_order == "dmy"
    assert entity.is_active is True


def test_entity_update_rejects_bad_date_order():
    client = Client()
    client.force_login(make_user("rev-upd2", ("reviewer",)))
    entity = make_entity()

    client.post(
        reverse("catalog:entity_update", args=[entity.pk]),
        {"date_order": "xyz", "is_active": "on"},
    )

    entity.refresh_from_db()
    assert entity.date_order == ""


def test_entity_alias_add_and_duplicate():
    client = Client()
    client.force_login(make_user("rev-alias", ("reviewer",)))
    entity = make_entity()
    other = Entity.objects.create(name="Other")
    EntityAlias.objects.create(entity=other, alias="Shared")

    response = client.post(
        reverse("catalog:alias_add", args=[entity.pk]),
        {"alias": "TestBoard", "next": detail_url(entity)},
    )
    assert response.status_code == 302
    assert EntityAlias.objects.filter(entity=entity, alias="TestBoard").exists()

    # duplicate for same entity: no new row
    client.post(
        reverse("catalog:alias_add", args=[entity.pk]),
        {"alias": "TestBoard"},
    )
    assert EntityAlias.objects.filter(normalized_alias="testboard").count() == 1

    # alias owned by another entity: preserved, error shown
    response = client.post(
        reverse("catalog:alias_add", args=[entity.pk]),
        {"alias": "Shared"},
        follow=True,
    )
    assert EntityAlias.objects.get(normalized_alias="shared").entity == other
    assert "ya está asignado".encode() in response.content


def test_exam_create_under_entity():
    client = Client()
    client.force_login(make_user("rev-exam", ("reviewer",)))
    entity = make_entity()
    language = Language.objects.create(code="eng", name="English")

    response = client.post(
        reverse("catalog:exam_create", args=[entity.pk]),
        {"name": "New Exam", "language": str(language.pk)},
    )

    assert response.status_code == 302
    exam = Exam.objects.get(entity=entity, name="New Exam")
    assert exam.language == language


def test_exam_create_duplicate_is_idempotent():
    client = Client()
    client.force_login(make_user("rev-exam2", ("reviewer",)))
    entity = make_entity()
    Exam.objects.create(entity=entity, name="New Exam")

    client.post(
        reverse("catalog:exam_create", args=[entity.pk]),
        {"name": "New Exam"},
    )

    assert Exam.objects.filter(entity=entity, name="New Exam").count() == 1


def test_entity_writes_require_reviewer():
    client = Client()
    client.force_login(make_user("view-wr", ("viewer",)))
    entity = make_entity()

    assert (
        client.post(
            reverse("catalog:entity_update", args=[entity.pk]),
            {"date_order": "mdy"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            reverse("catalog:alias_add", args=[entity.pk]), {"alias": "X"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            reverse("catalog:exam_create", args=[entity.pk]), {"name": "X"}
        ).status_code
        == 403
    )


def test_equivalence_add_honors_next():
    client = Client()
    client.force_login(make_user("rev-eq", ("reviewer",)))
    entity = make_entity()
    exam = Exam.objects.create(entity=entity, name="Exam")
    entity_url = detail_url(entity)

    response = client.post(
        reverse("catalog:equivalence_add", args=[exam.pk]),
        {
            "accredited_level": "B2",
            "next": entity_url,
        },
    )

    assert response.status_code == 302
    assert response.url == entity_url
    assert Equivalence.objects.filter(exam=exam, accredited_level="B2").exists()


def test_equivalence_add_rejects_external_next():
    client = Client()
    client.force_login(make_user("rev-eq2", ("reviewer",)))
    entity = make_entity()
    exam = Exam.objects.create(entity=entity, name="Exam")

    response = client.post(
        reverse("catalog:equivalence_add", args=[exam.pk]),
        {
            "accredited_level": "B2",
            "next": "https://evil.example.com/",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("catalog:equivalences")


def test_equivalence_update_honors_next():
    client = Client()
    client.force_login(make_user("rev-eq3", ("reviewer",)))
    entity = make_entity()
    exam = Exam.objects.create(entity=entity, name="Exam")
    equivalence = Equivalence.objects.create(exam=exam, accredited_level="B2")
    entity_url = detail_url(entity)

    response = client.post(
        reverse("catalog:equivalence_update", args=[equivalence.pk]),
        {
            "accredited_level": "C1",
            "is_active": "on",
            "next": entity_url,
        },
    )

    assert response.status_code == 302
    assert response.url == entity_url
    equivalence.refresh_from_db()
    assert equivalence.accredited_level == "C1"
