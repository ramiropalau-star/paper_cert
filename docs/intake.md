# Intake, validation, and Paperless integration

## Supported files

- PDF (`.pdf`)
- Images: JPG/JPEG (`.jpg`, `.jpeg`), PNG (`.png`), TIFF (`.tif`, `.tiff`),
  WebP (`.webp`), BMP (`.bmp`), GIF (`.gif`), HEIC (`.heic`),
  HEIF (`.heif`), AVIF (`.avif`)

Before validation, `preprocess_upload` sniffs the payload with `python-magic`
and repairs the filename when the extension is missing or unknown: the real
type decides the extension (`certificate` → `certificate.pdf`,
`certificate.txt` containing a PNG → `certificate.png`). HEIC/HEIF files are
decoded through `pillow-heif`, which is registered in both the Django app and
the OCR service.

Validation rejects unsupported extensions, disallowed declared MIME types,
content that does not match the extension (magic-byte sniffing with
`python-magic`), empty files, corrupt PDFs, encrypted PDFs, corrupt images,
files over `APP_UPLOAD_MAX_BYTES`, and PDFs over `APP_PDF_MAX_PAGES`.

Defaults:

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_UPLOAD_MAX_BYTES` | `26214400` (25 MiB) | Maximum upload size. |
| `APP_PDF_MAX_PAGES` | `100` | Maximum pages in a PDF. |
| `APP_MEDIA_ROOT` | `/data/media` | Staging directory parent. |

`core.middleware.RequestSizeLimitMiddleware` rejects oversized requests from
`Content-Length` with HTTP 413 before the view runs. Intake validates the file
again, so the limit is enforced for direct service calls too.

## Staging

Validated bytes are written under `MEDIA_ROOT/staging/` with a random UUID
filename. The staging file exists only while the original is posted to
Paperless-ngx and is removed in a `finally` block, including on failure.

## Pipeline

```text
upload -> validate -> SHA-256 fingerprint -> duplicate check
       -> documents row (received) -> Paperless post + poll (stored)
       -> staging cleanup
```

- Duplicate detection uses SHA-256 across the whole file. A repeated upload
  returns the existing `Document`; no second document or certificate row is
  created.
- The `Document` row is created before the Paperless call so failures are
  visible. A Paperless failure sets `processing_state=error` and stores the
  reason in `error_reason`.
- A successful Paperless task stores `paperless_document_id` and moves the
  document to `stored`. A certificate row is created later by classification.
- The app does not keep a permanent local copy.

## Paperless-ngx configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_PAPERLESS_URL` | `http://paperless:8000` | Paperless base URL. |
| `APP_PAPERLESS_TOKEN` | empty | API token (`Authorization: Token ...`). |
| `APP_PAPERLESS_OTHER_TAG` | `Otros` | Tag for unrecognized/manual-review documents. |
| `APP_PAPERLESS_TIMEOUT_SECONDS` | `30` | HTTP timeout. |
| `APP_PAPERLESS_POLL_INTERVAL_SECONDS` | `1` | Task polling interval. |
| `APP_PAPERLESS_POLL_TIMEOUT_SECONDS` | `60` | Maximum wait for storage. |

The `DocumentStore` adapter in `documents/services/paperless.py` owns these
Paperless assumptions:

- `POST /api/documents/post_document/` uploads the file and returns a task id.
- `GET /api/tasks/?task_id=...` is polled until `SUCCESS` or `FAILURE`;
  `related_document` becomes `paperless_document_id`.
- `GET /api/documents/{id}/download/` returns the original.
- `DELETE /api/documents/{id}/` deletes the original.
- Tags are ensured, added, and removed through `/api/tags/` and
  `PATCH /api/documents/{id}/`.

HTTP 5xx, 429, timeouts, and transport errors are retryable
`PaperlessError`s; other 4xx responses are non-retryable. The token is never
logged.

### Manual-review label

Paperless-ngx uses tags instead of folders. The configured `Otros` tag is
applied by classification to non-certificate documents, unresolved language or
entity records, and processing failures; approval removes it. If tagging fails,
the app records the failure and keeps the document in the review queue.
Operators can map the tag to a Paperless storage path for a folder-like view.

## Deletion

Only members of the `admin` group (or superusers) can delete. The view first
deletes the original from Paperless; if that fails, the local record is kept and
the operator sees an error. On success, the document and its pages, certificate,
and review events are removed by cascade.

## Tests

`documents/tests/test_validation.py` covers every rejection path and valid PDF/
PNG input. `documents/tests/test_paperless.py` uses `respx` for post/poll,
failure, timeout, download, delete, and tag contracts.
`documents/tests/test_intake.py` covers staging cleanup, duplicate handling,
Paperless error persistence, upload views, and authorized deletion.
