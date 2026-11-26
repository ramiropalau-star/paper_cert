# Proposal

## Why

Two pressures surfaced from real usage and the model bake-off:

1. **Extraction is brittle at the edges.** Strict page-evidence validation rejects the
   *entire* extraction when a single literal field carries an unverifiable quote —
   even the incumbent 7B model was rejected on 5 of 13 real certificates. Fields the
   model simply omits (score, dates on trilingual layouts) have no deterministic
   fallback, so reviewers re-type values that are plainly present in the text.
   Manual reprocessing still depends on the n8n webhook round-trip, which has
   already left documents stuck mid-pipeline.

2. **Review throughput.** Reviewers must open each document detail page to see the
   certificate image, and the documents table offers no quick preview, column
   filtering, or sorting — slowing triage of the pending queue.

## What Changes

- **Per-field evidence soft-fallback (keep value, mark unverified).** When a literal
  field's evidence quote cannot be verified on the cited page, the extracted value
  is kept but flagged as unverified instead of failing the whole extraction. The
  flag is persisted per field, surfaced in review UI, and cleared when a reviewer
  edits or confirms the field. Date candidates keep the existing drop-only
  behavior.
- **Deterministic fallbacks for score and dates.** When the model returns empty
  score or date candidates, a regex/label pass over the stored page text fills
  them using the same pattern as the existing student-name fallback — marked
  unverified like any other fallback-derived value.
- **Focused second-pass extraction.** If critical fields (score, dates) remain
  empty after the primary extraction, one bounded follow-up call asks the model
  for only the missing fields with verbatim quotes. Runs only on already-imperfect
  documents; never on the happy path.
- **Direct re-extract action.** A reviewer-facing "Re-extract" action on the
  document detail page invokes the extraction service directly, removing the n8n
  webhook dependency for manual retries.
- **Documents table UX.** An eye-icon quick preview (modal with the certificate
  render, same source as the gallery enlarge view), per-column text filters, and
  click-to-sort ascending/descending on column headers — all client-side over the
  already-rendered rows, preserving existing GET filters.
- **Quote normalization hardening.** Broaden `_norm_text` equivalence (NFKD fold,
  typographic dash folding) to reduce spurious evidence rejections.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `certificate-extraction`: evidence-validation failure semantics change from
  whole-extraction rejection to per-field unverified retention; new deterministic
  fallback and focused second-pass requirements; new re-extract entry point.
- `review-experience`: documents table gains quick preview, column filters, and
  sorting; unverified-field marking is surfaced during review.

## Impact

- `documents/services/extraction.py` — evidence validation, fallbacks, second pass.
- `documents/models.py` — new `unverified_fields` JSON list on `Certificate`
  (migration required).
- `documents/services/review.py` — confirm/edit clears unverified marks;
  `ReviewEvent` records them.
- `documents/views.py`, `documents/templates/documents/list.html`,
  `detail.html` — preview modal, filters, sorting, re-extract action,
  unverified badges.
- `documents/filters.py` — optional `unverified` filter param.
- Tests across extraction, review, and list views; docs (`review.md`,
  `classification.md`/`configuration.md` as applicable).
