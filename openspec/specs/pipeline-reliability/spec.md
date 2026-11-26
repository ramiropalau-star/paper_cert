# pipeline-reliability Specification

## Purpose
Keeps the certificate pipeline observable and recoverable when downstream services fail or leave documents and report jobs in intermediate states.

## Requirements

### Requirement: Outbound trigger outcomes are inspected

The system SHALL inspect the HTTP status and any explicit error payload of every outbound n8n processing and report trigger. A non-2xx status or an error payload SHALL be recorded with the affected document or report job identifier. The bundled workflows SHALL return a non-2xx status from their error branches. The originating user action SHALL NOT fail solely because the trigger failed.

#### Scenario: Processing trigger returns a server error
- **WHEN** the n8n processing webhook returns HTTP 500 for a stored document
- **THEN** the failure is logged with the document identifier and response status
- **AND** the document remains in a recoverable state

#### Scenario: Error payload with a success status
- **WHEN** the n8n webhook returns HTTP 200 with an explicit error payload
- **THEN** the failure is logged with the affected identifier
- **AND** the work remains eligible for recovery

#### Scenario: Report trigger returns not found
- **WHEN** the n8n report webhook returns HTTP 404 for a queued report job
- **THEN** the failure is logged with the report job identifier and response status
- **AND** the report job remains eligible for recovery

#### Scenario: Trigger succeeds
- **WHEN** the n8n webhook returns a 2xx response without an error payload
- **THEN** no failure is recorded for that trigger

### Requirement: Stuck documents are recovered within a bounded budget

The system SHALL recover documents left in the recoverable processing states `stored`, `text_ready`, and `extracted` beyond a configurable age by requeuing them through the normal pipeline, using a bounded attempt budget. A document left in `received` beyond the threshold SHALL move to `error` because its staged upload is no longer available. When the budget is exhausted, the document SHALL move to `error` with a reason. Recovery SHALL be idempotent.

#### Scenario: Stale stored document is requeued
- **WHEN** a document has remained in `stored` longer than the configured threshold and has recovery attempts remaining
- **THEN** the recovery run re-triggers processing for that document
- **AND** no second document is created

#### Scenario: Recovery budget is exhausted
- **WHEN** a document has exhausted its recovery attempts
- **THEN** the document moves to `error` with a recovery reason
- **AND** it is no longer retried automatically

#### Scenario: Orphaned received document is failed
- **WHEN** a document has remained in `received` longer than the threshold
- **THEN** the document moves to `error` with a reason
- **AND** recovery does not attempt to re-upload it

#### Scenario: Fresh or terminal document is untouched
- **WHEN** a document is younger than the threshold or is in a terminal state
- **THEN** recovery leaves its state and timestamps unchanged

### Requirement: Stuck report jobs are recovered within a bounded budget

The system SHALL recover report jobs left in `queued` or `running` beyond a configurable age, retrying generation within a bounded attempt budget and moving exhausted jobs to `error` with a reason. `ready` jobs SHALL NOT be regenerated.

#### Scenario: Stale queued job is retried
- **WHEN** a report job has remained `queued` longer than the configured threshold and has attempts remaining
- **THEN** the recovery run retries generation for that same job
- **AND** no duplicate report job is created

#### Scenario: Stale running job is recovered
- **WHEN** a report job has remained `running` longer than the configured threshold
- **THEN** the recovery run retries generation for that same job

#### Scenario: Report recovery budget is exhausted
- **WHEN** a report job has exhausted its recovery attempts
- **THEN** the job moves to `error` with a reason
- **AND** it is no longer retried automatically

#### Scenario: Ready job is untouched
- **WHEN** a report job is already `ready`
- **THEN** recovery does not regenerate it or change its artifact

### Requirement: Transient Paperless failures retry with backoff

The system SHALL retry idempotent Paperless operations that fail transiently, including timeouts, HTTP 429, and HTTP 5xx, with bounded exponential backoff before surfacing the error. Permanent HTTP 4xx failures SHALL NOT be retried. Document uploads SHALL NOT be retried blindly because Paperless offers no idempotency key.

