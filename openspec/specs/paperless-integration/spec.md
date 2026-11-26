# paperless-integration Specification

## Purpose
Defines how the application synchronizes Paperless documents, updates tags, and serves thumbnails without repeating work that has not changed.

## Requirements

### Requirement: Sync fetches only new documents after the watermark

The system SHALL persist a Paperless sync watermark and request only documents added after that watermark, with a configurable overlap window to avoid boundary loss. When no watermark exists, the first sync SHALL perform a full scan.

#### Scenario: First sync is full
- **WHEN** the application has no stored watermark
- **THEN** the sync lists all Paperless documents
- **AND** it stores the newest watermark after a successful run

#### Scenario: Later sync is incremental
- **WHEN** a watermark exists
- **THEN** the sync requests only documents added at or after the watermark minus the overlap window
- **AND** it does not list the whole archive

#### Scenario: Overlap does not duplicate
- **WHEN** a document appears in the overlap window more than once
- **THEN** the existing local document is reused
- **AND** no duplicate document is created

### Requirement: A full reconciliation remains available

The system SHALL provide an explicit full-reconciliation path that ignores the watermark and compares the whole Paperless archive with local documents. A full reconciliation SHALL be usable from the sync command and from the recovery workflow.

#### Scenario: Operator requests a full reconcile
- **WHEN** the sync command runs with the full-reconcile option
- **THEN** it lists the whole archive regardless of the watermark
- **AND** it reports scanned, ingested, duplicate, and error counts

#### Scenario: Full reconcile repairs a missed document
- **WHEN** a Paperless document is missing locally because of a previous watermark gap
- **THEN** the full reconcile ingests it through the normal pipeline

### Requirement: The watermark advances only after success

The system SHALL advance the watermark only after a sync completes without a listing failure. A failed or partial listing SHALL leave the previous watermark unchanged so the next run retries the same range.

#### Scenario: Listing failure preserves the watermark
- **WHEN** the Paperless listing fails
- **THEN** the stored watermark does not change
- **AND** the next sync retries from the same point

#### Scenario: Successful sync advances the watermark
- **WHEN** the listing and ingestion complete
- **THEN** the watermark advances to the newest processed document
- **AND** the sync reports its counts

### Requirement: Tag updates are batched per document

The system SHALL resolve tag identifiers once per sync and update a document's tags with at most one PATCH per document. It SHALL NOT perform a separate tag lookup and PATCH for every tag added or removed.

#### Scenario: Adding and removing tags uses one PATCH
- **WHEN** a certificate classification adds two tags and removes one
- **THEN** the document receives a single PATCH with the final tag list

#### Scenario: Tag catalog is reused
- **WHEN** multiple documents are updated in one sync
- **THEN** tag identifiers are resolved once and reused

### Requirement: Thumbnails are cached by document version

The system SHALL cache Paperless thumbnails by document identifier and version. A cache hit SHALL serve the stored thumbnail without calling Paperless. A cache miss or version change SHALL fetch and store a fresh thumbnail. A Paperless failure SHALL fall back to a clear placeholder or the previous cached image without breaking the page.

#### Scenario: Cache hit avoids Paperless
- **WHEN** a thumbnail is requested for an unchanged document
- **THEN** the stored thumbnail is served
- **AND** no Paperless thumbnail request is made

#### Scenario: Version change refreshes the cache
- **WHEN** the document version changes
- **THEN** the next request fetches a fresh thumbnail
- **AND** replaces the cached entry

#### Scenario: Paperless failure degrades gracefully
- **WHEN** the thumbnail fetch fails
- **THEN** the page still renders with a placeholder or the previous cached image

### Requirement: Sync remains idempotent and observable

The sync SHALL remain idempotent and SHALL report scanned, ingested, duplicate, and error counts. Repeated syncs of unchanged documents SHALL NOT create duplicate documents, certificates, or tags.

#### Scenario: Repeated sync is idempotent
- **WHEN** the sync runs twice with no new Paperless documents
- **THEN** the second run creates no duplicates
- **AND** it reports zero ingested

#### Scenario: Errors remain visible
- **WHEN** a document cannot be ingested
- **THEN** the sync reports the error with the Paperless identifier
- **AND** the watermark logic does not hide the failed document forever
