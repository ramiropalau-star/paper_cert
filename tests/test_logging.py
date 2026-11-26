"""Structured logging: request id propagation and formatter output."""

import json
import logging

from django.test import RequestFactory

from core.logging import (
    JsonFormatter,
    KeyValueFormatter,
    RequestIdFilter,
    request_id_var,
)
from core.middleware import RequestIdMiddleware


def make_record(message="hello", **extra):
    record = logging.LogRecord("test", logging.INFO, __file__, 1, message, (), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_keyvalue_formatter_renders_known_extras():
    formatter = KeyValueFormatter("%(levelname)s %(message)s")
    record = make_record(
        "trigger failed",
        document_id=7,
        outcome="trigger_failed",
        status_code=500,
    )
    RequestIdFilter().filter(record)
    output = formatter.format(record)
    assert "document_id=7" in output
    assert "outcome=trigger_failed" in output
    assert "status_code=500" in output


def test_keyvalue_formatter_omits_missing_extras():
    formatter = KeyValueFormatter("%(levelname)s %(message)s")
    record = make_record("plain message")
    output = formatter.format(record)
    assert output == "INFO plain message"
    assert "document_id" not in output


def test_request_id_filter_uses_contextvar():
    token = request_id_var.set("req-123")
    try:
        record = make_record("with id")
        RequestIdFilter().filter(record)
        assert record.request_id == "req-123"
    finally:
        request_id_var.reset(token)


def test_json_formatter_outputs_valid_json_with_extras():
    formatter = JsonFormatter()
    record = make_record(
        "recovery failed",
        report_id=9,
        outcome="error",
        status_code=503,
    )
    payload = json.loads(formatter.format(record))
    assert payload["message"] == "recovery failed"
    assert payload["report_id"] == 9
    assert payload["outcome"] == "error"
    assert payload["status_code"] == 503


def test_request_id_middleware_uses_incoming_header():
    factory = RequestFactory()
    seen = {}

    def get_response(request):
        seen["request_id"] = request.request_id
        seen["contextvar"] = request_id_var.get()
        return "response"

    middleware = RequestIdMiddleware(get_response)
    request = factory.get("/healthz", HTTP_X_REQUEST_ID="abc-123")
    assert middleware(request) == "response"
    assert seen == {"request_id": "abc-123", "contextvar": "abc-123"}
    assert request_id_var.get() == ""


def test_request_id_middleware_generates_id_when_missing():
    factory = RequestFactory()
    seen = {}

    def get_response(request):
        seen["request_id"] = request.request_id
        return "response"

    middleware = RequestIdMiddleware(get_response)
    middleware(factory.get("/healthz"))
    assert seen["request_id"]
