# Design

## Context

`_row_values` uses `_date_cell(document.updated_at)` for the "Fecha de procesamiento" column. `certificates_queryset` parses date filters and ignores values that do not parse. `ReportJob` stores filters, status, artifact path, and error, but not the row counts. `_date_cell` calls `.date()` directly, which uses UTC for aware datetimes. `run_report_job` already returns a ready job without regenerating it.

## Goals / Non-Goals

**Goals:**

- Make the processing date independent of later edits.
- Persist and display counts that match the workbook.
- Reject invalid filters.
- Use the configured local timezone.
- Keep ready artifacts immutable.

**Non-Goals:**

- Redesigning the report UI or changing the certificate selection rules.
- Recomputing historical artifacts.
- Adding scheduled reports or delivery changes.

## Decisions

### 1. Add `Document.processed_at`

Add `processed_at = DateTimeField(null=True, blank=True, db_index=True)`. Set it with `timezone.now()` when classification reaches a terminal outcome (`pending_review` or an error that produces a certificate) and when a reprocess completes classification. Do not change it on certificate edits, approval, rejection, or metadata-only saves. A data migration backfills `processed_at = updated_at` for existing rows and documents that this is the best available historical approximation.

The report uses `_date_cell(document.processed_at or document.updated_at)` so a row never loses its date if a legacy document was not backfilled.

Alternatives: use `Certificate.updated_at` (changes on edits), use the latest `ReviewEvent` (missing for pending/error rows). Rejected.

### 2. Persist counts on the report job

Add `counts = JSONField(default=dict, blank=True)`. `generate_report` computes `approved`, `pending`, and `rejected` lists once, uses those same lists for `build_workbook`, and stores `{"approved": len(...), "pending": len(...), "rejected": len(...), "total": ...}` before marking the job ready. The detail template shows the counts; a legacy job with an empty `counts` shows "No disponible" instead of zeros.

Alternatives: derive counts from the artifact (extra parsing, can drift), compute in the template (re-queries live data and can disagree with the artifact). Rejected.

### 3. Validate filters before creating a job

Add `ReportFilterError` and `parse_report_filters(filters)` in `reports/services.py`. For each provided date filter, call `parse_date_text`; if it returns `None` or reports ambiguity, raise with the filter name. `create_report_job` validates first and raises, so the view can show a message and no job is created. `generate_report` also catches the error for jobs created by another path and marks the job as error with a clear reason.

The existing inclusive `issue_date__gte`/`issue_date__lte` behavior stays. `include_pending` continues to mean pending plus validated; the count uses the same combined list.

### 4. Convert timestamps with the application timezone

`_date_cell` uses `timezone.localtime(value).date()` when the datetime is aware, and `.date()` otherwise. Date fields (`issue_date`, etc.) remain plain dates. The report documentation states that date filters are calendar dates in the application timezone and that both bounds are inclusive.

### 5. Keep the ready artifact immutable

`run_report_job` keeps its early return for `READY`. `generate_report` only writes a new file for a job that is not ready. A new report always creates a new `ReportJob`, so a previous artifact is never overwritten. Tests compare the artifact bytes and modification time after a source change and after re-running the ready job.

## Risks / Trade-offs

- The backfill uses `updated_at`, which may reflect a later edit for old rows → documented as an approximation; new rows are exact.
- Adding `processed_at` requires touching classification and reprocess paths → tests cover both terminal paths.
- Rejecting invalid filters changes behavior for callers that relied on silent fallback → the error is explicit and the form shows it; no valid filter is affected.
- Storing counts adds a JSON field → simple, migration-safe, and tolerant of future report types.

## Migration Plan

1. Add both fields and the data migration; run `migrate`.
2. Deploy the service and template changes together.
3. Generate a new report to verify counts and dates; previous ready jobs remain downloadable with "No disponible" counts.
4. Rollback: the new columns are additive; the previous code ignores them. Keep the columns and revert the application if needed.

## Open Questions

None that change the spec, approach, or task breakdown.
