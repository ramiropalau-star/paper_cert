# Proposal

## Why

Date extraction misses many issue dates. Real certificates in the system
show three failure modes: month names in Catalan/other languages are not
recognized at all (`MONTH_NAME` only covers English/Spanish and `dateutil`
cannot parse them, so candidates are dropped silently without even an
`ambiguous_date` reason); dates printed without a nearby label (e.g. the
trilingual issue-date block beside a signature) are invisible to the
label-anchored fallback; and the model labels most dates `exam`, leaving
`issue_date` empty.

## What Changes

- Multilingual month-name parsing: a curated month-name map
  (Catalan, Spanish, English, French, German, Portuguese, Italian + common
  abbreviations) integrated into date parsing and the
  `_looks_like_date`/`MONTH_NAME` heuristics, so named-month dates in any
  supported language parse instead of being dropped.
- Deterministic date harvesting: scan stored page texts for all date-like
  patterns (numeric formats + multilingual month names) and add candidates
  the model missed, deduplicated by parsed date (trilingual repetitions
  collapse to one candidate), role `unknown` unless a nearby label indicates
  otherwise.
- Multilingual role labels for the issue-date fallback (expedició,
  emissió, data d'emissió, fecha de expedición, date of issue, relevé,
  ausgestellt, rilascio, etc.).
- Noise guardrails: skip lines containing birth/Geburtsdatum/nacimiento/
  naixement markers; reject implausible years; avoid duplicate candidates.
- Prompt clarification: dates beside signature/issuer blocks are usually
  issue dates; month names may appear in any language of the document.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `certificate-extraction`: date candidates SHALL be harvested
  deterministically across supported languages and parsed regardless of
  month-name language; unparseable-but-date-like text SHALL surface as
  ambiguous rather than vanish.

## Impact

- `documents/services/extraction.py`: `_DATE_VALUE_RE`, month map,
  `_fallback_issue_date` labels, harvest function, prompt text,
  `PROMPT_VERSION` bump.
- `documents/services/classification.py`: `MONTH_NAME` /
  `_looks_like_date` / `parse_date_text` multilingual coverage.
- Tests: per-language month names, trilingual dedupe, label-less harvest,
  birth-date exclusion, bogus-year rejection.
