# Spec Delta

## ADDED Requirements

### Requirement: Extraction incorporates configured field label aliases

When building the extraction instruction and running deterministic field
fallbacks, the system SHALL include the active field label aliases that
apply to the document: all global aliases for the field, plus aliases
scoped to the document's resolved entity when the document has already been
classified. Aliases SHALL be presented to the model as additional label
examples for their field and SHALL extend fallback label matching without
weakening verbatim-evidence validation.

#### Scenario: Global alias appears in the extraction instruction

- **WHEN** an active global alias exists for the student name field
- **THEN** the extraction instruction lists it as an additional label
  example for that field

#### Scenario: Entity-scoped alias applies after classification

- **WHEN** a document is reprocessed after classification and an active
  alias is scoped to its resolved entity
- **THEN** the extraction for that document includes the scoped alias

#### Scenario: Unclassified document uses global aliases only

- **WHEN** a document has no resolved entity yet (first extraction pass)
- **THEN** only global aliases are applied; entity-scoped aliases are not
  used

#### Scenario: Alias-derived values still require evidence

- **WHEN** a value is recovered through an alias
- **THEN** it carries evidence from the document text like any other
  extracted value, and unverifiable evidence still marks the field
  unverified rather than discarding the value
