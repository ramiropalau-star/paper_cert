# Proposal

## Why

The watcher lists every Paperless document every 60 seconds, tag synchronization performs several HTTP requests per tag, and the gallery fetches each thumbnail from Paperless on every page view. The result is unnecessary load that grows with the archive, slower review screens, and more chances to hit transient Paperless errors.

## What Changes

- **Incremental sync**: persist a sync watermark and request only documents added after it, with a small overlap window and a full-reconciliation command for recovery.
- **Batched tag updates**: resolve the tag catalog once per sync, compute the final tag set for a document, and send at most one PATCH per document instead of a request per tag.
- **Thumbnail cache**: cache thumbnails by Paperless document id and version, serve cache hits, and refresh on a miss or version change.
- **Stable sync reporting**: keep the existing scanned/ingested/duplicates/errors counts; advance the watermark only after a successful sync.
- **Tests and documentation**: cover watermark progress, full reconcile, tag request counts, cache hits/misses/invalidation, and the new operational settings.

## Capabilities

### New Capabilities

- `paperless-integration`: durable behavior for syncing Paperless documents incrementally, updating tags efficiently, and serving cached thumbnails without losing idempotency.

### Modified Capabilities

None.

## Impact

- **Services**: `documents/services/sync.py`, `documents/services/labels.py`, `documents/services/paperless.py`, thumbnail views in `documents/views.py`.
- **Data**: a singleton sync-state model and migration; cache directory or cache backend configuration.
- **Commands**: `sync_paperless` gains a full-reconcile option.
- **Risk**: a wrong watermark can skip documents; the overlap window and full reconcile bound that risk. A stale thumbnail cache can show an older preview until the version key or TTL changes.
