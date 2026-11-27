# Tasks

## 1. Schema and dependencies

- [x] 1.1 Add `PyMuPDF` to `requirements.txt` (pinned, published >7 days ago), rebuild the app image and confirm `import fitz` works inside the container
- [x] 1.2 Add `DocumentPage.layout` JSONField (null/blank) and make `FormatProfile.year` nullable (NULL = entity pool); generate and apply the migration; verify `manage.py migrate` runs clean and existing rows are untouched

## 2. Embedded text cleaning

- [x] 2.1 Create `documents/services/text_clean.py` with conservative cleaning (NFKC, whitespace collapse, control-char strip, small explicit repair map); write unit tests covering corrupted fixtures (`Englishmbridgeessment`-style artifacts handled conservatively — no unbounded rewriting) and clean-text passthrough
- [x] 2.2 Wire cleaning into `acquire_text` for embedded PDF pages in `documents/services/text.py`; verify via test that stored `DocumentPage.text` is cleaned and OCR pages are unaffected
- [x] 2.3 Exclude metadata-style lines (`^[a-z][a-z0-9_]*:\s`) from anchor candidacy in `format_profile.py` `_candidate_lines`; add regression test that `language: english` never becomes an anchor while `Date taken:` still can

## 3. Layout capture at ingestion

- [x] 3.1 Add `_pdf_layouts(data)` helper extracting per-page `{"lines": [...], "images": [...]}` via fitz, best-effort (errors → `layout=None`); unit-test with a generated PDF containing text + an image
- [x] 3.2 Persist layout in `_save`/`_embedded_pages` flow (`DocumentPage.layout`); verify end-to-end that an embedded PDF page stores non-empty layout and a scanned/OCR page stores NULL
- [x] 3.3 Add a watcher/reprocess path note: layout backfill for existing approved docs is optional — document the management command or skip decision in code comments; verify no regression in `acquire_text` idempotency tests

## 4. Adaptive cohorts and layout anchors

- [x] 4.1 Implement entity pool profile maintenance in `format_profile.py`: on rebuild, create/update the `year=NULL` profile from all approved entity samples; per-year profiles keep working for drift; verify pool profile appears with correct `sample_count` in tests
- [x] 4.2 Update cohort resolution/scoring to prefer exact `(entity, exam?, year)` → `(entity, exam?, year=NULL)` → `(entity, year=NULL)`; verify scoring tests cover each fallback level
- [x] 4.3 Add layout anchor candidates: position-bucketed text lines and image-region buckets, same corroboration threshold, stored with `kind` field; verify anchors like `image:top-right` emerge only with corroboration and one-off photos don't
- [x] 4.4 Update format score to count matched layout anchors; verify score changes in tests and missing layout anchors don't penalize beyond quality weight
- [x] 4.5 Update `format_profiles` view/context and template to show pool profiles distinctly (e.g., "Todos los años") and display anchor `kind`; verify page renders for pool + year profiles

## 5. Anonymized template preview

- [x] 5.1 Add staff-only preview endpoint that renders page 1 of a cohort sample via fitz, redacts `student_name` occurrences (and NPA if present) with opaque boxes, caches per `(profile_id, version)`; verify PNG returned and name pixels covered in test
- [x] 5.2 Add "Sin muestra disponible" fallback for non-renderable/missing samples and for name-as-image cases (never serve unredacted personal data); verify fallback renders correctly
- [x] 5.3 Add preview link/thumbnail on `format_profiles.html`; verify end-to-end in browser preview

## 6. Verification and deploy

- [x] 6.1 Run full pytest suite and `ruff check`/`ruff format --check`; all green
- [x] 6.2 Rebuild app image, redeploy, and validate on real data: approve/rebuild produces pool profiles with non-empty anchors on the Cambridge/Entity-3 cohort and the preview shows a redacted certificate
- [x] 6.3 Update `docs/` review/format-profile documentation if behavior visible to reviewers changed

## Workflow follow-up

- After deploy, optionally re-run text acquisition on approved documents to backfill `layout` (off-peak); not required for correctness.
