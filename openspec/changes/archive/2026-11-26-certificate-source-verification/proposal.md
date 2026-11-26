# Proposal

## Why

Certificates carry issuer verification data (CSV codes, verification
numbers, verification URLs, QR codes) that today is ignored: it stays buried
in page text and reviewers cannot tell at a glance whether a certificate
was validated against its source. Some issuers offer programmatic
verification (CSV-style codes via GET); others only expose web portals.

## What Changes

- Extract and store `verification_code` and `verification_url` per
  certificate, via deterministic label-anchored patterns (multi-language:
  "Cod. Verificació", "Verification Number", "CSV", "URL Verif", etc.) plus
  model extraction as backup.
- New `verification_status` on Certificate: `none` | `self_reported`
  (code/URL found on document) | `verified_at_source` (automated check
  passed) | `manually_confirmed` (reviewer confirmed against source).
- Automated source verification for issuers with a known GET-verifiable
  pattern (CSV codes, e.g. tramita.gva.es style); result recorded with
  timestamp and evidence.
- Reviewer action "confirm verified at source" for portal-only issuers,
  recording actor + timestamp; review UI shows code, URL (clickable), and
  status badge.
- Optional: detect QR codes embedded in certificate PDFs and store the
  decoded payload as verification evidence.

## Capabilities

### New Capabilities

- `certificate-source-verification`: capture issuer verification artifacts
  (code, URL, QR payload) from certificates and track whether the
  certificate was validated against the issuing source, automatically where
  feasible or manually by a reviewer.

### Modified Capabilities

- `certificate-extraction`: SHALL also capture verification code and URL
  when present on the document.
- `review-experience`: SHALL display verification status/code/URL and
  offer the manual confirm action to authorized reviewers.

## Impact

- `documents/models.py`: `verification_code`, `verification_url`,
  `verification_status`, `verified_by`, `verified_at` fields + migration.
- `documents/services/extraction.py` or new `verification.py`: deterministic
  harvest patterns + optional model fields.
- New verifier abstraction: per-pattern GET check (CSV family first);
  pluggable per issuer.
- Review templates/views: status badge, code/URL display, confirm action.
- Optional QR decode dependency (e.g. pyzbar/zxing) — decision in design.
