"""Outbound n8n trigger outcomes: TriggerResult, logging, recoverability."""

import json
import logging
from pathlib import Path

import httpx
import pytest
import respx
from django.contrib.auth.models import User

from documents.models import Document
from documents.services.n8n import notify_processing, notify_report
from reports.models import ReportJob
from reports.services import create_report_job

pytestmark = pytest.mark.django_db

PROCESSING_URL = "http://n8n.test/webhook/process"
REPORT_URL = "http://n8n.test/webhook/report"


def make_document(**overrides) -> Document:
    data = {
        "fingerprint": "a" * 64,
        "original_filename": "certificate.pdf",
        "content_type": "application/pdf",
        "size_bytes": 10,
        "processing_state": Document.ProcessingState.STORED,
        "paperless_document_id": "42",
    }
    data.update(overrides)
    return Document.objects.create(**data)


@respx.mock
def test_notify_processing_success():
    route = respx.post(PROCESSING_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    document = make_document()
    result = notify_processing(document)
    assert result.delivered
    assert result.status_code == 200
    assert route.called


@respx.mock
def test_notify_processing_server_error():
    respx.post(PROCESSING_URL).mock(return_value=httpx.Response(500))
    document = make_document()
    result = notify_processing(document)
    assert not result.delivered
    assert result.status_code == 500
    assert "500" in result.error


@respx.mock
def test_notify_processing_error_payload_with_200():
    respx.post(PROCESSING_URL).mock(
        return_value=httpx.Response(200, json={"error": True, "stage": "pipeline"})
    )
    document = make_document()
    result = notify_processing(document)
    assert not result.delivered
    assert result.status_code == 200


@respx.mock
def test_notify_processing_transport_error():
    respx.post(PROCESSING_URL).mock(side_effect=httpx.ConnectError("boom"))
    document = make_document()
    result = notify_processing(document)
    assert not result.delivered
    assert result.status_code is None
    assert "boom" in result.error


@respx.mock
def test_notify_report_not_found():
    respx.post(REPORT_URL).mock(return_value=httpx.Response(404))
    job = ReportJob.objects.create(status=ReportJob.Status.QUEUED)
    result = notify_report(job)
    assert not result.delivered
    assert result.status_code == 404


def test_failed_trigger_leaves_document_recoverable():
    """A failed processing trigger must not change the persisted state."""
    document = make_document()
    with respx.mock:
        respx.post(PROCESSING_URL).mock(return_value=httpx.Response(503))
        from documents.services.review import reprocess_document

        outcome = reprocess_document(document, None)
    assert outcome.ok
    document.refresh_from_db()
    assert document.processing_state == Document.ProcessingState.STORED


def test_failed_trigger_leaves_report_job_queued():
    user = User.objects.create_user("u")
    with respx.mock:
        respx.post(REPORT_URL).mock(return_value=httpx.Response(500))
        job = create_report_job({}, user)
    job.refresh_from_db()
    assert job.status == ReportJob.Status.QUEUED


def test_workflow_error_responders_return_5xx():
    root = Path(__file__).resolve().parents[2]
    for name in ("processing", "report"):
        workflow = json.loads((root / "n8n" / "workflows" / f"{name}.json").read_text())
        responders = [node for node in workflow["nodes"] if node.get("name") == "Respond error"]
        assert responders, f"{name} workflow has no error responder"
        for node in responders:
            code = node["parameters"].get("options", {}).get("responseCode")
            assert code is not None and int(code) >= 500


def _workflow(name: str) -> dict:
    root = Path(__file__).resolve().parents[2]
    return json.loads((root / "n8n" / "workflows" / f"{name}.json").read_text())


def _connections_to(workflow: dict, source: str) -> list[str]:
    targets = []
    for outputs in workflow["connections"].get(source, {}).get("main", []):
        for connection in outputs:
            targets.append(connection["node"])
    return targets


@pytest.mark.parametrize("name", ["processing", "report"])
def test_workflow_webhook_requires_token(name):
    workflow = _workflow(name)
    nodes = {node["name"]: node for node in workflow["nodes"]}

    webhook = next(node for node in workflow["nodes"] if node["type"] == "n8n-nodes-base.webhook")
    gate = nodes["Token válido"]
    assert gate["type"] == "n8n-nodes-base.if"

    condition = gate["parameters"]["conditions"]["conditions"][0]
    assert "x-webhook-token" in condition["leftValue"]
    assert "$env.APP_N8N_WEBHOOK_TOKEN" in condition["rightValue"]

    # The webhook feeds only the gate; no stage runs before authentication.
    assert _connections_to(workflow, webhook["name"]) == ["Token válido"]

    true_branch, false_branch = workflow["connections"]["Token válido"]["main"]
    stage_nodes = [
        node["name"] for node in workflow["nodes"] if node["type"] == "n8n-nodes-base.httpRequest"
    ]
    assert [c["node"] for c in true_branch] == [stage_nodes[0]]
    assert [c["node"] for c in false_branch] == ["Respond unauthorized"]

    unauthorized = nodes["Respond unauthorized"]
    assert unauthorized["type"] == "n8n-nodes-base.respondToWebhook"
    assert unauthorized["parameters"]["options"]["responseCode"] == 401


@pytest.mark.parametrize("name", ["processing", "report"])
def test_workflow_never_echoes_token(name):
    workflow = _workflow(name)
    for node in workflow["nodes"]:
        params = json.dumps(node.get("parameters", {}))
        # The token may only appear inside the IF comparison, never in output.
        if "APP_N8N_WEBHOOK_TOKEN" in params:
            assert node["type"] == "n8n-nodes-base.if"
        response_body = node.get("parameters", {}).get("responseBody", "")
        assert "WEBHOOK_TOKEN" not in response_body


@respx.mock
def test_trigger_failure_log_excludes_token(monkeypatch, settings, caplog):
    token = "super-secret-webhook-token"
    monkeypatch.setitem(settings.APP, "n8n_processing_webhook_url", PROCESSING_URL)
    monkeypatch.setitem(settings.APP, "n8n_webhook_token", token)
    respx.post(PROCESSING_URL).mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )
    document = make_document()

    with caplog.at_level(logging.WARNING, logger="documents.services.n8n"):
        result = notify_processing(document)

    assert not result.delivered
    assert result.status_code == 401
    assert token not in caplog.text
    assert token not in result.error
