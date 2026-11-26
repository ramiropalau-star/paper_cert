# Tasks

## 1. Model + scoring

- [x] 1.1 Add `is_active` (default True), `deactivated_by` (FK user null),
  `deactivated_at` (datetime null) to `FormatProfile` + migration.
  Verify migrate clean.
- [x] 1.2 Update `format_profile.py`: `_score_against` and the
  cross-entity scan filter `is_active=True`; add
  `rescore_entity_year(entity_id, year, exam_id)` helper that recomputes
  `score_document_format` for matching certificates. Verify with tests:
  inactive profile ignored, reactivation restores scoring, rescore
  updates stored scores.

## 2. Document list visibility

- [x] 2.1 Add `format=doubtful` param to `filter_documents` (score below
  threshold, or NULL score with a qualifying active profile for the
  entity). Verify filter tests.
- [x] 2.2 `document_list` view: pass threshold + per-row format badge
  data; `list.html`: format badge column/badge with band colors and
  `row-format-warn` class; add "Formato dudoso" option to the filters
  form. Verify template renders bands and filter round-trips.

## 3. Profile management UI

- [x] 3.1 `format_profile_list` view + `format_profiles.html`: profiles
  grouped by entity/year/exam, sample_count, anchor count, status,
  deactivate/reactivate POST (reviewer+, sets deactivated_by/at),
  rescore POST. Verify view tests: list renders, role enforcement,
  deactivate hides from scoring, rescore recomputes.
- [x] 3.2 Link management page from list/detail navigation.

## 4. Verification

- [x] 4.1 Run full test suite; `openspec validate
  format-profile-visibility --strict`.
