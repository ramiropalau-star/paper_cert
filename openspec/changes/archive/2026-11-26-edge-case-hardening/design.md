# Design

## Context

See proposal.md for motivation. Relevant current state:

- `documents/views.py` (768 lines) builds the document list queryset inline in `_filter_documents`. `language`/`entity` params are passed straight into `certificate__language_id=` / `certificate__entity_id=`; Django raises `ValueError` on non-numeric input → 500. Other filters (`state`, `q`, `organism`, `level`, `issue_date`) already degrade gracefully.
- `deploy.sh` reads `.env` values only via `env_val()` for the final banner, but line ~94 hardcodes `:8090` in `DJANGO_CSRF_TRUSTED_ORIGINS`, line ~243 uses `${APP_PORT:-8090}` from the shell environment (which is never exported from `.env`), and line ~265 defaults the display port to 8090 — while `.env.example` and `compose.yaml` default to 8080.
- Reason merging is copy-pasted three times with only the owned-code set differing: `_reason_list` in `text.py` (`TEXT_REASON_CODES`), `_reason_list` in `extraction.py` (`EXTRACTION_REASON_CODES`), `_merge_reasons` in `classification.py` (`CLASSIFICATION_REASON_CODES`). All three keep reasons not owned by the stage and append/dedupe the stage's fresh reasons.
- `_sniffed_type`/`_effective_name` exist in both `text.py` and `paperless_ingest.py` but are NOT identical: `paperless_ingest` filters the sniffed MIME against `_SNIFFED_TYPES` and maps via `_EXTENSION_BY_TYPE`; `text.py` returns any sniffed MIME and maps via `_EXTENSION_BY_MIME`. They must be unified behind parameters, not blindly merged.
- `snapshot_certificate` in `documents/services/review.py` has zero callers.

## Goals / Non-Goals

**Goals:**
- Invalid list filters never produce 5xx; behavior for valid filters unchanged.
- `deploy.sh` has a single source of truth for the app port matching `.env.example`/compose.
- One shared implementation for reason merging and sniff/name helpers; dead code removed; filter logic out of `views.py`.

**Non-Goals:**
- Changing filter semantics (e.g., making `language=abc` an exact-id-only filter) — literal fallback stays.
- Splitting `views.py` beyond extracting the filter/queryset helpers.
- Touching `security-hardening` scope (it already covers request-size middleware and webhook auth).

## Decisions

- **Filter fix**: in the extracted filter module, apply `language_id`/`entity_id` branches only when the value `.isdigit()`; always keep the `*_literal__icontains` branch. Alternative considered: try/except `ValueError` around the queryset — rejected because the `Q` object is built before evaluation; validating the param up front is clearer and testable.
- **Port fix**: resolve the port once near the top of `deploy.sh` via `env_val APP_PORT` with default `8080` (matching `.env.example`/compose), export it as `APP_PORT` for the health check, and interpolate it into the generated `DJANGO_CSRF_TRUSTED_ORIGINS`. Rationale: one resolution point removes the three divergent hardcodings. Note `env_val` greps `.env`, which exists by the time CSRF origins are written (the `.env` block runs first).
- **Shared helpers**: create `documents/services/review_reasons.py` (or add to an existing shared module) exporting `merge_review_reasons(existing, fresh, owned_codes)`. Each stage passes its own constant. For sniffing, create `documents/services/filetype.py` exporting `sniffed_type(data, allowed_mimes=None)` and `effective_name(filename, content_type, extension_map)`; `paperless_ingest` passes its allowlist/map, `text.py` its own. Alternative considered: keep per-stage wrappers — rejected, wrappers would just re-hide the duplication.
- **Dead code**: delete `snapshot_certificate`; verify no template/templatetag references it first (grep confirms none today).

## Risks / Trade-offs

- [Unifying sniff helpers changes MIME filtering behavior if allowlists diverge subtly] → Keep both callers' exact current maps/allowlists as parameters; cover with tests asserting each stage's accepted types.
- [Reason-merge refactor alters `review_reasons` ordering/content] → Preserve exact semantics: keep non-owned reasons in order, append fresh non-duplicates, `dict.fromkeys` dedupe; existing tests plus new unit tests on the shared helper.
- [deploy.sh port change could break existing deployments relying on 8090] → Existing `.env` files already carry `APP_PORT`; only fresh deploys and the health-check default change, and the default now matches compose.

## Migration Plan

No data migration. Deploy: code changes are backward compatible; `deploy.sh` fix takes effect on next deploy run. Rollback: revert the change; no persisted state is affected.
