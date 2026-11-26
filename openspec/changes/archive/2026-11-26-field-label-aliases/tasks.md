# Tasks

## 1. FieldLabelAlias model and service

- [x] 1.1 Create `FieldLabelAlias` model in `documents/models.py`
  (`field` choices mirroring extraction fields incl. date roles,
  `alias`, `normalized_alias`, `scope_entity` FK null=global,
  `scope_key` denormalized for uniqueness, `source` manual|learned,
  `is_active`, `created_by`, timestamps) + migration. Verify with
  `manage.py makemigrations`/`migrate` and a model test for
  normalization and duplicate rejection.
- [x] 1.2 Create `documents/services/field_aliases.py` with
  `aliases_for_document(document)` (global + entity-scoped when the
  certificate has a resolved entity, scoped first) and
  `aliases_for_fields(fields)`. Verify with unit tests covering
  global-only, scoped match, scoped precedence, inactive exclusion.

## 2. Alias-aware extraction

- [x] 2.1 Extend `build_messages`/`extract` entry points in
  `documents/services/extraction.py` to accept alias hints and append a
  "known labels" section to the user message; bump `PROMPT_VERSION` to
  `extraction-v7`. Verify prompt content includes aliases in a unit test.
- [x] 2.2 Extend `_fallback_student_name` label set and add alias lists
  for score/date fallbacks fed from `aliases_for_document`; cap injected
  aliases per field. Verify fallback tests: alias label recovers value,
  unknown label does not, cap respected.
- [x] 2.3 Wire the re-extract path (review service / management command)
  to pass document-scoped aliases. Verify re-extract of a classified doc
  uses scoped aliases and an unclassified doc uses global only.

## 3. Review UI: teach alias + management

- [x] 3.1 Add inline teach-alias form on `detail.html` next to empty /
  unverified literal fields: alias input, scope select (Global / this
  entity only when `certificate.entity` set), POST endpoint creating the
  alias (source=manual, actor=request.user) with role check (reviewer+).
  Verify with view tests: create global, create scoped, viewer 403,
  duplicate alias message.
- [x] 3.2 Add alias management page (list/create/edit/activate/
  deactivate) under review or catalog section, reviewer+ only. Verify
  with view tests for each action and role enforcement.
- [x] 3.3 Extend re-extract flow to snapshot literal fields before/after
  and render the diff on detail page; record in ReviewEvent. Verify
  re-extract shows changed values and unchanged fields are not listed.

## 4. Verification

- [x] 4.1 Run full test suite (`manage.py test` or project equivalent)
  and verify no regressions; run `openspec validate field-label-aliases
  --strict`.
