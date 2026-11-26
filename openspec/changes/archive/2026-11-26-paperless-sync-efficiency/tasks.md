# Tasks

## 1. Sync watermark and incremental listing

- [x] 1.1 Add `PaperlessSyncState` and its migration; verify the singleton is created and updated by tests.
- [x] 1.2 Extend `DocumentStore.list_documents(since=...)` with the Paperless `added__gte` filter and verify the filter against the running API; if it is unsupported, implement the ordered-pagination fallback and record the result.
- [x] 1.3 Implement the overlap window and incremental path in `sync_paperless_documents`; verify the first run is full, the second only requests the window, and repeated documents do not duplicate.

## 2. Full reconciliation and watermark failure semantics

- [x] 2.1 Add the `--full` option to `sync_paperless`; verify it lists the whole archive and repairs a missing local document.
- [x] 2.2 Advance the watermark only on a successful listing, and to the oldest failure minus the overlap when ingestion errors exist; verify with listing-failure and ingest-failure tests.

## 3. Batched tag updates

- [x] 3.1 Add `tag_catalog`, `ensure_tags`, and `set_tags` to `DocumentStore`; verify current tags are fetched once and the final list is PATCHed once.
- [x] 3.2 Rewrite `sync_classification_tags` to use `set_tags`; verify adding and removing tags in one sync produces one PATCH and leaves unmanaged tags untouched.

## 4. Thumbnail cache

- [x] 4.1 Configure the cache backend and add the versioned thumbnail cache in `document_thumbnail`; verify a cache hit makes no Paperless call and a version change fetches a fresh image.
- [x] 4.2 Add the placeholder response for Paperless thumbnail failures; verify the gallery remains usable and no 404 is raised for a transient failure.

## 5. Documentation and integration

- [x] 5.1 Document the watermark, overlap, full reconcile, cache directory, and thumbnail TTL in `docs/operations.md`; verify the documented settings match `.env.example`.
- [x] 5.2 Run the sync, tag, thumbnail, and command tests plus the full suite; record the observed request counts and results.
- [x] 5.3 Run `openspec validate paperless-sync-efficiency --strict` and fix any artifact issues.

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Verify the archived `paperless-integration` spec and the resulting capability baseline.
