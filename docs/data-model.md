# Data model and catalog management

The application uses four domain apps:

- `catalog` — reference data (languages, entities, exams, equivalences, CEFR
  rules, format profiles).
- `documents` — intake, extracted records, review workflow, audit history,
  Paperless sync state.
- `reports` — asynchronous Excel report jobs.
- `accounts` — user management views on top of Django auth.

`core` holds shared infrastructure (internal API, logging, middleware) and
Django auth tables provide users, groups, and permissions.

## Catalog (`catalog`)

### `Language`

- `code`: unique short code (ISO 639-2/T style, for example `eng`).
- `name`: canonical English name.
- `name_es`: Spanish display name.
- `is_active`: hides retired languages from new classifications.
- `created_at`, `updated_at`.

### `LanguageAlias`

- `language`: parent language.
- `alias`: text as cataloged by an administrator.
- `normalized_alias`: unique value computed on save with NFKC, casefold, and
  whitespace collapse. Accents are preserved; matching is exact.

### `Entity`

- `name`: unique canonical certifying-entity name.
- `is_active`: hides retired entities.
- `date_order`: day-first or month-first date interpretation for dates
  printed by this entity's certificates.
- `notes`: operational notes.
- `created_at`, `updated_at`.

### `EntityAlias`

- `entity`: parent entity.
- `alias`: cataloged spelling or variant.
- `normalized_alias`: unique normalized value, computed on save.

### `Exam`

- `entity`: optional owning entity (`PROTECT`).
- `language`: optional language (`PROTECT`).
- `name`: exam name, unique per entity.
- `is_active`.
- `created_at`, `updated_at`.

### `ExamAlias`

- `exam`: parent exam.
- `alias`: cataloged spelling or variant.
- `normalized_alias`: unique normalized value, computed on save.

### `Equivalence`

- `exam`: exam the equivalence belongs to.
- `level`: CEFR level the exam corresponds to.
- `source`: provenance of the mapping (for example `manual`, `review`).
- `is_active`: inactive equivalences never apply.
- `created_at`, `updated_at`.

Equivalences are reviewed and edited in the in-app catalog UI at `/catalog/`
(see "Catalog management" below).

### `CefrConversionRule`

- `exam`: exam the rule belongs to.
- `score_min`, `score_max`: inclusive numeric range.
- `cefr_level`: one of `A1`, `A2`, `B1`, `B2`, `C1`, `C2`.
- `reference`: documented source for the mapping.
- `approved_by`: approver name.
- `approved_at`: set automatically the first time an active rule is saved.
- `is_active`: inactive rules are placeholders and never apply.
- `created_at`, `updated_at`.

A database check constraint enforces `score_max >= score_min`. Model validation
requires `approved_by` and `reference` before a rule can be active. The
`CefrConversionRule.objects.effective()` queryset additionally requires
`is_active`, `approved_at`, a non-empty approver, and a non-empty reference;
classification must use only that queryset.

### `FormatProfile`

Learned format signature for one certifying entity, keyed by a cohort:

- `entity`: owning entity (`PROTECT`).
- `exam`: optional exam (`PROTECT`); set only when enough samples exist for
  the exam-scoped cohort.
- `issue_year`: calendar year of emission the profile describes; `NULL`
  marks the entity-level pool profile learned across all years.
- `sample_count`: number of approved certificates that fed the profile.
- `anchors`: JSON list of corroborated anchors with their document
  frequency within the cohort — normalized text lines, plus layout anchors
  (`kind: "layout"`, `feature` token) for recurring positioned text and
  image regions.
- `value_shapes`: JSON map of learned per-field value patterns (date order,
  score/code shape, level vocabulary) keyed by extraction field.
- `quality`: JSON map of measured precision, recall, and anchor churn on
  approved samples.
- `drift_detected`, `drift_detail`: drift signal when recent approved samples
  diverge from the anchors the profile was built from.
- `version`: monotonic version bumped on every rebuild; `version_history`
  keeps a bounded snapshot of previous versions for audit.
- `provenance`: JSON describing how the profile was built (source samples,
  weighting rules).
- `last_rebuilt_at`: timestamp of the last rebuild.
- `created_at`, `updated_at`.

Profiles are rebuilt from approved certificates (anchors must appear in at
least two samples or in at least half the cohort) and drive the
`format_score`/`format_cohort` fields on `Certificate` during
classification. See `docs/review.md` for scoring details.

