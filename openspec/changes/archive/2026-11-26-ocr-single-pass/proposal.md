# Proposal

## Why

The OCR service runs two recognition passes over scanned pages: `ocrmypdf` produces a PDF that the service does not return, and then Tesseract runs again on each rendered page just to obtain text and confidence. This roughly doubles the cost of the slowest stage. The request timeout is also equal to the per-page timeout, so a multi-page PDF can fail because the whole request exceeded a limit intended for one page.

## What Changes

- **Single recognition pass**: render each page once and run Tesseract once, using its TSV output for both text and confidence. Remove the redundant `ocrmypdf` OCR call and the unused PDF artifact.
- **Separate timeouts**: add a per-page timeout and a total request timeout; a multi-page document completes when each page fits its budget and the total fits the request budget.
- **Stable contract**: preserve the versioned OCR response fields (`page_number`, `text`, `method`, `confidence`, `mean_confidence`, `quality`, `contract_version`, `engine`).
- **Explicit failures**: a page timeout is reported as a structured, retryable error that identifies the page instead of silently dropping it.
- **Tests and documentation**: cover one recognition call per page, multi-page timeout behavior, contract compatibility, and the new environment variables.

## Capabilities

### New Capabilities

- `ocr-processing`: durable behavior for converting document pages to text and confidence with a single recognition pass, bounded per-page and total time, and a stable service contract.

### Modified Capabilities

None.

## Impact

- **Service**: `ocr-service/app.py`, `ocr-service/Dockerfile`, `ocr-service/requirements.txt`.
- **Configuration**: OCR timeout variables and `.env.example`.
- **Clients**: `documents/services/ocr.py` consumes the same contract; timeout defaults may change.
- **Risk**: removing `ocrmypdf` may change recognition quality on skewed or low-quality scans; benchmark before rollout and keep preprocessing only if it demonstrably helps.
