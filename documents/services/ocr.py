"""Client for the isolated OCR service contract."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from django.conf import settings


class OcrError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "ocr_failed",
        retryable: bool = False,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.status_code = status_code


@dataclass(frozen=True)
class OcrPage:
    page_number: int
    text: str
    method: str
    confidence: float
    layout: dict | None = None


@dataclass(frozen=True)
class OcrResult:
    pages: tuple[OcrPage, ...]
    engine: dict
    mean_confidence: float
    quality: str
    contract_version: str


class OcrClient:
    """HTTP adapter for the versioned OCR service."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        languages: list[str] | tuple[str, ...] | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        page_limit: int | None = None,
        client: httpx.Client | None = None,
    ):
        app = settings.APP
        self.base_url = str(base_url or app["ocr_url"]).rstrip("/")
        self.languages = tuple(languages or app["ocr_languages"])
        self.timeout = float(app["ocr_timeout_seconds"] if timeout is None else timeout)
        self.retries = max(0, int(app["ocr_retries"] if retries is None else retries))
        self.page_limit = int(app["pdf_max_pages"] if page_limit is None else page_limit)
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def extract(
        self,
        data: bytes,
        filename: str,
        content_type: str,
        *,
        languages: list[str] | tuple[str, ...] | None = None,
        page_limit: int | None = None,
    ) -> OcrResult:
        selected_languages = tuple(languages or self.languages)
        limit = int(self.page_limit if page_limit is None else page_limit)
        last_error: OcrError | None = None

        for attempt in range(self.retries + 1):
            try:
                response = self._client.post(
                    "/v1/ocr",
                    files={"file": (filename, data, content_type)},
                    data={
                        "languages": ",".join(selected_languages),
                        "page_limit": str(limit),
                    },
                )
            except httpx.TimeoutException:
                last_error = OcrError("OCR request timed out", code="timeout", retryable=True)
            except httpx.HTTPError as exc:
                last_error = OcrError(
                    f"OCR request failed: {exc}", code="transport_error", retryable=True
                )
            else:
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = OcrError(
                        f"OCR service returned HTTP {response.status_code}",
                        code="service_unavailable",
                        retryable=True,
                        status_code=response.status_code,
                    )
                elif response.status_code >= 400:
                    raise self._error_from_response(response)
                else:
                    return self._parse_result(response)

            if attempt >= self.retries:
                raise last_error

        raise last_error or OcrError("OCR request failed")

    def _error_from_response(self, response: httpx.Response) -> OcrError:
        code = "ocr_rejected"
        message = f"OCR service returned HTTP {response.status_code}"
        retryable = False
        try:
            payload = response.json()
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            code = str(error.get("code") or code)
            message = str(error.get("message") or message)
            retryable = bool(error.get("retryable", False))
        except ValueError:
            pass
        return OcrError(
            message,
            code=code,
            retryable=retryable,
            status_code=response.status_code,
        )

    def _parse_result(self, response: httpx.Response) -> OcrResult:
        try:
            payload = response.json()
            pages = tuple(
                OcrPage(
                    page_number=int(page["page_number"]),
                    text=str(page["text"]),
                    method=str(page["method"]),
                    confidence=float(page["confidence"]),
                )
                for page in payload["pages"]
            )
            return OcrResult(
                pages=pages,
                engine=dict(payload.get("engine") or {}),
                mean_confidence=float(payload["mean_confidence"]),
                quality=str(payload.get("quality", "ok")),
                contract_version=str(payload["contract_version"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise OcrError(
                "OCR service returned an invalid response", code="invalid_response"
            ) from exc


def build_ocr_client() -> OcrClient:
    return OcrClient()
