# Proposal

## Why

Certificates whose entity, exam, or language literal does not match the
catalog land in review with `unknown_entity` / `unknown_language` /
`equivalence_not_found`, but today the only remedies are manual field edits
(one certificate at a time) or Django admin (entities, exams, aliases are not
editable in-app). Reviewers need a fast path: see at a glance which records
are blocked by missing catalog data, jump to the entity, and add or configure
it — including its UV L2 equivalences — without leaving the review flow.

## What Changes

- **Catalog-pending markers**: documents with unresolved `entity`, `exam`,
  or `language` literals show a visible "catálogo pendiente" badge in the
  document list, gallery, and review detail; the queue gains a filter for
  unresolved catalog references.
- **Entity detail page** (`/catalog/entities/<id>/`): browse an entity's
  aliases, exams, languages, `date_order`, and equivalences; reviewers can
  add aliases, exams, and equivalences and edit entity metadata in-app —
  capabilities previously limited to Django admin.
- **Inline catalog resolution**: from the review detail page, an unresolved
  literal offers a "Resolver" action that lets the reviewer pick an existing
  catalog entry (with search) or create a new entity/exam inline (prefilled
  with the printed literal), assign it to the certificate, register the
  literal as an alias, and optionally reclassify the document.
- **Equivalence definition**: equivalences can be added/edited from the
  entity detail page (reusing the existing equivalence form logic), so a
  newly onboarded exam can be fully configured in one place.
- All resolution writes reuse the existing review audit trail
  (`ReviewEvent`) and respect role requirements (`viewer` read-only,
  `reviewer`/`admin` write).

## Capabilities

### New Capabilities

- `catalog-management`: in-app browsing and editing of catalog master data —
  entity detail views, alias/exam/equivalence management, and entity
  onboarding beyond the current equivalence-only UI.

### Modified Capabilities

- `review-workflow`: new inline catalog-resolution action on the review
  detail page and links from unresolved literals to catalog pages.
- `review-experience`: catalog-pending badges and an unresolved-catalog
  filter so reviewers can spot catalog gaps without decoding reason codes.

## Impact

- `catalog/`: new views, URLs, and templates for entity detail and
  resolution helpers; extends the existing `/catalog/` UI.
- `documents/`: review detail template gains resolve links/badges; list and
  gallery templates gain the pending-catalog marker; filters gain an
  unresolved-catalog option.
- `documents/services/`: a resolution service that assigns catalog FKs,
  creates aliases/exams/entities idempotently, writes `ReviewEvent`s, and
  optionally triggers reclassification — reusing normalization and learning
  helpers where possible.
- No new dependencies, no schema changes expected (all target models
  already exist).
