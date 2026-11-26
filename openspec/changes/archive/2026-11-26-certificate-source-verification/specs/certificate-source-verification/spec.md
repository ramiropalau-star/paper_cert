# Spec Delta

## Purpose

Capture issuer verification artifacts (codes, URLs, QR payloads) printed on
certificates and track whether each certificate was validated against its
issuing source, automatically where a verifiable pattern exists or
manually by an authorized reviewer.

## ADDED Requirements

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
