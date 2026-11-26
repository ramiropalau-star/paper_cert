"""Structured logging support: request ids and key-value/JSON formatters."""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

#: Extra fields rendered by the key-value formatter, in stable order.
KNOWN_EXTRA_KEYS = (
    "request_id",
    "document_id",
    "report_id",
    "outcome",
    "status_code",
    "reason",
    "error",
    "method",
    "path",
    "attempt",
)

_LOG_RECORD_BUILTINS = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {
    "message",
    "asctime",
}


class RequestIdFilter(logging.Filter):
    """Inject the current request id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", ""):
            record.request_id = request_id_var.get()
        return True


class KeyValueFormatter(logging.Formatter):
    """Append known structured fields as ``key=value`` pairs."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = " ".join(
            f"{key}={getattr(record, key)}"
            for key in KNOWN_EXTRA_KEYS
            if getattr(record, key, None) not in (None, "")
        )
        return f"{base} {extras}" if extras else base


class JsonFormatter(logging.Formatter):
    """Render each record as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_BUILTINS or key.startswith("_"):
                continue
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)