#### Scenario: Transient failure succeeds on retry
- **WHEN** an idempotent Paperless request fails with HTTP 503 and a later attempt succeeds
- **THEN** the operation returns the successful result
- **AND** the retry is recorded without turning the document into an error

#### Scenario: Upload is not retried blindly
- **WHEN** a document upload POST fails with a transient error
- **THEN** the operation fails without a second upload attempt
- **AND** the failure is surfaced so an operator can retry safely

#### Scenario: Permanent failure is not retried
- **WHEN** a Paperless request fails with HTTP 400
- **THEN** the operation fails immediately without further attempts

#### Scenario: Retry budget is exhausted
- **WHEN** a Paperless operation still fails after the configured attempts
- **THEN** the error is surfaced to the caller with the original status

### Requirement: Invalid extraction output is repaired with feedback

When model output fails JSON or schema validation, the system SHALL retry with the validation failure and the invalid output included as repair context, within the existing bounded attempt budget. Confidence values outside the range 0..1 and evidence quotes absent from the cited page SHALL be rejected as invalid output.

#### Scenario: Invalid JSON is retried with feedback
- **WHEN** the model returns malformed JSON
- **THEN** the next attempt includes the validation error and the invalid output as repair context

#### Scenario: Out-of-range confidence is rejected
- **WHEN** the model returns a confidence value below 0 or above 1
- **THEN** the output is rejected as invalid and the repair path applies

#### Scenario: Unsupported evidence quote is rejected
- **WHEN** the model cites a page and quote that does not appear in that page's text
- **THEN** the output is rejected as invalid and the repair path applies

#### Scenario: Repair budget is exhausted
- **WHEN** all attempts produce invalid output
- **THEN** the document is routed to review with the `invalid_extraction` reason

### Requirement: State transitions are validated and consistent

The system SHALL validate certificate and document state changes against one transition policy. Illegal transitions SHALL be refused with a user-visible error and SHALL NOT persist partial changes. Approving or rejecting a certificate SHALL keep the document and certificate states consistent.

#### Scenario: Approving a rejected certificate is refused
- **WHEN** an operator attempts to approve a certificate whose review status is `rejected`
- **THEN** the action is refused with a user-visible error
- **AND** neither the certificate nor the document state changes

#### Scenario: Validating an approved certificate is refused
- **WHEN** an operator attempts to validate a certificate whose review status is `approved`
- **THEN** the action is refused with a user-visible error

#### Scenario: Approval updates both records atomically
- **WHEN** a pending certificate with all required fields is approved
- **THEN** the certificate becomes `approved` and the document becomes `approved` in the same transaction

#### Scenario: Reprocess resets both records
- **WHEN** an operator reprocesses a document
- **THEN** the document returns to `stored` and the certificate returns to `pending`
- **AND** the previous states are preserved in the review event

### Requirement: Failures are observable without leaking content

The system SHALL render structured failure fields, including request, document, report, and outcome identifiers, in application logs. The system SHALL expose a read-only status report of stale documents and report jobs, including attempt counts. Logs SHALL NOT include certificate text or secrets.

#### Scenario: Structured fields appear in logs
- **WHEN** a trigger or recovery failure is logged
- **THEN** the rendered log line includes the relevant document or report identifier and the outcome
- **AND** it does not include the certificate text

#### Scenario: Operator can inspect stale work
- **WHEN** an operator runs the read-only recovery status command
- **THEN** the output lists stale documents and report jobs with their attempts
- **AND** the command does not modify any state

### Requirement: Recovery preserves pipeline idempotency

Recovery and retries SHALL preserve pipeline idempotency. Reprocessing a document SHALL update its existing certificate and SHALL NOT create duplicate documents, certificates, or report jobs.

#### Scenario: Recovery after partial success does not duplicate
- **WHEN** recovery re-triggers a document that already has a certificate
- **THEN** the existing certificate is updated
- **AND** no second document or certificate is created

#### Scenario: Report recovery reuses the job
- **WHEN** recovery retries a report job
- **THEN** the existing job is updated
- **AND** no second report job is created
