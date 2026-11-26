# review-workflow Specification

## Purpose
Give operators a queue and detail view to verify, correct, approve, reject, or reprocess extracted certificates, while keeping an auditable history of every manual change.

## Requirements

### Requirement: Review queue with document states
The system SHALL provide a list of uploaded documents that distinguishes processed, pending-review, approved, rejected, and error states, and SHALL let users filter that list by state.

#### Scenario: Documents grouped by state
- **WHEN** a user opens the document list
- **THEN** each document shows its current review state
- **AND** the user can filter the list to processed, pending, approved, rejected, or error documents

#### Scenario: Error state visible
- **WHEN** processing fails for a document
- **THEN** the document appears in the error state with the failure reason available

### Requirement: Review detail with original document
The system SHALL show the original document alongside its extracted data, including an indicator of whether text came from embedded PDF text or OCR and warnings for fields that require review.

#### Scenario: Side-by-side review
- **WHEN** a reviewer opens a record pending review
- **THEN** the original document and the extracted fields are visible together

#### Scenario: Field warnings displayed
- **WHEN** the entity, level, or date requires review
- **THEN** the record displays a clear warning for each affected field

### Requirement: Manual correction of extracted data
The system SHALL let an authorized reviewer edit extracted fields and SHALL preserve the previously stored values in the change history.

#### Scenario: Reviewer edits a value
- **WHEN** a reviewer changes an extracted field and saves
- **THEN** the corrected value becomes the record's current value
- **AND** the previous value, reviewer, and timestamp are recorded in the history

#### Scenario: Required fields validated
- **WHEN** a reviewer attempts to approve a record that lacks a required field
- **THEN** the system prevents approval and identifies the missing field

### Requirement: Approve and reject records
The system SHALL let an authorized reviewer approve or reject a record, and SHALL record the decision with its actor and timestamp.

#### Scenario: Approval makes record reportable
- **WHEN** a reviewer approves a record
- **THEN** the record is eligible for inclusion in the main Excel report

#### Scenario: Rejection excludes record
- **WHEN** a reviewer rejects a record
- **THEN** the record is excluded from the main Excel report
- **AND** the rejection and its reason are recorded

### Requirement: Reprocess a document without duplicating it
The system SHALL let an authorized user reprocess a document, SHALL reuse the existing document record, and SHALL record the reprocessing event.

#### Scenario: Reprocessing updates the existing record
- **WHEN** a user requests reprocessing of a document
- **THEN** the pipeline runs again against the same document record
- **AND** no duplicate document or certificate record is created

#### Scenario: Previous values preserved in history
- **WHEN** reprocessing replaces extracted values
- **THEN** the values replaced by the new run remain available in the history
- **AND** the record returns to pending review

### Requirement: Audit history of changes and reprocessing
The system SHALL maintain a history of manual edits and reprocessing events for each record.

#### Scenario: History entry content
- **WHEN** a manual edit or reprocessing event occurs
- **THEN** the history records the event type, actor, timestamp, and affected previous and new values

#### Scenario: History is viewable
- **WHEN** a reviewer opens a record's history
- **THEN** the recorded changes and reprocessing events are displayed in chronological order

### Requirement: Search certificate data
The system SHALL let users search and filter records by student name, language, entity, level, and issue date.

#### Scenario: Search by student
- **WHEN** a user searches for part of a student name
- **THEN** matching certificate records are returned

#### Scenario: Combined filters
- **WHEN** a user combines language, entity, level, and issue-date filters
- **THEN** the results satisfy all selected filters

### Requirement: Route unrecognized documents to a manual-review label
The system SHALL apply a configurable document-store label, `Otros` by default, to documents that are not identified as language certificates, whose language or certifying entity cannot be resolved, or whose processing fails, and SHALL keep those documents in the manual-review queue. The system SHALL remove the label when the record is approved.

#### Scenario: Non-certificate document labeled for review
- **WHEN** extraction determines that an uploaded document is not a language certificate
- **THEN** the system applies the configured manual-review label to the original in the document store
- **AND** the document remains available in the review queue

#### Scenario: Unresolved language or entity labeled for review
- **WHEN** a certificate's language or certifying entity cannot be resolved against the catalog
- **THEN** the system applies the configured manual-review label
- **AND** the record is routed to manual identification

#### Scenario: Processing failure labeled for review
- **WHEN** text acquisition, extraction, or classification fails for a stored document
- **THEN** the system applies the configured manual-review label
- **AND** the document remains visible in the error state with its failure reason

