# certificate-source-verification Specification

## Purpose
Capture issuer verification artifacts (codes, URLs, QR payloads) printed on
certificates and track whether each certificate was validated against its
issuing source, automatically where a verifiable pattern exists or
manually by an authorized reviewer.

## Requirements

### Requirement: Verification artifacts are extracted and stored

The system SHALL extract, when present on the document, the issuer
verification code and verification URL (e.g. "Cod. Verificació",
"Verification Number", "CSV", "URL Verif", "verifiers" links), store them
on the certificate, and keep them visible in review. Extraction SHALL use
deterministic label-anchored patterns first and SHALL NOT fabricate codes
that are not present.

#### Scenario: CSV code and URL captured

- **WHEN** the document prints "Autenticidad verificable mediante CSV
  9613SQ59-... en https://www.tramita.gva.es/..."
- **THEN** the certificate stores the code and URL and review displays them

#### Scenario: Verification number captured

- **WHEN** the document prints a "Verification Number" with its value
- **THEN** the value is stored as the verification code

#### Scenario: No verification data present

- **WHEN** the document contains no recognizable verification code or URL
- **THEN** verification fields stay empty and status is `none`

### Requirement: Verification status lifecycle

Each certificate SHALL carry a verification status: `none`,
`self_reported` (artifacts found on the document), `verified_at_source`
(automated check passed), or `manually_confirmed` (reviewer confirmed
against the source). Status SHALL be visible in review and filterable in
the document list. Only `verified_at_source` and `manually_confirmed`
SHALL count as verified.

#### Scenario: Artifacts found set self_reported

- **WHEN** extraction finds a verification code or URL
- **THEN** status becomes `self_reported`

#### Scenario: Verified statuses are distinguishable

- **WHEN** one certificate was verified automatically and another was
  confirmed manually by a reviewer
- **THEN** review shows different badges/labels for each, including who
  confirmed and when for manual confirmation

### Requirement: Automated verification where a pattern exists

The system SHALL attempt automated source verification only for issuers
whose verification endpoint follows a known programmatic pattern (CSV-style
GET verification). The attempt SHALL record the outcome (success/failure/
unreachable) and SHALL NOT mark a certificate verified when the source
cannot be reached or does not confirm the code. Issuers without a known
pattern SHALL NOT be auto-verified.

#### Scenario: CSV code verifies against source

- **WHEN** a certificate has a CSV-style code and the source endpoint
  confirms it
- **THEN** status becomes `verified_at_source` with timestamp and evidence

#### Scenario: Source unreachable does not verify

- **WHEN** the verification endpoint times out or errors
- **THEN** status remains `self_reported` and the failure is recorded

#### Scenario: Portal-only issuer is not auto-verified

- **WHEN** the issuer only offers a web form (no known programmatic
  pattern)
- **THEN** no automated attempt is made and status stays `self_reported`

### Requirement: Reviewer manual confirmation

Authorized reviewers SHALL be able to mark a certificate as verified at
source after checking the issuer's portal themselves. The action SHALL
record the actor and timestamp, require reviewer role, and SHALL be
reversible (unconfirm) with the history preserved.

#### Scenario: Reviewer confirms portal verification

- **WHEN** a reviewer opens the verification URL, confirms the code on the
  issuer site, and clicks "verified at source"
- **THEN** status becomes `manually_confirmed` with actor and timestamp

#### Scenario: Viewer cannot confirm

- **WHEN** a viewer attempts the confirm action
- **THEN** the request is rejected

### Requirement: QR payload capture (optional phase)

When a certificate PDF contains a decodable QR code, the system MAY decode
it and store the payload as verification evidence alongside code/URL.
Undecodable or absent QRs SHALL NOT block verification fields.

#### Scenario: QR decoded and stored

- **WHEN** a certificate image contains a QR encoding a verification URL or
  code
- **THEN** the payload is stored and shown as verification evidence

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
