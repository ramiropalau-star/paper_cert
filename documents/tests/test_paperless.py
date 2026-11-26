import json

import httpx
import pytest
import respx

from documents.services.paperless import DocumentStore, PaperlessError

BASE_URL = "http://paperless.test"


def store(**overrides) -> DocumentStore:
    options = {
        "base_url": BASE_URL,
        "token": "token",
        "poll_interval": 0,
        "poll_timeout": 1,
    }
    options.update(overrides)
    return DocumentStore(**options)


@respx.mock
def test_store_document_posts_polls_and_returns_document_id(tmp_path):
    pdf = tmp_path / "certificate.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    post = respx.post(f"{BASE_URL}/api/documents/post_document/").respond(json="task-1")
    respx.get(f"{BASE_URL}/api/tasks/").respond(
        json={
            "results": [
                {"task_id": "other", "status": "SUCCESS", "related_document_ids": [7]},
                {
                    "task_id": "task-1",
                    "status": "SUCCESS",
                    "related_document_ids": [42],
                },
            ]
        }
    )

    document_id = store().store_document(pdf, "certificate.pdf", "application/pdf")

    assert document_id == "42"
    assert post.called


@respx.mock
def test_store_document_reports_task_failure(tmp_path):
    pdf = tmp_path / "certificate.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    respx.post(f"{BASE_URL}/api/documents/post_document/").respond(json="task-1")
    respx.get(f"{BASE_URL}/api/tasks/").respond(
        json={
            "results": [
                {
                    "task_id": "task-1",
                    "status": "FAILURE",
                    "result": "unreadable",
                }
            ]
        }
    )

    with pytest.raises(PaperlessError) as excinfo:
        store().store_document(pdf, "certificate.pdf", "application/pdf")

    assert "unreadable" in str(excinfo.value)


@respx.mock
def test_store_document_reports_timeout(tmp_path):
    pdf = tmp_path / "certificate.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    respx.post(f"{BASE_URL}/api/documents/post_document/").mock(
        side_effect=httpx.TimeoutException("slow")
    )

    with pytest.raises(PaperlessError) as excinfo:
        store().store_document(pdf, "certificate.pdf", "application/pdf")

    assert excinfo.value.retryable is True


@respx.mock
def test_task_poll_timeout_is_retryable(tmp_path):
    pdf = tmp_path / "certificate.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    respx.post(f"{BASE_URL}/api/documents/post_document/").respond(json="task-1")
    respx.get(f"{BASE_URL}/api/tasks/").respond(
        json={"results": [{"task_id": "task-1", "status": "STARTED"}]}
    )

    with pytest.raises(PaperlessError) as excinfo:
        store(poll_timeout=0).store_document(pdf, "certificate.pdf", "application/pdf")

    assert excinfo.value.retryable is True


@respx.mock
def test_ensure_tag_creates_missing_tag():
    respx.get(f"{BASE_URL}/api/tags/", params={"name": "Otros"}).respond(json={"results": []})
    respx.post(f"{BASE_URL}/api/tags/").respond(json={"id": 7, "name": "Otros"})

    assert store().ensure_tag("Otros") == 7


@respx.mock
def test_add_tag_patches_document_tags():
    respx.get(f"{BASE_URL}/api/tags/", params={"name": "Otros"}).respond(
        json={"results": [{"id": 7, "name": "Otros"}]}
    )
    respx.get(f"{BASE_URL}/api/documents/42/").respond(json={"id": 42, "tags": [1]})
    patch = respx.patch(f"{BASE_URL}/api/documents/42/").respond(json={"id": 42})

    assert store().add_tag("42", "Otros") is True
    assert json.loads(patch.calls[0].request.content) == {"tags": [1, 7]}


@respx.mock
def test_remove_tag_patches_document_tags():
    respx.get(f"{BASE_URL}/api/tags/", params={"name": "Otros"}).respond(
        json={"results": [{"id": 7, "name": "Otros"}]}
    )
    respx.get(f"{BASE_URL}/api/documents/42/").respond(json={"id": 42, "tags": [1, 7]})
    patch = respx.patch(f"{BASE_URL}/api/documents/42/").respond(json={"id": 42})

    assert store().remove_tag("42", "Otros") is True
    assert json.loads(patch.calls[0].request.content) == {"tags": [1]}


@respx.mock
def test_add_tag_is_idempotent():
    respx.get(f"{BASE_URL}/api/tags/", params={"name": "Otros"}).respond(
        json={"results": [{"id": 7, "name": "Otros"}]}
    )
    respx.get(f"{BASE_URL}/api/documents/42/").respond(json={"id": 42, "tags": [7]})
    patch = respx.patch(f"{BASE_URL}/api/documents/42/").respond(json={"id": 42})

    assert store().add_tag("42", "Otros") is False
    assert not patch.called


@respx.mock
def test_download_and_delete_document():
    respx.get(f"{BASE_URL}/api/documents/42/download/").respond(content=b"pdf")
    delete = respx.delete(f"{BASE_URL}/api/documents/42/").respond(status_code=204)

    store_instance = store()
    assert store_instance.download_original("42") == b"pdf"
    store_instance.delete_document("42")
    assert delete.called


