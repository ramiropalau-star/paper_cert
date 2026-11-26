# OCR service

The OCR stage is an isolated, stateless FastAPI service. It has its own image,
runs as a non-root user, and talks to the Django app only through a versioned
HTTP contract. CPU and memory spikes stay out of the web container, and the
engine can be replaced by swapping the container while the contract stays
stable.

## Image

`ocr-service/Dockerfile` uses `python:3.12-slim`, installs Tesseract with the
English and Spanish language packs, and DejaVu fonts, then installs pinned
Python dependencies. The runtime stage runs as UID `10001`.

```bash
docker build -t paperless-ocr:dev ocr-service
docker run --rm -p 8000:8000 paperless-ocr:dev
curl http://127.0.0.1:8000/health
```

`GET /health` returns `200` with the contract version and engine versions when
Tesseract is available; otherwise it returns `503` with `status: "degraded"`.

The test stage includes pytest, httpx, and reportlab:

```bash
docker build --target test -t paperless-ocr:test ocr-service
docker run --rm paperless-ocr:test
```

## Contract

`POST /v1/ocr` accepts `multipart/form-data`:

| Field | Required | Meaning |
| --- | --- | --- |
| `file` | yes | PDF or image: JPG/JPEG, PNG, TIFF, WebP, BMP, GIF, HEIC, HEIF, AVIF. |
| `languages` | no | Comma-separated Tesseract languages, for example `eng,spa`. Defaults to `OCR_LANGUAGES`. |
| `page_limit` | no | Maximum pages or TIFF frames. `0` uses `OCR_PAGE_LIMIT`. |

Successful response:

```json
{
  "contract_version": "v1",
  "engine": {
    "name": "tesseract",
    "tesseract": "tesseract 5.5.0"
  },
  "page_count": 2,
  "mean_confidence": 0.91,
  "quality": "ok",
  "pages": [
    {
      "page_number": 1,
      "text": "LANGUAGE CERTIFICATE B2",
      "method": "ocr",
      "confidence": 0.93
    },
    {
      "page_number": 2,
      "text": "Embedded page text",
      "method": "embedded",
      "confidence": 1.0
    }
  ]
}
```

- `method` is `embedded` when the original PDF page already had enough text and
  `ocr` when OCR was required.
- `mean_confidence` is the mean Tesseract word confidence over OCR pages only;
  pages with embedded text count as `1.0` individually but do not dilute the OCR
  mean.
- `quality` is `low` when OCR pages exist and their mean confidence is below
  `OCR_LOW_CONFIDENCE_THRESHOLD`. The request still succeeds so the app can
  retain the text and send it to manual review.

Error response:

```json
{
  "error": {
    "code": "no_text",
    "message": "OCR produced too little usable text",
    "retryable": false
  }
}
```

| Code | HTTP | Retryable | Meaning |
| --- | --- | --- | --- |
| `empty_file` | 400 | no | Zero-byte upload. |
| `unsupported_file` | 400 | no | Not a supported PDF or image. |
| `file_too_large` | 413 | no | Exceeds `OCR_MAX_UPLOAD_BYTES`. |
| `too_many_pages` | 422 | no | Exceeds the page/frame cap. |
| `unreadable` | 422 | no | Corrupt PDF, encrypted PDF, unreadable image, or OCR engine failure. |
| `no_text` | 422 | no | OCR text is below the usefulness threshold. |
| `page_timeout` | 504 | yes | A single page exceeded `OCR_PAGE_TIMEOUT_SECONDS` or the remaining request budget; the message names the page. |
| `request_timeout` | 504 | yes | The whole request exceeded `OCR_REQUEST_TIMEOUT_SECONDS`. |

## PDF handling

1. The service reads the embedded text of every page with pypdf.
2. If every page meets `OCR_MIN_TEXT_CHARS`, it returns embedded text and does
   not run OCR.
3. Otherwise each page without enough embedded text is rendered once from the
   input PDF with pypdfium2 and sent to a single Tesseract TSV pass. Mixed
   PDFs keep `method: "embedded"` on text pages and `method: "ocr"` on scanned
   pages, page by page.
4. Each OCR page gets its confidence from the TSV word confidences of that
   same pass; there is no second recognition pass and no intermediate OCR'd
   PDF.

Images (including HEIC/HEIF via `pillow-heif`) and multi-page TIFFs are OCR'd
frame by frame with the same TSV confidence path. Page order is preserved and
no page is silently dropped.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `OCR_LANGUAGES` | `eng,spa` | Default Tesseract languages. |
| `OCR_PAGE_TIMEOUT_SECONDS` | `60` | Maximum Tesseract time per page. |
| `OCR_REQUEST_TIMEOUT_SECONDS` | `600` | Total budget for the whole request; also caps the HTTP wait. |
| `OCR_PAGE_LIMIT` | `100` | Default page/frame cap. |
| `OCR_MIN_TEXT_CHARS` | `20` | Minimum usable characters per page and overall. |
| `OCR_LOW_CONFIDENCE_THRESHOLD` | `0.55` | Mean OCR confidence below this is `quality: "low"`. |
| `OCR_MAX_UPLOAD_BYTES` | `26214400` | Upload size cap. |

The Django app sends `APP_OCR_LANGUAGES` on every request, so changing the app
configuration changes OCR without code changes. The contract test
`test_configured_languages_are_forwarded` verifies that the selected languages
reach the Tesseract call.

## App-side client

`documents/services/ocr.py` provides `OcrClient` and `build_ocr_client()`.
The client:

- posts to `/v1/ocr` with the configured languages and `APP_PDF_MAX_PAGES`;
- applies `APP_OCR_TIMEOUT_SECONDS`, which must stay above the service
  `OCR_REQUEST_TIMEOUT_SECONDS` so the service reports its own timeout first
  (default `660` vs `600`); the gunicorn worker timeout (`720`) must in turn
  stay above `APP_OCR_TIMEOUT_SECONDS`;
- retries transport errors, timeouts, HTTP 429, and 5xx at most
  `APP_OCR_RETRIES` times;
- raises typed `OcrError` values with `code`, `retryable`, and `status_code`;
- rejects malformed success payloads instead of guessing.

`documents/tests/test_ocr.py` covers success, transient failure, retry
exhaustion, service error mapping, timeouts, malformed responses, and
configuration overrides.

## Engine substitution

Downstream stages consume only `pages[].text`, `pages[].method`,
`pages[].confidence`, `mean_confidence`, `quality`, and engine metadata. Any
engine behind the same contract can replace this container without changing
Django extraction, classification, review, or reporting behavior. The app-side
client must not depend on engine-specific fields beyond `engine.name` and the
reported versions.
