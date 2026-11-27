import json
import re

import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from catalog.models import Entity
from documents.models import Certificate, Document, DocumentPage, FieldLabelAlias
from documents.services.extraction import (
    build_messages,
    extract_certificate,
)
from documents.services.field_aliases import aliases_for_document, teach_alias

pytestmark = pytest.mark.django_db


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
        "paperless_document_id": "77",
        "processing_state": Document.ProcessingState.TEXT_READY,
        "text_method": Document.TextMethod.EMBEDDED,
    }
    data.update(overrides)
    return Document.objects.create(**data)


def add_page(document: Document, text: str) -> None:
    DocumentPage.objects.create(
        document=document,
        page_number=1,
        text=text,
        method=DocumentPage.Method.EMBEDDED,
    )


def field(value, *, page: int = 1, quote: str = "quote"):
    return {"value": value, "evidence": {"page": page, "quote": quote}, "confidence": 0.9}


def payload_dict(**overrides) -> dict:
    data = {
        "is_language_certificate": True,
        "multiple_certificates_suspected": False,
        "student_name": field(None),
        "language": field(None),
        "entity": field(None),
        "issuing_body": field(None),
        "test_center": field(None),
        "exam": field(None),
        "level": field(None),
        "score": field(None),
        "certificate_code": field(None),
        "dates": [],
        "confidence": 0.9,
    }
    data.update(overrides)
    return data


class FakeLlm:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages})
        return self.responses.pop(0)


class FakeStore:
    def label_document(self, *a, **k):
        return True

    def close(self):
        pass


def test_alias_normalization_and_dedup():
    user = make_user("u1")
    created, message = teach_alias(field="student_name", alias="  Test   Taker Name ", actor=user)
    assert created is not None
    assert created.normalized_alias == "test taker name"
    assert created.scope_key == "global"
    created2, message2 = teach_alias(field="student_name", alias="test taker name", actor=user)
    assert created2 is None and "Ya existe" in message2


def test_aliases_for_document_scoped_and_global():
    entity = Entity.objects.create(name="Cambridge", is_active=True)
    other = Entity.objects.create(name="Other", is_active=True)
    user = make_user("u2")
    teach_alias(field="student_name", alias="Global Label", actor=user)
    teach_alias(field="student_name", alias="Scoped Label", actor=user, scope_entity=entity)
    teach_alias(field="student_name", alias="Other Label", actor=user, scope_entity=other)
    FieldLabelAlias.objects.create(
        field="student_name",
        alias="Inactive",
        scope_key="global",
        normalized_alias="inactive",
        is_active=False,
    )

    document = make_document()
    assert aliases_for_document(document) == {"student_name": ["Global Label"]}

    Certificate.objects.create(document=document, entity=entity)
    result = aliases_for_document(document)
    assert result["student_name"] == ["Scoped Label", "Global Label"]


def test_alias_injected_into_prompt():
    teach_alias(field="student_name", alias="Aspirante", actor=make_user("u3"))
    messages = build_messages("doc text", {"student_name": ["Aspirante"]})
    assert "Aspirante" in messages[1]["content"]
    messages_default = build_messages("doc text")
    assert "known labels" not in messages_default[1]["content"]


def test_alias_drives_student_name_fallback():
    document = make_document()
    add_page(document, "CERTIFICATE\nNombre del Aspirante: Laura Pérez García\n")
    FieldLabelAlias.objects.create(
        field="student_name",
        alias="Nombre del Aspirante",
        normalized_alias="nombre del aspirante",
        scope_key="global",
    )
    llm = FakeLlm([json.dumps(payload_dict())])

    extract_certificate(document, llm=llm, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    assert certificate.student_name == "Laura Pérez García"


def test_alias_drives_issue_date_fallback():
    document = make_document()
    add_page(document, "Exámenes EUR\nFecha de expedició: 05/12/2020\n")
    FieldLabelAlias.objects.create(
        field="issue_date",
        alias="Fecha de expedició",
        normalized_alias="fecha de expedicio",
        scope_key="global",
    )
    llm = FakeLlm([json.dumps(payload_dict())])

    extract_certificate(document, llm=llm, store=FakeStore())

    certificate = Certificate.objects.get(document=document)
    texts = [c["text"] for c in certificate.date_texts["candidates"]]
    assert any("05/12/2020" in t for t in texts)


def test_teach_alias_view_roles_and_duplicate(client):
    reviewer = make_user("rev", ("reviewer",))
    viewer = make_user("view", ("viewer",))
    document = make_document(processing_state=Document.ProcessingState.PENDING_REVIEW)
    url = reverse("documents:teach_alias", args=[document.pk])

    client.force_login(viewer)
    response = client.post(url, {"field": "student_name", "alias": "X Y"})
    assert response.status_code == 403

    client.force_login(reviewer)
    response = client.post(url, {"field": "student_name", "alias": "Nombre X"})
    assert response.status_code == 302
    assert FieldLabelAlias.objects.filter(alias="Nombre X").exists()
    response = client.post(url, {"field": "student_name", "alias": "Nombre X"})
    assert not FieldLabelAlias.objects.filter(alias="Nombre X").count() == 2


def test_field_alias_list_requires_reviewer(client):
    viewer = make_user("v2", ("viewer",))
    url = reverse("documents:field_aliases")
    client.force_login(viewer)
    assert client.get(url).status_code == 403
    reviewer = make_user("r2", ("reviewer",))
    client.force_login(reviewer)
    assert client.get(url).status_code == 200


def test_teach_alias_uses_dedicated_form_outside_cert_form(client):
    """Teach-alias controls sit inside #cert-form's table but must belong to
    their own <form> via the form= attribute: a nested <form> is dropped by
    browsers, and an unassociated required input blocks the certificate save."""
    reviewer = make_user("rev-form", ("reviewer",))
    document = make_document(processing_state=Document.ProcessingState.PENDING_REVIEW)
    Certificate.objects.create(
        document=document,
        student_name="Ada Lovelace",
        language_literal="",
    )
    client.force_login(reviewer)

    response = client.get(reverse("documents:detail", args=[document.pk]))

    content = response.content.decode()
    teach_form_id = f"teach-{document.pk}-language"
    teach_url = reverse("documents:teach_alias", args=[document.pk])
    assert f'<form id="{teach_form_id}" method="post" action="{teach_url}"' in content
    assert f'form="{teach_form_id}"' in content
    cert_form = content.split('id="cert-form"', 1)[1].split("</form>", 1)[0]
    assert "<form" not in cert_form
    alias_inputs = re.findall(r"<input[^>]*name=\"alias\"[^>]*>", cert_form)
    assert alias_inputs
    assert all('form="teach-' in tag for tag in alias_inputs)
