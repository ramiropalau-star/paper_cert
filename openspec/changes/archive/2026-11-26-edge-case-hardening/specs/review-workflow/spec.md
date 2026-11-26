# Spec Delta

## ADDED Requirements

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