@respx.mock
def test_get_retries_transient_failure_then_succeeds(monkeypatch):
    from django.conf import settings

    monkeypatch.setitem(settings.APP, "paperless_retries", 2)
    monkeypatch.setitem(settings.APP, "paperless_retry_backoff_seconds", 0)
    route = respx.get(f"{BASE_URL}/api/documents/42/").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"id": 42, "tags": []}),
        ]
    )

    metadata = store().get_document_metadata("42")

    assert metadata["id"] == 42
    assert route.call_count == 2


@respx.mock
def test_get_does_not_retry_permanent_failure(monkeypatch):
    from django.conf import settings

    monkeypatch.setitem(settings.APP, "paperless_retries", 3)
    monkeypatch.setitem(settings.APP, "paperless_retry_backoff_seconds", 0)
    route = respx.get(f"{BASE_URL}/api/documents/42/").respond(status_code=400)

    with pytest.raises(PaperlessError) as excinfo:
        store().get_document_metadata("42")

    assert excinfo.value.retryable is False
    assert route.call_count == 1


@respx.mock
def test_get_retry_budget_exhausted(monkeypatch):
    from django.conf import settings

    monkeypatch.setitem(settings.APP, "paperless_retries", 2)
    monkeypatch.setitem(settings.APP, "paperless_retry_backoff_seconds", 0)
    route = respx.get(f"{BASE_URL}/api/documents/42/").respond(status_code=503)

    with pytest.raises(PaperlessError) as excinfo:
        store().get_document_metadata("42")

    assert excinfo.value.retryable is True
    assert excinfo.value.status_code == 503
    assert route.call_count == 3  # initial + 2 retries


@respx.mock
def test_post_is_never_retried(monkeypatch, tmp_path):
    from django.conf import settings

    monkeypatch.setitem(settings.APP, "paperless_retries", 3)
    monkeypatch.setitem(settings.APP, "paperless_retry_backoff_seconds", 0)
    pdf = tmp_path / "certificate.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    route = respx.post(f"{BASE_URL}/api/documents/post_document/").respond(status_code=503)

    with pytest.raises(PaperlessError):
        store().store_document(pdf, "certificate.pdf", "application/pdf")

    assert route.call_count == 1


@respx.mock
def test_tag_catalog_is_fetched_once():
    route = respx.get(f"{BASE_URL}/api/tags/").respond(
        json={
            "count": 2,
            "next": None,
            "results": [
                {"id": 1, "name": "Idioma: English"},
                {"id": 2, "name": "Otros"},
            ],
        }
    )

    selected = store()
    assert selected.tag_catalog() == {"Idioma: English": 1, "Otros": 2}
    assert selected.tag_catalog() == {"Idioma: English": 1, "Otros": 2}
    assert route.call_count == 1


@respx.mock
def test_set_tags_patches_final_set_once():
    respx.get(f"{BASE_URL}/api/tags/").respond(
        json={
            "count": 3,
            "next": None,
            "results": [
                {"id": 1, "name": "Idioma: English"},
                {"id": 2, "name": "Entidad: Old"},
                {"id": 3, "name": "Custom"},
            ],
        }
    )
    respx.get(f"{BASE_URL}/api/documents/42/").respond(json={"id": 42, "tags": [1, 2, 3]})
    patch = respx.patch(f"{BASE_URL}/api/documents/42/").respond(json={"id": 42})

    assert store().set_tags("42", ["Idioma: English", "Custom"]) is True
    assert json.loads(patch.calls[0].request.content) == {"tags": [1, 3]}
    assert patch.call_count == 1


@respx.mock
def test_set_tags_skips_patch_when_unchanged():
    respx.get(f"{BASE_URL}/api/tags/").respond(
        json={
            "count": 1,
            "next": None,
            "results": [{"id": 1, "name": "Idioma: English"}],
        }
    )
    respx.get(f"{BASE_URL}/api/documents/42/").respond(json={"id": 42, "tags": [1]})
    patch = respx.patch(f"{BASE_URL}/api/documents/42/").respond(json={"id": 42})

    assert store().set_tags("42", ["Idioma: English"]) is False
    assert not patch.called


@respx.mock
def test_set_tags_creates_missing_tags():
    respx.get(f"{BASE_URL}/api/tags/").respond(json={"count": 0, "next": None, "results": []})
    respx.post(f"{BASE_URL}/api/tags/").respond(json={"id": 9, "name": "Nuevo"})
    respx.get(f"{BASE_URL}/api/documents/42/").respond(json={"id": 42, "tags": []})
    patch = respx.patch(f"{BASE_URL}/api/documents/42/").respond(json={"id": 42})

    assert store().set_tags("42", ["Nuevo"]) is True
    assert json.loads(patch.calls[0].request.content) == {"tags": [9]}


@respx.mock
def test_document_tag_names_uses_shared_catalog():
    route = respx.get(f"{BASE_URL}/api/tags/").respond(
        json={
            "count": 2,
            "next": None,
            "results": [
                {"id": 1, "name": "Idioma: English"},
                {"id": 2, "name": "Otros"},
            ],
        }
    )
    respx.get(f"{BASE_URL}/api/documents/42/").respond(json={"id": 42, "tags": [1, 2]})

    selected = store()
    assert set(selected.document_tag_names("42")) == {"Idioma: English", "Otros"}
    assert route.call_count == 1
