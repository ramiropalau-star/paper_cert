# Spec Delta

## ADDED Requirements

### Requirement: Veracity score combines independent evidence

The system SHALL compute a veracity score between 0 and 1 for each certificate that combines independent evidence: source-verification status, format/profile match, label-value consistency, and extraction evidence coverage. The score SHALL store its component values and weights version, SHALL NOT be treated as proof of authenticity, and SHALL NOT auto-approve or bypass review.

#### Scenario: Verified source raises the score

- **WHEN** a certificate is `verified_at_source` and its format and evidence are consistent
- **THEN** its veracity score is high and its source-verification component is recorded as verified

#### Scenario: High format without source verification is limited

- **WHEN** a certificate has a high format score but verification status is `none` or `self_reported`
- **THEN** its veracity score remains below the verified range
- **AND** the source-verification component shows unverified

#### Scenario: Missing evidence lowers the score

- **WHEN** extracted fields lack supporting evidence or label consistency
- **THEN** those components reduce the veracity score
- **AND** the breakdown shows which component is weak

#### Scenario: Score never auto-approves

- **WHEN** a certificate has a high veracity score
- **THEN** it still requires the normal review decision
- **AND** no approval or delivery action is taken automatically

### Requirement: Source verification and veracity are distinct

Source verification and veracity SHALL be represented separately. A certificate can be `verified_at_source` or `manually_confirmed` with a high veracity score, or have a high format score with `none` or `self_reported` verification and a lower veracity score; the UI SHALL show both signals.

#### Scenario: Verified source is shown separately

- **WHEN** a certificate is verified at source
- **THEN** the source-verification badge states that status
- **AND** the veracity score is shown as a separate value

#### Scenario: Format-only result is not presented as verified

- **WHEN** a certificate has a high format score but no source verification
- **THEN** the UI does not label it as verified
- **AND** the veracity breakdown identifies the missing source verification

### Requirement: Per-issuer verifier configuration is data-driven

Verifier configuration SHALL be stored as per-issuer data, including host, code pattern, URL template, success criteria, and optional source-document parser. Authorized reviewers SHALL manage it without code changes; viewers SHALL NOT. Invalid configuration SHALL be rejected.

#### Scenario: New issuer is configured without code changes

- **WHEN** an authorized reviewer adds a verifier configuration for a new issuer
- **THEN** certificates from that issuer can use the configured verification pattern
- **AND** no deployment or code change is required

#### Scenario: Invalid configuration is rejected

- **WHEN** a configuration has an invalid URL template or code pattern
- **THEN** the system rejects it with a clear error
- **AND** existing verification behavior is unchanged

#### Scenario: Viewer cannot edit verifier configuration

- **WHEN** a viewer attempts to change a verifier configuration
- **THEN** the request is rejected

### Requirement: Source-document field comparison

When a verifier returns a source document, the system SHALL compare its fields with the extracted certificate, record matches and mismatches, and route material mismatches to review. It SHALL NOT mark a certificate verified or approved solely from a comparison.

#### Scenario: Source fields match

- **WHEN** the source document returns the same student, issuer, level, and date as the certificate
- **THEN** the comparison records matches for those fields
- **AND** the result is stored as verification evidence

#### Scenario: Source fields mismatch

- **WHEN** the source document returns a different student or score
- **THEN** the comparison records the mismatch
- **AND** the certificate is routed to review

#### Scenario: Source document is unavailable

- **WHEN** the verifier confirms the code but returns no source document
- **THEN** verification can still succeed
- **AND** the comparison is marked unavailable rather than failed

### Requirement: Verified samples are eligible for learning

Verified samples SHALL be eligible as higher-weight learning input for format profiles and aliases. Rejected or unapproved documents SHALL NOT contribute, and verification SHALL NOT bypass corroboration or conflict rules.

#### Scenario: Verified sample is eligible

- **WHEN** a certificate is `verified_at_source` or `manually_confirmed`
- **THEN** its sample is eligible for profile and alias learning with higher weight

#### Scenario: Unapproved sample is excluded

- **WHEN** a document is rejected or never approved
- **THEN** it does not contribute to learning even if it has verification artifacts