#### Scenario: Approval clears the manual-review label
- **WHEN** a reviewer approves a record that carries the manual-review label
- **THEN** the system removes the label from the original document
- **AND** the approved record remains reportable

#### Scenario: Labeling failure does not block review
- **WHEN** the document store cannot apply or remove the label
- **THEN** the system records the failure and keeps the document in the review queue
- **AND** the processing result is not discarded

### Requirement: Document list filters tolerate invalid values

The document list SHALL ignore or safely handle filter parameters that cannot match a catalog foreign key, and SHALL NOT return a server error for them. Non-numeric values for identifier-based filters SHALL fall back to matching the literal text fields only.

#### Scenario: Non-numeric language filter
- **WHEN** a reviewer opens the document list with `?language=abc`
- **THEN** the system returns the list page successfully
- **AND** the filter matches documents whose language literal contains the value, without error

#### Scenario: Non-numeric entity filter
- **WHEN** a reviewer opens the document list with `?entity=abc`
- **THEN** the system returns the list page successfully
- **AND** the filter matches documents whose entity literal contains the value, without error

#### Scenario: Valid identifier still resolves the relation
- **WHEN** a reviewer filters by a numeric language or entity identifier
- **THEN** documents linked to that catalog entry are included in the results

### Requirement: Approval feeds catalog learning
Approving or validating a certificate SHALL trigger catalog learning as part of the same operation, and the review history SHALL record that learning occurred.

#### Scenario: Approval records learning outcome
- **WHEN** a reviewer approves a certificate
- **THEN** catalog learning runs for that certificate
- **AND** the review history records which catalog entries, aliases, or rules were learned (or that none were needed)

#### Scenario: Learning failure does not block approval
- **WHEN** catalog learning encounters an error
- **THEN** the approval still completes
- **AND** the learning failure is recorded for follow-up

#### Scenario: Validation also teaches
- **WHEN** a reviewer validates a manually corrected certificate without approving it
- **THEN** catalog learning applies the same rules as for approval

### Requirement: Inline catalog resolution from review

The review detail page SHALL offer a resolution action for certificates
whose `entity`, `exam`, or `language` literal is unresolved. The action
SHALL let the reviewer either select an existing catalog entry (searchable)
or create a new catalog entry prefilled with the printed literal, then
assign the resolved foreign key to the certificate.

#### Scenario: Resolve entity to existing entry
- **WHEN** a reviewer resolves an unresolved entity literal to an existing
  `Entity`
- **THEN** `certificate.entity` is set to that entity
- **AND** the printed literal is preserved in `entity_literal`
- **AND** a `ReviewEvent` records the change with the actor

#### Scenario: Create entity from literal
- **WHEN** a reviewer creates a new entity using the printed literal as its
  name
- **THEN** an `Entity` and an `EntityAlias` for the normalized literal are
  created
- **AND** `certificate.entity` points to the new entity
- **AND** the creation is idempotent when repeated

#### Scenario: Resolve exam within entity
- **WHEN** a reviewer resolves an exam literal
- **THEN** the exam is matched or created scoped to the certificate's
  resolved entity (and language when known)
- **AND** `certificate.exam` is updated accordingly

#### Scenario: Resolve language to existing entry
- **WHEN** a reviewer resolves a language literal
- **THEN** the literal is registered as a `LanguageAlias` of the chosen
  `Language` if absent
- **AND** `certificate.language` is set

### Requirement: Optional reclassification after resolution

After a successful resolution the reviewer SHALL be offered (or the action
SHALL perform) a reclassification of that document so dependent fields
(level, equivalence, format cohort, review reasons) are recomputed. Manual
field freezes SHALL still be respected.

#### Scenario: Reclassify after resolving entity
- **WHEN** resolution completes and reclassification is triggered
- **THEN** classification re-runs against the updated catalog links
- **AND** review reasons are recomputed (e.g., `unknown_entity` clears)

### Requirement: Resolution respects roles and audit

Catalog resolution SHALL require the reviewer role (or admin); viewers
SHALL NOT be able to resolve. Every resolution SHALL write an audit event
identifying the actor, the field resolved, and the before/after catalog
references.

#### Scenario: Viewer cannot resolve
- **WHEN** a viewer attempts the resolution action
- **THEN** the request is rejected and no catalog or certificate data
  changes