## Documents (`documents`)

### `Document`

- `fingerprint`: unique SHA-256 of the original bytes.
- `original_filename`, `content_type`, `size_bytes`.
- `paperless_document_id`: identifier in Paperless-ngx; indexed.
- `page_count`: number of acquired pages.
- `text_method`: `embedded`, `ocr`, `mixed`, or empty before acquisition.
- `processing_state`: `received`, `stored`, `text_ready`, `extracted`,
  `classified`, `pending_review`, `approved`, `rejected`, or `error`.
- `error_reason`: operator-readable failure detail.
- `review_reasons`: JSON list of text/processing review reason codes.
- `uploaded_by`: user who uploaded the file, if known.
- `processed_at`: when the pipeline finished processing the document.
- `recovery_attempts`, `last_recovery_at`: stuck-work recovery bookkeeping.
- `created_at`, `updated_at`.

State progression:

```text
received -> stored -> text_ready -> extracted -> classified
        -> pending_review -> approved | rejected
error is reachable from any processing step
```

### `DocumentPage`

- `document`: parent document.
- `page_number`: unique per document.
- `text`: page text (embedded text is conservatively normalized — NFKC,
  whitespace collapse — before storage).
- `method`: `embedded` or `ocr`.
- `ocr_confidence`: optional mean confidence.
- `layout`: optional JSON with per-page layout captured from embedded PDFs —
  text lines with bounding boxes and image regions — used by format-profile
  learning. `NULL` for OCR/scanned pages and documents ingested before
  layout capture.

### `Certificate`

One certificate row per document, enforced by a `OneToOneField`.

- `student_name`.
- `language_literal`, `language` (catalog FK).
- `entity_literal`, `entity` (catalog FK).
- `issuing_body_literal`, `test_center_literal`.
- `exam_literal`, `exam` (catalog FK).
- `level_literal`, `cefr_level`, `cefr_source` (`explicit`,
  `approved_rule`, `manual`).
- `equivalence`: catalog `Equivalence` the level was resolved from, when
  applicable.
- `score_literal`.
- `issue_date`, `exam_date`, `result_date`, `detected_date`; `date_texts`
  retains raw date wording keyed by category.
- `certificate_code`.
- `evidence`, `field_confidence` (JSON); `confidence` (overall; blends
  extraction confidence with the format score when available).
- `format_score`, `format_cohort`: learned-format match result and the
  profile cohort it was scored against.
- `is_language_certificate`: nullable until classification.
- `multiple_certificates_suspected`.
- `review_status`: `pending`, `approved`, `rejected`, `validated`.
- `review_reasons`: JSON list of reason codes.
- `manual_fields`: JSON list of field names a human edited during review;
  those fields are frozen against automatic re-extraction until released.
- `prompt_version`.
- `pre_detection`: JSON record of the deterministic issuer/type
  pre-detection pass (result, confidence, margin, candidates, classifier
  fallback use).
- `extraction_run`: FK to the `ExtractionRun` that produced the current
  extraction.
- `veracity_score`, `veracity_components`, `veracity_weights_version`,
  `veracity_computed_at`: numeric review-aid score with its component
  breakdown and the weights version used.
- `source_comparison`: JSON field-level comparison against a
  verifier-returned source document.
- `created_at`, `updated_at`.

### `ReviewEvent`

- `certificate`: parent certificate.
- `event_type`: `edit`, `validate`, `approve`, `reject`, `reprocess`,
  `learn`.
- `actor`: user, nullable if deleted.
- `reason`: rejection or operational reason.
- `before`, `after`: JSON snapshots of affected fields. Learning runs are
  recorded on the triggering approve/validate event via their outcome payload.
- `created_at`; default ordering is chronological.

`edit` events also serve as the audit trail for manual-field freezes;
`learn` events are emitted by `learn_from_history` backfills.

### `FieldLabelAlias`

- `field`: extraction field the alias maps to (`student_name`, `score`, ...).
- `alias`, `normalized_alias`: printed label and its normalized form.
- `scope_entity`: optional catalog entity scope; null means global.
- `scope_key`: `"global"` or the entity id, computed on save.
- `source`: `manual` or `learned`.
- `lifecycle`: `candidate`, `active`, or `rejected`. Only `active` aliases
  feed extraction; learned aliases start as candidates and activate on
  corroboration or reviewer confirmation.
