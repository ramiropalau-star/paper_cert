# Tasks

## 1. Catalog resolution service

- [x] 1.1 Create `documents/services/catalog_resolution.py` with
  `resolve_catalog_field(certificate, field, target, actor, *, reclassify)`
  supporting `entity`, `exam`, `language`: assigns the FK, preserves the
  literal, ensures the matching alias (`EntityAlias`/`ExamAlias`/
  `LanguageAlias`) via `get_or_create` on `normalized_alias`, writes a
  `ReviewEvent` (`event_type=edit`) with before/after catalog ids, and
  reports alias conflicts instead of reassigning. Verify with unit tests
  covering assign, alias creation, idempotent re-run, and conflict.
- [x] 1.2 Extract the reclassify state pattern from
  `reclassify_certificates` into a shared helper
  (`documents/services/reclassification.py::reclassify_document`) and make
  the command use it. Verify existing command tests still pass.

## 2. Entity detail page

- [x] 2.1 Add `GET /catalog/entities/<pk>/` view + template showing entity
  name, `is_active`, `date_order`, aliases, exams (language + equivalence
  counts), read-only for viewers, write controls for reviewers/admins.
  Verify with view tests for both roles.
- [x] 2.2 Add POST handlers on the entity page: edit `date_order`/`is_active`,
  add alias (idempotent via `normalized_alias`), create exam under the
  entity (optional language). Verify with tests for success, duplicate
  alias, and viewer 403.
- [x] 2.3 Embed per-exam "add equivalence" forms on the entity page reusing
  the existing validation; extend `equivalence_add`/`equivalence_update`
  to honor a validated `next` parameter so they redirect back. Verify with
  tests covering create, band validation, and redirect target.

## 3. Review integration

- [x] 3.1 Add `GET/POST /catalog/resolve/` page: params `document`, `field`;
  searchable existing-entry picker, "create new" prefilled with the literal,
  entity/language scoping for exams, `reclasificar` checkbox. Wire POST to
  `resolve_catalog_field` + optional `reclassify_document`, then redirect
  to the document detail. Verify with tests for each field type, create-new
  path, alias conflict message, and viewer 403.
- [x] 3.2 Update `documents/templates/documents/detail.html`: unresolved
  literals (`entity`, `exam`, `language`) render a "Resolver" link to the
  resolve page preserving the current document/field; resolved values link
  to the entity detail page when an entity FK exists. Verify with template
  assertions in review tests.

## 4. Catalog-pending markers and filter

- [x] 4.1 Annotate document list and gallery querysets with unresolved
  catalog flags (literal non-empty AND FK null for entity/exam/language)
  and render a "catálogo pendiente" badge in `list.html`, `gallery.html`,
  and `detail.html`. Verify with tests asserting badge presence/absence.
- [x] 4.2 Add an `catalog=pending` filter option to the document queue
  (AND-combined with existing filters) listing documents with at least one
  unresolved catalog literal. Verify with filter tests.

## 5. Verification

- [x] 5.1 Run the full test suite (`pytest`) and `manage.py check`; fix any
  regressions. Verify all green.
- [x] 5.2 Manual smoke in the running stack: open a pending-review document
  with `unknown_entity`, resolve it via the new flow, confirm alias +
  ReviewEvent + reclassification clearing `unknown_entity`, and confirm
  the entity page shows the new exam/equivalence.
- [x] 5.3 Update `docs/` (review.md, data-model.md if needed, and the doc
  index if a new page is added) to describe resolution, entity page, badge,
  and filter. Verify docs render and match implemented routes.
