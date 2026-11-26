# Verification notes — language-certificate-recognition

Evidence gathered while implementing the change. Test suite: `pytest`
(Django test settings, SQLite in-memory) — all tests green; `ruff check` and
`ruff format` clean on touched packages.

## document-ingestion

- Format/MIME/magic-byte/size/PDF-integrity/page-limit validation:
  `documents/tests/test_validation.py`, `test_intake.py`.
- SHA-256 dedup before Paperless upload: `test_intake.py` duplicate cases,
  E2E `test_duplicate_upload_creates_single_record`.
- Paperless adapter contract: `test_paperless.py` (respx-mocked HTTP).

## text-extraction

- Embedded-first, OCR fallback, per-page method/confidence:
  `test_text_acquisition.py`; OCR client contract `test_ocr.py`.
- E2E: `test_e2e.py::test_text_pdf_end_to_end`,
  `test_scanned_pdf_end_to_end_uses_ocr`, image parametrized cases,
  multipage.

## certificate-extraction

- Versioned prompt + strict JSON schema, Pydantic validation, bounded
  retries, no-invention rule: `test_extraction.py`, `docs/extraction.md`.
- Internal endpoint idempotency/state guards:
  `POST /internal/documents/<id>/extract/` tests in `test_extraction.py`.

## certificate-classification

- Exact alias matching, role separation, CEFR rules, date normalization,
  review-reason aggregation: `test_classification.py`, `docs/classification.md`.
- E2E unknown entity / ambiguous date / incomplete certificate cases in
  `test_e2e.py`.

## review-workflow

- Queue/filters/search/detail/edit/approve/reject/reprocess/history:
  `test_review.py` (20 tests), `docs/review.md`.
- `Otros` Paperless label on approval failure paths: label service tests +
  E2E `test_non_certificate_labeled_otros`,
  `test_unknown_entity_stays_literal_and_reviews`.

## excel-reporting

- Workbook columns, date cells, autofilter, approved-only main sheet,
  `Pendientes de revisión` sheet, filters, no-match error, authorized
  download: `reports/tests/test_reports.py` (11 tests), `docs/reporting.md`,
  sample `docs/examples/report-sample.xlsx`.

## platform-operations

- Compose topology, pinned images, no internal published ports, env coverage,
  Dockerfile hardening, initdb, bootstrap command: `tests/test_ops.py`
  (9 tests), `compose.yaml`, `docker/`, `.env.example`, `docs/operations.md`,
  `docs/n8n.md`, `n8n/workflows/*.json` (validated JSON).
- Internal endpoints use `X-Internal-Token` (`core/internal.py`), contract
  tests in `tests/test_internal_api.py` and per-endpoint tests.

## fixtures and e2e (section 13)

- Deterministic generator `tests/fixturegen.py`; committed outputs in
  `tests/fixtures/files/` verified byte-identical by `test_fixtures.py`.
- Pipeline E2E `documents/tests/test_e2e.py` (12 tests) covering text PDF,
  scanned PDF, JPG/PNG/TIFF, multipage, incomplete, ambiguous date, unknown
  entity, non-certificate, duplicate.
- Compose smoke test: `scripts/smoke.sh` documented in `docs/operations.md`;
  executed against the live stack — see "Live Docker verification" below.

## Live Docker verification (section 13.4)

Executed on the deployment host with the full compose stack
(`qwen2.5:7b-instruct` pulled into Ollama):

- App healthy at `:8090`; Paperless UI published at `:9090`; watcher service
  running.
- Paperless-first ingestion verified end-to-end: `post_document` upload →
  Paperless *Document Added* workflow → `POST /internal/paperless/webhook/`
  → app ingest (dedup + `stored`) → n8n processing flow → text acquisition →
  Ollama extraction → catalog classification → `pending_review` with
  certificate (`cefr_level=B2`). Fixes found during live run: Paperless task
  polling (`related_document_ids`), `{{ doc_id }}` webhook params, n8n
  `$json.body` scoping bug, `ALLOWED_HOSTS` for service names, and missing
  `csrf_exempt` on `internal_run_report`.
- Report jobs executed through the n8n report workflow reached `ready` with
  generated `.xlsx` artifacts under `/data/reports`.

## Addendum: UV L2 equivalence, validated state, in-app viewer, Paperless tags

Post-spec enhancements verified live on the Docker stack:

- `catalog.Equivalence` seeded from the UV "Taula d'Equivalències L2" PDF
  (24 pages, coordinate-based extraction): 186 equivalences across eng,
  spa, deu, fra, ita, por, rus, zho; catalog grew to 170 exams / 35
  entities. `certificate.equivalence` resolves score-banded rules first,
  unbanded fallback; unmapped exams add `equivalence_not_found` and stay
  in review. Verified live: B2 First -> equivalence `B2`.
- `review_status=validated` with audit event; validated records appear in
  the report pending sheet as "Validado" until approved.
- `GET /documents/<id>/original/` proxies the Paperless original inline;
  review detail renders a split view (editable data left, document right)
  at full viewport height (`X_FRAME_OPTIONS=SAMEORIGIN`).
- Paperless classification tags (`Idioma:`, `Nivel:`, `Entidad:`,
  `Examen:`, `Equivalencia UV L2:`) synced on classify and manual edit;
  verified live on existing documents.
- 227 tests green; ruff clean; migrations applied; seed re-run live.
