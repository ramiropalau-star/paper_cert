# Tasks

## 1. Project foundation and tooling

- [x] 1.1 Scaffold the repository layout (`app/`, `ocr-service/`, `n8n/workflows/`, `docs/`, `tests/`, `docker/`) with a Django project and base settings module; verify the expected tree exists and `python -c "import config.settings"` succeeds in the built image.
- [x] 1.2 Pin runtime and development dependencies (Django, psycopg, gunicorn, whitenoise, httpx, pypdf, openpyxl, python-magic, python-dateutil, pytest, pytest-django, respx, factory-boy, ruff) and verify a clean `pip install -r requirements-dev.txt` completes inside the app image.
- [x] 1.3 Implement environment-driven settings for database, hosts, cookies, upload limits, service token, OCR URL, Paperless URL/token, Ollama URL/model, and pipeline thresholds; verify settings tests load overrides from environment variables.
- [x] 1.4 Add ruff and pytest configuration with a documented local check command; verify `ruff check .` and `pytest --collect-only` pass.
- [x] 1.5 Add base URL routing, a health endpoint, base template, and static assets; verify the health endpoint returns 200 and unknown routes render the error template.
- [x] 1.6 Document development setup, local test execution, and directory conventions in `docs/development.md`; verify every documented command runs as written.

## 2. Data model, migrations, and catalog

- [x] 2.1 Implement `documents`, `document_pages`, and `certificates` models with status choices, unique fingerprint, one-certificate-per-document constraint, and timestamps; verify migrations apply and model tests cover uniqueness and default states.
- [x] 2.2 Implement catalog models (`languages`, `entities`, `entity_aliases`, `exams`, `cefr_conversion_rules`) with alias uniqueness and approved-rule metadata; verify migration and constraint tests pass.
- [x] 2.3 Implement `review_events` and `report_jobs` models; verify migrations apply and tests cover event types, payload storage, and job states.
- [x] 2.4 Register catalog, document, certificate, and user models in Django admin with role-restricted access; verify admin pages load for staff and are denied to non-staff in view tests.
- [x] 2.5 Add an idempotent management command or data migration that seeds languages, the specified English, French, German, Spanish, Italian, and Portuguese entities/exams, aliases, and CEFR rule placeholders; verify re-running produces no duplicates and tests assert required coverage.
- [x] 2.6 Add catalog editing guardrails (approved CEFR rules require approver, reference, and active flag) and tests proving unapproved or inactive rules never apply.
- [x] 2.7 Document the data model and catalog management in `docs/data-model.md`; verify the documented fields match the migrations.

## 3. Authentication, roles, and internal API security

- [x] 3.1 Implement login and logout with session authentication and protected views; verify unauthenticated requests redirect to login and authenticated sessions reach the app.
- [x] 3.2 Create `viewer`, `reviewer`, and `admin` role groups with permission checks on document, review, catalog, and report views; verify role tests return allowed or forbidden results as specified.
- [x] 3.3 Implement the `/internal/` service-token authentication layer with constant-time comparison and structured request logging; verify missing, wrong, and valid tokens produce denied, denied, and accepted responses.
- [x] 3.4 Enforce CSRF protection, secure cookie settings, and upload size limits in configuration; verify tests cover CSRF rejection, cookie flags, and oversized requests.
- [x] 3.5 Document authentication, permissions, and internal API handling in `docs/security.md`; verify the documented roles match the permission tests.

## 4. Intake, validation, duplicate detection, and Paperless integration

- [x] 4.1 Implement the upload view and staging storage with randomized filenames; verify view tests accept PDF and image uploads and create a staging file.
- [x] 4.2 Implement file validation for extension, declared MIME, magic bytes, PDF parseability, size cap, and page cap; verify one test per rejection path and an acceptance test for valid files.
- [x] 4.3 Implement SHA-256 fingerprinting and duplicate handling; verify re-uploading the same bytes returns the existing record and creates no second document or certificate.
- [x] 4.4 Implement the Paperless client (post document, poll task, download original, delete) behind a `DocumentStore` adapter; verify respx contract tests for success, document-store failure, and timeout.
- [x] 4.5 Wire the intake state machine from validation through storage to a persisted `documents` row; verify an integration test with a fake Paperless service reaches the stored state and a failure test records an explicit error state.
- [x] 4.6 Implement authorized deletion that removes the certificate data, review history, and stored original; verify allowed and forbidden deletion tests.
- [x] 4.7 Document intake, supported formats, limits, and Paperless configuration in `docs/intake.md`; verify every documented variable exists in `.env.example`.
- [x] 4.8 Extend the Paperless adapter with tag ensure/apply/remove operations and add the configurable `APP_PAPERLESS_OTHER_TAG` setting (default `Otros`); verify respx tests for tag lookup, creation, application, removal, and failure.

## 5. OCR service

