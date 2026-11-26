# Spec Delta

## ADDED Requirements

### Requirement: Unverifiable evidence retains the value flagged as unverified

When a literal field's evidence quote cannot be verified verbatim on the cited
page, the system SHALL keep the extracted value, mark that field as unverified,
and continue the extraction instead of rejecting the whole result. Fields whose
evidence verifies normally SHALL remain verified. The unverified mark SHALL be
persisted per field and cleared when a reviewer edits or explicitly confirms
the field.

#### Scenario: Single bad quote no longer fails extraction

- **WHEN** the model returns a complete extraction where one literal field's
  evidence quote does not appear on its cited page
- **THEN** the extraction completes and stores all returned values
- **AND** only the offending field is marked unverified
- **AND** the document proceeds to classification and review

#### Scenario: Unverified mark survives to review

- **WHEN** a certificate has fields marked unverified
- **THEN** the review UI shows which fields are unverified
- **AND** editing or confirming a field clears its unverified mark

#### Scenario: Verified fields are unaffected

- **WHEN** every literal field's evidence quote verifies on its cited page
- **THEN** no field is marked unverified

### Requirement: Deterministic fallback fills empty score and dates

When the model returns an empty score or no date candidates, the system SHALL
attempt a deterministic label/regex pass over the stored page text to fill them,
using the same fallback pattern as the student-name recovery. Fallback-derived
values SHALL be marked unverified.

#### Scenario: Score recovered from page text

- **WHEN** the model omits the score but the page text contains a recognizable
  score pattern (e.g. `80 /100`, `Score: 89`)
- **THEN** the score field is populated from the matched text and marked
  unverified

#### Scenario: Issue date recovered from page text

- **WHEN** the model returns no usable date candidates but the page text contains
  a recognizable date near a date label
- **THEN** the issue date is populated from the matched text and marked
  unverified

#### Scenario: Nothing found stays empty

- **WHEN** neither the model nor the deterministic pass finds a score or date
- **THEN** the field remains empty and no unverified mark is added

### Requirement: Focused second pass recovers missing critical fields

When the primary extraction leaves critical fields (score or dates) empty after
fallbacks, the system SHALL issue at most one bounded follow-up extraction
request scoped to the missing fields, requiring verbatim quotes. The second pass
SHALL NOT run when the primary extraction already produced verified values for
those fields, and its results SHALL pass the same evidence validation.

#### Scenario: Second pass runs only on gaps

- **WHEN** the primary extraction plus fallbacks still lacks a score or issue
  date
- **THEN** exactly one follow-up request asks only for the missing fields
- **AND** returned values are validated against page evidence before storing

#### Scenario: Happy path skips the second pass

- **WHEN** the primary extraction already yields verified score and dates
- **THEN** no follow-up request is made

### Requirement: Reviewers can re-extract a document directly

The system SHALL provide a reviewer-facing action that re-runs extraction for a
single document without depending on the external ingestion webhook. The action
SHALL be idempotent, SHALL preserve manually entered fields, and SHALL record a
review event describing the re-extraction.

#### Scenario: Manual re-extract bypasses the webhook

- **WHEN** a reviewer triggers re-extraction on a document whose pipeline is
  stuck or whose extraction missed fields
- **THEN** extraction runs against the stored page texts directly
- **AND** the document returns to the appropriate processing state on success

#### Scenario: Manual fields are preserved

- **WHEN** re-extraction runs on a certificate with fields in `manual_fields`
- **THEN** those fields are not overwritten by the new extraction
