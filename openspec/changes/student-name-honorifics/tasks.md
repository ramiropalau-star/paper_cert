# Tasks

## 1. Title stripping

- [ ] 1.1 Implement `_strip_name_honorifics` in
  `documents/services/extraction.py`: conservative multilingual always-strip
  list (ES/EN/FR/DE/CA/PT/IT), accent-folded case-insensitive leading-token
  match, ≥2 remaining words required, max 3 iterations, returns stripped
  value + removed tokens. Verify with unit tests per language and edge
  cases (ambiguous "Don", "D.", title mid-name, one-word remainder).
- [ ] 1.2 Apply the strip to `student_name` in `_persist_certificate` and
  record removed tokens in certificate metadata/evidence for audit.
  Verify persisted value is stripped and metadata retains the original.
- [ ] 1.3 Add prompt guidance line to `SYSTEM_PROMPT` (exclude honorifics
  from student_name) and bump `PROMPT_VERSION`. Verify prompt snapshot test.

## 2. Verification

- [ ] 2.1 Run extraction test suite + `manage.py test documents` (or project
  equivalent); verify no regressions and `openspec validate
  student-name-honorifics --strict` passes.
