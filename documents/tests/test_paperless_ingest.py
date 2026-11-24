"""Tests for Paperless-first ingestion via webhook."""

import json

import pytest
import respx
from django.test import Client
from django.urls import reverse

from documents.models import Document
from documents.services.paperless_ingest import ingest_paperless_document
from documents.tests.factories import pdf_bytes

pytestmark = pytest.mark.django_db

BASE_URL = "http://paperless.test"


def _store_options():
    return {
        "base_url": BASE_URL,
        "token": "token",
        "timeout": 5,
        "poll_interval": 0,
        "poll_timeout": 1,
    }


def _metadata(document_id="42", filename="certificate.pdf", mime="application/pdf"):
    return {
        "id": int(document_id),
        "title": "certificate",
        "mime_type": mime,
        "original_file_name": filename,
    }


def _mock_paperless(
    document_id="42", content=None, filename="certificate.pdf", mime="application/pdf"
):
    respx.get(f"{BASE_URL}/api/documents/{document_id}/").respond(
        json=_metadata(document_id, filename, mime)
    )
    respx.get(f"{BASE_URL}/api/documents/{document_id}/download/").respond(
        content=content if content is not None else pdf_bytes()
    )


@respx.mock
def test_ingest_creates_stored_document(tmp_path, monkeypatch, settings):
    monkeypatch.setitem(settings.APP, "n8n_processing_webhook_url", "")
    _mock_paperless()

    from documents.services.paperless import DocumentStore

    result = ingest_paperless_document("42", store=DocumentStore(**_store_options()))

    assert result.error == ""
    document = result.document
    assert document.paperless_document_id == "42"
    assert document.processing_state == Document.ProcessingState.STORED
    assert document.fingerprint


@respx.mock
def test_ingest_is_idempotent_by_paperless_id(monkeypatch, settings):
    monkeypatch.setitem(settings.APP, "n8n_processing_webhook_url", "")
    _mock_paperless()
    Document.objects.create(
        fingerprint="f" * 64,
        original_filename="certificate.pdf",
        content_type="application/pdf",
        size_bytes=10,
        paperless_document_id="42",
        processing_state=Document.ProcessingState.STORED,
    )

    from documents.services.paperless import DocumentStore

    result = ingest_paperless_document("42", store=DocumentStore(**_store_options()))

    assert result.duplicate is True
    assert Document.objects.count() == 1


@respx.mock
def test_ingest_deduplicates_by_fingerprint(monkeypatch, settings):
    monkeypatch.setitem(settings.APP, "n8n_processing_webhook_url", "")
    data = pdf_bytes()
    import hashlib

    Document.objects.create(
        fingerprint=hashlib.sha256(data).hexdigest(),
        original_filename="other.pdf",
        content_type="application/pdf",
        size_bytes=len(data),
        processing_state=Document.ProcessingState.STORED,
    )
    _mock_paperless(content=data)

    from documents.services.paperless import DocumentStore

    result = ingest_paperless_document("42", store=DocumentStore(**_store_options()))

    assert result.duplicate is True
    assert Document.objects.count() == 1


@respx.mock
def test_ingest_rejects_invalid_file(monkeypatch):
    _mock_paperless(content=b"not a pdf", filename="fake.pdf")

    from documents.services.paperless import DocumentStore

    result = ingest_paperless_document("42", store=DocumentStore(**_store_options()))

    assert result.error
    assert Document.objects.count() == 0


@respx.mock
def test_webhook_endpoint_ingests(monkeypatch, settings):
    monkeypatch.setitem(settings.APP, "internal_api_token", "secret")
    monkeypatch.setitem(settings.APP, "n8n_processing_webhook_url", "")
    _mock_paperless(document_id="77")

    client = Client()
    url = reverse("internal-paperless-webhook")
    response = client.post(
        url,
        data=json.dumps({"event": "document_added", "document": {"id": 77}}),
        content_type="application/json",
        HTTP_X_INTERNAL_TOKEN="secret",
    )

    assert response.status_code == 200
    assert response.json()["duplicate"] is False
    assert Document.objects.get().paperless_document_id == "77"


def test_webhook_endpoint_requires_token(settings, monkeypatch):
    monkeypatch.setitem(settings.APP, "internal_api_token", "secret")

    response = Client().post(
        reverse("internal-paperless-webhook"),
        data={"document_id": "1"},
        content_type="application/json",
    )

    assert response.status_code == 401


def test_webhook_endpoint_rejects_missing_id(settings, monkeypatch):
    monkeypatch.setitem(settings.APP, "internal_api_token", "secret")

    response = Client().post(
        reverse("internal-paperless-webhook"),
        data={},
        content_type="application/json",
        HTTP_X_INTERNAL_TOKEN="secret",
    )

    assert response.status_code == 400
