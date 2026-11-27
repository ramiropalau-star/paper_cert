import json

import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from catalog.models import Entity, Exam
from documents.models import FieldLabelAlias
from documents.services.extraction import extract_certificate
from documents.services.field_aliases import (
    aliases_for_document,
    aliases_for_pre_detection,
    propose_alias_candidate,
    set_alias_lifecycle,
    teach_alias,
)
from documents.services.review import apply_manual_edit
from documents.tests.factories import (
    add_page,
    make_certificate,
    make_document,
    make_field_alias,
)

pytestmark = pytest.mark.django_db


def make_user(username: str, roles: tuple[str, ...] = ()) -> User:
    user = User.objects.create_user(username, password="password")
    for role in roles:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
    return user


class FakeLlm:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, *, format=None, temperature=0.0):
        self.calls.append({"messages": messages})
        return self.responses.pop(0)

    def close(self):
        pass


# --- 6.1 lifecycle ---


def test_manual_alias_is_active_and_authoritative():
    reviewer = make_user("rev1", ("reviewer",))
    alias, message = teach_alias(field="student_name", alias="Test Taker Name", actor=reviewer)
    assert alias is not None
    assert alias.lifecycle == FieldLabelAlias.Lifecycle.ACTIVE
    assert alias.source == FieldLabelAlias.Source.MANUAL
    assert alias.is_active is True


def test_candidate_alias_not_used_by_extraction():
    entity = Entity.objects.create(name="Cambridge English")
    document = make_document()
    make_certificate(document=document, entity=entity)
    FieldLabelAlias.objects.create(
        field=FieldLabelAlias.Field.STUDENT_NAME,
        alias="Candidate Label",
        scope_entity=entity,
        source=FieldLabelAlias.Source.LEARNED,
        lifecycle=FieldLabelAlias.Lifecycle.CANDIDATE,
        is_active=False,
    )

    alias_map = aliases_for_document(document)

    assert "Candidate Label" not in alias_map.get("student_name", [])


def test_lifecycle_transitions_record_actor():
    reviewer = make_user("rev2", ("reviewer",))
    alias, _ = teach_alias(field="exam", alias="Prova Final", actor=reviewer)
    ok, _ = set_alias_lifecycle(alias, "rejected", reviewer)
    assert ok
    alias.refresh_from_db()
    assert alias.lifecycle == "rejected"
    assert alias.is_active is False
    assert alias.provenance["last_transition"]["actor"] == "rev2"


# --- 6.2 corroboration and conflict ---


def _observe(field="student_name", alias="Obtained By", entity=None, cert_id=None):
    return propose_alias_candidate(
        field=field,
        alias=alias,
        scope_entity=entity,
        provenance={"certificate_id": cert_id, "source": "test"} if cert_id else {},
    )


def test_single_observation_stays_candidate():
    alias, outcome = _observe(cert_id=1)
    assert outcome == "created"
    assert alias.lifecycle == "candidate"
    assert alias.support_count == 1
    assert alias.is_active is False


def test_corroborated_alias_activates():
    entity = Entity.objects.create(name="Cambridge English")
    _observe(entity=entity, cert_id=1)
    alias, outcome = _observe(entity=entity, cert_id=2)
    assert outcome == "corroborated"
    assert alias.lifecycle == "active"
    assert alias.is_active is True
    assert alias.support_count == 2
    assert alias.confidence > 0


def test_same_certificate_does_not_corroborate():
    _observe(cert_id=1)
    _alias, outcome = _observe(cert_id=1)
    assert outcome == "exists"


def test_conflict_stays_candidate():
    entity = Entity.objects.create(name="Cambridge English")
    # Active alias for a DIFFERENT field claims the same printed label.
    FieldLabelAlias.objects.create(
        field=FieldLabelAlias.Field.EXAM,
        alias="Result",
        scope_entity=entity,
        lifecycle=FieldLabelAlias.Lifecycle.ACTIVE,
        is_active=True,
    )
    _observe(field="score", alias="Result", entity=entity, cert_id=1)
    alias, outcome = _observe(field="score", alias="Result", entity=entity, cert_id=2)
    assert outcome == "conflict"
    assert alias.lifecycle == "candidate"
    assert alias.is_active is False
    assert alias.provenance.get("conflict") is True


def test_rejected_alias_never_relearned():
    reviewer = make_user("rev3", ("reviewer",))
    alias, _ = _observe(alias="Never Use", cert_id=1)
    set_alias_lifecycle(alias, "rejected", reviewer)
    _alias, outcome = _observe(alias="Never Use", cert_id=2)
    assert outcome == "rejected"


# --- 6.3 reviewer-correction proposals ---


