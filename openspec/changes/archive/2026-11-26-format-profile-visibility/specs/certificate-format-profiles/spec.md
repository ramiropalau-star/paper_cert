# Spec Delta

## ADDED Requirements

### Requirement: Format score visible in the document list

The document list SHALL display each certificate's format score as a
visually distinct badge together with its cohort label when available,
and SHALL apply a warning visual treatment (color) to rows whose format
score is below the configured confidence threshold or whose format score
is absent while a profile exists for the entity. Documents without any
applicable profile SHALL be visually neutral, not flagged as errors.

#### Scenario: Low format score row is flagged

- **WHEN** a certificate's format score is below the confidence threshold
- **THEN** its row in the document list shows a warning-colored badge so
  it attracts reviewer attention

#### Scenario: No applicable profile is neutral

- **WHEN** a certificate's entity has no learned profile with enough
  samples
- **THEN** the format badge is absent or neutral and the row is not
  flagged

#### Scenario: Score and cohort shown

- **WHEN** a certificate has a computed format score
- **THEN** the list shows the score and the cohort label (entity, year,
  exam when segmented)

### Requirement: Filter documents by format confidence

The document list SHALL offer a filter that restricts results to
documents whose format score is below the confidence threshold
("doubtful format"), composing with the existing filters.

#### Scenario: Doubtful-format filter

- **WHEN** a reviewer selects the doubtful-format filter
- **THEN** only documents with a format score below the threshold (or an
  applicable profile that scored them low) are listed

### Requirement: Format profiles are manageable

Authorized reviewers SHALL be able to list format profiles (entity,
year, exam cohort, sample count, anchors), deactivate or reactivate a
profile, and trigger rescoring of documents affected by the change.
Deactivation SHALL exclude the profile from scoring without deleting it,
and the action SHALL be recorded for audit. Only reviewers or admins
SHALL manage profiles.

#### Scenario: Reviewer deactivates a wrong profile

- **WHEN** a reviewer deactivates a profile learned from bad data
- **THEN** subsequent format scoring ignores that profile, documents
  keep their stored scores until rescored, and the deactivation is
  recorded with actor and timestamp

#### Scenario: Viewer cannot manage profiles

- **WHEN** a viewer attempts to deactivate a profile
- **THEN** the request is rejected

#### Scenario: Rescore after reactivation

- **WHEN** a reviewer reactivates a profile and requests rescoring
- **THEN** affected certificates' format scores are recomputed against
  the current active profiles
