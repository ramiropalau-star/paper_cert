# Spec Delta

## Purpose

Configurable label aliases that teach the extraction pipeline which printed
labels on a certificate correspond to which structured fields, so reviewers
can extend field recognition without code changes.

## ADDED Requirements

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
An alias MAY be scoped to a single catalog entity, in which case it SHALL
apply only to documents whose extracted entity resolves to that entity.
Scoped aliases SHALL take precedence over global aliases for the same field
when both could match.

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
