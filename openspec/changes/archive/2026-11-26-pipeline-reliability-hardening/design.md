# Design

## Context

The Django application owns document and certificate state, while n8n orchestrates the synchronous HTTP stages (`text`, `extract`, `classify`) and the report flow. Existing reliability primitives are partial:

- `notify_processing` and `notify_report` are fire-and-forget: they catch transport exceptions but ignore non-2xx responses.
- `DocumentStore` classifies transient and permanent errors, but no caller retries them.
- The only always-on loop is `watch_inbox`, which syncs Paperless documents; it never inspects local intermediate states.
- State assignments are spread across services, and `approve_certificate` and `validate_certificate` enforce different preconditions.
- The logging formatter drops `extra` fields, so the structured logs already emitted by `core/internal.py` and the services are invisible.

Constraints: no new infrastructure (no Celery/Redis), the watcher management command is the only always-on worker, PostgreSQL in production, SQLite in tests, and migrations are used.

## Goals / Non-Goals

**Goals:**

- Make stalled documents and report jobs recoverable through a bounded, idempotent loop.
- Surface downstream failures in logs and in an operator-readable status report.
- Retry only safe Paperless operations, with exponential backoff.
- Improve extraction retries with validation feedback.
- Enforce a single state-transition policy.

**Non-Goals:**

- A new queue, broker, or distributed worker.
- n8n webhook authentication, Paperless port exposure, OCR single-pass optimization, report date semantics, or UI redesign.
- Automatic retry of document uploads (duplicate risk).

## Decisions

### 1. Recovery is a service plus a management command, invoked by the watcher

`documents/services/recovery.py` owns `recover_stuck_documents()` and `recover_stuck_reports()`. A new `documents/management/commands/recover_stuck.py` exposes `--dry-run`, `--older-than`, `--max-attempts`, `--documents-only`, and `--reports-only`. `watch_inbox` calls the service every `APP_RECOVERY_INTERVAL_SECONDS` (default 60) after the Paperless sync block. The command can also run manually or from cron.

The run is safe to repeat: each row is claimed inside `transaction.atomic()` with `select_for_update()`, then its state and age are re-checked before acting. Terminal states are excluded. A single watcher process is the normal deployment; a concurrent manual run waits on the row lock and then skips work already done.

Alternatives considered: a separate daemon (more moving parts), Celery (new infrastructure), recovery inside request handlers (blocks requests, duplicates logic). Rejected.

### 2. Recovery attempts are persisted on the affected rows

Add `Document.recovery_attempts` (default 0) and `Document.last_recovery_at` (null). Add `ReportJob.attempts` (default 0) and `ReportJob.last_attempt_at` (null).

Each recovery action increments the counter. When the counter exceeds `APP_RECOVERY_MAX_ATTEMPTS` (default 3), the row moves to `error` with `recovery_attempts_exhausted`. `recovery_attempts` resets when the document leaves a recoverable state through the state helper, and when `reprocess_document()` runs. `ReportJob.attempts` resets when a new job is created; a `ready` job is never touched.

Alternatives: derive attempts from logs (not queryable, lossy) or a separate recovery table (more schema and joins). Rejected.

### 3. Document recovery re-triggers n8n; report recovery runs locally

For `stored`, `text_ready`, and `extracted`, recovery calls `notify_processing(document)` to replay the n8n workflow. The stages are idempotent (page upserts, certificate upsert, classification update), and n8n's HTTP nodes already retry transient stage failures. Replaying may repeat OCR or extraction for later states; that is acceptable for a rare recovery and keeps orchestration in one place. A future optimization can resume at the next stage without changing the contract.

For `received`, no source bytes are persisted, so recovery moves the document to `error` with `recovery_orphaned_received`; it never attempts a re-upload.

For report jobs, recovery calls `run_report_job(job.pk)` directly instead of re-triggering n8n. Report generation is local and idempotent for `ready`, and it should not depend on the same n8n instance whose failure caused the stall. The n8n webhook remains the normal path.

Alternatives: run extraction/classification directly in the reaper (bypasses orchestration, blocks the watcher on slow LLM calls) or always re-trigger n8n for reports (fails when n8n is down). Rejected.

### 4. Trigger outcomes are results, not exceptions

`notify_processing` and `notify_report` return a `TriggerResult` with `delivered`, `status_code`, and `error`. They make one attempt with a configurable timeout and log non-2xx, explicit error payloads, and transport failures with `document_id` or `report_id`, `status_code`, and `outcome`.

The bundled n8n workflows currently respond with HTTP 200 from their error branches, so a status-only check would report false success. The workflows change their error responders to a 5xx status, and the client treats either a non-2xx status or an explicit `error` payload as failure. This keeps the check correct during a rolling deployment where the old workflow may still return 200.

Callers do not fail the user action when a trigger fails; the persisted state plus the reaper is the recovery path. `reprocess_document` still reports success after a failed trigger because the document remains recoverable.

Alternatives: raise on failure (couples web requests to n8n availability) or retry inside the request (blocks uploads for the retry budget). Rejected.

### 5. Paperless retries at the adapter boundary, scoped to idempotent methods

