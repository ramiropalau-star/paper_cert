# Design

## Context

`process_pdf` currently runs `ocrmypdf.ocr(..., skip_text=True, optimize=0, jobs=1)`, extracts text from the generated PDF, then renders each scanned page from that PDF and runs Tesseract again for confidence. The generated PDF is discarded; only its text is used, and the second Tesseract pass supplies the confidence. For images, `process_image` already uses a single Tesseract pass.

The service has `settings.timeout_seconds`, used both for each Tesseract call and, indirectly, as the only timeout. `render_pdf_page` uses `pypdfium2` at scale 2.0. The Django client (`documents/services/ocr.py`) expects the versioned contract.

## Goals / Non-Goals

**Goals:**

- One recognition pass per scanned page.
- Separate per-page and total request timeouts.
- Preserve the OCR response contract.
- Remove now-unused OCR dependencies and image packages.
- Keep temporary files inside a context-managed directory.

**Non-Goals:**

- Changing the OCR engine or language set.
- Adding deskew/denoise preprocessing beyond what Tesseract receives.
- Parallel page processing (can be evaluated later if CPU allows).

## Decisions

### 1. Render each scanned page from the input PDF and OCR it once

For each page, keep the embedded text when it meets `min_text_chars`. Otherwise render the page from the **input** PDF with `render_pdf_page` and call `run_tesseract_tsv` once. Use that call's text and confidence directly; do not run `ocrmypdf` and do not extract text from a generated PDF.

`ocrmypdf` with `skip_text=True`, `optimize=0`, and `jobs=1` does not add preprocessing that the current path uses; it mainly produces a PDF that is discarded. Removing it reduces the image size and the duplicate recognition.

Alternatives: keep `ocrmypdf` and skip the second Tesseract pass (loses confidence), keep both and accept the cost (current problem). Rejected.

### 2. Enforce a total deadline and a per-page budget

Add `page_timeout_seconds` (default 60) and `request_timeout_seconds` (default 600) to the OCR settings. At request start, compute `deadline = monotonic() + request_timeout_seconds`. Before each page, compute `remaining = deadline - monotonic()`; if `remaining <= 0`, raise a total-timeout `OcrFailure`. Pass `min(page_timeout_seconds, remaining)` to Tesseract.

The per-page timeout error includes the page number in its message and uses a distinct code (`page_timeout`) so the client and logs can distinguish it from `request_timeout`. The Django client's HTTP timeout must be greater than the service's request timeout; document both.

Alternatives: rely only on the client timeout (the service keeps working after the client disconnects), one timeout for both (current problem). Rejected.

### 3. Preserve the contract and update engine metadata

Keep `_page` and `_result` unchanged: `page_number`, `text`, `method`, `confidence`, `mean_confidence`, `quality`, `contract_version`, and `pages`. Update `engine_info()` to report Tesseract as the recognizer and drop the `ocrmypdf` entry. If embedded text is used, the page method stays `embedded` and confidence stays `1.0`.

Alternatives: change the contract to expose per-page timing (not needed by the client). Rejected.

### 4. Remove unused dependencies only after verification

After removing the `ocrmypdf` call, check whether `ocrmypdf`, `pikepdf`, `ghostscript`, and `qpdf` are still imported or executed. Remove them from `requirements.txt` and the Dockerfile if unused. Keep `pypdf`, `pypdfium2`, Pillow, `pillow-heif`, Tesseract language packs, and fonts.

Alternatives: leave the dependencies (larger image, unnecessary attack surface). Rejected.

### 5. Preserve failure semantics

`no_text`, `unreadable`, `too_many_pages`, `file_too_large`, and `empty_file` keep their codes and status codes. Add `page_timeout` and `request_timeout` as retryable 504 errors. Temporary images remain inside `TemporaryDirectory`, so success and failure both clean up.

## Risks / Trade-offs

- Removing `ocrmypdf` may reduce quality on skewed scans → benchmark a sample before rollout; if preprocessing is needed, add an explicit image preprocessor rather than reintroducing a discarded OCR pass.
- Sequential page OCR is slower on multi-page documents → the total timeout and page budget make the limit explicit; parallelism is a separate optimization.
- The client timeout must exceed the service total timeout → document the relationship and validate it in configuration.
- Removing OS packages could break an unexpected code path → grep imports and run the OCR service test target after the change.

## Migration Plan

1. Deploy the new OCR image and set `PAGE_TIMEOUT_SECONDS`/`REQUEST_TIMEOUT_SECONDS` (defaults are safe).
2. Ensure `APP_OCR_TIMEOUT_SECONDS` in the Django app is greater than the service's total timeout.
3. Run the OCR service test target and a multi-page smoke test.
4. Rollback: redeploy the previous OCR image; the contract is unchanged, so the Django client needs no rollback.

## Open Questions

None that change the spec, approach, or task breakdown. Parallel page OCR is a future optimization, not a requirement of this change.
