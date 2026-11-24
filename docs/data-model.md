# Data model and catalog management

The application uses three domain apps: `catalog` (reference data), `documents`
(intake, extracted records, and audit history), and `reports` (Excel jobs).
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
- `text`: page text.
- `method`: `embedded` or `ocr`.
- `ocr_confidence`: optional mean confidence.

### `Certificate`

One certificate row per document, enforced by a `OneToOneField`.

- `student_name`.
- `language_literal`, `language` (catalog FK).
- `entity_literal`, `entity` (catalog FK).
- `issuing_body_literal`, `test_center_literal`.
- `exam_literal`, `exam` (catalog FK).
- `level_literal`, `cefr_level`, `cefr_source` (`explicit`,
  `approved_rule`, `manual`).
- `score_literal`.
- `issue_date`, `exam_date`, `result_date`, `detected_date`; `date_texts`
  retains raw date wording keyed by category.
- `certificate_code`.
- `evidence`, `field_confidence` (JSON); `confidence` (overall).
- `is_language_certificate`: nullable until classification.
- `multiple_certificates_suspected`.
- `review_status`: `pending`, `approved`, `rejected`.
- `review_reasons`: JSON list of reason codes.
- `prompt_version`.
- `created_at`, `updated_at`.

### `ReviewEvent`

- `certificate`: parent certificate.
- `event_type`: `edit`, `approve`, `reject`, `reprocess`.
- `actor`: user, nullable if deleted.
- `reason`: rejection or operational reason.
- `before`, `after`: JSON snapshots of affected fields.
- `created_at`; default ordering is chronological.

## Reports (`reports`)

### `ReportJob`

- `status`: `queued`, `running`, `ready`, `error`.
- `filters`: JSON filter payload.
- `requested_by`: user, nullable.
- `artifact_path`: generated workbook path.
- `error_reason`.
- `completed_at`.
- `created_at`, `updated_at`.

## Catalog management

The admin role manages catalog data and users in Django admin. Roles are
Django groups; only superusers or members of the `admin` group can open the
registered admin pages.

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
