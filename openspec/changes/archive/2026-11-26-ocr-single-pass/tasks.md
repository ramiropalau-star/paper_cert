# Tasks

## 1. Single-pass PDF recognition

- [x] 1.1 Replace the `ocrmypdf` path in `ocr-service/app.py` with per-page rendering from the input PDF and one Tesseract call per scanned page; verify scanned and mixed embedded/OCR PDFs with service tests.
- [x] 1.2 Remove the generated output PDF and any second text-extraction pass; verify no code path invokes a second OCR engine for the same page.

## 2. Timeout separation

- [x] 2.1 Add `page_timeout_seconds` and `request_timeout_seconds` to the OCR settings and enforce a total deadline with a per-page budget; verify multi-page success, page timeout, and total timeout with service tests.
- [x] 2.2 Document the relationship between the service request timeout and the Django `APP_OCR_TIMEOUT_SECONDS`, and verify the defaults are compatible.

## 3. Contract and engine metadata

- [x] 3.1 Keep the response fields unchanged and update `engine_info()` to report only the recognizer actually used; verify the Django OCR client parses the response with existing tests.
- [x] 3.2 Ensure embedded pages remain `embedded` with confidence 1.0 and scanned pages remain `ocr` with their measured confidence; verify with mixed-page tests.

## 4. Cleanup and dependencies

- [x] 4.1 Remove `ocrmypdf`, `pikepdf`, `ghostscript`, and `qpdf` from the OCR image if they are no longer imported or executed; verify the OCR Docker test target builds and passes.
- [x] 4.2 Verify temporary page images are removed on success and on failure; add or adjust tests for both paths.

## 5. Integration verification

- [x] 5.1 Run the OCR service test target, the Django OCR tests, and a multi-page smoke test; record the observed results.
- [x] 5.2 Benchmark one representative scanned PDF before and after the change and record the per-page time and total time; confirm no contract regression.
- [x] 5.3 Run `openspec validate ocr-single-pass --strict` and fix any artifact issues.

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Verify the archived `ocr-processing` spec and the resulting capability baseline.
