# Proposal

## Why

Extraction label knowledge is hardcoded: `_NAME_LABELS`, the score/date
fallback regexes, and the system prompt's per-field label lists all live in
`documents/services/extraction.py`. When a certificate uses an issuer-specific
label the model and fallbacks do not know (e.g. "Test Taker Name" for
`student_name`), the only fix today is a code change and redeploy. Reviewers
who can see the certificate and know the mapping have no way to teach it.

## What Changes

- New `FieldLabelAlias` model storing label aliases per extraction field,
  with optional entity scope (global when `scope_entity` is null) and a
  `source` (`manual` | `learned`) plus active flag.
- Extraction becomes alias-aware: known aliases are injected into the model
  prompt per document and extend the deterministic fallback label sets, so
  new labels work on first pass (global) and on re-extract (scoped).
- Reviewer-facing "teach alias" flow on the review detail page for empty or
  unverified fields: enter the label as printed, optionally scope to the
  document's entity, then reprocess and see before/after values.
- Re-extract uses the alias set applicable to the document (global + entity
  scope when classified) and reports which aliases were applied.
- Admin/manage surface to list, edit, deactivate aliases (reviewer+ role).

## Capabilities

### New Capabilities

- `field-label-mapping`: configurable label aliases that teach extraction
  which printed labels correspond to which certificate fields, including
  scope (global vs per-entity), provenance, and lifecycle.

### Modified Capabilities

- `certificate-extraction`: extraction SHALL incorporate configured field
  label aliases when building the model prompt and deterministic fallbacks.
- `review-experience`: review detail SHALL offer a teach-alias action for
  unresolved/unverified fields and SHALL surface reprocess results for
  validating a mapping.

## Impact

- `documents/models.py`: new `FieldLabelAlias` model + migration.
- `documents/services/extraction.py`: prompt builder and fallback label sets
  become alias-driven; re-extract path applies scoped aliases.
- `documents/services/learning.py` or new service: alias lookup/caching.
- Review views/templates: teach-alias form, alias management UI, reprocess
  diff display.
- Tests: alias CRUD, prompt injection, fallback matching, scoped application
  on re-extract, role enforcement.
