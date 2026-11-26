# catalog-management Specification

## Purpose
In-app management of catalog master data: reviewers can browse an entity's
aliases, exams, and equivalences and onboard new certifying bodies without
Django admin, closing the gap that previously forced catalog changes through
admin or silent review edits.

## Requirements

### Requirement: Entity detail page

The catalog UI SHALL provide an entity detail page listing the entity's
canonical name, active flag, `date_order`, aliases, exams (with language and
equivalence counts), and a link to manage each exam's equivalences. The page
SHALL be readable by any authenticated user and writable by reviewers and
admins.

#### Scenario: Reviewer opens an entity
- **WHEN** a reviewer opens `/catalog/entities/<id>/`
- **THEN** the page shows the entity name, aliases, exams, and equivalence
  summary
- **AND** write controls are visible

#### Scenario: Viewer opens an entity
- **WHEN** a viewer opens the entity detail page
- **THEN** the same information is shown read-only
- **AND** no write controls are offered

### Requirement: Manage entity metadata and aliases

Reviewers SHALL be able to edit an entity's `date_order` and `is_active`
flag and add new aliases from the entity detail page. Alias additions SHALL
be idempotent: re-adding an existing normalized alias SHALL NOT create a
duplicate and SHALL NOT reassign it to another entity without an explicit
confirmation path.

#### Scenario: Add an alias variant
- **WHEN** a reviewer submits a new alias spelling for the entity
- **THEN** an `EntityAlias` is created pointing to that entity
- **AND** the alias list on the page reflects it

#### Scenario: Duplicate alias is harmless
- **WHEN** a reviewer submits an alias whose normalized form already exists
- **THEN** no duplicate row is created
- **AND** the existing assignment is preserved

### Requirement: Manage exams under an entity

Reviewers SHALL be able to create an exam under an entity (optionally
scoped to a language) and see its existing aliases and equivalences from the
entity detail page.

#### Scenario: Create exam for entity
- **WHEN** a reviewer submits a new exam name under an entity
- **THEN** an `Exam` row is created scoped to that entity
- **AND** it appears in the entity's exam list and in equivalence management

### Requirement: Manage equivalences per exam

Reviewers SHALL be able to add, update, and deactivate `Equivalence` rows
for an exam from the catalog UI, including score bands and the accredited
CEFR level. Inactive equivalences SHALL NOT apply during classification.

#### Scenario: Add equivalence to new exam
- **WHEN** a reviewer defines an accredited level (optionally score-banded)
  for an exam
- **THEN** an active `Equivalence` is created and visible in the exam's
  equivalence list
- **AND** subsequent classifications can resolve it

#### Scenario: Deactivate an equivalence
- **WHEN** a reviewer marks an equivalence inactive
- **THEN** it remains visible but flagged inactive
- **AND** classification stops applying it
