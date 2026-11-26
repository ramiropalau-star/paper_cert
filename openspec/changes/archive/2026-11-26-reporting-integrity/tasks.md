# Tasks

## 1. Stable processing timestamp

- [x] 1.1 Add `Document.processed_at`, its migration, and the backfill from `updated_at`; verify existing rows receive a value and new rows default to empty until processing.
- [x] 1.2 Set `processed_at` at classification terminal outcomes and on successful reprocessing, without changing it on edits, approval, or rejection; verify with classification, edit, and reprocess tests.

## 2. Report dates and timezone

- [x] 2.1 Use `processed_at` (with a legacy fallback) for the report's processing-date column and convert aware timestamps with `timezone.localtime`; verify an edit does not change the date and a near-midnight timestamp uses the local date.
- [x] 2.2 Document the timezone and inclusive date-range semantics in the report UI or operations documentation; verify the documented behavior matches the queryset.

## 3. Persisted counts

- [x] 3.1 Add `ReportJob.counts`, populate it from the same lists used to build the workbook, and display it in the report detail; verify counts equal the sheet data-row counts and pending includes validated.
- [x] 3.2 Handle legacy jobs with empty counts without showing false zeros; verify the detail template renders "No disponible".

## 4. Filter validation

- [x] 4.1 Add `ReportFilterError` and `parse_report_filters`, validate before creating a job, and surface the error in the view; verify an invalid exact date and an invalid range are rejected without creating a job.
- [x] 4.2 Catch the same error in `generate_report` for jobs created elsewhere and mark the job as error with a clear reason; verify with a direct service test.

## 5. Snapshot integrity

- [x] 5.1 Verify a ready job returns its existing artifact without rewriting it after source data changes, and a new job reflects the new data without altering the old artifact.
- [x] 5.2 Add regression tests for row/count agreement across approved, pending, validated, and rejected certificates.

## 6. Integration verification

- [x] 6.1 Run the reports, classification, review, and migration tests plus the full suite; record the observed results.
- [x] 6.2 Run `openspec validate reporting-integrity --strict` and fix any artifact issues.

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Verify the archived `reporting-integrity` spec and the resulting capability baseline.
