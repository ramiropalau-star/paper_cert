# Tasks

## 1. Multilingual month parsing

- [x] 1.1 Add `MONTH_NAMES` map (CA/ES/EN/FR/DE/PT/IT names + abbreviations,
  folded via `_norm_text`) in a shared location usable by both
  `extraction.py` and `classification.py`. Verify with unit tests per
  language.
- [x] 1.2 Extend `parse_date_text` in `classification.py` with a
  month-name branch (day+monthname+year, monthname+year, US order variant)
  and regenerate `MONTH_NAME`/`_looks_like_date` from the map. Verify:
  "18 Setembre 2026", "5 décembre 2020", "3 März 2021" parse; "SEPTIEMBRE
  2020" surfaces as date-like.

## 2. Deterministic date harvest

- [x] 2.1 Implement `_harvest_dates(page_texts)` in `extraction.py`:
  numeric + month-name patterns, dedupe by parsed value against existing
  candidates, birth-marker and year-range (1900–2100) exclusions, role
  `unknown` unless a multilingual label is within ~80 chars. Verify with
  fixture page texts: trilingual block → 1 candidate, birth date skipped,
  "0399" rejected.
- [x] 2.2 Extend `_ISSUE_DATE_LABEL_RE` with CA/FR/DE/PT/IT issue labels and
  wire `_harvest_dates` into `extract_certificate` after `_merge_focus`,
  before persist. Verify integration test: doc with label-less date block
  ends with a `detected_date`/ambiguous reason after classification.
- [x] 2.3 Update `SYSTEM_PROMPT` dates bullet (any-language months,
  signature-block dates usually issue) and bump `PROMPT_VERSION` to next
  free version. Verify prompt test.

## 3. Verification

- [x] 3.1 Run `manage.py test documents` (or project suite) — no
  regressions; `openspec validate multilingual-date-detection --strict`.
- [x] 3.2 Manual spot-check: re-extract docs 43/44/50/47 in a dev/staging
  pass and confirm dates appear (43 gets detected_date, 47's '0399' gone).
