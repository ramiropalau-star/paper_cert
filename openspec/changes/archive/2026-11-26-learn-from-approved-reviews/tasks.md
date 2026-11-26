# Tasks

## 1. Catalog format profile model

- [x] 1.1 Add `FormatProfile` model to `catalog/models.py` (entity FK, nullable exam FK, year, anchors JSON, sample_count, unique constraint on entity+exam+year) and generate the migration; verify `manage.py makemigrations --check` is clean and `migrate` applies it.
- [x] 1.2 Add `APP_FORMAT_*` settings (`format_min_samples=2`, `format_min_exam_samples=3`, `format_score_threshold=0.4`, `format_max_score=0.5`) to `config/settings.py` and `.env.example`; verify `tests/test_settings.py` still passes.

## 2. Catalog learning service

- [x] 2.1 Implement `documents/services/learning.py::learn_from_certificate(certificate, actor)` covering: alias creation for language/entity/exam literals→FKs (get_or_create, conflict skip), limited `Exam` auto-creation per design D5, unbanded `Equivalence` creation per D3, inactive `CefrConversionRule` candidate per D4; return a learning-outcome summary dict. Verify with unit tests in `documents/tests/test_learning.py`: alias creation, idempotent re-run, alias conflict skip, equivalence creation, inactive CEFR rule, rejected-certificate exclusion.
- [x] 2.2 Add `ReviewEvent.EventType.LEARN` and record the learning outcome on the approval/validation `ReviewEvent.after["learning"]`; verify a test asserts the outcome is persisted in the event payload.

## 3. Review hooks

- [x] 3.1 Call `learn_from_certificate` after commit in `approve_certificate` and `validate_certificate` inside try/except so failures never block approval; verify tests in `documents/tests/test_review.py` cover: learning runs on approve, learning exception still returns ok=True, and no learning on reject.

## 4. Format profile learning and scoring

- [x] 4.1 Implement `documents/services/format_profile.py`: anchor extraction (normalized lines, length/alpha filters), cohort upsert on approval (`learn_format_profile`), and `score_document_format` per design D7/D8 (cohort preference, entity-union fallback, min-samples neutrality, cross-entity cap). Verify unit tests cover: anchor corroboration threshold, cohort isolation by year, insufficient-sample neutrality, cross-entity cap.
- [x] 4.2 Call `learn_format_profile` from the same post-approval hook in `review.py`; verify a test shows an approved certificate's anchors land in its `(entity, year)` cohort only.

## 5. Classification integration

- [x] 5.1 Add `Certificate.format_score` and `format_cohort` fields + migration; verify migration applies cleanly.
- [x] 5.2 In `classify_certificate`, after `apply_dates` and before `aggregate_reasons`: compute and persist format score/cohort, blend into `certificate.confidence` (0.7/0.3 when score present), and emit `format_mismatch` when entity resolved and score below threshold; add the reason code to `CLASSIFICATION_REASON_CODES` and a "Formato no reconocido" entry in `review_display.py`. Verify tests in `documents/tests/test_classification.py` cover: score persisted, confidence blend, reason emitted below threshold, neutral when no profile.

## 6. Review UI

- [x] 6.1 Show format score and cohort on the certificate detail page near the confidence display, and include `format_mismatch` in reason rendering; verify a review test asserts the score appears when present.

## 7. Backfill and docs

- [x] 7.1 Add management command `learn_from_history` that replays `learn_from_certificate` + `learn_format_profile` over already-approved/validated certificates (idempotent); verify it runs against the test DB without duplicating aliases/rules.
- [x] 7.2 Update `docs/` (or README section) describing the learning loop, cohort behavior, and the new settings; verify documented commands match actual management commands.

## 8. Integration verification

- [x] 8.1 Run the full test suite (`pytest`) and `manage.py check`; verify all green.
- [x] 8.2 Manual smoke: approve a certificate in the running stack, confirm catalog aliases/equivalence/profile rows appear and a second similar document classifies without `unknown_entity`/`format_mismatch`.
