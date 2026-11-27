# field-label-mapping Specification

## Purpose
Configurable label aliases that teach the extraction pipeline which printed
labels on a certificate correspond to which structured fields, so reviewers
can extend field recognition without code changes.

## Requirements

### Requirement: Field label aliases are stored per field

The system SHALL store label aliases as data, each bound to exactly one
extraction field (e.g. student name, score, issue date), with the alias text
kept verbatim as printed on certificates, a source marker (`manual` or
`learned`), and an active flag. Aliases SHALL be normalized for matching
(case, accents, whitespace, typographic dashes/quotes) without altering the
stored literal.

#### Scenario: Reviewer teaches a new label

- **WHEN** a reviewer saves an alias "Nombre del aspirante" for the student
  name field
- **THEN** the alias is stored active with source `manual` and is available
  to subsequent extractions

#### Scenario: Duplicate alias is idempotent

- **WHEN** the same normalized alias is saved twice for the same field and
  scope
- **THEN** the system keeps a single record and reports the duplicate
  instead of creating a second entry

### Requirement: Aliases can be scoped globally or per entity

An alias SHALL apply globally to every document when it has no entity scope.
An alias MAY be scoped to a single catalog entity. A scoped alias SHALL apply
when the document's entity resolves to that entity or when issuer pre-detection
resolves that entity with sufficient confidence before extraction. Scoped
aliases SHALL take precedence over global aliases for the same field when both
could match.

#### Scenario: Global alias applies to any document

- **WHEN** an active global alias exists for a field
- **THEN** every extraction for that field considers the alias regardless of
  the document's entity

#### Scenario: Entity-scoped alias applies only to that entity

- **WHEN** an alias is scoped to entity Cambridge and a document's entity
  resolves to a different entity
- **THEN** the scoped alias is not used for that document's extraction

#### Scenario: Scoped alias wins over global for same field

- **WHEN** a global alias and an entity-scoped alias both exist for the same
  field and the document matches the scope
- **THEN** the entity-scoped alias is preferred for label matching on that
  document

#### Scenario: Pre-detected issuer uses scoped aliases before extraction

- **WHEN** issuer pre-detection resolves entity Cambridge with sufficient
  confidence before extraction
- **THEN** active aliases scoped to Cambridge are available to that extraction
- **AND** a scoped alias can recover a field before a certificate record exists

#### Scenario: Ambiguous pre-detection uses only global aliases

- **WHEN** issuer pre-detection cannot resolve an entity with sufficient
  confidence
- **THEN** only active global aliases are used for that extraction
- **AND** no entity-scoped alias is applied speculatively

### Requirement: Alias lifecycle is manageable by reviewers

Authorized reviewers SHALL be able to list, create, edit, deactivate, and
reactivate aliases. Viewers SHALL NOT be able to modify aliases. Every
creation, edit, and deactivation SHALL record the actor and timestamp.
Deactivated aliases SHALL NOT be used by extraction but SHALL remain visible
in the listing for auditability.

#### Scenario: Viewer cannot manage aliases

- **WHEN** a user with viewer role attempts to create or deactivate an alias
- **THEN** the request is rejected and no alias is modified

#### Scenario: Deactivated alias is ignored by extraction

- **WHEN** an alias is deactivated
- **THEN** subsequent extractions do not use it, and it still appears in the
  alias listing marked inactive

### Requirement: Extraction consumes active aliases

The extraction pipeline SHALL incorporate active aliases applicable to a
document when building the model instruction and when running deterministic
field fallbacks, so a newly taught label can recover a field that was
previously empty or unverified.

#### Scenario: Taught alias recovers an empty field on reprocess

- **WHEN** a reviewer teaches an alias for a field that was empty and
  reprocesses the document
- **THEN** the extraction considers the alias and, if the label is present
  in the document text, fills the field

#### Scenario: Alias does not fabricate data

- **WHEN** an alias is configured but the document does not contain the
  label or a plausible value near it
- **THEN** the field remains empty and no value is inferred

### Requirement: Learned aliases require corroboration and lifecycle

The system SHALL store learned aliases with a lifecycle state of candidate,
active, or rejected, plus support count, confidence, provenance, and scope.
A learned alias SHALL become active only after corroboration from multiple
approved certificates or explicit reviewer confirmation. Manual aliases SHALL
remain authoritative, rejected documents SHALL never teach, and conflicting
learned aliases SHALL NOT auto-activate.

#### Scenario: Single observation stays a candidate

- **WHEN** a label is observed once in an approved certificate
- **THEN** it is stored as a candidate and is not used by extraction

#### Scenario: Corroborated alias becomes active

- **WHEN** the same normalized label appears in enough approved certificates
  for the same field and scope
- **THEN** the learned alias becomes active for that scope

#### Scenario: Conflict does not auto-activate

- **WHEN** a learned candidate conflicts with an existing active alias for the
  same field and scope
- **THEN** it remains a candidate until a reviewer resolves it
- **AND** extraction keeps using the active alias

#### Scenario: Rejected document never teaches

- **WHEN** a document is rejected
- **THEN** its labels never create or support an alias

### Requirement: Reviewer corrections can propose alias candidates

When a reviewer corrects a field value or teaches a label, the system MAY
propose an alias candidate derived from that correction, scoped to the
certificate's issuer when known. The candidate SHALL NOT become active until
corroboration or explicit confirmation, and the proposal SHALL record its
provenance.

#### Scenario: Correction proposes a candidate

- **WHEN** a reviewer corrects a field and the printed label is identifiable
- **THEN** the system offers to save a candidate alias for that field and issuer
- **AND** the candidate is not used until confirmed or corroborated

#### Scenario: Reviewer rejects the proposal

- **WHEN** the reviewer dismisses the alias proposal
- **THEN** no alias is created and the correction is still saved

### Requirement: Alias provenance is visible to reviewers

The alias listing and review detail SHALL show each alias's source (manual or
learned), lifecycle state, support count, confidence, and scope. Authorized
reviewers SHALL be able to confirm, reject, deactivate, or reactivate aliases,
and every change SHALL record the actor and timestamp.

#### Scenario: Reviewer inspects a learned alias

- **WHEN** a reviewer opens the alias listing
- **THEN** each alias shows its source, state, support, confidence, and scope

#### Scenario: Reviewer rejects a candidate

- **WHEN** a reviewer rejects a candidate alias
- **THEN** its state becomes rejected and it is not used by extraction
- **AND** the decision is recorded with actor and timestamp