- [x] 5.1 Scaffold the `ocr-service` FastAPI app with a pinned non-root Dockerfile including OCRmyPDF, Tesseract language packs, and Ghostscript; verify the image builds and `/health` returns healthy.
- [x] 5.2 Implement the versioned OCR contract for PDFs (with skip-text support) and images, accepting language lists, enforcing page caps and timeouts, and returning per-page text plus confidence; verify contract tests with a text PDF, a scanned PDF, and a PNG image.
- [x] 5.3 Implement OCR failure and quality signaling (unreadable input, timeout, low mean confidence); verify tests cover each signal and its error payload.
- [x] 5.4 Implement the app-side OCR client with timeouts, bounded retries, and typed errors; verify respx tests for success, transient failure, and exhaustion.
- [x] 5.5 Document OCR languages, engine substitution, and limits in `docs/ocr.md`; verify the documented language configuration is honored by a contract test.

## 6. Text acquisition pipeline

- [x] 6.1 Implement per-page embedded-text extraction with pypdf and configurable sufficiency thresholds; verify tests with a text PDF record each page as embedded and skip OCR.
- [x] 6.2 Implement per-page OCR fallback and persistence of page text, page method, document method (`embedded`, `ocr`, `mixed`), and page count; verify tests for scanned, image-only, mixed, and multi-page documents.
- [x] 6.3 Implement review flags and error states for insufficient text, low OCR confidence, and OCR failure; verify tests assert the reasons and states.
- [x] 6.4 Implement the idempotent internal text-acquisition endpoint; verify repeated calls update existing page rows without duplicates and preserve valid state transitions.
- [x] 6.5 Document thresholds, provenance, and failure handling in `docs/text-acquisition.md`; verify documented thresholds are present in `.env.example`.

## 7. Extraction with Ollama

- [x] 7.1 Implement the Ollama chat client with configurable base URL, model, timeout, JSON-schema format, and typed errors; verify respx tests for success, timeout, and server error.
- [x] 7.2 Define the versioned extraction prompt and JSON schema covering certificate detection, required fields, evidence, confidence, literal level/score, dates, and code; verify the schema validates and prompt tests assert the no-invention and evidence rules.
- [x] 7.3 Implement Pydantic validation, bounded retries on invalid output, and routing to review on exhaustion; verify tests for invalid JSON, schema mismatch, retry success, and retry exhaustion.
- [x] 7.4 Implement input-size caps plus non-certificate and multiple-certificate flags; verify tests that oversized input, non-certificates, and suspected multiple certificates are flagged without silent truncation.
- [x] 7.5 Persist extraction results, prompt version, per-field evidence, and confidence; verify database assertions match the model response.
- [x] 7.6 Implement the idempotent internal extraction endpoint with state guards; verify repeated calls do not duplicate data and invalid state transitions are refused.
- [x] 7.7 Document model selection, prompt versioning, and extraction troubleshooting in `docs/extraction.md`; verify documented model configuration is read from the environment in tests.

## 8. Classification and normalization

- [x] 8.1 Implement Unicode normalization (NFKC, casefold, whitespace collapse) and exact alias matching; verify unit tests accept known variants and reject fuzzy near-matches.
- [x] 8.2 Implement language and entity classification storing literal and normalized values plus examining entity, issuing body, and test center roles; verify tests for known aliases, role separation, and "Entidad pendiente de identificar".
- [x] 8.3 Implement CEFR assignment from explicit levels and approved conversion rules, recording rule-derived levels; verify tests for explicit levels, matching approved rules, and the no-rule case.
- [x] 8.4 Implement date parsing, YYYY-MM-DD normalization, original date retention, and issue/exam/result/detected date handling; verify tests for formats, ambiguous day-month order, and distinct dates.
- [x] 8.5 Implement review-reason aggregation for missing essential fields, unknown entities, ambiguous dates, low confidence, and multiple certificates; verify each reason is persisted with the record.
- [x] 8.6 Implement the idempotent internal classification endpoint; verify repeated classification yields stable values and no duplicate review reasons.
- [x] 8.7 Document catalog editing, the CEFR approval workflow, and the `Otros` manual-review label behavior in `docs/classification.md`; verify the admin steps match the implemented guardrails.
- [x] 8.8 Apply the configured `Otros` Paperless label to non-certificate, unresolved-language/entity, and failed-processing documents while keeping them in the manual-review queue; verify idempotent application and non-blocking behavior when the document store is unavailable.

## 9. Review UI and audit

- [x] 9.1 Implement the document list with state filters and pagination; verify view tests render processed, pending, approved, rejected, and error states.
- [x] 9.2 Implement the review detail view with the original document displayed alongside extracted fields, text-method indicator, and per-field warnings; verify tests assert all three elements.
- [x] 9.3 Implement manual editing with validation and audit events capturing actor, timestamp, and before/after values; verify edit tests and history assertions.
- [x] 9.4 Implement approve and reject actions restricted to reviewers, with required reasons for rejection and removal of the `Otros` manual-review label on approval; verify role, validation, state, and label-removal tests.
- [x] 9.5 Implement reprocessing that reuses the document, preserves history, and returns the certificate to pending review; verify no duplicate rows and chronological history.
- [x] 9.6 Implement search and combined filters by student, language, entity, level, and issue date; verify query tests for each filter and combinations.
- [x] 9.7 Implement the history view; verify events render in chronological order with their payloads.
- [x] 9.8 Document the review workflow and audit behavior in `docs/review.md`; verify the documented actions match the view tests.

