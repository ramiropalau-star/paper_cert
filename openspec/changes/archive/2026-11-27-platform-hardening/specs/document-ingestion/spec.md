# Spec Delta

## ADDED Requirements

### Requirement: Watched-folder intake waits for files to settle

The system SHALL NOT read or move a file dropped into the watched folder until its size and modification time have remained unchanged for a configurable settle window. A file that is still being written SHALL remain in place and be reconsidered on a later scan.

#### Scenario: Partially written file is left alone

- **WHEN** a file in the watched folder changes size or modification time within the settle window
- **THEN** the system does not read, validate, or move it
- **AND** a later scan processes it after it settles

#### Scenario: Settled file is processed normally

- **WHEN** a file's size and modification time have been unchanged for the settle window
- **THEN** the system reads and processes it through the normal intake pipeline

#### Scenario: Settle window is configurable

- **WHEN** an operator changes the configured settle window
- **THEN** the watched-folder scan uses the new value without code changes

### Requirement: Concurrent duplicate uploads converge on one record

The system SHALL handle two intake paths that submit the same content concurrently by returning the already-created document. A uniqueness collision SHALL NOT surface as an unhandled error.

#### Scenario: Concurrent duplicate upload

- **WHEN** two intake paths submit the same file content at the same time
- **THEN** exactly one document record is created
- **AND** the other path reports the existing document as a duplicate

## MODIFIED Requirements

### Requirement: Store the original document

The system SHALL store every accepted original file in the configured document manager and SHALL keep a persistent identifier or link from the certificate record to that original. A storage failure SHALL remain retryable without deleting the document record.

#### Scenario: Original preserved and linked

- **WHEN** a document is accepted
- **THEN** the original file is stored in Paperless-ngx or the configured document store
- **AND** the certificate record retains an identifier or link that resolves to the original

#### Scenario: Document storage failure is explicit

- **WHEN** the configured document manager is unavailable during intake
- **THEN** the upload is reported as failed with a retryable error
- **AND** the system does not present the document as successfully processed

#### Scenario: Retry after storage failure

- **WHEN** the same content is uploaded again after a storage failure left the document in `error` with no document-store identifier
- **THEN** the system attempts storage again
- **AND** on success the existing document record moves out of `error` and enters the normal pipeline
