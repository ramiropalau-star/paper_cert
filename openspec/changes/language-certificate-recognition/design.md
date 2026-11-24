# Design

## Context

Greenfield repository: only OpenSpec scaffolding exists, so every component is new. The system runs self-hosted with Docker and must use Paperless-ngx as the document manager, n8n as the orchestrator, and Ollama for local inference. See `proposal.md` for motivation and `specs/` for the behavior contract. Relevant constraints:

- Certificates arrive in many languages and layouts; the model must extract only what is printed.
- The catalog of languages, entities, and exams must change without code changes.
- The user-facing interface and Excel labels are specified in Spanish; code, prompts, logs, and technical documentation are in English.
- The system must not assert authenticity or convert scores without an approved rule.

## Goals / Non-Goals

**Goals:**

- A reproducible single-host Docker stack with internal services unreachable from outside.
- A deterministic, auditable path: upload -> text acquisition -> extraction -> classification -> review -> approved report.
- Replaceable OCR engine and configurable LLM model.
- Idempotent processing keyed by document fingerprint and document id.

**Non-Goals:**

- Certificate authenticity verification, external code validation, or score equivalence beyond approved rules.
- Multi-tenant operation, horizontal scaling, or high availability.
- Automatically splitting a file that contains several certificates.
- Fuzzy or probabilistic entity matching.

## Decisions

### Application stack: Django + server-rendered UI

Use Python 3.12, Django 5.x, PostgreSQL 16, Django templates with HTMX, Gunicorn, and Django's ORM/migrations. Use Django admin for catalog and user administration, and Django auth for sessions and permissions.

- Rationale: authentication, permissions, CSRF protection, migrations, and an admin UI for the editable catalog come built in, which directly satisfies several requirements without custom infrastructure.
- Alternatives considered: FastAPI + SPA (more moving parts, requires custom auth/admin/session handling), Flask (no batteries), Django REST + separate frontend (unnecessary complexity for a single-team tool).

### Orchestration boundary: n8n sequences, Django owns logic

n8n flows call authenticated internal endpoints by document id; the Django service layer performs each step and persists state. n8n owns sequencing, handoffs, and workflow-level retries. Internal payloads carry ids and filter objects, never document bytes.

- Rationale: n8n satisfies the orchestration requirement while business rules remain unit-testable and versioned in Python. Flows stay small and auditable.
- Alternatives considered: embedding extraction/classification logic in n8n Code nodes (hard to test and reuse), Celery-only pipeline (does not meet the n8n requirement).

### Document storage: Paperless-ngx behind a thin adapter

Accepted originals are posted to Paperless-ngx through its API, and the app stores `paperless_document_id` plus a fingerprint. A small `DocumentStore` adapter isolates Paperless assumptions so a local-volume store could be substituted. Duplicate detection uses SHA-256 in the application database before upload. OCR runs on temporary copies; derived text is stored in the database, and no permanent OCR PDF copy is kept (the spec only requires linking one if generated).

Paperless-ngx has tags rather than folders, so manual-review routing uses a configurable tag: `APP_PAPERLESS_OTHER_TAG` (default `Otros`). The adapter ensures the tag exists, applies it idempotently to documents that are not language certificates, whose language or entity cannot be resolved, or whose processing fails, and removes it when a reviewer approves the record. Tag failures are logged and retried without blocking processing or the app review queue; operators can additionally map the tag to a Paperless storage path if they want a folder-like layout.

- Rationale: Paperless remains the repository of record, while deduplication and lifecycle are controlled by the app.
- Alternative considered: storing PDFs locally only (simpler, but contradicts the required architecture).

### Text acquisition: per-page decisions with recorded provenance

Use pypdf to measure non-whitespace characters per page. Pages below a configurable threshold go through OCR; pages above it use embedded text. Mixed PDFs use OCRmyPDF with `--skip-text`. Images go directly to OCR. Store one `document_pages` row per page with its text, method (`embedded` or `ocr`), and OCR confidence. The document-level method is `embedded`, `ocr`, or `mixed`. Low OCR confidence or insufficient resulting text flags review.

- Rationale: per-page provenance is more truthful than a single document label and supports the review indicator.
- Alternative considered: always OCR (slow, discards reliable embedded text).

