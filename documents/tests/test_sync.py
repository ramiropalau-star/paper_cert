"""Tests for Paperless -> Django reconciliation sync."""

from datetime import UTC, datetime

import httpx
import pytest
import respx

from documents.models import Document, PaperlessSyncState
from documents.services.paperless import DocumentStore
from documents.services.sync import sync_paperless_documents
from documents.tests.factories import pdf_bytes
from documents.tests.test_paperless_ingest import BASE_URL, _store_options

pytestmark = pytest.mark.django_db


def _remote_doc(document_id, added, filename=None):
    return {
        "id": int(document_id),
        "original_file_name": filename or f"{document_id}.pdf",
        "mime_type": "application/pdf",
        "added": added,
    }


def _list_route(*docs):
    return respx.get(f"{BASE_URL}/api/documents/").respond(
        json={
            "count": len(docs),
            "next": None,
            "previous": None,
            "results": list(docs),
        }
    )


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
def test_first_sync_is_full_and_sets_watermark(monkeypatch, settings):
    monkeypatch.setitem(settings.APP, "n8n_processing_webhook_url", "")
    route = _list_route(
        _remote_doc("10", "2026-01-01T10:00:00Z", "a.pdf"),
        _remote_doc("11", "2026-01-01T12:00:00Z", "b.pdf"),
    )
    _mock_document("10", "a.pdf")
    _mock_document("11", "b.pdf")

    result = sync_paperless_documents(store=DocumentStore(**_store_options()))

    assert result.ingested == 2
    state = PaperlessSyncState.objects.get(pk=1)
    assert state.last_added == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert state.last_paperless_id == "11"
    assert "added__gte" not in route.calls[0].request.url.params


