# Design

## Context

See `proposal.md` for motivation. Relevant current state:

- `/catalog/` today only exposes the equivalence table and a combined
  entity+exam+equivalences creation form (`catalog/views.py`); entity
  metadata, aliases, and exam management still require Django admin.
- Review detail (`documents/templates/documents/detail.html`) shows resolved
  names or raw literals; unresolved literals render as plain text with a
  warning glyph but no action.
- `documents/services/learning.py` already knows how to create aliases
  idempotently (`normalized_alias` unique) and how review events are
  recorded; `documents/management/commands/reclassify_certificates.py`
  contains the state juggling needed to re-run classification on a
  `pending_review` document.
- `catalog.normalization.normalize_catalog_text` is the single
  normalization used by aliases and matching.

## Goals / Non-Goals

**Goals:**

- One-click path from an unresolved literal in review to a resolved catalog
  link, with alias registration and audit.
- In-app entity page covering aliases, exams, `date_order`, `is_active`,
  and per-exam equivalences.
- Visible catalog-gap markers and a dedicated queue filter.

**Non-Goals:**

- No bulk catalog import or CSV upload.
- No changes to matching rules, learning triggers, or format profiles.
- No new user roles; `viewer` stays read-only, `reviewer`/`admin` write.
- Language creation stays out of scope (the six seeded languages are
  fixed); resolving a language literal only picks an existing `Language`
  and registers an alias.

## Decisions

### D1 — Resolution lives in a dedicated service, not in the view

New `documents/services/catalog_resolution.py` exposes
`resolve_catalog_field(certificate, field, target, actor, *, reclassify)`.
It assigns the FK, keeps the literal, ensures the alias row
(`EntityAlias`/`ExamAlias`/`LanguageAlias`) via `get_or_create` on
`normalized_alias`, writes a `ReviewEvent` (`event_type=edit`, before/after
catalog ids), and optionally reclassifies. Views stay thin; the same
service can later be reused by learning or bulk flows.

Alternative considered: reusing `learning.py`'s alias helpers directly in
the view — rejected because resolution also assigns FKs and writes events,
which is workflow logic, not learning logic.

### D2 — Entity creation happens through the resolve flow, not a general
entity CRUD

The entity detail page edits metadata/aliases/exams/equivalences but does
not offer entity create/delete (still admin for deletes). New entities are
created implicitly when a reviewer resolves a literal with "crear nueva":
the literal becomes the canonical name and its normalized form the first
alias. This matches the spec (resolution creates entity+alias) and avoids
duplicating `entity_create`'s multi-field form.

### D3 — Reuse the reclassify state pattern via a shared helper

`reclassify_certificates` currently inlines "set `EXTRACTED` →
`classify_certificate`". Extract that into a small service function
(e.g. `documents/services/reclassification.py::reclassify_document`)
used by both the command and the resolution view, so behavior (manual
field freezes, reason recomputation, `Otros` label refresh) stays
identical.

### D4 — Resolve UI is a dedicated page, not a modal

`GET /catalog/resolve/?document=<id>&field=entity|exam|language` renders a
searchable picker (existing entries filtered by normalized text) plus a
"create new" section prefilled with the literal, an entity/language scope
selector where relevant (exam resolution requires the resolved entity),
and a "reclasificar" checkbox (default on). A dedicated page keeps the
review detail simple and works without JS.

### D5 — Catalog-pending badge is computed, not stored

Unresolved = literal non-empty AND FK null. Annotate the document
queryset (`entity_literal != "" AND entity IS NULL`, etc.) for list and
gallery, and compute the same flags in the detail view. No schema change;
the badge stays correct as resolutions happen.

### D6 — Equivalence forms redirect back to the entity page

Extend `equivalence_add`/`equivalence_update` to honor a `next`
parameter (validated to stay within `/catalog/`) so forms embedded in the
entity page return there; default remains the equivalence table.

## Risks / Trade-offs

- [Alias collision: literal's normalized form already belongs to another
  entity] → resolution reports the conflict and offers only the existing
  assignment or an explicit admin path; never silently reassigns.
- [Exam ambiguity: same exam name under multiple entities] → exam picker
  is scoped to the certificate's resolved entity; if the entity is also
  unresolved, the UI forces resolving the entity first.
- [Reclassification cost] → classification is deterministic and cheap (no
  LLM call); `--reextract` is never triggered by resolution.
- [Reviewer creates near-duplicate entities with slightly different
  names] → accepted risk; aliases and the catalog-pending badge make
  duplicates visible, and `learn_from_history`/admin can merge later.
- [Badge query cost on large lists] → single annotated EXISTS-style
  conditions per row set; indexes on the FK/literal columns already
  exist or are cheap at this scale.

## Migration Plan

No data migration. Deploy = rebuild `app`/`watcher` images. Rollback =
redeploy previous image; new URLs 404 harmlessly and badges/filters are
additive only.
