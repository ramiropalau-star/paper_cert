from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client
from django.urls import reverse

from catalog.models import Entity, Equivalence, Exam, Language

pytestmark = pytest.mark.django_db


def make_user(username: str, roles: tuple[str, ...] = ()) -> User:
    user = User.objects.create_user(username, password="password")
    for role in roles:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
    return user


def make_entity_with_exam():
    language = Language.objects.create(code="eng", name="English", name_es="Inglés")
    entity = Entity.objects.create(name="Test Board")
    exam = Exam.objects.create(entity=entity, name="Test Exam", language=language)
    return entity, exam


def test_equivalence_table_lists_entities():
    client = Client()
    client.force_login(make_user("viewer-cat", ("viewer",)))
    make_entity_with_exam()

    response = client.get(reverse("catalog:equivalences"))

    assert response.status_code == 200
    assert b"Test Board" in response.content
    assert b"Test Exam" in response.content


def test_equivalence_table_requires_login():
    response = Client().get(reverse("catalog:equivalences"))
    assert response.status_code == 302


def test_equivalence_update_changes_rule():
    _entity, exam = make_entity_with_exam()
    equivalence = Equivalence.objects.create(
        exam=exam, accredited_level="B2", score_min=Decimal("100"), score_max=Decimal("150")
    )
    client = Client()
    client.force_login(make_user("rev-cat", ("reviewer",)))

    response = client.post(
        reverse("catalog:equivalence_update", args=[equivalence.pk]),
        {
            "accredited_level": "C1",
            "score_min": "100",
            "score_max": "",
            "is_active": "on",
        },
    )

    assert response.status_code == 302
    equivalence.refresh_from_db()
    assert equivalence.accredited_level == "C1"
    assert equivalence.score_max is None
    assert equivalence.is_active is True


def test_equivalence_update_rejects_bad_band():
    _entity, exam = make_entity_with_exam()
    equivalence = Equivalence.objects.create(exam=exam, accredited_level="B2")
    client = Client()
    client.force_login(make_user("rev-cat2", ("reviewer",)))

    client.post(
        reverse("catalog:equivalence_update", args=[equivalence.pk]),
        {"accredited_level": "B2", "score_min": "200", "score_max": "100"},
    )

    equivalence.refresh_from_db()
    assert equivalence.score_min is None


def test_equivalence_update_requires_reviewer():
    _entity, exam = make_entity_with_exam()
    equivalence = Equivalence.objects.create(exam=exam, accredited_level="B2")
    client = Client()
    client.force_login(make_user("view-cat", ("viewer",)))

    response = client.post(
        reverse("catalog:equivalence_update", args=[equivalence.pk]),
        {"accredited_level": "C1"},
    )

    assert response.status_code == 403
    equivalence.refresh_from_db()
    assert equivalence.accredited_level == "B2"


def test_equivalence_add_to_existing_exam():
    _entity, exam = make_entity_with_exam()
    client = Client()
    client.force_login(make_user("rev-cat3", ("reviewer",)))

    response = client.post(
        reverse("catalog:equivalence_add", args=[exam.pk]),
        {"accredited_level": "A2", "score_min": "", "score_max": "", "source": "Manual"},
    )

    assert response.status_code == 302
    assert Equivalence.objects.filter(exam=exam, accredited_level="A2").exists()


def test_entity_create_with_equivalences():
    language = Language.objects.create(code="deu", name="German", name_es="Alemán")
    client = Client()
    client.force_login(make_user("rev-cat4", ("reviewer",)))

    response = client.post(
        reverse("catalog:entity_new"),
        {
            "entity_name": "New Board",
            "entity_aliases": "NewBoard, NB",
            "exam_name": "New Exam",
            "language": str(language.pk),
            "eq_level": ["B1", "", "C1"],
            "eq_min": ["", "", ""],
            "eq_max": ["", "", ""],
        },
    )

    assert response.status_code == 302
    entity = Entity.objects.get(name="New Board")
    exam = Exam.objects.get(entity=entity, name="New Exam")
    assert exam.language == language
    assert entity.aliases.count() == 2
    assert set(
        Equivalence.objects.filter(exam=exam).values_list("accredited_level", flat=True)
    ) == {"B1", "C1"}


def test_entity_create_validates_required_fields():
    client = Client()
    client.force_login(make_user("rev-cat5", ("reviewer",)))

    response = client.post(
        reverse("catalog:entity_new"),
        {"entity_name": "", "exam_name": "", "eq_level": ["B2"]},
    )

    assert response.status_code == 200
    assert not Entity.objects.filter(name="").exists()