def test_correction_proposes_scoped_candidate():
    entity = Entity.objects.create(name="Cambridge English")
    document = make_document()
    add_page(document, text="Student Name: Ada Lovelace\nCambridge English B2 First")
    certificate = make_certificate(document=document, entity=entity, student_name="Wrong Name")
    reviewer = make_user("rev4", ("reviewer",))

    outcome = apply_manual_edit(certificate, {"student_name": "Ada Lovelace"}, reviewer)

    assert outcome.ok
    assert outcome.notes
    proposal = FieldLabelAlias.objects.get(field="student_name", alias="Student Name")
    assert proposal.scope_entity_id == entity.pk
    assert proposal.lifecycle == "candidate"
    assert proposal.provenance["observations"][0]["source"] == "review_correction"


def test_proposal_dismissal_via_reject():
    reviewer = make_user("rev5", ("reviewer",))
    alias, _ = _observe(alias="Dismiss Me", cert_id=1)
    ok, _ = set_alias_lifecycle(alias, "rejected", reviewer)
    assert ok
    alias.refresh_from_db()
    assert alias.lifecycle == "rejected"
    assert alias.is_active is False


# --- 6.4 pre-detection scoped aliases ---


def test_pre_detection_scoped_aliases():
    entity = Entity.objects.create(name="Cambridge English")
    make_field_alias(
        field=FieldLabelAlias.Field.STUDENT_NAME,
        alias="Scoped Label",
        scope_entity=entity,
    )
    make_field_alias(
        field=FieldLabelAlias.Field.EXAM,
        alias="Global Label",
    )

    matched = aliases_for_pre_detection({"result": "match", "entity_id": entity.pk})
    assert "Scoped Label" in matched["student_name"]
    assert "Global Label" in matched["exam"]

    ambiguous = aliases_for_pre_detection({"result": "ambiguous"})
    assert "Scoped Label" not in ambiguous.get("student_name", [])
    assert "Global Label" in ambiguous["exam"]

    none_result = aliases_for_pre_detection({"result": "none"})
    assert "Scoped Label" not in none_result.get("student_name", [])


def test_extract_uses_pre_detection_scoped_alias():
    entity = Entity.objects.create(name="Cambridge English")
    Exam.objects.create(entity=entity, name="B2 First")
    make_field_alias(
        field=FieldLabelAlias.Field.STUDENT_NAME,
        alias="Test Taker",
        scope_entity=entity,
    )
    document = make_document()
    add_page(
        document,
        text=("Cambridge English B2 First\nTest Taker: Ada Lovelace\nissued 12 May 2024\n"),
    )
    payload = {
        "is_language_certificate": True,
        "multiple_certificates_suspected": False,
        "student_name": {
            "value": "Ada Lovelace",
            "evidence": {"page": 1, "quote": "Test Taker: Ada Lovelace"},
            "confidence": 0.9,
        },
        "language": {"value": "English", "evidence": None, "confidence": 0.9},
        "entity": {"value": "Cambridge English", "evidence": None, "confidence": 0.9},
        "issuing_body": {"value": None, "evidence": None, "confidence": None},
        "test_center": {"value": None, "evidence": None, "confidence": None},
        "exam": {"value": "B2 First", "evidence": None, "confidence": 0.9},
        "level": {"value": "B2", "evidence": None, "confidence": 0.9},
        "score": {"value": "180", "evidence": None, "confidence": 0.9},
        "certificate_code": {"value": None, "evidence": None, "confidence": None},
        "dates": [
            {
                "text": "12 May 2024",
                "role": "issue",
                "page": 1,
                "quote": "issued 12 May 2024",
            }
        ],
        "confidence": 0.9,
    }
    llm = FakeLlm([json.dumps(payload)])

    extract_certificate(document, llm=llm)

    sent = llm.calls[0]["messages"][1]["content"]
    assert "Test Taker" in sent


# --- 6.5 listing surface and permissions ---


def test_alias_list_shows_lifecycle_and_actions(client):
    reviewer = make_user("rev6", ("reviewer",))
    _observe(alias="Shown Candidate", cert_id=1)
    client.force_login(reviewer)

    response = client.get(reverse("documents:field_aliases"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Shown Candidate" in content
    assert "Candidato" in content
    assert "Soporte" in content
    assert "Confianza" in content


def test_alias_reject_action(client):
    reviewer = make_user("rev7", ("reviewer",))
    viewer = make_user("view7", ("viewer",))
    alias, _ = _observe(alias="Reject Via UI", cert_id=1)
    url = reverse("documents:field_aliases")

    client.force_login(viewer)
    assert client.post(url, {"action": "reject", "alias_id": alias.pk}).status_code == 403

    client.force_login(reviewer)
    response = client.post(url, {"action": "reject", "alias_id": alias.pk})
    assert response.status_code == 302
    alias.refresh_from_db()
    assert alias.lifecycle == "rejected"
    assert alias.is_active is False
