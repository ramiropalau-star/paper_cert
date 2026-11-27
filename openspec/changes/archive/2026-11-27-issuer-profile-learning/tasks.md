# Tasks

## 1. Data model and migrations

- [x] 1.1 Add additive migrations for `FormatProfile` (value shapes, quality, drift, version, provenance), `FieldLabelAlias` (lifecycle, support, confidence, provenance), `Certificate` (pre-detection result/confidence, extraction run, veracity score/components, source comparison), and new `ExtractionRun`, `VerifierConfig`, `EvaluationRun`, and `EvaluationCase` tables; verify `python manage.py makemigrations --check` and `python manage.py migrate` succeed.
- [x] 1.2 Add constraints and indexes for alias lifecycle/scope, profile issuer/type/version, extraction-run timestamps, and evaluation-run status; verify `python manage.py check` and the model tests pass.
- [x] 1.3 Add factories/builders for the new models and fields; verify the existing test factories still build valid records.
- [x] 1.4 Update `docs/data-model.md` with the new tables, fields, and relationships; verify the documented schema matches the migrations.

## 2. Evaluation harness

- [x] 2.1 Implement versioned golden-set creation from approved or validated certificates with human-confirmed fields; verify tests cover approved inclusion, rejected exclusion, and immutable versions.
- [x] 2.2 Implement a dry-run evaluation runner that does not persist extracted fields, review reasons, or processing-state changes; verify an integration test asserts live records are unchanged.
- [x] 2.3 Implement per-field exact and normalized accuracy, missing-field rate, fabricated-value rate, evidence-quote validity, and latency metrics grouped by issuer and certificate type; verify unit tests with synthetic cases.
- [x] 2.4 Implement baseline comparison and regression/improvement reporting without automatic deployment or activation; verify tests for regression, improvement, and no live configuration change.
- [x] 2.5 Add a management command to run, list, and compare evaluations; verify the command runs against a fixture golden set and produces a report.
- [x] 2.6 Document the evaluation workflow and commands in `docs/development.md` and `docs/operations.md`; verify every documented command runs as written.

## 3. Deterministic issuer and type pre-detection

- [x] 3.1 Implement deterministic signals from active aliases, profile anchors, exam/language vocabulary, and verifier domains, with confidence and margin scoring; verify tests for clear match, ambiguous match, and no match.
- [x] 3.2 Add the optional bounded classifier fallback behind configuration, off by default; verify tests for disabled behavior, one-call maximum, and ambiguity-only invocation.
- [x] 3.3 Persist the pre-detection result, confidence, and margin on the extraction run and certificate; verify tests for stored values and ambiguous results.
- [x] 3.4 Document pre-detection signals, thresholds, and fallback behavior in `docs/extraction.md`; verify the documentation matches the tested behavior.

## 4. Profile-guided extraction

- [x] 4.1 Build the profile context (learned labels, value shapes, expected anchors, anonymized exemplars) with a token budget; verify tests for inclusion, anonymization, and budget truncation.
- [x] 4.2 Implement the deterministic candidate pre-pass for label-value pairs, scores, and dates, and require the model to validate candidates with verbatim evidence; verify tests for verified, unverified, and empty candidates.
- [x] 4.3 Wire pre-detection and profile context into the extraction service with a global fallback when the result is ambiguous or no profile exists; verify integration tests for detected and ambiguous paths.
- [x] 4.4 Record model, prompt version, profile version, pre-detection result/confidence, pass count, fallback use, and latency per run; verify tests for the stored metadata.
- [x] 4.5 Update `docs/extraction.md` and `docs/configuration.md` with the two-pass flow and prompt context; verify the documented behavior matches the tests.

## 5. Consistency check and bounded fallback

- [x] 5.1 Implement the post-classification entity/exam comparison and the `entity_mismatch` review reason; verify tests for mismatch, ambiguous no-mismatch, and review-reason rendering.
- [x] 5.2 Implement at most one bounded re-extraction with the resolved issuer profile; verify tests for one-run maximum, evidence validation, and no loop.
- [x] 5.3 Implement the optional fallback-model escalation for missing critical fields; verify tests for gaps-only invocation, complete-extraction skip, and recorded failure.
- [x] 5.4 Document the consistency check and fallback behavior in `docs/extraction.md` and `docs/review.md`; verify the documentation matches the tests.

## 6. Learned aliases and pre-detection scoping