Add `paperless_retries` (default 2) and `paperless_retry_backoff_seconds` (default 0.5) to `APP`. `DocumentStore._request` retries `retryable` errors for `GET`, `PATCH`, and `DELETE` with exponential backoff (`base * 2**attempt`, capped). It does not retry `POST`.

The reason is specific: `POST /api/documents/post_document/` has no idempotency key, and a retry after a lost response could create a duplicate Paperless document. The upload path keeps its single attempt; a failed upload moves the document to `error` with the Paperless error, and the operator can retry the upload. Automatic upload recovery is a non-goal.

Alternatives: retry all methods (duplicate risk), retry in every caller (duplication), use an idempotency key (unsupported by Paperless). Rejected.

### 6. Extraction repair loop with evidence and confidence validation

`_call_model(llm, text, page_texts)` builds the initial messages. On `json.JSONDecodeError`, `ValidationError`, or `ValueError`, it:

1. Appends the invalid assistant output.
2. Appends a user message with the validation error and a short instruction to return only corrected JSON matching the schema.
3. Retries up to `MAX_INVALID_ATTEMPTS` (existing value: 3).

Pydantic validates confidence with `ge=0, le=1`. A post-parse `_validate_evidence(payload, page_texts)` checks that each `evidence.quote` appears in the cited page after whitespace normalization; a failure raises `ValueError` and triggers repair. `page_texts` comes from `document.pages` as `page_number -> text`, loaded once per extraction; the combined text remains the prompt input.

On exhaustion, the existing `_fail(..., code="invalid_extraction", state=PENDING_REVIEW)` path is unchanged.

Alternatives: resend the identical prompt (current behavior, wastes attempts) or relax validation (lets bad data through). Rejected.

### 7. One state-transition policy

New `documents/services/state.py` defines the allowed transitions and provides `transition_document()` and `transition_certificate()`. Both validate, persist with `update_fields`, reset recovery attempts when leaving recoverable states, and raise `StateTransitionError` for illegal moves.

Document policy:

```
received      -> stored | error
stored        -> text_ready | pending_review | error
text_ready    -> extracted | pending_review | error
extracted     -> pending_review | error
pending_review-> approved | rejected
approved      -> rejected
error | rejected | pending_review | approved -> stored   (reprocess only)
```

Certificate policy:

```
pending   -> validated | rejected
validated -> approved | rejected
approved  -> rejected
rejected  -> terminal until reprocess
```

`approve_certificate`, `reject_certificate`, `validate_certificate`, `reprocess_document`, the `_save` helpers in text/extraction/classification, and the internal endpoints call the helper. Approve, reject, and reprocess keep the certificate and document changes in one `transaction.atomic()`. Approving or validating a rejected certificate is refused before any write.

Alternatives: keep per-function checks (drift, inconsistent errors) or add a Django FSM dependency (overkill). Rejected.

### 8. Observability: request ID, formatter, status report

`core/logging.py` adds:

- `request_id_var`, a contextvar set by `RequestIdMiddleware` from `X-Request-ID` or a generated UUID, reset in `finally`.
- `RequestIdFilter`, which injects `request_id` into every record.
- `KeyValueFormatter`, which appends known extras (`request_id`, `document_id`, `report_id`, `outcome`, `status_code`) when present. `LOG_FORMAT=json` selects a JSON formatter.

`config/settings.py` uses the new formatter and filter. `recover_stuck --dry-run` prints stale documents and report jobs with state, age, and attempts, without writing. Logs never include page text, prompts, model output, tokens, or request bodies; the existing 300-character bound on Paperless response bodies stays.

## Risks / Trade-offs

- Replaying n8n may repeat OCR or extraction for `text_ready`/`extracted` → threshold is longer than the slowest stage, attempts are bounded, and stages are idempotent. A future stage-resume optimization can reduce cost without changing the contract.
- Exhausted recovery moves work to `error` and requires operator action → clear reason, status command, and `reprocess_document()` resets attempts.
- Upload POST is not retried → transient upload failures still need a manual retry. This is deliberate to avoid duplicate Paperless documents.
- Report recovery bypasses n8n → generation is local and idempotent; the webhook remains the normal path and recovery is the fallback.
- `select_for_update` behavior differs on SQLite → production is PostgreSQL; tests cover logic and idempotency, not multi-process contention.
- New migration on existing data → defaults are safe; no backfill is required.
- Formatter changes could affect log parsers → the default remains a single-line readable format; JSON is opt-in.

## Migration Plan

1. Add the four fields and generate `documents/migrations/0005_*` and `reports/migrations/0002_*`; apply with `manage.py migrate`.
2. Add the new `APP_*` settings with defaults; no `.env` change is required. Document them in `.env.example`.
3. Deploy the app, then restart `watch_inbox` so it loads the recovery loop. The command can run manually before the loop is enabled.
4. Monitor `recovery_run`, `recovery_requeued`, `recovery_exhausted`, and `trigger_failed` events.
5. Rollback: set `APP_RECOVERY_INTERVAL_SECONDS=0` or remove the watcher call and restart the watcher. The new fields remain unused; the migration can be reversed, dropping only recovery bookkeeping.

## Open Questions

None that change the spec, approach, or task breakdown. Default thresholds are configurable and can be tuned after observing real pipeline latencies.
