# Design

## Context

See proposal.md — Why. Relevant current state:

- `DocumentPage` stores only `text`, `method`, `ocr_confidence` — no layout.
- `FormatProfile` (catalog app) is keyed by `(entity, exam?, year)`;
  `year` is a required positive integer. Anchors are `[{"text", "df"}]`
  corroborated within one cohort via `max(2, ceil(n/2))`.
- Text comes from `pypdf` `page.extract_text()` (embedded) or the OCR
  service. pypdf gives no coordinates; PyMuPDF (`fitz`) is not a dependency.
- Pillow is already a dependency; no PDF renderer exists in the stack.

## Goals / Non-Goals

Goals:

- Profiles learn real anchors with today's volume (~1–2 approved certs per
  entity-year) by pooling across years when a cohort is under-sampled.
- Layout signals (text positions, image regions) available for anchor
  learning and drift detection.
- Reviewers can visually verify a learned template without seeing student
  identity.
- Cheap, conservative embedded-text cleaning.

Non-goals:

- OCR-side layout capture (scans get text-only pages; layout is a PDF
  embedded-text feature in v1).
- Per-exam pool profiles (phase 2 if entity pools prove too coarse).
- Changing extraction prompts or field-label learning.

## Decisions

### D1 — Pooling via nullable `year` on FormatProfile

Make `FormatProfile.year` nullable; `year=NULL` means the entity-level pool
profile (exam stays NULL — pools are per entity across all exams/years).

- On rebuild, the system still maintains per-year profiles for drift
  detection, and additionally maintains the entity pool profile learned from
  all approved samples of that entity.
- Scoring prefers the most specific cohort: exact `(entity, exam?, year)` →
  `(entity, exam?, year=NULL)` → `(entity, year=NULL)` pool. First match with
  anchors wins; existing `_score_against` fallback union is replaced by this
  explicit hierarchy.
- Rationale over alternatives: a separate `PoolProfile` model duplicates
  anchors/version/drift machinery; widening cohort keys to year ranges
  fragments pools arbitrarily. NULL-year reuses everything (versioning,
  history, UI listing) and is a purely additive migration.

### D2 — Layout capture with PyMuPDF at ingestion

Add `PyMuPDF` (pinned) as a dependency. In `acquire_text`, for PDF pages that
use the embedded text path, also extract per-page layout:

- text lines with bounding boxes (fitz `page.get_text("dict")` blocks), and
- image regions (`page.get_image_info()` → bbox + size).

Store as JSON on a new `DocumentPage.layout` field:

```json
{"lines": [{"text": "...", "bbox": [x0,y0,x1,y1]}],
 "images": [{"bbox": [...], "width": w, "height": h}]}
```

- Only populated for embedded-PDF pages; OCR/scanned pages get `layout=NULL`.
- Layout extraction is wrapped best-effort: any fitz error logs and stores
  `layout=NULL` — it never blocks ingestion (per spec).
- Rationale: one library gives both coordinates and rendering for D4.
  pypdf's visitor API can give text coordinates but not reliable image
  placement, and cannot render pages for the preview.

### D3 — Layout anchors as corroborated structural tokens

Anchor candidates gain a second family alongside text lines:

- **Position-bucketed text anchors**: a recurring text line is upgraded to a
  layout anchor when it also appears in the same coarse region bucket
  (e.g., top/middle/bottom × left/center/right of the page) across
  corroborating samples.
- **Image-region anchors**: recurring image bboxes (same bucket, similar
  aspect) become anchors like `image:top-right`.

Both obey the same `max(2, ceil(n/2))` corroboration and are stored in the
same `anchors` JSON with a `kind` field (`text` | `layout`) so reviewers and
scoring can distinguish them. Scoring counts a layout anchor as matched when
the incoming document has a compatible feature in the same bucket.

- Rationale: buckets (not exact coordinates) survive minor template shifts
  between centers/years — which is exactly the variance the user described.
- Alternative rejected: exact coordinate matching — too brittle across
  centers that shift elements by a few mm.

### D4 — Anonymized preview via fitz rendering + name redaction

New view/endpoint on the format profiles screen:

- Pick the most recent approved sample certificate of the profile's cohort
  (pool profiles use any entity sample).
- Download original from Paperless store, render page 1 with fitz at ~110
  DPI, draw opaque boxes over every `search_for(student_name)` hit (plus the
  NPA string if present).
- Serve the PNG through a Django view (staff-only, `send_file`-style); cache
  per `(profile_id, version)` in memory/django cache — no new model needed.
- Fallback: no renderable sample → template shows "Sin muestra disponible".
- Redaction limitation: only literal name occurrences are covered; a name
  rendered as an image (scanned certs) cannot be redacted → for those,
  preview falls back to the extracted text lines with the name removed, or
  shows the unavailable state. Logged as a known limitation.

### D5 — Conservative embedded-text cleaning

New `documents/services/text_clean.py` applied when building page text for
embedded PDFs (before storing `DocumentPage.text`):

- NFKC normalization + whitespace collapse (extends existing catalog
  normalization).
- Repair map for reliably-detectable artifacts observed in real data
  (e.g., doubled letters from OCR-layer merges are NOT auto-fixed —
  unbounded; only a small explicit map like `ﬁ`→`fi` remnants post-NFKC,
  stray control chars).
- **Anchor-candidate filtering** (the effective metadata cleanup): lines
  matching `^[a-z][a-z0-9_]*:\s` (lowercase snake `key: value`, e.g.
  `language: english`) are excluded in `_candidate_lines`, not from stored
  text — stored text stays faithful to the document for evidence quotes.

- Rationale: mutating stored text breaks evidence traceability; filtering at
  candidacy fixes the observed `language: english` anchor pollution without
  touching reviewer-visible text. The spec's "stored text uses repaired
  form" is satisfied for unambiguous repairs only.

## Risks / Trade-offs

- PyMuPDF adds a native dependency to the image → pin version, verify build
  in Docker; fallback: layout stays NULL and feature degrades gracefully.
- Pool profiles may learn cross-year boilerplate that hides year drift →
  per-year profiles still exist and drift detection runs per cohort; pool is
  additive, not a replacement.
- Entity pools with exams mixed (e.g., Cambridge + TOEFL under one entity)
  could corroborate generic English-cert boilerplate → acceptable: those
  lines ARE shared format signals; exam-specific anchors still come from
  per-exam/year cohorts when they reach threshold.
- Rendering every preview on demand is slow → cache by profile version;
  render at 110 DPI, single page.
- Name redaction misses stylized/name-as-image cases → fallback state, never
  show unredacted personal data.

## Migration Plan

1. Additive migration: `DocumentPage.layout` (JSON, null),
   `FormatProfile.year` → nullable. No data backfill required; existing
   pages keep `layout=NULL` and old profiles keep working.
2. Deploy code; new ingestions populate layout. Optionally re-run text
   acquisition on approved docs later to backfill layout (separate task,
   off-peak).
3. Rollback: revert deploy; nullable fields are harmless leftovers.

## Open Questions

- Whether OCR pages should get layout from the OCR service (it may already
  return word boxes) — deferrable; v1 treats OCR pages as layout-less.
- Exact DPI/cache TTL for previews — tune during implementation.
