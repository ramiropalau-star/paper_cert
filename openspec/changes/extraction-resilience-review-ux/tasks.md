# Tasks

## 1. Unverified-field retention in extraction

- [ ] 1.1 Add `unverified_fields` JSON list field to `Certificate` (migration).
- [ ] 1.2 Change `_validate_evidence` so a literal field with an unverifiable
      quote keeps its value, records the field name for unverified marking, and
      logs `extraction_evidence_unverified`; verified fields unchanged.
- [ ] 1.3 Persist `unverified_fields` during extraction `_persist`; merge with
      any pre-existing marks.
- [ ] 1.4 Clear unverified marks in `review.py` when a reviewer edits or
      confirms a field; record in `ReviewEvent` where applicable.
- [ ] 1.5 Broaden `_norm_text` with NFKD fold and typographic dash/quote
      folding.
- [ ] 1.6 Tests: single bad quote keeps value + marks unverified; verified
      fields unaffected; edit clears the mark; normalization cases.

## 2. Deterministic fallbacks and second pass

- [ ] 2.1 Implement `_fallback_score` (label-anchored numeric/`/100` patterns)
      over stored page text; fills empty `score`, marked unverified.
- [ ] 2.2 Implement `_fallback_dates` for issue date using date labels +
      multi-format date regex; marked unverified.
- [ ] 2.3 Implement focused second pass: when score or issue date still empty,
      one bounded model call requesting only missing fields with verbatim
      quotes; merge before evidence validation.
- [ ] 2.4 Tests: fallback fills score/date on fixture text; no fallback when
      model already returned values; second pass runs once and only on gaps;
      hallucinated second-pass value lands unverified.

## 3. Direct re-extract action

- [ ] 3.1 Add reviewer-facing re-extract endpoint reusing the extraction
      service; preserves `manual_fields`; writes a `reextract` ReviewEvent.
- [ ] 3.2 Add "Re-extraer" action to `detail.html` with confirmation.
- [ ] 3.3 Tests: endpoint re-runs extraction idempotently, preserves manual
      fields, records event, requires reviewer role.

## 4. Documents table UX

- [ ] 4.1 Eye-icon quick preview per row: modal with document render (reuse
      gallery image endpoint); close via button, backdrop, Escape; focus
      return.
- [ ] 4.2 Per-column text filters (client-side) under the header row.
- [ ] 4.3 Click-to-sort on column headers (asc/desc toggle + indicator,
      numeric-aware).
- [ ] 4.4 Client-side pagination: default 10 rows, page-size selector
      (10/25/50/100/All) persisted in sessionStorage, resets on filter/sort
      change, composes with column filters.
- [ ] 4.5 Unverified badge/marker on list rows and detail fields; optional
      `unverified` filter param in `documents/filters.py`.
- [ ] 4.6 Remove the hover tooltip on the "Equiv. UV" column in `list.html`
      (drop `has-tip`/`data-tip`); the link to the equivalences page suffices.
- [ ] 4.7 Tests: preview endpoint/modal markup, filter/sort/pagination JS
      behavior (template assertions + any existing JS test harness), unverified
      filter param.

## 5. Docs, verify, ship

- [ ] 5.1 Update `docs/review.md` (unverified marks, re-extract, table UX) and
      `docs/classification.md` or `docs/operations.md` if behavior docs change.
- [ ] 5.2 Run full test suite; `manage.py check`; rebuild images; smoke-test on
      a real pending document (preferably one that previously failed evidence
      validation).
- [ ] 5.3 Mirror to `paper_cert`, commit, push.
