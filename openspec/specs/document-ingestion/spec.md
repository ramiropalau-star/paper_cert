# document-ingestion Specification

## Purpose
Accept language-certificate files, reject unsafe or unsupported input, prevent duplicate processing, and keep every record traceable to its original document throughout its lifecycle.

## Requirements

### Requirement: Accept PDF and image uploads
The system SHALL accept PDF documents and image files in JPG, JPEG, PNG, and TIFF formats through the web application.

#### Scenario: PDF upload accepted
- **WHEN** an authenticated user uploads a valid PDF file within the configured size limit
- **THEN** the system accepts the file and starts the processing pipeline for it

#### Scenario: Image upload accepted
- **WHEN** an authenticated user uploads a valid JPG, JPEG, PNG, or TIFF image within the configured size limit
- **THEN** the system accepts the file and starts the processing pipeline for it

#### Scenario: Unsupported file type rejected
- **WHEN** a user uploads a file whose type is not PDF, JPG, JPEG, PNG, or TIFF
- **THEN** the system rejects the upload with a clear error message
- **AND** no document record or processing job is created

#### Scenario: Oversized file rejected
- **WHEN** a user uploads a file larger than the configured maximum size
- **THEN** the system rejects the upload with a clear error message
- **AND** no document record or processing job is created

### Requirement: Validate files before processing
The system SHALL verify that each uploaded file is readable and structurally valid before any text extraction or AI processing begins.

#### Scenario: Corrupt or unreadable file rejected
- **WHEN** a user uploads a file that cannot be opened as its declared format
- **THEN** the system rejects the file and reports why it cannot be processed
- **AND** the file is not sent to OCR, AI extraction, or the document manager as a processed record

#### Scenario: Validation error is visible
- **WHEN** validation fails for an upload
- **THEN** the user can see the failed attempt and its reason in the document list

### Requirement: Detect duplicate documents by fingerprint
The system SHALL compute a content fingerprint of every uploaded file and SHALL reject or merge a new upload whose fingerprint matches an already stored document.

#### Scenario: Identical file uploaded twice
- **WHEN** a user uploads a file whose fingerprint matches an existing document
- **THEN** the system identifies the existing document instead of creating a second document record
- **AND** the user is informed that the file was already processed

#### Scenario: Duplicate detection survives reprocessing
- **WHEN** an existing document is reprocessed through any pipeline path
- **THEN** the system updates the existing record and does not create an additional document or certificate row

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

### Requirement: Delete a document and its associated data
The system SHALL let an authorized user delete a document together with its extracted data, review history, and generated associations.

#### Scenario: Authorized deletion removes data
- **WHEN** an authorized user confirms deletion of a document
- **THEN** the system removes the certificate record, its extracted fields, and its review history
- **AND** the original is removed from the document store or marked as deleted according to the store's policy

#### Scenario: Unauthorized deletion refused
- **WHEN** a user without deletion permission requests deletion
- **THEN** the system refuses the action and leaves the document and its data unchanged

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
