# Tasks

## 1. Configuration and schema

- [x] 1.1 Add `APP_RECOVERY_INTERVAL_SECONDS`, `APP_RECOVERY_STALE_SECONDS`, `APP_RECOVERY_MAX_ATTEMPTS`, `APP_PAPERLESS_RETRIES`, `APP_PAPERLESS_RETRY_BACKOFF_SECONDS`, and `APP_N8N_WEBHOOK_TIMEOUT_SECONDS` to `read_app_settings()` and `.env.example`; verify the defaults with a focused settings test and `python manage.py check`.
- [x] 1.2 Add `recovery_attempts` and `last_recovery_at` to `Document`, and `attempts` and `last_attempt_at` to `ReportJob`; generate `documents/migrations/0005_*` and `reports/migrations/0002_*`; verify `makemigrations --check --dry-run` is clean and the migration applies to the test database.

## 2. State transition policy

- [x] 2.1 Implement `documents/services/state.py` with the allowed document and certificate transitions, `StateTransitionError`, and helpers that persist with `update_fields` and reset recovery attempts on state exit; verify legal and illegal transitions with unit tests.
- [x] 2.2 Refactor `approve_certificate`, `reject_certificate`, `validate_certificate`, `reprocess_document`, and the pipeline `_save` helpers to use the state helpers; verify approve/reject/reprocess keep certificate and document states consistent and that rejected certificates cannot be approved or validated.

## 3. Outbound trigger outcomes

- [x] 3.1 Add a `TriggerResult` to `documents/services/n8n.py`, inspect the HTTP status and explicit error payload, and log failures with `document_id` or `report_id`, `status_code`, and `outcome`; verify 2xx, 4xx, 5xx, 200-with-error-payload, and transport-error cases with unit tests.
- [x] 3.2 Update `process_upload`, `ingest_paperless_document`, `reprocess_document`, and `create_report_job` to use the result without failing the user action; verify with tests that a failed trigger still leaves the document or job recoverable.
- [x] 3.3 Change the error responders in `n8n/workflows/processing.json` and `n8n/workflows/report.json` to return a 5xx status and verify the exported workflows still import and route errors correctly.

## 4. Paperless transient retries

- [x] 4.1 Add bounded exponential backoff for `retryable` errors on idempotent `GET`, `PATCH`, and `DELETE` requests in `DocumentStore._request`; verify a 503-then-success case, a 400-without-retry case, and an exhausted-budget case with unit tests.
- [x] 4.2 Keep document upload `POST` single-attempt and document the duplicate risk; verify with a test that a transient upload failure performs exactly one POST.

## 5. Extraction repair

- [x] 5.1 Change `_call_model` to append the invalid model output and the validation error to the retry messages; verify a malformed-JSON retry includes both in a unit test.
- [x] 5.2 Add confidence range validation and evidence-quote validation against the cited page text; verify out-of-range confidence and unsupported quotes trigger repair with unit tests.
- [x] 5.3 Preserve the exhaustion path to `pending_review` with `invalid_extraction`; verify the state and reason with a test.

## 6. Stuck-work recovery

- [x] 6.1 Implement `documents/services/recovery.py` for documents: requeue `stored`, `text_ready`, and `extracted`; fail `received` with `recovery_orphaned_received`; enforce the attempt budget and reset attempts on state exit; verify each state, idempotency, and exhaustion with tests.
- [x] 6.2 Implement report recovery for `queued` and `running` jobs, leave `ready` untouched, and call `run_report_job` directly; verify retry, exhaustion, and no-duplicate-job cases with tests.
- [x] 6.3 Add `documents/management/commands/recover_stuck.py` with `--dry-run`, `--older-than`, `--max-attempts`, `--documents-only`, and `--reports-only`; verify dry-run reports stale work and writes nothing.
- [x] 6.4 Integrate recovery into `watch_inbox` at the configured interval and document the manual command, thresholds, and error reasons in `docs/operations.md`; verify `APP_RECOVERY_INTERVAL_SECONDS=0` disables the loop and the documented command runs as written.

## 7. Observability

- [x] 7.1 Add `RequestIdMiddleware`, a contextvar-backed log filter, and a formatter that renders `request_id`, `document_id`, `report_id`, `outcome`, and `status_code`; verify the fields appear in captured log output and are absent when not supplied.
- [x] 7.2 Log recovery runs, requeues, and exhaustions without page text, prompts, tokens, or request bodies; verify the emitted events and absence of sensitive content with tests.

## 8. Integration verification

- [x] 8.1 Run the full suite, `python manage.py check`, `makemigrations --check --dry-run`, and `openspec validate pipeline-reliability-hardening --strict`; fix any failures and record the observed results.
- [x] 8.2 Run a manual smoke test: create a stale document and a stale report job in a test database, run `recover_stuck --dry-run`, then the real command, and verify recovery, no duplicate records, and the expected terminal states.

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Verify the archived specs and the resulting capability baseline.
