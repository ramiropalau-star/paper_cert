# Proposal

## Why

The language-certificate pipeline can silently stall. Outbound n8n triggers ignore HTTP failures (`documents/services/n8n.py:23`, `reports/services.py:270`), transient Paperless errors are classified as retryable but never retried, and there is no recovery path for documents or report jobs left in intermediate states. Operators only discover the problem when a certificate never reaches review or a report never appears. The pending `platform-operations` capability already promises bounded retries and visible failures; this change makes that promise true for the critical processing path.

## What Changes

- **Outbound trigger delivery**: n8n trigger calls inspect the HTTP status and any explicit error payload, log failures with document/report correlation, and use a bounded timeout. The bundled workflows return a non-2xx status from their error branches instead of HTTP 200. Delivery stays best-effort at request time, but failures are recorded so recovery can act on them.
- **Stuck-work recovery**: add an idempotent recovery command and watcher integration that requeues documents in transient states and report jobs left `queued`/`running` beyond a configurable threshold. Exhausted recovery marks the item `error` with a reason instead of retrying forever.
- **Paperless adapter retries**: honor the existing `retryable` classification with bounded exponential backoff for timeouts and 5xx/429 responses; permanent 4xx errors fail immediately.
- **Extraction repair retry**: when model output fails JSON/schema validation, retry with the validation error and the invalid output as repair context instead of resending the identical prompt. Validate confidence range and evidence quotes.
- **State-transition integrity**: centralize allowed `Document.ProcessingState` and `Certificate.ReviewStatus` transitions, reconcile the two fields, and refuse illegal transitions (for example, approving a rejected certificate) with a clear error.
- **Failure observability**: render structured fields (`request_id`, `document_id`, `report_id`, `outcome`) in logs and expose stuck-item counts so an operator can detect a stalled pipeline.
- **Tests**: cover n8n non-2xx handling, recovery thresholds and idempotency, retry/backoff behavior, extraction repair, illegal transitions, and structured log output.

Non-goals: n8n webhook authentication and Paperless port exposure (security change); OCR single-pass optimization and sync/tag batching (performance change); report date semantics and UI copy changes (reporting/UX change). Those should be separate changes.

## Capabilities

### New Capabilities

- `pipeline-reliability`: durable behavior for delivering outbound orchestration triggers, recovering stuck processing and report work, bounding retries, preserving valid state transitions, and making failures observable.

### Modified Capabilities

None. The pending `platform-operations` capability (from `language-certificate-recognition`, not yet archived) covers bounded retries at a high level; this change introduces the concrete reliability capability without changing that pending spec.

## Impact

- **Code**: `documents/services/n8n.py`, `documents/services/inbox.py`, `documents/services/paperless.py`, `documents/services/extraction.py`, `documents/services/review.py`, `documents/models.py`, `config/settings.py`, plus a new management command.
- **Behavior**: processing and report recovery becomes automatic; non-2xx trigger responses are logged; illegal transitions are refused; transient Paperless failures retry with backoff.
- **Operations**: new configurable thresholds and timeouts; logs carry correlation fields; no new external dependency.
- **APIs**: no public endpoint changes; internal trigger and state-transition semantics tighten.
- **Risk**: recovery must be idempotent and must not duplicate certificates or report rows; retries must remain bounded.
