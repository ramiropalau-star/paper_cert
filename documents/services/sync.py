"""Reconcile Django documents with everything stored in Paperless.

The Paperless webhook only fires for documents consumed after it was
configured. This sync closes the gap: it lists Paperless documents and
ingests the ones missing from Django through the normal dedup pipeline.

A persisted watermark (``PaperlessSyncState``) lets regular runs request only
documents added since the last successful sync, minus an overlap window.
``full=True`` ignores the watermark and reconciles the whole archive.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.utils.dateparse import parse_datetime

from documents.models import Document, PaperlessSyncState
from documents.services.paperless import DocumentStore, PaperlessError, build_document_store
from documents.services.paperless_ingest import ingest_paperless_document

logger = logging.getLogger("documents.sync")


@dataclass
class SyncResult:
    scanned: int = 0
    ingested: int = 0
    duplicates: int = 0
    errors: list[str] = field(default_factory=list)
    full: bool = False
    watermark: datetime | None = None


def _parse_added(value: Any) -> datetime | None:
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed is not None and parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed


def _overlap() -> timedelta:
    return timedelta(seconds=float(settings.APP.get("sync_overlap_seconds") or 0))


def _save_watermark(state: PaperlessSyncState, added: datetime | None, remote_id: str) -> None:
    if added is None:
        return
    state.last_added = added
    state.last_paperless_id = remote_id
    state.save(update_fields=["last_added", "last_paperless_id", "updated_at"])


def sync_paperless_documents(
    *, store: DocumentStore | None = None, full: bool = False
) -> SyncResult:
    result = SyncResult(full=full)
    state, _ = PaperlessSyncState.objects.get_or_create(pk=1)
    result.watermark = state.last_added
    overlap = _overlap()
    since = None if full or not state.last_added else state.last_added - overlap

    owns_store = store is None
    store = store or build_document_store()
    try:
        try:
            remote = store.list_documents(since=since)
        except PaperlessError as exc:
            if since is None or exc.status_code != 400:
                raise
            logger.warning(
                "sync_filter_unsupported",
                extra={"outcome": "fallback", "error": str(exc)},
            )
            remote = store.list_documents()
    except Exception as exc:  # PaperlessError or transport issues
        result.errors.append(f"No se pudo listar Paperless: {exc}")
        return result
    finally:
        if owns_store:
            store.close()

    known_ids = set(
        Document.objects.exclude(paperless_document_id="")
        .exclude(paperless_document_id__isnull=True)
        .values_list("paperless_document_id", flat=True)
    )
    result.scanned = len(remote)

    newest_added: datetime | None = None
    newest_id = ""
    failed: list[tuple[datetime, str]] = []

    for metadata in remote:
        remote_id = str(metadata.get("id") or "").strip()
        if not remote_id:
            continue
        added = _parse_added(metadata.get("added"))
        if added is not None and (newest_added is None or added > newest_added):
            newest_added = added
            newest_id = remote_id
        if remote_id in known_ids:
            continue
        outcome = ingest_paperless_document(remote_id)
        if outcome.error:
            result.errors.append(f"Paperless #{remote_id}: {outcome.error}")
            if added is not None:
                failed.append((added, remote_id))
        elif outcome.duplicate:
            result.duplicates += 1
        else:
            result.ingested += 1

    if failed:
        # Retry from the oldest failure (minus overlap) so newer documents are
        # not hidden while the bad one keeps failing.
        oldest_added, oldest_id = min(failed, key=lambda item: item[0])
        _save_watermark(state, oldest_added - overlap, oldest_id)
    elif newest_added is not None and (state.last_added is None or newest_added > state.last_added):
        _save_watermark(state, newest_added, newest_id)
    state.refresh_from_db(fields=["last_added"])
    result.watermark = state.last_added
    return result
