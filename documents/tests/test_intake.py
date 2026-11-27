import pytest
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.urls import reverse

from documents.models import Document
from documents.services.intake import fingerprint_bytes, process_upload
from documents.services.paperless import PaperlessError
from documents.services.staging import staged_upload
from documents.services.validation import validate_upload
from documents.tests.factories import pdf_bytes

pytestmark = pytest.mark.django_db


class FakeStore:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.paths = []
        self.closed = False
        self.deleted = []

    def store_document(self, path, filename, content_type):
        self.paths.append(path)
        assert path.exists()
        if self.error:
            raise self.error
        return "42"

    def delete_document(self, document_id):
        self.deleted.append(document_id)

    def close(self):
        self.closed = True


def make_user(username="viewer", role="viewer"):
    user = User.objects.create_user(username, password="password")
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.add(group)
    return user


def test_process_upload_stores_document_and_removes_staging_file():
    user = make_user()
    fake = FakeStore()

    result = process_upload(
        pdf_bytes(),
        "certificate.pdf",
        "application/pdf",
        user=user,
        store=fake,
    )

    assert result.error == ""
    assert result.duplicate is False
    assert result.document.processing_state == Document.ProcessingState.STORED
    assert result.document.paperless_document_id == "42"
    assert result.document.page_count == 1
    assert fake.closed is False
    assert not any(path.exists() for path in fake.paths)


def test_duplicate_upload_returns_existing_document():
    fake = FakeStore()
    payload = pdf_bytes()
    first = process_upload(payload, "certificate.pdf", "application/pdf", store=fake)
    second = process_upload(payload, "copy.pdf", "application/pdf", store=fake)

    assert second.duplicate is True
    assert second.document.pk == first.document.pk
    assert Document.objects.count() == 1
    assert len(fake.paths) == 1


def test_invalid_upload_creates_no_document():
    result = process_upload(b"not a pdf", "certificate.txt", "text/plain")

    assert result.document is None
    assert result.error_code == "unsupported_extension"
    assert Document.objects.count() == 0


def test_paperless_failure_is_persisted_as_error_state():
    fake = FakeStore(error=PaperlessError("Paperless unavailable", retryable=True))

    result = process_upload(pdf_bytes(), "certificate.pdf", "application/pdf", store=fake)

    assert result.error_code == "paperless_error"
    assert result.document.processing_state == Document.ProcessingState.ERROR
    assert "Paperless unavailable" in result.document.error_reason


def test_concurrent_duplicate_converges_on_existing_document(monkeypatch):
    payload = pdf_bytes()
    validated = validate_upload(payload, "certificate.pdf", "application/pdf")
    fingerprint = fingerprint_bytes(validated.data)
    winner = Document.objects.create(
        fingerprint=fingerprint,
        original_filename="certificate.pdf",
        content_type="application/pdf",
        size_bytes=len(validated.data),
        processing_state=Document.ProcessingState.STORED,
        paperless_document_id="42",
    )

    # Simulate the race: the existence check misses, then the insert loses.
    monkeypatch.setattr(Document.objects, "filter", lambda *a, **k: Document.objects.none())
    monkeypatch.setattr(
        Document.objects,
        "create",
        lambda **kwargs: (_ for _ in ()).throw(IntegrityError("duplicate key")),
    )
    monkeypatch.setattr(Document.objects, "get", lambda **kwargs: winner)

    result = process_upload(payload, "certificate.pdf", "application/pdf")

    assert result.duplicate is True
    assert result.document.pk == winner.pk
    assert result.error == ""


def test_upload_retries_storage_for_error_document_without_paperless_id():
    payload = pdf_bytes()
    validated = validate_upload(payload, "certificate.pdf", "application/pdf")
    stuck = Document.objects.create(
        fingerprint=fingerprint_bytes(validated.data),
        original_filename="certificate.pdf",
        content_type="application/pdf",
        size_bytes=len(validated.data),
        processing_state=Document.ProcessingState.ERROR,
        error_reason="Paperless unavailable",
    )
    fake = FakeStore()

    result = process_upload(payload, "certificate.pdf", "application/pdf", store=fake)

    assert result.duplicate is True
    assert result.error == ""
    stuck.refresh_from_db()
    assert stuck.processing_state == Document.ProcessingState.STORED
    assert stuck.paperless_document_id == "42"
    assert stuck.error_reason == ""
    assert Document.objects.count() == 1


