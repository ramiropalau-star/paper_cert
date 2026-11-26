# Tasks

## 1. Document list filter tolerance

- [x] 1.1 Extract the document-list filter/queryset logic from `documents/views.py` into a dedicated module (e.g. `documents/filters.py`); verify `documents` view tests still pass unchanged.
- [x] 1.2 Apply the `language_id`/`entity_id` branches only for numeric values and always keep the literal `icontains` branch; verify `?language=abc` and `?entity=abc` return 200 with literal matches in view tests.
- [x] 1.3 Audit the remaining GET filters (`state`, `q`, `organism`, `level`, `issue_date`) for the same failure class and fix any that can raise; verify each with a parameterized view test.

## 2. Deployment port consistency

- [x] 2.1 Resolve `APP_PORT` once in `deploy.sh` via `env_val` with default `8080`, export it for the health check, and interpolate it into the generated `DJANGO_CSRF_TRUSTED_ORIGINS`; verify a fresh-deploy run writes origins on the configured port.
- [x] 2.2 Replace the remaining `8090` fallbacks (health check, banner) with the resolved value; verify `deploy.sh` shellcheck/`bash -n` passes and the documented commands in `docs/operations.md` still match.

## 3. Shared service helpers

- [x] 3.1 Add a shared reason-merge helper parameterized by owned reason codes; verify unit tests cover ordering, dedupe, and per-stage code ownership for text, extraction, and classification.
- [x] 3.2 Migrate `text.py`, `extraction.py`, and `classification.py` to the shared helper; verify the existing service tests pass and `review_reasons` content is unchanged for each stage.
- [x] 3.3 Add shared sniff/name helpers that accept the caller's MIME allowlist and extension map; verify unit tests reproduce each stage's current accept/reject behavior.
- [x] 3.4 Migrate `text.py` and `paperless_ingest.py` to the shared helpers; verify upload, Paperless-ingest, and sniffing tests pass, including HEIC/image-archive cases.

## 4. Dead code and module size

- [x] 4.1 Delete `snapshot_certificate` from `documents/services/review.py` after confirming zero references; verify `grep` finds no callers and the full test suite passes.
- [x] 4.2 Confirm `documents/views.py` is reduced to HTTP handling after the filter extraction; verify no view behavior changed via the existing view test suite.

## 5. Integration verification

- [x] 5.1 Run the full suite (`pytest`), `python manage.py check`, and `bash -n deploy.sh`; record the observed results.
- [x] 5.2 Run `openspec validate edge-case-hardening --strict` and fix any artifact issues.

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Verify the archived `review-workflow`, `platform-operations`, and `code-health` specs and the resulting capability baseline.
