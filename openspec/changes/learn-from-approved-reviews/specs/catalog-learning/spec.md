# Spec Delta

## Purpose

Convert human-verified review decisions into durable catalog knowledge so that subsequently processed certificates from the same issuers resolve automatically, without code changes or manual catalog edits.

## ADDED Requirements

### Requirement: Approval teaches literal-to-catalog aliases
When a reviewer approves or validates a certificate whose literal values were resolved or manually assigned to catalog entries, the system SHALL record the printed literal as an alias of the resolved catalog entry when no alias already covers it, so future documents printing the same or equivalent text resolve without review.

#### Scenario: Approved variant becomes an alias
- **WHEN** a certificate is approved and its printed entity literal differs from the canonical entity name but was resolved to that entity
- **THEN** an alias linking the printed literal to the entity exists in the catalog
- **AND** a later certificate printing the same literal resolves to that entity automatically

#### Scenario: Learning is idempotent
- **WHEN** the same certificate is approved again or reprocessed and re-approved
- **THEN** no duplicate alias, entity, exam, or rule is created

#### Scenario: Manual assignment of unknown literal
- **WHEN** a reviewer assigns a catalog entity or exam to a certificate whose literal did not previously resolve
- **THEN** on approval the literal is registered as an alias of the assigned catalog entry

### Requirement: Approval creates missing catalog entries
When a reviewer supplies catalog values that do not exist for an unknown literal, the system SHALL create the minimal catalog entries needed (entity and/or exam scoped to the resolved entity and language) so the assignment is reusable.

#### Scenario: New issuer enters the catalog
- **WHEN** a reviewer approves a certificate for an issuer absent from the catalog and selects or creates its entity
- **THEN** the entity exists in the catalog and the printed literal resolves to it on subsequent documents

### Requirement: Approval derives equivalence and CEFR rules with attribution
When an approved certificate carries a manually corrected equivalence or CEFR level that no active rule produces, the system SHALL record a candidate rule tied to the approving actor and the source certificate, so the mapping is reusable and auditable.

#### Scenario: Manual equivalence becomes a rule
- **WHEN** a reviewer approves a certificate whose equivalence was set manually and no equivalence rule applies to its exam
- **THEN** an equivalence rule is recorded for that exam reflecting the approved value
- **AND** the rule references the approving actor and the source certificate

#### Scenario: CEFR correction becomes a conversion rule
- **WHEN** a reviewer approves a certificate whose CEFR level was corrected manually and no approved conversion rule produces it
- **THEN** a CEFR conversion rule candidate is recorded with the approving actor as approver and the certificate as reference

#### Scenario: Learned rules do not bypass approval requirements
- **WHEN** a learned CEFR rule is created
- **THEN** it satisfies the same approval-metadata requirements as any other active conversion rule
- **AND** its provenance identifies it as review-derived

### Requirement: Learning never overrides human catalog decisions
Catalog learning SHALL only add entries or aliases; it SHALL NOT modify, deactivate, or reassign existing catalog entries, aliases, equivalences, or rules.

#### Scenario: Conflicting alias already exists
- **WHEN** a literal to be learned already maps to a different catalog entry
- **THEN** the system does not create a conflicting alias
- **AND** the discrepancy is left for manual resolution

### Requirement: Rejected certificates do not teach
Certificates that are rejected, or that remain unapproved, SHALL NOT contribute aliases, catalog entries, equivalences, or format-profile anchors.

#### Scenario: Rejection leaves catalog untouched
- **WHEN** a certificate is rejected after manual review
- **THEN** no alias, catalog entry, equivalence, CEFR rule, or format anchor is created from it

#### Scenario: Pending certificate does not teach
- **WHEN** a certificate sits in pending review without approval or validation
- **THEN** catalog learning does not run for it