- [x] 6.1 Add lifecycle, support, confidence, and provenance handling to the alias service; verify tests for candidate/active/rejected transitions and manual-alias authority.
- [x] 6.2 Implement corroboration and conflict handling; verify tests for single-observation candidate, corroborated activation, and conflict remaining a candidate.
- [x] 6.3 Implement reviewer-correction alias proposals with issuer scope; verify tests for proposal, dismissal, and scope selection.
- [x] 6.4 Scope aliases by the pre-detected issuer before extraction; verify tests for scoped alias use, ambiguous global-only behavior, and resolved-entity mismatch behavior.
- [x] 6.5 Update the alias listing and review surfaces with source, lifecycle, support, confidence, and scope; verify template tests and the role-permission tests.
- [x] 6.6 Update `docs/configuration.md` with the alias lifecycle and pre-detection scoping; verify the documentation matches the tests.

## 7. Format profile quality, drift, versioning, and verified weighting

- [x] 7.1 Add profile versioning and provenance, and a rebuild command that preserves the previous version; verify tests for new versions and audit history.
- [x] 7.2 Add sample count, precision/recall, anchor churn, and drift detection; verify tests for drift detection and low-quality down-weighting.
- [x] 7.3 Weight source-verified samples higher than merely approved samples while keeping corroboration rules; verify tests for weighting and corroboration.
- [x] 7.4 Feed profile quality and drift into the veracity score and review display; verify tests for quality-adjusted components.
- [x] 7.5 Update `docs/classification.md` with profile quality, drift, versioning, and verified weighting; verify the documentation matches the tests.

## 8. Veracity scoring and verifier configuration

- [x] 8.1 Implement the veracity service with component values, weights version, and stored score; verify unit tests for source-verified, format-only, and missing-evidence cases.
- [x] 8.2 Implement per-issuer `VerifierConfig` CRUD with URL/host validation, timeouts, and reviewer/admin permissions; verify tests for new issuer, invalid config, and viewer denial.
- [x] 8.3 Migrate the existing UV/GVA verifier behavior into seed configuration; verify existing verification tests still pass.
- [x] 8.4 Implement source-document field comparison and material-mismatch routing to review; verify tests for match, mismatch, and unavailable source document.
- [x] 8.5 Feed source-verified samples into profile and alias learning with higher weight; verify tests for eligibility and excluded unapproved samples.
- [x] 8.6 Update `docs/configuration.md` and `docs/security.md` with verifier configuration, validation, and permissions; verify the documentation matches the tests.

## 9. Review UI and document list

- [x] 9.1 Add the numeric veracity badge and quality band to the document list, derive the row color from the veracity band, and keep the format score as a separate badge; verify template tests and an accessibility check that color is not the only cue.
- [x] 9.2 Add the veracity breakdown with human labels to the review detail, including an explicit "not available" state; verify template tests and unknown-component fallback.
- [x] 9.3 Replace the list's preview-only eye action with a lazy-loaded inline thumbnail that opens the review detail, keeping a separate zoom modal; verify template tests and keyboard behavior.
- [x] 9.4 Make the review detail render the source document by default alongside the data on wide screens and in the stacked layout on narrow screens; verify a rendered-page test and a manual responsive check.
- [x] 9.5 Ensure a high veracity score never hides review reasons or bypasses the explicit approval action; verify template tests for high-score-with-warning cases.
- [x] 9.6 Update `docs/review.md` with the veracity value, breakdown, default-visible document, and inline thumbnail behavior; verify the documentation matches the tests.

## 10. Integration and rollout

- [x] 10.1 Add an end-to-end test covering upload, pre-detection, profile-guided extraction, classification, veracity scoring, review, and approval; verify the focused end-to-end test passes.
- [x] 10.2 Run the evaluation baseline against the current prompt/model and record the report before enabling the new path; verify the report exists and the regression comparison runs.
- [x] 10.3 Verify the feature flags for pre-detection, veracity scoring, and the UI changes can be disabled independently; verify the rollback path in a test or documented manual check.
- [x] 10.4 Update `docs/extraction.md`, `docs/classification.md`, `docs/review.md`, `docs/configuration.md`, and `docs/data-model.md` for the complete feature; verify every documented command and behavior matches the implementation.
- [x] 10.5 Run the full test suite and linters; verify `DJANGO_SETTINGS_MODULE=config.settings_test .venv/bin/pytest` and `.venv/bin/ruff check . && .venv/bin/ruff format --check .` pass.
- [x] 10.6 Re-run the evaluation against the new configuration and confirm no unresolved regression before requesting archive; verify the comparison report is attached to the change.

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Verify the archived specs and the implementation still agree.
