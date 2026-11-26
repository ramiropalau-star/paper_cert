# Proposal

## Why

Language certificates arrive as PDFs and images from many exam boards, with inconsistent layouts, languages, and entity naming. Manual transcription into spreadsheets is slow, error-prone, and unauditable. This change delivers a reproducible, self-hosted pipeline that keeps the original document, extracts only what the certificate states, classifies it against an editable catalog, and produces an Excel report while routing uncertain records to a human review loop.

## What Changes

- New dockerized web application for uploading PDFs and images, browsing processed documents, searching extracted data, reviewing/correcting records, and downloading reports.
- Intake pipeline with format, size, and integrity validation; SHA-256-based duplicate detection; storage in Paperless-ngx; and a persistent link between each record and its original document.
- Text acquisition that uses embedded PDF text when sufficient and falls back to OCR for scanned PDFs, image-only PDFs, and supported images (JPG, JPEG, PNG, TIFF), processing every page and recording which method was used.
- Local LLM extraction through Ollama with a strict JSON schema, an explicit no-invention rule, per-field source evidence and confidence, bounded retries on invalid output, and automatic review triggers for missing essential data, ambiguous dates, low confidence, or suspected multiple certificates in one file.
- Language and certifying-entity classification using an editable, extensible catalog with aliases and variants; dual storage of literal and normalized values; distinction between examining entity, issuing body, and test center; unknown entities stay literal and are marked "pending identification"; CEFR level is assigned only when explicit or backed by an approved conversion rule; issue, exam, and result dates are kept distinct.
- Human review workflow with manual editing, approve/reject/reprocess actions, status tracking, review alerts, and an audit history of manual changes and reprocessing.
- Manual-review routing for unrecognized documents: files that are not identified as language certificates, whose language or entity cannot be resolved, or whose processing fails are tagged with a configurable Paperless-ngx label (`Otros` by default) so operators can filter them for manual review; the label is cleared when a record is approved.
- Excel (.xlsx) report generation and download with one row per certificate, required columns, filters, headers, proper date formatting, and a separate sheet for records pending review.
- n8n orchestration of ingestion, OCR, extraction, validation, persistence, and report generation, delivered as exportable flows or documented creation instructions.
- Complete Docker Compose environment (web application, n8n, Paperless-ngx, Ollama, PostgreSQL, optional Redis, OCR) on an internal network, configured through environment variables with a `.env.example`, and persistent Docker volumes.
- Documentation for installation, Ollama model setup, backups, updates, report generation, and error review.

**Non-goals**

- Certifying the authenticity of a certificate. Storing a verification code does not imply validation.
- Automatically converting scores across exams or assigning CEFR levels without an explicit statement or an approved, documented per-exam rule.
- Exposing administrative UIs, databases, or internal services publicly by default.

## Capabilities

### New Capabilities

- `document-ingestion`: upload of PDFs and images, file validation, fingerprint-based duplicate detection, storage and linkage with the document manager, and deletion of documents with their data.
- `text-extraction`: embedded-text detection, OCR fallback for scanned or image documents (including multi-page), OCR language configuration, provenance tracking, and review flags for unreadable input.
- `certificate-extraction`: structured extraction through a local model, schema validation, no-invention and evidence rules, confidence scoring, bounded retries, and extraction-driven review triggers.
- `certificate-classification`: editable catalog of languages, entities, exams, and aliases; entity-role distinction; literal-plus-normalized storage; unknown-entity handling; CEFR and date normalization rules.
- `review-workflow`: review queue and detail view, manual correction, approve/reject/reprocess actions, status indicators, audit history, and a configurable `Otros` label for unrecognized documents awaiting manual identification.
- `excel-reporting`: Excel generation and download, required columns, filters, date formatting, and a separate sheet for pending records.
- `platform-operations`: Docker Compose topology and service configuration, environment-based secrets, persistence volumes, authentication and permissions, error handling and retries, idempotency, and operational documentation.

### Modified Capabilities

None. This is a greenfield project; no existing capabilities or requirements are affected.

## Impact

Greenfield repository. Adds application source code, Dockerfile, compose file, `.env.example`, database schema and migrations, editable seed catalog, n8n flow exports, operational documentation, test fixtures (text PDFs, scanned PDFs, images, multi-page documents, incomplete certificates), and a sample Excel report. External dependencies: Paperless-ngx, n8n, Ollama, PostgreSQL, and an OCR engine. No existing APIs, data, or users are affected.
