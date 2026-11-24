"""Reconcile Django documents with everything stored in Paperless.

The Paperless webhook only fires for documents consumed after it was
configured. This sync closes the gap: it lists every Paperless document and
ingests the ones missing from Django through the normal dedup pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from documents.models import Document
from documents.services.paperless import DocumentStore, build_document_store
from documents.services.paperless_ingest import ingest_paperless_document

logger = logging.getLogger("documents.sync")


@dataclass
class SyncResult:
    scanned: int = 0
    ingested: int = 0
    duplicates: int = 0
    errors: list[str] = field(default_factory=list)


def sync_paperless_documents(*, store: DocumentStore | None = None) -> SyncResult:
    result = SyncResult()
    owns_store = store is None
    store = store or build_document_store()
    try:
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

    for metadata in remote:
        remote_id = str(metadata.get("id") or "").strip()
        if not remote_id:
            continue
        if remote_id in known_ids:
            continue
        outcome = ingest_paperless_document(remote_id)
        if outcome.error:
            result.errors.append(f"Paperless #{remote_id}: {outcome.error}")
        elif outcome.duplicate:
            result.duplicates += 1
        else:
            result.ingested += 1
    return result
