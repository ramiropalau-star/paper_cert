"""Tests for Paperless -> Django reconciliation sync."""

import pytest
import respx

from documents.models import Document
from documents.services.paperless import DocumentStore
from documents.services.sync import sync_paperless_documents
from documents.tests.factories import pdf_bytes
from documents.tests.test_paperless_ingest import BASE_URL, _store_options

pytestmark = pytest.mark.django_db


def _mock_document(document_id, filename):
    respx.get(f"{BASE_URL}/api/documents/{document_id}/").respond(
        json={
            "id": int(document_id),
            "title": filename,
            "mime_type": "application/pdf",
            "original_file_name": filename,
        }
    )
    respx.get(f"{BASE_URL}/api/documents/{document_id}/download/").respond(
        content=pdf_bytes(pages=int(document_id) % 3 + 1)
    )


@respx.mock
def test_sync_ingests_missing_documents(monkeypatch, settings):
    monkeypatch.setitem(settings.APP, "n8n_processing_webhook_url", "")
    respx.get(f"{BASE_URL}/api/documents/").respond(
        json={
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {"id": 10, "original_file_name": "a.pdf", "mime_type": "application/pdf"},
                {"id": 11, "original_file_name": "b.pdf", "mime_type": "application/pdf"},
            ],
        }
    )
    _mock_document("10", "a.pdf")
    _mock_document("11", "b.pdf")

    result = sync_paperless_documents(store=DocumentStore(**_store_options()))

    assert result.scanned == 2
    assert result.ingested == 2
    assert result.errors == []
    assert Document.objects.filter(paperless_document_id__in=["10", "11"]).count() == 2


@respx.mock
def test_sync_skips_known_and_dedups(monkeypatch, settings):
    monkeypatch.setitem(settings.APP, "n8n_processing_webhook_url", "")
    Document.objects.create(
        fingerprint="a" * 64,
        original_filename="dup.pdf",
        content_type="application/pdf",
        size_bytes=1,
        paperless_document_id="10",
    )
    respx.get(f"{BASE_URL}/api/documents/").respond(
        json={
            "count": 2,
            "next": None,
            "results": [
                {"id": 10},
                {"id": 11, "original_file_name": "new.pdf", "mime_type": "application/pdf"},
            ],
        }
    )
    _mock_document("11", "new.pdf")

    result = sync_paperless_documents(store=DocumentStore(**_store_options()))

    assert result.scanned == 2
    assert result.ingested == 1
    assert Document.objects.filter(paperless_document_id="11").exists()


@respx.mock
def test_sync_handles_paperless_list_failure():
    respx.get(f"{BASE_URL}/api/documents/").respond(500)

    result = sync_paperless_documents(store=DocumentStore(**_store_options()))

    assert result.scanned == 0
    assert result.errors


@respx.mock
def test_delete_all_wipes_django_and_paperless(settings):
    from django.contrib.auth.models import Group, User
    from django.test import Client
    from django.urls import reverse

    user = User.objects.create_user("admin-del", password="x")
    group, _ = Group.objects.get_or_create(name="admin")
    user.groups.add(group)
    Document.objects.create(
        fingerprint="b" * 64,
        original_filename="a.pdf",
        content_type="application/pdf",
        size_bytes=1,
        paperless_document_id="10",
    )
    respx.get(f"{BASE_URL}/api/documents/").respond(
        json={"count": 1, "next": None, "results": [{"id": 10}]}
    )
    respx.delete(f"{BASE_URL}/api/documents/10/").respond(204)

    client = Client()
    client.force_login(user)
    response = client.post(reverse("documents:delete_all"))

    assert response.status_code == 302
    assert Document.objects.count() == 0


def test_document_queue_lists_processing_only():
    from django.contrib.auth.models import Group, User
    from django.test import Client
    from django.urls import reverse

    user = User.objects.create_user("viewer-q", password="x")
    group, _ = Group.objects.get_or_create(name="viewer")
    user.groups.add(group)
    Document.objects.create(
        fingerprint="c" * 64,
        original_filename="busy.pdf",
        content_type="application/pdf",
        size_bytes=1,
        processing_state=Document.ProcessingState.EXTRACTED,
    )
    Document.objects.create(
        fingerprint="d" * 64,
        original_filename="done.pdf",
        content_type="application/pdf",
        size_bytes=1,
        processing_state=Document.ProcessingState.APPROVED,
    )

    client = Client()
    client.force_login(user)
    response = client.get(reverse("documents:queue"))

    assert response.status_code == 200
    assert b"busy.pdf" in response.content
    assert b"done.pdf" not in response.content


@respx.mock
def test_provision_webhook_creates_when_missing(settings):
    from documents.management.commands.provision_paperless_webhook import (
        provision_paperless_webhook,
    )
    from documents.services.paperless import DocumentStore

    respx.get(f"{BASE_URL}/api/workflows/").respond(json={"count": 0, "results": []})
    respx.post(f"{BASE_URL}/api/workflows/").respond(json={"id": 7})

    ok, detail = provision_paperless_webhook(store=DocumentStore(**_store_options()))

    assert ok
    assert "7" in detail


@respx.mock
def test_provision_webhook_skips_existing(settings):
    from documents.management.commands.provision_paperless_webhook import (
        provision_paperless_webhook,
    )
    from documents.services.paperless import DocumentStore

    respx.get(f"{BASE_URL}/api/workflows/").respond(
        json={
            "count": 1,
            "results": [
                {
                    "id": 3,
                    "actions": [
                        {
                            "type": 4,
                            "webhook": {"url": "http://app:8000/internal/paperless/webhook/"},
                        }
                    ],
                }
            ],
        }
    )

    ok, detail = provision_paperless_webhook(store=DocumentStore(**_store_options()))

    assert ok
    assert "ya existe" in detail
