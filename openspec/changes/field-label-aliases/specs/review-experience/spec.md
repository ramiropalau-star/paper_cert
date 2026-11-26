# Spec Delta

## ADDED Requirements

### Requirement: Teach-alias action on unresolved fields

The review detail page SHALL offer a teach-alias action next to fields that
are empty or marked unverified. The action SHALL let the reviewer enter the
label exactly as printed on the document and SHALL offer an entity scope
option only when the document's entity is resolved. Submitting SHALL create
the alias and offer to reprocess the document.

#### Scenario: Reviewer teaches alias from review

- **WHEN** a reviewer opens teach-alias on an empty student name field,
  enters the printed label, and confirms
- **THEN** an active alias is created for that field and the reviewer is
  offered a reprocess action

#### Scenario: Scope option only when entity is known

- **WHEN** the document's entity is unresolved
- **THEN** the teach-alias form does not offer entity scoping and the alias
  is saved globally

### Requirement: Reprocess surfaces mapping outcome

After reprocessing triggered from teach-alias, the review detail SHALL show
which fields changed value, so the reviewer can validate that the taught
mapping worked before approving. If the field remains empty, the reviewer
SHALL be able to teach another alias or edit the field manually.

#### Scenario: Successful mapping is visible

- **WHEN** reprocessing fills the previously empty field via the taught
  alias
- **THEN** the detail page shows the new value and the change is recorded
  in the review history

#### Scenario: Failed mapping keeps manual path open

- **WHEN** reprocessing still leaves the field empty
- **THEN** the reviewer can teach another alias or enter the value manually
  without losing the document state
