"""Paperless-ngx document-store adapter."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx
from django.conf import settings


class PaperlessError(Exception):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class DocumentStore:
    """Small adapter over the Paperless-ngx API used by the pipeline."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        poll_interval: float | None = None,
        poll_timeout: float | None = None,
        client: httpx.Client | None = None,
    ):
        app = settings.APP
        self.base_url = str(base_url or app["paperless_url"]).rstrip("/")
        self.token = str(token if token is not None else app["paperless_token"])
        self.timeout = float(timeout or app["paperless_timeout_seconds"])
        self.poll_interval = float(
            app["paperless_poll_interval_seconds"] if poll_interval is None else poll_interval
        )
        self.poll_timeout = float(
            app["paperless_poll_timeout_seconds"] if poll_timeout is None else poll_timeout
        )
        self.retries = int(app.get("paperless_retries") or 0)
        self.retry_backoff = float(app.get("paperless_retry_backoff_seconds") or 0.5)
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Token {self.token}"},
            timeout=self.timeout,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    _IDEMPOTENT_METHODS = {"GET", "PATCH", "DELETE"}
    _MAX_BACKOFF_SECONDS = 8.0

    def _request_once(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise PaperlessError(f"Paperless request timed out: {exc}", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise PaperlessError(f"Paperless request failed: {exc}", retryable=True) from exc

        if response.status_code >= 500 or response.status_code == 429:
            raise PaperlessError(
                f"Paperless returned HTTP {response.status_code}",
                retryable=True,
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise PaperlessError(
                f"Paperless returned HTTP {response.status_code}: {response.text[:300]}",
                retryable=False,
                status_code=response.status_code,
            )
        return response

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Issue a request, retrying transient failures on idempotent methods.

        ``POST`` is never retried: Paperless has no idempotency key for
        ``post_document``, so a retry after a lost response could create a
        duplicate document.
        """
        attempts = self.retries + 1 if method.upper() in self._IDEMPOTENT_METHODS else 1
        last_error: PaperlessError | None = None
        for attempt in range(attempts):
            try:
                return self._request_once(method, url, **kwargs)
            except PaperlessError as exc:
                last_error = exc
                if not exc.retryable or attempt == attempts - 1:
                    raise
                delay = min(self.retry_backoff * (2**attempt), self._MAX_BACKOFF_SECONDS)
                time.sleep(delay)
        raise last_error  # pragma: no cover - loop always returns or raises

    def _json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise PaperlessError("Paperless returned invalid JSON") from exc

    @staticmethod
    def _extract_task_id(payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        if isinstance(payload, dict):
            for key in ("task_id", "uuid", "id"):
                if payload.get(key):
                    return str(payload[key])
        raise PaperlessError("Paperless did not return a task id")

    def _wait_for_task(self, task_id: str) -> str:
        deadline = time.monotonic() + self.poll_timeout
        while True:
            response = self._request("GET", "/api/tasks/")
            payload = self._json(response)
            tasks = payload.get("results", []) if isinstance(payload, dict) else payload
            if isinstance(tasks, dict):
                tasks = [tasks]
            task = next(
                (t for t in tasks or [] if str(t.get("task_id")) == task_id),
                None,
            )
            if task is not None:
                status = str(task.get("status", "")).lower()
                if status in {"success", "completed"}:
                    document_ids = task.get("related_document_ids") or []
                    if document_ids:
                        return str(document_ids[0])
                    document_id = task.get("related_document")
                    if isinstance(document_id, dict):
                        document_id = document_id.get("id")
                    if document_id:
                        return str(document_id)
                    raise PaperlessError("Paperless task succeeded without a related document")
                if status in {"failure", "failed"}:
                    detail = task.get("result") or "Paperless task failed"
                    raise PaperlessError(str(detail))
            if time.monotonic() >= deadline:
                raise PaperlessError(
                    "Timed out waiting for Paperless to store the document",
                    retryable=True,
                )
            time.sleep(self.poll_interval)

    def store_document(self, path: Path, filename: str, content_type: str) -> str:
        with path.open("rb") as handle:
            response = self._request(
                "POST",
                "/api/documents/post_document/",
                files={"document": (filename, handle, content_type)},
            )
        task_id = self._extract_task_id(self._json(response))
        return self._wait_for_task(task_id)

    def download_original(self, document_id: str) -> bytes:
        response = self._request("GET", f"/api/documents/{document_id}/download/")
        return response.content

    def download_thumbnail(self, document_id: str) -> bytes:
        response = self._request("GET", f"/api/documents/{document_id}/thumb/")
        return response.content

    def get_document_metadata(self, document_id: str) -> dict[str, Any]:
        response = self._request("GET", f"/api/documents/{document_id}/")
        payload = self._json(response)
        if not isinstance(payload, dict):
            raise PaperlessError("Paperless returned invalid document metadata")
        return payload

    def list_documents(self, *, since: Any = None) -> list[dict[str, Any]]:
        """Return metadata for Paperless documents (paginated).

        When ``since`` is a datetime, only documents added at or after it are
        requested via the ``added__gte`` filter.
        """
        results: list[dict[str, Any]] = []
        url = "/api/documents/"
        params: dict[str, Any] | None = {"page_size": 100}
        if since is not None:
            params["added__gte"] = since.isoformat()
        while url:
            response = self._request("GET", url, params=params)
            payload = self._json(response)
            if isinstance(payload, dict):
                results.extend(payload.get("results", []))
                url = payload.get("next") or ""
                params = None
            else:
                results.extend(payload or [])
                break
        return [item for item in results if isinstance(item, dict)]

    def delete_document(self, document_id: str) -> None:
        self._request("DELETE", f"/api/documents/{document_id}/")

    def _find_tag(self, name: str) -> int | None:
        response = self._request("GET", "/api/tags/", params={"name": name})
        payload = self._json(response)
        results = payload.get("results", []) if isinstance(payload, dict) else payload
        for tag in results or []:
            if tag.get("name") == name:
                return int(tag["id"])
        return None

    def ensure_tag(self, name: str) -> int:
        existing = self._find_tag(name)
        if existing is not None:
            return existing
        response = self._request("POST", "/api/tags/", json={"name": name})
        payload = self._json(response)
        if not isinstance(payload, dict) or "id" not in payload:
            raise PaperlessError("Paperless did not return the created tag id")
        return int(payload["id"])

    def _document_tag_ids(self, document_id: str) -> list[int]:
        response = self._request("GET", f"/api/documents/{document_id}/")
        payload = self._json(response)
        tags = payload.get("tags", []) if isinstance(payload, dict) else []
        return [int(tag) for tag in tags]

    def add_tag(self, document_id: str, name: str) -> bool:
        tag_id = self.ensure_tag(name)
        current = self._document_tag_ids(document_id)
        if tag_id in current:
            return False
        self._request(
            "PATCH",
            f"/api/documents/{document_id}/",
            json={"tags": [*current, tag_id]},
        )
        return True

    def _load_tag_catalog(self) -> dict[str, int]:
        catalog: dict[str, int] = {}
        url = "/api/tags/"
        params: dict[str, Any] | None = {"page_size": 100}
        while url:
            response = self._request("GET", url, params=params)
            payload = self._json(response)
            if isinstance(payload, dict):
                for tag in payload.get("results", []):
                    if isinstance(tag, dict) and tag.get("name") and tag.get("id") is not None:
                        catalog[str(tag["name"])] = int(tag["id"])
                url = payload.get("next") or ""
                params = None
            else:
                for tag in payload or []:
                    if isinstance(tag, dict) and tag.get("name") and tag.get("id") is not None:
                        catalog[str(tag["name"])] = int(tag["id"])
                break
        return catalog

    def tag_catalog(self) -> dict[str, int]:
        """Return the name -> id map for every Paperless tag, fetched once."""
        if not hasattr(self, "_tag_catalog"):
            self._tag_catalog = self._load_tag_catalog()
        return self._tag_catalog

    def ensure_tags(self, names: Any) -> None:
        """Create any missing tags and keep the catalog up to date."""
        catalog = self.tag_catalog()
        for name in names:
            if name in catalog:
                continue
            response = self._request("POST", "/api/tags/", json={"name": name})
            payload = self._json(response)
            if not isinstance(payload, dict) or "id" not in payload:
                raise PaperlessError("Paperless did not return the created tag id")
            catalog[name] = int(payload["id"])

    def set_tags(self, document_id: str, names: Any) -> bool:
        """Replace the document's tag set with ``names`` using one PATCH.

        Returns True when the document was modified. Callers compute the final
        desired set (including tags they do not manage).
        """
        wanted_names = sorted({str(name) for name in names})
        self.ensure_tags(wanted_names)
        catalog = self.tag_catalog()
        wanted_ids = sorted({catalog[name] for name in wanted_names})
        current = self._document_tag_ids(document_id)
        if sorted(current) == wanted_ids:
            return False
        self._request(
            "PATCH",
            f"/api/documents/{document_id}/",
            json={"tags": wanted_ids},
        )
        return True

    def document_tag_names(self, document_id: str) -> list[str]:
        tag_ids = set(self._document_tag_ids(document_id))
        if not tag_ids:
            return []
        id_to_name = {tag_id: name for name, tag_id in self.tag_catalog().items()}
        return [id_to_name[tag_id] for tag_id in tag_ids if tag_id in id_to_name]

    def remove_tag(self, document_id: str, name: str) -> bool:
        tag_id = self._find_tag(name)
        if tag_id is None:
            return False
        current = self._document_tag_ids(document_id)
        if tag_id not in current:
            return False
        self._request(
            "PATCH",
            f"/api/documents/{document_id}/",
            json={"tags": [value for value in current if value != tag_id]},
        )
        return True


def build_document_store() -> DocumentStore:
    return DocumentStore()
