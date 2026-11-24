"""Client for the local Ollama chat API."""

from __future__ import annotations

from typing import Any

import httpx
from django.conf import settings


class OllamaError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "ollama_failed",
        retryable: bool = False,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.status_code = status_code


class OllamaClient:
    """HTTP adapter for Ollama ``/api/chat`` with bounded transport retries."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        client: httpx.Client | None = None,
    ):
        app = settings.APP
        self.base_url = str(base_url or app["ollama_url"]).rstrip("/")
        self.model = str(model or app["ollama_model"])
        self.timeout = float(app["ollama_timeout_seconds"] if timeout is None else timeout)
        self.retries = max(0, int(app["ollama_retries"] if retries is None else retries))
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        format: dict[str, Any] | str | None = None,
        temperature: float = 0.0,
    ) -> str:
        """Send a chat request and return the assistant message content."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if format is not None:
            payload["format"] = format

        last_error: OllamaError | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self._client.post("/api/chat", json=payload)
            except httpx.TimeoutException:
                last_error = OllamaError("Ollama request timed out", code="timeout", retryable=True)
            except httpx.HTTPError as exc:
                last_error = OllamaError(
                    f"Ollama request failed: {exc}",
                    code="transport_error",
                    retryable=True,
                )
            else:
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = OllamaError(
                        f"Ollama returned HTTP {response.status_code}",
                        code="service_unavailable",
                        retryable=True,
                        status_code=response.status_code,
                    )
                elif response.status_code >= 400:
                    raise self._error_from_response(response)
                else:
                    return self._parse_content(response)

            if attempt >= self.retries:
                raise last_error

        raise last_error or OllamaError("Ollama request failed")

    def _error_from_response(self, response: httpx.Response) -> OllamaError:
        message = f"Ollama returned HTTP {response.status_code}"
        try:
            payload = response.json()
            if isinstance(payload, dict) and payload.get("error"):
                message = f"{message}: {payload['error']}"
        except ValueError:
            pass
        return OllamaError(
            message,
            code="request_rejected",
            retryable=False,
            status_code=response.status_code,
        )

    @staticmethod
    def _parse_content(response: httpx.Response) -> str:
        try:
            payload = response.json()
            content = payload["message"]["content"]
        except (KeyError, TypeError, ValueError) as exc:
            raise OllamaError(
                "Ollama returned an invalid response", code="invalid_response"
            ) from exc
        if not isinstance(content, str):
            raise OllamaError("Ollama returned an invalid response", code="invalid_response")
        return content


def build_ollama_client() -> OllamaClient:
    return OllamaClient()
