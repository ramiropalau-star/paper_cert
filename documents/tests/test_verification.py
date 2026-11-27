import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from documents.models import Certificate, Document, DocumentPage, ReviewEvent
from documents.services.verification import (
    apply_verification_artifacts,
    harvest_verification,
)
from documents.services.verifiers import verify_at_source

pytestmark = pytest.mark.django_db

GVA_TEXT = (
    "CERTIFICACIÓ ACADÈMICA DE NIVELL\n"
    "Autenticitat verificable mitjançant CSV 9613SQ59-DUKRFULT-YG7CRNFK "
    "en https://www.tramita.gva.es/csv-front/index.faces?cadena=9613SQ59-DUKRFULT-YG7CRNFK\n"
)

UV_TEXT = (
    "www.uv.es/cdi\n\n"
    "Id: UV-REDFirma-4751635 Cod. Verificació: H480BGXM95JWD2R2\n"
    "URL Verif: https://seu.uv.es/\n"
)

CAMBRIDGE_TEXT = (
    "160\n150\nReading\n189\nVerification Number\nD7952856\n"
    "This is an official Statement of Results. To verify the results, use "
    "the Results\nVerification Service https://www.cambridgeenglish.org/verifiers.\n"
)

OXFORD_TEXT = (
    "Results Verification\nTo verify the results shown on this\n"
    "Certificate, go to\ngo.oup.com/oxfordtestofenglish/verify\n"
)


def make_user(username: str, roles: tuple[str, ...] = ()) -> User:
    user = User.objects.create_user(username, password="password")
    for role in roles:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
    return user


def make_certificate(**overrides) -> Certificate:
    document = Document.objects.create(
        fingerprint="v" * 64,
        original_filename="certificate.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        processing_state=Document.ProcessingState.PENDING_REVIEW,
    )
    data = {"document": document, "student_name": "Ada"}
    data.update(overrides)
    return Certificate.objects.create(**data)


def test_harvest_gva_csv():
    artifacts = harvest_verification({1: GVA_TEXT})
    assert artifacts.code == "9613SQ59-DUKRFULT-YG7CRNFK"
    assert artifacts.url.startswith("https://www.tramita.gva.es/csv-front/")


def test_harvest_uv_code_url_and_document_id():
    artifacts = harvest_verification({1: UV_TEXT})
    assert artifacts.code == "H480BGXM95JWD2R2"
    assert artifacts.url == "https://seu.uv.es/"
    assert artifacts.evidence["document_id"] == "UV-REDFirma-4751635"


def test_harvest_cambridge_verification_number():
    artifacts = harvest_verification({1: CAMBRIDGE_TEXT})
    assert artifacts.code == "D7952856"
    assert "cambridgeenglish.org/verifiers" in artifacts.url


def test_harvest_oxford_bare_domain():
    artifacts = harvest_verification({1: OXFORD_TEXT})
    assert artifacts.url == "https://go.oup.com/oxfordtestofenglish/verify"


def test_harvest_none():
    artifacts = harvest_verification({1: "CERTIFICATE OF ENGLISH\nB2 First\n"})
    assert not artifacts.found


def test_apply_artifacts_sets_self_reported():
    certificate = make_certificate()
    apply_verification_artifacts(certificate, {1: GVA_TEXT})
    certificate.refresh_from_db()
    assert certificate.verification_status == "self_reported"
    assert certificate.verification_code == "9613SQ59-DUKRFULT-YG7CRNFK"


def test_apply_artifacts_none_status():
    certificate = make_certificate()
    apply_verification_artifacts(certificate, {1: "no verification here"})
    certificate.refresh_from_db()
    assert certificate.verification_status == "none"


def test_manual_confirm_survives_reextract():
    user = make_user("verifier", ("reviewer",))
    certificate = make_certificate(
        verification_status="manually_confirmed",
        verified_by=user,
    )
    apply_verification_artifacts(certificate, {1: GVA_TEXT})
    certificate.refresh_from_db()
    assert certificate.verification_status == "manually_confirmed"
    assert certificate.verified_by == user


def test_verify_at_source_unknown_domain_untouched():
    certificate = make_certificate(
        verification_url="https://portal.example.com/verify",
        verification_status="self_reported",
    )
    verify_at_source(certificate)
    certificate.refresh_from_db()
    assert certificate.verification_status == "self_reported"


