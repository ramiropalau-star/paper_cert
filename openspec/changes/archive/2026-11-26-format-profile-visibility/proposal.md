# Proposal

## Why

Format profiles already learn per-entity/year layout signatures from
approved certificates and produce a `format_score`, but the score is only
visible inside the certificate detail page. Reviewers cannot see at a
glance which documents match their issuer's known format, cannot filter
the document table by format confidence, and have no way to inspect,
correct, or invalidate a learned profile that turned out wrong.

## What Changes

- Show the format score (and cohort) as a colored badge in the document
  list table; rows below the confidence threshold get a visual warning
  treatment so they attract review attention.
- Add a "formato dudoso" filter to the document list (and reuse the
  existing filter plumbing).
- Add a format-profile management page (reviewer+): list profiles per
  entity/year/exam cohort with anchors and sample counts, deactivate or
  reactivate a profile, and trigger a re-score of affected documents.
- Record profile deactivation/reactivation in the review/audit trail.

## Capabilities

### New Capabilities

### Modified Capabilities

- `certificate-format-profiles`: add requirements for surfacing the
  format score in the document list, filtering by format confidence,
  and managing (inspect/deactivate/rescore) learned profiles.
- `review-experience`: add a requirement that low format-confidence
  documents are visually flagged in the document table.

## Impact

- `documents/filters.py`, `documents/views.py`, `documents/urls.py`:
  new filter param and management views.
- `documents/templates/documents/list.html`, `detail.html`, new
  `format_profiles.html` template.
- `catalog/models.py` `FormatProfile`: add `is_active` flag (+migration).
- `documents/services/format_profile.py`: honor `is_active` in scoring;
  add rescore helper.
- `documents/services/review.py` or new audit path for profile
  activate/deactivate events.
- Tests: filters, views (roles), scoring with inactive profiles.
