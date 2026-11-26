# Design

## Context

`FormatProfile` (entity, exam?, year) stores df-corroborated text anchors
learned from approved certificates. `score_document_format` computes a
weighted-recall score at classification, blended into `confidence`;
`format_score_threshold` (0.4) already feeds review reasons. Profiles are
only created/updated by `learn_format_profile` on approval — there is no
`is_active` flag, no UI, and no way to invalidate a bad cohort.

## Goals / Non-Goals

Goals:

- Surface format confidence in the document list with color coding.
- Let reviewers inspect, deactivate/reactivate, and rescore profiles.
- Keep scoring honest: inactive profiles contribute nothing.

Non-goals:

- Changing the anchor-learning algorithm or scoring formula.
- Per-anchor editing (profiles are regenerated from approved certs;
  deactivate is the correction mechanism).
- Blocking review actions on format score (already informational).

## Decisions

### D1: `is_active` flag on FormatProfile

Boolean default True + migration. `_score_against` and the cross-entity
scan filter `is_active=True`. Deactivation preserves anchors/samples for
audit and possible reactivation. Alternative (delete row) rejected:
loses history and makes "was this ever learned" unanswerable.

### D2: Doubtful-format filter param

`filter_documents` gains `format=doubtful`: documents whose certificate
has `format_score IS NOT NULL AND format_score < threshold`, plus docs
with an entity that HAS active profiles but `format_score IS NULL`
(scored-never / no cohort match is ambiguous — excluded to keep the
filter strict; document in UI copy). Composes with existing params.

Actually simpler and more honest: `format=doubtful` = `format_score <
threshold` OR (`format_score IS NULL` AND entity has ≥1 active profile
with sample_count ≥ min_samples). Implement via subquery/Exists.

### D3: List badge + row coloring

Annotate the document list queryset with the certificate's
`format_score` (already on Certificate — no extra query beyond existing
select_related). Badge shows `Formato XX%` with band classes
(good ≥ threshold, warn < threshold, none = no profile). Row gets a CSS
class `row-format-warn` when below threshold. Threshold read from
`settings.APP` same as scoring.

### D4: Management page

`/documents/format-profiles/` (reviewer+): table of profiles grouped by
entity → year → exam with sample_count, anchor count, status, actions
(deactivate/reactivate, rescore cohort). Rescore = recompute
`score_document_format` for certificates of that entity (+year via
`certificate_year`) and save; run synchronously (cohorts are small) with
a confirmation. Audit: reuse `ReviewEvent`? Profiles aren't certificates —
use Django messages + a `FormatProfileAudit` is overkill; record actor +
timestamp on the profile itself (`deactivated_by`, `deactivated_at`)
plus messages. Keep it simple: fields on model.

### D5: Rescore scope

Rescore button per profile row recomputes scores for certificates whose
`certificate_year()` matches the profile year AND entity matches (and
exam when segmented). Certificates are few (<100) — synchronous loop is
fine.

## Risks / Trade-offs

- [Stale scores after deactivation] → mitigated by explicit rescore
  action; scores are advisory anyway.
- [format_score NULL ambiguity] → filter treats NULL-with-profile as
  doubtful only when the entity actually has a qualifying profile;
  documented in UI.
- [Anchor noise] → unchanged; df-corroboration already filters.