def test_verify_at_source_success_marker(monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html"}
        content = b"El documento s'ha verificat correctament"
        text = "El documento s'ha verificat correctament"

    monkeypatch.setattr(
        "documents.services.verifiers.httpx.Client",
        _fake_httpx_client(FakeResponse()),
    )
    certificate = make_certificate(
        verification_url="https://www.tramita.gva.es/csv-front/index.faces?cadena=X",
        verification_code="X",
        verification_status="self_reported",
    )
    verify_at_source(certificate)
    certificate.refresh_from_db()
    assert certificate.verification_status == "verified_at_source"
    assert certificate.verified_at is not None
    assert certificate.verification_evidence["auto_check"]["ok"] is True


def test_verify_at_source_no_marker_stays_self_reported(monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html"}
        content = b"<html>form shell with captcha</html>"
        text = "<html>form shell with captcha</html>"

    monkeypatch.setattr(
        "documents.services.verifiers.httpx.Client",
        _fake_httpx_client(FakeResponse()),
    )
    certificate = make_certificate(
        verification_url="https://www.tramita.gva.es/csv-front/index.faces?cadena=X",
        verification_code="X",
        verification_status="self_reported",
    )
    verify_at_source(certificate)
    certificate.refresh_from_db()
    assert certificate.verification_status == "self_reported"
    assert certificate.verification_evidence["auto_check"]["ok"] is False


def _fake_httpx_client(response):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            FakeClient.requested_url = url
            return response

    return FakeClient


def test_uv_verify_success_returns_pdf(monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/pdf"}
        content = b"%PDF-1.7 fake signed document"
        text = ""

    monkeypatch.setattr(
        "documents.services.verifiers.httpx.Client",
        _fake_httpx_client(FakeResponse()),
    )
    certificate = make_certificate(
        verification_url="https://seu.uv.es/",
        verification_code="H480BGXM95JWD2R2",
        verification_evidence={"document_id": "UV-REDFirma-4751635"},
        verification_status="self_reported",
    )
    verify_at_source(certificate)
    certificate.refresh_from_db()
    assert certificate.verification_status == "verified_at_source"
    auto = certificate.verification_evidence["auto_check"]
    assert auto["ok"] is True and auto["detail"] == "signed_pdf_returned"
    assert "identificador=UV-REDFirma-4751635" in auto["evidence"]["url"]


def test_uv_verify_html_response_not_verified(monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html"}
        content = b"<html>login page</html>"
        text = "<html>login page</html>"

    monkeypatch.setattr(
        "documents.services.verifiers.httpx.Client",
        _fake_httpx_client(FakeResponse()),
    )
    certificate = make_certificate(
        verification_url="https://seu.uv.es/",
        verification_code="BAD",
        verification_evidence={"document_id": "UV-REDFirma-1"},
        verification_status="self_reported",
    )
    verify_at_source(certificate)
    certificate.refresh_from_db()
    assert certificate.verification_status == "self_reported"


def test_uv_verify_missing_document_id(monkeypatch):
    certificate = make_certificate(
        verification_url="https://seu.uv.es/",
        verification_code="H480",
        verification_status="self_reported",
    )
    verify_at_source(certificate)
    certificate.refresh_from_db()
    assert certificate.verification_status == "self_reported"
    assert certificate.verification_evidence["auto_check"]["detail"] == "missing_document_id"


def test_verify_source_view_roles_and_audit(client):
    reviewer = make_user("revv", ("reviewer",))
    viewer = make_user("viewv", ("viewer",))
    certificate = make_certificate(
        verification_code="ABC12345",
        verification_url="https://seu.uv.es/",
        verification_status="self_reported",
    )
    url = reverse("documents:verify_source", args=[certificate.document_id])

    client.force_login(viewer)
    response = client.post(url, {"action": "confirm"})
    assert response.status_code == 403

    client.force_login(reviewer)
    client.post(url, {"action": "confirm"})
    certificate.refresh_from_db()
    assert certificate.verification_status == "manually_confirmed"
    assert certificate.verified_by == reviewer
    assert ReviewEvent.objects.filter(certificate=certificate, event_type="verify").exists()

    client.post(url, {"action": "unconfirm"})
    certificate.refresh_from_db()
    assert certificate.verification_status == "self_reported"
    assert certificate.verified_by is None


def test_extraction_stores_verification_artifacts():
    import json

    from documents.services.extraction import (
        extract_certificate,
    )

    document = Document.objects.create(
        fingerprint="w" * 64,
        original_filename="certificate.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        processing_state=Document.ProcessingState.TEXT_READY,
        text_method=Document.TextMethod.EMBEDDED,
    )
    DocumentPage.objects.create(
        document=document,
        page_number=1,
        text=GVA_TEXT,
        method=DocumentPage.Method.EMBEDDED,
    )

    def field(value):
        return {"value": value, "evidence": None, "confidence": 0.9}

    payload = {
        "is_language_certificate": True,
        "multiple_certificates_suspected": False,
        "student_name": field("Ada"),
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

    class FakeLlm:
        def chat(self, messages, **kwargs):
            return json.dumps(payload)

        def close(self):
            pass

    class FakeStore:
        def label_document(self, *a, **k):
            return True

        def close(self):
            pass

    extract_certificate(document, llm=FakeLlm(), store=FakeStore())
    certificate = Certificate.objects.get(document=document)
    assert certificate.verification_code == "9613SQ59-DUKRFULT-YG7CRNFK"
    assert certificate.verification_status == "self_reported"
