# Spec Delta

## ADDED Requirements

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