## 10. Excel reporting

- [x] 10.1 Implement report job creation with filters and state tracking; verify tests cover filter persistence, job states, and permission enforcement.
- [x] 10.2 Implement the workbook generator with the required Spanish column headers, approved-only main sheet, Excel date cells, header row, and autofilter; verify openpyxl read-back tests assert columns, values, and formats.
- [x] 10.3 Implement the optional "Pendientes de revisión" sheet with explicit status and no presentation as confirmed data; verify tests for inclusion, exclusion, and sheet naming.
- [x] 10.4 Implement filtered report generation, the download endpoint, and the job-status UI; verify tests for filters, no-match handling, and authorized download.
- [x] 10.5 Generate and commit a sample `.xlsx` from test fixtures under `docs/examples/`; verify it opens and matches the documented columns.
- [x] 10.6 Document report generation, columns, filters, and pending-sheet behavior in `docs/reporting.md`; verify the documented sample matches the committed workbook.

## 11. n8n orchestration

- [x] 11.1 Define and export the processing workflow (intake trigger, text acquisition, extraction, classification, persistence, error branch) as JSON in `n8n/workflows/`; verify the JSON is valid and the flow contains every stage.
- [x] 11.2 Define and export the report workflow that creates and completes report jobs; verify the JSON is valid and references the internal report endpoints.
- [x] 11.3 Implement the app-side trigger and internal endpoints the flows call, including service-token auth and idempotency; verify contract tests for each endpoint and repeated calls.
- [x] 11.4 Implement bounded flow retries, error marking, and no-duplicate behavior in the workflows and app error handling; verify failure-simulation tests end in an error state without duplicate records.
- [x] 11.5 Document workflow import, credentials, and operational recovery in `docs/n8n.md`; verify the import steps are reproducible from a clean n8n instance.

## 12. Docker Compose environment and operations

- [x] 12.1 Create the app Dockerfile (multi-stage, non-root, collected static assets, healthcheck) and verify the image builds and serves the health endpoint.
- [x] 12.2 Create `compose.yaml` with app, OCR, n8n, Paperless-ngx, PostgreSQL, Redis, Ollama, and optional Gotenberg/Tika, including healthchecks, volumes, and networks; verify `docker compose config` succeeds and no internal service publishes a port.
- [x] 12.3 Complete `.env.example` with every required variable, safe placeholders, and comments; verify a script or test confirms every referenced variable is present.
- [x] 12.4 Provide initialization automation for migrations, catalog seed, admin creation, and Ollama model pull; verify the documented fresh-start sequence completes.
- [x] 12.5 Document backup, restore, and update procedures including volumes, PostgreSQL dumps, and pinned image tags in `docs/operations.md`; verify each documented command is syntactically valid.
- [x] 12.6 Apply security hardening (non-root users, internal network, resource limits, no secrets in images, safe logging) and verify with configuration tests and a compose config review.
- [x] 12.7 Write installation, configuration, and usage instructions in `README.md`, linking the operational docs; verify a clean-environment walkthrough follows the document without missing steps.

## 13. Integration fixtures and end-to-end verification

- [x] 13.1 Build a deterministic fixture generator for text PDF, scanned PDF, JPG/PNG/TIFF images, multi-page PDF, incomplete certificate, ambiguous date, unknown entity, and duplicate file; verify generation is repeatable and fixtures are small.
- [x] 13.2 Add an end-to-end pipeline test with fake Paperless, OCR, and Ollama covering a text PDF and a scanned PDF; verify extracted fields, review triggers, and idempotency.
- [x] 13.3 Add end-to-end tests for image input, multi-page input, incomplete certificates, unknown entities, non-certificate documents labeled `Otros`, and duplicate uploads; verify each acceptance criterion is exercised.
- [x] 13.4 Run the documented compose smoke test with a small local model against the sample certificates; verify the flow reaches approved records, a downloadable Excel, and a visible error path.
- [x] 13.5 Verify the full acceptance checklist in `proposal.md` against observed behavior and record the evidence in the change notes.

## Implementation addenda (post-spec intake paths)

- [x] A1. Multi-file upload in the web UI (`documents/views.py`,
  `upload.html`); verified live.
- [x] A2. Watched inbox folder: `documents/services/inbox.py`,
  `watch_inbox` command, `watcher` compose service, `./inbox` bind mount;
  verified live (file dropped → `processed/`, pipeline ran).
- [x] A3. Paperless-first ingestion: `documents/services/paperless_ingest.py`,
  `POST /internal/paperless/webhook/`, Paperless *Document Added* workflow
  provisioned in the deployment; verified live end-to-end.

## Workflow follow-up

- Archive the change after implementation and verification are complete.
- Verify the archived specs and the updated capability inventory.