@respx.mock
def test_second_sync_requests_only_overlap_window(monkeypatch, settings):
    monkeypatch.setitem(settings.APP, "n8n_processing_webhook_url", "")
    PaperlessSyncState.objects.create(pk=1, last_added=datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    route = _list_route()

    result = sync_paperless_documents(store=DocumentStore(**_store_options()))

    assert result.scanned == 0
    params = route.calls[0].request.url.params
    assert params["added__gte"].startswith("2026-01-01T11:50")


@respx.mock
def test_incremental_sync_skips_known_documents(monkeypatch, settings):
    monkeypatch.setitem(settings.APP, "n8n_processing_webhook_url", "")
    Document.objects.create(
        fingerprint="e" * 64,
        original_filename="known.pdf",
        content_type="application/pdf",
        size_bytes=1,
        paperless_document_id="10",
    )
    PaperlessSyncState.objects.create(pk=1, last_added=datetime(2026, 1, 1, 11, 0, tzinfo=UTC))
    _list_route(_remote_doc("10", "2026-01-01T11:30:00Z", "known.pdf"))

    result = sync_paperless_documents(store=DocumentStore(**_store_options()))

    assert result.scanned == 1
    assert result.ingested == 0
    assert Document.objects.filter(paperless_document_id="10").count() == 1
    state = PaperlessSyncState.objects.get(pk=1)
    assert state.last_added == datetime(2026, 1, 1, 11, 30, tzinfo=UTC)


@respx.mock
def test_full_sync_ignores_watermark_and_repairs_missing(monkeypatch, settings):
    monkeypatch.setitem(settings.APP, "n8n_processing_webhook_url", "")
    PaperlessSyncState.objects.create(pk=1, last_added=datetime(2026, 1, 2, 0, 0, tzinfo=UTC))
    route = _list_route(_remote_doc("10", "2026-01-01T10:00:00Z", "a.pdf"))
    _mock_document("10", "a.pdf")

    result = sync_paperless_documents(store=DocumentStore(**_store_options()), full=True)

    assert result.full is True
    assert result.ingested == 1
    assert "added__gte" not in route.calls[0].request.url.params


@respx.mock
def test_listing_failure_keeps_watermark(monkeypatch, settings):
    monkeypatch.setitem(settings.APP, "paperless_retries", 0)
    original = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    PaperlessSyncState.objects.create(pk=1, last_added=original, last_paperless_id="9")
    respx.get(f"{BASE_URL}/api/documents/").respond(500)

    result = sync_paperless_documents(store=DocumentStore(**_store_options()))

    assert result.errors
    state = PaperlessSyncState.objects.get(pk=1)
    assert state.last_added == original
    assert state.last_paperless_id == "9"


@respx.mock
def test_ingest_failure_advances_watermark_to_oldest_failure(monkeypatch, settings):
    monkeypatch.setitem(settings.APP, "n8n_processing_webhook_url", "")
    monkeypatch.setitem(settings.APP, "paperless_retries", 0)
    _list_route(
        _remote_doc("10", "2026-01-01T10:00:00Z", "bad.pdf"),
        _remote_doc("11", "2026-01-01T11:00:00Z", "good.pdf"),
    )
    respx.get(f"{BASE_URL}/api/documents/10/").respond(
        json={
            "id": 10,
            "title": "bad",
            "mime_type": "application/pdf",
            "original_file_name": "bad.pdf",
        }
    )
    respx.get(f"{BASE_URL}/api/documents/10/download/").respond(500)
    _mock_document("11", "good.pdf")

    result = sync_paperless_documents(store=DocumentStore(**_store_options()))

    assert result.ingested == 1
    assert len(result.errors) == 1
    state = PaperlessSyncState.objects.get(pk=1)
    # Oldest failure (10:00) minus the 600s overlap -> 09:50.
    assert state.last_added == datetime(2026, 1, 1, 9, 50, tzinfo=UTC)
    assert state.last_paperless_id == "10"


@respx.mock
def test_unsupported_since_filter_falls_back_to_full_listing(monkeypatch, settings, caplog):
    monkeypatch.setitem(settings.APP, "n8n_processing_webhook_url", "")
    import logging

    PaperlessSyncState.objects.create(pk=1, last_added=datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    route = respx.get(f"{BASE_URL}/api/documents/").mock(
        side_effect=[
            httpx.Response(400, json={"detail": "Invalid filter"}),
            httpx.Response(
                200,
                json={
                    "count": 1,
                    "next": None,
                    "results": [_remote_doc("10", "2026-01-01T10:00:00Z", "a.pdf")],
                },
            ),
        ]
    )
    _mock_document("10", "a.pdf")

    with caplog.at_level(logging.WARNING, logger="documents.sync"):
        result = sync_paperless_documents(store=DocumentStore(**_store_options()))

    assert result.ingested == 1
    assert result.errors == []
    assert len(route.calls) == 2
    assert "added__gte" in route.calls[0].request.url.params
    assert "added__gte" not in route.calls[1].request.url.params
    assert any(r.message == "sync_filter_unsupported" for r in caplog.records)


def test_sync_command_full_flag(capsys):
    from django.core.management import call_command

    with respx.mock:
        respx.get(f"{BASE_URL}/api/documents/").respond(
            json={"count": 0, "next": None, "results": []}
        )
        call_command("sync_paperless")
        call_command("sync_paperless", full=True)

    out = capsys.readouterr().out
    assert "incremental" in out
    assert "completa" in out


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


def _admin_client():
    from django.contrib.auth.models import Group, User
    from django.test import Client

    user = User.objects.create_user("admin-del", password="x")
    group, _ = Group.objects.get_or_create(name="admin")
    user.groups.add(group)
    client = Client()
    client.force_login(user)
    return client


def _tracked_document():
    return Document.objects.create(
        fingerprint="b" * 64,
        original_filename="a.pdf",
        content_type="application/pdf",
        size_bytes=1,
        paperless_document_id="10",
    )


@respx.mock
def test_delete_all_tracked_scope_ignores_untracked(settings):
    from django.urls import reverse

    _tracked_document()
    respx.get(f"{BASE_URL}/api/documents/").respond(
        json={
            "count": 2,
            "next": None,
            "results": [{"id": 10}, {"id": 11}],
        }
    )
    delete_tracked = respx.delete(f"{BASE_URL}/api/documents/10/").respond(204)
    delete_untracked = respx.delete(f"{BASE_URL}/api/documents/11/").respond(204)

    client = _admin_client()
    response = client.post(reverse("documents:delete_all"), {"scope": "tracked"})

    assert response.status_code == 302
    assert Document.objects.count() == 0
    assert delete_tracked.called
    assert not delete_untracked.called


@respx.mock
def test_delete_all_untracked_requires_typed_confirmation(settings):
    from django.urls import reverse

    _tracked_document()
    respx.get(f"{BASE_URL}/api/documents/").respond(
        json={
            "count": 2,
            "next": None,
            "results": [{"id": 10}, {"id": 11}],
        }
    )
    delete_untracked = respx.delete(f"{BASE_URL}/api/documents/11/").respond(204)

    client = _admin_client()
    response = client.post(reverse("documents:delete_all"), {"scope": "untracked"})

    assert response.status_code == 302
    assert Document.objects.count() == 1
    assert not delete_untracked.called


@respx.mock
def test_delete_all_untracked_confirmed_deletes_only_untracked(settings, caplog):
    import logging

    from django.urls import reverse

    _tracked_document()
    respx.get(f"{BASE_URL}/api/documents/").respond(
        json={
            "count": 2,
            "next": None,
            "results": [{"id": 10}, {"id": 11}],
        }
    )
    delete_tracked = respx.delete(f"{BASE_URL}/api/documents/10/").respond(204)
    delete_untracked = respx.delete(f"{BASE_URL}/api/documents/11/").respond(204)

    client = _admin_client()
    with caplog.at_level(logging.INFO, logger="documents.views"):
        response = client.post(
            reverse("documents:delete_all"),
            {"scope": "untracked", "confirm": "DELETE-UNTRACKED"},
        )

    assert response.status_code == 302
    assert Document.objects.count() == 1
    assert delete_untracked.called
    assert not delete_tracked.called

    record = next(r for r in caplog.records if r.message == "bulk_delete")
    assert record.scope == "untracked"
    assert record.untracked_count == 1


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
