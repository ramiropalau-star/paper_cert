# Design

## Context

`sync_paperless_documents` calls `store.list_documents()`, which paginates the whole `/api/documents/` collection every run. `sync_classification_tags` calls `document_tag_names` (one document GET plus one tags GET), then `remove_tag` and `add_tag` per change; each does its own tag lookup, document GET, and PATCH. `document_thumbnail` fetches from Paperless on every request and raises 404 on failure.

`Document` stores `paperless_document_id`, `updated_at`, and the certificate relation. The sync command is `documents/management/commands/sync_paperless.py`; the watcher calls the service on an interval.

## Goals / Non-Goals

**Goals:**

- Stop listing the whole archive on every sync.
- One PATCH per document for tag changes.
- Serve unchanged thumbnails without Paperless.
- Keep sync idempotent and observable.
- Provide a full reconcile for recovery.

**Non-Goals:**

- Replacing Paperless webhooks or changing ingestion semantics.
- Real-time thumbnail invalidation from Paperless events (version key + TTL is enough).
- A distributed task queue.

## Decisions

### 1. Persist a singleton watermark

Add `PaperlessSyncState` with `last_added` (datetime, nullable) and `last_paperless_id` (string, blank) plus `updated_at`. Use `get_or_create(pk=1)`; no user-facing admin. A migration creates the table. The first run has `last_added=None` and is full.

`DocumentStore.list_documents(since=None)` passes Paperless's `added__gte` filter when `since` is set. If the running Paperless rejects that filter, the implementation falls back to the existing full listing and logs `sync_filter_unsupported`; the next release can switch to ordered pagination. The design does not pretend the filter exists without verification, so task 1 includes a live check.

Alternatives: store the watermark in a settings row / JSON file (no migration, but weaker concurrency and no audit). Rejected.

### 2. Use an overlap window and advance to the oldest failure

`sync_paperless_documents(full=False)` computes `since = last_added - overlap` (default 10 minutes, `APP_SYNC_OVERLAP_SECONDS`). It lists, skips known ids, ingests new ones, and records the maximum `added` seen. On success with no errors, it stores that maximum. On ingest errors, it stores the oldest failed document's `added - overlap` (or leaves the watermark unchanged when no timestamp is available), so failures are retried without hiding newer documents. A listing failure leaves the watermark unchanged.

`full=True` ignores the watermark, lists the whole archive, and on success stores the newest timestamp. The management command exposes `--full`; the watcher keeps the default.

Alternatives: never advance on any error (a permanently bad document blocks all progress). Rejected.

### 3. Resolve tags once and PATCH once per document

Add `DocumentStore.tag_catalog()` that paginates `/api/tags/` once per store/sync and returns a name→id map. Add `ensure_tags(names)` that creates missing tags and updates the catalog. Add `set_tags(document_id, names)`:

1. fetch the document's current tag ids once;
2. map current ids to names through the catalog;
3. keep unmanaged tags, replace managed tags with `names`;
4. PATCH once with the final id list.

`sync_classification_tags` builds the desired managed set, calls `set_tags`, and no longer loops over `add_tag`/`remove_tag`. Other callers can still use the single-tag methods.

Alternatives: use Paperless bulk-edit endpoints (not needed for one document at a time). Rejected.

### 4. Cache thumbnails with a versioned key

Configure a filesystem cache in `settings.py` (`CACHES` default `FileBasedCache` under `var/cache`, overridable by `APP_CACHE_DIR`). The thumbnail view uses key `thumbnail:{paperless_id}:{updated_at.timestamp()}` and stores `{"bytes": ..., "content_type": ...}` for 24 hours. A hit returns immediately; a miss fetches from Paperless, stores, and returns. A version change produces a new key, so stale entries are not served. On Paperless failure, return a static placeholder SVG with HTTP 200 so the gallery remains usable; never raise 404 for a transient thumbnail failure.

Alternatives: `LocMemCache` (not shared across workers), browser-only caching (still calls Paperless on first load per user). Rejected.

### 5. Preserve sync reporting

`SyncResult` keeps `scanned`, `ingested`, `duplicates`, and `errors`; add `full` and `watermark` for logs/commands. Repeated syncs skip known ids, so they create no duplicates. Errors include the Paperless id, as today.

## Risks / Trade-offs

- `added__gte` filter support varies by Paperless version → verify live and fall back to full listing with a warning.
- A watermark gap can skip documents → overlap window plus `--full` recovery.
- Advancing to the oldest failure can reprocess documents → idempotent ingestion and known-id skips make that safe.
- Filesystem cache is local to one host → acceptable for the single-host Compose deployment; use Redis later if scaled.
- Stale thumbnails until the local `updated_at` changes → 24-hour TTL bounds it.

## Migration Plan

1. Add the model and migration; run `migrate`.
2. Add cache settings and `APP_SYNC_OVERLAP_SECONDS` to `.env.example`; restart.
3. Run `sync_paperless --full` once after deploy to establish the baseline, then let the watcher use incremental mode.
4. Rollback: the new table and cache are additive; the previous code ignores them. Revert the image and keep the table.

## Open Questions

None that block the spec. The exact Paperless filter name is verified in task 1; the fallback keeps the behavior correct if it differs.
