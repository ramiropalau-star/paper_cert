# Proposal

## Why

The post-implementation audit found three gaps that no pending change covers: the document list returns HTTP 500 on malformed filter values, `deploy.sh` verifies and configures a hardcoded port that disagrees with `.env.example` and `compose.yaml`, and several service helpers are duplicated or dead, which makes future fixes risk diverging copies.

## What Changes

- Make the `/documents/` list filters (`language`, `entity`) tolerant of non-numeric values: match the literal fields only and never raise `ValueError`/500. Audit other GET filters for the same class of bug.
- Fix `deploy.sh` so the application port is read from `.env` (default matching `.env.example`/compose, 8080) everywhere it is used: health check, final banner, and `DJANGO_CSRF_TRUSTED_ORIGINS` generated on first deploy.
- Deduplicate the reason-merging helpers (`_reason_list` in `text.py`/`extraction.py`, `_merge_reasons` in `classification.py`) and the sniffing/name helpers (`_sniffed_type`, `_effective_name` in `text.py`/`paperless_ingest.py`) into shared modules, preserving each caller's reason-code ownership and MIME allowlist.
- Remove dead code (`snapshot_certificate` in `documents/services/review.py`) and extract the document-list filtering logic out of the 768-line `documents/views.py` into a dedicated module.

## Capabilities

### New Capabilities

- `code-health`: Internal code quality requirements — shared helpers, no dead code, bounded view modules.

### Modified Capabilities

- `review-workflow`: Document search/filtering tolerates invalid filter values without server errors.
- `platform-operations`: Deployment script uses the configured application port consistently for health checks, trusted origins, and operator output.

## Impact

- `documents/views.py` (filter handling, module split), new `documents/filters.py` (or similar), `documents/services/{text,extraction,classification,paperless_ingest,review}.py`.
- `deploy.sh`, possibly `docs/operations.md`.
- No API, schema, or dependency changes. Behavior change is limited to: invalid filter params no longer 500, and fresh deploys configure the correct port.
