import logging

import pytest
from django.conf import settings
from django.test import override_settings

pytestmark = pytest.mark.django_db


def test_internal_endpoint_rejects_missing_token(client):
    response = client.get("/internal/healthz")

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


def test_internal_endpoint_rejects_wrong_token(client):
    response = client.get("/internal/healthz", HTTP_X_INTERNAL_TOKEN="wrong")

    assert response.status_code == 401


def test_internal_endpoint_accepts_valid_token(client):
    response = client.get(
        "/internal/healthz",
        HTTP_X_INTERNAL_TOKEN="test-internal-token",
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "scope": "internal"}


def test_empty_configured_token_denies_every_request(client):
    with override_settings(APP={**settings.APP, "internal_api_token": ""}):
        response = client.get(
            "/internal/healthz",
            HTTP_X_INTERNAL_TOKEN="",
        )

    assert response.status_code == 401


def test_internal_requests_are_logged_with_outcome(client, caplog):
    caplog.set_level(logging.INFO, logger="core.internal")

    client.get("/internal/healthz", HTTP_X_INTERNAL_TOKEN="wrong")
    client.get(
        "/internal/healthz",
        HTTP_X_INTERNAL_TOKEN="test-internal-token",
        HTTP_X_REQUEST_ID="request-123",
    )

    records = [record for record in caplog.records if record.name == "core.internal"]
    assert [record.outcome for record in records] == ["denied", "accepted"]
    assert records[1].path == "/internal/healthz"
    assert records[1].request_id == "request-123"
