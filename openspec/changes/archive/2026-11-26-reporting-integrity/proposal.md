# Proposal

## Why

The generated workbook labels a column "Fecha de procesamiento" but fills it with `document.updated_at`, so any later edit changes the date of an already-processed certificate. Invalid date filters are silently ignored, which broadens a report instead of rejecting an impossible one. The report job does not persist the counts it generated, so the UI cannot show what the artifact actually contains, and dates are converted without an explicit local-timezone rule.

## What Changes

- **Stable processing date**: add `Document.processed_at`, set it when classification reaches a terminal outcome, and use it in reports instead of `updated_at`; backfill existing rows with the best available timestamp.
- **Persisted counts**: store approved, pending, rejected, and total counts on the report job and show them in the report detail.
- **Validated filters**: reject invalid or ambiguous date filters with a clear error instead of silently ignoring them.
- **Consistent dates**: convert report timestamps to the configured local timezone and document inclusive date bounds.
- **Snapshot consistency**: compute rows and counts from the same per-status lists, and never rewrite an existing ready artifact.
- **Tests and documentation**: cover stable dates after edits, count/row agreement, invalid filters, timezone conversion, and artifact immutability.

## Capabilities

### New Capabilities

- `reporting-integrity`: durable behavior for producing certificate reports whose dates, counts, filters, and artifacts faithfully represent the selected data.

### Modified Capabilities

None.

## Impact

- **Data**: `Document.processed_at` and `ReportJob.counts` with migrations and backfill.
- **Services**: `documents/services/classification.py`, `documents/services/review.py` where terminal processing is recorded, and `reports/services.py`.
- **Views and templates**: report creation validation and `reports/templates/reports/detail.html`.
- **Risk**: the backfill uses `updated_at` for existing rows, which is the best available historical value and is documented as such. Reports generated before the change are not rewritten.
