# Design

## Context

See proposal.md — Why. Extraction label knowledge is hardcoded in
`documents/services/extraction.py`: `_NAME_LABELS` for the student-name
fallback, `_SCORE_LABEL_RE`/`_ISSUE_DATE_LABEL_RE` for score/date fallbacks,
and per-field label lists inside `SYSTEM_PROMPT`. The pipeline order is
`TEXT_READY → EXTRACTED → CLASSIFIED → PENDING_REVIEW`, so the entity FK is
only resolved after extraction; entity-scoped aliases can therefore only
apply on re-extract (when `certificate.entity` is already set), never on the
first pass.

## Goals / Non-Goals

Goals:

- Aliases as data, editable by reviewers without deploys.
- Global aliases usable on every extraction pass; entity-scoped aliases on
  re-extract of classified documents.
- Teach-alias UX anchored on empty/unverified fields in review.
- Reprocess shows before/after so the mapping is validated by a human.

Non-goals:

- Automatic alias learning from approved reviews (`source='learned'` is
  reserved in the schema; no auto-creation in this change).
- Per-exam or per-format-profile scoping (entity scope only).
- Changing evidence validation rules — alias-derived values go through the
  same verbatim-quote checks.
- Generalizing fallbacks into a fully data-driven engine; aliases extend the
  existing per-field fallback lists.

## Decisions

### D1: `FieldLabelAlias` model in `documents`

Fields: `field` (choices mirroring `LITERAL_FIELDS` keys plus date roles),
`alias` (verbatim text), `normalized_alias` (via the same `_norm_text`
folding used for evidence), `scope_entity` (FK to `Entity`, null = global),
`source` (`manual`|`learned`), `is_active`, `created_by`, `created_at`,
`updated_at`.

Uniqueness: Postgres treats NULLs as distinct, so `(field,
normalized_alias, scope_entity)` cannot dedupe global aliases via
`unique_together`. Store a denormalized `scope_key` CharField (`"global"` or
the entity id as string) maintained on save, with `UniqueConstraint(field,
normalized_alias, scope_key)`. The service layer keeps `scope_entity` as the
FK for queries/UI.

Alternatives considered: JSON field on Entity for scoped labels (rejected —
splits the model in two, no global listing/audit); proxy through
`FormatProfile` (rejected — profiles are per entity+year cohorts built by
learning, wrong granularity and lifecycle).

### D2: Alias resolution service `documents/services/field_aliases.py`

`aliases_for_document(document) -> dict[field, list[str]]` returns active
aliases, always including global ones and adding `scope_entity` matches when
`document`'s certificate has a resolved entity. `aliases_for_fields(fields)`
for admin/preview. Cached per request/task; the table is small so a
process-local TTL cache (e.g. 60s) is enough — invalidated implicitly.

Precedence: when both global and scoped aliases exist for a field, scoped
entries are listed first so prompt ordering and fallback search prefer them.

### D3: Prompt injection, not prompt rewrite

`build_messages` gains an optional `alias_hints` parameter. When non-empty,
the user message appends a short section: "Additional known labels for this
document: student_name may also appear as '…'; score may also appear as
'…'". The static `SYSTEM_PROMPT` stays unchanged except its hardcoded label
examples remain as the baseline. `PROMPT_VERSION` bumps to `extraction-v7`
because model-visible input changes.

Alternative considered: regenerating the whole system prompt per document —
rejected, it breaks prompt caching and makes behavior harder to reason about.

### D4: Fallbacks consume aliases per field

`_fallback_student_name` already matches `_NAME_LABELS`; it becomes
`_NAME_LABELS + aliases['student_name']`. Score/date fallbacks get parallel
alias lists (`_SCORE_LABEL_ALIASES`, `_ISSUE_DATE_LABEL_ALIASES`) seeded from
the existing regex label vocabulary where practical, extended by aliases.
Each fallback caps alias matches (first N sorted) to bound runtime.

### D5: Teach-alias UI on review detail

Next to each empty/unverified literal field, a "enseñar alias" affordance
opens an inline form: alias text input + scope select (Global / this entity,
only when `certificate.entity` is set) + confirm. POST creates the alias
(source=`manual`, actor=request.user) and redirects back with the reprocess
CTA. A management list page (`/catalog/field-aliases/` or review section)
lists aliases with activate/deactivate for reviewer+.

### D6: Reprocess reports field diffs

The existing re-extract endpoint already writes a `reextract` ReviewEvent.
Extend it (or the detail view) to snapshot literal fields before/after and
render a small diff ("student_name: vacío → 'John Doe'") so the reviewer
validates the mapping visually. No new pipeline stage.

## Risks / Trade-offs

- [Bad alias misleads the model] → Evidence validation unchanged; values
  still need verbatim quotes or land unverified. Reviewer sees diff before
  approving.
- [Prompt grows with many aliases] → Cap aliases injected per field (e.g.
  20, scoped first); admin page shows counts.
- [Alias learned for entity A pollutes global] → Scope defaults to global
  only when entity is unresolved; UI makes scope explicit, never implicit.
- [Normalized collision across scopes] → `scope_key` uniqueness prevents
  same alias+field in two scopes? No — same alias CAN exist globally and
  scoped; precedence rule handles it. True duplicates within a scope are
  blocked by the constraint.
- [Re-extract of unclassified doc can't use scoped aliases] → By design;
  teach-alias offers global scope when entity unresolved. Documented in UI
  copy.

## Migration Plan

1. Migration adds `FieldLabelAlias` (empty table — no data migration).
2. Deploy app; aliases start empty, behavior identical to today.
3. Reviewers teach aliases organically; rollback = deactivate rows or
  revert deploy (table can stay).

## Open Questions

- Whether learned-source auto-population from approved reviews should be a
  follow-up change (likely yes, once manual aliases prove their value).
