# Design

## Context

Extraction today: `_call_model` → `parse_payload` → `_validate_evidence` (literal
fields strict — one bad quote rejects everything; date candidates soft — bad
candidates dropped). `student_name` already has a deterministic label fallback.
`Certificate` has `manual_fields` (JSON list) and `evidence`/`field_confidence`
(JSON dicts) but no per-field trust flag. The documents list is a plain Django
template table; the gallery already renders document pages for enlarge view.
Manual reprocessing currently depends on the n8n webhook round-trip.

## Goals / Non-Goals

**Goals:**

- Stop losing whole extractions to a single unverifiable quote, without letting
  invented values pass silently — keep the value, mark it unverified.
- Recover score/dates deterministically when the model omits them.
- Give reviewers a fast visual triage loop: preview, filter, sort, paginate.
- Remove the webhook dependency for manual re-extraction.

**Non-Goals:**

- Changing the model, prompt version semantics, or classification logic.
- Server-side pagination/sorting of the documents table (client-side only —
  the queue is tens of rows, not thousands).
- Retroactive re-verification of already-stored certificates (the re-extract
  action covers that on demand).

## Decisions

### Unverified marking: new `unverified_fields` JSON list on `Certificate`

Parallel to `manual_fields`. Extraction adds field names whose evidence failed
verification or whose value came from a fallback/second pass; review clears a
name when the reviewer edits/confirms that field. Alternatives considered:
reusing `field_confidence` (it's a float map — can't express "unverified" vs
"low confidence" distinctly) and review reasons (they're document-level, not
per-field persistent state). A dedicated list keeps semantics clean and makes
the UI badge trivial.

### Keep-value semantics on evidence failure

On quote-verification failure for a literal field: keep `field.value`, append
the field name to `unverified_fields`, log `extraction_evidence_unverified`,
continue. This differs from dates (which drop the candidate) because a literal
field has exactly one candidate — dropping it would lose the value entirely,
while keeping it flagged preserves reviewer optionality. Accepted trade-off:
a hallucinated value can reach the queue, but it is explicitly badged and the
reviewer must look at it — the same trust level as any other extracted field.

### Deterministic fallbacks live next to the student-name fallback

New helpers in `extraction.py`: `_fallback_score(text)` and
`_fallback_dates(text, page_texts)` using label-anchored regexes (score:
`/\d+(\.\d+)?\s*\/\s*\d+/`, `Score|Puntuació|Nota` prefixes; dates: known date
labels + multi-format date regex, restricted to page 1 unless evidence says
otherwise). Results populate the same payload fields marked unverified. Order:
model → deterministic fallback → focused second pass (only if still empty).

### Focused second pass is one bounded call

`_call_model` gains a `focus_fields` variant of `build_messages` that asks only
for missing critical fields with mandatory verbatim quotes. Runs at most once,
only when score or issue date is still empty after fallbacks, and its output
merges into the payload before `_validate_evidence` — so a hallucinated second
-pass value fails verification and lands as unverified rather than trusted.

### Re-extract endpoint reuses the extraction service

`POST /documents/<pk>/re-extract/` (reviewer+) calls the same extraction entry
point used by the pipeline, skipping n8n. Manual fields are preserved because
`_persist` already respects `manual_fields`; a `ReviewEvent` (`reextract`)
records the action. Idempotent: running twice is safe.

### Table UX is vanilla JS, no dependencies

`list.html` gains: an eye button per row opening a `<dialog>`/modal with the
document render URL (reuse the gallery's page-image endpoint); a filter row
under `<thead>` with per-column text inputs; sortable `<th>` toggles; and a
client-side pagination controller (default 10, selector 10/25/50/100/All,
persisted in `sessionStorage`). All operate on `data-*` attributes already
present or cheaply added; sorting uses `localeCompare` with numeric awareness.
No new CSS framework; extends `app.css`.

### `_norm_text` hardening

Add NFKD normalization + fold typographic dashes/quotes to ASCII equivalents
before comparison. One-line-ish change, reduces spurious rejections without
weakening the verbatim check meaningfully.

## Risks / Trade-offs

- **Unverified values could mislead if the badge is missed.** Mitigated by
  badging in list + detail and an `unverified` filter so reviewers can isolate
  them.
- **Fallback regexes may grab wrong numbers** (e.g. a page number near "Score").
  Mitigated by label-anchoring and the unverified flag; precision over recall.
- **Client-side table JS on a template with conditional columns.** The no-cert
  rows render placeholder cells; the controller must handle them (treat as
  empty strings). Covered by tests.
- **Second pass adds latency on hard docs** (~one extra model call, only when
  needed). Bounded to one call; acceptable.