- `support_count`, `confidence`, `provenance`: learning bookkeeping.
- `is_active`: reviewer on/off switch; an alias must be both `active` in
  lifecycle and `is_active` to be used.
- `created_by`, `created_at`, `updated_at`.

### `ExtractionRun`

One row per extraction pass over a document:

- `document`, `certificate`: what was extracted.
- `status`: `running`, `completed`, `failed`.
- `model`, `prompt_version`, `profile`, `profile_version`: configuration
  that produced the result.
- `pre_detection`: JSON snapshot of the pre-detection result.
- `pass_count`, `fallback_used`, `fallback_model`: bounded retry/escalation
  bookkeeping.
- `latency_ms`, `error`, `started_at`, `finished_at`, `created_at`.

### `VerifierConfig`

Per-issuer verifier configuration stored as data:

- `entity`: optional catalog entity the config belongs to.
- `host`: allowed verifier hostname (validated).
- `code_pattern`: optional regex used to recognize verification codes.
- `url_template`: optional URL template with `{code}`/`{document_id}`
  placeholders; must be an http(s) URL on `host`.
- `success_criteria`: JSON success markers/content checks.
- `source_document_parser`, `source_field_patterns`: how to parse and
  compare a verifier-returned source document.
- `timeout_seconds`, `is_active`, `created_by`, `created_at`, `updated_at`.

### `EvaluationRun` / `EvaluationCase`

Offline extraction evaluation storage:

- `EvaluationRun`: `status` (`queued`, `running`, `completed`, `failed`),
  `set_name`/`set_version` of the golden set used, `config` snapshot,
  `metrics`, `comparison` vs a baseline run, `baseline_run` FK, `actor`,
  `code_revision`, `started_at`/`finished_at`/`created_at`.
- `EvaluationCase`: one golden-set case per human-confirmed certificate —
  `set_name`/`set_version`, `certificate` FK, `entity`/`exam` FKs,
  `profile_version`, `source_text`, `expected` fields, `evidence`, and
  `context` (model/prompt context used). New golden-set versions create new
  rows; old versions are never mutated.

### `PaperlessSyncState`

Single-row watermark tracking the Paperless-ngx document-id sync cursor,
so the periodic sync does not rescan the whole document store.

## Reports (`reports`)

### `ReportJob`

- `status`: `queued`, `running`, `ready`, `error`.
- `filters`: JSON filter payload.
- `requested_by`: user, nullable.
- `artifact_path`: generated workbook path.
- `counts`: JSON summary of the rows included in the workbook.
- `error_reason`.
- `attempts`, `last_attempt_at`: retry bookkeeping for failed jobs.
- `completed_at`.
- `created_at`, `updated_at`.

## Catalog management

Master data (languages, entities, exams, aliases) is managed in Django admin
by the `admin` role. Roles are Django groups; only superusers or members of
the `admin` group can open the registered admin pages.

Equivalences have an in-app UI at `/catalog/` available to reviewers:

- the equivalence table with add/update forms,
- an entity + exam + aliases + equivalences creation form for onboarding a
  new certifying body without touching the admin.

See `docs/classification.md` for how equivalences are consumed and
`docs/review.md` for the review workflow that also learns catalog entries.

Seed the initial catalog:

```bash
.venv/bin/python manage.py seed_catalog
```

The command is idempotent: it creates the six languages, 26 entities, 45 exams,
their aliases, and two inactive CEFR placeholders. Re-running it does not
duplicate rows. CEFR placeholders never apply until an administrator supplies
an approver and reference and marks the rule active.

## Manual-review label

Paperless-ngx uses tags instead of folders. `APP_PAPERLESS_OTHER_TAG` defaults
to `Otros`; classification applies it to non-certificate documents, unresolved
language or entity records, and processing failures, and approval removes it.
Operators can map that tag to a Paperless storage path when a folder-like view
is preferred.

## Migrations

```bash
DB_ENGINE=sqlite DJANGO_DEBUG=true .venv/bin/python manage.py makemigrations --check
DB_ENGINE=sqlite DJANGO_DEBUG=true .venv/bin/python manage.py migrate
```

Tests build the schema from migrations, so a missing migration fails the suite.
