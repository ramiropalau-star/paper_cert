# Proposal

## Why

Format profiles currently learn almost no anchors: cohorts are segmented by
entity + single issuance year, so most cohorts hold 1–2 approved samples and
the corroboration threshold (`max(2, ceil(n/2))`) can never be met. Anchor
candidates are also limited to normalized text lines — layout information
(positions, images such as logos or student photos) is never captured — and
the embedded text layer arrives corrupted by the extractor (ligatures,
concatenated words, metadata lines like `language: english`). Reviewers also
cannot see what a learned profile actually looks like, so they cannot judge
whether it learned the right template.

## What Changes

- **Adaptive year cohorts**: keep per-year profiles, but when a cohort cannot
  reach the minimum sample count, merge its samples into an entity-level pool
  spanning multiple years so anchors can emerge. Anchors still require
  corroboration across distinct documents, so year-specific layouts simply
  fail to corroborate instead of forcing false anchors. Drift detection keeps
  working per cohort.
- **Layout capture at ingestion**: store per-page layout data (text line
  bounding boxes and image regions) extracted from the PDF so format learning
  can use positional/structural signals, not only text lines.
- **Layout-aware anchors**: extend anchor candidates beyond text lines to
  recurring structural features (e.g., presence and rough position of image
  regions such as logos or photo areas), still subject to corroboration.
- **Embedded text cleaning**: normalize/repair common embedded-text
  corruptions before text is used for anchors and extraction candidates, and
  exclude metadata-style lines (e.g., `language: english`) from anchor
  candidacy.
- **Anonymized profile preview**: the format profiles screen shows a rendered
  sample certificate for each profile with the student name redacted, so
  reviewers can visually verify the learned template.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `certificate-format-profiles`: adaptive cohort pooling across years,
  layout/positional anchors, anchor candidate filtering, and anonymized
  sample preview on the profiles screen.
- `document-ingestion`: per-page layout data capture and embedded-text
  cleaning before text is stored for downstream use.

## Impact

- `documents/services/format_profile.py` — cohort resolution, anchor
  candidate extraction, scoring fallback.
- `documents/models.py` — additive fields for per-page layout data and
  profile sample reference; migration required.
- Text extraction/intake path (`documents/services/`) — layout extraction
  (pypdf is already a dependency) and text cleaning.
- `documents/templates/documents/format_profiles.html` and the profiles
  view — anonymized sample rendering endpoint.
- No breaking changes; existing profiles remain valid and are rebuilt on the
  next approval.