### OCR service: dedicated stateless container

A separate `ocr` service (FastAPI + OCRmyPDF/Tesseract, non-root) exposes a versioned HTTP contract: submit a file or document id plus language list, receive page texts, engine version, and mean confidence. Timeouts and page limits are enforced. The Django app talks to it through an OCR client interface.

- Rationale: isolates CPU/memory spikes from the web app and makes engine substitution a container swap behind a stable contract.
- Alternatives considered: OCR inside the web container (resource coupling), cloud OCR (conflicts with self-hosting).

### Extraction: one structured Ollama call with strict validation

Call Ollama `POST /api/chat` with a versioned Spanish/English-agnostic extraction prompt, `format` set to the JSON schema, temperature 0, and the text delimited as untrusted content. The schema covers: certificate detection, multiple-certificate suspicion, field values with `evidence` (page + quote) and `confidence`, literal level and score, candidate date objects, and certificate code. Validate with Pydantic; retry at most twice on schema/JSON failure; then route to review. Inputs above a configured character cap are routed to review instead of being silently truncated. Store the prompt version with each extraction.

- Rationale: schema-constrained output plus deterministic validation is the strongest defense against invention and malformed data.
- Default model: `qwen2.5:7b-instruct` (multilingual, supports structured output), configurable via `OLLAMA_MODEL`.
- Alternatives considered: regex per issuer (unmaintainable across dozens of formats), hosted LLM APIs (not local).

### Classification: catalog data with exact alias matching

Catalog tables: `languages`, `entities`, `entity_aliases`, `exams`, `cefr_conversion_rules`. Matching normalizes with NFKC + casefold + whitespace collapse and requires an exact alias match; no fuzzy assignment. Literal printed text is always retained next to the normalized value. Unknown entities get the status label "Entidad pendiente de identificar" and review. CEFR is only set from an explicit statement or an active, approved rule whose score range matches; rule use is recorded. Dates are parsed with explicit formats and dateutil; ambiguous day/month or untyped dates become `detected_date` and trigger review. Issue, exam, and result dates are separate columns; original date text is retained.

- Rationale: matches the "never guess" behavior and keeps the catalog authoritative.
- Alternative considered: trigram similarity (silently misclassifies similar names).

### Data model

Core tables:

- `documents`: fingerprint (unique), original filename, MIME type, size, Paperless id, storage state, page count, text method, processing state, error reason, timestamps, uploader.
- `document_pages`: document, page number, text, method, OCR confidence.
- `certificates`: one per document (unique FK), student name, language literal/id, entity literal/id, issuing body literal, test center literal, exam literal/id, level literal, CEFR value/source, score literal, issue/exam/result/detected dates, original date text, certificate code, extraction evidence (JSONB), per-field and overall confidence, certificate flag, multiple-certificate flag, review status, review reasons, timestamps.
- `review_events`: certificate, event type (`edit`, `approve`, `reject`, `reprocess`), actor, timestamp, before/after payload, reason.
- `report_jobs`: requester, filters, state, artifact path, timestamps.
- Django auth tables for users, groups, and permissions; catalog tables above.

State machine: `received -> stored -> text_ready -> extracted -> classified -> pending_review -> approved | rejected`, with `error` reachable from processing steps. Reprocessing preserves the record, appends history, and returns the certificate to `pending_review`. Review reasons include missing essential fields, unknown language or entity, ambiguous dates, low confidence, multiple certificates, non-certificate documents, and processing failures; the same conditions that prevent automatic recognition also apply the `Otros` Paperless label.

- Rationale: a single certificate row per document honors the duplicate rule; multi-certificate files are flagged rather than auto-split.
- Trade-off: supporting true multi-certificate files later requires a schema change.

### Review and reporting

Every extraction starts in `pending_review`; approval is required for the main report. Manual edits update current values and append an `edit` event with before/after data. Reports are asynchronous `report_jobs`: the UI creates a job with filters, n8n triggers generation, the app writes an `.xlsx` with openpyxl (write-only mode) into a mounted volume, and the UI polls state before download. Main sheet contains approved records; the optional "Pendientes de revisión" sheet contains pending ones with an explicit status column. Dates are written as Excel date values. Columns: Alumno, Idioma, Nivel, Nivel MCER, Entidad certificadora, Fecha de expedición, Certificado o examen, Puntuación, Estado, Fecha de procesamiento, Referencia al documento.

