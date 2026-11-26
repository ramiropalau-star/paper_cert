# Proposal

## Why

Certificates frequently print the student's name preceded by an honorific or
title ("Doña María González", "Mr. John Smith", "Mme Claire Martin",
"Frau Anna Schmidt"). The extractor currently keeps the title inside
`student_name`, polluting search, catalog matching, and reports. Reviewers
must hand-edit every affected record.

## What Changes

- `student_name` values SHALL be stripped of leading honorifics/titles from
  a curated multilingual list (Spanish, English, French, German, Catalan /
  Valencian, Portuguese, Italian) as a deterministic post-extraction step.
- The extraction instruction SHALL tell the model to exclude titles, as a
  first line of defense; the deterministic strip is the safety net.
- Stripping SHALL be conservative: only leading tokens that are unambiguous
  titles are removed; ambiguous tokens that can be real given names
  (e.g. "Don", initials like "D."/"M.") are NOT stripped by default.
- When stripping changes the value, the change SHALL be traceable (recorded
  in extraction metadata / evidence) so reviewers can audit it.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `certificate-extraction`: extracted person names SHALL exclude leading
  honorifics/titles across supported certificate languages, applied
  deterministically with auditability.

## Impact

- `documents/services/extraction.py`: title list + strip function applied
  in `_persist_certificate` (or equivalent), prompt guidance line,
  `PROMPT_VERSION` bump.
- Tests: multilingual title cases, ambiguous-token preservation,
  no-title names unchanged, audit metadata.
