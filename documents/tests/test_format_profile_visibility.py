from datetime import date

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from catalog.models import Entity, FormatProfile
from documents.filters import doubtful_format_q, filter_documents
from documents.models import Certificate, Document, DocumentPage
from documents.services.format_profile import (
    rescore_entity_year,
    score_document_format,
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
        "fingerprint": "g" * 64,
        "original_filename": "certificate.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
        "processing_state": Document.ProcessingState.PENDING_REVIEW,
    }
    data.update(overrides)
    return Document.objects.create(**data)


def make_certificate(document: Document, **overrides) -> Certificate:
    entity = Entity.objects.get(name="Cambridge English")
    data = {
        "document": document,
        "student_name": "Ada Lovelace",
        "language_literal": "English",
        "entity": entity,
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


def add_page(document: Document, text: str) -> None:
    DocumentPage.objects.create(
        document=document, page_number=1, text=text,
        method=DocumentPage.Method.EMBEDDED,
    )


def make_profile(entity: Entity, **overrides) -> FormatProfile:
    data = {
        "entity": entity,
        "year": 2024,
        "anchors": [{"text": "cambridge assessment english", "df": 2}],
        "sample_count": 3,
        "is_active": True,
    }
    data.update(overrides)
    return FormatProfile.objects.create(**data)


# --- doubtful-format filter ---


def test_doubtful_filter_low_score():
    entity = Entity.objects.get(name="Cambridge English")
    make_profile(entity)
    low = make_certificate(make_document(fingerprint="1" * 64), format_score=0.1)
    high = make_certificate(make_document(fingerprint="2" * 64), format_score=0.9)
    none_score = make_certificate(make_document(fingerprint="3" * 64))

    qs = filter_documents({"format": "doubtful"})
    pks = set(qs.values_list("certificate__pk", flat=True))
    assert low.pk in pks
    assert none_score.pk in pks  # NULL score + qualifying active profile
    assert high.pk not in pks


def test_doubtful_filter_ignores_inactive_profile():
    entity = Entity.objects.get(name="Cambridge English")
    make_profile(entity, is_active=False)
    cert = make_certificate(make_document(fingerprint="4" * 64))

    qs = filter_documents({"format": "doubtful"})
    assert cert.pk not in set(qs.values_list("certificate__pk", flat=True))


def test_doubtful_q_annotation_in_list(client):
    viewer = make_user("vf", ("viewer",))
    entity = Entity.objects.get(name="Cambridge English")
    make_profile(entity)
    low = make_certificate(
        make_document(fingerprint="5" * 64), format_score=0.1
    )
    client.force_login(viewer)
    response = client.get(reverse("documents:list"))
    assert response.status_code == 200
    row = next(
        d for d in response.context["page"].object_list
        if d.certificate.pk == low.pk
    )
    assert row.format_doubtful is True


# --- scoring honors is_active ---


def test_inactive_profile_not_scored():
    entity = Entity.objects.get(name="Cambridge English")
    profile = make_profile(entity)
    document = make_document(fingerprint="6" * 64)
    add_page(document, "cambridge assessment english\nthis is to certify\n")
    cert = make_certificate(document, issue_date=date(2024, 1, 1))

    score, cohort = score_document_format(cert)
    assert score is not None and cohort

    profile.is_active = False
    profile.save()
    score2, cohort2 = score_document_format(cert)
    assert score2 is None


def test_rescore_entity_year_updates_scores():
    entity = Entity.objects.get(name="Cambridge English")
    make_profile(entity)
    document = make_document(fingerprint="7" * 64)
    add_page(document, "cambridge assessment english\nthis is to certify\n")
    cert = make_certificate(
        document,
        issue_date=date(2024, 1, 1),
        review_status=Certificate.ReviewStatus.PENDING,
    )
    count = rescore_entity_year(entity.pk, 2024)
    assert count >= 1
    cert.refresh_from_db()
    assert cert.format_score is not None


# --- management view ---


def test_format_profile_list_roles_and_actions(client):
    reviewer = make_user("fprev", ("reviewer",))
    viewer = make_user("fpview", ("viewer",))
    entity = Entity.objects.get(name="Cambridge English")
    profile = make_profile(entity)
    url = reverse("documents:format_profiles")

    client.force_login(viewer)
    assert client.get(url).status_code == 403
    response = client.post(
        url, {"action": "deactivate", "profile_id": profile.pk}
    )
    assert response.status_code == 403

    client.force_login(reviewer)
    assert client.get(url).status_code == 200

    client.post(url, {"action": "deactivate", "profile_id": profile.pk})
    profile.refresh_from_db()
    assert profile.is_active is False
    assert profile.deactivated_by == reviewer
    assert profile.deactivated_at is not None

    client.post(url, {"action": "activate", "profile_id": profile.pk})
    profile.refresh_from_db()
    assert profile.is_active is True
    assert profile.deactivated_by is None

    client.post(url, {"action": "rescore", "profile_id": profile.pk})
