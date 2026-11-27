"""VerifierConfig CRUD, config-driven verification, and source comparison."""

import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from catalog.models import Entity
from documents.models import VerifierConfig
from documents.services.verifiers import verify_at_source
from documents.tests.factories import make_certificate, make_verifier_config

pytestmark = pytest.mark.django_db


def make_user(username: str, roles: tuple[str, ...] = ()) -> User:
    user = User.objects.create_user(username, password="password")
    for role in roles:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
    return user


def _fake_httpx_client(response):
    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return response

    return _Client


# --- 8.2 CRUD and permissions ---


def test_verifier_config_list_requires_reviewer(client):
    viewer = make_user("vv", ("viewer",))
    reviewer = make_user("vr", ("reviewer",))
    url = reverse("documents:verifier_configs")

    client.force_login(viewer)
    assert client.get(url).status_code == 403
    assert client.post(url, {"action": "create", "host": "x.org"}).status_code == 403

    client.force_login(reviewer)
    assert client.get(url).status_code == 200


def test_create_verifier_config(client):
    reviewer = make_user("vc", ("reviewer",))
    client.force_login(reviewer)
    response = client.post(
        reverse("documents:verifier_configs"),
        {
            "action": "create",
            "host": "verify.newissuer.org",
            "url_template": "https://verify.newissuer.org/check?c={code}",
            "timeout_seconds": "5",
            "success_criteria": '{"markers": ["ok"]}',
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    config = VerifierConfig.objects.get(host="verify.newissuer.org")
    assert config.success_criteria == {"markers": ["ok"]}
    assert config.created_by == reviewer


def test_invalid_verifier_config_rejected(client):
    reviewer = make_user("vb", ("reviewer",))
    client.force_login(reviewer)
    url = reverse("documents:verifier_configs")

    # Invalid URL template (not http(s)).
    response = client.post(
        url,
        {
            "action": "create",
            "host": "bad.example.org",
            "url_template": "ftp://bad.example.org/{code}",
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    assert not VerifierConfig.objects.filter(host="bad.example.org").exists()

    # Invalid regex code pattern.
    response = client.post(
        url,
        {
            "action": "create",
            "host": "bad2.example.org",
            "url_template": "https://bad2.example.org/{code}",
            "code_pattern": "([unclosed",
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    assert not VerifierConfig.objects.filter(host="bad2.example.org").exists()

    # Out-of-range timeout.
    response = client.post(
        url,
        {
            "action": "create",
            "host": "bad3.example.org",
            "url_template": "https://bad3.example.org/{code}",
            "timeout_seconds": "999",
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    assert not VerifierConfig.objects.filter(host="bad3.example.org").exists()


# --- 8.3 config-driven verification ---


def test_config_verifier_used_for_known_host(monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html"}
        content = b"resultado verificado correctamente"
        text = "resultado verificado correctamente"

    monkeypatch.setattr(
        "documents.services.verifiers.httpx.Client",
        _fake_httpx_client(FakeResponse()),
    )
    make_verifier_config(
        host="verify.example.org",
        url_template="https://verify.example.org/check?c={code}",
        success_criteria={"markers": ["verificado"]},
    )
    certificate = make_certificate(
        verification_url="https://verify.example.org/check?c=ABC123",
        verification_code="ABC123",
        verification_status="self_reported",
    )
    verify_at_source(certificate)
    certificate.refresh_from_db()
    assert certificate.verification_status == "verified_at_source"
    auto = certificate.verification_evidence["auto_check"]
    assert auto["evidence"]["config_id"] is not None


def test_config_verifier_entity_scoping(monkeypatch):
    entity = Entity.objects.create(name="Scoped Entity")
    other = Entity.objects.create(name="Other Entity")
    seen_urls = []

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html"}
        content = b"ok-marker"
        text = "ok-marker"

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            seen_urls.append(url)
            return FakeResponse()

    monkeypatch.setattr("documents.services.verifiers.httpx.Client", _Client)
    make_verifier_config(
        entity=entity,
        host="scoped.example.org",
        url_template="https://scoped.example.org/e1?c={code}",
        success_criteria={"markers": ["ok-marker"]},
    )
    make_verifier_config(
        host="scoped.example.org",
        url_template="https://scoped.example.org/global?c={code}",
        success_criteria={"markers": ["ok-marker"]},
    )
    cert = make_certificate(
        entity=entity,
        verification_url="https://scoped.example.org/",
        verification_code="C1",
        verification_status="self_reported",
    )
    verify_at_source(cert)
    assert seen_urls == ["https://scoped.example.org/e1?c=C1"]

    seen_urls.clear()
    cert2 = make_certificate(
        entity=other,
        verification_url="https://scoped.example.org/",
        verification_code="C2",
        verification_status="self_reported",
    )
    verify_at_source(cert2)
    assert seen_urls == ["https://scoped.example.org/global?c=C2"]


# --- 8.4 source-document comparison ---


def _pdf_response(text=""):
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/pdf"}
        content = b"%PDF-1.7 fake"
        _text = text

    return FakeResponse()


def test_source_comparison_match(monkeypatch):
    monkeypatch.setattr(
        "documents.services.verifiers._pdf_text",
        lambda content, max_pages=5: "Student Name: Ada Lovelace\nScore: 180",
    )
    monkeypatch.setattr(
        "documents.services.verifiers.httpx.Client",
        _fake_httpx_client(_pdf_response()),
    )
    make_verifier_config(
        host="src.example.org",
        url_template="https://src.example.org/doc?c={code}",
        success_criteria={"require_pdf": True},
        source_document_parser="pdf_text",
        source_field_patterns={
            "student_name": r"Student Name:\s*(.+)",
            "score": r"Score:\s*(\d+)",
        },
    )
    certificate = make_certificate(
        student_name="Ada Lovelace",
        score_literal="180",
        verification_url="https://src.example.org/doc",
        verification_code="C9",
        verification_status="self_reported",
    )
    verify_at_source(certificate)
    certificate.refresh_from_db()
    assert certificate.verification_status == "verified_at_source"
    assert certificate.source_comparison["status"] == "match"
    assert certificate.source_comparison["fields"]["student_name"]["match"] is True
    assert "source_mismatch" not in (certificate.review_reasons or [])


def test_source_comparison_mismatch_routes_to_review(monkeypatch):
    monkeypatch.setattr(
        "documents.services.verifiers._pdf_text",
        lambda content, max_pages=5: "Student Name: Someone Else\nScore: 90",
    )
    monkeypatch.setattr(
        "documents.services.verifiers.httpx.Client",
        _fake_httpx_client(_pdf_response()),
    )
    make_verifier_config(
        host="src2.example.org",
        url_template="https://src2.example.org/doc?c={code}",
        success_criteria={"require_pdf": True},
        source_document_parser="pdf_text",
        source_field_patterns={
            "student_name": r"Student Name:\s*(.+)",
            "score": r"Score:\s*(\d+)",
        },
    )
    certificate = make_certificate(
        student_name="Ada Lovelace",
        score_literal="180",
        verification_url="https://src2.example.org/doc",
        verification_code="C9",
        verification_status="self_reported",
    )
    verify_at_source(certificate)
    certificate.refresh_from_db()
    # Verification itself still succeeds; comparison records the mismatch.
    assert certificate.verification_status == "verified_at_source"
    assert certificate.source_comparison["status"] == "mismatch"
    assert "source_mismatch" in (certificate.review_reasons or [])


def test_source_comparison_unavailable_without_document(monkeypatch):
    class HtmlResponse:
        status_code = 200
        headers = {"content-type": "text/html"}
        content = b"<html>ok verified</html>"
        text = "ok verified"

    monkeypatch.setattr(
        "documents.services.verifiers.httpx.Client",
        _fake_httpx_client(HtmlResponse()),
    )
    make_verifier_config(
        host="src3.example.org",
        url_template="https://src3.example.org/check?c={code}",
        success_criteria={"markers": ["verified"]},
        source_document_parser="pdf_text",
        source_field_patterns={"student_name": r"Name:\s*(.+)"},
    )
    certificate = make_certificate(
        verification_url="https://src3.example.org/check",
        verification_code="C1",
        verification_status="self_reported",
    )
    verify_at_source(certificate)
    certificate.refresh_from_db()
    assert certificate.verification_status == "verified_at_source"
    assert certificate.source_comparison["status"] == "unavailable"


# --- 8.5 verified samples and learning eligibility ---


def test_verified_alias_observation_gets_confidence_bonus():
    from documents.models import FieldLabelAlias
    from documents.services.field_aliases import propose_alias_candidate

    _a1, outcome1 = propose_alias_candidate(
        field="student_name",
        alias="Verified Label",
        provenance={"certificate_id": 101, "verified": True},
    )
    _a2, _ = propose_alias_candidate(
        field="exam",
        alias="Plain Label",
        provenance={"certificate_id": 102},
    )
    verified = FieldLabelAlias.objects.get(alias="Verified Label")
    plain = FieldLabelAlias.objects.get(alias="Plain Label")
    assert verified.confidence > plain.confidence
    # Corroboration is NOT bypassed: still a candidate after one observation.
    assert verified.lifecycle == "candidate"
    assert verified.support_count == 1
    assert outcome1 == "created"


def test_rejected_sample_never_teaches_profile():
    from datetime import date

    from catalog.models import Entity, FormatProfile
    from documents.services.format_profile import learn_format_profile
    from documents.tests.factories import add_page, make_document

    entity = Entity.objects.create(name="Rejected Entity")
    doc = make_document(fingerprint="rej" * 16)
    add_page(doc, text="shared boilerplate line one\nshared boilerplate line two")
    cert = make_certificate(
        document=doc,
        entity=entity,
        issue_date=date(2024, 1, 1),
        review_status="rejected",
        verification_status="verified_at_source",
    )
    assert learn_format_profile(cert) is None
    assert not FormatProfile.objects.filter(entity=entity).exists()