- Rationale: async jobs avoid request timeouts and keep n8n in the reporting path.
- Alternative considered: synchronous download (simpler, but conflicts with orchestration and large sets).

### Security and operations

- Session cookies (`HttpOnly`, `SameSite=Lax`, `Secure` configurable) for the UI; CSRF protection on state changes.
- Internal API under `/internal/` requires a constant-time-checked service token from the environment; it is rejected if the token is absent or mismatched. Tokens are never logged.
- Roles via Django groups: `viewer` (read/download), `reviewer` (edit/approve/reject/reprocess), `admin` (catalog/users/deletion).
- Upload controls: extension + MIME + magic-byte sniffing, size cap, page cap, PDF parse validation, randomized staging names, temporary files removed after processing.
- Internal services publish no ports; only the app entry point is mapped. A single user-defined bridge network isolates service DNS; optional egress restriction is documented for hardened deployments.
- JSON structured logs include request id, document id, step, and outcome; they exclude extracted text, evidence quotes, and field values.
- Bounded retries with exponential backoff for Paperless, Ollama, and OCR transient failures; exhaustion sets `error`.

### Docker topology

Services: `app` (Gunicorn, port mapped), `ocr`, `n8n`, `paperless` (webserver), `db` (PostgreSQL with separate databases for app, Paperless, and n8n), `redis` (Paperless broker/cache), `ollama`, and Gotenberg/Tika only if required by the pinned Paperless release. Volumes: `postgres-data`, `paperless-data`, `paperless-media`, `n8n-data`, `ollama-models`, `app-media` (staging), `reports`. `.env.example` documents every variable with safe placeholders. Images are pinned; healthchecks gate dependent services; initialization is a documented sequence (migrations, seed, superuser, model pull, n8n import).

- Rationale: one database server reduces footprint; separate databases keep ownership clean.
- Alternative considered: one Postgres per service (more isolation, more memory and ops overhead).

### Testing strategy

- pytest + pytest-django; factory-based fixtures; respx to fake Paperless/Ollama/OCR HTTP contracts.
- Generated fixtures: text PDF, scanned PDF, image, multi-page PDF, incomplete certificate, ambiguous date, unknown entity, duplicate file.
- Unit tests for validation, fingerprints, date parsing, alias matching, CEFR rules, state transitions, report columns, and idempotency.
- Excel assertions by reading the generated workbook back with openpyxl.
- A documented compose smoke test covers the full path with a stub model or a small local model.

## Risks / Trade-offs

- [Model hallucination] -> Schema-constrained output, no-invention prompt rules, per-field evidence, confidence thresholds, mandatory human approval.
- [Prompt injection inside documents] -> Text is delimited as untrusted, no tool calls, strict schema, deterministic post-validation.
- [OCR errors on poor scans] -> Confidence thresholds, insufficient-text flags, reviewer access to the original.
- [Paperless API drift] -> Pinned image version, thin adapter, contract tests against recorded responses.
- [n8n as orchestration bottleneck] -> Flows exported in the repo, steps callable independently, error states allow requeue.
- [Shared PostgreSQL contention] -> Separate databases, connection limits, documented upgrade path to dedicated instances.
- [Large files exhausting resources] -> Size and page caps, OCR timeouts, dedicated container with limits.
- [Catalog quality] -> Seeded data, admin editing, auditability, review for unknown entities.
- [Ambiguous dates] -> Never assign a category blindly; store `detected_date` and require review.

## Migration Plan

Greenfield; no data migration. Deployment sequence: copy `.env.example` to `.env` and fill secrets, build images, start `db` and `redis`, run migrations and catalog seed, create the admin user, start the remaining services, pull the Ollama model, import n8n flows, run the smoke test. Rollback: keep volumes, redeploy the previous pinned image tags, and restore PostgreSQL dumps plus volume backups if a migration must be reverted. Backups cover `postgres-data`, `paperless-data`, `paperless-media`, `n8n-data`, and `ollama-models`.
