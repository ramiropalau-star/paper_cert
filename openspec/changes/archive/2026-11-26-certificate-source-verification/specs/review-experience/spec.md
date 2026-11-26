# Spec Delta

## ADDED Requirements

### Requirement: Review displays verification status and artifacts

The review detail page SHALL show the verification status badge
(`none`/`self_reported`/`verified_at_source`/`manually_confirmed`), the
verification code, and the verification URL as a clickable link, plus who
confirmed and when for manual confirmations.

#### Scenario: Reviewer sees verification panel

- **WHEN** a certificate has a verification code and URL
- **THEN** the detail page shows the status badge, code, and a link to the
  issuer verification page

### Requirement: Reviewer confirms source verification manually

The review detail page SHALL offer a "verified at source" action to
reviewer+ roles that records actor and timestamp, and SHALL allow
unconfirming while preserving history.

#### Scenario: Confirm action records actor

- **WHEN** a reviewer clicks "verified at source"
- **THEN** the certificate status becomes `manually_confirmed` and the
  review history records the actor and timestamp
