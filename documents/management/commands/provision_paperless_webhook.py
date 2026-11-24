"""Provision the Paperless 'document added' webhook into Django.

Idempotent: looks for an existing workflow whose webhook action already
points at the app's internal ingest endpoint; creates it when missing.
Safe to run on every deploy.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from documents.services.paperless import DocumentStore, PaperlessError, build_document_store

logger = logging.getLogger("documents.provision")

WORKFLOW_NAME = "App intake webhook"
TRIGGER_TYPE_DOCUMENT_ADDED = 2
TRIGGER_SOURCES_ALL = [1, 2, 3, 4]
ACTION_TYPE_WEBHOOK = 4


def _webhook_target() -> str:
    return str(
        settings.APP.get("paperless_webhook_target")
        or "http://app:8000/internal/paperless/webhook/"
    )


def _desired_payload() -> dict:
    token = str(settings.APP.get("internal_api_token") or "")
    headers = {"X-Internal-Token": token} if token else {}
    return {
        "name": WORKFLOW_NAME,
        "order": 1,
        "enabled": True,
        "triggers": [
            {
                "type": TRIGGER_TYPE_DOCUMENT_ADDED,
                "sources": TRIGGER_SOURCES_ALL,
                "filter_path": None,
                "filter_filename": None,
                "filter_mailrule": None,
                "matching_algorithm": 0,
                "match": "",
                "is_insensitive": True,
                "filter_has_tags": [],
                "filter_has_all_tags": [],
                "filter_has_not_tags": [],
                "filter_custom_field_query": None,
                "filter_has_any_correspondents": [],
                "filter_has_not_correspondents": [],
                "filter_has_any_document_types": [],
                "filter_has_not_document_types": [],
                "filter_has_any_storage_paths": [],
                "filter_has_not_storage_paths": [],
                "filter_has_correspondent": None,
                "filter_has_document_type": None,
                "filter_has_storage_path": None,
                "schedule_offset_days": 0,
                "schedule_is_recurring": False,
                "schedule_recurring_interval_days": 1,
                "schedule_date_field": "added",
                "schedule_date_custom_field": None,
            }
        ],
        "actions": [
            {
                "type": ACTION_TYPE_WEBHOOK,
                "webhook": {
                    "url": _webhook_target(),
                    "use_params": True,
                    "as_json": True,
                    "params": {
                        "event": "document_added",
                        "document_id": "{{ doc_id }}",
                    },
                    "body": None,
                    "headers": headers,
                    "include_document": False,
                },
            }
        ],
    }


def _workflow_points_at_app(workflow: dict) -> bool:
    target = _webhook_target()
    for action in workflow.get("actions") or []:
        webhook = action.get("webhook") or {}
        if webhook.get("url") == target:
            return True
    return False


def provision_paperless_webhook(*, store: DocumentStore | None = None) -> tuple[bool, str]:
    """Ensure the intake webhook exists in Paperless. Returns (ok, detail)."""
    owns_store = store is None
    store = store or build_document_store()
    try:
        response = store._request("GET", "/api/workflows/")
        payload = store._json(response)
        results = payload.get("results", []) if isinstance(payload, dict) else payload
        for workflow in results or []:
            if _workflow_points_at_app(workflow):
                return True, f"Webhook ya existe (workflow #{workflow.get('id')})."

        response = store._request("POST", "/api/workflows/", json=_desired_payload())
        created = store._json(response)
        workflow_id = created.get("id") if isinstance(created, dict) else None
        return True, f"Webhook creado (workflow #{workflow_id})."
    except PaperlessError as exc:
        return False, str(exc)
    finally:
        if owns_store:
            store.close()


class Command(BaseCommand):
    help = "Create or verify the Paperless document-added webhook."

    def handle(self, *args, **options):
        ok, detail = provision_paperless_webhook()
        if ok:
            self.stdout.write(self.style.SUCCESS(f"Paperless webhook: {detail}"))
        else:
            self.stdout.write(self.style.WARNING(f"Paperless webhook: {detail}"))
