# Spec Delta

## ADDED Requirements

### Requirement: Format-aware confidence scoring
Classification SHALL incorporate the document's format score into the certificate's stored confidence and review-reason computation, in addition to extraction-reported confidence.

#### Scenario: Low format score lowers confidence
- **WHEN** a certificate's format score is low
- **THEN** the stored confidence reflects the weaker format evidence
- **AND** the `low_confidence` review reason applies when the blended value falls below the configured threshold

#### Scenario: Missing format evidence is neutral
- **WHEN** no format profile applies to the document's entity or cohort
- **THEN** the format score does not penalize the certificate's confidence