def test_upload_retry_failure_keeps_document_in_error():
    payload = pdf_bytes()
    validated = validate_upload(payload, "certificate.pdf", "application/pdf")
    stuck = Document.objects.create(
        fingerprint=fingerprint_bytes(validated.data),
        original_filename="certificate.pdf",
        content_type="application/pdf",
        size_bytes=len(validated.data),
        processing_state=Document.ProcessingState.ERROR,
        error_reason="Paperless unavailable",
    )
    fake = FakeStore(error=PaperlessError("still down", retryable=True))

    result = process_upload(payload, "certificate.pdf", "application/pdf", store=fake)

    assert result.error_code == "paperless_error"
    stuck.refresh_from_db()
    assert stuck.processing_state == Document.ProcessingState.ERROR
    assert stuck.paperless_document_id == ""
    assert "still down" in stuck.error_reason


def test_duplicate_of_healthy_document_does_not_retouch_storage():
    payload = pdf_bytes()
    first = process_upload(payload, "certificate.pdf", "application/pdf", store=FakeStore())
    second_store = FakeStore()

    second = process_upload(payload, "copy.pdf", "application/pdf", store=second_store)

    assert second.duplicate is True
    assert second.document.pk == first.document.pk
    assert second_store.paths == []


def test_staging_file_names_are_random_and_cleaned():
    paths = []
    with staged_upload(pdf_bytes(), "certificate.pdf") as first:
        assert first.exists()
        paths.append(first)
    with staged_upload(pdf_bytes(), "certificate.pdf") as second:
        assert second.exists()
        paths.append(second)

    assert paths[0] != paths[1]
    assert not any(path.exists() for path in paths)


def test_upload_view_accepts_pdf_and_redirects(client, monkeypatch):
    user = make_user()
    fake = FakeStore()
    monkeypatch.setattr("documents.services.intake.build_document_store", lambda: fake)
    client.force_login(user)

    response = client.post(
        reverse("documents:upload"),
        {
            "document": SimpleUploadedFile(
                "certificate.pdf", pdf_bytes(), content_type="application/pdf"
            )
        },
    )

    assert response.status_code == 302
    assert Document.objects.count() == 1
    assert Document.objects.get().processing_state == Document.ProcessingState.STORED


def test_upload_view_duplicate_is_not_counted_twice(client, monkeypatch):
    user = make_user()
    fake = FakeStore()
    monkeypatch.setattr("documents.services.intake.build_document_store", lambda: fake)
    client.force_login(user)

    payload = pdf_bytes()
    for _ in range(2):
        client.post(
            reverse("documents:upload"),
            {
                "document": SimpleUploadedFile(
                    "certificate.pdf", payload, content_type="application/pdf"
                )
            },
        )

    assert Document.objects.count() == 1


def test_upload_view_rejects_unsupported_file(client, monkeypatch):
    user = make_user()
    client.force_login(user)

    response = client.post(
        reverse("documents:upload"),
        {"document": SimpleUploadedFile("notes.txt", b"text", content_type="text/plain")},
    )

    assert response.status_code == 302
    assert Document.objects.count() == 0


def test_delete_allowed_for_admin(client, monkeypatch):
    admin = make_user("admin-user", "admin")
    document = Document.objects.create(
        fingerprint="a" * 64,
        original_filename="certificate.pdf",
        paperless_document_id="42",
    )
    fake = FakeStore()
    monkeypatch.setattr("documents.views.uploads.build_document_store", lambda: fake)
    client.force_login(admin)

    response = client.post(reverse("documents:delete", args=[document.pk]))

    assert response.status_code == 302
    assert fake.deleted == ["42"]
    assert Document.objects.count() == 0


def test_delete_forbidden_for_viewer(client):
    viewer = make_user()
    document = Document.objects.create(
        fingerprint="b" * 64,
        original_filename="certificate.pdf",
    )
    client.force_login(viewer)

    response = client.post(reverse("documents:delete", args=[document.pk]))

    assert response.status_code == 403
    assert Document.objects.count() == 1
