# Text acquisition

Text acquisition turns the original stored in Paperless-ngx into one
`document_pages` row per page plus a document-level provenance value. The
original is downloaded on demand; no permanent local copy is kept.

## Thresholds

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_EMBEDDED_TEXT_MIN_CHARS` | `30` | Non-whitespace characters a PDF page must contain to be trusted as embedded text. |
| `APP_OCR_MIN_TEXT_CHARS` | `30` | Non-whitespace characters required across the document before text is considered usable. |
| `APP_OCR_LOW_CONFIDENCE_THRESHOLD` | `0.55` | OCR mean confidence below this records a review reason. |
| `APP_PDF_MAX_PAGES` | `100` | Page cap enforced by intake and the OCR service. |
| `APP_OCR_LANGUAGES` | `eng,spa` | Languages forwarded to the OCR service. |

The thresholds count non-whitespace characters with `usable_char_count()`. They
are the documented values in `.env.example`; changing them requires no code
change.

## Decision flow

```text
stored document
  -> download original from Paperless
  -> PDF? extract every page with pypdf
       -> every page at or above embedded threshold: embedded only, no OCR
       -> otherwise: OCR service (skip-text on sufficient pages)
  -> image? OCR service directly
  -> persist page rows and document provenance
  -> text_ready, pending_review, or error
```

- Embedded-only PDFs never call the OCR service.
- Scanned PDFs, image-only PDFs, and images call OCR.
- Mixed PDFs keep the per-page method returned by OCR: sufficient pages remain
  `embedded`, insufficient pages become `ocr`. The document method is `mixed`.
- OCR responses must contain every page in order. A short or reordered response
  is an `incomplete_ocr` error rather than silently missing pages.
- Multi-page PDFs and TIFFs retain page order.

## Provenance

Each `DocumentPage` stores `text`, `method` (`embedded` or `ocr`), and
`ocr_confidence` (only for OCR pages). `Document.text_method` is:

- `embedded` when every page used embedded text;
- `ocr` when every page used OCR;
- `mixed` when both occurred.

The review detail view can show these values directly, satisfying the
provenance requirement without a generated OCR PDF copy.

## States and review reasons

`Document.processing_state` after acquisition:

| Situation | State | Review reason(s) |
| --- | --- | --- |
| Usable text | `text_ready` | none |
| Usable OCR text below confidence threshold | `text_ready` | `low_ocr_confidence` |
| Total text below usefulness threshold | `pending_review` | `insufficient_text` |
| OCR returns no usable text | `pending_review` | `insufficient_text` |
| OCR/parser failure, timeout, missing original | `error` | `ocr_failed`, `unreadable`, `original_unavailable`, etc. |

`Document.review_reasons` is a JSON list. Text-acquisition codes are replaced on
each run; unrelated codes from later stages are preserved. A low-confidence
result still reaches `text_ready` so extraction can run with a warning. An
insufficient-text or error result stops the normal pipeline and appears in the
review/error queue.

When acquisition moves a document to `pending_review` for insufficient text or
to `error`, it applies the configured Paperless `Otros` label. The label is
best-effort: a Paperless failure appends `manual_label_failed` to
`review_reasons` and logs the failure, but never discards page text or changes
the processing outcome. The original remains available in Paperless.

## Idempotency

`acquire_text()` updates existing `document_pages` rows by page number,
removes rows beyond the new page count, and updates the document fields in one
transaction. Repeating acquisition for the same document does not duplicate
rows.

Terminal and downstream states (`extracted`, `classified`, `approved`,
`rejected`, or `pending_review` with a certificate) are skipped. Relevant
processing states (`stored`, `text_ready`, `error`, and text-only
`pending_review`) can be retried.

## Internal endpoint

```text
POST /internal/documents/<id>/text/
X-Internal-Token: <APP_INTERNAL_API_TOKEN>
```

The endpoint accepts no document bytes; it downloads the original from
Paperless by id. It is CSRF-exempt and requires the constant-time internal
token. Repeated calls are idempotent.

Response:

```json
{
  "document_id": 12,
  "state": "text_ready",
  "text_method": "embedded",
  "page_count": 2,
  "review_reasons": [],
  "error": "",
  "skipped": false
}
```

A skipped terminal document returns `skipped: true` and its current values. A
missing document returns 404; an invalid token returns 401.

## Failure handling

- `PaperlessError` while downloading: `error` with `original_unavailable`.
- Unparseable PDF: `error` with `unreadable`; existing pages are preserved.
- OCR timeout/transport/5xx after bounded retries: `error` with `ocr_failed`.
- OCR `no_text`: `pending_review` with `insufficient_text`.
- Label failure: processing result preserved, `manual_label_failed` recorded.
- A later reprocess can retry from `error` or text-only `pending_review`
  without creating a second document.

## Tests

`documents/tests/test_text_acquisition.py` covers embedded-only PDFs skipping
OCR, scanned PDFs, image-only input, mixed PDFs, multi-page order, low
confidence, insufficient text, OCR failure, no-text review, missing originals,
label failure, token enforcement, terminal skipping, and endpoint idempotency.
